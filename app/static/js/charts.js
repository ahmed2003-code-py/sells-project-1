const CHART_COLORS = {
  brand: '#45f1bb',
  brand2: '#6df4c8',
  accent: '#c6bfff',
  accent2: '#d5cfff',
  info: '#5bc8ff',
  warning: '#ffb84d',
  danger: '#ff6b8a',
  muted: '#6e7178',
  text: '#e3e2e6',
  textMuted: '#bacac1',
  bg: 'transparent',
  grid: 'rgba(186,202,193,0.06)',
};

// Wait for Plotly to load (up to 5 seconds), then call the drawer function.
function _waitForPlotly(fn, attempt = 0) {
  if (typeof Plotly !== 'undefined') { fn(); return; }
  if (attempt >= 50) { console.warn('Plotly CDN failed to load'); return; }
  setTimeout(() => _waitForPlotly(fn, attempt + 1), 100);
}

const PALETTE = [
  CHART_COLORS.brand,
  CHART_COLORS.accent,
  CHART_COLORS.info,
  CHART_COLORS.warning,
  CHART_COLORS.danger,
  CHART_COLORS.brand2,
  CHART_COLORS.accent2,
];

function chartLayout(opts = {}) {
  const isRTL = document.documentElement.dir === 'rtl';
  return {
    paper_bgcolor: 'transparent',
    plot_bgcolor: 'transparent',
    font: {
      family: isRTL ? 'IBM Plex Sans Arabic, system-ui, sans-serif' : 'Inter, system-ui, sans-serif',
      color: CHART_COLORS.textMuted,
      size: 12,
    },
    margin: { t: 10, r: 20, b: 40, l: 50, ...opts.margin },
    xaxis: {
      gridcolor: CHART_COLORS.grid,
      zeroline: false,
      color: CHART_COLORS.textMuted,
      tickfont: { size: 11 },
      ...opts.xaxis,
    },
    yaxis: {
      gridcolor: CHART_COLORS.grid,
      zeroline: false,
      color: CHART_COLORS.textMuted,
      tickfont: { size: 11 },
      ...opts.yaxis,
    },
    showlegend: opts.showlegend !== false,
    legend: {
      font: { color: CHART_COLORS.text, size: 11 },
      bgcolor: 'transparent',
      ...opts.legend,
    },
    hoverlabel: {
      bgcolor: '#1f1f23',
      bordercolor: 'rgba(186,202,193,0.12)',
      font: { color: '#e3e2e6', size: 12 },
    },
    ...opts.layout,
  };
}

const chartConfig = {
  displayModeBar: false,
  responsive: true,
  locale: 'en',
};

function drawBarChart(containerId, data, options = {}) {
  const el = document.getElementById(containerId);
  if (!el) return;

  const trace = {
    type: 'bar',
    x: data.x,
    y: data.y,
    marker: {
      color: data.colors || PALETTE[0],
      line: { width: 0 },
    },
    text: data.labels || data.y.map(v => typeof v === 'number' ? v.toFixed(1) : v),
    textposition: 'outside',
    textfont: { color: CHART_COLORS.text, size: 11 },
    hovertemplate: (options.hovertemplate || '<b>%{x}</b><br>%{y}<extra></extra>'),
  };

  const layout = chartLayout({
    xaxis: { tickangle: options.xangle || 0 },
    showlegend: false,
    ...options,
  });

  _waitForPlotly(() => Plotly.newPlot(el, [trace], layout, chartConfig));
}

function drawHorizontalBar(containerId, data, options = {}) {
  const el = document.getElementById(containerId);
  if (!el) return;

  const trace = {
    type: 'bar',
    orientation: 'h',
    x: data.x,
    y: data.y,
    marker: {
      color: data.colors || PALETTE[0],
      line: { width: 0 },
    },
    text: data.labels || data.x.map(v => typeof v === 'number' ? v.toFixed(1) + '%' : v),
    textposition: 'outside',
    textfont: { color: CHART_COLORS.text, size: 11 },
    hovertemplate: '<b>%{y}</b><br>%{x}<extra></extra>',
  };

  const layout = chartLayout({
    showlegend: false,
    margin: { l: 120, r: 60, t: 20, b: 40 },
    ...options,
  });

  _waitForPlotly(() => Plotly.newPlot(el, [trace], layout, chartConfig));
}

function drawDonut(containerId, data, options = {}) {
  const el = document.getElementById(containerId);
  if (!el) return;

  const trace = {
    type: 'pie',
    labels: data.labels,
    values: data.values,
    hole: 0.6,
    marker: {
      colors: data.colors || PALETTE,
      line: { color: '#121316', width: 2 },
    },
    textinfo: 'label+percent',
    textfont: { size: 12, color: CHART_COLORS.text },
    hovertemplate: '<b>%{label}</b><br>%{value} (%{percent})<extra></extra>',
  };

  const layout = chartLayout({
    showlegend: true,
    margin: { t: 20, r: 20, b: 20, l: 20 },
    annotations: options.centerText ? [{
      text: options.centerText,
      showarrow: false,
      font: { size: 18, color: CHART_COLORS.text, family: 'inherit' },
    }] : [],
    ...options,
  });

  _waitForPlotly(() => Plotly.newPlot(el, [trace], layout, chartConfig));
}

function drawLineChart(containerId, series, options = {}) {
  const el = document.getElementById(containerId);
  if (!el) return;

  const traces = series.map((s, i) => ({
    type: 'scatter',
    mode: 'lines+markers',
    name: s.name,
    x: s.x,
    y: s.y,
    line: { color: s.color || PALETTE[i % PALETTE.length], width: 3, shape: 'spline', smoothing: 1.0 },
    marker: { size: 8, color: s.color || PALETTE[i % PALETTE.length] },
    fill: s.fill ? 'tozeroy' : 'none',
    fillcolor: s.fill ? (s.color || PALETTE[i % PALETTE.length]).replace(')', ', 0.1)').replace('rgb', 'rgba') : undefined,
    hovertemplate: '<b>%{x}</b><br>%{y}<extra></extra>',
  }));

  const layout = chartLayout(options);
  _waitForPlotly(() => Plotly.newPlot(el, traces, layout, chartConfig));
}

function drawGauge(containerId, value, options = {}) {
  const el = document.getElementById(containerId);
  if (!el) return;

  const color = value >= 75 ? CHART_COLORS.brand
              : value >= 55 ? CHART_COLORS.warning
              : CHART_COLORS.danger;

  const trace = {
    type: 'indicator',
    mode: 'gauge+number',
    value: value,
    number: { suffix: '%', font: { color: CHART_COLORS.text, size: 32 } },
    gauge: {
      axis: { range: [0, 100], tickcolor: CHART_COLORS.textMuted, tickfont: { size: 10 } },
      bar: { color: color, thickness: 0.8 },
      bgcolor: '#292a2d',
      borderwidth: 0,
      steps: [
        { range: [0, 25], color: 'rgba(255, 107, 138, 0.18)' },
        { range: [25, 55], color: 'rgba(255, 184, 77, 0.12)' },
        { range: [55, 100], color: 'rgba(69, 241, 187, 0.12)' },
      ],
      threshold: {
        line: { color: CHART_COLORS.text, width: 2 },
        thickness: 0.9,
        value: options.target || 75,
      },
    },
  };

  const layout = chartLayout({
    margin: { t: 20, r: 20, b: 20, l: 20 },
    showlegend: false,
    ...options,
  });

  _waitForPlotly(() => Plotly.newPlot(el, [trace], layout, chartConfig));
}

function drawRadarChart(containerId, data, options = {}) {
  const el = document.getElementById(containerId);
  if (!el) return;

  const trace = {
    type: 'scatterpolar',
    r: data.values,
    theta: data.labels,
    fill: 'toself',
    fillcolor: 'rgba(69, 241, 187, 0.15)',
    line: { color: CHART_COLORS.brand, width: 2 },
    marker: { size: 6, color: CHART_COLORS.brand },
    hovertemplate: '<b>%{theta}</b><br>%{r}%<extra></extra>',
  };

  const layout = {
    paper_bgcolor: 'transparent',
    plot_bgcolor: 'transparent',
    font: { family: 'inherit', color: CHART_COLORS.textMuted, size: 11 },
    margin: { t: 20, r: 40, b: 20, l: 40 },
    showlegend: false,
    polar: {
      bgcolor: 'transparent',
      radialaxis: {
        visible: true,
        range: [0, 100],
        gridcolor: CHART_COLORS.grid,
        tickfont: { size: 10 },
      },
      angularaxis: {
        gridcolor: CHART_COLORS.grid,
        tickfont: { size: 11 },
      },
    },
    ...options,
  };

  _waitForPlotly(() => Plotly.newPlot(el, [trace], layout, chartConfig));
}

function drawStackedBar(containerId, series, xLabels, options = {}) {
  const el = document.getElementById(containerId);
  if (!el) return;

  const traces = series.map((s, i) => ({
    type: 'bar',
    name: s.name,
    x: xLabels,
    y: s.values,
    marker: { color: s.color || PALETTE[i % PALETTE.length] },
    hovertemplate: '<b>%{x}</b><br>' + s.name + ': %{y}<extra></extra>',
  }));

  const layout = chartLayout({
    barmode: 'stack',
    ...options,
  });

  _waitForPlotly(() => Plotly.newPlot(el, traces, layout, chartConfig));
}

function scoreColorHex(pct) {
  return pct >= 75 ? CHART_COLORS.brand : pct >= 55 ? CHART_COLORS.warning : CHART_COLORS.danger;
}

window.Charts = {
  drawBarChart,
  drawHorizontalBar,
  drawDonut,
  drawLineChart,
  drawGauge,
  drawRadarChart,
  drawStackedBar,
  scoreColorHex,
  COLORS: CHART_COLORS,
  PALETTE,
};
