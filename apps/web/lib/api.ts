// Types mirror services/api/voicerx/contracts/followup.py. Synthetic data only.

export type Button = { id: string; label: string };

export type Message = {
  id: string;
  sender: "clinic" | "patient";
  kind: "text" | "summary" | "question" | "answer" | "urgent" | "system";
  text: string;
  buttons: Button[];
  at: string;
  touch_id: string | null;
  cites: string[];
};

export type Touch = {
  id: string;
  kind: "summary" | "tolerance" | "progress" | "end_of_course" | "review";
  due_at: string;
  questions: string[];
  medicine_ids: string[];
  status: "planned" | "sent" | "answered" | "skipped" | "expired";
};

export type Answer = { question: string; value: string; quote: string | null; medicine_id: string | null };

export type FollowUpRecord = {
  id: string;
  received_at: string;
  raw_text: string;
  transcript_source: "typed" | "prisma" | "button" | null;
  answers: Answer[];
  red_flags: string[];
  action: "recorded" | "answered" | "clarified" | "escalated" | "urgent" | "stopped";
  reply_text: string;
  reply_cites: string[];
};

export type DoctorTask = {
  id: string;
  kind: string;
  record_id: string | null;
  created_at: string;
  note: string;
  status: "open" | "done";
};

export type ClinicTask = DoctorTask & { conversation_id: string; patient_name: string; case_id: string };

export type Conversation = {
  id: string;
  synthetic: true;
  case_id: string;
  patient_name: string;
  doctor_name: string;
  clinic_name: string;
  language: string;
  visit_date: string;
  clock: string;
  plan: { touches: Touch[] };
  messages: Message[];
  records: FollowUpRecord[];
  tasks: DoctorTask[];
  awaiting: { touch_id: string; question: string } | null;
  stopped: boolean;
  advanced?: boolean;
};

export type DemoVisit = {
  case_id: string;
  synthetic: true;
  patient_name: string;
  doctor_name: string;
  clinic_name: string;
  language: string;
  visit_date: string;
  medicines: string[];
};

export const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function call<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(API + path, {
    method: body === undefined ? "GET" : "POST",
    headers: body === undefined || body === null ? undefined : { "Content-Type": "application/json" },
    body: body === undefined || body === null ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail.detail ? String(detail.detail) : `Request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  visits: () => call<DemoVisit[]>("/demo/visits"),
  start: (caseId: string) => call<Conversation>(`/demo/visits/${caseId}/start`, null),
  send: (id: string, body: { text: string } | { button: string }) =>
    call<Conversation>(`/conversations/${id}/messages`, body),
  advance: (id: string) => call<Conversation>(`/conversations/${id}/advance`, null),
  tasks: () => call<ClinicTask[]>("/clinic/tasks"),
  reset: () => call<{ reset: boolean }>("/demo/reset", null),
};
