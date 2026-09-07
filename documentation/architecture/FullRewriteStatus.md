# Full Rewrite Status

Repo: C:\Users\crste\git\MidiVis2
Plan: documentation/architecture/FullRewritePlan.md

## Current milestone
3 — UI shell + widgets + slots (done, plus three post-milestone bugfixes below;
awaiting your test/commit)

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
(none — Milestone 3 fully complete: widgets, theme, SlotManager with both bugs fixed,
all four slots, the dashboard, the new `main.py` shell, and the `midi/` metadata modules
it needs (`load.py`/`channel_remap.py`/`analyze.py`/`instruments.py`) are all done,
unit-tested, and manually verified against real FluidSynth hardware. Traditional
notation, recording, MIDI input/hardware, and the sequencer backend are deliberately
untouched — Milestones 4 onward.)

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

### Manual test steps for you to run
1. `python -m unittest discover -s tests -v` — should show 61/61 passing (58 from this
   milestone + 3 from the post-milestone Shift-sustain bugfix above).
2. `python main.py` — window opens at 1200×720 titled "MidiVis": menu bar (File, View)
   at the top, dashboard panel on the left (New File/Open File/Play/Reset/Tracks
   buttons), and the timeline/bars/keyboard/properties slot stack filling the rest.
3. **File > Open...**, pick a file from `midiTracks/` (e.g. `twinkle.mid`) — dashboard's
   Play/Reset/Tracks buttons enable, the bars view fills with note rectangles, the
   properties bar shows the filename + key/time-sig/tempo.
4. **Space** or the dashboard's **Play** button — audible playback starts, notes light
   up in the bars view and the on-screen keyboard as they play, the timeline fills.
5. **Click the Tracks button** — dropdown opens with All/None + one row per track
   (drum tracks, if any, grouped below a "Drums" separator). **Uncheck a track** — its
   notes disappear from the bars view and go silent (audible if it was actively
   sounding); re-check it to confirm both come back. Click **All**/**None** to confirm
   the bulk toggles work and update the "N/M tracks" hint under the button.
6. **Drag the timeline bar** while playing — should scrub smoothly (position preview
   follows the mouse without any audio glitching *during* the drag itself), then resume
   playing from the released position, not the pre-drag one. Try it again while paused —
   should hold at the released position and start from there when you press Space (this
   exercises the `seek_preview()`/`seek()` split called out in Deviations above — worth
   testing carefully since it's a real design change, not a straight port).
7. **Click and drag a key on the on-screen keyboard** — should sound a preview note
   (bypassing track mute) and highlight; **Shift+click** a key to latch/sustain it,
   click again to release. Then **Shift+click two or three different keys** (latching
   each) and **release the Shift key** (not click anything) — all of them should cut
   off immediately. This is the post-milestone bugfix above; before it, releasing
   Shift did nothing and each note stayed stuck on until individually re-clicked.
8. **Ctrl+scroll over the bars view** — zooms in/out (fewer/more measures visible).
   **Plain scroll over the bars view** — scrolls the note-lane strip up/down.
   **Shift+scroll or a horizontal trackpad swipe** over the bars view — nudges playback
   position forward/back.
9. **Drag a slot's handle strip** (the narrow grip on the left edge of each panel) to
   reorder the stack — e.g. drag Properties above Bars — confirm the new order sticks
   and that clicking within each panel still hits the right one (this exercises the
   click-priority-vs-visual-order fix).
10. **View > Slots**, uncheck one (e.g. Keyboard) — that panel disappears and the
    flexible bars view grows to fill the space; re-check it to bring it back.
11. **View > Color Theme > Light** — every panel (dashboard, menu bar, track dropdown,
    all four slots) should re-theme, including the track dropdown, which the old app
    left stuck in dark colors under Light theme (Plan Part 2's called-out bug — confirm
    it's actually fixed here, not just structurally themed).
12. **Resize the window** (drag an edge/corner) — panels reflow; shrinking narrow/short
    enough should not crash (there's a `MIN_WIN_W`/`MIN_WIN_H` floor).
13. Quit via **Esc** or the window's close button — clean exit, no traceback, no
    orphaned `python.exe` holding the audio device afterward.
14. **Regression check**: confirm play/pause/seek still behave exactly as Milestone 2's
    hardware testing established (no regressions from moving those code paths under the
    new UI) — the "seek while paused: audio may click for one frame" known issue is
    still expected and unchanged.

## Notes for the next session
Start Milestone 4 (Notation/transcription + sprite atlas) per `FullRewritePlan.md`
Part 4 and Part 3.3/3.2: `quantize.py` (rhythm quantization — duration → type/dots/
tuplet, tie-across-barline), `spelling.py` (key-signature-aware enharmonic spelling),
the glyph atlas pipeline (`assets/glyphs/` SVG source, `tools/build_atlas.py`,
`notation/glyphs.py`'s `GlyphAtlas`), `notation/engraver.py` (Timeline + TempoMap →
laid-out glyph placements, pure/no rendering), and the traditional grand-staff view
built on top of it. Per Plan Part 3.3, there's an explicit open question worth a quick
spike before committing: hand-drawn/commissioned glyph art vs. restyling an
open-license SMuFL font (e.g. Bravura) toward the rounder/weightier SimplyPiano/Flowkey
look — not blocking, but decide early since it shapes the whole atlas pipeline.

This is also where `app.view` and a `render/slots/sheet_slot.py` dispatcher (picking
between `BarsSlot` and the new traditional slot) need to be introduced — Milestone 3
deliberately skipped both since there was only one view to dispatch to (see this
session's Deviations). `BarsSlot` currently registers directly as the `'sheet'` slot id
in `main.py`; that wiring is what needs to change to go through the new dispatcher
instead, not `BarsSlot` itself.

Reference material in the old `MidiVis` repo for Milestone 4: `ui/slots/
traditional_sheet.py` (596 lines — the live grand-staff renderer; `ui/slots/
midi_sheet_traditional.py` is the confirmed-dead pre-refactor leftover, don't use it)
for the overall layout algorithm (staff positioning, stem/beam/ledger-line drawing,
voice/staff assignment), but per Plan Part 3.3 the specific pieces to *replace* rather
than port are: the OS-font clef lookup (silently disappears if `segoeuisymbol` lacks
the glyphs — Plan Part 2's called-out failure mode), the literal-`'#'`-character
accidentals (always sharp, ignores `app.key_sig`), and the hand-drawn Bézier rests.
Keep stems/beams/ledger-lines/staff-lines procedural per Part 3.3 — they already look
fine and are naturally resolution-independent.

Nothing from Milestone 3 is left in a partial state — no cleanup needed before
starting. `App.timeline`/`note_events`/`track_channels`/`instruments` and the
`midi/load.py`/`channel_remap.py`/`analyze.py` modules from this session should be
kept and built on, not rebuilt — the notation engraver consumes the same `Timeline`
the bars view already does.

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
