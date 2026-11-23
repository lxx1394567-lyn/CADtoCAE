"""Launcher preferences; only persist configurations that have actually succeeded."""
import json
import os
from pathlib import Path
import shutil

def settings_path():
    return Path(os.environ.get('BATCHRUNNER_SETTINGS', str(Path(os.environ.get('LOCALAPPDATA', Path.home()))/'CADtoCAE/BatchRunner/settings.json')))

def load_preferences():
    try:
        return json.loads(settings_path().read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}

def detected_command():
    saved = load_preferences().get('command', [])
    if isinstance(saved, list) and saved and shutil.which(saved[0]):
        return saved
    if shutil.which('abaqus'):
        return ['abaqus']
    return []

def save_successful_configuration(command, environment):
    from .state import write_json
    if command and shutil.which(command[0]):
        write_json(settings_path(), dict(command=command, environment=environment))
