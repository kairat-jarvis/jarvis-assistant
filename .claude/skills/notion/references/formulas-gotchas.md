# Notion Formula 2.0 — gotchas, error decoder, working-days template

## Error decoder

Every Notion formula rejection shows one of these messages. The real cause is usually not what the message suggests.

| Error message | Actual cause | Fix |
|---|---|---|
| `Type error with formula` (with `let(x, prop("date"), …)`) | `let()` cannot bind a date-property to a variable | Inline `prop("date")` everywhere, do not bind via `let` |
| `Type error with formula` (with `let(x, dateBetween(A, B, "days"), …)`) | `let()` cannot bind a `dateBetween` result either, even though it's a number | Inline the `dateBetween(...)` expression |
| `Type error with formula` (with `dateBetween(parseDate("..."), prop("date"), "days")`) | `parseDate()` and a property date are not comparable types | Replace `parseDate("...")` with `fromTimestamp(ms)` |
| `Type error with formula` (with `style(prop("..."), "b", "blue_background")` or any `style()` whose args/branches transitively depend on a `prop()`) | `style()` via the API only accepts pure-literal arguments — any prop reference (even via a helper boolean formula) poisons the type check | For conditional highlighting, drop `style()` and use text markers (emoji + CAPS). For true per-row styling, use Notion's native conditional formatting in the UI (Team+ plan) — see SKILL.md §Conditional formatting |
| `Parse error with formula` | Unbalanced parens or wrong function arity | Count `(` vs `)`; inspect the tail of the expression |
| `This API is deprecated` (on `GET /v1/databases/{id}` with `Notion-Version: 2022-06-28`) | Mixing an old API version with database property access | Use `Notion-Version: 2025-09-03` and `/v1/data_sources/{ds_id}` |
| `validation_error` with no further info on a PATCH | Property name doesn't exist or type mismatch (e.g. trying to set `select` options on a `status` property) | GET the DB to check exact name + type |
| PATCH to `/v1/databases/{id}` returns 200 but response has no `properties` key | You're using the **old database endpoint** under the new `Notion-Version: 2025-09-03` — schema now lives on data sources | Switch to `PATCH /v1/data_sources/{ds_id}`; that endpoint does return `properties` in the body |

## Why `let()` behaves this way (guess)

Empirically confirmed: `let(x, 5, x + 1)` works, `let(x, 5 + 3, x * 2)` works, nested numeric `let` works, but anything where the bound value touches a property-date or `dateBetween` result raises a type error. The formula 2.0 type-inference inside `let` appears to lose date-flavor tagging and then fail strict checks later.

Practical consequence: **treat `let()` as "numeric literals only"**. Anything involving a date, inline it.

## Why `parseDate` ≠ property date

`parseDate("2026-01-01")` returns a date of an internal "parsed" type. Property dates have a different flavor (carries timezone context from the workspace). `dateBetween` strict-checks the flavor and throws "Type error".

`fromTimestamp(ms)` returns a date compatible with property dates, because both flow through the same Unix-epoch machinery. Always use it for constant holidays / reference dates.

## Working days formula — full template

Goal: count working days (Mon–Fri) between two date properties, subtracting a list of holidays that fall on weekdays. Both endpoints inclusive.

Inputs:
- `START` property (e.g. `prop("1-Начало")`)
- `END` property (e.g. `prop("6-45й Заключение")`)
- A list of holiday dates — generate their UTC-midnight Unix ms via `scripts/compute_holiday_ms.py`

Structure (schematic):

```
if(empty(START) or empty(END), toNumber(""),
  TOTAL - 2*W - SUN - SAT - HOLIDAYS
)
```

Where:
- `TOTAL  = (dateBetween(END, START, "days") + 1)`            # inclusive day count
- `DOW    = day(START)`                                        # Notion: Monday=1; Sun = 0 or 7 depending on convention
- `W      = floor(TOTAL / 7)`                                  # full weeks
- `R      = TOTAL - 7 * W`                                     # remainder days (0..6)
- `SUN    = if((7 - DOW) % 7 < R, 1, 0)`                       # Sunday in remainder?
- `SAT    = if((13 - DOW) % 7 < R, 1, 0)`                      # Saturday in remainder?
- `HOLIDAYS = sum of per-holiday: if(dateBetween(fromTimestamp(ms), START, "days") >= 0 and dateBetween(END, fromTimestamp(ms), "days") >= 0, 1, 0)`

Key constraint: because `let()` breaks with dates, `TOTAL`, `DOW`, `W`, `R`, `SUN`, `SAT` cannot be stored in variables — each must be written out in full everywhere it's used. The resulting expression is ~3 KB of source but Notion stores and computes it fine.

### Weekend math — why it works

Let `R` = remainder days (0 ≤ R ≤ 6) starting at day-of-week `DOW`. The formulas `(7 − DOW) % 7` and `(13 − DOW) % 7` give "days until next Sunday" and "days until next Saturday" respectively. If that distance is less than `R`, the corresponding weekend day lives inside the remainder window.

The expressions are **mod-7 invariant**: whether Notion encodes Sunday as 0 (Sunday=0..Saturday=6) or as 7 (ISO: Monday=1..Sunday=7), the remainder after `% 7` is identical for both mappings of the same real weekday. So the math is correct even if we're uncertain which convention Notion uses.

Since `R ≤ 6`, there's at most one Saturday and one Sunday in the remainder. Whole-week weekend days come from `2 * W`.

### Generating the holidays part

For each holiday date (ISO `YYYY-MM-DD`):
1. Compute Unix ms at UTC midnight.
2. Build the check: `if(dateBetween(fromTimestamp(<ms>), START, "days") >= 0 and dateBetween(END, fromTimestamp(<ms>), "days") >= 0, 1, 0)`
3. Join all checks with ` + `.

See `references/holidays-kz.md` for the RK 2026 list with timestamps pre-computed.

## Rollup vs Relation-in-formula — which to pick

In Notion Formula 2.0, `prop("Relation")` returns a **list of related pages**, and you can walk it: `prop("Relation").map(current.prop("Status"))` reads each linked page's Status. So relation-in-formula is more powerful than it seems.

Still prefer **Rollup** when:
- The aggregation is a native rollup function (count, sum, min, max, earliest/latest date, checkbox percent) — cleaner than formula equivalents and sortable/filterable as a first-class number.
- The rollup is used across many formulas — compute once in the rollup, reference it as a simple number.

Prefer **Relation-in-formula** when:
- You need conditional logic over linked pages (`filter`, `every`, `some`) that rollup doesn't expose.
- You need to format / style the output (rollup can't return styled text).
- You're inside a larger formula already and a rollup would add indirection.

Signs you should switch to rollup if you wrote a formula:
- Your `map(..., current.prop("X"))` is followed by a simple `.sum()` / `.count()` — rollup does this without a formula.
- You reference the same relation-derived aggregate from multiple formulas — DRY via rollup.

## Debugging a failed PATCH — step-by-step

1. Reproduce with a **minimal** expression — strip to 1 `if()` and 1 `dateBetween`. Does that succeed?
2. Add ONE piece at a time. The error switches from "Parse" to "Type" when parens are OK but types aren't.
3. When you hit a type error, the last piece you added is the suspect. Usually: `let` with a date, or `parseDate` with a prop.
4. Read the DB back and confirm the stored expression — sometimes Notion silently rewrites it.

## Parens count cheat-sheet

Each `let(var, value, body)` costs 1 open + 1 close. Each `if(cond, then, else)` costs 1 open + 1 close. Each `prop(...)`, `empty(...)`, `dateBetween(...)`, `floor(...)`, `day(...)`, `fromTimestamp(...)` is self-balanced. Count opens and closes — they must be equal. A parse error with correctly-typed atoms is almost always a parens issue.
