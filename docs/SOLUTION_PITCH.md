# VoiceRX: speak the visit, the prescription writes itself

**One-page solution pitch · Gnani hackathon · November 2026**
Live demo: [gnani-private-clinic-demo.vercel.app/guest](https://gnani-private-clinic-demo.vercel.app/guest) (read-only guest doctor, synthetic patients)

## The problem

An Indian outpatient doctor sees dozens of patients a day, often in Hinglish or a regional language. Notes are typed or handwritten after the patient leaves, prescriptions are hard to read, and the patient goes home with instructions in a language they may not read well. Once they leave, the clinic hears nothing until the next visit: missed doses, side effects and new lab reports stay invisible.

## The solution

VoiceRX listens to the consultation, drafts the report and prescription for the doctor to check, and then stays with the patient on WhatsApp.

1. **Speak.** The doctor records the visit as usual, in Hinglish, Hindi, English, Tamil, Telugu or Gujarati. **Gnani** turns speech into text while they talk.
2. **Check.** VoiceRX extracts complaints, findings, diagnosis and medicines. Every line links to the words it came from, and anything unclear is asked, not guessed.
3. **Prescribe.** Medicines are matched to about 2.5 lakh Indian brands, with usual dose and food instructions filled in for the doctor to confirm.
4. **Approve.** One click produces a versioned, fingerprinted prescription PDF and a FHIR health record (the format India's ABDM uses).
5. **Follow up.** The patient gets the PDF on WhatsApp and can tap for a **Gnani voice note** of their prescription in their own language. Check-ins track doses. Questions, callback requests and uploaded lab reports come back to the doctor as tasks and a "since the last visit" summary.

## Why it is different

- **The doctor stays in charge.** Nothing reaches the patient until the doctor approves, and every AI sentence shows its source.
- **Built for India.** It works in local languages and code-mixed speech, uses Indian brand names, and follows up through WhatsApp, which patients already use.
- **Closes the loop.** Most scribes stop at the note. VoiceRX carries the visit into the patient's week and back to the next consultation.

## What is built and running

- A hosted doctor dashboard (FastAPI, Supabase Postgres, Vercel) with hospital, doctor and patient workspaces, recording, review, approval, PDFs and FHIR export.
- A live Meta WhatsApp bot that delivers reports, sends voice notes on request, answers from the approved report, and raises doctor tasks.
- Privacy by default: phone numbers are encrypted, sessions are server-side with CSRF protection, the webhook is signature-checked, and the demo uses synthetic data only.
- 675 automated unit tests, and a read-only guest preview for anyone to explore.

## Next steps

Clinical validation on real multilingual consultations, individual doctor accounts, approved WhatsApp templates, and a pilot with a partner hospital's outpatient department.

*VoiceRX is a hackathon prototype on synthetic data. It is not a certified medical device, and the clinician remains responsible for every approved prescription.*
