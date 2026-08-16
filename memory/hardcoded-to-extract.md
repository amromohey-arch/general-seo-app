# Hardcoded in the Reference App — Must Become Configuration

All found in `reference/618-seo-v3/`. This is the concrete extraction list —
each item below is currently a Python constant or literal string and needs
to become a field read from a per-tenant config record instead.

## `modules/generator.py`

- `BRAND_CONTEXT` — brand facts: name, location, services, pricing
  philosophy, contact info, "never say X" landmines. Entirely 618-specific
  prose baked into the prompt.
- `FULL_CSS` — colors, fonts, full stylesheet. Assumes 618's specific
  brand palette and typography.
- Approved hooks list, banned AI-tell words, caption structure —
  reasonable defaults, but currently not overridable per tenant.

## `modules/discovery.py`

- Seed topics — currently hardcoded to music video production
  specifically. Needs to be per-tenant, generated from the business
  profile at onboarding.

## `modules/video_script.py` / spotlight-related funnel logic

- TOFU/MOFU/BOFU funnel definitions — grounded in 618's specific funnel
  deck, not universal. Either needs to become configurable per tenant, or
  the funnel-classification feature itself needs to be optional (not
  every business runs a TOFU/MOFU/BOFU content funnel).

## `templates/index.html` / output assembly

- Squarespace-specific CSS scoping (`.aw` wrapper class, `q618-` prefix on
  interactive elements) — assumes every future tenant also publishes to
  Squarespace, which will not hold. See `missing-features.md` for the
  CMS-agnostic output layer this implies.

## `modules/spotlight.py`

- The entire module (artist/video commentary content) is 100%
  music-industry-specific. Does not generalize. See `missing-features.md`
  — this needs to become an optional plugin, not a core feature every
  tenant gets by default.
