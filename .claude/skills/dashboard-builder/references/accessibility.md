# Accessibility Checklist (WCAG 2.2 AA + APCA preview)

Every dashboard must pass this list before declaring done. Use it as a final review before saving the file.

## Colour & contrast

- [ ] Body text ≥ **4.5:1** against background (use https://webaim.org/resources/contrastchecker/)
- [ ] Large text (≥ 18.66 px bold or ≥ 24 px) ≥ **3:1**
- [ ] UI components and graphical objects ≥ **3:1**
- [ ] Colour is **never** the only signal. Always pair with: shape, label, icon, pattern, position
  - Bad: red bars vs green bars
  - Good: red bars labeled "DOWN ↓", green bars labeled "UP ↑"
- [ ] Test with grayscale (CSS `filter: grayscale(1)`) — chart should still be readable

## Keyboard & focus

- [ ] Every interactive element reachable via Tab
- [ ] Focus indicator visible: `outline: 2px solid var(--accent); outline-offset: 2px`
- [ ] Tab order is logical (DOM order matches visual order)
- [ ] Esc closes modals/sheets
- [ ] No keyboard traps

## Targets

- [ ] All click/tap targets ≥ **24×24 px** (WCAG 2.2 SC 2.5.8 Target Size Minimum)
- [ ] Spacing between targets ≥ 8px

## Motion

- [ ] All animations respect `prefers-reduced-motion`:

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}
```

```js
// In ECharts init
if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
  option.animation = false;
}
```

- [ ] No auto-playing video/audio
- [ ] No flashing > 3 times/second

## Semantic HTML

- [ ] `<header>`, `<main>`, `<aside>`, `<section>`, `<article>` used appropriately
- [ ] One `<h1>` per page (dashboard title)
- [ ] Heading hierarchy is logical (h1 → h2 → h3, no skipping)
- [ ] Buttons are `<button>`, links are `<a>` — never `<div onclick>`
- [ ] Forms have `<label>` for every input

## ARIA (only when semantic HTML can't express it)

- [ ] Charts have `role="img"` and `aria-label="<descriptive text>"`
- [ ] Live regions for streaming data: `aria-live="polite"`
- [ ] Hidden visual decoration: `aria-hidden="true"`
- [ ] Custom controls (cmdk palette) use `role="combobox"` / `role="listbox"` correctly

## Charts specifically

- [ ] Chart has a text alternative (data table accessible nearby OR `aria-label` summarising the trend)
- [ ] Tooltip content is keyboard-accessible (focus on data points)
- [ ] Axis labels have sufficient contrast (often missed — check axis colour against background)
- [ ] Don't rely solely on hover for critical info — show key values inline

## Screen reader sanity test

Test with macOS VoiceOver (`Cmd+F5`) or Windows Narrator (`Win+Ctrl+Enter`):
- Page title is read
- Heading structure makes sense
- KPI tiles read as "Revenue, $284,500, up 12.4 percent vs last week"
- Charts announce their summary (not just "graphic")

## APCA (WCAG 3 preview)

APCA is the new contrast model in WCAG 3 working draft. Different from WCAG 2 ratio — uses Lc (Lightness contrast) values.

| Use case | Min APCA Lc |
|---|---|
| Body text < 18 px | 75 |
| Headings 24–32 px | 60 |
| Large text > 32 px | 45 |
| Non-text UI elements | 30 |

Check: https://apcacontrast.com/ — paste your colour pairs.

If your design passes WCAG 2.2 AA AND APCA Lc ≥ 60 for body text, you're future-proof.

## Final verification

```bash
# Lighthouse accessibility audit (local file)
npx lighthouse "file:///path/to/dashboard.html" --only-categories=accessibility --view
```

Score should be **≥ 95**. Below 90, go back and fix.
