/* NSW Housing Supply Pipeline Dashboard — Chart rendering
   Uses Chart.js 4.4.4 with the validated dataviz palette */

(function() {
  'use strict';

  // --- Palette ---
  const LIGHT = {
    series: ['#2a78d6','#eb6834','#1baf7a','#eda100','#e87ba4','#008300'],
    text:   '#0b0b0b', secondary: '#52514e', muted: '#898781',
    grid:   '#e1e0d9', surface: '#fcfcfb',
    good: '#0ca30c', serious: '#ec835a', critical: '#d03b3b',
  };
  const DARK = {
    series: ['#3987e5','#d95926','#199e70','#c98500','#d55181','#008300'],
    text:   '#f0efec', secondary: '#c3c2b7', muted: '#898781',
    grid:   '#2c2c2a', surface: '#1a1a19',
    good: '#0ca30c', serious: '#ec835a', critical: '#d03b3b',
  };

  function getPalette() {
    const dm = document.documentElement.getAttribute('data-theme');
    if (dm === 'dark') return DARK;
    if (dm === 'light') return LIGHT;
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? DARK : LIGHT;
  }

  // --- Compact numbers ---
  function compact(n) {
    if (n >= 1e6) return (n / 1e6).toFixed(1).replace(/\.0$/, '') + 'M';
    if (n >= 1e3) return (n / 1e3).toFixed(1).replace(/\.0$/, '') + 'K';
    return n.toLocaleString();
  }

  // --- Common chart defaults ---
  function baseOpts(pal, title) {
    return {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        title: { display: !!title, text: title || '', color: pal.text,
                 font: { size: 14, weight: '600', family: 'system-ui' }, padding: { bottom: 12 } },
        legend: { position: 'bottom', labels: { color: pal.secondary, usePointStyle: true,
                  pointStyle: 'rectRounded', padding: 16,
                  font: { size: 12, family: 'system-ui' } } },
        tooltip: { backgroundColor: pal.surface, titleColor: pal.text,
                   bodyColor: pal.secondary, borderColor: pal.grid, borderWidth: 1,
                   cornerRadius: 6, padding: 10,
                   bodyFont: { family: 'system-ui' }, titleFont: { family: 'system-ui', weight: '600' },
                   callbacks: { label: function(ctx) {
                     return ctx.dataset.label + ': ' + ctx.parsed.y.toLocaleString();
                   }}},
      },
      scales: {
        x: { grid: { display: false }, ticks: { color: pal.muted, font: { size: 11 } },
             border: { color: pal.grid } },
        y: { grid: { color: pal.grid, lineWidth: 1 },
             ticks: { color: pal.muted, font: { size: 11 },
                      callback: function(v) { return compact(v); } },
             border: { display: false } }
      }
    };
  }

  // --- KPI tiles ---
  function renderKPIs(data) {
    const container = document.querySelector('.findings-section');
    if (!container) return;

    const pipeline = data.pipeline;
    const totalLodged = pipeline.lodged.reduce((a,b) => a+b, 0);
    const totalApproved = pipeline.approved_dev.reduce((a,b) => a+b, 0);
    const totalCon = pipeline.approved_con.filter(v => v != null).reduce((a,b) => a+b, 0);

    const compQ = data.completions;
    const totalComplete = compQ.houses.reduce((a,b) => a+b, 0) + compQ.other.reduce((a,b) => a+b, 0);

    // Weighted DA and construction %
    const totalCumDA = data.target_progress.reduce((a,t) => a + t.cumulative, 0);
    const totalProrDA = data.target_progress.reduce((a,t) => a + t.prorated_target, 0);
    const weightedDA = totalProrDA > 0 ? Math.round(totalCumDA / totalProrDA * 100) : 0;
    const totalCumCon = data.target_progress_con.reduce((a,t) => a + t.cumulative, 0);
    const totalProrCon = data.target_progress_con.reduce((a,t) => a + t.prorated_target, 0);
    const weightedCon = totalProrCon > 0 ? Math.round(totalCumCon / totalProrCon * 100) : 0;

    // Greenfield totals
    const totalCapacity = data.greenfield.reduce((a,g) => a + g.capacity, 0);
    const totalNewLots = data.greenfield.reduce((a,g) => a + g.new_lots_created, 0);

    const kpis = [
      { label: 'Dwellings lodged', value: compact(totalLodged) },
      { label: 'Dev approvals', value: compact(totalApproved) },
      { label: 'Construction approvals', value: compact(totalCon) },
      { label: 'Completions', value: compact(totalComplete) },
      { label: 'DA % of pro-rated target', value: weightedDA + '%' },
      { label: 'Construction % of target', value: weightedCon + '%' },
      { label: 'Greenfield capacity', value: compact(totalCapacity) },
      { label: 'New lots created', value: compact(totalNewLots) },
    ];

    const row = document.createElement('div');
    row.className = 'kpi-row';
    kpis.forEach(k => {
      const tile = document.createElement('div');
      tile.className = 'kpi-tile';
      tile.innerHTML = '<div class="kpi-label">' + k.label + '</div>' +
                       '<div class="kpi-value">' + k.value + '</div>';
      row.appendChild(tile);
    });
    container.insertBefore(row, container.querySelector('h2').nextSibling);
  }

  // --- Pipeline line chart ---
  function renderPipeline(data) {
    const pal = getPalette();
    const ctx = document.getElementById('pipelineChart');
    if (!ctx) return;

    const monthNames = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    const labels = data.pipeline.months.map(m => {
      const parts = m.split('-');
      return monthNames[parseInt(parts[1]) - 1] + ' ' + parts[0].slice(2);
    });

    const opts = baseOpts(pal);
    opts.elements = { line: { borderWidth: 2, tension: 0 }, point: { radius: 0, hoverRadius: 5, hitRadius: 12 } };
    opts.interaction = { mode: 'index', intersect: false };

    new Chart(ctx, {
      type: 'line',
      data: {
        labels: labels,
        datasets: [
          { label: 'Lodged for development', data: data.pipeline.lodged,
            borderColor: pal.series[0], backgroundColor: pal.series[0] + '1a', fill: false },
          { label: 'Approved for development', data: data.pipeline.approved_dev,
            borderColor: pal.series[1], backgroundColor: pal.series[1] + '1a', fill: false },
          { label: 'Approved for construction', data: data.pipeline.approved_con,
            borderColor: pal.series[2], backgroundColor: pal.series[2] + '1a', fill: false },
        ]
      },
      options: opts
    });
  }

  // --- Completions stacked bar ---
  function renderCompletions(data) {
    const pal = getPalette();
    const ctx = document.getElementById('completionsChart');
    if (!ctx) return;

    const opts = baseOpts(pal);
    opts.scales.x.stacked = true;
    opts.scales.y.stacked = true;
    opts.plugins.tooltip.callbacks.label = function(ctx) {
      return ctx.dataset.label + ': ' + ctx.parsed.y.toLocaleString();
    };

    new Chart(ctx, {
      type: 'bar',
      data: {
        labels: data.completions.quarters,
        datasets: [
          { label: 'Houses', data: data.completions.houses,
            backgroundColor: pal.series[0], maxBarThickness: 24, borderRadius: 0 },
          { label: 'Other dwellings', data: data.completions.other,
            backgroundColor: pal.series[1], maxBarThickness: 24,
            borderRadius: { topLeft: 4, topRight: 4 } },
        ]
      },
      options: opts
    });
  }

  // --- Target LGA horizontal bar (dual measure: DA + construction) ---
  function renderTargets(data) {
    const pal = getPalette();
    const ctx = document.getElementById('targetChart');
    if (!ctx) return;

    const daData = data.target_progress_top15 || data.target_progress;
    const conLookup = {};
    (data.target_progress_con || []).forEach(function(t) { conLookup[t.lga] = t; });

    const sorted = daData.slice().sort(function(a,b) {
      var aCon = conLookup[a.lga] ? conLookup[a.lga].pct_of_prorated : 0;
      var bCon = conLookup[b.lga] ? conLookup[b.lga].pct_of_prorated : 0;
      return aCon - bCon;
    });
    const labels = sorted.map(function(t) { return t.lga; });
    const daValues = sorted.map(function(t) { return t.pct_of_prorated; });
    const conValues = sorted.map(function(t) {
      var c = conLookup[t.lga];
      return c ? c.pct_of_prorated : 0;
    });

    const opts = baseOpts(pal);
    opts.indexAxis = 'y';
    opts.plugins.legend.display = true;
    opts.scales.x.ticks.callback = function(v) { return v + '%'; };
    opts.scales.x.grid = { color: pal.grid, lineWidth: 1 };
    opts.scales.y.grid = { display: false };
    opts.scales.y.ticks = { color: pal.secondary, font: { size: 11 } };
    opts.plugins.tooltip.callbacks.label = function(ctx) {
      var idx = ctx.dataIndex;
      var t = sorted[idx];
      if (ctx.datasetIndex === 0) {
        return 'DA: ' + t.pct_of_prorated.toFixed(1) + '% (' + t.cumulative.toLocaleString() +
               ' of ' + t.prorated_target.toLocaleString() + ' pro-rated)';
      } else {
        var c = conLookup[t.lga];
        if (!c) return 'Construction: no data';
        return 'Construction: ' + c.pct_of_prorated.toFixed(1) + '% (' + c.cumulative.toLocaleString() +
               ' of ' + c.prorated_target.toLocaleString() + ' pro-rated)';
      }
    };

    new Chart(ctx, {
      type: 'bar',
      data: {
        labels: labels,
        datasets: [
          { label: 'DA approvals', data: daValues,
            backgroundColor: pal.series[1] + 'aa', maxBarThickness: 14,
            borderRadius: { topLeft: 0, topRight: 4, bottomRight: 4, bottomLeft: 0 } },
          { label: 'Construction approvals', data: conValues,
            backgroundColor: pal.series[2] + 'aa', maxBarThickness: 14,
            borderRadius: { topLeft: 0, topRight: 4, bottomRight: 4, bottomLeft: 0 } },
        ]
      },
      options: opts
    });

    const wrap = ctx.parentElement;
    if (!wrap.querySelector('.target-caption')) {
      const note = document.createElement('div');
      note.className = 'target-caption';
      note.style.cssText = 'font-size:12px;color:' + pal.muted + ';text-align:right;margin-top:4px;';
      note.textContent = '100% = linear share of five-year completion target (not a delivery benchmark for approvals)';
      wrap.appendChild(note);
    }
  }

  // --- Feasibility gap: construction÷DA ratio by LGA ---
  function renderFeasibility(data) {
    const pal = getPalette();
    const ctx = document.getElementById('feasibilityChart');
    if (!ctx) return;

    const feas = data.feasibility || [];
    if (feas.length === 0) return;

    // Sort by ratio ascending (worst feasibility at top)
    const sorted = feas.slice().sort(function(a,b) { return a.con_da_ratio - b.con_da_ratio; });
    const labels = sorted.map(function(r) { return r.lga; });
    const values = sorted.map(function(r) { return r.con_da_ratio; });

    // Single colour — ranking carries the message; traffic-light coding
    // would imply ratios above 1.0 are "good" when they are a CDC artefact
    const barColor = pal.series[0];

    const opts = baseOpts(pal);
    opts.indexAxis = 'y';
    opts.layout = { padding: { top: 16 } };  // room for the 1:1 label above the plot
    opts.plugins.legend.display = false;
    opts.scales.x.min = 0;
    opts.scales.x.grid = { color: pal.grid, lineWidth: 1 };
    opts.scales.y.grid = { display: false };
    opts.scales.y.ticks = { color: pal.secondary, font: { size: 10 }, autoSkip: false };
    opts.plugins.tooltip.callbacks.label = function(ctx) {
      var r = sorted[ctx.dataIndex];
      return 'Ratio: ' + r.con_da_ratio.toFixed(2) +
             ' (DA ' + r.da_pct.toFixed(0) + '% / Con ' + r.con_pct.toFixed(0) + '%)';
    };

    var chart = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: labels,
        datasets: [{
          data: values,
          backgroundColor: barColor,
          maxBarThickness: 12,
          borderRadius: { topLeft: 0, topRight: 4, bottomRight: 4, bottomLeft: 0 },
        }]
      },
      options: opts,
      plugins: [{
        afterDraw: function(chart) {
          var xScale = chart.scales.x;
          var yScale = chart.scales.y;
          var xPixel = xScale.getPixelForValue(1.0);
          if (xPixel >= xScale.left && xPixel <= xScale.right) {
            var drawCtx = chart.ctx;
            drawCtx.save();
            drawCtx.beginPath();
            drawCtx.setLineDash([4, 4]);
            drawCtx.strokeStyle = pal.muted;
            drawCtx.lineWidth = 1;
            drawCtx.moveTo(xPixel, yScale.top);
            drawCtx.lineTo(xPixel, yScale.bottom);
            drawCtx.stroke();
            drawCtx.restore();
            // Label
            drawCtx.fillStyle = pal.muted;
            drawCtx.font = '11px system-ui';
            drawCtx.textAlign = 'center';
            drawCtx.fillText('1:1', xPixel, yScale.top - 4);
          }
        }
      }]
    });
  }

  // --- Greenfield: two panels (capacity left, lots right) ---
  function renderGreenfieldCapacity(data) {
    const pal = getPalette();
    const ctx = document.getElementById('greenfieldCapChart');
    if (!ctx) return;

    const nameMap = {
      'Council Led Greenfield': 'Council Led',
      'Greater Macarthur Growth Area': 'Gr. Macarthur',
      'Greater Penrith to Eastern Creek Investigation Area': 'Gr. Penrith–E. Creek',
      'North West Growth Area': 'North West',
      'South West Growth Area': 'South West',
      'Western Sydney Aerotropolis': 'Aerotropolis',
      'Wilton Growth Area': 'Wilton',
    };

    const sorted = data.greenfield.slice().sort((a,b) => b.capacity - a.capacity);
    const labels = sorted.map(g => nameMap[g.growth_area] || g.growth_area);

    const opts = baseOpts(pal, 'Planned dwelling capacity');
    opts.indexAxis = 'y';
    opts.plugins.legend.display = false;
    opts.scales.x.min = 0;
    opts.scales.x.grid = { color: pal.grid, lineWidth: 1 };
    opts.scales.y.grid = { display: false };
    opts.scales.y.ticks = { color: pal.secondary, font: { size: 11 } };
    opts.plugins.tooltip.callbacks.label = function(ctx) {
      return 'Capacity: ' + ctx.parsed.x.toLocaleString();
    };

    new Chart(ctx, {
      type: 'bar',
      data: {
        labels: labels,
        datasets: [{
          data: sorted.map(g => g.capacity),
          backgroundColor: pal.series[0],
          maxBarThickness: 18,
          borderRadius: { topLeft: 0, topRight: 4, bottomRight: 4, bottomLeft: 0 },
        }]
      },
      options: opts
    });
  }

  function renderGreenfieldLots(data) {
    const pal = getPalette();
    const ctx = document.getElementById('greenfieldLotsChart');
    if (!ctx) return;

    const nameMap = {
      'Council Led Greenfield': 'Council Led',
      'Greater Macarthur Growth Area': 'Gr. Macarthur',
      'Greater Penrith to Eastern Creek Investigation Area': 'Gr. Penrith–E. Creek',
      'North West Growth Area': 'North West',
      'South West Growth Area': 'South West',
      'Western Sydney Aerotropolis': 'Aerotropolis',
      'Wilton Growth Area': 'Wilton',
    };

    const sorted = data.greenfield.slice().sort((a,b) => b.capacity - a.capacity);
    const labels = sorted.map(g => nameMap[g.growth_area] || g.growth_area);

    const opts = baseOpts(pal, 'Lots: approved vs created');
    opts.indexAxis = 'y';
    opts.plugins.legend.display = true;
    opts.scales.x.min = 0;
    opts.scales.x.grid = { color: pal.grid, lineWidth: 1 };
    opts.scales.y.grid = { display: false };
    opts.scales.y.ticks = { color: pal.secondary, font: { size: 11 } };
    opts.plugins.tooltip.callbacks.label = function(ctx) {
      var v = ctx.parsed.x;
      return ctx.dataset.label + ': ' + (v == null ? '—' : v.toLocaleString());
    };

    new Chart(ctx, {
      type: 'bar',
      data: {
        labels: labels,
        datasets: [
          { label: 'Lots approved', data: sorted.map(g => g.has_audit_data ? g.lots_approved : null),
            backgroundColor: pal.series[2], maxBarThickness: 14,
            borderRadius: { topLeft: 0, topRight: 4, bottomRight: 4, bottomLeft: 0 } },
          { label: 'New lots created', data: sorted.map(g => Math.max(0, g.new_lots_created)),
            backgroundColor: pal.series[1], maxBarThickness: 14,
            borderRadius: { topLeft: 0, topRight: 4, bottomRight: 4, bottomLeft: 0 } },
        ]
      },
      options: opts
    });
  }

  // --- Table view toggles ---
  function addTableViews(data) {
    // Pipeline table
    addTableToggle('pipelineChart', function() {
      const months = data.pipeline.months;
      let html = '<table class="data-table"><thead><tr><th>Month</th><th>Lodged</th><th>Dev approved</th><th>Con approved</th></tr></thead><tbody>';
      for (let i = 0; i < months.length; i++) {
        html += '<tr><td>' + months[i] + '</td><td class="num">' +
          data.pipeline.lodged[i].toLocaleString() + '</td><td class="num">' +
          data.pipeline.approved_dev[i].toLocaleString() + '</td><td class="num">' +
          (data.pipeline.approved_con[i] != null ? data.pipeline.approved_con[i].toLocaleString() : '—') + '</td></tr>';
      }
      html += '</tbody></table>';
      return html;
    });

    // Completions table
    addTableToggle('completionsChart', function() {
      let html = '<table class="data-table"><thead><tr><th>Quarter</th><th>Houses</th><th>Other</th><th>Total</th></tr></thead><tbody>';
      for (let i = 0; i < data.completions.quarters.length; i++) {
        const total = data.completions.houses[i] + data.completions.other[i];
        html += '<tr><td>' + data.completions.quarters[i] + '</td><td class="num">' +
          data.completions.houses[i].toLocaleString() + '</td><td class="num">' +
          data.completions.other[i].toLocaleString() + '</td><td class="num">' +
          total.toLocaleString() + '</td></tr>';
      }
      html += '</tbody></table>';
      return html;
    });

    // Target progress table
    addTableToggle('targetChart', function() {
      var conLookup = {};
      (data.target_progress_con || []).forEach(function(t) { conLookup[t.lga] = t; });
      let html = '<table class="data-table"><thead><tr><th>LGA</th><th>5-yr target</th>' +
        '<th>DA approvals</th><th>DA % pro-rated</th>' +
        '<th>Con approvals</th><th>Con % pro-rated</th></tr></thead><tbody>';
      const sorted = data.target_progress.slice().sort((a,b) => b.pct_of_prorated - a.pct_of_prorated);
      sorted.forEach(t => {
        var c = conLookup[t.lga];
        html += '<tr><td>' + t.lga + '</td><td class="num">' + t.target_5yr.toLocaleString() +
          '</td><td class="num">' + t.cumulative.toLocaleString() +
          '</td><td class="num">' + t.pct_of_prorated.toFixed(1) + '%' +
          '</td><td class="num">' + (c ? c.cumulative.toLocaleString() : '—') +
          '</td><td class="num">' + (c ? c.pct_of_prorated.toFixed(1) + '%' : '—') + '</td></tr>';
      });
      html += '</tbody></table>';
      return html;
    });

    // Feasibility table
    addTableToggle('feasibilityChart', function() {
      var feas = data.feasibility || [];
      let html = '<table class="data-table"><thead><tr><th>LGA</th><th>DA approvals</th>' +
        '<th>DA %</th><th>Con approvals</th><th>Con %</th><th>Con÷DA ratio</th></tr></thead><tbody>';
      feas.forEach(function(r) {
        html += '<tr><td>' + r.lga + '</td><td class="num">' + r.da_approvals.toLocaleString() +
          '</td><td class="num">' + r.da_pct.toFixed(1) + '%' +
          '</td><td class="num">' + r.con_approvals.toLocaleString() +
          '</td><td class="num">' + r.con_pct.toFixed(1) + '%' +
          '</td><td class="num">' + r.con_da_ratio.toFixed(2) + '</td></tr>';
      });
      html += '</tbody></table>';
      return html;
    });

    // Greenfield table (attach to capacity chart)
    addTableToggle('greenfieldCapChart', function() {
      var hasNeg = data.greenfield.some(g => g.new_lots_created < 0);
      let html = '<table class="data-table"><thead><tr><th>Growth area</th><th>Capacity</th><th>Lots approved</th><th>In assessment</th><th>New lots</th></tr></thead><tbody>';
      data.greenfield.forEach(g => {
        var auditApproved = g.has_audit_data ? g.lots_approved.toLocaleString() : '—';
        var auditAssess = g.has_audit_data ? g.lots_in_assessment.toLocaleString() : '—';
        var newLotsStr = g.new_lots_created.toLocaleString();
        if (g.new_lots_created < 0) newLotsStr = '<span title="Net negative">' + newLotsStr + ' *</span>';
        html += '<tr><td>' + g.growth_area + '</td><td class="num">' + g.capacity.toLocaleString() +
          '</td><td class="num">' + auditApproved +
          '</td><td class="num">' + auditAssess +
          '</td><td class="num">' + newLotsStr + '</td></tr>';
      });
      html += '</tbody></table>';
      if (hasNeg) html += '<p style="font-size:0.85em;color:var(--text-secondary,#666);margin-top:0.5em">* Negative new-lots figure (net demolitions or lot consolidations exceed new lots created). Shown as 0 in the chart.</p>';
      return html;
    });
  }

  function addTableToggle(chartId, buildTable) {
    const canvas = document.getElementById(chartId);
    if (!canvas) return;
    const section = canvas.closest('.chart-section');
    if (!section) return;

    // Avoid duplicate toggles
    if (section.querySelector('.table-toggle[data-for="' + chartId + '"]')) return;

    const btn = document.createElement('button');
    btn.className = 'table-toggle';
    btn.setAttribute('data-for', chartId);
    btn.textContent = 'Show data table';

    const wrap = document.createElement('div');
    wrap.className = 'data-table-wrap';
    wrap.setAttribute('role', 'region');
    wrap.setAttribute('aria-label', 'Data table');

    section.appendChild(btn);
    section.appendChild(wrap);

    btn.addEventListener('click', function() {
      if (wrap.classList.contains('visible')) {
        wrap.classList.remove('visible');
        btn.textContent = 'Show data table';
      } else {
        if (!wrap.innerHTML) wrap.innerHTML = buildTable();
        wrap.classList.add('visible');
        btn.textContent = 'Hide data table';
      }
    });
  }

  // --- Theme toggle ---
  function addThemeToggle() {
    const btn = document.createElement('button');
    btn.className = 'theme-toggle';
    btn.textContent = '◑ Theme';
    btn.setAttribute('aria-label', 'Toggle light/dark mode');
    document.body.appendChild(btn);

    btn.addEventListener('click', function() {
      const root = document.documentElement;
      const current = root.getAttribute('data-theme');
      if (current === 'dark') {
        root.setAttribute('data-theme', 'light');
      } else {
        root.setAttribute('data-theme', 'dark');
      }
      Chart.helpers.each(Chart.instances, function(instance) { instance.destroy(); });
      renderCharts();
    });
  }

  // --- Main ---
  function renderCharts() {
    renderPipeline(DATA);
    renderCompletions(DATA);
    renderTargets(DATA);
    renderFeasibility(DATA);
    renderGreenfieldCapacity(DATA);
    renderGreenfieldLots(DATA);
  }

  document.addEventListener('DOMContentLoaded', function() {
    Chart.defaults.font.family = 'system-ui, -apple-system, "Segoe UI", sans-serif';
    renderKPIs(DATA);
    renderCharts();
    addTableViews(DATA);
    addThemeToggle();
  });
})();
