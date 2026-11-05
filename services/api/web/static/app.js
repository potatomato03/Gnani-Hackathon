"use strict";
/* ARDAI doctor app (design by Rakshit, 5 Nov; wired to the real API in runbook D-129). Plain JavaScript, no build step.
   All network calls are in `live`. All field-name guessing is in `adapt`.
   If static/mock.js is loaded it replaces `live` with in-memory demo data. */
const API = "/api/v1";
const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;

/* ---------------- helpers ---------------- */
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const wait = ms => new Promise(r => setTimeout(r, ms));
const initials = n => String(n || "?").replace(/^Dr\.?\s+/i, "").split(/\s+/).map(w => w[0]).slice(0, 2).join("").toUpperCase();
const first = n => String(n || "").split(" ")[0];
const fmtDate = iso => iso ? new Date(String(iso).slice(0, 10) + "T12:00:00+05:30").toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" }) : "";
const fmtTime = iso => new Date(iso).toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit", timeZone: "Asia/Kolkata" });
const fmtWhen = iso => iso ? `${fmtDate(iso)}, ${fmtTime(iso)}` : "";
const cap = s => s ? s[0].toUpperCase() + s.slice(1) : "";
const store = { get(k) { try { return localStorage.getItem(k); } catch (_) { return null; } }, set(k, v) { try { localStorage.setItem(k, v); } catch (_) {} } };
const sized = (svg, n) => svg.replace("<svg", `<svg width="${n}" height="${n}"`);
const ICON = {
  mic: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/></svg>',
  pdf: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M12 12v6M9.5 15.5 12 18l2.5-2.5"/></svg>',
  json: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M8 4c-2 0-2 1.5-2 3s0 3-2 3c2 0 2 1.5 2 3s0 3 2 3M16 4c2 0 2 1.5 2 3s0 3 2 3c-2 0-2 1.5-2 3s0 3-2 3"/></svg>',
  check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m5 12 5 5 9-10"/></svg>',
  x: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" aria-hidden="true"><path d="M7 7l10 10M17 7 7 17"/></svg>',
  chev: '<svg class="chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>',
  alert: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M12 9v4M12 17h.01"/><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/></svg>',
  upload: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 16V4M7 9l5-5 5 5M5 20h14"/></svg>',
  type: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><path d="M4 7V5h16v2M12 5v14M9 19h6"/></svg>',
  pause: '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><rect x="6" y="5" width="4" height="14" rx="1"/><rect x="14" y="5" width="4" height="14" rx="1"/></svg>',
  play: '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M8 5v14l11-7z"/></svg>',
  plus: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>',
  book: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2z"/><path d="M4 19V5"/></svg>',
  chat: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12a8 8 0 0 1-12 7l-5 1 1-5a8 8 0 1 1 16-3Z"/></svg>',
  wa: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2a10 10 0 0 0-8.6 15.1L2 22l5-1.3A10 10 0 1 0 12 2Zm0 18.2c-1.5 0-3-.4-4.3-1.2l-.3-.2-3 .8.8-2.9-.2-.3A8.2 8.2 0 1 1 12 20.2Z"/></svg>'
};
let toastTimer;
function toast(msg) { const t = $("#toast"); t.textContent = msg; t.classList.add("show"); clearTimeout(toastTimer); toastTimer = setTimeout(() => t.classList.remove("show"), 2800); }
class ApiError extends Error { constructor(code, message, status) { super(message); this.code = code; this.status = status; } }

/* =================================================================
   LIVE API: routes from DASHBOARD_AND_API.md (5 Nov)
   ================================================================= */
let api = null, csrf = null, session = null;
const toLogin = expired => location.replace(window.VoiceRxMock ? "login.html" : "/" + (expired ? "?expired=1" : ""));
async function http(method, path, body, extra = {}) {
  const headers = { Accept: "application/json", ...(extra.headers || {}) };
  if (method !== "GET" && csrf) headers["X-CSRF-Token"] = csrf;
  let payload = body;
  if (body !== undefined && !(body instanceof Blob)) { headers["Content-Type"] = "application/json"; payload = JSON.stringify(body); }
  const res = await fetch(API + path, { method, headers, body: payload, credentials: "same-origin" });
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    if (res.status === 401) toLogin(true);
    const fallback = { 403: "You don't have access to this.", 413: "That file is too big.", 429: "Too many requests. Wait a moment and try again." }[res.status] || "Something went wrong. Try again.";
    throw new ApiError(data.error?.code || "http_" + res.status, data.error?.message || fallback, res.status);
  }
  return data;
}
const PART_BYTES = 3 * 1024 * 1024;
const q = o => { const s = new URLSearchParams(Object.entries(o).filter(([, v]) => v !== undefined && v !== null && v !== "")).toString(); return s ? "?" + s : ""; };
const live = {
  me: () => http("GET", "/me"),
  logout: () => http("POST", "/auth/logout"),
  hospitals: () => http("GET", "/workspace/hospitals"),
  doctors: id => http("GET", `/workspace/hospitals/${id}/doctors`),
  addDoctor: (id, body) => http("POST", `/workspace/hospitals/${id}/doctors`, body),
  select: body => http("POST", "/workspace/select", body),
  patients: (list, s, doctor_id) => http("GET", "/patients" + q({ list, q: s, doctor_id })),
  // The form speaks in words; the API wants codes ("hindi" -> "hi-IN", "female" -> "F", "none" -> "nka").
  register: body => http("POST", "/patients", { ...body, language: LANG_CODE[body.language] || body.language,
    sex: { female: "F", male: "M" }[body.sex] || body.sex, allergy_status: body.allergy_status === "none" ? "nka" : body.allergy_status }),
  patient: id => http("GET", `/patients/${id}`),
  journey: id => http("GET", `/patients/${id}/journey`).then(adapt.journey).catch(() => null),
  encounter: id => http("GET", `/encounters/${id}`),
  createEncounter: pid => http("POST", `/patients/${pid}/encounters`, {}),
  typedSource: (enc, text, language) => http("POST", `/encounters/${enc}/sources`, { kind: "typed", language, text }),
  async audioSource(enc, blob, language, onProgress) {
    const type = (blob.type || "audio/webm").split(";")[0];
    if (blob.size <= PART_BYTES) return http("POST", `/encounters/${enc}/sources/audio?language=${language}`, blob, { headers: { "Content-Type": type, "X-Recording-Consent": "patient-agreed" } });
    const u = await http("POST", `/encounters/${enc}/audio-uploads`, { size: blob.size, media_type: type, language, recording_consent: true });
    const id = u.upload_id ?? u.id, step = u.part_bytes || PART_BYTES, parts = Math.ceil(blob.size / step);
    for (let i = 0; i < parts; i++) {
      await http("PUT", `/audio-uploads/${id}/parts/${i}`, blob.slice(i * step, (i + 1) * step, "application/octet-stream"), { headers: { "Content-Type": "application/octet-stream" } });
      onProgress?.((i + 1) / parts);
    }
    return http("POST", `/audio-uploads/${id}/complete`, {});
  },
  // A recording sent in pieces while the visit goes on, so its transcript is ready when it stops (D-131).
  liveBegin: (enc, type, language) => http("POST", `/encounters/${enc}/live-recordings`, { media_type: type, language, recording_consent: true }),
  livePart: (id, part, blob, final) => http("PUT", `/live-recordings/${id}/parts/${part}${final ? "?final=true" : ""}`, blob, { headers: { "Content-Type": "application/octet-stream" } }),
  liveComplete: id => http("POST", `/live-recordings/${id}/complete`, {}),
  startRun: (enc, src) => http("POST", `/encounters/${enc}/runs`, { source_id: src.source_id ?? src.id, source_version: src.source_version ?? src.version }).then(adapt.run),
  run: id => http("GET", `/runs/${id}`).then(adapt.run),
  retry: id => http("POST", `/runs/${id}/retry`).then(adapt.run),
  report: (enc, version) => http("GET", `/encounters/${enc}/report` + q({ version })),
  resolve: (enc, r, resolutions) => http("POST", `/encounters/${enc}/resolutions`, { expected_version: r.version, expected_content_hash: r.content_hash, resolutions }),
  approve: (enc, r) => http("POST", `/encounters/${enc}/approvals`, { expected_version: r.version, expected_content_hash: r.content_hash }),
  artifacts: enc => http("GET", `/encounters/${enc}/artifacts`).then(d => items(d).map(adapt.artifact)),
  deliveries: enc => http("GET", `/encounters/${enc}/clinic-reports`).then(d => items(d).map(adapt.delivery)),
  retryDelivery: enc => http("POST", `/encounters/${enc}/clinic-reports/retry`, {}),
  shortlist: enc => http("GET", `/encounters/${enc}/shortlist`),
  catalog: s => http("GET", "/catalog/search" + q({ q: s })),
  knowledge: (question, encounter_id) => http("POST", "/knowledge/search", { question, encounter_id }),
  tasks: () => http("GET", "/followup/tasks").then(d => ({ items: items(d).map(adapt.task) })),
  followup: enc => http("GET", `/encounters/${enc}/followup`).then(adapt.followup),
  followStart: enc => http("POST", `/encounters/${enc}/followup`, {}).then(adapt.followup),
  followSend: (enc, body) => http("POST", `/encounters/${enc}/followup/messages`, body).then(adapt.followup),
  followMemory: enc => http("GET", `/encounters/${enc}/followup/memory`).then(d => ({ ...d, documents: (d.documents || []).map(adapt.upload) })),
  followAdvance: enc => http("POST", `/encounters/${enc}/followup/advance`, {}),
  followDoc: (enc, file) => http("POST", `/encounters/${enc}/followup/documents`, file, { headers: { "Content-Type": file.type || "application/pdf" } }),
  taskDone: (enc, id) => http("POST", `/encounters/${enc}/followup/tasks/${id}/done`, {}),
  reviewUpload: id => http("POST", `/patient-uploads/${id}/review`, {}),
  uploadUrl: id => `${API}/patient-uploads/${id}/download`,
  previewUrl: (enc, version) => `${API}/encounters/${enc}/preview.pdf${q({ version })}`,
  downloadUrl: id => `${API}/artifacts/${id}/download`,
  pharmacy: () => http("GET", "/pharmacy/stock"),
  uploadStock: (filename, csv) => http("POST", "/pharmacy/stock", { filename, csv })
};

/* =================================================================
   Adapters: the one place that knows backend field names.
   Fields marked "assumed" in DESIGN.md are resolved here.
   ================================================================= */
const items = d => d?.items || d?.patients || d?.hospitals || d?.doctors || d?.tasks || d?.jobs || d?.results || d?.artifacts || (Array.isArray(d) ? d : []);
const LANG_CODE = { english: "en-IN", hindi: "hi-IN", tamil: "ta-IN", telugu: "te-IN", gujarati: "gu-IN" };
const LANG_WORD = Object.fromEntries(Object.entries(LANG_CODE).map(([w, c]) => [c, w]));
const TASK_TEXT = { callback: "Call the patient back", urgent: "Urgent: patient reported a problem", question: "Patient question to answer", report_review: "Review a report the patient sent" };
const ART_KIND = { report_pdf: "pdf", fhir_bundles: "fhir" };
const DELIVERY_KIND = { report_pdf: "pdf", prescription_voice: "voice", voice_option: "voice_option" };
const adapt = {
  // /me and /workspace/select: the actor is the doctor once a doctor is chosen; the shared admin has role "admin".
  session(s) {
    const w = s.workspace || {}, role = s.scope?.role;
    const doctor = w.doctor || (role === "doctor" && s.actor ? { id: s.actor.id, display_name: s.actor.display_name, specialty: s.actor.specialty } : null);
    return { ...s, admin: !!(w.admin ?? w.is_admin ?? s.workspace_admin), hospital: w.hospital || (s.scope?.organisation_id ? { id: s.scope.organisation_id, name: s.scope.organisation_name } : null), doctor };
  },
  doctor: d => ({ ...d, name: d.display_name || d.name, specialty: d.specialty ? cap(String(d.specialty).replaceAll("_", " ")) : "" }),
  patient(p) {
    const list = Array.isArray(p.allergies) ? p.allergies : p.allergies?.items || [];
    const status = p.allergies?.status || { nka: "none", known: "known", unknown: "unknown" }[p.allergy_status] || (list.length ? "known" : "unknown");
    // Consents are stored as a list; registration asked about recording, so its absence means "not agreed".
    const consents = Array.isArray(p.consents) ? { ai: p.consents.includes("ai_processing"), recording: p.consents.includes("recording"), whatsapp: p.consents.includes("followup_whatsapp") } : (p.consents || p.consent || {});
    return { ...p, age: p.age ?? p.age_years ?? (p.birth_year ? new Date().getFullYear() - p.birth_year : null), language: p.language || LANG_WORD[p.language_pref] || null,
      allergies: { status, items: list }, consents, last_visit_date: p.last_visit_date || p.last_visit, visit_state: p.visit_state || p.open_state, blocking_count: p.blocking_count ?? p.open_blocking };
  },
  encounter: e => ({ ...e, date: e.date || e.visit_date, diagnosis: e.diagnosis || (e.diagnoses || []).join(", "), complaint: e.complaint || (e.complaints || []).join(", ") }),
  run: r => r && ({ ...r, id: r.id ?? r.run_id, error: typeof r.error === "string" ? { message: r.error } : r.error }),
  artifact: a => ({ ...a, kind: ART_KIND[a.kind] || a.kind }),
  delivery: j => ({ ...j, kind: DELIVERY_KIND[j.kind] || j.kind, status: j.status || j.state }),
  task: t => ({ ...t, title: t.title || TASK_TEXT[t.kind] || cap(String(t.kind || "task").replaceAll("_", " ")), detail: t.detail || t.note }),
  upload: u => ({ ...u, filename: u.filename || `${u.mime === "application/pdf" ? "PDF report" : "Report image"}${u.received_at ? ", " + fmtDate(u.received_at) : ""}`, reviewed: u.reviewed ?? !!u.reviewed_at }),
  journey: j => j && ({ ...j, questions: (j.questions || []).map(x => ({ ...x, text: x.text || x.question })), uploads: (j.uploads || []).map(adapt.upload) }),
  followup(d) {
    const c = d.conversation;
    return { ...d, status: c ? "active" : "inactive", simulated: c?.plan?.channel === "simulated" && !c.stopped,
      status_label: c ? `Approved visit, ${c.plan?.channel === "simulated" ? "local simulator, nothing is sent" : "WhatsApp"}${c.stopped ? ", stopped by the patient" : ""}` : "",
      messages: (c?.messages || []).map(m => ({ ...m, direction: m.direction || (m.sender === "patient" ? "in" : "out"), buttons: (m.buttons || []).map(b => ({ id: b.id, title: b.title || b.label })) })),
      reason: d.reason };
  },
  report(r) {
    const sections = r.report?.sections || {};
    const groups = (r.report_groups || []).map(g => {
      if (Array.isArray(g)) {
        const [heading, secs] = g;
        return { key: secs[0], heading, lines: secs.flatMap(sec => (sections[sec] || []).map((l, i) => ({ ref: `${sec}:${i}`, text: l.text ?? l, cites: l.cites || [] }))) };
      }
      if (g.lines) return g;
      const lines = (g.sections || []).flatMap(sec => (Array.isArray(r.report?.[sec]) ? r.report[sec] : []).map((l, i) => ({ ref: `${sec}:${i}`, text: l.text ?? l, cites: l.cites || [] })));
      return { key: g.key || g.heading, heading: g.heading || g.title, lines };
    }).filter(g => g.lines.length);
    const meds = (r.medication_views || []).map(adapt.med), byId = Object.fromEntries(meds.map(m => [m.id, m]));
    const header = r.report?.header || {};
    return { ...r, report_groups: groups, issue_views: (r.issue_views || []).map(i => adapt.issue(i, byId)), findings: r.findings || {},
      medication_views: meds.filter(m => m.row || !("row" in m)), all_meds: byId,
      date: r.date || header.visit_date || r.visit_date, clinician: r.clinician || header.doctor_name,
      approval: r.approval ? { ...r.approval, approved_by: r.approval.approved_by || r.approval.approver_name } : null,
      artifacts: (r.artifacts || []).map(adapt.artifact) };
  },
  // Our schedules: grid {m,a,e,n}, frequency {times, period}, as_needed {max_per_day}, taper. The screens use kinds.
  med(m) {
    const s = m.schedule, n = v => v && v !== "-" && Number(v) !== 0 ? v : 0;
    const schedule = !s ? null : s.kind ? s : s.type === "grid" ? { kind: "slots", slots: ["m", "a", "e", "n"].map(k => n(s[k])) }
      : s.type === "frequency" ? (s.period === "day" ? { kind: "frequency", times_per_day: s.times } : { kind: "weekly", times: s.times })
      : s.type === "as_needed" ? { kind: "as_needed", max_per_day: s.max_per_day } : s.type === "taper" ? { kind: "taper" } : null;
    return { ...m, raw_schedule: s, schedule, label: m.label || m.row?.label || m.product_label || m.name || m.spoken_name || m.spoken_as,
      composition: m.composition || m.product_composition || "", form: m.form || m.product_form, filled: m.filled || {},
      unresolved: Array.isArray(m.unresolved) ? (m.unresolved.length ? m.unresolved : null) : m.unresolved, display: m.display || m.row?.detail };
  },
  // Our checks name their corrections ("acknowledge", "choose_product"); each becomes a button here.
  issue(i, meds) {
    const med = meds[i.target], acts = [];
    for (const a of i.actions || []) {
      if (typeof a !== "string") { if (a.resolutions || a.edit || a.find || a.line) acts.push(a); continue; }
      const one = (label, value = {}, target = i.target) => acts.push({ label, resolutions: [{ action: a, target, value }] });
      if (a === "choose_product") {
        (med?.suggestions || []).forEach(x => acts.push({ label: `Use ${x.label}${x.stock ? ", " + STOCK_TEXT[x.stock.status].toLowerCase() : ""}`,
          resolutions: [{ action: a, target: i.target, value: { product_id: x.product_id }, reason: `Heard "${med.spoken_name}"; meant ${x.label}.` },
            ...(x.standard || []).map(p => ({ action: p.action, target: i.target, value: p.value, reason: p.reason }))] }));
        if (!(med?.suggestions || []).length) (med?.candidates || []).filter(c => c.id !== med.product_id).forEach(c => acts.push({ label: `Use ${c.label}`, resolutions: [{ action: a, target: i.target, value: { product_id: c.id } }] }));
        acts.push({ label: "Find another medicine", find: i.target });
      } else if (["set_dose", "set_timing", "set_food", "set_duration"].includes(a)) { if (!acts.some(x => x.edit)) acts.push({ label: "Edit the medicine", edit: i.target }); }
      else if (a === "acknowledge") one("Accept as it is", { code: i.code });
      else if (a === "confirm_interpretation") one("Correct as written", { code: i.code });
      else if (a === "confirm_order") one("Confirm");
      else if (a === "remove_medicine") one("Remove medicine");
      else if (a === "dismiss_item") one("Rule it out");
      else if (a === "remove_line") one("Remove sentence", {}, i.lines?.[0] || i.target);
      else if (a === "edit_line") acts.push({ label: "Edit sentence", line: i.lines?.[0] || i.target });
    }
    return { ...i, id: i.id || i.uid, severity: i.severity === "warning" ? "warn" : i.severity, actions: acts };
  }
};

/* Hospital pharmacy stock (runbook D-126): a label and a one-click swap, never an automatic change. */
const STOCK_TEXT = { in_stock: "In stock", low: "Low stock", out: "Out of stock", not_stocked: "Not stocked" };
const STOCK_CLS = { in_stock: "ok", low: "warn", out: "risk", not_stocked: "muted" };
const stockChip = st => st ? `<span class="chip ${STOCK_CLS[st.status]}" title="Hospital pharmacy">Pharmacy: ${STOCK_TEXT[st.status]}${["in_stock", "low"].includes(st.status) ? ` (${esc(st.quantity)})` : ""}</span>` : "";

/* =================================================================
   Display preferences (per viewer, browser storage only)
   ================================================================= */
const prefs = { text: store.get("vrx-text") || "standard", motion: store.get("vrx-motion") || (reduce ? "off" : "on") };
function applyPrefs() {
  document.documentElement.dataset.text = prefs.text;
  document.documentElement.dataset.motion = prefs.motion;
  $$(".pills[data-pref]").forEach(g => g.querySelectorAll("button").forEach(b => b.setAttribute("aria-pressed", String(prefs[g.dataset.pref] === b.dataset.v))));
}
$$(".pills[data-pref]").forEach(g => g.addEventListener("click", e => {
  const b = e.target.closest("button[data-v]"); if (!b) return;
  prefs[g.dataset.pref] = b.dataset.v; store.set("vrx-" + g.dataset.pref, b.dataset.v); applyPrefs();
}));
document.addEventListener("click", e => { const m = $("#displayMenu"); if (m.open && !m.contains(e.target)) m.open = false; });
document.addEventListener("keydown", e => { if (e.key === "Escape" && $("#displayMenu").open) { $("#displayMenu").open = false; $("#displayMenu summary").focus(); } });
applyPrefs();

/* =================================================================
   Router
   ================================================================= */
const state = { tab: "today", q: "", rows: [], selected: null, patient: null, visit: null, poll: 0, searchT: 0, hospital: null, tasks: [], guard: "" };
const view = () => $("#view");
const stopPolling = () => clearTimeout(state.poll);
function swap() { const v = view(); if (reduce) return; v.classList.remove("swap"); void v.offsetWidth; v.classList.add("swap"); }
function showError(msg, retry) {
  view().innerHTML = `<div class="page narrow"><div class="panel error-box" role="alert"><p>${esc(msg)}</p><button class="btn btn-line" id="retryView">Try again</button></div></div>`;
  $("#retryView").onclick = retry;
}
async function route() {
  if (state.visit?.phase === "recording") {
    if (!confirm("Stop and discard the recording in progress?")) { history.replaceState(null, "", state.guard); return; }
    stopMic(); state.visit.phase = "idle";
  }
  state.guard = location.hash;
  stopPolling();
  const [, name = "", id] = location.hash.split("/");
  if (session.admin && !session.doctor && name !== "workspace") { location.hash = "#/workspace"; return; }
  $$(".nav a").forEach(a => { const on = a.dataset.nav === (name === "followup" ? "followups" : name === "encounters" || name === "" ? "patients" : name); on ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current"); });
  try {
    if (name === "workspace") return await renderWorkspace();
    if (name === "register") return await renderRegister();
    if (name === "followups") return await renderTasks();
    if (name === "pharmacy") return await renderPharmacy();
    if (name === "followup" && id) return await renderFollowup(id);
    if (name === "encounters" && id) { const e = await api.encounter(id); return await openPatient(e.patient?.id ?? e.patient_id, id); }
    await openPatient(name === "patients" ? id : null);
  } catch (x) { if (x.status !== 401) showError(x.message, route); }
}
window.addEventListener("hashchange", route);
function renderShell() {
  const d = session.doctor?.display_name || session.doctor?.name;
  $("#docName").textContent = d || "Choose a doctor";
  $("#docOrg").textContent = session.hospital?.name || "No hospital selected";
  $("#docInit").textContent = initials(d || session.hospital?.name);
  const caps = session.capabilities || {};
  $("#navPharmacy").hidden = !caps.pharmacy;
  $('[data-nav="register"]').hidden = caps.register === false;
}
$("#signOut").addEventListener("click", async () => { try { await api.logout(); } catch (_) {} toLogin(); });
$("#search").addEventListener("input", e => {
  clearTimeout(state.searchT);
  state.searchT = setTimeout(() => { state.q = e.target.value.trim(); $("#plist") ? loadList() : (location.hash = "#/patients"); }, 250);
});
async function loadTasks() {
  try {
    state.tasks = items(await api.tasks()).filter(t => t.status !== "done");
    const c = $("#taskCount"); c.textContent = state.tasks.length; c.hidden = !state.tasks.length;
  } catch (_) { state.tasks = []; }
}

/* =================================================================
   Hospitals and doctors
   ================================================================= */
async function renderWorkspace() {
  view().innerHTML = `<div class="page narrow"><div class="skel tall w40"></div><div class="skel"></div></div>`;
  const list = items(await api.hospitals());
  const hid = state.hospital;
  if (!hid) {
    view().innerHTML = `<div class="page wide"><header class="page-head center"><h1>Choose a hospital</h1><p>Pick where you're working today.</p></header>
      <ul class="choice-grid">${list.map(h => `<li><button class="choice" data-h="${esc(h.id)}"><span class="avatar doc big">${esc(initials(h.name))}</span><b>${esc(h.name)}</b><span>${esc(h.city || (h.doctor_count != null ? h.doctor_count + " doctors" : ""))}</span></button></li>`).join("")}</ul>
      ${list.length ? "" : `<div class="panel first"><h3>No hospitals yet</h3><p>Ask the workspace owner to add one.</p></div>`}</div>`;
    $$("[data-h]").forEach(b => b.onclick = async () => {
      b.disabled = true;
      try { session = adapt.session({ ...session, ...(await api.select({ hospital_id: b.dataset.h })) }); csrf = session.csrf_token || csrf; state.hospital = b.dataset.h; renderShell(); await renderWorkspace(); }
      catch (x) { toast(x.message); b.disabled = false; }
    });
    swap(); return;
  }
  const d = await api.doctors(hid), doctors = items(d).map(adapt.doctor), hospital = d.hospital || list.find(h => h.id === hid) || {};
  view().innerHTML = `<div class="page wide">
    <header class="page-head"><button class="link-btn" id="backH">All hospitals</button><h1>${esc(hospital.name)}</h1><p>Choose the doctor to work as. Their patients open next.</p></header>
    <ul class="choice-grid doctors">${doctors.map(x => `<li><button class="choice row-choice" data-d="${esc(x.id)}"><span class="avatar doc">${esc(initials(x.name))}</span><span><b>${esc(x.name)}</b><span>${esc(x.specialty || "")}</span></span></button></li>`).join("")}</ul>
    ${doctors.length ? "" : `<p class="hint">No doctors here yet. Add the first one below.</p>`}
    <section class="panel addform" aria-label="Add a doctor"><h3>Add a doctor</h3>
      <form id="addDoc" class="form-grid three" novalidate>
        <label class="field"><span>Full name</span><input class="input" name="name" required autocomplete="off"></label>
        <label class="field"><span>Specialty</span><input class="input" name="specialty" required autocomplete="off"></label>
        <label class="field"><span>Registration number (optional)</span><input class="input" name="registration_no" autocomplete="off"></label>
        <p class="err span-all" id="docErr" role="alert"></p>
        <div class="span-all"><button class="btn btn-dark">${ICON.plus}Add doctor</button></div>
      </form></section></div>`;
  $("#backH").onclick = () => { state.hospital = null; renderWorkspace(); };
  $$("[data-d]").forEach(b => b.onclick = async () => {
    b.disabled = true;
    try {
      session = adapt.session({ ...session, ...(await api.select({ hospital_id: hid, doctor_id: b.dataset.d })) });
      csrf = session.csrf_token || csrf; if (!session.doctor) session.doctor = doctors.find(x => x.id === b.dataset.d);
      if (!session.hospital) session.hospital = hospital;
      renderShell(); state.selected = null; state.tab = "today"; await loadTasks(); location.hash = "#/patients";
    } catch (x) { toast(x.message); b.disabled = false; }
  });
  $("#addDoc").onsubmit = async e => {
    e.preventDefault();
    const f = e.target, err = $("#docErr");
    if (!f.name.value.trim() || !f.specialty.value.trim()) { err.textContent = "Enter the doctor's name and specialty."; return; }
    try {
      await api.addDoctor(hid, { name: f.name.value.trim(), specialty: f.specialty.value.trim(), registration_no: f.registration_no.value.trim() || undefined });
      toast("Doctor added."); await renderWorkspace();
    } catch (x) { err.textContent = x.message; }
  };
  swap();
}

/* =================================================================
   Register a patient
   ================================================================= */
const PATIENT_LANGS = [["english", "English"], ["hindi", "Hindi"], ["tamil", "Tamil"], ["telugu", "Telugu"], ["gujarati", "Gujarati"]];
const SPOKEN = [["hinglish", "Hinglish"], ...PATIENT_LANGS];
const langName = c => (SPOKEN.find(l => l[0] === c) || [c, cap(c)])[1];
async function renderRegister() {
  const docs = session.admin && session.hospital ? items(await api.doctors(session.hospital.id)).map(adapt.doctor) : session.doctor ? [adapt.doctor(session.doctor)] : [];
  view().innerHTML = `<div class="page narrow">
    <header class="page-head"><h1>Register a patient</h1><p>Added to ${esc(session.hospital?.name || "this hospital")}. Use made-up details only: this is a synthetic demo.</p></header>
    <form class="panel" id="reg" novalidate>
      <div class="form-grid">
        <label class="field span-all"><span>Full name</span><input class="input" name="name" required autocomplete="off"></label>
        <label class="field"><span>Assigned doctor</span><select class="select" name="doctor_id">${docs.map(d => `<option value="${esc(d.id)}"${d.id === session.doctor?.id ? " selected" : ""}>${esc(d.name)}</option>`).join("")}</select></label>
        <div class="field"><span>Phone with country code</span><div class="phone"><select class="select" name="cc" aria-label="Country code"><option value="+91">+91</option><option value="+1">+1</option><option value="+44">+44</option><option value="+971">+971</option></select><input class="input" name="phone" inputmode="tel" aria-label="Phone number" autocomplete="off"></div></div>
        <label class="field"><span>Preferred language</span><select class="select" name="language">${PATIENT_LANGS.map(([c, n]) => `<option value="${c}">${n}</option>`).join("")}</select></label>
        <label class="field"><span>Year of birth</span><input class="input" name="birth_year" type="number" min="1900" max="${new Date().getFullYear()}" inputmode="numeric"></label>
        <label class="field"><span>Sex</span><select class="select" name="sex"><option value="female">Female</option><option value="male">Male</option><option value="other">Other</option></select></label>
        <fieldset class="field span-all"><legend>Allergies</legend><div class="toggles">
          <label><input type="radio" name="allergy_status" value="unknown" checked>Not asked yet</label>
          <label><input type="radio" name="allergy_status" value="none">No known allergies</label>
          <label><input type="radio" name="allergy_status" value="known">Has allergies</label>
        </div></fieldset>
        <label class="field span-all" id="allergyBox" hidden><span>Known allergies, separated by commas</span><input class="input" name="allergies" autocomplete="off"></label>
      </div>
      <fieldset class="consents"><legend>Patient's agreement</legend>
        <label class="consent"><input type="checkbox" name="ai_consent"> <span><b>AI processing.</b> ARDAI can draft reports from this patient's visits. Required.</span></label>
        <label class="consent"><input type="checkbox" name="recording_consent"> <span><b>Recording.</b> Visits can be recorded.</span></label>
        <label class="consent"><input type="checkbox" name="whatsapp_consent"> <span><b>WhatsApp.</b> Approved reports and check-ins go to this number. Demo test numbers only.</span></label>
      </fieldset>
      <p class="err" id="regErr" role="alert"></p>
      <div class="row"><button class="btn btn-dark" id="regGo">Register patient</button><a class="btn btn-line" href="#/patients">Cancel</a></div>
    </form></div>`;
  const f = $("#reg");
  f.querySelectorAll("[name=allergy_status]").forEach(r => r.onchange = () => $("#allergyBox").hidden = f.allergy_status.value !== "known");
  f.onsubmit = async e => {
    e.preventDefault();
    const err = $("#regErr"), bad = (m, el) => { err.textContent = m; el?.focus(); };
    const phone = f.phone.value.replace(/[^\d]/g, ""), year = +f.birth_year.value;
    if (!f.name.value.trim()) return bad("Enter the patient's name.", f.name);
    if (phone.length < 6) return bad("Enter a phone number.", f.phone);
    if (!(year >= 1900 && year <= new Date().getFullYear())) return bad("Enter a year of birth, like 1980.", f.birth_year);
    if (f.allergy_status.value === "known" && !f.allergies.value.trim()) return bad("List the allergies.", f.allergies);
    if (!f.ai_consent.checked) return bad("AI processing agreement is needed to register.", f.ai_consent);
    err.textContent = ""; const b = $("#regGo"); b.disabled = true; b.textContent = "Registering";
    try {
      const r = await api.register({
        name: f.name.value.trim(), phone: f.cc.value + phone, language: f.language.value, doctor_id: f.doctor_id.value, birth_year: year, sex: f.sex.value,
        allergy_status: f.allergy_status.value, allergies: f.allergies.value.split(",").map(s => s.trim()).filter(Boolean),
        ai_consent: f.ai_consent.checked, recording_consent: f.recording_consent.checked, whatsapp_consent: f.whatsapp_consent.checked
      });
      toast("Patient registered."); state.tab = "all"; location.hash = `#/patients/${r.id ?? r.patient_id ?? r.patient?.id}`;
    } catch (x) { err.textContent = x.message; b.disabled = false; b.textContent = "Register patient"; }
  };
  swap();
}

/* =================================================================
   Patients: sidebar + main
   ================================================================= */
function ensureLayout() {
  if ($("#main")) return;
  const h = new Date().toLocaleString("en-IN", { hour: "numeric", hour12: false, timeZone: "Asia/Kolkata" });
  const name = (session.doctor?.display_name || session.doctor?.name || "").replace(/^(Dr\.?\s+)(\S+)\s+/, "$1");
  view().innerHTML = `<div class="layout">
    <aside class="side" aria-label="Patients">
      <div class="hello"><h1>${+h < 12 ? "Good morning" : +h < 17 ? "Good afternoon" : "Good evening"}${name ? ", " + esc(name) : ""}</h1><p>${new Date().toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long", timeZone: "Asia/Kolkata" })}</p></div>
      <section class="attention" id="attention" aria-label="Needs your attention" hidden></section>
      <div class="tabs" role="tablist" aria-label="Patient list"><button role="tab" data-tab="today">Today</button><button role="tab" data-tab="all">All patients</button></div>
      ${session.capabilities?.register === false ? "" : `<a class="btn btn-line add-patient" href="#/register">${ICON.plus}Add patient</a>`}
      <ul class="plist" id="plist" aria-live="polite"></ul>
    </aside>
    <main class="main" id="main" tabindex="-1"></main></div>`;
  $(".tabs").onclick = async e => { const b = e.target.closest("[data-tab]"); if (b) { state.tab = b.dataset.tab; await loadList(); } };
  $("#plist").onclick = e => { const b = e.target.closest(".pitem"); if (b) location.hash = `#/patients/${b.dataset.id}`; };
  $("#main").addEventListener("click", onMainClick);
  swap();
}
async function loadList() {
  $$(".tabs button").forEach(b => b.setAttribute("aria-selected", String(b.dataset.tab === state.tab)));
  try { state.rows = items(await api.patients(state.tab, state.q, session.admin ? session.doctor?.id : undefined)).map(adapt.patient); }
  catch (x) { state.rows = []; $("#plist").innerHTML = `<li class="empty-list">Couldn't load patients. ${esc(x.message)} <button class="link-btn" id="retryList">Try again</button></li>`; $("#retryList").onclick = loadList; return; }
  renderList(); renderAttention();
}
function rowState(p) {
  if (p.visit_state === "in_review") return p.blocking_count ? `<span class="state warn"><span class="dot warn"></span>${p.blocking_count} to check</span>` : `<span class="state iris"><span class="dot iris"></span>Ready</span>`;
  if (p.visit_state === "processing") return `<span class="state iris"><span class="dot iris"></span>Preparing</span>`;
  const f = { on_track: ["ok", "On track"], slightly_off: ["warn", "Slightly off track"], missed: ["risk", "Missed doses"], no_reply: ["warn", "No reply"] }[p.followup_status];
  return f ? `<span class="dot ${f[0]}" title="${f[1]}"><span class="sr">${f[1]}</span></span>` : "";
}
function renderList() {
  const ul = $("#plist"); if (!ul) return;
  if (!state.rows.length) {
    ul.innerHTML = state.q ? `<li class="empty-list">No patient matches "${esc(state.q)}". Try a first name or an ID.</li>` : `<li class="empty-list">${state.tab === "today" ? "No visits today." : "No patients yet."} <a class="link-btn" href="#/register">Register a patient</a></li>`;
    return;
  }
  ul.innerHTML = state.rows.map((p, i) => {
    const sub = state.tab === "today" && p.reason ? p.reason : p.last_visit_date ? "Last seen " + fmtDate(p.last_visit_date).replace(/ \d{4}$/, "") : "No visits yet";
    return `<li class="${state.fresh ? "stagger n" + Math.min(i, 7) : ""}"><button class="pitem" data-id="${esc(p.id)}" aria-current="${p.id === state.selected}">
      <span class="avatar" aria-hidden="true">${p.appointment_time && state.tab === "today" ? esc(p.appointment_time) : esc(initials(p.name))}</span>
      <span class="grow"><span class="name">${esc(p.name)}</span><span class="why">${esc(sub)}</span></span>${rowState(p)}</button></li>`;
  }).join("");
}
function renderAttention() {
  const box = $("#attention"); if (!box) return;
  const list = state.tasks.slice(0, 4); box.hidden = !list.length;
  box.innerHTML = `<h2>${ICON.alert}Needs your attention</h2>` + list.map(t => `<a href="#/followup/${esc(t.encounter_id)}"><b>${esc(t.patient_name || "Patient")}</b><span>${esc(t.title)}</span></a>`).join("");
}
const TODAY_ISO = () => window.VoiceRxMock?.today || new Date().toLocaleDateString("en-CA", { timeZone: session?.scope?.timezone || "Asia/Kolkata" });

async function openPatient(id, encId) {
  state.fresh = !$("#main");
  ensureLayout();
  await loadList(); state.fresh = false;
  id = id || state.rows[0]?.id;
  const main = $("#main");
  if (!id) { main.innerHTML = `<div class="panel first"><h3>No patients here yet</h3><p>Register your first patient to start a visit.</p><a class="btn btn-sun mt" href="#/register">${ICON.plus}Register patient</a></div>`; return; }
  state.selected = id; renderList();
  main.innerHTML = `<div class="panel" aria-busy="true"><div class="skel tall w40"></div><div class="skel"></div><div class="skel w80"></div></div>`;
  const [det, journey] = await Promise.all([api.patient(id), api.journey(id)]);
  if (state.selected !== id) return;
  const encounters = [...(det.encounters || det.visits || [])].map(adapt.encounter).sort((a, b) => String(b.date).localeCompare(String(a.date)));
  // Today's unfinished visit comes first; once every visit today is approved, the latest one shows (runbook D-136).
  const today = encounters.filter(e => e.date === TODAY_ISO());
  const open = encId ? encounters.find(e => e.id === encId) : today.find(e => e.state !== "approved") || today[0];
  const lastApproved = encounters.find(e => e.state === "approved" && e !== open);
  const lastReport = lastApproved ? adapt.report(await api.report(lastApproved.id, lastApproved.approved_version)) : null;
  const p = adapt.patient(det.patient || det);
  state.patient = { ...p, encounters, journey, lastReport };
  const row = state.rows.find(r => r.id === id);
  state.visit = open ? { enc: open.id, phase: "loading" } : (state.tab === "today" && row) ? { phase: "idle", language: "hinglish" } : null;
  renderPatient(true);
  if (open) await resumeVisit(open);
  main.focus({ preventScroll: true });
}

function allergyChip(a) {
  if (a?.status === "known") return `<span class="chip risk">Allergic to ${esc((a.items || []).join(", "))}</span>`;
  if (a?.status === "none") return `<span class="chip muted">No known allergies</span>`;
  return `<span class="chip warn">Allergies not recorded yet</span>`;
}
function renderPatient(animate) {
  const p = state.patient, v = state.visit, main = $("#main");
  const past = p.encounters.filter(e => e.state === "approved" && e.id !== v?.enc);
  main.innerHTML = `
    <div class="phead">
      <span class="avatar" aria-hidden="true">${esc(initials(p.name))}</span>
      <div><h2>${esc(p.name)}</h2>
        <ul class="facts">${p.age != null ? `<li>${esc(p.age)} years</li>` : ""}${p.sex ? `<li>${esc(cap(p.sex))}</li>` : ""}<li>ID ${esc(p.mrn || p.id)}</li>${p.language ? `<li>Speaks ${esc(langName(p.language))}</li>` : ""}${p.phone_last4 ? `<li>Phone ends ${esc(p.phone_last4)}</li>` : ""}<li>${allergyChip(p.allergies)}</li></ul>
      </div>
      ${!v ? `<div class="actions"><button class="btn btn-sun" data-act="new-visit">${ICON.mic}Start a new visit</button></div>` : ""}
    </div>
    <div class="stack">
      ${v ? `<section class="visit-card" id="visit" aria-label="Today's visit"></section>` : ""}
      ${briefHTML(p)}
      ${past.length ? `<section class="panel" aria-label="Past visits"><div class="ph"><h3>Past visits</h3><p>${past.length} approved ${past.length === 1 ? "visit" : "visits"}</p></div>
        <ul class="visits">${past.map(e => `<li class="visit" data-open="false" data-enc="${esc(e.id)}">
          <button aria-expanded="false"><span class="vdate">${fmtDate(e.date)}</span><span class="vdx">${esc(e.diagnosis || e.complaint || "Visit")}</span><span class="vstate chip ok">Approved</span>${ICON.chev}</button>
          <div class="vbody"><div><div class="inner"></div></div></div></li>`).join("")}</ul></section>` : ""}
    </div>`;
  if (v) renderVisit();
  if (animate && !reduce) { main.classList.remove("swap"); void main.offsetWidth; main.classList.add("swap"); }
}

function briefHTML(p) {
  const r = p.lastReport;
  if (!r) return `<section class="panel first"><h3>First visit</h3><p>There's no earlier record for ${esc(first(p.name))}. Today's visit starts their record.</p></section>`;
  const g = k => r.report_groups.find(x => x.key === k || x.heading?.toLowerCase().startsWith(k))?.lines.map(l => l.text).join(" ") || "";
  return `<div class="grid2">
    <section class="panel" aria-label="Since the last visit">
      <div class="ph"><h3>Since the last visit</h3><p>${fmtDate(r.date)}</p></div>
      <dl class="sum">
        <dt>They came for</dt><dd>${esc(g("present") || "Not recorded")}</dd>
        <dt>You found</dt><dd>${esc(g("assessment") || "Not recorded")}</dd>
        <dt>You prescribed</dt><dd>${r.medication_views.length ? r.medication_views.map(m => `<div><b>${esc(m.label)}</b>, ${esc(medShort(m))}</div>`).join("") : "No medicines"}</dd>
        <dt>You advised</dt><dd>${esc(g("treatment") || "Nothing extra")}</dd>
        <dt>Follow-up</dt><dd>${esc(g("review") || "Not set")}</dd>
      </dl>
    </section>
    ${journeyHTML(p)}
  </div>`;
}
function journeyHTML(p) {
  const j = p.journey || {}, f = j.adherence, ups = j.uploads || [], qs = j.questions || [], fn = esc(first(p.name));
  const lastEnc = p.lastReport?.encounter_id;
  const head = chip => `<div class="ph"><div class="wa-head"><span class="wa-badge">${ICON.wa}</span><h3>WhatsApp check-ins</h3></div>${chip || ""}</div>`;
  if (!f && !ups.length && !qs.length) return `<section class="panel">${head()}<p class="wa-sum muted">Nothing from ${fn} yet. Check-ins start once a report is approved and delivered.</p>${lastEnc ? `<a class="btn btn-line btn-small" href="#/followup/${esc(lastEnc)}">${ICON.chat}Open follow-up</a>` : ""}</section>`;
  const cls = { on_track: "ok", slightly_off: "warn", missed: "risk", no_reply: "warn" }[f?.status] || "muted";
  const word = { taken: "taken", late: "taken late", missed: "missed", not_due: "not due" };
  return `<section class="panel" aria-label="WhatsApp check-ins">
    ${head(f ? `<span class="chip ${cls}">${esc(f.label)}</span>` : "")}
    ${f ? `<p class="wa-sum">${esc(f.summary)}</p>
    <div class="adh" role="table" aria-label="Doses over the last 7 days">
      <div role="row" class="contents"><span role="columnheader"><span class="sr">Medicine</span></span>${f.days.map(d => `<span class="d" role="columnheader">${esc(d)}</span>`).join("")}</div>
      ${f.rows.map(r => `<div role="row" class="contents"><span class="lbl" role="rowheader">${esc(r.medicine)}</span>${r.cells.map((c, k) => `<span class="cell ${c}" role="cell" title="${esc(f.days[k])}: ${word[c]}">${c === "missed" ? ICON.x : c === "taken" ? ICON.check : ""}<span class="sr">${word[c]}</span></span>`).join("")}</div>`).join("")}
    </div>
    <div class="legend"><span><i class="taken"></i>Taken</span><span><i class="late"></i>Late</span><span><i class="missed"></i>Missed</span><span><i class="not_due"></i>Not due</span></div>
    ${f.last_message ? `<p class="quote">"${esc(f.last_message.text)}"<small>${fn} on WhatsApp, ${fmtWhen(f.last_message.at)}</small></p>` : ""}` : ""}
    ${qs.length ? `<h4 class="sub-h">${fn} asked</h4><ul class="plain">${qs.map(x => `<li>${esc(x.text || x)}</li>`).join("")}</ul>` : ""}
    ${ups.length ? `<h4 class="sub-h">Reports ${fn} sent</h4>${uploadsHTML(ups)}` : ""}
    ${lastEnc ? `<a class="btn btn-line btn-small mt" href="#/followup/${esc(lastEnc)}">${ICON.chat}Open follow-up</a>` : ""}
  </section>`;
}
function uploadsHTML(ups) {
  return `<ul class="plain uploads">${ups.map(u => `<li><span class="grow"><b>${esc(u.filename || u.title || "Report")}</b>${u.summary ? `<span class="muted">${esc(u.summary)}</span>` : ""}</span>
    <span class="row tight">${u.id && api.uploadUrl ? `<a class="btn btn-line btn-small" href="${esc(api.uploadUrl(u.id))}">Download</a>` : ""}
    ${u.reviewed ? `<span class="chip ok">Reviewed</span>` : `<button class="btn btn-soft btn-small" data-review="${esc(u.id)}">Mark reviewed</button>`}</span></li>`).join("")}</ul>`;
}

/* Medicine wording */
const FOOD = { after_food: "after food", before_food: "before food", with_food: "with food", empty_stomach: "on an empty stomach", before_breakfast: "before breakfast" };
const SLOT = ["morning", "afternoon", "evening", "night"];
function scheduleText(s) {
  if (!s) return "timing not set";
  if (s.kind === "as_needed") return "when needed" + (s.max_per_day ? `, up to ${s.max_per_day} a day` : "");
  if (s.kind === "frequency") return (["", "once", "twice", "three times", "four times"][s.times_per_day] || s.times_per_day + " times") + " a day";
  if (s.kind === "slots") { const on = s.slots.map((n, i) => n ? SLOT[i] : null).filter(Boolean); return on.length === 1 ? "every " + on[0] : on.length ? on.slice(0, -1).join(", ") + " and " + on.at(-1) : "timing not set"; }
  if (s.kind === "weekly") return `${s.times} ${s.times === 1 ? "time" : "times"} a week`;
  if (s.kind === "taper") return "tapering dose, see full instructions";
  return s.phrase ? `"${s.phrase}" (check timing)` : "timing not set";
}
const doseText = d => d ? `${d.amount} ${d.unit}${d.amount !== "1" && !/ml/i.test(d.unit) ? "s" : ""}` : "dose not set";
const medShort = m => m.display || `${doseText(m.dose)} ${scheduleText(m.schedule)}${m.food ? ", " + (FOOD[m.food] || m.food) : ""}${m.duration ? `, ${m.duration.value} ${m.duration.unit}${m.duration.value > 1 ? "s" : ""}` : ""}`;

/* =================================================================
   Visit: idle -> record/type/upload -> processing -> review -> approved
   ================================================================= */
function stepper(n) {
  return `<ol class="stepper" aria-label="Visit progress">${["Record", "Check", "Approve"].map((s, i) => `<li data-s="${i < n ? "done" : i === n ? "now" : "todo"}"${i === n ? ' aria-current="step"' : ""}>${s}</li>`).join("")}</ol>`;
}
const STEP_TEXT = { transcribing: "Turning speech into text", extracting: "Picking out symptoms, findings and medicines", checking: "Checking medicines and instructions", writing: "Writing the report", report_checks: "Checking the report", assembling: "Putting the prescription together", suggesting: "Preparing medicine suggestions" };
function renderVisit() {
  const box = $("#visit"); if (!box) return;
  const p = state.patient, v = state.visit, fn = esc(first(p.name));
  if (v.phase === "loading") { box.innerHTML = stepper(1) + `<div class="skel tall w40"></div><div class="skel"></div>`; return; }

  if (v.phase === "idle") {
    const refused = p.consents?.recording === false || p.recording_consent === false;
    box.innerHTML = stepper(0) + `<div class="rec-grid">
      <div><button class="mic idle" id="micBtn" aria-describedby="consentErr">${ICON.mic}<span class="halo"></span><span class="sr">Start recording</span></button><span class="mic-label" aria-hidden="true">Start recording</span></div>
      <div class="rec-copy">
        <h3>Record today's visit with ${fn}</h3>
        <p>Talk to ${fn} the way you normally do. When you stop, ARDAI drafts the report and prescription for you to check.</p>
        <div class="lang-row"><label for="lang">Language spoken</label><select class="select" id="lang">${SPOKEN.map(([c, n]) => `<option value="${c}"${c === v.language ? " selected" : ""}>${n}</option>`).join("")}</select></div>
        ${refused ? `<p class="hint warn">${fn} didn't agree to recording at registration. Type your notes instead.</p>` : `<label class="consent" id="consentRow"><input type="checkbox" id="consent" ${v.consent ? "checked" : ""}> <span>${fn} has agreed to this visit being recorded</span></label>`}
        <p class="hint warn" id="consentErr" role="alert" hidden></p>
      </div>
    </div>
    <div class="alt">
      <label class="btn btn-line" for="fileIn">${ICON.upload}Upload a recording</label><input class="sr" type="file" id="fileIn" accept="audio/*">
      <button class="btn btn-line" data-act="type">${ICON.type}Type notes instead</button>
    </div>`;
    $("#lang").onchange = e => v.language = e.target.value;
    const c = $("#consent");
    if (c) c.onchange = e => { v.consent = e.target.checked; if (v.consent) { $("#consentErr").hidden = true; $("#consentRow").classList.remove("need"); } };
    const need = () => { const er = $("#consentErr"); er.hidden = false; er.textContent = refused ? "Recording isn't allowed for this patient." : `Ask ${first(p.name)} first, then tick the box.`; $("#consentRow")?.classList.add("need"); c?.focus(); };
    $("#micBtn").onclick = () => v.consent ? startRecording() : need();
    $("#fileIn").onclick = e => { if (!v.consent) { e.preventDefault(); need(); } };
    $("#fileIn").onchange = e => { const f = e.target.files[0]; if (f) submitAudio(f); };
    return;
  }
  if (v.phase === "typing") {
    box.innerHTML = stepper(0) + `<h3>Type the visit notes</h3><p class="hint mb">Write it the way you'd dictate it. Brand names are fine.</p>
      <label class="field"><span class="sr">Visit notes</span><textarea class="textarea" id="notes" maxlength="20000" placeholder="Fever for three days, no cough. Dolo 650 one tablet when needed, after food, three days.">${esc(v.text || "")}</textarea></label>
      <p class="hint warn" id="typeErr" role="alert" hidden></p>
      <div class="row"><button class="btn btn-dark" id="typeGo">Create report</button><button class="btn btn-line" data-act="cancel">Back</button></div>`;
    $("#notes").focus(); $("#notes").oninput = e => v.text = e.target.value; $("#typeGo").onclick = submitTyped;
    return;
  }
  if (v.phase === "recording") {
    box.innerHTML = stepper(0) + `<div class="rec-grid">
      <div><button class="mic live" id="micStop">${ICON.mic}<span class="halo" id="halo"></span><span class="sr">Stop recording</span></button><span class="mic-label" aria-hidden="true">${v.paused ? "Paused" : "Listening"}</span></div>
      <div>
        <div class="live-top"><span class="rec-dot ${v.paused ? "paused" : ""}" aria-hidden="true"></span><span class="timer" id="timer" role="timer">00:00</span></div>
        <canvas class="live-wave" id="liveWave" aria-hidden="true"></canvas>
        <div class="row"><button class="btn btn-dark" id="stopBtn">Stop recording</button><button class="btn btn-line" id="pauseBtn">${v.paused ? ICON.play + "Resume" : ICON.pause + "Pause"}</button><button class="btn btn-quiet" id="discardBtn">Discard</button></div>
        <p class="hint">${mic.fake ? "Microphone isn't available here, so this is a pretend recording for the demo." : "Speak normally. Recording stops by itself after 20 minutes."}</p>
        <p class="hint" id="liveNote" aria-live="polite">${liveNote(mic.live)}</p>
      </div></div>`;
    $("#stopBtn").onclick = $("#micStop").onclick = stopRecording;
    $("#pauseBtn").onclick = togglePause;
    $("#discardBtn").onclick = () => { stopMic(); v.phase = "idle"; renderVisit(); toast("Recording discarded."); };
    tickTimer(); drawLive();
    return;
  }
  if (v.phase === "review-audio") {
    box.innerHTML = stepper(0) + `<h3>Listen back, or create the report</h3><p class="hint">Recording length ${esc(v.duration || "")}.</p>
      ${v.url ? `<audio controls src="${v.url}"></audio>` : ""}
      <div class="row mt"><button class="btn btn-dark" id="useRec">Create report</button><button class="btn btn-line" id="redo">Record again</button></div>`;
    $("#useRec").onclick = () => submitAudio(v.blob);
    $("#redo").onclick = () => { if (v.url) URL.revokeObjectURL(v.url); Object.assign(v, { phase: "idle", blob: null, url: null, live: null }); renderVisit(); };
    return;
  }
  if (["uploading", "processing", "failed"].includes(v.phase)) {
    // Medicines first (runbook D-137, D-138): after the stop the doctor only picks medicines; the report is
    // written out of sight and shown, whole, once the doctor is done.
    if (v.phase === "failed") {
      box.dataset.frame = "";
      box.innerHTML = stepper(1) + `<h3>The report couldn't be prepared</h3><div id="pendingMeds">${pendingHTML(v)}</div>
        <div class="error-box" role="alert"><p>${esc(v.error || "Something went wrong while writing the report.")}</p>${v.run ? `<button class="btn btn-dark" id="retryRun">Try again</button>` : ""}</div>`;
      $("#retryRun")?.addEventListener("click", retryRun);
      return;
    }
    const frame = v.medsDone ? "proc-wait" : "proc-pick";
    if (box.dataset.frame === frame) return;  // a poll changes nothing the doctor sees
    box.dataset.frame = frame;
    if (v.medsDone) {
      box.innerHTML = stepper(1) + `<div class="finishing" role="status"><span class="spinner ink" aria-hidden="true"></span><div><h3>Putting ${fn}'s report together</h3><p class="hint m0">A few seconds more.</p></div></div>
        <div id="pendingMeds">${pendingHTML(v)}</div>`;
      return;
    }
    box.innerHTML = stepper(1) + `<div class="proc-meds"><div class="ph-row"><div><h3>Pick ${fn}'s medicines</h3>
        <p class="hint m0">Enter adds a medicine and opens the next. Esc when you're done; the report opens then.</p></div>
        <button class="btn btn-dark" data-act="meds-done">Done, show the report</button></div>
      <div id="pendingMeds">${pendingHTML(v)}</div><div id="pickerHost"></div></div>`;
    if (v.picker) drawPicker(); else if (!v.pickedOnce) { v.pickedOnce = true; openPicker(); }
    return;
  }
  box.dataset.frame = "";
  if (v.phase === "review") return renderReview(box);
  if (v.phase === "approved") return renderApproved(box);
}

/* -------- Recording -------- */
const mic = { stream: null, ctx: null, analyser: null, data: null, rec: null, chunks: [], raf: 0, tick: 0, start: 0, pausedAt: 0, pausedTotal: 0, fake: false, auto: 0, live: null, liveTimer: 0 };
/* While the visit goes on, the recording so far goes to the server every 10 seconds and is transcribed there,
   so the report starts as soon as the doctor stops. If anything here fails, the recording is uploaded whole
   when the report is created, as before. */
const LIVE_EVERY = 10000;
function liveStart(encReady, type, language) {
  const L = { id: null, part: 0, queue: [], chain: Promise.resolve(), ok: true, finished: false, status: null };
  L.ready = encReady.then(enc => api.liveBegin(enc, type, language)).then(r => { L.id = r.id; }).catch(() => { L.ok = false; });
  return L;
}
function liveSend(L, final) {
  if (!L?.ok) return Promise.resolve();
  const pieces = L.queue.splice(0);
  if (!pieces.length && !final) return L.chain;
  L.chain = L.chain.then(async () => {
    await L.ready; if (!L.ok) return;
    const blob = new Blob(pieces, { type: "application/octet-stream" });
    for (let tries = 1; ; tries++) {
      try { L.status = await api.livePart(L.id, L.part, blob, final); L.part++; L.finished = !!L.status.finished; break; }
      catch (x) {
        // A piece that cannot be taken ends the head start; the whole file is uploaded at the end instead.
        if (tries >= 3 || [404, 409, 413, 422].includes(x.status)) { L.ok = false; break; }
        await new Promise(r => setTimeout(r, 1500 * tries));
      }
    }
    const el = $("#liveNote"); if (el) el.textContent = liveNote(L);
  });
  return L.chain;
}
const liveNote = L => L?.ok && L.status?.transcribed_s ? `Writing it down as you talk: ${fmtClock(L.status.transcribed_s * 1000)} so far.` : "";
async function startRecording() {
  const v = state.visit; mic.fake = false; mic.chunks = []; mic.rec = null; mic.live = null; v.live = null;
  try {
    mic.stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
    mic.ctx = new AudioContext(); mic.analyser = mic.ctx.createAnalyser(); mic.analyser.fftSize = 256;
    mic.ctx.createMediaStreamSource(mic.stream).connect(mic.analyser); mic.data = new Uint8Array(mic.analyser.frequencyBinCount);
    mic.rec = new MediaRecorder(mic.stream);
    mic.rec.ondataavailable = e => { if (e.data.size) { mic.chunks.push(e.data); mic.live?.queue.push(e.data); } };
    if (api.liveBegin) {
      mic.live = liveStart(ensureEncounter(), (mic.rec.mimeType || "audio/webm").split(";")[0], v.language || "hinglish");
      clearInterval(mic.liveTimer); mic.liveTimer = setInterval(() => liveSend(mic.live, false), LIVE_EVERY);
    }
    mic.rec.start(1000);
  } catch (_) {
    if (!window.VoiceRxMock) { toast("Microphone permission is needed to record. You can upload a file or type instead."); return; }
    mic.fake = true;
  }
  Object.assign(mic, { start: performance.now(), pausedTotal: 0, pausedAt: 0 });
  v.phase = "recording"; v.paused = false; renderVisit();
  clearTimeout(mic.auto); mic.auto = setTimeout(() => state.visit?.phase === "recording" && stopRecording(), 20 * 60 * 1000);
}
const elapsed = () => Math.max(0, (mic.pausedAt || performance.now()) - mic.start - mic.pausedTotal);
const fmtClock = ms => { const s = Math.floor(ms / 1000); return String(Math.floor(s / 60)).padStart(2, "0") + ":" + String(s % 60).padStart(2, "0"); };
function tickTimer() { clearInterval(mic.tick); const t = () => { const el = $("#timer"); if (el) el.textContent = fmtClock(elapsed()); }; t(); mic.tick = setInterval(t, 250); }
function togglePause() {
  const v = state.visit;
  if (!v.paused) { v.paused = true; mic.pausedAt = performance.now(); mic.rec?.pause(); }
  else { v.paused = false; mic.pausedTotal += performance.now() - mic.pausedAt; mic.pausedAt = 0; mic.rec?.resume(); }
  cancelAnimationFrame(mic.raf); renderVisit();
}
function drawLive() {
  const c = $("#liveWave"); if (!c) return;
  const dpr = Math.min(devicePixelRatio || 1, 2), w = c.clientWidth, h = c.clientHeight;
  if (c.width !== w * dpr) { c.width = w * dpr; c.height = h * dpr; }
  const ctx = c.getContext("2d"); ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, w, h);
  const bars = Math.floor(w / 6), t = performance.now() / 1000, paused = state.visit?.paused;
  if (mic.analyser) mic.analyser.getByteFrequencyData(mic.data);
  let level = 0; ctx.fillStyle = "#16171C";
  for (let b = 0; b < bars; b++) {
    let v = mic.analyser ? mic.data[Math.floor((b / bars) * mic.data.length * .7)] / 255 : Math.abs(Math.sin(b * .4 + t * 6) * .6 + Math.sin(b * .11 - t * 2.3) * .4) * (.55 + .45 * Math.sin(t * 1.7) ** 2);
    if (paused) v = .03;
    level += v; const bh = Math.max(3, v * h * .95);
    ctx.globalAlpha = .3 + v * .7; ctx.beginPath(); ctx.roundRect(b * 6, (h - bh) / 2, 3, bh, 2); ctx.fill();
  }
  ctx.globalAlpha = 1;
  const halo = $("#halo"); if (halo && !reduce) halo.style.transform = `scale(${1 + Math.min(level / bars, 1) * .2})`;
  mic.raf = requestAnimationFrame(drawLive);
}
function stopMic() {
  cancelAnimationFrame(mic.raf); clearInterval(mic.tick); clearTimeout(mic.auto); clearInterval(mic.liveTimer);
  try { if (mic.rec && mic.rec.state !== "inactive") mic.rec.stop(); } catch (_) {}
  mic.stream?.getTracks().forEach(t => t.stop()); mic.ctx?.close().catch(() => {});
  mic.stream = mic.ctx = mic.analyser = null;
}
async function stopRecording() {
  const v = state.visit, ms = elapsed();
  let blob;
  if (mic.rec) { const done = new Promise(r => mic.rec.onstop = r); stopMic(); await done; blob = new Blob(mic.chunks, { type: mic.rec.mimeType || "audio/webm" }); }
  else { stopMic(); blob = new Blob([new Uint8Array(64)], { type: "audio/webm" }); }
  const L = mic.live; mic.live = null;
  if (ms < 2000) { toast("That was too short. Record at least 2 seconds."); v.phase = "idle"; renderVisit(); return; }
  // The last piece goes now, while the doctor listens back; the report can start without another upload.
  if (L?.ok) { liveSend(L, true); v.live = L; }
  Object.assign(v, { blob, duration: fmtClock(ms), pendingMeds: [], pickedOnce: false, picker: null, medsDone: false, ready: null });
  submitAudio(blob);
}

/* -------- Submit and process -------- */
function ensureEncounter() {
  // Recording now creates the visit as it starts, so a second call waits for the first rather than making another.
  const v = state.visit;
  if (v.enc) return Promise.resolve(v.enc);
  return v.encReady ||= api.createEncounter(state.patient.id).then(e => {
    v.enc = e.id ?? e.encounter_id; history.replaceState(null, "", `#/encounters/${v.enc}`); state.guard = location.hash; return v.enc;
  }).catch(x => { v.encReady = null; throw x; });
}
async function submitAudio(blob) {
  const v = state.visit;
  if (blob.size > 40 * 1024 * 1024) { toast("That file is over 40 MB. Use a shorter recording."); return; }
  v.phase = "uploading"; v.run = null; v.upPct = 0; renderVisit();
  const L = blob === v.blob ? v.live : null; v.live = null;
  try {
    const enc = await ensureEncounter();
    let src = null;
    if (L) { await L.chain; if (L.ok && L.finished) src = await api.liveComplete(L.id).catch(() => null); }
    src = src || await api.audioSource(enc, blob, v.language || "hinglish", pct => { v.upPct = pct; renderVisit(); });
    await startProcessing(enc, src);
  } catch (x) { v.phase = "failed"; v.error = x.message; renderVisit(); }
}
async function submitTyped() {
  const v = state.visit, text = (v.text || "").trim(), e = $("#typeErr");
  if (text.length < 10) { e.hidden = false; e.textContent = "Write a little more so there's something to report."; return; }
  v.phase = "uploading"; renderVisit();
  try { const enc = await ensureEncounter(); await startProcessing(enc, await api.typedSource(enc, text, v.language || "hinglish")); }
  catch (x) { v.phase = "failed"; v.error = x.message; renderVisit(); }
}
async function startProcessing(enc, src) {
  const v = state.visit;
  v.run = await api.startRun(enc, src); v.phase = "processing"; renderVisit(); refreshRows(); pollRun(1200);
}
function pollRun(delay) {
  stopPolling();
  const v = state.visit, pid = state.selected;
  state.poll = setTimeout(async () => {
    if (state.selected !== pid || !v.run) return;
    try {
      v.run = await api.run(v.run.id ?? v.run.run_id);
      if (v.run.state === "succeeded") {
        v.ready = adapt.report(await api.report(v.enc));
        if (v.medsDone) await showReport(v);  // otherwise it waits, out of sight, until the doctor is done
        return;
      }
      if (v.run.state === "failed" || v.run.state === "incomplete") { v.phase = "failed"; v.error = v.run.error?.message || "Processing stopped before the report was ready."; renderVisit(); return; }
      renderVisit(); pollRun(document.hidden ? 8000 : 2000);
    } catch (_) { pollRun(Math.min(15000, delay * 2)); }
  }, delay);
}
async function retryRun() { const v = state.visit; try { v.run = await api.retry(v.run.id ?? v.run.run_id); v.phase = "processing"; renderVisit(); pollRun(1200); } catch (x) { toast(x.message); } }
async function resumeVisit(open) {
  const v = state.visit;
  try {
    if (open.state === "in_review" || open.state === "approved") {
      v.report = adapt.report(await api.report(open.id)); v.phase = v.report.status === "approved" ? "approved" : "review";
      if (v.phase === "approved") pollFiles(800);
    } else if (open.state === "processing" || open.state === "failed") {
      const e = await api.encounter(open.id), run = e.latest_run || e.run;
      if (run) { v.run = adapt.run(run); v.phase = open.state === "failed" ? "failed" : "processing"; v.error = run.error?.message; if (v.phase === "processing") pollRun(1200); } else v.phase = "idle";
    } else { v.phase = "idle"; v.language = "hinglish"; }
  } catch (_) { v.phase = "idle"; }
  renderVisit();
}
async function refreshRows() { try { state.rows = items(await api.patients(state.tab, state.q, session.admin ? session.doctor?.id : undefined)).map(adapt.patient); renderList(); } catch (_) {} }

/* -------- Review -------- */
function renderReview(box) {
  const v = state.visit, r = v.report, fn = esc(first(state.patient.name));
  const blocks = r.issue_views.filter(i => i.severity === "block"), warns = r.issue_views.filter(i => i.severity !== "block");
  box.innerHTML = stepper(r.can_approve ? 2 : 1) + `
    <div class="review-head">
      <div><h3>Check ${fn}'s draft report</h3><p>Tap any sentence to see what was heard. Fix anything that's off, then approve.</p></div>
      <div class="row">
        <span class="saved">${sized(ICON.check, 18)}Saved, version ${esc(r.version)}</span>
        <button class="btn btn-line btn-small" data-act="ref">${ICON.book}Look up</button>
        <button class="btn btn-line btn-small" data-act="pdf">${ICON.pdf}Preview PDF</button>
        <button class="btn btn-line btn-small" data-act="json">${ICON.json}Download JSON</button>
      </div>
    </div>
    ${r.issue_views.length ? `<section class="checks" aria-label="Things to check"><h4>${ICON.alert}${blocks.length ? `${blocks.length} ${blocks.length === 1 ? "thing" : "things"} to answer before you approve` : "Worth a quick look"}</h4>
      ${[...blocks, ...warns].map(i => `<div class="issue ${i.severity === "block" ? "" : "warn-only"}"><b>${esc(i.title)}</b><p>${esc(i.message || "")}</p>
        <div class="row">${i.actions.map((a, k) => `<button class="btn ${k === 0 ? "btn-dark" : "btn-line"} btn-small" data-fix="${esc(i.id)}" data-k="${k}">${esc(a.label)}</button>`).join("")}</div></div>`).join("")}
    </section>` : `<div class="all-clear">${sized(ICON.check, 20)}Nothing needs your answer. Read it through and approve.</div>`}
    <div class="${v.reveal ? "reveal" : ""}">${reportHTML(r, true)}</div>
    ${stockNoteHTML(r)}
    <div class="approve-bar">
      <button class="btn btn-dark" id="approveBtn" ${r.can_approve ? "" : "disabled"}>Approve report</button>
      <p>${r.can_approve ? `Approving saves the final report and sends the PDF to ${fn} on WhatsApp, if they agreed.` : `Answer the ${blocks.length === 1 ? "check" : blocks.length + " checks"} above to approve.`}</p>
    </div>`;
  v.reveal = false;
  box.querySelectorAll("[data-fix]").forEach(b => b.onclick = () => {
    const i = r.issue_views.find(x => x.id === b.dataset.fix), a = i.actions[+b.dataset.k], v = state.visit;
    if (a.edit) { const med = r.medication_views.find(m => m.id === a.edit); if (med) openPicker(med); return; }
    if (a.find) { Object.assign(v, { adding: true, replacing: a.find, editing: null, newMed: null }); renderVisit(); return; }
    if (a.line) { const t = box.querySelector(`.sent[data-ref="${CSS.escape(a.line)}"]`); t?.click(); t?.closest(".rgroup")?.querySelector("[data-line=edit]")?.click(); return; }
    applyFix(a.resolutions.map(x => ({ reason: `Answered: ${i.title}`, ...x })), b);
  });
  $("#approveBtn").onclick = approve;
  wireReport(box, r, true);
  wireAddMedicine(box);
  // The picker survives a redraw; after adding a medicine it opens again for the next one (until Esc).
  if (v.chainPicker) { v.chainPicker = false; openPicker(); } else drawPicker();
}
function stockNoteHTML(r) {
  if (!r.pharmacy) return "";
  const missing = r.medication_views.filter(m => m.stock && ["out", "not_stocked"].includes(m.stock.status));
  return missing.length
    ? `<p class="stock-note warn" role="status">${ICON.alert}<span>${missing.length === 1 ? "One medicine isn't" : missing.length + " medicines aren't"} available at the hospital pharmacy: ${esc(missing.map(m => m.label).join(", "))}. You can still approve; the patient would buy ${missing.length === 1 ? "it" : "them"} elsewhere.</span></p>`
    : `<p class="stock-note" role="status">${sized(ICON.check, 18)}<span>Every medicine is available at the hospital pharmacy (stock as of ${fmtWhen(r.pharmacy.as_of)}).</span></p>`;
}
function reportHTML(r, editable) {
  return `<div class="report">
    <p class="tip">Outpatient visit on ${fmtDate(r.date)}${r.clinician ? ` with ${esc(r.clinician)}` : ""}.</p>
    ${r.report_groups.map(g => `<section class="rgroup"><h4>${esc(g.heading)}</h4>
      <p>${g.lines.map(l => `<button class="sent" data-ref="${esc(l.ref)}" aria-expanded="false">${esc(l.text)}</button>`).join(" ")}</p>
      <div class="evidence" hidden aria-live="polite"></div></section>`).join("")}
    <section class="rgroup"><div class="ph-row"><h4>Medicines</h4>${editable ? `<button class="btn btn-line btn-small" data-act="add-med" title="Shortcut: space bar">${ICON.plus}Add medicine <kbd class="kbd">Space</kbd></button>` : ""}</div>
      ${editable && state.visit?.replacing ? `<p class="hint">Choose the medicine for "${esc(r.all_meds?.[state.visit.replacing]?.label || "")}".</p>` : ""}
      ${editable && state.visit?.newMed ? `<div class="medit add"><p class="hint m0"><b>${esc(state.visit.newMed.label)}</b> ${esc(state.visit.newMed.composition)}</p>${editorHTML(state.visit.newMed)}</div>` : editable && state.visit?.adding ? addMedHTML() : ""}${editable ? `<div id="pickerHost"></div>` : ""}${medsHTML(r.medication_views, editable)}</section>
  </div>`;
}
function medsHTML(meds, editable) {
  if (!meds.length) return `<p class="z">No medicines prescribed.</p>`;
  const tag = { standard: "from standard instructions", auto: "picked automatically", learned: "from this clinic's past choices", unit: "unit filled in", generic: "matched to the generic" };
  return `<div class="meds-wrap"><table class="meds">
    <thead><tr><th scope="col">Medicine</th><th class="s" scope="col">Morning</th><th class="s" scope="col">Afternoon</th><th class="s" scope="col">Evening</th><th class="s" scope="col">Night</th>${editable ? '<th class="s" scope="col"><span class="sr">Edit</span></th>' : ""}</tr></thead>
    <tbody>${meds.map(m => {
      const slots = m.schedule?.kind === "slots" ? m.schedule.slots : null, filled = Object.entries(m.filled || {});
      return `<tr>
        <td><span class="mname">${esc(m.label)}</span><span class="mcomp">${esc(m.composition)}</span>
          <span class="mhow">${m.action && m.action !== "start" ? esc(cap(m.action)) + ". " : ""}${esc(medShort(m))}</span>
          ${filled.length ? `<span class="filled chip iris" title="${esc(filled.map(([k, x]) => k + ": " + (tag[x] || x)).join(". "))}">${esc(filled.map(([k]) => k).join(", "))} filled in, please check</span>` : ""}
          ${editable && m.standard?.length ? `<span class="std"><span class="chip iris">Usual directions</span> ${esc(m.standard.map(p => p.text).join(" · "))} <button class="btn btn-line btn-small" data-std="${esc(m.id)}">Use these</button></span>` : ""}
          ${m.stock ? `<span class="stock">${stockChip(m.stock)}${editable && m.stock.alternatives.length ? `<span class="stock-alt"><span class="hint m0">Same composition in stock:</span>${m.stock.alternatives.map(a => `<button class="btn btn-line btn-small" data-swap="${esc(m.id)}" data-product="${esc(a.product_id)}" data-label="${esc(a.label)}" data-status="${esc(m.stock.status)}" title="${esc(a.composition)}">Use ${esc(a.label)} (${esc(a.quantity)})</button>`).join("")}</span>` : ""}</span>` : ""}
        </td>
        ${[0, 1, 2, 3].map(i => `<td class="s">${slots ? (slots[i] ? `<span class="n">${esc(slots[i])}</span>` : `<span class="z">–</span>`) : (i === 0 ? `<span class="z">${esc(m.schedule ? scheduleText(m.schedule) : "")}</span>` : "")}</td>`).join("")}
        ${editable ? `<td class="s"><button class="btn btn-line btn-small" data-edit="${esc(m.id)}" ${m.unresolved ? 'disabled title="Answer the check above first"' : ""}>Edit</button></td>` : ""}
      </tr>${editable && state.visit?.editing === m.id ? `<tr><td colspan="6">${editorHTML(m)}</td></tr>` : ""}`;
    }).join("")}</tbody></table></div>`;
}
const unitOf = m => m.dose?.unit || { capsule: "capsule", syrup: "mL", suspension: "mL", solution: "mL", drops: "drop" }[m.form] || (/CAP/i.test(m.label) ? "capsule" : /SYRUP/i.test(m.label) ? "mL" : "tablet");
const DAYS = { day: 1, week: 7, month: 30 };
const daysOf = d => d ? d.value * (DAYS[d.unit] || 1) : "";
function editorHTML(m) {
  const s = m.schedule || {}, slots = s.kind === "slots" ? s.slots : [0, 0, 0, 0], prn = s.kind === "as_needed", unit = unitOf(m);
  return `<form class="medit" id="medEdit" data-med="${esc(m.id)}">
    <div class="two">
      <label class="field m0"><span>How much each time</span><select class="select" name="dose">${[...new Set([...(unit === "mL" ? ["2.5", "5", "10"] : ["0.5", "1", "2", "3", "4"]), ...(m.dose?.amount ? [m.dose.amount] : [])])].map(d => `<option value="${d}"${(m.dose?.amount ?? (unit === "mL" ? "5" : "1")) === d ? " selected" : ""}>${d} ${esc(unit)}</option>`).join("")}</select></label>
      <label class="field m0"><span>For how many days</span><input class="input" name="days" type="number" min="1" max="365" inputmode="numeric" value="${esc(daysOf(m.duration))}"></label>
    </div>
    <fieldset><legend>When to take it</legend><div class="toggles">
      ${SLOT.map((n, i) => `<label><input type="checkbox" name="slot" value="${i}" ${slots[i] ? "checked" : ""} ${prn ? "disabled" : ""}>${cap(n)}</label>`).join("")}
      <label><input type="checkbox" name="prn" ${prn ? "checked" : ""}>When needed</label>
    </div></fieldset>
    <label class="field m0"><span>Food</span><select class="select" name="food">${m.food ? "" : `<option value="">Not said</option>`}${Object.entries(FOOD).filter(([k]) => k !== "before_breakfast").map(([k, t]) => `<option value="${k}"${m.food === k ? " selected" : ""}>${cap(t)}</option>`).join("")}</select></label>
    ${s.kind === "taper" || s.kind === "frequency" ? `<p class="hint warn">This medicine says "${esc(scheduleText(s))}". Saving replaces that with the times you tick.</p>` : ""}
    <p class="hint warn" id="editErr" role="alert" hidden></p>
    <div class="row"><button class="btn btn-dark" type="submit">${m.id === "__new" ? "Add to prescription" : "Save changes"}</button><button class="btn btn-line" type="button" data-act="cancel-edit">Cancel</button>${m.id === "__new" ? "" : `<button class="btn btn-quiet danger" type="button" data-act="remove-med" data-med="${esc(m.id)}">Remove medicine</button>`}</div>
  </form>`;
}
function addMedHTML() {
  return `<div class="medit add" id="addMed">
    <label class="field m0"><span>Find a medicine</span><input class="input" id="medQ" placeholder="Type a brand or generic name" autocomplete="off"></label>
    <div class="row"><button class="btn btn-soft btn-small" data-act="shortlist">Show common choices</button><button class="btn btn-quiet btn-small" data-act="close-add">Close</button></div>
    <ul class="picks" id="medResults" aria-live="polite"></ul></div>`;
}
function wireAddMedicine(box) {
  const input = $("#medQ", box); if (!input) return;
  input.focus(); let t;
  input.oninput = () => { clearTimeout(t); const s = input.value.trim(); if (s.length < 2) { $("#medResults").innerHTML = ""; return; } t = setTimeout(async () => showPicks(items(await api.catalog(s))), 200); };
}
function showPicks(list) {
  const ul = $("#medResults"); if (!ul) return;
  ul.innerHTML = list.length ? list.map(p => `<li><button class="pick" data-product="${esc(p.id ?? p.product_id)}" data-label="${esc(p.label || p.name || p.brand)}" data-comp="${esc(p.composition || "")}" data-form="${esc(p.form || "")}" data-food="${esc(p.food || "")}"><b>${esc(p.label || p.name || p.brand)}</b><span>${esc(p.composition || p.generic || "")}${p.group ? " · " + esc(p.group) : ""}</span>${stockChip(p.stock)}</button></li>`).join("") : `<li class="hint">No medicine found. Check the spelling.</li>`;
}
/* -------- Keyboard medicine picker (runbook D-122, brought back in D-133) --------
   Space on the review screen opens it with this visit's common choices (narrowed from the findings). Type or
   ↓ ↑ to choose and Enter to pick; then ↑ ↓ moves between the rows, ← → changes the value, Enter adds the
   medicine and opens the next one, Esc steps back, and Esc again closes. Edit opens the same rows. */
const PK_DAYS = [1, 2, 3, 5, 7, 10, 14, 21, 30, 60, 90];
const PK_TIMES = [["1", "Once"], ["2", "Twice"], ["3", "Three times"], ["4", "Four times"], ["sos", "When needed"]];
const PK_WHEN = { "1": ["m", "a", "e", "n"], "2": ["mn", "me", "ma", "an"], "3": ["man", "men"], "4": ["maen"], sos: [""] };
const PK_SLOT = { m: "Morning", a: "Afternoon", e: "Evening", n: "Night" };
const PK_FOOD = [["", "Not said"], ["after_food", "After food"], ["before_food", "Before food"], ["with_food", "With food"], ["empty_stomach", "Empty stomach"]];
const PK_ONCE = { morning: "m", afternoon: "a", evening: "e", night: "n" };
const pkWhenText = w => w ? w.split("").map(s => PK_SLOT[s]).join(" + ") : "As needed";
const PICKING = ["uploading", "processing", "review"];
function openPicker(med) {
  const v = state.visit; if (!v || !PICKING.includes(v.phase) || !$("#pickerHost")) return;
  Object.assign(v, { editing: null, adding: false, newMed: null, replacing: null });
  const meds = v.phase === "review" ? v.report.medication_views : v.pendingMeds || [];
  v.picker = { med: med || null, q: "", options: [], active: 0, chosen: null, rows: [], row: 0,
    taken: meds.map(m => m.product_id).filter(Boolean), number: meds.length + 1 };
  // Before the draft, the list may still be improving from the visit (runbook D-137), so fetch it afresh.
  if (v.phase !== "review" && v.shortlists) delete v.shortlists[v.enc];
  if (med) pkStart(v.picker, { product_id: med.product_id, label: med.label, composition: med.composition, form: med.form, food: med.food }, med);
  drawPicker();
  $("#pickerHost")?.scrollIntoView({ block: "nearest" });
  if (!med && !(v.shortlists || {})[v.enc]) {
    v.shortlists ||= {};
    api.shortlist(v.enc).then(s => { v.shortlists[v.enc] = { conditions: s?.conditions || [], items: items(s) }; })
      .catch(x => { v.shortlists[v.enc] = { conditions: [], items: [] }; toast(x.message); })
      .finally(() => { if (state.visit?.picker && !state.visit.picker.chosen) { if (!$("#pkQ")) drawPicker(); else pkRefresh(); } });
  } else if (!med) pkRefresh();
}
function pendingHTML(v) {
  const list = v.pendingMeds || [];
  return list.length ? `<ul class="pending">${list.map((m, i) => `<li><span><b>${esc(m.label)}</b><span class="pk-sub">${esc(m.text)}</span></span><button class="btn btn-quiet btn-small" data-unpend="${i}" aria-label="Remove ${esc(m.label)}">Remove</button></li>`).join("")}</ul>` : "";
}
async function addPending(v) {
  const list = v.pendingMeds || []; if (!list.length) return;
  const have = new Set(v.report.medication_views.map(m => m.product_id)), add = list.filter(m => !have.has(m.product_id)), already = list.filter(m => have.has(m.product_id));
  v.pendingMeds = [];
  if (add.length) {
    try { v.report = adapt.report(await api.resolve(v.enc, v.report, add.map(m => ({ action: "add_medicine", target: "new", value: m.value, reason: "Added by the doctor." })))); }
    catch (x) { v.pendingMeds = add; toast(`Couldn't add ${add.map(m => m.label).join(", ")}: ${x.message}`); return; }
  }
  toast([add.length ? `Added ${add.length === 1 ? add[0].label : add.length + " medicines"} you picked.` : "", already.length ? `${already.map(m => m.label).join(", ")} ${already.length === 1 ? "was" : "were"} already in the draft.` : ""].filter(Boolean).join(" "));
}
async function showReport(v) {
  if (!v.ready || v.phase === "review") return;
  v.report = v.ready; v.ready = null; const picked = (v.pendingMeds || []).length;
  await addPending(v); v.phase = "review"; v.reveal = true; renderVisit(); refreshRows(); if (!picked) toast("Draft report is ready.");
}
function medsDone() {
  const v = state.visit; if (!v || v.phase === "review") return;
  v.medsDone = true; v.picker = null;
  if (v.ready) showReport(v); else renderVisit();
}
function closePicker() { const v = state.visit; if (v) v.picker = null; drawPicker(); }
function pkStart(p, o, current) {
  const s = current?.raw_schedule;
  const slots = s?.type === "grid" ? "maen".split("").filter(k => Number(s[k]) > 0).join("") : "";
  const times = s?.type === "as_needed" ? "sos" : slots ? String(slots.length) : s?.type === "frequency" ? String(Math.min(s.times, 4)) : o.once_daily ? "1" : "2";
  const days = current?.duration ? daysOf(current.duration) : 5, unit = unitOf(o);
  const doses = unit === "mL" ? ["2.5", "5", "7.5", "10", "15"] : ["0.5", "1", "2", "3", "4"];
  const dose = current?.dose?.amount || (unit === "mL" ? "5" : "1");
  const when = slots && slots.length === Number(times) && PK_WHEN[times].includes(slots) ? slots
    : times === "1" && PK_ONCE[o.once_daily] ? PK_ONCE[o.once_daily] : PK_WHEN[times][0];
  p.chosen = o; p.row = 0;
  p.rows = [
    { key: "days", label: "Days", values: [...new Set([...PK_DAYS, days])].sort((a, b) => a - b), value: days, text: d => `${d} day${d > 1 ? "s" : ""}` },
    { key: "times", label: "Times a day", values: PK_TIMES.map(t => t[0]), value: times, text: t => Object.fromEntries(PK_TIMES)[t] },
    { key: "when", label: "Which time", values: PK_WHEN[times], value: when, text: pkWhenText },
    { key: "dose", label: "Dose", values: [...new Set([...doses, dose])], value: dose, text: d => `${d === "0.5" ? "½" : d} ${unit}${unit !== "mL" && Number(d) > 1 ? "s" : ""}` },
    { key: "food", label: "Food", values: PK_FOOD.map(f => f[0]), value: current ? (current.food || "") : (o.food || ""), text: f => Object.fromEntries(PK_FOOD)[f] },
  ];
}
function pkSet(p, r, value) {
  r.value = value;
  if (r.key === "times") { const w = p.rows[2]; w.values = PK_WHEN[value]; w.value = value === "1" && PK_ONCE[p.chosen.once_daily] ? PK_ONCE[p.chosen.once_daily] : PK_WHEN[value][0]; }
}
let pkTimer;
function pkRefresh() {
  const v = state.visit, p = v?.picker; if (!p || p.chosen) return;
  const q = p.q.trim().toLowerCase(), common = (v.shortlists?.[v.enc]?.items || []).filter(o => !p.taken.includes(o.product_id)
    && (!q || `${o.label} ${o.composition || ""} ${o.group || ""}`.toLowerCase().includes(q)));
  p.options = common; p.active = 0; pkDrawList();
  clearTimeout(pkTimer);
  if (q.length < 2) return;
  pkTimer = setTimeout(async () => {
    try {
      const found = items(await api.catalog(q)), seen = new Set(common.map(o => o.product_id));
      if (state.visit?.picker !== p || p.chosen || p.q.trim().toLowerCase() !== q) return;
      p.options = [...common, ...found.filter(x => !seen.has(x.id ?? x.product_id)).map(x => ({ product_id: x.id ?? x.product_id, label: x.label || x.name,
        composition: x.composition || "", form: x.form, food: x.food, once_daily: x.once_daily, why: x.stock ? "Pharmacy: " + STOCK_TEXT[x.stock.status] : "" }))];
      p.active = Math.min(p.active, Math.max(p.options.length - 1, 0)); pkDrawList();
    } catch (x) { toast(x.message); }
  }, 200);
}
function pkDrawList() {
  const v = state.visit, p = v?.picker, ul = $("#pkList"); if (!p || !ul) return;
  const loaded = v.shortlists?.[v.enc];
  ul.innerHTML = p.options.map((o, i) => `<li class="pk-item${i === p.active ? " active" : ""}" role="option" aria-selected="${i === p.active}" data-pk="${i}">
      <span>${o.group ? `<span class="chip pk-group">${esc(o.group)}</span>` : ""}<b>${esc(o.label)}</b></span><span class="pk-sub">${esc([o.composition, o.why].filter(Boolean).join(" · "))}</span></li>`).join("")
    || `<li class="hint m0">${p.q.trim().length > 1 ? "Searching…" : loaded ? "No common choices for this visit. Type a name." : "Loading the common choices…"}</li>`;
  ul.querySelector(".active")?.scrollIntoView({ block: "nearest" });
}
function drawPicker() {
  const v = state.visit, p = v?.picker, host = $("#pickerHost"); if (!host) return;
  if (!p) { host.innerHTML = ""; return; }
  if (!p.chosen) {
    const conditions = v.shortlists?.[v.enc]?.conditions || [];
    host.innerHTML = `<div class="picker" id="picker">
      <div class="pk-head"><b>Medicine ${p.number}</b><span class="hint m0">Enter adds it and opens the next · Esc when done</span></div>
      ${conditions.length ? `<p class="hint m0">Common for ${esc(conditions.slice(0, 4).join(", "))}</p>` : ""}
      <input class="input" id="pkQ" type="search" autocomplete="off" aria-label="Find a medicine" placeholder="Type a medicine, or press ↓ for the common choices" value="${esc(p.q)}">
      <ul class="pk-list" id="pkList" role="listbox" aria-label="Medicines"></ul>
      <p class="pk-hint">↓ ↑ choose · Enter pick · Esc close</p></div>`;
    const input = $("#pkQ"); input.oninput = () => { p.q = input.value; pkRefresh(); };
    pkDrawList(); input.focus();
    return;
  }
  host.innerHTML = `<div class="picker" id="picker" tabindex="-1" aria-label="Instructions for ${esc(p.chosen.label)}">
    <div class="pk-chosen"><b>${esc(p.chosen.label)}</b><span class="pk-sub">${esc(p.chosen.composition || "")}</span></div>
    ${p.rows.map((r, i) => `<div class="pk-row${i === p.row ? " active" : ""}"><span class="pk-label">${esc(r.label)}</span><div class="pk-opts">
      ${r.values.map(x => `<button type="button" tabindex="-1" class="pk-opt${x === r.value ? " sel" : ""}" data-pkrow="${i}" data-pkval="${esc(String(x))}">${esc(r.text(x))}</button>`).join("")}</div></div>`).join("")}
    <p class="pk-hint">↑ ↓ row · ← → change · Enter ${p.med ? "save" : "add"} · Esc ${p.med ? "close" : "back"}</p></div>`;
  host.querySelector(".pk-row.active .sel")?.scrollIntoView({ block: "nearest", inline: "nearest" });
  $("#picker").focus({ preventScroll: true });
}
function pkSave() {
  const v = state.visit, p = v.picker, get = k => p.rows.find(r => r.key === k).value, when = get("when"), amount = get("dose");
  const dose = { amount, unit: unitOf(p.chosen) }, food = get("food"), duration = { value: get("days"), unit: "day" };
  const schedule = get("times") === "sos" ? { type: "as_needed" } : { type: "grid", ...Object.fromEntries(["m", "a", "e", "n"].map(k => [k, when.includes(k) ? amount : "0"])) };
  if (!p.med && v.phase !== "review") {
    // The draft isn't here yet: keep the medicine, show it, and open the next one (runbook D-137).
    const text = [`${amount} ${dose.unit}`, get("times") === "sos" ? "when needed" : pkWhenText(when).toLowerCase(), food ? Object.fromEntries(PK_FOOD)[food].toLowerCase() : "", `${duration.value} day${duration.value > 1 ? "s" : ""}`].filter(Boolean).join(", ");
    v.pendingMeds = [...(v.pendingMeds || []), { product_id: p.chosen.product_id, label: p.chosen.label, text, value: { product_id: p.chosen.product_id, dose, schedule, food, duration } }];
    v.picker = null; const list = $("#pendingMeds"); if (list) list.innerHTML = pendingHTML(v); openPicker(); return;
  }
  if (!p.med) {
    // Adding one opens the picker again for the next medicine, until Esc.
    v.picker = null; v.chainPicker = true;
    return applyFix([{ action: "add_medicine", target: "new", value: { product_id: p.chosen.product_id, dose, schedule, food, duration }, reason: "Added by the doctor." }]);
  }
  const m = p.med, changes = [];
  if (m.dose?.amount !== dose.amount || m.dose?.unit !== dose.unit) changes.push({ action: "set_dose", value: dose, reason: "Dose set by the doctor." });
  if (JSON.stringify(m.raw_schedule) !== JSON.stringify(schedule)) changes.push({ action: "set_timing", value: { schedule }, reason: "Timing set by the doctor." });
  if (food && food !== m.food) changes.push({ action: "set_food", value: { food }, reason: "Food timing set by the doctor." });
  if (daysOf(m.duration) !== duration.value) changes.push({ action: "set_duration", value: duration, reason: "Duration set by the doctor." });
  v.picker = null;
  if (!changes.length) { drawPicker(); return toast("Nothing changed."); }
  applyFix(changes.map(c => ({ ...c, target: m.id })));
}
document.addEventListener("keydown", e => {
  const v = state.visit, p = v?.picker;
  if (!p) {
    // Space opens the picker on the review screen, unless the doctor is typing or has a button or link selected.
    const tag = document.activeElement?.tagName;
    if (e.key === " " && !e.ctrlKey && !e.metaKey && !e.altKey && !e.shiftKey && PICKING.includes(v?.phase) && $("#pickerHost")
        && !["INPUT", "TEXTAREA", "SELECT", "BUTTON", "A", "SUMMARY"].includes(tag) && !document.querySelector("dialog[open]")) {
      e.preventDefault(); openPicker();
    }
    return;
  }
  if (!e.target.closest?.("#picker")) return;
  if (!p.chosen) {
    if (e.key === "ArrowDown") { e.preventDefault(); p.active = Math.min(p.active + 1, p.options.length - 1); pkDrawList(); }
    else if (e.key === "ArrowUp") { e.preventDefault(); p.active = Math.max(p.active - 1, 0); pkDrawList(); }
    else if (e.key === "Enter") { e.preventDefault(); if (p.options[p.active]) { pkStart(p, p.options[p.active]); drawPicker(); } }
    else if (e.key === "Escape") { e.preventDefault(); if (v.phase === "review") closePicker(); else medsDone(); }
    // The space that opened the picker, or one pressed before typing, shows the common choices instead of a blank.
    else if (e.key === " " && !e.target.value) e.preventDefault();
    return;
  }
  const r = p.rows[p.row], i = r.values.indexOf(r.value);
  if (e.key === "ArrowDown") { e.preventDefault(); p.row = (p.row + 1) % p.rows.length; drawPicker(); }
  else if (e.key === "ArrowUp") { e.preventDefault(); p.row = (p.row + p.rows.length - 1) % p.rows.length; drawPicker(); }
  else if (e.key === "ArrowRight") { e.preventDefault(); pkSet(p, r, r.values[Math.min(i + 1, r.values.length - 1)]); drawPicker(); }
  else if (e.key === "ArrowLeft") { e.preventDefault(); pkSet(p, r, r.values[Math.max(i - 1, 0)]); drawPicker(); }
  else if (e.key === "Enter") { e.preventDefault(); pkSave(); }
  else if (e.key === "Escape") { e.preventDefault(); if (p.med) closePicker(); else { p.chosen = null; drawPicker(); } }
});
document.addEventListener("mousedown", e => {
  const p = state.visit?.picker; if (!p) return;
  const item = e.target.closest("[data-pk]"), opt = e.target.closest("[data-pkrow]");
  if (item) { e.preventDefault(); const o = p.options[+item.dataset.pk]; if (o) { pkStart(p, o); drawPicker(); } }
  else if (opt) {
    e.preventDefault(); p.row = +opt.dataset.pkrow; const r = p.rows[p.row];
    pkSet(p, r, r.values.find(x => String(x) === opt.dataset.pkval)); drawPicker();
  }
});
function wireReport(box, r, editable) {
  box.querySelectorAll(".sent").forEach(b => b.onclick = () => {
    const sec = b.closest(".rgroup"), ev = sec.querySelector(".evidence"), open = b.getAttribute("aria-expanded") === "true";
    box.querySelectorAll(".sent").forEach(x => x.setAttribute("aria-expanded", "false")); box.querySelectorAll(".evidence").forEach(x => x.hidden = true);
    if (open) return;
    b.setAttribute("aria-expanded", "true");
    const line = r.report_groups.flatMap(g => g.lines).find(l => l.ref === b.dataset.ref);
    const found = (line?.cites || []).map(id => r.findings[id]).filter(Boolean);
    ev.innerHTML = `<h5>What was heard</h5><ul>${found.map(f => `<li><q>${esc(f.quote)}</q> <span class="chip ${f.assertion === "absent" ? "muted" : "ok"}">${f.assertion === "absent" ? "Said as absent" : "Said as present"}</span>${f.certainty && f.certainty !== "stated" ? ` <span class="chip warn">${esc(cap(f.certainty))}</span>` : ""}</li>`).join("") || "<li>No direct quote for this sentence.</li>"}</ul>
      ${editable ? `<div class="row mt"><button class="btn btn-line btn-small" data-line="edit">Edit sentence</button><button class="btn btn-quiet btn-small danger" data-line="remove">Remove sentence</button></div>` : ""}`;
    ev.hidden = false;
    if (!editable) return;
    $("[data-line=remove]", ev).onclick = e => applyFix([{ action: "remove_line", target: line.ref, reason: "Removed by the doctor." }], e.currentTarget);
    $("[data-line=edit]", ev).onclick = () => {
      ev.innerHTML = `<label class="field m0"><span>Edit sentence</span><textarea class="textarea short" id="lineText">${esc(line.text)}</textarea></label><div class="row mt"><button class="btn btn-dark btn-small" id="lineSave">Save changes</button></div>`;
      $("#lineText").focus();
      $("#lineSave").onclick = e => { const text = $("#lineText").value.trim(); if (text) applyFix([{ action: "edit_line", target: line.ref, value: text, reason: "Edited by the doctor." }], e.currentTarget); };
    };
  });
  if (!editable) return;
  box.querySelectorAll("[data-edit]").forEach(b => b.onclick = () => openPicker(r.medication_views.find(m => m.id === b.dataset.edit)));
  box.querySelectorAll("[data-std]").forEach(b => b.onclick = () => {
    const m = r.medication_views.find(x => x.id === b.dataset.std);
    applyFix(m.standard.map(p => ({ action: p.action, target: m.id, value: p.value, reason: p.reason })), b);
  });
  box.querySelectorAll("[data-swap]").forEach(b => b.onclick = e => {
    e.stopPropagation();
    applyFix([{ action: "choose_product", target: b.dataset.swap, value: { product_id: b.dataset.product }, reason: `${STOCK_TEXT[b.dataset.status]} at the hospital pharmacy; changed to ${b.dataset.label}, same composition.` }], b);
  });
  const f = $("#medEdit");
  if (f) {
    f.prn.onchange = () => f.querySelectorAll("[name=slot]").forEach(x => x.disabled = f.prn.checked);
    f.onsubmit = e => {
      e.preventDefault();
      const m = f.dataset.med === "__new" ? state.visit.newMed : r.medication_views.find(x => x.id === f.dataset.med), days = parseInt(f.days.value, 10), er = $("#editErr");
      const slots = [0, 1, 2, 3].map(i => f.querySelector(`[name=slot][value="${i}"]`).checked ? 1 : 0);
      if (!f.prn.checked && !slots.some(Boolean)) { er.hidden = false; er.textContent = "Tick at least one time, or choose When needed."; return; }
      if (!(days > 0)) { er.hidden = false; er.textContent = "Enter the number of days."; f.days.focus(); return; }
      const dose = { amount: f.dose.value, unit: unitOf(m) }, food = f.food.value;
      const schedule = f.prn.checked ? { type: "as_needed" } : { type: "grid", ...Object.fromEntries(["m", "a", "e", "n"].map((k, i) => [k, slots[i] ? f.dose.value : "0"])) };
      if (m.id === "__new") {
        if (!food) { er.hidden = false; er.textContent = "Choose when to take it with food."; return; }
        Object.assign(state.visit, { editing: null, newMed: null, adding: false });
        return applyFix([{ action: "add_medicine", target: "new", value: { product_id: m.product_id, dose, schedule, food, duration: { value: days, unit: "day" } }, reason: "Added by the doctor." }], f.querySelector("[type=submit]"));
      }
      const changes = [];
      if (m.dose?.amount !== dose.amount || m.dose?.unit !== dose.unit) changes.push({ action: "set_dose", value: dose, reason: "Dose set by the doctor." });
      if (JSON.stringify(m.raw_schedule) !== JSON.stringify(schedule)) changes.push({ action: "set_timing", value: { schedule }, reason: "Timing set by the doctor." });
      if (food && food !== m.food) changes.push({ action: "set_food", value: { food }, reason: "Food timing set by the doctor." });
      if (daysOf(m.duration) !== days) changes.push({ action: "set_duration", value: { value: days, unit: "day" }, reason: "Duration set by the doctor." });
      state.visit.editing = null;
      if (!changes.length) { renderVisit(); return toast("Nothing changed."); }
      applyFix(changes.map(c => ({ ...c, target: m.id })), f.querySelector("[type=submit]"));
    };
  }
}
async function applyFix(resolutions, btn) {
  const v = state.visit;
  if (btn) { btn.disabled = true; btn.textContent = "Saving"; }
  try { v.report = adapt.report(await api.resolve(v.enc, v.report, resolutions)); renderVisit(); refreshRows(); toast(`Saved. This is now version ${v.report.version}.`); }
  catch (x) {
    if (x.code === "version_conflict") { v.report = adapt.report(await api.report(v.enc)); renderVisit(); toast(x.message); }
    else { toast(x.message); if (btn) { btn.disabled = false; btn.textContent = "Try again"; } }
  }
}
async function approve() {
  const v = state.visit, b = $("#approveBtn");
  b.disabled = true; b.textContent = "Approving";
  try { v.report = adapt.report(await api.approve(v.enc, v.report)); v.phase = "approved"; v.justApproved = true; renderVisit(); refreshRows(); pollFiles(1500); }
  catch (x) {
    toast(x.message); b.disabled = false; b.textContent = "Approve report";
    if (x.code === "version_conflict" || x.code === "approval_blocked") { v.report = adapt.report(await api.report(v.enc)); renderVisit(); }
  }
}

/* -------- Approved: files and WhatsApp delivery -------- */
const DELIVERY = { pending: [0, "Queued"], queued: [0, "Queued"], waiting: [0, "Waiting for the patient to message first"], waiting_window: [0, "Waiting for the patient to message first"], waiting_artifact: [0, "Waiting for the PDF"], waiting_for_window: [0, "Waiting for the patient to message first"], waiting_for_artifact: [0, "Waiting for the PDF"], accepted: [1, "Accepted by WhatsApp"], sent: [1, "Sent"], delivered: [2, "Delivered"], read: [3, "Read"], failed: [-1, "Couldn't be delivered"], cancelled: [-1, "Cancelled"] };
function deliveryHTML(jobs, fn) {
  if (!jobs) return "";
  if (!jobs.length) return `<section class="deliver"><h4><span class="wa-badge small">${ICON.wa}</span>WhatsApp</h4><p class="hint">Nothing is queued for ${fn}. Check their WhatsApp agreement and number.</p></section>`;
  const names = ["Queued", "Sent", "Delivered", "Read"], failed = jobs.some(j => DELIVERY[j.status]?.[0] === -1);
  return `<section class="deliver" aria-label="WhatsApp delivery"><h4><span class="wa-badge small">${ICON.wa}</span>Sending to ${fn} on WhatsApp</h4>
    ${jobs.map(j => { const [n, word] = DELIVERY[j.status] || [0, cap(j.status)]; return `<div class="dline"><div class="dhead"><b>${{ pdf: "Prescription PDF", voice: "Prescription voice note", voice_option: "Voice note button" }[j.kind] || "Message"}</b><span class="${n < 0 ? "bad" : ""}">${esc(word)}</span></div>
      <ol class="dtrack ${n < 0 ? "failed" : ""}" aria-hidden="true">${names.map((s, i) => `<li class="${i <= n ? "on" : ""}">${s}</li>`).join("")}</ol></div>`; }).join("")}
    ${failed ? `<button class="btn btn-dark btn-small" data-act="retry-delivery">Try sending again</button>` : ""}</section>`;
}
function renderApproved(box) {
  const v = state.visit, r = v.report, a = r.approval || {}, fn = esc(first(state.patient.name));
  const arts = r.artifacts || [], label = { pdf: ["Prescription and report", "PDF", ICON.pdf], fhir_bundles: ["Health record (FHIR)", "JSON", ICON.json], fhir_json: ["Health record (FHIR)", "JSON", ICON.json], fhir: ["Health record (FHIR)", "JSON", ICON.json] };
  box.innerHTML = stepper(3) + `
    <div class="done-hero">
      <div class="seal${v.justApproved ? "" : " still"}" aria-hidden="true"><svg viewBox="0 0 72 72"><circle cx="36" cy="36" r="36"/><path d="M22 37l9 9 19-21"/></svg></div>
      <div><h3>${fn}'s report is approved</h3><p class="hint nomargin">Approved by ${esc(a.approved_by || "")}${a.approved_at ? " at " + fmtTime(a.approved_at) : ""}. Version ${esc(r.version)}.</p></div>
      <div class="row pushright"><button class="btn btn-line" data-act="new-visit">${ICON.mic}Start another visit</button><a class="btn btn-sun" href="#/followup/${esc(v.enc)}">${ICON.chat}Open follow-up</a></div>
    </div>
    ${deliveryHTML(v.jobs, fn)}
    <div class="files">
      ${arts.map(f => { const [t, kind, ic] = label[f.kind] || [f.kind, "", ICON.json]; return `<div class="file"><span class="ic">${ic}</span><span><b>${t}</b><span>${f.state === "ready" ? kind + ", ready" : f.state === "failed" ? "Couldn't be made" : "Being prepared"}</span></span>
        ${f.state === "ready" ? `<button class="btn btn-dark btn-small" data-art="${esc(f.id)}" data-kind="${esc(f.kind)}">Download</button>` : f.state === "failed" ? "" : `<span class="spinner ink" aria-label="Preparing"></span>`}</div>`; }).join("")}
      <div class="file"><span class="ic">${ICON.json}</span><span><b>Report data</b><span>JSON, ready</span></span><button class="btn btn-line btn-small" data-act="json">Download</button></div>
    </div>
    <details class="more"><summary class="btn btn-quiet">Show the approved report</summary>${reportHTML(r, false)}</details>`;
  v.justApproved = false;
  box.querySelectorAll("[data-art]").forEach(b => b.onclick = () => downloadArtifact(b.dataset.art, b.dataset.kind));
  wireReport(box, r, false);
}
function pollFiles(delay) {
  stopPolling();
  const v = state.visit, pid = state.selected;
  state.poll = setTimeout(async () => {
    if (state.selected !== pid || v.phase !== "approved") return;
    try {
      const [arts, jobs] = await Promise.all([api.artifacts(v.enc), api.deliveries(v.enc).catch(() => null)]);
      const open = $("details.more")?.open;
      v.report.artifacts = arts; v.jobs = jobs || v.jobs; renderVisit();
      if (open) $("details.more").open = true;
      const busy = v.report.artifacts.some(a => ["pending", "running"].includes(a.state)) || (v.jobs || []).some(j => !["read", "failed", "cancelled"].includes(j.status));
      if (busy) pollFiles(2500);
    } catch (_) { pollFiles(5000); }
  }, delay);
}

/* =================================================================
   Follow-ups
   ================================================================= */
async function renderTasks() {
  view().innerHTML = `<div class="page narrow"><div class="skel tall w40"></div><div class="skel"></div></div>`;
  await loadTasks();
  const all = items(await api.tasks());
  const open = all.filter(t => t.status !== "done"), done = all.filter(t => t.status === "done");
  const row = t => `<li class="task ${t.status === "done" ? "is-done" : ""}"><a class="grow" href="#/followup/${esc(t.encounter_id)}"><b>${esc(t.title)}</b><span>${esc(t.patient_name || "Patient")}${t.detail ? `: ${esc(t.detail)}` : ""}</span></a>
    ${t.status === "done" ? `<span class="chip ok">Done</span>` : `<button class="btn btn-line btn-small" data-done="${esc(t.id)}" data-enc="${esc(t.encounter_id)}">Mark done</button>`}</li>`;
  view().innerHTML = `<div class="page narrow"><header class="page-head"><h1>Follow-ups</h1><p>What your patients need from you after their visit.</p></header>
    ${open.length ? `<ul class="panel tasks">${open.map(row).join("")}</ul>` : `<div class="panel first"><h3>You're all caught up</h3><p>New tasks appear here when a patient's follow-up needs you.</p></div>`}
    ${done.length ? `<h2 class="sect">Done</h2><ul class="panel tasks">${done.map(row).join("")}</ul>` : ""}</div>`;
  $$("[data-done]").forEach(b => b.onclick = async () => {
    b.disabled = true;
    try { await api.taskDone(b.dataset.enc, b.dataset.done); toast("Task marked done."); await renderTasks(); }
    catch (x) { toast(x.message); b.disabled = false; }
  });
  swap();
}
async function renderFollowup(enc) {
  const encounter = await api.encounter(enc), p = adapt.patient(encounter.patient || {});
  const [fu, memory, tasks] = await Promise.all([api.followup(enc), api.followMemory(enc).catch(() => ({})), api.tasks().catch(() => [])]);
  const fn = esc(first(p.name)), msgs = fu.messages || [], last = msgs.at(-1), buttons = last?.buttons || [];
  const myTasks = items(tasks).filter(t => t.encounter_id === enc);
  const active = fu.status === "active" || msgs.length;
  const wasThere = $("#thread");
  view().innerHTML = `<div class="page wide">
    <header class="page-head"><a class="link-btn" href="#/patients/${esc(p.id)}">Back to ${fn}</a><h1>Follow-up with ${esc(p.name)}</h1><p>${fu.status_label ? esc(fu.status_label) : "Messages, reports and tasks after the visit."}</p></header>
    <div class="fgrid">
      <section class="panel chatwrap" aria-label="WhatsApp conversation">
        <div class="ph"><div class="wa-head"><span class="wa-badge">${ICON.wa}</span><h3>Conversation</h3></div></div>
        ${active ? `<ol class="thread" id="thread" aria-live="polite">${msgs.map(m => `<li class="msg ${m.direction === "in" ? "in" : "out"}"><p>${esc(m.text)}</p><small>${m.at ? fmtTime(m.at) : ""}</small></li>`).join("")}</ol>
        ${fu.simulated ? `<div class="sim">
          ${buttons.length ? `<div class="row tight">${buttons.map(b => `<button class="btn btn-line btn-small" data-reply="${esc(b.id ?? b)}">${esc(b.title ?? b)}</button>`).join("")}</div>` : ""}
          <form id="simForm" class="row"><label class="grow"><span class="sr">Reply as ${fn}</span><input class="input" id="simText" placeholder="Reply as ${fn} (demo)" autocomplete="off"></label><button class="btn btn-dark">Send</button></form>
          <div class="row tight"><button class="btn btn-quiet btn-small" id="simClock">Move demo clock forward</button>
          <label class="btn btn-quiet btn-small" for="docIn">Send a report as ${fn}</label><input class="sr" type="file" id="docIn" accept="application/pdf,image/*"></div>
        </div>` : `<p class="hint">Replies arrive from ${fn}'s WhatsApp.</p>`}` : `<div class="first"><p>${esc(fu.reason || "Follow-up hasn't started for this visit.")}</p>${fu.available === false ? "" : `<button class="btn btn-sun mt" id="fuStart">${ICON.chat}Start follow-up</button>`}</div>`}
      </section>
      <div class="stack">
        <section class="panel"><h3>Tasks for you</h3>${myTasks.length ? `<ul class="tasks bare">${myTasks.map(t => `<li class="task ${t.status === "done" ? "is-done" : ""}"><span class="grow"><b>${esc(t.title)}</b>${t.detail ? `<span>${esc(t.detail)}</span>` : ""}</span>${t.status === "done" ? `<span class="chip ok">Done</span>` : `<button class="btn btn-line btn-small" data-done="${esc(t.id)}">Mark done</button>`}</li>`).join("")}</ul>` : `<p class="muted">No tasks for this visit.</p>`}</section>
        <section class="panel"><h3>What we remember</h3>${(memory.items || []).length ? `<ul class="plain">${memory.items.map(m => `<li>${esc(m.text ?? m)}</li>`).join("")}</ul>` : `<p class="muted">Nothing yet.</p>`}</section>
        <section class="panel"><h3>Reports from ${fn}</h3>${(memory.documents || []).length ? uploadsHTML(memory.documents) : `<p class="muted">No reports uploaded.</p>`}</section>
      </div>
    </div></div>`;
  const reload = () => renderFollowup(enc);
  const send = async body => { try { await api.followSend(enc, body); await reload(); } catch (x) { toast(x.message); } };
  const thread = $("#thread"); if (thread) thread.scrollTop = thread.scrollHeight;
  $("#fuStart")?.addEventListener("click", async e => { e.currentTarget.disabled = true; try { await api.followStart(enc); await reload(); } catch (x) { toast(x.message); } });
  $("#simForm")?.addEventListener("submit", e => { e.preventDefault(); const t = $("#simText").value.trim(); if (t) send({ text: t }); });
  $$("[data-reply]").forEach(b => b.onclick = () => send({ button: b.dataset.reply }));
  $("#simClock")?.addEventListener("click", async () => { try { await api.followAdvance(enc); toast("Demo clock moved forward."); await reload(); } catch (x) { toast(x.message); } });
  $("#docIn")?.addEventListener("change", async e => { const f = e.target.files[0]; if (!f) return; if (f.size > 10 * 1024 * 1024) return toast("That file is over 10 MB."); try { await api.followDoc(enc, f); toast("Report sent."); await reload(); } catch (x) { toast(x.message); } });
  $$("[data-done]").forEach(b => b.onclick = async () => { b.disabled = true; try { await api.taskDone(enc, b.dataset.done); await loadTasks(); await reload(); } catch (x) { toast(x.message); b.disabled = false; } });
  $$("[data-review]").forEach(b => b.onclick = () => markReviewed(b, reload));
  if (!wasThere) swap();
  stopPolling();
  if (active) state.poll = setTimeout(() => { if (location.hash === `#/followup/${enc}` && document.activeElement?.id !== "simText") reload(); }, 8000);
}
/* =================================================================
   Hospital pharmacy stock (runbook D-126 to D-128)
   ================================================================= */
async function renderPharmacy() {
  view().innerHTML = `<div class="page narrow"><div class="skel tall w40"></div><div class="skel"></div></div>`;
  const data = await api.pharmacy();
  const MATCH = { matched: ["ok", "Matched"], added: ["iris", "Added to clinic list"], unmatched: ["risk", "Not matched"] };
  const table = rows => `<div class="meds-wrap"><table class="meds stock-table"><thead><tr><th scope="col">Pharmacy item</th><th scope="col">Catalogue medicine</th><th scope="col">Match</th><th class="s" scope="col">Qty</th><th scope="col">Stock</th></tr></thead>
    <tbody>${rows.map(i => `<tr><td><span class="mname">${esc(i.item_name)}</span><span class="mcomp">${esc(i.composition || "")}</span></td><td>${esc(i.product_label || "")}</td>
      <td><span class="chip ${MATCH[i.match_state][0]}">${MATCH[i.match_state][1]}</span></td><td class="s">${esc(i.quantity)}</td><td><span class="chip ${STOCK_CLS[i.status]}">${STOCK_TEXT[i.status]}</span></td></tr>`).join("")}</tbody></table></div>`;
  const attention = data.imported ? data.items.filter(i => i.status !== "in_stock" || i.match_state === "unmatched") : [];
  view().innerHTML = `<div class="page wide"><header class="page-head"><h1>Hospital pharmacy</h1>
      <p>Upload the pharmacy's stock export. Doctors then see stock on each prescription line and can switch an unavailable medicine to one in stock with the same composition. Stock never changes a prescription by itself.</p></header>
    <section class="panel addform" aria-label="Upload stock"><h3>Upload stock</h3>
      <p class="hint">A CSV with the item name and quantity. Item code, composition and reorder level help matching. Each upload replaces the last. Made-up data only.</p>
      <div class="row"><label class="btn btn-line" for="stockFile">${ICON.upload}Choose CSV</label><input class="sr" type="file" id="stockFile" accept=".csv,text/csv"><span class="hint m0" id="stockName">No file chosen</span><button class="btn btn-dark" id="stockGo" disabled>Upload stock</button></div>
      <p class="err" id="stockErr" role="alert"></p></section>
    ${data.imported ? `<section class="panel"><div class="ph"><h3>Stock as of ${esc(fmtWhen(data.as_of))}</h3><p>${esc(data.filename)}</p></div>
      <p>${esc(data.rows)} items, ${esc(data.matched - (data.added || 0))} matched to the catalogue${data.added ? `, ${esc(data.added)} added to the clinic list for review` : ""}${data.unmatched ? `, ${esc(data.unmatched)} not matched` : ""}.</p>
      <div class="row tight">${["in_stock", "low", "out"].map(k => `<span class="chip ${STOCK_CLS[k]}">${STOCK_TEXT[k]}: ${esc(data.counts[k])}</span>`).join("")}</div></section>
    ${attention.length ? `<section class="panel"><div class="ph"><h3>Needs attention</h3><p>${attention.length} ${attention.length === 1 ? "item" : "items"}</p></div>${table(attention)}</section>` : ""}
    <details class="panel more"><summary class="btn btn-quiet">Show all ${esc(data.items.length)} items</summary>${table(data.items)}</details>`
    : `<div class="panel first"><h3>No stock uploaded yet</h3><p>Once a file is uploaded, prescriptions show what the pharmacy has.</p></div>`}</div>`;
  const file = $("#stockFile"), go = $("#stockGo");
  file.onchange = () => { $("#stockName").textContent = file.files[0]?.name || "No file chosen"; go.disabled = !file.files[0]; };
  go.onclick = async () => {
    const f = file.files[0]; if (!f) return;
    if (f.size > 2000000) { $("#stockErr").textContent = "That file is over 2 MB. Export only medicines."; return; }
    go.disabled = true; go.textContent = "Uploading";
    try { await api.uploadStock(f.name, await f.text()); toast("Stock updated."); await renderPharmacy(); }
    catch (x) { $("#stockErr").textContent = x.message; go.disabled = false; go.textContent = "Upload stock"; }
  };
  swap();
}

async function markReviewed(b, then) { b.disabled = true; try { await api.reviewUpload(b.dataset.review); toast("Marked as reviewed."); await then(); } catch (x) { toast(x.message); b.disabled = false; } }

/* =================================================================
   Reference drawer
   ================================================================= */
const drawer = $("#refDrawer");
$("#refClose").onclick = () => drawer.close();
$("#refForm").onsubmit = async e => {
  e.preventDefault();
  const qv = $("#refQ").value.trim(), out = $("#refResults"); if (!qv) return;
  out.innerHTML = `<div class="skel"></div><div class="skel w80"></div>`;
  try {
    const list = items(await api.knowledge(qv, state.visit?.enc));
    out.innerHTML = list.length ? list.map(r => `<article class="passage"><h3>${esc(r.title || r.source)}</h3><p class="muted">${esc([r.source, r.section].filter(Boolean).join(", "))}</p><p>${esc(r.content)}</p>${/^https:/.test(r.url || "") ? `<a class="link-btn" href="${esc(r.url)}" target="_blank" rel="noopener noreferrer">Open source</a>` : ""}</article>`).join("") : `<p class="hint">Nothing found. Try the generic name.</p>`;
  } catch (x) { out.innerHTML = `<p class="hint warn">${esc(x.message)}</p>`; }
};

/* =================================================================
   Downloads
   ================================================================= */
function saveBlob(blob, name) { const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 1000); }
function downloadJSON(r) { saveBlob(new Blob([JSON.stringify(r, null, 2)], { type: "application/json" }), `${r.patient_id}_${r.date}_v${r.version}_${r.status}.json`); toast("JSON downloaded."); }
function downloadArtifact(id, kind) {
  if (api.downloadUrl) { location.href = api.downloadUrl(id); return; }
  const r = state.visit.report;
  if (kind === "pdf") return printReport(r);
  saveBlob(new Blob([JSON.stringify({ note: "Demo mode. The real FHIR bundle comes from the backend.", report: r }, null, 2)], { type: "application/json" }), `${r.patient_id}_${r.date}_fhir_demo.json`);
}
function printReport(r) {
  const p = state.patient;
  $("#print").innerHTML = `${r.status !== "approved" ? '<div class="wm">DRAFT</div>' : ""}
    <div class="ph"><div><h1>${esc(session.hospital?.name)}</h1><div>${esc(r.clinician || "")}</div></div>
    <div class="ra">Visit ${fmtDate(r.date)}<br>${esc(p.name)}, ${esc(p.age)} y, ${esc(cap(p.sex))}<br>ID ${esc(p.id)}<br>${p.allergies?.status === "known" ? "Allergy: " + esc(p.allergies.items.join(", ")) : p.allergies?.status === "none" ? "No known allergies" : "Allergies not recorded"}</div></div>
    ${r.report_groups.map(g => `<h4>${esc(g.heading)}</h4><p>${g.lines.map(l => esc(l.text)).join(" ")}</p>`).join("")}
    <h4>Medicines</h4><table><thead><tr><th>Medicine</th><th>Morning</th><th>Afternoon</th><th>Evening</th><th>Night</th></tr></thead><tbody>
    ${r.medication_views.map(m => { const s = m.schedule?.kind === "slots" ? m.schedule.slots : null; return `<tr><td><b>${esc(m.label)}</b> (${esc(m.composition)})<br>${esc(medShort(m))}</td>${[0, 1, 2, 3].map(i => `<td>${s ? (s[i] || "–") : i === 0 ? esc(scheduleText(m.schedule)) : ""}</td>`).join("")}</tr>`; }).join("")}
    </tbody></table><p class="foot">Synthetic demo record. ${r.status === "approved" ? "Approved by " + esc(r.approval?.approved_by || "") + "." : "Draft, not approved."}</p>`;
  window.print();
}

function onMainClick(e) {
  const vt = e.target.closest(".visit > button");
  if (vt) return togglePast(vt);
  const past = e.target.closest("[data-past]");
  if (past) {
    const r = past.closest(".visit")._report;
    if (past.dataset.past === "json") return downloadJSON(r);
    const art = r.artifacts?.find(a => a.kind === "pdf" && a.state === "ready");
    return art && api.downloadUrl ? void (location.href = api.downloadUrl(art.id)) : printReport(r);
  }
  const rv = e.target.closest("[data-review]");
  if (rv) return markReviewed(rv, () => openPatient(state.selected));
  const pick = e.target.closest("[data-product]");
  if (pick && !pick.dataset.swap) {
    const v = state.visit, pid = pick.dataset.product;
    if (v.replacing) { const target = v.replacing; Object.assign(v, { adding: false, replacing: null }); return applyFix([{ action: "choose_product", target, value: { product_id: pid }, reason: `Chosen by the doctor: ${pick.dataset.label}.` }], pick); }
    Object.assign(v, { adding: false, editing: "__new", newMed: { id: "__new", product_id: pid, label: pick.dataset.label, composition: pick.dataset.comp, form: pick.dataset.form, food: pick.dataset.food || null, dose: null, schedule: null, duration: null, filled: {} } });
    return renderVisit();
  }
  const unpend = e.target.closest("[data-unpend]");
  if (unpend) { const v = state.visit; v.pendingMeds.splice(+unpend.dataset.unpend, 1); $("#pendingMeds").innerHTML = pendingHTML(v); if (v.picker) v.picker.taken = v.pendingMeds.map(m => m.product_id); return; }
  const act = e.target.closest("[data-act]"); if (!act) return;
  const v = state.visit;
  ({
    "new-visit"() { state.visit = { phase: "idle", language: "hinglish" }; renderPatient(); $("#visit").scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "center" }); },
    type() { v.phase = "typing"; renderVisit(); },
    cancel() { v.phase = "idle"; renderVisit(); },
    "cancel-edit"() { Object.assign(v, { editing: null, newMed: null }); renderVisit(); },
    "remove-med"() { v.editing = null; applyFix([{ action: "remove_medicine", target: act.dataset.med, reason: "Removed by the doctor." }], act); },
    "add-med"() { openPicker(); },
    "meds-done"() { medsDone(); },
    "close-add"() { Object.assign(v, { adding: false, replacing: null }); renderVisit(); },
    async shortlist() { act.disabled = true; act.textContent = "Loading"; try { showPicks(items(await api.shortlist(v.enc))); } catch (x) { toast(x.message); } act.disabled = false; act.textContent = "Show common choices"; },
    json() { downloadJSON(v.report); },
    pdf() { api.previewUrl ? window.open(api.previewUrl(v.enc, v.report.version), "_blank", "noopener") : printReport(v.report); },
    ref() { $("#refResults").innerHTML = ""; drawer.showModal(); $("#refQ").focus(); },
    async "retry-delivery"() { act.disabled = true; try { await api.retryDelivery(v.enc); toast("Sending again."); pollFiles(800); } catch (x) { toast(x.message); act.disabled = false; } }
  })[act.dataset.act]?.();
}
async function togglePast(vt) {
  const li = vt.parentElement, open = li.dataset.open !== "true";
  li.dataset.open = String(open); vt.setAttribute("aria-expanded", String(open));
  const inner = li.querySelector(".inner");
  if (!open || inner.dataset.loaded) return;
  inner.innerHTML = `<div class="skel"></div><div class="skel w70"></div>`;
  try {
    const r = adapt.report(await api.report(li.dataset.enc)); inner.dataset.loaded = "1"; li._report = r;
    inner.innerHTML = reportHTML(r, false) + `<div class="row mt"><button class="btn btn-line btn-small" data-past="pdf">${ICON.pdf}Download PDF</button><button class="btn btn-line btn-small" data-past="json">${ICON.json}Download JSON</button></div>`;
    wireReport(inner, r, false);
  } catch (x) { inner.innerHTML = `<p class="hint warn">${esc(x.message)}</p>`; }
}

/* =================================================================
   Boot
   ================================================================= */
addEventListener("DOMContentLoaded", async () => {
  api = window.VoiceRxMock || live;
  try { session = adapt.session(await api.me()); csrf = session.csrf_token; }
  catch (x) {
    if (x.status === 401) return toLogin();
    $("#app").hidden = false; return showError("ARDAI can't reach the server right now.", () => location.reload());
  }
  $("#app").hidden = false; $("#demoBadge").hidden = !window.VoiceRxMock;
  if (!reduce) { $("#app").classList.add("entering"); setTimeout(() => $("#app").classList.remove("entering"), 520); }
  renderShell();
  // The shared workspace opens on its hospitals, then doctors, then that doctor's patients (runbook D-134).
  // A reload deeper in (a patient, a visit, a follow-up) stays where it was.
  if (session.admin && ["", "#", "#/", "#/patients"].includes(location.hash)) { state.hospital = null; history.replaceState(null, "", "#/workspace"); }
  if (session.doctor) await loadTasks();
  route();
});
