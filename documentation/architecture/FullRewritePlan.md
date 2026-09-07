# MidiVis Full Rewrite Plan

## Context

MidiVis started as a quick subprocess-driven FluidSynth wrapper (`cb78600`, commit message literally
"Has issues with playback"), was rebuilt on FluidSynth's ctypes C API two commits later, and has since
grown organically through a series of "add feature → patch the thing that broke" commits: live
recording, MIDI hotplug input, a hand-rolled draggable panel system, and a from-scratch grand-staff
renderer. The architecture has held up surprisingly well for how far it's been pushed, but three
concrete, still-open problems prompted this rewrite:

1. **FluidSynth playback freezes**, **seek plays from the wrong location**, and **DirectSound
   occasionally corrupts** badly enough to need `net stop/start "Windows Audio"` or a reboot. The
   current code already contains a heavily-commented workaround for the worst of this
   (`FluidEngine.silent_play_seek` in [fluid_engine.py](../../fluid_engine.py) — mute every channel,
   play, seek, `sounds_off` everything as a backstop, then restore mute state) plus a policy of
   re-registering the playback callback after nearly every player call, evidence that the
   play-then-async-seek model is being fought rather than solved.
2. Note/bar/measure timing is wall-clock-only (`pygame.time.get_ticks()`), never checked against what
   FluidSynth is actually outputting — so timing drift, freezes, and desync are invisible to the app
   until the user notices the sound is wrong.
3. Notation rendering mixes hand-drawn vector shapes with OS-font glyphs in a way that looks
   inconsistent and is fragile (clefs render only if `segoeuisymbol` happens to contain the right
   Unicode musical-symbol codepoints on the host machine; silently disappear otherwise).

This document inventories what the app does today, the specific pitfalls found while reading every
module, and the target architecture for a full rewrite — informed by your answers: build a swappable
audio-backend abstraction (FluidSynth's player *and* a custom sample-accurate sequencer, chosen at
runtime via settings, so both can be compared); treat SimplyPiano/Flowkey as a real feature direction
(practice mode), not just a style reference; lay cross-platform groundwork without committing to
shipping on other OSes yet; and execute as a clean full rewrite in staged milestones rather than an
in-place patch sequence.

---

## Part 0 — Where & How This Gets Executed

**Location**: this is not an in-place refactor. The rewrite lives in a new sibling repository at
`C:\Users\crste\git\MidiVis2`, git-initialized from scratch — not a fork/clone of `MidiVis`. The
current `MidiVis` repo stays exactly as-is on disk, untouched, as a reference the new codebase can be
read against (GM instrument tables, the exact `silent_play_seek` workaround, sample MIDI files under
`midiTracks/`, etc.) but never edited or executed as part of this work.

**Three-file tracking system**, all under `documentation/architecture/` (in both repos — see Milestone
0 below):
- **`FullRewritePlan.md`** — this document. Stable; the source of truth for scope and architecture.
  Only edited when the plan itself changes (a milestone turns out to be wrong, a new requirement shows
  up) — not touched just to record progress.
- **`FullRewriteStatus.md`** — the living progress tracker, updated at the end of every session. Says
  which milestone is current, what's done, what's in-progress, decisions/deviations made along the way,
  test results, and what a fresh context needs to know to continue. This is the file a new session reads
  first.
- **`FullRewritePrompt.md`** — a reusable, copy-pasteable prompt (given in full in Appendix B at the end
  of this document) that kicks off "resume and do the next milestone." You paste its contents into a
  fresh context each session; it tells the agent to read Status + Plan, do exactly one milestone's worth
  of work, then stop.

**Checkpoint policy** (per your instruction — you want to test and commit between milestones, not have
an agent barrel through all of them):
- One session implements **one milestone** (or, if a milestone is large, an explicitly-scoped slice of
  it — Status records exactly where the slice ended).
- The agent **stops at the milestone/slice boundary** — it does not automatically continue into the
  next milestone even if it finishes with tokens/time to spare.
- The agent **does not commit**. It leaves the working tree with uncommitted changes for you to review,
  test, and commit yourself — matching how this session has behaved throughout.
- Before stopping, the agent **updates `FullRewriteStatus.md`**: what was completed, files touched, any
  deviations from the plan and why, manual test steps for you to run, and anything a fresh context would
  need to know to pick up cleanly (there is no conversation memory carried between sessions — Status is
  the only handoff mechanism).

**Running a session**: open a fresh Claude Code context with `C:\Users\crste\git\MidiVis2` as the
working directory, paste in the contents of `FullRewritePrompt.md` (Appendix B), and it will read
Status + Plan and proceed. You do not need to explain anything else — that's the point of the prompt
file.

---

## Part 1 — Current Feature Inventory (must survive the rewrite)

**Playback**
- Load any type-0/type-1 SMF via `mido`; tempo map, time signature, key signature (meta or
  pitch-class-detected fallback) extraction.
- Channel remap on load so every track gets a unique MIDI channel (drum tracks pinned to ch. 9),
  enabling accurate per-track mute regardless of the file's original channel layout.
- Play / pause / seek (click-to-scrub and drag-to-scrub, with visual-only "preview" during drag),
  reset-to-start, horizontal-mouse-wheel nudge-seek.
- Per-track mute via a channel-level playback-callback filter; keyboard/preview notes bypass muting.
- Sheet zoom (ctrl+wheel), independent vertical scroll per view.

**Views (draggable/reorderable/hideable vertical panel stack)**
- Timeline scrubber.
- Piano-roll ("bars") view — colored note rectangles, mini vertical keyboard strip, octave/measure
  gridlines.
- Traditional grand-staff notation view — hand-vector noteheads/stems/flags/beams/ledger lines, an
  OS-font clef and sharp-only accidentals, heuristic rest placement, 2x-supersampled soft AA.
- On-screen 88-key piano (click/drag/glissando, Shift = latch/sustain toggle).
- Properties panel — file metadata, key/time/tempo, instrument list, live MIDI-input device status.

**Input & recording**
- Computer-keyboard piano input (2-octave QWERTY layout, Shift = sustain pedal with correct
  "ring until pedal or key release, whichever is later" semantics).
- USB MIDI device hotplug detection (subprocess-isolated enumeration to dodge an rtmidi/Windows GIL
  freeze), debounced disconnect (2 missed polls) to survive transient enumeration hiccups.
- Live recording: arm → record → save-as-new-track workflow with a `.work`-file safety copy, a
  template-driven track-name field, melodic/drum channel+instrument picker, live note overlay on both
  sheet views while recording, auto-extending timeline if recording runs past the loaded file's end.
- Track deletion (soft, committed to disk on quit/before next recording).

**App shell**
- File menu (new/open/recent), View menu (theme, slot visibility), Keyboard menu (mute toggle).
- Dark/light theme, mostly centralized (`ui/theme.py`), persisted to `%APPDATA%\MidiVis\settings.json`
  (atomic write).
- Native file-open/save dialogs via a throwaway `tkinter.Tk()` root.

**Adjacent tooling (documented, not wired into the app)**
- `documentation/architecture/MixToMidi.md` — an external Demucs → basic-pitch → mido pipeline for
  turning a mixed MP3 into a multi-stem MIDI file loadable by MidiVis. Stays an external pre-processing
  step for now; not in scope for this rewrite, but the future-features section below leaves room for
  it.

---

## Part 2 — Pitfalls Found (root causes, not just symptoms)

### Audio engine
- **`audio.driver` is hard-coded to `dsound`**, no fallback. This is the documented source of the
  "reboot needed" DirectSound corruption.
- **`silent_play_seek`** exists because `fluid_player_play()` on a DONE/READY player restarts from
  tick 0, and the subsequent `fluid_player_seek()` call is asynchronous — there's a real window where
  wrong-position audio would be audible without the all-channels-mute-then-`sounds_off` workaround.
  `fluid_player_seek()` also only works while the player is `PLAYING`, forcing every "seek while
  paused" call to transiently `play()` then re-`pause()`.
  The callback is defensively re-registered after almost every player call — evidence this was tuned
  against observed flakiness, not derived from documented API guarantees.
- **Elapsed time is wall-clock (`pygame.time.get_ticks()`), never reconciled against FluidSynth's own
  position** (`get_tick()` is deliberately unused because async-seek makes it stale). This means any
  real audio hiccup — a freeze, an underrun, a stall — is invisible to the app; the UI clock and note
  highlighting keep marching forward whether or not sound is actually playing.
- **This is the second audio backend the project has tried.** The very first commit used
  subprocess + stdin-shell control of a `fluidsynth` binary (CC7-volume-based "muting", a Windows Job
  Object to avoid orphaned processes, a crash-watcher thread) and was abandoned one commit later for
  reliability reasons. The lesson: don't re-introduce subprocess/IPC control of the synth.
- Hard Windows-only (`os.add_dll_directory`, hard-coded `libfluidsynth-3.dll`, `dsound`).

### MIDI data / timing model
- Tempo-map-to-ticks conversion logic is implemented **three times independently**
  (`App._seconds_to_ticks`, `midi_processing.build_timeline`'s internal closure, and implicitly via
  `MidiRecorder`'s fixed-tempo math) — a single shared, bidirectional tempo-map utility doesn't exist.
- `MidiRecorder` converts elapsed-seconds to ticks using **one fixed tempo captured at arm() time** —
  notes recorded across a tempo-change boundary drift off-grid.
- Channel remap hard-caps at 15 melodic channels (MIDI's real limit); tracks beyond that silently
  fall back to `min(original_channels)`, which can collide with another track's assigned channel and
  break per-track mute isolation. Multiple simultaneous drum tracks (all pinned to ch. 9) also
  silently collapse into one mute group.
- "Active notes" (for highlighting) is walked via three near-duplicate copies of the same
  "scan timeline, toggle on note_on/off" loop (`_rebuild_active_notes`, `_sync_event_index`,
  `App.update()`'s tail loop).
- `_seconds_to_ticks`/timeline building do an **O(n) linear rescan** on every seek — fine at today's
  file sizes, a latent perf cliff for long, dense files.

### Notation rendering
- Clefs are rendered by asking an OS font (`segoeuisymbol`) for the Unicode Supplementary-Multilingual-
  Plane musical-symbol codepoints (U+1D11E, U+1D122) and rescaling the resulting glyph bitmap. If the
  font doesn't have those glyphs, **clefs silently disappear** with no fallback.
- Accidentals are a literal `'#'` character rendered via a normal system font — always sharp,
  never flat/natural, and **ignorant of the file's actual key signature** (`app.key_sig` is computed
  but never consulted for enharmonic spelling).
- Rests are hand-drawn Bézier-curve approximations tuned by eye (hardcoded control points like
  `(rx-3*sc, cy-int(ls*0.9))`) — not font-rendered, but visibly the roughest shapes in the renderer,
  and almost certainly what reads as "looks terrible."
- Note-duration classification is fixed-threshold beat-count bucketing — no dotted notes, no
  triplets, no ties across barlines, and rest placement is a heuristic gap-finder rather than derived
  from real quantization.
- Voice/staff assignment is a hardcoded pitch ≥ 60 split, not track/channel/clef-aware — multi-track
  files with an explicit left/right-hand track structure get flattened into a naive pitch threshold.
- The whole staff is rendered at 2x internal resolution then `smoothscale`d down every frame purely to
  fake anti-aliasing pygame doesn't do natively for primitives — real cost, band-aid quality.

### UI layer
- **`ui/dashboard.py` (1146 lines)** carries most of the UI's technical debt: absolute hardcoded pixel
  offsets for every button (separator lines must be hand-kept in sync with them), a from-scratch
  single-line text-input widget (cursor blink, click-to-position, insert/delete) duplicating standard
  toolkit behavior, a `tkinter.Tk()` root spun up and destroyed per file-dialog call, and direct reads
  into other subsystems' `_`-prefixed "private" attributes (`app._track_channels`, `app._tempos`,
  `app._seconds_to_ticks`).
- The Track dropdown and Record-arm sub-panels **bypass the theme system entirely** — hardcoded color
  literals mean Light theme silently does nothing to them (a real, present bug, independent of the
  rewrite).
- **`ui/menu_bar.py`** re-implements the same "list of items, optional separators, optional submenu"
  hit-test/draw logic **six times** with only width/anchor constants differing — a clear
  generalize-once opportunity.
- **`ui/slot_manager.py`** (the reorderable-panel system) is a reasonable pattern overall but:
  click-priority order is a hardcoded tuple independent of the actual visual stacking order (so
  dragging "properties" above "sheet" doesn't change click priority — a real latent bug); only one
  "flex" slot is genuinely supported (two simultaneously-flexible slots would overlap); `rects()` is
  redundantly recomputed once per slot per frame (O(n²), harmless at n=4).
- Scrollbar drag-thumb logic and "mini keyboard with active-note highlight" are each independently
  reimplemented 2–3 times (`bars_sheet.py`, `traditional_sheet.py`, `keyboard.py`) instead of shared.
- `ui/slots/midi_sheet_bars.py` and `ui/slots/midi_sheet_traditional.py` are **dead leftover files**
  from before the OOP refactor (superseded by `bars_sheet.py`/`traditional_sheet.py`), still tracked in
  git, imported by nothing — confirms `CLAUDE.md`'s architecture section is stale.

### MIDI I/O
- USB device enumeration runs a **fresh Python subprocess every 5 seconds forever**, specifically to
  dodge `python-rtmidi` holding the GIL during Windows MIDI API calls. This is a real, deliberate
  design decision (not an accident) but has a **packaging landmine**: it invokes `sys.executable -c
  "..."`, which breaks silently under a frozen/bundled executable (PyInstaller etc.) since
  `sys.executable` would then be the app itself, not a Python interpreter — worth fixing if this ever
  ships as a packaged app.
- Sustain-pedal (CC64) "hold notes until pedal or key release, whichever is later" is correctly
  implemented for the **computer keyboard** input but has **no equivalent for real USB MIDI
  keyboards** — CC64 is recorded for playback-file purposes but never forwarded live, so a hardware
  sustain pedal doesn't audibly sustain through this app's live-monitoring path.
- The `ChannelAction` model declares `'volume' | 'tempo' | 'pitch_bend' | 'cc'` action kinds but only
  `'piano_notes'` is implemented — dead/half-built branches with no tracking.
- Port lookup by exact name match; two identically-named USB-MIDI devices are ambiguous.

### Project hygiene
- `FLUIDSYNTH_BIN` / `SOUNDFONT` are absolute paths to files on the developer's own machine
  ([midi_visualizer.py:43-44](../../midi_visualizer.py#L43-L44)) — a hard blocker for anyone else
  running this, and for any future packaging.
- No `requirements.txt`/`pyproject.toml`; `dependencies/mido` and `dependencies/midi2audio` are vendored
  copies that aren't actually imported by anything (the app uses a pip-installed `mido`) — dead weight
  mixed in with the one submodule that *is* real infrastructure context (`dependencies/pyfluidsynth`,
  also currently unused directly since `fluid_engine.py` hand-rolls its own ctypes bindings).
- `CLAUDE.md`'s architecture section describes the pre-refactor file layout — stale documentation is
  itself a process pitfall worth calling out (this rewrite should update it as part of the work, not
  after).

---

## Part 3 — Target Architecture

```
midivis/
  audio/
    engine.py          — AudioEngine ABC: play/pause/seek/get_clock_seconds/set_channel_muted/...
    fluid_player.py     — FluidPlayerBackend: today's fluid_player-based approach, refined
    sequencer.py        — SequencerBackend: custom sample-accurate engine (new)
    fluidsynth_ffi.py    — shared ctypes bindings to libfluidsynth (both backends sit on this)
    devices.py          — audio output device enumeration (PortAudio-backed)
  midi/
    model.py            — Timeline, TempoMap, NoteEvent — single source of truth data structures
    load.py             — SMF -> Timeline (replaces midi_processing.build_timeline/build_note_events)
    channel_remap.py    — track -> channel assignment (fixes the >15-track / multi-drum-track gaps)
    quantize.py         — rhythm quantization: duration -> (type, dots, tuplet), tie-across-barline
    spelling.py         — key-signature-aware enharmonic pitch spelling
    recorder.py         — recording state machine (tempo-map-aware, not single-tempo)
  input/
    manager.py          — device hotplug + per-(device,channel) role routing (packaging-safe enum.)
    keyboard.py          — computer-keyboard input
    hardware.py          — RtMidi hardware input (adds live sustain-pedal passthrough; multiple
                             simultaneous devices, channel-demuxed roles for combo keys+pads devices)
    drum_pads.py         — on-screen drum pad input, configurable pad -> note mapping
  notation/
    engraver.py         — Timeline + TempoMap -> laid-out glyph placements (pure, no rendering)
    glyphs.py            — GlyphAtlas: loads the sprite atlas, exposes glyph lookups by name/size-tier
  render/
    theme.py             — single theme source (already close to this; consolidate dashboard into it)
    widgets/              — Button, Menu, Dropdown, Scrollbar, TextInput, MiniKeyboard (shared, not
                             reimplemented per-slot)
    slots/                — thin views: timeline, bars, traditional, keyboard, drum_pad, properties,
                             (practice)
  practice/
    scoring.py            — compare live input against the loaded piece, timing/pitch tolerance
    session.py            — practice-mode state: hand isolation, tempo scaling, section looping
  app.py                  — App state (slimmed: delegates to audio/midi/notation, not a god-object)
  settings.py              — (keep close to as-is; solid)
  main.py
tools/
  build_atlas.py           — offline: vector glyph sources -> packed sprite atlas + manifest
assets/
  glyphs/                  — source vector art (SVG) for the notation glyph set
  atlas/                   — generated PNG + JSON manifest (checked in or built at install time)
```

### 3.1 Audio backend abstraction (your choice: build both, switchable)

Define one `AudioEngine` interface both backends implement:

```python
class AudioEngine(Protocol):
    def load(self, midi_bytes: bytes) -> None: ...
    def play(self) -> None: ...
    def pause(self) -> None: ...
    def seek(self, ticks: int) -> None: ...
    def get_clock_seconds(self) -> float: ...   # authoritative elapsed time
    def get_status(self) -> PlayerStatus: ...
    def set_channel_muted(self, channel: int, muted: bool) -> None: ...
    def note_on/note_off/cc/program_change(...) -> None: ...   # live/preview passthrough
```

**`FluidPlayerBackend`** — today's model, kept because it's the known-working path and useful as a
comparison baseline:
- Preserve `silent_play_seek` and the defensive callback-reregistration pattern verbatim — this is
  hard-won institutional knowledge about real FluidSynth behavior, not incidental code to "clean up."
- Add a driver fallback chain: try `wasapi` first (lower latency, avoids DirectSound's corruption
  history), fall back to `dsound`, then `waveout`, logging which one actually initialized.
- `get_clock_seconds()` still uses wall-clock internally (same reasoning as today: `fluid_player`'s own
  tick counter lags behind seeks) — this backend's clock is *not* audio-derived, and that should be a
  documented, visible property of choosing it, not a hidden gotcha.

**`SequencerBackend`** — the structural fix:
- Never touch `fluid_player`. Render audio directly via `fluid_synth_write_s16`/`write_float` into a
  buffer, driven by our own audio output stream (via `sounddevice`, which wraps PortAudio and exposes
  WASAPI shared/exclusive, ASIO, and — cross-platform bonus — CoreAudio/ALSA backends through one API).
- Maintain our own tick-indexed event queue (built from `midi.model.Timeline`) and inject MIDI events
  into the synth at exact sample-frame boundaries inside the audio callback — this is what makes seek
  and mute *not racy*: there's no async player state machine to fight, just "what sample are we
  rendering right now, what events fall in this block."
  `get_clock_seconds()` becomes **samples rendered so far / sample rate** — a true audio-derived clock,
  finally closing the gap that let freezes go unnoticed.
  Looping a practice section, adjustable tempo (scale event timestamps, not audio time-stretch — pitch
  stays correct since we're re-synthesizing, not resampling captured audio), and count-in are all
  straightforward here and much harder to bolt onto `fluid_player`.
- This is genuinely the highest-effort, highest-risk part of the rewrite. Build it after
  `FluidPlayerBackend` is solid, behind the same interface, so the app works throughout.

**Settings**: `audio.backend: "fluid_player" | "sequencer"` (and, for the player backend,
`audio.driver: "auto" | "wasapi" | "dsound" | "waveout"`), switchable without restarting if feasible,
restart-to-apply otherwise. This directly gives you the side-by-side comparison tool you asked for.

### 3.2 MIDI data model & notation/transcription engine

- One `Timeline`/`TempoMap` object, one tempo-conversion utility (`seconds_to_ticks`,
  `ticks_to_seconds`) used everywhere — deletes the three duplicated implementations.
- `channel_remap.py` fixes the two known gaps: detect and warn (or auto-split) when a file has more
  than 15 melodic tracks or multiple simultaneous drum tracks, instead of silently colliding mute
  groups.
- `quantize.py`: real rhythm quantization against a configurable grid (default: the file's own
  resolution), producing duration classes with dots and simple tuplets, and tie-generation across
  barlines — replaces the fixed-threshold beat bucketing and heuristic gap-rest-finder.
- `spelling.py`: enharmonic spelling driven by the actual key signature (falls back to the existing
  pitch-class detector when absent) — fixes "always sharp" accidentals.
- Voice/staff assignment becomes a per-track/channel property (with pitch-based default), not a
  hardcoded pitch ≥ 60 split — so multi-track files that already encode left/right hand keep that
  structure.
- `recorder.py` converts using the live tempo map at the actual recorded tick, not one tempo frozen at
  arm() time.

**Recording quantization (new — fixes "bar view tends to have unaligned bars"):** live-played notes
never land exactly on the grid, so recorded note onsets/durations drift relative to the tempo map,
which is exactly what makes bars look unaligned in the piano-roll/notation views afterward. `quantize.py`
gains a companion function that operates on recorded ticks directly (not just on render-time duration
classification): snap each recorded note's onset — and, separately, its duration — to the nearest
subdivision of a configurable grid (1/8, 1/16, 1/16 triplet, etc.), with an adjustable **strength**
(0–100%: 100% = hard-snap to grid, lower values pull partway there, preserving some human feel).
Exposed in the Record-arm panel as a grid + strength setting, applied either live as events are
buffered or as a one-shot pass in `stop_and_save()` before the track is written — the latter is safer
(lets the raw take be discarded/re-quantized without re-recording) and is the default; both reuse the
same quantization math the notation engine already needs, so this isn't a second parallel
implementation.

### 3.3 Sprite-atlas notation rendering

- Author (or adapt) a small vector glyph set — clef (treble/bass, maybe alto for later), noteheads
  (whole/half/filled), accidentals (sharp/flat/natural), rests (whole/half/quarter/8th/16th), time
  signature digits, dynamics if/when needed — in the clean-but-weighty SimplyPiano/Flowkey style you
  referenced, as SVG source under `assets/glyphs/`.
  *Open question, not blocking the plan*: hand-draw/commission original art, or start from an
  open-license SMuFL font (e.g. Bravura, SIL license) and restyle it toward the rounder/weightier look
  — worth a quick spike before committing either way.
- `tools/build_atlas.py`: offline pipeline — rasterize each SVG at 2–3 fixed size tiers (covers the
  zoom range without needing the current runtime supersample-then-smoothscale trick), pack into one
  atlas PNG + a JSON manifest (glyph name/tier → UV rect).
- `notation/glyphs.py` (`GlyphAtlas`): loads the atlas once, returns `pygame.Surface.subsurface()`
  regions for blitting — no runtime font lookups, no OS-font dependency, no silent-omission failure
  mode.
- Keep stems/beams/ledger-lines/staff-lines procedural (they already look fine and are naturally
  resolution-independent for arbitrary angles/lengths) — the atlas replaces exactly the pieces that are
  either font-dependent (clefs, accidentals) or visually rough (rests), per your framing.

### 3.4 UI layer

- Extract a real shared widget layer (`render/widgets/`): `Button`, `Menu`/`Submenu` (collapses
  menu_bar.py's six duplicated hit-test/draw blocks into one parameterized component), `Scrollbar`
  (used by both sheet views instead of two copies), `TextInput` (replaces dashboard's hand-rolled
  cursor/editing code), `MiniKeyboard` (used by both the bottom keyboard and the piano-roll's strip).
- Consolidate **all** chrome — including the Track dropdown and Record-arm panel — onto the one theme
  system; delete the hardcoded-literal fallback colors in `Button.draw`.
- Fix `SlotManager`'s click-priority-vs-visual-order mismatch and the single-flex-slot limitation while
  the panel system is being touched anyway (both are small, contained fixes).
- Keep the tkinter file-dialog approach (it already works fine, per `CLAUDE.md`; cross-platform too).

### 3.5 Practice mode (new — you confirmed this is a real feature direction, not just style)

- `practice/session.py`: hand isolation (solo/mute by assigned hand, reusing the staff/hand-assignment
  data from 3.2), adjustable practice tempo (via the sequencer backend's event-timestamp scaling),
  section looping (start/end measure markers, seek-back-on-reach for the sequencer backend; approximate
  for the fluid_player backend), count-in.
- `practice/scoring.py`: compare live MIDI input (from `input/`) against the expected notes at the
  current playhead window; pitch-correct/incorrect and (later) timing-tolerance feedback, surfaced back
  into the sheet views as a color state (extends the existing `active_notes`-highlight mechanism rather
  than replacing it).
- A new "practice" slot type (falling-notes highway over the on-screen keyboard, matching the reference
  screenshots) sits alongside — not instead of — the existing bars/traditional views; it's presentation
  over the same `Timeline`/`GlyphAtlas`/scoring data, not a parallel data model.
- Scope note: this is the largest net-new feature area. Build it after the audio/notation/rendering
  foundations are solid — trying to build practice-mode scoring on top of the wall-clock-drift timing
  model would just inherit the same bugs this rewrite exists to fix.

### 3.6 Per-device, per-channel input routing + drum pad input & slot (new)

Two of your devices drive this design directly: a MIDI keyboard and a separate drum pad controller
connected *simultaneously*, and a combo controller (Akai-style keys+pads in one box) that can send
keys and pads on **different channels from the same physical port**. Today's model
(`midi_input.py`'s `ChannelAction`) already gestures at per-channel routing but only ever implements
one action kind (`'piano_notes'`) — this generalizes it into the real mechanism rather than adding a
second, parallel one.

- **Routing model**: every connected input (computer keyboard, and each independently-enumerated USB
  MIDI port) has a per-channel **role** assignment: `piano` (pass through to the keyboard/note-on
  pipeline), `drum_pads` (route through the drum-kit note mapping below), or `ignore`. This replaces
  the half-built `ChannelAction` enum with a fully-implemented one.
  - Two separate physical devices → typically one device's channel(s) all set to `piano`, the other's
    all set to `drum_pads`.
  - One combo device (keys + pads on different channels of the same port) → that single device's
    channel-role map has e.g. channel 1 = `piano`, channel 10 = `drum_pads` — both roles active
    concurrently from one `RtMidiInput` connection, demultiplexed by channel before dispatch.
  - `input/manager.py` demuxes each incoming message by `(device_id, channel)` to the right logical
    handler instead of assuming one role per port, which is the structural change from today's
    one-handler-per-port model.
- **Drum kit note mapping** is independent of routing: it defines what each pad *means* (which
  physical/incoming note maps to which kit piece — kick, snare, hats, etc.) regardless of which
  device/channel feeds it. Pre-populated from the standard GM percussion layout already present in
  `midi_instruments.GM_DRUM_NOTE_NAMES`, remappable per pad (click a pad, then play/pick the source
  note to reassign it).
- **On-screen drum pad input**: a grid of clickable/touchable pads is *also* just another input
  source feeding the same `drum_pads` role/kit mapping (`input/drum_pads.py`, a `DrumPadInput` with the
  same `note_on_callback`/`record_*_callback` shape as `MidiInputBase`) — the on-screen pads and a
  hardware pad controller are two producers into the same pipeline, not two separate features.
- **Settings**: persisted per device as `{device_id: {channel: role}}` alongside the existing
  per-role config (keyboard key-note map, drum-kit pad-note map), extending the pattern already used
  for `midi_inputs` in `settings.json` today. The "MIDI Inputs" panel (today's `properties.py` list,
  carried into `render/`) grows a per-device-per-channel role picker instead of assuming a device-level
  role.
- New `render/slots/drum_pad.py` view: a fixed-height pad grid (visually distinct from piano keys),
  active-state highlighting reusing the same `active_notes` mechanism the piano keyboard and piano-roll
  strip already use — no new highlighting concept needed.
- Works for both live play-along (through whichever `AudioEngine` is selected) and as a recording input
  source (arm a drum track; pad hits from any routed device/on-screen grid land on channel 9 like any
  other drum-track recording).

### 3.7 MIDI I/O fixes

- Replace subprocess-per-poll enumeration with a **persistent** helper process (spawned once, polls
  internally, reports over a pipe) instead of spawning a fresh interpreter every 5 seconds — same GIL-
  isolation benefit, far less overhead, and avoids the `sys.executable -c` packaging landmine (the
  persistent helper can be a proper frozen-safe entry point).
- Forward CC64 live to the audio engine for hardware MIDI input (parity with the computer-keyboard
  path's correct sustain semantics).
- Either implement the declared `ChannelAction` kinds (`volume`/`tempo`/`pitch_bend`/`cc`) or remove
  them from the model — no more half-built dead branches.
- Disambiguate same-named USB-MIDI ports (index-based identity in addition to name).

### 3.8 Cross-platform groundwork (per your answer: lay groundwork, don't commit to shipping)

- `sounddevice`/PortAudio for the sequencer backend audio path is inherently cross-platform (WASAPI/
  ASIO/DirectSound on Windows, CoreAudio on macOS, ALSA/PulseAudio/JACK on Linux) — choosing it over a
  Windows-only ctypes audio path is the single highest-leverage portability decision here.
- Isolate the remaining genuinely Windows-only pieces (`os.add_dll_directory`, `libfluidsynth-3.dll`
  naming, the `dsound`/`waveout` driver options) behind small platform-detection shims so a future
  macOS/Linux port touches one file, not the whole audio layer.
- Replace the hard-coded `FLUIDSYNTH_BIN`/`SOUNDFONT` absolute paths with settings-driven config + a
  first-run setup flow (detect common install locations, else prompt) — this alone unblocks anyone else
  running the app, on any OS.
- Add a `requirements.txt`/`pyproject.toml`; drop the unused vendored `dependencies/mido` and
  `dependencies/midi2audio` copies (the app uses pip-installed `mido`; nothing imports the vendored
  ones).

---

## Part 4 — Milestones

Each numbered milestone is one session's worth of work under the checkpoint policy in Part 0: implement
it, leave the app runnable, update `FullRewriteStatus.md`, stop — don't continue into the next one in
the same session. Earlier milestones intentionally under-deliver on notation/practice polish rather
than block on them.

0. **Bootstrap `MidiVis2`** — `git init` the new repo at `C:\Users\crste\git\MidiVis2`; create
   `documentation/architecture/` and copy this plan (`FullRewritePlan.md`), an initial
   `FullRewriteStatus.md` (Appendix A), and `FullRewritePrompt.md` (Appendix B) into it; copy over
   `CLAUDE.md` as a starting point (to be rewritten as the new architecture solidifies) and the
   `midiTracks/` sample files. Do **not** copy any old source modules wholesale — the target module
   layout is different enough that each piece should be written fresh against the plan, consulting the
   old `MidiVis` repo (left untouched on disk) as reference. End state: an empty-but-initialized repo,
   Status says "Milestone 0 done, ready for Milestone 1."
1. **Scaffolding** — new package layout, `requirements.txt`/`pyproject.toml`, settings-driven
   FluidSynth/soundfont paths + first-run prompt, `midi/model.py` + shared tempo-map utility.
2. **Audio engine v1** — `FluidPlayerBackend` behind the `AudioEngine` interface (WASAPI-first driver
   fallback chain, `silent_play_seek` behavior preserved), basic playback wired to a minimal shell UI.
   App is runnable end-to-end at this point, feature-parity-minus-notation.
3. **UI shell + widgets + slots** — `render/widgets/`, theme consolidation, `SlotManager` fixes, bars
   view, timeline, keyboard, properties — feature parity with today's app apart from traditional
   notation.
4. **Notation/transcription + sprite atlas** — `quantize.py`, `spelling.py`, glyph atlas pipeline,
   `notation/engraver.py`, traditional view rebuilt on top of it.
5. **Recording + MIDI input** — tempo-map-aware recorder, recording quantization (grid + strength,
   fixes unaligned bars from live-played timing), persistent-process device enumeration, hardware
   sustain-pedal parity, channel-remap edge-case fixes, per-device-per-channel input routing (multiple
   simultaneous hardware devices, channel-demuxed roles for combo keys+pads controllers), drum pad
   input + slot (default GM mapping, configurable per-pad note assignment).
6. **Sequencer backend** — build `SequencerBackend`, wire the `audio.backend` switch, validate
   side-by-side against the player backend (this is the milestone most likely to need iteration/spikes;
   if it runs long, it's fine for a session to stop mid-milestone — Status should record exactly what's
   left).
7. **Practice mode** — hand isolation, tempo/looping (sequencer backend), scoring, new practice slot.
8. **Polish & docs** — update `CLAUDE.md` to match the new layout (keep documentation from going stale
   again), packaging pass.

---

## Verification

- No automated test suite exists today; introduce targeted unit tests as each new pure module lands
  (`midi/quantize.py`, `midi/spelling.py`, `midi/channel_remap.py`, tempo-map conversions) since these
  are pure functions and cheap to test in isolation.
- Manual verification per milestone: run `python main.py` (or current entry point), load a sample file
  from `midiTracks/`, exercise play/pause/seek-while-playing/seek-while-paused, track mute, and — once
  the sequencer backend lands — flip `audio.backend` in settings and confirm both play the same file
  identically (this is the direct payoff of building the abstraction: a side-by-side sanity check).
- For the sprite atlas, visually diff the traditional notation view against the current renderer on a
  handful of `midiTracks/` files spanning simple and complex rhythms (rests, accidentals, beamed runs).
- For recording quantization: record an intentionally sloppy take, confirm bars line up in both sheet
  views after quantizing, and confirm a strength of 0% leaves timing untouched (regression guard against
  quantization always firing).
- For drum pads: confirm the default GM mapping plays the expected kit pieces, remap a pad, restart the
  app, and confirm the custom mapping persisted.
- For input routing: connect a MIDI keyboard and a separate drum pad controller simultaneously and
  confirm both work concurrently with independent roles; on a combo keys+pads device (e.g. Akai-style),
  confirm assigning different roles to different channels of the *same* port correctly demuxes keys vs
  pads from one connection.

---

## Appendix A — Initial `FullRewriteStatus.md`

Write this verbatim as `documentation/architecture/FullRewriteStatus.md` in `MidiVis2` during
Milestone 0, then update it at the end of every session from then on. (A copy of this initial version
also lives at `documentation/architecture/FullRewriteStatus.md` in this repo, ready to carry over.)

```markdown
# Full Rewrite Status

Repo: C:\Users\crste\git\MidiVis2
Plan: documentation/architecture/FullRewritePlan.md

## Current milestone
0 — Bootstrap (not started)

## Completed milestones
(none yet)

## In progress / partially done this session
(none yet)

## Decisions made or deviations from the plan
(none yet — record anything here where implementation diverged from FullRewritePlan.md and why, so
the plan document itself doesn't need constant editing)

## Test results from the last session
(none yet)

## Notes for the next session
Start with Milestone 0 (repo bootstrap) exactly as scoped in FullRewritePlan.md Part 4.
```

---

## Appendix B — `FullRewritePrompt.md` (reusable session-start prompt)

Write this verbatim as `documentation/architecture/FullRewritePrompt.md` in `MidiVis2` during
Milestone 0. Paste its content into a fresh context at the start of every subsequent session. (A copy
also lives at `documentation/architecture/FullRewritePrompt.md` in this repo, ready to carry over.)

```markdown
Read documentation/architecture/FullRewriteStatus.md, then documentation/architecture/FullRewritePlan.md
(both in this repo, MidiVis2). Status tells you which milestone is current and what's already done;
Plan (Part 4) defines that milestone's scope, and its earlier sections give the architecture/design
context you need to implement it correctly.

Implement exactly the current milestone — no more. If it's already partially done (Status will say so),
continue from where it left off rather than restarting. If a milestone turns out to be too large for one
session, it's fine to stop partway: just make sure Status precisely records what's done and what's left
before you stop.

Do not start work on the next milestone once the current one is finished, even if you have capacity left
— stop and let me test and commit first.

Do not commit anything yourself. Leave the working tree with uncommitted changes for me to review and
test.

The old MidiVis repo (sibling folder, path in FullRewritePlan.md Part 0) is available read-only as a
reference for exact prior behavior (e.g. the FluidSynth workarounds, GM instrument tables, sample MIDI
files) — read from it as needed, never write to it.

Before you stop, update documentation/architecture/FullRewriteStatus.md with: what was completed this
session, files touched, any deviations from FullRewritePlan.md and why, manual test steps I should run
to verify this milestone, and anything a fresh context would need to know to continue (there is no
memory carried over between sessions besides this file).
```
