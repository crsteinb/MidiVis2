'''FluidPlayerBackend: FluidSynth's own fluid_player driving playback.

The known-working model from the old MidiVis (fluid_engine.py's FluidEngine),
refined per Plan Part 3.1:
- WASAPI-first audio driver fallback chain (fluidsynth_ffi.create_audio_driver)
  instead of the old hard-coded dsound-only setup.
- Elapsed-time bookkeeping (previously App._t0_ticks/pygame.time.get_ticks(), plus
  App._seconds_to_ticks doing an O(n) linear tempo-map rescan on every call) moves
  into this backend and uses the shared TempoMap (midi/model.py) instead.

silent_play_seek and the defensive callback-reregistration-after-nearly-every-call
pattern are preserved verbatim — Plan Part 3.1 calls these out explicitly as
hard-won FluidSynth behavior, not incidental code to clean up.
'''
from __future__ import annotations

import time
from ctypes import c_uint16

from midivis.audio import fluidsynth_ffi as ffi_mod
from midivis.audio.engine import PlayerStatus
from midivis.midi.model import TempoMap

_STATUS_MAP = {
    ffi_mod.FLUID_PLAYER_READY: PlayerStatus.READY,
    ffi_mod.FLUID_PLAYER_PLAYING: PlayerStatus.PLAYING,
    ffi_mod.FLUID_PLAYER_STOPPING: PlayerStatus.STOPPING,
    ffi_mod.FLUID_PLAYER_DONE: PlayerStatus.DONE,
}

# fluid_player_seek() can transiently return -1 (failure) for a few milliseconds
# right after fluid_player_play() — player_get_status() flips to PLAYING
# synchronously, but the internal state seek() depends on settles asynchronously on
# the player's own thread. Observed needing ~10-30ms / 9-26 attempts in practice on
# this machine; the cap here is a generous multiple of that.
_SEEK_RETRY_ATTEMPTS = 150
_SEEK_RETRY_DELAY_S = 0.001


class FluidPlayerBackend:
    def __init__(self, bin_dir: str, soundfont: str) -> None:
        self._ffi = ffi_mod.load(bin_dir)
        f = self._ffi.fn

        self._settings = f['new_fluid_settings']()
        if not self._settings:
            raise RuntimeError('fluid_settings creation failed')
        f['setint'](self._settings, b'audio.periods', 8)
        f['setint'](self._settings, b'audio.period-size', 512)

        self._synth = f['new_fluid_synth'](self._settings)
        if not self._synth:
            raise RuntimeError('fluid_synth creation failed')

        sfid = f['sfload'](self._synth, soundfont.encode(), 1)
        if sfid == -1:
            raise RuntimeError(f'sfload failed: {soundfont}')
        self._sfid = sfid

        self._adriver, self.driver_name = ffi_mod.create_audio_driver(
            self._ffi, self._settings, self._synth)
        print(f'[FluidPlayerBackend] audio driver: {self.driver_name}')

        self._player = None
        self._tempo_map: TempoMap | None = None

        # 16-bit bitmask: bit N set means channel N is muted (note_on discarded by
        # the playback callback below). Written from the main thread, read from the
        # player callback thread — a 16-bit read/write is effectively atomic on
        # x86/x64, so no lock is needed.
        self._muted = c_uint16(0)

        muted = self._muted

        @ffi_mod.MIDI_CALLBACK_TYPE
        def _cb(data, event):
            if f['event_get_type'](event) == ffi_mod.MIDI_NOTE_ON:
                ch = f['event_get_channel'](event)
                if (muted.value >> ch) & 1:
                    return 0  # discard note_on for muted channel
            return f['handle_event'](self._synth, event)

        self._midi_cb = _cb  # keep alive — ctypes GCs unreferenced callbacks

        self._playing = False
        self._elapsed = 0.0             # cached elapsed seconds while paused/stopped
        self._t0: float | None = None   # perf_counter() origin while playing

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load(self, midi_bytes: bytes, tempo_map: TempoMap) -> None:
        self._destroy_player()
        f = self._ffi.fn
        self._player = f['new_fluid_player'](self._synth)
        if not self._player:
            raise RuntimeError('fluid_player creation failed')
        f['player_add_mem'](self._player, midi_bytes, len(midi_bytes))
        f['player_set_loop'](self._player, 1)  # 1 = play once
        f['player_set_cb'](self._player, self._midi_cb, None)
        self._tempo_map = tempo_map
        self._playing = False
        self._elapsed = 0.0
        self._t0 = None

    # ------------------------------------------------------------------
    # Playback control
    # ------------------------------------------------------------------

    def play(self) -> None:
        if not self._player:
            return
        ticks = self._tempo_map.seconds_to_ticks(self._elapsed) if self._tempo_map else 0
        self._silent_play_seek(ticks)
        f = self._ffi.fn
        f['player_play'](self._player)  # ensures PLAYING state; no-op if already there
        f['player_set_cb'](self._player, self._midi_cb, None)
        self._t0 = time.perf_counter() - self._elapsed
        self._playing = True

    def pause(self) -> None:
        if not self._player:
            return
        self._elapsed = self.get_clock_seconds()
        self._ffi.fn['player_stop'](self._player)
        self._playing = False
        self._t0 = None

    def stop(self) -> None:
        '''Reset to a stopped state at position 0 — Python-side bookkeeping only.

        Deliberately does not touch the physical fluid_player. The actual reset
        happens safely inside the next play() call via silent_play_seek(0); calling
        fluid_player_seek directly here (on what may be a DONE player) would reopen
        the exact race silent_play_seek exists to close. Mirrors the old App's
        song-end handling, which was also a pure Python-state reset
        (App._reset_playback()) deferred to the next play().
        '''
        self._playing = False
        self._t0 = None
        self._elapsed = 0.0

    def seek(self, seconds: float) -> None:
        self._elapsed = max(0.0, seconds)
        if not self._player:
            return
        ticks = self._tempo_map.seconds_to_ticks(self._elapsed) if self._tempo_map else 0
        f = self._ffi.fn
        was_playing = self._playing
        # fluid_player_seek is only valid while PLAYING — briefly enter that state,
        # then re-stop if the caller wasn't already playing. This can let a frame of
        # audio from the pre-seek position leak through (CLAUDE.md's documented
        # "seek while paused: audio may click for one frame" known issue) — accepted
        # tradeoff, not something silent_play_seek is used for here (that's reserved
        # for play(), the case that was actually causing audible glitches).
        f['player_play'](self._player)
        f['player_set_cb'](self._player, self._midi_cb, None)
        if not self._seek_with_retry(ticks):
            print(f'[FluidPlayerBackend] seek to tick {ticks} did not take effect '
                  f'after {_SEEK_RETRY_ATTEMPTS} attempts')
        f['player_set_cb'](self._player, self._midi_cb, None)
        if was_playing:
            self._t0 = time.perf_counter() - self._elapsed
        else:
            f['player_stop'](self._player)

    def _silent_play_seek(self, ticks: int) -> None:
        '''Play + seek with all channels muted during the race window.

        fluid_player_play() on a DONE/READY player restarts from tick 0. Between
        play() and the async seek() taking effect, notes from tick 0 would sound on
        unmuted channels. Muting everything first makes the callback discard every
        note_on during that window; sounds_off cuts anything that leaked through
        anyway; mute state is restored after.
        '''
        if not self._player:
            return
        f = self._ffi.fn
        saved = self._muted.value
        self._muted.value = 0xFFFF
        f['player_play'](self._player)
        f['player_set_cb'](self._player, self._midi_cb, None)
        if not self._seek_with_retry(ticks):
            print(f'[FluidPlayerBackend] seek to tick {ticks} did not take effect '
                  f'after {_SEEK_RETRY_ATTEMPTS} attempts')
        f['player_set_cb'](self._player, self._midi_cb, None)
        for ch in range(16):
            f['sounds_off'](self._synth, ch)
        self._muted.value = saved

    def _seek_with_retry(self, ticks: int) -> bool:
        '''fluid_player_seek() returns -1 (and has no effect) for a few milliseconds
        right after fluid_player_play() — see _SEEK_RETRY_ATTEMPTS above. Both
        seek() and _silent_play_seek() previously discarded this return code, so a
        seek issued right after resuming from pause could silently fail: our own
        elapsed-time bookkeeping (self._elapsed) would show the new position, but
        the physical player — and therefore the actual audio — stayed wherever it
        was before the seek. That's the exact bug this retry loop closes.
        '''
        f = self._ffi.fn
        for _ in range(_SEEK_RETRY_ATTEMPTS):
            if f['player_seek'](self._player, int(ticks)) == 0:
                return True
            time.sleep(_SEEK_RETRY_DELAY_S)
        return False

    # ------------------------------------------------------------------
    # Position / status
    # ------------------------------------------------------------------

    def get_clock_seconds(self) -> float:
        '''Authoritative elapsed time — wall-clock, not derived from FluidSynth's own
        tick counter. fluid_player_get_current_tick() lags behind async seeks, so
        using it would reintroduce the desync the old app avoided by staying
        wall-clock-only. This is a known, documented property of this backend (Plan
        Part 3.1) rather than a hidden gotcha: SequencerBackend (Milestone 6) is what
        finally gets a true audio-derived clock (samples rendered / sample rate).
        '''
        if self._playing and self._t0 is not None:
            return time.perf_counter() - self._t0
        return self._elapsed

    def get_status(self) -> PlayerStatus:
        '''Reports READY whenever we've paused/stopped ourselves, regardless of what
        the physical fluid_player object is doing — only consults the real player
        status while self._playing (our own intent flag) is still True.

        fluid_player has no distinct "paused" state: pause()'s fluid_player_stop()
        settles the physical player at FLUID_PLAYER_DONE, indistinguishable from the
        song actually finishing. Without this guard, App.update()'s "if DONE, reset
        position to 0" song-end detection would fire on the very next frame after
        every ordinary pause, snapping playback back to the start.
        '''
        if not self._player or not self._playing:
            return PlayerStatus.READY
        return _STATUS_MAP.get(self._ffi.fn['player_get_status'](self._player), PlayerStatus.READY)

    # ------------------------------------------------------------------
    # Muting
    # ------------------------------------------------------------------

    def set_channel_muted(self, channel: int, muted: bool) -> None:
        '''Mute/unmute a channel in the playback callback filter.

        Muting discards incoming note_on events from the player before they reach
        the synth. Keyboard/preview notes use note_on() directly and are unaffected.
        When muting, any currently-sounding notes on that channel are cut immediately.
        '''
        if muted:
            self._muted.value |= (1 << channel)
            self._ffi.fn['sounds_off'](self._synth, channel)
        else:
            self._muted.value &= ~(1 << channel)

    # ------------------------------------------------------------------
    # MIDI synthesis passthrough (keyboard/preview — bypasses the player + muting)
    # ------------------------------------------------------------------

    def note_on(self, channel: int, note: int, velocity: int) -> None:
        self._ffi.fn['noteon'](self._synth, channel, note, velocity)

    def note_off(self, channel: int, note: int) -> None:
        self._ffi.fn['noteoff'](self._synth, channel, note)

    def cc(self, channel: int, ctrl: int, value: int) -> None:
        self._ffi.fn['cc'](self._synth, channel, ctrl, value)

    def program_change(self, channel: int, program: int) -> None:
        self._ffi.fn['prog'](self._synth, channel, program)

    def all_notes_off(self, channel: int) -> None:
        self._ffi.fn['notes_off'](self._synth, channel)

    def all_sounds_off(self, channel: int) -> None:
        self._ffi.fn['sounds_off'](self._synth, channel)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _destroy_player(self) -> None:
        if self._player:
            self._ffi.fn['player_stop'](self._player)
            self._ffi.fn['delete_fluid_player'](self._player)
            self._player = None

    def shutdown(self) -> None:
        self._destroy_player()
        f = self._ffi.fn
        if self._adriver:
            f['delete_fluid_audio_driver'](self._adriver)
            self._adriver = None
        if self._synth:
            f['delete_fluid_synth'](self._synth)
            self._synth = None
        if self._settings:
            f['delete_fluid_settings'](self._settings)
            self._settings = None
