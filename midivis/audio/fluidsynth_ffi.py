'''Shared ctypes bindings to libfluidsynth.

Extracted from the old MidiVis's fluid_engine.py (the FluidEngine class hand-rolled
its own bindings inline) so both FluidPlayerBackend (this milestone) and the future
SequencerBackend (Milestone 6, Plan Part 3.1 — renders via fluid_synth_write_s16
directly instead of fluid_player) sit on one binding layer rather than each
duplicating ctypes signatures independently.
'''
from __future__ import annotations

import ctypes
import os
from ctypes import c_char_p, c_double, c_int, c_size_t, c_void_p
from dataclasses import dataclass

FLUID_PLAYER_READY = 0
FLUID_PLAYER_PLAYING = 1
FLUID_PLAYER_STOPPING = 2
FLUID_PLAYER_DONE = 3

MIDI_NOTE_ON = 0x90

# fluid_player playback callback signature: int (*)(void *data, fluid_midi_event_t *event)
MIDI_CALLBACK_TYPE = ctypes.CFUNCTYPE(c_int, c_void_p, c_void_p)

_DLL_NAME = 'libfluidsynth-3.dll'

# fluid_log level FLUID_WARN — driver-probe diagnostics like "SDL3 not initialized".
# FLUID_ERR/FLUID_PANIC are unaffected by suppressing this level.
_FLUID_WARN = 2


def _bind(lib) -> dict:
    def fn(name, argtypes, restype):
        f = getattr(lib, name)
        f.argtypes = argtypes
        f.restype = restype
        return f

    return {
        # settings
        'new_fluid_settings':    fn('new_fluid_settings',    [],                               c_void_p),
        'delete_fluid_settings': fn('delete_fluid_settings', [c_void_p],                       None),
        'setstr':                fn('fluid_settings_setstr',  [c_void_p, c_char_p, c_char_p],  c_int),
        'setint':                fn('fluid_settings_setint',  [c_void_p, c_char_p, c_int],     c_int),
        'setnum':                fn('fluid_settings_setnum',  [c_void_p, c_char_p, c_double],  c_int),
        # synth
        'new_fluid_synth':       fn('new_fluid_synth',        [c_void_p],                      c_void_p),
        'delete_fluid_synth':    fn('delete_fluid_synth',     [c_void_p],                      None),
        'sfload':                fn('fluid_synth_sfload',     [c_void_p, c_char_p, c_int],     c_int),
        'noteon':                fn('fluid_synth_noteon',     [c_void_p, c_int, c_int, c_int], c_int),
        'noteoff':               fn('fluid_synth_noteoff',    [c_void_p, c_int, c_int],        c_int),
        'cc':                    fn('fluid_synth_cc',         [c_void_p, c_int, c_int, c_int], c_int),
        'prog':                  fn('fluid_synth_program_change', [c_void_p, c_int, c_int],    c_int),
        'notes_off':             fn('fluid_synth_all_notes_off',  [c_void_p, c_int],           c_int),
        'sounds_off':            fn('fluid_synth_all_sounds_off', [c_void_p, c_int],           c_int),
        # playback callback helpers
        'event_get_type':    fn('fluid_midi_event_get_type',    [c_void_p],            c_int),
        'event_get_channel': fn('fluid_midi_event_get_channel', [c_void_p],            c_int),
        'handle_event':      fn('fluid_synth_handle_midi_event', [c_void_p, c_void_p], c_int),
        # audio driver
        'new_fluid_audio_driver':    fn('new_fluid_audio_driver',    [c_void_p, c_void_p], c_void_p),
        'delete_fluid_audio_driver': fn('delete_fluid_audio_driver', [c_void_p],           None),
        # player
        'new_fluid_player':    fn('new_fluid_player',    [c_void_p],            c_void_p),
        'delete_fluid_player': fn('delete_fluid_player', [c_void_p],            None),
        'player_add':          fn('fluid_player_add',    [c_void_p, c_char_p],  c_int),
        'player_play':         fn('fluid_player_play',   [c_void_p],            c_int),
        'player_stop':         fn('fluid_player_stop',   [c_void_p],            c_int),
        'player_seek':         fn('fluid_player_seek',   [c_void_p, c_int],     c_int),
        'player_set_loop':     fn('fluid_player_set_loop',          [c_void_p, c_int],     c_int),
        'player_add_mem':      fn('fluid_player_add_mem',
                                  [c_void_p, c_char_p, c_size_t],               c_int),
        'player_set_cb':       fn('fluid_player_set_playback_callback',
                                  [c_void_p, MIDI_CALLBACK_TYPE, c_void_p],     c_int),
        'player_get_status':   fn('fluid_player_get_status',        [c_void_p],            c_int),
        'player_get_tick':     fn('fluid_player_get_current_tick',  [c_void_p],            c_int),
        'player_get_total':    fn('fluid_player_get_total_ticks',   [c_void_p],            c_int),
    }


@dataclass
class FluidSynthFFI:
    '''Bound libfluidsynth function table plus the loaded CDLL and log-callback
    reference, both of which must stay alive for as long as the bindings are used.
    '''
    lib: ctypes.CDLL
    fn: dict
    _warn_cb: object


def load(bin_dir: str) -> FluidSynthFFI:
    '''Load libfluidsynth-3.dll from bin_dir and bind the function table.'''
    os.add_dll_directory(bin_dir)  # Python 3.8+ DLL dependency resolution on Windows
    lib = ctypes.CDLL(os.path.join(bin_dir, _DLL_NAME))
    fn = _bind(lib)

    log_cb_type = ctypes.CFUNCTYPE(None, c_int, c_char_p, c_void_p)
    warn_cb = log_cb_type(lambda lvl, msg, data: None)
    lib.fluid_set_log_function.argtypes = [c_int, log_cb_type, c_void_p]
    lib.fluid_set_log_function.restype = c_void_p
    lib.fluid_set_log_function(_FLUID_WARN, warn_cb, None)

    return FluidSynthFFI(lib=lib, fn=fn, _warn_cb=warn_cb)


def create_audio_driver(ffi: FluidSynthFFI, settings, synth,
                         drivers: tuple[str, ...] = ('wasapi', 'dsound', 'waveout')):
    '''Try each driver name in order, returning (driver_handle, driver_name) for the
    first one that initializes.

    WASAPI first: lower latency and avoids DirectSound's documented corruption
    history (the old MidiVis hard-coded dsound only — see Plan Part 2's "DirectSound
    occasionally corrupts, needs a reboot" pitfall, and CLAUDE.md's "DirectSound
    corruption" known issue). Falls back to dsound, then waveout, so a machine
    without WASAPI support still works.
    '''
    for name in drivers:
        ffi.fn['setstr'](settings, b'audio.driver', name.encode())
        driver = ffi.fn['new_fluid_audio_driver'](settings, synth)
        if driver:
            return driver, name
    raise RuntimeError(f'no audio driver initialized (tried: {", ".join(drivers)})')
