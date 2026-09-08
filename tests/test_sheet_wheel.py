'''SheetSlot owns ctrl+wheel zoom / wheel scroll / horizontal-wheel seek —
moved here from a main.py special case that bypassed the slot handle_event
contract entirely and, as a real bug, always wrote app.bars_scroll even when
the traditional view (which reads app.trad_scroll) was active. These tests
guard the behavior and the specific regression fix.
'''
import os
import unittest

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')

import pygame

from midivis.render.slots.sheet_slot import SheetSlot

pygame.init()


class _FakeApp:
    def __init__(self, view='bars'):
        self.loaded = True
        self.view = view
        self.bpm = 120.0
        self.sheet_zoom = 1.0
        self.bars_scroll = 0.5
        self.trad_scroll = 0.5


class _mods:
    '''Context manager faking pygame.key.get_mods() for the duration of a
    wheel event, since SheetSlot reads live modifier state (same pattern as
    test_keyboard_slot.py).
    '''

    def __init__(self, mods):
        self._mods = mods
        self._real = None

    def __enter__(self):
        self._real = pygame.key.get_mods
        pygame.key.get_mods = lambda: self._mods

    def __exit__(self, *exc):
        pygame.key.get_mods = self._real


class _mouse_at:
    '''Context manager faking pygame.mouse.get_pos(), since MOUSEWHEEL events
    carry no `pos` of their own.
    '''

    def __init__(self, pos):
        self._pos = pos
        self._real = None

    def __enter__(self):
        self._real = pygame.mouse.get_pos
        pygame.mouse.get_pos = lambda: self._pos

    def __exit__(self, *exc):
        pygame.mouse.get_pos = self._real


def _wheel(x=0, y=0):
    return pygame.event.Event(pygame.MOUSEWHEEL, x=x, y=y)


class SheetWheelTest(unittest.TestCase):
    def setUp(self):
        self.slot = SheetSlot()
        self.rect = pygame.Rect(0, 0, 800, 600)
        self.inside = self.rect.center
        self.outside = (self.rect.right + 50, self.rect.bottom + 50)

    def test_ctrl_wheel_zooms_in(self):
        app = _FakeApp()
        with _mouse_at(self.inside), _mods(pygame.KMOD_CTRL):
            self.slot.handle_event(_wheel(y=1), self.rect, app)
        self.assertAlmostEqual(app.sheet_zoom, 1.15)

    def test_ctrl_wheel_zooms_out_and_clamps_at_floor(self):
        app = _FakeApp()
        app.sheet_zoom = 0.26
        with _mouse_at(self.inside), _mods(pygame.KMOD_CTRL):
            self.slot.handle_event(_wheel(y=-1), self.rect, app)
        self.assertGreaterEqual(app.sheet_zoom, 0.25)

    def test_ctrl_wheel_clamps_at_ceiling(self):
        app = _FakeApp()
        app.sheet_zoom = 16.0
        with _mouse_at(self.inside), _mods(pygame.KMOD_CTRL):
            self.slot.handle_event(_wheel(y=1), self.rect, app)
        self.assertEqual(app.sheet_zoom, 16.0)

    def test_plain_wheel_scrolls_bars_view_only(self):
        app = _FakeApp(view='bars')
        with _mouse_at(self.inside):
            self.slot.handle_event(_wheel(y=1), self.rect, app)
        self.assertNotEqual(app.bars_scroll, 0.5)
        self.assertEqual(app.trad_scroll, 0.5)   # untouched

    def test_plain_wheel_scrolls_traditional_view_only(self):
        '''Regression test: the old main.py code always wrote bars_scroll,
        so wheel-scroll silently did nothing in the traditional view.
        '''
        app = _FakeApp(view='traditional')
        with _mouse_at(self.inside):
            self.slot.handle_event(_wheel(y=1), self.rect, app)
        self.assertNotEqual(app.trad_scroll, 0.5)
        self.assertEqual(app.bars_scroll, 0.5)   # untouched

    def test_plain_wheel_scroll_clamps_to_unit_range(self):
        app = _FakeApp(view='bars')
        app.bars_scroll = 0.0
        with _mouse_at(self.inside):
            self.slot.handle_event(_wheel(y=5), self.rect, app)   # would go negative
        self.assertGreaterEqual(app.bars_scroll, 0.0)

    def test_horizontal_wheel_returns_seek_signal_without_touching_zoom_or_scroll(self):
        app = _FakeApp()
        with _mouse_at(self.inside):
            result = self.slot.handle_event(_wheel(x=2), self.rect, app)
        self.assertEqual(result, ('seek', (60.0 / app.bpm) * 2))
        self.assertEqual(app.sheet_zoom, 1.0)
        self.assertEqual(app.bars_scroll, 0.5)

    def test_wheel_outside_rect_is_ignored(self):
        app = _FakeApp()
        with _mouse_at(self.outside), _mods(pygame.KMOD_CTRL):
            result = self.slot.handle_event(_wheel(y=1), self.rect, app)
        self.assertFalse(result)
        self.assertEqual(app.sheet_zoom, 1.0)

    def test_wheel_ignored_when_nothing_loaded(self):
        app = _FakeApp()
        app.loaded = False
        with _mouse_at(self.inside), _mods(pygame.KMOD_CTRL):
            result = self.slot.handle_event(_wheel(y=1), self.rect, app)
        self.assertFalse(result)
        self.assertEqual(app.sheet_zoom, 1.0)


if __name__ == '__main__':
    unittest.main()
