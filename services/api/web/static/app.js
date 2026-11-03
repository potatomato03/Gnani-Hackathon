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
const LANG = { 'hi-IN': 'Hindi', 'en-IN': 'English', 'te-IN': 'Telugu', 'ta-IN': 'Tamil', hinglish: 'Hinglish',
  hindi: 'Hindi', english: 'English', tamil: 'Tamil', telugu: 'Telugu' };
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
        h('dl', {}, [['Languages offered', 'Hinglish, Hindi, English, Tamil, Telugu'],['Every line', 'Has a source'], ['Sent to patient', 'Only after approval']]
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
  const language = h('select', { class: 'input' }, [['hinglish', 'Hinglish'], ['hindi', 'Hindi'], ['english', 'English'], ['tamil', 'Tamil'], ['telugu', 'Telugu']]
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
  main().replaceChildren(...header(encounter),
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
  set_duration: 'Set duration', remove_medicine: 'Remove medicine', confirm_order: 'Confirm I said it', acknowledge: 'Acknowledge',
  edit_line: 'Edit line', remove_line: 'Remove line', add_line: 'Add a line', dismiss_item: 'Rule out finding' };
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

  // One editor at a time; every correction carries the doctor's reason (DESIGN.md section 7).
  function openEditor(action, target, host, issue, preset) {
    host.querySelector('.editor')?.remove();
    const reason = h('input', { class: 'input', placeholder: 'Why? For example: confirmed with the patient', required: true });
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
      if (preset && med) reason.value = `Heard “${med.spoken_name}”; meant ${preset.label}.`;
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
      h('label', { class: 'field' }, h('span', { text: 'Reason' }), reason),
      h('div', { class: 'row' },
        h('button', { class: 'btn btn-dark btn-sm', type: 'button', onclick: () => {
          if (!reason.value.trim()) { reason.focus(); return toast('Add a short reason for this correction.', true); }
          submit([{ action, target: fields._target ? fields._target() : target, value: value(), reason: reason.value.trim() }]);
        } }, 'Save correction'),
        h('button', { class: 'btn btn-quiet btn-sm', type: 'button', onclick: () => editor.remove() }, 'Cancel')));
    host.append(editor);
    editor.querySelector('input, select, textarea')?.focus();
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
            s.chosen_before ? h('span', { class: 'chip iris', text: `You chose this before (${s.chosen_before}×)` }) : ''),
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
      h('p', { class: 'muted small', text: 'Fingerprint ' + view.content_hash.slice(0, 12) + '. Approval, files and delivery have separate states; nothing has been sent to the patient.' }), files);
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
  const medsPanel = h('section', { class: 'panel' }, h('div', { class: 'ph' }, h('h3', { text: 'Prescription' }), h('p', { text: tableMeds.length ? 'Morning · Afternoon · Evening · Night' : 'No medicines started or changed.' })),
    tableMeds.length ? h('div', { class: 'wrapx' }, h('table', { class: 'meds' },
      h('thead', {}, h('tr', {}, h('th', { text: 'Medicine' }), ['M', 'A', 'E', 'N'].map(x => h('th', { class: 's', text: x })))),
      h('tbody', {}, tableMeds.map(m => {
        const cell = h('td', {},
          h('span', { class: 'mname', text: m.row.label }), h('span', { class: 'how', text: m.row.detail }),
          m.row.flags.length ? h('div', { class: 'attrs' }, m.row.flags.map(f => h('span', { class: 'chip miss', text: f.replaceAll('_', ' ') }))) : '',
          canEdit && m.standard?.length ? h('div', { class: 'standard' }, h('span', { class: 'chip iris', text: 'Standard' }), standardText(m),
            h('button', { class: 'btn btn-line btn-sm', type: 'button', onclick: () => submit(standardItems(m, m.standard)) }, 'Accept')) : '',
          h('div', { class: 'acts' },
            canEdit ? ['choose_product', 'set_dose', 'set_timing', 'set_food', 'set_duration', ...(m.speaker_unclear ? ['confirm_order'] : []), 'remove_medicine']
              .filter(a => a !== 'choose_product' || m.match !== 'exact' || m.candidates.length > 1)
              .map(a => h('button', { class: 'btn btn-quiet btn-sm', type: 'button', onclick: () => openEditor(a, m.id, cell) }, ACTION_TEXT[a])) : '',
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
        h('span', { class: 'sev', text: issue.severity === 'block' ? 'Must fix' : 'Warning' }), h('b', { text: issue.title }),
        h('p', { class: 'where', text: describe(issue) }),
        issue.title !== issue.message && !issue.message.startsWith(issue.code.replaceAll('_', ' ')) ? h('p', { class: 'where', text: issue.message }) : '');
      const med = issue.target_kind === 'medicine' ? medById[issue.target] : null;
      if (canEdit && med?.suggestions?.length && PRODUCT_CODES.includes(issue.code)) card.append(suggestionList(med, card, issue));
      if (canEdit && issue.actions.length) card.append(h('div', { class: 'choices' }, issue.actions.map(a => h('button', { class: 'btn btn-line btn-sm', type: 'button',
        onclick: () => (a === 'edit_line' || a === 'remove_line') && issue.target_kind === 'finding'
          ? (issue.lines[0] ? (showLine(issue.lines[0]), openEditor(a, issue.lines[0], evidence)) : null)
          : openEditor(a, issue.target, card, issue) }, ACTION_TEXT[a]))));
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
    h('div', { class: 'review' },
      h('div', { class: 'stack' }, approvePanel, reportPanel, medsPanel, sourcePanel),
      h('div', { class: 'aside' }, issuesPanel, evidence)));
  drawTranscript([]);
  if (ui.selectedLine && report.sections[ui.selectedLine.split(':')[0]]?.[Number(ui.selectedLine.split(':')[1])]) showLine(ui.selectedLine);
  else ui.selectedLine = null;
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
