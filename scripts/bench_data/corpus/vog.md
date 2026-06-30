# VoG Groundedness Check

VoG, short for Verification of Groundedness, is the second verification layer.
It asks a language model whether the source and target passages actually support
a proposed relation, then parses a GROUNDED, PARTIAL, or REJECTED verdict.
Following the honesty contract, missing evidence or an unavailable model causes a
rejection rather than an inflated score.
