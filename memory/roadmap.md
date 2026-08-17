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
   **Known:** Saymex Engineers runs on Netlify, with git-commit-triggered
   rebuilds and no CMS editor. Fix Guys runs on Square Online, which is
   CMS-editor-based, similar to Squarespace. This determines how big the
   CMS-agnostic-output problem really is versus how much to build
   speculatively — Fix Guys needs output that works inside a CMS editor,
   Saymex needs output that survives a git-based rebuild pipeline instead.
2. **Build Fix Guys first, not Saymex.** Lower stakes, proves the
   config-driven approach works before touching a business where mistakes
   carry real professional consequences.
3. **Extract 618's hardcoded values into a single config schema** as the
   first real code change. This is useful on its own, independent of
   the rest of this project, and is the concrete first task.
   **Done for `generator.py` specifically** — `BRAND_CONTEXT` and
   `FULL_CSS` are now built at import time from
   `reference/618-seo-v3/config/618-media.json` instead of hardcoded
   constants, verified byte-identical against the pre-refactor source
   (aside from two intentional additions), with config-loading failure
   handling and a field-by-field audited required-keys check. See commits
   `dcea78b` and `da1360e`.
   **Not yet done:** `discovery.py` (seed topics) still uses its own
   hardcoded `SEED_TOPICS` list, and `video_script.py` (approved hooks,
   caption structure, TOFU/MOFU/BOFU funnel definitions) still uses its
   own hardcoded constants — neither reads from `618-media.json` yet,
   even though the config schema already has `seed_topics`, `social_video`,
   and `funnel` sections anticipating this. This was intentionally out of
   scope for the `generator.py` pass, not forgotten — wiring those two
   modules to the same config is the natural next extraction step.
4. **Only after Fix Guys works cleanly:** properly design the industry
   risk/caution profile before starting Saymex. Do not skip or rush this
   step for Saymex specifically — see `missing-features.md` for why.

## Status

Nothing has been built yet for the generalized version's platform (signup,
onboarding, multi-tenant infra) — that work hasn't started. The first real
code change (see step 3 above) has: `generator.py` in the reference app is
now config-driven for one tenant (618 Media), proving the extraction
approach works before it's repeated for `discovery.py`/`video_script.py`
and generalized to new tenants.
