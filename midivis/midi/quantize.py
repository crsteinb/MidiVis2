'''Rhythm quantization for notation (Plan Part 3.2): duration -> (type, dots,
tuplet), tie-generation across barlines, and (new, user-requested) snapping
a note's onset/release to a fixed rhythmic grid for notation *display*.

Replaces the old repo's `_note_type` (traditional_sheet.py) — a fixed
beats-count threshold bucket with no dotted notes, no triplets, and no idea
that a note might cross a barline and need to be drawn as two tied noteheads.

Scope note: the "grid + strength" quantization mentioned in Plan Part 3.2's
recording-quantization sidebar (snapping a *live-recorded* note's onset/
duration to a grid *and writing that back into the saved track*, with an
adjustable strength dial) is still Milestone 5's job, not this module's —
there's no recorder yet for it to plug into, and it permanently changes the
saved note data. `snap_tick`/`snap_note_span` below are a different, simpler
thing: an always-optional, display-only snap the traditional notation view
applies to its own copy of the note data every time it engraves a page,
controlled by the user-facing "note accuracy threshold" setting
(`settings['notation']['snap_grid']`) — it never touches `Timeline.note_events`,
playback, or the bars view's active-note highlighting, all of which
intentionally keep using exact MIDI timing.
'''
from __future__ import annotations

import math
from dataclasses import dataclass

# (name, duration in quarter-note beats), longest to shortest.
_BASE_TYPES = [
    ('whole', 4.0),
    ('half', 2.0),
    ('quarter', 1.0),
    ('eighth', 0.5),
    ('sixteenth', 0.25),
    ('thirty_second', 0.125),
]
# Capped at a single dot -- double-dotted notation is rare enough in real
# scores that it should only ever appear when a file's data unambiguously
# calls for it, never as this classifier's "closest fit" guess for an
# imprecise duration. Real (non-machine-quantized) MIDI durations routinely
# land ~10-15% short of a round value (a note's natural release trailing
# off before the next note, an early-cut sustain, an export quirk) — e.g. a
# whole note at 3.5 beats out of 4. With double-dots in the candidate pool,
# that 3.5 was the *closer* match to "double-dotted half" (exactly 3.5) than
# to "whole" (4.0), and got classified that way even though a human
# engraver reading the same performance would write it as a plain whole
# note, not reach for a rarely-used double-dot. Capping at one dot removes
# that always-available "perfect but implausible" candidate, so the
# classifier falls back to the musically ordinary whole/dotted-half instead.
_DOT_MULT = {0: 1.0, 1: 1.5}

# Default "traditional note accuracy threshold" — see snap_note_span.
DEFAULT_SNAP_GRID = 32


@dataclass(frozen=True)
class DurationClass:
    note_type: str            # one of _BASE_TYPES' names
    dots: int                  # 0 or 1
    tuplet: tuple[int, int] | None   # (actual, normal), e.g. (3, 2) for a triplet


def classify_duration(beats: float) -> DurationClass:
    '''Nearest standard duration class (by log-ratio, so e.g. a slightly-off
    eighth note doesn't get pulled toward a sixteenth just because the raw
    beat difference is small) for a duration given in quarter-note beats.
    '''
    beats = max(beats, 1e-6)
    candidates: list[tuple[str, int, tuple[int, int] | None, float]] = []
    for name, base in _BASE_TYPES:
        for dots, mult in _DOT_MULT.items():
            candidates.append((name, dots, None, base * mult))
        candidates.append((name, 0, (3, 2), base * 2.0 / 3.0))   # triplet
    best = min(candidates, key=lambda c: abs(math.log(c[3] / beats)))
    return DurationClass(note_type=best[0], dots=best[1], tuplet=best[2])


def snap_tick(tick: int, ticks_per_beat: int, grid_denominator: int = 32) -> int:
    '''Snap an absolute tick position to the nearest point on a fixed
    rhythmic grid. `grid_denominator` names the grid the way a note value
    would be (32 = nearest 1/32 note, 16 = nearest 1/16 note, ...);
    `grid_denominator=0` (or any falsy value) disables snapping and returns
    `tick` unchanged -- an "exact timing" mode for files whose off-grid
    timing is deliberate rather than performance noise.
    '''
    if not grid_denominator:
        return tick
    step = max(1, (ticks_per_beat * 4) // grid_denominator)
    return round(tick / step) * step


def snap_note_span(start_tick: int, end_tick: int, ticks_per_beat: int,
                     grid_denominator: int = 32) -> tuple[int, int]:
    '''Snap both ends of a note to the rhythmic grid (see `snap_tick`) —
    the "traditional note accuracy threshold" setting the notation view
    trades exact MIDI timing for readability with. `grid_denominator=32`
    (the default) means every onset and release lands on the nearest 1/32
    note; a real performance's natural slop — a note released a touch
    late, a legato attack that starts a hair before the previous note's
    release — routinely reads as a spurious brief overlap or gap once
    engraved literally, and crushing both ends onto the same clean grid is
    what actually removes that, upstream of chord grouping / rest-gap
    detection / tie-splitting, rather than just cleaning up the *duration*
    classification after the fact the way `quantize_duration_ticks` does.

    Guards against a degenerate zero/negative-length note if both ends snap
    to the same grid point (nudges the end forward by one grid step).

    Never applied to the app's own playback/highlight timing — only within
    `notation/engraver.py`'s own copy of the note data, built fresh from
    `Timeline.note_events` each time notation is engraved; the audio engine
    and the bars view's active-note highlighting keep using the real,
    unsnapped tick data on purpose.
    '''
    if not grid_denominator:
        return start_tick, end_tick
    step = max(1, (ticks_per_beat * 4) // grid_denominator)
    snapped_start = round(start_tick / step) * step
    snapped_end = round(end_tick / step) * step
    if snapped_end <= snapped_start:
        snapped_end = snapped_start + step
    return snapped_start, snapped_end


def quantize_duration_ticks(duration_ticks: int, ticks_per_beat: int, subdivision: int = 4) -> int:
    '''Snap a duration (in ticks) to the nearest grid step before
    classifying it, where the grid is `ticks_per_beat / subdivision` (the
    default, subdivision=4, is a sixteenth-note grid).

    Real (non-programmatically-quantized) MIDI files routinely encode note
    durations a few ticks short of the "intended" value — a note released
    slightly early, or a file authored by an arpeggiator/DAW export — which
    is inaudible but, fed raw into `classify_duration`, snaps to the nearest
    *exact* ratio and can misclassify a plain eighth note as a
    double-dotted sixteenth just because it's 8 ticks short. This is the
    "against a configurable grid" half of Plan Part 3.2's rhythm
    quantization: always-on, display-only duration snapping, distinct from
    Milestone 5's recording-quantization (which snaps a live take's *onset*
    into the actual saved note data, with an adjustable strength dial —
    this function never touches note timing, only what glyph gets drawn).
    '''
    step = max(1, ticks_per_beat // subdivision)
    return max(step, round(duration_ticks / step) * step)


def measure_ticks(ticks_per_beat: int, time_sig: tuple[int, int]) -> int:
    '''Length of one measure in ticks. ticks_per_beat is per quarter note
    (standard SMF division), so a measure is ticks_per_beat * 4 * num/den.
    '''
    num, den = time_sig
    return max(1, int(round(ticks_per_beat * 4 * num / den)))


def split_across_barlines(start_tick: int, end_tick: int, ticks_per_beat: int,
                           time_sig: tuple[int, int]) -> list[tuple[int, int]]:
    '''Split [start_tick, end_tick) at every measure boundary it crosses.

    A note entirely within one measure returns a single segment (its own
    start/end, unchanged) — the common case, no tie needed. A note spanning
    barlines returns one segment per measure it touches; the engraver ties
    consecutive segments together with a tie arc instead of drawing one
    notehead whose duration overruns the barline.
    '''
    m = measure_ticks(ticks_per_beat, time_sig)
    if end_tick <= start_tick:
        return [(start_tick, end_tick)]
    segments = []
    t = start_tick
    while t < end_tick:
        boundary = ((t // m) + 1) * m
        seg_end = min(end_tick, boundary)
        segments.append((t, seg_end))
        t = seg_end
    return segments
