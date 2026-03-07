#!/bin/bash

CONFIG_DIR="$HOME/birdnet-go-app/config"
DATA_DIR="$HOME/birdnet-go-app/data"
CONFIG_FILE="$CONFIG_DIR/config.yaml"

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

verify_config_file() {
    print_message "🔍 Checking for BirdNET-Go config file at: $CONFIG_FILE" "$GRAY"
    if [ -f "$CONFIG_FILE" ]; then
        print_message "✅ Config file found: $CONFIG_FILE" "$GREEN"
    else
        print_message "❌ Config file not found: $CONFIG_FILE" "$RED"
        print_message "⚠️  BirdNET-Go does not appear to be installed for this user." "$YELLOW"
        print_message "💡 Make sure the Luistervink task processor is installed as the same user that installed BirdNET-Go." "$YELLOW"
        exit 1
    fi
}

verify_config_file

update_paths() {
    local settings_file="${HOME}/luistervink/settings.py"
    sed -i "s|^CONFIG_DIR = .*|CONFIG_DIR = '$CONFIG_DIR'|" "$settings_file"
    sed -i "s|^DATA_DIR = .*|DATA_DIR = '$DATA_DIR'|" "$settings_file"
}

install_or_update_luistervink() {
    local branch=main
    local repo_url="https://github.com/gijsbertbas/luistervink-integrations.git"
    local target_dir="${HOME}/luistervink"
    
    if [ -d "$target_dir" ]; then
        print_message "📦 Luistervink directory exists, updating..." "$GRAY"
        cd "$target_dir"
        git pull origin $branch
    else
        print_message "📦 Cloning Luistervink repository..." "$GRAY"
        git clone -b $branch --depth=1 "$repo_url" "$target_dir"
    fi

    update_paths
}

apt-get install -y python3-venv git

install_or_update_luistervink

python3 -m venv ${HOME}/luistervink/venv
${HOME}/luistervink/venv/bin/pip install -r ${HOME}/luistervink/requirements.txt

install_cron_job() {
    sudo sed -i '/luistervink/,+1d' /etc/crontab

    sudo tee -a /etc/crontab > /dev/null << EOF
#luistervink
*/10 * * * * $USER sleep \$(shuf -i 0-9 -n 1)m; /$HOME/luistervink/venv/bin/python $HOME/luistervink/taskcheck.py 2>&1 | /usr/bin/logger -t luistervink_task_check
EOF
}

install_cron_job

print_message "✅ Luistervink task processor is installed or updated." "$GREEN"
