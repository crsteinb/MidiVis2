import unittest
from unittest import mock

from midivis.audio import fluid_player as fluid_player_mod
from midivis.audio import fluidsynth_ffi as ffi_mod
from midivis.audio.engine import PlayerStatus
from midivis.audio.fluid_player import FluidPlayerBackend


class _FakeFFI:
    '''Stands in for a loaded fluidsynth_ffi.FluidSynthFFI — just enough of the .fn
    table for get_status() to call player_get_status(). No real DLL/hardware needed.
    '''

    def __init__(self, raw_status):
        self.fn = {'player_get_status': lambda player: raw_status}


def _make_backend(playing: bool, raw_status: int) -> FluidPlayerBackend:
    '''Builds a FluidPlayerBackend without going through __init__ (which loads the
    real libfluidsynth-3.dll) so get_status()'s logic can be unit tested without
    FluidSynth installed.
    '''
    backend = FluidPlayerBackend.__new__(FluidPlayerBackend)
    backend._player = object()  # any truthy placeholder — get_status() only checks truthiness
    backend._playing = playing
    backend._ffi = _FakeFFI(raw_status)
    return backend


class GetStatusPauseQuirkTest(unittest.TestCase):
    '''Regression test for the "pause resets to the beginning" bug.

    fluid_player has no distinct "paused" state — only READY/PLAYING/STOPPING/DONE.
    pause()'s fluid_player_stop() settles the physical player at FLUID_PLAYER_DONE,
    identical to genuine song-end. get_status() must report READY once we've paused
    ourselves regardless of what the physical player says, or App.update()'s
    song-end-reset (get_status() == DONE -> reset position to 0) fires on the very
    next frame after any ordinary pause and snaps playback back to 0.
    '''

    def test_reports_ready_when_paused_even_if_physical_status_is_done(self):
        backend = _make_backend(playing=False, raw_status=ffi_mod.FLUID_PLAYER_DONE)
        self.assertEqual(backend.get_status(), PlayerStatus.READY)

    def test_reports_ready_when_paused_even_if_physical_status_still_playing(self):
        # Covers the instant right after pause() is called, before fluid_player's
        # internal async stop has fully taken effect.
        backend = _make_backend(playing=False, raw_status=ffi_mod.FLUID_PLAYER_PLAYING)
        self.assertEqual(backend.get_status(), PlayerStatus.READY)

    def test_reports_real_status_while_still_playing(self):
        backend = _make_backend(playing=True, raw_status=ffi_mod.FLUID_PLAYER_PLAYING)
        self.assertEqual(backend.get_status(), PlayerStatus.PLAYING)

    def test_reports_done_while_playing_when_song_actually_ends(self):
        # The case App.update()'s song-end reset is meant to catch — must still work.
        backend = _make_backend(playing=True, raw_status=ffi_mod.FLUID_PLAYER_DONE)
        self.assertEqual(backend.get_status(), PlayerStatus.DONE)

    def test_reports_ready_when_no_player_loaded(self):
        backend = FluidPlayerBackend.__new__(FluidPlayerBackend)
        backend._player = None
        backend._playing = False
        backend._ffi = None
        self.assertEqual(backend.get_status(), PlayerStatus.READY)


class SeekWithRetryTest(unittest.TestCase):
    '''Regression test for the "seek while paused does not work — resuming plays from
    the original pre-seek position" bug.

    fluid_player_seek() returns -1 (failure, no effect) for a few milliseconds right
    after fluid_player_play() — player_get_status() flips to PLAYING synchronously,
    but the internal state seek() depends on settles asynchronously on the player's
    own thread. Both seek() and _silent_play_seek() (used by play()) previously
    discarded that return code, so a seek issued right after resuming from pause
    could silently have no effect: our own elapsed-time bookkeeping (self._elapsed)
    showed the new position, but the physical player — and therefore the actual
    audio — stayed exactly where it was before the seek. Confirmed on real hardware
    via fluid_player_get_current_tick() before/after the fix.
    '''

    def _make_backend(self, fail_count: int) -> FluidPlayerBackend:
        backend = FluidPlayerBackend.__new__(FluidPlayerBackend)
        backend._player = object()
        calls = {'n': 0}

        def fake_seek(player, ticks):
            calls['n'] += 1
            return -1 if calls['n'] <= fail_count else 0

        backend._ffi = _FakeFFI(raw_status=0)
        backend._ffi.fn['player_seek'] = fake_seek
        backend._calls = calls
        return backend

    def test_retries_until_seek_succeeds(self):
        backend = self._make_backend(fail_count=5)
        with mock.patch.object(fluid_player_mod.time, 'sleep'):
            self.assertTrue(backend._seek_with_retry(1234))
        self.assertEqual(backend._calls['n'], 6)  # 5 failures + 1 success

    def test_succeeds_immediately_when_seek_works_first_try(self):
        backend = self._make_backend(fail_count=0)
        with mock.patch.object(fluid_player_mod.time, 'sleep'):
            self.assertTrue(backend._seek_with_retry(1234))
        self.assertEqual(backend._calls['n'], 1)

    def test_gives_up_after_max_attempts_instead_of_looping_forever(self):
        backend = self._make_backend(fail_count=1_000_000)  # never succeeds
        with mock.patch.object(fluid_player_mod.time, 'sleep'):
            self.assertFalse(backend._seek_with_retry(1234))
        self.assertEqual(backend._calls['n'], fluid_player_mod._SEEK_RETRY_ATTEMPTS)


if __name__ == '__main__':
    unittest.main()
