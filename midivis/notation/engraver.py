'''Timeline + TempoMap -> laid-out glyph placements (Plan Part 3.3), pure
data, no rendering.

Replaces the per-frame, inline layout math the old
`ui/slots/traditional_sheet.py` did directly inside `draw()` (chord grouping,
rest-finding, beam bucketing, staff assignment, always-sharp accidentals) —
here that's all computed once per (file, key-signature) into an `Engraving`,
independent of playback position/zoom/scroll, which change every frame.

**Adaptation from the plan's literal wording**: Part 3 describes this module
as producing "laid-out glyph placements" the way a fixed-page engraver would
(absolute x/y per glyph). This app's traditional view is a continuously
scrolling staff, not a fixed page — a glyph's pixel x position is a function
of *live* playhead/zoom/scroll, recomputed every frame, so baking absolute
pixel positions in here would make them stale the instant the user scrubs or
zooms. Instead this module resolves everything that's actually
time-invariant: which staff a note is on, its diatonic staff position
(via midi/spelling.py), its accidental, its duration class (via
midi/quantize.py, including tie-across-barline splitting), and beam/chord
grouping. `render/slots/traditional.py` — the thin rendering layer — turns
`(start_tick, diatonic_step)` into `(pixel_x, pixel_y)` each frame the same
way `render/slots/bars.py` already turns `(start_s)` into pixel_x, and looks
up the actual glyph bitmap from `notation/glyphs.py`'s `GlyphAtlas`.

Both tick and second timestamps are precomputed once here (not just ticks)
because seconds is what the renderer needs every single frame for
horizontal scroll position — recomputing that tempo-map conversion 60 times
a second for every visible note would be wasted work for a value that never
changes after engraving. Ticks are kept alongside as the canonical unit
(matching `midi/model.py`'s `NoteEvent`) since duration-class/tie/beam
grouping all need exact tick arithmetic, not float seconds.
'''
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from midivis.midi import quantize, spelling
from midivis.midi.model import NoteEvent, TempoMap

StaffOf = Callable[[int], str]


def default_staff_of(note: int) -> str:
    '''Pitch-based default staff split (Plan Part 3.2: "voice/staff assignment
    becomes a per-track/channel property (with pitch-based default)"). Per-
    track/channel staff configuration is not built this milestone — see
    FullRewriteStatus.md's Milestone 4 deviations — but this is the one
    function a future settings-driven `staff_of` needs to replace, not
    scattered pitch-threshold checks.
    '''
    return 'treble' if note >= 60 else 'bass'


@dataclass(frozen=True)
class EngravedNote:
    start_tick: int
    end_tick: int
    start_s: float
    end_s: float
    track_id: int
    staff: str                                     # 'treble' | 'bass'
    pitches: tuple[tuple[int, int, int], ...]        # (midi_note, diatonic_step, accidental) per chord member
    note_type: str
    dots: int
    tuplet: tuple[int, int] | None
    tie_prev: bool
    tie_next: bool


@dataclass(frozen=True)
class EngravedRest:
    start_tick: int
    end_tick: int
    start_s: float
    end_s: float
    staff: str
    track_id: int
    rest_type: str
    dots: int


@dataclass
class Engraving:
    notes: list[EngravedNote] = field(default_factory=list)
    rests: list[EngravedRest] = field(default_factory=list)
    beam_groups: list[list[int]] = field(default_factory=list)   # indices into .notes


def _group_chords(note_events: list[NoteEvent], staff_of: StaffOf,
                    ticks_per_beat: int) -> dict[tuple[int, str, int], list[NoteEvent]]:
    '''{(start_tick, staff, track_id): [NoteEvent, ...]} — near-simultaneous
    notes in the same staff/track become one chord (one stem, one set of
    noteheads), same tolerance-based grouping as the old
    `_group_chords`, just in ticks (exact) instead of seconds (tempo-
    dependent, and recomputed every frame there).
    '''
    tol = max(1, ticks_per_beat // 16)
    groups: dict[tuple[int, str, int], list[NoteEvent]] = {}
    lane_start: dict[tuple[str, int], int] = {}
    for ev in sorted(note_events, key=lambda e: e.start_tick):
        staff = staff_of(ev.note)
        lane = (staff, ev.track_id)
        gt = lane_start.get(lane)
        if gt is None or ev.start_tick - gt > tol:
            gt = ev.start_tick
            lane_start[lane] = gt
        groups.setdefault((gt, staff, ev.track_id), []).append(ev)
    return groups


def _find_rests(chords: dict[tuple[int, str, int], list[NoteEvent]],
                 ticks_per_beat: int, time_sig: tuple[int, int],
                 tempo_map: TempoMap) -> list[EngravedRest]:
    '''Gaps between consecutive chords in each (staff, track) lane, same
    "gap bigger than ~half a beat" heuristic as the old `_find_rests` —
    what's actually new is that the *duration* of each rest found this way
    is run through quantize.classify_duration + split_across_barlines
    instead of a fixed beats-count threshold, and a rest spanning a barline
    is correctly split into tied... rests don't tie, but they do need one
    glyph per measure rather than one oversized rest overrunning the line.
    '''
    lanes: dict[tuple[str, int], list[tuple[int, int]]] = {}
    for (start_tick, staff, track_id), members in chords.items():
        end_tick = start_tick + max(m.end_tick - m.start_tick for m in members)
        lanes.setdefault((staff, track_id), []).append((start_tick, end_tick))

    min_gap = int(ticks_per_beat * 0.45)
    rests: list[EngravedRest] = []
    for (staff, track_id), spans in lanes.items():
        spans.sort()
        t = spans[0][0]
        for s, e in spans:
            if s - t > min_gap:
                for seg_start, seg_end in quantize.split_across_barlines(t, s, ticks_per_beat, time_sig):
                    q_ticks = quantize.quantize_duration_ticks(seg_end - seg_start, ticks_per_beat)
                    dc = quantize.classify_duration(q_ticks / ticks_per_beat)
                    rests.append(EngravedRest(
                        start_tick=seg_start, end_tick=seg_end,
                        start_s=tempo_map.ticks_to_seconds(seg_start),
                        end_s=tempo_map.ticks_to_seconds(seg_end),
                        staff=staff, track_id=track_id, rest_type=dc.note_type, dots=dc.dots))
            t = max(t, e)
    return rests


_BEAMABLE = {'eighth', 'sixteenth', 'thirty_second'}


def _beam_groups(notes: list[EngravedNote], ticks_per_beat: int,
                   time_sig: tuple[int, int]) -> list[list[int]]:
    '''Bucket consecutive beamable notes sharing a (staff, track, measure,
    beat) into beam groups, same bucketing key as the old
    `_draw_beam_group`'s caller, just computed from exact ticks instead of
    `start_t % (beat_dur * time_sig[0])` float arithmetic.
    '''
    beat_ticks = ticks_per_beat
    measure_beats = time_sig[0]
    buckets: dict[tuple[str, int, int, int], list[int]] = {}
    for i, n in enumerate(notes):
        if n.note_type not in _BEAMABLE or n.tuplet is not None:
            continue
        beat_idx_total = n.start_tick // beat_ticks
        measure_idx = beat_idx_total // measure_beats
        beat_idx = beat_idx_total % measure_beats
        key = (n.staff, n.track_id, measure_idx, beat_idx)
        buckets.setdefault(key, []).append(i)
    return [idxs for idxs in buckets.values() if len(idxs) >= 2]


def engrave(note_events: list[NoteEvent], tempo_map: TempoMap,
            time_sig: tuple[int, int], key_sig: str | None,
            staff_of: StaffOf | None = None,
            grid_denominator: int = quantize.DEFAULT_SNAP_GRID) -> Engraving:
    staff_of = staff_of or default_staff_of
    ticks_per_beat = tempo_map.ticks_per_beat

    # Readability over strict MIDI-timing accuracy (user-requested "note
    # accuracy threshold"): snap every note's onset/release onto a fixed
    # grid before anything else touches it, so a real performance's natural
    # slop -- a note released a touch late, a legato attack that starts a
    # hair before the previous note's release -- doesn't read as a spurious
    # overlap or a tiny phantom rest once engraved literally. This builds a
    # fresh list of NoteEvents; Timeline.note_events itself (and therefore
    # playback/the bars view's active-note highlighting) is never touched.
    if grid_denominator:
        note_events = [
            NoteEvent(*quantize.snap_note_span(ne.start_tick, ne.end_tick,
                                                  ticks_per_beat, grid_denominator),
                       note=ne.note, velocity=ne.velocity,
                       channel=ne.channel, track_id=ne.track_id)
            for ne in note_events
        ]

    chords = _group_chords(note_events, staff_of, ticks_per_beat)
    rests = _find_rests(chords, ticks_per_beat, time_sig, tempo_map)

    notes: list[EngravedNote] = []
    for (start_tick, staff, track_id), members in sorted(chords.items()):
        end_tick = start_tick + min(m.end_tick - m.start_tick for m in members)
        segments = quantize.split_across_barlines(start_tick, end_tick, ticks_per_beat, time_sig)
        for i, (seg_start, seg_end) in enumerate(segments):
            q_ticks = quantize.quantize_duration_ticks(seg_end - seg_start, ticks_per_beat)
            dc = quantize.classify_duration(q_ticks / ticks_per_beat)
            pitches = tuple(
                (m.note, *_spelled_position(m.note, key_sig)) for m in members)
            notes.append(EngravedNote(
                start_tick=seg_start, end_tick=seg_end,
                start_s=tempo_map.ticks_to_seconds(seg_start),
                end_s=tempo_map.ticks_to_seconds(seg_end),
                track_id=track_id, staff=staff, pitches=pitches,
                note_type=dc.note_type, dots=dc.dots, tuplet=dc.tuplet,
                tie_prev=(i > 0), tie_next=(i < len(segments) - 1)))

    beam_groups = _beam_groups(notes, ticks_per_beat, time_sig)
    return Engraving(notes=notes, rests=rests, beam_groups=beam_groups)


def _spelled_position(note: int, key_sig: str | None) -> tuple[int, int]:
    sp = spelling.spell(note, key_sig)
    return sp.diatonic_step, sp.accidental
