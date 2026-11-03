"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, type ClinicTask, type Conversation, type Health, type Message, type Visit } from "@/lib/api";
import { MAX_SECONDS, toWav16k } from "@/lib/wav";

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
const VOICE_OFF = "Voice is off: add GNANI_API_KEY to the API's environment to use Gnani Prisma and Timbre.";

export default function Page() {
  const [visits, setVisits] = useState<Visit[]>([]);
  const [visitId, setVisitId] = useState<string | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [conv, setConv] = useState<Conversation | null>(null);
  const [tasks, setTasks] = useState<ClinicTask[]>([]);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [playing, setPlaying] = useState<string | null>(null);
  const [recording, setRecording] = useState<number | null>(null);
  const chatEnd = useRef<HTMLDivElement>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const player = useRef<HTMLAudioElement | null>(null);

  const voiceOn = health !== null && health.speech !== "off";
  // A conversation started from a real phone (private testing, runbook D-113): replies come only from the phone.
  const onWhatsApp = conv?.plan.channel === "whatsapp";

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

  const open = useCallback(
    (id: string, restart = false) =>
      run(async () => {
        setNotice(null);
        setVisitId(id);
        return api.start(id, restart);
      }),
    [run],
  );

  useEffect(() => {
    Promise.all([api.health(), api.visits()])
      .then(([h, list]) => {
        setHealth(h);
        setVisits(list);
        const first = list.find((v) => v.consent);
        if (first) return open(first.visit_id);
      })
      .catch(() =>
        setError("Cannot reach the follow-up API. Start it with: PYTHONPATH=services/api .venv/bin/uvicorn voicerx.app:app --port 8000"),
      );
  }, [open]);

  useEffect(() => {
    chatEnd.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [conv?.messages.length]);

  // Messages from the phone arrive through the webhook, so a WhatsApp conversation is polled.
  const conversationId = conv?.id;
  useEffect(() => {
    if (!onWhatsApp || !conversationId || busy) return;
    const timer = window.setInterval(async () => {
      try {
        const [next, open] = await Promise.all([api.conversation(conversationId), api.tasks()]);
        setConv((current) => (current && current.id === next.id ? { ...next, delivery: current.delivery } : current));
        setTasks(open);
      } catch {
        // the next poll tries again
      }
    }, 3000);
    return () => window.clearInterval(timer);
  }, [onWhatsApp, conversationId, busy]);

  const nextTouch = useMemo(
    () => conv?.plan.touches.filter((t) => t.status === "planned").sort((a, b) => a.due_at.localeCompare(b.due_at))[0],
    [conv],
  );
  const lastClinic = conv ? [...conv.messages].reverse().find((m) => m.sender === "clinic") : undefined;
  const openButtons = lastClinic && conv?.awaiting && lastClinic.buttons.length ? lastClinic.buttons : [];
  const visit = visits.find((v) => v.visit_id === visitId);

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

  const listen = async (m: Message) => {
    if (!conv) return;
    setError(null);
    setPlaying(m.id);
    try {
      let audioId = m.audio_id;
      if (!audioId) {
        // First play: Timbre synthesises this exact message once; later plays use the cached file.
        const voiced = await api.voice(conv.id, m.id);
        audioId = voiced.audio_url.slice("/audio/".length, -".mp3".length);
        const id = audioId;
        setConv({ ...conv, messages: conv.messages.map((x) => (x.id === m.id ? { ...x, audio_id: id } : x)) });
      }
      const url = api.audioUrl(audioId);
      player.current?.pause();
      const audio = new Audio(url);
      player.current = audio;
      audio.onended = () => setPlaying(null);
      audio.onerror = () => setPlaying(null);
      await audio.play().catch(() => setPlaying(null));
    } catch (e) {
      setPlaying(null);
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const toggleRecording = async () => {
    if (!conv) return;
    if (recorder.current) {
      recorder.current.stop();
      return;
    }
    setError(null);
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      setError("Microphone not available. You can send a synthetic voice note instead.");
      return;
    }
    const chunks: Blob[] = [];
    const rec = new MediaRecorder(stream);
    recorder.current = rec;
    const started = Date.now();
    const timer = window.setInterval(() => {
      const seconds = Math.floor((Date.now() - started) / 1000);
      setRecording(seconds);
      if (seconds >= MAX_SECONDS) rec.stop();
    }, 250);
    setRecording(0);
    rec.ondataavailable = (e) => chunks.push(e.data);
    rec.onstop = () => {
      window.clearInterval(timer);
      stream.getTracks().forEach((t) => t.stop());
      recorder.current = null;
      setRecording(null);
      const conversationId = conv.id;
      run(async () => api.voiceNote(conversationId, await toWav16k(new Blob(chunks, { type: rec.mimeType }))));
    };
    rec.start();
  };

  const sendSynthetic = () => {
    const text = draft.trim();
    if (!conv || !text) return;
    setDraft("");
    run(() => api.syntheticVoice(conv.id, text));
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
            <span>Approved visit</span>
            <select value={visitId ?? ""} onChange={(e) => open(e.target.value)} disabled={busy || !visits.length}>
              {visits.map((v) => (
                <option key={v.visit_id} value={v.visit_id} disabled={!v.consent}>
                  {v.source === "demo" ? "Demo" : "Approved run"} · {v.patient_name} · {v.medicines.join(", ")} ({v.language})
                  {v.consent ? "" : " · no follow-up consent"}
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
                if (visitId) return api.start(visitId);
              })
            }
            disabled={busy || !visitId}
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
            <span className="sim">
              {onWhatsApp ? "Real WhatsApp · private test" : health?.speech === "fake" ? "Simulated · fake voice" : "Simulated"}
            </span>
          </div>
          <div className="chat" aria-live="polite">
            {conv?.messages.map((m, i) => {
              const prev = conv.messages[i - 1];
              const newDay = !prev || day(prev.at) !== day(m.at);
              return (
                <div key={m.id}>
                  {newDay && <div className="day">{day(m.at)}</div>}
                  <Bubble
                    m={m}
                    voiceOn={voiceOn}
                    fake={health?.speech === "fake"}
                    playing={playing === m.id}
                    onListen={() => listen(m)}
                  />
                </div>
              );
            })}
            {notice && <div className="day">{notice}</div>}
            {onWhatsApp && conv?.delivery && <div className="day">Not sent yet: {conv.delivery}</div>}
            <div ref={chatEnd} />
          </div>
          {!onWhatsApp && openButtons.length > 0 && (
            <div className="quick">
              {openButtons.map((b) => (
                <button key={b.id} onClick={() => send({ button: b.id })} disabled={busy}>
                  {b.label}
                </button>
              ))}
            </div>
          )}
          {onWhatsApp ? (
            <div className="hints" role="note">
              This chat runs on real WhatsApp. Replies come from the phone; <strong>Advance</strong> sends the next
              check-in to it. Synthetic visits only, for private testing (see <code>docs/whatsapp-testing.md</code>).
            </div>
          ) : (
            <>
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
              {recording !== null ? (
                <div className="recording" role="status">
                  <span className="dot" aria-hidden /> Recording {recording}s / {MAX_SECONDS}s — tap ■ to send
                </div>
              ) : (
                <input
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  placeholder={conv?.stopped ? "Messages stopped" : "Type a message"}
                  aria-label="Message"
                  maxLength={2000}
                  disabled={busy || !conv}
                />
              )}
              {draft.trim() && recording === null ? (
                <>
                  <button
                    type="button"
                    className="round alt"
                    onClick={sendSynthetic}
                    disabled={busy || !conv || !voiceOn || draft.trim().length > 300}
                    aria-label="Send as synthetic voice note"
                    title={voiceOn ? "Send as a synthetic voice note (Timbre voice, transcribed by Prisma)" : VOICE_OFF}
                  >
                    🔊
                  </button>
                  <button type="submit" className="round" disabled={busy || !conv} aria-label="Send">
                    ➤
                  </button>
                </>
              ) : (
                <button
                  type="button"
                  className={`round ${recording !== null ? "stop" : ""}`}
                  onClick={toggleRecording}
                  disabled={busy || !conv || !voiceOn || conv.stopped}
                  aria-label={recording !== null ? "Stop and send voice note" : "Record a voice note"}
                  title={voiceOn ? "Record a voice note (up to 30 s). Only the transcript is kept." : VOICE_OFF}
                >
                  {recording !== null ? "■" : "🎤"}
                </button>
              )}
            </form>
            <div className="hints">
              {voiceOn ? (
                <>Tap ▶ on a message to hear it (Gnani Timbre). Record 🎤, or type and tap 🔊 for a synthetic voice note.</>
              ) : (
                <>{VOICE_OFF}</>
              )}
              <br />
              Try: <code>seene mein dard ho raha hai</code> · <code>Inhaler दिन में कितनी बार ले सकते हैं?</code> ·{" "}
              <code>Wysolone अभी बंद कर दूँ?</code> · <code>DOCTOR</code> · <code>STOP</code>
            </div>
            </>
          )}
        </section>

        <section className="doctor" aria-label="What the doctor sees">
          <h2>What the doctor sees</h2>
          <p className="muted">
            {visit
              ? `${visit.doctor_name} · visit on ${visit.visit_date} · approved by ${visit.approved_by}` +
                (visit.review_date ? ` · review ${visit.review_date}` : "")
              : ""}
          </p>
          <h3>
            Needs attention, all patients <span className="count">{tasks.length}</span>
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
                    <small>
                      {day(r.received_at)} {time(r.received_at)} ·{" "}
                      {r.transcript_source === "prisma" ? "voice note (Prisma)" : r.transcript_source}
                    </small>
                  </div>
                  <p className="quote">«{r.raw_text || "no speech heard"}»</p>
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
            message wording are drafts pending doctor and language review. Voice notes are transcribed and the recording
            is discarded.
          </p>
        </section>
      </main>
    </div>
  );
}

type BubbleProps = { m: Message; voiceOn: boolean; fake: boolean; playing: boolean; onListen: () => void };

function Bubble({ m, voiceOn, fake, playing, onListen }: BubbleProps) {
  return (
    <div className={`bubble ${m.sender} ${m.kind}`}>
      {m.kind === "answer" && <span className="tag">From your approved prescription</span>}
      {m.kind === "urgent" && <span className="tag">Urgent</span>}
      {m.voice && (
        <span className="tag voice">
          🎤 Voice note · {fake ? "fake transcription (offline test, no Gnani call)" : "transcribed by Gnani Prisma"}
        </span>
      )}
      <p>{m.voice && !m.text ? "(no speech heard)" : m.text}</p>
      {m.sender === "clinic" && m.buttons.length > 0 && (
        <div className="inline-buttons" aria-hidden>
          {m.buttons.map((b) => (
            <span key={b.id}>{b.label}</span>
          ))}
        </div>
      )}
      {m.sender === "clinic" && voiceOn && (
        <button className="listen" onClick={onListen} disabled={playing} aria-label="Listen to this message">
          {playing ? "♪ Playing…" : "▶ Listen"}
        </button>
      )}
      <time>{time(m.at)}</time>
    </div>
  );
}
