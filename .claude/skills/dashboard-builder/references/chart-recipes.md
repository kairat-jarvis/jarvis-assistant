# ECharts Recipes

ECharts 5.6 (Apache 2.0) is the default chart engine. CDN: `https://cdn.jsdelivr.net/npm/echarts@5.6.0/dist/echarts.min.js`.

## Initialisation pattern (always use this)

```js
const el = document.getElementById('chart-id');
const chart = echarts.init(el, null, { renderer: 'canvas', useDirtyRect: true });
chart.setOption(option);

// Resize on window/container change
const ro = new ResizeObserver(() => chart.resize());
ro.observe(el);

// Honour reduced motion
if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
  option.animation = false;
}
```

## Theme tokens (apply to all charts)

```js
const theme = {
  // Match these to your dashboard's CSS vars
  textColor: '#E4E4E7',           // body
  axisColor: '#A1A1AA',           // muted
  splitLine: 'rgba(255,255,255,0.05)',
  accent:    '#3B82F6',           // electric blue
  accent2:   '#8B5CF6',           // violet (paired)
  series:    ['#3B82F6','#8B5CF6','#EC4899','#84CC16','#F59E0B','#06B6D4'],
  bg:        'transparent'
};

// Common option fragments
const commonGrid = { left: 8, right: 8, top: 24, bottom: 24, containLabel: true };
const commonAxis = {
  axisLine:  { lineStyle: { color: theme.axisColor, opacity: 0.3 } },
  axisTick:  { show: false },
  axisLabel: { color: theme.axisColor, fontSize: 11 },
  splitLine: { lineStyle: { color: theme.splitLine } }
};
const commonTooltip = {
  trigger: 'axis',
  backgroundColor: 'rgba(24,24,27,0.95)',
  borderColor: 'rgba(255,255,255,0.1)',
  borderWidth: 1,
  textStyle: { color: '#FAFAFA', fontSize: 12 },
  extraCssText: 'backdrop-filter: blur(8px); border-radius: 8px;'
};
```

## 1. Sparkline (KPI tile)

```js
{
  grid: { left: 0, right: 0, top: 0, bottom: 0 },
  xAxis: { type: 'category', show: false, data: dates },
  yAxis: { type: 'value', show: false, scale: true },
  tooltip: { ...commonTooltip, formatter: (p) => `${p[0].name}: <b>${p[0].value}</b>` },
  series: [{
    type: 'line', data: values, smooth: true, symbol: 'none',
    lineStyle: { color: theme.accent, width: 2 },
    areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
      { offset: 0, color: theme.accent + 'AA' },
      { offset: 1, color: theme.accent + '00' }
    ])}
  }]
}
```

## 2. Line + area (trend chart)

```js
{
  grid: commonGrid,
  tooltip: commonTooltip,
  legend: { textStyle: { color: theme.textColor }, top: 0, right: 0, icon: 'circle' },
  xAxis: { ...commonAxis, type: 'category', boundaryGap: false, data: dates },
  yAxis: { ...commonAxis, type: 'value' },
  series: seriesArray.map((s, i) => ({
    name: s.name, type: 'line', data: s.values, smooth: true, symbol: 'none',
    lineStyle: { color: theme.series[i], width: 2 },
    areaStyle: { color: theme.series[i] + '20' }
  }))
}
```

## 3. Bar (categorical)

```js
{
  grid: commonGrid,
  tooltip: commonTooltip,
  xAxis: { ...commonAxis, type: 'category', data: categories },
  yAxis: { ...commonAxis, type: 'value' },
  series: [{
    type: 'bar', data: values,
    itemStyle: {
      color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
        { offset: 0, color: theme.accent },
        { offset: 1, color: theme.accent + '88' }
      ]),
      borderRadius: [6, 6, 0, 0]
    },
    barMaxWidth: 32
  }]
}
```

## 4. Donut (composition)

```js
{
  tooltip: { ...commonTooltip, trigger: 'item', formatter: '{b}: <b>{c}</b> ({d}%)' },
  legend: { orient: 'vertical', left: 'right', top: 'middle', textStyle: { color: theme.textColor } },
  series: [{
    type: 'pie', radius: ['55%', '80%'], center: ['35%', '50%'],
    avoidLabelOverlap: true, label: { show: false }, labelLine: { show: false },
    itemStyle: { borderColor: '#09090B', borderWidth: 2, borderRadius: 4 },
    data: items.map((it, i) => ({ name: it.name, value: it.value, itemStyle: { color: theme.series[i] }}))
  }]
}
```

## 5. Heatmap (calendar / matrix)

```js
{
  tooltip: { ...commonTooltip, position: 'top' },
  grid: { ...commonGrid, height: '70%' },
  xAxis: { ...commonAxis, type: 'category', data: hours,   splitArea: { show: true } },
  yAxis: { ...commonAxis, type: 'category', data: days,    splitArea: { show: true } },
  visualMap: {
    min: 0, max: maxVal, calculable: true, orient: 'horizontal', left: 'center', bottom: 0,
    inRange: { color: ['#1E293B', theme.accent] },
    textStyle: { color: theme.textColor }
  },
  series: [{
    type: 'heatmap', data: data,        // [[xIdx, yIdx, value], ...]
    label: { show: false },
    emphasis: { itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.5)' }}
  }]
}
```

## 6. Treemap (hierarchical proportions)

```js
{
  tooltip: { ...commonTooltip, formatter: '{b}: <b>{c}</b>' },
  series: [{
    type: 'treemap', data: tree, roam: false,
    breadcrumb: { show: false },
    label: { color: '#FAFAFA', fontSize: 12, fontWeight: 500 },
    upperLabel: { show: false },
    itemStyle: { gapWidth: 2, borderColor: '#09090B', borderRadius: 4 },
    levels: [
      { itemStyle: { borderWidth: 0, gapWidth: 4 }},
      { colorSaturation: [0.3, 0.6], itemStyle: { borderColorSaturation: 0.7, gapWidth: 2 }}
    ]
  }]
}
```

## 7. Sankey (flow)

```js
{
  tooltip: { ...commonTooltip, trigger: 'item' },
  series: [{
    type: 'sankey',
    data: nodes,                          // [{name: 'A'}, {name: 'B'}]
    links: links,                         // [{source: 'A', target: 'B', value: 10}]
    nodeAlign: 'left',
    itemStyle: { borderWidth: 0, color: theme.accent },
    lineStyle: { color: 'gradient', curveness: 0.5, opacity: 0.5 },
    label: { color: theme.textColor, fontSize: 11 }
  }]
}
```

## 8. Gauge (single-metric % / progress)

```js
{
  series: [{
    type: 'gauge', startAngle: 200, endAngle: -20, min: 0, max: 100, radius: '95%',
    progress: { show: true, width: 18, itemStyle: { color: theme.accent }},
    axisLine: { lineStyle: { width: 18, color: [[1, 'rgba(255,255,255,0.08)']] }},
    pointer: { show: false },
    axisTick: { show: false }, splitLine: { show: false }, axisLabel: { show: false },
    detail: {
      valueAnimation: true, fontSize: 36, fontWeight: 600, color: theme.textColor,
      offsetCenter: [0, 0], formatter: '{value}%'
    },
    data: [{ value: percent }]
  }]
}
```

## 9. Candlestick (financial — bonus)

```js
{
  grid: commonGrid, tooltip: commonTooltip,
  xAxis: { ...commonAxis, type: 'category', data: dates },
  yAxis: { ...commonAxis, type: 'value', scale: true },
  series: [{
    type: 'candlestick', data: ohlc,        // [[open, close, low, high], ...]
    itemStyle: {
      color: '#22C55E', color0: '#EF4444',           // up / down
      borderColor: '#22C55E', borderColor0: '#EF4444'
    }
  }]
}
```

## Number formatting

Always format big numbers:

```js
const fmt = (n) => {
  if (n >= 1e9) return (n / 1e9).toFixed(1) + 'B';
  if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M';
  if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K';
  return n.toString();
};
// Apply in axisLabel.formatter or tooltip.formatter
```

## Performance tips

- Datasets > 10k points → set `large: true, largeThreshold: 2000` on series.
- 100k+ points → switch `renderer: 'canvas'` (default) with `progressive: 5000`.
- Real-time → use `chart.appendData({ seriesIndex: 0, data: newPoints })`, not full setOption.
