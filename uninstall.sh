#!/bin/bash

TARGET_DIR="$HOME/luistervink"
ASSUME_YES=0
for arg in "$@"; do
    case "$arg" in
        -y|--yes) ASSUME_YES=1 ;;
    esac
done

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
GRAY='\033[0;90m'
NC='\033[0m' # No Color

print_message() {
    local nonewline=${3:-""}
    local message="$1"
    local color="$2"
    if [ "$nonewline" = "nonewline" ]; then
        echo -en "${color}${message}${NC}"
    else
        echo -e "${color}${message}${NC}"
    fi
}

confirm() {
    if [ "$ASSUME_YES" -eq 1 ]; then
        return
    fi

    if [ ! -t 0 ] && [ ! -r /dev/tty ]; then
        print_message "❌ No terminal available to read confirmation." "$RED"
        print_message "💡 Run non-interactively with: curl -s <url> | bash -s -- --yes" "$YELLOW"
        exit 1
    fi

    print_message "⚠️  This will remove $TARGET_DIR and the luistervink cron entry from /etc/crontab." "$YELLOW"
    print_message "Continue? [y/N] " "$YELLOW" "nonewline"
    if [ -t 0 ]; then
        read -r reply
    else
        read -r reply < /dev/tty
    fi
    case "$reply" in
        y|Y|yes|YES) ;;
        *)
            print_message "Aborted." "$RED"
            exit 1
            ;;
    esac
}

remove_cron_job() {
    if sudo grep -q '#luistervink' /etc/crontab; then
        print_message "🗑  Removing luistervink cron entry from /etc/crontab..." "$GRAY"
        sudo sed -i '/luistervink/,+1d' /etc/crontab
    else
        print_message "ℹ️  No luistervink cron entry found in /etc/crontab." "$GRAY"
    fi
}

remove_luistervink_dir() {
    if [ -d "$TARGET_DIR" ]; then
        print_message "🗑  Removing $TARGET_DIR..." "$GRAY"
        rm -rf "$TARGET_DIR"
    else
        print_message "ℹ️  $TARGET_DIR does not exist." "$GRAY"
    fi
}

confirm
remove_cron_job
remove_luistervink_dir

print_message "✅ Luistervink task processor has been uninstalled." "$GREEN"
