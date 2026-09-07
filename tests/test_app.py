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
        self.muted: dict[int, bool] = {}
        self.notes_on: list[tuple[int, int]] = []
        self.notes_off: list[tuple[int, int]] = []

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

    def set_channel_muted(self, channel, muted):
        self.muted[channel] = muted

    def note_on(self, channel, note, velocity):
        self.notes_on.append((channel, note))

    def note_off(self, channel, note):
        self.notes_off.append((channel, note))

    def cc(self, channel, ctrl, value):
        pass

    def program_change(self, channel, program):
        pass

    def all_notes_off(self, channel):
        pass

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


class AppTrackListTest(unittest.TestCase):
    def setUp(self):
        self.engine = _StubEngine()
        self.app = App(self.engine)
        self.app.load(_SAMPLE)

    def test_load_populates_track_metadata(self):
        self.assertTrue(self.app.tracks)
        self.assertEqual(self.app.enabled_tracks, set(self.app.tracks.keys()))
        self.assertEqual(self.app.note_events, self.app._all_note_events)

    def test_toggle_track_filters_note_events_and_mutes_channels(self):
        track_id = next(iter(self.app.tracks))
        channels = self.app.track_channels.get(track_id, set())

        self.app.toggle_track(track_id)

        self.assertNotIn(track_id, self.app.enabled_tracks)
        self.assertTrue(all(e[4] != track_id for e in self.app.note_events))
        for ch in channels:
            # Muted unless another still-enabled track shares the channel.
            still_used = any(ch in self.app.track_channels.get(t, set())
                              for t in self.app.enabled_tracks)
            self.assertEqual(self.engine.muted.get(ch, False), not still_used)

        self.app.toggle_track(track_id)
        self.assertIn(track_id, self.app.enabled_tracks)
        for ch in channels:
            self.assertFalse(self.engine.muted.get(ch, True))

    def test_set_all_tracks_false_mutes_every_channel(self):
        self.app.set_all_tracks(False)
        self.assertEqual(self.app.enabled_tracks, set())
        self.assertEqual(self.app.note_events, [])
        all_channels = {ch for chs in self.app.track_channels.values() for ch in chs}
        for ch in all_channels:
            self.assertTrue(self.engine.muted.get(ch, False))


class AppSeekPreviewTest(unittest.TestCase):
    def setUp(self):
        self.engine = _StubEngine()
        self.app = App(self.engine)
        self.app.load(_SAMPLE)

    def test_seek_preview_does_not_touch_engine(self):
        self.app.seek_preview(1.0)
        self.assertEqual(self.app.elapsed, 1.0)
        self.assertEqual(self.engine.seeks, [])

    def test_seek_commits_preview_and_clears_it(self):
        self.app.seek_preview(1.0)
        self.app.seek(2.0)
        self.assertEqual(self.engine.seeks[-1], 2.0)
        self.assertEqual(self.app.elapsed, 2.0)   # now reads engine.clock, not the preview


class AppKeyboardPassthroughTest(unittest.TestCase):
    def test_kb_note_on_off_bypass_player_and_track_kb_notes(self):
        engine = _StubEngine()
        app = App(engine)
        app.kb_note_on(60)
        self.assertIn(60, app.kb_notes)
        self.assertIn((0, 60), engine.notes_on)
        app.kb_note_off(60)
        self.assertNotIn(60, app.kb_notes)
        self.assertIn((0, 60), engine.notes_off)


if __name__ == '__main__':
    unittest.main()
