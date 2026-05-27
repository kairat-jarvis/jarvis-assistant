# Dashboard Trends 2026 — Field Reference

Use this when the user asks for "modern look", "make it look 2026", or you need to defend a design choice.

## Visual

### 1. Bento-box layouts (dominant)
Asymmetric grid of rounded tiles (16–24 px radius). One hero tile spans 2×2, supporting tiles vary from 1×1 to 2×1. Apple Sequoia, Linear Insights, Vercel product pages, Stripe Atlas all converged here.

```css
/* Bento template — 12-col grid, varied spans */
.bento {
  display: grid;
  grid-template-columns: repeat(12, 1fr);
  grid-auto-rows: minmax(140px, auto);
  gap: 16px;
}
.bento .hero  { grid-column: span 6; grid-row: span 2; }  /* big KPI */
.bento .wide  { grid-column: span 6; grid-row: span 1; }  /* trend chart */
.bento .small { grid-column: span 3; grid-row: span 1; }  /* mini KPI */
```

**Glassmorphism** survives only as accent (`backdrop-filter: blur(20px)` on a sidebar or hover state). Don't use it as the dashboard fabric — it tanks readability.

**Neumorphism** is dead. Soft shadows fail WCAG contrast tests.

### 2. Dark-first colour
- Background: NOT `#000`. Use `#09090B` (Tailwind `zinc-950`) or `#0A0A0A`.
- Cards: `#18181B` (`zinc-900`) with 1px `#27272A` (`zinc-800`) border.
- Body text: `#FAFAFA` / `#E4E4E7`.
- Muted text: `#A1A1AA`.
- One saturated accent: electric blue `#3B82F6`, lime `#84CC16`, magenta `#EC4899` — pick ONE per dashboard.

Modern colour spaces:
```css
:root {
  --accent: oklch(0.7 0.18 245);          /* perceptually-uniform blue */
  --accent-soft: oklch(0.7 0.18 245 / 0.15);
}
```
OKLCH is supported in all modern browsers (2024+). Falls back gracefully.

### 3. Typography
- **Inter** (still the workhorse) or **Geist** (Vercel) / **Geist Mono** for numbers
- **IBM Plex Sans + Plex Mono** for executive/audit dashboards
- Body 13–14 px, headings 32–56 px, `letter-spacing: -0.02em` on big text
- KPI numbers ALWAYS `font-variant-numeric: tabular-nums` — non-negotiable, otherwise digits jitter on update

```css
.kpi-value {
  font-size: 2.25rem;
  font-weight: 600;
  letter-spacing: -0.02em;
  font-variant-numeric: tabular-nums;
  font-feature-settings: "ss01", "cv11";
}
```

### 4. Motion
- Spring physics, not easing curves
- Numbers count up on mount (use a small `requestAnimationFrame` loop or motion library)
- Charts draw in 400–600 ms (ECharts: `animationDuration: 500, animationEasing: 'cubicOut'`)
- Hover via `transform: translateY(-2px)`, never `width`/`height` changes
- Wrap all motion:

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
```

### 5. Accessibility (WCAG 2.2 minimum)
- Focus-visible ring: `2px` solid accent, `2px` offset
- Click targets ≥ 24×24 px
- Contrast ≥ 4.5:1 body, ≥ 3:1 large text
- Colour never the only signal — pair with shape, label, icon, or pattern
- APCA contrast model is rising (WCAG 3 preview) — check via apcacontrast.com if in doubt

## Architectural patterns

### Hero-metric + supporting grid
```
┌────────────────────┬─────────┬─────────┐
│                    │  KPI 2  │  KPI 3  │
│   HERO METRIC      ├─────────┼─────────┤
│   + sparkline      │  KPI 4  │  KPI 5  │
├────────────────────┴─────────┴─────────┤
│           TREND CHART (full width)     │
├────────────┬───────────────────────────┤
│  TABLE     │   SECONDARY CHART         │
└────────────┴───────────────────────────┘
```

### Filter bar = top segmented; sidebar = nav only
Sidebars collapsed to icon-rail (Linear/Notion pattern). Filters as horizontal segmented buttons OR a sticky top bar. Cross-cutting actions go into a `cmdk` palette (⌘K).

### Drill-down = slide-over sheet (right side), not modal
```
Click a row → sheet slides in from right with details
URL syncs: ?row=42&tab=metrics
Esc closes; doesn't lose dashboard context
```

### Streaming + skeleton loaders per tile
Don't block the page. Each tile shows a skeleton (`background: linear-gradient` shimmer) while loading.

### Mobile-first
Below 768px:
- KPI grid → horizontal snap-scroll carousel
- Multi-series charts → single sparklines
- Filters → bottom-sheet (Vaul-style)

## AI-native references
- **Vercel v0** — text-to-React baseline
- **Anthropic Artifacts** — single-file dashboards inline
- **Hex Magic** — NL → SQL → chart + narrative
- **ThoughtSpot Spotter** — search-driven BI
- **Tableau Pulse** — auto-anomaly + plain-English insight cards

When generating a dashboard, consider adding ONE auto-narrative tile that summarises the data in 1–2 sentences. This is the 2026 differentiator over PowerBI.

## Best-in-class dashboards to reference visually
- Linear Insights — bento + dark + motion
- Vercel Analytics — Geist + RSC streaming + sparklines
- Stripe Dashboard — financial density done right
- PostHog — open-source product analytics
- Supabase Studio — DB admin done well
- Plausible — minimal web analytics

Open one of these in a browser before you start designing if you've been away from this space for >3 months.
