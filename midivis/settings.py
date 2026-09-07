'''User settings persistence for MidiVis. Saved to %APPDATA%/MidiVis2/settings.json.

Atomic-write pattern carried forward as-is from the old MidiVis repo (settings.py,
called out as "solid" in the rewrite plan) — write to a temp file then os.replace()
so a crash mid-write can't corrupt the settings file.
'''

import os
import json
import tempfile

SETTINGS_DIR = os.path.join(os.environ.get(
    'APPDATA', os.path.expanduser('~')), 'MidiVis2')
SETTINGS_FILE = os.path.join(SETTINGS_DIR, 'settings.json')
MAX_RECENT = 5

_DEFAULTS = {
    'recent_files': [],   # list of absolute paths, most recent first
    'midi_inputs': {},
    'recording': {
        'channel': 0,
        'program': 0,
    },
    'audio': {
        'fluidsynth_bin': '',  # folder containing libfluidsynth-3.dll
        'soundfont': '',       # path to a .sf2 file
    },
}


def load():
    '''Load settings from disk. Returns defaults for any missing keys.'''
    if not os.path.isfile(SETTINGS_FILE) or os.path.getsize(SETTINGS_FILE) == 0:
        return _defaults_copy()
    try:
        with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        for k, v in _DEFAULTS.items():
            if k not in data:
                data[k] = v.copy() if isinstance(v, dict) else v
            elif isinstance(v, dict):
                for sub_k, sub_v in v.items():
                    data[k].setdefault(sub_k, sub_v)
        # Drop any recent files that no longer exist on disk
        data['recent_files'] = [
            p for p in data['recent_files'] if os.path.isfile(p)]
        return data
    except Exception as e:
        print(f'Failed to load settings: {e}')
        return _defaults_copy()


def save(settings):
    '''Persist settings to disk atomically so a crash can't leave a corrupt file.'''
    os.makedirs(SETTINGS_DIR, exist_ok=True)
    try:
        fd, tmp = tempfile.mkstemp(dir=SETTINGS_DIR, suffix='.tmp')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=2)
            os.replace(tmp, SETTINGS_FILE)
        except Exception:
            os.unlink(tmp)
            raise
    except Exception as e:
        print(f'Failed to save settings: {e}')


def add_recent_file(settings, path):
    '''Prepend path to recent_files, deduplicate, cap at MAX_RECENT, then save.'''
    recent = [r for r in settings.get('recent_files', []) if r != path]
    recent.insert(0, path)
    settings['recent_files'] = recent[:MAX_RECENT]
    save(settings)


def _defaults_copy():
    return {k: (v.copy() if isinstance(v, dict) else v) for k, v in _DEFAULTS.items()}
