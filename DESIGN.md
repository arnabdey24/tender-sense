---
name: TenderSense
description: Public procurement intelligence — evidence shown beside every verdict.
colors:
  brand-600: "oklch(0.48 0.13 245)"
  brand-400: "oklch(0.702 0.117 245)"
  brand-50: "oklch(0.972 0.013 245)"
  background: "oklch(0.994 0.002 245)"
  foreground: "oklch(0.185 0.012 250)"
  card: "oklch(1 0 0)"
  muted: "oklch(0.968 0.005 245)"
  muted-foreground: "oklch(0.505 0.015 250)"
  accent: "oklch(0.957 0.012 245)"
  accent-foreground: "oklch(0.33 0.1 245)"
  border: "oklch(0.917 0.006 245)"
  sidebar: "oklch(0.978 0.004 245)"
  dark-background: "oklch(0.178 0.012 250)"
  dark-foreground: "oklch(0.972 0.004 245)"
  dark-card: "oklch(0.216 0.014 250)"
  dark-sidebar: "oklch(0.198 0.013 250)"
  dark-primary: "oklch(0.7 0.12 245)"
  dark-muted-foreground: "oklch(0.715 0.014 250)"
  grade-s: "oklch(0.52 0.19 300)"
  grade-a: "oklch(0.53 0.14 150)"
  grade-b: "oklch(0.72 0.15 70)"
  grade-c: "oklch(0.55 0.02 260)"
  success: "oklch(0.52 0.13 150)"
  warning: "oklch(0.52 0.12 70)"
  info: "oklch(0.52 0.1 200)"
  destructive: "oklch(0.55 0.2 27)"
typography:
  page-title:
    fontFamily: "Geist Variable, Noto Sans Bengali, system-ui, sans-serif"
    fontSize: "1.5rem"
    fontWeight: 600
    lineHeight: 1.25
    letterSpacing: "-0.019em"
  section:
    fontFamily: "Geist Variable, Noto Sans Bengali, system-ui, sans-serif"
    fontSize: "1.25rem"
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: "-0.014em"
  card-title:
    fontFamily: "Geist Variable, Noto Sans Bengali, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 500
    lineHeight: 1.375
    letterSpacing: "normal"
  body:
    fontFamily: "Geist Variable, Noto Sans Bengali, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: "normal"
  supporting:
    fontFamily: "Geist Variable, Noto Sans Bengali, system-ui, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 400
    lineHeight: 1.42
    letterSpacing: "normal"
  caption:
    fontFamily: "Geist Variable, Noto Sans Bengali, system-ui, sans-serif"
    fontSize: "0.6875rem"
    fontWeight: 500
    lineHeight: 1.36
    letterSpacing: "normal"
rounded:
  sm: "6px"
  md: "8px"
  lg: "10px"
  xl: "14px"
  "2xl": "18px"
  pill: "26px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "16px"
  lg: "24px"
  xl: "36px"
components:
  button-primary:
    backgroundColor: "{colors.brand-600}"
    textColor: "oklch(0.99 0.005 245)"
    rounded: "{rounded.lg}"
    height: "32px"
    padding: "0 10px"
    typography: "{typography.body}"
  button-primary-hover:
    backgroundColor: "color-mix(in oklch, oklch(0.48 0.13 245) 80%, transparent)"
    textColor: "oklch(0.99 0.005 245)"
  button-outline:
    backgroundColor: "{colors.background}"
    textColor: "{colors.foreground}"
    rounded: "{rounded.lg}"
    height: "32px"
    padding: "0 10px"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.foreground}"
    rounded: "{rounded.lg}"
    height: "32px"
  card:
    backgroundColor: "{colors.card}"
    textColor: "{colors.foreground}"
    rounded: "{rounded.xl}"
    padding: "16px"
    typography: "{typography.body}"
  badge-grade-s:
    backgroundColor: "{colors.grade-s}"
    textColor: "oklch(0.99 0.005 300)"
    rounded: "{rounded.pill}"
    height: "20px"
    padding: "0 8px"
  badge-status-warning:
    backgroundColor: "color-mix(in oklch, oklch(0.52 0.12 70) 15%, transparent)"
    textColor: "{colors.warning}"
    rounded: "{rounded.pill}"
    height: "20px"
    padding: "0 8px"
  input:
    backgroundColor: "transparent"
    textColor: "{colors.foreground}"
    rounded: "{rounded.lg}"
    height: "32px"
    padding: "4px 10px"
  sidebar-item-active:
    backgroundColor: "oklch(0.945 0.012 245)"
    textColor: "{colors.accent-foreground}"
    rounded: "{rounded.md}"
    padding: "8px"
---

# Design

## Overview

TenderSense reads public procurement notices, grades them against a company's
capability profile, and shows the evidence behind the grade. The interface owns
one idea — **evidence beside verdict** — and refuses the SaaS-dashboard default
of aggregate KPI tiles above a chart above a table, which spends the best space
on vanity totals while the day's decisions queue below the fold.

Apple's three themes govern: clarity (a real type ramp, tabular figures,
negative space doing the grouping), deference (hairlines and near-neutral
surfaces; brand blue only on action), and depth (a five-step elevation ramp and
translucent materials where content genuinely passes underneath).

Colour strategy is **Restrained**: neutrals plus one accent. That is the floor
for a surface people came to operate, and grade colour is the only saturation
allowed to carry meaning.

## Colors

### Primary

`brand-600` `oklch(0.48 0.13 245)` — deep ocean blue. Institutional trust, right
for public procurement. It appears on primary actions, links, the current
selection and focus rings. **Never** as a page-scale fill, a tinted card, or
decoration.

In dark the primary rises to `brand-400` `oklch(0.7 0.12 245)` and takes
near-black ink. A mid-blue with white text measures 3.6:1 in dark; the lighter
step with dark ink measures 7.3:1.

### Neutral

Grounds are faintly cool (hue 245–250, chroma ≤ 0.014) rather than pure grey, so
they sit with the brand rather than beside it.

Light: background `0.994` → card `1.0`, with the sidebar at `0.978` as a second
neutral layer. Dark: background `0.178` → sidebar `0.198` → card `0.216` →
popover `0.232`. Dark surfaces are raised greys, never black.

### Named Rules

- **Both themes are designed, not derived.** Dark is never a computed inversion
  of light. Every foreground/background pair is checked to WCAG AA against the
  surface it actually sits on, per theme.
- **Grade colour is data, and is reserved.** S violet, A green, B amber, C grey
  are the shipped grading vocabulary. They are never reused as a chart series,
  never rebranded, and never the only signal — the letter is always present.
- **Status tokens are legible as text on the page ground**, not only as fills.
  `--success`, `--warning`, `--info` all pass 4.5:1 on `background` in both
  themes. `--*-foreground` is the ink used *on* a solid fill of that colour and
  must never be used as a text colour on the page ground.
- **Chart series are validated, not chosen.** The five categorical steps pass a
  colour-blind separation check on adjacent pairs, a chroma floor, a lightness
  band, and ≥3:1 against the surface — separately per theme. The dark ramp is
  re-stepped into L 0.48–0.67 rather than lightened.
- Beyond four simultaneous unordered series, add a legend plus direct labels or
  facet. The light ramp's blue-vs-purple pair is close under protanopia when all
  five are on screen at once and unlabelled.

## Typography

One family. Geist for Latin, Noto Sans Bengali for Bengali — no display face,
because a product UI carries more type roles than a brand page and exaggerated
contrast just makes noise in a table.

### Hierarchy

40/44 marketing headline · 24/30 page title · 20/26 section · 16/22 card title ·
14/21 body · 12/17 supporting · 11/15 caption. Tracking tightens as size grows
(−0.028em at the top, normal at body). Sizes are fixed rem, never fluid.

### Named Rules

- **11px is the floor.** Nothing ships smaller.
- **Figures are tabular** on every table cell, `<time>`, badge and `.tabular`
  element. A deadline counting down from 10 days to 9 must not shift the column
  beside it.
- **Bengali is set at 0.96em with a 1.7 line height.** Noto Sans Bengali runs
  optically larger than Geist at the same pixel size. Notices, quoted evidence
  and assistant replies arrive in either script, sometimes in one sentence.
- Geist's contextual alternates are disabled (`font-feature-settings: "calt" 0`)
  because they muddy small UI labels.

## Layout

Sidebar 256px, collapsing to a 48px icon rail. Header 56px, sticky and
translucent. Content padding 16px, 24px from `md`.

Responsive behaviour is **structural, not fluid**: the sidebar collapses, the
header's org label drops to its icon under `sm`, the breadcrumb truncates on one
line rather than wrapping into a fixed-height bar, and grids restack. Type never
scales with the viewport.

Prose measure stays 65–75ch (`max-w-prose`); tables and dense panels may run
wider.

## Elevation & Depth

### Shadow Vocabulary

Five steps, `xs` → `xl`. Every level carries **both an offset and a blur**.

Dark uses its own deeper, wider ramp at higher opacity — a shadow tuned for
paper is invisible on a dark ground.

### Named Rules

- **A zero-offset coloured halo is decoration, not depth.** Not used.
- **Translucency is a material, not a finish.** `.material-chrome` and
  `.material-panel` are applied only where content genuinely scrolls underneath:
  the sticky app header, the landing header, the assistant panel. Both degrade to
  an opaque token where `backdrop-filter` is unsupported.
- Cards separate with a 1px `foreground/10` ring, not a heavy border and not a
  nested card. Nested cards are always wrong.

## Shapes

Radii derive from one 0.625rem root: 6 · 8 · 10 · 14 · 18 · 26(pill). Controls
take 10, cards 14, badges the pill. These are the values shadcn Base UI already
ships; the redesign deliberately did not move them, because the component family
is the product's vocabulary and earned familiarity outranks novelty here.

## Components

### Buttons

32px default height (28 sm, 36 lg), 10px radius, 14px medium label, 4px icon
gap. Primary is a solid brand fill; outline, ghost, secondary, destructive and
link complete the set. Focus is a 3px `ring/50` plus a `ring` border. Active
nudges down 1px.

### Chips

Badges are 20px pills at 12px medium. Grade variants are solid fills; status
variants (`success`, `warning`, `info`) are a 15% tint of the token with the
token itself as text — one consistent pattern across all three.

### Cards / Containers

14px radius, 16px internal spacing on a `--card-spacing` variable, 1px
`foreground/10` ring, no shadow by default. Footers take a top border and a
`muted/50` ground.

### Inputs / Fields

32px height, 10px radius, transparent ground with an `input` border, brand caret.
Invalid state borders `destructive` and rings it at 20%.

### Navigation

Sidebar items are 8px-radius rows at 14px with a 16px icon. The active row takes
a brand-tinted ground and brand-tinted text — never a heavy fill.

### Signature component: the mark

`LogoMark` draws a document with radar arcs rising from its right edge. Both
tones come from `currentColor` — document solid, arcs at 55% — so one component
serves every surface and both themes. Below 28px it is **redrawn**, not scaled:
`detail="compact"` drops the third arc and the third rule and thickens both.

### Signature component: the voice orb

The assistant's orb encodes microphone amplitude as scale and session state as
motion, with a readable text label always present beside it. It carries no
meaning in colour alone and stops entirely under `prefers-reduced-motion`.

**It is the one sanctioned exception to the flat-material rule.** The orb keeps
its conic gradient, specular highlight and inset shadow. A finish review scored
that as contradicting the flat 2D world; the product owner overruled it
deliberately. The exception covers the orb and nothing else — no other surface
inherits imitation dimensionality from it, and this is not a licence to add
gradients or bevels elsewhere.

## Do's and Don'ts

### Do:

- Show the evidence next to the verdict. Every grade opens onto its quoted line.
- Display unknown as unknown. "Needs verification" is a first-class state.
- Put the deadline high in the hierarchy of any tender surface.
- Theme the surfaces the browser draws: selection, caret, scrollbars, focus
  rings, underline offset, tabular figures.
- Keep motion at 130–260ms, exponential ease-out, reporting state only.

### Don't:

- Don't invert one theme to make the other.
- Don't use brand blue for anything but action, selection, link or focus. A
  status count (the unread badge) takes ink, not brand.
- Don't wash a surface with a brand-tinted radial gradient. The hero glow behind
  a headline is the generic-SaaS tell; both instances were removed.
- Don't reuse a grade or status colour as a chart series.
- Don't put a kicker or eyebrow above a heading.
- Don't ship gradient text, glass-as-decoration, coloured left-border accents,
  hard offset shadows, or an emoji standing in for an icon.
- Don't orchestrate a page-load sequence in the app. Users load into a task.
- Don't add a second family, a display face, or fluid type to the product UI.
