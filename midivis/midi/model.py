'''Core MIDI data structures: TempoMap, NoteEvent, Timeline.

The single source of truth for tempo <-> tick <-> second conversion. Replaces
three independent implementations that existed in the old MidiVis codebase
(App._seconds_to_ticks, midi_processing.build_timeline's internal closure, and
MidiRecorder's single-tempo-frozen-at-arm() math) with one bidirectional,
tempo-map-aware utility used everywhere.
'''

from __future__ import annotations

import bisect
from dataclasses import dataclass, field

import mido

DEFAULT_TEMPO_US = 500_000  # microseconds per quarter note = 120 BPM


@dataclass(frozen=True)
class TempoChange:
    tick: int
    tempo_us: int  # microseconds per quarter note


@dataclass
class TempoMap:
    '''Bidirectional tick <-> second conversion for one MIDI file's tempo track.

    Change points are pre-sorted and their cumulative seconds pre-computed at
    construction time, so seconds_to_ticks/ticks_to_seconds are O(log n) via
    bisect rather than rescanning the tempo list on every call.
    '''
    ticks_per_beat: int
    changes: list[TempoChange] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.changes = sorted(self.changes, key=lambda c: c.tick)
        self._change_ticks = [c.tick for c in self.changes]

        cum_seconds = []
        cur_tick, cur_tempo = 0, DEFAULT_TEMPO_US
        cum = 0.0
        for chg in self.changes:
            cum += mido.tick2second(chg.tick - cur_tick, self.ticks_per_beat, cur_tempo)
            cum_seconds.append(cum)
            cur_tick, cur_tempo = chg.tick, chg.tempo_us
        self._cum_seconds = cum_seconds

    @classmethod
    def from_midi(cls, mid: mido.MidiFile) -> 'TempoMap':
        '''Build a TempoMap from all set_tempo meta messages in a mido.MidiFile.'''
        changes = []
        if mid.type == 1:
            for track in mid.tracks:
                abs_tick = 0
                for msg in track:
                    abs_tick += msg.time
                    if msg.type == 'set_tempo':
                        changes.append(TempoChange(abs_tick, msg.tempo))
        else:
            abs_tick = 0
            for msg in mido.merge_tracks(mid.tracks):
                abs_tick += msg.time
                if msg.type == 'set_tempo':
                    changes.append(TempoChange(abs_tick, msg.tempo))
        return cls(ticks_per_beat=mid.ticks_per_beat, changes=changes)

    def tempo_at_tick(self, tick: int) -> int:
        '''Return the active tempo (microseconds/quarter note) at an absolute tick.'''
        idx = bisect.bisect_right(self._change_ticks, tick) - 1
        return self.changes[idx].tempo_us if idx >= 0 else DEFAULT_TEMPO_US

    def ticks_to_seconds(self, tick: int) -> float:
        idx = bisect.bisect_right(self._change_ticks, tick) - 1
        if idx < 0:
            return mido.tick2second(tick, self.ticks_per_beat, DEFAULT_TEMPO_US)
        chg = self.changes[idx]
        base_sec = self._cum_seconds[idx]
        return base_sec + mido.tick2second(tick - chg.tick, self.ticks_per_beat, chg.tempo_us)

    def seconds_to_ticks(self, seconds: float) -> int:
        idx = bisect.bisect_right(self._cum_seconds, seconds) - 1
        if idx < 0:
            return int(mido.second2tick(seconds, self.ticks_per_beat, DEFAULT_TEMPO_US))
        chg = self.changes[idx]
        rem_sec = seconds - self._cum_seconds[idx]
        return int(chg.tick + mido.second2tick(rem_sec, self.ticks_per_beat, chg.tempo_us))


@dataclass
class NoteEvent:
    '''One sounded note. Timing is stored in ticks — the tempo-invariant unit —
    with seconds derived on demand via TempoMap so a single event survives a
    tempo-map change (e.g. re-quantization) without needing to be recomputed.
    '''
    start_tick: int
    end_tick: int
    note: int
    velocity: int
    channel: int
    track_id: int


@dataclass
class Timeline:
    '''A loaded MIDI file's musical content: tempo map + note events.

    Populated by midi/load.py (not yet implemented — later milestone); this
    class is the shared container both the audio and notation/UI layers will
    read from.
    '''
    tempo_map: TempoMap
    note_events: list[NoteEvent] = field(default_factory=list)

    @property
    def ticks_per_beat(self) -> int:
        return self.tempo_map.ticks_per_beat
