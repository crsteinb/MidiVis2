'''AudioEngine: the interface both playback backends implement (Plan Part 3.1).

Milestone 2 implements only FluidPlayerBackend (fluid_player.py). SequencerBackend
(the sample-accurate custom engine) is Milestone 6 — it will sit behind this same
interface so the app works with either "audio.backend" setting without the rest of
the app knowing which one is active.

get_clock_seconds() is the *authoritative* elapsed-time source. This is a deliberate
change from the old MidiVis, where App owned a wall-clock timer
(App._t0_ticks/pygame.time.get_ticks()) independent of the engine. Moving clock
ownership into the engine means each backend can be honest about where its clock
actually comes from — FluidPlayerBackend's is still wall-clock (documented, not a
hidden gotcha; see fluid_player.py), while SequencerBackend's will be
samples-rendered/sample-rate, a true audio-derived clock.
'''
from __future__ import annotations

from enum import Enum
from typing import Protocol, runtime_checkable

from midivis.midi.model import TempoMap


class PlayerStatus(Enum):
    READY = 0
    PLAYING = 1
    STOPPING = 2
    DONE = 3


@runtime_checkable
class AudioEngine(Protocol):
    def load(self, midi_bytes: bytes, tempo_map: TempoMap) -> None:
        '''Load a MIDI file (already-serialized bytes) for playback.'''
        ...

    def play(self) -> None:
        '''Resume/start playback from the current position.'''
        ...

    def pause(self) -> None:
        '''Stop playback, holding the current position.'''
        ...

    def stop(self) -> None:
        '''Reset to a stopped state at position 0.'''
        ...

    def seek(self, seconds: float) -> None:
        '''Jump to an absolute position, in seconds.'''
        ...

    def get_clock_seconds(self) -> float:
        '''Authoritative elapsed time, in seconds.'''
        ...

    def get_status(self) -> PlayerStatus:
        ...

    def set_channel_muted(self, channel: int, muted: bool) -> None:
        ...

    def note_on(self, channel: int, note: int, velocity: int) -> None:
        '''Live/preview note-on — bypasses the player and any channel muting.'''
        ...

    def note_off(self, channel: int, note: int) -> None:
        ...

    def cc(self, channel: int, ctrl: int, value: int) -> None:
        ...

    def program_change(self, channel: int, program: int) -> None:
        ...

    def all_notes_off(self, channel: int) -> None:
        ...

    def shutdown(self) -> None:
        ...
