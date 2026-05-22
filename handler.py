from dataclasses import dataclass, asdict
import json
import os
import sqlite3
import logging
from datetime import datetime
import time
from dto import Detection
from tzlocal import get_localzone

from client import LuistervinkClient
from settings import DB_PATH, DATA_DIR, MAX_DETECTIONS_UPLOAD

log = logging.getLogger("task_processor")


def _connect() -> sqlite3.Connection:
    """Open the birdnet-go database and verify it uses the v2 schema.

    birdnet-go's v2 ("enhanced") datastore replaces the flat ``notes`` table
    with a normalized ``detections`` / ``labels`` structure. Raise early with a
    clear message if the database has not been migrated yet.
    """
    con = sqlite3.connect(DB_PATH)
    has_detections = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'detections'"
    ).fetchone()
    if has_detections is None:
        con.close()
        raise RuntimeError(
            f"No 'detections' table found in {DB_PATH}; the birdnet-go database "
            "has not been migrated to the v2 schema yet"
        )
    return con


class BaseHandler:
    type: str

    STATUS_IN_PROGRESS = "in_progress"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"

    def __init__(self, client: LuistervinkClient, spec: dict) -> None:
        self.client = client
        self.spec = spec

    def handle(self) -> str:
        """Handle the task and return a result."""
        raise NotImplementedError("Subclasses should implement this method.")


class DetectionSoundHandler(BaseHandler):
    type: str = "sound_request"
    spec: dict

    def handle(self) -> str:
        filepath = self._find_detection_filename()
        if filepath is None:
            log.warning("No detection found for the given spec.")
            return self._handle_no_sound("Detection not found")

        if not os.path.exists(filepath):
            log.error(f"Detection file does not exist: {filepath}")
            return self._handle_no_sound("Sound file not available")

        log.info(f"Found detection file: {filepath}")
        return self._handle_sound(filepath)

    def _find_detection_filename(self) -> str | None:
        """Find a detection in the database based on the spec."""
        # detections.detected_at is an absolute Unix epoch (seconds), so match
        # against it directly instead of formatting local date/time strings.
        utc_dt = datetime.fromisoformat(self.spec["timestamp"].replace("Z", "+00:00"))
        detected_at = int(utc_dt.timestamp())

        sql = """
            SELECT l.scientific_name, d.clip_name
            FROM detections d
            JOIN labels l ON l.id = d.label_id
            WHERE d.detected_at = ?
              AND l.scientific_name = ?
              AND d.confidence >= ?
        """
        with _connect() as con:
            detections = con.execute(
                sql,
                (
                    detected_at,
                    self.spec.get("scientific_name"),
                    self.spec.get("confidence"),
                ),
            ).fetchall()

        if len(detections) == 1:
            return self._construct_file_path(detections[0])
        return None

    def _handle_no_sound(self, status: str) -> None:
        """Handle cases where no detection sound is found."""
        url = f"/api/detections/{self.spec['id']}"
        response = self.client.put(url, data={"sound_reference": status})
        if response.status_code != 200:
            log.error(
                f"Failed to update detection: {response.status_code} {response.text}"
            )

    def _handle_sound(self, filepath: str) -> str:
        """Handle the case where a sound file is found."""
        with open(filepath, "rb") as f:
            files = {"sound": (os.path.basename(filepath), f, "audio/mpeg")}
            url = f"/api/detections/{self.spec['id']}/sound/"
            response = self.client.post(url, files=files)

        if response.status_code != 201:
            log.error(
                f"Failed to upload sound file: {response.status_code} {response.text}"
            )

    @staticmethod
    def _construct_file_path(detection: tuple[str]) -> str:
        """Construct the file path for the detection file."""
        _, clip_name = detection
        return f"{DATA_DIR}/clips/{clip_name}"


@dataclass
class ReloadDetectionsResult:
    uploaded: int = 0
    failed: int = 0
    skipped: int = 0
    index: int = 0
    message: str = ""

    def to_json(self) -> str:
        return json.dumps(asdict(self))


class ReloadDetectionsHandler(BaseHandler):
    type: str = "reload_detections"
    spec: dict
    result: ReloadDetectionsResult
    max_index: int
    task_id: str
    max_failures: int = 5

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        try:
            self.task_id = self.spec["id"]
            previous_result = json.loads(self.spec.get("results") or "{}")
            self.result = ReloadDetectionsResult(**previous_result)
            max_uploads = int(self.spec.get("max_batch_size", MAX_DETECTIONS_UPLOAD))
            self.max_index = self.result.index + max_uploads
        except Exception as e:
            self.result = ReloadDetectionsResult(message=str(e))
            self._post_results(self.STATUS_FAILED)
            raise e

    def handle(self) -> str:
        dt = datetime.fromisoformat(self.spec["date"].replace("Z", "+00:00"))
        date = dt.strftime("%Y-%m-%d")
        log.info(f"Reloading detections for date: {date}")

        detections = self._collect_detections(date)
        log.info(f"Collected {len(detections)} detections for date: {date}")

        self._upload_detections(detections)
        log.info(
            f"Processed detections, {len(detections) - self.result.index - 1} remaining"
        )

        status = (
            self.STATUS_COMPLETED
            if (self.result.index + 1) >= len(detections)
            else self.STATUS_IN_PROGRESS
        )
        self._post_results(status)

    def _collect_detections(self, date: str) -> list[Detection]:
        # Field order must correspond with the Detection dataclass.
        # detected_at is stored as a UTC Unix epoch; convert to a local date
        # to match the requested calendar day. Only 'species' labels are
        # uploaded (excludes noise/environment/device), and detections flagged
        # 'unlikely' by the ultrasonic validation filter are skipped.
        sql = """
            SELECT d.detected_at, l.scientific_name, d.confidence, d.latitude, d.longitude
            FROM detections d
            JOIN labels l ON l.id = d.label_id
            JOIN label_types lt ON lt.id = l.label_type_id
            WHERE date(d.detected_at, 'unixepoch', 'localtime') = ?
              AND lt.name = 'species'
              AND d.unlikely = 0
            ORDER BY d.detected_at ASC
        """
        with _connect() as con:
            detections = con.execute(sql, (date,)).fetchall()
        return [Detection(*detection) for detection in detections]

    def _upload_detections(self, detections: list[Detection]) -> None:
        consecutive_failures = 0

        for detection in detections[self.result.index :]:
            if self.result.index >= self.max_index:
                break
            if consecutive_failures >= self.max_failures:
                self._post_results(self.STATUS_FAILED)
                return

            # detected_at is an absolute Unix epoch; render it in system-local
            # time to keep the uploaded timestamp consistent with prior behaviour.
            timestamp = datetime.fromtimestamp(
                detection.detected_at, tz=get_localzone()
            )

            data = {
                "timestamp": timestamp.isoformat(),
                "scientificName": detection.scientific_name,
                "lat": detection.latitude,
                "lon": detection.longitude,
                "confidence": detection.confidence,
                "soundscapeId": 0,
                "soundscapeStartTime": 0,
                "soundscapeEndTime": 0,
            }

            try:
                response = self.client.post("/api/detections/", data=data)
                log.info(f"Luistervink POST Response Status - {response.status_code}")
                if response.status_code == 201:
                    self.result.uploaded += 1
                    consecutive_failures = 0
                elif (
                    response.status_code == 409
                ):  # conflict (detection existst already)
                    self.result.skipped += 1
                    consecutive_failures = 0
                else:
                    self.result.message = f"Unexpected response: {response.text}"
                    self.result.failed += 1
                    log.warning(self.result.message)
                    consecutive_failures += 1

            except BaseException as e:
                self.result.failed += 1
                self.result.message = f"Cannot POST detection: {e}"
                log.error(self.result.message)
                consecutive_failures += 1

            self.result.index += 1
            time.sleep(0.2)  # avoid overwhelming the server

    def _post_results(self, status: str) -> None:
        url = f"/api/tasks/{self.task_id}"
        data = {"status": status, "results": self.result.to_json()}
        response = self.client.put(url, data=data)
        if response.status_code != 200:
            log.error(f"Failed to update task: {response.status_code} {response.text}")
