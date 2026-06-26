/* ── Hermes Loop Web UI — Application ──────────────────────────────────── */

const API = {
  status: '/api/status',
  ledger: '/api/ledger',
  config: '/api/config',
  configRaw: '/api/config/raw',
  iterations: '/api/iterations',
  logs: '/api/logs',
  health: '/api/health',
  start: '/api/loop/start',
  stop: '/api/loop/stop',
  pause: '/api/loop/pause',
  resume: '/api/loop/resume',
  cliPreview: '/api/config/cli-preview',
  live: '/live',
};

// ── State ─────────────────────────────────────────────────────────────────
let currentTab = 'dashboard';
let configData = null;
let configGroups = [];
let configValues = {};    // persistent values across group switches
let activeConfigGroup = null;
let loopStatus = 'stopped';
let pollInterval = null;
let sseSource = null;
let iterationsPage = 0;
const ITERATIONS_PER_PAGE = 25;

// ── Initialization ────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  initNavigation();
  initSSE();
  fetchStatus();
  startPolling();
});

function initNavigation() {
  document.querySelectorAll('.nav-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      switchTab(btn.dataset.tab);
    });
  });
}

function switchTab(tab) {
  currentTab = tab;
  document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
  document.querySelector(`.nav-btn[data-tab="${tab}"]`).classList.add('active');
  document.querySelectorAll('.tab-content').forEach(s => s.classList.remove('active'));
  document.getElementById(`tab-${tab}`).classList.add('active');

  if (tab === 'config' && !configData) loadConfig();
  if (tab === 'iterations') loadIterations();
  if (tab === 'logs') refreshLogs();
}

// ── SSE (Live Updates) ───────────────────────────────────────────────────
function initSSE() {
  if (sseSource) sseSource.close();

  sseSource = new EventSource(API.live);

  sseSource.addEventListener('init', (e) => {
    try {
      const data = JSON.parse(e.data);
      updateConnectionStatus(true);
      if (data.data) updateDashboard(data.data);
    } catch (err) { console.error('SSE init parse error:', err); }
  });

  sseSource.addEventListener('update', (e) => {
    try {
      const data = JSON.parse(e.data);
      if (data.type === 'status_update' && data.data) {
        updateDashboard(data.data);
      } else if (data.type === 'status') {
        loopStatus = data.status;
        updateControlButtons();
        updateLoopStatusBadge();
      }
    } catch (err) { console.error('SSE update parse error:', err); }
  });

  sseSource.addEventListener('heartbeat', () => {});

  sseSource.onopen = () => updateConnectionStatus(true);
  sseSource.onerror = () => {
    updateConnectionStatus(false);
    sseSource.close();
    setTimeout(initSSE, 5000);
  };
}

function updateConnectionStatus(connected) {
  const dot = document.querySelector('#connection-indicator .conn-dot');
  const text = document.getElementById('connection-text');
  if (connected) {
    dot.className = 'conn-dot connected';
    text.textContent = 'connected';
  } else {
    dot.className = 'conn-dot disconnected';
    text.textContent = 'reconnecting...';
  }
}

// ── Polling (fallback) ───────────────────────────────────────────────────
function startPolling() {
  if (pollInterval) clearInterval(pollInterval);
  pollInterval = setInterval(() => {
    if (currentTab === 'dashboard') fetchStatus();
    if (currentTab === 'logs') refreshLogs();
  }, 3000);
}

// ── Status Fetching ──────────────────────────────────────────────────────
async function fetchStatus() {
  try {
    const res = await fetch(API.status);
    const data = await res.json();
    updateDashboard(data);
  } catch (err) { console.error('Status fetch error:', err); }
}

function updateDashboard(data) {
  if (!data) return;

  // Loop status
  loopStatus = data.loop_status || 'stopped';
  updateLoopStatusBadge();
  updateControlButtons();

  // Ledger stats
  const led = data.ledger || {};
  document.getElementById('stat-iterations').textContent = led.total_iterations || 0;

  const stats = data.stats || {};
  document.getElementById('stat-success-errors').textContent =
    `${stats.success_count || 0} / ${stats.error_count || 0}`;

  const totalDur = stats.total_duration_seconds || 0;
  document.getElementById('stat-duration').textContent = formatDuration(totalDur);

  const avgDur = stats.avg_duration_seconds || 0;
  document.getElementById('stat-avg-duration').textContent = formatDuration(avgDur);

  // ETA
  const eta = data.eta || {};
  document.getElementById('stat-eta').textContent = eta.remaining_formatted || 'N/A';

  // Progress
  const maxIt = led.max_iterations || 0;
  const curIt = led.total_iterations || 0;
  const pct = maxIt > 0 ? Math.min(100 * curIt / maxIt, 100) : 0;
  document.getElementById('progress-fill').style.width = pct + '%';
  document.getElementById('progress-text').textContent =
    maxIt > 0 ? `${curIt}/${maxIt} (${pct.toFixed(0)}%)` : `${curIt} / ∞`;

  // Goal info
  document.getElementById('info-goal').textContent = led.goal || '—';
  document.getElementById('info-evolved').textContent = led.evolved_goal || '—';
  document.getElementById('info-started').textContent = formatTs(led.started_at);

  // Error breakdown
  const errCounts = data.error_counts || {};
  const errTotal = Object.values(errCounts).reduce((a, b) => a + (b || 0), 0);
  if (errTotal > 0) {
    document.getElementById('error-section').style.display = '';
    const grid = document.getElementById('error-grid');
    const types = [
      { key: 'timeout', label: 'Timeout', cls: 'etimeout' },
      { key: 'network', label: 'Network', cls: 'enetwork' },
      { key: 'schema', label: 'Schema', cls: 'eschema' },
      { key: 'unknown', label: 'Unknown', cls: 'eunknown' },
    ];
    grid.innerHTML = types.map(t =>
      `<div class="error-card ${t.cls}"><span class="ecount">${errCounts[t.key] || 0}</span>${t.label}</div>`
    ).join('');
  } else {
    document.getElementById('error-section').style.display = 'none';
  }

  // Mitigations
  const mitigations = data.mitigations || {};
  const activeMits = [];
  if (mitigations.timeout_increased) activeMits.push('Timeout Increased');
  if (mitigations.cooldown_elevated) activeMits.push('Cooldown Elevated');
  if (mitigations.force_subprocess) activeMits.push('Force Subprocess');
  if (mitigations.reduced_workers) activeMits.push('Reduced Workers');
  if (activeMits.length > 0) {
    document.getElementById('mitigation-section').style.display = '';
    document.getElementById('mitigation-list').innerHTML =
      activeMits.map(m => `<span class="mitigation-tag">${m}</span>`).join('');
  } else {
    document.getElementById('mitigation-section').style.display = 'none';
  }

  // Latest iteration
  const latest = data.latest_iteration;
  const latestDiv = document.getElementById('latest-iteration');
  if (latest && latest.n) {
    const cls = latest.error ? 'error-row' : '';
    const summary = (latest.summary || '').substring(0, 200);
    const errText = latest.error ? `<div class="lit-error">Error: ${latest.error}</div>` : '';
    latestDiv.innerHTML = `
      <div class="lit-header">
        <strong>#${latest.n}</strong> <span class="tag ${latest.error ? 'tag-err' : 'tag-ok'}">${latest.classification || latest.task_type || 'unknown'}</span>
        <span style="color:var(--fg-muted)">${latest.duration_seconds || 0}s</span>
      </div>
      <div class="lit-summary">${summary}</div>
      ${errText}
    `;
  } else {
    latestDiv.innerHTML = '<span style="color:var(--fg-muted)">No iterations yet</span>';
  }

  // Recent iterations table
  updateRecentIterations(data);

  // Update iteration count on iterations tab
  document.getElementById('iterations-count').textContent = `${led.total_iterations || 0} total`;
}

function updateRecentIterations(data) {
  const tbody = document.getElementById('recent-iterations-body');
  // Fetch full iterations list for the mini-table
  fetch(API.iterations + '?limit=10')
    .then(r => r.json())
    .then(result => {
      const iters = result.iterations || [];
      tbody.innerHTML = iters.map(it => {
        const cls = it.error ? 'error-row' : '';
        const tagCls = it.error ? 'tag-err' : 'tag-ok';
        const status = it.error ? 'ERR' : (it.classification || 'OK');
        return `<tr class="${cls}">
          <td>${it.n}</td>
          <td><span class="tag tag-info">${it.task_type || ''}</span></td>
          <td>${it.duration_seconds || 0}s</td>
          <td class="summary-col" title="${escapeHtml(it.summary || '')}">${(it.summary || '').substring(0, 80)}</td>
          <td><span class="tag ${tagCls}">${status}</span></td>
        </tr>`;
      }).join('');
    })
    .catch(() => {});
}

function updateLoopStatusBadge() {
  const badge = document.getElementById('loop-status-badge');
  badge.textContent = loopStatus;
  badge.className = 'badge ' + loopStatus;
}

function updateControlButtons() {
  const startBtn = document.getElementById('btn-start');
  const stopBtn = document.getElementById('btn-stop');
  const pauseBtn = document.getElementById('btn-pause');
  const resumeBtn = document.getElementById('btn-resume');

  startBtn.disabled = loopStatus === 'running';
  stopBtn.disabled = loopStatus === 'stopped';
  pauseBtn.disabled = loopStatus !== 'running';
  resumeBtn.disabled = loopStatus !== 'paused';
}

// ── Loop Control ──────────────────────────────────────────────────────────
async function controlLoop(action) {
  const endpoints = {
    start: API.start,
    stop: API.stop,
    pause: API.pause,
    resume: API.resume,
  };

  const url = endpoints[action];
  if (!url) return;

  try {
    const btn = document.getElementById(`btn-${action}`);
    if (btn) btn.disabled = true;

    const res = await fetch(url, { method: 'POST' });
    const data = await res.json();

    if (!data.success) {
      alert(`Error: ${data.error || 'Unknown error'}`);
    }

    // Immediate status refresh
    setTimeout(fetchStatus, 500);
    setTimeout(fetchStatus, 2000);
  } catch (err) {
    alert(`Failed to ${action} loop: ${err.message}`);
  } finally {
    const btn = document.getElementById(`btn-${action}`);
    if (btn) btn.disabled = false;
  }
}

// ── Configuration ─────────────────────────────────────────────────────────
async function loadConfig() {
  try {
    const res = await fetch(API.config);
    const data = await res.json();
    configData = data.config;
    configGroups = data.groups || [];
    renderConfigGroups();
  } catch (err) {
    console.error('Config load error:', err);
  }
}

function renderConfigGroups() {
  const container = document.getElementById('config-groups');
  container.innerHTML = configGroups.map((g, i) =>
    `<button class="config-group-btn${i === 0 ? ' active' : ''}" data-group="${g.id}">
      ${g.name}
    </button>`
  ).join('');

  // Init persistent values from loaded config
  if (configData) {
    Object.entries(configData).forEach(([key, meta]) => {
      if (!(key in configValues)) {
        configValues[key] = meta.value || meta.default || '';
      }
    });
  }

  container.querySelectorAll('.config-group-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      // Flush current group's DOM values before switching
      flushConfigGroup();
      container.querySelectorAll('.config-group-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      renderConfigPanel(btn.dataset.group);
    });
  });

  // Render first group
  if (configGroups.length > 0) {
    activeConfigGroup = configGroups[0].id;
    renderConfigPanel(configGroups[0].id);
  }
}

function flushConfigGroup() {
  // Read all currently rendered fields into configValues
  const fields = document.querySelectorAll('#config-panel [id^="cfg-"]');
  fields.forEach(field => {
    const key = field.name || field.id.replace('cfg-', '');
    if (key) configValues[key] = field.value;
  });
}

function renderConfigPanel(groupId) {
  const panel = document.getElementById('config-panel');
  if (!configData) {
    panel.innerHTML = '<div class="config-empty">Loading configuration...</div>';
    return;
  }

  activeConfigGroup = groupId;

  const groupFields = Object.entries(configData)
    .filter(([, meta]) => meta.group === groupId);

  if (groupFields.length === 0) {
    panel.innerHTML = '<div class="config-empty">No settings in this group.</div>';
    return;
  }

  panel.innerHTML = groupFields.map(([key, meta]) => {
    // Use persisted value if available, otherwise fall back to default
    const value = key in configValues ? configValues[key] : (meta.value || meta.default || '');
    const required = meta.required ? '<span class="required-mark">*</span>' : '';
    const desc = meta.description || '';
    let input;

    if (meta.type === 'bool') {
      input = `<select name="${key}" id="cfg-${key}">
        <option value="false"${value === 'false' ? ' selected' : ''}>false</option>
        <option value="true"${value === 'true' ? ' selected' : ''}>true</option>
      </select>`;
    } else if (meta.type === 'select' && meta.options) {
      input = `<select name="${key}" id="cfg-${key}">
        ${meta.options.map(o => `<option value="${o}"${value === o ? ' selected' : ''}>${o}</option>`).join('')}
      </select>`;
    } else if (meta.multiline) {
      input = `<textarea name="${key}" id="cfg-${key}" rows="3">${escapeHtml(value)}</textarea>`;
    } else if (meta.type === 'int' || meta.type === 'float') {
      input = `<input type="number" name="${key}" id="cfg-${key}" value="${escapeHtml(value)}" step="${meta.type === 'float' ? '0.1' : '1'}">`;
    } else {
      input = `<input type="text" name="${key}" id="cfg-${key}" value="${escapeHtml(value)}">`;
    }

    return `<div class="config-field">
      <label for="cfg-${key}">${meta.label || key}${required}</label>
      <div class="field-desc">${desc}</div>
      ${input}
    </div>`;
  }).join('');
}

async function saveConfig() {
  // Flush current group's DOM values into configValues
  flushConfigGroup();

  // Use the persistent configValues dict which has all groups' edits
  const config = { ...configValues };

  try {
    const res = await fetch(API.config, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config),
    });
    const data = await res.json();
    if (data.success) {
      showSavedMsg('Saved!');
    } else {
      alert('Failed to save configuration: ' + (data.message || 'unknown error'));
    }
  } catch (err) {
    alert(`Error saving config: ${err.message}`);
  }
}

function resetConfig() {
  if (!confirm('Reset all configuration fields to their current saved values?')) return;
  loadConfig();
  showSavedMsg('Reset');
}

function showSavedMsg(text) {
  const msg = document.getElementById('config-saved-msg');
  msg.textContent = text;
  msg.classList.add('show');
  setTimeout(() => msg.classList.remove('show'), 2000);
}

// ── Iterations Table ──────────────────────────────────────────────────────
async function loadIterations(page = 0) {
  iterationsPage = page;
  const offset = page * ITERATIONS_PER_PAGE;
  try {
    const res = await fetch(`${API.iterations}?limit=${ITERATIONS_PER_PAGE}&offset=${offset}`);
    const data = await res.json();
    renderIterations(data);
    renderIterationsPagination(data);
  } catch (err) {
    console.error('Iterations load error:', err);
  }
}

function renderIterations(data) {
  const tbody = document.getElementById('iterations-body');
  const iters = data.iterations || [];

  if (iters.length === 0) {
    tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:var(--fg-muted);padding:40px;">No iterations recorded yet</td></tr>';
    return;
  }

  tbody.innerHTML = iters.map(it => {
    const cls = it.error ? 'error-row' : '';
    const tagCls = it.error ? 'tag-err' : 'tag-ok';
    const status = it.error ? 'ERR' : (it.classification || 'OK');
    return `<tr class="${cls}">
      <td>${it.n}</td>
      <td style="white-space:nowrap;font-size:0.78rem;color:var(--fg-muted)">${formatTs(it.started_at)}</td>
      <td>${it.duration_seconds || 0}s</td>
      <td><span class="tag tag-info">${it.task_type || ''}</span></td>
      <td><span class="tag ${tagCls}">${status}</span></td>
      <td class="summary-col" title="${escapeHtml(it.summary || '')}">${(it.summary || '').substring(0, 100)}</td>
      <td style="color:var(--danger);font-size:0.78rem">${it.error ? it.error.substring(0, 60) : ''}</td>
    </tr>`;
  }).join('');
}

function renderIterationsPagination(data) {
  const totalPages = Math.ceil((data.total || 0) / ITERATIONS_PER_PAGE);
  const container = document.getElementById('iterations-pagination');

  if (totalPages <= 1) {
    container.innerHTML = '';
    return;
  }

  let html = `<button ${iterationsPage === 0 ? 'disabled' : ''} onclick="loadIterations(${iterationsPage - 1})">← Prev</button>`;
  html += `<span class="page-info">Page ${iterationsPage + 1} of ${totalPages}</span>`;
  html += `<button ${iterationsPage >= totalPages - 1 ? 'disabled' : ''} onclick="loadIterations(${iterationsPage + 1})">Next →</button>`;
  container.innerHTML = html;
}

// ── Logs ──────────────────────────────────────────────────────────────────
async function refreshLogs() {
  try {
    const res = await fetch(API.logs + '?limit=200');
    const data = await res.json();
    renderLogs(data.logs || []);
  } catch (err) { console.error('Logs fetch error:', err); }
}

function renderLogs(logs) {
  const container = document.getElementById('log-container');
  if (logs.length === 0) {
    container.innerHTML = '<div class="log-empty">No logs yet. Start the loop to see output.</div>';
    return;
  }

  const wasAtBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 50;

  container.innerHTML = logs.map(l =>
    `<div class="log-entry">
      <span class="log-ts">${formatTs(l.timestamp, true)}</span>
      <span class="log-level ${l.level}">${l.level.toUpperCase()}</span>
      <span class="log-msg">${escapeHtml(l.message)}</span>
    </div>`
  ).join('');

  if (wasAtBottom) {
    container.scrollTop = container.scrollHeight;
  }
}

function clearLogs() {
  document.getElementById('log-container').innerHTML =
    '<div class="log-empty">Logs cleared. New entries will appear here.</div>';
}

// ── Utilities ─────────────────────────────────────────────────────────────
function formatDuration(seconds) {
  if (!seconds || seconds <= 0) return '0s';
  if (seconds < 60) return `${seconds.toFixed(0)}s`;
  if (seconds < 3600) return `${(seconds / 60).toFixed(1)}m`;
  return `${(seconds / 3600).toFixed(1)}h`;
}

function formatTs(ts, showTime = false) {
  if (!ts) return '—';
  try {
    const s = ts.replace('T', ' ').replace('Z', '');
    return showTime ? s.substring(11, 19) : s.substring(0, 16);
  } catch (e) {
    return ts.substring(0, 16);
  }
}

function escapeHtml(str) {
  if (!str) return '';
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}
