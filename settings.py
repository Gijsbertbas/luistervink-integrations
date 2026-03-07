import functools
from pathlib import Path
import yaml


# Assuming birdnet-go is installed with sudo
CONFIG_DIR = '/root/birdnet-go-app/config'
DATA_DIR = '/root/birdnet-go-app/data'

DB_PATH = f'{DATA_DIR}/birdnet.db'


@functools.cache
def get_settings(path: str = f'{CONFIG_DIR}/config.yaml') -> dict:
    config_path = Path(path)
    with config_path.open('r', encoding='utf-8') as f:
        settings = yaml.safe_load(f) or {}
    
    if 'luistervink' not in settings['realtime']:
        print('ERROR Luistervink not available, running this from the Luistervink branch??')
        return {}
        
    return settings['realtime']['luistervink']
