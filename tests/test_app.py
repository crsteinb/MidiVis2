import os
import unittest

from midivis.app import App
from midivis.audio.engine import PlayerStatus

_SAMPLE = os.path.join(os.path.dirname(__file__), '..', 'midiTracks', 'twinkle.mid')


class _StubEngine:
    '''Minimal AudioEngine stand-in — exercises App's delegation without touching
    real FluidSynth/hardware, which unit tests shouldn't depend on.
    '''

    def __init__(self):
        self.loaded_bytes = None
        self.tempo_map = None
        self.status = PlayerStatus.READY
        self.clock = 0.0
        self.seeks = []

    def load(self, midi_bytes, tempo_map):
        self.loaded_bytes = midi_bytes
        self.tempo_map = tempo_map
        self.status = PlayerStatus.READY
        self.clock = 0.0

    def play(self):
        self.status = PlayerStatus.PLAYING

    def pause(self):
        self.status = PlayerStatus.READY

    def stop(self):
        self.status = PlayerStatus.READY
        self.clock = 0.0

    def seek(self, seconds):
        self.seeks.append(seconds)
        self.clock = seconds

    def get_clock_seconds(self):
        return self.clock

    def get_status(self):
        return self.status

    def shutdown(self):
        self.status = PlayerStatus.READY


class AppWithoutEngineTest(unittest.TestCase):
    '''Loading/inspecting metadata must not require a working audio engine — e.g.
    FluidSynth failed to initialize but the app should still show file info.
    '''

    def test_load_succeeds_and_elapsed_stays_zero(self):
        app = App(engine=None)
        self.assertTrue(app.load(_SAMPLE))
        self.assertTrue(app.loaded)
        self.assertEqual(app.title, 'twinkle.mid')
        self.assertGreater(app.total_dur, 0)
        self.assertEqual(app.elapsed, 0.0)
        self.assertFalse(app.playing)

    def test_play_pause_seek_are_no_ops(self):
        app = App(engine=None)
        app.load(_SAMPLE)
        app.play()
        app.pause()
        app.seek(5.0)
        self.assertFalse(app.playing)


class AppWithStubEngineTest(unittest.TestCase):
    def setUp(self):
        self.engine = _StubEngine()
        self.app = App(self.engine)
        self.app.load(_SAMPLE)

    def test_load_forwards_bytes_and_tempo_map(self):
        self.assertIsNotNone(self.engine.loaded_bytes)
        self.assertIs(self.engine.tempo_map, self.app.tempo_map)

    def test_play_pause_delegate_to_engine(self):
        self.app.play()
        self.assertTrue(self.app.playing)
        self.app.pause()
        self.assertFalse(self.app.playing)

    def test_seek_clamps_to_total_duration(self):
        self.app.seek(self.app.total_dur + 100)
        self.assertEqual(self.engine.seeks[-1], self.app.total_dur)

    def test_seek_clamps_negative_to_zero(self):
        self.app.seek(-5.0)
        self.assertEqual(self.engine.seeks[-1], 0.0)

    def test_update_resets_on_done(self):
        self.app.play()
        self.engine.status = PlayerStatus.DONE
        self.engine.clock = self.app.total_dur
        self.app.update()
        self.assertEqual(self.engine.get_status(), PlayerStatus.READY)
        self.assertEqual(self.app.elapsed, 0.0)

    def test_shutdown_clears_engine(self):
        self.app.shutdown()
        self.assertIsNone(self.app.engine)


if __name__ == '__main__':
    unittest.main()
