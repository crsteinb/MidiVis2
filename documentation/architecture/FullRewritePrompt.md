Read documentation/architecture/FullRewriteStatus.md, then documentation/architecture/FullRewritePlan.md
(both in this repo, MidiVis2). Status tells you which milestone is current and what's already done;
Plan (Part 4) defines that milestone's scope, and its earlier sections give the architecture/design
context you need to implement it correctly.

Implement exactly the current milestone — no more. If it's already partially done (Status will say so),
continue from where it left off rather than restarting. If a milestone turns out to be too large for one
session, it's fine to stop partway: just make sure Status precisely records what's done and what's left
before you stop.

Do not start work on the next milestone once the current one is finished, even if you have capacity left
— stop and let me test and commit first.

Do not commit anything yourself. Leave the working tree with uncommitted changes for me to review and
test.

The old MidiVis repo (sibling folder, path in FullRewritePlan.md Part 0) is available read-only as a
reference for exact prior behavior (e.g. the FluidSynth workarounds, GM instrument tables, sample MIDI
files) — read from it as needed, never write to it.

Before you stop, update documentation/architecture/FullRewriteStatus.md with: what was completed this
session, files touched, any deviations from FullRewritePlan.md and why, manual test steps I should run
to verify this milestone, and anything a fresh context would need to know to continue (there is no
memory carried over between sessions besides this file).
