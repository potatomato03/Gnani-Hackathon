// VoiceRx doctor workspace. Plain modules, no build step; served same-origin with the API (DESIGN.md 4.1).
// Every element is built with DOM calls, never innerHTML, so no record text can inject markup.

const root = document.getElementById('root');
let session = null;
const ui = { list: 'all', q: '', patientId: null, pollTimer: null, selectedLine: null, editing: null };

// ---------- Small helpers ----------

function h(tag, props = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === 'class') el.className = value;
    else if (key === 'text') el.textContent = value;
    else if (key.startsWith('on')) el.addEventListener(key.slice(2).toLowerCase(), value);
    else if (key === 'dataset') Object.assign(el.dataset, value);
    else if (value === true) el.setAttribute(key, '');
    else el.setAttribute(key, value);
  }
  for (const kid of kids.flat(Infinity)) {
    if (kid === null || kid === undefined || kid === false) continue;
    el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
  return el;
}

// replaceChildren with nested lists flattened (replaceChildren itself would print a list as "[object …]").
function put(el, ...kids) {
  el.replaceChildren(...kids.flat(Infinity).filter(k => k !== null && k !== undefined && k !== false && k !== ''));
  return el;
}

function svg(path, viewBox = '0 0 24 24') {
  const el = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  el.setAttribute('viewBox', viewBox); el.setAttribute('fill', 'none'); el.setAttribute('stroke', 'currentColor');
  el.setAttribute('stroke-width', '2'); el.setAttribute('stroke-linecap', 'round'); el.setAttribute('stroke-linejoin', 'round');
  for (const d of [].concat(path)) {
    const p = document.createElementNS('http://www.w3.org/2000/svg', 'path'); p.setAttribute('d', d); el.append(p);
  }
  return el;
}
const ICON = {
  search: ['M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14Z', 'm20 20-3.5-3.5'],
  mic: ['M12 15a3 3 0 0 0 3-3V6a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3Z', 'M19 11a7 7 0 0 1-14 0', 'M12 18v3'],
  check: ['M5 12.5 10 17l9-10'],
};

class ApiError extends Error {
  constructor(status, error) { super(error?.message || 'Request failed'); this.status = status; this.code = error?.code; this.detail = error; }
}

async function api(path, { method = 'GET', body } = {}) {
  const headers = { Accept: 'application/json' };
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (method !== 'GET' && session) headers['X-CSRF-Token'] = session.csrf_token;
  const response = await fetch('/api/v1' + path, { method, headers, credentials: 'same-origin',
    body: body === undefined ? undefined : JSON.stringify(body) });
  if (response.status === 204) return null;
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401 && path !== '/me') { session = null; renderLogin(); }
    throw new ApiError(response.status, data.error);
  }
  return data;
}

let toastTimer;
function toast(message, bad = false) {
  const el = document.getElementById('toast');
  el.textContent = message; el.classList.toggle('bad', bad); el.classList.add('show');
  clearTimeout(toastTimer); toastTimer = setTimeout(() => el.classList.remove('show'), bad ? 6000 : 3200);
}
function fail(error) { console.error(error); toast(error.message || 'Something went wrong.', true); }

const initials = name => name.replace(/^Dr\.?\s+/, '').split(/\s+/).map(w => w[0]).slice(0, 2).join('').toUpperCase();
const LANG = { 'hi-IN': 'Hindi', 'en-IN': 'English', 'te-IN': 'Telugu', 'ta-IN': 'Tamil', 'gu-IN': 'Gujarati', hinglish: 'Hinglish',
  hindi: 'Hindi', english: 'English', tamil: 'Tamil', telugu: 'Telugu', gujarati: 'Gujarati' };
function fmtDate(iso) {
  if (!iso) return '';
  return new Date(iso.length === 10 ? iso + 'T00:00:00' : iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });
}
function fmtTime(iso) {
  return new Date(iso).toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Kolkata' }) + ' IST';
}
function allergyChip(p) {
  if (p.allergy_status === 'known') return h('span', { class: 'chip miss', text: 'Allergies: ' + p.allergies.join(', ') });
  if (p.allergy_status === 'nka') return h('span', { class: 'chip ok', text: 'No known allergies' });
  return h('span', { class: 'chip off', text: 'Allergy status unknown' });
}
function stateChip(state, blocking) {
  const map = { open: ['muted', 'Not processed'], processing: ['iris', 'Processing'], failed: ['miss', 'Needs retry'],
    in_review: ['off', blocking ? `Draft · ${blocking} to resolve` : 'Draft · ready to approve'], approved: ['ok', 'Approved'] };
  const [cls, label] = map[state] || ['muted', state];
  return h('span', { class: 'chip ' + cls, text: label });
}

// ---------- Sign-in ----------

async function renderLogin() {
  stopPolling();
  root.replaceChildren();
  const card = h('div', { class: 'auth' }, h('p', { class: 'muted', text: 'Loading…' }));
  root.append(h('section', { class: 'login', 'aria-label': 'Sign in' },
    h('div', { class: 'brand' }, h('span', { class: 'brand-mark', 'aria-hidden': 'true' }), 'VoiceRx'),
    h('div', { class: 'login-body' },
      h('div', { class: 'pitch' },
        h('h1', { text: 'Speak the visit. Check the report. Approve.' }),
        h('p', { class: 'lede', text: 'VoiceRx drafts the visit note and prescription from what was said, shows you every source quote, and flags anything it is unsure of. Nothing reaches a patient until you approve it.' }),
        h('dl', {}, [['Languages offered', 'Hinglish, Hindi, English, Tamil, Telugu, Gujarati'],['Every line', 'Has a source'], ['Sent to patient', 'Only after approval']]
          .map(([term, value]) => h('div', {}, h('dt', { text: term }), h('dd', { text: value }))))),
      card),
    h('div')));
  try {
    const options = await api('/auth/options');
    if (!options.dev_login) {
      card.replaceChildren(h('h2', { text: 'Sign in' }),
        h('p', { class: 'sub', text: "Sign-in with Supabase Auth isn't set up yet, and development sign-in is switched off on this server." }));
      return;
    }
    const { users } = await api('/auth/dev-users');
    const err = h('p', { class: 'err', role: 'alert' });
    card.replaceChildren(
      h('h2', { text: 'Sign in' }),
      h('p', { class: 'sub', text: 'Development sign-in: choose a synthetic doctor. No real patients or credentials.' }),
      h('div', { class: 'doc-pick' }, users.map(u => h('button', { type: 'button', onclick: async () => {
        try { session = await api('/auth/dev-login', { method: 'POST', body: { user_id: u.id } }); startApp(); }
        catch (e) { err.textContent = e.message; }
      } }, h('span', { class: 'avatar doc', text: initials(u.display_name) }),
        h('span', {}, h('b', { text: u.display_name }), h('small', { text: `${u.specialty.replace('_', ' ')} · ${u.organisation_name}` }))))),
      err,
      h('p', { class: 'fine', text: 'Password sign-in arrives with Supabase Auth. This server only lists synthetic doctors.' }));
  } catch (e) { card.replaceChildren(h('p', { class: 'err', text: e.message })); }
}

// ---------- Shell ----------

function startApp() {
  root.replaceChildren();
  const hour = Number(new Date().toLocaleString('en-IN', { hour: 'numeric', hour12: false, timeZone: 'Asia/Kolkata' }));
  const greeting = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening';
  const search = h('input', { class: 'input', type: 'search', placeholder: 'Search by name, MRN or patient ID', 'aria-label': 'Search patients' });
  let searchTimer;
  search.addEventListener('input', () => { clearTimeout(searchTimer); searchTimer = setTimeout(() => { ui.q = search.value; loadPatients(); }, 250); });
  const tabs = h('div', { class: 'tabs', role: 'tablist' }, [['today', "Today's visits"], ['all', 'All patients']].map(([key, label]) =>
    h('button', { type: 'button', role: 'tab', 'aria-selected': String(ui.list === key), onclick: e => {
      ui.list = key; tabs.querySelectorAll('button').forEach(b => b.setAttribute('aria-selected', String(b === e.currentTarget))); loadPatients();
    } }, label)));
  root.append(h('div', { class: 'app' },
    h('header', { class: 'top' },
      h('div', { class: 'brand' }, h('span', { class: 'brand-mark', 'aria-hidden': 'true' }), 'VoiceRx'),
      h('label', { class: 'search' }, svg(ICON.search), search),
      h('div', { class: 'me' },
        h('button', { class: 'btn btn-quiet', type: 'button', onclick: () => { location.hash = '#/followups'; } }, 'Follow-ups'),
        h('button', { class: 'btn btn-quiet', type: 'button', onclick: () => openReference(null) }, 'Reference'),
        h('div', { class: 'who' }, h('b', { text: session.actor.display_name }), h('span', { text: session.scope.organisation_name })),
        h('span', { class: 'avatar doc', text: initials(session.actor.display_name) }),
        h('button', { class: 'btn btn-quiet', type: 'button', onclick: signOut }, 'Sign out'))),
    h('div', { class: 'layout' },
      h('aside', { class: 'side' },
        h('div', { class: 'hello' }, h('h1', { text: `${greeting}, ${session.actor.display_name.split(' ').slice(0, 2).join(' ')}` }),
          h('p', { text: new Date().toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'long', timeZone: 'Asia/Kolkata' }) })),
        tabs, h('ul', { class: 'plist', id: 'plist' })),
      h('main', { class: 'main', id: 'main' }))),
    h('aside', { class: 'drawer', id: 'drawer', 'aria-label': 'Reference information' }));
  window.onhashchange = route;
  loadPatients();
  route();
}

async function signOut() {
  try { await api('/auth/logout', { method: 'POST' }); } catch (e) { /* the session may already be gone */ }
  session = null; location.hash = ''; renderLogin();
}

async function loadPatients() {
  const list = document.getElementById('plist');
  if (!list) return;
  try {
    const data = await api(`/patients?list=${ui.list}&q=${encodeURIComponent(ui.q)}`);
    list.replaceChildren(...(data.items.length ? data.items.map(p => h('li', {},
      h('button', { class: 'pitem', type: 'button', 'aria-current': String(p.id === ui.patientId), onclick: () => { location.hash = '#/patients/' + p.id; } },
        h('span', {},h('span', { class: 'name', text: p.name }),
          h('span', { class: 'why', text: `${p.mrn} · ${p.last_visit ? 'last visit ' + fmtDate(p.last_visit) : 'no visits yet'}` })),
        p.open_state ? stateChip(p.open_state, p.open_blocking) : ''))) :
      [h('li', { class: 'empty-list', text: ui.list === 'today' ? 'No visits started today yet. Open a patient from All patients.' : 'No patients match.' })]));
  } catch (e) { fail(e); }
}

function main() { return document.getElementById('main'); }
function stopPolling() { clearTimeout(ui.pollTimer); ui.pollTimer = null; }

function route() {
  stopPolling();
  ui.cleanup?.(); ui.cleanup = null;
  const [, kind, id] = location.hash.split('/');
  if (kind === 'patients' && id) return showPatient(id);
  if (kind === 'encounters' && id) return showEncounter(id);
  if (kind === 'followup' && id) return showFollowup(id);
  if (kind === 'followups') return showFollowupTasks();
  ui.patientId = null;
  main().replaceChildren(h('div', { class: 'panel first' }, h('h3', { text: 'Choose a patient' }),
    h('p', { text: 'Pick someone from the list to see their visits, or start a new visit for them.' })));
}

// ---------- Patient ----------

async function showPatient(id) {
  ui.patientId = id;
  loadPatients();
  main().replaceChildren(h('p', { class: 'muted', text: 'Loading…' }));
  try {
    const { patient, encounters } = await api('/patients/' + id);
    const age = new Date().getFullYear() - patient.birth_year;
    main().replaceChildren(
      h('div', { class: 'phead' },
        h('div', {}, h('h2', { text: patient.name }), h('ul', { class: 'facts' },
          h('li', { text: `About ${age} years · ${patient.sex === 'F' ? 'Female' : patient.sex === 'M' ? 'Male' : patient.sex}` }),
          h('li', { class: 'mono', text: patient.mrn }), h('li', { text: 'Speaks ' + (LANG[patient.language_pref] || patient.language_pref) }),
          h('li', {}, allergyChip(patient)))),
        h('div', { class: 'actions' }, session.capabilities.capture ?
          h('button', { class: 'btn btn-dark', type: 'button', onclick: () => startVisit(id) }, 'Start a visit') : '')),
      patientCommunicationPanel(patient), patientJourneyPanel(patient.id),
      h('section', { class: 'panel' },
        h('div', { class: 'ph' }, h('h3', { text: 'Visits' }), h('p', { text: encounters.length ? `${encounters.length} on record` : '' })),
        encounters.length ? h('ul', { class: 'visits' }, encounters.map(e => h('li', {},
          h('button', { type: 'button', onclick: () => { location.hash = '#/encounters/' + e.id; } },
            h('span', { class: 'vdate', text: fmtDate(e.visit_date) }),
            h('span', { class: 'vdx', text: (e.diagnoses[0] || e.complaints[0] || (e.state === 'open' ? 'Not processed yet' : '—')) + ' · ' + e.clinician_name }),
            stateChip(e.state, e.blocking))))) :
          h('div', { class: 'first' }, h('p', { text: 'No visits yet. Start one to type or paste the consultation.' }))));
  } catch (e) { fail(e); }
}

async function startVisit(patientId) {
  try {
    const encounter = await api(`/patients/${patientId}/encounters`, { method: 'POST' });
    location.hash = '#/encounters/' + encounter.id;
  } catch (e) { fail(e); }
}

// ---------- Encounter ----------

async function showEncounter(id) {
  main().replaceChildren(h('p', { class: 'muted', text: 'Loading…' }));
  try {
    const encounter = await api('/encounters/' + id);
    ui.patientId = encounter.patient.id;
    loadPatients();
    if (['in_review', 'approved'].includes(encounter.state)) return showReview(encounter);
    if (encounter.state === 'processing' && encounter.run) return showProcessing(encounter, encounter.run);
    return showCapture(encounter);
  } catch (e) { fail(e); }
}

function header(encounter, extra) {
  return [
    h('div', { class: 'crumb' }, h('button', { type: 'button', onclick: () => { location.hash = '#/patients/' + encounter.patient.id; } }, '← ' + encounter.patient.name)),
    h('div', { class: 'phead' },
      h('div', {}, h('h2', { text: encounter.patient.name }), h('ul', { class: 'facts' },
        h('li', { text: 'Visit ' + fmtDate(encounter.visit_date) }), h('li', { text: encounter.clinician_name }),
        h('li', { class: 'mono', text: encounter.patient.mrn }), h('li', {}, allergyChip(encounter.patient)), extra ? h('li', {}, extra) : ''))),
  ];
}

const MAX_RECORDING_MS = 20 * 60 * 1000;
const clock = ms => `${Math.floor(ms / 60000)}:${String(Math.floor(ms / 1000) % 60).padStart(2, '0')}`;

async function showCapture(encounter) {
  const failed = encounter.run && ['failed', 'incomplete'].includes(encounter.run.state);
  const language = h('select', { class: 'input' }, [['hinglish', 'Hinglish'], ['hindi', 'Hindi'], ['english', 'English'], ['tamil', 'Tamil'], ['telugu', 'Telugu'], ['gujarati', 'Gujarati']]
    .map(([v, l]) => h('option', { value: v, selected: encounter.source?.language === v }, l)));
  const consent = h('input', { type: 'checkbox' });
  const status = h('p', { class: 'muted small', role: 'status' });
  const timer = h('span', { class: 'timer', text: '0:00' });
  const meterBar = h('i');
  const meter = h('span', { class: 'level', 'aria-hidden': 'true' }, meterBar);
  const mic = h('button', { class: 'mic', type: 'button', 'aria-label': 'Start recording' }, svg(ICON.mic));
  const micLabel = h('span', { class: 'mic-label', text: 'Record' });
  const live = h('div', { class: 'live', hidden: true }, h('div', { class: 'row' }, h('span', { class: 'rec-dot' }), timer, meter));
  const controls = h('div', { class: 'row' });
  const review = h('div', { class: 'stack' });
  const fileInput = h('input', { type: 'file', accept: 'audio/*', class: 'sr', id: 'audio-file' });

  // Typing stays available: no microphone, a patient who declines recording, or a synthetic sample.
  const text = h('textarea', { class: 'input', rows: '8', placeholder: 'Type or paste what was said in the consultation.' });
  if (encounter.source?.kind === 'typed') text.value = encounter.source.text;
  const samples = h('select', { class: 'input', 'aria-label': 'Insert a synthetic sample' }, h('option', { value: '' }, 'Insert a synthetic sample…'));
  const process = h('button', { class: 'btn btn-dark', type: 'button' }, 'Write the draft from this text');
  const typed = h('details', { class: 'typed', open: encounter.source?.kind === 'typed' },
    h('summary', { text: 'Type or paste instead' }),
    h('label', { class: 'field' }, h('span', { text: 'What was said' }), text),
    h('label', { class: 'field' }, h('span', { text: 'Synthetic samples for this patient' }), samples),
    h('p', { class: 'muted small', text: 'Typed text needs no recording consent. It is stored as this visit\'s source and checked quote by quote.' }),
    process);

  const recordingAllowed = encounter.patient.consents?.includes('recording') ?? true;
  main().replaceChildren(...header(encounter), patientJourneyPanel(encounter.patient.id),
    h('section', { class: 'record' },
      h('div', { class: 'capture' },
        h('div', {}, mic, micLabel),
        h('div', {},
          h('h3', { text: failed ? 'Processing stopped' : 'Record the consultation' }),
          failed ? h('p', { class: 'err', text: encounter.run.error || 'The last attempt failed.' }) : '',
          failed ? h('div', { class: 'row' }, h('button', { class: 'btn btn-line btn-sm', type: 'button', onclick: () => retryRun(encounter) },
            encounter.source?.kind === 'audio' ? 'Retry the same recording' : 'Retry the same text')) : '',
          h('p', { class: 'muted', text: 'Speak as you normally would. Gnani Prisma transcribes the recording; every finding in the draft is then checked against that transcript.' }),
          h('div', { class: 'row' }, h('label', { class: 'field' }, h('span', { text: 'Language spoken' }), language)),
          h('label', { class: 'consent' }, consent, h('span', { text: recordingAllowed ? 'The patient agreed to this recording.' : 'This patient\'s record has no consent to recording. Type the visit instead.' })),
          live, controls, review, status,
          h('div', { class: 'row' }, h('label', { class: 'btn btn-line btn-sm', for: 'audio-file' }, 'Upload an audio file'), fileInput),
          typed))));
  if (!recordingAllowed) { mic.disabled = true; consent.disabled = true; }

  let recorder = null, stream = null, chunks = [], started = 0, banked = 0, ticker = null, audioContext = null, frame = null, discard = false, stopping = false;
  const elapsed = () => banked + (recorder?.state === 'recording' && !stopping ? Date.now() - started : 0);
  // Bank the running stretch before stopping: by the time onstop fires the recorder is no longer 'recording'.
  const stopRecording = drop => {
    if (!recorder || stopping) return;
    if (recorder.state === 'recording') banked += Date.now() - started;
    stopping = true; discard = drop; recorder.stop();
  };
  const needConsent = () => {
    if (consent.checked) return false;
    consent.focus(); toast('Confirm the patient agreed to the recording first.', true); return true;
  };
  const stopMeter = () => { cancelAnimationFrame(frame); audioContext?.close(); audioContext = null; meterBar.style.width = '0%'; };
  const startMeter = () => {
    audioContext = new AudioContext();
    const analyser = audioContext.createAnalyser(); analyser.fftSize = 1024;
    audioContext.createMediaStreamSource(stream).connect(analyser);
    const data = new Float32Array(analyser.fftSize);
    const draw = () => {
      analyser.getFloatTimeDomainData(data);
      const rms = Math.sqrt(data.reduce((sum, v) => sum + v * v, 0) / data.length);
      meterBar.style.width = Math.min(100, rms * 400) + '%';
      frame = requestAnimationFrame(draw);
    };
    draw();
  };
  const leaving = e => { e.preventDefault(); e.returnValue = ''; };
  const setControls = () => {
    const state = recorder?.state || 'inactive';
    live.hidden = state === 'inactive';
    mic.setAttribute('aria-label', state === 'inactive' ? 'Start recording' : 'Stop recording');
    micLabel.textContent = state === 'inactive' ? 'Record' : 'Stop';
    mic.classList.toggle('on', state !== 'inactive');
    put(controls, state === 'inactive' ? [] : [
      h('button', { class: 'btn btn-line btn-sm', type: 'button', onclick: () => {
        if (recorder.state === 'recording') { banked += Date.now() - started; recorder.pause(); }
        else { started = Date.now(); recorder.resume(); }
        setControls();
      } }, state === 'paused' ? 'Resume' : 'Pause'),
      h('button', { class: 'btn btn-quiet btn-sm', type: 'button', onclick: () => stopRecording(true) }, 'Discard')]);
    status.textContent = state === 'paused' ? 'Paused.' : state === 'recording' ? 'Recording. Nothing is sent until you stop and choose to use it.' : status.textContent;
  };

  async function startRecording() {
    if (needConsent()) return;
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) { status.textContent = 'This browser cannot record. Upload a file or type instead.'; return; }
    try { stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 } }); }
    catch (e) { status.textContent = 'The microphone is blocked or missing. Allow it for this site, or upload a file or type instead.'; return; }
    const type = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4'].find(t => MediaRecorder.isTypeSupported(t));
    recorder = new MediaRecorder(stream, type ? { mimeType: type } : undefined);
    chunks = []; banked = 0; discard = false; stopping = false; put(review);
    recorder.ondataavailable = e => { if (e.data.size) chunks.push(e.data); };
    recorder.onstop = () => {
      clearInterval(ticker); stopMeter(); stream.getTracks().forEach(t => t.stop());
      window.removeEventListener('beforeunload', leaving);
      const blob = new Blob(chunks, { type: (recorder.mimeType || 'audio/webm').split(';')[0] });
      const length = elapsed(); recorder = null; setControls();
      if (discard) { status.textContent = 'Recording discarded.'; return; }
      showRecorded(blob, length);
    };
    recorder.start(1000); started = Date.now();
    ticker = setInterval(() => { timer.textContent = clock(elapsed()); if (elapsed() >= MAX_RECORDING_MS) stopRecording(false); }, 250);
    window.addEventListener('beforeunload', leaving);
    startMeter(); setControls();
  }

  function showRecorded(blob, length) {
    const url = URL.createObjectURL(blob);
    put(review, h('audio', { controls: true, src: url, class: 'player' }),
      h('p', { class: 'muted small', text: `${clock(length)} recorded. Listen back if you like, then use it or record again.` }),
      h('div', { class: 'row' },
        h('button', { class: 'btn btn-dark', type: 'button', onclick: e => { e.currentTarget.disabled = true; upload(blob); } }, 'Use this recording'),
        h('button', { class: 'btn btn-quiet', type: 'button', onclick: () => { URL.revokeObjectURL(url); put(review); status.textContent = ''; timer.textContent = '0:00'; } }, 'Record again')));
    status.textContent = '';
  }

  async function upload(blob) {
    if (needConsent()) return;
    status.textContent = 'Uploading the recording…';
    try {
      const response = await fetch(`/api/v1/encounters/${encounter.id}/sources/audio?language=${language.value}`, {
        method: 'POST', credentials: 'same-origin', body: blob,
        headers: { 'Content-Type': (blob.type || 'audio/webm').split(';')[0], 'X-CSRF-Token': session.csrf_token, 'X-Recording-Consent': 'patient-agreed' } });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new ApiError(response.status, data.error);
      status.textContent = `Uploaded ${Math.round(data.duration_s)} seconds of audio. Starting…`;
      const run = await api(`/encounters/${encounter.id}/runs`, { method: 'POST', body: { source_id: data.id, source_version: data.version } });
      showProcessing(encounter, run);
    } catch (e) { status.textContent = ''; fail(e); review.querySelectorAll('button').forEach(b => { b.disabled = false; }); }
  }

  mic.addEventListener('click', () => (recorder ? stopRecording(false) : startRecording()));
  // Leaving the page mid-recording discards it and releases the microphone.
  ui.cleanup = () => stopRecording(true);
  fileInput.addEventListener('change', () => {
    const file = fileInput.files[0];
    fileInput.value = '';
    if (!file) return;
    if (needConsent()) return;
    put(review, h('p', { class: 'muted small', text: `${file.name} (${(file.size / 1048576).toFixed(1)} MB)` }));
    upload(file);
  });
  api(`/patients/${encounter.patient.id}/samples`).then(({ items }) => {
    items.forEach(s => samples.append(h('option', { value: s.id, dataset: { text: s.text, language: s.language } }, `${s.id} (${LANG[s.language] || s.language})`)));
    if (!items.length) samples.firstChild.textContent = 'No samples for this patient';
  }).catch(() => {});
  samples.addEventListener('change', () => {
    const option = samples.selectedOptions[0];
    if (option?.dataset.text) { text.value = option.dataset.text; language.value = option.dataset.language; }
  });
  process.addEventListener('click', async () => {
    process.disabled = true;
    try {
      const source = await api(`/encounters/${encounter.id}/sources`, { method: 'POST', body: { kind: 'typed', language: language.value, text: text.value } });
      const run = await api(`/encounters/${encounter.id}/runs`, { method: 'POST', body: { source_id: source.id, source_version: source.version } });
      showProcessing(encounter, run);
    } catch (e) { fail(e); process.disabled = false; }
  });
}

async function retryRun(encounter) {
  try { showProcessing(encounter, await api(`/runs/${encounter.run.run_id}/retry`, { method: 'POST' })); } catch (e) { fail(e); }
}

const STEP_TEXT = { transcribing: 'Transcribe the recording with Gnani Prisma', extracting: 'Find findings and medicines', checking: 'Check every quote against what was said',
  writing: 'Write the report', report_checks: 'Check each report line against its sources', assembling: 'Put the draft together',
  suggesting: 'Suggest products for unclear medicine names' };

function showProcessing(encounter, run) {
  const list = h('ol', { class: 'proc' });
  const note = h('p', { class: 'muted small' });
  main().replaceChildren(...header(encounter, h('span', { class: 'chip iris', text: 'Processing' })),
    h('section', { class: 'record' }, h('h3', { text: 'Writing the draft' }),
      h('p', { class: 'muted', text: 'Each step below is real progress from the server. This usually takes under a minute.' }), list, note));
  let delay = 2000;
  const draw = r => {
    list.replaceChildren(...r.steps.map(s => h('li', { class: s.state }, h('span', { class: 'tick' }, svg(ICON.check)),
      STEP_TEXT[s.key] + (s.state === 'skipped' ? ' (not needed for typed text)' : ''))));
    note.textContent = r.state === 'retry_wait' ? (r.error || 'Waiting to retry.') : r.attempts > 1 ? `Attempt ${r.attempts}` : '';
  };
  const poll = async () => {
    try {
      const r = await api('/runs/' + run.run_id);
      draw(r); delay = 2000;
      if (r.state === 'succeeded') return showEncounter(encounter.id);
      if (['failed', 'incomplete', 'cancelled'].includes(r.state)) return showEncounter(encounter.id);
    } catch (e) { delay = Math.min(delay * 2, 15000); if (e.status === 401) return; }
    ui.pollTimer = setTimeout(poll, document.hidden ? Math.max(delay, 8000) : delay);
  };
  draw(run);
  stopPolling();
  ui.pollTimer = setTimeout(poll, 1200);
}

// ---------- Review ----------

const ACTION_TEXT = { choose_product: 'Choose product', set_dose: 'Set dose', set_timing: 'Set timing', set_food: 'Set food',
  set_duration: 'Set duration', remove_medicine: 'Remove medicine', confirm_order: 'Accept', acknowledge: 'Accept',
  edit_line: 'Edit line', remove_line: 'Remove line', add_line: 'Add a line', dismiss_item: 'Rule out finding',
  confirm_interpretation: 'Correct' };
// The signed-in doctor is recorded with every change, so nothing asks for a typed reason: confirmations save in
// one click, edits save from their fields, and the audit keeps one of these plain reasons.
const DONE_REASON = { choose_product: 'Product chosen by the doctor.', set_dose: 'Dose set by the doctor.',
  set_timing: 'Timing set by the doctor.', set_food: 'Food timing set by the doctor.', set_duration: 'Duration set by the doctor.',
  remove_medicine: 'Removed by the doctor.', confirm_order: 'Confirmed by the doctor as their own order.',
  acknowledge: 'Reviewed and accepted by the doctor.', edit_line: 'Edited by the doctor.', remove_line: 'Removed by the doctor.',
  add_line: 'Written by the doctor.', dismiss_item: 'Ruled out by the doctor.',
  confirm_interpretation: 'Confirmed correct as written by the doctor.' };
const ONE_CLICK = ['confirm_order', 'acknowledge', 'confirm_interpretation'];
const CONFIRM_TEXT = { remove_medicine: 'Yes, remove', remove_line: 'Yes, remove', dismiss_item: 'Yes, rule out' };
// ---------- Medicine picker (runbook D-122): choose a medicine and its instructions without the mouse ----------
// Search or ↓ through the visit's common choices, Enter to pick; then ↑↓ moves between rows, ←→ changes the
// value, Enter saves, Esc steps back. Nothing is typed but the search.

const PK_DAYS = [1, 2, 3, 5, 7, 10, 14, 21, 30, 60, 90];
const PK_TIMES = [['1', 'Once'], ['2', 'Twice'], ['3', 'Three times'], ['4', 'Four times'], ['sos', 'When needed']];
const PK_WHEN = { '1': ['m', 'a', 'e', 'n'], '2': ['mn', 'me', 'ma', 'an'], '3': ['man', 'men'], '4': ['maen'], sos: [''] };
const PK_SLOT = { m: 'Morning', a: 'Afternoon', e: 'Evening', n: 'Night' };
const PK_DOSES = ['0.5', '1', '2', '3', '4'];
const PK_FOOD = [['', 'Not said'], ['before_food', 'Before food'], ['after_food', 'After food'], ['with_food', 'With food'], ['empty_stomach', 'Empty stomach']];
const PK_UNIT = { tablet: 'tablet', capsule: 'capsule', sachet: 'sachet', syrup: 'teaspoon', suspension: 'teaspoon', drops: 'drop', inhaler: 'puff' };
const ONCE_SLOT = { morning: 'm', afternoon: 'a', evening: 'e', night: 'n' };
const whenText = w => w ? w.split('').map(s => PK_SLOT[s]).join(' + ') : 'As needed';

function medicinePicker({ shortlist, med, onSave, onCancel, taken = [], number = 1 }) {
  const box = h('div', { class: 'picker', tabindex: '-1' });
  const search = h('input', { class: 'input', type: 'search', placeholder: 'Type a medicine, or press ↓ for the common choices', autocomplete: 'off' });
  const list = h('ul', { class: 'pk-list', role: 'listbox' });
  const rowsHost = h('div', { class: 'pk-rows' });
  const hint = h('p', { class: 'muted small pk-hint' });
  let options = [], active = 0, chosen = null, rows = [], row = 0, timer;

  const drawList = () => {
    list.replaceChildren(...options.map((o, i) => h('li', { class: 'pk-item' + (i === active ? ' active' : ''), role: 'option',
      onmousedown: e => { e.preventDefault(); pick(o); } },
      h('div', {}, o.group ? h('span', { class: 'chip muted pk-group', text: o.group }) : '', h('b', { text: o.label })),
      h('span', { class: 'muted small', text: [o.composition, o.why].filter(Boolean).join(' · ') }))));
    list.querySelector('.active')?.scrollIntoView({ block: 'nearest' });
  };
  // What is already prescribed drops out, so the list moves on to the next kind of medicine.
  const fromShortlist = q => shortlist.items.filter(o => !taken.includes(o.product_id)
    && (!q || (o.label + ' ' + o.composition + ' ' + (o.group || '')).toLowerCase().includes(q.toLowerCase())));
  const refresh = () => {
    const q = search.value.trim();
    options = fromShortlist(q); active = 0; drawList();
    clearTimeout(timer);
    if (q.length < 2) return;
    timer = setTimeout(async () => {
      try {
        const { items } = await api('/catalog/search?q=' + encodeURIComponent(q));
        const seen = new Set(options.map(o => o.product_id));
        options = [...fromShortlist(q), ...items.filter(p => !seen.has(p.id)).map(p => ({ product_id: p.id, label: p.label,
          composition: p.composition, form: p.form, food: p.food, once_daily: p.once_daily }))];
        active = Math.min(active, Math.max(options.length - 1, 0)); drawList();
      } catch (e) { fail(e); }
    }, 200);
  };

  // The instruction rows, with values taken from the medicine (when editing) or its standard instructions.
  function startRows(o, current) {
    chosen = o;
    const s = current?.schedule;
    const slots = s?.type === 'grid' ? 'maen'.split('').filter(k => Number(s[k]) > 0).join('') : '';
    const times = s?.type === 'as_needed' ? 'sos' : slots ? String(slots.length) : s?.type === 'frequency' ? String(Math.min(s.times, 4))
      : o.once_daily ? '1' : '2';
    const days = current?.duration ? current.duration.value * ({ day: 1, week: 7, month: 30 })[current.duration.unit] : 5;
    const pickWhen = t => slots && slots.length === Number(t) && PK_WHEN[t].includes(slots) ? slots
      : t === '1' && ONCE_SLOT[o.once_daily] ? ONCE_SLOT[o.once_daily] : PK_WHEN[t][0];
    rows = [
      { key: 'days', label: 'Days', values: PK_DAYS.includes(days) ? PK_DAYS : [...PK_DAYS, days].sort((a, b) => a - b), value: days, text: d => `${d} day${d > 1 ? 's' : ''}` },
      { key: 'times', label: 'Times a day', values: PK_TIMES.map(t => t[0]), value: times, text: t => Object.fromEntries(PK_TIMES)[t] },
      { key: 'when', label: 'Which time', values: PK_WHEN[times], value: pickWhen(times), text: whenText },
      { key: 'dose', label: 'Dose', values: PK_DOSES, value: current?.dose?.amount && PK_DOSES.includes(current.dose.amount) ? current.dose.amount : '1',
        text: d => `${d === '0.5' ? '½' : d} ${PK_UNIT[o.form] || 'unit'}${Number(d) > 1 ? 's' : ''}` },
      { key: 'food', label: 'Food', values: PK_FOOD.map(f => f[0]), value: current ? (current.food || '') : (o.food || ''), text: f => Object.fromEntries(PK_FOOD)[f] },
    ];
    row = 0;
    search.hidden = true; list.hidden = true;
    drawRows();
    // When editing, the picker isn't on the page yet; focus once it is, so the arrow keys reach it.
    setTimeout(() => box.focus(), 0);
  }
  const drawRows = () => {
    rowsHost.replaceChildren(h('div', { class: 'pk-chosen' }, h('b', { text: chosen.label }), h('span', { class: 'muted small', text: chosen.composition || '' })),
      ...rows.map((r, i) => h('div', { class: 'pk-row' + (i === row ? ' active' : '') },
        h('span', { class: 'pk-label', text: r.label }),
        h('div', { class: 'pk-opts' }, r.values.map(v => h('button', { class: 'pk-opt' + (v === r.value ? ' sel' : ''), type: 'button', tabindex: '-1',
          onmousedown: e => { e.preventDefault(); row = i; set(r, v); } }, r.text(v)))))));
    rowsHost.querySelector('.pk-row.active .sel')?.scrollIntoView({ block: 'nearest', inline: 'nearest' });
    hint.textContent = '↑ ↓ row · ← → change · Enter save · Esc back';
  };
  const set = (r, v) => {
    r.value = v;
    if (r.key === 'times') { const when = rows[2]; when.values = PK_WHEN[v]; when.value = v === '1' && ONCE_SLOT[chosen.once_daily] ? ONCE_SLOT[chosen.once_daily] : PK_WHEN[v][0]; }
    drawRows();
  };
  const result = () => {
    const get = k => rows.find(r => r.key === k).value;
    const when = get('when');
    return { product: chosen, dose: { amount: get('dose'), unit: PK_UNIT[chosen.form] || 'unit' },
      schedule: get('times') === 'sos' ? { type: 'as_needed', max_per_day: null }
        : { type: 'grid', ...Object.fromEntries('maen'.split('').map(k => [k, when.includes(k) ? '1' : '0'])) },
      food: get('food'), duration: { value: get('days'), unit: 'day' } };
  };

  search.addEventListener('input', refresh);
  search.addEventListener('keydown', e => {
    if (e.key === 'ArrowDown') { e.preventDefault(); active = Math.min(active + 1, options.length - 1); drawList(); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); active = Math.max(active - 1, 0); drawList(); }
    else if (e.key === 'Enter') { e.preventDefault(); if (options[active]) pick(options[active]); }
    else if (e.key === 'Escape') { e.preventDefault(); onCancel(); }
    // The space that opened the picker, or a second press, shows the common choices rather than typing a blank.
    else if (e.key === ' ' && !search.value) { e.preventDefault(); }
  });
  box.addEventListener('keydown', e => {
    if (!chosen || e.target === search) return;
    const r = rows[row], i = r.values.indexOf(r.value);
    if (e.key === 'ArrowDown') { e.preventDefault(); row = (row + 1) % rows.length; drawRows(); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); row = (row + rows.length - 1) % rows.length; drawRows(); }
    else if (e.key === 'ArrowRight') { e.preventDefault(); set(r, r.values[Math.min(i + 1, r.values.length - 1)]); }
    else if (e.key === 'ArrowLeft') { e.preventDefault(); set(r, r.values[Math.max(i - 1, 0)]); }
    else if (e.key === 'Enter') { e.preventDefault(); onSave(result()); }
    else if (e.key === 'Escape') { e.preventDefault(); if (med) onCancel(); else { chosen = null; rowsHost.replaceChildren(); search.hidden = false; list.hidden = false; hint.textContent = '↓ ↑ choose · Enter pick · Esc close'; search.focus(); } }
  });
  function pick(o) { startRows(o); }

  if (med) {
    box.append(rowsHost, hint);
    startRows({ product_id: med.product_id, label: med.product_label || med.spoken_name, composition: '', form: med.product_form || 'tablet' }, med);
  } else {
    box.append(h('div', { class: 'pk-head' }, h('b', { text: `Medicine ${number}` }), h('span', { class: 'muted small', text: 'Enter saves and opens the next · Esc when done' })),
      shortlist.conditions.length ? h('p', { class: 'muted small', text: 'Common for: ' + shortlist.conditions.slice(0, 4).join(', ') }) : '',
      search, list, rowsHost, hint);
    hint.textContent = '↓ ↑ choose · Enter pick · Esc close';
    refresh();
    setTimeout(() => search.focus(), 0);
  }
  return box;
}

// What VoiceRx filled in rather than heard (runbook D-118), shown on the prescription row for the doctor to check.
const FILLED_PRODUCT = { generic: 'Generic name', auto: 'Name matched: check', learned: 'Chosen before in this clinic' };
const FILLED_FIELD = { dose: 'dose', food: 'food', schedule: 'times' };
function filledChips(m) {
  const f = m.filled || {};
  const standard = Object.keys(FILLED_FIELD).filter(k => f[k] === 'standard').map(k => FILLED_FIELD[k]);
  return [f.product ? h('span', { class: 'chip ' + (f.product === 'auto' ? 'off' : 'muted'), text: FILLED_PRODUCT[f.product] || f.product }) : '',
    standard.length ? h('span', { class: 'chip iris', text: 'Standard ' + standard.join(', ') }) : ''];
}
const TIER_TEXT = { formulary: 'In formulary', indian: 'Indian list · unverified', clinic: 'Clinic list · pending review' };
const PRODUCT_CODES = ['unmatched_product', 'ambiguous_product', 'fuzzy_product_match', 'allergy_conflict'];
const SOURCE_TEXT = { openfda_label: 'US label (openFDA)', nlem_2022: 'NLEM 2022', jan_aushadhi: 'Jan Aushadhi' };

async function showReview(encounter, view) {
  try { view = view || await api(`/encounters/${encounter.id}/report`); } catch (e) { return fail(e); }
  const report = view.report;
  const draft = view.status === 'draft';
  const canEdit = draft && view.capabilities.resolve;
  const issuesByTarget = {};
  view.issue_views.forEach(i => (issuesByTarget[i.target] ||= []).push(i));
  const flaggedLine = ref => (issuesByTarget[ref] || []).length > 0 ||
    report.sections[ref.split(':')[0]][Number(ref.split(':')[1])].cites.some(c => (issuesByTarget[c] || []).length);
  const evidence = h('section', { class: 'panel evidence' });
  const transcript = h('div', { class: 'transcript' });

  const submit = async items => {
    try {
      const updated = await api(`/encounters/${encounter.id}/resolutions`, { method: 'POST',
        body: { expected_version: view.version, expected_content_hash: view.content_hash, resolutions: items } });
      ui.editing = null; toast(`Saved. Draft is now version ${updated.version}.`);
      showReview(encounter, updated);
    } catch (e) {
      ui.chainPicker = false;
      if (e.code === 'version_conflict') { toast(e.message, true); return showEncounter(encounter.id); }
      fail(e);
    }
  };

  const drawTranscript = quotes => {
    const text = encounter.source?.text || '';
    const spans = [];
    for (const q of quotes || []) { const at = q ? text.indexOf(q) : -1; if (at >= 0) spans.push([at, at + q.length]); }
    spans.sort((a, b) => a[0] - b[0]);
    const parts = []; let pos = 0;
    for (const [s, e] of spans) { if (s < pos) continue; parts.push(text.slice(pos, s), h('mark', { text: text.slice(s, e) })); pos = e; }
    parts.push(text.slice(pos));
    transcript.replaceChildren(...parts);
    transcript.querySelector('mark')?.scrollIntoView({ block: 'nearest' });
  };

  const showLine = ref => {
    ui.selectedLine = ref;
    document.querySelectorAll('.line').forEach(b => b.classList.toggle('sel', b.dataset.ref === ref));
    const [section, index] = ref.split(':');
    const line = report.sections[section][Number(index)];
    const findings = line.cites.map(c => view.findings[c]).filter(Boolean);
    const reviewIssues = view.issue_views.filter(i => (i.target === ref || line.cites.includes(i.target))
      && i.actions.includes('confirm_interpretation'));
    put(evidence, h('div', { class: 'ph' }, h('h3', { text: 'Evidence' }), h('p', { text: view.section_names[section] })),
      h('p', { text: line.text }),
      findings.length ? findings.map(f => h('div', { class: 'finding' },
        h('b', { text: f.term }), h('p', { class: 'quote', text: '“' + f.quote + '”' }),
        h('div', { class: 'attrs' }, h('span', { class: 'chip ' + (f.assertion === 'absent' ? 'muted' : 'iris'), text: f.assertion }),
          h('span', { class: 'chip muted', text: f.certainty }), f.laterality ? h('span', { class: 'chip muted', text: f.laterality }) : '',
          f.subject !== 'patient' ? h('span', { class: 'chip off', text: 'about ' + f.subject }) : '',
          h('span', { class: 'chip muted', text: 'said by ' + f.said_by }), h('span', { class: 'chip muted', text: f.id })))) :
        h('p', { class: 'err', text: 'This line cites no checked finding.' }),
      canEdit ? h('div', { class: 'row' },
        reviewIssues.length ? h('button', { class: 'btn btn-dark btn-sm', type: 'button',
          title: 'Confirm the flagged interpretations for this line as correct',
          onclick: () => submit(reviewIssues.map(i => ({ action: 'confirm_interpretation', target: i.target,
            value: { code: i.code }, reason: DONE_REASON.confirm_interpretation }))) }, 'Correct') : '',
        h('button', { class: 'btn btn-line btn-sm', type: 'button', onclick: () => openEditor('edit_line', ref, evidence) }, 'Edit line'),
        h('button', { class: 'btn btn-risk btn-sm', type: 'button', onclick: () => openEditor('remove_line', ref, evidence) }, 'Remove line')) : '');
    drawTranscript(findings.map(f => f.quote));
  };

  const medById = Object.fromEntries(view.medication_views.map(m => [m.id, m]));
  const describe = issue => {
    if (issue.target_kind === 'medicine') { const m = medById[issue.target]; return 'Medicine: ' + (m?.product_label || m?.spoken_name || issue.target); }
    if (issue.target_kind === 'line') { const [s, i] = issue.target.split(':'); return `${view.section_names[s]}: “${report.sections[s][Number(i)]?.text || ''}”`; }
    if (issue.target_kind === 'finding') { const f = view.findings[issue.target]; return `Finding: ${f?.term || issue.target}` + (f ? ` (“${f.quote}”)` : ''); }
    return 'Whole report';
  };

  // One editor at a time. Every correction carries a reason (DESIGN.md section 7), supplied here from context.
  function openEditor(action, target, host, issue, preset) {
    host.querySelector('.editor')?.remove();
    let reason = DONE_REASON[action];
    const fields = h('div');
    let value = () => ({});
    const med = medById[target];
    const select = (options, current) => h('select', { class: 'input' }, options.map(([v, l]) => h('option', { value: v, selected: v === current }, l)));
    if (action === 'choose_product') {
      // Suggestions, the matcher's candidates and the formulary; search and "add a product" reach every tier.
      const options = new Map();
      (med?.suggestions || []).forEach(s => options.set(s.product_id, `${s.label} · ${TIER_TEXT[s.tier] || s.tier}`));
      (med?.candidates || []).forEach(c => options.set(c.id, c.label));
      view.catalog.forEach(p => { if (!options.has(p.id)) options.set(p.id, p.label); });
      const s = select([...options], preset?.product_id || med?.product_id);
      const offer = (id, label) => { if (!options.has(id)) { options.set(id, label); s.append(h('option', { value: id }, label)); } s.value = id; };
      const search = h('input', { class: 'input', type: 'search', placeholder: 'Search all products: formulary, Indian list, clinic' });
      const found = h('div', { class: 'found' });
      let searchTimer;
      search.addEventListener('input', () => {
        clearTimeout(searchTimer);
        searchTimer = setTimeout(async () => {
          if (search.value.trim().length < 2) return put(found);
          try {
            const { items } = await api('/catalog/search?q=' + encodeURIComponent(search.value));
            put(found, items.map(p => h('button', { class: 'btn btn-quiet btn-sm', type: 'button',
              onclick: () => { offer(p.id, `${p.label} · ${TIER_TEXT[p.tier] || p.tier}`); put(found); search.value = ''; } },
              `${p.label} (${p.composition})`)));
          } catch (e) { fail(e); }
        }, 250);
      });
      const newName = h('input', { class: 'input', placeholder: 'Brand name as on the pack, e.g. Colaquick' });
      const newForm = select(['tablet', 'capsule', 'syrup', 'suspension', 'injection', 'sachet', 'powder', 'gel', 'cream', 'drops', 'other'].map(f => [f, f]), 'tablet');
      const newComposition = h('input', { class: 'input', placeholder: 'Composition, e.g. Collagen Peptide (10g) + Vitamin C (40mg)' });
      const add = h('details', { class: 'add-product' }, h('summary', { text: 'Add a product that isn’t listed' }),
        h('label', { class: 'field' }, h('span', { text: 'Brand' }), newName),
        h('div', { class: 'row' }, h('label', { class: 'field' }, h('span', { text: 'Form' }), newForm),
          h('label', { class: 'field' }, h('span', { text: 'Composition' }), newComposition)),
        h('p', { class: 'muted small', text: 'Added for this clinic and marked pending review. It can be used at once.' }),
        h('button', { class: 'btn btn-line btn-sm', type: 'button', onclick: async () => {
          try {
            const p = await api('/catalog/products', { method: 'POST', body: { name: newName.value, form: newForm.value, composition: newComposition.value } });
            offer(p.id, `${p.label} · ${TIER_TEXT.clinic}`); add.open = false; toast(`${p.label} added for this clinic.`);
          } catch (e) { fail(e); }
        } }, 'Add and select'));
      fields.append(h('label', { class: 'field' }, h('span', { text: 'Product' }), s), search, found, add);
      if (preset && med) reason = `Heard “${med.spoken_name}”; meant ${preset.label}.`;
      value = () => ({ product_id: s.value });
    } else if (action === 'set_dose') {
      const amount = h('input', { class: 'input', inputmode: 'decimal', value: med?.dose?.amount || '1' });
      const unit = select(['tablet', 'capsule', 'ml', 'puff', 'teaspoon', 'drop', 'sachet', 'unit'].map(u => [u, u]), med?.dose?.unit || 'tablet');
      fields.append(h('div', { class: 'row' }, h('label', { class: 'field' }, h('span', { text: 'Amount' }), amount), h('label', { class: 'field' }, h('span', { text: 'Unit' }), unit)));
      value = () => ({ amount: amount.value.trim(), unit: unit.value });
    } else if (action === 'set_timing') {
      const s = med?.schedule || {};
      const kind = select([['grid', 'Morning / afternoon / evening / night'], ['frequency', 'Times a day or week'], ['as_needed', 'When needed']], s.type === 'taper' ? 'grid' : (s.type || 'grid'));
      const slots = 'maen'.split('').map(k => h('input', { class: 'input', inputmode: 'decimal', value: s.type === 'grid' ? s[k] : '0', 'aria-label': { m: 'Morning', a: 'Afternoon', e: 'Evening', n: 'Night' }[k] }));
      const times = h('input', { class: 'input', type: 'number', min: '1', value: s.times || '1' });
      const period = select([['day', 'a day'], ['week', 'a week']], s.period || 'day');
      const maxDay = h('input', { class: 'input', type: 'number', min: '1', value: s.max_per_day || '', placeholder: 'No limit stated' });
      const grid = h('div', { class: 'row' }, slots.map((input, i) => h('label', { class: 'field' }, h('span', { text: ['Morning', 'Afternoon', 'Evening', 'Night'][i] }), input)));
      const freq = h('div', { class: 'row' }, h('label', { class: 'field' }, h('span', { text: 'Times' }), times), h('label', { class: 'field' }, h('span', { text: 'Per' }), period));
      const prn = h('div', { class: 'row' }, h('label', { class: 'field' }, h('span', { text: 'At most per day' }), maxDay));
      const sync = () => { grid.hidden = kind.value !== 'grid'; freq.hidden = kind.value !== 'frequency'; prn.hidden = kind.value !== 'as_needed'; };
      kind.addEventListener('change', sync); sync();
      fields.append(h('label', { class: 'field' }, h('span', { text: 'Schedule' }), kind), grid, freq, prn);
      value = () => ({ schedule: kind.value === 'grid' ? { type: 'grid', m: slots[0].value.trim(), a: slots[1].value.trim(), e: slots[2].value.trim(), n: slots[3].value.trim() }
        : kind.value === 'frequency' ? { type: 'frequency', times: Number(times.value), period: period.value }
          : { type: 'as_needed', max_per_day: maxDay.value ? Number(maxDay.value) : null } });
    } else if (action === 'set_food') {
      const s = select([['after_food', 'After food'], ['before_food', 'Before food'], ['with_food', 'With food'], ['empty_stomach', 'Empty stomach']], med?.food || 'after_food');
      fields.append(h('label', { class: 'field' }, h('span', { text: 'Food' }), s)); value = () => ({ food: s.value });
    } else if (action === 'set_duration') {
      const n = h('input', { class: 'input', type: 'number', min: '1', value: med?.duration?.value || '5' });
      const unit = select([['day', 'days'], ['week', 'weeks'], ['month', 'months']], med?.duration?.unit || 'day');
      fields.append(h('div', { class: 'row' }, h('label', { class: 'field' }, h('span', { text: 'For' }), n), h('label', { class: 'field' }, h('span', { text: 'Unit' }), unit)));
      value = () => ({ value: Number(n.value), unit: unit.value });
    } else if (action === 'edit_line') {
      const [s, i] = target.split(':');
      const t = h('textarea', { class: 'input', rows: '3' }); t.value = report.sections[s][Number(i)].text;
      fields.append(h('label', { class: 'field' }, h('span', { text: 'Line text (its citations stay as they are)' }), t)); value = () => ({ text: t.value });
    } else if (action === 'add_line') {
      // The issue targets a finding; the new line goes into the section the doctor picks and cites that finding.
      const findingId = target;
      const f = view.findings[findingId];
      const section = select(Object.entries(view.section_names), 'plan');
      const t = h('textarea', { class: 'input', rows: '2' }); t.value = f ? f.term : '';
      fields.append(h('p', { class: 'muted small', text: `Cites finding ${findingId}: “${f?.quote || ''}”` }),
        h('label', { class: 'field' }, h('span', { text: 'Section' }), section), h('label', { class: 'field' }, h('span', { text: 'Line text' }), t));
      value = () => ({ text: t.value, cites: [findingId] });
      fields._target = () => section.value;
    } else if (action === 'acknowledge') {
      value = () => ({ code: issue.code });
    }
    const editor = h('div', { class: 'editor' }, h('b', { text: ACTION_TEXT[action] }), fields,
      h('div', { class: 'row' },
        h('button', { class: 'btn btn-dark btn-sm', type: 'button', onclick: () =>
          submit([{ action, target: fields._target ? fields._target() : target, value: value(), reason }]) },
          CONFIRM_TEXT[action] || 'Save'),
        h('button', { class: 'btn btn-quiet btn-sm', type: 'button', onclick: () => editor.remove() }, 'Cancel')));
    host.append(editor);
    editor.querySelector('input, select, textarea')?.focus();
  }

  // Accept saves at once; anything else opens its short form.
  function act(action, target, host, issue) {
    if (!ONE_CLICK.includes(action)) return openEditor(action, target, host, issue);
    submit([{ action, target, value: ['acknowledge', 'confirm_interpretation'].includes(action) ? { code: issue.code } : {}, reason: DONE_REASON[action] }]);
  }

  // What was heard and what it may have been (spec 2026-11-03, part B). Never applied without a click.
  function suggestionList(med, card, issue) {
    const likely = med.suggestions[0]?.likely;
    return h('div', { class: 'suggest' },
      h('p', { class: 'where', text: `Heard “${med.spoken_name}”. ${likely ? 'Likely match first; confirm it:' : 'Possible matches; choose the one you meant:'}` }),
      med.suggestions.map((s, i) => h('div', { class: 'sugg' + (i === 0 && likely ? ' top' : '') },
        h('div', {},
          h('b', { text: s.label }),
          h('div', { class: 'attrs' },
            h('span', { class: 'chip ' + (s.tier === 'formulary' ? 'ok' : 'off'), text: TIER_TEXT[s.tier] || s.tier }),
            s.sound_alike_sibling ? h('span', { class: 'chip miss', text: 'Sound-alike: check which' }) : '',
            s.strength_match === false ? h('span', { class: 'chip off', text: 'Strength differs from what was said' }) : '',
            s.chosen_before ? h('span', { class: 'chip iris', text: `Chosen before in this clinic (${s.chosen_before}×)` }) : ''),
          s.reason ? h('p', { class: 'muted small', text: s.reason }) : '',
          s.standard?.length ? h('p', { class: 'muted small', text: 'Also sets the standard: ' + s.standard.map(p => p.text).join(' · ') }) : ''),
        h('button', { class: 'btn btn-line btn-sm', type: 'button', onclick: () => submit([
          { action: 'choose_product', target: med.id, value: { product_id: s.product_id }, reason: `Heard “${med.spoken_name}”; meant ${s.label}.` },
          ...standardItems(med, s.standard)]) }, 'Use this'))));
  }

  // Standard instructions fill only what the doctor left unsaid, and only when accepted (runbook D-115).
  const standardItems = (med, items) => (items || []).map(p => ({ action: p.action, target: med.id, value: p.value, reason: p.reason }));
  const withStandard = view.medication_views.filter(m => m.standard?.length);
  const standardText = m => m.standard.map(p => p.text).join(' · ');

  // Approval panel
  let approvePanel;
  if (draft) {
    const approve = h('button', { class: 'btn btn-dark', type: 'button', disabled: !view.can_approve }, `Approve version ${view.version}`);
    approve.addEventListener('click', async () => {
      approve.disabled = true;
      try {
        const approved = await api(`/encounters/${encounter.id}/approvals`, { method: 'POST', body: { expected_version: view.version, expected_content_hash: view.content_hash } });
        toast('Approved. The PDF is being prepared.');
        showReview({ ...encounter, state: 'approved' }, approved);
      } catch (e) { approve.disabled = false; if (e.code === 'version_conflict') { toast(e.message, true); return showEncounter(encounter.id); } fail(e); }
    });
    approvePanel = h('section', { class: 'panel' }, h('div', { class: 'approve-bar' },
      h('div', {}, h('h3', { text: `Draft version ${view.version}` }),
        h('p', { text: view.blocking_count ? `${view.blocking_count} blocking issue${view.blocking_count > 1 ? 's' : ''} to resolve before approval. Warnings can be acknowledged.` : 'No blocking issues. Read the draft, then approve.' })),
      h('div', { class: 'row' }, h('a', { class: 'btn btn-line', href: `/api/v1/encounters/${encounter.id}/preview.pdf?version=${view.version}`, target: '_blank', rel: 'noopener' }, 'Preview PDF'), approve)),
      h('p', { class: 'muted small', text: 'Fingerprint ' + view.content_hash.slice(0, 12) }));
  } else {
    const files = h('div', { class: 'row' });
    const clinicStatus = h('div', { class: 'stack', role: 'status' });
    const drawClinic = jobs => clinicStatus.replaceChildren(...jobs.map(j => h('p', { class: 'muted small',
      text: `WhatsApp clinic copy · ${j.kind === 'report_pdf' ? 'PDF' : j.kind === 'voice_option' ? 'Voice option' : 'Requested audio'}: ${j.state.replaceAll('_', ' ')}${j.error ? ' · ' + j.error : ''}` })),
      jobs.some(j => j.state === 'failed') && view.capabilities.resolve ? h('button', { class: 'btn btn-line btn-sm', type: 'button',
        onclick: async () => { try { const r = await api(`/encounters/${encounter.id}/clinic-reports/retry`, { method: 'POST' }); drawClinic(r.items); } catch (e) { fail(e); } } }, 'Retry failed WhatsApp delivery') : '');
    drawClinic(view.clinic_deliveries || []);
    const drawFiles = artifacts => files.replaceChildren(...artifacts.map(a => a.state === 'ready'
      ? h('a', { class: 'btn btn-line btn-sm', href: `/api/v1/artifacts/${a.id}/download` }, a.kind === 'report_pdf' ? 'Download approved PDF' : 'Download FHIR bundles')
      : h('span', { class: 'chip ' + (a.state === 'failed' ? 'miss' : 'muted'), text: `${a.kind === 'report_pdf' ? 'PDF' : 'FHIR'}: ${a.state}` })));
    drawFiles(view.artifacts);
    if (view.artifacts.some(a => ['pending', 'running'].includes(a.state))) {
      const pollFiles = async () => {
        try { const { items } = await api(`/encounters/${encounter.id}/artifacts`); const mine = items.filter(a => a.version === view.version); drawFiles(mine);
          if (mine.some(a => ['pending', 'running'].includes(a.state))) ui.pollTimer = setTimeout(pollFiles, 2500); } catch (e) { /* keep the page */ }
      };
      stopPolling(); ui.pollTimer = setTimeout(pollFiles, 2000);
    }
    approvePanel = h('section', { class: 'panel stack' },
      h('div', { class: 'approved' }, svg(ICON.check), h('span', {}, h('b', { text: `Approved version ${view.version}` }),
        ` by ${view.approval?.approver_name || 'the doctor'}, ${view.approval ? fmtTime(view.approval.approved_at) : ''}`)),
      h('p', { class: 'muted small', text: 'Fingerprint ' + view.content_hash.slice(0, 12) + '. Follow-up and delivery have their own status.' }), files, clinicStatus,
      h('a', { class: 'btn btn-line', href: `#/followup/${encounter.id}` }, 'Open patient follow-up'));
  }

  // Report, under the headings of an outpatient summary. A section's sentences run on as one paragraph; each
  // stays selectable, so its sources are one click away. Advice reads one sentence a line, and review closes it.
  const sentence = t => /[.!?]$/.test(t.trim()) ? t.trim() : t.trim() + '.';
  const lineEl = (s, i, line) => { const ref = `${s}:${i}`;
    return h('span', { class: 'line' + (flaggedLine(ref) ? ' flagged' : '') + (ui.selectedLine === ref ? ' sel' : ''), role: 'button', tabindex: '0',
      dataset: { ref }, onclick: () => showLine(ref), onkeydown: e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); showLine(ref); } } },
      h('span', { text: sentence(line.text) }), h('span', { class: 'cite', text: line.cites.join(', ') || 'no source' })); };
  const reportPanel = h('section', { class: 'panel' }, h('div', { class: 'ph' }, h('h3', { text: 'Report' }), h('p', { text: 'Select a sentence to see what it is based on.' })),
    h('p', { class: 'opening', text: `Patient seen in the outpatient clinic on ${fmtDate(report.header.visit_date)}.` }),
    view.report_groups.map(([title, sections]) => {
      const lines = sections.flatMap(s => (report.sections[s] || []).map((line, i) => lineEl(s, i, line)));
      const current = title === 'Present problem' && report.current_medicines.length
        ? h('div', { class: 'section' }, h('h4', { text: 'Current medicines' }), report.current_medicines.map(t => h('p', { text: t }))) : '';
      if (!lines.length) return current;
      if (title === 'Review') return h('div', { class: 'section closing' }, lines);
      return [h('div', { class: 'section ' + (title === 'Treatment advised' ? 'advice' : 'prose') }, h('h4', { text: title }),
        title === 'Treatment advised' ? lines : h('p', {}, lines.flatMap((el, i) => i ? [' ', el] : [el]))), current];
    }),
    report.not_discussed.length ? h('p', { class: 'not-discussed', text: 'Not discussed: ' + report.not_discussed.join(', ') + '.' }) : '');

  // Medicines
  const slot = v => v && v !== '-' && Number(v) !== 0 ? h('span', { class: 'pill-n', text: v }) : h('span', { class: 'pill-z', text: v === '-' ? '·' : '0' });
  const tableMeds = view.medication_views.filter(m => m.row);
  const pickerHost = h('div');
  const closePicker = () => { pickerHost.replaceChildren(); ui.picking = false; };
  // Add a medicine nobody said, or change a medicine's instructions, from the keyboard (runbook D-122).
  const openPicker = async med => {
    ui.picking = true;
    let shortlist = { conditions: [], items: [] };
    if (!med) {
      ui.shortlists ||= {};
      try { shortlist = ui.shortlists[encounter.id] ||= await api(`/encounters/${encounter.id}/shortlist`); } catch (e) { fail(e); }
    }
    const taken = view.medication_views.map(m => m.product_id).filter(Boolean);
    pickerHost.replaceChildren(medicinePicker({ shortlist, med, taken, number: tableMeds.length + 1, onCancel: closePicker, onSave: r => {
      // Saving a new medicine opens the picker again for the next one, until Esc.
      if (!med) { ui.chainPicker = true; return submit([{ action: 'add_medicine', target: 'new', reason: 'Added by the doctor.', value: {
        product_id: r.product.product_id, dose: r.dose, schedule: r.schedule, food: r.food, duration: r.duration } }]); }
      const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
      const changes = [];
      if (!same(r.dose, med.dose)) changes.push({ action: 'set_dose', value: r.dose });
      if (!same(r.schedule, med.schedule)) changes.push({ action: 'set_timing', value: { schedule: r.schedule } });
      if (r.food && r.food !== med.food) changes.push({ action: 'set_food', value: { food: r.food } });
      if (!same(r.duration, med.duration)) changes.push({ action: 'set_duration', value: r.duration });
      if (!changes.length) return closePicker();
      submit(changes.map(c => ({ ...c, target: med.id, reason: DONE_REASON[c.action] })));
    } }));
  };
  const addButton = canEdit ? h('button', { class: 'btn btn-line btn-sm', type: 'button', title: 'Shortcut: space bar', onclick: () => openPicker() }, 'Add medicine', h('kbd', { class: 'kbd', text: 'Space' })) : '';
  const medsPanel = h('section', { class: 'panel' }, h('div', { class: 'ph' }, h('h3', { text: 'Prescription' }),
    h('div', { class: 'row' }, h('p', { text: tableMeds.length ? 'Morning · Afternoon · Evening · Night' : 'No medicines started or changed.' }), addButton)),
    pickerHost,
    tableMeds.length ? h('div', { class: 'wrapx' }, h('table', { class: 'meds' },
      h('thead', {}, h('tr', {}, h('th', { text: 'Medicine' }), ['M', 'A', 'E', 'N'].map(x => h('th', { class: 's', text: x })))),
      h('tbody', {}, tableMeds.map(m => {
        const cell = h('td', {},
          h('span', { class: 'mname', text: m.row.label }), h('span', { class: 'how', text: m.row.detail }),
          Object.keys(m.filled || {}).length ? h('div', { class: 'attrs' }, filledChips(m)) : '',
          m.row.flags.length ? h('div', { class: 'attrs' }, m.row.flags.map(f => h('span', { class: 'chip miss', text: f.replaceAll('_', ' ') }))) : '',
          canEdit && m.standard?.length ? h('div', { class: 'standard' }, h('span', { class: 'chip iris', text: 'Standard' }), standardText(m),
            h('button', { class: 'btn btn-line btn-sm', type: 'button', onclick: () => submit(standardItems(m, m.standard)) }, 'Accept')) : '',
          h('div', { class: 'acts' },
            canEdit && m.match === 'exact' ? h('button', { class: 'btn btn-quiet btn-sm', type: 'button', onclick: () => openPicker(m) }, 'Edit instructions') : '',
            canEdit ? ['choose_product', ...(m.match === 'exact' ? [] : ['set_dose', 'set_timing', 'set_food', 'set_duration']),
              ...(m.speaker_unclear ? ['confirm_order'] : []), 'remove_medicine']
              .filter(a => a !== 'choose_product' || m.match !== 'exact' || m.candidates.length > 1)
              .map(a => h('button', { class: 'btn btn-quiet btn-sm', type: 'button', onclick: () => act(a, m.id, cell) }, ACTION_TEXT[a])) : '',
            view.capabilities.knowledge && (m.product_id || m.candidates.length) ? h('button', { class: 'btn btn-quiet btn-sm', type: 'button', onclick: () => openReference({ encounter, med: m }) }, 'Reference') : ''));
        return h('tr', {}, cell, m.row.grid.map(v => h('td', { class: 's' }, slot(v))));
      })))) : '');

  // Issues
  const issuesPanel = h('section', { class: 'panel' }, h('div', { class: 'ph' }, h('h3', { text: 'To review' }),
    h('p', { text: view.issue_views.length ? `${view.blocking_count} blocking · ${view.issue_views.length - view.blocking_count} warnings` : 'Nothing flagged' })),
    canEdit && withStandard.length ? h('div', { class: 'standard-all' }, h('b', { text: 'Standard instructions for what wasn’t said' }),
      withStandard.map(m => h('p', { text: `${m.product_label || m.spoken_name}: ${standardText(m)}` })),
      h('p', { class: 'muted small', text: 'Usual directions for these medicines. Not yet reviewed by a clinician.' }),
      h('button', { class: 'btn btn-dark btn-sm', type: 'button', onclick: () => submit(withStandard.flatMap(m => standardItems(m, m.standard))) },
        withStandard.length > 1 ? `Accept all ${withStandard.length}` : 'Accept')) : '',
    view.issue_views.map(issue => {
      const card = h('div', { class: 'issue ' + issue.severity },
        h('span', { class: 'sev', text: issue.actions.includes('confirm_interpretation') ? 'Needs review' : issue.severity === 'block' ? 'Must fix' : 'Warning' }), h('b', { text: issue.title }),
        h('p', { class: 'where', text: describe(issue) }),
        issue.actions.includes('confirm_interpretation') ? h('p', { class: 'muted small', text: 'Choose Correct if this is accurate as written, or edit/remove it.' }) : '',
        issue.title !== issue.message && !issue.message.startsWith(issue.code.replaceAll('_', ' ')) ? h('p', { class: 'where', text: issue.message }) : '');
      const med = issue.target_kind === 'medicine' ? medById[issue.target] : null;
      if (canEdit && med?.suggestions?.length && PRODUCT_CODES.includes(issue.code)) card.append(suggestionList(med, card, issue));
      // An instruction said away from its medicine: use it as heard, in one click.
      if (canEdit && issue.uses?.length) card.append(h('div', { class: 'choices' }, issue.uses.map(u => h('button', {
        class: 'btn btn-sm btn-dark', type: 'button',
        onclick: () => submit([{ ...u.item, target: issue.target, reason: `Said “${u.label.slice(5, -1)}” for this medicine; confirmed by the doctor.` }]) }, u.label))));
      // Accept leads; the rest are ways to edit.
      const ordered = [...issue.actions.filter(a => ONE_CLICK.includes(a)), ...issue.actions.filter(a => !ONE_CLICK.includes(a))];
      if (canEdit && issue.actions.length) card.append(h('div', { class: 'choices' }, ordered.map(a => h('button', {
        class: 'btn btn-sm ' + (ONE_CLICK.includes(a) ? 'btn-dark' : 'btn-line'), type: 'button',
        onclick: () => (a === 'edit_line' || a === 'remove_line') && issue.target_kind === 'finding'
          ? (issue.lines[0] ? (showLine(issue.lines[0]), openEditor(a, issue.lines[0], evidence)) : null)
          : act(a, issue.target, card, issue) }, ACTION_TEXT[a]))));
      else if (issue.target_kind === 'line') card.append(h('button', { class: 'btn btn-quiet btn-sm', type: 'button', onclick: () => showLine(issue.target) }, 'Show line'));
      return card;
    }));

  const spoken = encounter.source?.kind === 'audio';
  const sourcePanel = h('section', { class: 'panel' }, h('div', { class: 'ph' }, h('h3', { text: 'What was said' }),
    h('p', { text: encounter.source ? (spoken ? `Gnani Prisma transcript of a ${clock(encounter.source.duration_s * 1000)} recording` : `Typed source v${encounter.source.version}`)
      + ` · ${LANG[encounter.source.language] || encounter.source.language}` : '' })),
    spoken ? h('audio', { controls: true, preload: 'none', src: encounter.source.audio_url, class: 'player' }) : '', transcript);

  evidence.replaceChildren(h('h3', { text: 'Evidence' }), h('p', { class: 'muted small', text: 'Select a report line to see the quotes it rests on.' }));
  main().replaceChildren(...header(encounter, stateChip(draft ? 'in_review' : 'approved', view.blocking_count)),
    patientJourneyPanel(encounter.patient.id),
    h('div', { class: 'review' },
      h('div', { class: 'stack' }, approvePanel, reportPanel, medsPanel, sourcePanel),
      h('div', { class: 'aside' }, issuesPanel, evidence)));
  drawTranscript([]);
  if (ui.selectedLine && report.sections[ui.selectedLine.split(':')[0]]?.[Number(ui.selectedLine.split(':')[1])]) showLine(ui.selectedLine);
  else ui.selectedLine = null;
  ui.picking = false;
  ui.addMedicine = canEdit ? { open: () => { medsPanel.scrollIntoView({ block: 'start' }); openPicker(); }, host: pickerHost } : null;
  if (ui.chainPicker) { ui.chainPicker = false; if (ui.addMedicine) ui.addMedicine.open(); }
}

// The space bar on a review screen opens the medicine picker with the visit's common choices, unless the doctor
// is typing or has a button or link selected (where space presses it).
document.addEventListener('keydown', e => {
  const busy = ['INPUT', 'TEXTAREA', 'SELECT', 'BUTTON', 'A'].includes(document.activeElement?.tagName);
  if (e.key === ' ' && !e.ctrlKey && !e.metaKey && !e.altKey && !e.shiftKey && !busy && !ui.picking
      && ui.addMedicine && document.contains(ui.addMedicine.host)) {
    e.preventDefault();
    ui.addMedicine.open();
  }
});

// ---------- Follow-up: the real agent, with a clearly labelled synthetic patient simulator ----------

function patientCommunicationPanel(patient) {
  if (!session.capabilities.resolve) return '';
  const phone = h('input', { class: 'input', type: 'tel', autocomplete: 'off', placeholder: 'Country code and WhatsApp number', 'aria-label': 'Patient WhatsApp number' });
  const language = h('select', { class: 'input', 'aria-label': 'Patient native language' },
    ['hi-IN','en-IN','ta-IN','te-IN','gu-IN'].map(code => h('option', { value: code, selected: code === patient.language_pref }, LANG[code])));
  const consent = h('input', { type: 'checkbox' });
  const status = h('p', { class: 'muted small', role: 'status' });
  return h('details', { class: 'panel stack' }, h('summary', { text: 'Patient WhatsApp and native language' }),
    h('p', { class: 'muted small', text: 'The patient verifies the connection once using the private invitation on an approved visit. Later approved reports use that same connection. This private test server accepts its configured test numbers.' }),
    h('label', { class: 'field' }, h('span', { text: 'WhatsApp number' }), phone),
    h('label', { class: 'field' }, h('span', { text: 'Native language for future prescriptions and requested audio' }), language),
    h('label', { class: 'consent' }, consent, 'The patient agreed to WhatsApp delivery and follow-up.'),
    h('button', { class: 'btn btn-line', type: 'button', onclick: async () => {
      if (!consent.checked) { status.textContent = 'Confirm patient consent first.'; return; }
      try { const result = await api(`/patients/${patient.id}/whatsapp-target`, { method: 'POST', body: { phone: phone.value, language: language.value, consent_confirmed: true } });
        phone.value = ''; status.textContent = result.linked ? 'Verified WhatsApp connection retained. Preference saved for future visits.' : 'Target saved. After approval, open patient follow-up and let the patient send the private JOIN invitation once.';
      } catch (e) { status.textContent = e.message; }
    } }, 'Save communication preferences'), status);
}

function patientJourneyPanel(patientId) {
  if (!session.capabilities.resolve) return '';
  const panel = h('section', { class: 'panel stack patient-journey', 'aria-label': 'Patient history for this visit' },
    h('h3', { text: 'Between visits' }), h('p', { class: 'muted small', text: 'Loading patient questions and lab history…' }));
  async function load() {
    try {
      const data = await api(`/patients/${patientId}/journey`);
      panel.replaceChildren(h('div', { class: 'ph' }, h('h3', { text: 'Between visits' }),
        h('span', { class: 'chip ' + (data.whatsapp.linked && !data.whatsapp.opted_out ? 'ok' : 'muted'), text: data.whatsapp.opted_out ? 'WhatsApp stopped' : data.whatsapp.linked ? 'WhatsApp verified' : 'WhatsApp not yet linked' })),
        h('p', { class: 'muted small', text: 'Patient-reported questions and uploaded reports across visits. These do not change the approved clinical record.' }),
        h('details', { open: data.tasks.some(t => t.status === 'open') },
          h('summary', { text: `Patient questions and requests · ${data.questions.length}` }),
          ...data.questions.slice(0, 30).map(q => h('article', { class: 'history-entry' },
            h('small', { class: 'muted', text: `${fmtTime(q.at)} · ${q.source || 'patient'} · ${q.action}` }),
            h('p', { class: 'followup-text', text: q.question }),
            q.reply ? h('details', {}, h('summary', { text: 'What the assistant replied' }), h('p', { class: 'followup-text', text: q.reply })) : '',
            h('a', { href: `#/followup/${q.encounter_id}`, text: 'Conversation and doctor tasks' }))),
          data.questions.length ? '' : h('p', { class: 'muted', text: 'No patient questions recorded yet.' })),
        h('details', { open: data.uploads.some(u => !u.reviewed_at) }, h('summary', { text: `Lab reports and other uploads · ${data.uploads.length}` }),
          ...data.uploads.map(u => h('article', { class: 'history-entry stack' },
            h('small', { class: 'muted', text: fmtTime(u.received_at) + ' · ' + (u.reviewed_at ? 'Reviewed ' + fmtTime(u.reviewed_at) : 'Awaiting doctor review') }),
            h('p', { class: 'followup-text', text: u.summary }),
            h('div', { class: 'row' }, h('a', { class: 'btn btn-line btn-sm', href: u.download_url, text: 'Open original report' }),
              !u.reviewed_at ? h('button', { class: 'btn btn-line btn-sm', type: 'button', onclick: async () => {
                try { await api(`/patient-uploads/${u.id}/review`, { method: 'POST' }); await load(); } catch (e) { fail(e); }
              } }, 'Mark reviewed') : ''))),
          data.uploads.length ? '' : h('p', { class: 'muted', text: 'No uploaded reports yet.' })));
    } catch (e) { panel.replaceChildren(h('h3', { text: 'Between visits' }), h('p', { class: 'err', text: e.message })); }
  }
  load(); return panel;
}

async function showFollowupTasks() {
  main().replaceChildren(h('p', { class: 'muted', text: 'Loading follow-up tasks…' }));
  try {
    const { items } = await api('/followup/tasks');
    main().replaceChildren(h('h1', { text: 'Patient follow-ups' }),
      h('p', { class: 'muted', text: 'Patient-reported questions and problems. These do not change the approved prescription.' }),
      ...items.map(t => h('section', { class: 'panel stack' }, h('span', { class: 'chip ' + (t.kind === 'urgent' ? 'miss' : 'off'), text: t.kind.replaceAll('_', ' ') }),
        h('h3', { text: t.patient_name }), h('p', { class: 'followup-text', text: t.note }),
        h('a', { class: 'btn btn-line', href: `#/followup/${t.encounter_id}` }, 'Open conversation'))),
      items.length ? '' : h('p', { class: 'panel', text: 'No open follow-up tasks.' }));
  } catch (e) { fail(e); }
}

async function showFollowup(encounterId) {
  const base = `/encounters/${encounterId}/followup`;
  const title = h('h1', { text: 'Patient follow-up' });
  const status = h('p', { class: 'muted', role: 'status' });
  const transcript = h('div', { class: 'followup-messages stack', tabindex: '0', 'aria-label': 'Follow-up conversation' });
  const tasks = h('section', { class: 'panel stack', 'aria-label': 'Doctor follow-up tasks' });
  const join = h('p', { class: 'followup-text' });
  const delivery = h('section', { class: 'panel stack', 'aria-label': 'Patient delivery status' });
  const consent = h('button', { class: 'btn btn-line', type: 'button', onclick: async () => {
    try { await api(base + '/consent', { method: 'POST', body: { enabled: true } }); await refresh(); }
    catch (e) { fail(e); }
  } }, 'Record consent for synthetic follow-up');
  consent.hidden = true;
  const input = h('input', { class: 'input', maxlength: '2000', placeholder: 'Try DOCTOR, STOP, or a medicine question', 'aria-label': 'Simulated patient reply' });
  const send = h('button', { class: 'btn btn-dark', type: 'submit' }, 'Send simulated reply');
  const simulator = h('form', { class: 'panel stack followup-simulator', onsubmit: async e => {
    e.preventDefault(); if (!input.value.trim()) return;
    await reply({ text: input.value.trim() });
  } }, h('h3', { text: 'Simulate the patient' }),
  h('p', { class: 'muted small', text: 'Local synthetic conversation. No WhatsApp message is sent.' }), input, send,
  h('button', { class: 'btn btn-line', type: 'button', onclick: async () => {
    try { const result = await api(base + '/advance', { method: 'POST' }); if (active) { draw(result); if (!result.advanced) toast('No further scheduled check-in.'); } }
    catch (e) { fail(e); }
  } }, 'Simulate next scheduled check-in'));
  const reportFile = h('input', { type: 'file', accept: 'application/pdf,image/png,image/jpeg,image/webp', 'aria-label': 'Synthetic patient report' });
  reportFile.addEventListener('change', async () => {
    const file = reportFile.files[0]; if (!file) return;
    if (file.size > 10000000) { toast('Reports must be under 10 MB.', true); return; }
    try {
      const response = await fetch('/api/v1' + base + '/documents', { method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': file.type, 'X-CSRF-Token': session.csrf_token }, body: file });
      const result = await response.json(); if (!response.ok) throw new Error(result.error?.message || 'Upload failed');
      if (active) draw(result);
    } catch (e) { fail(e); } finally { reportFile.value = ''; }
  });
  simulator.append(h('label', { class: 'stack' }, 'Send a synthetic report for doctor review', reportFile));
  simulator.hidden = true;
  const memory = h('section', { class: 'panel stack' }, h('h3', { text: 'Patient-reported history' }));
  async function loadMemory() {
    const result = await api(base + '/memory');
    if (!active) return;
    memory.replaceChildren(h('h3', { text: 'Patient-reported history' }),
      h('p', { class: 'muted small', text: 'Unreviewed patient statements and uploaded report readings. These are separate from the approved visit.' }),
      ...result.items.map(i => h('p', { class: 'followup-text', text: `${i.kind.replaceAll('_', ' ')}: ${i.text}` })),
      ...result.documents.map(d => h('details', {}, h('summary', { text: d.reading.report_type || 'Uploaded report' }),
        h('p', { class: 'followup-text', text: d.reading.transcription }),
        ...d.reading.findings.map(f => h('p', { text: `${f.name}: ${f.value} ${f.unit || ''} · ${f.flag || 'flag unspecified'} · “${f.quote}”` })))));
  }
  let active = true;
  ui.cleanup = () => { active = false; };
  const start = h('button', { class: 'btn btn-line', type: 'button', onclick: async () => {
    start.disabled = true;
    try {
      const result = await api(base, { method: 'POST' });
      if (active) { join.replaceChildren(result.whatsapp_configured ? `Private invitation (valid once for 24 hours): ${result.join_command}` : '',
        result.join_url ? h('a', { class: 'btn btn-line', href: result.join_url, target: '_blank', rel: 'noopener', text: 'Open WhatsApp connection message' }) : ''); draw(result); }
    } catch (e) { fail(e); } finally { start.disabled = false; }
  } }, 'Start follow-up');
  async function reply(body) {
    send.disabled = true;
    try { const result = await api(base + '/messages', { method: 'POST', body }); if (active) { input.value = ''; draw(result); } }
    catch (e) { fail(e); } finally { send.disabled = false; }
  }
  function draw(result) {
    const c = result.conversation;
    title.textContent = c ? `${c.patient_name} · Follow-up` : 'Patient follow-up';
    consent.hidden = Boolean(c) || !result.reason?.includes('consent');
    status.textContent = c ? `Approved visit · ${LANG[c.language] || c.language} · ${c.plan.channel === 'simulated' ? 'Local simulator · no external delivery' : 'WhatsApp · ' + result.delivery}` : result.reason;
    delivery.replaceChildren(h('h3', { text: 'Report and requested audio' }),
      ...(result.deliveries || []).map(job => h('p', {}, h('b', { text: job.kind === 'report_pdf' ? 'Approved PDF: ' : `Prescription audio (${LANG[job.language] || job.language}): ` }),
        job.state.replaceAll('_', ' '), job.error ? ' · ' + job.error : '')),
      h('p', { class: 'muted small', text: 'Approval queues the PDF. The patient can ask VOICE for their native-language prescription audio. Outside the WhatsApp reply window, delivery waits for a patient message.' }));
    start.textContent = c ? 'Refresh private WhatsApp invitation' : 'Start follow-up';
    start.hidden = Boolean(c?.stopped) || Boolean(c && !result.whatsapp_configured);
    simulator.hidden = !c || c.stopped || c.plan.channel !== 'simulated';
    transcript.replaceChildren(...(c?.messages || []).map(m => h('section', { class: `panel stack followup-message ${m.sender}` },
      h('b', { text: m.sender === 'clinic' ? 'Clinic assistant' : 'Synthetic patient' }),
      h('p', { class: 'followup-text', text: m.text }),
      h('small', { class: 'muted', text: fmtTime(m.at) + (m.cites.length ? ' · Approved medicine: ' + m.cites.join(', ') : '') }),
      ...(result.receipts || []).filter(r => r.message_ref === m.id).map(r => h('span', { class: 'chip muted', text: 'WhatsApp: ' + r.status })),
      m.sender === 'clinic' && m === c.messages.at(-1) && c.plan.channel === 'simulated' && !c.stopped
        ? h('div', { class: 'row' }, m.buttons.map(b => h('button', { class: 'btn btn-line btn-sm', type: 'button', onclick: () => reply({ button: b.id }) }, b.label))) : '')));
    const open = (c?.tasks || []).filter(t => t.status === 'open');
    tasks.replaceChildren(h('h3', { text: 'Doctor follow-up tasks' }), ...open.map(t => h('div', { class: 'stack' },
      h('b', { text: t.kind.replaceAll('_', ' ') }), h('p', { class: 'followup-text', text: t.note }),
      h('button', { class: 'btn btn-line btn-sm', type: 'button', onclick: async () => {
        try { await api(`${base}/tasks/${t.id}/done`, { method: 'POST' }); await refresh(); } catch (e) { fail(e); }
      } }, 'Mark reviewed'))), open.length ? '' : h('p', { class: 'muted', text: 'No open tasks.' }));
    if (c?.stopped) status.textContent += ' · Patient stopped follow-up';
    transcript.scrollTop = transcript.scrollHeight;
    if (c) loadMemory().catch(fail);
  }
  async function refresh() { const result = await api(base); if (active) draw(result); }
  main().replaceChildren(h('a', { class: 'crumb', href: `#/encounters/${encounterId}` }, '← Approved visit'),
    title, status, consent, start, join, delivery, transcript, simulator, tasks, memory,
    h('button', { class: 'btn btn-line', type: 'button', onclick: () => refresh().catch(fail) }, 'Refresh conversation'));
  try { await refresh(); } catch (e) { fail(e); }
}

// ---------- Reference drawer (DESIGN.md section 10: beside the record, never in it) ----------

function openReference(context) {
  const drawer = document.getElementById('drawer');
  const name = context?.med ? (context.med.product_label || context.med.spoken_name) : null;
  const question = h('input', { class: 'input', placeholder: 'Ask about a medicine', value: name ? `What is ${context.med.spoken_name} used for?` : '' });
  const results = h('div');
  const note = h('p', { class: 'note', text: 'Reference passages from US drug labels (openFDA), India’s NLEM 2022 and the Jan Aushadhi list. They are not part of the record and are not checked against this patient.' });
  const ask = async q => {
    if (!q.trim()) return;
    results.replaceChildren(h('p', { class: 'muted', text: 'Searching…' }));
    try {
      const data = await api('/knowledge/search', { method: 'POST', body: { question: q,
        ...(context?.med ? { encounter_id: context.encounter.id, medication_id: context.med.id } : {}) } });
      put(results,
        data.scope ? h('p', { class: 'muted small', text: 'Limited to: ' + (data.scope.ingredients.join(', ') || 'no known ingredients') }) : '',
        data.results.length ? data.results.map(r => {
          const long = r.content.length > 520;
          const body = h('p', { text: long ? r.content.slice(0, 520) + '…' : r.content });
          return h('article', { class: 'hit' }, h('header', {}, h('span', { class: 'chip muted', text: SOURCE_TEXT[r.source] || r.source }),
            h('b', { text: r.title }), h('span', { class: 'muted small', text: r.section })), body,
            h('div', { class: 'row' }, long ? h('button', { class: 'btn btn-quiet btn-sm', type: 'button', onclick: e => { body.textContent = r.content; e.currentTarget.remove(); } }, 'Show all') : '',
              r.url ? h('a', { href: r.url, target: '_blank', rel: 'noopener noreferrer' }, 'Source ↗') : ''));
        }) : h('p', { class: 'muted', text: 'No reference passage found. Nothing is assumed.' }));
    } catch (e) { results.replaceChildren(h('p', { class: 'err', text: e.message })); }
  };
  const quick = ['Uses', 'Dose', 'Interactions', 'Pregnancy', 'Side effects'].map(topic => h('button', { class: 'btn btn-line btn-sm', type: 'button',
    onclick: () => { question.value = name ? `${context.med.spoken_name} ${topic.toLowerCase()}` : topic; ask(question.value); } }, topic));
  question.addEventListener('keydown', e => { if (e.key === 'Enter') ask(question.value); });
  drawer.replaceChildren(h('div', { class: 'ph' }, h('h3', { text: 'Reference' }),
    h('button', { class: 'btn btn-quiet', type: 'button', onclick: () => drawer.classList.remove('open') }, 'Close')),
    name ? h('p', { class: 'muted small', text: name }) : '', note, question, h('div', { class: 'row quick' }, quick), results);
  drawer.classList.add('open');
  question.focus();
  if (name) ask(question.value);
}

document.addEventListener('keydown', e => { if (e.key === 'Escape') document.getElementById('drawer')?.classList.remove('open'); });

// ---------- Start ----------

(async () => {
  try { session = await api('/me'); startApp(); } catch (e) { renderLogin(); }
})();
