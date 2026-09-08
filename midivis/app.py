'''App: application state (Plan Part 3's app.py).

Milestone 2 kept this deliberately minimal ("load a file, play/pause/seek").
Milestone 3 grows it to match: track list + per-track mute, active-note
tracking for the bars view, and the metadata (bpm/time_sig/key_sig/
instruments) the properties panel needs — i.e. "feature parity with today's
app apart from traditional notation" per Plan Part 4, minus recording/MIDI
input (Milestone 5) and the notation engine (Milestone 4).

Playback mechanics (play/pause/seek/elapsed) still forward straight to the
injected AudioEngine, which owns the clock (Milestone 2's design). The one
addition there is `seek_preview()`: a visual-only position used while the
timeline is being dragged. The old App could just overwrite its own
wall-clock `elapsed` field for this; here `elapsed` is a property that reads
the engine, so there's no local field to freely overwrite. Instead
`_preview_elapsed`, when set, shadows the engine's clock for display and for
active-note computation without calling into the engine at all — only
`seek()` (drag release / click-to-seek) actually commits a position to the
engine and clears it.
'''
from __future__ import annotations

import os

import mido

from midivis.audio.engine import AudioEngine, PlayerStatus
from midivis.midi import analyze
from midivis.midi import channel_remap
from midivis.midi import load as midi_load
from midivis.midi.model import TempoMap, Timeline
from midivis.midi import quantize
from midivis.notation import engraver
from midivis.notation.engraver import Engraving


class App:
    def __init__(self, engine: AudioEngine | None) -> None:
        self.engine = engine
        self.midi_path: str | None = None
        self.title: str = ''
        self.tempo_map: TempoMap | None = None
        self.timeline: Timeline | None = None
        self.total_dur: float = 0.0

        self.bpm: float = 120.0
        self.time_sig: tuple[int, int] = (4, 4)
        self.key_sig: str | None = None
        self.measure_times: list[tuple[int, float]] = []

        self.tracks: dict[int, str] = {}
        self.enabled_tracks: set[int] = set()
        self.track_channels: dict[int, set[int]] = {}
        self.instruments: dict[int, list[int]] = {}

        # (start_s, end_s, note, velocity, track_id) tuples — _all_note_events
        # is every note in the file; note_events is filtered to enabled_tracks
        # (what the bars view actually draws).
        self._all_note_events: list[tuple[float, float, int, int, int]] = []
        self.note_events: list[tuple[float, float, int, int, int]] = []
        # Flattened (time_s, kind, note, track_id) on/off events, sorted, used
        # to track active_notes incrementally during playback and by full
        # rebuild on seek — same two-mode approach as the old App.
        self._flat_events: list[tuple[float, int, int, int]] = []
        self._event_index = 0
        self.active_notes: set[int] = set()
        # How many currently-open instances of each note are sounding.
        # active_notes alone can't tell two overlapping/back-to-back
        # instances of the *same* pitch apart from one instance -- see
        # _apply_event's docstring for why that's a real bug, not a
        # hypothetical one.
        self._active_note_counts: dict[int, int] = {}

        self._preview_elapsed: float | None = None

        self.kb_notes: set[int] = set()
        self._kb_channel = 0

        self.sheet_zoom: float = 1.0
        self.bars_scroll: float = 0.0
        self.properties_expanded: bool = False

        self.view: str = 'bars'
        self.trad_scroll: float = 0.5
        self.engraving: Engraving | None = None
        # "Note accuracy threshold" for the traditional view (user-facing
        # setting: settings['notation']['snap_grid']) — see
        # midi/quantize.py's snap_note_span for what this actually does.
        # main.py sets this from settings before the first load(); changing
        # it afterward goes through set_notation_snap_grid() so the current
        # file's notation re-engraves without a full reload.
        self.notation_snap_grid: int = quantize.DEFAULT_SNAP_GRID

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

        self.timeline = midi_load.load_timeline(mid, self.tempo_map)
        self._all_note_events = [
            (self.tempo_map.ticks_to_seconds(ne.start_tick),
             self.tempo_map.ticks_to_seconds(ne.end_tick),
             ne.note, ne.velocity, ne.track_id)
            for ne in self.timeline.note_events
        ]
        self._flat_events = sorted(
            [(s, 0, note, tid) for (s, e, note, vel, tid) in self._all_note_events]
            + [(e, 1, note, tid) for (s, e, note, vel, tid) in self._all_note_events],
            key=lambda ev: (ev[0], ev[1]))

        self.tracks = midi_load.get_track_names(mid)
        self.track_channels = midi_load.get_track_channels(mid)
        self.instruments = midi_load.get_instruments(mid)
        self.enabled_tracks = set(self.tracks.keys())
        self.note_events = list(self._all_note_events)

        self.bpm = analyze.get_tempo(mid)
        self.time_sig = analyze.get_time_signature(mid)
        self.key_sig = analyze.get_key_signature(mid) or analyze.detect_key_signature(mid)
        self.measure_times = midi_load.build_measure_times(
            self.bpm, self.time_sig[0], self.total_dur)

        self.engraving = engraver.engrave(
            self.timeline.note_events, self.tempo_map, self.time_sig, self.key_sig,
            grid_denominator=self.notation_snap_grid)

        self._preview_elapsed = None
        self._reset_playback()
        self.kb_notes = set()

        mid_bytes, ch_remap = channel_remap.remap_channels(mid)
        for tid, new_ch in ch_remap.items():
            self.track_channels[tid] = {new_ch}

        if self.engine:
            self.engine.load(mid_bytes, self.tempo_map)
            self._update_track_muting()
        return True

    def set_notation_snap_grid(self, grid_denominator: int) -> None:
        '''Change the traditional view's "note accuracy threshold" and
        re-engrave the current file immediately (if one is loaded) — a menu
        toggle should take effect right away, not just on the next file
        open. Cheap enough to do synchronously: engraving one file is a
        one-shot pass over its notes, not a per-frame cost.
        '''
        self.notation_snap_grid = grid_denominator
        if self.timeline is not None:
            self.engraving = engraver.engrave(
                self.timeline.note_events, self.tempo_map, self.time_sig, self.key_sig,
                grid_denominator=self.notation_snap_grid)

    # ------------------------------------------------------------------
    # Playback
    # ------------------------------------------------------------------

    @property
    def playing(self) -> bool:
        return bool(self.engine) and self.engine.get_status() == PlayerStatus.PLAYING

    @property
    def elapsed(self) -> float:
        if self._preview_elapsed is not None:
            return self._preview_elapsed
        if not self.engine:
            return 0.0
        return self.engine.get_clock_seconds()

    def play(self) -> None:
        if not self.loaded or not self.engine:
            return
        self._preview_elapsed = None
        if self.elapsed >= self.total_dur:
            self.engine.stop()
            self._reset_playback()
        self._sync_event_index()
        self._rebuild_active_notes()
        self.engine.play()

    def pause(self) -> None:
        if not self.engine:
            return
        self.engine.pause()

    def seek(self, seconds: float) -> None:
        self._preview_elapsed = None
        if not self.engine:
            return
        self.engine.seek(max(0.0, min(seconds, self.total_dur)))
        self._sync_event_index()
        self._rebuild_active_notes()

    def seek_preview(self, seconds: float) -> None:
        '''Visual-only position update — used during timeline drag, without
        calling into the engine (see the module docstring).
        '''
        self._preview_elapsed = max(0.0, min(seconds, self.total_dur))
        self._sync_event_index()
        self._rebuild_active_notes()

    def update(self) -> None:
        '''Poll for song-end, and otherwise advance active_notes forward to
        match elapsed. Checks get_status() directly rather than gating on
        self.playing — see Milestone 2's Status notes on why that gate is
        wrong (playing is already False the instant status flips to DONE).
        '''
        if self.engine and self.engine.get_status() == PlayerStatus.DONE:
            self.engine.stop()
            self._reset_playback()
            return
        if self._preview_elapsed is not None:
            return   # frozen at the drag-preview position; nothing to advance
        elapsed = self.elapsed
        while (self._event_index < len(self._flat_events)
               and self._flat_events[self._event_index][0] <= elapsed):
            _, kind, note, track_id = self._flat_events[self._event_index]
            if track_id in self.enabled_tracks:
                self._apply_event(kind, note)
            self._event_index += 1

    def _apply_event(self, kind: int, note: int) -> None:
        '''Update active_notes for one on/off event, tracking a per-note
        open-instance count rather than a bare boolean.

        A single track can absolutely retrigger the same pitch before its
        previous sounding has ended (legato/overlapping releases in a real
        performance, or two note-on events for the same note whose note-offs
        arrive out of the "obvious" order) — midi/load.py's
        _events_to_notes already models this correctly with a FIFO per
        (note, channel, track), producing two overlapping/back-to-back
        NoteEvents for the same pitch. But a plain `set[int]` can't
        represent "two instances of note 60 are open" as anything other
        than "note 60 is open" — so the first instance's note-off call
        (`discard`) incorrectly turned the note off even while a second,
        still-sounding instance was in progress (reported: notes losing
        their highlight before the note actually ends, or a stale highlight
        outliving what the bars view drew for it). Counting open instances
        per note fixes this: the note only leaves active_notes when its
        count reaches zero.
        '''
        if kind == 0:
            self._active_note_counts[note] = self._active_note_counts.get(note, 0) + 1
            self.active_notes.add(note)
        else:
            remaining = self._active_note_counts.get(note, 0) - 1
            if remaining <= 0:
                self._active_note_counts.pop(note, None)
                self.active_notes.discard(note)
            else:
                self._active_note_counts[note] = remaining

    def _reset_playback(self) -> None:
        self._event_index = 0
        self.active_notes = set()
        self._active_note_counts = {}

    def _sync_event_index(self) -> None:
        '''Recompute _event_index to match the current elapsed after a
        discontinuous jump (seek/seek_preview) rather than incrementing.
        '''
        self._event_index = 0
        while (self._event_index < len(self._flat_events)
               and self._flat_events[self._event_index][0] <= self.elapsed):
            self._event_index += 1

    def _rebuild_active_notes(self) -> None:
        self.active_notes = set()
        self._active_note_counts = {}
        for t, kind, note, track_id in self._flat_events:
            if t > self.elapsed:
                break
            if track_id not in self.enabled_tracks:
                continue
            self._apply_event(kind, note)

    # ------------------------------------------------------------------
    # Track list / mute
    # ------------------------------------------------------------------

    def set_all_tracks(self, enabled: bool) -> None:
        self.enabled_tracks = set(self.tracks.keys()) if enabled else set()
        self._rebuild_filtered()

    def toggle_track(self, track_id: int) -> None:
        if track_id in self.enabled_tracks:
            self.enabled_tracks.discard(track_id)
        else:
            self.enabled_tracks.add(track_id)
        self._rebuild_filtered()

    def _rebuild_filtered(self) -> None:
        self.note_events = [e for e in self._all_note_events if e[4] in self.enabled_tracks]
        self._rebuild_active_notes()
        self._update_track_muting()

    def _update_track_muting(self) -> None:
        if not self.engine:
            return
        for channels in self.track_channels.values():
            for ch in channels:
                ch_on = any(ch in self.track_channels.get(t, set()) for t in self.enabled_tracks)
                self.engine.set_channel_muted(ch, not ch_on)

    # ------------------------------------------------------------------
    # On-screen keyboard passthrough
    # ------------------------------------------------------------------

    def kb_note_on(self, note: int) -> None:
        if self.engine:
            self.engine.note_on(self._kb_channel, note, 100)
        self.kb_notes.add(note)

    def kb_note_off(self, note: int) -> None:
        if self.engine:
            self.engine.note_off(self._kb_channel, note)
        self.kb_notes.discard(note)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def shutdown(self) -> None:
        if self.engine:
            self.engine.shutdown()
            self.engine = None
