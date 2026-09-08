import unittest

from midivis.midi.spelling import key_accidentals, spell


class KeyAccidentalsTest(unittest.TestCase):
    def test_c_major_and_no_key(self):
        self.assertEqual(key_accidentals('C major'), 0)
        self.assertEqual(key_accidentals(None), 0)

    def test_sharp_majors(self):
        self.assertEqual(key_accidentals('G major'), 1)
        self.assertEqual(key_accidentals('D major'), 2)
        self.assertEqual(key_accidentals('A major'), 3)
        self.assertEqual(key_accidentals('E major'), 4)
        self.assertEqual(key_accidentals('B major'), 5)
        self.assertEqual(key_accidentals('F# major'), 6)
        self.assertEqual(key_accidentals('C# major'), 7)

    def test_flat_majors(self):
        self.assertEqual(key_accidentals('F major'), -1)
        self.assertEqual(key_accidentals('Bb major'), -2)
        self.assertEqual(key_accidentals('Eb major'), -3)
        self.assertEqual(key_accidentals('Ab major'), -4)

    def test_relative_minors_match_their_major(self):
        self.assertEqual(key_accidentals('A minor'), key_accidentals('C major'))
        self.assertEqual(key_accidentals('E minor'), key_accidentals('G major'))
        self.assertEqual(key_accidentals('D minor'), key_accidentals('F major'))
        self.assertEqual(key_accidentals('F# minor'), key_accidentals('A major'))


class SpellTest(unittest.TestCase):
    def test_c_major_all_natural(self):
        for note in (60, 62, 64, 65, 67, 69, 71):
            sp = spell(note, 'C major')
            self.assertEqual(sp.accidental, 0)

    def test_sharp_key_spells_black_keys_as_sharps(self):
        # D major (2 sharps): pitch class 6 (F#/Gb) must be spelled F#, not Gb.
        sp = spell(66, 'D major')
        self.assertEqual(sp.letter, 'F')
        self.assertEqual(sp.accidental, 1)

    def test_flat_key_spells_black_keys_as_flats(self):
        # F major (1 flat): pitch class 10 (Bb/A#) must be spelled Bb, not A#.
        sp = spell(70, 'F major')
        self.assertEqual(sp.letter, 'B')
        self.assertEqual(sp.accidental, -1)

    def test_diatonic_scale_tone_matches_key_signature(self):
        # G major's one sharp (F#) must be spelled as F-sharp wherever it
        # occurs, not just at the pitch-class level -- confirms the letter
        # itself (not just the accidental symbol) is key-aware.
        sp = spell(66, 'G major')   # F#5
        self.assertEqual((sp.letter, sp.accidental), ('F', 1))

    def test_staff_position_differs_for_enharmonic_spellings(self):
        # C#4 (sharp key) and Db4 (flat key) are the same MIDI note but must
        # land on different staff positions (C's line vs D's line) -- this is
        # the actual bug being fixed, not just which symbol gets drawn.
        sharp_sp = spell(61, 'D major')
        flat_sp = spell(61, 'F major')
        self.assertEqual(sharp_sp.letter, 'C')
        self.assertEqual(flat_sp.letter, 'D')
        self.assertNotEqual(sharp_sp.diatonic_step, flat_sp.diatonic_step)

    def test_octave_and_diatonic_step_middle_c(self):
        sp = spell(60, 'C major')   # C4
        self.assertEqual(sp.letter, 'C')
        self.assertEqual(sp.diatonic_step, 4 * 7 + 0)


if __name__ == '__main__':
    unittest.main()
