# Layout Patterns

## Default: Hero + Bento Grid

```
┌──────────────────────────┬──────────┬──────────┐
│                          │  KPI 2   │  KPI 3   │
│  HERO METRIC             │ value    │ value    │
│  big number              │ ▁▃▅▇▅    │ ▁▂▃▅▆    │
│  delta% sparkline        ├──────────┼──────────┤
│                          │  KPI 4   │  KPI 5   │
├──────────────────────────┴──────────┴──────────┤
│           TREND CHART (full width)             │
├────────────────┬───────────────────────────────┤
│  TABLE / LIST  │   SECONDARY CHART             │
│                │   (donut / treemap / heatmap) │
└────────────────┴───────────────────────────────┘
```

CSS template:

```css
.dashboard {
  display: grid;
  grid-template-columns: repeat(12, 1fr);
  grid-auto-rows: minmax(140px, auto);
  gap: 16px;
  padding: 24px;
}
.tile { background: var(--card); border: 1px solid var(--border); border-radius: 16px; padding: 20px; }
.hero       { grid-column: span 6; grid-row: span 2; }
.kpi        { grid-column: span 3; }
.trend      { grid-column: span 12; grid-row: span 2; }
.table      { grid-column: span 5; grid-row: span 3; }
.secondary  { grid-column: span 7; grid-row: span 3; }

@media (max-width: 1024px) {
  .hero, .trend, .table, .secondary { grid-column: span 12; }
  .kpi { grid-column: span 6; }
}
@media (max-width: 640px) {
  .kpi { grid-column: span 12; }
}
```

## KPI tile anatomy

```html
<div class="tile kpi">
  <div class="kpi-label">Revenue</div>
  <div class="kpi-value">$284.5K</div>
  <div class="kpi-delta positive">
    <svg>↑</svg> +12.4%
    <span class="muted">vs last week</span>
  </div>
  <div class="kpi-spark" id="spark-revenue"></div>
</div>
```

```css
.kpi-label   { font-size: 12px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em; }
.kpi-value   { font-size: 2.25rem; font-weight: 600; letter-spacing: -0.02em;
               font-variant-numeric: tabular-nums; margin: 8px 0 4px; }
.kpi-delta   { display: flex; align-items: center; gap: 4px; font-size: 13px; }
.kpi-delta.positive { color: #22C55E; }
.kpi-delta.negative { color: #EF4444; }
.kpi-spark   { height: 40px; margin-top: 12px; }
```

## Hero metric anatomy

Same as KPI but bigger: value at 4–5rem, sparkline at 80px height, delta with bigger arrow icon, optional small annotation ("trending up over last 30 days").

## Filter bar (top, segmented)

```html
<div class="filter-bar">
  <div class="segmented">
    <button class="active">7d</button>
    <button>30d</button>
    <button>90d</button>
    <button>1y</button>
    <button>All</button>
  </div>
  <div class="filter-group">
    <select><option>All regions</option></select>
    <select><option>All products</option></select>
  </div>
  <div class="actions">
    <button class="cmdk">⌘K</button>
    <button class="export">Export</button>
  </div>
</div>
```

```css
.filter-bar { display: flex; gap: 12px; align-items: center; padding: 16px 24px;
              border-bottom: 1px solid var(--border); }
.segmented { display: inline-flex; background: var(--bg-secondary); border-radius: 8px; padding: 4px; }
.segmented button { background: transparent; border: 0; padding: 6px 14px; border-radius: 6px;
                    font-size: 13px; color: var(--text-muted); cursor: pointer; }
.segmented button.active { background: var(--card); color: var(--text-primary); box-shadow: 0 1px 3px var(--shadow); }
```

## Drill-down sheet (right side)

```html
<aside class="sheet" x-show="selected" x-transition.duration.250ms>
  <header>
    <h3>Details</h3>
    <button @click="selected = null">×</button>
  </header>
  <div class="sheet-body">…</div>
</aside>
```

```css
.sheet {
  position: fixed; top: 0; right: 0; width: min(480px, 90vw); height: 100vh;
  background: var(--card); border-left: 1px solid var(--border);
  box-shadow: -8px 0 32px rgba(0,0,0,0.2); z-index: 50;
  transform: translateX(0); transition: transform 0.25s ease;
}
.sheet[hidden] { transform: translateX(100%); }
```

URL state sync (vanilla JS):
```js
function updateURL(params) {
  const url = new URL(window.location);
  Object.entries(params).forEach(([k, v]) => v ? url.searchParams.set(k, v) : url.searchParams.delete(k));
  history.replaceState(null, '', url);
}
```

## Skeleton loaders

```css
.skeleton {
  background: linear-gradient(90deg, var(--bg-secondary) 0%, var(--border-light) 50%, var(--bg-secondary) 100%);
  background-size: 200% 100%; animation: shimmer 1.5s infinite;
  border-radius: 8px;
}
@keyframes shimmer { 0% { background-position: 200% 0 } 100% { background-position: -200% 0 } }
```

## Mobile breakpoint behaviour

| Element | Desktop | Mobile (<768px) |
|---|---|---|
| KPI grid | 4 columns | horizontal snap-scroll, full-width cards |
| Filter bar | Top horizontal | Sticky bottom-sheet (Vaul-style) |
| Multi-series chart | All series | Single primary series (toggle to add) |
| Sidebar | Icon rail | Hidden, hamburger drawer |
| Drill-down sheet | Right slide-over | Bottom slide-up, full height |

## Cmd-K palette (optional, polished)

Use [cmdk](https://cmdk.paco.me/) for React or roll a vanilla version with dialog + input + list. Keyboard:
- `Cmd/Ctrl+K` opens
- `↑↓` navigates
- `Enter` selects
- `Esc` closes

Scope: navigation, filters, "go to row X", export, theme toggle.
