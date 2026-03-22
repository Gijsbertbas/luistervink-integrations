import logging
from client import LuistervinkClient
from dto import Task
from handler import DetectionSoundHandler, ReloadDetectionsHandler
from settings import get_settings, MAX_TASKS
import sys

log = logging.getLogger("task_processor")
log.setLevel(logging.INFO)
formatter = logging.Formatter("[%(name)s][%(levelname)s] %(message)s")
handler = logging.StreamHandler(stream=sys.stdout)
handler.setLevel(logging.INFO)
handler.setFormatter(formatter)
log.addHandler(handler)


class TasksProcessor:
    def __init__(self, client: LuistervinkClient):
        self.client = client
        self.handlers = [
            DetectionSoundHandler,
            ReloadDetectionsHandler,
        ]

    def process_tasks(self):
        """Process tasks from the Luistervink API."""
        tasks = self.collect()
        log.info(f"{len(tasks)} task{'s' if len(tasks) == 1 else ''} collected")

        if len(tasks) > MAX_TASKS:
            log.warning(f"Limiting to the first {MAX_TASKS} tasks")

        for task in tasks[:MAX_TASKS]:
            log.info(
                f"[Luistervink] Processing task: {task.type} with spec: {task.spec}"
            )
            try:
                self.process(task)
                log.info(f"[Luistervink] Task processed successfully")
            except Exception as e:
                log.error(f"[Luistervink] Failed to process task: {task.type}: {e}")

    def process(self, task: Task):
        for handler in self.handlers:
            if handler.type == task.type:
                return handler(self.client, task.spec).handle()
        log.warning(f"[Luistervink] No handler found for task type: {task.type}")

    def collect(self) -> list[Task]:
        """Collect tasks from the Luistervink API."""
        try:
            response = self.client.get("tasks")
            if response.status_code != 200:
                log.error(
                    f"[Luistervink] Failed to fetch tasks: {response.status_code} {response.text}"
                )
            tasks = response.json()
            return [Task(**task) for task in tasks]
        except Exception as e:
            log.error(f"[Luistervink] Error collecting tasks: {e}")
            return []


if __name__ == "__main__":
    settings = get_settings()
    if not settings["enabled"]:
        log.info("Luistervink integration not enabled, not processing further")
        sys.exit(0)

    client = LuistervinkClient(settings)
    processor = TasksProcessor(client)
    processor.process_tasks()
