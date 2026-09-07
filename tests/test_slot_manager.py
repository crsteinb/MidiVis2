'''Regression tests for the two SlotManager bugs Plan Part 2/3.4 call out by
name: the single-flex-slot limitation (two flexible slots used to fully
overlap) and the click-priority-vs-visual-order mismatch (a hardcoded
dispatch tuple ignored drag-to-reorder). No real pygame display is needed —
pygame.Rect/pygame.event work headless.
'''
import os
import unittest

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')

import pygame

from midivis.render.slots.slot_base import SlotBase
from midivis.render.slots.slot_manager import SlotManager

pygame.init()


class _FixedSlot(SlotBase):
    def __init__(self, slot_id, height, on_event=None):
        super().__init__(slot_id)
        self.fixed_height = height
        self._on_event = on_event
        self.events_received = []

    def handle_event(self, event, rect, app):
        self.events_received.append(event)
        return bool(self._on_event and self._on_event(event, rect, app))


class _FlexSlot(SlotBase):
    fixed_height = None

    def __init__(self, slot_id):
        super().__init__(slot_id)


class TwoFlexSlotsTest(unittest.TestCase):
    def test_leftover_height_split_evenly_between_two_flex_slots(self):
        a, b = _FlexSlot('a'), _FlexSlot('b')
        mgr = SlotManager([a, b])
        content = pygame.Rect(0, 0, 100, 200)
        rects = mgr.rects(content)

        self.assertEqual(rects['a'].height + rects['b'].height, 200)
        self.assertLessEqual(abs(rects['a'].height - rects['b'].height), 1)
        # And they must not overlap -- the bug this guards against.
        self.assertEqual(rects['a'].bottom, rects['b'].top)

    def test_odd_remainder_goes_to_last_flex_slot_not_dropped(self):
        a, b, c = _FlexSlot('a'), _FlexSlot('b'), _FlexSlot('c')
        mgr = SlotManager([a, b, c])
        content = pygame.Rect(0, 0, 100, 101)   # 101 doesn't divide evenly by 3
        rects = mgr.rects(content)
        total = rects['a'].height + rects['b'].height + rects['c'].height
        self.assertEqual(total, 101)

    def test_mixed_fixed_and_two_flex_slots(self):
        fixed = _FixedSlot('fixed', 30)
        a, b = _FlexSlot('a'), _FlexSlot('b')
        mgr = SlotManager([fixed, a, b])
        content = pygame.Rect(0, 0, 100, 230)
        rects = mgr.rects(content)
        self.assertEqual(rects['fixed'].height, 30)
        self.assertEqual(rects['a'].height + rects['b'].height, 200)
        self.assertEqual(rects['fixed'].bottom, rects['a'].top)
        self.assertEqual(rects['a'].bottom, rects['b'].top)


class ClickPriorityFollowsVisualOrderTest(unittest.TestCase):
    def _click_event(self, pos):
        return pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos)

    def test_only_the_first_slot_in_order_gets_a_consumed_event(self):
        def claim(_event, _rect, _app):
            return True

        sheet = _FixedSlot('sheet', 100, on_event=claim)
        keyboard = _FixedSlot('keyboard', 100, on_event=claim)
        mgr = SlotManager([sheet, keyboard])
        content = pygame.Rect(0, 0, 100, 200)

        consumed = mgr.handle_event(self._click_event((50, 10)), content, app=None)
        self.assertTrue(consumed)
        self.assertEqual(len(sheet.events_received), 1)
        self.assertEqual(len(keyboard.events_received), 0)   # never reached -- sheet claimed it first

    def test_dispatch_order_tracks_drag_reorder(self):
        '''The core bug: after dragging 'keyboard' above 'sheet', event
        dispatch order must follow the new visual order, not a fixed tuple.
        '''
        seen_order = []

        def record(_event, _rect, _app, name):
            seen_order.append(name)
            return False   # never consume, so both get a chance

        sheet = _FixedSlot('sheet', 50, on_event=lambda e, r, a: record(e, r, a, 'sheet'))
        keyboard = _FixedSlot('keyboard', 50, on_event=lambda e, r, a: record(e, r, a, 'keyboard'))
        mgr = SlotManager([sheet, keyboard])
        content = pygame.Rect(0, 0, 100, 100)

        # Simulate a completed drag that moves 'keyboard' before 'sheet'.
        mgr._order = ['keyboard', 'sheet']

        mgr.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=(10, 10)),
                          content, app=None)
        self.assertEqual(seen_order, ['keyboard', 'sheet'])


if __name__ == '__main__':
    unittest.main()
