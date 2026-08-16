# Roadmap

## Two real test businesses, already lined up

1. **The Fix Guys** — Amro's boss's business. Key cutting, engraving,
   watch repair, phone repair, automotive keys, Erina Fair Shopping
   Centre. Local trade business. **Low content risk. Build this first.**
2. **Saymex Engineers** — a friend's forensic/insurance structural
   engineering firm in Sydney. Professional B2B, compliance-adjacent.
   **Higher stakes — a wrong sentence has real professional consequences.
   Do not start this until the risk-profile system (see
   `missing-features.md`) is properly designed, not just stubbed.**

## Agreed next steps, in order

1. **Find out what Fix Guys and Saymex actually run their websites on.**
   Not yet known. Determines how big the CMS-agnostic-output problem
   really is versus how much to build speculatively.
2. **Build Fix Guys first, not Saymex.** Lower stakes, proves the
   config-driven approach works before touching a business where mistakes
   carry real professional consequences.
3. **Extract 618's hardcoded values into a single config schema** as the
   first real code change. This is useful on its own, independent of
   the rest of this project, and is the concrete first task.
4. **Only after Fix Guys works cleanly:** properly design the industry
   risk/caution profile before starting Saymex. Do not skip or rush this
   step for Saymex specifically — see `missing-features.md` for why.

## Status

Nothing has been built yet for the generalized version. This repo's first
commits are the actual start of the build. All of the above is design and
architecture that's already been decided — implementation has not started.
