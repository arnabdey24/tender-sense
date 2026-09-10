# TenderSense design system and brand

Status: in progress. Branch `feat/design-system-and-assistant-ui`.
Date: 2026-09-10.

## Why

The application shipped through M7 on stock shadcn defaults. Concretely:

- Every palette token is a shade of grey, including all five `--chart-*` slots,
  so a chart cannot distinguish two series by colour.
- The favicon is still `/vite.svg`; the browser tab shows the Vite logo.
- The "logo" is a generic `FileTextIcon` inside a black rounded square.
- The landing page is a centred `h1` with two buttons.
- A complete `ThemeProvider` is mounted but nothing renders a theme control,
  so dark mode is reachable only by pressing `d` with no field focused. There is
  no `color-scheme` declaration and no pre-hydration script, so a user who
  prefers dark gets a white flash on every load.

The product asks a bidder to trust a grade that decides whether they spend two
weeks preparing a bid. The interface has to look like it was built by people who
would be right about that.

## Decisions taken

| Decision | Choice | Reason |
| --- | --- | --- |
| Logo mark | Signal document — document silhouette with radar arcs | Self-explanatory: the app senses new notices |
| Brand colour | Deep ocean blue, `oklch(0.48 0.13 245)` | Institutional trust, fits public procurement |
| `--info` token | Moved to teal | It previously sat on the new brand hue |
| Themes | Light and dark, explicitly switchable | Requested; provider already exists |
| Icon language | 2D flat, single-weight stroke, no gradients or 3D | Requested |

Grade colours are already spoken for and do not move: S violet, A green,
B amber, C grey. The brand blue was chosen to stay clear of all four.

## Apple's principles, applied here

Not a visual pastiche — the three HIG themes, read against this app.

**Clarity.** Legibility at every size, with meaning carried by hierarchy rather
than decoration. Here: a real type ramp instead of ad-hoc `text-2xl`; tabular
figures on every deadline, score and amount; negative space doing the grouping
work that borders currently do.

**Deference.** The interface defers to the content. Here the content is the
tender and its grade. Chrome recedes to hairlines and near-neutral surfaces;
the brand blue appears only on actions, links and focus, never as decoration.

**Depth.** Layers communicate hierarchy. Here: translucent materials on the
sticky header and the assistant panel, a deliberate elevation ramp instead of
one `shadow-lg`, and motion that moves things from where they were.

## Plan

### 1. Foundations — `frontend/src/index.css`

- Brand ramp `--brand-50…900` in OKLCH; `--primary` bound to it.
- Real chart palette: five distinguishable, colour-blind-safe hues per theme.
- Elevation ramp `--shadow-xs…xl` tuned separately for light and dark.
- Material tokens for translucent surfaces.
- Motion tokens: durations and Apple-style easing curves.
- Dark theme rebuilt: raised surfaces rather than pure black, borders that
  read at low contrast, shadows that actually show.

### 2. Brand assets

- `Logo.tsx` — 2D SVG, mark plus optional wordmark, `currentColor`-driven.
- `favicon.svg`, plus PNG fallbacks, `apple-touch-icon.png`, `site.webmanifest`.
- `index.html`: real favicon links, `color-scheme`, theme-colour per scheme,
  Open Graph tags, and a blocking pre-hydration theme script to kill the flash.

### 3. Theme switching

- `ThemeToggle` component: light / dark / system, in the app header and on the
  auth and landing pages.
- Keep the `d` shortcut, but document it in the toggle's tooltip.

### 4. Application shell

- Sidebar: real logo lockup, grouped navigation, refined active state.
- Header: sticky, translucent, with the theme toggle.
- `PageHeader`: proper type ramp.
- Landing and auth pages rebuilt around the brand.

### 5. Assistant surfaces

- Launcher, panel chrome, message bubbles and the voice orb restyled onto the
  new tokens; the orb's colours currently hardcode `--success`/`--info`.

### 6. Verification

`npm run typecheck`, `npm run lint`, `npm test` (includes axe), `npm run build`.
Contrast checked against WCAG AA in both themes.

## Out of scope

Backend assistant behaviour, matching, scoring and rules are untouched. Voice
stays behind `ASSISTANT_VOICE_ENABLED`. This is presentation only.
