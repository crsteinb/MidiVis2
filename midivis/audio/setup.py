'''FluidSynth binary + SoundFont discovery and first-run configuration.

Old MidiVis hard-coded FLUIDSYNTH_BIN/SOUNDFONT as absolute paths that only
existed on the original developer's machine (midi_visualizer.py:43-44) — a
hard blocker for anyone else running the app. This replaces that with
settings-driven paths (settings.py's 'audio' dict): try common install
locations first, fall back to an interactive one-time prompt whose answer
gets persisted.
'''

from __future__ import annotations

import glob
import os

_DLL_NAME = 'libfluidsynth-3.dll'

_FLUIDSYNTH_BIN_GLOBS = [
    r'C:\Program Files\FluidSynth\bin',
    r'C:\Program Files\fluidsynth\bin',
    r'C:\tools\fluidsynth\bin',
    os.path.expanduser(r'~\fluidsynth\*\bin'),
    os.path.expanduser(r'~\scoop\apps\fluidsynth\current\bin'),
    r'C:\ProgramData\chocolatey\lib\fluidsynth\tools\*\bin',
]

_SOUNDFONT_GLOBS = [
    os.path.expanduser(r'~\Documents\**\*.sf2'),
    os.path.expanduser(r'~\Downloads\**\*.sf2'),
    r'C:\soundfonts\**\*.sf2',
    r'C:\Program Files\FluidSynth\sf2\**\*.sf2',
]


def find_fluidsynth_bin() -> str | None:
    '''Best-effort search of common install locations for libfluidsynth-3.dll.'''
    for pattern in _FLUIDSYNTH_BIN_GLOBS:
        for path in glob.glob(pattern):
            if os.path.isfile(os.path.join(path, _DLL_NAME)):
                return path
    return None


def find_soundfont() -> str | None:
    '''Best-effort search of common locations for a .sf2 file.'''
    for pattern in _SOUNDFONT_GLOBS:
        matches = glob.glob(pattern, recursive=True)
        if matches:
            return matches[0]
    return None


def prompt_for_fluidsynth_bin() -> str | None:
    '''Ask the user to locate the FluidSynth "bin" folder. Returns None if cancelled
    or the chosen folder doesn't actually contain libfluidsynth-3.dll.
    '''
    import tkinter as tk
    from tkinter import filedialog, messagebox

    root = tk.Tk()
    root.withdraw()
    messagebox.showinfo(
        'MidiVis setup',
        'MidiVis needs FluidSynth to play audio.\n\n'
        f'Select the "bin" folder of a FluidSynth install (the one containing {_DLL_NAME}).')
    path = filedialog.askdirectory(title='Select FluidSynth bin folder')
    root.destroy()
    if path and os.path.isfile(os.path.join(path, _DLL_NAME)):
        return path
    return None


def prompt_for_soundfont() -> str | None:
    '''Ask the user to locate a .sf2 SoundFont file. Returns None if cancelled.'''
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    path = filedialog.askopenfilename(
        title='Select a SoundFont (.sf2) file',
        filetypes=[('SoundFont', '*.sf2'), ('All files', '*.*')])
    root.destroy()
    return path or None


def ensure_audio_paths(settings: dict) -> bool:
    '''Fill settings['audio']['fluidsynth_bin']/['soundfont'] if missing or no
    longer valid, auto-detecting first and falling back to an interactive
    prompt. Mutates settings in place. Returns False if the user cancelled
    setup and a required path is still unresolved.
    '''
    audio = settings.setdefault('audio', {})

    bin_dir = audio.get('fluidsynth_bin', '')
    if not (bin_dir and os.path.isfile(os.path.join(bin_dir, _DLL_NAME))):
        bin_dir = find_fluidsynth_bin() or prompt_for_fluidsynth_bin()
        if not bin_dir:
            return False
        audio['fluidsynth_bin'] = bin_dir

    sf2 = audio.get('soundfont', '')
    if not (sf2 and os.path.isfile(sf2)):
        sf2 = find_soundfont() or prompt_for_soundfont()
        if not sf2:
            return False
        audio['soundfont'] = sf2

    return True
