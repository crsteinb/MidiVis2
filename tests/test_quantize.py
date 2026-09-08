import unittest

from midivis.midi.quantize import (
    classify_duration, measure_ticks, quantize_duration_ticks, snap_note_span, snap_tick,
    split_across_barlines)


class ClassifyDurationTest(unittest.TestCase):
    def test_exact_base_types(self):
        self.assertEqual(classify_duration(4.0).note_type, 'whole')
        self.assertEqual(classify_duration(2.0).note_type, 'half')
        self.assertEqual(classify_duration(1.0).note_type, 'quarter')
        self.assertEqual(classify_duration(0.5).note_type, 'eighth')
        self.assertEqual(classify_duration(0.25).note_type, 'sixteenth')

    def test_dotted_quarter(self):
        dc = classify_duration(1.5)
        self.assertEqual(dc.note_type, 'quarter')
        self.assertEqual(dc.dots, 1)
        self.assertIsNone(dc.tuplet)

    def test_dots_are_capped_at_one_even_for_an_exact_double_dot_value(self):
        # 3.5 beats is the exact value of a double-dotted half -- but dots
        # are deliberately capped at one (see quantize.py's module comment:
        # double-dots are rare in practice and this exact-looking value is
        # usually just an imprecisely-timed whole/dotted-half in real MIDI),
        # so the nearest *allowed* candidate wins instead.
        dc = classify_duration(3.5)
        self.assertLessEqual(dc.dots, 1)
        self.assertEqual(dc.note_type, 'whole')
        self.assertEqual(dc.dots, 0)

    def test_eighth_note_triplet(self):
        dc = classify_duration(1.0 / 3.0)
        self.assertEqual(dc.note_type, 'eighth')
        self.assertEqual(dc.tuplet, (3, 2))
        self.assertEqual(dc.dots, 0)

    def test_slightly_off_duration_snaps_to_nearest(self):
        # A hair short of an eighth note shouldn't get pulled toward the
        # sixteenth just because the absolute beat delta is small.
        dc = classify_duration(0.48)
        self.assertEqual(dc.note_type, 'eighth')

    def test_zero_or_negative_duration_does_not_crash(self):
        dc = classify_duration(0.0)
        self.assertIsInstance(dc.note_type, str)


class SnapTickTest(unittest.TestCase):
    def test_snaps_to_nearest_32nd_note_by_default(self):
        # tpb=96 -> a 32nd note is 96*4/32 = 12 ticks.
        self.assertEqual(snap_tick(5, ticks_per_beat=96), 0)
        self.assertEqual(snap_tick(7, ticks_per_beat=96), 12)
        self.assertEqual(snap_tick(12, ticks_per_beat=96), 12)

    def test_coarser_grid_snaps_further(self):
        # 16th-note grid: step = 96*4/16 = 24 ticks.
        self.assertEqual(snap_tick(20, ticks_per_beat=96, grid_denominator=16), 24)

    def test_zero_denominator_disables_snapping(self):
        self.assertEqual(snap_tick(1234567, ticks_per_beat=96, grid_denominator=0), 1234567)


class SnapNoteSpanTest(unittest.TestCase):
    def test_late_release_is_pulled_back_onto_the_grid(self):
        # A note that should end cleanly at tick 96 (start of the next grid
        # point) but was released a few ticks late in the real performance.
        start, end = snap_note_span(0, 100, ticks_per_beat=96)
        self.assertEqual((start, end), (0, 96))

    def test_early_overlapping_onset_is_pulled_back_onto_the_grid(self):
        # The exact "minor overlap" scenario reported: one note's release
        # trails a few ticks past the next note's (early) onset. Snapping
        # both independently removes the overlap instead of preserving it.
        first_start, first_end = snap_note_span(0, 100, ticks_per_beat=96)
        second_start, second_end = snap_note_span(92, 192, ticks_per_beat=96)
        self.assertEqual((first_start, first_end), (0, 96))
        self.assertEqual((second_start, second_end), (96, 192))
        self.assertLessEqual(first_end, second_start)   # no overlap survives

    def test_degenerate_same_grid_point_gets_a_minimum_one_step_duration(self):
        # Both ends snapping to the same point would otherwise collapse the
        # note to zero length.
        start, end = snap_note_span(1, 5, ticks_per_beat=96)   # both round to 0
        self.assertGreater(end, start)

    def test_zero_denominator_disables_snapping(self):
        self.assertEqual(snap_note_span(5, 103, ticks_per_beat=96, grid_denominator=0), (5, 103))


class QuantizeDurationTicksTest(unittest.TestCase):
    def test_slightly_short_duration_snaps_up_to_clean_eighth(self):
        # A "performed" eighth note a few ticks short of exact (common in
        # real, non-programmatically-quantized files) should snap to a
        # clean eighth, not misclassify as some odd dotted value.
        for raw in (80, 83, 88, 92, 99):
            snapped = quantize_duration_ticks(raw, ticks_per_beat=192)
            self.assertEqual(snapped, 96)   # eighth note = ticks_per_beat/2

    def test_exact_grid_value_is_unchanged(self):
        self.assertEqual(quantize_duration_ticks(96, 192), 96)

    def test_snapping_feeds_a_clean_classification(self):
        q = quantize_duration_ticks(88, ticks_per_beat=192)
        dc = classify_duration(q / 192)
        self.assertEqual(dc.note_type, 'eighth')
        self.assertEqual(dc.dots, 0)


class MeasureTicksTest(unittest.TestCase):
    def test_common_time(self):
        self.assertEqual(measure_ticks(480, (4, 4)), 1920)

    def test_three_four(self):
        self.assertEqual(measure_ticks(480, (3, 4)), 1440)

    def test_six_eight(self):
        self.assertEqual(measure_ticks(480, (6, 8)), 1440)


class SplitAcrossBarlinesTest(unittest.TestCase):
    def test_note_within_one_measure_is_not_split(self):
        segs = split_across_barlines(100, 500, 480, (4, 4))
        self.assertEqual(segs, [(100, 500)])

    def test_note_crossing_one_barline_splits_in_two(self):
        # Measure length 1920; note starts at 1800, ends at 2200 (crosses the
        # barline at 1920).
        segs = split_across_barlines(1800, 2200, 480, (4, 4))
        self.assertEqual(segs, [(1800, 1920), (1920, 2200)])

    def test_note_spanning_multiple_measures_produces_one_segment_per_measure(self):
        segs = split_across_barlines(0, 1920 * 3, 480, (4, 4))
        self.assertEqual(segs, [(0, 1920), (1920, 3840), (3840, 5760)])

    def test_segments_are_contiguous_and_cover_the_full_range(self):
        segs = split_across_barlines(1000, 5000, 480, (4, 4))
        self.assertEqual(segs[0][0], 1000)
        self.assertEqual(segs[-1][1], 5000)
        for (_, end), (start2, _) in zip(segs, segs[1:]):
            self.assertEqual(end, start2)


if __name__ == '__main__':
    unittest.main()
