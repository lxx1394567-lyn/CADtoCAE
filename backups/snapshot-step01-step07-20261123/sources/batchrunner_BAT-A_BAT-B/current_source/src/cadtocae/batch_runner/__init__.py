"""Independent, checkpoint-based Abaqus batch scheduling."""
from pathlib import Path
VERSION = '4.0-dev'

def cae_worker_source():
    return Path(__file__).with_name('cae_worker.py').read_text(encoding='utf-8-sig')
