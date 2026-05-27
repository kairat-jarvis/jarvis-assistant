---
name: dashboard-builder
description: Build interactive dashboards in three modes — single-file HTML (Tailwind + Alpine + ECharts), Next.js + shadcn/ui + Tremor app, or Quarto report. Includes 4 production-grade themes (Claude-light, Zinc-dark, Executive, Realtime-ops), ECharts snippets for 8 chart types, OKLCH palettes, WCAG 2.2 checklist. Use this skill whenever the user mentions dashboards, KPI screens, analytics views, executive reports, monitoring panels, "панель", "дашборд", "аналитика", "отчёт по метрикам", or wants to visualise tabular data interactively — even if they don't explicitly say "dashboard". Default output goes to `/Users/kairat/Claude Code/Excel/Interactiv Dashboard`.
---

# Dashboard Builder

Build production-grade interactive dashboards in three output modes, with four pre-designed themes and an ECharts-first chart library.

## When to Use This Skill

Trigger on:
- "сделай дашборд / панель / аналитику по ..."
- "покажи метрики / KPI / отчёт за ..."
- "monitoring", "ops dashboard", "executive summary"
- User has a CSV/SQL/JSON dataset and asks to "визуализировать"
- User wants to embed analytics in Notion/Telegram/email
- Any mention of charts + interactivity + filters in the same request

Do NOT trigger for:
- One-off static chart (use a Python matplotlib/plotly snippet instead)
- Slide presentation (use `marp-slide`)
- PDF report (use `pptx-official` or LaTeX)

## Default Output Location

**Save all generated dashboards to:** `/Users/kairat/Claude Code/Excel/Interactiv Dashboard/`

Filename pattern: `<topic>_<YYYY-MM-DD>.html` (single-html) or a project subfolder for next-shadcn/quarto modes.

## Quick Start (3 steps)

### Step 1: Pick mode

| User intent | Mode | Output |
|---|---|---|
| "Покажи дашборд / отправь в телеграм / сделай быстро" | **single-html** | one `.html` file, no build |
| "Сделай приложение / админку / нужны фильтры и роутинг" | **next-shadcn** | Next.js project |
| "Отчёт по данным / есть .csv / нужна репродуцируемость" | **quarto** | `.qmd` → static HTML |

When ambiguous → **single-html** (lowest friction, JARVIS-style shareable artifact).

### Step 2: Pick theme

| Theme | Vibe | Best for |
|---|---|---|
| **claude-light** | Cream `#faf9f5`, Inter, Claude-orange `#D97757` | Personal, Notion-embed, project status |
| **zinc-dark** | Near-black `#09090B`, Geist, electric blue accent | Linear/Vercel-style ops & analytics |
| **executive** | Pure white, IBM Plex, near-zero color | Reports for management, audit-grade |
| **realtime-ops** | Black + lime + magenta, dense | n8n/AI monitoring, live streams |

Read `references/trends-2026.md` if user asks for "modern look" — pick zinc-dark by default.

### Step 3: Build

For **single-html**:
1. Read `references/layout-patterns.md` (hero metric + bento grid)
2. Read `references/chart-recipes.md` (ECharts snippets for the chart types you need)
3. Copy the chosen theme from `modes/single-html/theme-*.html`
4. Replace placeholder data with user data (or sample data if none provided)
5. Save to `/Users/kairat/Claude Code/Excel/Interactiv Dashboard/<topic>_<date>.html`
6. Verify by running `python scripts/open_dashboard.py <path>` (opens in browser)

For **next-shadcn**:
- Read `modes/next-shadcn/README.md` for scaffold commands and shadcn block selection.

For **quarto**:
- Read `modes/quarto/README.md` and copy `modes/quarto/template.qmd`.

## Mandatory quality bar

Every dashboard must satisfy (verify before declaring done):

- [ ] **Tabular numerals** on every KPI: `font-variant-numeric: tabular-nums`
- [ ] **Hero metric** top-left with delta % and sparkline
- [ ] **Bento grid** layout, NOT equal-size grid (vary tile spans)
- [ ] **Accessible color contrast** ≥ 4.5:1 body, ≥ 3:1 large text (WCAG 2.2 AA)
- [ ] **Color is never the only signal** in charts (always +shape/label)
- [ ] **`prefers-reduced-motion`** respected (wrap animations)
- [ ] **Mobile breakpoint** at 768px — KPIs stack, charts simplify
- [ ] **Tooltip on every chart**, formatted numbers, currency where relevant
- [ ] **Loaded fonts via preconnect**, ECharts via CDN with SRI hash if possible
- [ ] **Title + favicon** set to dashboard topic, not "Document"

Full checklist: `references/accessibility.md`.

## Reference files (read on demand)

- `references/trends-2026.md` — bento, OKLCH, dark-first, motion principles
- `references/chart-recipes.md` — ECharts snippets for 8 chart types
- `references/layout-patterns.md` — hero+grid, KPI row, slide-over drilldown, filter UX
- `references/accessibility.md` — WCAG 2.2 checklist + APCA preview

## Assets

- `assets/chart-snippets/` — standalone ECharts examples (line, bar, treemap, heatmap, sankey, gauge, geo, candlestick) — copy & inline
- `assets/color-palettes.json` — OKLCH-based palettes per theme

## Scripts

- `scripts/open_dashboard.py <path>` — opens HTML in default browser for visual verification
- `scripts/scaffold_next.sh <project-name>` — scaffolds Next.js + shadcn + Tremor + Recharts project

## Workflow integration

This skill follows the project's superpowers flow (see `CLAUDE.md`):
1. If the dashboard is non-trivial (>3 charts, custom data, reusable) → invoke `brainstorming` first to clarify metrics/audience.
2. For multi-step builds → `writing-plans` before coding.
3. Always finish with `verification-before-completion` (open the file, confirm it renders).

## Anti-patterns (don't do these)

- **Don't** generate Chart.js when ECharts is available — ECharts wins on richness at the same file size.
- **Don't** use `#000` background — use `zinc-950` `#09090B`.
- **Don't** use rainbow palettes — pick ONE accent + neutrals.
- **Don't** equal-grid 3×3 cards — that's PowerBI 2018, not bento.
- **Don't** put filters in a sidebar — top segmented bar or `cmdk` palette.
- **Don't** ship without verifying the file opens and charts render.
