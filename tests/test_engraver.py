import unittest

from midivis.midi.model import NoteEvent, TempoMap
from midivis.notation.engraver import engrave


def _tempo_map(ticks_per_beat=480):
    return TempoMap(ticks_per_beat=ticks_per_beat)


class EngraveNotesTest(unittest.TestCase):
    def test_single_note_treble(self):
        tm = _tempo_map()
        notes = [NoteEvent(start_tick=0, end_tick=480, note=72, velocity=100, channel=0, track_id=0)]
        eng = engrave(notes, tm, (4, 4), 'C major')
        self.assertEqual(len(eng.notes), 1)
        n = eng.notes[0]
        self.assertEqual(n.staff, 'treble')
        self.assertEqual(n.note_type, 'quarter')
        self.assertFalse(n.tie_prev)
        self.assertFalse(n.tie_next)
        self.assertEqual(n.pitches[0][0], 72)

    def test_default_grid_denominator_is_32nd_note(self):
        # engrave() should snap by default (readability over raw MIDI-timing
        # accuracy) without the caller having to opt in explicitly.
        tm = _tempo_map()   # ticks_per_beat=480 -> 32nd note = 60 ticks
        notes = [NoteEvent(start_tick=5, end_tick=485, note=72, velocity=100, channel=0, track_id=0)]
        eng = engrave(notes, tm, (4, 4), 'C major')
        self.assertEqual(eng.notes[0].start_tick, 0)
        self.assertEqual(eng.notes[0].end_tick, 480)

    def test_low_note_goes_to_bass_staff(self):
        tm = _tempo_map()
        notes = [NoteEvent(0, 480, 40, 100, 0, 0)]
        eng = engrave(notes, tm, (4, 4), 'C major')
        self.assertEqual(eng.notes[0].staff, 'bass')

    def test_simultaneous_notes_form_one_chord(self):
        tm = _tempo_map()
        notes = [
            NoteEvent(0, 480, 60, 100, 0, 0),
            NoteEvent(2, 480, 64, 100, 0, 0),   # 2 ticks later -- within tolerance
            NoteEvent(0, 480, 67, 100, 0, 0),
        ]
        eng = engrave(notes, tm, (4, 4), 'C major')
        self.assertEqual(len(eng.notes), 1)
        self.assertEqual(len(eng.notes[0].pitches), 3)

    def test_key_signature_affects_spelling(self):
        tm = _tempo_map()
        notes = [NoteEvent(0, 480, 66, 100, 0, 0)]   # F#/Gb pitch class
        sharp_key = engrave(notes, tm, (4, 4), 'D major').notes[0]
        flat_key = engrave(notes, tm, (4, 4), 'F major').notes[0]
        self.assertEqual(sharp_key.pitches[0][2], 1)    # sharp
        self.assertEqual(flat_key.pitches[0][2], -1)     # flat


class TieAcrossBarlineTest(unittest.TestCase):
    def test_note_crossing_barline_splits_into_tied_segments(self):
        tm = _tempo_map(ticks_per_beat=480)   # measure = 1920 ticks in 4/4
        notes = [NoteEvent(start_tick=1800, end_tick=2400, note=60, velocity=100, channel=0, track_id=0)]
        eng = engrave(notes, tm, (4, 4), 'C major')
        self.assertEqual(len(eng.notes), 2)
        first, second = eng.notes
        self.assertEqual(first.end_tick, 1920)
        self.assertEqual(second.start_tick, 1920)
        self.assertFalse(first.tie_prev)
        self.assertTrue(first.tie_next)
        self.assertTrue(second.tie_prev)
        self.assertFalse(second.tie_next)

    def test_note_within_one_measure_is_not_tied(self):
        tm = _tempo_map()
        notes = [NoteEvent(0, 480, 60, 100, 0, 0)]
        eng = engrave(notes, tm, (4, 4), 'C major')
        self.assertEqual(len(eng.notes), 1)
        self.assertFalse(eng.notes[0].tie_prev)
        self.assertFalse(eng.notes[0].tie_next)


class RestsTest(unittest.TestCase):
    def test_gap_between_notes_produces_a_rest(self):
        tm = _tempo_map()
        notes = [
            NoteEvent(0, 480, 60, 100, 0, 0),
            NoteEvent(1920, 2400, 60, 100, 0, 0),   # gap of 1440 ticks (1.5 quarter beats)
        ]
        eng = engrave(notes, tm, (4, 4), 'C major')
        self.assertEqual(len(eng.rests), 1)
        self.assertEqual(eng.rests[0].start_tick, 480)
        self.assertEqual(eng.rests[0].end_tick, 1920)

    def test_rest_carries_the_track_id_of_its_lane(self):
        # A rest must be attributable to a track so per-track mute/visibility
        # (app.enabled_tracks) can filter it out along with that track's
        # notes -- without this, muting every track still left rests
        # rendered (a real bug: EngravedRest had no track_id at all).
        tm = _tempo_map()
        notes = [
            NoteEvent(0, 480, 60, 100, 0, 5),
            NoteEvent(1920, 2400, 60, 100, 0, 5),
        ]
        eng = engrave(notes, tm, (4, 4), 'C major')
        self.assertEqual(len(eng.rests), 1)
        self.assertEqual(eng.rests[0].track_id, 5)

    def test_no_gap_no_rest(self):
        tm = _tempo_map()
        notes = [
            NoteEvent(0, 480, 60, 100, 0, 0),
            NoteEvent(480, 960, 62, 100, 0, 0),
        ]
        eng = engrave(notes, tm, (4, 4), 'C major')
        self.assertEqual(eng.rests, [])

    def test_separate_staves_have_independent_rests(self):
        tm = _tempo_map()
        notes = [
            NoteEvent(0, 480, 72, 100, 0, 0),     # treble, then a gap
            NoteEvent(1920, 2400, 72, 100, 0, 0),
            NoteEvent(0, 2400, 40, 100, 0, 1),     # bass, continuous, no gap
        ]
        eng = engrave(notes, tm, (4, 4), 'C major')
        self.assertEqual(len(eng.rests), 1)
        self.assertEqual(eng.rests[0].staff, 'treble')


class BeamGroupsTest(unittest.TestCase):
    def test_consecutive_eighth_notes_in_one_beat_are_beamed(self):
        tm = _tempo_map(ticks_per_beat=480)
        notes = [
            NoteEvent(0, 240, 60, 100, 0, 0),
            NoteEvent(240, 480, 62, 100, 0, 0),
        ]
        eng = engrave(notes, tm, (4, 4), 'C major')
        self.assertEqual(len(eng.beam_groups), 1)
        self.assertEqual(len(eng.beam_groups[0]), 2)

    def test_single_eighth_note_is_not_beamed_alone(self):
        tm = _tempo_map(ticks_per_beat=480)
        notes = [NoteEvent(0, 240, 60, 100, 0, 0)]
        eng = engrave(notes, tm, (4, 4), 'C major')
        self.assertEqual(eng.beam_groups, [])

    def test_quarter_notes_are_never_beamed(self):
        tm = _tempo_map(ticks_per_beat=480)
        notes = [
            NoteEvent(0, 480, 60, 100, 0, 0),
            NoteEvent(480, 960, 62, 100, 0, 0),
        ]
        eng = engrave(notes, tm, (4, 4), 'C major')
        self.assertEqual(eng.beam_groups, [])


class NoteAccuracyThresholdTest(unittest.TestCase):
    '''User-requested: err on the side of sheet-music readability over exact
    MIDI timing. A note released a touch late (overlapping the next note's
    onset by a few ticks) is common real-performance noise, not an
    intentional overlap -- the traditional view should engrave it as clean,
    non-overlapping notes by snapping both onset and release onto a fixed
    grid (default: nearest 1/32 note), while an "exact timing" setting
    (grid_denominator=0) should still be honored for anyone who wants raw
    MIDI timing reflected literally.
    '''

    def test_late_release_overlapping_the_next_note_is_cleaned_up(self):
        tm = _tempo_map(ticks_per_beat=480)   # 32nd note = 60 ticks
        notes = [
            NoteEvent(5, 485, 60, 100, 0, 0),     # released 5 ticks late, overlapping note 2
            NoteEvent(480, 960, 62, 100, 0, 0),    # clean onset
        ]
        eng = engrave(notes, tm, (4, 4), 'C major')
        first, second = sorted(eng.notes, key=lambda n: n.start_tick)
        self.assertEqual(first.end_tick, 480)
        self.assertEqual(second.start_tick, 480)
        self.assertLessEqual(first.end_tick, second.start_tick)   # no overlap

    def test_grid_denominator_zero_preserves_exact_raw_timing(self):
        tm = _tempo_map(ticks_per_beat=480)
        notes = [NoteEvent(5, 485, 60, 100, 0, 0)]
        eng = engrave(notes, tm, (4, 4), 'C major', grid_denominator=0)
        self.assertEqual(eng.notes[0].start_tick, 5)
        self.assertEqual(eng.notes[0].end_tick, 485)

    def test_coarser_grid_denominator_snaps_to_16th_notes_instead(self):
        tm = _tempo_map(ticks_per_beat=480)   # 16th note = 120 ticks
        notes = [NoteEvent(10, 490, 60, 100, 0, 0)]
        eng = engrave(notes, tm, (4, 4), 'C major', grid_denominator=16)
        self.assertEqual(eng.notes[0].start_tick, 0)
        self.assertEqual(eng.notes[0].end_tick, 480)


if __name__ == '__main__':
    unittest.main()
