'''Track -> MIDI channel assignment (Plan Part 3.2).

Ported from the old repo's midi_processing.remap_channels. Assigns every
note-bearing track a unique channel so channel-based mute filtering is
track-accurate regardless of the file's original channel layout: drum tracks
(any note on channel 9) are pinned to channel 9, melodic tracks draw from the
remaining 15-channel pool.

This is the *basic* remap Milestone 3 needs to make per-track mute correct in
the common case. The two known gaps this doesn't yet handle — more than 15
simultaneous melodic tracks, and multiple simultaneous drum tracks colliding
on channel 9 — are Milestone 5's "channel-remap edge-case fixes" per Plan
Part 4; this module is exactly what that milestone extends, not a
placeholder to be replaced.
'''
from __future__ import annotations

import copy
import io

import mido

DRUM_CHANNEL = 9
_MELODIC_POOL = [c for c in range(16) if c != DRUM_CHANNEL]


def remap_channels(mid: mido.MidiFile) -> tuple[bytes, dict[int, int]]:
    '''Return (bytes, {track_id: channel}) with each note-bearing track
    assigned a unique MIDI channel. track_id matches midi.load's convention:
    track index for SMF type 1, original channel for type 0.
    '''
    track_orig: dict[int, set[int]] = {}
    for i, track in enumerate(mid.tracks):
        chs = {m.channel for m in track if m.type == 'note_on' and m.velocity > 0}
        if chs:
            track_orig[i] = chs

    used: set[int] = set()
    ch_assign: dict[int, int] = {}
    melodic_idx = 0
    for tid in sorted(track_orig):
        orig_chs = track_orig[tid]
        if DRUM_CHANNEL in orig_chs:
            ch_assign[tid] = DRUM_CHANNEL
            used.add(DRUM_CHANNEL)
        else:
            while melodic_idx < len(_MELODIC_POOL) and _MELODIC_POOL[melodic_idx] in used:
                melodic_idx += 1
            if melodic_idx >= len(_MELODIC_POOL):
                ch_assign[tid] = min(orig_chs)
            else:
                ch_assign[tid] = _MELODIC_POOL[melodic_idx]
                used.add(_MELODIC_POOL[melodic_idx])
                melodic_idx += 1

    if all(track_orig.get(tid) == {ch} for tid, ch in ch_assign.items()):
        buf = io.BytesIO()
        mid.save(file=buf)
        return buf.getvalue(), ch_assign

    mid2 = copy.deepcopy(mid)
    for tid, new_ch in ch_assign.items():
        for j, msg in enumerate(mid2.tracks[tid]):
            if hasattr(msg, 'channel') and msg.channel != new_ch:
                mid2.tracks[tid][j] = msg.copy(channel=new_ch)

    buf = io.BytesIO()
    mid2.save(file=buf)
    return buf.getvalue(), ch_assign
