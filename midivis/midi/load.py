'''SMF -> Timeline, plus track/instrument metadata extraction (Plan Part 3).

Replaces the old repo's midi_processing.build_timeline/build_note_events
(ticks instead of pre-computed seconds now that NoteEvent stores ticks — see
midi/model.py's NoteEvent docstring — so this module doesn't need a tempo map
at all to build note events; seconds are derived on demand via TempoMap) and
folds in get_track_names/get_track_channels/get_instruments, which the old
repo kept in the same module (midi_processing.py) for the same reason: all of
these are "read structural/track metadata out of an SMF, no UI" concerns with
no natural home of their own in Plan Part 3's tree.
'''
from __future__ import annotations

from collections import deque

import mido

from midivis.midi.model import NoteEvent, Timeline, TempoMap


def _tick_events(mid: mido.MidiFile) -> list[tuple[int, int, mido.Message]]:
    '''Sorted (abs_tick, track_id, msg) for all note_on/note_off/CC64 events.

    track_id is the mido track index for SMF type 1 (multi-track), or the
    channel number for type 0 (single merged track) — matching
    get_track_channels/get_track_names below.
    '''
    events: list[tuple[int, int, mido.Message]] = []
    if mid.type == 1:
        for track_idx, track in enumerate(mid.tracks):
            abs_tick = 0
            for msg in track:
                abs_tick += msg.time
                if msg.type in ('note_on', 'note_off'):
                    events.append((abs_tick, track_idx, msg))
                elif msg.type == 'control_change' and msg.control == 64:
                    events.append((abs_tick, track_idx, msg))
    else:
        abs_tick = 0
        for msg in mido.merge_tracks(mid.tracks):
            abs_tick += msg.time
            if msg.type in ('note_on', 'note_off'):
                events.append((abs_tick, msg.channel, msg))
            elif msg.type == 'control_change' and msg.control == 64:
                events.append((abs_tick, msg.channel, msg))
    events.sort(key=lambda e: e[0])
    return events


def _events_to_notes(tick_events: list[tuple[int, int, mido.Message]],
                      ticks_per_beat: int) -> list[NoteEvent]:
    '''Resolve note_on/note_off pairs into NoteEvents, honoring sustain
    pedal (CC64): a note released while the pedal is down keeps sounding
    until the pedal lifts, "whichever is later" — same semantics as the old
    build_note_events.
    '''
    starts: dict[tuple[int, int, int], deque] = {}
    sustained: dict[tuple[int, int, int], deque] = {}
    pedal: dict[int, bool] = {}
    notes: list[NoteEvent] = []

    for tick, track_id, msg in tick_events:
        if msg.type == 'control_change' and msg.control == 64:
            ch = msg.channel
            down = msg.value >= 64
            was_on = pedal.get(ch, False)
            pedal[ch] = down
            if was_on and not down:
                for key in [k for k in sustained if k[1] == ch]:
                    q = sustained.pop(key)
                    note, _, tid = key
                    for st, vel in q:
                        notes.append(NoteEvent(st, tick, note, vel, ch, tid))
            continue

        key = (msg.note, msg.channel, track_id)
        if msg.type == 'note_on' and msg.velocity > 0:
            starts.setdefault(key, deque()).append((tick, msg.velocity))
        else:
            q = starts.get(key)
            if q:
                st, vel = q.popleft()
                if not q:
                    del starts[key]
                if pedal.get(msg.channel, False):
                    sustained.setdefault(key, deque()).append((st, vel))
                else:
                    notes.append(NoteEvent(st, tick, msg.note, vel, msg.channel, track_id))

    # Notes with no matching note_off (truncated/malformed file): extend to
    # the last event tick (or a minimal 16th-note if that's earlier than the
    # note's own start, e.g. a lone unterminated note in an empty file).
    last_tick = tick_events[-1][0] if tick_events else 0
    min_dur = max(1, ticks_per_beat // 4)
    for (note, ch, track_id), q in list(starts.items()) + list(sustained.items()):
        for st, vel in q:
            notes.append(NoteEvent(st, max(st + min_dur, last_tick), note, vel, ch, track_id))

    return notes


def load_timeline(mid: mido.MidiFile, tempo_map: TempoMap) -> Timeline:
    tick_events = _tick_events(mid)
    notes = _events_to_notes(tick_events, mid.ticks_per_beat)
    return Timeline(tempo_map=tempo_map, note_events=notes)


def get_track_names(mid: mido.MidiFile) -> dict[int, str]:
    '''{track_id: display_name} for tracks that carry note_on events.'''
    if mid.type == 1:
        names = {}
        for i, track in enumerate(mid.tracks):
            if any(msg.type == 'note_on' and msg.velocity > 0 for msg in track):
                name = (track.name or '').strip() or f'Track {i}'
                names[i] = name
        return names
    channels = set()
    for msg in mido.merge_tracks(mid.tracks):
        if hasattr(msg, 'channel'):
            channels.add(msg.channel)
    return {ch: f'Channel {ch + 1}' for ch in sorted(channels)}


def get_track_channels(mid: mido.MidiFile) -> dict[int, set[int]]:
    '''{track_id: set(channels)} based on note_on events (pre-remap).'''
    if mid.type == 1:
        return {
            i: {msg.channel for msg in track if msg.type == 'note_on' and msg.velocity > 0}
            for i, track in enumerate(mid.tracks)
        }
    return {ch: {ch} for ch in range(16)}


def get_instruments(mid: mido.MidiFile) -> dict[int, list[int]]:
    '''{track_id: [program_number, ...]} for tracks that send program_change.'''
    if mid.type == 1:
        result = {}
        for i, track in enumerate(mid.tracks):
            progs = [msg.program for msg in track if msg.type == 'program_change']
            if progs:
                result[i] = progs
        return result
    ch_progs: dict[int, list[int]] = {}
    for msg in mido.merge_tracks(mid.tracks):
        if msg.type == 'program_change':
            ch_progs.setdefault(msg.channel, []).append(msg.program)
    return ch_progs


def build_measure_times(bpm: float, sig_num: int, total: float) -> list[tuple[int, float]]:
    '''[(measure_index, start_seconds), ...] covering total plus a small buffer.'''
    dur = (60.0 / bpm) * sig_num
    count = int(total / dur) + 2
    return [(i, i * dur) for i in range(count)]
