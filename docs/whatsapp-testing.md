# Testing the follow-up agent on real WhatsApp

This guide is for **private testing on the team's own phones** (runbook D-113). The challenge bans real phone numbers from the project and the demo. So:
- the submitted demo and video stay on the simulated chat (D-105);
- every visit here is synthetic;
- phone numbers live only in your `.env` and in the server's memory.

Never commit `.env`, and never share a screenshot that shows a phone number.

It uses Meta's free WhatsApp Cloud API test number. Your laptop runs the API and the web page. A free Cloudflare quick tunnel gives the API a public HTTPS address, so Meta's webhook can reach it.

```
your phone ──WhatsApp──► Meta ──webhook──► tunnel ──► API on your laptop (:8000) ◄── web page (:3000)
           ◄─────────────────────── Graph API ◄──────┘
```

Facts below were read from Meta's docs on 3 Nov 2026 (Graph API v26.0). Meta changes its dashboard often, so labels may differ slightly.

## 1. Create the Meta app and test number

1. Go to developers.facebook.com, log in, and open **My Apps → Create app**. Pick the use case for WhatsApp ("Connect with customers through WhatsApp"), and create or choose a business portfolio.
2. Open **WhatsApp → API Setup**. Meta gives you a **test phone number**. Note these:
   - the **Phone number ID**, a number shown under the test number (it isn't the phone number itself);
   - a **temporary access token**, which lasts 24 hours. Generate a new one each day, or create a system-user token with the `whatsapp_business_messaging` permission.
3. Under **To**, add your own WhatsApp number and confirm it with the code Meta sends. Up to 5 numbers can be added.
4. Press **Send message** once, which sends Meta's `hello_world` template to your phone. That opens the chat with the test number.
5. Open **App settings → Basic** and copy the **App secret**. The server uses it to check that each webhook really came from Meta.

## 2. Fill in `.env`

In the repository root, copy the template to `.env`, which is git-ignored: `copy .env.example .env` on Windows, `cp .env.example .env` on macOS or Linux. Then fill in these lines:

```
WHATSAPP_TOKEN=<temporary or system-user access token>
WHATSAPP_PHONE_NUMBER_ID=<phone number ID from API Setup>
WHATSAPP_APP_SECRET=<app secret>
WHATSAPP_VERIFY_TOKEN=<any long random string you choose>
WHATSAPP_TEST_NUMBERS=<your number with country code, digits only, e.g. 91XXXXXXXXXX>
GNANI_API_KEY=<optional: voice notes and calls>
PATIENT_HASH_KEY=<any long random string: the key patient memory is stored under>
GEMINI_API_KEY=<optional but recommended: the model that reads free text and report photos>
SUPABASE_DB_URL=<optional: patient memory in Supabase; without it memory is kept in runs/followup-demo/memory/>
```

- `WHATSAPP_TEST_NUMBERS` takes a comma-separated list. The server ignores every other number.
- Without the five `WHATSAPP_` settings, WhatsApp stays off and the API behaves exactly as before.
- Without a model key the bot answers with its keyword rules only, and report photos can't be read (runbook D-115, D-119).
- Patient memory needs the tables from `supabase/migrations/20261104000000_patient_memory.sql`: run `.venv\Scripts\python -I tools/supabase/apply_migration.py supabase/migrations/20261104000000_patient_memory.sql` once (runbook D-118).

## 3. Start the API and the web page

Windows (PowerShell), from the repository root:

```powershell
python -m venv .venv
```

```powershell
.venv\Scripts\pip install -r services/api/requirements.txt
```

```powershell
$env:PYTHONPATH = "services/api"; .venv\Scripts\python -m uvicorn voicerx.app:app --port 8000
```

macOS or Linux:

```bash
python3 -m venv .venv && .venv/bin/pip install -r services/api/requirements.txt
```

```bash
PYTHONPATH=services/api .venv/bin/uvicorn voicerx.app:app --port 8000
```

In a second terminal:

```bash
cd apps/web && npm install && npm run dev
```

Open http://localhost:3000 and check that http://localhost:8000/health shows `"whatsapp": "on"`.

## 4. Open the tunnel

Install `cloudflared`. On Windows, `winget install --id Cloudflare.cloudflared`; on macOS, `brew install cloudflared`; on Linux, use the package from Cloudflare's downloads page. Then, in a third terminal:

```bash
cloudflared tunnel --url http://localhost:8000
```

It prints an address like `https://<random-words>.trycloudflare.com`. That address changes every time you restart `cloudflared`. Through the tunnel, the server answers only `/whatsapp/webhook`; reset, advance and the doctor's task list are refused from outside.

## 5. Connect the webhook

In the Meta app, open **WhatsApp → Configuration → Webhook → Edit**:
- **Callback URL:** `https://<random-words>.trycloudflare.com/whatsapp/webhook`
- **Verify token:** the same `WHATSAPP_VERIFY_TOKEN` as in `.env`

Press **Verify and save**. Then, under **Webhook fields**, subscribe to **messages** (this also brings photos and documents).

If verification works but nothing arrives when you message the number, your app may not be subscribed to the WhatsApp Business Account (seen on 4 Nov with an account made through the new use-case flow). Subscribe it once, with the access token from `.env`:

```bash
curl -X POST -H "Authorization: Bearer <WHATSAPP_TOKEN>" https://graph.facebook.com/v26.0/<WABA_ID>/subscribed_apps
```

`<WABA_ID>` is the WhatsApp Business Account ID on **API Setup**. A `GET` on the same URL lists the subscribed apps.

## 6. Try it

On your phone, in the chat with the test number, send:

```
JOIN fam-010-a
```

The first message asks, in Hindi and English, which language to chat in; tap one and the summary of that synthetic visit arrives in it, with a **Menu** list (My medicines, Talk to doctor, Send a report, Change language, Stop messages). In the web page, pick the same visit ("Wysolone 10, Asthalin…"). The chat shows **Real WhatsApp · private test**, and the doctor's side updates as you reply. Things to try:
- Write in your own words, e.g. `since yesterday I feel dizzy after the tablets` or `bukhar utar gaya hai`. With a model key, the bot reads it and records it or tells the doctor; the reply is always fixed text.
- Send a **synthetic** report: a `report.pdf` from `runs/followup-demo/visits/<case>/`, or a photo of one. The doctor gets a "Report sent" task, and the findings appear under `http://localhost:8000/patients/<patient key>/memory`. Never send a real report.
- `Montair कब लेनी है?` is answered with the approved MONTAIR row.
- `seene mein dard ho raha hai` gets the urgent reply and an urgent task at the top of the doctor's list.
- Press **Advance to next check-in** in the web page. The check-in arrives on the phone with reply buttons; tap one.
- A voice note of 30 s or less (needs `GNANI_API_KEY`) is transcribed by Prisma and answered as text plus a Timbre voice note.
- `DOCTOR` opens a callback task; `STOP` ends all messages.
- Other visit codes: `JOIN fam-001-a` (Hindi) and `JOIN fam-004-a` (English). Send anything else first to get the list.

## 7. Voice calls (optional)

The patient can also **call** the test number on WhatsApp and talk to the same agent. Prisma listens, the same rules and gate decide the reply, and Timbre speaks it. The replies also appear in the chat as text. This needs `GNANI_API_KEY`. Facts are from Meta's Calling docs, 3 Nov 2026:
- Calls from a WhatsApp user to a business are free.
- Public test numbers may use calling, but it's off by default.
- The clinic can't call the patient from the US test number: business-initiated calling isn't available for US numbers.

1. Switch calling on for the number, using the settings already in `.env`:

   ```bash
   PYTHONPATH=services/api .venv/bin/python -m voicerx.agent.whatsapp enable-calling
   ```

   On Windows: `$env:PYTHONPATH = "services/api"; .venv\Scripts\python -m voicerx.agent.whatsapp enable-calling`
2. In the Meta app, under **WhatsApp → Configuration → Webhook fields**, also subscribe to **calls**.
3. Send `JOIN fam-010-a` first, so the call knows which visit it's about. Then tap the call icon in the chat with the test number.

On the call:
- The agent says it's an AI assistant, then asks for your question. Speak after it finishes, because it doesn't hear you while it talks.
- It answers medicine questions only from the approved prescription.
- It ends the call after a warning sign (and tells you to go to emergency or call 108), after `DOCTOR`, after `STOP`, after 6 questions, or after two silences.

Your voice is kept in memory only for the sentence being transcribed and is never saved.

**Network:**
- Call audio goes directly between your laptop and Meta over UDP; the tunnel carries only the signalling.
- Some college or office Wi-Fi blocks outbound UDP. If the call connects and then drops, or you hear nothing, use a phone hotspot.
- There's no TURN relay.

**Credits:** each question on a call is one Prisma call, plus one Timbre call for any reply text not voiced before. Greetings and repeated answers are cached in `runs/followup-demo/audio/`. A full call is at most about 13 Gnani calls.

## Credits

Messages are free during testing. With `GNANI_API_KEY` set, each patient voice note is one Prisma call. Each reply to a voice note is one Timbre call, unless that exact text was voiced before; replies are cached in `runs/followup-demo/audio/`.

## Troubleshooting

| What you see | Why, and what to do |
|---|---|
| Nothing arrives on the phone; the API log shows `401` or "access token" | The 24-hour token expired. Generate a new one and restart the API. |
| `131030` or "recipient not in allowed list" | Add your number under **API Setup → To** and confirm it. |
| The page says "Not sent yet: outside WhatsApp's 24-hour window" | WhatsApp allows free-form messages only within 24 hours of the patient's last message. Send any message from the phone, and the queued ones go out. |
| The page says "waiting for the phone" | The API restarted, and it keeps phone numbers only in memory. Send any message from the phone. |
| Meta can't verify the webhook | Check the tunnel is running, the URL ends in `/whatsapp/webhook`, and the verify token matches `.env` exactly. |
| `401 bad signature` in the API log | `WHATSAPP_APP_SECRET` is wrong. |
| The tunnel URL stopped working | `cloudflared` was restarted. Paste the new URL into the webhook settings. |
| Your messages are ignored | Your number isn't in `WHATSAPP_TEST_NUMBERS` (digits only, with country code). |
| Webhook verified, but messages never reach the API | Subscribe the app to the WhatsApp Business Account (step 5, `subscribed_apps`). |
| The bot answers only with "Sorry, I did not understand" to free text | No model key, or every Gemini model is busy (`503 high demand`). Set `GEMINI_API_KEY`; busy models are retried after 60 s. `GEMINI_MODEL` and `GEMINI_FALLBACK_MODEL` pick others. |
| "Sorry, I could not read that file" | No model key, the model was busy, or the photo was unreadable. Only PDFs and JPG, PNG or WEBP photos under 10 MB are taken. |
| No call icon in the chat | Run `enable-calling` (step 7), and reopen the chat. |
| The call is declined at once | Send `JOIN <code>` first. Also check that `GNANI_API_KEY` is set, that the visit wasn't stopped with STOP, and that no other call is in progress. |
| The call rings out, or connects with no sound | The **calls** webhook field isn't subscribed, or UDP is blocked on your network (try a hotspot). The API log shows `WhatsApp call failed: …`. |
