/* ── Hermes Loop Web UI — Application ──────────────────────────────────── */

const API = {
  status: '/api/status', ledger: '/api/ledger', config: '/api/config',
  configRaw: '/api/config/raw', iterations: '/api/iterations', logs: '/api/logs',
  health: '/api/health', start: '/api/loop/start', stop: '/api/loop/stop',
  pause: '/api/loop/pause', resume: '/api/loop/resume',
  cliPreview: '/api/config/cli-preview', live: '/live',
};

// ── State ─────────────────────────────────────────────────────────────────
let currentTab = 'dashboard';
let configData = null, configGroups = [], configValues = {}, activeConfigGroup = null;
let loopStatus = 'stopped';
let sseSource = null;
let iterationsPage = 0;
const ITERATIONS_PER_PAGE = 25;
let lastLogIdx = -1;         // append-only log tracking
let workerLogFilter = null;  // filter logs by worker ID
let _lastSeenIterationCount = 0;  // only refetch iterations when count changes

// ── Initialization ────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.nav-btn').forEach(btn => {
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
  });
  initSSE();
  fetchStatus();
});

function switchTab(tab) {
  currentTab = tab;
  document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
  document.querySelector(`.nav-btn[data-tab="${tab}"]`).classList.add('active');
  document.querySelectorAll('.tab-content').forEach(s => s.classList.remove('active'));
  document.getElementById(`tab-${tab}`).classList.add('active');
  if (tab === 'config' && !configData) loadConfig();
  if (tab === 'iterations') loadIterations();
  if (tab === 'workers') { _lastWorkerLogCounts = {}; _activeWorkerLog = null; showWorkerCards(); fetchStatus(); }
}

// ── SSE (push-based updates, no polling) ─────────────────────────────────
function initSSE() {
  if (sseSource) sseSource.close();
  sseSource = new EventSource(API.live);

  sseSource.addEventListener('init', (e) => {
    try {
      const d = JSON.parse(e.data);
      updateConnectionStatus(true);
      if (d.data) updateDashboard(d.data);
    } catch (err) {}
  });

  sseSource.addEventListener('update', (e) => {
    try {
      const d = JSON.parse(e.data);
      if (d.type === 'status_update' && d.data) updateDashboard(d.data);
      else if (d.type === 'status') {
        loopStatus = d.status;
        updateControlButtons();
        updateLoopStatusBadge();
      }
      // Log entries pushed from server
      if (d.type === 'log_entry' && d.entry) appendLog(d.entry);
    } catch (err) {}
  });

  sseSource.addEventListener('heartbeat', () => {});
  sseSource.onopen = () => updateConnectionStatus(true);
  sseSource.onerror = () => {
    updateConnectionStatus(false);
    sseSource.close();
    setTimeout(initSSE, 5000);
  };
}

// ── Dashboard updates (granular DOM, no full re-renders) ──────────────────
async function fetchStatus() {
  try {
    const res = await fetch(API.status);
    updateDashboard(await res.json());
  } catch (err) {}
}

function updateDashboard(data) {
  if (!data) return;
  loopStatus = data.loop_status || 'stopped';
  updateLoopStatusBadge();
  updateControlButtons();

  const led = data.ledger || {};
  setText('stat-iterations', led.total_iterations || 0);
  const stats = data.stats || {};
  setText('stat-success-errors', `${stats.success_count || 0} / ${stats.error_count || 0}`);
  setText('stat-duration', formatDuration(stats.total_duration_seconds || 0));
  setText('stat-avg-duration', formatDuration(stats.avg_duration_seconds || 0));
  const eta = data.eta || {};
  setText('stat-eta', eta.remaining_formatted || 'N/A');

  const maxIt = led.max_iterations || 0, curIt = led.total_iterations || 0;
  const pct = maxIt > 0 ? Math.min(100 * curIt / maxIt, 100) : 0;
  document.getElementById('progress-fill').style.width = pct + '%';
  setText('progress-text', maxIt > 0 ? `${curIt}/${maxIt} (${pct.toFixed(0)}%)` : `${curIt} / ∞`);

  setText('info-goal', led.goal || '—');
  setText('info-evolved', led.evolved_goal || '—');
  setText('info-started', formatTs(led.started_at));

  // Error breakdown
  const errCounts = data.error_counts || {};
  const errTotal = Object.values(errCounts).reduce((a, b) => a + (b || 0), 0);
  const errSection = document.getElementById('error-section');
  if (errTotal > 0) {
    errSection.style.display = '';
    ['timeout','network','schema','unknown'].forEach((k, i) => {
      const cls = ['etimeout','enetwork','eschema','eunknown'][i];
      const card = document.getElementById(`err-card-${k}`);
      if (card) card.querySelector('.ecount').textContent = errCounts[k] || 0;
    });
  } else { errSection.style.display = 'none'; }

  // Mitigations
  const m = data.mitigations || {};
  const active = [];
  if (m.timeout_increased) active.push('Timeout+');
  if (m.cooldown_elevated) active.push('Cooldown+');
  if (m.force_subprocess) active.push('No-Library');
  if (m.reduced_workers) active.push('Workers-');
  const mitSection = document.getElementById('mitigation-section');
  if (active.length) {
    mitSection.style.display = '';
    document.getElementById('mitigation-list').innerHTML =
      active.map(t => `<span class="mitigation-tag">${escapeHtml(t)}</span>`).join('');
  } else { mitSection.style.display = 'none'; }

  updateLiveIteration(data.live_iteration);
  updateLatestIteration(data.latest_iteration);
  updateRecentIterations(data);
  setText('iterations-count', `${led.total_iterations || 0} total`);

  // Workers tab
  if (currentTab === 'workers') renderWorkers(data);

  // Feed active worker terminal regardless of tab visibility
  if (_activeWorkerLog !== null && data.worker_term) {
    feedWorkerTerminal(_activeWorkerLog, (data.worker_term[_activeWorkerLog] || []));
  }

  // Append new log entries
  const logs = data.recent_logs || [];
  if (logs.length > 0) {
    for (let i = lastLogIdx + 1; i < logs.length; i++) appendLog(logs[i]);
    lastLogIdx = logs.length - 1;
  }
}

function updateLatestIteration(latest) {
  const div = document.getElementById('latest-iteration');
  if (latest && latest.n) {
    const tagCls = latest.error ? 'tag-err' : 'tag-ok';
    const summary = (latest.summary || '').substring(0, 200);
    const errText = latest.error ? `<div class="lit-error">Error: ${escapeHtml(String(latest.error))}</div>` : '';
    const wt = latest.worktree_merge;
    const wtText = (wt && (wt.merged > 0 || wt.failed > 0))
      ? `<div class="lit-wt-merge"><span class="tag tag-wt">wt:${wt.merged}✓ ${wt.failed}✗${wt.skipped ? ' ' + wt.skipped + '–' : ''}</span></div>`
      : '';
    div.innerHTML = `<div class="lit-header">
      <strong>#${latest.n}</strong> <span class="tag ${tagCls}">${escapeHtml(latest.classification || latest.task_type || 'unknown')}</span>
      <span style="color:var(--fg-muted)">${latest.duration_seconds || 0}s</span>
    </div><div class="lit-summary">${escapeHtml(summary)}</div>${errText}${wtText}`;
  } else {
    div.innerHTML = '<span style="color:var(--fg-muted)">No iterations yet</span>';
  }
}

function updateRecentIterations(data) {
  const count = (data.ledger && data.ledger.total_iterations) || 0;
  const tbody = document.getElementById('recent-iterations-body');

  // Reset scenario: count dropped below last seen — clear existing rows
  if (count < _lastSeenIterationCount) {
    tbody.innerHTML = '';
    _lastSeenIterationCount = 0;
  }
  if (count <= _lastSeenIterationCount) return;
  _lastSeenIterationCount = count;

  // Use latest_iteration from SSE data to avoid a separate fetch race
  const latest = data.latest_iteration;
  if (latest && latest.n) {
    // Collect Ns already in the DOM to prevent duplicates
    const seenNs = new Set();
    tbody.querySelectorAll('tr').forEach(row => {
      const td = row.querySelector('td');
      if (td) {
        const rowN = parseInt(td.textContent, 10);
        if (!isNaN(rowN)) seenNs.add(rowN);
      }
    });

    // Only add the latest row if it's not already present
    if (!seenNs.has(latest.n)) {
      const cls = latest.error ? 'error-row' : '';
      const tagCls = latest.error ? 'tag-err' : 'tag-ok';
      const wt = latest.worktree_merge;
      const wtHtml = (wt && (wt.merged > 0 || wt.failed > 0))
        ? `<span class="tag tag-wt" title="merged:${wt.merged} failed:${wt.failed}${wt.skipped != null ? ' skipped:'+wt.skipped : ''}">wt:${wt.merged}✓ ${wt.failed}✗</span>`
        : '';
      const rowHtml = `<tr class="${cls}">
        <td>${latest.n}</td><td><span class="tag tag-info">${escapeHtml(latest.task_type || '')}</span></td>
        <td>${latest.duration_seconds || 0}s</td>
        <td class="summary-col" title="${escapeHtml(latest.summary || '')}">${escapeHtml((latest.summary || '').substring(0, 80))}</td>
        <td><span class="tag ${tagCls}">${latest.error ? 'ERR' : (latest.classification || 'OK')}</span></td>
        <td style="font-size:0.78rem">${wtHtml}</td>
      </tr>`;
      // Prepend to tbody (insert after any existing header-like content, if any)
      const temp = document.createElement('tbody');
      temp.innerHTML = rowHtml;
      tbody.insertBefore(temp.firstChild, tbody.firstChild);
    }
  } else {
    // Fallback: fetch full list if latest_iteration isn't available
    fetch(API.iterations + '?limit=10').then(r => r.json()).then(result => {
      const iters = result.iterations || [];
      const seenNs = new Set();
      tbody.querySelectorAll('tr').forEach(row => {
        const td = row.querySelector('td');
        if (td) {
          const rowN = parseInt(td.textContent, 10);
          if (!isNaN(rowN)) seenNs.add(rowN);
        }
      });
      const frag = document.createDocumentFragment();
      iters.forEach(it => {
        if (seenNs.has(it.n)) return;
        seenNs.add(it.n);
        const cls = it.error ? 'error-row' : '';
        const tagCls = it.error ? 'tag-err' : 'tag-ok';
        const wt = it.worktree_merge;
        const wtHtml = (wt && (wt.merged > 0 || wt.failed > 0))
          ? `<span class="tag tag-wt" title="merged:${wt.merged} failed:${wt.failed}${wt.skipped != null ? ' skipped:'+wt.skipped : ''}">wt:${wt.merged}✓ ${wt.failed}✗</span>`
          : '';
        const temp = document.createElement('tbody');
        temp.innerHTML = `<tr class="${cls}">
          <td>${it.n}</td><td><span class="tag tag-info">${escapeHtml(it.task_type || '')}</span></td>
          <td>${it.duration_seconds || 0}s</td>
          <td class="summary-col" title="${escapeHtml(it.summary || '')}">${escapeHtml((it.summary || '').substring(0, 80))}</td>
          <td><span class="tag ${tagCls}">${it.error ? 'ERR' : (it.classification || 'OK')}</span></td>
          <td style="font-size:0.78rem">${wtHtml}</td>
        </tr>`;
        frag.insertBefore(temp.firstChild, frag.firstChild);
      });
      tbody.insertBefore(frag, tbody.firstChild);
      // Update _lastSeenIterationCount from fetched data
      if (result.total_iterations != null) {
        _lastSeenIterationCount = result.total_iterations;
      }
    }).catch(() => {});
  }
}

function updateLiveIteration(live) {
  const section = document.getElementById('live-section');
  if (!live || !live.n) { section.style.display = 'none'; return; }
  section.style.display = '';
  document.getElementById('live-iter-num').textContent = '#' + live.n;
  const el = live.elapsed_seconds || 0;
  document.getElementById('live-elapsed').textContent = el > 0
    ? `(${Math.floor(el/60)}m ${el%60}s)` : '';
  const workers = live.workers || [];
  const grid = document.getElementById('worker-grid');
  if (!workers.length) { grid.innerHTML = '<div class="worker-card"><div class="wstatus">Waiting...</div></div>'; return; }
  grid.innerHTML = workers.map(w => {
    const cls = w.status === 'ok' ? 'ok' : (w.status === 'error' ? 'error' : 'running');
    const label = w.status === 'ok' ? 'OK' : (w.status === 'error' ? 'ERR' : 'Running');
    const dur = w.duration_seconds ? w.duration_seconds.toFixed(0) + 's' : '...';
    return `<div class="worker-card ${cls}" onclick="filterWorkerLogs('${w.id}')" title="Click to filter logs by Worker #${w.id}">
      <div class="wid">Worker #${w.id}</div>
      <div class="wstatus">${label}</div>
      <div class="wdur">${dur}</div>
    </div>`;
  }).join('');
}

// ── Append-only log rendering (preserves text selection) ──────────────────
function appendLog(entry) {
  if (!entry || !entry.message) return;
  // Extract worker ID from message for filtering
  const workerMatch = entry.message.match(/worker\s*#(\d+)/i);
  const wid = workerMatch ? workerMatch[1] : null;

  const container = document.getElementById('log-container');
  // Clear empty state on first entry
  if (container.querySelector('.log-empty')) container.innerHTML = '';

  const wasAtBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 80;

  const msgSpan = document.createElement('span');
  msgSpan.className = 'log-msg';
  msgSpan.textContent = entry.message;

  const levelSpan = document.createElement('span');
  levelSpan.className = 'log-level ' + (entry.level || 'info');
  levelSpan.textContent = (entry.level || 'INFO').toUpperCase();

  const tsSpan = document.createElement('span');
  tsSpan.className = 'log-ts';
  tsSpan.textContent = formatTs(entry.timestamp, true);

  const div = document.createElement('div');
  div.className = 'log-entry';
  if (wid) div.dataset.worker = wid;
  div.appendChild(tsSpan);
  div.appendChild(levelSpan);
  div.appendChild(msgSpan);
  container.appendChild(div);

  // Apply worker filter
  if (workerLogFilter !== null) {
    div.style.display = (wid === workerLogFilter) ? '' : 'none';
  }

  // Cap at 500 entries
  while (container.children.length > 500) container.removeChild(container.firstChild);

  if (wasAtBottom) container.scrollTop = container.scrollHeight;
}

function filterWorkerLogs(wid) {
  if (workerLogFilter === wid) {
    workerLogFilter = null;  // toggle off
  } else {
    workerLogFilter = wid;
  }
  const container = document.getElementById('log-container');
  container.querySelectorAll('.log-entry').forEach(el => {
    el.style.display = (!workerLogFilter || el.dataset.worker === workerLogFilter) ? '' : 'none';
  });
  // Update worker card highlights
  document.querySelectorAll('.worker-card').forEach(c => c.style.outline = '');
  if (workerLogFilter) {
    const card = document.querySelector(`.worker-card[onclick*="${workerLogFilter}"]`);
    if (card) card.style.outline = '2px solid var(--accent)';
  }
  // Also update filter badge
  const badge = document.getElementById('log-filter-badge');
  if (badge) {
    badge.textContent = workerLogFilter ? `Worker #${workerLogFilter}` : '';
    badge.style.display = workerLogFilter ? '' : 'none';
  }
}

// ── Controls ──────────────────────────────────────────────────────────────
function updateLoopStatusBadge() {
  const b = document.getElementById('loop-status-badge');
  b.textContent = loopStatus;
  b.className = 'badge ' + loopStatus;
}
function updateControlButtons() {
  document.getElementById('btn-start').disabled = loopStatus === 'running';
  document.getElementById('btn-stop').disabled = loopStatus === 'stopped';
  document.getElementById('btn-pause').disabled = loopStatus !== 'running';
  document.getElementById('btn-resume').disabled = loopStatus !== 'paused';
}

async function resetLedger() {
  if (!confirm('Reset the ledger?')) return;
  try {
    const res = await fetch('/api/loop/reset', { method: 'POST' });
    const data = await res.json();
    if (data.success) { lastLogIdx = -1; _lastWorkerLogCounts = {}; _lastSeenIterationCount = 0; fetchStatus(); }
    else alert('Reset failed: ' + (data.error || 'unknown'));
  } catch (err) { alert('Reset failed: ' + err.message); }
}

async function controlLoop(action) {
  const endpoints = { start: API.start, stop: API.stop, pause: API.pause, resume: API.resume };
  const url = endpoints[action]; if (!url) return;
  try {
    const btn = document.getElementById(`btn-${action}`);
    if (btn) btn.disabled = true;
    const res = await fetch(url, { method: 'POST' });
    const data = await res.json();
    if (!data.success) alert(`Error: ${data.error || 'Unknown error'}`);
    if (action === 'start') { lastLogIdx = -1; _lastWorkerLogCounts = {}; _lastSeenIterationCount = 0; document.getElementById('log-container').innerHTML = ''; }
    setTimeout(fetchStatus, 500);
    setTimeout(fetchStatus, 2000);
  } catch (err) { alert(`Failed: ${err.message}`); }
  finally { const btn = document.getElementById(`btn-${action}`); if (btn) btn.disabled = false; }
}

// ── Configuration ─────────────────────────────────────────────────────────
async function loadConfig() {
  try {
    const res = await fetch(API.config);
    const data = await res.json();
    configData = data.config; configGroups = data.groups || [];
    renderConfigGroups();
  } catch (err) {}
}
function renderConfigGroups() {
  const container = document.getElementById('config-groups');
  container.innerHTML = configGroups.map((g, i) =>
    `<button class="config-group-btn${i === 0 ? ' active' : ''}" data-group="${g.id}">${g.name}</button>`).join('');
  if (configData) Object.entries(configData).forEach(([k, m]) => {
    if (!(k in configValues)) configValues[k] = m.value || m.default || '';
  });
  container.querySelectorAll('.config-group-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      flushConfigGroup();
      container.querySelectorAll('.config-group-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      renderConfigPanel(btn.dataset.group);
    });
  });
  if (configGroups.length > 0) { activeConfigGroup = configGroups[0].id; renderConfigPanel(configGroups[0].id); }
}
function flushConfigGroup() {
  document.querySelectorAll('#config-panel [id^="cfg-"]').forEach(f => {
    const k = f.name || f.id.replace('cfg-', '');
    if (k) configValues[k] = f.value;
  });
}
function renderConfigPanel(groupId) {
  const panel = document.getElementById('config-panel');
  if (!configData) { panel.innerHTML = '<div class="config-empty">Loading...</div>'; return; }
  activeConfigGroup = groupId;
  const fields = Object.entries(configData).filter(([, m]) => m.group === groupId);
  if (!fields.length) { panel.innerHTML = '<div class="config-empty">No settings in this group.</div>'; return; }
  panel.innerHTML = fields.map(([key, meta]) => {
    const v = key in configValues ? configValues[key] : (meta.value || meta.default || '');
    const req = meta.required ? '<span class="required-mark">*</span>' : '';
    const desc = meta.description || ''; let input;
    if (meta.type === 'bool') input = `<select name="${key}" id="cfg-${key}"><option value="false"${v==='false'?' selected':''}>false</option><option value="true"${v==='true'?' selected':''}>true</option></select>`;
    else if (meta.type === 'select' && meta.options) input = `<select name="${key}" id="cfg-${key}">${meta.options.map(o => `<option value="${o}"${v===o?' selected':''}>${o}</option>`).join('')}</select>`;
    else if (meta.multiline) input = `<textarea name="${key}" id="cfg-${key}" rows="3">${escapeHtml(v)}</textarea>`;
    else if (meta.type === 'int' || meta.type === 'float') input = `<input type="number" name="${key}" id="cfg-${key}" value="${escapeHtml(v)}" step="${meta.type==='float'?'0.1':'1'}">`;
    else input = `<input type="text" name="${key}" id="cfg-${key}" value="${escapeHtml(v)}">`;
    return `<div class="config-field"><label for="cfg-${key}">${meta.label||key}${req}</label><div class="field-desc">${desc}</div>${input}</div>`;
  }).join('');
}
async function saveConfig() {
  flushConfigGroup();
  try {
    const res = await fetch(API.config, { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({...configValues}) });
    const data = await res.json();
    data.success ? showSavedMsg('Saved!') : alert('Failed: ' + (data.message || 'unknown'));
  } catch (err) { alert('Error: ' + err.message); }
}
function resetConfig() { if (confirm('Reset all config fields?')) { loadConfig(); showSavedMsg('Reset'); } }
function showSavedMsg(t) { const m = document.getElementById('config-saved-msg'); m.textContent = t; m.classList.add('show'); setTimeout(() => m.classList.remove('show'), 2000); }

// ── Iterations Table ──────────────────────────────────────────────────────
async function loadIterations(page = 0) {
  iterationsPage = page;
  try {
    const res = await fetch(`${API.iterations}?limit=${ITERATIONS_PER_PAGE}&offset=${page*ITERATIONS_PER_PAGE}`);
    const data = await res.json();
    const tbody = document.getElementById('iterations-body');
    const iters = data.iterations || [];
    if (!iters.length) { tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;color:var(--fg-muted);padding:40px;">No iterations yet</td></tr>'; return; }
    tbody.innerHTML = iters.map(it => {
      const cls = it.error ? 'error-row' : '';
      const tagCls = it.error ? 'tag-err' : 'tag-ok';
      const wt = it.worktree_merge;
      const wtHtml = (wt && (wt.merged > 0 || wt.failed > 0))
        ? `<span class="tag tag-wt" title="merged:${wt.merged} failed:${wt.failed}${wt.skipped != null ? ' skipped:'+wt.skipped : ''}">wt:${wt.merged}✓ ${wt.failed}✗</span>`
        : '';
      return `<tr class="${cls}"><td>${it.n}</td><td style="white-space:nowrap;font-size:0.78rem;color:var(--fg-muted)">${formatTs(it.started_at)}</td><td>${it.duration_seconds||0}s</td><td><span class="tag tag-info">${escapeHtml(it.task_type||'')}</span></td><td><span class="tag ${tagCls}">${it.error?'ERR':(it.classification||'OK')}</span></td><td class="summary-col" title="${escapeHtml(it.summary||'')}">${escapeHtml((it.summary||'').substring(0,100))}</td><td style="color:var(--danger);font-size:0.78rem">${it.error?escapeHtml(String(it.error).substring(0,60)):''}</td><td style="font-size:0.78rem">${wtHtml}</td></tr>`;
    }).join('');
    const tp = Math.ceil((data.total||0)/ITERATIONS_PER_PAGE);
    const pc = document.getElementById('iterations-pagination');
    pc.innerHTML = tp > 1 ? `<button ${iterationsPage===0?'disabled':''} onclick="loadIterations(${iterationsPage-1})">← Prev</button><span class="page-info">Page ${iterationsPage+1} of ${tp}</span><button ${iterationsPage>=tp-1?'disabled':''} onclick="loadIterations(${iterationsPage+1})">Next →</button>` : '';
  } catch (err) {}
}

// ── Workers Tab (cards → click for real xterm.js terminal) ─────────────
let _lastWorkerLogCounts = {};
let _lastWorkerTermIdx = {};
let _activeWorkerLog = null;
let _allWorkerData = null;
let _workerTerminals = {};  // wid -> {term, fit}

function createWorkerTerminal(wid) {
  const container = document.getElementById('worker-terminal-container');
  container.innerHTML = '';

  const term = new Terminal({
    cursorBlink: true,
    fontSize: 13,
    fontFamily: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace",
    theme: {
      background: '#0d1117',
      foreground: '#c9d1d9',
      cursor: '#58a6ff',
      selectionBackground: '#264f78',
      black: '#484f58', red: '#ff7b72', green: '#3fb950',
      yellow: '#d29922', blue: '#58a6ff', magenta: '#bc8cff',
      cyan: '#39c5cf', white: '#b1bac4',
      brightBlack: '#6e7681', brightRed: '#ffa198', brightGreen: '#56d364',
      brightYellow: '#e3b341', brightBlue: '#79c0ff', brightMagenta: '#d2a8ff',
      brightCyan: '#56d4dd', brightWhite: '#f0f6fc',
    },
    allowProposedApi: true,
    scrollback: 5000,
  });

  const fitAddon = new FitAddon.FitAddon();
  term.loadAddon(fitAddon);
  term.open(container);
  fitAddon.fit();

  _workerTerminals[wid] = { term, fit: fitAddon };
  _lastWorkerTermIdx[wid] = 0;

  // Feed existing terminal output
  const termLines = _allWorkerData ? (_allWorkerData.worker_term || {})[wid] || [] : [];
  termLines.forEach(line => term.write(line + '\r\n'));

  return term;
}

function renderWorkers(data) {
  _allWorkerData = data;
  const container = document.getElementById('worker-cards');
  const live = data.live_iteration;
  const workerLogs = data.worker_logs || {};
  const allWorkers = live && live.workers ? [...live.workers] : [];
  const seenIds = new Set(allWorkers.map(w => w.id));
  Object.keys(workerLogs).forEach(wid => {
    if (!seenIds.has(wid)) allWorkers.push({id: wid, status: 'running'});
  });

  if (!allWorkers.length) {
    container.innerHTML = '<div class="log-empty">No workers active. Start the loop to see per-worker output.</div>';
    _lastWorkerLogCounts = {};
    return;
  }

  document.getElementById('workers-subtitle').textContent =
    live && live.n ? `Iteration #${live.n} — ${allWorkers.filter(w => w.status === 'running').length} running, ${allWorkers.filter(w => w.status === 'ok').length} done` : '';

  container.innerHTML = allWorkers.map(w => {
    const cls = w.status === 'ok' ? 'ok' : (w.status === 'error' ? 'error' : 'running');
    const dur = w.duration_seconds ? w.duration_seconds.toFixed(0) + 's' : '';
    const logs = workerLogs[w.id] || [];
    const termLines = (data.worker_term || {})[w.id] || [];
    const label = w.status === 'ok' ? 'Done' : w.status === 'error' ? 'Error' : 'Running';
    return `<div class="worker-card-item ${cls}" onclick="showWorkerLog('${w.id}')">
      <div class="wc-wid">Worker #${w.id}</div>
      <div class="wc-status">${label}</div>
      <div class="wc-dur">${dur}</div>
      <div class="wc-lines">${termLines.length} lines</div>
    </div>`;
  }).join('');

  // If viewing a worker, feed new terminal lines — now handled in updateDashboard
}

function showWorkerLog(wid) {
  _activeWorkerLog = wid;
  document.getElementById('workers-cards-view').style.display = 'none';
  document.getElementById('workers-log-view').style.display = '';

  const termLines = _allWorkerData ? (_allWorkerData.worker_term || {})[wid] || [] : [];
  document.getElementById('worker-log-title').textContent = 'Worker #' + wid;
  document.getElementById('worker-log-meta').textContent = termLines.length + ' lines';

  createWorkerTerminal(wid);
}

function showWorkerCards() {
  _activeWorkerLog = null;
  Object.values(_workerTerminals).forEach(t => { try { t.term.dispose(); } catch(e) {} });
  _workerTerminals = {};
  document.getElementById('workers-cards-view').style.display = '';
  document.getElementById('workers-log-view').style.display = 'none';
}

function feedWorkerTerminal(wid, termLines) {
  const t = _workerTerminals[wid];
  if (!t) return;
  const prevIdx = _lastWorkerTermIdx[wid] || 0;
  for (let i = prevIdx; i < termLines.length; i++) {
    t.term.write(termLines[i] + '\r\n');
  }
  _lastWorkerTermIdx[wid] = termLines.length;
  document.getElementById('worker-log-meta').textContent = termLines.length + ' lines';
}

// ── Utilities ─────────────────────────────────────────────────────────────
function setText(id, text) { const el = document.getElementById(id); if (el) el.textContent = text; }
function formatDuration(s) { if (!s || s <= 0) return '0s'; if (s < 60) return `${s.toFixed(0)}s`; if (s < 3600) return `${(s/60).toFixed(1)}m`; return `${(s/3600).toFixed(1)}h`; }
function formatTs(ts, time) { if (!ts) return '—'; try { const s = ts.replace('T',' ').replace('Z',''); return time ? s.substring(11,19) : s.substring(0,16); } catch(e) { return ts.substring(0,16); } }
function escapeHtml(s) { if (!s) return ''; const d = document.createElement('div'); d.textContent = String(s); return d.innerHTML; }
function updateConnectionStatus(ok) {
  document.querySelector('#connection-indicator .conn-dot').className = 'conn-dot ' + (ok ? 'connected' : 'disconnected');
  document.getElementById('connection-text').textContent = ok ? 'connected' : 'reconnecting...';
}
