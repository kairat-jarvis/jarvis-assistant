# single-html mode

Generates a single self-contained `.html` file. No build, no install — open in any browser.

## When to use

- Quick artifact for Telegram / Notion-embed / Google Drive sharing
- One-off analytical view, doesn't need updating
- The user just said "сделай дашборд" without specifying a stack
- Personal dashboards, NOT multi-user apps

## How to build

1. **Pick a theme** based on intent:
   - `theme-claude-light.html` — personal projects, JARVIS-style, Notion-embed
   - `theme-zinc-dark.html`    — analytics, SaaS, "modern" look (default for unspecified)
   - `theme-executive.html`    — financial/management report, audit-grade, print-ready
   - `theme-realtime-ops.html` — monitoring, n8n status, AI ops with live updates

2. **Copy the theme file** to the output folder (`/Users/kairat/Claude Code/Excel/Interactiv Dashboard/<topic>_<date>.html`).

3. **Replace placeholders**:
   - `<title>` and `<h1>` — dashboard topic
   - Sample data in the `dash()` Alpine component (`kpi`, `projects`, `events`, etc.) — replace with user data
   - ECharts series data (`series:[{data:...}]`) — replace with real values
   - Labels in Russian/English to match user language

4. **Customise sparingly**:
   - Use `references/chart-recipes.md` snippets if you need a chart type not present
   - Use `references/layout-patterns.md` if you need to add/remove tiles
   - Keep the theme's CSS variables — change values, don't rename

5. **Verify**: run `python ../../scripts/open_dashboard.py <output-path>` — opens in browser.

## Theme matrix

| Theme | Bg | Accent | Font | Best for |
|---|---|---|---|---|
| claude-light | `#faf9f5` cream | `#D97757` orange | Inter | Personal, project portfolios, Notion embed |
| zinc-dark | `#09090B` near-black | `oklch(0.7 0.18 245)` electric blue | Inter + JetBrains Mono | SaaS analytics, modern look |
| executive | `#FFFFFF` white | `#111111` black | IBM Plex Sans + Plex Mono | Management reports, audit, print |
| realtime-ops | `#000000` black | `#84CC16` lime + `#EC4899` magenta | Inter + JetBrains Mono | Monitoring, live streams, AI ops |

## What's bundled in every theme

- Tailwind-free CSS (vanilla, no CDN warning)
- ECharts 5.6 from jsdelivr
- Alpine.js 3.14 from jsdelivr (for state — only where needed)
- Self-hosted Inter/Geist/Plex via Google Fonts preconnect
- WCAG 2.2 focus rings, `prefers-reduced-motion`, mobile breakpoints
- Hero KPI + 4 mini KPIs + 1 trend + 1 secondary + 1 table/list layout
- Slide-over sheet for drill-down (where applicable)
- Responsive 12-col → 6-col → 1-col grid

## Don't do

- Don't bring in Tailwind CDN — it warns in console "for production use the proper build"
- Don't add jQuery — Alpine + vanilla JS handles everything
- Don't use Chart.js — ECharts is richer at same size
- Don't change the theme's font family without updating the preconnect link
- Don't rely on internet for data — embed data inline; only CDNs for libraries
