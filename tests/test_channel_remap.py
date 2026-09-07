import io
import unittest

import mido

from midivis.midi.channel_remap import DRUM_CHANNEL, remap_channels


def _track(channel, notes=(60,)):
    t = mido.MidiTrack()
    for n in notes:
        t.append(mido.Message('note_on', channel=channel, note=n, velocity=80, time=0))
        t.append(mido.Message('note_off', channel=channel, note=n, velocity=0, time=10))
    return t


def _type1_midi(tracks):
    mid = mido.MidiFile(type=1, ticks_per_beat=480)
    for t in tracks:
        mid.tracks.append(t)
    return mid


class RemapChannelsTest(unittest.TestCase):
    def test_already_unique_channels_unchanged_and_bytes_reload(self):
        mid = _type1_midi([_track(0), _track(1)])
        data, assign = remap_channels(mid)
        self.assertEqual(assign, {0: 0, 1: 1})
        reloaded = mido.MidiFile(file=io.BytesIO(data))
        self.assertEqual(reloaded.type, 1)

    def test_colliding_melodic_channels_get_unique_assignments(self):
        # Both tracks originally on channel 0 -- must be split apart.
        mid = _type1_midi([_track(0), _track(0)])
        data, assign = remap_channels(mid)
        self.assertEqual(len(set(assign.values())), 2)
        self.assertNotIn(DRUM_CHANNEL, assign.values())

        reloaded = mido.MidiFile(file=io.BytesIO(data))
        seen_channels = set()
        for i, track in enumerate(reloaded.tracks):
            chs = {m.channel for m in track if m.type == 'note_on'}
            self.assertEqual(chs, {assign[i]})
            seen_channels |= chs
        self.assertEqual(seen_channels, set(assign.values()))

    def test_drum_track_pinned_to_channel_9(self):
        mid = _type1_midi([_track(9, notes=(38,)), _track(0)])
        _data, assign = remap_channels(mid)
        self.assertEqual(assign[0], DRUM_CHANNEL)
        self.assertNotEqual(assign[1], DRUM_CHANNEL)

    def test_melodic_tracks_never_assigned_the_drum_channel(self):
        # Several melodic tracks all colliding on channel 5, plus a drum
        # track on channel 9: the melodic tracks must be split across the
        # pool without ever landing on channel 9.
        tracks = [_track(5), _track(5), _track(5), _track(9, notes=(38,))]
        mid = _type1_midi(tracks)
        _data, assign = remap_channels(mid)
        drum_tid = 3
        self.assertEqual(assign[drum_tid], DRUM_CHANNEL)
        melodic_assigned = [assign[i] for i in range(3)]
        self.assertEqual(len(set(melodic_assigned)), 3)
        self.assertNotIn(DRUM_CHANNEL, melodic_assigned)

    def test_tracks_without_notes_are_ignored(self):
        empty = mido.MidiTrack()
        empty.append(mido.MetaMessage('track_name', name='empty', time=0))
        mid = _type1_midi([_track(0), empty])
        _data, assign = remap_channels(mid)
        self.assertEqual(set(assign.keys()), {0})


if __name__ == '__main__':
    unittest.main()
