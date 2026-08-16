# Project: Multi-Tenant SEO Content App

## What this is

Generalizing a working, single-tenant SEO content automation tool (built
for one video production business, 618 Media) into a multi-tenant app that
any business can sign up for and use.

**Status: architecture and design decided, no code written yet for the
generalized version.** The first commits in this repo will be the actual
start of the build.

## Before doing any work, read

- `memory/architecture.md` — the core technical decision (multi-tenant,
  not per-business clones) and the two-phase system design
- `memory/design-principles.md` — how this should feel to a non-technical
  user, and why
- `memory/hardcoded-to-extract.md` — what's hardcoded in the reference app
  that must become configuration
- `memory/missing-features.md` — what doesn't exist yet and needs building
- `memory/roadmap.md` — agreed next steps and the two real test businesses

## Reference implementation

`reference/618-seo-v3/` is the current, working, single-tenant app this is
being generalized from. It's a real deployed Flask app (Google Cloud Run +
GCS storage + Gemini API). Read `reference/618-seo-v3/modules/generator.py`
first — `BRAND_CONTEXT` and `FULL_CSS` are where nearly all of the
hardcoding for one specific business is concentrated, and are the clearest
picture of what a config schema needs to cover.

Treat this folder as read-only reference, not a starting point to edit
directly — the generalized app is a new build informed by it, not a fork
of it.

## Who this is for

Two real people, both already lined up:
- **Amro** — technical, comfortable with code and config, wants control
- **A non-technical business owner** (e.g. a forensic engineer, a trade
  business owner) — zero patience for anything that feels like software
  setup

Design and build for the second person by default. Advanced control stays
available, but never in the way.

## Standing instruction

Whenever a code/file change is ready, always show the exact git commands
(add, status, commit, push) needed to save and sync it — every time,
without being asked.
