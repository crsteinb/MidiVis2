# MidiVis — Claude Context

Pygame-based MIDI visualizer and player. FluidSynth handles all audio via native C API;
Pygame handles rendering and input. Runs on Windows.

> **Rewrite in progress** (see [documentation/architecture/FullRewritePlan.md](documentation/architecture/FullRewritePlan.md)
> and [FullRewriteStatus.md](documentation/architecture/FullRewriteStatus.md) for current milestone).
> Everything below this note describes the **old, pre-rewrite** architecture (single-file
> `midi_visualizer.py` + flat modules) and is kept only as reference until the rewrite reaches
> Milestone 8 (Polish & docs), which rewrites this file to match the new `main.py` + `midivis/`
> package layout. Today's actual entry point is `python main.py`.

## Running the app

```
python midi_visualizer.py
```

No build step. Entry point is `run()` at the bottom of [midi_visualizer.py](midi_visualizer.py).

## Dependencies

**Python packages** (no requirements.txt yet — install manually):
- `pygame`
- `mido`
- `python-rtmidi`

**External binaries** (not pip-installable, paths hard-coded in [midi_visualizer.py:37-38](midi_visualizer.py#L37-L38)):
- **FluidSynth** — currently v2.5.1 at `FLUIDSYNTH_BIN`. v2.5.4 is available; update the constant after upgrading.
- **SoundFont** — GeneralUser GS sf2 at `SOUNDFONT`. Required for audio output.

**User settings** persist to `%APPDATA%\MidiVis\settings.json` (created at runtime).

## Architecture

```
midi_visualizer.py   — App class (state + playback), main loop
fluid_engine.py      — FluidSynth ctypes wrapper (FluidEngine class)
midi_analyzer.py     — Pure MIDI parsing helpers (tempo, time sig, key sig)
midi_instruments.py  — GM name tables: GM_NAMES, GM_DRUM_KIT_NAMES, GM_DRUM_NOTE_NAMES + helpers
midi_input.py        — Computer keyboard + USB MIDI input, device hotplug detection
midi_recorder.py     — Live recording state machine, .work file → canonical MIDI save
settings.py          — settings.json load/save (atomic write)
utils.py             — Minimal path helpers

ui/
  dashboard.py       — Left panel (file open, track list, record arm, playback controls)
  menu_bar.py        — Top menu (File, View, Keyboard menus + submenus)
  fonts.py           — Lazy font cache (normal, normal_bold, small, measure_bars, measure_trad)
  slots/
    slot_base.py     — SlotLayout: draggable/reorderable vertical panels
    timeline.py      — Playback scrubber (30px fixed)
    keyboard.py      — Piano keyboard visualization (110px fixed)
    midi_sheet_bars.py         — Piano roll view
    midi_sheet_traditional.py  — Grand staff notation view
    properties.py    — File metadata + MIDI input status panel (MIN_H = 36)
```

### FluidSynth audio subsystem

FluidSynth runs as a **native C API integration** via ctypes — no subprocess. The wrapper lives
in [fluid_engine.py](fluid_engine.py) (`FluidEngine` class).

The synth and audio driver are created once at startup and live for the entire session. The
player is recreated per file load via `engine.load_from_mem(bytes)` (not `load_file`) because
channel remapping serialises a modified MIDI file into memory first.

- **Play:** `engine.play()` — preceded by `engine.seek(ticks)` when starting from non-zero
- **Pause:** `engine.pause()` (`fluid_player_stop`)
- **Seek:** `engine.play()` + `engine.seek(ticks)` + optional `engine.pause()` — required because
  `fluid_player_seek` only works while the player is in PLAYING state
- **Song end:** detected via `engine.get_status() == FLUID_PLAYER_DONE` in `App.update()`
- **Elapsed time:** wall-clock only — `(pygame.time.get_ticks() - _t0_ticks) / 1000.0`.
  `engine.get_tick()` is NOT used for elapsed tracking (async seek lag causes stale values).
- **Muting:** channel-level muting via a playback callback (`fluid_player_set_playback_callback`).
  The callback discards `note_on` events for muted channels. Direct `fluid_synth_noteon` calls
  (keyboard/preview) bypass the callback and are always audible.
- **SDL3 warning suppression:** `fluid_set_log_function(FLUID_WARN, noop, NULL)` called at init
  to silence driver-probe diagnostics.

No subprocess, no stdin pipe, no process crash detection thread, no Windows Job Object needed.

### MIDI channel architecture

MIDI supports 16 channels (0–15). **Channel 9 is the sole GM percussion channel** — note
numbers map to drum hits; program numbers select drum kits from Bank 128.

On file load, `_remap_channels(mid)` in `midi_visualizer.py` assigns each track a unique
channel so channel-based mute filtering is track-accurate:
- Drum tracks (any note on ch 9) → stay on ch 9
- Melodic tracks → assigned sequentially from `[0-8, 10-15]` (15-channel pool), hard-capped
- Excess melodic tracks beyond 15 share channels best-effort
- The remapped MIDI is serialised to bytes and loaded via `engine.load_from_mem()`

`App._track_channels` maps `track_id → set(channels)` and is updated by the remap.

### MIDI input

USB device enumeration runs in an isolated subprocess (`_enumerate_midi_ports` in
[midi_input.py](midi_input.py)) on a 5-second polling interval. `rtmidi.MidiIn()` holds the
Python GIL during Windows MIDI API calls; calling it on the main thread freezes the UI.

### Recording

`MidiRecorder` in [midi_recorder.py](midi_recorder.py) uses a three-state machine:
`IDLE → ARMED → RECORDING`. On arm it creates a `.work` copy of the target file. On save it
appends the buffered track and promotes `.work` to canonical via `shutil.copy2`.

**Key details:**
- `arm(path, track_name, channel_programs, ticks_per_beat, tempo_us, start_tick=0)` —
  `start_tick` offsets all recorded note ticks to the playhead position at recording start.
  Computed via `app._seconds_to_ticks(app.elapsed)` in the dashboard before arming.
- Recording auto-starts playback (`app.play()`) if the file is not already playing.
- If playback reaches `FLUID_PLAYER_DONE` while recording, the app extends `total_dur` and
  `measure_times` 4 measures ahead instead of resetting — recording continues past the file end.
- **Space key** stops an active recording (saves + reloads). When not recording, space toggles
  play/pause as usual. Logic lives in `Dashboard.stop_recording()`.
- Drum vs melodic toggle in the arm panel: melodic channels skip ch 9; drum channel locked to 9.
  Channel arrow shows `"(used by Track N)"` if the channel is already occupied.

**Live note display during recording:**
- `App._live_notes: dict` — `(note, channel) → (start_elapsed_sec, velocity)` for held notes
- `App._live_note_events: list` — completed live notes `(start_s, end_s, note, vel, '__recording__')`
- `App._on_record_note_on/off` wrapper methods feed both the live display and `MidiRecorder`
- Bars view: in-progress notes grow rightward to the playhead; completed ones rendered in
  `note_active` colour
- Traditional view: in-progress notes injected as 16th-note duration; snap to actual duration
  on release

**Recording instrument display:**
- `App._rec_preview_name: str` — always set (defaults to `gm_name(0)`); updated by
  `preview_instrument()`, reset to default by `restore_preview()` and `load()`
- Properties panel shows the name right-aligned in the collapsed bar, left of the `+/−` button
- A red circle (210, 45, 45) appears to the left of the name when state is `RECORDING`

### Key signature detection

`midi_analyzer.get_key_signature(mid)` reads the `key_signature` meta message and returns
`None` if absent (recorded files never carry one). `detect_key_signature(mid)` falls back to
pitch-class analysis: counts each of 12 pitch classes across all `note_on` events, scores all
24 keys (12 major + 12 minor) by how many of their 7 scale tones appear, and returns the
best match. `App.load()` uses `get_key_signature(mid) or detect_key_signature(mid)`.

### Settings

`settings.save()` is atomic: writes to a temp file then `os.replace()`. A crash mid-write cannot
corrupt the settings file. `settings.load()` short-circuits on zero-byte file.

### SlotLayout

`ui/slots/slot_base.py` manages the vertical panel stack (timeline → sheet → keyboard →
properties). Panels are draggable/reorderable and individually hideable via the View menu.
The flexible `sheet` slot fills remaining height after fixed-height slots are subtracted.

Properties slot collapsed height is `slot_properties.MIN_H = 36`. The `+/−` toggle button is
drawn geometrically (two rectangles) rather than rendered text, for reliable centering.

## Known issues / constraints

- **seek_preview during drag** — FluidSynth continues playing from its internal position while the
  timeline is being dragged; it only resyncs on drag release (`seek()`). This is intentional.
- **seek while paused** — `fluid_player_seek` requires PLAYING state. `App.seek()` calls
  `engine.play()` briefly before seeking and then re-pauses. Audio may click for one frame.
- **DirectSound corruption** — if audio breaks badly, `net stop/start "Windows Audio"` or a
  reboot is required. No subprocess is spawned, so hard-killing Python leaves no orphaned
  FluidSynth processes.
- **Single-tempo recording** — `MidiRecorder` uses the first tempo for tick conversion. Notes
  recorded across a tempo-change boundary may be slightly off-grid.

## Key constants (midi_visualizer.py)

| Constant | Value | Purpose |
|---|---|---|
| `WIN_W` / `WIN_H` | 1200 × 720 | Default window size |
| `LEFT_W` | 150 | Dashboard panel width |
| `FLUIDSYNTH_BIN` | (hard-coded path) | FluidSynth binary directory |
| `SOUNDFONT` | (hard-coded path) | GeneralUser GS .sf2 path |

## File dialogs

Use the tkinter implementation in `ui/dashboard.py`. ctypes and subprocess approaches were
investigated and abandoned — tkinter was working correctly, the prior issue was an unrelated
lingering Python process.

## Theme

All UI modules carry both `'dark'` and `'light'` color palettes. Theme is toggled via the
View menu and persisted in settings.

## Sample MIDI files

`midiTracks/` contains sample files (Beethoven, Undertale, Vampire Killer, etc.) for testing.
`midiTracks/testRec*.mid` are files recorded with this app (no key_signature meta — key is
detected algorithmically).
