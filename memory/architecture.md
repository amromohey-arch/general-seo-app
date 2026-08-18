# Architecture

## Core decision: one shared multi-tenant app, not per-business clones

Businesses sign up and log in to a shared platform. Not "download and
deploy your own copy" — that's what the 618 reference implementation is,
and it's exactly what we're moving away from.

This means real engineering considerations that don't exist in the
reference app:
- **Per-tenant data isolation.** One business's articles, scripts, and API
  usage must never be visible to or touchable by another tenant. This is
  a hard requirement, not a nice-to-have — get the data model right before
  building features on top of it.
- **Per-tenant API cost caps.** One business with runaway usage must not
  be able to burn through a shared budget or degrade service for others.
- **A real onboarding flow.** Doesn't exist today. In the reference app,
  everything is set once, by hand, via environment variables.

## The two-phase system (the key insight, don't lose this)

Not "technical setup phase, then business setup phase" — that was the
original framing and it's wrong. The real split:

- **Phase 0 — platform infrastructure.** Gemini API key, Google Cloud
  project, OAuth consent screen, deployment, billing, spend caps. Done
  **once**, by the platform operator (Amro), for the whole platform.
  Customers never see any part of this.
- **Phase 1 — business onboarding.** The *only* thing a customer ever
  sees. No API keys, no Cloud Console, no GitHub, nothing that looks like
  software configuration.

This is what actually solves "non-technical users will struggle with
setup" — not a friendlier wizard around the same hard steps, but removing
those steps from the customer's path entirely.

## What's left in Phase 1, once infrastructure is off the table

1. Describe the business in plain language (name, industry, location,
   services, what makes them different)
2. Pick a content posture / preset (trade & local, professional B2B,
   creative portfolio) — this also sets the risk/caution profile (see
   `missing-features.md`)
3. One real connect step: **Sign in with Google** for Search Console —
   the one thing that's genuinely per-business and can't be shared
   platform-wide
4. Where the content publishes (Squarespace, WordPress, etc.) —
   determines output format, not something hand-configured

## Decisions made 2026-08-18

**Multi-tenant config loading:** one process per tenant, config selected
via `CONFIG_PATH` at deploy time (same as `generator.py`'s current
behavior) — not per-request tenant resolution. Deliberately deferred:
per-request resolution would require passing tenant context through every
function instead of using module-level constants computed at import, and
there's no self-serve signup flow that needs it yet. Revisit only if/when
tenants can self-provision instead of being onboarded manually.

**Gemini API usage:** one shared API key across all tenants, with a
per-tenant usage counter and a hard monthly cap read from that tenant's
config, enforced in code — not separate keys per tenant, not a full
billing/metering system. Purpose is a safety net against a bug or runaway
loop burning quota, not cost allocation between paying customers. Revisit
separate keys only if an external party ever needs isolated, billable
usage.
