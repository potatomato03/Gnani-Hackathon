# Follow-up agent design

Status: **demo built** (text and buttons, simulated chat); see "As built" below. Voice, models and the real WhatsApp adapter are not built. It rests on [the research](../../research/followup-agent.md), which the bracketed `R` numbers below refer to: [R4] is source 4 there. The extraction and report backend it builds on is on `aditya/extraction-report`.

## Goal

After a doctor approves a visit, VoiceRx follows up with the patient by WhatsApp chat, WhatsApp voice note or a voice call:

- checks whether the medicines are tolerated and taken, and whether symptoms improve;
- answers questions only from the approved visit;
- passes everything else to the doctor;
- sends warning signs to urgent care at once;
- takes requests for a review or a new consultation.

Each exchange becomes a small structured record with quotes, which the doctor dashboard shows later.

## Decisions taken with the user

| Decision | Why |
|---|---|
| Our own agent behind a channel interface, connected to WhatsApp through the Cloud API, not Meta Business Agent | Meta Business Agent excludes the Health vertical [R1]. A clinic's own task-specific bot is allowed under WhatsApp's AI rule [R2][R3]. |
| The demo runs in a simulated WhatsApp-style chat in the web app, on synthetic patients | The challenge bans real phone numbers [R42], and seed numbers (`+91-00000-NNNNN`) can't receive WhatsApp |
| The real WhatsApp adapter is designed now, built behind the same interface, and switched off until the team decides | Keeps the demo honest about what would ship |

## Constraints

Every rule from `CLAUDE.md` holds. These matter most here:

- **Nothing before approval.** Follow-ups start from an `ApprovedReport` only. A draft never reaches a patient.
- **Answers come only from the approved record.** The agent may state a fact only if it is in the frozen approved report: medicine table, patient-language box, report lines. The case files' `allowed_claims` and `forbidden_claims` define this for tests.
- **Medicine wording comes from fixed templates.** Doses, timing and duration go out through the existing language templates (`exports/templates/lang/*.yaml`, `exports/patient_box.py`), never a model translation.
- **No clinical changes.** The agent never changes a dose, starts or stops a medicine, diagnoses, or interprets a new symptom. It records what the patient said and escalates.
- **Urgency is rules first.** A model may raise urgency, never lower it [R23].
- **Every record says `synthetic: true` in this project**, and the chat screen shows "SYNTHETIC DATA".
- **Speech costs credits.** Each Prisma or Timbre call needs the team's approval (hard rule 7). Tests use fakes and cached audio.

## Flow

```
ApprovedReport ──► plan_followups (code) ──► FollowUpPlan: touches with due times
                                                  │
     scheduler, every minute ◄────────────────────┘
          │  due touch, consent ok, quiet hours ok
          ▼
   ChannelAdapter.send(template)  ──►  patient
                                          │ reply: button, text or voice note
   ChannelAdapter.receive ◄───────────────┘
          │ voice note → Prisma transcript
          ▼
   route (code, then model) ──► red flag?  ──► urgent template + doctor alert
                             ──► check-in answer ──► FollowUpRecord
                             ──► question ──► grounded answer, or escalate
                             ──► "DOCTOR" / new consult ──► DoctorTask
          ▼
   doctor dashboard (later): exceptions first
```

## Units

New code lives in the planned `agent/` package (`services/api/voicerx/agent/`) and in `contracts/`. Each unit has one job.

| Unit | Job |
|---|---|
| `contracts/followup.py` | Pydantic models below. Extra fields forbidden, like the other contracts. |
| `agent/plan.py` | `plan_followups(approved, consents, now) -> FollowUpPlan`. Code only. |
| `agent/redflags.py` | Rules-first red-flag check per language, from a doctor-reviewed YAML list (`data/rules/red_flags.yaml`). |
| `agent/route.py` | Sorts an inbound message into check-in answer, question, red flag, human request, new consult, or stop. Buttons and keywords are handled by code; free text goes to the model with a fixed schema. |
| `agent/ground.py` | Builds an answer from the approved record and checks it, in the same style as Check 2: every claim must cite a record field, or the answer is replaced by an escalation. |
| `agent/gate.py` | Final check before anything is sent: consent, quiet hours, message cap, template use outside the 24-hour window, `synthetic` label. |
| `agent/channels/base.py` | `ChannelAdapter` interface. |
| `agent/channels/simulated.py` | Demo chat channel that the web app talks to. |
| `agent/channels/whatsapp.py` | Cloud API adapter: webhook in; template, interactive and audio messages out. Off by default. |
| `agent/channels/voice.py` | Gnani channel: Prisma for inbound voice notes and calls, Timbre for outbound voice notes. Used by the browser call. |
| `exports/templates/lang/*.yaml` | New `followup:` block: check-in questions, button labels, urgent message, escalation and stop replies, in hi, ta, te and en. Pending language review. |

## Plan: what gets sent, and when

Code builds the plan from the approved record. No model sets a time.

| Touch | When | Asks |
|---|---|---|
| `summary` | At approval | Visit summary and medicine instructions from the patient box, plus the AI disclosure and the "DOCTOR" and "STOP" keywords |
| `tolerance` | Day 2 after the start of any newly started medicine (from `ResolvedMedication.start` and the visit date) | "Any problem with the new medicine?" Buttons: No problem / Some problem / Stopped it |
| `progress` | Middle of the longest course, only if the course is 7 days or longer | "How are you now?" Buttons: Better / Same / Worse, and "Taking the medicines?" Buttons: Taking all / Missed some / Stopped |
| `end_of_course` | Last day of each course (`Duration`) | Same as `progress` |
| `review` | 2 days before the review date | Reminder plus "Can you come?" Buttons: Yes / Need another day |

- **Review date.** It's taken only from a structured value the doctor confirms at approval. It's never parsed from the model-written `follow_up` lines. If no review date is confirmed, no `review` touch is sent. This is an open question for the approval screen (Q-23 below).
- **Limits** (Assistant calls, to be reviewed):
  - at most one outbound touch a day and five per visit;
  - outbound only between 09:00 and 20:00 IST;
  - after two unanswered touches, stop and add a `no_response` item for the doctor [R26][R28].
- **Patient-initiated messages** are answered at any hour. Night use is normal [R11]. Answers at night still pass every check.

## Conversation rules

- **First message:**
  - "Assistant (AI) for Dr <name>'s clinic, about your visit on <date>."
  - "Reply DOCTOR to reach the clinic, STOP to stop messages."
  - The disclosure, the person's name and the one purpose all come first [R27].
- **Buttons first, free text and voice notes always accepted** [R15][R18].
- **Language:**
  - Replies use the patient's `language_pref`.
  - Code-mixed Hinglish is the default for `hi-IN` [R17].
  - Only fixed template text goes out for medicine instructions.
- **Questions:**
  - If the answer is fully in the record, answer it and cite it.
  - Otherwise reply "I'll ask Dr <name>" and create a `DoctorTask`.
  - Matches the case files' actions: `answer`, `clarify`, `escalate`, `urgent`.
- **Red flags:**
  - On any match, send the fixed urgent message in the patient's language ("go to the nearest emergency / call 108"), create an urgent `DoctorTask`, and stop the routine plan.
  - The list doesn't exist yet, and it needs doctor review before use. Example starting entries: chest pain, breathlessness, swelling of the face or throat, fainting, blood in vomit or stool. Each entry carries wording in every language.
- **New consultation or review request:** record a `DoctorTask` of kind `consult_request`. No triage beyond red flags.
- **STOP:** withdraws follow-up consent on the patient record, confirms once, and sends nothing more [R37][R45].
- **Never:** sell or order medicines [R44], ask for ID numbers [R43], or share one patient's chat with another.

## Contracts

```python
class FollowUpTouch(Strict):
    id: str
    kind: Literal["summary", "tolerance", "progress", "end_of_course", "review"]
    due_at: datetime
    medicine_ids: list[str] = []
    status: Literal["planned", "sent", "answered", "skipped", "expired"] = "planned"

class FollowUpPlan(Strict):
    visit_ref: str                 # case_id / visit id of the ApprovedReport
    report_hash: str               # content_hash of the approved report it was built from
    patient_id: str
    channel: Literal["simulated", "whatsapp", "voice"]
    language: str
    touches: list[FollowUpTouch]

class FollowUpAnswer(Strict):
    question: Literal["tolerance", "symptom_status", "adherence", "review_attendance"]
    value: str                     # button value or normalised code, e.g. "worse", "missed_some"
    quote: str | None              # verbatim patient text or transcript span, when free text
    medicine_id: str | None = None

class FollowUpRecord(Strict):
    id: str
    synthetic: Literal[True] = True
    clinic_id: str
    patient_id: str
    visit_ref: str
    report_hash: str
    touch_id: str | None           # None for patient-initiated messages
    channel: Literal["simulated", "whatsapp", "voice"]
    received_at: datetime
    raw_text: str                  # what the patient sent, or the transcript
    transcript_source: Literal["typed", "prisma", "button"] | None
    answers: list[FollowUpAnswer]
    red_flags: list[str]           # rule ids that fired
    action: Literal["recorded", "answered", "clarified", "escalated", "urgent", "stopped"]
    reply_text: str                # exactly what was sent back
    reply_cites: list[str]         # record fields the reply used

class DoctorTask(Strict):
    id: str
    kind: Literal["urgent", "question", "consult_request", "no_response", "worse", "stopped_medicine", "side_effect"]
    record_id: str | None
    patient_id: str
    visit_ref: str
    created_at: datetime
    status: Literal["open", "done"] = "open"
```

- **Consent values.** The patient record's `consents` gains `followup_whatsapp` and `followup_call`, separate from the existing `call`. Seed patients get them as synthetic values.
- **Storage.** Records are stored per clinic, patient and visit, the scope the `db/` package plans. Until the database exists, they are JSON files under `runs/` like the pipeline's outputs.

## Dashboard view (for the later build)

- **Per patient:** a timeline of touches and records with quotes.
- **Clinic home page:** open `DoctorTask`s, sorted urgent first, then worse, side effect, stopped medicine, question, consult request, and no response. Routine "better / taking all" answers are collapsed [R33].

## Channels

| Channel | Demo | Real use |
|---|---|---|
| Simulated chat | Yes: WhatsApp-style page in `apps/web` showing buttons, voice-note playback and the synthetic label | — |
| WhatsApp Cloud API | No | Utility templates for touches; interactive buttons; audio in by media URL [R38]; per-message charges from 1 Oct 2026 [R7][R8]; opt-in collected at the clinic [R37] |
| Browser voice call (Gnani) | Yes, for the call part of the demo | Same agent; Prisma in, Timbre out; target under about 1.2 s per turn [R23] |
| Outbound phone or WhatsApp call | No | Business-initiated WhatsApp calling isn't listed for India [R9]; telecom calls need TRAI compliance [R41]. Q-25. |

## Testing

- **Unit, test-first:**
  - the plan from approved fixtures (dates, caps, quiet hours, no review touch without a confirmed date);
  - each red-flag rule in each language;
  - routing of buttons and keywords;
  - gate refusals: no consent, after STOP, outside hours, a draft report, free text outside the 24-hour window on WhatsApp.
- **Grounding:** run the case files' `agent_questions` (29 today: 14 answer, 13 escalate, 2 urgent) through `route` and `ground`.
  - Pass if: the expected action matches, every allowed claim used is cited, and no forbidden claim appears.
  - Report the counts with coverage, e.g. "13 of 13 escalations", as the eval rules require.
- **Sabotage tests** in the style of Task 14b:
  - a model reply that changes a dose;
  - one that answers a question the record doesn't cover;
  - one that lowers an urgent message;
  - one that skips the AI disclosure.

  Each must be blocked by `ground` or `gate`.
- **New synthetic follow-up scenarios per family:** better, worse, side effect, missed doses, red flag, consult request, STOP, voice note. Written as YAML beside the cases, stopping at `auto_checked` until reviewed.

## Runbook entries

Recorded in `runbook.md` when the demo was built. The IDs first proposed here (D-94 to D-99, Q-23 to Q-26) had been taken by the medicine-knowledge work in the meantime, so they were renumbered:

| Runbook ID | Entry |
|---|---|
| D-104 | Own backend on the Cloud API, not Meta Business Agent |
| D-105 | Simulated WhatsApp chat demo on synthetic patients (Confirmed) |
| D-106 | Code-built touch plan from the approved report |
| D-107 | Sending hours, caps, stop after two unanswered |
| D-108 | Rules-first red flags; a model may only raise urgency |
| D-109 | One gate for every outbound message; disclosure, DOCTOR and STOP |
| D-110 | Demo visits through the real pipeline from saved stage outputs |
| Q-25 to Q-28 | Review date at approval; red-flag and template review; outbound calls; Gnani credits |

## As built (differences from the contracts above)

- `FollowUpTouch` also carries `questions`, the check-in questions it asks in order, because touches on the same day merge.
- `DoctorTask` also carries `note`, a one-line English summary with the patient's words, and a `callback` kind for "DOCTOR" requests.
- Follow-up wording lives in `services/api/voicerx/agent/templates/{hi,en}.yaml`, not inside the patient-box templates, so the PDF's templates stay untouched. Medicine rows still come from `exports/patient_box.py`. Telugu and Tamil follow-up wording is not written yet (Q-26).
- `Message`, `Awaiting` and `Conversation` hold the chat itself. All are in `services/api/voicerx/contracts/followup.py`.

## Out of scope

- Real WhatsApp numbers, real outbound calls, payments, medicine orders
- The doctor dashboard UI (the records and tasks are designed for it)
- Any clinical decision by the agent
- Production consent management under the DPDP Rules [R45]; the demo records consent flags only

## Open risks

- **Opinions aren't patient data.** Most opinion sources are builders and clinicians. Response rates must be measured in a pilot, not assumed.
- **WhatsApp's health clause.** It forbids health information where the law requires stronger safeguards [R43]. A real launch needs a legal read on DPDP and any health-data rules.
- **India's WhatsApp prices** aren't checked yet; they're in Meta's rate-card CSV [R7].
