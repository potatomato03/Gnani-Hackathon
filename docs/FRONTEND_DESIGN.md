# VoiceRx doctor dashboard: design guide and connection sheet

*v2, 5 Nov 2026. Frontend by Rakshit. For Astra, Aditya's Claude.*
*Written against `DASHBOARD_AND_API.md` (5 Nov). Replaces v1. Rakshit does not push to the repo; Astra owns the commits.*

**The design is final direction, not a suggestion.** The 4 Nov look stays. Don't restyle it with the old `app.css`. Everything new extends the same colours, type and components.

---

## 1. What's in the zip

```
web/
  login.html                 Served at "/" when signed out
  index.html                 Served at "/" when signed in
  auth-assets/               Public. Must load before sign-in.
    base.css                 Colours, type, buttons, moving background
    login.css, login.js      Sign-in page
    demo-account.js          DEMO ONLY. Do not ship.
  static/                    Locked until sign-in
    app.css, app.js          The whole doctor app
    mock.js                  DEMO ONLY. Do not ship.
contract_stub.py             Stand-in API for testing (section 6)
DESIGN.md                    This file
```

To see it in demo mode:

```bash
python -m http.server 5173 --directory web
```

Open `http://localhost:5173/login.html` and use "Fill in the demo account".

---

## 2. How to put it in the repo

1. **Split matches your middleware.** `/static` is locked in hosted mode and the login page can only load `/auth-assets/{name}`. So login has its own page and its own assets, and holds no product data.
2. Copy `web/auth-assets/*` (except `demo-account.js`) into the folder behind `/auth-assets/{name}`, and allow `base.css`, `login.css`, `login.js`.
3. Copy `web/static/app.css` and `app.js` into `services/api/web/static/`, replacing the current ones.
4. Serve `login.html` and `index.html` from `GET /` by session state.
5. **Delete the two "Demo only" lines**: one `<script>` in `login.html`, one in `index.html`. With `mock.js` gone, the page talks to `/api/v1`. Nothing else switches it.
6. The doctor app also loads `auth-assets/base.css`, so `GET /auth-assets/base.css` must work when signed in.
7. CSP: no inline scripts, no inline styles, no `style=""` attributes, no `data:` images. It only needs Google Fonts (`fonts.googleapis.com`, `fonts.gstatic.com`) and `blob:` for media (listening back to a recording). No build step, no dependencies.
8. Add a cache-busting version to the asset URLs. Stale CSS and JS caused real confusion while testing this, the same drift your audit flagged.

**Credentials:** nothing real lives in the browser. `demo-account.js` is a made-up value for the mock only. In production the shared account stays in server configuration.

---

## 3. Design rules to keep

**Colour.** Gnani's sunrise on warm paper.

| Name | Value | Use |
|---|---|---|
| Paper | `#FBF8F3` | Page |
| Ink | `#16171C` | Text, main buttons |
| Saffron | `#F5964A` | Sun gradient, counts |
| Marigold | `#FFD27A` | Dose numbers, sentence highlight |
| Blush | `#F2B4C4` | Sun gradient |
| Periwinkle | `#8E9CF7` | Sun gradient |
| Iris | `#4A4FCB` | Links, focus rings |
| Green / Amber / Rose | `#11704E` / `#875003` / `#A5283F` | On track / slightly off / missed. Never colour alone: each has words too. |

**Type.** Instrument Serif for headings, Geist for everything else. Body is 17px. Sizes are in `rem` so the Large text setting works. Sentence case. No all-caps labels.

**Shape.** Black pill for the main action. The sun gradient is only for the record orb, `Start a new visit`, `Open follow-up` and avatars. Only the visit card and the sign-in card are raised; everything else uses a thin border.

**Motion.**
- The background drifts slowly behind every screen. **Display > Background motion** turns it off, as required for anything moving longer than 5 seconds. Login has **Pause animation**.
- Interface motion is under 300 ms with a strong ease-out. Buttons press to 0.97.
- One-off moments only: list stagger on arrival, report sections revealing once, the record orb breathing until pressed, the checkmark drawing on approval.
- Nothing moves on the login features section, on purpose.
- `prefers-reduced-motion` removes all movement. Motion is never the only signal of a change.

**For non-technical doctors.** At least 44px tap targets. Plain words: "Check", not "resolve". Every error says what to do next. One stepper: Record, Check, Approve. Approve explains why it's locked.

---

## 4. Screens and routes

| Hash route | Screen | API calls |
|---|---|---|
| none | Sign-in page (`login.html`) | `POST /auth/login {username, password}`, `GET /auth/options`, `GET /auth/dev-users`, `POST /auth/dev-login` (dev only). On success the page reloads `/`. |
| all | App start | `GET /me`. A `401` reloads `/`. Any other failure shows a retry screen. |
| all | Sign out | `POST /auth/logout` |
| `#/workspace` | Hospitals, doctors, add a doctor | `GET /workspace/hospitals`, `GET /workspace/hospitals/{id}/doctors`, `POST .../doctors`, `POST /workspace/select` |
| `#/register` | Register patient | `POST /patients` (doctors from the roster route) |
| `#/patients/{id}` | Sidebar + patient: record on top, last visit, check-ins, past visits at the bottom | `GET /patients?list=&q=&doctor_id=`, `GET /patients/{id}`, `GET /patients/{id}/journey`, `GET /encounters/{id}/report?version=`, `GET /followup/tasks` |
| `#/encounters/{id}` | Same screen, that visit open | `GET /encounters/{id}` to find the patient |
| same | Capture | `POST /patients/{id}/encounters`, `POST /encounters/{id}/sources`, `POST /encounters/{id}/sources/audio?language=` (up to 3 MiB), or `POST .../audio-uploads`, `PUT /audio-uploads/{uid}/parts/{n}`, `POST .../complete` above that |
| same | Processing | `POST /encounters/{id}/runs`, `GET /runs/{id}` (1.2 s, then 2 s; 8 s if the tab is hidden; backs off to 15 s on errors), `POST /runs/{id}/retry` |
| same | Review | `POST /encounters/{id}/resolutions`, `GET /catalog/search?q=`, `GET /encounters/{id}/shortlist` (only on "Show common choices", since it can call a model), `POST /knowledge/search`, `GET /encounters/{id}/preview.pdf?version=` |
| same | Approve and files | `POST /encounters/{id}/approvals`, `GET /encounters/{id}/artifacts`, `GET /artifacts/{id}/download` |
| same | WhatsApp delivery | `GET /encounters/{id}/clinic-reports` (every 2.5 s until read or failed), `POST .../clinic-reports/retry` |
| `#/followups` | Task list | `GET /followup/tasks`, `POST /encounters/{eid}/followup/tasks/{tid}/done` |
| `#/followup/{id}` | Conversation, tasks, memory, reports | `GET` and `POST /encounters/{id}/followup`, `POST .../followup/messages`, `POST .../followup/advance`, `POST .../followup/documents`, `GET .../followup/memory`, `POST /patient-uploads/{id}/review`, `GET /patient-uploads/{id}/download` |

Every change sends `X-CSRF-Token` from the session. Audio sends `X-Recording-Consent: patient-agreed`. Errors show `error.message` as written, so keep those messages plain.

**Not in the UI yet:** `POST /patients/{id}/whatsapp-target`, `POST /encounters/{id}/followup/consent`, `POST /catalog/products`, `GET /patients/{id}/samples`, playing back stored audio, and showing the transcript on the review screen. They're easy to add in the same style if you want them for the demo.

---

## 5. Field names the UI assumes

**The API doc doesn't give these response shapes, so please confirm them.** `adapt` near the top of `static/app.js` is the only place that knows field names, and it already accepts several spellings. Change it there, or change the response. Screens don't need touching. `contract_stub.py` has a working example of each shape.

| Response | Fields used |
|---|---|
| `/me`, `/workspace/select` | `csrf_token`, `scope{organisation_id, organisation_name, timezone}`, **`workspace{admin, hospital{id,name}, doctor{id,display_name}}`** |
| Hospitals, doctors | `items[]`: hospital `{id, name, city}`, doctor `{id, display_name or name, specialty}` |
| `/patients` | `items[]`: `id, name, birth_year or age, sex, language, allergy_status, allergies[], last_visit_date, visit_state, blocking_count`. Optional: `appointment_time, reason, followup_status, phone_last4` |
| `/patients/{id}` | `patient`, `encounters[]`: `id, date, state, approved_version, diagnosis`. Optional: `consents.recording` |
| `/patients/{id}/journey` | `questions[]`, `uploads[]{id, filename, summary, reviewed}`. Optional: `adherence` (below) |
| `/encounters/{id}` | `patient{...}` or `patient_id`, `latest_run` or `run` |
| `/runs/{id}` | `id, state, steps[]{key, label, state}, error.message` |
| Report | `version, content_hash, status, date, can_approve, blocking_count, findings{id:{quote, assertion, certainty}}, approval{approved_by, approved_at}, artifacts[]{id, kind, state}`. `report_groups[]` with either `lines[]{ref, text, cites[]}` or `sections[]` read from `report[section]` |
| `medication_views[]` | `id, label, composition, action, dose{amount, unit}, schedule, food, duration{value, unit}, filled{field: source}, unresolved`. Optional: `display` (a ready-made sentence, used instead of building one). `schedule.kind`: `slots{slots:[m,a,e,n]}`, `frequency{times_per_day}`, `as_needed{max_per_day}`, `taper`, `unresolved{phrase}` |
| `issue_views[]` | `id, severity, title, message, actions[]{label, resolutions[]}`. Each button sends its `resolutions` unchanged. **An action without `resolutions` gets no button.** |
| Clinic reports | `items[]{id, kind: pdf|voice, status}`, with the statuses from your doc |
| Tasks | `items[]{id, encounter_id, patient_name, title, detail, status}` |
| Follow-up | `status, reason, messages[]{direction: in|out, text, at, buttons[]{id, title}}` |
| Memory | `items[]{text}`, `documents[]` |

**Resolutions the UI writes itself**, with `expected_version` and `expected_content_hash`:

| Action | `value` | From |
|---|---|---|
| `set_dose` | `{amount, unit}` | Medicine editor |
| `set_timing` | `{kind: "slots", slots:[m,a,e,n]}` or `{kind: "as_needed"}` | Medicine editor |
| `set_food` | `"after_food"` and so on | Medicine editor |
| `set_duration` | `{value, unit: "day"}` | Medicine editor |
| `add_medicine` | `{product_id, label, composition}` | Find a medicine |
| `remove_medicine` | none | Medicine editor |
| `edit_line` | new text, `target` is `section:index` | Tap a sentence |
| `remove_line` | none, `target` is `section:index` | Tap a sentence |

Only `set_dose` is confirmed by your docs. Please check the other `value` shapes.

**Nice to have:** `adherence` on the journey gives the 7-day dose grid, in this shape:

```json
{ "status": "slightly_off", "label": "Slightly off track", "summary": "Took 5 of 7 night doses.",
  "days": ["Thu","Fri","Sat","Sun","Mon","Tue","Wed"],
  "rows": [{ "medicine": "Cetzine", "cells": ["taken","taken","missed","missed","taken","taken","not_due"] }],
  "last_message": { "text": "Fever is less now.", "at": "2026-11-05T08:12:00+05:30" } }
```

Without it, the panel shows the questions and uploaded reports instead.

---

## 6. Testing against a stand-in API

```bash
python contract_stub.py
```

Open `http://localhost:5180`. The stub behaves like hosted mode: demo files are stripped, `/static` is locked before sign-in, CSRF is enforced on every change, and a strict CSP is on.

**What was tested on it:** sign-in (wrong and right password), hospital, doctor, patient, typed notes, processing, tapping a sentence, answering a check, approving, files and delivery. It passed with no CSP errors.

**What it does not prove:** the stub uses the shapes in section 5, not your real responses, so it hasn't been run against the real backend. Audio upload, the follow-up conversation and registration were tested in demo mode only.

---

## 7. Decisions for Rakshit and Astra

- **Hospital tab removed from login.** Everyone now signs in with one shared account and picks the hospital after, so the 4 Nov Doctor/Hospital tabs had nothing to do.
- **Editor limits.** The medicine editor handles slots and "when needed". It warns before replacing a taper or a frequency. A fuller editor is still needed for those.
- **WhatsApp copy.** The Approve bar says the PDF goes to the patient on WhatsApp "if they agreed", because delivery depends on consent, the allowed test numbers and Meta's messaging window.
