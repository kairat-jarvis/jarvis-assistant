# next-shadcn mode

Generates a full Next.js 15 app with shadcn/ui + Tremor + Recharts. Use when the user needs:
- Auth, multi-page navigation, persistent state
- Multiple users / shareable URLs / API-backed data
- A real product, not a one-off artifact
- Vercel deployment

For one-off shareable dashboards → use `single-html` instead.

## Scaffold

Run from terminal in the parent of the new project folder:

```bash
bash ../../scripts/scaffold_next.sh <project-name>
```

This will:
1. `npx create-next-app@latest` with TypeScript + Tailwind + App Router + src/ + import alias `@/*`
2. `npx shadcn@latest init` with default options + neutral base color + zinc/slate scheme
3. `npx shadcn@latest add` core components: button, card, dialog, sheet, dropdown-menu, input, table, tabs, badge, separator, sonner, command, chart
4. Install Tremor: `npm i @tremor/react`
5. Install Recharts (already comes via shadcn chart): verify `npm i recharts`
6. Install icons: `npm i lucide-react`
7. Install motion: `npm i motion`
8. Install nuqs (URL state): `npm i nuqs`
9. Install Vaul (mobile bottom-sheet): `npm i vaul`
10. Install date-fns: `npm i date-fns`

## Recommended file layout

```
src/
├── app/
│   ├── layout.tsx            # root, fonts (Geist), theme provider
│   ├── page.tsx              # main dashboard (RSC)
│   ├── (sections)/
│   │   ├── revenue/page.tsx
│   │   ├── users/page.tsx
│   │   └── ops/page.tsx
│   └── api/
│       └── metrics/route.ts  # data endpoints
├── components/
│   ├── ui/                   # shadcn output — DO NOT modify
│   ├── tiles/
│   │   ├── kpi-tile.tsx      # reusable KPI with sparkline
│   │   ├── trend-tile.tsx    # line chart wrapper
│   │   └── table-tile.tsx
│   ├── filter-bar.tsx
│   ├── command-palette.tsx   # cmdk
│   └── sheet-drilldown.tsx
└── lib/
    ├── format.ts             # number formatters with tabular-nums
    ├── theme.ts              # OKLCH palette
    └── data.ts               # data access (Supabase, fetch, etc.)
```

## Block selection (shadcn/ui blocks)

shadcn ships 30+ dashboard blocks at https://ui.shadcn.com/blocks. Pick by intent:

| User intent | Block |
|---|---|
| Generic SaaS dashboard | `dashboard-01` |
| Analytics with charts | `dashboard-02` |
| Sidebar variants | `sidebar-01` … `sidebar-16` |
| Login/signup | `login-01` to `login-05` |

To add a block:
```bash
npx shadcn@latest add dashboard-01
```

This drops a complete page into your app. Customise from there — don't fight the block's structure.

## Theme tokens (apply globally)

In `src/app/globals.css`, override shadcn's default theme to match the dashboard-builder palette:

```css
@layer base {
  :root {
    --background: 0 0% 100%;
    --foreground: 240 10% 3.9%;
    /* shadcn neutral defaults */
  }
  .dark {
    --background: 240 10% 3.9%;          /* zinc-950 */
    --foreground: 0 0% 98%;
    --primary:    214 100% 60%;          /* electric blue */
    --primary-foreground: 0 0% 98%;
    /* ... */
  }
  * { font-variant-numeric: tabular-nums; }   /* CRITICAL: tabular nums by default */
}
```

## Default chart engine

In Next.js mode, prefer **Recharts** (via shadcn `<ChartContainer>` wrapper) for React-native composition. Use ECharts only for high-density (>10k points) or chart types Recharts can't do (sankey, treemap, geo).

```tsx
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import { LineChart, Line, XAxis, YAxis } from "recharts";

const config = { revenue: { label: "Revenue", color: "hsl(var(--primary))" } };

<ChartContainer config={config} className="h-[280px]">
  <LineChart data={data}>
    <XAxis dataKey="month" />
    <YAxis />
    <ChartTooltip content={<ChartTooltipContent />} />
    <Line dataKey="revenue" stroke="var(--color-revenue)" strokeWidth={2} dot={false} />
  </LineChart>
</ChartContainer>
```

For ECharts in React: use `echarts-for-react` package, or render imperatively in `useEffect` with a ref.

## URL state with nuqs

```tsx
import { useQueryState } from 'nuqs';

const [period, setPeriod] = useQueryState('period', { defaultValue: '30d' });
const [selected, setSelected] = useQueryState('selected');
```

Drill-down sheet opens when `selected` is set. URL stays `?period=30d&selected=42`.

## Deployment

```bash
vercel --prod
```

Or use the `vercel:deploy` skill if available.

## Don't do

- Don't customise shadcn's `components/ui/*` files — re-add them via CLI to update
- Don't mix Tremor and shadcn primitives in the same tile — pick one per tile
- Don't put data fetching in client components — use RSC + Server Actions
- Don't disable Tailwind's `tabular-nums` utility — apply it everywhere KPIs render
- Don't ship without `prefers-reduced-motion` wrapping motion components
