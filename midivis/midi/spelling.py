'''Key-signature-aware enharmonic pitch spelling (Plan Part 3.2).

Fixes the old repo's hand-drawn notation renderer always spelling black keys
as sharps regardless of the file's actual key signature (`_is_accidental`
always rendered a literal '#' in traditional_sheet.py) — and, more subtly,
always placing them at the *sharped* letter's staff position too (its `_DIAT`
table maps every chromatic pitch class to a fixed diatonic step, e.g. C#/Db
was always drawn on C's line/space). Real notation is letter-based: C# sits
on the C line with a sharp; Db sits on the D line with a flat. Getting the
staff position right, not just the accidental symbol, is why this needs to
compute a (letter, accidental) pair per note rather than just picking a
symbol.

Scope (deliberately bounded, see FullRewriteStatus.md's Milestone 4 deviations
for the reasoning): rather than deriving a full per-scale-degree spelling
table (which would need double-sharps/flats for the small number of unusual
key/pitch combinations), every key is classified as "sharp-flavored" or
"flat-flavored" from its accidental count, and *all twelve* pitch classes in
that key use the corresponding single-sharp or single-flat spelling table.
This reproduces correct textbook spelling for every scale tone (a key's own
diatonic accidentals are, by construction, single sharps or single flats) and
gives a consistent, unsurprising spelling for chromatic passing tones — not
full harmonic-function spelling, but a real fix for the "ignores key
signature entirely" bug, not just a cosmetic one.
'''
from __future__ import annotations

from dataclasses import dataclass

LETTER_ORDER = ['C', 'D', 'E', 'F', 'G', 'A', 'B']

# Index = pitch class 0-11. Deliberately no B#/Cb/E#/Fb: every entry stays
# within one letter of its natural pitch class, so diatonic-step arithmetic
# never needs to cross an octave boundary to account for them.
SHARP_SPELLING = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
FLAT_SPELLING = ['C', 'Db', 'D', 'Eb', 'E', 'F', 'Gb', 'G', 'Ab', 'A', 'Bb', 'B']

# Direct ports of mido's own key-signature decode table (mido/midifiles/meta.py's
# _key_signature_decode, reversed name->sf), NOT re-derived from pitch class —
# C# major (7 sharps) and Db major (5 flats) share a pitch class but are
# distinct, both-valid key names, so folding to "fewer accidentals" would
# silently turn one into the other. Keying directly off the name mido/
# midi/analyze.py already produce sidesteps that ambiguity entirely.
_MAJOR_ACCIDENTALS = {
    'Cb': -7, 'Gb': -6, 'Db': -5, 'Ab': -4, 'Eb': -3, 'Bb': -2, 'F': -1, 'C': 0,
    'G': 1, 'D': 2, 'A': 3, 'E': 4, 'B': 5, 'F#': 6, 'C#': 7,
}
_MINOR_ACCIDENTALS = {
    'Ab': -7, 'Eb': -6, 'Bb': -5, 'F': -4, 'C': -3, 'G': -2, 'D': -1, 'A': 0,
    'E': 1, 'B': 2, 'F#': 3, 'C#': 4, 'G#': 5, 'D#': 6, 'A#': 7,
}


@dataclass(frozen=True)
class Spelling:
    letter: str            # 'A'..'G'
    accidental: int         # -1 flat, 0 natural, +1 sharp
    diatonic_step: int       # absolute step: (octave * 7) + letter index, C4 = 28


def key_accidentals(key_sig: str | None) -> int:
    '''Signed accidental count for a key_sig string like "F# minor" or
    "Bb major" (the format midi/analyze.py's get_key_signature/
    detect_key_signature produce) — positive = sharps, negative = flats.
    Returns 0 (no accidentals — same as C major) if key_sig is None or
    unrecognized.
    '''
    if not key_sig:
        return 0
    tonic, _, mode = key_sig.strip().partition(' ')
    table = _MINOR_ACCIDENTALS if mode.strip() == 'minor' else _MAJOR_ACCIDENTALS
    return table.get(tonic, 0)


def spell(note: int, key_sig: str | None) -> Spelling:
    '''Spell a MIDI note number under the given key signature.'''
    accidentals = key_accidentals(key_sig)
    table = SHARP_SPELLING if accidentals >= 0 else FLAT_SPELLING
    name = table[note % 12]
    letter = name[0]
    accidental = 0
    if len(name) > 1:
        accidental = 1 if name[1] == '#' else -1
    octave = note // 12 - 1
    diatonic_step = octave * 7 + LETTER_ORDER.index(letter)
    return Spelling(letter=letter, accidental=accidental, diatonic_step=diatonic_step)
