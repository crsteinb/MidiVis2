import unittest

import mido

from midivis.midi.model import DEFAULT_TEMPO_US, NoteEvent, TempoChange, TempoMap, Timeline


class TempoMapConstantTempoTest(unittest.TestCase):
    def setUp(self):
        self.tpb = 480
        self.tempo_map = TempoMap(ticks_per_beat=self.tpb, changes=[])

    def test_matches_mido_conversions_directly(self):
        for ticks in (0, 1, 480, 960, 123456):
            expected = mido.tick2second(ticks, self.tpb, DEFAULT_TEMPO_US)
            self.assertAlmostEqual(self.tempo_map.ticks_to_seconds(ticks), expected)

    def test_roundtrip(self):
        for ticks in (0, 240, 480, 100_000):
            seconds = self.tempo_map.ticks_to_seconds(ticks)
            self.assertEqual(self.tempo_map.seconds_to_ticks(seconds), ticks)

    def test_tempo_at_tick_is_default_before_any_change(self):
        self.assertEqual(self.tempo_map.tempo_at_tick(0), DEFAULT_TEMPO_US)
        self.assertEqual(self.tempo_map.tempo_at_tick(999_999), DEFAULT_TEMPO_US)


class TempoMapMultiTempoTest(unittest.TestCase):
    '''Regression guard: must match the old App._seconds_to_ticks /
    midi_processing.build_timeline segment-walking math exactly, just computed
    via bisect instead of a linear scan.
    '''

    def setUp(self):
        self.tpb = 480
        # 120 BPM for the first 2 beats, then 90 BPM, then 150 BPM.
        self.changes = [
            TempoChange(tick=960, tempo_us=666_667),   # 90 BPM at beat 2
            TempoChange(tick=2400, tempo_us=400_000),  # 150 BPM at beat 5
        ]
        self.tempo_map = TempoMap(ticks_per_beat=self.tpb, changes=self.changes)

    def _reference_ticks_to_seconds(self, tick):
        cur_tick, cur_tempo, sec = 0, DEFAULT_TEMPO_US, 0.0
        for chg in sorted(self.changes, key=lambda c: c.tick):
            if chg.tick > tick:
                break
            sec += mido.tick2second(chg.tick - cur_tick, self.tpb, cur_tempo)
            cur_tick, cur_tempo = chg.tick, chg.tempo_us
        sec += mido.tick2second(tick - cur_tick, self.tpb, cur_tempo)
        return sec

    def test_ticks_to_seconds_matches_reference_walk(self):
        for tick in (0, 500, 960, 1500, 2400, 5000):
            self.assertAlmostEqual(
                self.tempo_map.ticks_to_seconds(tick),
                self._reference_ticks_to_seconds(tick),
                places=9,
            )

    def test_seconds_to_ticks_roundtrip_across_tempo_changes(self):
        for tick in (0, 500, 960, 961, 1500, 2400, 2401, 5000):
            seconds = self.tempo_map.ticks_to_seconds(tick)
            self.assertEqual(self.tempo_map.seconds_to_ticks(seconds), tick)

    def test_tempo_at_tick_steps_through_changes(self):
        self.assertEqual(self.tempo_map.tempo_at_tick(0), DEFAULT_TEMPO_US)
        self.assertEqual(self.tempo_map.tempo_at_tick(959), DEFAULT_TEMPO_US)
        self.assertEqual(self.tempo_map.tempo_at_tick(960), 666_667)
        self.assertEqual(self.tempo_map.tempo_at_tick(2399), 666_667)
        self.assertEqual(self.tempo_map.tempo_at_tick(2400), 400_000)


class TempoMapFromMidiTest(unittest.TestCase):
    def test_type1_gathers_tempo_across_tracks(self):
        mid = mido.MidiFile(type=1, ticks_per_beat=480)
        meta_track = mido.MidiTrack()
        meta_track.append(mido.MetaMessage('set_tempo', tempo=500_000, time=0))
        meta_track.append(mido.MetaMessage('set_tempo', tempo=400_000, time=480))
        note_track = mido.MidiTrack()
        note_track.append(mido.Message('note_on', note=60, velocity=64, time=0))
        mid.tracks.append(meta_track)
        mid.tracks.append(note_track)

        tempo_map = TempoMap.from_midi(mid)

        self.assertEqual(tempo_map.ticks_per_beat, 480)
        self.assertEqual([c.tick for c in tempo_map.changes], [0, 480])
        self.assertEqual(tempo_map.tempo_at_tick(480), 400_000)

    def test_type0_single_merged_track(self):
        mid = mido.MidiFile(type=0, ticks_per_beat=240)
        track = mido.MidiTrack()
        track.append(mido.MetaMessage('set_tempo', tempo=600_000, time=0))
        track.append(mido.Message('note_on', note=60, velocity=64, time=0))
        mid.tracks.append(track)

        tempo_map = TempoMap.from_midi(mid)

        self.assertEqual(tempo_map.tempo_at_tick(0), 600_000)


class ModelContainersTest(unittest.TestCase):
    def test_timeline_ticks_per_beat_delegates_to_tempo_map(self):
        tempo_map = TempoMap(ticks_per_beat=96, changes=[])
        timeline = Timeline(tempo_map=tempo_map, note_events=[
            NoteEvent(start_tick=0, end_tick=96, note=60, velocity=100, channel=0, track_id=0),
        ])
        self.assertEqual(timeline.ticks_per_beat, 96)
        self.assertEqual(len(timeline.note_events), 1)


if __name__ == '__main__':
    unittest.main()
