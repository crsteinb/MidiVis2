'''Regression test for a user-reported bug: Shift is the on-screen keyboard's
sustain-pedal modifier (click-to-latch a note), but releasing Shift left
latched notes stuck on forever -- the only way to release them was to click
each one again. KeyboardSlot.handle_event now treats Shift KEYUP as "release
everything the pedal is holding."
'''
import os
import unittest

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')

import pygame

from midivis.render.slots.keyboard import KeyboardSlot
from midivis.render.widgets.mini_keyboard import FIRST_NOTE

pygame.init()


class _FakeApp:
    def __init__(self):
        self.kb_notes = set()

    def kb_note_on(self, note):
        self.kb_notes.add(note)

    def kb_note_off(self, note):
        self.kb_notes.discard(note)


class ShiftReleasesLatchedNotesTest(unittest.TestCase):
    def setUp(self):
        self.slot = KeyboardSlot()
        self.app = _FakeApp()
        self.rect = pygame.Rect(0, 0, 800, 110)

    def _click(self, note, shift):
        mods = pygame.KMOD_SHIFT if shift else 0
        pos = self._pos_for_note(note)
        with self._mods(mods):
            self.slot.handle_event(
                pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos), self.rect, self.app)
            self.slot.handle_event(
                pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=pos), self.rect, self.app)

    def _pos_for_note(self, note):
        for x in range(self.rect.x, self.rect.right):
            hit = self.slot.hit_test((x, self.rect.centery), self.rect)
            if hit == note:
                return (x, self.rect.centery)
        raise AssertionError(f'no on-screen position found for note {note}')

    class _mods:
        '''Context manager that fakes pygame.key.get_mods() for the duration
        of the click, since KeyboardSlot reads live modifier state.
        '''

        def __init__(self, mods):
            self._mods = mods
            self._real = None

        def __enter__(self):
            self._real = pygame.key.get_mods
            pygame.key.get_mods = lambda: self._mods

        def __exit__(self, *exc):
            pygame.key.get_mods = self._real

    def test_shift_click_latches_note_past_mouse_release(self):
        self._click(FIRST_NOTE, shift=True)
        self.assertIn(FIRST_NOTE, self.app.kb_notes)   # still sounding after mouseup

    def test_releasing_shift_releases_every_latched_note(self):
        self._click(FIRST_NOTE, shift=True)
        self._click(FIRST_NOTE + 2, shift=True)
        self.assertEqual(self.app.kb_notes, {FIRST_NOTE, FIRST_NOTE + 2})

        self.slot.handle_event(
            pygame.event.Event(pygame.KEYUP, key=pygame.K_LSHIFT), self.rect, self.app)

        self.assertEqual(self.app.kb_notes, set())

    def test_shift_release_with_nothing_latched_is_a_no_op(self):
        consumed = self.slot.handle_event(
            pygame.event.Event(pygame.KEYUP, key=pygame.K_LSHIFT), self.rect, self.app)
        self.assertFalse(consumed)
        self.assertEqual(self.app.kb_notes, set())


if __name__ == '__main__':
    unittest.main()
