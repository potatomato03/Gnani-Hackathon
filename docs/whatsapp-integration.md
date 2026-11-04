# Dashboard and WhatsApp follow-up integration

Implemented 4 November 2026. Bot source: `devansh/whatsapp-nlp-bot` at `bb8317d` in
[Gnani-Hackathon](https://github.com/potatomato03/Gnani-Hackathon/tree/devansh/whatsapp-nlp-bot).
The bot's agent, speech adapters, contracts and tests were ported selectively. The newer doctor dashboard,
medicine pipeline and application database remain the integration host.

## Run the local simulator

From the repository root, using the existing Python environment:

```powershell
$env:PYTHONPATH = 'services/api'
../.venv/Scripts/python -m voicerx.app.migrate
../.venv/Scripts/python tools/demo/followup_dashboard.py
../.venv/Scripts/python -m uvicorn voicerx.app.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/#/encounters/enc-followup-demo`. Development sign-in requires
`APP_DEV_LOGIN=1` in the ignored `.env`. The demo script creates a dedicated synthetic patient and draft
from cached stage fixtures, runs the actual extraction checks and report assembly, and makes no model or
speech call. It preserves an existing demo rather than overwriting approval or chat history.

1. Review and approve the synthetic draft. PDF/FHIR jobs still run independently.
2. Choose **Open patient follow-up**. A consented synthetic approval creates one follow-up automatically.
3. Choose Hindi or English. The bot shows the approved medicine instructions, with fixed wording and citations.
4. Use **Simulate next scheduled check-in** and the quick reply buttons, or type a medicine question.
5. Type `DOCTOR` to create a callback task; open **Follow-ups** in the top bar to see it. **Mark reviewed**
   closes the task and records the clinician action.
6. Type `STOP` to end the conversation. The same visit cannot be restarted to bypass that choice.

Existing synthetic patients may need **Record consent for synthetic follow-up**, then **Start follow-up**.
Consent is an audited patient preference. Current consent is checked again whenever the bot is used.
The doctor can revoke it through `POST .../followup/consent` with `{"enabled": false}`.

The simulator sends no WhatsApp message. Its advance control deliberately jumps a demo clock; it is unavailable
on a bound WhatsApp conversation. Free-text understanding and report reading use the configured model when
needed; rules, fixed replies and model-failure fallback remain available. Live Gnani calls are not used by the
dashboard's text simulator. The bot's speech and call modules are retained from the source branch; browser or
WhatsApp voice calling is not connected to the doctor workspace endpoint.

## End-to-end data flow

```text
Typed/recorded consultation → checked draft → doctor correction → immutable approved version
    ├─ PDF/FHIR artifact jobs → private approved PDF archive in Supabase
    ├─ durable PDF delivery → verified patient WhatsApp (no repeated JOIN on later visits)
    └─ eligible synthetic visit + consent + supported language → app.followups
          ├─ authenticated local patient simulator
          └─ optional signed Meta webhook → durable inbox → worker → fixed bot replies
                   ↓
          patient statements, check-in answers, STOP, questions and report readings
                   ↓
          saved conversation + per-patient memory + doctor follow-up tasks
          private original lab upload + quoted summary + doctor review status
                   ↓
          patient chart / next consultation / review: Between visits panel
```

The report in `app.report_versions` is the only clinical source. The bot revalidates its content hash and
current approved version. Patient statements and uploaded document readings do not edit prescriptions.
Patient history now uses private Supabase tables `app.patient_memory` and `app.patient_documents`, with RLS
enabled. The local fallback remains under `APP_ARTIFACTS_DIR/followup-memory`, with clinic/patient-derived keys;
no raw upload or phone number is stored there. Existing fallback history is included on reads but is not bulk
uploaded automatically. Back up that directory alongside application artifacts. Conversations,
tasks and check-in state live in Supabase's private `app.followups` table and survive a restart. PDF export
failures do not undo approval or follow-up creation.

Chat templates support Hindi and English; other native preferences use English chat. Complete prescription
audio supports English, Hindi, Tamil, Telugu and Gujarati, using structured approved medication values and
fixed language templates rather than model translation. Non-English wording remains a draft requiring
language review and is labelled in the audio. Template wording and warning-sign rules require independent
clinical and language review.

## Connected patient journey

On the patient chart, **Patient WhatsApp and native language** records the allowed test recipient,
language preference and consent. The raw number is not written to the chart; a keyed contact fingerprint
is retained. The patient's first one-use JOIN verifies the link. Later approved visits inherit it and
supersede the earlier bot session while preserving its records and tasks. Shared family numbers currently
require clinic reconciliation rather than silently linking two patients.

Approval queues the PDF only. The worker generates and archives the approved file, uploads it to Meta,
and sends it as a document. Actual signed receipts update accepted, delivered and read states in the UI.
Without a verified contact, file, or open 24-hour reply window, the job remains in an explicit waiting state.
There is no business-initiated report-ready template yet; outside that window, the patient must message
the bot to resume delivery. Optional `WHATSAPP_SENDER_NUMBER` enables a click-to-chat JOIN link.

The patient can use **Approved report PDF**, **Prescription voice**, and **Visit findings** from the menu,
or send `PDF`, `VOICE`, `VOICE in Tamil`, or `FINDINGS`. Audio is queued only after an explicit request,
including a supported request transcribed from a patient voice note. It reads every approved active/stopped
medicine's product, dose, schedule (including taper steps), route, food, duration and start condition;
missing instructions stay missing. An incoming voice note alone does not trigger an outgoing voice note.
The immutable approved visit determines the default native language; saved preferences apply to future visits.

Questions, cited replies, requests and doctor tasks are visible across encounters in **Between visits**
on the patient chart, capture screen and draft review screen. PDF/photo lab uploads are summarized with
source quotations for the doctor, never used to independently change treatment. Accepted originals up to
10 MB are stored privately with a SHA-256 fingerprint. If reading fails, the original is retained with a
manual-review task and a truthful patient acknowledgement. Clinicians can download the original and mark
it reviewed. All these APIs use clinic scope, normal sessions and CSRF; none are public tunnel routes.

Migrations `006_patient_memory.sql` and `007_patient_journey.sql` create the private memory, contact,
outbox, approved PDF and upload tables with RLS. Original uploads have no public storage URL. These database
tables must be included in backups. Run `tools/demo/followup_dashboard.py --meta-test --next-visit` to prepare
`enc-journey-demo`, a second cached synthetic consultation for the already-linked phone-test patient.

## Doctor APIs

All these routes require the normal server session and organisation membership. POST requests require CSRF.

| Route under `/api/v1` | Purpose |
|---|---|
| `GET /encounters/{id}/followup` | Conversation, eligibility and actual transport receipts |
| `POST /encounters/{id}/followup` | Idempotent start and rotate one-use WhatsApp invitation |
| `POST /encounters/{id}/followup/consent` | Record/revoke synthetic follow-up consent |
| `POST /encounters/{id}/followup/messages` | Simulated patient text or quick button |
| `POST /encounters/{id}/followup/advance` | Advance only the simulator's next check-in |
| `POST /encounters/{id}/followup/documents` | PDF/photo body, maximum 10 MB, for doctor review |
| `GET /encounters/{id}/followup/memory` | Patient-reported history and unreviewed report readings |
| `GET /followup/tasks` | Open tasks for the current clinic |
| `POST /encounters/{id}/followup/tasks/{task_id}/done` | Audited task completion |
| `GET /patients/{id}/journey` | Cross-visit questions, replies, tasks, lab summaries and review status |
| `POST /patients/{id}/whatsapp-target` | Consented allowed-recipient target and native preference |
| `GET /patient-uploads/{id}/download` | Private, fingerprint-checked original lab file |
| `POST /patient-uploads/{id}/review` | Audited clinician review stamp |

The upstream standalone demo is retained as `voicerx.followup_api` for its regression tests. It is not mounted
in the doctor application. Use `voicerx.app.main:app` for the integrated workflow.

## Optional Meta transport

The initial integration used local simulation. On 4 November the user supplied Meta credentials and requested
a private test to their own phone. Those credentials are now loaded only into the ignored `.env`; the local
allowlist is restricted to that explicitly requested recipient. Meta's token and sender-number checks passed.
The first test template was rejected with error `131030`. After the user added the recipient in Meta, a retry
was accepted and its message ID/status were recorded in Supabase. Provider acceptance is not delivery
confirmation. The following transport is implemented:

- HMAC-SHA256 verification, business phone-ID checking, a bounded webhook body and test-number allowlist.
- A clinician-issued random invitation, stored hashed, valid once for 24 hours. A phone cannot select a
  patient by claiming a patient ID or choosing from an exposed list of visit codes.
- Verified message IDs enter `app.whatsapp_events` before HTTP acknowledgement. The worker persists progress,
  retries transient processing failures up to three times and suppresses replay across service restarts.
- Replies, quick buttons, patient audio and PDF/photo reading reuse the imported agent. Phone numbers are
  reconstructed only from the configured test allowlist and are not stored in the inbox/conversation.
- Provider acceptance, `sent`, `delivered`, `read` and `failed` remain distinct receipt states. The UI does not
  equate approval or a simulated summary with patient delivery.
- Scheduled WhatsApp check-ins run only while the customer-service window is open and inside sending hours.
  Outside that window they wait for the patient's next message; no business-initiated template is implemented.

For the phone test, `voicerx.webhook_proxy:app` on port 8001 exposes only `/whatsapp/webhook`, caps requests at
1 MB and forwards the signature to the doctor app on port 8000. All dashboard, authentication and static-file
paths return 404 through this proxy. Access logs are disabled so verification tokens are not logged. A
Cloudflare tunnel must target **8001**. The user explicitly approved relaying their WhatsApp test messages and
Meta delivery events through Cloudflare. The temporary tunnel is running, public route-boundary checks passed,
and Meta verified and accepted the replacement webhook subscription. A separate `enc-whatsapp-demo` synthetic
visit was prepared for the phone test; binding it requires the one-use JOIN invitation supplied privately.
The invitation and temporary callback hostname are under ignored `runs/whatsapp-integration`, not in source.
The real phone test completed: JOIN bound the visit, English and My medicines buttons worked, and a DOCTOR
reply created an open callback task plus a `request` row in private Supabase memory. Five bot messages had
Meta `read` receipts at verification. The JOIN invitation has been consumed.

The connected journey was subsequently tested with `enc-journey-demo`, a second synthetic consultation for
the same patient. Approval automatically reused the verified channel, generated PDF/FHIR, privately archived
the 81,344-byte PDF, and sent the PDF through Meta. The user's explicit `VOICE` request generated the complete
Hindi medicine instructions through Gnani and sent a 31.92-second Ogg Opus voice note. Both PDF and audio
received signed Meta `read` receipts. The real-phone question `How do I take Dolo ?` was answered with approved
medicine citation `rx1` and appears in the cross-visit history API beside the earlier DOCTOR request.
The user explicitly approved Gnani processing of the synthetic prescription. Original lab retention, quoted
summaries, manual-review fallback and signed upload routing were tested using rollback-only synthetic
fixtures and fake provider transports; no actual phone-uploaded lab or live lab-reading model was claimed.

The shared Meta app's callback changed to another relay during testing. The approved webhook-only relay was
restored and verified before the successful phone checks. If another teammate uses this same Meta app, agree
on a single active webhook; do not run competing tunnel configuration jobs. The dashboard stays private.
Gnani's documented `container=ogg` returns Opus; the actual sent file was also decoded and checked locally.
See [Gnani audio format reference](https://docs.gnani.ai/api/TTS/tts-inference).

During setup, the Meta app callback changed to a different tunnel after verification. Restoring the approved
callback resolved the missing JOIN. If several developers use the same Meta app, coordinate callback changes;
an app-level callback replacement can redirect another developer's inbound messages. Redacted signed-webhook
diagnostics record only event kinds, counts, sender lengths and filter outcomes in the private audit log.
Keep development sign-in private. Calling is explicitly rejected by this integrated endpoint;
the upstream standalone calling demo requires its optional `aiortc` dependency and separate validation.

Outbound provider calls and a database commit cannot be one atomic transaction. If a process fails after Meta
accepts a send but before the local transaction commits, a retry can duplicate that outbound message. The
durable inbox guarantees deduplicated completed inbound events, not exactly-once provider delivery.

## Validation

The combined pipeline and imported agent regression suite runs with:

```powershell
../.venv/Scripts/python -m pytest services/api/tests -q
node --check services/api/web/static/app.js
```

The dashboard integration tests use real Postgres with isolated synthetic fixtures and roll back every database
change. No speech/model provider or Meta endpoint is called:

```powershell
$env:VOICERX_TEST_APP_DB = '1'
../.venv/Scripts/python -m pytest services/api/tests/integration/test_dashboard_followup.py -q
../.venv/Scripts/python -m pytest services/api/tests/integration/test_patient_journey.py -q
Remove-Item Env:VOICERX_TEST_APP_DB
```

They cover approval-to-chat-to-task flow, grounded medicine answers, unchanged approved JSON, consent, STOP,
CSRF, clinic isolation, restart persistence, signed inbox enqueue, one-use invitations, duplicate events,
receipt ordering, simulated check-ins and warning-sign escalation.

Earlier port verification on 4 November 2026: **801 passed, 3 skipped** across `services/api/tests` and `tools`,
including all five rollback-only dashboard integration tests. Skips cover the optional WebRTC loopback and
the separately opted-in legacy memory-store checks. JavaScript syntax and whitespace checks passed. Browser
verification covered actual dashboard approval, PDF/FHIR readiness, language choice, approved instructions,
callback creation, the clinic task inbox, and conversation persistence after an application restart.

Connected-journey verification: the broad API/agent run passed 639 tests with 3 optional skips; the tools
suite passed 181 tests. After the final additions, all 22 patient-journey/native-prescription tests passed
against rollback-only Postgres fixtures and local provider fakes. This includes cross-clinic download/review
denial, CSRF, consent revocation, PDF recovery without the local file, signed lab uploads, missing-summary
fallback, taper/stopped medicines and spoken delivery requests. Syntax and key-leak checks passed. Live phone
PDF, requested Hindi audio and a grounded medication answer are verified separately above. Browser automation
was unavailable for the latest UI, so its underlying authenticated APIs and JavaScript syntax were checked;
the earlier dashboard screenshots do not count as visual verification of the new Between visits panel.
