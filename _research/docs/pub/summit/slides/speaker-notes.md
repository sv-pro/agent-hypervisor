# Speaker Notes

## Slide 1 — Title

Open with the practical claim, not the philosophy.
Say: this talk is about turning observed agent behavior into deterministic runtime boundaries.

## Slide 2 — The problem

Emphasize that the attack surface is now wider than prompt injection.
Mention tools, orchestration, memory, and external side effects.

## Slide 3 — The practical failure mode

Define scope creep in plain language.
Explain that this is what teams can actually observe in operations.

## Slide 4 — The shift in mindset

Use the contrast:
"Can the agent do X?" versus "Does X exist in the agent’s world?"
Pause here — this is the conceptual hinge of the talk.

## Slide 5 — The pipeline

Walk slowly through Observe -> Profile -> Manifest -> Enforce.
Stress that this is not a live-agent magic trick; it is a reproducible engineering loop.

## Slide 6 — What the PoC actually does

Be explicit about the bounded claim.
Say: this PoC proves feasibility for a workflow, not general semantic safety.

## Slide 7 — Benign workflow

Point to the derived `repo_safe_write` profile.
Highlight that local work is allowed, but remote push becomes `REQUIRE_APPROVAL`.

## Slide 8 — Unsafe workflow

Explain each denial separately.
Make it clear that there is no single magic blocklist; multiple policy checks are involved.

## Slide 9 — Why this matters

Frame the value as bounded autonomy and deterministic enforcement.
Say that this is more useful than runtime improvisation with ever-expanding permissions.

## Slide 10 — Limits

Say this part calmly and directly.
Acknowledge that profiles are imperfect drafts and that semantic ambiguity remains.

## Slide 11 — Practical adoption path

Turn the idea into a sequence teams can actually follow.
This is the "take it home" slide.

## Slide 12 — Close

Repeat the thesis in one sentence:
Observed execution can be compiled into runtime boundaries.
End on the PoC proof, not on a broad manifesto.
