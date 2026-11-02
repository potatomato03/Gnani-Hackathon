# Follow-up agent: research

Research for the patient-side follow-up agent: what happens after a doctor approves a VoiceRx prescription. The agent reaches the patient over WhatsApp or a voice call. It collects follow-ups and handles requests for help or a new consultation, and it turns each exchange into a small record for the doctor dashboard.

Done on 2 Nov 2026 with Serper web search and page fetches: 51 searches and 39 pages read. Raw results stay outside the repo. This file keeps only the summary and links.

## How to read the tags

| Tag | Meaning |
|---|---|
| **Primary** | Read on the platform's or regulator's own page on 2 Nov 2026 |
| **Measured** | A published study with numbers |
| **Opinion** | What people say in threads or interviews. Most come from builders and clinicians, not patients, so they are a weak signal of patient behaviour. |
| **Snippet** | Only the search snippet or abstract was read, not the full page |
| **Vendor** | A claim by a company selling this kind of product |

## The five findings that change the design

1. **Meta's own AI agent can't serve a clinic.** Meta Business Agent (the "Meta AI" set-up inside WhatsApp) supports every vertical except Finance, Government, **Health**, Alcohol, Gambling, over-the-counter drugs and matrimony [1] (Primary). So the follow-up agent has to be our own backend, connected through the WhatsApp Business Platform (Cloud API), not Meta's built-in agent.
2. **A clinic's task-specific bot is allowed. A general chatbot is not.** Since 15 Jan 2026, WhatsApp bars AI providers whose AI assistant is the "primary (rather than incidental or ancillary) functionality" [2][3] (Primary, quoted by TechCrunch). Meta told TechCrunch the rule doesn't touch businesses using AI to serve their own customers [3]. An agent that only talks about one approved visit for one clinic is the allowed kind. It must stay that way: no open-ended health chat.
3. **One-way reminders didn't work in India.** In a randomised trial with 388 hypertension patients in Punjab, WhatsApp reminders sent 3 days and 1 day before a follow-up visit didn't raise attendance: 21.8% against 19.6%, p = 0.603 [4] (Measured). A two-way post-discharge text programme saw response rates rise from 20% to 40% [5] (Measured, Snippet). The agent should ask a question and act on the answer, not just remind.
4. **The proactive message must be a template, and every message now costs money.** A business can start a conversation only with an approved template message. Free-form replies are allowed only inside the 24-hour window that opens when the patient writes [6] (Primary). From 1 Oct 2026, Meta charges per message for service messages and for utility messages sent inside the window. Each business number gets 1,000 free service messages a month [7][8] (Primary).
5. **Outbound WhatsApp calls from an Indian number aren't confirmed.** Meta's calling page lists business-initiated calling only for the United States, Canada, Egypt, Vietnam and Nigeria [9] (Primary). A vendor blog says India is supported [10] (Vendor). Until that's settled, voice follow-ups use a patient-initiated call or the browser call, not an outbound WhatsApp call.

## What users like and dislike

### What works

- **WhatsApp, not an app.**
  - A founder of an IVF support product dropped a native app three weeks in because patients mid-treatment wouldn't install anything new [11] (Opinion).
  - A builder who spoke to 30 small-clinic doctors in India heard that doctors already run patient contact from WhatsApp, and that "a solution that isn't WhatsApp-native doesn't exist to them" [12] (Opinion).
  - Meta cites a 2025 Kantar study: 91% of online adults in India chat with a business every week [13] (Primary, citing Kantar).
- **Medication reminders are what people asked for most.** For the IVF product, "help me not miss my injection" beat education, community and cost tracking [11] (Opinion). A WhatsApp reminder for elderly patients uses one tap ("Yes") per dose and alerts family after a missed dose [14] (Opinion).
- **Buttons beat typing for structured answers.** In Meta's testing, bots using buttons and lists got "significantly higher response rates and conversions" than text-only bots, and people understood them better [15] (Primary; Meta gives no numbers). Builders recommend fixed flows for booking and structured questions, with a language model only for free text, because one made-up answer in a clinical context becomes a real complaint [16] (Opinion).
- **Code-mixing.** In a Microsoft Research study, multilingual users "strongly prefer chatbots that can code-mix" [17] (Measured, Snippet). This matches the Hinglish scripts we already have.
- **Voice notes.** Many Indian users find voice notes easier than typing, and not only older users [18] (Opinion). Others dislike receiving them [19] (Opinion, Snippet). So accept voice notes in, and send text plus an optional voice note out.
- **Night use.** The IVF product's busiest hours are 10 PM to 3 AM, which is patient-initiated use [11] (Opinion). Patients will write at night even if we never send then.

### What fails

- **Wrong medical advice is the top fear.** All 30 doctors asked "what if it says the wrong thing?", and the builder limited the bot to logistics with hard rule-based stops on symptoms [12] (Opinion). Dentists called AI phone agents "too confidently incorrect" [20] (Opinion). Reddit threads on chatbots giving bad health advice are common [21] (Opinion, Snippet). A systematic review found patient safety was rarely evaluated in health chatbot studies, and that unconstrained free-text input carries risk [22] (Measured, Snippet).
- **Under-triaged urgency.** A clinic voice-agent builder found that a vaguely described chest pain got a "we'll call you back". The advice from the thread is to keep the threshold for handing off to a human "close to zero", because patients play symptoms down [23] (Opinion).
- **No way to reach a human.** People strongly want a one-step route to a person [24] (Opinion, Snippet). A dental clinic reports that patients prefer an AI that answers over a call nobody picks up, but only because the AI is told it "cannot diagnose" and offers a callback [20] (Opinion).
- **Slow voice replies.** On calls, "anything over ~1.2 seconds response time and callers hang up thinking the line is dead" [23] (Opinion).
- **Sounding like a robocall.** Indian government officials worried that Kilkari's recorded health calls "sound akin to telemarketing calls", which lowered listenership [25] (Snippet). Kilkari still reached over 80% of subscribers, but only 39% stayed enrolled, mainly lost through low listenership and calls unanswered for six weeks [26] (Measured). Builders say to give the AI disclosure, the person's name and the one purpose in the first sentence [27] (Opinion).
- **Reminder fatigue.** After a few weeks, medication alarms "become background noise you swipe without reading", while a short text the patient replies "DONE" to keeps working [28] (Opinion). ARMMAN's mMitra used AI to predict drop-off and cut drop-off risk by up to 32% among high-risk women [29] (Measured, Snippet). So drop-off can be predicted and acted on.
- **Forced consent.** Tata 1mg's pre-ticked consent that "overrides" DND registration drew strong criticism on Reddit [30] (Opinion).
- **Trust breaks fast.** "One piece of content that feels even slightly salesy or inaccurate — and you lose the user permanently" [11] (Opinion).

### What doctors want

- **After-hours messages are the real problem, more than bookings** [12] (Opinion).
- **Advice over WhatsApp is unpaid and risky.** A top comment from a doctor on r/indianmedschool says no patient in a decade paid for advice given on reports over WhatsApp [31] (Opinion). Another doctor says prescribing over phone or WhatsApp "is not recommended nor do I do it" [32] (Opinion, Snippet). Some clinicians won't use personal numbers at all [12] (Opinion).
- **Alert fatigue.** A 2026 study links digital alert fatigue in nurse-led remote care to less escalation [33] (Measured, Snippet). The dashboard has to show exceptions first, not every message.

### Precedent in India

- MyGov Corona Helpdesk on WhatsApp passed 30 million users [34] (Snippet).
- Tamil Nadu launched Nalam AI in July 2026, a government WhatsApp chatbot for OP registration, appointments, prescriptions and lab reports [35] (Primary).
- PM-JAY runs the Ayushman Sarathi WhatsApp chatbot [36] (Snippet).

Patients in India are used to health services on WhatsApp.

## Channels

| Channel | Good for | Limits |
|---|---|---|
| WhatsApp text with buttons | Check-ins, adherence, booking a review, short answers from the approved visit | Template needed to start; per-message charges; opt-in needed [6][7][37] |
| WhatsApp voice note | Patients who would rather speak; sending instructions in the patient's language | Inbound audio arrives as a media download link [38] (Primary). Prisma transcription costs Gnani credits. |
| WhatsApp call | Patient calls the clinic number; user-initiated calls are free [39] (Primary) | Business-initiated calls need the patient's permission [40] (Primary), and India isn't on Meta's business-initiated list [9] |
| Phone call over the telecom network (Gnani) | Older patients and feature phones; strongest fit for Gnani's telephony models | TRAI rules on robocalls and DND [41] (Snippet); the challenge bans real phone numbers and recorded calls [42] |
| Browser call | The demo; no phone number involved | Patient needs a smartphone and the link |

## Platform rules

- **Opt-in** [37] (Primary):
  - Required before messaging. It must name the business and state that the person is opting in.
  - It can be collected in person, on paper, by SMS, on a website or through IVR.
  - Meta recommends a separate opt-in per message category and a clear way to opt out.
  - Low-quality numbers (blocks, reports) get rate-limited.
- **Health content** [43] (Primary):
  - Don't use WhatsApp for telemedicine or health information where the law requires systems with stronger safeguards for health data.
  - Don't ask for full ID numbers.
  - Don't share one customer's chat with another customer.
- **Commerce** [44] (Primary): no direct sale of prescription drugs or medical devices. Healthcare services that don't sell directly are allowed. The agent mustn't sell or order medicines.
- **Pricing from 1 Oct 2026** [7][8] (Primary):
  - Per message, by category and market.
  - Service messages cost the same as utility messages, with no volume tiers and a free tier of 1,000 a month per number.
  - Meta Business Agent messages are charged separately.
  - India's rates are in Meta's rate-card CSV, which we haven't read.

## Legal and consent

- **DPDP Act 2023 and DPDP Rules 2025** (notified 13 Nov 2025) [45][46] (Primary):
  - 18 months of phased compliance.
  - A separate, clear consent notice that names the specific purpose.
  - Consent can be withdrawn at any time.
  - Requests from the person must be answered within 90 days.
  - A child's data needs verifiable parental consent, except for essential services such as healthcare.
- **Telemedicine Practice Guidelines 2020** [47] (Primary, Snippet):
  - A patient may start a follow-up consultation to continue ongoing treatment.
  - The AIIMS FAQ reads "follow-up" as up to 6 months [48] (Snippet).
  - Prescribing stays with the registered doctor. The agent never prescribes or changes a dose.
- **TRAI** [41] (Snippet): DND preferences cover health as a category, and the 2025 rules target auto-dialler and robocall nuisance. Any real outbound calling needs a registered sender and DND checks. That's out of scope for the demo.
- **Challenge rule** [42] (Primary): "Don't put anyone's real phone numbers, account numbers, Aadhaar, PAN or recorded calls into your project or demo. Use synthetic data." The demo can't message a real WhatsApp number. Relevant awards: Real Deal (named examples include rural health workers), Mixed Vibes (code-mixed speech) and Noise Canceller (telephone audio) [42].

## Recommendations

1. **Build our own agent on the Cloud API, not Meta Business Agent.** Health is excluded from Meta Business Agent [1], and its answers can't be held to the approved visit.
2. **Keep the scope narrow on purpose:**
   - This visit's medicines, check-ins, booking a review and passing questions to the doctor.
   - No general health chat. This is safer [12][22], and it keeps us on the allowed side of WhatsApp's AI rule [2].
3. **Ask, don't just remind.** Each check-in is a question with buttons: "Better / Same / Worse" and "Taking all / Missed some / Stopped". Free text and voice notes are always accepted [4][5][15].
4. **Few, timed messages:**
   - The schedule comes from the approved visit: a day-2 or day-3 tolerance check for new medicines, end of course, and before the review date.
   - Stop after two unanswered check-ins and tell the doctor instead [26][28].
5. **Treat urgency as rules first:**
   - Red-flag words in each language, reviewed by a doctor, trigger a fixed urgent reply and a doctor alert.
   - A model may raise urgency, never lower it [23].
6. **Say it's an AI, name the clinic and the purpose, and always offer "DOCTOR"** to reach a person [24][27].
7. **Code-mixed language by default, voice notes welcome both ways** [17][18].
8. **Consent:**
   - Collect it per category at the clinic (visit summary, check-ins; never marketing).
   - Record it on the patient record, and honour "STOP".
   - Never pre-tick and never make it a condition of care [30][37][45].
9. **Show the doctor exceptions first:**
   - Red flags, worse, stopped medicine and questions waiting on the doctor at the top.
   - Routine "better / taking all" collapsed [33].
10. **Demo on synthetic data in a simulated WhatsApp chat** [42]. Keep the real WhatsApp adapter behind the same interface, switched off.

## Sources

1. Meta Business Agent overview, eligibility — https://developers.facebook.com/documentation/meta-business-agent/overview
2. WhatsApp pricing policy for AI Providers — https://developers.facebook.com/documentation/business-messaging/whatsapp/pricing/ai-providers
3. TechCrunch, "WhatsApp changes its terms to bar general-purpose chatbots" (updated 15 Jan 2026) — https://techcrunch.com/2025/10/18/whatssapp-changes-its-terms-to-bar-general-purpose-chatbots-from-its-platform/
4. Favaretti et al. 2024, WhatsApp debunking reminders RCT, Punjab — https://pmc.ncbi.nlm.nih.gov/articles/PMC11382525/
5. Huxford et al. 2025, two-way text messages for post-discharge follow-up — https://pmc.ncbi.nlm.nih.gov/articles/PMC12338838/
6. WhatsApp template messages overview — https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/overview
7. Pricing on the WhatsApp Business Platform — https://developers.facebook.com/documentation/business-messaging/whatsapp/pricing
8. Pricing updates for Meta Business Agent, service and utility messages — https://developers.facebook.com/documentation/business-messaging/whatsapp/pricing/non-template-messages
9. Cloud API Calling, availability — https://developers.facebook.com/documentation/business-messaging/whatsapp/calling
10. Infiq, WhatsApp Business Calling API in India — https://www.infiq.in/blog/whatsapp-business-calling-api-guide
11. r/indianstartups, WhatsApp-first product for IVF patients — https://www.reddit.com/r/indianstartups/comments/1s9fhx6/
12. r/SideProject, WhatsApp AI agent for small clinics, 30 doctors — https://www.reddit.com/r/SideProject/comments/1sx4tpt/
13. Meta, Business AI on WhatsApp for small businesses in India (May 2026) — https://about.fb.com/news/2026/05/introducing-business-ai-on-whatsapp-for-small-businesses-in-india/
14. r/indianstartups, WhatsApp medicine reminder for elderly — https://www.reddit.com/r/indianstartups/comments/1wz7qa5/
15. Meta, sending interactive messages — https://developers.facebook.com/docs/whatsapp/guides/interactive-messages/
16. r/n8n, WhatsApp Flows vs pure LLM for clinic automation — https://www.reddit.com/r/n8n/comments/1sxnqqa/
17. Microsoft Research, "Do multilingual users prefer chat-bots that code-mix?" — https://www.microsoft.com/en-us/research/publication/do-multilingual-users-prefer-chat-bots-that-code-mix-lets-nudge-and-find-out/
18. r/indiasocial, audio messages instead of texting — https://www.reddit.com/r/indiasocial/comments/1jcwxvt/
19. r/PetPeeves, people hate receiving voice messages — https://www.reddit.com/r/PetPeeves/comments/1x7973s/
20. r/Dentists, AI handling inbound phone calls — https://www.reddit.com/r/Dentists/comments/1q82sk8/
21. r/technology, AI chatbots fail medical misinformation test — https://www.reddit.com/r/technology/comments/1ttrq78/
22. Laranjo et al. 2018, conversational agents in healthcare: a systematic review — https://pmc.ncbi.nlm.nih.gov/articles/PMC6118869/
23. r/aiagents, AI voice agent for a local clinic — https://www.reddit.com/r/aiagents/comments/1rufe5n/
24. r/ArtificialInteligence, one-touch "talk to a human" — https://www.reddit.com/r/ArtificialInteligence/comments/1xblhi2/
25. NHSRC, Kilkari and Mobile Academy Evaluation Report 2022-23 — https://nhsrcindia.org/sites/default/files/2024-01/Kilkari%20and%20Mobile%20Academy%20Evaluation%20Report%202022-23.pdf
26. Mohan et al. 2022, reach of the Kilkari programme across 13 states — https://pmc.ncbi.nlm.nih.gov/articles/PMC9366343/
27. r/AI_Agents, agents that phone businesses, what breaks — https://www.reddit.com/r/AI_Agents/comments/1x0n6kk/
28. r/samsunggalaxy, medication reminders — https://www.reddit.com/r/samsunggalaxy/comments/1uxhr0x/
29. ARMMAN, mMitra — https://armman.org/mmitra/
30. r/IndiaTech, Tata 1mg pre-ticked promotional consent — https://www.reddit.com/r/IndiaTech/comments/1s4b08d/
31. r/indianmedschool, "Views on this" — https://www.reddit.com/r/indianmedschool/comments/1qmc23n/
32. r/indianmedschool, the doctor-patient relationship, an Indian doctor's POV — https://www.reddit.com/r/indianmedschool/comments/1nshurg/
33. Zhang et al. 2026, digital alert fatigue in nurse-led remote postoperative care — https://link.springer.com/article/10.1186/s12912-026-04486-2
34. Express Computer, MyGov Corona Helpdesk passes 30M users — https://www.expresscomputer.in/news/whatsapp-chatbot-mygov-corona-helpdesk-surpasses-30m-users/74138/
35. NHM Tamil Nadu, Nalam AI — https://nhm.tn.gov.in/nalam-ai-at-rggh-hospital/
36. MoHFW on X, Ayushman Sarathi WhatsApp chatbot — https://x.com/MoHFW_INDIA/status/2071911233327177817
37. Meta, get opt-in for WhatsApp — https://developers.facebook.com/documentation/business-messaging/whatsapp/getting-opt-in
38. Meta, WhatsApp media — https://developers.facebook.com/documentation/business-messaging/whatsapp/business-phone-numbers/media
39. Meta, Calling API pricing — https://developers.facebook.com/documentation/business-messaging/whatsapp/calling/pricing
40. Meta, business-initiated calls — https://developers.facebook.com/documentation/business-messaging/whatsapp/calling/business-initiated-calls
41. TRAI, unsolicited commercial communications — http://www.trai.gov.in/faqcategory/unsolicited-commercial-communicationsucc
42. Gnani AI, Great Indian AI Internship Challenge — https://www.gnani.ai/internship
43. WhatsApp Business Messaging Policy — https://business.whatsapp.com/policy
44. Meta, WhatsApp Business Platform policy violations — https://developers.facebook.com/documentation/business-messaging/whatsapp/policy-enforcement-violations
45. PIB, DPDP Rules 2025 notified — https://static.pib.gov.in/WriteReadData/specificdocs/documents/2025/nov/doc20251117695301.pdf
46. DPDP Act 2023, section 6 (consent) — https://www.dpdpa.com/dpdpa2023/chapter-2/section6.html
47. MoHFW, Telemedicine Practice Guidelines (2020) — https://esanjeevani.mohfw.gov.in/assets/guidelines/Telemedicine_Practice_Guidelines.pdf
48. AIIMS, FAQ on Telemedicine Practice Guidelines — https://www.aiims.edu/images/pdf/notice/FAQ_Telemedicine.pdf

## Limits

- Opinion sources are mostly builders, clinicians and Reddit users, not a patient survey. Treat them as hypotheses to test, not as findings.
- Several items were checked only from the snippet or abstract; they're tagged.
- India's WhatsApp rates, India's place in business-initiated calling, and whether the WhatsApp Business app's Business AI is open to clinics are still unconfirmed.
- Nothing here is legal advice.
