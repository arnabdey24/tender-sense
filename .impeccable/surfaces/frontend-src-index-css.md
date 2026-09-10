---
version: 1
slug: "frontend-src-index-css"
primary_target: "frontend/src/index.css"
related_targets: ["frontend/src/components/layout","frontend/src/features/assistant","frontend/index.html"]
---

Scope: the TenderSense web application's visual layer — design tokens
(`frontend/src/index.css`), brand assets, theme switching, the app shell
(sidebar, header, page header), the auth and landing surfaces, and the tender
assistant's panel chrome. Routes, queries, and backend behaviour are out of
scope by the product owner's instruction.

Visitor mode: **Operate** for everything under `/app` and `/admin`; the marketing
landing route is **Persuade** at small scale.

Audience and job: a bid manager triaging a morning shortlist at a desk on a large
monitor, and a company director checking the headline on a phone between
meetings. Both are first-class. The task is to decide, per notice, whether it is
worth two weeks of bid preparation.

Constraints the product owner pinned: signal-document logo, deep ocean blue
`oklch(0.48 0.13 245)`, 2D flat single-weight icons, Apple's clarity/deference/
depth as the governing principles, light and dark both switchable and defaulting
to the OS. Grade colours (S violet, A green, B amber, C grey) are shipped data
and may not be rebranded. Colour strategy: **Restrained** — neutrals plus one
accent, the correct floor for a surface people came to operate.

Unresolved: none blocking. Whether the tender table gains a density control is
deferred, being a layout change and out of the agreed scope.

## Direction contract

THESIS: The surface owns *evidence beside verdict* — a grade is never shown
without the reason it can be checked against. It refuses the SaaS-dashboard
default arrangement, a row of aggregate KPI tiles above a chart above a table,
which spends the best real estate on vanity totals while the day's actual
decisions queue below the fold.

OWN-WORLD: Cool near-neutral grounds (`oklch(0.994 0.002 245)` paper,
`oklch(0.178 0.012 250)` night) separated by hairlines rather than nested boxes.
Ocean blue appears only on action, selection, link and focus — never as
decoration or as a filled hero panel. Grade colour is data and is the only
saturation permitted to carry meaning. Component metrics stay exactly as shadcn
Base UI ships them: 32px controls, 10px radii, 14px cards on a 1px
`foreground/10` ring, 20px pill badges, Lucide at 1.7px stroke on a 24px grid.
Geist for Latin, Noto Sans Bengali for Bengali content, one family each, no
display face. Numerals are tabular wherever a figure can change.

STORY: The visitor understands within one screen which notices closed the gap
between "worth reading" and "worth bidding", believes it because every grade
carries its evidence and every unknown is labelled unknown rather than rounded,
and acts by opening a notice and recording bid, hold or skip.

FIRST VIEWPORT: A 256px sidebar carrying the signal mark and the workspace
navigation; a 56px translucent sticky header with breadcrumb, org switcher,
theme control and the notification bell. The content column leads with the page
title and its one-line description, then the day's shortlist as ranked rows —
each row a grade letter, the title, the procuring entity, the money, and the
deadline as time-remaining in the org's timezone. The primary action is per-row
and inline: open the notice. No hero panel, no full-bleed colour field.

FORM: Refined instance of the established application shell — position one on
the ordered list, because the product owner scoped this to the visual layer and
an Operate surface earns familiarity rather than novelty. No seed key: the
direction was pinned by the product owner in this session (signal-document mark,
ocean blue, Apple principles, both themes), and a pinned direction beats the
roll, so the concept tournament was not run. This is recorded rather than
skipped silently.

FINISH: unreviewed and undocumented is unfinished; this build ends with the
finish review, the verdict, DESIGN.md, and every shipping raster carrying its
provenance
