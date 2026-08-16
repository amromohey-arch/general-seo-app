# Missing Entirely — Needs to Be Built

## 1. The onboarding flow itself

Doesn't exist in any form yet. See `design-principles.md` for how it
should feel, and `architecture.md` for exactly what it needs to collect.

## 2. Industry risk / caution profile — a real dial, not an afterthought

Different businesses carry genuinely different content risk. A wrong
sentence about video production pricing is a minor annoyance. A wrong
sentence about structural engineering compliance or insurance claims is a
real professional liability problem. The risk profile should control:
- How much caution/hedging language is required in generated content
- Whether specific numbers, code references, or compliance claims require
  mandatory human review before publishing (vs. optional review)
- How conservative the duplicate/accuracy-checking is

This should be set (or at least defaulted) automatically based on the
business-type preset chosen at onboarding — not something every tenant has
to configure manually.

## 3. Business-type presets

So a new business starts from a sensible content-strategy template instead
of defining one from a blank page. At minimum:
- Trade / local business (e.g. a repair shop)
- Professional B2B / compliance-adjacent (e.g. forensic engineering)
- Creative / portfolio (e.g. 618 Media itself)

Each preset should set sensible defaults for: tone, content structure,
funnel/no-funnel, and the risk profile above.

## 4. CMS-agnostic output layer

Currently everything assumes Squarespace (see `hardcoded-to-extract.md`).
Before building this out further: find out what the two real test
businesses (see `roadmap.md`) actually publish on. That determines how big
this problem really is versus how much to build speculatively.

## 5. Optional/pluggable feature modules

The "spotlight" (artist/video commentary) feature is entirely
music-industry-specific and must not be a default part of the generalized
app. This is the first case of a broader pattern worth designing for:
some features are core (article generation, discovery, scripts), and some
are vertical-specific plugins that only some tenants would ever enable.
Design the plugin boundary now, even if spotlight is the only plugin that
exists for a while.
