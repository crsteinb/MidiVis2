'''App: slimmed application state (Plan Part 3's app.py).

Delegates all playback mechanics — including elapsed-time tracking, which the old
MidiVis's App owned directly via pygame.time.get_ticks() — to an AudioEngine
implementation (Plan Part 3.1). App itself only knows "what file is loaded" and
"what does the tempo map say the total duration is"; play/pause/seek/elapsed all
forward straight to the engine.

Track list/mute UI, the notation views, and MIDI input/recording are later
milestones (Plan Part 4: Milestone 3 onward) — this is deliberately just
"load a file, play/pause/seek", matching Milestone 2's "basic playback wired to a
minimal shell UI" scope. It doesn't build midi.model.Timeline yet either: the
FluidPlayerBackend plays raw file bytes directly (like the old engine.load_from_mem()
path), so nothing here needs populated note events.
'''
from __future__ import annotations

import os

import mido

from midivis.audio.engine import AudioEngine, PlayerStatus
from midivis.midi.model import TempoMap


class App:
    def __init__(self, engine: AudioEngine | None) -> None:
        self.engine = engine
        self.midi_path: str | None = None
        self.title: str = ''
        self.tempo_map: TempoMap | None = None
        self.total_dur: float = 0.0

    @property
    def loaded(self) -> bool:
        return self.midi_path is not None

    def load(self, path: str) -> bool:
        try:
            mid = mido.MidiFile(path, clip=True)
        except Exception as e:
            print(f'Failed to load MIDI: {e}')
            return False

        self.midi_path = path
        self.title = os.path.basename(path)
        self.tempo_map = TempoMap.from_midi(mid)
        self.total_dur = mid.length

        if self.engine:
            with open(path, 'rb') as f:
                midi_bytes = f.read()
            self.engine.load(midi_bytes, self.tempo_map)
        return True

    @property
    def playing(self) -> bool:
        return bool(self.engine) and self.engine.get_status() == PlayerStatus.PLAYING

    @property
    def elapsed(self) -> float:
        if not self.engine:
            return 0.0
        return self.engine.get_clock_seconds()

    def play(self) -> None:
        if not self.loaded or not self.engine:
            return
        self.engine.play()

    def pause(self) -> None:
        if not self.engine:
            return
        self.engine.pause()

    def seek(self, seconds: float) -> None:
        if not self.engine:
            return
        self.engine.seek(max(0.0, min(seconds, self.total_dur)))

    def update(self) -> None:
        '''Poll for song-end and reset to a stopped state at position 0.

        Checks get_status() directly rather than gating on self.playing — playing
        is already False once status flips to DONE (it's defined as status ==
        PLAYING), so gating on it would make this never fire.
        '''
        if self.engine and self.engine.get_status() == PlayerStatus.DONE:
            self.engine.stop()

    def shutdown(self) -> None:
        if self.engine:
            self.engine.shutdown()
            self.engine = None
