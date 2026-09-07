'''MIDI file metadata extraction — tempo, time signature, key signature.
Pure functions, ported from the old repo's midi_analyzer.py.
'''
from __future__ import annotations

import mido


def get_tempo(mid: mido.MidiFile) -> float:
    '''BPM from the first set_tempo message, defaulting to 120.'''
    for track in mid.tracks:
        for msg in track:
            if msg.type == 'set_tempo':
                return mido.tempo2bpm(msg.tempo)
    return 120.0


def get_time_signature(mid: mido.MidiFile) -> tuple[int, int]:
    '''(numerator, denominator) from the first time_signature message, defaulting to (4, 4).'''
    for track in mid.tracks:
        for msg in track:
            if msg.type == 'time_signature':
                return (msg.numerator, msg.denominator)
    return (4, 4)


def get_key_signature(mid: mido.MidiFile) -> str | None:
    '''Key signature from the first key_signature meta message, or None if absent.'''
    for track in mid.tracks:
        for msg in track:
            if msg.type == 'key_signature':
                key = msg.key
                if key.endswith('m'):
                    return f'{key[:-1]} minor'
                return f'{key} major'
    return None


_MAJOR_STEPS = [0, 2, 4, 5, 7, 9, 11]
_MINOR_STEPS = [0, 2, 3, 5, 7, 8, 10]
_PITCH_CLASS_NAMES = ['C', 'C#', 'D', 'Eb', 'E', 'F', 'F#', 'G', 'Ab', 'A', 'Bb', 'B']


def detect_key_signature(mid: mido.MidiFile) -> str:
    '''Detect key from pitch-class distribution when no key_signature meta is present.'''
    pc = [0] * 12
    for track in mid.tracks:
        for msg in track:
            if msg.type == 'note_on' and msg.velocity > 0:
                pc[msg.note % 12] += 1

    if not any(pc):
        return 'C major'

    best, winner = -1, 'C major'
    for root in range(12):
        maj = sum(pc[(root + i) % 12] for i in _MAJOR_STEPS)
        if maj > best:
            best, winner = maj, f'{_PITCH_CLASS_NAMES[root]} major'
        minor = sum(pc[(root + i) % 12] for i in _MINOR_STEPS)
        if minor > best:
            best, winner = minor, f'{_PITCH_CLASS_NAMES[root]} minor'
    return winner
