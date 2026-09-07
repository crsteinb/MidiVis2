import unittest

import mido

from midivis.midi.load import (
    build_measure_times, get_instruments, get_track_channels, get_track_names, load_timeline,
)
from midivis.midi.model import TempoMap


def _type1_midi(tracks, ticks_per_beat=480):
    mid = mido.MidiFile(type=1, ticks_per_beat=ticks_per_beat)
    for t in tracks:
        mid.tracks.append(t)
    return mid


class LoadTimelineTest(unittest.TestCase):
    def test_simple_note_becomes_one_note_event(self):
        t = mido.MidiTrack([
            mido.Message('note_on', channel=0, note=60, velocity=90, time=0),
            mido.Message('note_off', channel=0, note=60, velocity=0, time=480),
        ])
        mid = _type1_midi([t])
        tempo_map = TempoMap.from_midi(mid)
        timeline = load_timeline(mid, tempo_map)

        self.assertEqual(len(timeline.note_events), 1)
        ne = timeline.note_events[0]
        self.assertEqual((ne.start_tick, ne.end_tick, ne.note, ne.velocity, ne.channel, ne.track_id),
                          (0, 480, 60, 90, 0, 0))

    def test_sustain_pedal_extends_note_past_release(self):
        # Note released at tick 100 while the pedal is down should keep
        # sounding until the pedal lifts at tick 300, not end at tick 100.
        t = mido.MidiTrack([
            mido.Message('control_change', channel=0, control=64, value=127, time=0),
            mido.Message('note_on', channel=0, note=60, velocity=90, time=0),
            mido.Message('note_off', channel=0, note=60, velocity=0, time=100),
            mido.Message('control_change', channel=0, control=64, value=0, time=200),
        ])
        mid = _type1_midi([t])
        tempo_map = TempoMap.from_midi(mid)
        timeline = load_timeline(mid, tempo_map)

        self.assertEqual(len(timeline.note_events), 1)
        ne = timeline.note_events[0]
        self.assertEqual(ne.start_tick, 0)
        self.assertEqual(ne.end_tick, 300)

    def test_note_without_note_off_extends_to_last_event(self):
        t = mido.MidiTrack([
            mido.Message('note_on', channel=0, note=60, velocity=90, time=0),
            mido.Message('note_on', channel=0, note=64, velocity=90, time=100),
            mido.Message('note_off', channel=0, note=64, velocity=0, time=100),
        ])
        mid = _type1_midi([t])
        tempo_map = TempoMap.from_midi(mid)
        timeline = load_timeline(mid, tempo_map)

        unterminated = next(ne for ne in timeline.note_events if ne.note == 60)
        self.assertGreaterEqual(unterminated.end_tick, 200)

    def test_overlapping_same_note_pairs_in_order(self):
        # Two overlapping note_on/note_off pairs for the same pitch should
        # pair up FIFO (first on with first off), not collapse into one.
        t = mido.MidiTrack([
            mido.Message('note_on', channel=0, note=60, velocity=90, time=0),
            mido.Message('note_on', channel=0, note=60, velocity=90, time=50),
            mido.Message('note_off', channel=0, note=60, velocity=0, time=50),
            mido.Message('note_off', channel=0, note=60, velocity=0, time=50),
        ])
        mid = _type1_midi([t])
        tempo_map = TempoMap.from_midi(mid)
        timeline = load_timeline(mid, tempo_map)
        self.assertEqual(len(timeline.note_events), 2)
        starts = sorted(ne.start_tick for ne in timeline.note_events)
        self.assertEqual(starts, [0, 50])


class TrackMetadataTest(unittest.TestCase):
    def test_get_track_names_uses_track_name_meta_or_fallback(self):
        named = mido.MidiTrack([
            mido.MetaMessage('track_name', name='Melody', time=0),
            mido.Message('note_on', channel=0, note=60, velocity=90, time=0),
        ])
        unnamed = mido.MidiTrack([
            mido.Message('note_on', channel=1, note=62, velocity=90, time=0),
        ])
        mid = _type1_midi([named, unnamed])
        names = get_track_names(mid)
        self.assertEqual(names, {0: 'Melody', 1: 'Track 1'})

    def test_get_track_names_ignores_note_free_tracks(self):
        meta_only = mido.MidiTrack([mido.MetaMessage('track_name', name='Empty', time=0)])
        mid = _type1_midi([meta_only])
        self.assertEqual(get_track_names(mid), {})

    def test_get_track_channels(self):
        t = mido.MidiTrack([
            mido.Message('note_on', channel=3, note=60, velocity=90, time=0),
            mido.Message('note_on', channel=5, note=61, velocity=90, time=0),
        ])
        mid = _type1_midi([t])
        self.assertEqual(get_track_channels(mid), {0: {3, 5}})

    def test_get_instruments(self):
        t = mido.MidiTrack([
            mido.Message('program_change', channel=0, program=40, time=0),
            mido.Message('note_on', channel=0, note=60, velocity=90, time=0),
        ])
        mid = _type1_midi([t])
        self.assertEqual(get_instruments(mid), {0: [40]})


class BuildMeasureTimesTest(unittest.TestCase):
    def test_covers_total_duration_plus_buffer(self):
        # 120 BPM, 4/4 -> 2s per measure. 10s of audio should yield at least
        # ceil(10/2) measures, plus the documented +2 buffer.
        measures = build_measure_times(bpm=120.0, sig_num=4, total=10.0)
        self.assertGreaterEqual(measures[-1][1], 10.0)
        self.assertEqual(measures[0], (0, 0.0))
        # Indices are contiguous starting at 0.
        self.assertEqual([m[0] for m in measures], list(range(len(measures))))


if __name__ == '__main__':
    unittest.main()
