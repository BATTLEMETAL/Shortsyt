/**
 * Shortsyt Dashboard — Frontend JS
 * Multi-account YouTube management panel
 */

// ── State ──────────────────────────────────────────────────
let accounts = [];
let activeSSE = null;     // current EventSource
let activeStreamKey = ''; // current stream key

// ── Init ───────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  loadStats();
  loadAccounts();
  setInterval(() => { loadStats(); loadAccounts(); }, 15000); // auto-refresh every 15s

  // Close modals on backdrop click
  document.getElementById('add-modal').addEventListener('click', e => {
    if (e.target.id === 'add-modal') closeAddModal();
  });
  document.getElementById('history-modal').addEventListener('click', e => {
    if (e.target.id === 'history-modal') closeHistoryModal();
  });

  // Auto-slug from display name
  document.getElementById('input-display-name').addEventListener('input', e => {
    const slugField = document.getElementById('input-id');
    if (!slugField._manuallyEdited) {
      slugField.value = e.target.value
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, '_')
        .replace(/^_+|_+$/g, '');
    }
  });
  document.getElementById('input-id').addEventListener('input', () => {
    document.getElementById('input-id')._manuallyEdited = true;
  });
});

// ── API helpers ─────────────────────────────────────────────
async function api(method, url, body) {
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json' },
  };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(url, opts);
  return res.json();
}

// ── Stats ───────────────────────────────────────────────────
async function loadStats() {
  try {
    const data = await api('GET', '/api/stats');
    setText('stat-accounts', data.total_accounts);
    setText('stat-tokens', data.active_tokens);
    setText('stat-videos', data.total_videos);
    setText('stat-running', data.running);

    // Running indicator on server dot
    const dot = document.getElementById('server-dot');
    if (data.running > 0) {
      dot.style.background = 'var(--accent2)';
      setText('server-status', `${data.running} automat${data.running > 1 ? 'y' : ''} działa`);
    } else {
      dot.style.background = 'var(--green)';
      setText('server-status', 'Panel online');
    }
  } catch (e) {
    document.getElementById('server-dot').style.background = 'var(--red)';
    setText('server-status', 'Błąd połączenia');
  }
}

// ── Accounts ────────────────────────────────────────────────
async function loadAccounts() {
  try {
    accounts = await api('GET', '/api/accounts');
    renderAccounts(accounts);
    setText('accounts-count', `${accounts.length} kont`);
  } catch (e) {
    document.getElementById('accounts-grid').innerHTML =
      `<div class="empty-state"><div class="empty-icon">⚠️</div><div class="empty-title">Błąd połączenia z serwerem</div><div class="empty-sub">${e.message}</div></div>`;
  }
}

function renderAccounts(data) {
  const grid = document.getElementById('accounts-grid');
  if (!data.length) {
    grid.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">📺</div>
        <div class="empty-title">Brak kont</div>
        <div class="empty-sub">Dodaj pierwsze konto klienta YouTube klikając "Nowy klient"</div>
      </div>`;
    return;
  }

  grid.innerHTML = data.map(acc => buildAccountCard(acc)).join('');
}

function buildAccountCard(acc) {
  const tokenClass = acc.token.status;
  const tokenDot = `<span class="token-dot"></span>`;
  const isRunning = acc.is_running;

  const niche = acc.niche.length > 50 ? acc.niche.slice(0, 50) + '…' : acc.niche;

  const lastVideoHtml = acc.last_video
    ? `<div class="last-video">
        <div class="last-video-label">Ostatnie wideo</div>
        <div class="last-video-title">${escHtml(acc.last_video)}</div>
        <div class="last-video-date">${acc.last_video_date || ''}</div>
       </div>`
    : `<div class="last-video"><div class="last-video-label">Ostatnie wideo</div><div class="last-video-date">Brak historii</div></div>`;

  const runningHtml = isRunning
    ? `<div class="running-indicator">
        <div class="spinner"></div>
        Automat działa — trwa generowanie wideo...
       </div>`
    : '';

  return `
  <div class="account-card ${isRunning ? 'running' : ''} fade-in" id="card-${acc.id}">
    <div class="card-header">
      <div class="card-avatar">${getChannelEmoji(acc.niche)}</div>
      <div class="card-info">
        <div class="card-name">${escHtml(acc.display_name)}</div>
        <div class="card-client">${escHtml(acc.client_name)}</div>
        <div class="card-id">${acc.id}</div>
      </div>
      <div class="token-badge ${tokenClass}">${tokenDot} ${escHtml(acc.token.label)}</div>
    </div>
    <div class="card-body">
      <div class="card-niche">🎯 Nisza: <strong>${escHtml(niche)}</strong></div>
      <div class="card-stats">
        <div class="card-stat">
          <div class="card-stat-label">Wideo</div>
          <div class="card-stat-value">${acc.video_count}</div>
        </div>
        <div class="card-stat">
          <div class="card-stat-label">Status</div>
          <div class="card-stat-value" style="color:${statusColor(acc.token.status)}">${statusLabel(acc.token.status)}</div>
        </div>
        <div class="card-stat">
          <div class="card-stat-label">Dodano</div>
          <div class="card-stat-value" style="font-size:11px">${acc.added || '—'}</div>
        </div>
      </div>
      ${lastVideoHtml}
      ${runningHtml}
      <div class="card-actions">
        <button class="btn btn-primary" onclick="runAccount('${acc.id}')" ${isRunning ? 'disabled' : ''}>
          🚀 ${isRunning ? 'Działa...' : 'Uruchom'}
        </button>
        <button class="btn btn-secondary" onclick="authorizeAccount('${acc.id}')">
          🔐 Autoryzuj
        </button>
        <button class="btn btn-secondary" onclick="showHistory('${acc.id}', '${escHtml(acc.display_name)}')">
          📋 Historia
        </button>
        <button class="btn-icon" title="Usuń konto" onclick="deleteAccount('${acc.id}', '${escHtml(acc.display_name)}')">
          🗑️
        </button>
      </div>
    </div>
  </div>`;
}

// ── Actions ─────────────────────────────────────────────────
async function runAccount(accountId) {
  const acc = accounts.find(a => a.id === accountId);
  if (!acc) return;

  openLogPanel(`🚀 Uruchamiam automat — ${acc.display_name}`);
  appendLog(`▶ Start: one_click_cashcow.py --konto ${accountId} --nisza "${acc.niche}"`, 'info');

  try {
    const res = await api('POST', `/api/run/${accountId}`);
    if (res.error) {
      appendLog(`❌ ${res.error}`, 'error');
      toast(res.error, 'error');
      return;
    }
    startSSEStream(res.stream_key);
    toast(`Automat uruchomiony dla ${acc.display_name}`, 'success');
    setTimeout(loadAccounts, 1500);
  } catch (e) {
    appendLog(`❌ Błąd połączenia: ${e.message}`, 'error');
  }
}

async function authorizeAccount(accountId) {
  const acc = accounts.find(a => a.id === accountId);
  const name = acc ? acc.display_name : accountId;

  openLogPanel(`🔐 Autoryzacja OAuth — ${name}`);
  appendLog(`▶ Uruchamiam authorize_channel.py --konto ${accountId}`, 'info');
  appendLog(`ℹ️  Zostanie otwarta przeglądarka — zaloguj się na właściwe konto Google.`, 'info');

  try {
    const res = await api('POST', `/api/authorize/${accountId}`);
    if (res.error) {
      appendLog(`❌ ${res.error}`, 'error');
      toast(res.error, 'error');
      return;
    }
    startSSEStream(res.stream_key);
    toast(`Autoryzacja uruchomiona dla ${name}`, 'info');
    setTimeout(loadAccounts, 5000);
  } catch (e) {
    appendLog(`❌ Błąd: ${e.message}`, 'error');
  }
}

async function deleteAccount(accountId, displayName) {
  if (!confirm(`Czy na pewno chcesz usunąć konto "${displayName}" z panelu?\n\n(Token OAuth pozostanie na dysku, tylko wpis z panelu zostanie usunięty)`)) return;
  try {
    const res = await api('DELETE', `/api/accounts/${accountId}`);
    if (res.success) {
      toast(`Konto "${displayName}" usunięte z panelu`, 'info');
      loadAccounts();
      loadStats();
    }
  } catch (e) {
    toast('Błąd usuwania', 'error');
  }
}

async function showHistory(accountId, displayName) {
  document.getElementById('history-modal-title').textContent = `📋 Historia wideo — ${displayName}`;
  document.getElementById('history-modal-body').innerHTML =
    `<div class="page-loader"><div class="spinner"></div> Ładowanie...</div>`;
  openHistoryModal();

  try {
    const history = await api('GET', `/api/accounts/${accountId}/history`);
    const body = document.getElementById('history-modal-body');
    if (!history.length) {
      body.innerHTML = `<div class="history-empty">📭 Brak historii wideo dla tego konta.</div>`;
      return;
    }
    body.innerHTML = `<ul class="history-list">${history.map((item, i) => `
      <li class="history-item">
        <div class="history-num">${i + 1}</div>
        <div>
          <div class="history-title">${escHtml(item.title || '—')}</div>
          <div class="history-date">${(item.timestamp || '').slice(0, 16).replace('T', ' ')}</div>
        </div>
      </li>`).join('')}</ul>`;
  } catch (e) {
    document.getElementById('history-modal-body').innerHTML =
      `<div class="history-empty">❌ Błąd ładowania historii.</div>`;
  }
}

async function refreshAll() {
  toast('Odświeżam dane...', 'info');
  await Promise.all([loadStats(), loadAccounts()]);
  toast('Dane odświeżone', 'success');
}

// ── Add Account ─────────────────────────────────────────────
async function submitAddAccount(e) {
  e.preventDefault();
  const btn = e.target.querySelector('[type=submit]');
  btn.disabled = true;
  btn.textContent = 'Dodawanie...';

  const body = {
    id: document.getElementById('input-id').value.trim(),
    display_name: document.getElementById('input-display-name').value.trim(),
    niche: document.getElementById('input-niche').value.trim(),
    client_name: document.getElementById('input-client-name').value.trim(),
    genre: document.getElementById('input-genre').value,
    language: document.getElementById('input-language').value,
    persona: document.getElementById('input-persona').value.trim(),
    tone: document.getElementById('input-tone').value.trim(),
    target_age: document.getElementById('input-target-age').value,
  };

  try {
    const res = await api('POST', '/api/accounts', body);
    if (res.error) {
      toast(res.error, 'error');
    } else {
      toast(`✅ Konto "${body.display_name}" dodane pomyślnie!`, 'success');
      closeAddModal();
      e.target.reset();
      document.getElementById('input-id')._manuallyEdited = false;
      loadAccounts();
      loadStats();
    }
  } catch (err) {
    toast('Błąd serwera', 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Dodaj konto';
  }
}

// ── SSE Log Stream ───────────────────────────────────────────
function startSSEStream(streamKey) {
  if (activeSSE) {
    activeSSE.close();
    activeSSE = null;
  }
  activeStreamKey = streamKey;
  const spinner = document.getElementById('log-spinner');
  spinner.style.display = 'block';

  const evtSource = new EventSource(`/api/stream/${streamKey}`);
  activeSSE = evtSource;

  evtSource.onmessage = e => {
    const data = e.data;
    if (data === '__DONE__') {
      spinner.style.display = 'none';
      const doneEl = document.createElement('div');
      doneEl.className = 'log-done';
      doneEl.textContent = '✅ Operacja zakończona';
      document.getElementById('log-body').appendChild(doneEl);
      scrollLogToBottom();
      evtSource.close();
      activeSSE = null;
      setTimeout(() => { loadAccounts(); loadStats(); }, 1000);
      return;
    }
    if (data.startsWith(':')) return; // heartbeat comment
    appendLog(data);
  };

  evtSource.onerror = () => {
    appendLog('⚠️ Połączenie SSE przerwane', 'warning');
    spinner.style.display = 'none';
    evtSource.close();
    activeSSE = null;
  };
}

// ── Log Panel ────────────────────────────────────────────────
function openLogPanel(title) {
  document.getElementById('log-panel').classList.add('open');
  document.getElementById('log-title-text').textContent = title || 'Log operacji';
}

function closeLogPanel() {
  document.getElementById('log-panel').classList.remove('open');
  if (activeSSE) { activeSSE.close(); activeSSE = null; }
}

function appendLog(text, type = '') {
  const body = document.getElementById('log-body');
  const line = document.createElement('div');
  line.className = `log-line ${classifyLog(text, type)}`;
  line.textContent = text;
  body.appendChild(line);
  scrollLogToBottom();
}

function classifyLog(text, hint) {
  if (hint) return hint;
  if (/✅|SUKCES|sukces|powiedz|OK|Token|gotowy|Zapisano/.test(text)) return 'success';
  if (/❌|BŁĄD|błąd|Error|error|Krytyczny/.test(text)) return 'error';
  if (/⚠️|WARNING|uwaga/.test(text)) return 'warning';
  if (/🚀|🎬|🎯|📊|🔐|ℹ️|Start|Inicjal|Etap|Faza/.test(text)) return 'info';
  return '';
}

function scrollLogToBottom() {
  const body = document.getElementById('log-body');
  body.scrollTop = body.scrollHeight;
}

function clearLog() {
  document.getElementById('log-body').innerHTML = '';
}

// ── Modals ───────────────────────────────────────────────────
function openAddModal() { document.getElementById('add-modal').classList.add('open'); }
function closeAddModal() { document.getElementById('add-modal').classList.remove('open'); }
function openHistoryModal() { document.getElementById('history-modal').classList.add('open'); }
function closeHistoryModal() { document.getElementById('history-modal').classList.remove('open'); }

// ── Toast ─────────────────────────────────────────────────────
function toast(msg, type = 'info') {
  const container = document.getElementById('toast-container');
  const el = document.createElement('div');
  const icons = { success: '✅', error: '❌', info: 'ℹ️', warning: '⚠️' };
  el.className = `toast ${type}`;
  el.innerHTML = `<span>${icons[type] || 'ℹ️'}</span> <span>${escHtml(String(msg))}</span>`;
  container.appendChild(el);
  setTimeout(() => {
    el.style.animation = 'slideOut 0.25s ease forwards';
    setTimeout(() => el.remove(), 260);
  }, 3500);
}

// ── Utils ─────────────────────────────────────────────────────
function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}

function statusColor(status) {
  return { ok: 'var(--green)', expired: 'var(--yellow)', missing: 'var(--red)', error: 'var(--red)' }[status] || 'var(--text-muted)';
}

function statusLabel(status) {
  return { ok: 'Gotowy', expired: 'Wygasły', missing: 'Brak', error: 'Błąd' }[status] || status;
}

function getChannelEmoji(niche) {
  const n = (niche || '').toLowerCase();
  if (n.includes('roblox') || n.includes('brainrot') || n.includes('gaming')) return '🎮';
  if (n.includes('dark') || n.includes('psychology') || n.includes('mindset')) return '🧠';
  if (n.includes('finance') || n.includes('money') || n.includes('crypto')) return '💰';
  if (n.includes('fitness') || n.includes('workout') || n.includes('health')) return '💪';
  if (n.includes('food') || n.includes('cook') || n.includes('recipe')) return '🍕';
  if (n.includes('travel') || n.includes('vlog')) return '✈️';
  if (n.includes('music')) return '🎵';
  return '📺';
}

const ALL_PAGES = ['accounts','pipeline','scanner','profiles','connections','client'];
const PAGE_TITLES = {
  accounts:'📊 Dashboard', pipeline:'⚡ Pipeline', scanner:'📡 Skaner treści',
  profiles:'🎯 Profile kanałów', connections:'🔗 Połącz konta', client:'👤 Konto klienta'
};

function showPage(page) {
  document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
  document.getElementById(`nav-${page}`)?.classList.add('active');
  ALL_PAGES.forEach(p => {
    const el = document.getElementById(`page-${p}`);
    if (el) el.classList.toggle('hidden', p !== page);
  });
  const statsGrid = document.getElementById('stats-grid');
  if (statsGrid) statsGrid.style.display = page === 'accounts' ? '' : 'none';
  setText('topbar-title', PAGE_TITLES[page] || '📊 Dashboard');
  if (page === 'pipeline') loadPipeline();
  if (page === 'profiles') loadProfiles();
  if (page === 'scanner') populateScannerSelect();
  if (page === 'connections') { loadConnections(); loadOAuthAccounts(); }
}

// ── Pipeline ────────────────────────────────────────────────
async function loadPipeline() {
  const grid = document.getElementById('pipeline-grid');
  const sel = document.getElementById('pipeline-account-select');
  try {
    const steps = await api('GET', '/api/pipeline/steps');
    // populate account selector
    sel.innerHTML = '<option value="">— Wszystkie konta —</option>';
    accounts.forEach(a => {
      sel.innerHTML += `<option value="${a.id}">${escHtml(a.display_name)}</option>`;
    });
    grid.innerHTML = steps.map(s => `
      <div class="pipeline-card ${s.is_running?'running':''} ${s.exists?'':'unavailable'} fade-in">
        ${s.is_running ? '<div class="pipeline-running-bar"></div>' : ''}
        <span class="pipeline-icon">${s.icon}</span>
        <div class="pipeline-name">${escHtml(s.name)}</div>
        <div class="pipeline-script">${s.script}</div>
        <div class="pipeline-actions">
          <button class="btn btn-primary" onclick="runPipelineStep('${s.id}')" ${!s.exists||s.is_running?'disabled':''}>
            ${s.is_running ? '⏳ Działa...' : '▶ Uruchom'}
          </button>
          ${s.is_running ? `<button class="btn btn-danger" onclick="stopPipelineStep('${s.id}')">⏹ Stop</button>` : ''}
        </div>
      </div>`).join('');
  } catch(e) {
    grid.innerHTML = `<div class="empty-state"><div class="empty-icon">⚠️</div><div class="empty-title">Błąd ładowania</div></div>`;
  }
}

async function runPipelineStep(stepId) {
  const accId = document.getElementById('pipeline-account-select')?.value || '';
  openLogPanel(`⚡ Pipeline: ${stepId}`);
  try {
    const res = await api('POST', `/api/pipeline/run/${stepId}`, { account_id: accId });
    if (res.error) { appendLog(`❌ ${res.error}`, 'error'); toast(res.error,'error'); return; }
    startSSEStream(res.stream_key);
    toast(`Pipeline ${stepId} uruchomiony`, 'success');
    setTimeout(loadPipeline, 2000);
  } catch(e) { appendLog(`❌ ${e.message}`, 'error'); }
}

async function stopPipelineStep(stepId) {
  try {
    await api('POST', `/api/pipeline/stop/${stepId}`);
    toast('Proces zatrzymany', 'info');
    setTimeout(loadPipeline, 1000);
  } catch(e) { toast('Błąd', 'error'); }
}

// ── Profiles ────────────────────────────────────────────────
async function loadProfiles() {
  const list = document.getElementById('profiles-list');
  try {
    const accs = await api('GET', '/api/accounts');
    if (!accs.length) { list.innerHTML = '<div class="empty-state"><div class="empty-icon">🎯</div><div class="empty-title">Brak profili</div></div>'; return; }
    list.innerHTML = accs.map(acc => {
      const cp = acc.channel_profile || {};
      const uv = cp.universal_values || {};
      const gv = cp.genre_values || {};
      return `
      <div class="profile-card fade-in">
        <div class="profile-card-header" onclick="this.parentElement.querySelector('.profile-card-body').classList.toggle('hidden')">
          <div class="profile-card-title">
            <span>${getChannelEmoji(acc.niche)}</span>
            <div>
              <div>${escHtml(acc.display_name)}</div>
              <div class="profile-card-subtitle">${escHtml(acc.niche)}</div>
            </div>
            <span class="genre-badge">${cp.genre || 'general'}</span>
          </div>
          <span style="color:var(--text-dim)">▼</span>
        </div>
        <div class="profile-card-body hidden">
          <div class="profile-section">
            <div class="profile-section-title">⚙️ Ustawienia kanału</div>
            <div class="profile-fields">
              <div class="profile-field"><div class="profile-field-label">Język</div><div class="profile-field-value">${cp.language||'—'}</div></div>
              <div class="profile-field"><div class="profile-field-label">Głos TTS</div><div class="profile-field-value">${cp.voice||'—'}</div></div>
              <div class="profile-field profile-field-full"><div class="profile-field-label">Persona</div><div class="profile-field-value">${escHtml(cp.persona||'—')}</div></div>
              <div class="profile-field profile-field-full"><div class="profile-field-label">Ton</div><div class="profile-field-value">${escHtml(cp.tone||'—')}</div></div>
            </div>
          </div>
          <div class="profile-section">
            <div class="profile-section-title">✅ Wartości uniwersalne</div>
            <div class="universal-values-grid">
              ${Object.entries(uv).map(([k,v]) => `<div class="uv-item"><span class="uv-key">${k}</span><span class="uv-val ${v===false?'warn':''}">${v}</span></div>`).join('')}
            </div>
          </div>
          <div class="profile-section">
            <div class="profile-section-title">🎯 Wartości gatunkowe (${cp.genre||'general'})</div>
            <div class="profile-fields">
              ${Object.entries(gv).map(([k,v]) => `<div class="profile-field"><div class="profile-field-label">${k}</div><div class="profile-field-value">${Array.isArray(v)?v.join(', '):escHtml(String(v))}</div></div>`).join('')}
            </div>
          </div>
          <div class="profile-section">
            <div class="profile-section-title">🔖 SEO Tags</div>
            <div class="profile-tags">${(cp.seo_tags||[]).map(t=>`<span class="profile-tag">${escHtml(t)}</span>`).join('')}</div>
          </div>
          <div style="margin-top:16px;text-align:right">
            <button class="btn btn-primary" onclick="openProfileEdit('${acc.id}')">✏️ Edytuj profil</button>
          </div>
        </div>
      </div>`;
    }).join('');
  } catch(e) { list.innerHTML = `<div class="empty-state"><div class="empty-icon">⚠️</div><div class="empty-title">Błąd: ${e.message}</div></div>`; }
}

function openProfileEdit(accId) {
  const acc = accounts.find(a => a.id === accId);
  if (!acc) return;
  const cp = acc.channel_profile || {};
  const body = document.getElementById('profile-modal-body');
  document.getElementById('profile-modal-title').textContent = `🎯 Edytuj: ${acc.display_name}`;
  body.innerHTML = `
    <form onsubmit="saveProfile(event,'${accId}')">
      <div class="form-group"><label class="form-label">Persona</label><input class="form-input" id="pe-persona" value="${escHtml(cp.persona||'')}"/></div>
      <div class="form-group"><label class="form-label">Ton</label><input class="form-input" id="pe-tone" value="${escHtml(cp.tone||'')}"/></div>
      <div class="form-group"><label class="form-label">Hook style</label><input class="form-input" id="pe-hook" value="${escHtml(cp.hook_style||'')}"/></div>
      <div class="form-group"><label class="form-label">Music style</label><input class="form-input" id="pe-music" value="${escHtml(cp.music_style||'')}"/></div>
      <div class="form-group"><label class="form-label">Background style</label><input class="form-input" id="pe-bg" value="${escHtml(cp.background_style||'')}"/></div>
      <div class="form-actions"><button type="button" class="btn btn-secondary" onclick="closeProfileModal()">Anuluj</button><button type="submit" class="btn btn-primary">💾 Zapisz</button></div>
    </form>`;
  document.getElementById('profile-modal').classList.add('open');
}

function closeProfileModal() { document.getElementById('profile-modal').classList.remove('open'); }

async function saveProfile(e, accId) {
  e.preventDefault();
  const data = { channel_profile: {
    persona: document.getElementById('pe-persona').value,
    tone: document.getElementById('pe-tone').value,
    hook_style: document.getElementById('pe-hook').value,
    music_style: document.getElementById('pe-music').value,
    background_style: document.getElementById('pe-bg').value,
  }};
  try {
    const res = await api('PUT', `/api/accounts/${accId}/profile`, data);
    if (res.success) { toast('Profil zapisany','success'); closeProfileModal(); loadProfiles(); loadAccounts(); }
    else toast(res.error||'Błąd','error');
  } catch(e) { toast('Błąd serwera','error'); }
}

// ── Scanner ─────────────────────────────────────────────────
function populateScannerSelect() {
  const sel = document.getElementById('scanner-account-select');
  sel.innerHTML = '<option value="">— wybierz —</option>';
  accounts.forEach(a => { sel.innerHTML += `<option value="${a.id}">${escHtml(a.display_name)}</option>`; });
}

async function runContentScan() {
  const accId = document.getElementById('scanner-account-select').value;
  if (!accId) { toast('Wybierz konto','warning'); return; }
  const logEl = document.getElementById('scan-live-log');
  const logBody = document.getElementById('scan-log-body');
  const spinner = document.getElementById('scan-spinner');
  logEl.classList.remove('hidden');
  logBody.innerHTML = '';
  spinner.style.display = 'block';
  try {
    const res = await api('POST', `/api/scan/${accId}`);
    if (res.error) { toast(res.error,'error'); return; }
    const evtSource = new EventSource(`/api/stream/${res.stream_key}`);
    evtSource.onmessage = e => {
      if (e.data === '__DONE__') { spinner.style.display='none'; evtSource.close(); loadTrends(accId); return; }
      const line = document.createElement('div');
      line.className = `log-line ${classifyLog(e.data,'')}`;
      line.textContent = e.data;
      logBody.appendChild(line);
      logBody.scrollTop = logBody.scrollHeight;
    };
    evtSource.onerror = () => { spinner.style.display='none'; evtSource.close(); };
  } catch(e) { toast('Błąd','error'); }
}

async function loadTrends(accId) {
  try {
    const data = await api('GET', `/api/trends/${accId}`);
    if (data.error) return;
    const results = document.getElementById('trend-results');
    const meta = document.getElementById('trend-meta');
    const body = document.getElementById('trend-body');
    results.classList.remove('hidden');
    meta.textContent = `Raport: ${data.fetched_at || data.generated_at || '—'}`;
    const p = data.patterns || data;
    body.innerHTML = `
      <div class="trend-grid">
        <div class="trend-block"><div class="trend-block-label">Hot Topics</div>${(p.hot_topics_today||[]).map(t=>`<span class="trend-tag">${escHtml(t)}</span>`).join('')}</div>
        <div class="trend-block"><div class="trend-block-label">Top Keywords</div>${(p.top_keywords_today||[]).slice(0,8).map(t=>`<span class="trend-tag">${escHtml(t)}</span>`).join('')}</div>
        <div class="trend-block"><div class="trend-block-label">Format</div><span class="trend-format-badge">${p.dominant_format||'—'}</span></div>
      </div>`;
  } catch(e) { /* no trends yet */ }
}

// ── OAuth Account Cards ───────────────────────────────────────
async function loadOAuthAccounts() {
  const list = document.getElementById('oauth-accounts-list');
  if (!list) return;
  if (!accounts.length) {
    list.innerHTML = `<div class="empty-state"><div class="empty-icon">📋</div><div class="empty-title">Brak kont — dodaj konto przez "+ Nowy klient"</div></div>`;
    return;
  }
  // Render skeletons first
  list.innerHTML = accounts.map(a => `
    <div class="oauth-card fade-in" id="oauth-card-${a.id}">
      <div class="oauth-card-left">
        <span class="oauth-platform-icon">🎬</span>
        <div>
          <div class="oauth-name">${escHtml(a.display_name)}</div>
          <div class="oauth-id">@${a.id} · ${a.niche ? escHtml(a.niche.slice(0,40)) : ''}</div>
        </div>
      </div>
      <div class="oauth-card-right">
        <span class="oauth-status-badge loading" id="token-badge-${a.id}">⏳ sprawdzam...</span>
        <button class="btn btn-secondary btn-sm" onclick="authorizeAccount('${a.id}')">🔐 Autoryzuj YT</button>
        <button class="btn btn-info btn-sm" onclick="runAnalyzer('${a.id}')">🔬 Analizuj kanał</button>
      </div>
    </div>`).join('');

  // Fetch token status for each account in parallel
  await Promise.all(accounts.map(async a => {
    try {
      const ts = await api('GET', `/api/accounts/${a.id}/token_status`);
      const badge = document.getElementById(`token-badge-${a.id}`);
      if (badge) {
        badge.textContent = ts.label;
        badge.className = `oauth-status-badge ${ts.color}`;
      }
    } catch(e) { /* ignore */ }
  }));
}

async function authorizeAccount(accId) {
  openLogPanel(`🔐 Autoryzacja OAuth: ${accId}`);
  appendLog(`▶ Uruchamiam authorize_channel.py --konto ${accId}`, 'info');
  appendLog(`⚠️ Otworzy się przeglądarka — zaloguj na właściwe konto Google YT!`, 'warning');
  try {
    const res = await api('POST', `/api/authorize/${accId}`);
    if (res.error) { appendLog(`❌ ${res.error}`, 'error'); return; }
    startSSEStream(res.stream_key);
    // Refresh token status after 30s
    setTimeout(() => loadOAuthAccounts(), 30000);
  } catch(e) { appendLog(`❌ ${e.message}`, 'error'); }
}

async function runAnalyzer(accId) {
  const acc = accounts.find(a => a.id === accId);
  const name = acc ? acc.display_name : accId;
  openLogPanel(`🔬 Analiza kanału: ${name}`);
  appendLog(`▶ Uruchamiam smart_video_analyzer.py dla konta "${accId}"`, 'info');
  appendLog(`📊 Pobieranie danych z YT Analytics API — może potrwać 1-2 min...`, 'info');
  try {
    const res = await api('POST', `/api/analyze/${accId}`);
    if (res.error) { appendLog(`❌ ${res.error}`, 'error'); return; }
    startSSEStream(res.stream_key);
    toast(`🔬 Analiza kanału "${name}" uruchomiona`, 'success');
  } catch(e) { appendLog(`❌ ${e.message}`, 'error'); }
}

// ── Connections (Platform References) ───────────────────────
async function loadConnections() {
  const container = document.getElementById('connections-list');
  // populate conn-account select
  const sel = document.getElementById('conn-account');
  if (sel) {
    sel.innerHTML = '<option value="">— globalne —</option>';
    accounts.forEach(a => { sel.innerHTML += `<option value="${a.id}">${escHtml(a.display_name)}</option>`; });
  }
  if (!container) return;
  try {
    const refs = await api('GET', '/api/connections');
    if (!refs.length) {
      container.innerHTML = `<div class="empty-state"><div class="empty-icon">🔗</div><div class="empty-title">Brak referencji</div><div class="empty-sub">Dodaj linki do najlepszych filmów z YT, TikTok, IG lub FB</div></div>`;
      return;
    }
    container.innerHTML = refs.map((r,i) => `
      <div class="connection-item fade-in">
        <span class="connection-platform">${platformIcon(r.platform)}</span>
        <div class="connection-info">
          <div class="connection-url">${escHtml(r.url)}</div>
          <div class="connection-meta">${r.platform} · ${r.account_id||'global'} · ${r.added||''}</div>
        </div>
        <button class="btn-icon" onclick="deleteConnection(${i})" title="Usuń">🗑️</button>
      </div>`).join('');
  } catch(e) { container.innerHTML = '<div class="empty-state"><div class="empty-icon">⚠️</div><div class="empty-title">Błąd</div></div>'; }
}

function platformIcon(p) {
  return {youtube:'🎬',tiktok:'🎵',instagram:'📸',facebook:'📘'}[p] || '🔗';
}

async function addConnection() {
  const url = document.getElementById('conn-url').value.trim();
  const platform = document.getElementById('conn-platform').value;
  const accId = document.getElementById('conn-account').value;
  if (!url) { toast('Wklej link','warning'); return; }
  try {
    const res = await api('POST', '/api/connections', { url, platform, account_id: accId });
    if (res.success) { toast('Referencja dodana','success'); document.getElementById('conn-url').value=''; loadConnections(); }
    else toast(res.error||'Błąd','error');
  } catch(e) { toast('Błąd','error'); }
}

async function deleteConnection(index) {
  try {
    await api('DELETE', `/api/connections/${index}`);
    toast('Usunięto','info');
    loadConnections();
  } catch(e) { toast('Błąd','error'); }
}

// populate conn-account select when connections page opens
const _origLoadConnections = loadConnections;
async function loadConnections() {
  const sel = document.getElementById('conn-account');
  if (sel) {
    sel.innerHTML = '<option value="">— globalne —</option>';
    accounts.forEach(a => { sel.innerHTML += `<option value="${a.id}">${escHtml(a.display_name)}</option>`; });
  }
  await _origLoadConnections();
}

// ── Client Account Modal ─────────────────────────────────────
function openClientAddModal() {
  document.getElementById('client-add-modal').classList.add('open');
}
function closeClientAddModal() {
  document.getElementById('client-add-modal').classList.remove('open');
}

async function submitClientAccount(e) {
  e.preventDefault();
  const btn = e.target.querySelector('[type=submit]');
  btn.disabled = true; btn.textContent = 'Tworzenie...';
  const id = document.getElementById('ci-id').value.trim()
    .toLowerCase().replace(/[^a-z0-9]+/g, '_');
  const body = {
    id,
    display_name: document.getElementById('ci-display-name').value.trim(),
    niche: document.getElementById('ci-niche').value.trim(),
    client_name: document.getElementById('ci-client-name').value.trim(),
    genre: 'product_review',
    language: document.getElementById('ci-language').value,
    persona: document.getElementById('ci-persona').value.trim() ||
      'Honest product reviewer who saves people money',
    tone: document.getElementById('ci-tone').value.trim() ||
      'Friendly, honest, direct. Never pushy or salesy.',
    target_age: '25-35',
  };
  try {
    const res = await api('POST', '/api/accounts', body);
    if (res.error) { toast(res.error, 'error'); }
    else {
      toast(`✅ Konto klientki "${body.display_name}" dodane!`, 'success');
      closeClientAddModal();
      e.target.reset();
      loadAccounts(); loadStats();
      showPage('accounts');
    }
  } catch(err) { toast('Błąd serwera', 'error'); }
  finally { btn.disabled = false; btn.textContent = '✅ Utwórz konto'; }
}
