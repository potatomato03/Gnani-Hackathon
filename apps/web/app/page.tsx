"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, type ClinicTask, type Conversation, type DemoVisit, type Message } from "@/lib/api";

const IST = "Asia/Kolkata";
const time = (iso: string) =>
  new Intl.DateTimeFormat("en-IN", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: IST }).format(new Date(iso));
const day = (iso: string) =>
  new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric", timeZone: IST }).format(new Date(iso));

const TASK_LABEL: Record<string, string> = {
  urgent: "Urgent",
  worse: "Feels worse",
  side_effect: "Side effect",
  stopped_medicine: "Stopped medicine",
  question: "Question",
  callback: "Wants a call",
  consult_request: "Appointment",
  no_response: "No response",
};
const TOUCH_LABEL: Record<string, string> = {
  summary: "Visit summary",
  tolerance: "New-medicine check",
  progress: "Mid-course check",
  end_of_course: "End-of-course check",
  review: "Review reminder",
};

export default function Page() {
  const [visits, setVisits] = useState<DemoVisit[]>([]);
  const [caseId, setCaseId] = useState("fam-001-a");
  const [conv, setConv] = useState<Conversation | null>(null);
  const [tasks, setTasks] = useState<ClinicTask[]>([]);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const chatEnd = useRef<HTMLDivElement>(null);

  const run = useCallback(async (step: () => Promise<Conversation | void>) => {
    setBusy(true);
    setError(null);
    try {
      const next = await step();
      if (next) setConv(next);
      setTasks(await api.tasks());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, []);

  const startVisit = useCallback(
    (id: string) =>
      run(async () => {
        setNotice(null);
        return api.start(id);
      }),
    [run],
  );

  useEffect(() => {
    api
      .visits()
      .then((list) => {
        setVisits(list);
        return startVisit("fam-001-a");
      })
      .catch(() => setError("Cannot reach the follow-up API. Start it with: PYTHONPATH=services/api .venv/bin/uvicorn voicerx.app:app --port 8000"));
  }, [startVisit]);

  useEffect(() => {
    chatEnd.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [conv?.messages.length]);

  const nextTouch = useMemo(
    () => conv?.plan.touches.filter((t) => t.status === "planned").sort((a, b) => a.due_at.localeCompare(b.due_at))[0],
    [conv],
  );
  const lastClinic = conv ? [...conv.messages].reverse().find((m) => m.sender === "clinic") : undefined;
  const openButtons = lastClinic && conv?.awaiting && lastClinic.buttons.length ? lastClinic.buttons : [];
  const visit = visits.find((v) => v.case_id === caseId);

  const send = (body: { text: string } | { button: string }) => {
    if (!conv) return;
    run(() => api.send(conv.id, body));
  };
  const advance = () => {
    if (!conv) return;
    run(async () => {
      const next = await api.advance(conv.id);
      setNotice(next.advanced ? null : "Nothing more is scheduled for this visit.");
      return next;
    });
  };

  return (
    <div className="shell">
      <div className="banner" role="note">
        SYNTHETIC DATA — demo only, not for clinical use. Every patient, doctor and message here is made up.
      </div>
      <header className="topbar">
        <div className="brand">
          <span className="logo" aria-hidden>Rx</span>
          <div>
            <h1>VoiceRx follow-up</h1>
            <p>After the doctor approves a prescription, the assistant follows up with the patient.</p>
          </div>
        </div>
        <div className="controls">
          <label className="field">
            <span>Visit</span>
            <select
              value={caseId}
              onChange={(e) => {
                setCaseId(e.target.value);
                startVisit(e.target.value);
              }}
              disabled={busy}
            >
              {visits.map((v) => (
                <option key={v.case_id} value={v.case_id}>
                  {v.patient_name} · {v.medicines.join(", ")} ({v.language})
                </option>
              ))}
            </select>
          </label>
          <button className="primary" onClick={advance} disabled={busy || !conv || conv.stopped}>
            Advance to next check-in
            {nextTouch ? <small>{day(nextTouch.due_at)}</small> : <small>none left</small>}
          </button>
          <button
            className="ghost"
            onClick={() =>
              run(async () => {
                setNotice(null);
                await api.reset();
                return api.start(caseId);
              })
            }
            disabled={busy}
          >
            Reset demo
          </button>
        </div>
      </header>

      {error && <div className="error" role="alert">{error}</div>}

      <main className="panes">
        <section className="phone" aria-label="Patient's WhatsApp chat (simulated)">
          <div className="phone-head">
            <span className="avatar" aria-hidden>{conv?.clinic_name.slice(0, 1) ?? "C"}</span>
            <div>
              <strong>{conv?.clinic_name ?? "Clinic"}</strong>
              <small>AI assistant · {conv ? `for ${conv.patient_name}` : "…"}</small>
            </div>
            <span className="sim">Simulated</span>
          </div>
          <div className="chat" aria-live="polite">
            {conv?.messages.map((m, i) => {
              const prev = conv.messages[i - 1];
              const newDay = !prev || day(prev.at) !== day(m.at);
              return (
                <div key={m.id}>
                  {newDay && <div className="day">{day(m.at)}</div>}
                  <Bubble m={m} />
                </div>
              );
            })}
            {notice && <div className="day">{notice}</div>}
            <div ref={chatEnd} />
          </div>
          {openButtons.length > 0 && (
            <div className="quick">
              {openButtons.map((b) => (
                <button key={b.id} onClick={() => send({ button: b.id })} disabled={busy}>
                  {b.label}
                </button>
              ))}
            </div>
          )}
          <form
            className="compose"
            onSubmit={(e) => {
              e.preventDefault();
              const text = draft.trim();
              if (!text) return;
              setDraft("");
              send({ text });
            }}
          >
            <input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder={conv?.stopped ? "Messages stopped" : "Type a message"}
              aria-label="Message"
              maxLength={2000}
              disabled={busy || !conv}
            />
            <button type="submit" disabled={busy || !conv || !draft.trim()} aria-label="Send">
              ➤
            </button>
          </form>
          <div className="hints">
            Try: <code>seene mein dard ho raha hai</code> · <code>Inhaler दिन में कितनी बार ले सकते हैं?</code> ·{" "}
            <code>Wysolone अभी बंद कर दूँ?</code> · <code>DOCTOR</code> · <code>STOP</code>
          </div>
        </section>

        <section className="doctor" aria-label="What the doctor sees">
          <h2>What the doctor sees</h2>
          <p className="muted">
            {visit ? `${visit.doctor_name} · visit on ${visit.visit_date}` : ""} · Needs attention first; routine answers are
            collapsed.
          </p>
          <h3>
            Needs attention, all demo patients <span className="count">{tasks.length}</span>
          </h3>
          {tasks.length === 0 ? (
            <p className="empty">Nothing needs the doctor yet.</p>
          ) : (
            <ul className="tasks">
              {tasks.map((t) => (
                <li key={t.id} className={`task ${t.kind}`}>
                  <span className="badge">{TASK_LABEL[t.kind] ?? t.kind}</span>
                  <div>
                    <strong>{t.patient_name}</strong> <small>{day(t.created_at)} {time(t.created_at)}</small>
                    <p>{t.note}</p>
                  </div>
                </li>
              ))}
            </ul>
          )}

          <h3>Follow-up records</h3>
          {conv && conv.records.length > 0 ? (
            <ol className="records">
              {conv.records.map((r) => (
                <li key={r.id}>
                  <div className="rec-head">
                    <span className={`act ${r.action}`}>{r.action}</span>
                    <small>{day(r.received_at)} {time(r.received_at)} · {r.transcript_source}</small>
                  </div>
                  <p className="quote">«{r.raw_text}»</p>
                  {r.answers.map((a, i) => (
                    <p key={i} className="ans">
                      {a.question.replace(/_/g, " ")}: <b>{a.value.replace(/_/g, " ")}</b>
                    </p>
                  ))}
                  {r.red_flags.length > 0 && <p className="flag">Warning sign: {r.red_flags.join(", ")}</p>}
                  {r.reply_cites.length > 0 && <p className="ans">Answered from: {r.reply_cites.join(", ")}</p>}
                </li>
              ))}
            </ol>
          ) : (
            <p className="empty">No replies from the patient yet.</p>
          )}

          <h3>Follow-up plan</h3>
          <ol className="plan">
            {conv?.plan.touches.map((t) => (
              <li key={t.id} className={t.status}>
                <span>{TOUCH_LABEL[t.kind]}</span>
                <small>
                  {day(t.due_at)} {time(t.due_at)} · {t.status}
                </small>
              </li>
            ))}
          </ol>
          <p className="muted small">
            Planned by code from the approved report, 09:00–20:00 IST, at most five per visit. Warning-sign rules and
            message wording are drafts pending doctor and language review.
          </p>
        </section>
      </main>
    </div>
  );
}

function Bubble({ m }: { m: Message }) {
  return (
    <div className={`bubble ${m.sender} ${m.kind}`}>
      {m.kind === "answer" && <span className="tag">From your approved prescription</span>}
      {m.kind === "urgent" && <span className="tag">Urgent</span>}
      <p>{m.text}</p>
      {m.sender === "clinic" && m.buttons.length > 0 && (
        <div className="inline-buttons" aria-hidden>
          {m.buttons.map((b) => (
            <span key={b.id}>{b.label}</span>
          ))}
        </div>
      )}
      <time>{time(m.at)}</time>
    </div>
  );
}
