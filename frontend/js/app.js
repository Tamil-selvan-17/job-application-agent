const API = ""; // same origin

// Safety net: if any part of this script throws or a promise rejects unhandled,
// log it clearly instead of the page silently going dead (e.g. buttons doing
// nothing, status text stuck on "checking..." forever).
window.addEventListener("error", (e) => {
  console.error("Unhandled JS error:", e.message, e.filename, e.lineno);
});
window.addEventListener("unhandledrejection", (e) => {
  console.error("Unhandled promise rejection:", e.reason);
});

// ---------- Tabs ----------
document.querySelectorAll("[data-tab]").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll("[data-tab]").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    document.querySelectorAll(".tab-pane").forEach((p) => p.classList.add("d-none"));
    document.getElementById(`tab-${btn.dataset.tab}`).classList.remove("d-none");
  });
});

// ---------- Settings (read-only display; actual config lives in backend/.env) ----------
async function loadSettings() {
  const res = await fetch(`${API}/api/settings`);
  const s = await res.json();
  document.getElementById("disp_ai_provider").textContent = s.ai_provider || "-";
  document.getElementById("disp_ollama_base_url").textContent = s.ollama_base_url || "-";
  document.getElementById("disp_ollama_model").textContent = s.ollama_model || "-";
  document.getElementById("disp_gemini_model").textContent = s.gemini_model || "-";
  document.getElementById("disp_gemini_key").textContent = s.gemini_api_key_set ? "set ✔" : "not set";
  checkAiHealth();
}

document.getElementById("test-ai-btn").addEventListener("click", checkAiHealth);

async function checkAiHealth() {
  const badge = document.getElementById("ai-status-badge");
  badge.textContent = "checking AI...";
  badge.className = "badge bg-secondary";
  try {
    const res = await fetch(`${API}/api/settings/ai/health`);
    const data = await res.json();
    if (data.ok) {
      badge.textContent = `${data.provider} ✔ connected`;
      badge.className = "badge bg-success";
    } else {
      badge.textContent = `${data.provider} ✘ ${data.error || "unreachable"}`;
      badge.className = "badge bg-danger";
    }
  } catch (e) {
    badge.textContent = "AI check failed";
    badge.className = "badge bg-danger";
  }
}

// ---------- Config ----------
async function loadConfig() {
  const res = await fetch(`${API}/api/config`);
  const cfg = await res.json();
  document.getElementById("config-json").value = JSON.stringify(cfg, null, 2);
}

document.getElementById("reload-config-btn").addEventListener("click", loadConfig);

document.getElementById("save-config-btn").addEventListener("click", async () => {
  const msg = document.getElementById("config-msg");
  let parsed;
  try {
    parsed = JSON.parse(document.getElementById("config-json").value);
  } catch (e) {
    msg.textContent = "Invalid JSON: " + e.message;
    msg.className = "ms-2 text-danger";
    return;
  }
  const res = await fetch(`${API}/api/config`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(parsed),
  });
  if (res.ok) {
    msg.textContent = "Config saved ✔ (applies immediately)";
    msg.className = "ms-2 text-success";
    loadConfig();
  } else {
    const err = await res.json();
    msg.textContent = "Save failed: " + JSON.stringify(err.detail || err);
    msg.className = "ms-2 text-danger";
  }
});

document.getElementById("config-file-input").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${API}/api/config/upload`, { method: "POST", body: formData });
  const msg = document.getElementById("config-msg");
  if (res.ok) {
    msg.textContent = "Uploaded & saved ✔";
    msg.className = "ms-2 text-success";
    loadConfig();
  } else {
    const err = await res.json();
    msg.textContent = "Upload failed: " + JSON.stringify(err.detail || err);
    msg.className = "ms-2 text-danger";
  }
});

// ---------- Resumes ----------
let currentResumeId = null;

async function loadResumes() {
  const res = await fetch(`${API}/api/resumes`);
  const resumes = await res.json();
  const list = document.getElementById("resumes-list");
  list.innerHTML = "";
  if (resumes.length === 0) {
    list.innerHTML = '<div class="text-muted">No resumes uploaded yet.</div>';
    return;
  }
  resumes.forEach((r) => {
    const item = document.createElement("button");
    item.className = "list-group-item list-group-item-action d-flex justify-content-between align-items-center";
    item.innerHTML = `
      <span>
        ${r.is_default ? "⭐ " : ""}<strong>${r.filename}</strong>
        <span class="text-muted small ms-2">v${r.current_version} · ${new Date(r.uploaded_at).toLocaleString()}</span>
      </span>
      <span class="badge bg-secondary">${r.file_type}</span>
    `;
    item.addEventListener("click", () => openResumeDetail(r.id));
    list.appendChild(item);
  });
}
document.getElementById("reload-resumes-btn").addEventListener("click", loadResumes);

document.getElementById("resume-upload-btn").addEventListener("click", async () => {
  const fileInput = document.getElementById("resume-file-input");
  const msg = document.getElementById("resume-upload-msg");
  if (!fileInput.files[0]) {
    msg.textContent = "Choose a file first";
    msg.className = "text-danger";
    return;
  }
  const isDefault = document.getElementById("resume-set-default").checked;
  const formData = new FormData();
  formData.append("file", fileInput.files[0]);
  const res = await fetch(`${API}/api/resumes/upload?is_default=${isDefault}`, {
    method: "POST",
    body: formData,
  });
  if (res.ok) {
    msg.textContent = "Uploaded ✔";
    msg.className = "text-success";
    fileInput.value = "";
    loadResumes();
  } else {
    const err = await res.json();
    msg.textContent = "Upload failed: " + JSON.stringify(err.detail || err);
    msg.className = "text-danger";
  }
});

async function openResumeDetail(id) {
  currentResumeId = id;
  const res = await fetch(`${API}/api/resumes/${id}`);
  const r = await res.json();
  document.getElementById("resume-detail-card").classList.remove("d-none");
  document.getElementById("resume-detail-title").textContent = `${r.filename} (v${r.current_version})`;
  document.getElementById("resume-detail-text").textContent = r.extracted_text || "(no text extracted)";
  document.getElementById("resume-analysis-block").classList.add("d-none");
  loadVersions(id);
}

document.getElementById("resume-detail-close").addEventListener("click", () => {
  document.getElementById("resume-detail-card").classList.add("d-none");
  currentResumeId = null;
});

document.getElementById("resume-set-default-btn").addEventListener("click", async () => {
  if (!currentResumeId) return;
  await fetch(`${API}/api/resumes/${currentResumeId}/default`, { method: "PUT" });
  loadResumes();
  openResumeDetail(currentResumeId);
  loadConfig(); // config.default_resume is synced server-side - refresh to show it
});

document.getElementById("resume-delete-btn").addEventListener("click", async () => {
  if (!currentResumeId) return;
  if (!confirm("Delete this resume and all its versions?")) return;
  await fetch(`${API}/api/resumes/${currentResumeId}`, { method: "DELETE" });
  document.getElementById("resume-detail-card").classList.add("d-none");
  currentResumeId = null;
  loadResumes();
});

document.getElementById("resume-version-input").addEventListener("change", async (e) => {
  if (!currentResumeId || !e.target.files[0]) return;
  const formData = new FormData();
  formData.append("file", e.target.files[0]);
  await fetch(`${API}/api/resumes/${currentResumeId}/versions`, { method: "POST", body: formData });
  loadResumes();
  openResumeDetail(currentResumeId);
});

document.getElementById("resume-analyze-btn").addEventListener("click", async () => {
  if (!currentResumeId) return;
  const btn = document.getElementById("resume-analyze-btn");
  btn.disabled = true;
  btn.textContent = "Analyzing...";
  try {
    const res = await fetch(`${API}/api/resumes/${currentResumeId}/analyze`, { method: "POST" });
    const data = await res.json();
    if (res.ok) {
      document.getElementById("resume-analysis-block").classList.remove("d-none");
      document.getElementById("resume-analysis-text").textContent = `[${data.provider}]\n\n${data.result_text}`;
    } else {
      alert("Analysis failed: " + JSON.stringify(data.detail || data));
    }
  } finally {
    btn.disabled = false;
    btn.textContent = "Analyze with AI";
  }
});

async function loadVersions(resumeId) {
  const res = await fetch(`${API}/api/resumes/${resumeId}/versions`);
  const versions = await res.json();
  const list = document.getElementById("resume-versions-list");
  list.innerHTML = "";
  versions.forEach((v) => {
    const li = document.createElement("li");
    li.className = "list-group-item small";
    li.textContent = `v${v.version} - ${v.filename} - ${new Date(v.created_at).toLocaleString()}`;
    list.appendChild(li);
  });
}

// ---------- Jobs ----------
let currentJobId = null;
let currentJobUrl = "";

async function loadJobs() {
  const minMatch = document.getElementById("min-match-filter").value;
  const url = minMatch ? `${API}/api/jobs?min_match=${encodeURIComponent(minMatch)}` : `${API}/api/jobs`;
  const res = await fetch(url);
  const jobs = await res.json();
  const list = document.getElementById("jobs-list");
  list.innerHTML = "";
  if (jobs.length === 0) {
    list.innerHTML = minMatch
      ? '<div class="text-muted">No jobs with that match % yet - try "Analyze All Unanalyzed" first.</div>'
      : '<div class="text-muted">No jobs added yet.</div>';
    return;
  }
  jobs.forEach((j) => {
    const item = document.createElement("button");
    item.className = "list-group-item list-group-item-action d-flex justify-content-between align-items-center";
    const matchBadge = j.match_percent !== null && j.match_percent !== undefined
      ? `<span class="badge bg-primary ms-2">${j.match_percent}% match</span>`
      : "";
    item.innerHTML = `
      <span>
        <strong>${j.title}</strong> @ ${j.company}
        <span class="text-muted small ms-2">${j.location || ""}</span>
        ${matchBadge}
      </span>
      <span class="badge bg-secondary">${j.status}</span>
    `;
    item.addEventListener("click", () => openJobDetail(j.id));
    list.appendChild(item);
  });
}
document.getElementById("reload-jobs-btn").addEventListener("click", loadJobs);
document.getElementById("min-match-filter").addEventListener("change", loadJobs);

document.getElementById("analyze-unanalyzed-btn").addEventListener("click", async () => {
  const btn = document.getElementById("analyze-unanalyzed-btn");
  const msg = document.getElementById("analyze-unanalyzed-msg");
  btn.disabled = true;
  btn.textContent = "Analyzing...";
  msg.textContent = "";
  try {
    const res = await fetch(`${API}/api/jobs/analyze-unanalyzed`, { method: "POST" });
    const data = await res.json().catch(() => ({}));
    if (res.ok) {
      msg.textContent = `Analyzed ${data.succeeded}/${data.attempted} job(s) (${data.failed} failed).`;
      msg.className = "d-block mb-2 text-success";
      loadJobs();
    } else {
      msg.textContent = "Failed: " + (data.detail || `HTTP ${res.status}`);
      msg.className = "d-block mb-2 text-danger";
    }
  } catch (e) {
    msg.textContent = "Request failed: " + e.message;
    msg.className = "d-block mb-2 text-danger";
  } finally {
    btn.disabled = false;
    btn.textContent = "Analyze All Unanalyzed (AI)";
  }
});

document.getElementById("job-add-btn").addEventListener("click", async () => {
  const msg = document.getElementById("job-add-msg");
  const body = {
    title: document.getElementById("job-title").value,
    company: document.getElementById("job-company").value,
    location: document.getElementById("job-location").value,
    url: document.getElementById("job-url").value,
    salary_text: document.getElementById("job-salary").value,
    description: document.getElementById("job-description").value,
    source: "manual",
  };
  if (!body.title || !body.company || !body.description) {
    msg.textContent = "Title, company, and description are required";
    msg.className = "ms-2 text-danger";
    return;
  }
  const res = await fetch(`${API}/api/jobs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (res.ok) {
    msg.textContent = "Added ✔";
    msg.className = "ms-2 text-success";
    ["job-title", "job-company", "job-location", "job-url", "job-salary", "job-description"].forEach(
      (id) => (document.getElementById(id).value = "")
    );
    loadJobs();
  } else {
    const err = await res.json();
    msg.textContent = "Failed: " + JSON.stringify(err.detail || err);
    msg.className = "ms-2 text-danger";
  }
});

async function openJobDetail(id) {
  currentJobId = id;
  const res = await fetch(`${API}/api/jobs/${id}`);
  const j = await res.json();
  currentJobUrl = j.url || "";
  document.getElementById("job-detail-card").classList.remove("d-none");
  document.getElementById("job-detail-title").textContent = `${j.title} @ ${j.company}`;
  document.getElementById("job-detail-desc").textContent = j.description;
  document.getElementById("job-status-select").value = j.status;
  renderJobAnalysis(j.analysis);

  // Server already extracts an email address from the JD text if present -
  // prefill it as a starting point for "Email HR", always worth double-checking.
  document.getElementById("job-hr-email").value = j.hr_email_guess || "";
  document.getElementById("job-email-apply-msg").textContent = "";
  document.getElementById("job-email-preview-block").classList.add("d-none");

  const statusEl = document.getElementById("job-application-status");
  if (j.application_method === "email" && j.applied_at) {
    statusEl.textContent = `Applied via email to ${j.application_email_to} on ${new Date(j.applied_at).toLocaleString()}`;
  } else if (j.application_method === "website" && j.applied_at) {
    statusEl.textContent = `Applied via website on ${new Date(j.applied_at).toLocaleString()}`;
  } else {
    statusEl.textContent = "";
  }
}

function renderJobAnalysis(analysis) {
  const block = document.getElementById("job-analysis-block");
  if (!analysis) {
    block.classList.add("d-none");
    return;
  }
  block.classList.remove("d-none");
  document.getElementById("job-match-badge").textContent = `${analysis.match_percent}%`;
  document.getElementById("job-match-reason").textContent = analysis.match_reason || "";
  document.getElementById("job-experience").textContent = analysis.experience_required || "-";
  document.getElementById("job-difficulty").textContent = analysis.interview_difficulty || "-";

  const fill = (id, items) => {
    const el = document.getElementById(id);
    el.innerHTML = "";
    (items || []).forEach((s) => {
      const li = document.createElement("li");
      li.textContent = s;
      el.appendChild(li);
    });
  };
  fill("job-skills-list", analysis.extracted_skills);
  fill("job-missing-skills-list", analysis.missing_skills);
  fill("job-learning-list", analysis.learning_suggestions);
}

document.getElementById("job-detail-close").addEventListener("click", () => {
  document.getElementById("job-detail-card").classList.add("d-none");
  currentJobId = null;
});

document.getElementById("job-status-select").addEventListener("change", async (e) => {
  if (!currentJobId) return;
  await fetch(`${API}/api/jobs/${currentJobId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status: e.target.value }),
  });
  loadJobs();
});

document.getElementById("job-apply-btn").addEventListener("click", async () => {
  if (!currentJobId) return;
  const btn = document.getElementById("job-apply-btn");
  btn.disabled = true;
  const originalText = btn.textContent;
  btn.textContent = "Opening...";
  try {
    if (currentJobUrl) {
      let destination = currentJobUrl;
      try {
        const res = await fetch(`${API}/api/jobs/${currentJobId}/resolve-url`);
        if (res.ok) {
          const data = await res.json();
          if (data.url) destination = data.url;
        }
      } catch (e) {
        console.error("resolve-url failed, using original link:", e);
      }
      window.open(destination, "_blank", "noopener");
    } else {
      alert("This job has no URL saved - marking it as applied without opening a page.");
    }
    await fetch(`${API}/api/jobs/${currentJobId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: "applied", application_method: "website" }),
    });
    document.getElementById("job-status-select").value = "applied";
    openJobDetail(currentJobId); // refresh the application-status line
    loadJobs();
  } finally {
    btn.disabled = false;
    btn.textContent = originalText;
  }
});

document.getElementById("job-email-preview-btn").addEventListener("click", async () => {
  if (!currentJobId) return;
  const msg = document.getElementById("job-email-apply-msg");
  const btn = document.getElementById("job-email-preview-btn");
  btn.disabled = true;
  btn.textContent = "Loading preview...";
  try {
    const res = await fetch(`${API}/api/jobs/${currentJobId}/apply-email/preview`, { method: "POST" });
    const data = await res.json().catch(() => ({}));
    if (res.ok) {
      document.getElementById("job-email-subject").value = data.subject || "";
      document.getElementById("job-email-body").value = data.html_body || "";
      if (data.hr_email_guess && !document.getElementById("job-hr-email").value) {
        document.getElementById("job-hr-email").value = data.hr_email_guess;
      }
      document.getElementById("job-email-preview-block").classList.remove("d-none");
      msg.textContent = "Review below, edit if needed, then Confirm & Send.";
      msg.className = "ms-2 text-muted";
    } else {
      msg.textContent = "Failed: " + (data.detail || `HTTP ${res.status}`);
      msg.className = "ms-2 text-danger";
    }
  } catch (e) {
    msg.textContent = "Request failed: " + e.message;
    msg.className = "ms-2 text-danger";
  } finally {
    btn.disabled = false;
    btn.textContent = "Preview Email";
  }
});

document.getElementById("job-email-cancel-btn").addEventListener("click", () => {
  document.getElementById("job-email-preview-block").classList.add("d-none");
  document.getElementById("job-email-apply-msg").textContent = "";
});

document.getElementById("job-email-confirm-send-btn").addEventListener("click", async () => {
  if (!currentJobId) return;
  const hrEmail = document.getElementById("job-hr-email").value.trim();
  const msg = document.getElementById("job-email-apply-msg");
  if (!hrEmail) {
    msg.textContent = "Enter an HR/recruiter email first";
    msg.className = "ms-2 text-danger";
    return;
  }
  const btn = document.getElementById("job-email-confirm-send-btn");
  btn.disabled = true;
  btn.textContent = "Sending...";
  try {
    const res = await fetch(`${API}/api/jobs/${currentJobId}/apply-email`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        hr_email: hrEmail,
        subject: document.getElementById("job-email-subject").value,
        html_body: document.getElementById("job-email-body").value,
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (res.ok && data.sent) {
      msg.textContent = `Sent to ${data.recipient} ✔`;
      msg.className = "ms-2 text-success";
      document.getElementById("job-email-preview-block").classList.add("d-none");
      openJobDetail(currentJobId);
      loadJobs();
    } else {
      msg.textContent = "Failed: " + (data.detail || data.reason || `HTTP ${res.status}`);
      msg.className = "ms-2 text-danger";
    }
  } catch (e) {
    msg.textContent = "Request failed: " + e.message;
    msg.className = "ms-2 text-danger";
  } finally {
    btn.disabled = false;
    btn.textContent = "Confirm & Send";
  }
});

document.getElementById("job-delete-btn").addEventListener("click", async () => {
  if (!currentJobId) return;
  if (!confirm("Delete this job?")) return;
  await fetch(`${API}/api/jobs/${currentJobId}`, { method: "DELETE" });
  document.getElementById("job-detail-card").classList.add("d-none");
  currentJobId = null;
  loadJobs();
});

document.getElementById("job-analyze-btn").addEventListener("click", async () => {
  if (!currentJobId) return;
  const btn = document.getElementById("job-analyze-btn");
  btn.disabled = true;
  btn.textContent = "Analyzing...";
  try {
    const res = await fetch(`${API}/api/jobs/${currentJobId}/analyze`, { method: "POST" });
    const data = await res.json();
    if (res.ok) {
      renderJobAnalysis(data.analysis);
    } else {
      alert("Analysis failed: " + JSON.stringify(data.detail || data));
    }
  } finally {
    btn.disabled = false;
    btn.textContent = "Analyze / ATS Match";
  }
});

// ---------- Email notifications ----------
async function loadEmailStatus() {
  const el = document.getElementById("email-status-text");
  try {
    const res = await fetch(`${API}/api/notifications/status`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const providerLabels = { brevo: "Brevo (HTTP API)", sendgrid: "SendGrid (HTTP API)", smtp: "SMTP" };
    const providerLabel = providerLabels[data.provider] || data.provider;
    el.textContent = data.configured
      ? `Configured ✔ (via ${providerLabel})`
      : `Not configured (provider: ${providerLabel} - set the matching vars in .env)`;
    el.className = data.configured ? "text-success" : "text-muted";
  } catch (e) {
    el.textContent = "Could not check status: " + e.message;
    el.className = "text-danger";
  }
}

document.getElementById("send-test-email-btn").addEventListener("click", async () => {
  const msg = document.getElementById("email-test-msg");
  msg.textContent = "Sending...";
  msg.className = "ms-2 text-muted";
  try {
    const res = await fetch(`${API}/api/notifications/test-email`, { method: "POST" });
    const data = await res.json().catch(() => ({}));
    if (res.ok) {
      msg.textContent = `Sent to ${data.recipient} ✔`;
      msg.className = "ms-2 text-success";
    } else {
      msg.textContent = "Failed: " + (data.detail || `HTTP ${res.status}`);
      msg.className = "ms-2 text-danger";
    }
  } catch (e) {
    msg.textContent = "Request failed: " + e.message;
    msg.className = "ms-2 text-danger";
  }
});

// ---------- Job search ----------
document.getElementById("run-search-btn").addEventListener("click", async () => {
  const btn = document.getElementById("run-search-btn");
  const msg = document.getElementById("search-msg");
  btn.disabled = true;
  btn.textContent = "Searching...";
  msg.textContent = "";
  try {
    const res = await fetch(`${API}/api/jobsearch/run`, { method: "POST" });
    const data = await res.json().catch(() => ({}));
    if (res.ok) {
      msg.textContent =
        `Found ${data.fetched_total}, added ${data.new_jobs_added} new. ` +
        `Skipped: ${data.skipped_duplicate} duplicate, ${data.skipped_irrelevant ?? 0} not relevant enough ` +
        `(needed ${data.min_keyword_hits_required ?? "?"} keyword matches), ` +
        `${data.skipped_language ?? 0} wrong language (target: ${data.target_language ?? "English"}), ` +
        `${data.skipped_location ?? 0} wrong location, ${data.skipped_job_type ?? 0} wrong job type, ` +
        `${data.skipped_experience ?? 0} too senior, ${data.skipped_stale ?? 0} too old, ` +
        `${data.skipped_filtered} filtered (blacklist/exclude).`;
      if (data.source_errors && Object.keys(data.source_errors).length) {
        msg.textContent += " Source errors: " + JSON.stringify(data.source_errors);
      }
      msg.className = "ms-2 text-success";
      loadJobs();
    } else {
      msg.textContent = "Search failed: " + (data.detail ? JSON.stringify(data.detail) : `HTTP ${res.status}`);
      msg.className = "ms-2 text-danger";
    }
  } catch (e) {
    msg.textContent = "Request failed: " + e.message;
    msg.className = "ms-2 text-danger";
  } finally {
    btn.disabled = false;
    btn.textContent = "Search Jobs Now";
  }
});

document.getElementById("clear-jobs-btn").addEventListener("click", async () => {
  if (!confirm('Delete all jobs with status "New"? Saved/Applied/Interview/Offer jobs are kept.')) return;
  const msg = document.getElementById("search-msg");
  try {
    const res = await fetch(`${API}/api/jobs/clear?status=new`, { method: "DELETE" });
    const data = await res.json().catch(() => ({}));
    if (res.ok) {
      msg.textContent = `Cleared ${data.deleted} job(s).`;
      msg.className = "ms-2 text-success";
      loadJobs();
    } else {
      msg.textContent = "Clear failed: " + (data.detail || `HTTP ${res.status}`);
      msg.className = "ms-2 text-danger";
    }
  } catch (e) {
    msg.textContent = "Request failed: " + e.message;
    msg.className = "ms-2 text-danger";
  }
});

async function loadFollowupsDue() {
  try {
    const res = await fetch(`${API}/api/notifications/followups/due`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const jobs = await res.json();
    const card = document.getElementById("followups-card");
    const list = document.getElementById("followups-list");
    if (!jobs.length) {
      card.classList.add("d-none");
      return;
    }
    card.classList.remove("d-none");
    list.innerHTML = "";
    jobs.forEach((j) => {
      const row = document.createElement("div");
      row.className = "d-flex justify-content-between align-items-center border-bottom py-1";
      row.innerHTML = `
        <span><strong>${j.title}</strong> @ ${j.company}
          <span class="text-muted small ms-2">applied ${j.applied_at ? new Date(j.applied_at).toLocaleDateString() : ""}</span>
        </span>
        <button class="btn btn-sm btn-outline-primary">Send Reminder</button>
      `;
      row.querySelector("button").addEventListener("click", async (e) => {
        e.target.disabled = true;
        try {
          const res = await fetch(`${API}/api/notifications/followups/${j.id}/send`, { method: "POST" });
          const data = await res.json().catch(() => ({}));
          e.target.textContent = data.sent ? "Sent ✔" : "Failed: " + (data.reason || `HTTP ${res.status}`);
          if (data.sent) loadFollowupsDue();
        } catch (err) {
          e.target.textContent = "Error: " + err.message;
        }
      });
      list.appendChild(row);
    });
  } catch (e) {
    console.error("loadFollowupsDue failed:", e);
    // Non-fatal: leave the follow-ups card hidden rather than breaking the rest of the page.
  }
}

// ---------- Cover Letters ----------
async function loadCoverLetters() {
  try {
    const res = await fetch(`${API}/api/cover-letters`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const items = await res.json();
    const list = document.getElementById("cl-list");
    list.innerHTML = "";
    if (!items.length) {
      list.innerHTML = '<div class="text-muted">No cover letters uploaded yet.</div>';
      return;
    }
    items.forEach((c) => {
      const row = document.createElement("div");
      row.className = "list-group-item d-flex justify-content-between align-items-center";
      row.innerHTML = `
        <span>${c.is_default ? "⭐ " : ""}<strong>${c.filename}</strong>
          <span class="text-muted small ms-2">${new Date(c.uploaded_at).toLocaleString()}</span>
        </span>
        <span>
          <button class="btn btn-sm btn-outline-primary me-1" data-action="default">Set Default</button>
          <button class="btn btn-sm btn-outline-danger" data-action="delete">Delete</button>
        </span>
      `;
      row.querySelector('[data-action="default"]').addEventListener("click", async () => {
        await fetch(`${API}/api/cover-letters/${c.id}/default`, { method: "PUT" });
        loadCoverLetters();
        loadConfig(); // config.default_cover_letter is synced server-side - refresh to show it
      });
      row.querySelector('[data-action="delete"]').addEventListener("click", async () => {
        if (!confirm("Delete this cover letter?")) return;
        await fetch(`${API}/api/cover-letters/${c.id}`, { method: "DELETE" });
        loadCoverLetters();
      });
      list.appendChild(row);
    });
  } catch (e) {
    console.error("loadCoverLetters failed:", e);
  }
}

document.getElementById("cl-upload-btn").addEventListener("click", async () => {
  const fileInput = document.getElementById("cl-file-input");
  const msg = document.getElementById("cl-upload-msg");
  if (!fileInput.files[0]) {
    msg.textContent = "Choose a file first";
    msg.className = "text-danger";
    return;
  }
  const isDefault = document.getElementById("cl-set-default").checked;
  const formData = new FormData();
  formData.append("file", fileInput.files[0]);
  try {
    const res = await fetch(`${API}/api/cover-letters/upload?is_default=${isDefault}`, {
      method: "POST",
      body: formData,
    });
    const data = await res.json().catch(() => ({}));
    if (res.ok) {
      msg.textContent = "Uploaded ✔";
      msg.className = "text-success";
      fileInput.value = "";
      loadCoverLetters();
    } else {
      msg.textContent = "Upload failed: " + (data.detail || `HTTP ${res.status}`);
      msg.className = "text-danger";
    }
  } catch (e) {
    msg.textContent = "Request failed: " + e.message;
    msg.className = "text-danger";
  }
});

// ---------- Version badge ----------
async function loadVersion() {
  try {
    const res = await fetch(`${API}/api/version`);
    const data = await res.json();
    document.getElementById("version-badge").textContent = data.version || "unknown";
  } catch (e) {
    document.getElementById("version-badge").textContent = "version unknown";
  }
}

// ---------- Job language preference ----------
async function loadLanguagePref() {
  try {
    const res = await fetch(`${API}/api/config`);
    const cfg = await res.json();
    document.getElementById("pref-language").value = cfg.language || "English";
  } catch (e) {
    console.error("loadLanguagePref failed:", e);
  }
}

document.getElementById("pref-language").addEventListener("change", async (e) => {
  const msg = document.getElementById("pref-language-msg");
  try {
    const res = await fetch(`${API}/api/config`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ language: e.target.value }),
    });
    if (res.ok) {
      msg.textContent = "Saved ✔";
      msg.className = "ms-2 text-success";
      loadConfig();
    } else {
      msg.textContent = "Failed to save";
      msg.className = "ms-2 text-danger";
    }
  } catch (err) {
    msg.textContent = "Request failed: " + err.message;
    msg.className = "ms-2 text-danger";
  }
});

// ---------- Init ----------
loadSettings();
loadConfig();
loadResumes();
loadJobs();
loadEmailStatus();
loadFollowupsDue();
loadCoverLetters();
loadVersion();
loadLanguagePref();
