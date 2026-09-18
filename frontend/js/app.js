/* ==========================================================
   AI Job Application Agent — app.js
   Comprehensive vanilla JS for all frontend features.
   All API calls use fetch(). Modular, commented, no Bootstrap.
   ========================================================== */

'use strict';

/* ─────────────────────────────────────────────────────────
   STATE
   ───────────────────────────────────────────────────────── */
const State = {
  currentTab:      'dashboard',
  currentJobId:    null,
  currentJob:      null,
  currentResumeId: null,
  allJobs:         [],
  allResumes:      [],
  automationPoll:  null,   // setInterval handle
  followupJobId:   null,   // which job we're sending a follow-up for
  profileData:     {},     // cached candidate profile
  tagsData: {
    technical: [],
    soft:      [],
    languages: [],
  },
};

/* ─────────────────────────────────────────────────────────
   API HELPERS
   ───────────────────────────────────────────────────────── */
const API = {
  base: '',   // same origin

  async get(path) {
    const r = await fetch(this.base + path);
    if (!r.ok) { const t = await r.text(); throw new Error(t || r.statusText); }
    return r.json();
  },

  async post(path, body) {
    const r = await fetch(this.base + path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!r.ok) { const t = await r.text(); throw new Error(t || r.statusText); }
    return r.json();
  },

  async put(path, body) {
    const r = await fetch(this.base + path, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!r.ok) { const t = await r.text(); throw new Error(t || r.statusText); }
    return r.json();
  },

  async del(path) {
    const r = await fetch(this.base + path, { method: 'DELETE' });
    if (!r.ok) { const t = await r.text(); throw new Error(t || r.statusText); }
    return r.json().catch(() => ({}));
  },

  async postForm(path, formData) {
    const r = await fetch(this.base + path, { method: 'POST', body: formData });
    if (!r.ok) { const t = await r.text(); throw new Error(t || r.statusText); }
    return r.json();
  },

  async postRaw(path, body) {
    const r = await fetch(this.base + path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!r.ok) { const t = await r.text(); throw new Error(t || r.statusText); }
    return r.json();
  },
};

/* ─────────────────────────────────────────────────────────
   TOAST NOTIFICATIONS
   ───────────────────────────────────────────────────────── */
const Toast = {
  show(msg, type = 'info', duration = 4000) {
    const container = document.getElementById('toast-container');
    const el = document.createElement('div');
    el.className = `toast toast-${type}`;
    const icon = { success: '✓', error: '✕', warning: '⚠', info: 'ℹ' }[type] || 'ℹ';
    el.innerHTML = `<span>${icon}</span><span>${msg}</span>`;
    container.appendChild(el);
    setTimeout(() => {
      el.classList.add('hiding');
      setTimeout(() => el.remove(), 300);
    }, duration);
  },
  success: (m, d) => Toast.show(m, 'success', d),
  error:   (m, d) => Toast.show(m, 'error',   d),
  warning: (m, d) => Toast.show(m, 'warning', d),
  info:    (m, d) => Toast.show(m, 'info',    d),
};

/* ─────────────────────────────────────────────────────────
   HELPER UTILITIES
   ───────────────────────────────────────────────────────── */
const $ = (id) => document.getElementById(id);
const $$ = (sel, ctx = document) => ctx.querySelector(sel);

function setText(id, val)  { const el = $(id); if (el) el.textContent = val ?? '—'; }
function setHtml(id, val)  { const el = $(id); if (el) el.innerHTML  = val ?? ''; }
function show(id)          { const el = $(id); if (el) el.classList.remove('d-none'); }
function hide(id)          { const el = $(id); if (el) el.classList.add('d-none'); }
function toggle(id, cond)  { cond ? show(id) : hide(id); }

function setMsg(id, msg, type = '') {
  const el = $(id);
  if (!el) return;
  el.textContent = msg;
  el.style.color = { success: 'var(--green)', error: 'var(--red)', warning: 'var(--yellow)', '': 'var(--text-muted)' }[type] || 'var(--text-muted)';
}

function fmtDate(d) {
  if (!d) return '—';
  try { return new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }); } catch { return d; }
}

function esc(str) {
  return String(str ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

/* ─────────────────────────────────────────────────────────
   TAB ROUTING
   ───────────────────────────────────────────────────────── */
const TAB_LOADERS = {
  dashboard: () => App.loadDashboard(),
  profile:   () => App.loadProfile(),
  jobs:      () => App.loadJobs(),
  resumes:   () => App.loadResumes(),
  settings:  () => App.loadSettings(),
};

function switchTab(tabId) {
  // Hide all panes
  document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
  // Deactivate all nav buttons
  document.querySelectorAll('.sidebar-nav button').forEach(b => b.classList.remove('active'));
  // Activate target
  const pane = $(`tab-${tabId}`);
  if (pane) pane.classList.add('active');
  const btn = document.querySelector(`.sidebar-nav button[data-tab="${tabId}"]`);
  if (btn) btn.classList.add('active');

  State.currentTab = tabId;
  if (TAB_LOADERS[tabId]) TAB_LOADERS[tabId]();
}

/* ─────────────────────────────────────────────────────────
   STATUS BADGES & JOB CARD HELPERS
   ───────────────────────────────────────────────────────── */
const STATUS_MAP = {
  new:           { cls: 'badge-new',      dot: 'new',      label: 'NEW' },
  saved:         { cls: 'badge-new',      dot: 'new',      label: 'SAVED' },
  analyzed:      { cls: 'badge-analyzed', dot: 'analyzed', label: 'ANALYZED' },
  resume_ready:  { cls: 'badge-ready',    dot: 'ready',    label: 'RESUME READY' },
  email_sent:    { cls: 'badge-sent',     dot: 'sent',     label: 'EMAIL SENT' },
  applied:       { cls: 'badge-applied',  dot: 'applied',  label: 'APPLIED' },
  rejected:      { cls: 'badge-failed',   dot: 'failed',   label: 'REJECTED' },
  interview:     { cls: 'badge-ready',    dot: 'ready',    label: 'INTERVIEW' },
  offer:         { cls: 'badge-applied',  dot: 'applied',  label: 'OFFER' },
  not_responded: { cls: 'badge-failed',   dot: 'failed',   label: 'NO RESPONSE' },
};

function statusBadgeHTML(status) {
  const s = STATUS_MAP[status] || STATUS_MAP.new;
  return `<span class="badge ${s.cls}"><span class="badge-dot ${s.dot}"></span>${s.label}</span>`;
}

function matchBadgeHTML(score) {
  if (!score && score !== 0) return '';
  const pct = Math.round(score);
  return `<span class="badge badge-match">${pct}% match</span>`;
}

function buildJobCard(job) {
  const status   = job.status || 'new';
  const match    = job.match_score;
  const hasEmail = job.hr_email;
  const contacts = (job.contacts_count || 0);
  const resumeReady = job.resume_generated;
  const atsScore = job.ats_score;

  return `
  <div class="job-card glow" id="job-card-${job.id}" onclick="App.openJobDetail('${job.id}')">
    <div class="job-card-top">
      <div style="display:flex;gap:6px;flex-wrap:wrap">
        ${statusBadgeHTML(status)}
      </div>
      ${match != null ? matchBadgeHTML(match) : ''}
    </div>
    <div class="job-card-title">${esc(job.title || job.role_name || '(No Title)')}</div>
    <div class="job-card-meta">
      <span>${esc(job.company || '—')} · ${esc(job.location || '—')}</span>
      ${job.experience_required ? `<span>${esc(job.experience_required)} · ${esc(job.job_type || 'Full-time')}</span>` : ''}
    </div>
    <div class="job-card-info">
      <div class="job-card-info-row">
        <span class="badge-dot ${resumeReady ? 'ready' : 'new'}" style="width:7px;height:7px;border-radius:50%;background:${resumeReady ? 'var(--green)' : 'var(--text-muted)'}"></span>
        <span>Resume: ${resumeReady ? `Ready${atsScore ? ` (ATS: ${Math.round(atsScore)}%)` : ''}` : 'Not generated'}</span>
      </div>
      <div class="job-card-info-row">
        <span class="badge-dot ${hasEmail || contacts ? 'ready' : 'new'}" style="width:7px;height:7px;border-radius:50%;background:${hasEmail || contacts ? 'var(--green)' : 'var(--text-muted)'}"></span>
        <span>HR Email: ${contacts ? `${contacts} contact${contacts > 1 ? 's' : ''} found` : (hasEmail ? 'On file' : 'Not found')}</span>
      </div>
    </div>
    <div class="job-card-actions" onclick="event.stopPropagation()">
      <button class="btn btn-secondary btn-xs" onclick="App.triggerAnalyzeJD('${job.id}')">Analyze JD</button>
      <button class="btn btn-secondary btn-xs" onclick="App.triggerFindContacts('${job.id}')">Find HR</button>
      <button class="btn btn-primary btn-xs" onclick="App.triggerGenerateResume('${job.id}')">Gen Resume</button>
      ${resumeReady ? `<button class="btn btn-secondary btn-xs" onclick="App.triggerPreviewPDF('${job.id}')">Preview PDF</button>` : ''}
      <button class="btn btn-secondary btn-xs" onclick="App.triggerEmailHR('${job.id}')">Email HR</button>
      <button class="btn btn-secondary btn-xs" onclick="App.triggerApplyWeb('${job.id}')">Apply Web</button>
    </div>
  </div>`;
}

/* ─────────────────────────────────────────────────────────
   SKILL TAGS INPUT
   ───────────────────────────────────────────────────────── */
function initTagsInput(wrapperId, inputId, dataKey) {
  const wrapper = $(wrapperId);
  const input   = $(inputId);
  if (!wrapper || !input) return;

  // Render tags
  function renderTags() {
    // Remove all tag-items
    wrapper.querySelectorAll('.tag-item').forEach(t => t.remove());
    State.tagsData[dataKey].forEach((tag, i) => {
      const el = document.createElement('span');
      el.className = 'tag-item';
      el.innerHTML = `${esc(tag)}<button type="button" onclick="App.removeTag('${dataKey}',${i})" title="Remove">×</button>`;
      wrapper.insertBefore(el, input);
    });
  }

  function addTag(val) {
    const v = val.trim();
    if (!v || State.tagsData[dataKey].includes(v)) return;
    State.tagsData[dataKey].push(v);
    renderTags();
  }

  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault();
      addTag(input.value);
      input.value = '';
    } else if (e.key === 'Backspace' && !input.value) {
      State.tagsData[dataKey].pop();
      renderTags();
    }
  });

  wrapper.addEventListener('click', () => input.focus());
  renderTags();
}

/* ─────────────────────────────────────────────────────────
   ACCORDION HELPERS (Experience, Education, Projects, Certs)
   ───────────────────────────────────────────────────────── */
function buildAccordion(containerId, items, fieldsDef, removeCallback) {
  const container = $(containerId);
  if (!container) return;
  container.innerHTML = '';
  items.forEach((item, idx) => {
    const div = document.createElement('div');
    div.className = 'accordion-item open';
    div.id = `acc-${containerId}-${idx}`;
    const title = item.title || item.role || item.institution || item.name || `Entry ${idx + 1}`;
    div.innerHTML = `
      <div class="accordion-header" onclick="this.parentElement.classList.toggle('open')">
        <span class="accordion-title">${esc(title)}</span>
        <div style="display:flex;gap:6px;align-items:center">
          <button class="btn btn-danger btn-xs" onclick="event.stopPropagation();${removeCallback}(${idx})" type="button">Remove</button>
          <span class="accordion-toggle">▾</span>
        </div>
      </div>
      <div class="accordion-body">
        ${fieldsDef.map(f => `
          <div class="form-group">
            <label class="form-label">${esc(f.label)}</label>
            ${f.type === 'textarea'
              ? `<textarea class="form-control" data-acc="${containerId}" data-idx="${idx}" data-field="${f.key}" rows="3">${esc(item[f.key] || '')}</textarea>`
              : `<input type="${f.type || 'text'}" class="form-control" data-acc="${containerId}" data-idx="${idx}" data-field="${f.key}" value="${esc(item[f.key] || '')}">`
            }
          </div>`).join('')}
      </div>`;
    container.appendChild(div);
  });

  // Bind change events
  container.querySelectorAll('[data-acc]').forEach(el => {
    el.addEventListener('input', () => {
      const i   = parseInt(el.dataset.idx);
      const key = el.dataset.field;
      items[i][key] = el.value;
    });
  });
}

/* ─────────────────────────────────────────────────────────
   PDF MODAL
   ───────────────────────────────────────────────────────── */
function openPDFModal(src, title) {
  $('pdf-modal-iframe').src = src;
  setText('pdf-modal-title', title || 'Resume Preview');
  $('pdf-modal').classList.remove('d-none');
}

function closePDFModal() {
  $('pdf-modal').classList.add('d-none');
  $('pdf-modal-iframe').src = 'about:blank';
}

/* ─────────────────────────────────────────────────────────
   JOB DETAIL PANEL
   ───────────────────────────────────────────────────────── */
function openPanel() {
  $('job-detail-panel').classList.add('open');
  $('panel-overlay').classList.add('open');
  document.body.style.overflow = 'hidden';
}

function closePanel() {
  $('job-detail-panel').classList.remove('open');
  $('panel-overlay').classList.remove('open');
  document.body.style.overflow = '';
  stopAutomationPoll();
  State.currentJobId = null;
  State.currentJob   = null;
}

/* ─────────────────────────────────────────────────────────
   STEPPER UPDATE
   ───────────────────────────────────────────────────────── */
function updateStepper(job) {
  const hasAnalysis  = !!(job.analysis || job.match_score != null);
  const hasContacts  = !!(job.hr_email || job.contacts_count);
  const hasResume    = !!job.resume_generated;
  const applied      = ['applied', 'email_sent'].includes(job.status);

  function setStep(n, done, active) {
    const btn = $(`step-btn-${n}`);
    const item = $(`step-item-${n}`);
    if (!btn) return;
    btn.classList.toggle('completed', done);
    btn.classList.toggle('active', active && !done);
    if (item) item.classList.toggle('step-done', done);
  }

  setStep(1, hasAnalysis,                    !hasAnalysis);
  setStep(2, hasContacts,                    hasAnalysis && !hasContacts);
  setStep(3, hasResume,                      hasContacts && !hasResume);
  setStep(4, hasResume,                      hasResume);
  setStep(5, applied,                        hasResume && !applied);
}

/* ─────────────────────────────────────────────────────────
   AUTOMATION POLLING
   ───────────────────────────────────────────────────────── */
function startAutomationPoll(jobId) {
  stopAutomationPoll();
  State.automationPoll = setInterval(() => App.pollAutomationStatus(jobId), 2000);
}

function stopAutomationPoll() {
  if (State.automationPoll) { clearInterval(State.automationPoll); State.automationPoll = null; }
}

/* ─────────────────────────────────────────────────────────
   MAIN APP OBJECT
   ───────────────────────────────────────────────────────── */
const App = {

  /* ── INIT ──────────────────────────────────────────────── */
  init() {
    // Sidebar navigation
    document.querySelectorAll('.sidebar-nav button[data-tab]').forEach(btn => {
      btn.addEventListener('click', () => switchTab(btn.dataset.tab));
    });

    // Panel close
    $('jdp-close-btn').addEventListener('click', closePanel);
    $('panel-overlay').addEventListener('click', closePanel);

    // PDF modal close
    $('pdf-modal-close').addEventListener('click', closePDFModal);
    $('pdf-modal').addEventListener('click', (e) => { if (e.target === $('pdf-modal')) closePDFModal(); });

    // Profile section tabs
    document.querySelectorAll('#profile-section-tabs .section-tab').forEach(tab => {
      tab.addEventListener('click', () => {
        document.querySelectorAll('#profile-section-tabs .section-tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.section-panel').forEach(p => p.classList.remove('active'));
        tab.classList.add('active');
        $(`section-${tab.dataset.section}`)?.classList.add('active');
      });
    });

    // Gemini model auto-save on change
    $('gemini-model-select').addEventListener('change', () => App.saveGeminiModel());

    // Language preference auto-save
    $('pref-language').addEventListener('change', () => App.saveLanguagePref());

    // Job search filter
    $('job-search-filter')?.addEventListener('input', () => App.renderJobs());
    $('min-match-filter')?.addEventListener('input',  () => App.renderJobs());

    // JD status select
    $('jdp-status-select').addEventListener('change', (e) => {
      if (State.currentJobId) App.updateJobStatus(State.currentJobId, e.target.value);
    });

    // Tags inputs
    initTagsInput('tags-technical', 'tags-technical-input', 'technical');
    initTagsInput('tags-soft',      'tags-soft-input',      'soft');
    initTagsInput('tags-languages', 'tags-languages-input', 'languages');

    // Upload zone drag-over
    const zone = $('resume-upload-zone');
    if (zone) {
      zone.addEventListener('dragover',  (e) => { e.preventDefault(); zone.classList.add('drag-over'); });
      zone.addEventListener('dragleave', ()  => zone.classList.remove('drag-over'));
      zone.addEventListener('drop',      (e) => { e.preventDefault(); zone.classList.remove('drag-over'); App.uploadResume(e.dataTransfer.files[0]); });
    }

    // Boot: load sidebar info + switch to dashboard
    App.loadVersion();
    App.checkAI();
    switchTab('dashboard');
  },

  switchTab,

  /* ── VERSION & AI STATUS ───────────────────────────────── */
  async loadVersion() {
    try {
      const d = await API.get('/api/version');
      setText('version-badge', `v${d.version || '?'}`);
      $('version-dot').classList.add('online');
    } catch {
      setText('version-badge', 'offline');
      $('version-dot').classList.add('offline');
    }
  },

  async checkAI() {
    try {
      const d = await API.get('/api/ai/health');
      const ok = d.status === 'ok' || d.healthy === true;
      setText('ai-status-badge', d.provider ? `${d.provider}: ${ok ? 'online' : 'error'}` : (ok ? 'AI online' : 'AI error'));
      $('ai-status-dot').className = 'status-dot ' + (ok ? 'online' : 'offline');
    } catch {
      setText('ai-status-badge', 'AI offline');
      $('ai-status-dot').className = 'status-dot offline';
    }
  },

  /* ═══════════════════════════════════════════════════════
     DASHBOARD
     ═════════════════════════════════════════════════════ */
  async loadDashboard() {
    try {
      const stats = await API.get('/api/applications/stats');
      setText('stat-applied',     stats.applied      ?? stats.total_applied    ?? 0);
      setText('stat-email-sent',  stats.email_sent   ?? stats.emails_sent      ?? 0);
      setText('stat-resume-ready',stats.resume_ready ?? stats.resumes_generated?? 0);
      setText('stat-failed',      stats.failed       ?? stats.rejected         ?? 0);
      setText('stat-pending',     stats.pending      ?? stats.pending_applications ?? 0);
    } catch(e) {
      console.warn('Stats error:', e.message);
    }

    try {
      const apps = await API.get('/api/applications');
      const list = Array.isArray(apps) ? apps : (apps.applications || []);
      const tbody = $('dashboard-apps-tbody');
      const table = $('dashboard-apps-table');
      const empty = $('dashboard-apps-empty');

      if (!list.length) {
        hide('dashboard-apps-table');
        show('dashboard-apps-empty');
        return;
      }
      show('dashboard-apps-table');
      hide('dashboard-apps-empty');
      table.style.display = '';

      tbody.innerHTML = list.slice(0, 20).map(a => `
        <tr>
          <td>${esc(a.company || a.company_name || '—')}</td>
          <td>${esc(a.role || a.title || a.job_title || '—')}</td>
          <td>${esc(a.method || a.application_method || '—')}</td>
          <td>${statusBadgeHTML(a.status || 'new')}</td>
          <td>${fmtDate(a.applied_at || a.created_at)}</td>
        </tr>`).join('');
    } catch(e) {
      console.warn('Applications error:', e.message);
    }
  },

  async runFollowupsAll() {
    setMsg('dashboard-action-msg', 'Running follow-ups...', '');
    try {
      const d = await API.post('/api/notifications/followups/run-all', {});
      setMsg('dashboard-action-msg', d.message || 'Follow-ups sent!', 'success');
      Toast.success(d.message || 'Follow-ups sent!');
    } catch(e) {
      setMsg('dashboard-action-msg', e.message, 'error');
      Toast.error('Follow-ups failed: ' + e.message);
    }
  },

  /* ═══════════════════════════════════════════════════════
     CANDIDATE PROFILE
     ═════════════════════════════════════════════════════ */
  async loadProfile() {
    try {
      const data = await API.get('/api/candidate');
      State.profileData = data;
      App._fillProfile(data);
      App._loadProfileResumesDropdown();
    } catch(e) {
      Toast.error('Failed to load profile: ' + e.message);
    }
  },

  _fillProfile(data) {
    const s = (id, val) => { const el = $(id); if (el) el.value = val || ''; };
    s('p-name',            data.name            || data.full_name || '');
    s('p-email',           data.email           || '');
    s('p-phone',           data.phone           || '');
    s('p-location',        data.location        || '');
    s('p-linkedin',        data.linkedin        || data.linkedin_url || '');
    s('p-github',          data.github          || data.github_url  || data.portfolio_url || '');
    s('p-summary',         data.summary         || data.professional_summary || '');
    s('p-target-role',     data.target_role     || data.current_role || '');
    s('p-years-exp',       data.years_experience|| data.years_of_experience || '');
    s('p-current-company', data.current_company || '');
    s('p-current-salary',  data.current_salary  || '');
    s('p-expected-salary', data.expected_salary || '');
    s('p-notice-period',   data.notice_period   || '');
    s('p-work-auth',       data.work_authorization || data.work_auth || '');
    s('p-work-mode',       data.preferred_work_mode || data.work_mode || '');

    // Skills tags
    State.tagsData.technical = data.technical_skills || data.skills || [];
    State.tagsData.soft      = data.soft_skills      || [];
    State.tagsData.languages = data.languages        || [];
    ['technical','soft','languages'].forEach(k => initTagsInput(`tags-${k}`, `tags-${k}-input`, k));

    // Accordion sections
    App._renderAccordion('education-list',    data.education     || [], 'education');
    App._renderAccordion('experience-list',   data.experience    || [], 'experience');
    App._renderAccordion('projects-list',     data.projects      || [], 'projects');
    App._renderAccordion('certs-list',        data.certifications|| [], 'certifications');

    // Template select
    const templateId = data.original_resume_id || data.template_resume_id || '';
    if (templateId) {
      const sel = $('profile-template-select');
      if (sel) sel.value = templateId;
    }
  },

  _renderAccordion(containerId, items, type) {
    const eduFields = [
      { key: 'institution', label: 'Institution' },
      { key: 'degree',      label: 'Degree / Qualification' },
      { key: 'field',       label: 'Field of Study' },
      { key: 'start_year',  label: 'Start Year', type: 'number' },
      { key: 'end_year',    label: 'End Year',   type: 'number' },
      { key: 'gpa',         label: 'GPA / Score (optional)' },
    ];
    const expFields = [
      { key: 'company',     label: 'Company' },
      { key: 'role',        label: 'Role / Title' },
      { key: 'location',    label: 'Location' },
      { key: 'start_date',  label: 'Start Date (e.g. Jan 2022)' },
      { key: 'end_date',    label: 'End Date (or "Present")' },
      { key: 'description', label: 'Description / Achievements', type: 'textarea' },
    ];
    const projFields = [
      { key: 'name',        label: 'Project Name' },
      { key: 'url',         label: 'Project URL (optional)' },
      { key: 'tech_stack',  label: 'Tech Stack' },
      { key: 'description', label: 'Description', type: 'textarea' },
    ];
    const certFields = [
      { key: 'name',        label: 'Certification Name' },
      { key: 'issuer',      label: 'Issuing Organization' },
      { key: 'issued_date', label: 'Issue Date' },
      { key: 'url',         label: 'Credential URL (optional)' },
    ];
    const fieldMap = { education: eduFields, experience: expFields, projects: projFields, certifications: certFields };
    const callbackMap = {
      education:      'App.removeEducation',
      experience:     'App.removeExperience',
      projects:       'App.removeProject',
      certifications: 'App.removeCert',
    };
    buildAccordion(containerId, items, fieldMap[type], callbackMap[type]);
  },

  _collectAccordionData(containerId) {
    const container = $(containerId);
    if (!container) return [];
    const itemsMap = {};
    container.querySelectorAll('[data-acc]').forEach(el => {
      const idx = el.getAttribute('data-idx');
      const field = el.getAttribute('data-field');
      if (!itemsMap[idx]) itemsMap[idx] = {};
      itemsMap[idx][field] = el.value;
    });
    return Object.values(itemsMap);
  },

  addEducationEntry() {
    if (!State.profileData.education) State.profileData.education = [];
    State.profileData.education.push({ institution: '', degree: '', field: '', start_year: '', end_year: '', gpa: '' });
    App._renderAccordion('education-list', State.profileData.education, 'education');
  },
  removeEducation(idx) {
    if (State.profileData.education) {
      State.profileData.education.splice(idx, 1);
      App._renderAccordion('education-list', State.profileData.education, 'education');
    }
  },
  addExperienceEntry() {
    if (!State.profileData.experience) State.profileData.experience = [];
    State.profileData.experience.push({ company: '', role: '', location: '', start_date: '', end_date: '', description: '' });
    App._renderAccordion('experience-list', State.profileData.experience, 'experience');
  },
  removeExperience(idx) {
    if (State.profileData.experience) {
      State.profileData.experience.splice(idx, 1);
      App._renderAccordion('experience-list', State.profileData.experience, 'experience');
    }
  },
  addProjectEntry() {
    if (!State.profileData.projects) State.profileData.projects = [];
    State.profileData.projects.push({ name: '', url: '', tech_stack: '', description: '' });
    App._renderAccordion('projects-list', State.profileData.projects, 'projects');
  },
  removeProject(idx) {
    if (State.profileData.projects) {
      State.profileData.projects.splice(idx, 1);
      App._renderAccordion('projects-list', State.profileData.projects, 'projects');
    }
  },
  addCertEntry() {
    if (!State.profileData.certifications) State.profileData.certifications = [];
    State.profileData.certifications.push({ name: '', issuer: '', issued_date: '', url: '' });
    App._renderAccordion('certs-list', State.profileData.certifications, 'certifications');
  },
  removeCert(idx) {
    if (State.profileData.certifications) {
      State.profileData.certifications.splice(idx, 1);
      App._renderAccordion('certs-list', State.profileData.certifications, 'certifications');
    }
  },
  removeTag(dataKey, idx) {
    if (State.tagsData && State.tagsData[dataKey]) {
      State.tagsData[dataKey].splice(idx, 1);
      initTagsInput(`tags-${dataKey}`, `tags-${dataKey}-input`, dataKey);
    }
  },

  async _loadProfileResumesDropdown() {
    try {
      const resumes = await API.get('/api/resumes');
      const list = Array.isArray(resumes) ? resumes : (resumes.resumes || []);
      const docxList = list.filter(r => (r.filename || r.name || '').toLowerCase().endsWith('.docx'));
      const optionsList = docxList.length ? docxList : list;
      const sel = $('profile-template-select');
      if (!sel) return;
      const current = sel.value || (State.profileData && (State.profileData.original_resume_id || State.profileData.template_resume_id)) || '';
      sel.innerHTML = '<option value="">— select uploaded DOCX —</option>' +
        optionsList.map(r => `<option value="${r.id}">${esc(r.filename || r.name)}</option>`).join('');
      if (current) {
        const hasOpt = Array.from(sel.options).some(o => o.value === String(current));
        if (hasOpt) sel.value = String(current);
      }
    } catch { /* ignore */ }
  },

  async saveProfileTemplate() {
    const sel = $('profile-template-select');
    const templateId = sel?.value || '';
    setMsg('profile-save-template-msg', 'Saving...', '');
    try {
      await API.put('/api/candidate', {
        ...(State.profileData || {}),
        original_resume_id: templateId,
        template_resume_id: templateId,
      });
      if (State.profileData) {
        State.profileData.original_resume_id = templateId;
        State.profileData.template_resume_id = templateId;
      }
      setMsg('profile-save-template-msg', '✓ Saved!', 'success');
      Toast.success('Resume template saved!');
      setTimeout(() => setMsg('profile-save-template-msg', ''), 3000);
    } catch(e) {
      setMsg('profile-save-template-msg', '✗ ' + e.message, 'error');
      Toast.error('Failed to save template: ' + e.message);
    }
  },

  async saveProfile() {
    const getData = (id) => $(id)?.value || '';
    const templateId = $('profile-template-select')?.value || (State.profileData && (State.profileData.original_resume_id || State.profileData.template_resume_id)) || '';
    const profile = {
      name:                  getData('p-name'),
      full_name:             getData('p-name'),
      email:                 getData('p-email'),
      phone:                 getData('p-phone'),
      location:              getData('p-location'),
      linkedin:              getData('p-linkedin'),
      github:                getData('p-github'),
      summary:               getData('p-summary'),
      target_role:           getData('p-target-role'),
      years_experience:      parseInt(getData('p-years-exp')) || 0,
      current_company:       getData('p-current-company'),
      current_salary:        getData('p-current-salary'),
      expected_salary:       getData('p-expected-salary'),
      notice_period:         getData('p-notice-period'),
      work_authorization:    getData('p-work-auth'),
      preferred_work_mode:   getData('p-work-mode'),
      technical_skills:      State.tagsData.technical,
      soft_skills:           State.tagsData.soft,
      languages:             State.tagsData.languages,
      education:             App._collectAccordionData('education-list'),
      experience:            App._collectAccordionData('experience-list'),
      projects:              App._collectAccordionData('projects-list'),
      certifications:        App._collectAccordionData('certs-list'),
      original_resume_id:    templateId,
      template_resume_id:    templateId,
      personal: {
        full_name: getData('p-name'),
        email:     getData('p-email'),
        phone:     getData('p-phone'),
        location:  getData('p-location'),
        linkedin:  getData('p-linkedin'),
        github:    getData('p-github'),
      },
      career: {
        current_title:    getData('p-target-role'),
        total_experience: getData('p-years-exp'),
        current_company:  getData('p-current-company'),
        current_ctc:      getData('p-current-salary'),
        expected_salary:  getData('p-expected-salary'),
        notice_period:    getData('p-notice-period'),
      },
      skills: State.tagsData.technical,
    };

    setMsg('profile-save-msg', 'Saving...', '');
    try {
      const updated = await API.put('/api/candidate', profile);
      State.profileData = updated || profile;
      setMsg('profile-save-msg', '✓ Saved!', 'success');
      Toast.success('Profile saved!');
      setTimeout(() => setMsg('profile-save-msg', ''), 3000);
    } catch(e) {
      setMsg('profile-save-msg', '✗ ' + e.message, 'error');
      Toast.error('Save failed: ' + e.message);
    }
  },

  async saveProfileTemplate() {
    const id = $('profile-template-select')?.value;
    if (!id) { Toast.warning('Select a DOCX file first'); return; }
    try {
      const curr = await API.get('/api/candidate');
      const updated = await API.put('/api/candidate', { ...curr, original_resume_id: id, template_resume_id: id });
      State.profileData = updated || { ...curr, original_resume_id: id, template_resume_id: id };
      Toast.success('DOCX Template saved!');
    } catch(e) {
      Toast.error('Failed: ' + e.message);
    }
  },

  // Accordion add/remove
  addEducationEntry()    { (State.profileData.education     = State.profileData.education     || []).push({}); App._renderAccordion('education-list',   State.profileData.education,     'education');    },
  addExperienceEntry()   { (State.profileData.experience    = State.profileData.experience    || []).push({}); App._renderAccordion('experience-list',  State.profileData.experience,    'experience');   },
  addProjectEntry()      { (State.profileData.projects      = State.profileData.projects      || []).push({}); App._renderAccordion('projects-list',    State.profileData.projects,      'projects');     },
  addCertEntry()         { (State.profileData.certifications= State.profileData.certifications|| []).push({}); App._renderAccordion('certs-list',       State.profileData.certifications,'certifications');},
  removeEducation(i)     { State.profileData.education.splice(i,1);     App._renderAccordion('education-list',   State.profileData.education,     'education');    },
  removeExperience(i)    { State.profileData.experience.splice(i,1);    App._renderAccordion('experience-list',  State.profileData.experience,    'experience');   },
  removeProject(i)       { State.profileData.projects.splice(i,1);      App._renderAccordion('projects-list',    State.profileData.projects,      'projects');     },
  removeCert(i)          { State.profileData.certifications.splice(i,1);App._renderAccordion('certs-list',       State.profileData.certifications,'certifications');},

  removeTag(key, idx) {
    State.tagsData[key].splice(idx, 1);
    initTagsInput(`tags-${key}`, `tags-${key}-input`, key);
  },

  /* ═══════════════════════════════════════════════════════
     JOBS
     ═════════════════════════════════════════════════════ */
  async loadJobs() {
    $('jobs-loading').style.display = 'block';
    $('jobs-grid').innerHTML = '';
    hide('jobs-empty');
    try {
      const data = await API.get('/api/jobs');
      State.allJobs = Array.isArray(data) ? data : (data.jobs || []);
      App.renderJobs();
      App.loadFollowups();
    } catch(e) {
      $('jobs-loading').textContent = 'Failed to load jobs.';
      Toast.error('Jobs load failed: ' + e.message);
    }
  },

  renderJobs() {
    $('jobs-loading').style.display = 'none';
    const minMatch = parseFloat($('min-match-filter')?.value) || 0;
    const searchQ  = ($('job-search-filter')?.value || '').toLowerCase().trim();
    let jobs = State.allJobs;
    if (minMatch > 0) jobs = jobs.filter(j => (j.match_score || 0) >= minMatch);
    if (searchQ)      jobs = jobs.filter(j => {
      const hay = `${j.title}${j.role_name}${j.company}${j.location}`.toLowerCase();
      return hay.includes(searchQ);
    });
    if (!jobs.length) { show('jobs-empty'); $('jobs-grid').innerHTML = ''; return; }
    hide('jobs-empty');
    $('jobs-grid').innerHTML = jobs.map(buildJobCard).join('');
  },

  async addJob() {
    const title = $('job-title')?.value.trim();
    const company = $('job-company')?.value.trim();
    const description = $('job-description')?.value.trim();
    if (!title || !company || !description) {
      Toast.warning('Title, Company, and Description are required.');
      return;
    }
    setMsg('job-add-msg', 'Adding...', '');
    try {
      await API.post('/api/jobs', {
        title,
        company,
        location:    $('job-location')?.value.trim()      || '',
        url:         $('job-url')?.value.trim()           || '',
        salary:      $('job-salary')?.value.trim()        || '',
        hr_email:    $('job-hr-email-input')?.value.trim()|| '',
        description,
      });
      setMsg('job-add-msg', '✓ Added!', 'success');
      Toast.success('Job added!');
      ['job-title','job-company','job-location','job-url','job-salary','job-hr-email-input','job-description']
        .forEach(id => { const el = $(id); if (el) el.value = ''; });
      App.loadJobs();
    } catch(e) {
      setMsg('job-add-msg', '✗ ' + e.message, 'error');
      Toast.error('Failed to add job: ' + e.message);
    }
  },

  async runJobSearch() {
    setMsg('search-msg', 'Searching...', '');
    $('run-search-btn').disabled = true;
    try {
      const d = await API.post('/api/jobsearch/run', {});
      const count = d.saved ?? d.new_jobs ?? d.total_fetched ?? 0;
      const msg = d.message || `Search complete! Found ${count} new job(s).`;
      setMsg('search-msg', msg, 'success');
      Toast.success(msg);
      App.loadJobs();
    } catch(e) {
      try {
        const d = await API.post('/api/jobsearch', {});
        const count = d.saved ?? d.new_jobs ?? d.total_fetched ?? 0;
        const msg = d.message || `Search complete! Found ${count} new job(s).`;
        setMsg('search-msg', msg, 'success');
        Toast.success(msg);
        App.loadJobs();
      } catch(e2) {
        setMsg('search-msg', '✗ ' + e2.message, 'error');
        Toast.error('Search failed: ' + e2.message);
      }
    } finally {
      $('run-search-btn').disabled = false;
    }
  },

  async clearNewJobs() {
    if (!confirm('Delete all jobs with status "new"?')) return;
    try {
      const d = await API.del('/api/jobs/clear');
      Toast.success(d.message || 'New jobs cleared.');
      App.loadJobs();
    } catch(e) {
      Toast.error('Failed: ' + e.message);
    }
  },

  async analyzeAllUnanalyzed() {
    setMsg('analyze-unanalyzed-msg', 'Analyzing...', '');
    $('analyze-unanalyzed-btn').disabled = true;
    try {
      const d = await API.post('/api/jobs/analyze-unanalyzed', {});
      const msg = d.message || `Analyzed ${d.analyzed || 0} jobs.`;
      setMsg('analyze-unanalyzed-msg', msg, 'success');
      Toast.success(msg);
      App.loadJobs();
    } catch(e) {
      setMsg('analyze-unanalyzed-msg', e.message, 'error');
      Toast.error('Analyze failed: ' + e.message);
    } finally {
      $('analyze-unanalyzed-btn').disabled = false;
    }
  },

  async importExcel() {
    const file = $('excel-import-input')?.files[0];
    if (!file) { Toast.warning('Select an Excel file first.'); return; }
    setMsg('excel-import-msg', 'Importing...', '');
    const fd = new FormData();
    fd.append('file', file);
    try {
      const d = await API.postForm('/api/jobs/import-excel', fd);
      setMsg('excel-import-msg', d.message || `Imported ${d.imported || 0} jobs.`, 'success');
      Toast.success(d.message || 'Import complete!');
      App.loadJobs();
    } catch(e) {
      setMsg('excel-import-msg', e.message, 'error');
      Toast.error('Import failed: ' + e.message);
    }
  },

  /* ── FOLLOW-UPS ────────────────────────────────────────── */
  async loadFollowups() {
    try {
      const apps = await API.get('/api/applications');
      const list = Array.isArray(apps) ? apps : (apps.applications || []);
      const dueDates = list.filter(a => a.followup_due || a.needs_followup);
      const card = $('followups-card');
      if (!card) return;
      if (!dueDates.length) { card.classList.add('d-none'); return; }
      card.classList.remove('d-none');
      const container = $('followups-list');
      container.innerHTML = dueDates.map(a => `
        <div class="resume-item" style="margin-bottom:8px">
          <div class="resume-info">
            <div class="resume-name">${esc(a.company)} — ${esc(a.role || a.title)}</div>
            <div class="resume-meta">Due: ${fmtDate(a.followup_due || a.followup_date)}</div>
          </div>
          <button class="btn btn-secondary btn-xs" onclick="App.previewFollowup('${a.job_id || a.id}')">Preview & Send</button>
        </div>`).join('');
    } catch { /* ignore */ }
  },

  async previewFollowup(jobId) {
    State.followupJobId = jobId;
    try {
      const d = await API.post(`/api/jobs/${jobId}/apply-email/preview`, {});
      $('followup-email-subject').value = d.subject || '';
      $('followup-email-body').value    = d.body    || '';
      setText('followup-preview-title', `Follow-up for Job #${jobId}`);
      show('followup-preview-block');
    } catch(e) {
      Toast.error('Preview failed: ' + e.message);
    }
  },

  async sendFollowup() {
    if (!State.followupJobId) return;
    try {
      await API.post(`/api/jobs/${State.followupJobId}/apply-email`, {
        subject: $('followup-email-subject')?.value,
        body:    $('followup-email-body')?.value,
      });
      setMsg('followup-send-msg', '✓ Sent!', 'success');
      Toast.success('Follow-up sent!');
      hide('followup-preview-block');
    } catch(e) {
      setMsg('followup-send-msg', e.message, 'error');
    }
  },

  /* ── TRIGGER HELPERS (Job Card Buttons) ───────────────── */
  async triggerAnalyzeJD(jobId) {
    await this.openJobDetail(jobId);
    await this.analyzeJD();
  },
  async triggerFindContacts(jobId) {
    await this.openJobDetail(jobId);
    await this.findContacts();
  },
  async triggerGenerateResume(jobId) {
    await this.openJobDetail(jobId);
    await this.generateResume();
  },
  async triggerPreviewPDF(jobId) {
    await this.openJobDetail(jobId);
    this.previewResumePDF();
  },
  async triggerEmailHR(jobId) {
    await this.openJobDetail(jobId);
    this.focusEmailHR();
  },
  async triggerApplyWeb(jobId) {
    await this.openJobDetail(jobId);
    this.startWebsiteApply();
  },

  /* ═══════════════════════════════════════════════════════
     JOB DETAIL PANEL
     ═════════════════════════════════════════════════════ */
  async openJobDetail(jobId) {
    State.currentJobId = jobId;
    openPanel();

    // Reset panel state
    hide('jdp-analysis-result');    show('jdp-analysis-placeholder');   hide('jdp-analysis-loading');
    hide('jdp-contacts-list');      show('jdp-contacts-placeholder');    hide('jdp-contacts-loading');
    hide('jdp-resume-result');      show('jdp-resume-placeholder');      hide('jdp-resume-loading');
    hide('jdp-automation-container'); show('jdp-website-placeholder');
    hide('jdp-match-badge');
    hide('jdp-email-preview-block');

    try {
      const job = await API.get(`/api/jobs/${jobId}`);
      State.currentJob = job;
      App._renderJobDetail(job);
    } catch(e) {
      Toast.error('Failed to load job: ' + e.message);
    }
  },

  _renderJobDetail(job) {
    setText('jdp-title', job.title || job.role_name || '(No Title)');
    const metaParts = [job.company, job.location, job.experience_required, job.job_type].filter(Boolean);
    setText('jdp-meta', metaParts.join(' · '));
    setHtml('jdp-status-badge', `<span class="badge-dot ${job.status || 'new'}"></span>${(STATUS_MAP[job.status] || STATUS_MAP.new).label}`);
    $('jdp-status-badge').className = `badge ${(STATUS_MAP[job.status] || STATUS_MAP.new).cls}`;
    $('jdp-status-select').value = job.status || 'new';
    setText('jdp-description', job.description || job.job_description || '—');

    if (job.hr_email) $('jdp-hr-email').value = job.hr_email;

    if (job.match_score != null) {
      show('jdp-match-badge');
      setText('jdp-match-badge', `${Math.round(job.match_score)}% match`);
    }

    if (job.analysis || job.match_score != null) App._renderAnalysis(job);
    if (job.resume_generated) App._renderResumeResult(job);

    App.loadJobContacts(job.id);
    updateStepper(job);
  },

  _renderAnalysis(job) {
    const a = job.analysis || {};
    hide('jdp-analysis-placeholder');
    show('jdp-analysis-result');

    const skills  = a.required_skills || a.extracted_skills || [];
    const missing = a.missing_skills  || [];
    $('jdp-skills-list').innerHTML  = skills.map(s => `<span class="badge badge-analyzed" style="font-size:10px">${esc(s)}</span>`).join('');
    $('jdp-missing-list').innerHTML = missing.map(s => `<span class="badge badge-failed"   style="font-size:10px">${esc(s)}</span>`).join('');
    setText('jdp-experience', a.experience_required || job.experience_required || '—');
    setText('jdp-difficulty', a.interview_difficulty || '—');

    const learning = a.learning_suggestions || [];
    if (learning.length) {
      show('jdp-learning-block');
      $('jdp-learning-list').innerHTML = learning.map(l => `<li>${esc(l)}</li>`).join('');
    } else {
      hide('jdp-learning-block');
    }
  },

  _renderResumeResult(job) {
    hide('jdp-resume-placeholder');
    hide('jdp-resume-loading');
    show('jdp-resume-result');

    const ats = job.ats_score || 0;
    const ring = $('jdp-ats-ring');
    ring.textContent = ats ? `${Math.round(ats)}%` : '—';
    ring.className = 'ats-score-ring ' + (ats >= 85 ? 'high' : ats >= 70 ? 'med' : 'low');

    const warn = $('jdp-ats-warn');
    if (ats > 0 && ats < 90) {
      warn.textContent = `ATS score is ${Math.round(ats)}%. Consider regenerating for a higher match.`;
      warn.classList.remove('d-none');
    } else {
      warn.classList.add('d-none');
    }

    $('jdp-dl-pdf-btn').href  = `/api/jobs/${job.id}/download-pdf`;
    $('jdp-dl-docx-btn').href = `/api/jobs/${job.id}/download-docx`;
  },

  async updateJobStatus(jobId, status) {
    try {
      await API.put(`/api/jobs/${jobId}`, { status });
      const card = $(`job-card-${jobId}`);
      if (card) {
        const topBadge = card.querySelector('.job-card-top .badge');
        if (topBadge) topBadge.outerHTML = statusBadgeHTML(status);
      }
      const job = State.allJobs.find(j => j.id === jobId);
      if (job) job.status = status;
    } catch(e) {
      Toast.error('Status update failed: ' + e.message);
    }
  },

  async deleteJob() {
    if (!State.currentJobId || !confirm('Delete this job? This cannot be undone.')) return;
    try {
      await API.del(`/api/jobs/${State.currentJobId}`);
      Toast.success('Job deleted.');
      closePanel();
      App.loadJobs();
    } catch(e) {
      Toast.error('Delete failed: ' + e.message);
    }
  },

  /* ── ANALYZE JD ────────────────────────────────────────── */
  async analyzeJD() {
    if (!State.currentJobId) return;
    show('jdp-analysis-loading');
    hide('jdp-analysis-result');
    hide('jdp-analysis-placeholder');
    try {
      const d = await API.post(`/api/jobs/${State.currentJobId}/analyze-jd`, {});
      State.currentJob = { ...State.currentJob, ...d, analysis: d };
      App._renderAnalysis(d);
      hide('jdp-analysis-loading');
      Toast.success('JD analyzed!');
      updateStepper(State.currentJob);
    } catch {
      // fallback to ATS analyze
      try {
        const d = await API.post(`/api/jobs/${State.currentJobId}/analyze`, {});
        State.currentJob = { ...State.currentJob, ...d };
        App._renderAnalysis(d);
        hide('jdp-analysis-loading');
        Toast.success('Analysis complete!');
        updateStepper(State.currentJob);
      } catch(e2) {
        hide('jdp-analysis-loading');
        show('jdp-analysis-placeholder');
        Toast.error('Analysis failed: ' + e2.message);
      }
    }
  },

  async runATSAnalysis() {
    if (!State.currentJobId) return;
    show('jdp-analysis-loading');
    hide('jdp-analysis-result');
    hide('jdp-analysis-placeholder');
    try {
      const d = await API.post(`/api/jobs/${State.currentJobId}/analyze`, {});
      State.currentJob = { ...State.currentJob, ...d };
      App._renderAnalysis(d);
      hide('jdp-analysis-loading');
      Toast.success('ATS analysis complete!');
      updateStepper(State.currentJob);
    } catch(e) {
      hide('jdp-analysis-loading');
      show('jdp-analysis-placeholder');
      Toast.error('Analysis failed: ' + e.message);
    }
  },

  /* ── FIND HR CONTACTS ──────────────────────────────────── */
  async findContacts() {
    if (!State.currentJobId) return;
    show('jdp-contacts-loading');
    hide('jdp-contacts-placeholder');
    $('jdp-contacts-list').innerHTML = '';
    try {
      const d = await API.post(`/api/jobs/${State.currentJobId}/find-contacts`, {});
      hide('jdp-contacts-loading');
      App._renderContacts(d.contacts || d || []);
      Toast.success(`Found ${(d.contacts || d || []).length} contacts!`);
      if (State.currentJob) { State.currentJob.contacts_count = (d.contacts || d || []).length; updateStepper(State.currentJob); }
    } catch(e) {
      hide('jdp-contacts-loading');
      show('jdp-contacts-placeholder');
      Toast.error('Find contacts failed: ' + e.message);
    }
  },

  async loadJobContacts(jobId) {
    try {
      const d = await API.get(`/api/jobs/${jobId}/contacts`);
      const list = d.contacts || d || [];
      if (list.length) {
        $('jdp-contacts-list').innerHTML = '';
        App._renderContacts(list);
        hide('jdp-contacts-placeholder');
      }
    } catch { /* ignore */ }
  },

  _renderContacts(contacts) {
    const container = $('jdp-contacts-list');
    if (!contacts.length) { show('jdp-contacts-placeholder'); return; }
    hide('jdp-contacts-placeholder');
    container.innerHTML = '';
    show('jdp-contacts-list');
    contacts.forEach(c => {
      const conf = (c.confidence || '').toLowerCase();
      const initials = (c.name || 'HR').split(' ').map(w => w[0]).slice(0,2).join('').toUpperCase();
      const item = document.createElement('div');
      item.className = 'contact-item';
      item.innerHTML = `
        <div class="contact-avatar">${initials}</div>
        <div class="contact-info">
          <div class="contact-name">${esc(c.name || 'Unknown')}</div>
          <div class="contact-email">${esc(c.email || '—')}</div>
          ${c.title ? `<div class="font-xs text-muted">${esc(c.title)}</div>` : ''}
        </div>
        <span class="confidence-badge confidence-${conf || 'medium'}">${esc(c.confidence || 'Medium')}</span>
        <button class="btn btn-secondary btn-xs" onclick="document.getElementById('jdp-hr-email').value='${esc(c.email||'')}';document.getElementById('jdp-email-section').scrollIntoView({behavior:'smooth'})">Use</button>`;
      container.appendChild(item);
    });
  },

  /* ── GENERATE RESUME ───────────────────────────────────── */
  async generateResume() {
    if (!State.currentJobId) return;

    // Show loading with steps
    hide('jdp-resume-result');
    hide('jdp-resume-placeholder');
    show('jdp-resume-loading');
    hide('jdp-gen-steps');

    // Step animation
    const steps = ['gen-step-1','gen-step-2','gen-step-3','gen-step-4'];
    steps.forEach(s => { const el = $(s); if(el) { el.className='loading-step'; } });
    show('jdp-gen-steps');

    let stepIdx = 0;
    const stepTimer = setInterval(() => {
      if (stepIdx > 0) { const prev = $(steps[stepIdx-1]); if(prev) prev.className='loading-step done'; }
      if (stepIdx < steps.length) { const curr = $(steps[stepIdx]); if(curr) curr.className='loading-step active'; stepIdx++; }
    }, 1200);

    try {
      const d = await API.post(`/api/jobs/${State.currentJobId}/customize-resume`, {});
      clearInterval(stepTimer);
      steps.forEach(s => { const el=$(s); if(el) el.className='loading-step done'; });
      hide('jdp-resume-loading');

      const ats = d.ats_score || d.match_score || 0;
      State.currentJob = { ...State.currentJob, resume_generated: true, ats_score: ats };
      App._renderResumeResult(State.currentJob);
      Toast.success(`Resume generated! ATS: ${Math.round(ats)}%`);
      updateStepper(State.currentJob);
      App.loadJobs();
    } catch(e) {
      clearInterval(stepTimer);
      hide('jdp-resume-loading');
      show('jdp-resume-placeholder');
      Toast.error('Resume generation failed: ' + e.message);
    }
  },

  previewResumePDF() {
    if (!State.currentJobId) return;
    openPDFModal(`/api/jobs/${State.currentJobId}/preview-pdf`, `Resume — ${State.currentJob?.title || 'Job'}`);
    $('step-btn-4').classList.add('completed');
  },

  /* ── EMAIL HR ──────────────────────────────────────────── */
  focusEmailHR() {
    $('jdp-email-section')?.scrollIntoView({ behavior: 'smooth' });
    $('jdp-hr-email')?.focus();
  },

  async previewPersonalizedEmail() {
    const email = $('jdp-hr-email')?.value.trim();
    if (!email) { Toast.warning('Enter an HR email address first.'); return; }
    if (!State.currentJobId) return;

    setMsg('jdp-email-msg', 'Loading preview...', '');
    try {
      const d = await API.post(`/api/jobs/${State.currentJobId}/apply-email-personalized/preview`, { hr_email: email });
      $('jdp-email-subject').value = d.subject || '';
      $('jdp-email-body').value    = d.html_body || d.body || '';
      show('jdp-email-preview-block');
      setMsg('jdp-email-msg', '', '');
    } catch(e) {
      // Fallback to generic preview
      try {
        const d = await API.post(`/api/jobs/${State.currentJobId}/apply-email/preview`, { hr_email: email });
        $('jdp-email-subject').value = d.subject || '';
        $('jdp-email-body').value    = d.html_body || d.body || '';
        show('jdp-email-preview-block');
        setMsg('jdp-email-msg', '');
      } catch(e2) {
        setMsg('jdp-email-msg', e2.message, 'error');
        Toast.error('Preview failed: ' + e2.message);
      }
    }
  },

  async sendPersonalizedEmail() {
    const email   = $('jdp-hr-email')?.value.trim();
    const subject = $('jdp-email-subject')?.value;
    const body    = $('jdp-email-body')?.value;
    if (!email || !State.currentJobId) return;

    $('jdp-email-send-btn').disabled = true;
    try {
      await API.post(`/api/jobs/${State.currentJobId}/apply-email-personalized`, { hr_email: email, subject, body });
      Toast.success('Email sent!');
      hide('jdp-email-preview-block');
      if (State.currentJob) { State.currentJob.status = 'email_sent'; updateStepper(State.currentJob); }
      App.loadJobs();
    } catch {
      // Fallback
      try {
        await API.post(`/api/jobs/${State.currentJobId}/apply-email`, { hr_email: email, subject, body });
        Toast.success('Email sent!');
        hide('jdp-email-preview-block');
        App.loadJobs();
      } catch(e2) {
        Toast.error('Send failed: ' + e2.message);
      }
    } finally {
      $('jdp-email-send-btn').disabled = false;
    }
  },

  /* ── WEBSITE APPLY ─────────────────────────────────────── */
  async startWebsiteApply() {
    if (!State.currentJobId) return;
    const job = State.currentJob || {};
    const url = job.url || job.application_url || '';

    hide('jdp-website-placeholder');
    show('jdp-automation-container');
    hide('jdp-captcha-alert');
    show('jdp-confirm-alert');
    hide('jdp-screenshot-wrap');
    hide('jdp-fields-preview-wrap');
    setText('jdp-auto-status-text', 'Application link opened in new tab. Use Candidate Assist below to copy field details.');
    $('jdp-auto-status-header').querySelector('.spinner')?.classList.add('d-none');

    if (url && (url.startsWith('http://') || url.startsWith('https://'))) {
      window.open(url, '_blank');
      Toast.success('Job link opened in new tab!');
    }

    try {
      await API.post(`/api/jobs/${State.currentJobId}/apply-website`, {});
      startAutomationPoll(State.currentJobId);
    } catch(e) {
      console.warn('Backend automation notice:', e.message);
    }
  },

  copyFieldValue(val) {
    if (!val) return;
    navigator.clipboard.writeText(val);
    Toast.success('Copied to clipboard!');
  },

  async pollAutomationStatus(jobId) {
    try {
      const d = await API.get(`/api/jobs/${jobId}/apply-website/status`);
      const status = (d.status || '').toUpperCase();
      if (status && status !== 'INITIALIZING') {
        setText('jdp-auto-status-text', d.message || status);
      }

      if (status === 'CAPTCHA_REQUIRED') {
        show('jdp-captcha-alert');
        hide('jdp-confirm-alert');
        stopAutomationPoll();
      } else if (status === 'AWAITING_CONFIRMATION' || status === 'ASSISTED_APPLY') {
        hide('jdp-captcha-alert');
        show('jdp-confirm-alert');
        stopAutomationPoll();
      } else if (status === 'COMPLETED' || status === 'APPLIED') {
        hide('jdp-captcha-alert');
        hide('jdp-confirm-alert');
        stopAutomationPoll();
        Toast.success('Application submitted!');
        if (State.currentJob) { State.currentJob.status = 'applied'; updateStepper(State.currentJob); }
        App.loadJobs();
      } else if (status === 'ERROR' || status === 'FAILED') {
        stopAutomationPoll();
        show('jdp-confirm-alert');
      }

      // Screenshot
      if (d.screenshot) {
        show('jdp-screenshot-wrap');
        $('jdp-screenshot').src = d.screenshot.startsWith('data:') ? d.screenshot : `data:image/png;base64,${d.screenshot}`;
      }

      // Form fields preview / candidate assist
      const fields = (d.form_preview && d.form_preview.length) ? d.form_preview : (d.fields || []);
      if (fields && fields.length) {
        show('jdp-fields-preview-wrap');
        $('jdp-fields-tbody').innerHTML = fields.map(f => `
          <tr>
            <td><b>${esc(f.name || f.field)}</b></td>
            <td style="max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(f.value || '—')}</td>
            <td>
              ${f.value ? `<button class="btn btn-secondary btn-xs" onclick="App.copyFieldValue('${esc(f.value.replace(/'/g, "\\'"))}')">Copy</button>` : '<span class="text-muted font-xs">—</span>'}
            </td>
          </tr>`).join('');
      }
    } catch(e) {
      console.warn('Automation poll error:', e.message);
    }
  },

  async continueAfterCaptcha() {
    if (!State.currentJobId) return;
    try {
      await API.post(`/api/jobs/${State.currentJobId}/apply-website/continue`, {});
      hide('jdp-captcha-alert');
      setText('jdp-auto-status-text', 'Continuing...');
      startAutomationPoll(State.currentJobId);
    } catch(e) { Toast.error('Continue failed: ' + e.message); }
  },

  async confirmWebApply() {
    if (!State.currentJobId) return;
    $('jdp-confirm-alert').querySelector('button')?.setAttribute('disabled','true');
    try {
      await API.post(`/api/jobs/${State.currentJobId}/apply-website/confirm`, {});
      hide('jdp-confirm-alert');
      Toast.success('Application confirmed and submitted!');
      if (State.currentJob) { State.currentJob.status = 'applied'; updateStepper(State.currentJob); }
      App.loadJobs();
    } catch(e) { Toast.error('Confirm failed: ' + e.message); }
  },

  async cancelWebApply() {
    if (!State.currentJobId) return;
    stopAutomationPoll();
    try {
      await API.post(`/api/jobs/${State.currentJobId}/apply-website/cancel`, {});
      hide('jdp-automation-container');
      show('jdp-website-placeholder');
      Toast.info('Automation cancelled.');
    } catch(e) {
      Toast.error('Cancel failed: ' + e.message);
    }
  },

  /* ═══════════════════════════════════════════════════════
     RESUMES
     ═════════════════════════════════════════════════════ */
  async loadResumes() {
    const container = $('resumes-list');
    if (!container) return;
    container.innerHTML = '<div class="text-muted font-sm">Loading...</div>';
    try {
      const data = await API.get('/api/resumes');
      State.allResumes = Array.isArray(data) ? data : (data.resumes || []);
      App._renderResumeList();
      App._loadProfileResumesDropdown();
    } catch(e) {
      container.innerHTML = `<div class="text-muted font-sm">Failed: ${esc(e.message)}</div>`;
    }
  },

  _renderResumeList() {
    const container = $('resumes-list');
    if (!State.allResumes.length) {
      container.innerHTML = '<div class="text-muted font-sm">No resumes uploaded yet.</div>';
      return;
    }
    container.innerHTML = State.allResumes.map(r => {
      const isDefault = r.is_default;
      const ext = (r.filename || r.name || '').split('.').pop().toUpperCase();
      const icon = ext === 'PDF' ? '📕' : '📘';
      return `
        <div class="resume-item" id="resume-item-${r.id}">
          <div class="resume-icon">${icon}</div>
          <div class="resume-info">
            <div class="resume-name">${esc(r.filename || r.name)}</div>
            <div class="resume-meta">
              ${isDefault ? '<span class="badge badge-ready" style="font-size:9px">DEFAULT</span>' : ''}
              ${fmtDate(r.uploaded_at || r.created_at)}
              ${r.version ? ` · v${r.version}` : ''}
            </div>
          </div>
          <div class="resume-actions">
            <button class="btn btn-secondary btn-xs" onclick="App.showResumeDetail('${r.id}')">Details</button>
            ${!isDefault ? `<button class="btn btn-ghost btn-xs" onclick="App.setResumeDefaultById('${r.id}')">Set Default</button>` : ''}
            <button class="btn btn-danger btn-xs" onclick="App.deleteResumeById('${r.id}')">Remove</button>
          </div>
        </div>`;
    }).join('');
  },

  async uploadResume(droppedFile) {
    const file = droppedFile || $('resume-file-input')?.files[0];
    if (!file) { Toast.warning('Select a file first.'); return; }
    const isDefault = $('resume-set-default')?.checked || false;
    setMsg('resume-upload-msg', 'Uploading...', '');
    const fd = new FormData();
    fd.append('file', file);
    if (isDefault) fd.append('set_default', 'true');
    try {
      const d = await API.postForm('/api/resumes/upload', fd);
      setMsg('resume-upload-msg', '✓ Uploaded!', 'success');
      Toast.success('Resume uploaded!');
      $('resume-file-input').value = '';
      App.loadResumes();
    } catch(e) {
      setMsg('resume-upload-msg', '✗ ' + e.message, 'error');
      Toast.error('Upload failed: ' + e.message);
    }
  },

  async showResumeDetail(resumeId) {
    State.currentResumeId = String(resumeId);
    let resume = State.allResumes.find(r => String(r.id) === String(resumeId));
    try {
      const detail = await API.get(`/api/resumes/${resumeId}`);
      if (detail) resume = detail;
    } catch { /* use cached */ }

    if (!resume) return;
    setText('resume-detail-title', resume.filename || resume.name);
    setText('resume-detail-text', resume.extracted_text || '(No text extracted yet)');
    // Versions
    const ul = $('resume-versions-list');
    const versions = resume.versions || [];
    ul.innerHTML = versions.map((v,i) => `
      <li class="resume-item" style="padding:8px 12px">
        <div class="resume-info"><div class="resume-name font-sm">v${v.version || i+1}</div><div class="resume-meta">${fmtDate(v.uploaded_at)}</div></div>
      </li>`).join('') || '<li class="text-muted font-sm" style="padding:6px 0">No version history</li>';
    hide('resume-analysis-block');
    show('resume-detail-card');
    $('resume-detail-card').scrollIntoView({ behavior: 'smooth' });
  },

  async setResumeDefault()        { await App.setResumeDefaultById(State.currentResumeId); },
  async setResumeDefaultById(id)  {
    try {
      await API.put(`/api/resumes/${id}/default`, {});
      Toast.success('Set as default!');
      App.loadResumes();
    } catch(e) {
      Toast.error('Failed: ' + e.message);
    }
  },

  async deleteResume()            { await App.deleteResumeById(State.currentResumeId); },
  async deleteResumeById(id) {
    if (!id || !confirm('Are you sure you want to remove this resume file?')) return;
    try {
      await API.del(`/api/resumes/${id}`);
      Toast.success('Resume removed.');
      if (State.currentResumeId === String(id)) hide('resume-detail-card');
      App.loadResumes();
    } catch(e) {
      Toast.error('Delete failed: ' + e.message);
    }
  },

  async uploadResumeVersion() {
    if (!State.currentResumeId) return;
    const file = $('resume-version-input')?.files[0];
    if (!file) return;
    const fd = new FormData();
    fd.append('file', file);
    try {
      await API.postForm(`/api/resumes/upload`, fd);
      Toast.success('New version uploaded!');
      App.loadResumes();
    } catch(e) {
      Toast.error('Upload failed: ' + e.message);
    }
  },

  async analyzeResume() {
    if (!State.currentResumeId) return;
    $('resume-analyze-btn').disabled = true;
    $('resume-analyze-btn').textContent = 'Analyzing...';
    try {
      const d = await API.post(`/api/resumes/${State.currentResumeId}/analyze`, {});
      show('resume-analysis-block');
      setText('resume-analysis-text', typeof d.analysis === 'string' ? d.analysis : JSON.stringify(d.analysis || d, null, 2));
      Toast.success('Analysis complete!');
    } catch(e) {
      Toast.error('Analyze failed: ' + e.message);
    } finally {
      $('resume-analyze-btn').disabled = false;
      $('resume-analyze-btn').textContent = '🤖 Analyze with AI';
    }
  },

  /* ═══════════════════════════════════════════════════════
     SETTINGS
     ═════════════════════════════════════════════════════ */
  async loadSettings() {
    try {
      const s = await API.get('/api/settings');
      setText('disp_ai_provider',    s.ai_provider     || '—');
      setText('disp_ollama_base_url',s.ollama_base_url  || '—');
      setText('disp_ollama_model',   s.ollama_model     || '—');
      setText('disp_gemini_key',     s.gemini_api_key_set ? '●●●●●●●● (set)' : '(not set)');
      const sel = $('gemini-model-select');
      if (sel) {
        const choices = s.gemini_model_choices || [
          "gemini-2.0-flash",
          "gemini-1.5-flash",
          "gemini-2.5-flash",
          "gemini-2.0-flash-lite",
          "gemini-1.5-pro",
          "gemini-1.5-flash-8b",
          "gemini-2.5-pro",
          "gemini-flash-latest",
          "gemini-pro-latest"
        ];
        sel.innerHTML = choices.map(m => `<option value="${esc(m)}">${esc(m)}</option>`).join('');
        if (s.gemini_model) sel.value = s.gemini_model;
      }
    } catch(e) {
      Toast.error('Settings load failed: ' + e.message);
    }

    App.loadEmailStatus();
    App.loadConfig();
    App._loadConfigPrefs();
  },

  async loadEmailStatus() {
    try {
      const d = await API.get('/api/notifications/status');
      const ok = d.configured || d.status === 'ok';
      setText('email-status-text', ok ? `✓ Configured (${d.provider || 'email'})` : `✗ Not configured`);
      $('email-status-text').style.color = ok ? 'var(--green)' : 'var(--red)';
    } catch {
      setText('email-status-text', 'Could not check status');
    }
  },

  async saveGeminiModel() {
    const model = $('gemini-model-select')?.value;
    if (!model) return;
    setMsg('gemini-model-msg', 'Saving...', '');
    try {
      await API.put('/api/settings/gemini-model', { model: model, gemini_model: model });
      setMsg('gemini-model-msg', '✓ Saved (' + model + ')', 'success');
      Toast.success('Gemini model updated to ' + model);
      setTimeout(() => setMsg('gemini-model-msg',''), 3000);
      App.checkAI();
    } catch(e) {
      try {
        await API.put('/api/settings', { gemini_model: model, model: model });
        setMsg('gemini-model-msg', '✓ Saved (' + model + ')', 'success');
        Toast.success('Gemini model updated to ' + model);
        setTimeout(() => setMsg('gemini-model-msg',''), 3000);
        App.checkAI();
      } catch(e2) {
        setMsg('gemini-model-msg', '✗ ' + e2.message, 'error');
        Toast.error('Save failed: ' + e2.message);
      }
    }
  },

  async testAIConnection() {
    setMsg('settings-msg', 'Testing...', '');
    $('test-ai-btn').disabled = true;
    try {
      let d;
      try {
        d = await API.get('/api/ai/health');
      } catch {
        d = await API.get('/api/settings/ai/health');
      }
      const ok = d.ok || d.healthy || d.status === 'ok';
      const detail = d.model ? ` (${d.provider} / ${d.model})` : d.error ? ` (${d.error})` : '';
      setMsg('settings-msg', ok ? `✓ Connection OK${detail}` : `✗ Failed${detail}`, ok ? 'success' : 'error');
      if (ok) Toast.success(`AI Connection OK!${detail}`);
      else    Toast.error(`AI Connection failed${detail}`);
      App.checkAI();
    } catch(e) {
      setMsg('settings-msg', '✗ ' + e.message, 'error');
      Toast.error('Test connection failed: ' + e.message);
    } finally {
      $('test-ai-btn').disabled = false;
    }
  },

  async sendTestEmail() {
    setMsg('email-test-msg', 'Sending...', '');
    $('send-test-email-btn').disabled = true;
    try {
      const d = await API.post('/api/notifications/test-email', {});
      setMsg('email-test-msg', d.message || '✓ Sent!', 'success');
      Toast.success('Test email sent!');
    } catch(e) {
      setMsg('email-test-msg', '✗ ' + e.message, 'error');
      Toast.error('Test email failed: ' + e.message);
    } finally {
      $('send-test-email-btn').disabled = false;
    }
  },

  async _loadConfigPrefs() {
    try {
      const cfg = await API.get('/api/config');
      if (cfg.language)              $('pref-language').value = cfg.language;
      if (cfg.job_posted_within_days) $('pref-posted-within-days').value = cfg.job_posted_within_days;
    } catch { /* ignore */ }
  },

  async saveLanguagePref() {
    const lang = $('pref-language')?.value;
    setMsg('pref-language-msg', 'Saving...', '');
    try {
      const cfg = await API.get('/api/config');
      await API.put('/api/config', { ...cfg, language: lang });
      setMsg('pref-language-msg', '✓ Saved', 'success');
      setTimeout(() => setMsg('pref-language-msg',''), 2500);
    } catch(e) {
      setMsg('pref-language-msg', '✗ ' + e.message, 'error');
    }
  },

  async savePostedWithin() {
    const days = parseInt($('pref-posted-within-days')?.value);
    if (!days || days < 1) { Toast.warning('Enter a valid number of days.'); return; }
    setMsg('pref-posted-within-msg', 'Saving...', '');
    try {
      const cfg = await API.get('/api/config');
      await API.put('/api/config', { ...cfg, job_posted_within_days: days });
      setMsg('pref-posted-within-msg', '✓ Saved', 'success');
      setTimeout(() => setMsg('pref-posted-within-msg',''), 2500);
    } catch(e) {
      setMsg('pref-posted-within-msg', '✗ ' + e.message, 'error');
    }
  },

  async loadConfig() {
    try {
      const cfg = await API.get('/api/config');
      $('config-json').value = JSON.stringify(cfg, null, 2);
      setMsg('config-msg', '');
    } catch(e) {
      setMsg('config-msg', 'Load failed: ' + e.message, 'error');
    }
  },

  async saveConfig() {
    const raw = $('config-json')?.value;
    setMsg('config-msg', 'Saving...', '');
    let parsed;
    try { parsed = JSON.parse(raw); } catch {
      setMsg('config-msg', '✗ Invalid JSON', 'error');
      Toast.error('Invalid JSON — check syntax.');
      return;
    }
    try {
      await API.put('/api/config', parsed);
      setMsg('config-msg', '✓ Saved!', 'success');
      Toast.success('Config saved!');
      setTimeout(() => setMsg('config-msg',''), 3000);
    } catch(e) {
      setMsg('config-msg', '✗ ' + e.message, 'error');
      Toast.error('Save failed: ' + e.message);
    }
  },

  uploadConfigFile() {
    const file = $('config-file-input')?.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const parsed = JSON.parse(e.target.result);
        $('config-json').value = JSON.stringify(parsed, null, 2);
        setMsg('config-msg', 'File loaded — click Save to apply.', '');
        Toast.info('JSON file loaded. Click Save to apply.');
      } catch {
        Toast.error('Invalid JSON file.');
      }
    };
    reader.readAsText(file);
  },
};

/* ─────────────────────────────────────────────────────────
   BOOT
   ───────────────────────────────────────────────────────── */
window.App = App;
document.addEventListener('DOMContentLoaded', () => App.init());
