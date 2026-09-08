'''Regression test for a real bug: the traditional view culled notes/rests
from position computation (not just drawing) using a fixed 200px margin
beyond the visible edges. A tied note's partner segment can be up to one
full measure away in time (quantize.split_across_barlines splits ties at
measure boundaries), and at high zoom one measure can span far more than
200px on screen even though it's the very next segment -- so the tie's
second half fell outside the margin and the tie vanished while the first
note (and its tie arc) were still visible. Reported by the user as ties
"getting culled too soon", "not appearing soon enough", and "popping in and
out while still on screen" -- all symptoms of the same margin being too
small relative to the current zoom level.
'''
import unittest

from midivis.render.slots.traditional import _visibility_margin


class VisibilityMarginTest(unittest.TestCase):
    def test_floors_at_200px_for_zoomed_out_or_fast_tempo_views(self):
        # A tiny measure-in-pixels shouldn't shrink the margin below the
        # old fixed value -- there also needs to be *some* buffer for
        # smooth scroll-in regardless of zoom.
        self.assertEqual(_visibility_margin(measure_dur=2.0, pps=10.0), 200)

    def test_grows_to_one_full_measure_at_high_zoom(self):
        # This is the exact shape of the reported bug: at high zoom, one
        # measure's pixel width comfortably exceeds the old fixed 200px,
        # so the margin must grow to match or a tied note's partner segment
        # (up to one measure away) gets culled while still relevant.
        measure_dur, pps = 2.0, 1200.0   # one measure = 2400px
        margin = _visibility_margin(measure_dur, pps)
        self.assertEqual(margin, 2400)
        self.assertGreater(margin, 200)

    def test_margin_covers_a_full_measure_so_both_tie_segments_are_included(self):
        # A tied note's two segments are separated by at most one measure
        # of screen-space (by construction, since ties only split at
        # measure boundaries) -- the margin must be at least that large so
        # a segment sitting right at the visible edge always has its
        # measure-away partner's position computed too.
        measure_dur, pps = 1.5, 900.0
        one_measure_px = measure_dur * pps
        self.assertGreaterEqual(_visibility_margin(measure_dur, pps), one_measure_px)


if __name__ == '__main__':
    unittest.main()
