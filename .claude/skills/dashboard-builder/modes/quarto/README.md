# quarto mode

Generates a static HTML dashboard from a `.qmd` (Quarto Markdown) file. Use when the user has:
- A `.csv`, `.xlsx`, `.parquet`, or SQL data source
- Python/R/Julia in the workflow
- Need for reproducibility ("re-render when data updates")
- Wants version-controlled `.qmd` source

For interactive web app → use `next-shadcn`. For one-off shareable HTML → use `single-html`.

## Prerequisites

```bash
# Install Quarto CLI (if not present)
# macOS:    brew install --cask quarto
# Windows:  winget install --id Posit.Quarto
# Verify:   quarto --version  (should be 1.5+)

# Python deps for the template:
pip install pandas plotly itables
```

## Build

1. Copy `template.qmd` to the output folder.
2. Edit the YAML header (title, dashboard layout).
3. Replace data-loading cells with the user's data path/SQL query.
4. Render:

```bash
quarto render template.qmd
```

Output: `template.html` in the same folder.

## Layout primitives

Quarto Dashboards use `##` (column/row) and `###` (card) headings:

```markdown
# {.toolbar}                    # filter bar at top

## Row {height=20%}
### {.value-box}                # KPI card
[code chunk producing dict]
### {.value-box}
### {.value-box}

## Row
### Trend chart                 # regular card
[code chunk producing plot]
### Side panel
```

## Plot library

Default: **Plotly Python** (interactive, plays well with Quarto). For ECharts in Quarto, use the `pyecharts` package and embed via `from pyecharts.charts import Line; line.render_notebook()`.

For static print-grade charts: matplotlib with `seaborn-v0_8` style.

## When to use a Quarto dashboard

| Scenario | Quarto Dashboard | Other |
|---|---|---|
| Reproducible analyst report | ✅ | |
| Auto re-render via cron | ✅ | |
| User uploads CSV → see dashboard | ❌ | Use single-html or Streamlit |
| Real-time updates | ❌ | Use realtime-ops single-html |
| Multiple pages with auth | ❌ | Use next-shadcn |

## Don't do

- Don't use Quarto for interactive forms or write-back — it's a static renderer
- Don't embed huge data inline; use external `.parquet` and load on render
- Don't fight the row/column layout — it's a CSS grid; if you need pixel control, switch modes
