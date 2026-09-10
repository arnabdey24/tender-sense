# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Two primary users, both first-class:

- **Bid / tender manager** at a contracting or supply firm. Lives in the product
  daily at a desk on a large monitor. Opens the 08:00 Asia/Dhaka digest, triages
  the day's shortlist, opens the notices worth reading, and records bid / hold /
  skip with a note. Needs scanning density, many rows at once, and the keyboard.
- **Company owner or business-development director.** Dips in between meetings,
  often on a laptop or phone. Wants the headline — what is worth bidding on today
  and why — with the full evidence one tap away, not the whole pipeline.

Both matter equally, so the phone layout is a genuine restructure, not a shrunk
desktop. Secondary: platform operations staff (`is_superuser`) who watch source
health and job runs.

## Product Purpose

TenderSense watches public procurement portals (e-GP Bangladesh, World Bank STEP),
matches every new notice against a company's capability profile **by meaning rather
than keywords**, applies that company's own hard eligibility rules, grades the fit
S / A / B / C, explains the grade against quoted evidence, and delivers a ranked
daily shortlist in-app and by email.

Success is a bidder finding the tender they would otherwise have missed, and
trusting the grade enough to commit two weeks of bid preparation to it.

## Positioning

Semantic matching against a structured company profile, combined with a
deterministic, per-tenant eligibility rule engine. A keyword alert service cannot
tell a firm that it is ineligible on turnover; a generic LLM wrapper cannot show
which rule failed, against which quoted line of the notice, under which version of
the company's profile. The grade is reproducible and attributable, not a vibe.

## Operating Context

- Multi-tenant SaaS. A company registers, becoming an **Organization**; the
  registering user is admin. Roles are admin / member, with email invites.
- The tender pool is **shared** across tenants. Profile, rules, matches, decisions
  and notifications are per-org and never cross.
- Daily rhythm: scrapers run, matches compute, a digest goes out at a per-org time
  (default 08:00 Asia/Dhaka), an instant alert fires for an S-grade eligible
  notice, deadline reminders fire for tenders marked "bid".
- Deadlines are the dominant pressure. Urgency is derived in the org's timezone:
  expired / critical ≤3d / high ≤7d / normal ≤21d / low / unknown.
- Money is BDT and USD, compared through recorded FX rates. Bangladeshi users
  read amounts in lakh and crore.
- Notices are English, Bangla, or mixed. The interface chrome is English; **notice
  content and assistant conversation may be Bangla**, so the type stack must carry
  Bengali script without falling back to a mismatched face.

## Capabilities and Constraints

- Onboarding → capability profile → eligibility rules → notification recipients →
  matches → tender detail → decision.
- Grades: S ≥ 0.78, A ≥ 0.70, B ≥ 0.62, else C, all configurable per deployment.
  Similarity is `0.6 × best_facet + 0.4 × mean(top 3 facets)`.
- Eligibility per rule is pass / fail / unknown / warn. Overall: ineligible on any
  hard fail, needs_verification on any hard unknown, else eligible. **"Needs
  verification" is a first-class state, not an error** — low extraction confidence
  is expected and must be shown honestly rather than rounded to a yes or a no.
- A tender assistant (text now, live English/Bangla voice behind
  `ASSISTANT_VOICE_ENABLED`) explains a recorded assessment and builds charts,
  calculations and checklists in an analysis workspace. It explains existing
  results; it never independently decides a grade.
- Attachments (PDF bidding documents) are not parsed in v1. Extraction runs on the
  notice title, description and detail-page fields only — so missing data is
  common and must be designed for.
- No billing. A `plan` column exists on organization.

## Brand Commitments

- Name **TenderSense**, already in the shipped product and in the BRD.
- Confirmed with the product owner for this redesign:
  - Logo is a **signal document** — a document silhouette with radar arcs rising
    from its edge, meaning the product senses new notices.
  - Brand colour is **deep ocean blue**, `oklch(0.48 0.13 245)`.
  - Icons are **2D and flat**: single-weight stroke, no gradients, no 3D.
  - **Apple's design principles** (clarity, deference, depth) govern the interface.
  - Light and dark themes, both explicitly switchable, defaulting to the OS setting.
- Grade colours are already shipped and are **not** available for rebranding:
  S violet, A green, B amber, C grey.

## Evidence on Hand

- `docs/TenderSense_BRD.pdf` — BracIT's original brief.
- `docs/IMPLEMENTATION_PLAN.md` — confirmed product decisions and the milestone log
  through M7.
- `docs/CHATBOT_VOICE_PLAN.md` — the assistant and live-voice design.
- `docs/RUNBOOK.md` — operations.
- Synthetic seed data (~40 tenders, one sample company, relevance labels) in
  `backend/data/seed/`; frontend fixtures in `frontend/src/mocks/fixtures.ts`.

There are **no** real customers, testimonials, logos, case studies, press mentions,
pricing or usage numbers. Marketing surfaces must not invent any; a placeholder is
correct where a real fact is missing.

## Product Principles

1. **Show the evidence, not just the verdict.** Every grade, every rule result and
   every number traces back to a quoted line and a recorded version. A fluent
   explanation is not a substitute for evidence.
2. **Missing data stays missing.** Unknown is displayed as unknown. The product
   never rounds low confidence into a clean answer.
3. **The deadline is the clock.** Time remaining outranks almost everything else
   in the hierarchy of any tender surface.
4. **The tenant boundary is absolute.** Nothing from one organization is ever
   visible to another, in any surface, cache or export.
5. **Earned familiarity.** This is a tool used under deadline pressure. Standard
   affordances, consistent vocabulary, no invented controls.

## Accessibility & Inclusion

- WCAG 2.1 AA is the committed bar — already enforced by axe tests
  (`frontend/src/test/a11y.test.tsx`) and to be held in both themes.
- Colour is never the only signal: grades carry a letter, rule results carry a
  label and an icon, voice states carry readable text.
- `prefers-reduced-motion` is honoured, including by the assistant's voice orb.
- Full keyboard operation, including the assistant panel and voice controls.
- Bengali script renders in a face chosen for it, at a size matched to the Latin
  face, in both chrome and content.
