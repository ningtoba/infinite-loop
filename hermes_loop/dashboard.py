"""Status HTML dashboard and SSE broadcast helpers."""

import json
import os
import threading

from .config import LAUNCH_LOOP_VERSION
from .file_utils import _log
from .goal_utils import _goal_hash

# SSE (Server-Sent Events) client tracking for live dashboard
_sse_clients: list = []
_sse_clients_lock = threading.Lock()


# Status HTML template (static HTML page, no SSE)
_STATUS_HTML_TPL = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="refresh" content="30">
<title>Infinite Loop Dashboard</title>
<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Ctext y='.9em' font-size='90'%3E%E2%99%BE%EF%B8%8F%3C/text%3E%3C/svg%3E">
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  :root { --bg: #0d1117; --fg: #c9d1d9; --card-bg: #161b22; --border: #30363d; --border-row: #21262d; --accent: #58a6ff; --muted: #8b949e; --dim: #484f58; --err-bg: rgba(218, 54, 51, 0.1); }
  @media (prefers-color-scheme: light) {
    :root { --bg: #f6f8fa; --fg: #24292f; --card-bg: #ffffff; --border: #d0d7de; --border-row: #e1e4e8; --accent: #0969da; --muted: #656d76; --dim: #8b949e; --err-bg: rgba(218, 54, 51, 0.05); }
  }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: var(--bg); color: var(--fg); padding: 20px; }
  h1 { font-size: 1.5rem; margin-bottom: 1rem; color: var(--accent); }
  h2 { font-size: 1.1rem; margin: 1.5rem 0 0.5rem; color: var(--muted); }
  .meta { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 8px; margin-bottom: 1rem; }
  .meta-item { background: var(--card-bg); padding: 8px 12px; border-radius: 6px; font-size: 0.85rem; }
  .meta-item .label { color: var(--muted); }
  .meta-item .value { color: var(--fg); font-weight: 600; }
  .status-badge { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 0.8rem; font-weight: 600; }
  .running { background: #1f6feb; color: #fff; }
  .stopped { background: #da3633; color: #fff; }
  .paused { background: #d29922; color: #000; }
  table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
  th { text-align: left; padding: 8px 6px; border-bottom: 1px solid var(--border); color: var(--muted); text-transform: uppercase; font-size: 0.75rem; }
  td { padding: 8px 6px; border-bottom: 1px solid var(--border-row); }
  .error-row td { background: var(--err-bg); }
  .summary { max-width: 350px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--muted); }
  .tag { display: inline-block; padding: 1px 6px; border-radius: 4px; font-size: 0.75rem; margin-right: 4px; }
  .tag-ok { background: #1a3a1a; color: #3fb950; }
  .tag-err { background: #3a1a1a; color: #f85149; }
  .tag-evolve { background: #1a1a3a; color: #58a6ff; }
  .tag-wtree { background: #1a3a2a; color: #3fb950; }
  .progress { height: 8px; background: var(--border); border-radius: 4px; margin: 8px 0; }
  .progress-fill { height: 8px; background: #1f6feb; border-radius: 4px; transition: width 0.3s; }
  .stats-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 8px; margin-bottom: 1rem; }
  .stat-card { background: var(--card-bg); padding: 12px; border-radius: 6px; text-align: center; }
  .stat-card .num { font-size: 1.5rem; font-weight: 700; color: var(--accent); }
  .stat-card .label { font-size: 0.75rem; color: var(--muted); margin-top: 4px; }
  .cooldown-active { color: #d29922; }
  .cooldown-idle { color: var(--muted); }
  .compact-toggle { float: right; font-size: 0.75rem; color: var(--accent); cursor: pointer; text-decoration: underline; margin-top: 1.5rem; }
  .compact-mode .meta, .compact-mode .stats-grid, .compact-mode h2, .compact-mode .progress, .compact-mode .cooldown-row, .compact-mode #iterations-table { display: none; }
  .compact-mode #summary-only { display: block; }
  #summary-only { display: none; }
</style>
</head>
<body>
<script>
function toggleCompact() {
  document.body.classList.toggle('compact-mode');
  localStorage.setItem('loop-dashboard-compact', document.body.classList.contains('compact-mode'));
}
(function() {
  if (localStorage.getItem('loop-dashboard-compact') === 'true') {
    document.body.classList.add('compact-mode');
  }
})();
</script>
<h1>&#x267E;&#xFE0F; Infinite Loop Dashboard <span style="font-size:0.7rem;color:var(--dim)">v{VERSION}</span></h1>
<div class="meta">
  <div class="meta-item"><span class="label">Status</span><br><span class="status-badge {STATUS_CLASS}">{STATUS}</span></div>
  <div class="meta-item"><span class="label">Iterations</span><br><span class="value">{TOTAL}</span></div>
  <div class="meta-item"><span class="label">Goal</span><br><span class="value">{GOAL}</span></div>
  <div class="meta-item"><span class="label">Started</span><br><span class="value">{STARTED}</span></div>
  <div class="meta-item"><span class="label">Last Updated</span><br><span class="value">{LAST_UPDATED}</span></div>
  <div class="meta-item"><span class="label">ETA</span><br><span class="value">{ETA}</span></div>
  <div class="meta-item"><span class="label">Cooldown</span><br><span class="value {COOLDOWN_CLASS}">{COOLDOWN}</span></div>
</div>

<h2>Stats <span class="compact-toggle" onclick="toggleCompact()">[toggle summary-mode]</span></h2>
<div class="stats-grid">
  <div class="stat-card"><div class="num">{SUCCESS}</div><div class="label">Success</div></div>
  <div class="stat-card"><div class="num">{ERRORS}</div><div class="label">Errors</div></div>
  <div class="stat-card"><div class="num">{TOTAL_DUR}s</div><div class="label">Total Time</div></div>
  <div class="stat-card"><div class="num">{AVG_DUR}s</div><div class="label">Avg / Iteration</div></div>
  <div class="stat-card"><div class="num">{CPU_SEC}s</div><div class="label">CPU Seconds</div></div>
  <div class="stat-card"><div class="num">{MEM_MB}MB</div><div class="label">Memory (RSS)</div></div>
  <div class="stat-card"><div class="num">{MEM_PCT}%</div><div class="label">Memory %</div></div>
</div>

{EVA_GOAL_ROW}

{PROGRESS_ROW}

<h2>Iterations</h2>
<table id="iterations-table"><thead><tr><th>#</th><th>Time</th><th>Duration</th><th>Type</th><th>Summary</th><th>ETA</th></tr></thead><tbody>
{ITER_ROWS}
</tbody></table>
<div id="summary-only">
<p style="color:var(--muted);font-size:0.85rem;">{SUMMARY_ONLY_TEXT}</p>
</div>
<p style="margin-top: 12px; font-size: 0.8rem; color: var(--dim);">Auto-generated by infinite-loop daemon v{VERSION}</p>
</body></html>"""

# SSE-powered live dashboard HTML template (no meta-refresh, uses EventSource)
_SSE_DASHBOARD_HTML_TPL = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Infinite Loop Dashboard (Live)</title>
<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Ctext y='.9em' font-size='90'%3E%E2%99%BE%EF%B8%8F%3C/text%3E%3C/svg%3E">
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  :root { --bg: #0d1117; --fg: #c9d1d9; --card-bg: #161b22; --border: #30363d; --border-row: #21262d; --accent: #58a6ff; --muted: #8b949e; --dim: #484f58; --err-bg: rgba(218, 54, 51, 0.1); }
  @media (prefers-color-scheme: light) {
    :root { --bg: #f6f8fa; --fg: #24292f; --card-bg: #ffffff; --border: #d0d7de; --border-row: #e1e4e8; --accent: #0969da; --muted: #656d76; --dim: #8b949e; --err-bg: rgba(218, 54, 51, 0.05); }
  }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: var(--bg); color: var(--fg); padding: 20px; }
  h1 { font-size: 1.5rem; margin-bottom: 1rem; color: var(--accent); }
  h2 { font-size: 1.1rem; margin: 1.5rem 0 0.5rem; color: var(--muted); }
  .meta { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 8px; margin-bottom: 1rem; }
  .meta-item { background: var(--card-bg); padding: 8px 12px; border-radius: 6px; font-size: 0.85rem; }
  .meta-item .label { color: var(--muted); }
  .meta-item .value { color: var(--fg); font-weight: 600; }
  #status-badge { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 0.8rem; font-weight: 600; }
  .running { background: #1f6feb; color: #fff; }
  .stopped { background: #da3633; color: #fff; }
  .paused { background: #d29922; color: #000; }
  .reloading { background: #da3633; color: #fff; }
  .no_ledger { background: var(--dim); color: #fff; }
  table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
  th { text-align: left; padding: 8px 6px; border-bottom: 1px solid var(--border); color: var(--muted); text-transform: uppercase; font-size: 0.75rem; }
  td { padding: 8px 6px; border-bottom: 1px solid var(--border-row); }
  .error-row td { background: var(--err-bg); }
  .summary { max-width: 350px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--muted); }
  .tag { display: inline-block; padding: 1px 6px; border-radius: 4px; font-size: 0.75rem; margin-right: 4px; }
  .tag-ok { background: #1a3a1a; color: #3fb950; }
  .tag-err { background: #3a1a1a; color: #f85149; }
  .tag-evolve { background: #1a1a3a; color: #58a6ff; }
  .tag-wtree { background: #1a3a2a; color: #3fb950; }
  .progress { height: 8px; background: var(--border); border-radius: 4px; margin: 8px 0; }
  .progress-fill { height: 8px; background: #1f6feb; border-radius: 4px; transition: width 0.3s; }
  .stats-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 8px; margin-bottom: 1rem; }
  .stat-card { background: var(--card-bg); padding: 12px; border-radius: 6px; text-align: center; }
  .stat-card .num { font-size: 1.5rem; font-weight: 700; color: var(--accent); }
  .stat-card .label { font-size: 0.75rem; color: var(--muted); margin-top: 4px; }
  #cooldown-display { font-size: 0.85rem; }
  .cooldown-active { color: #d29922; }
  .cooldown-idle { color: var(--muted); }
  .compact-toggle { float: right; font-size: 0.75rem; color: var(--accent); cursor: pointer; text-decoration: underline; margin-top: 1.5rem; }
  .compact-mode .meta, .compact-mode .stats-grid, .compact-mode h2, .compact-mode .progress, .compact-mode .cooldown-row, .compact-mode #iterations-table, .compact-mode #goals-panel, .compact-mode #error-panel, .compact-mode #metrics-panel { display: none; }
  .compact-mode #summary-only { display: block; }
  #summary-only { display: none; }
  #connection-status { font-size: 0.75rem; color: var(--muted); float: right; }
  .connected { color: #3fb950; }
  .disconnected { color: #f85149; }
  .err-card { background: var(--err-bg); padding: 8px 12px; border-radius: 6px; font-size: 0.82rem; display: inline-block; margin: 4px 4px 0 0; }
  .err-card .num { font-weight: 700; margin-right: 4px; }
  .err-timeout { border-left: 3px solid #d29922; }
  .err-network { border-left: 3px solid #da3633; }
  .err-schema { border-left: 3px solid #a371f7; }
  .err-unknown { border-left: 3px solid var(--dim); }
  .mitigation-tag { display: inline-block; padding: 1px 6px; border-radius: 4px; font-size: 0.72rem; background: #1a3a1a; color: #3fb950; margin: 2px; }
  .mitigation-active { background: #3a1a1a; color: #f85149; }
  .goal-row { display: flex; align-items: center; padding: 4px 0; font-size: 0.82rem; border-bottom: 1px solid var(--border-row); }
  .goal-row .gidx { color: var(--dim); width: 24px; }
  .goal-row .gstatus { width: 20px; text-align: center; margin-right: 6px; }
  .goal-row .gtext { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--fg); }
  .goal-done .gtext { color: var(--muted); text-decoration: line-through; }
  .goal-active .gtext { color: var(--accent); }
</style>
</head>
<body>
<h1>&#x267B;&#xFE0F; Infinite Loop <span id="connection-status" class="disconnected">&#x25CF; disconnected</span></h1>
<div class="meta" id="meta-cards">
  <div class="meta-item"><span class="label">Status</span><br><span id="status-badge" class="running">loading...</span></div>
  <div class="meta-item"><span class="label">Total Iterations</span><br><span class="value" id="total-iterations">-</span></div>
  <div class="meta-item"><span class="label">Goal</span><br><span class="value" id="goal">-</span></div>
  <div class="meta-item"><span class="label">Evolved Goal</span><br><span class="value" id="evolved-goal">-</span></div>
  <div class="meta-item"><span class="label">Started At</span><br><span class="value" id="started-at">-</span></div>
  <div class="meta-item"><span class="label">Last Updated</span><br><span class="value" id="last-updated">-</span></div>
</div>

<div class="stats-grid" id="stats-grid">
  <div class="stat-card"><div class="num" id="stat-success">-</div><div class="label">Success</div></div>
  <div class="stat-card"><div class="num" id="stat-error">-</div><div class="label">Errors</div></div>
  <div class="stat-card"><div class="num" id="stat-avg-duration">-</div><div class="label">Avg Duration</div></div>
  <div class="stat-card"><div class="num" id="stat-consec-errors">-</div><div class="label">Consec Errors</div></div>
  <div class="stat-card"><div class="num" id="stat-eta">-</div><div class="label">ETA</div></div>
</div>

<div id="cooldown-display" class="cooldown-idle">Cooldown: idle</div>

<h2>Progress</h2>
<div class="progress" id="progress-bar"><div class="progress-fill" id="progress-fill" style="width:0%"></div></div>

<h2>Errors <span id="error-summary" style="font-size:0.75rem;color:var(--muted);font-weight:400;"></span></h2>
<div id="error-panel" style="margin-bottom:0.5rem;display:flex;flex-wrap:wrap;gap:4px;">
  <div class="err-card err-timeout"><span class="num" id="err-timeout">0</span>timeout</div>
  <div class="err-card err-network"><span class="num" id="err-network">0</span>network</div>
  <div class="err-card err-schema"><span class="num" id="err-schema">0</span>schema</div>
  <div class="err-card err-unknown"><span class="num" id="err-unknown">0</span>unknown</div>
  <div id="mitigations-container" style="margin-left:8px;"></div>
</div>

<h2>Metrics <span id="metrics-summary" style="font-size:0.75rem;color:var(--muted);font-weight:400;"></span></h2>
<div id="metrics-panel" class="stats-grid" style="margin-bottom:0.5rem;">
  <div class="stat-card"><div class="num" id="metric-avg-turns">-</div><div class="label">Avg Turns</div></div>
  <div class="stat-card"><div class="num" id="metric-tokens">-</div><div class="label">Tokens/Iter</div></div>
  <div class="stat-card"><div class="num" id="metric-est-cost">-</div><div class="label">Est Cost</div></div>
  <div class="stat-card"><div class="num" id="metric-iters-per-goal">-</div><div class="label">Iters/Goal</div></div>
</div>

<h2>Goals <span id="goals-summary" style="font-size:0.75rem;color:var(--muted);font-weight:400;"></span></h2>
<div id="goals-panel" style="margin-bottom:0.5rem;"></div>

<h2>Latest Iteration <span class="compact-toggle" id="compact-toggle" onclick="toggleCompact()">[compact]</span></h2>
<div id="summary-only"></div>
<table id="iterations-table">
<thead><tr><th>#</th><th>Type</th><th>Duration</th><th>Summary</th><th>Classification</th><th>Error</th><th>WT</th></tr></thead>
<tbody id="iterations-body"></tbody>
</table>

<p style="margin-top:1rem;font-size:0.75rem;color:var(--muted);">
  Live updates via SSE &mdash;
  <a href="/api/status" target="_blank" style="color:var(--accent);">JSON API</a> &middot;
  <a href="/status" target="_blank" style="color:var(--accent);">Simple Status</a> &middot;
  <a href="/health" target="_blank" style="color:var(--accent);">Health</a>
</p>

<script>
var compact = false;
function toggleCompact() {
    compact = !compact;
    document.body.classList.toggle('compact-mode', compact);
    document.getElementById('compact-toggle').textContent = compact ? '[expand]' : '[compact]';
}
function updateBadge(status) {
    var badge = document.getElementById('status-badge');
    badge.textContent = status;
    badge.className = '';
    if (status === 'running') badge.classList.add('running');
    else if (status === 'stopped') badge.classList.add('stopped');
    else if (status === 'paused') badge.classList.add('paused');
    else if (status === 'reloading') badge.classList.add('reloading');
    else badge.classList.add('no_ledger');
}
function updateErrorPanel(data) {
    var e = data.error_counts || {};
    document.getElementById('err-timeout').textContent = e.timeout || 0;
    document.getElementById('err-network').textContent = e.network || 0;
    document.getElementById('err-schema').textContent = e.schema || 0;
    document.getElementById('err-unknown').textContent = e.unknown || 0;
    var total = (e.timeout||0)+(e.network||0)+(e.schema||0)+(e.unknown||0);
    document.getElementById('error-summary').textContent = '(' + total + ' total errors)';
    var mc = document.getElementById('mitigations-container');
    mc.innerHTML = '';
    var m = data.mitigations || {};
    var mItems = [];
    if (m.timeout_increased) mItems.push('timeout+' + (m.timeout_mult || ''));
    if (m.cooldown_elevated) mItems.push('cooldown+');
    if (m.force_subprocess) mItems.push('no-library');
    if (m.reduced_workers) mItems.push('workers-');
    if (m.consecutive_errors > 1) mItems.push(m.consecutive_errors + ' consec errs');
    if (mItems.length === 0) mItems.push('none active');
    mItems.forEach(function(t) {
        var sp = document.createElement('span');
        sp.className = 'mitigation-tag' + (t === 'none active' ? '' : ' mitigation-active');
        sp.textContent = t;
        mc.appendChild(sp);
    });
}
function updateMetricsPanel(data) {
    document.getElementById('metric-avg-turns').textContent = data.avg_turns_per_iter != null ? data.avg_turns_per_iter : '-';
    document.getElementById('metric-tokens').textContent = data.avg_tokens_per_iter != null ? data.avg_tokens_per_iter : '-';
    document.getElementById('metric-est-cost').textContent = data.est_cost || '-';
    document.getElementById('metric-iters-per-goal').textContent = data.iters_per_goal != null ? data.iters_per_goal : '-';
    document.getElementById('metrics-summary').textContent = data.metrics_summary || '';
}
function updateGoalsPanel(data) {
    var gp = document.getElementById('goals-panel');
    var goals = data.goals || [];
    var doneCnt = 0;
    goals.forEach(function(g) { if (g.done) doneCnt++; });
    document.getElementById('goals-summary').textContent = doneCnt + '/' + goals.length + ' complete';
    gp.innerHTML = '';
    if (goals.length === 0) {
        gp.innerHTML = '<p style="font-size:0.82rem;color:var(--muted)">No goals file loaded</p>';
        return;
    }
    var pct = goals.length > 0 ? Math.min(100.0 * doneCnt / goals.length, 100.0) : 0;
    var pbDiv = document.createElement('div');
    pbDiv.className = 'progress';
    pbDiv.style.height = '6px';
    var pbFill = document.createElement('div');
    pbFill.className = 'progress-fill';
    pbFill.style.width = pct + '%';
    pbFill.style.height = '6px';
    pbDiv.appendChild(pbFill);
    gp.appendChild(pbDiv);
    var maxShow = Math.min(goals.length, 30);
    for (var i = 0; i < maxShow; i++) {
        var g = goals[i];
        var row = document.createElement('div');
        row.className = 'goal-row' + (g.done ? ' goal-done' : '') + (g.active ? ' goal-active' : '');
        var idxSpan = document.createElement('span');
        idxSpan.className = 'gidx';
        idxSpan.textContent = (i + 1);
        row.appendChild(idxSpan);
        var stSpan = document.createElement('span');
        stSpan.className = 'gstatus';
        stSpan.textContent = g.done ? '\\u2713' : (g.active ? '\\u25b6' : '\\u25cb');
        row.appendChild(stSpan);
        var txtSpan = document.createElement('span');
        txtSpan.className = 'gtext';
        txtSpan.textContent = g.text || '';
        row.appendChild(txtSpan);
        gp.appendChild(row);
    }
    if (goals.length > 30) {
        var more = document.createElement('p');
        more.style.cssText = 'font-size:0.75rem;color:var(--muted);margin-top:4px;';
        more.textContent = '... and ' + (goals.length - 30) + ' more goals';
        gp.appendChild(more);
    }
}
function updateMeta(data) {
    document.getElementById('total-iterations').textContent = data.total_iterations != null ? data.total_iterations : '-';
    document.getElementById('goal').textContent = data.goal || '-';
    document.getElementById('evolved-goal').textContent = data.evolved_goal || '-';
    document.getElementById('started-at').textContent = data.started_at || '-';
    document.getElementById('last-updated').textContent = data.last_updated || '-';
    updateBadge(data.status || 'unknown');
}
function updateStats(data) {
    var s = data.stats || {};
    document.getElementById('stat-success').textContent = s.success_count != null ? s.success_count : '-';
    document.getElementById('stat-error').textContent = s.error_count != null ? s.error_count : '-';
    document.getElementById('stat-avg-duration').textContent = s.avg_duration_seconds != null ? s.avg_duration_seconds + 's' : '-';
    document.getElementById('stat-consec-errors').textContent = data.consecutive_errors != null ? data.consecutive_errors : '-';
    var eta = data.eta || {};
    document.getElementById('stat-eta').textContent = eta.remaining_formatted || '-';
}
function updateProgress(data) {
    var maxIt = data.max_iterations;
    var curIt = data.total_iterations;
    if (maxIt > 0) {
        var pct = Math.min(100.0 * curIt / maxIt, 100.0);
        document.getElementById('progress-fill').style.width = pct + '%';
    } else {
        document.getElementById('progress-fill').style.width = '0%';
    }
}
function updateCooldown(data) {
    var cd = document.getElementById('cooldown-display');
    var seconds = data.cooldown;
    if (seconds > 0) {
        cd.textContent = 'Cooldown: ' + seconds + 's';
        cd.className = 'cooldown-active';
    } else {
        cd.textContent = 'Cooldown: idle';
        cd.className = 'cooldown-idle';
    }
}
function createTag(text, cls) {
    var span = document.createElement('span');
    span.className = 'tag ' + cls;
    span.textContent = text;
    return span;
}
function addIterationRow(iter) {
    if (!iter || !iter.n) return;
    var tbody = document.getElementById('iterations-body');
    // Reset detection: if total_iterations dropped (loop was reset),
    // clear all existing rows to prevent stale data
    if (window._sseMaxIterN && iter.n < window._sseMaxIterN) {
        tbody.innerHTML = '';
        window._sseMaxIterN = 0;
    }
    var existing = tbody.querySelector('tr[data-iter-n="' + iter.n + '"]');
    if (existing) return;
    var tr = document.createElement('tr');
    tr.setAttribute('data-iter-n', iter.n);
    if (iter.error && iter.error !== 'none' && iter.error !== '') {
        tr.className = 'error-row';
    }
    var tdN = document.createElement('td'); tdN.textContent = iter.n; tr.appendChild(tdN);
    var tdType = document.createElement('td');
    if (iter.task_type) {
        var cls = iter.task_type === 'error' ? 'tag-err' : 'tag-ok';
        tdType.appendChild(createTag(iter.task_type, cls));
    }
    tr.appendChild(tdType);
    var tdDur = document.createElement('td');
    tdDur.textContent = iter.duration_seconds != null ? iter.duration_seconds + 's' : '-';
    tr.appendChild(tdDur);
    var summary = iter.summary || iter.next_goal || '';
    var tdSum = document.createElement('td');
    tdSum.className = 'summary';
    tdSum.title = summary;
    tdSum.textContent = summary.substring(0, 80);
    tr.appendChild(tdSum);
    var tdCls = document.createElement('td');
    if (iter.classification) {
        var cCls = 'tag-ok';
        if (iter.classification === 'stuck' || iter.classification === 'regression') cCls = 'tag-err';
        else if (iter.classification === 'partial') cCls = 'tag-evolve';
        tdCls.appendChild(createTag(iter.classification, cCls));
    }
    tr.appendChild(tdCls);
    var tdErr = document.createElement('td');
    tdErr.textContent = iter.error && iter.error !== 'none' ? iter.error.substring(0, 60) + '...' : '';
    tr.appendChild(tdErr);
    // Worktree merge indicator — always emit a WT td to match table header
    var tdWt = document.createElement('td');
    tdWt.style.fontSize = '0.75rem';
    tdWt.style.color = 'var(--muted)';
    if (iter.worktree_merge) {
        var wt = iter.worktree_merge;
        var wtParts = [];
        if (wt.merged > 0) wtParts.push('m' + wt.merged);
        if (wt.failed > 0) wtParts.push('f' + wt.failed);
        if (wt.conflicts > 0) wtParts.push('c' + wt.conflicts);
        tdWt.textContent = wtParts.length ? 'wt:' + wtParts.join('/') : '';
        // Tooltip: source branches + per-worker details
        var tooltipParts = [];
        var sb = wt.source_branches;
        if (sb && sb.length > 0) {
            tooltipParts.push('branches: [' + sb.join(', ') + ']');
        }
        var pw = wt.per_worker;
        if (pw) {
            var wlines = [];
            for (var k in pw) {
                var ws = pw[k];
                var wline = 'W' + k + ': ' + ws.status;
                if (ws.branch) wline += '/' + ws.branch;
                if (ws.reason) wline += ' (' + ws.reason + ')';
                wlines.push(wline);
            }
            if (wlines.length) tooltipParts.push(wlines.join(' | '));
        }
        if (wt.merged > 0) tooltipParts.push('merged: ' + wt.merged);
        if (wt.failed > 0) tooltipParts.push('failed: ' + wt.failed);
        if (wt.conflicts > 0) tooltipParts.push('conflicts: ' + wt.conflicts);
        tdWt.title = tooltipParts.join(' | ');
    }
    tr.appendChild(tdWt);
    tbody.insertBefore(tr, tbody.firstChild);
    while (tbody.children.length > 100) {
        tbody.removeChild(tbody.lastChild);
    }
}
function renderDashboard(data) {
    if (!data) return;
    updateMeta(data);
    updateStats(data);
    updateProgress(data);
    updateCooldown(data);
    updateErrorPanel(data);
    updateMetricsPanel(data);
    updateGoalsPanel(data);
    if (data.iteration && data.iteration.n) {
        addIterationRow(data.iteration);
        // Track max N seen for reset detection
        if (data.iteration.n > (window._sseMaxIterN || 0)) {
            window._sseMaxIterN = data.iteration.n;
        }
    }
    // If data contains a full iterations array (initial fetch), render all rows
    if (data._iterations && data._iterations.length > 0) {
        data._iterations.forEach(function(it) {
            if (it.n) addIterationRow(it);
        });
    }
}
fetch('/api/status')
    .then(function (r) { return r.json(); })
    .then(function (fullState) {
        var led = fullState.ledger || {};
        var s = fullState.stats || {};
        var latest = fullState.latest_iteration || {};
        var renderData = {
            iteration: latest,
            status: fullState.loop_status || 'unknown',
            total_iterations: led.total_iterations || 0,
            max_iterations: led.max_iterations || 0,
            goal: (led.goal || '') || '-',
            evolved_goal: led.evolved_goal || '',
            started_at: led.started_at || '',
            last_updated: led.last_updated || '',
            stats: { success_count: s.success_count, error_count: s.error_count, total_duration_seconds: s.total_duration_seconds, avg_duration_seconds: s.avg_duration_seconds },
            consecutive_errors: s.consecutive_errors || 0,
            consecutive_successes: s.consecutive_successes || 0,
            cooldown: led.cooldown || 0,
            eta: fullState.eta || {},
            error_counts: fullState.error_counts || {},
            mitigations: fullState.mitigations || {}
        };
        renderDashboard(renderData);
        // Also fetch recent iterations for initial table render
        fetch('/api/iterations?limit=20')
            .then(function (r) { return r.json(); })
            .then(function (itData) {
                var iters = itData.iterations || [];
                if (iters.length > 0) {
                    renderData._iterations = iters;
                    renderDashboard(renderData);
                }
            })
            .catch(function () {});
    })
    .catch(function (err) {
        console.error('Initial fetch failed:', err);
        document.getElementById('connection-status').textContent = '\\u25CF fetch error';
        document.getElementById('connection-status').className = 'disconnected';
    });
var evtSource = new EventSource('/live');
evtSource.addEventListener('init', function (event) {
    try {
        var data = JSON.parse(event.data);
        if (data && data.data) renderDashboard(data.data);
    } catch (e) {
        console.error('SSE parse error:', e);
    }
});
evtSource.addEventListener('update', function (event) {
    try {
        var d = JSON.parse(event.data);
        if (d.type === 'status_update' && d.data) {
            var s = d.data.stats || {};
            var led = d.data.ledger || {};
            // In SSE mode, the iteration comes from d.data.latest_iteration
            // (not from ledger.iterations which does not exist in get_status() output)
            var latest = d.data.latest_iteration || {};
            var et = d.data.error_counts || {};
            renderDashboard({
                iteration: latest,
                status: d.data.loop_status || 'unknown',
                total_iterations: led.total_iterations || 0,
                max_iterations: led.max_iterations || 0,
                goal: led.goal || '-',
                evolved_goal: led.evolved_goal || '',
                started_at: led.started_at || '',
                last_updated: led.last_updated || '',
                stats: { success_count: s.success_count, error_count: s.error_count, total_duration_seconds: s.total_duration_seconds, avg_duration_seconds: s.avg_duration_seconds },
                consecutive_errors: s.consecutive_errors || 0,
                consecutive_successes: s.consecutive_successes || 0,
                cooldown: led.cooldown || 0,
                eta: d.data.eta || {},
                error_counts: et,
                mitigations: d.data.mitigations || {},
            });
        }
    } catch (e) {
        console.error('SSE parse error:', e);
    }
});
evtSource.addEventListener('heartbeat', function () {});
evtSource.onopen = function () {
    document.getElementById('connection-status').textContent = '\\u25CF connected';
    document.getElementById('connection-status').className = 'connected';
};
evtSource.onerror = function (err) {
    console.error('SSE error, reconnecting...', err);
    document.getElementById('connection-status').textContent = '\\u25CF disconnected (reconnecting...)';
    document.getElementById('connection-status').className = 'disconnected';
};
</script>
</body>
</html>"""


def _generate_status_html(state: dict, compact: bool = False) -> str:
    """Generate a self-contained HTML page from the current ledger state."""
    status = state.get("status", "unknown")
    status_cls = {"running": "running", "paused": "paused"}.get(status, "stopped")
    total = state.get("total_iterations", 0)
    goal = (state.get("initial_command") or "(none)")[:80]
    started = (state.get("started_at") or "?")[:19]
    last_upd = (state.get("last_updated") or "?")[:19]
    stats = state.get("stats", {})
    success = stats.get("success_count", 0)
    errors = stats.get("error_count", 0)
    total_dur = stats.get("total_duration_seconds", 0)
    avg_dur = stats.get("avg_duration_seconds", 0)

    iterations = state.get("iterations", [])
    cpu_sec = "0.0"
    mem_mb = "0"
    mem_pct = "0.0"
    if iterations:
        last_it = iterations[-1]
        cpu_sec = str(last_it.get("cpu_seconds_used", last_it.get("cpu_seconds", 0)))
        mem_val = last_it.get("memory_rss_mb", 0)
        mem_mb = f"{mem_val:.0f}" if isinstance(mem_val, float) else str(mem_val)
        mp_val = last_it.get("memory_percent", 0)
        if isinstance(mp_val, float):
            mem_pct = f"{mp_val * 100:.1f}"
        else:
            mem_pct = str(mp_val)

    eta_text = "N/A"
    max_it = state.get("max_iterations", 0)
    if max_it > 0 and total > 0:
        remaining = max_it - total
        if remaining > 0 and avg_dur > 0:
            eta_secs = remaining * avg_dur
            if eta_secs >= 3600:
                eta_text = f"{eta_secs / 3600:.1f}h"
            elif eta_secs >= 60:
                eta_text = f"{eta_secs / 60:.0f}m"
            else:
                eta_text = f"{eta_secs:.0f}s"
        elif remaining <= 0:
            eta_text = "Done"

    cooldown_val = state.get("cooldown", 0) or stats.get("cooldown", 0)
    cooldown_text = f"{cooldown_val}s" if cooldown_val else "None"
    cooldown_cls = "cooldown-active" if cooldown_val else "cooldown-idle"

    progress_row = ""
    if max_it > 0:
        pct = min(100.0 * total / max_it, 100.0) if max_it > 0 else 0
        progress_row = f'<h2>Progress</h2><div class="progress"><div class="progress-fill" style="width:{pct:.0f}%"></div></div><p style="font-size:0.8rem;color:var(--muted)">{total}/{max_it} ({pct:.0f}%)</p>'

    evolved = state.get("evolved_goal", "")
    eva_row = (
        f'<h2>Evolved Goal</h2><p style="color:var(--accent)">{evolved[:100]}</p>'
        if evolved
        else ""
    )

    summary_only_text = f"{total} iterations, {success} success, {errors} errors, {total_dur:.0f}s total, {avg_dur:.0f}s avg"

    rows = []
    for it in reversed(iterations[-100:]):
        n = it.get("n", "?")
        started_at = (it.get("started_at") or "?")[:16]
        dur = it.get("duration_seconds", 0)
        tt = it.get("task_type", "")
        summary = (it.get("summary") or "")[:100]
        err = it.get("error")
        has_err = bool(err)
        err_cls = ' class="error-row"' if has_err else ""
        has_evolve = bool(it.get("next_goal"))
        wt = it.get("worktree_merge") or {}
        has_wtree = bool(wt.get("merged", 0) > 0 or wt.get("failed", 0) > 0)
        tags = ""
        if has_err:
            tags += '<span class="tag tag-err">ERR</span> '
        if has_evolve:
            tags += '<span class="tag tag-evolve">EVOLVE</span> '
        if has_wtree:
            wt_parts = []
            if wt.get("merged", 0) > 0:
                wt_parts.append(f"WT:{wt['merged']}")
            if wt.get("failed", 0) > 0:
                wt_parts.append(f"WT-FAIL:{wt['failed']}")
            tags += f'<span class="tag tag-wtree">{" ".join(wt_parts)}</span> '

        it_eta = "N/A"
        if avg_dur > 0:
            remaining_eta = max_it - n if max_it > 0 else 0
            if remaining_eta > 0:
                it_eta_secs = remaining_eta * avg_dur
                if it_eta_secs >= 3600:
                    it_eta = f"{it_eta_secs / 3600:.1f}h"
                elif it_eta_secs >= 60:
                    it_eta = f"{it_eta_secs / 60:.0f}m"
                else:
                    it_eta = f"{it_eta_secs:.0f}s"

        rows.append(
            f"<tr{err_cls}><td>{n}</td><td>{started_at}</td>"
            f'<td>{dur}s</td><td>{tags}<span class="tag" style="color:var(--muted)">{tt}</span></td>'
            f'<td class="summary" title="{summary.replace(chr(34), "&quot;")}">{summary}</td>'
            f"<td>{it_eta}</td></tr>"
        )

    html = (
        _STATUS_HTML_TPL.replace("{STATUS_CLASS}", status_cls)
        .replace("{STATUS}", status)
        .replace("{TOTAL}", str(total))
        .replace("{GOAL}", goal)
        .replace("{STARTED}", started)
        .replace("{LAST_UPDATED}", last_upd)
        .replace("{SUCCESS}", str(success))
        .replace("{ERRORS}", str(errors))
        .replace("{TOTAL_DUR}", f"{total_dur:.0f}")
        .replace("{AVG_DUR}", f"{avg_dur:.0f}")
        .replace("{CPU_SEC}", cpu_sec)
        .replace("{MEM_MB}", mem_mb)
        .replace("{MEM_PCT}", mem_pct)
        .replace("{ETA}", eta_text)
        .replace("{COOLDOWN}", cooldown_text)
        .replace("{COOLDOWN_CLASS}", cooldown_cls)
        .replace("{EVA_GOAL_ROW}", eva_row)
        .replace("{PROGRESS_ROW}", progress_row)
        .replace("{ITER_ROWS}", "".join(rows))
        .replace("{SUMMARY_ONLY_TEXT}", summary_only_text)
        .replace("{VERSION}", LAUNCH_LOOP_VERSION)
    )

    if compact:
        html = html.replace("<body>", '<body class="compact-mode">')

    return html


def _write_status_html(html_path: str, state: dict):
    """Write the status HTML dashboard to a file."""
    try:
        html = _generate_status_html(state)
        os.makedirs(os.path.dirname(os.path.abspath(html_path)), exist_ok=True)
        with open(html_path, "w") as f:
            f.write(html)
    except (OSError, IOError) as e:
        _log(f"[HTML-DASH] Failed to write status page {html_path}: {e}")


def _broadcast_to_sse_clients(state: dict) -> None:
    """Push the latest iteration state as an SSE event to all connected clients."""
    global _sse_clients
    payload = _build_sse_payload(state)
    payload_json = json.dumps(payload, default=str)
    with _sse_clients_lock:
        alive = []
        for q in _sse_clients:
            try:
                q.put_nowait(payload_json)
                alive.append(q)
            except Exception:
                pass
        _sse_clients = alive


def _build_sse_payload(state: dict) -> dict:
    """Build a compact JSON payload from the full ledger state for SSE push."""
    stats = state.get("stats", {})
    iterations = state.get("iterations", [])
    latest = iterations[-1] if iterations else {}
    et = state.get("error_type_counts", {})
    mitigations = state.get("mitigations", {})
    mitigations["consecutive_errors"] = stats.get("consecutive_errors", 0)
    goals_completed = state.get("goals_completed", {})
    goals_specs = state.get("goals_specs", [])
    goals_list = []
    for idx, spec in enumerate(goals_specs):
        gtext = spec[0] if isinstance(spec, (tuple, list)) else spec
        gh = _goal_hash(gtext) if gtext else ""
        done = (
            gh in goals_completed and goals_completed[gh].get("status") == "completed"
        )
        active = False
        if state.get("goal_index") is not None:
            active = idx == state["goal_index"]
        goals_list.append({"text": gtext[:100], "done": done, "active": active})
    total_iters = state.get("total_iterations", 0)
    avg_turns = stats.get("avg_turns_per_iter", None) or latest.get("turns_used", None)
    avg_tokens = stats.get("avg_tokens_per_iter", None) or latest.get(
        "tokens_used", None
    )
    iters_per_goal = None
    if goals_list and total_iters > 0:
        iters_per_goal = max(1, total_iters // max(len(goals_list), 1))
    return {
        "iteration": latest,
        "_iterations": iterations[-20:],  # last 20 for SSE dashboard init
        "status": state.get("status", "unknown"),
        "total_iterations": total_iters,
        "max_iterations": state.get("max_iterations", 0),
        "goal": (state.get("initial_command") or "")[:80],
        "evolved_goal": state.get("evolved_goal", ""),
        "started_at": state.get("started_at", ""),
        "last_updated": state.get("last_updated", ""),
        "stats": {
            "success_count": stats.get("success_count", 0),
            "error_count": stats.get("error_count", 0),
            "total_duration_seconds": stats.get("total_duration_seconds", 0),
            "avg_duration_seconds": stats.get("avg_duration_seconds", 0),
        },
        "consecutive_errors": stats.get("consecutive_errors", 0),
        "consecutive_successes": state.get("consecutive_successes", 0),
        "cooldown": state.get("cooldown", 0),
        "eta": state.get("eta", {}),
        "error_counts": {
            "timeout": et.get("timeout", 0),
            "network": et.get("network", 0),
            "schema": et.get("schema", 0),
            "unknown": et.get("unknown", 0),
        },
        "mitigations": mitigations,
        "goals": goals_list,
        "avg_turns_per_iter": avg_turns,
        "avg_tokens_per_iter": avg_tokens,
        "est_cost": state.get("est_cost", None),
        "iters_per_goal": iters_per_goal,
        "metrics_summary": "",
    }
