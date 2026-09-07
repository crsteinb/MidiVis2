# Full Rewrite Status

Repo: C:\Users\crste\git\MidiVis2
Plan: documentation/architecture/FullRewritePlan.md

## Current milestone
3 — UI shell + widgets + slots (not started)

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
2 — Audio engine v1. Done this session:
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
(none — Milestone 2 fully complete: `AudioEngine` interface, `FluidPlayerBackend` with
the WASAPI-first driver fallback chain and `silent_play_seek` preserved, `app.py`
rewritten to delegate to the engine, and the minimal shell UI in `main.py`, are all
done and verified against real FluidSynth hardware. `midi/load.py`/`Timeline`
population, track list/mute, `render/widgets`, `SlotManager`, and every other
audio/render/notation/input module are deliberately untouched — they belong to
Milestone 3 onward.)

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

## Test results from this session
- `python -m unittest discover -s tests -v` — 17/17 passing (9 from Milestone 1's
  `test_model.py`, unchanged; 8 new in `test_app.py`). See "Files touched" above for
  what `test_app.py` covers and the real bug it caught (`App.update()`'s DONE-detection
  gating on `self.playing`, which is already `False` by the time status is `DONE`).
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

### Manual test steps for you to run
1. `python -m unittest discover -s tests -v` — should show 17/17 passing.
2. `python main.py` — window opens titled "MidiVis", showing "No file loaded — Ctrl+O
   to open" and the driver status line at the bottom (should say `[wasapi driver]` or
   `[dsound driver]`/`[waveout driver]` if wasapi isn't available on your machine).
3. **Ctrl+O**, pick a file from `midiTracks/` (e.g. `twinkle.mid`) — title updates to
   the filename, elapsed/total time appears, status line shows "paused".
4. **Space** — should start playing (audible), status line flips to "playing", the blue
   bar fills left-to-right in real time, elapsed time counts up.
5. **Space again** — pauses; elapsed stops advancing; press Space again to resume from
   the same position (not from 0).
6. **Click partway along the timeline bar** while paused — should jump the displayed
   elapsed time to that position (may click/blip audibly for one frame — this is the
   documented "seek while paused" known issue, not new this session). Press Space to
   confirm it resumes playing from the clicked position, not from before the click.
7. **Click near the very end of the bar while playing**, then wait — audio should
   finish, the bar should stop advancing and reset to the start, status flips back to
   "paused" with elapsed at 0:00 (may take a few seconds longer than the displayed
   total time to actually stop — this is the FluidSynth audio-tail behavior noted
   above, not a hang).
8. Press Space again after that — should replay cleanly from the beginning.
9. Quit via Esc or the window's close button — should exit cleanly, no traceback, no
   lingering FluidSynth/audio process (Task Manager: no orphaned `python.exe` holding
   the audio device after the window closes).
10. **Regression check on Milestone 1's flow**: delete/rename `%APPDATA%\MidiVis2\settings.json`
    and run `python main.py` again — should still auto-detect FluidSynth/SoundFont and
    write a fresh settings file (Milestone 1's `ensure_audio_paths()` is unchanged
    this session, but this confirms Milestone 2 didn't accidentally break the
    first-run flow it depends on).

## Notes for the next session
Start Milestone 3 (UI shell + widgets + slots) per `FullRewritePlan.md` Part 4 and
Part 3.4: `render/widgets/` (`Button`, `Menu`/`Submenu`, `Scrollbar`, `TextInput`,
`MiniKeyboard`), theme consolidation (`render/theme.py`, including the Track dropdown
and Record-arm panel the old repo left un-themed), `SlotManager` (fix the
click-priority-vs-visual-order mismatch and single-flex-slot limitation while it's
being built, not after), and the actual views: timeline, bars (piano-roll), keyboard,
properties. Per Plan Part 4, this milestone should reach "feature parity with today's
app apart from traditional notation" — i.e. track list + per-track mute (which needs
`midi/channel_remap.py` — not yet built; check whether Milestone 3's scope expects a
basic remap now or whether it's still deferred to Milestone 5's "channel-remap
edge-case fixes," which implies *some* remap needs to exist before then for mute to
work at all. Re-read Part 3.4/3.2 together before starting to resolve this — it
wasn't fully unambiguous on a close read this session).

Milestone 2's minimal shell UI in `main.py` (the 900×220 window, inline pygame
drawing) is explicitly throwaway — Milestone 3 replaces it wholesale with the real
`SlotManager`-based shell, not an incremental extension of it. Don't try to preserve
or extend the current `main.py` UI code; keep only its settings/engine-construction
bootstrapping (audio setup, `FluidPlayerBackend` construction, `atexit`-style shutdown)
when writing the new entry point.

`App` (`midivis/app.py`) will need to grow this milestone: track list (`tracks`,
`enabled_tracks`, per-track mute calling `engine.set_channel_muted`), and probably
`Timeline` population (`midi/load.py`, not yet built) if the bars view wants real note
events rather than re-parsing the `mido.MidiFile` directly — check Plan Part 3
(`midi/load.py`'s stated purpose: "SMF -> Timeline, replaces
midi_processing.build_timeline/build_note_events") before deciding whether `load.py`
belongs in this milestone or can wait. `App.tempo_map`/`total_dur`/`engine` from this
session should be kept, not rebuilt.

Reference material in the old `MidiVis` repo for Milestone 3: `ui/dashboard.py` (file
open/track list/record-arm — but per Plan Part 3.4/CLAUDE.md, its hand-rolled
`TextInput` and per-button hardcoded pixel offsets are exactly what `render/widgets/`
should replace, not copy), `ui/menu_bar.py` (the six-times-duplicated hit-test/draw
logic Part 3.4 wants collapsed into one `Menu`/`Submenu` widget), `ui/slot_manager.py`
+ `ui/slots/timeline.py`/`keyboard.py`/`properties.py` (the SlotLayout pattern,
including its two known bugs called out in Plan Part 2 — click-priority order and
single-flex-slot — fix both while porting, not after), `ui/theme.py` (dark/light
palettes to consolidate everything onto), `midi_processing.py` (`get_track_names`,
`get_track_channels`, `remap_channels`, `get_instruments` — needed once track list +
mute land; `remap_channels` specifically if Milestone 3 decides it needs basic remap
now rather than deferring fully to Milestone 5).

Nothing from Milestone 2 is left in a partial state — no cleanup needed before starting.

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
