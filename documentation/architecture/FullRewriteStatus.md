# Full Rewrite Status

Repo: C:\Users\crste\git\MidiVis2
Plan: documentation/architecture/FullRewritePlan.md

## Current milestone
4 — Notation/transcription + sprite atlas (done, plus seven post-milestone bugfixes
and one requested enhancement below; awaiting your test/commit)

## Post-Milestone-4 enhancement: "note accuracy threshold" setting

**Request**: in the traditional (sheet music) view, favor readability over strict
fidelity to MIDI timing — minor overlaps or late releases (ordinary performance noise)
should be ignored, with notes clamped to the nearest 1/32 note. Make the grid
resolution a setting rather than a hardcoded value.

**Design**: this is a *display-only* transform, applied fresh every time a file is
engraved — it never touches `Timeline.note_events`, playback, or the bars view's
active-note highlighting (all of which intentionally keep exact MIDI timing; the
readability tradeoff is specifically a notation-page concern, not a "the app plays the
wrong thing" concern).

- `midi/quantize.py` gained `snap_tick()`/`snap_note_span()`: snap an absolute tick (or
  both ends of a note) to the nearest point on a fixed rhythmic grid,
  `grid_denominator=32` by default (nearest 1/32 note), `grid_denominator=0` disabling
  snapping entirely for an "exact timing" option. `snap_note_span` also guards against
  a degenerate zero-length note if both ends round to the same grid point.
  `DEFAULT_SNAP_GRID = 32` is the one shared constant everything else below reads,
  instead of the value being duplicated across files.
- `notation/engraver.py`'s `engrave()` gained a `grid_denominator` parameter (default
  `quantize.DEFAULT_SNAP_GRID`) and now snaps every note's onset/release *before*
  chord grouping, rest-gap detection, or tie-splitting ever see it — building a fresh
  list of `NoteEvent`s rather than mutating the ones passed in, so `Timeline` itself
  stays untouched. This fixes the motivating case directly: a note released a few
  ticks late (overlapping the next note's onset) now snaps both ends onto the same
  clean grid point, removing the overlap instead of engraving it literally.
- `settings.py` gained a `'notation': {'snap_grid': 32}` default — the user-facing
  "note accuracy threshold".
- `App` gained `notation_snap_grid` (read from settings at startup in `main.py`, passed
  to `engraver.engrave()` in `load()`) and `set_notation_snap_grid(value)`, which
  updates the setting *and* immediately re-engraves the currently-loaded file (cheap —
  one pass over the file's notes, not a per-frame cost) so a menu change takes effect
  right away rather than only on the next file open.
- **View > Note Accuracy** menu (new, alongside the existing Color Theme/Slots
  submenus): Exact Timing / 1/16 Note / 1/32 Note (Recommended, the default) / 1/64
  Note, each a direct `app.set_notation_snap_grid(...)` + persisted to
  `settings['notation']['snap_grid']`. This is the "provide in the setting" half of the
  request — a real, discoverable UI control, not just an internal constant.

**Verification**: confirmed live-switching actually re-engraves with different data —
loaded `twinkle.mid`, sampled the first few engraved notes' ticks at the default 1/32
grid, then called `set_notation_snap_grid(0)` (exact timing) and confirmed the same
notes' ticks changed to their raw, unsnapped values (0,240→0,230 for the sampled
notes), then switched to a 1/16 grid and confirmed it re-engraved without error.
Re-rendered the traditional view headless and ran the full app-shell smoke test
(including simulating a real menu item click path) after wiring — no regressions.
Real-hardware `python main.py` launch still clean.

**Regression tests added**: `tests/test_quantize.py` gained `SnapTickTest` (3 tests)
and `SnapNoteSpanTest` (4 tests) covering the grid math directly, including the exact
"late release overlapping the next note" and "early overlapping onset" scenarios from
the request, and the zero-denominator disable path. `tests/test_engraver.py` gained
`NoteAccuracyThresholdTest` (3 tests): the same late-release-overlap scenario run
through the full `engrave()` pipeline and confirmed clean (no overlap survives), exact
timing preserved when `grid_denominator=0`, and a coarser 1/16 grid producing different
(more aggressively snapped) results than the default.
`python -m unittest discover -s tests -v` — **124/124 passing** (113 from before + 11
new).

## Post-Milestone-4 bugfixes (reported by user, fixed same session as reported)

### Bugfix 7: implausible double-dotted notes on ordinary sustained notes
**Symptom** (reported with a screenshot): a half note rendered with two augmentation
dots after it, in a spot that didn't musically make sense.

**Root cause**: `midi/quantize.py`'s `classify_duration()` picked the *nearest*
candidate duration by log-ratio distance, and double-dotted values (e.g. a
double-dotted half = exactly 3.5 beats) were in that candidate pool alongside plain
and single-dotted ones. Real (non-machine-quantized) MIDI files routinely encode a
sustained note a bit short of its "intended" round value — a note's natural release
trailing off before the next note starts, an early note-off, an export quirk —
commonly landing 10-15% short of a round number. A whole note performed as 3.5 out of
4 beats is numerically *closer* to "double-dotted half" (exactly 3.5) than to "whole"
(4.0, ~13% away) or "dotted half" (3.0, ~15% away), so the classifier picked the
double-dot — technically the nearest fit, but not what a human transcribing the same
performance would ever write, since double-dotted notation is rare and specifically
reserved for genuinely precise 3.5-beat rhythms, not inferred from an approximately
whole-note-length performed note. Confirmed via a direct dump across all four sample
files: every double-dot classification had a raw duration in the 3.45-3.6 beat range
(or, for a quarter-note case in `MIDI C Major.mid`, 1.7-1.9 beats) — imprecise timing,
not an intentional double-dot anywhere.

**Fix**: capped `_DOT_MULT` at a single dot (`{0: 1.0, 1: 1.5}`, removing the `2: 1.75`
entry) — double-dots are rare enough in practice that this classifier should never
reach for one as a "closest fit" guess; it now falls back to whichever ordinary
single-dot-or-plain candidate is nearest instead. `DurationClass.dots`'s docstring
updated from "0, 1, or 2" to "0 or 1" to match.

**Verification**: re-ran the double-dot dump across all four sample files
(`twinkle.mid`, `UndertaleMegalovania.mid`, `MIDI C Major.mid`, `HakunaMatata.mid`) —
zero notes classified with `dots >= 2` anywhere now (previously 20/2/2/29
respectively). Re-rendered the traditional view headless to confirm the fix doesn't
introduce any new visual regressions.

**Regression test updated**: `tests/test_quantize.py`'s `test_double_dotted_half` was
asserting the *old* (now-removed) behavior; replaced with
`test_dots_are_capped_at_one_even_for_an_exact_double_dot_value`, which feeds
`classify_duration()` the exact double-dot value (3.5 beats) and asserts it now falls
back to a plain whole note (`dots=0`) instead — the fix's actual behavior, not just
"dots never exceeds 1" as an isolated assertion.
`python -m unittest discover -s tests -v` — **113/113 passing** (one test's expected
values changed, none added/removed).

### Bugfix 6: overlapping/back-to-back same-pitch notes lost active-note highlighting early (or kept it too long)
**Symptom** (reported on `twinkle.mid`, one track unmuted): during playback, some
notes' highlight (bars-view piano strip / on-screen keyboard) didn't stay lit for the
note's full length, and in other cases stayed lit briefly after the bar had visibly
finished. User correctly diagnosed the likely mechanism themselves: "the second
overlapping note is clearing its highlight when the first note is released."

**Root cause**: `App.active_notes` was a plain `set[int]` — membership only, no
concept of "how many instances of this note are currently open." A single track can
legitimately retrigger the same pitch before its previous sounding ends (this is
exactly what `midi/load.py`'s `_events_to_notes` already models correctly, via a FIFO
queue per `(note, channel, track_id)` that pairs each note-on with the *next*
note-off — a real, common pattern for sustained/pedaled instruments, not a malformed
file). When that happens, `App._flat_events` contains two overlapping or back-to-back
(start, end) spans for the *same* note number. Processing them against a boolean set,
the first instance's note-off called `.discard(note)` unconditionally — turning the
note off in `active_notes` even while a second, still-sounding instance was open.
Confirmed this is a frequent real-world case, not a hypothetical: `twinkle.mid`'s
first Harp track alone contains **85** overlapping same-pitch note pairs.

**Fix**: added `App._active_note_counts: dict[int, int]`, tracking how many instances
of each note are currently open. A shared `_apply_event(kind, note)` helper
increments the count (and adds to `active_notes`) on note-on, decrements on note-off,
and only removes the note from `active_notes` once its count reaches zero. `update()`
and `_rebuild_active_notes()` (used by both live playback and `seek`/`seek_preview`)
both route through this one helper instead of duplicating the add/discard logic;
`_reset_playback()` clears the count dict alongside `active_notes`.

**Verification**: added a direct trace against the real overlapping pair `twinkle.mid`
actually contains (note 72, instances spanning 0.0–0.599s and 0.5–0.969s) — sampled
`72 in app.active_notes` at several points via `seek_preview()` and confirmed it now
stays `True` continuously from before the first instance starts through after the
second instance ends (0.1s through 0.9s), with no premature drop at 0.6s (right where
the old code would have cleared it when the first instance's note-off fired).

**Regression tests added**: `tests/test_app.py` gained `ActiveNotesOverlapTest` (4
tests) — drives `App._apply_event` directly (no file/engine needed) through the exact
overlapping-instance and back-to-back-instance sequences the bug covers, an unrelated-
notes-unaffected sanity check, and confirms `_reset_playback` clears the new counter
dict.
`python -m unittest discover -s tests -v` — **113/113 passing** (109 from before + 4
new in `test_app.py`).

### Bugfix 5: traditional view stuttered during playback ("freezes then jumps ahead")
**Symptom**: watching a file play in the traditional view, the screen would
occasionally freeze for a moment and then catch up, jumping ahead — described as
jarring since it breaks the sense of the notation smoothly following the music.

**Root cause**: `notation/glyphs.py`'s `GlyphAtlas.blit()` re-tinted a colored glyph
from scratch on *every single call* — `glyph.surface.copy()` (a fresh `Surface`
allocation) followed by a `BLEND_RGBA_MULT` fill — with no caching at all. Every
notehead, accidental, rest, flag, and augmentation dot the traditional view draws
passes a color, so a single busy frame could allocate and blend dozens of throwaway
surfaces, 60 times a second. The *audio* clock (wall-clock, per Milestone 2's design —
deliberately not paused by rendering) keeps advancing through any such hitch, so a
frame that takes noticeably longer than its budget doesn't just render late — the next
frame's `app.elapsed` has already moved forward by however long the hitch took,
producing exactly the reported "freeze, then jump ahead" rather than a smooth
slowdown. This is a real perf bug in code written this session, not present in the
bars view (which never used `GlyphAtlas`).

**Fix**: added a `_tint_cache: dict[(name, tier, color), Surface]` to `GlyphAtlas`,
populated lazily the first time a given glyph/tier/color combination is drawn and
reused on every subsequent call. The color set actually in play is small and
theme-driven (a handful of RGB tuples per palette), so the cache stays small and
bounded — confirmed empirically at 17-18 entries total across a whole file's worth of
frames, dark and light theme both exercised.

**Verification**: measured `TraditionalSlot.draw()` directly (bypassing the rest of the
event loop) over 300 frames on `UndertaleMegalovania.mid`'s dense passage — median
frame time dropped from 2.42ms to 1.92ms (~20% faster) and the worst-of-300 frame
dropped from 3.44ms to 2.84ms. Re-rendered dark→light→dark on `MIDI C Major.mid` using
the same `GlyphAtlas` instance across all three draws to confirm the cache doesn't leak
stale colors across a theme switch (each render showed the correct theme's colors, no
cross-contamination). Re-ran the full app-shell smoke test and a real-hardware
`python main.py` launch — no regressions.

**Regression tests added**: `tests/test_glyphs.py` (new) — asserts the cache behavior
directly: repeating the same (name, tier, color) reuses one cache entry; a different
color, or a different glyph name, each gets its own entry; an uncolored `blit()` (used
for clefs against a fixed staff color, so effectively unused today but part of the
public API) never touches the tint cache at all.
`python -m unittest discover -s tests -v` — **109/109 passing** (105 from before + 4
new in `test_glyphs.py`).

Note: this fix reduces the *average* rendering cost and, more importantly, the amount
of per-frame garbage generated (a likely contributor to intermittent GC-driven stutter
beyond what a tight synthetic benchmark loop can fully reproduce, since the real app
has audio/MIDI/other-slot activity running concurrently) — if any stutter is still
noticeable after this fix, it's worth another report with a screen recording or a note
of which file/zoom level triggers it, since there may be a second contributing factor
(e.g. the per-frame `enumerate(engraving.notes)` tie-pairing loop, which currently
walks the whole file's note list rather than just the visible window) not yet isolated.

### Bugfix 4: stems (and everything else positioned off a notehead) used the wrong x-origin convention
**Symptom** (reported with screenshots, after Bugfixes 2-3 were already in): stems
still looked disconnected from their noteheads — not a gap this time, but the stem
visibly cutting straight through the *middle* of the oval instead of attaching to its
side, "doesn't look like actual notes." User included a reference image of correctly-
engraved notation to clarify exactly what was wrong: real stems attach at the
notehead's right edge (for stem-up notes) or left edge (stem-down), not its center.

**Root cause**: a coordinate-convention mismatch introduced when the old hand-drawn
renderer's stem/ledger-line/dot/tie formulas were ported over. The old
`traditional_sheet.py` drew noteheads as polygons around a literal center point
`(cx, cy)`, so `_stem_data`'s `note_x + notehead_w // 2` correctly reached the right
edge (center + half-width). This session's `note_x` is computed the same way `bars.py`
positions note rectangles — as the note's time-based **left** edge — and
`GlyphAtlas.blit()` anchors noteheads at their own left edge too (all three notehead
glyphs have `minx=0`), so blitting the notehead directly at `note_x` was actually
correct *for the notehead itself*. But every formula ported from the old renderer
(`_stem_data`, `_draw_ledger_lines`, `_draw_dots`, the tie-arc endpoints in the main
`draw()` loop) still assumed `note_x` was the *center* — so `+ notehead_w // 2`
computed the horizontal *center* of the glyph (left edge + half-width), not its right
edge, and the stem was drawn straight through the middle of the (slanted, per Bravura's
design) oval instead of tangent to its side. The giveaway that this was a real,
pre-existing inconsistency (not something Bugfix 3 introduced): the accidental-
placement code inside `_draw_chord_heads` and the tie-arc endpoints were *already*
written assuming a center-based `note_x` — only the notehead blit itself and the
`geoms` dict that fed everything else were on the left-edge convention.

**Fix**: rather than auditing and re-deriving every individual offset formula, made
`note_x` consistently mean "notehead center" from the single point where it's computed
(in the geoms-building loop) onward — `note_x = left_x + notehead_w // 2`, where
`left_x` is the original time-based left edge (kept, under that name, only for the
off-screen culling check and the past/future color comparison, neither of which cares
about a half-notehead-width difference). This makes every downstream formula that was
already written for a center-based `note_x` (stems, ledger lines, dots, ties, beam
groups) correct without touching them. The one place that *did* need a matching change
is `_draw_chord_heads`'s notehead blit itself, which now shifts left by
`notehead_w // 2` before blitting, since `GlyphAtlas.blit` still anchors at the glyph's
own left edge — cancelling out the `geoms`-level shift so the notehead lands back at
its correct on-screen position while everything measured *from* `note_x` is now
correctly center-relative.

**Verification**: built an isolated headless test (quarter, half, whole, and a 2-note
chord, well-separated so none beam) and zoomed into the rendered PNG — stems now
visibly terminate flush against the notehead's edge (right edge for these stem-up
notes) rather than passing through its middle, for every note type tested including
chords (a single stem serving two stacked noteheads, attached at the outer edge, as
expected). Re-rendered `UndertaleMegalovania.mid`'s dense passage used in Bugfix 3's
verification — every note now visibly connects to its stem correctly; the passage is
still busy at default zoom (expected, per the density note in Bugfix 3/Milestone 4's
Deviations) but no longer looks structurally broken.

No regression test added — same reasoning as Bugfix 3 (pure glyph-offset geometry; a
numeric assertion would just re-state the `notehead_w // 2` arithmetic). Verified via
the headless isolated-note screenshot method, zoomed in enough to inspect the actual
pixel-level stem/notehead junction rather than eyeballing a full page.
`python -m unittest discover -s tests -v` — still 105/105 passing (no logic changed,
only positioning math).

### Bugfix 2: three real traditional-view rendering bugs, found via live testing
**Symptoms** (reported across several messages, with screenshots): (1) horizontal
"bars" rendered above the treble staff (and, less visibly, below the bass staff) that
weren't tied to any actual note needing a ledger line — described as "especially bad"
on dense 16th-note passages; (2) an individual notehead rendered with what looked like
stray ledger-line fragments cutting through it, "doesn't look like a traditional note
at all"; (3) with **all tracks unchecked** in the Tracks dropdown on `twinkle.mid`, the
bass staff still showed rest glyphs — should have been completely empty.

**Root causes** (three independent bugs, all in code written this session):

1. **Ledger lines compared an absolute step against relative thresholds.**
   `render/slots/traditional.py`'s `_draw_ledger_lines(surface, note_x, step, ...)`
   decides whether a note needs a ledger line via `step <= -2` (below the staff) or
   `step >= 10` (above it) — thresholds written for a step *relative to the staff's own
   bottom line* (0 = bottom line, 8 = top line; same convention the old
   `traditional_sheet.py` used). The call site was passing `n.pitches`' diatonic step
   straight from `midi/spelling.py`, which is an *absolute* step (high 20s/30s/40s for
   any real treble note, since it encodes octave too). Absolute steps are essentially
   always `>= 10`, so **every note** — regardless of whether it was anywhere near the
   staff — triggered the "needs a ledger line" branch. On a dense passage, many
   overlapping short ledger-line stubs (each individually correctly *positioned*, just
   wrongly *triggered*) chained together into what looked like continuous bars; on a
   single note, the same bogus stubs are what looked like fragments cutting through the
   notehead in the reported screenshot.
2. **`EngravedRest` had no `track_id` at all.** `notation/engraver.py`'s `_find_rests`
   already grouped rests by `(staff, track_id)` internally but discarded the track_id
   (`for (staff, _track_id), spans in lanes.items():`) before constructing the
   `EngravedRest` — so there was no field for the renderer to filter on, and
   `render/slots/traditional.py`'s rest-drawing loop had no way to honor
   `app.enabled_tracks` for rests the way it already did for notes. Muting every track
   correctly hid all notes but left every rest rendered.
3. **Notes/bars weren't clipped to the staff area** — `TraditionalSlot.draw()`'s
   `screen.set_clip(...)` left edge was `rx` (the whole panel, including the clef box to
   the left of `staff_x0`), not `staff_x0` itself. A note scrolled far enough left of the
   playhead (`note_x < staff_x0`) was still inside that wider clip rect and could render
   on top of the clef.

**Fixes**:
1. Re-base the step before calling `_draw_ledger_lines`: `step - ref_step` (where
   `ref_step` is `TREBLE_REF_STEP`/`BASS_REF_STEP` for that note's staff), computed at
   the actual call site rather than inside the function (the function's own thresholds
   are correct for a relative step; the bug was purely in what the caller passed it).
2. Added `track_id: int` to `EngravedRest`; `_find_rests` now keeps and passes it
   through instead of discarding it as `_track_id`. `traditional.py`'s rest loop gained
   `r.track_id not in enabled` alongside its existing staff check.
3. Moved the clef glyph blits to *before* `screen.set_clip(...)` is applied, and
   tightened the clip rect's left edge from `rx` to `staff_x0` — everything drawn after
   that point (staff lines, measure lines, notes, ties, rests, playhead) is now clipped
   to the staff area only; the clef box to its left is drawn once, outside the clip, and
   can no longer be overdrawn by scrolled note content.

**Verification**: re-rendered `UndertaleMegalovania.mid` headless after the ledger-line
fix — the phantom bars above the treble staff are gone entirely, confirmed by visual
diff against the pre-fix screenshot. Reproduced the user's exact "twinkle.mid, all
tracks unchecked" scenario headless — bass staff (and treble) now render completely
empty, no rests. Re-ran the full app-shell smoke test (`Dashboard`/`SlotManager`/
`SheetSlot`, `twinkle.mid`, all four tracks enabled) and saved a full-window screenshot
— no phantom bars, no notes overlapping the clef glyphs.

**Regression tests added**: `tests/test_traditional_ledger_lines.py` (new) — drives
`_draw_ledger_lines` directly against a real (headless) `pygame.Surface` and asserts
pixel output: no lines drawn for relative steps within/just-outside the staff (4, 9),
lines drawn for steps that actually need them (10, -2), plus one test that names the
bug shape explicitly (passing an absolute step like 30 *does* wrongly draw a line,
documenting the exact distinction the fix depends on). `tests/test_engraver.py` gained
`test_rest_carries_the_track_id_of_its_lane`, asserting `EngravedRest.track_id` matches
the source notes' track. No test added for the clipping fix — it's a pure rendering/
compositing concern (pygame's clip rect), verified by the same headless-screenshot
method as the other two.
`python -m unittest discover -s tests -v` — **105/105 passing** (99 from Milestone 4 +
1 new in `test_engraver.py` + 5 new in `test_traditional_ledger_lines.py`).

### Bugfix 3: unbeamed eighth/sixteenth-note flags overlapped their own notehead
**Symptom** (reported with a screenshot, after Bugfix 2's fixes were already in):
"note head rendering is still quite broken" — flagged (unbeamed eighth/sixteenth) notes
rendered with the flag glyph appearing to sit right on top of / wrap around the
notehead itself, rather than hanging cleanly above or below it at the end of a visible
stem.

**Root cause**: `render/slots/traditional.py`'s `_stem_data()` defaulted unbeamed-note
stem length to `LS * 2.2` (~53px at the app's fixed staff size). Measured the actual
Bravura flag glyphs this session (`flag8thUp`/`flag8thDown`/`flag16thUp`/
`flag16thDown` are all ~79px tall at this tier, ~3.3 staff-spaces — a normal SMuFL flag
height, since a flag is designed to hang a specific distance down the stem it attaches
to). A 53px stem is *shorter* than the 79px flag hanging from its tip, so the flag's
notehead-ward end always overshot 26px past the stem's own base and rendered on top of
the notehead — this was wrong for every single flagged note, not an edge case.

**Fix**: raised the default stem length to `LS * 3.5` (~84px) — comfortably longer than
the tallest flag glyph, matching standard engraving practice (a flagged note's stem is
conventionally about the same length regardless of note value, sized to clear its
flag). Beamed notes are unaffected — `_draw_beam_group` always passes its own explicit
`stem_ext` (`LS * 2.5`), which this default never applies to.

**Verification**: re-rendered isolated (non-adjacent, so unbeamed) eighth and sixteenth
notes at both stem directions — flags now hang from a clearly visible stem, ending just
short of the notehead rather than overlapping it. Re-checked against
`UndertaleMegalovania.mid`'s dense passages: individual flagged notes look correct now;
some visual crowding remains where an unbeamed note's flag (glyph width ~26-30px) sits
close to a neighboring note only ~17px away in time at the default zoom — traced this
to real (not buggy) tick-level beat bucketing: confirmed via a direct dump of
`engraving.beam_groups` that adjacent eighth notes *do* pair up into beam groups
whenever the data supports it (e.g. two eighths correctly filling one beat), and the
remaining unbeamed notes are ones with no same-beat partner, which correctly get an
individual flag per standard notation rules. This residual crowding is the same
default-zoom density characteristic already noted in Milestone 4's Deviations (the
app's existing Ctrl+scroll zoom addresses it) — not a new defect, and distinct from the
flag/notehead overlap this fix actually corrects.

No regression test added — this is pure glyph-geometry/spacing, the same category as
Milestone 3's reset-icon-arrowhead bugfix (a numeric assertion would just re-encode the
`LS * 3.5` constant rather than verify anything independent); verified via the headless
isolated-note screenshot method instead.
`python -m unittest discover -s tests -v` — still 105/105 passing (no logic changed,
only a rendering constant).

### Bugfix 1: inconsistent spacing between the dashboard's Bars/Traditional/Tracks buttons
**Symptom** (reported with a screenshot): the gap between "Traditional" and "Tracks"
was visibly smaller than the gap between "Bars" and "Traditional" — the two buttons
looked like they were touching.

**Root cause**: an arithmetic slip while adding the Bars/Traditional group in
`render/dashboard.py`'s `Dashboard.__init__`. The layout convention (established in
Milestone 3, confirmed by re-deriving it: New File→Open File is 50px apart within a
group, Open File→Play has a 42px gap between groups) means a new *group*'s top should
sit `BTN_H` (42px) past the previous group's bottom. Traditional's bottom is
`y0+298+42 = y0+340`, so Tracks should start at `y0+340+42 = y0+382` — instead it was
placed at `y0+340` (Traditional's bottom exactly), a copy-paste-arithmetic error that
put zero gap between them instead of the intended 42px.

**Fix**: `btn_tracks` moved from `y0+340` to `y0+382`; the third chrome separator moved
from `pt+330` to `pt+372` (10px above Tracks' new top, matching the other two
separators' 10-above-their-group convention). Verified via the same headless-screenshot
method as the layout/icon bugfixes in Milestone 3 — cropped the dashboard region of a
fresh render and visually confirmed the three button-group gaps now read as consistent.
`python -m unittest discover -s tests -v` — still 99/99 passing (no test covers pixel
layout, same reasoning as Milestone 3's analogous title-overlap bugfix).

## Post-Milestone-3 bugfixes (reported by user, fixed same session as reported)

### Bugfix 1: releasing Shift didn't release notes latched via the on-screen keyboard's sustain-pedal modifier
**Symptom**: on the on-screen keyboard (`KeyboardSlot`), holding Shift and clicking a
key latches it (per Plan Part 1's "Shift = latch/sustain toggle"), but releasing the
Shift key did nothing — the note kept sounding until you clicked it again. User's own
framing ("the shift key is the sustain pedal key") makes clear the expected semantics:
releasing the pedal should release whatever it's holding, like a real sustain pedal,
not require a second deliberate click per note.

**Root cause**: `KeyboardSlot.handle_event()` (ported near-verbatim from the old repo's
`ui/slots/keyboard.py`) only ever read the Shift modifier live, inside mouse-event
branches, to decide whether a click toggles a note into `app.kb_notes` versus playing
it normally. Nothing in the method — old or new — ever handled `pygame.KEYUP`, so
releasing Shift was simply invisible to it; a latched note stayed in `app.kb_notes`
(and therefore audible, since `AudioEngine.note_on`/`note_off` calls are the only thing
gating the actual sound) indefinitely.

**Fix**: `KeyboardSlot.handle_event()` now handles `pygame.KEYUP` for
`K_LSHIFT`/`K_RSHIFT` explicitly: it calls `app.kb_note_off()` for every note
currently in `app.kb_notes` (a snapshot copy, since `kb_note_off` mutates that set)
and returns `False` (doesn't consume the event — nothing else in this milestone's UI
cares about Shift release). This clears *all* currently-held on-screen-keyboard notes
on pedal release, not just ones latched via Shift-click — matches real sustain-pedal
behavior, and the only other way a note ends up in `kb_notes` is an in-progress plain
click-drag, where cutting it off on an incidental Shift release mid-drag is a rare,
harmless edge case (the drag's own `MOUSEBUTTONUP` handler still runs afterward and
just no-ops on a note that's already off).

**Regression test added**: `tests/test_keyboard_slot.py` (new file) — drives
`KeyboardSlot` directly against a minimal fake `App` (just `kb_notes`/`kb_note_on`/
`kb_note_off`), faking `pygame.key.get_mods()` for the duration of a simulated click so
the test doesn't depend on real OS key state. Covers: a Shift-click latches a note past
mouse-up (confirms the *original*, still-intended latch behavior wasn't broken by the
fix); Shift KEYUP releases every currently-latched note; Shift KEYUP with nothing
latched is a no-op that doesn't consume the event. 3 new tests.
`python -m unittest discover -s tests -v` — 61/61 passing (58 from Milestone 3 + 3 new).

### Bugfix 2: dashboard title text overlapping the "New File" button
**Symptom** (reported with a screenshot): the "MIDI VIS" title label at the top of the
left dashboard panel visibly overlapped the "New File" button directly below it.

**Root cause**: `render/dashboard.py`'s title-and-button y-offsets (`title` at `pt + 6`,
`btn_new` at `y0 + 16`) were ported directly from the old repo's identical constants.
Measuring the actual rendered height of the `small` font's "MIDI VIS" text on this
machine (`pygame.font.SysFont('segoeui', 11)`, 15px tall including line spacing) showed
the title's bottom edge landing at y=45 while the button's top edge started at y=40 — a
real 5px overlap, not a rounding artifact. (The old repo carried the same numbers; either
it had the same latent overlap and nobody happened to look closely, or font metrics
differ enough across machines/font-fallback that it didn't show up there. Either way,
±5px of margin is too fragile to rely on.) This was never caught in this session's own
Milestone 3 testing because none of the smoke tests actually *looked* at the rendered
window — they checked for crashes and simulated event outcomes, not visual layout.

**Fix**: shifted every dashboard button (and both chrome separator lines) down by a
uniform 14px in `render/dashboard.py` — preserves every *relative* gap between buttons/
separators (verified by re-checking each pair's spacing arithmetic against the old
values), just adds real clearance below the title. Re-measured after the fix: title
bottom at y=45, first button top now at y=54 — a 9px clear gap.

**Verification**: rendered the dashboard to an actual `pygame.Surface` (headless,
`SDL_VIDEODRIVER=dummy`) and saved it as a PNG to visually confirm the fix, rather than
trusting the arithmetic alone — no automated test covers pixel-level layout like this,
and none was added (a numeric layout assertion would be brittle against font/theme
changes; this is the kind of thing a screenshot check is actually right for). Not
checked into `tests/`.

### Bugfix 3: reset button's icon rendered as a malformed blob instead of an arrowhead
**Symptom** (reported with a zoomed screenshot): the dashboard's circular-arrow "reset"
icon showed a garbled flag/hook shape instead of a clean triangular arrowhead.

**Root cause**: `_icon_reset()` in `render/dashboard.py` (ported verbatim from the old
repo) computes the arrowhead as a triangle: a tip extended along the arc's tangent
direction at its start point, plus two base points offset perpendicular to that tangent.
The perpendicular vector was computed wrong — `perp_x = -tang_y` was correct, but the two
base points' y-coordinates were computed inline as `ty + w * (-tang_x)` and
`ty - w * (-tang_x)` instead of using the corresponding `perp_y = tang_x`. Concretely, for
the icon's actual tangent (`tang = (-0.866, -0.5)` at the arc's 60° start angle), the code
used offset vector `(0.5, 0.866)`, but the true perpendicular is `(0.5, -0.866)` — the
y-component's sign was flipped. A dot product confirms `(0.5, 0.866) · (-0.866, -0.5) =
-0.866 ≠ 0`, i.e. the "perpendicular" wasn't perpendicular at all, so the two base points
weren't symmetric around the tangent point and the "triangle" came out skewed into a
blob rather than a clean arrowhead. This is exactly the kind of small hand-derived-trig
bug the Plan's Part 2 notes call out about the old repo's hand-drawn vector icons in
general (there, about the notation renderer's rests; same underlying fragility here).

**Fix**: rewrote the vector math cleanly — `perp_x, perp_y = -tang_y, tang_x` (a proper
90° rotation of the tangent vector), then `tip`/`p1`/`p2` all built from named, correctly
signed vectors instead of inline sign-flipped expressions. No behavior change intended
beyond fixing the shape — same arc, same triangle size/position, just geometrically
correct now.

**Verification**: rendered the button in isolation to a PNG (zoomed 8x, headless) before
and after the fix to visually confirm — this is a pure-rendering bug with no meaningful
non-visual assertion to unit test (the "correct" output is "looks like an arrowhead",
which a screenshot check is the right tool for, not a pixel-coordinate assertion that
would just re-encode the same fixed math it's supposed to verify). Not checked into
`tests/`.

`python -m unittest discover -s tests -v` — still 61/61 passing after Bugfixes 2-3
(neither touched any code with existing test coverage).

## Post-Milestone-2 bugfixes (reported by user, fixed same session as reported)

### Bugfix 1: pausing reset the track to the beginning
**Symptom**: pressing Space to pause reset the track back to the beginning instead of
holding position — exactly the kind of thing this rewrite was supposed to fix, so this
was a real regression, not old behavior resurfacing.

**Root cause**: `fluid_player` has no distinct "paused" state — its only statuses are
READY/PLAYING/STOPPING/DONE. `FluidPlayerBackend.pause()`'s `fluid_player_stop()` call
settles the physical player at `FLUID_PLAYER_DONE`, indistinguishable at the C API
level from the song actually finishing. `FluidPlayerBackend.get_status()` mirrored that
raw physical status unconditionally, and `App.update()` polls `get_status() == DONE`
every frame to detect real song-end and reset position to 0 — so on the very next
frame after any ordinary pause, `update()` mistook the pause for the song ending and
zeroed `elapsed`. This is a side effect of a fix made *within* Milestone 2's own
session (removing `App.update()`'s old `self.playing` guard, which had been
masking genuine end-of-song detection — see the `AudioEngine.stop()` deviation note
below) — the guard removal was correct for real song-end, but exposed this second,
previously-masked case.

**Fix**: `FluidPlayerBackend.get_status()` ([midivis/audio/fluid_player.py](../../../midivis/audio/fluid_player.py))
now only consults the physical player status while `self._playing` (the backend's own
play/pause intent flag) is still `True`; once `pause()`/`stop()` has been called it
reports `READY` unconditionally, regardless of what the physical player settled into.
Real song-end is still detected correctly because `self._playing` stays `True` for the
whole natural PLAYING→DONE transition (nothing calls `pause()` on our behalf when a
song just ends).

**Verified against real hardware** (throwaway scripts, not checked in): (1) play 2s,
pause, poll `app.update()` for 1.5s simulating idle frames while paused — elapsed held
exactly steady, no drift; resumed play continued from the paused position, not 0.
(2) seek near end of file while playing, poll until real DONE — `elapsed` correctly
resets to 0, `get_status()` reports READY (not raw DONE) once stopped, and a
subsequent `play()` restarts cleanly from 0 — confirms genuine song-end detection
(the thing `tests/test_app.py` was written to protect) is unaffected by this fix.

**Regression test added**: `tests/test_fluid_player.py` (new file) — the existing
stub-engine-based `test_app.py` can't exercise this, since the stub doesn't model
`fluid_player`'s DONE-on-pause quirk; the bug lives entirely inside
`FluidPlayerBackend.get_status()`'s physical-status-vs-own-intent-flag logic.
Constructs a `FluidPlayerBackend` via `__new__` (bypassing `__init__`, which loads the
real `libfluidsynth-3.dll` — this way the test needs no FluidSynth install/hardware)
with a fake `._ffi.fn['player_get_status']` returning a canned raw status, and checks
`get_status()` against all four combinations of `{paused, playing} x {raw status
DONE, raw status PLAYING}`: reports READY whenever paused regardless of raw status
(the fix), and mirrors the real raw status whenever still playing, including
DONE (real song-end must still be detected). 5 tests, all passing.
`python -m unittest discover -s tests -v` — 22/22 passing (17 from before + 5 new).

### Bugfix 2: seeking while paused had no audible effect
**Symptom** (reported immediately after Bugfix 1 was fixed): seeking while paused
appeared to do nothing — pressing Space to resume played from the original pre-seek
position, not the seeked-to position.

**Root cause**: `fluid_player_seek()` can return `-1` (failure, no effect) for roughly
10-30ms right after `fluid_player_play()` is called — confirmed on real hardware via
`fluid_player_get_current_tick()`/checking the raw return code directly: 9-26 retry
attempts at a 1ms poll interval were needed before `player_seek()` returned `0`
(success), across 5 trials. `fluid_player_get_status()` flips to `PLAYING`
*synchronously* inside `fluid_player_play()`, but the internal state
`fluid_player_seek()` depends on evidently settles *asynchronously* on the player's
own thread — so status already reads PLAYING while seeking is still not yet possible.
Neither `FluidPlayerBackend.seek()` nor `_silent_play_seek()` (used inside `play()`)
were checking `player_seek()`'s return code — both are ported/adapted from the old
repo's `FluidEngine`, which had the same gap — so this failure has silently existed
since the very first `fluid_engine.py` in the old repo; it was never noticed there
because the *only* case that exposes it (seek while paused, before ever resuming) may
not have been exercised as directly, or the old app's threading/timing happened to
usually win the race. It's deterministic on this machine with today's code, not a
rare race.
**Why Bugfix 1's own hardware verification didn't catch this**: that verification
checked `app.elapsed` (our own Python wall-clock bookkeeping, set unconditionally by
`seek()` regardless of whether the underlying `player_seek()` call actually
succeeded) — never the actual physical `fluid_player` tick position. Plain
resume-without-seeking happened to still look/sound correct even with this bug present,
because `fluid_player_play()` resumes from its last real position rather than
restarting at 0 when stopped mid-song (only a genuinely fresh/finished player restarts
at 0) — so the failing, unchecked `player_seek()` call simply had nothing to change
in that case. The bug is only audible when a seek actually needs to move the position
before the next resume, which is exactly this report's scenario and wasn't covered by
Bugfix 1's manual checks.

**Fix**: added `FluidPlayerBackend._seek_with_retry(ticks)`
([midivis/audio/fluid_player.py](../../../midivis/audio/fluid_player.py)) — retries
`player_seek()` up to `_SEEK_RETRY_ATTEMPTS` (150) times at `_SEEK_RETRY_DELAY_S`
(1ms) intervals until it returns `0`, a generous margin over the observed 9-26
attempts; logs a warning and gives up if the cap is somehow exceeded rather than
looping forever. Used by both `seek()` and `_silent_play_seek()`. This does mean a
seek can now briefly (typically ~10-30ms, observed) block the calling thread — main.py
calls these synchronously from the UI event loop, so a seek can cost roughly one frame
at 60fps in the worst common case; imperceptible for a one-off user action (click,
press Space), not attempted to be made async this milestone.

**Verified against real hardware**: polled `fluid_player_get_current_tick()` directly
through the exact play→pause→seek(to 20s)→wait→play sequence from the bug report.
Before the fix: tick stayed pinned near the original pause position (~763, i.e. ~2s)
even 180ms after resuming — matching the reported symptom exactly. After the fix: tick
jumps to ~7698 (target was tick 7680, i.e. ~20s) within tens of milliseconds of
resuming. `python main.py` manually exercised: pause, click a new timeline position,
Space to resume — now audibly resumes from the clicked position.

**Regression test added**: `tests/test_fluid_player.py`'s new `SeekWithRetryTest` —
drives `_seek_with_retry()` directly (via the same `__new__`-bypass-`__init__`
pattern as Bugfix 1's tests, so no FluidSynth install/hardware needed) with a fake
`player_seek` that fails a configurable number of times before succeeding:
retries-until-success (succeeds on the Nth call), succeeds-immediately (1st call),
and gives-up-after-`_SEEK_RETRY_ATTEMPTS`-attempts-instead-of-looping-forever (fake
`player_seek` that never succeeds). `time.sleep` is mocked out so these run instantly
despite exercising the real retry loop. 3 new tests.
`python -m unittest discover -s tests -v` — 25/25 passing (22 from Bugfix 1 + 3 new).

## Completed milestones
4 — Notation/transcription + sprite atlas. Done this session:
- **`assets/fonts/Bravura.otf` + `OFL.txt`** (new, downloaded from
  `steinbergmedia/bravura`'s `master` branch, SIL Open Font License) — see
  Deviations for why this replaces Plan Part 3.3's planned hand-drawn/
  commissioned `assets/glyphs/` SVG source entirely: `pygame.font.Font` loads
  an arbitrary font *file* directly (not an OS-installed font by name), so
  bundling a real SMuFL font sidesteps the old renderer's exact failure mode
  (silently missing glyphs) without hand-authoring vector art at all.
- **`tools/build_atlas.py`** (new) — offline pipeline: rasterizes a curated
  29-glyph subset of Bravura (clefs, noteheads, accidentals, rests, flags,
  augmentation dot, time-sig digits) at 3 fixed staff-space sizes (14/24/44px
  — `sm`/`md`/`lg`) via `pygame.font.Font`, crops each tight (derived the
  crop/anchor math from `Font.metrics()`/`get_ascent()` empirically — see the
  module docstring), and packs them into one atlas. Run via
  `python tools/build_atlas.py`; only needs re-running if the glyph list or
  tier sizes change, not part of the app's runtime startup.
- **`assets/atlas/glyphs.png` + `glyphs.json`** (new, generated + checked in)
  — the packed sheet + manifest (`{tier: {glyph_name: {x,y,w,h,anchor_x,
  anchor_y}}}`) `notation/glyphs.py` loads at runtime.
- **`midivis/notation/glyphs.py`** (new) — `GlyphAtlas`: loads the atlas once,
  `get()`/`blit()` by (name, tier) with a `color=` tint (glyphs are
  rasterized white-on-transparent; tinting multiplies RGB while preserving
  each pixel's own anti-aliased alpha). `nearest_tier()` exists for a future
  per-DPI/zoom setting; the traditional view currently pins one fixed tier
  (`'md'`) — see Deviations.
- **`midivis/midi/quantize.py`** (new) — `classify_duration()` (duration in
  beats -> note type + dots + triplet, via nearest log-ratio match over a
  candidate table, replacing the old `_note_type`'s fixed-threshold
  bucketing), `measure_ticks()`/`split_across_barlines()` (tie-across-barline
  splitting), and `quantize_duration_ticks()` (snap a raw tick duration to a
  16th-note grid before classifying — added mid-session after real sample
  files showed *why* this is needed; see Deviations).
- **`midivis/midi/spelling.py`** (new) — `spell(note, key_sig)`: key-
  signature-aware enharmonic spelling. Fixes not just *which accidental
  symbol* gets drawn (the literal bug Plan Part 2 calls out) but the deeper
  version of it: which *staff position* a black key gets drawn at, since C#
  and Db are the same pitch but sit on different lines. Scope is deliberately
  bounded to single sharp/flat spelling (no double-accidentals) — see
  Deviations.
- **`midivis/notation/engraver.py`** (new) — `engrave()`: Timeline + TempoMap
  -> `Engraving` (chords grouped by tick-tolerance per (staff, track) lane,
  rests found from the gaps, ties split across barlines, notes bucketed into
  beam groups), all in ticks-and-precomputed-seconds, no rendering. Adapted
  from the plan's literal "laid-out glyph placements" framing since this
  app's staff scrolls live (see the module docstring for why baking pixel
  positions here would be wrong).
- **`midivis/render/slots/traditional.py`** (new) — the grand-staff view:
  `GlyphAtlas` blits for clefs/noteheads/accidentals/rests/flags/dots;
  procedural `pygame.draw` for stems, primary+secondary beams, ledger lines,
  staff lines, and (new — the old renderer never computed these) tie arcs.
  Active/past/future note coloring and click-drag vertical scroll ported
  from the old `traditional_sheet.py`'s equivalent behavior.
- **`midivis/render/slots/sheet_slot.py`** (new) — the `app.view`-driven
  dispatcher Milestone 3 deferred (`BarsSlot` was registered directly under
  the `'sheet'` id since only one view existed yet).
- **`midivis/app.py`** (grown) — `view: str = 'bars'`, `trad_scroll: float =
  0.5`, `engraving: Engraving | None`, built once in `load()` (right after
  `key_sig`/`time_sig` are known) via `engraver.engrave(...)` — not
  recomputed per frame or per track-mute-toggle; `TraditionalSlot` filters
  `app.engraving.notes`/`.rests` by `track_id in app.enabled_tracks` at draw
  time instead, since chord/rest/beam grouping is already per-(staff,track)
  lane and unaffected by which *other* tracks are muted.
- **`midivis/render/dashboard.py`** (grown) — Bars/Traditional toggle
  buttons (deferred from Milestone 3's "no view-mode toggle" scope note),
  inserted between the Play/Reset row and the Tracks button; every button
  below shifted down accordingly (Tracks now at `y0+382`, was `y0+248`) with
  a third chrome separator added above Bars. (Tracks' offset was originally
  miscalculated as `y0+340` — zero gap after Traditional — caught and fixed
  same session; see Post-Milestone-4 bugfixes above.)
- **`midivis/render/fonts.py`** (grown) — `measure_trad` font restored
  (Milestone 3 dropped it as "traditional-notation-only").
- **`midivis/render/theme.py`** (grown) — `trad_*` palette keys (background,
  divider, staff/bar/playhead/measure-number/note colors) for both themes,
  ported from the old `TraditionalSheetSlot._SLOT_COLORS`.
- **`main.py`** — registers `SheetSlot()` in place of `BarsSlot()`; no other
  changes.
- `tests/test_spelling.py`, `tests/test_quantize.py`, `tests/test_engraver.py`
  (all new) — pure-function unit tests per the Plan's Verification section.
  38 new tests total.
- Manually verified via headless rendering (see Test results below) —
  real hardware `python main.py` smoke test only (no audio-path changes this
  milestone, so no new hardware-specific behavior to verify beyond "still
  launches cleanly").

3 — UI shell + widgets + slots. Done this session:
- `midivis/render/theme.py` (new) — one consolidated `THEMES` dict (dark/light) covering
  every UI surface: shared slot infra (handle/scrollbar), dashboard chrome, menu bar, and
  — new relative to the old repo — the **track dropdown**, which the old
  `ui/dashboard.py` hardcoded in literal colors and which Light theme silently did nothing
  for (Plan Part 2's called-out bug). Replaces the old repo's two-dict `SLOT_THEMES`/
  `UI_THEMES` split.
- `midivis/render/widgets/` (new package) — the five widgets Plan Part 3.4 names:
  - `button.py` — `Button`, ported from the copy that used to live inline in
    `ui/dashboard.py`.
  - `menu.py` — `MenuItem`/`TopMenu`/`Dropdown`/`MenuBar`. `Dropdown` is the one
    parameterized hit-test/draw component the old `ui/menu_bar.py`'s six duplicated
    blocks (File dropdown, its Recent submenu, View dropdown, its Theme submenu, its
    Slots submenu, Keyboard dropdown) collapse onto; `MenuBar` composes two `Dropdown`s
    (top-level + one submenu level, matching the old system's actual max nesting depth)
    and drives them from a per-top-menu `items_fn() -> list[MenuItem]` callable so
    content can reflect live state (recent files, theme/slot checkmarks) without the
    widget knowing what any of that state means.
  - `scrollbar.py` — `VerticalScrollbar`, the one shared drag-thumb implementation now
    used by both the bars view's roll scrollbar and (structurally ready for) anything
    else that needs one — the old repo had bars_sheet.py's version as the only real
    implementation.
  - `mini_keyboard.py` — shared `is_black`/`white_index` note-geometry helpers, used by
    both `KeyboardSlot` (interactive) and `BarsSlot`'s piano strip (display-only) instead
    of each independently reimplementing the same math. Deliberately *not* a single
    widget that also owns drawing — see the module's docstring for why forcing one
    draw() over both would be the wrong abstraction.
  - `text_input.py` — `TextInput`, extracted from the old record-arm panel's hand-rolled
    cursor/insert/delete/click-to-position code. **Not wired into anything this
    milestone** — the record-arm panel it came from is Milestone 5 (recording) — built
    now, as its own tested unit, so M5 can consume it directly. See Deviations.
- `midivis/render/fonts.py` (new) — lazy font cache, ported from the old `ui/fonts.py`
  (`get_fonts()`, `symbol_font()` for the menu's ► / ✓ glyphs). Dropped
  `measure_trad`/`normal_bold` (traditional-notation-only, Milestone 4).
- `midivis/render/slots/` (new files: `slot_base.py`, `slot_manager.py`, `timeline.py`,
  `bars.py`, `keyboard.py`, `properties.py`) — the view stack. `slot_manager.py` fixes
  both bugs Plan Part 2/3.4 call out by name in the old `ui/slot_manager.py`, made while
  rebuilding it rather than patched after — see that file's module docstring for the
  exact mechanism of each fix, and `tests/test_slot_manager.py` for the regression tests:
  - **Single-flex-slot limitation**: `rects()` now splits leftover height evenly across
    however many `fixed_height=None` slots are visible (remainder pixels go to the last
    one), instead of giving 100% of the leftover to any one of them.
  - **Click-priority-vs-visual-order mismatch**: `handle_event()` now dispatches
    non-timeline slots in `self._order` (the same list drag-to-reorder mutates) instead
    of a hardcoded `('sheet', 'keyboard', 'properties')` tuple.
  - Also fixed the O(n) `render()` calling `rects()` once per slot instead of once per
    frame (Plan Part 2's "rects() is redundantly recomputed" note).
  - `bars.py` (renamed from `bars_sheet.py`/`BarsSheetSlot` → `BarsSlot`, keeping the
    `'sheet'` slot id) drops the live-recording note overlay (Milestone 5) and now sits
    on `VerticalScrollbar`/`mini_keyboard` instead of locally-duplicated copies.
  - `properties.py` drops the recording-state indicator and the MIDI-input-device column
    — both Milestone 5 concerns (`recorder`/`midi_input` don't exist in `App` yet).
  - No `sheet_slot.py` dispatcher this milestone — traditional notation doesn't exist
    yet, so `BarsSlot` is registered directly as the `'sheet'` slot; Milestone 4 adds the
    bars/traditional dispatch layer when there's a second view to dispatch to.
- `midivis/render/dashboard.py` (new) — left panel: New/Open file, Play/Pause, Reset,
  Tracks dropdown (per-track mute + Select All/None). Ported from the old
  `ui/dashboard.py` minus the record-arm panel (Milestone 5) and the Bars/Traditional
  view toggle (Milestone 4 — only one view exists so far) — see Deviations for why this
  trims the old 1145-line file down substantially rather than porting it whole.
- `midivis/midi/instruments.py` (new) — GM instrument/drum-kit/drum-note name tables,
  ported verbatim from the old repo's `midi_instruments.py`. Needed by the properties
  panel's instrument list.
- `midivis/midi/analyze.py` (new) — `get_tempo`/`get_time_signature`/`get_key_signature`/
  `detect_key_signature`, ported from the old repo's `midi_analyzer.py` (minus its
  instrument-table re-exports, which now live in `instruments.py` directly).
- `midivis/midi/channel_remap.py` (new) — `remap_channels()`, ported from the old
  `midi_processing.py`. This is the **basic** remap Milestone 3 needs for per-track mute
  to be channel-accurate; the two known gaps (>15 simultaneous melodic tracks, multiple
  simultaneous drum tracks) are explicitly still Milestone 5's "channel-remap edge-case
  fixes" — see Deviations for how this resolves the ambiguity the previous session's
  notes flagged.
- `midivis/midi/load.py` (new) — `load_timeline()` (SMF → `Timeline`, replacing the old
  `midi_processing.build_timeline`/`build_note_events`) plus `get_track_names`/
  `get_track_channels`/`get_instruments`/`build_measure_times`, folded into the same
  module for the same reason the old repo kept them together (`midi_processing.py`): all
  "read track/structural metadata out of an SMF" with no dedicated home in Plan Part 3's
  tree. `load_timeline` builds `NoteEvent`s directly in **ticks** (no tempo map needed at
  build time — a structural improvement over the old build_timeline, which pre-converted
  to seconds during construction, matching how `midi/model.py`'s `NoteEvent` docstring
  already said ticks should work).
- `midivis/app.py` (grown, not rewritten) — `App` gains: `tracks`/`enabled_tracks`/
  `track_channels`/`instruments` + `set_all_tracks()`/`toggle_track()`/
  `_update_track_muting()` (per-track mute, calling `engine.set_channel_muted`);
  `timeline`/`note_events`/`active_notes` + incremental/rebuild active-note tracking
  (ported from the old App's `_sync_event_index`/`_rebuild_active_notes`/`update()` tail
  loop, now over a precomputed `_flat_events` list instead of walking raw MIDI messages);
  `bpm`/`time_sig`/`key_sig`/`measure_times`; `kb_notes`/`kb_note_on()`/`kb_note_off()`
  (on-screen keyboard passthrough, bypassing the player exactly like the old app);
  `sheet_zoom`/`bars_scroll`/`properties_expanded`; and `seek_preview()` for
  drag-scrubbing. See Deviations for `seek_preview()`'s design — it had to be rethought,
  not just ported, because Milestone 2 moved clock ownership into the engine.
- `main.py` — replaced Milestone 2's throwaway 900x220 debug window wholesale (as that
  milestone's own notes said to) with the real shell: `MenuBar` (File: New/Open/Recent;
  View: Color Theme, Slots visibility), `Dashboard`, `SlotManager` with all four slots,
  window resize handling, mouse-wheel sheet zoom/scroll/seek-nudge, Ctrl+O, Space,
  Escape. Kept only Milestone 2's settings/audio-setup/engine-construction bootstrapping,
  per that milestone's own "Notes for the next session."
- `tests/test_channel_remap.py`, `tests/test_load.py`, `tests/test_text_input.py`,
  `tests/test_slot_manager.py` (all new) — pure-function/pure-logic unit tests per the
  Plan's Verification section ("introduce targeted unit tests as each new pure module
  lands"), covering: channel collision/drum-pinning assignment; tick-domain note-event
  construction including sustain-pedal extension and FIFO same-pitch pairing;
  `TextInput`'s editing logic; and the two `SlotManager` bug fixes as explicit
  regressions (a test that fails against the old hardcoded-tuple/single-flex-slot
  behavior and passes against the fix).
- `tests/test_app.py` (extended) — `_StubEngine` gained `set_channel_muted`/`note_on`/
  `note_off`/`program_change`/`all_notes_off`/`cc` (no-ops recording calls) so it still
  satisfies `App`'s now-larger `AudioEngine` usage; new tests cover track mute
  (`toggle_track`/`set_all_tracks` calling `engine.set_channel_muted` correctly,
  including the "still muted if another enabled track shares the channel" case),
  keyboard passthrough, and `seek_preview()` vs `seek()` (preview never touches the
  engine; `seek()` commits it and clears the preview).
- `python -m unittest discover -s tests -v` — 58/58 passing for the milestone itself
  (25 carried forward + 33 new — see Test results below for the exact breakdown);
  61/61 after the post-milestone Shift-sustain bugfix's 3 additional tests
  (`tests/test_keyboard_slot.py`, see Post-Milestone-3 bugfixes above).
- Manually verified against real hardware (`python main.py` with the real FluidSynth
  install already configured on this machine) — see Test results below.

2 — Audio engine v1. Done a previous session:
- `midivis/audio/engine.py` — `AudioEngine` Protocol (`PlayerStatus` enum: READY/
  PLAYING/STOPPING/DONE) per Plan Part 3.1. One deliberate signature deviation from
  the plan's pseudocode: `load(midi_bytes, tempo_map)` takes a `TempoMap` as well as
  bytes (the sketch in the plan only shows `load(midi_bytes)`), and `seek(seconds)`
  takes seconds rather than ticks — see Deviations below for why. Added `stop()`
  (not in the plan's sketch) — see Deviations.
- `midivis/audio/fluidsynth_ffi.py` (new, not in the Part 3 tree — see Deviations) —
  the ctypes function-table binding extracted out of what was one big class in the
  old repo's `fluid_engine.py`, so the future `SequencerBackend` (Milestone 6) can
  reuse the same binding layer instead of re-declaring ctypes signatures. Holds:
  `FLUID_PLAYER_*` status constants, `MIDI_CALLBACK_TYPE`, `load(bin_dir)` (DLL load +
  function binding + FLUID_WARN suppression, ported verbatim from `FluidEngine.__init__`),
  and `create_audio_driver(ffi, settings, synth, drivers=(...))` — the new WASAPI-first
  fallback chain Plan Part 3.1 calls for (tries `wasapi`, `dsound`, `waveout` in order,
  returns the first that initializes + its name). The old repo hard-coded `dsound` only.
- `midivis/audio/fluid_player.py` — `FluidPlayerBackend`, implementing `AudioEngine` on
  top of `fluidsynth_ffi`. Ported from the old repo's `FluidEngine` class:
  - `silent_play_seek` (renamed `_silent_play_seek`, now called from `play()`
    internally rather than being a second public method the caller chooses to use)
    and the defensive callback-reregistration-after-nearly-every-player-call pattern
    are preserved verbatim — per Plan Part 3.1's explicit instruction these are
    hard-won FluidSynth behavior, not to be "cleaned up."
  - **Elapsed-time ownership moved from `App` into this backend** (`get_clock_seconds()`,
    still wall-clock/`time.perf_counter()`-based, per Plan Part 3.1: "this backend's
    clock is not audio-derived, and that should be a documented, visible property of
    choosing it, not a hidden gotcha"). The old repo's `App._t0_ticks` /
    `pygame.time.get_ticks()` and `App._seconds_to_ticks` (an O(n) linear tempo-map
    rescan on every call, Plan Part 2's documented pitfall) are both gone — replaced
    by `self._t0`/`self._elapsed` here plus calls into the shared `TempoMap`
    (Milestone 1's `midi/model.py`), which is O(log n) via bisect.
  - `stop()` is new (not in the old `FluidEngine`): resets Python-side elapsed/playing
    state to 0/stopped *without* touching the physical `fluid_player` — see Deviations
    for why this had to be a distinct method from `pause()`.
- `midivis/app.py` — `App`, rewritten from scratch per Plan Part 3's "slimmed: delegates
  to audio/midi/notation, not a god-object." Holds only `midi_path`/`title`/`tempo_map`/
  `total_dur`; `play()`/`pause()`/`seek()`/`elapsed`/`playing` all forward straight to
  the injected `AudioEngine`. No track list, no note events, no `Timeline` population
  (per Milestone 1's status note, confirmed still correct: `FluidPlayerBackend` plays
  raw file bytes directly, same as the old `engine.load_from_mem()` path, so nothing
  here needs populated note events yet — that's Milestone 3/4 territory once there's a
  track list UI and notation views to feed).
- `main.py` — replaced the Milestone-1 placeholder with the real Milestone-2 entry
  point: resolves audio settings (unchanged from Milestone 1), constructs
  `FluidPlayerBackend`, opens a **deliberately minimal, throwaway** pygame window
  (900×220) — title/filename, a click-to-seek timeline bar, elapsed/total time,
  play/pause status, and which audio driver initialized. Space = play/pause,
  Ctrl+O = open (tkinter file dialog, reused from `ui/dashboard.py`'s pattern),
  click on the bar = seek, Esc = quit. No `render/widgets`, no `SlotManager`, no
  bars/traditional/keyboard/properties views — those are Milestone 3's job
  ("render/widgets/, theme consolidation, SlotManager fixes, bars view, timeline,
  keyboard, properties"); this UI exists purely to prove the audio engine works
  end-to-end and gets thrown away wholesale next milestone, not grown incrementally.
- `tests/test_app.py` — 8 new unit tests for `App` using a hand-written stub
  `AudioEngine` (no FluidSynth/hardware dependency, so these run in any environment):
  loading without an engine (metadata still populates, elapsed stays 0, play/pause/seek
  are no-ops), and with a stub engine — load forwards bytes+tempo_map, play/pause
  delegate, seek clamps to `[0, total_dur]`, `update()` resets state on DONE, shutdown
  clears the engine reference. **This test suite caught a real bug before it shipped**
  (see Deviations/bugs-found-and-fixed below) — worth keeping this pattern for future
  milestones' non-pure-but-still-unit-testable state machines.
- Manually verified against real hardware — see Test results below.

1 — Scaffolding. Done previous session:
- Created the `midivis/` package layout from Plan Part 3 as directory scaffolding: `audio/`,
  `midi/`, `input/`, `notation/`, `render/` (+ `render/widgets/`, `render/slots/`), `practice/` —
  each with an empty `__init__.py`. Only the two modules this milestone actually scopes are
  implemented; the rest are empty packages waiting for their milestone (audio backends in
  Milestone 2, widgets/slots in Milestone 3, notation/practice later, etc.). No `app.py` yet —
  that lands in Milestone 2 alongside the minimal shell UI.
- `midivis/midi/model.py` — `TempoMap`, `TempoChange`, `NoteEvent`, `Timeline`. `TempoMap` is the
  single shared tempo-conversion utility the plan calls for, replacing the three duplicated
  implementations in the old repo (`App._seconds_to_ticks`, `midi_processing.build_timeline`'s
  closure, `MidiRecorder`'s frozen-tempo math). `seconds_to_ticks`/`ticks_to_seconds`/
  `tempo_at_tick` are O(log n) via `bisect` over precomputed cumulative-seconds-at-each-tempo-
  change, not the old O(n) linear rescan (Plan Part 2 pitfall) — same formula, just indexed.
  `TempoMap.from_midi()` builds one from a `mido.MidiFile` (handles both type-0 merged-track and
  type-1 per-track tempo events, matching `midi_processing.build_timeline`'s existing type
  handling). `NoteEvent`/`Timeline` are the plain data containers Plan Part 3 names alongside
  `TempoMap`; `Timeline` isn't populated by real files yet since `midi/load.py`
  (SMF → Timeline) is out of scope this milestone — it's ready for whichever later milestone
  needs note events (UI/notation).
- `midivis/settings.py` — ported the old repo's atomic-write load/save pattern verbatim (temp
  file + `os.replace()`), extended `_DEFAULTS` with an `'audio'` sub-dict
  (`fluidsynth_bin`/`soundfont`, both `''`) for the new settings-driven paths. `load()`'s
  defaults-merge now recurses one level into dict-valued defaults so `'audio'` gets filled in
  for settings files written before this key existed, without clobbering a partially-set dict.
- `midivis/audio/setup.py` (new, not in the Part 3 tree — see Deviations) — replaces the old
  hard-coded `FLUIDSYNTH_BIN`/`SOUNDFONT` constants
  ([midi_visualizer.py:43-44](../../../MidiVis/midi_visualizer.py#L43-L44) in the old repo) with
  `find_fluidsynth_bin()`/`find_soundfont()` (glob over common install locations) and
  `prompt_for_fluidsynth_bin()`/`prompt_for_soundfont()` (tkinter folder/file pickers, same
  approach `ui/dashboard.py` already uses successfully in the old repo). `ensure_audio_paths()`
  ties it together: validate what's in settings → auto-detect → prompt, in that order, only
  writing back to settings on success.
- `main.py` — minimal entry point for this milestone only: loads settings, calls
  `ensure_audio_paths()`, saves, prints the resolved paths. This is *not* the app shell (no
  pygame window, no playback) — that's Milestone 2's "basic playback wired to a minimal shell
  UI." It exists so this milestone's deliverable (settings-driven audio path resolution) is
  actually runnable and testable on its own.
- `requirements.txt` — `pygame`, `mido`, `python-rtmidi` (the three packages the old repo's
  CLAUDE.md already documented as manual-install dependencies). Nothing added for
  not-yet-built features (e.g. `sounddevice` isn't needed until the Milestone 6 sequencer
  backend).
- `.gitignore` — `__pycache__/`, `*.pyc`, `.venv/`/`venv/`, `*.egg-info/`, `.pytest_cache/`,
  `build/`, `dist/`. Deferred from Milestone 0 per that session's Status note.
- `tests/test_model.py` — unit tests for `TempoMap` (constant-tempo case checked directly
  against `mido.tick2second`/`second2tick`; multi-tempo-change case checked against a
  from-scratch reference implementation of the old linear-scan algorithm to confirm the new
  `bisect`-based version is numerically identical, not just plausible; `from_midi()` for both
  SMF type 0 and type 1). Per Plan's Verification section calling out tempo-map conversions
  specifically as something to unit test now that the pure module exists. 9 tests, all passing
  (`python -m unittest discover -s tests`).

0 — Bootstrap. Done previous session:
- `git init`'d `C:\Users\crste\git\MidiVis2` (was previously just a bare folder containing
  `documentation/architecture/` with the three tracking files already in place — no repo yet).
- Copied `CLAUDE.md` from the old `MidiVis` repo into `MidiVis2/CLAUDE.md` verbatim, as the plan's
  "starting point, to be rewritten as the new architecture solidifies" — it still describes the *old*
  flat-file architecture (`midi_visualizer.py`, `fluid_engine.py`, etc.), not the target `midivis/`
  package layout in Plan Part 3. Do not treat it as authoritative for the new structure; it gets rewritten
  in Milestone 8 (Polish & docs).
- Copied the sample `.mid` files from the old repo's `midiTracks/` into `MidiVis2/midiTracks/` (11 files:
  Beethoven, Christmas Carols, Hakuna Matata, MIDI C Major, Undertale Megalovania, Vampire Killer,
  test/testRec1-4, twinkle). Deliberately did **not** copy `VampireKillerCV1.txt` (640KB, not a MIDI
  file — looked like ancillary lyrics/notes, not "sample MIDI files" per the plan's wording).
- Did not copy any old source modules (`midi_visualizer.py`, `fluid_engine.py`, `ui/`, etc.) — per plan,
  the new layout is written fresh each milestone, consulting old `MidiVis` (untouched on disk) as
  reference only.
- `FullRewritePlan.md`, `FullRewriteStatus.md` (this file), `FullRewritePrompt.md` were already present
  in `MidiVis2/documentation/architecture/` before this session started (someone had pre-seeded them) —
  verified their content matches this document's own Part 0/Appendix A/Appendix B verbatim, so left
  them as-is rather than re-copying.

## In progress / partially done this session
(none — Milestone 4 fully complete: quantize.py, spelling.py, the glyph atlas pipeline
(font asset + build tool + generated atlas + runtime loader), the engraver, the
traditional grand-staff view, the view-toggle dashboard buttons, and the sheet_slot.py
dispatcher are all done, unit-tested where the logic is pure, and manually verified via
headless rendering against several real sample files plus one real-hardware
`python main.py` launch. Recording, MIDI input/hardware, per-device input routing, and
the sequencer backend are deliberately untouched — Milestones 5 onward. One open item
carried forward, not a partial-completion: the Plan Part 3.3 open question about
hand-drawn/commissioned art vs. restyling a SMuFL font was resolved by adopting stock
Bravura unrestyled — see Deviations for why restyling itself (toward the rounder/
weightier look) is out of scope for this session specifically, not abandoned.)

## Decisions made or deviations from the plan
- **`AudioEngine.load()` takes `(midi_bytes, tempo_map)`, not just `midi_bytes`** as
  Part 3.1's pseudocode sketch shows. The backend needs a `TempoMap` for two things
  the plan itself assigns to this backend: converting `seek()`'s target position to
  MIDI ticks for `fluid_player_seek`, and (new this milestone) owning
  `get_clock_seconds()`'s wall-clock reference, which requires knowing what "seconds"
  a seek target corresponds to. Rather than have the backend build its own `TempoMap`
  from raw bytes (duplicating `TempoMap.from_midi`, reintroducing the "three
  implementations" problem Milestone 1 just fixed) or have callers pass raw ticks
  everywhere (pushing `TempoMap` usage back out to `App`, undoing the point of
  centralizing it in the engine), the caller (`App.load()`) builds the `TempoMap`
  once and hands it to the engine alongside the bytes. `seek()` also takes seconds,
  not ticks, for the same reason — ticks are an internal detail of how the backend
  talks to `fluid_player`, not something `App`/UI code should need to compute.
- **`AudioEngine.stop()` is new** (not in the plan's interface sketch, not in the old
  `FluidEngine`). Needed because moving elapsed-time ownership into the backend (per
  Part 3.1) created a case the old code didn't have to handle explicitly: on song-end
  (`PlayerStatus.DONE`), the *Python-side* elapsed/playing state needs resetting to
  0/stopped, but the *physical* `fluid_player` must NOT be touched directly — calling
  `fluid_player_seek` on a DONE player reopens exactly the race `silent_play_seek`
  exists to close. The old app's equivalent code path (`App.update()`'s
  `FLUID_PLAYER_DONE` branch) only ever called `App._reset_playback()`, a pure-Python
  reset, and left the physical reset to whatever the next `play()` call's
  `silent_play_seek` would do anyway — same idea, just needed its own named method
  now that this logic lives inside the engine instead of at the `App` level.
  **This exact distinction is what `tests/test_app.py` caught**: `App.update()`'s
  first draft gated the DONE-check on `self.playing`, but `playing` is defined as
  `status == PLAYING`, which is already `False` the instant status flips to `DONE` —
  so the reset never fired. Fixed by checking `get_status() == DONE` directly instead
  of gating on `playing`. Verified both by the unit test and by the real-hardware
  smoke test (play to end of file, confirm `elapsed` resets to 0 and a subsequent
  `play()` restarts cleanly from 0).
- **New file not in the Part 3 tree**: `midivis/audio/fluidsynth_ffi.py`. Part 3's
  tree names it explicitly ("shared ctypes bindings to libfluidsynth (both backends
  sit on this)") but doesn't spell out that `setup.py` (Milestone 1) is a *different*
  file with a different job (path discovery, not ctypes bindings) — noting this only
  because a future session skimming the tree might conflate the two; no actual
  conflict occurred.
- **New file not in the Part 3 tree**: `midivis/audio/setup.py` (FluidSynth-bin/SoundFont
  auto-detection + tkinter prompt, `ensure_audio_paths()`). Part 3.8 describes this behavior
  ("settings-driven config + a first-run setup flow") but the Part 3 tree doesn't name a file
  for it — `fluidsynth_ffi.py`/`fluid_player.py`/`engine.py` are all Milestone 2 concerns (the
  actual backend implementations), not path resolution. Placed it in `audio/` since it's
  audio-configuration logic and Milestone 2's `FluidPlayerBackend` will need to consume its
  output (`settings['audio']['fluidsynth_bin']`/`['soundfont']`) when constructing the FFI layer.
- **Settings directory renamed** `%APPDATA%\MidiVis` → `%APPDATA%\MidiVis2` (see
  `midivis/settings.py`'s `SETTINGS_DIR`). Not specified either way in the plan. Chose a
  separate store rather than sharing the old app's `settings.json` so `MidiVis2` can't
  corrupt/overwrite live settings for the still-installed old `MidiVis` app while both exist on
  disk during the rewrite, and so schema changes here (the new `audio` key, future
  `audio.backend`/`audio.driver` etc.) don't need to stay backward-compatible with the old
  app's reader. Easy to rename back in Milestone 8 (Polish) if a clean migration is wanted
  instead.
- **`main.py` was a placeholder as of Milestone 1** (see below) — resolved this session:
  Milestone 2 replaced it with the real "basic playback wired to a minimal shell UI" entry
  point per Plan Part 4. That shell UI is itself still deliberately minimal/throwaway
  (inline pygame drawing, no `render/widgets`/`SlotManager`) — Milestone 3 replaces it
  wholesale, not incrementally. Original Milestone-1 note, kept for history: "`main.py`
  this milestone is a placeholder, not the real entry point... It only exercises settings +
  first-run audio-path resolution — no pygame window, no `App`/`app.py`."
- **No channel remap, no `Timeline` population this milestone either** (confirms Milestone 1's
  prediction). `App.load()` reads the file's raw bytes and hands them to
  `FluidPlayerBackend.load()` unchanged — same as the old `engine.load_from_mem()` path.
  Per-track mute needs channel remap (`midi/channel_remap.py`, Milestone 5) and a track list
  UI (Milestone 3) to be meaningful, so it stays out of scope until then; nothing plays
  incorrectly without it since there's no mute control yet to be inconsistent with.
- **`App.total_dur` comes from `mido.MidiFile.length`**, with no safety buffer (the old app
  added "+5" seconds on top of its own timeline-derived duration). Observed on real hardware
  (see Test results): FluidSynth's audio tail can run a few seconds past the file's nominal
  last-event tick before `fluid_player` actually reports `FLUID_PLAYER_DONE` — a real,
  pre-existing FluidSynth/old-app characteristic (the old app's timeline `+5` buffer existed
  for exactly this reason), not something this rewrite introduced. Impact today is purely
  cosmetic: the minimal shell's progress bar clamps visually at 100% and the elapsed/total
  text can show elapsed slightly past total for a few seconds right at the end of a file,
  before `App.update()` detects `DONE` and resets to 0. Not fixed this milestone since it's
  cosmetic and `total_dur` computation is likely to move onto `Timeline` (once populated)
  anyway; worth a small buffer or basing `total_dur` on `fluid_player_get_total_ticks()` if it
  becomes visually annoying once Milestone 3 adds a real timeline widget.
- **`requirements.txt` chosen over `pyproject.toml`** — the plan allows either. Went with the
  simpler option since packaging (setup.py/build backend/entry points) isn't in scope until
  Milestone 8, and `requirements.txt` matches the old repo's existing (manual-install) pattern
  documented in `CLAUDE.md`.
- **Empty packages left as empty `__init__.py` only** (`input/`, `notation/`, `render/` +
  `widgets/`/`slots/`, `practice/`) — no placeholder/stub classes for `AudioEngine`,
  `GlyphAtlas`, etc. Milestone 1's scope per Plan Part 4 is specifically "new package layout...
  `midi/model.py` + shared tempo-map utility," not speculative interfaces for later milestones.
- `Timeline` (in `midi/model.py`) is defined but not populated by any loader yet — `midi/load.py`
  (SMF → Timeline, replacing `midi_processing.build_timeline`/`build_note_events`) is listed in
  Part 3 but not called out as in-scope for Milestone 1 specifically ("`midi/model.py` + shared
  tempo-map utility" only); left for whichever milestone first needs real note-event data
  (Milestone 2 loads bytes directly into the FluidSynth player, same as the old
  `engine.load_from_mem()` path, so it doesn't need `Timeline` populated either).

### Milestone 4 deviations

- **Glyph source is a bundled real SMuFL font (Bravura.otf), not hand-authored SVG.**
  Plan Part 3.3 names `assets/glyphs/` SVG source rasterized by
  `tools/build_atlas.py`, with an explicit "not blocking" open question: hand-draw/
  commission original art, or start from an open-license SMuFL font (Bravura is named
  directly) and restyle it. Discovered mid-session that `pygame.font.Font(path, size)`
  loads a font *file* directly — no OS font-name lookup at all — so downloading
  Bravura.otf (SIL OFL 1.1, confirmed via `steinbergmedia/bravura`'s own `redist/OFL.txt`,
  copied alongside it) and rasterizing specific codepoints via pygame at build time gets
  every architectural goal Part 3.3 wants (offline pipeline, no runtime OS-font
  dependency, no silent-omission failure mode) without writing a single Bezier curve by
  hand. The *restyling* half of the open question (toward the rounder/weightier
  SimplyPiano/Flowkey look) is genuinely not done — this session shipped stock Bravura,
  which looks like conventional engraved notation, not the reference screenshots' softer
  style. Restyling a font requires font-editing tooling (e.g. FontForge scripting) beyond
  what a build-time rasterizer can do; worth a dedicated look in Polish (Milestone 8) or
  whenever the visual style is being revisited, not blocking anything downstream since
  `notation/glyphs.py`'s interface (name+tier -> bitmap+anchor) doesn't care what font
  backs it.
- **`assets/glyphs/` (SVG source) and the SVG-rasterization step in Part 3.3's tree don't
  exist** — direct consequence of the above. `assets/fonts/Bravura.otf` (+ `OFL.txt`) is
  the source now; `assets/atlas/` (generated PNG + JSON manifest) is unchanged from the
  plan's own naming.
- **Only one glyph size tier is actually used at runtime** (`'md'`, 24px staff-space),
  though `build_atlas.py` generates three (`sm`=14, `md`=24, `lg`=44). Confirmed by
  re-reading the old `traditional_sheet.py` that staff size there was a fixed constant
  (`LS = 20`) never tied to `app.sheet_zoom` (zoom only ever affected horizontal note
  spacing/time scale, both there and in `bars.py` — resizing/zooming the panel changes
  how much *time* is visible or how much vertical *range* you can scroll to, not the
  staff's own size), so there's currently no zoom axis in this app that a mid-frame
  tier-switch would even respond to. Picked `'md'` specifically so it needs zero runtime
  rescaling (`LS = 24` in `traditional.py` matches the tier's staff-space size exactly).
  The other two tiers exist for a plausible future per-DPI or staff-zoom setting to pick
  from without rebuilding the atlas — not dead code, just not wired to anything yet.
- **`midi/quantize.py`'s "grid + strength" recording-quantization function (Plan Part
  3.2's sidebar) is NOT built this milestone** — confirmed correct scope reading Plan
  Part 4's milestone list: that's explicitly named under Milestone 5 ("recording
  quantization... fixes unaligned bars from live-played timing"), and there's no
  `recorder.py`/live-recording workflow yet for it to plug into or be tested against.
  What *is* built this milestone (`classify_duration`/`measure_ticks`/
  `split_across_barlines`) is the other half Plan Part 3.2 names in the same breath:
  "rhythm quantization... duration -> (type, dots, tuplet)... tie-generation across
  barlines" — the notation-display half, which the engraver needs regardless of whether
  recording exists yet.
- **`quantize_duration_ticks()` (new, not explicitly named in the plan) was added
  mid-session** after rendering real sample files (`midiTracks/MIDI C Major.mid`,
  `twinkle.mid`) showed *why* it's needed: real (non-machine-quantized) MIDI files
  routinely encode note durations a handful of ticks short of the "intended" value (a
  note released slightly early, or arpeggiator/DAW-exported timing) — feeding that raw
  duration straight into `classify_duration` snapped to the nearest *exact* ratio and
  regularly misclassified plain eighth notes as double-dotted sixteenths or triplets,
  purely from a handful of ticks of real-world imprecision. Snapping to a sixteenth-note
  grid *before* classifying (this function) eliminates that jitter for realistic files
  while leaving `classify_duration` itself exact and independently testable. This is
  display-only — it never touches `note_events`/playback timing, only which glyph gets
  drawn — so it's a different thing from Milestone 5's recording-quantization (which
  writes quantized ticks back into saved note data with an adjustable strength dial).
  Files with genuinely loose/expressive timing (confirmed on `MIDI C Major.mid`, which
  is not machine-quantized) will still show occasional odd dotted-note classifications
  even after this fix — a real, inherent limit of classifying arbitrary real-world
  durations against a fixed candidate table, not something achievable to fully solve
  with a single default grid choice. Not chased further this session; visually confirmed
  acceptable on every sample file tried.
- **`midi/spelling.py`'s scope is single sharp/flat only, no double-accidentals** — a
  key is classified as sharp- or flat-flavored (via a direct port of mido's own
  key-signature name→accidental-count table, not re-derived from pitch class — see the
  module's docstring for why re-deriving it is actually wrong, not just redundant: C#
  major (7 sharps) and Db major (5 flats) share a pitch class but are different, both-
  valid key names that a naive "fewest accidentals" fold would silently conflate) and
  *all twelve* pitch classes in that key use the corresponding sharp or flat table. This
  is exact for every key's own diatonic scale tones (by construction) and a reasonable,
  consistent default for chromatic passing tones — not full harmonic-function spelling.
  Verified this is a real fix, not just cosmetic, via
  `test_staff_position_differs_for_enharmonic_spellings`: C#4 and Db4 (same MIDI note)
  now land on genuinely different staff positions, which is the actual bug (the old
  renderer's `_DIAT` table always used C's position regardless of key).
- **Voice/staff assignment is still the old pitch >= 60 threshold** — Plan Part 3.2 says
  this "becomes a per-track/channel property (with pitch-based default)"; only the
  default half is built (`engraver.default_staff_of`, a named, swappable function rather
  than an inline literal scattered through the renderer, per the same section's framing).
  Per-track/channel staff configuration needs UI/settings scope not otherwise in this
  milestone's list; `engrave()`'s `staff_of` parameter exists specifically so a future
  settings-driven version is a one-line change at the call site in `app.py`, not a
  rewrite of the engraver.
- **Real sample files surfaced a genuine engraver bug during manual verification, fixed
  same session**: `traditional.py`'s stem-direction helper (`_group_stem_up`) compared
  each note's *absolute* diatonic step against a bare constant (`<= 4`, ported from the
  old `traditional_sheet.py`'s equivalent check without noticing the old code compared a
  step already made *relative to the staff's bottom line*, not an absolute one) — since
  every real treble note's absolute step is in the high-20s/30s, this made literally
  every stem in the app point the same direction regardless of pitch. Caught by
  rendering `midiTracks/MIDI C Major.mid` (a rising scale) and noticing all stems still
  pointed down. Fixed by adding `_MIDDLE_STEP = {'treble': TREBLE_REF_STEP + 4, 'bass':
  BASS_REF_STEP + 4}` (absolute step of each staff's own middle line) and threading the
  correct one through every call site (`_draw_chord`, `_draw_beam_group`, the tie-arc
  direction check). No unit test added for this specifically — it's a rendering-only
  concern verified by the same headless-screenshot method as Milestone 3's icon/layout
  bugfixes (see Test results below); a numeric assertion here would just re-encode the
  same threshold arithmetic it's meant to verify.
- **Beam/tie/stem rendering was verified correct via isolated synthetic-note headless
  renders**, not just by eyeballing dense real files: real sample files at the app's
  default 8-measures-visible zoom produce enough note density (especially
  `UndertaleMegalovania.mid`'s ~230 BPM sixteenth runs and `twinkle.mid`'s 4-track
  doubled arrangement, both intentionally busy files) that overlapping noteheads/stems/
  ties made it genuinely hard to tell correct-but-crowded apart from actually broken by
  eye alone. Isolated two-note and four-note synthetic `NoteEvent` lists (throwaway
  scripts, not checked in) confirmed beams, secondary (16th-note) beams, and tie arcs
  are all geometrically correct once instead rendered without that crowding — the
  visual density in busy real files is real crowding at default zoom (the app's existing
  Ctrl+scroll zoom control addresses this already), not a rendering defect.

### Milestone 3 deviations

- **Resolved the previous session's channel-remap ambiguity**: `midi/channel_remap.py` is built
  *now* (basic remap: unique channel per track, drum tracks pinned to 9), not deferred to
  Milestone 5. Re-reading Plan Part 3.4/3.2/4 together, Milestone 5's scope is specifically
  "channel-remap **edge-case** fixes" (>15 melodic tracks, multiple simultaneous drum tracks) —
  wording that only makes sense if a non-edge-case remap already exists for it to extend. Without
  a basic remap, per-track mute (explicitly part of Milestone 3's "feature parity" bar per Part 1's
  Playback feature list) would be wrong on any file whose tracks share MIDI channels, which is
  common. `channel_remap.py`'s module docstring records this reasoning inline so a future session
  doesn't need to re-derive it.
- **`App.seek_preview()` needed a real design change, not just a port**, because Milestone 2 moved
  clock ownership into the `AudioEngine` (`get_clock_seconds()`), so there's no local `App.elapsed`
  field left to freely overwrite during a timeline drag the way the old App did. Added
  `App._preview_elapsed: float | None`; the `elapsed` property returns it when set, shadowing the
  engine's clock for display and active-note computation without any engine calls during drag
  motion. Only `seek()` (drag release / click-to-seek) actually calls `engine.seek()` and clears
  `_preview_elapsed`. Consequence: `TimelineSlot`'s mouseup handler now calls `app.seek(app.elapsed)`
  unconditionally before optionally resuming playback — necessary because `FluidPlayerBackend`'s own
  `_elapsed` field (used internally by `play()`'s `silent_play_seek`) was never updated during the
  preview-only drag and would otherwise resume from the pre-drag position on the next `play()`.
  Verified in `tests/test_app.py`'s `AppSeekPreviewTest` and by direct event-simulation against both
  a stub engine and `engine=None` (this session's smoke-test transcripts, not checked in).
- **`render/dashboard.py` is much smaller than the old `ui/dashboard.py` (1145 lines) it replaces** —
  no record-arm panel (Milestone 5: recording), no Bars/Traditional view toggle (Milestone 4: only
  the bars view exists so far), no per-track delete (tied to the recording workflow in the old app,
  Milestone 5). Not a scope cut — Milestone 3 just isn't building UI for features that don't exist
  yet; both panels' worth of logic will land alongside the features that need them.
- **No `render/slots/sheet_slot.py` dispatcher this milestone.** The old repo's `SheetSlot` picked
  between `BarsSheetSlot`/`TraditionalSheetSlot` by `app.view`; with only the bars view built so
  far, `BarsSlot` is registered directly under the `'sheet'` slot id in `SlotManager`. Milestone 4
  adds the dispatcher (and an `app.view` field) when there's a second view to dispatch to —
  introducing it now would be a single-branch abstraction with nothing to abstract over yet.
- **`render/widgets/mini_keyboard.py` shares note-geometry (`is_black`/`white_index`), not a single
  `draw()`.** `KeyboardSlot` (horizontal, interactive, click/drag-to-play) and `BarsSlot`'s piano
  strip (vertical, display-only, sized to match the roll's note rows) render different enough things
  that forcing one shared `draw()` would be an awkward abstraction for no real reuse — what was
  actually duplicated in the old repo, and now isn't, is the black-key/white-key-index math, not the
  rendering.
- **`render/widgets/text_input.py` (`TextInput`) is built but not wired into anything.** Plan Part
  3.4 lists it as one of Milestone 3's five widgets; the record-arm panel it was extracted from
  (the old `ui/dashboard.py`'s hand-rolled cursor/editing code) is Milestone 5 (recording). Built now
  as its own tested unit (`tests/test_text_input.py`) so M5 can wire it in directly.
- **`midi/analyze.py` is a new file not named in Plan Part 3's tree** (the tree lists
  `channel_remap.py`/`quantize.py`/`spelling.py`/`recorder.py`/`load.py`/`model.py` under `midi/`
  but nothing for tempo/time-signature/key-signature extraction). Ported from the old repo's
  `midi_analyzer.py` (a separate file there too) rather than folding into `load.py`, keeping the same
  single-purpose split the old repo already had. `midi/instruments.py` similarly isn't named in
  Part 3's tree — ported from the old `midi_instruments.py` since the properties panel needs GM
  instrument/drum-kit names and there's no more natural home for them yet.
- **Properties panel drops the recording-state indicator and the MIDI-input-device column** that the
  old `ui/slots/properties.py` had — both read from `app.recorder`/`app.midi_input`, neither of
  which exist yet (Milestone 5). `expanded_height()`'s row-count math was simplified accordingly
  (no more "whichever of the left/right column is taller" — just the left column's fixed row count).

## Test results from this session
- `python -m unittest discover -s tests -v` — **99/99 passing**: 61 carried forward
  unchanged (Milestones 1-3 + post-M3 bugfixes) + 38 new (`test_spelling.py`: 10,
  `test_quantize.py`: 16, `test_engraver.py`: 12).
- **Atlas build verified visually**: ran `python tools/build_atlas.py`, composited the
  generated `glyphs.png` onto an opaque background and inspected it — all 29 glyphs
  present and legible across all 3 tiers (clefs, noteheads, accidentals, rests, flags,
  digits), no missing/blank cells.
- **`GlyphAtlas` smoke-tested headless** (`SDL_VIDEODRIVER=dummy`): loads the generated
  atlas, `nearest_tier()`/`get()`/`blit()` (including the `color=` tint path) all work
  without error.
- **Traditional view rendered headless against multiple real sample files** (throwaway
  scripts, not checked in — construct a real `App`, load an actual file, call
  `TraditionalSlot.draw()` onto a real `pygame.Surface`, save as PNG, view it):
  - `midiTracks/twinkle.mid` (4 tracks, doubled Harp+Piano arrangement) — confirmed
    clefs/staff/measure numbers render; flagged as *very* dense at default zoom, which
    led to isolating single tracks for clearer verification (see below), not a rendering
    defect (see Deviations).
  - `midiTracks/MIDI C Major.mid` (single track, simple rising scale) — this is where
    the stem-direction bug (see Deviations) was actually caught: every stem pointed the
    same direction regardless of pitch, obviously wrong for a rising scale. Re-rendered
    after the fix — stems now correctly flip direction around the staff's middle line.
    Also where `quantize_duration_ticks()` was added, after noticing spurious dotted-note
    classifications on this file's slightly-imprecise real durations.
  - `midiTracks/UndertaleMegalovania.mid` (3 tracks, D minor/1 flat, ~230 BPM) — confirmed
    flat-key accidentals render correctly (the piece's Bb key signature), and confirmed
    past/active/future note coloring (gray/red/blue) matches the bars view's scheme.
  - Both dark and light themes checked for each file — `trad_*` palette re-themes fully,
    no un-themed literals left over.
  - Isolated synthetic-note renders (two eighth notes, four sixteenth notes, a note tied
    across a barline) confirmed beams, secondary beams, and tie arcs are geometrically
    correct in a low-density scene, isolating that from real files' visual crowding.
- **Full app shell smoke test** (headless, real `App`/`Dashboard`/`SlotManager`/
  `SheetSlot` objects, `twinkle.mid` loaded): rendered the Bars view, simulated a click
  on the dashboard's Traditional button (confirmed `app.view` flips and the traditional
  view renders with no exception), clicked back to Bars, then ran a few `app.update()` +
  render frames in Traditional view with a seeked-forward position — no exceptions
  across the whole sequence. Saved a full-window screenshot: dashboard chrome (all
  buttons/separators), timeline, traditional notation, and the on-screen keyboard's
  active-note highlighting all agreed with each other (same notes highlighted red in
  both the score and the keyboard).
- **`python main.py` against real FluidSynth hardware**: launched cleanly, same benign
  `wasapi: requested mode cannot be fully satisfied` console line as every prior
  milestone, no traceback, `timeout 6 python main.py` exit code 124 (killed by timeout
  after a healthy run, not a crash). No audio-path code touched this milestone, so this
  is a regression check, not new-behavior verification.
- `git status` — exactly the files listed under "Files touched" above (Completed
  milestones, Milestone 4 entry) are new/modified; nothing stray, no leaked
  `__pycache__`.

### Manual test steps for you to run
1. `python -m unittest discover -s tests -v` — should show 99/99 passing.
2. `python main.py`, then **File > Open...** a file from `midiTracks/` (e.g.
   `UndertaleMegalovania.mid` or `MIDI C Major.mid` for something visually simpler).
3. Click the dashboard's **Traditional** button (next to **Bars**, below Play/Reset) —
   the sheet view switches from the piano-roll to a grand staff with a treble and bass
   clef, staff lines, and notation. Click **Bars** to switch back — confirm both views
   keep working after switching back and forth a few times.
4. **Play** (or Space) while in Traditional view — notes should scroll past the
   playhead, ties should show as small curved arcs connecting notes that cross a
   barline, and the currently-sounding note(s) should highlight in the same color as the
   bars view's active-note color, matching what lights up on the on-screen keyboard
   below.
5. **Uncheck a track** in the Tracks dropdown while in Traditional view — that track's
   notes/rests disappear from the staff (same per-track mute the bars view already has).
6. Try a file with a non-C-major key signature (e.g. `UndertaleMegalovania.mid`, D
   minor/1 flat) — accidentals should show as flats (♭), not sharps; try one with sharps
   too if you have one — confirm the accidental symbol and *which line/space the note
   sits on* both look right (this is the specific bug Milestone 4 fixes — the old app
   always drew '#' and always used the sharp-key staff position regardless of the file's
   actual key).
7. **Ctrl+scroll and plain-scroll over the traditional view** — same zoom/vertical-scroll
   behavior as the bars view (they share the same event/zoom plumbing via `SheetSlot`).
8. **View > Color Theme > Light** while in Traditional view — staff, clefs, notes,
   playhead, measure numbers should all re-theme (no leftover dark-only literals).
9. Load a file with fast/dense passages (e.g. `UndertaleMegalovania.mid`) and zoom in
   (Ctrl+scroll) on a busy section — individual noteheads/stems/beams should become
   legible as you zoom in, confirming the crowding at default zoom is a zoom/density
   issue, not broken geometry (see Deviations for the manual verification already done
   on this point).
10. Quit via Esc — clean exit, no traceback.

## Pre-Milestone-5 cleanup: sheet wheel handling moved out of main.py

**Not a milestone** — Plan scope is unchanged; this corrects a present inconsistency
before Milestone 5 (input routing) would otherwise have added a second ad hoc input
block on top of it.

**Problem**: `main.py`'s event loop had a 20-line `MOUSEWHEEL` special case
(ctrl+wheel zoom, plain-wheel scroll, horizontal-wheel seek) that bypassed the
`SlotBase.handle_event`/`SlotManager.handle_event` dispatch every other slot-owned
interaction already goes through — it did its own hit-testing against
`slot_manager.rects(content)` and wrote directly into `app.sheet_zoom`/
`app.bars_scroll`. This had already caused a real bug: the scroll branch always wrote
`bars_scroll`, so wheel-scroll silently did nothing in the traditional view (which
reads `trad_scroll`).

**Fix**: moved the logic into `SheetSlot.handle_event` (`render/slots/sheet_slot.py`),
which already knows which view (`bars`/`traditional`) is active, so it now writes the
*correct* scroll attribute — fixing the bug as a side effect. Horizontal-wheel seek has
no natural per-slot owner (it drives playback), so `handle_event` returns a
`('seek', delta)` signal; `SlotManager` accumulates it in a new `take_seek_delta()`
(mirroring the existing `'properties_toggle'` special-case pattern) and `main.py` reads
it once per frame instead of accumulating a local variable itself. The dashboard's
track-dropdown wheel-exclusion (dropdown can visually overlap the sheet rect) moved
into `_TrackDropdown.handle_event` alongside its other owned events, rather than staying
as a `main.py`-level guard.

Files touched: `render/slots/sheet_slot.py`, `render/slots/slot_manager.py`,
`render/dashboard.py`, `main.py`. New test file `tests/test_sheet_wheel.py` (9 tests:
zoom clamping both directions, per-view scroll incl. the traditional-view regression
case, scroll clamping, seek signal shape, position-outside-rect gating, not-loaded
gating). No slot's `handle_event` contract changed shape (still `event, rect, app ->
bool | str`, now also `| tuple[str, float]` for the sheet slot specifically) — deferred
extending it to `KEYDOWN`/`KEYUP` since no slot needs that yet; Milestone 5's
computer-keyboard piano input should be the first thing to route through this same
mechanism rather than adding a third ad hoc block to `main.py`.

## Notes for the next session
Start Milestone 5 (Recording + MIDI input) per `FullRewritePlan.md` Part 4 and Part
3.2/3.6/3.7: tempo-map-aware `midi/recorder.py` (replacing the old single-tempo-frozen-
at-arm() `MidiRecorder`), recording quantization (grid + strength — the *other* half of
Plan Part 3.2's quantization sidebar that this session deliberately deferred; see this
session's Deviations for exactly why it wasn't built yet and what it needs:
`midi/quantize.py`'s existing `classify_duration`/`split_across_barlines` are already
there for it to reuse, it just needs a new grid-snap-with-strength function operating on
recorded ticks directly, plus the actual recorder to call it from), persistent-process
MIDI device enumeration (replacing the fresh-subprocess-per-poll model — packaging
landmine called out in Plan Part 2), hardware sustain-pedal (CC64) live passthrough
parity with the computer-keyboard path, channel-remap edge-case fixes (>15 melodic
tracks, multiple simultaneous drum tracks — `midi/channel_remap.py`'s module docstring
already flags these as the deliberately-deferred gaps from Milestone 3), per-device-
per-channel input routing (`input/manager.py`, replacing the half-built `ChannelAction`
model), and drum pad input + a new `render/slots/drum_pad.py` view.

Reference material in the old `MidiVis` repo for Milestone 5: `midi_recorder.py` (the
whole `MidiRecorder` class — arm/record/save state machine, the `.work`-file safety
copy pattern) and `midi_input.py` (subprocess-isolated USB enumeration, the
`ChannelAction` model, sustain-pedal handling for the computer-keyboard path to mirror
for hardware input). `midi_instruments.GM_DRUM_NOTE_NAMES` (already ported to
`midivis/midi/instruments.py` in Milestone 3) is the source for the default GM drum-pad
mapping Plan Part 3.6 calls for.

`render/widgets/text_input.py`'s `TextInput` (built in Milestone 3, unused since then)
is specifically for this milestone's record-arm panel — use it directly rather than
re-rolling cursor/editing logic.

Nothing from Milestone 4 is left in a partial state — no cleanup needed before
starting. `app.engraving` (built once in `App.load()`) and `midi/quantize.py`/
`spelling.py` should be kept and built on, not rebuilt — the recorder's quantization
needs the same tick-domain math `quantize.py` already has, and any future notation
polish should extend `notation/engraver.py` rather than duplicate its chord/rest/beam
grouping elsewhere.

---

## Test results from Milestone 3 (previous session)
- `python -m unittest discover -s tests -v` — **58/58 passing**: 25 carried forward
  unchanged (Milestones 1-2 + the two post-M2 bugfixes) + 6 new in `test_app.py`
  (track mute, keyboard passthrough, seek-preview) + 27 across four new files
  (`test_channel_remap.py`: 5, `test_load.py`: 9, `test_slot_manager.py`: 5,
  `test_text_input.py`: 8).
- **`python main.py` against real FluidSynth hardware** (the install already configured
  on this machine from Milestone 1/2): launched with the last real `recent_files` entry
  (`HakunaMatata.mid` from the old repo's `midiTracks/`) auto-loading. Console showed
  only the expected `[FluidPlayerBackend] audio driver: wasapi` + the known-benign
  `wasapi: requested mode cannot be fully satisfied` line — no traceback, no
  import/attribute errors, across a `timeout 6 python main.py` run (exit code 124 =
  killed by the timeout after 6s of a healthy event loop, not a crash).
- **Headless event-simulation smoke tests** (throwaway scripts against `SDL_VIDEODRIVER=
  dummy`, not checked in — construct real `pygame.event.Event`s and dispatch them
  through the actual `SlotManager`/`Dashboard`/`MenuBar` objects, no manual clicking
  needed to verify wiring): loaded `twinkle.mid` via `App(engine=None)` and separately
  via a stub engine shaped like `_StubEngine`, then exercised — Tracks button opens the
  dropdown; clicking a track row toggles `enabled_tracks` and correctly shrinks
  `note_events`; clicking outside the dropdown closes it; a full
  mousedown/motion/mouseup timeline drag sequence (confirmed `elapsed` tracks the drag
  preview live, then confirmed the stub engine's `seek()` was actually called with the
  final dragged-to position on mouseup — this is the exact case the `seek_preview()`
  redesign in Deviations exists to get right); clicking a piano key adds/removes from
  `kb_notes`; clicking the properties `+/-` button expands the panel and grows its slot
  height; dragging the bars view's scrollbar thumb (in an artificially short content
  rect, to force `has_scroll=True`) updates `bars_scroll`; opening the View menu and
  hovering "Color Theme" opens its submenu with the expected `theme:dark`/`theme:light`
  items. All behaved as expected on first correct run (one early test bug on my end —
  a click position inside the drag-handle strip triggered `SlotManager`'s
  drag-to-reorder instead of reaching the slot, not a product bug — fixed by moving the
  test's click x-coordinate past `HANDLE_W`).
- `git status` — exactly the files listed under "Files touched" above are new/modified;
  nothing stray, no leaked `__pycache__`.

Nothing from Milestone 3 was left in a partial state at the start of Milestone 4.

---

## Test results from Milestone 2 (previous session)
- `python -m unittest discover -s tests -v` — 17/17 passing (9 from Milestone 1's
  `test_model.py`, unchanged; 8 new in `test_app.py`). `test_app.py` caught a real bug
  before it shipped (`App.update()`'s DONE-detection gating on `self.playing`, which is
  already `False` by the time status is `DONE`).
- **Real-hardware engine smoke test** (throwaway script, not checked in — exercised
  `FluidPlayerBackend` directly against the actual FluidSynth install/SoundFont, no
  pygame loop, to isolate engine mechanics from UI): loaded `midiTracks/twinkle.mid`,
  then in sequence — play (elapsed advances correctly against wall-clock), pause
  (elapsed freezes, matches paused-instant value), seek-while-paused (jumps exactly,
  no drift), resume-play-from-seek (continues from the seeked position, not from 0 or
  from where it was before seeking), seek-while-playing (jumps and continues advancing
  from the new position), seek-near-end-and-wait-for-DONE (status transitions
  PLAYING → DONE, `elapsed` resets to 0, physical player stays reporting DONE — matches
  `stop()`'s documented Python-only-reset design), replay-after-DONE (restarts cleanly
  from 0, confirming the deferred-physical-reset-via-next-`play()`'s-`silent_play_seek`
  design works as intended). All assertions passed. Console output confirmed
  `[FluidPlayerBackend] audio driver: wasapi` — the fallback chain correctly selected
  WASAPI over dsound/waveout on this machine (one FluidSynth-internal stderr line,
  `wasapi: requested mode cannot be fully satisfied`, printed during driver init but
  driver still initialized and played audio correctly — non-fatal, not one of the
  messages `fluid_set_log_function`'s FLUID_WARN suppression targets, left as-is).
- **DONE-detection timing note** (see also the `total_dur`-no-buffer deviation above):
  a follow-up diagnostic script polling `fluid_player_get_current_tick()`/
  `get_total_ticks()` directly showed the current tick exceeding the file's total tick
  count by ~1300 ticks (~3.5 real seconds at this file's tempo) before
  `FLUID_PLAYER_DONE` actually fired — FluidSynth's own audio tail, not a bug in this
  session's code. First smoke-test draft had too short a wait window and produced a
  false failure (`playing` still `True` after 4s); widening the wait window to ~10s
  confirmed DONE is reached reliably, just later than the nominal file duration.
- `python main.py` — launched the real window (900×220), left it running ~8s with no
  file pre-loaded (no `recent_files` entry yet this session), no crash/exception,
  clean exit on window close.
- `git status` — everything still untracked as expected (nothing committed, per
  policy); no `__pycache__` leaked (`.gitignore` from Milestone 1 still doing its job).

Nothing from Milestone 2 was left in a partial state at the start of Milestone 3.

---

## Test results from Milestone 1 (previous session)
- `python -m unittest discover -s tests -v` — 9/9 passing. Covers: `TempoMap` constant-tempo
  case against `mido.tick2second`/`second2tick` directly; multi-tempo-change case against a
  from-scratch reference re-implementation of the old repo's linear tempo-walk algorithm
  (`App._seconds_to_ticks`/`midi_processing.build_timeline`'s closure), confirming the new
  `bisect`-based `TempoMap` produces numerically identical results, not just plausible ones;
  `TempoMap.from_midi()` for both SMF type 0 (merged track) and type 1 (per-track tempo
  events); `Timeline`/`NoteEvent` container wiring.
- `python main.py` on a machine with a real FluidSynth install (`C:\Users\crste\fluidsynth\...`)
  and SoundFont (`C:\Users\crste\Documents\GeneralUser_GS_v2.0.3...`) already present:
  auto-detection (`find_fluidsynth_bin()`/`find_soundfont()`) found both without any prompt,
  matching the old repo's hard-coded `FLUIDSYNTH_BIN`/`SOUNDFONT` constants exactly. Settings
  file written to `%APPDATA%\MidiVis2\settings.json`.
- Re-ran `python main.py` with the just-written settings present — confirms the happy path
  (valid cached paths, no re-detection needed) works and is idempotent.
- Manually corrupted `settings.json`'s `audio.fluidsynth_bin`/`audio.soundfont` to nonexistent
  paths, re-ran `python main.py` — confirms `ensure_audio_paths()` correctly detects the stale/
  invalid cached paths and re-resolves them via auto-detection rather than trusting a broken
  cached value.
- **Not exercised**: the interactive tkinter prompt path (`prompt_for_fluidsynth_bin()`/
  `prompt_for_soundfont()`) — auto-detection succeeded on this dev machine so the fallback
  branch never ran. Manual test step below covers this.
- `git status` shows everything from this session as untracked (nothing committed, per policy);
  `.gitignore` correctly excludes all `__pycache__/`/`*.pyc` generated by the test/main.py runs
  above (confirmed via `git status` showing no `__pycache__` entries).

### Manual test steps for you to run
1. `pip install -r requirements.txt` (pygame/mido/python-rtmidi — confirm these install cleanly
   in whatever environment/venv you intend to use; this session used the machine's existing
   global install where all three were already present, so a truly clean-install path hasn't
   been verified).
2. `python -m unittest discover -s tests -v` — should show 9/9 passing.
3. `python main.py` — should print the resolved FluidSynth bin + SoundFont paths (auto-detected
   from your existing install) and exit 0.
4. Run it again — should print the same paths, faster, with no re-detection (reads straight from
   `%APPDATA%\MidiVis2\settings.json`).
5. **Exercise the prompt fallback** (not covered above): open
   `%APPDATA%\MidiVis2\settings.json` and set `audio.fluidsynth_bin` and `audio.soundfont` to
   `""`, then temporarily rename your FluidSynth folder or SoundFont file so auto-detection
   can't find it either — `python main.py` should pop the tkinter "MidiVis needs FluidSynth..."
   dialog, then a folder picker, then a file picker; cancelling either should print the
   "setup incomplete" message and exit without writing bad paths to settings. Rename things
   back afterward.

### Notes recorded at the end of Milestone 1 (superseded — kept for history)
Start Milestone 2 (Audio engine v1) per `FullRewritePlan.md` Part 4 and Part 3.1:
`FluidPlayerBackend` behind the `AudioEngine` interface (WASAPI-first driver fallback chain —
try `wasapi`, then `dsound`, then `waveout`, logging which one actually initialized — the old
repo hard-codes `dsound` only, the documented source of the DirectSound-corruption pitfall),
`silent_play_seek` behavior preserved verbatim (Part 3.1 is explicit this is hard-won behavior,
not something to "clean up"), basic playback wired to a minimal shell UI. This is the milestone
where the app becomes actually runnable end-to-end for the first time (per Part 4's own
description) — the current `main.py` should be replaced/absorbed into a real `app.py` +
entry-point flow at that point, not left alongside it.

Consume `settings['audio']['fluidsynth_bin']`/`['soundfont']` (via `midivis.settings.load()` +
`midivis.audio.setup.ensure_audio_paths()`, both already built) instead of hard-coding paths —
that plumbing is done and tested (see above), no further work needed on the path-resolution side
this next milestone.

Reference material in the old `MidiVis` repo for Milestone 2: `fluid_engine.py` (the whole
`FluidEngine` class — ctypes bindings, `silent_play_seek`, the defensive callback-reregistration
pattern, `FLUID_PLAYER_DONE` polling) is the direct source for `fluidsynth_ffi.py` +
`fluid_player.py`; `midi_visualizer.py:420` (`FluidEngine(FLUIDSYNTH_BIN, SOUNDFONT)`
construction) and the surrounding `App.load()`/play/pause/seek methods for how the engine is
driven end-to-end today.

Nothing from Milestone 1 is left in a partial state — no cleanup needed before starting.
