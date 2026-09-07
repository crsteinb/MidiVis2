import unittest

import pygame

from midivis.render.widgets.text_input import TextInput


def _key(key, unicode=''):
    return pygame.event.Event(pygame.KEYDOWN, key=key, unicode=unicode)


class TextInputTest(unittest.TestCase):
    def test_typing_inserts_at_cursor(self):
        ti = TextInput('helo')
        ti.cursor = 3
        ti.handle_key(_key(pygame.K_l, 'l'))
        self.assertEqual(ti.text, 'hello')
        self.assertEqual(ti.cursor, 4)

    def test_backspace_and_delete(self):
        ti = TextInput('hello')
        ti.cursor = 5
        ti.handle_key(_key(pygame.K_BACKSPACE))
        self.assertEqual(ti.text, 'hell')
        self.assertEqual(ti.cursor, 4)

        ti.cursor = 0
        ti.handle_key(_key(pygame.K_DELETE))
        self.assertEqual(ti.text, 'ell')
        self.assertEqual(ti.cursor, 0)

    def test_backspace_at_start_and_delete_at_end_are_no_ops(self):
        ti = TextInput('ab')
        ti.cursor = 0
        ti.handle_key(_key(pygame.K_BACKSPACE))
        self.assertEqual(ti.text, 'ab')

        ti.cursor = 2
        ti.handle_key(_key(pygame.K_DELETE))
        self.assertEqual(ti.text, 'ab')

    def test_arrow_keys_and_home_end_move_cursor(self):
        ti = TextInput('abcd')
        ti.cursor = 2
        ti.handle_key(_key(pygame.K_LEFT))
        self.assertEqual(ti.cursor, 1)
        ti.handle_key(_key(pygame.K_RIGHT))
        ti.handle_key(_key(pygame.K_RIGHT))
        self.assertEqual(ti.cursor, 3)
        ti.handle_key(_key(pygame.K_HOME))
        self.assertEqual(ti.cursor, 0)
        ti.handle_key(_key(pygame.K_END))
        self.assertEqual(ti.cursor, 4)

    def test_cursor_clamped_at_boundaries(self):
        ti = TextInput('a')
        ti.cursor = 0
        ti.handle_key(_key(pygame.K_LEFT))
        self.assertEqual(ti.cursor, 0)
        ti.cursor = 1
        ti.handle_key(_key(pygame.K_RIGHT))
        self.assertEqual(ti.cursor, 1)

    def test_return_unfocuses(self):
        ti = TextInput('a')
        ti.focused = True
        ti.handle_key(_key(pygame.K_RETURN))
        self.assertFalse(ti.focused)

    def test_non_printable_key_not_consumed(self):
        ti = TextInput('a')
        consumed = ti.handle_key(_key(pygame.K_F1))
        self.assertFalse(consumed)
        self.assertEqual(ti.text, 'a')

    def test_set_text_resets_cursor_to_end(self):
        ti = TextInput('a')
        ti.set_text('hello world')
        self.assertEqual(ti.cursor, len('hello world'))


if __name__ == '__main__':
    unittest.main()
