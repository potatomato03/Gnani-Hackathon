# Private hospital demo

The shared demo account opens Hospitals → onboarded doctor → assigned patients. Only the two demo hospitals named in the private `APP_PRIVATE_HOSPITALS` setting are enabled in the active workspace. Doctors and patients are entered by the operator; no clinical patients are seeded automatically. Earlier demo organisations remain archived for recovery and their sessions and pending deliveries are disabled.

## Access

The local bootstrap writes the generated shared password to `../credentials/private-demo-access.txt`. The password is stored in Postgres only as a salted scrypt hash. The private page does not disclose the product or hospitals before sign-in. Product assets and API routes require a valid server-side session. Development login and OpenAPI are disabled on hosted deployments. CSRF checks, origin checks, login attempt limits, no-store responses and HttpOnly/Secure/SameSite cookies protect the workspace.

This is one shared demo identity, as requested. Selecting a doctor is an explicitly audited workspace action; it is not proof that that doctor personally signed in. Individual accounts and individual revocation are needed if the shared demonstration setup is replaced.

## Registration and WhatsApp

Record name, birth year, sex, doctor, phone, preferred language, allergy status and the patient's consent choices. Phone numbers are encrypted with `APP_DATA_KEY`; API views expose only the last four digits. Recording and AI processing use separate consent choices. For this demonstration, WhatsApp sending remains limited to configured Meta test recipients.

An approved report queues its archived PDF to the registered number. The subsequent buttons offer Prescription voice and Patient menu. Voice synthesis is request-only and uses the approved report's native language. The Patient menu selects the exact report context before storing medicine questions, doctor requests or lab uploads in that patient's history. A shared test phone is never silently rebound to a different patient identity. Use the Patient menu under another patient's PDF to switch the active test context.

Meta's customer-service window still applies. A held delivery needs a new inbound patient message; an approved business-initiated template is not configured. STOP prevents further report sending; consent renewal is required before resuming stopped follow-up.

## Vercel

`vercel.json` declares an HTTP container service and a separate worker daemon. The API process does not start an in-process background worker in Vercel. The daemon polls the durable Postgres outboxes. Original recordings and all approved artifacts have private database copies, so the processes do not depend on a shared local disk. Large audio uploads use authenticated 3 MB parts to stay below the function request limit.

`.vercelignore` and `.dockerignore` include only necessary application source, reference data and assets. Credentials, `.env` files, runs, recordings, logs and database backups are excluded. Runtime credentials are configured as sensitive production variables, after the operator's explicit approval. Keep `APP_DATA_KEY` and `PATIENT_HASH_KEY` stable; losing the former prevents phone decryption and changing the latter changes existing contact hashes.

Deployment checks must verify anonymous product/API requests are rejected, private login works over HTTPS with a Secure cookie, the two empty hospital rosters load, the worker starts, and Meta's signed webhook points to the stable production URL. Do not use a Vercel protection-bypass token in browser code or Meta's callback URL. The signed webhook remains the one intentionally accessible bot endpoint.

For this rollout the operator explicitly chose to keep Meta's existing callback. It was verified unchanged and healthy. The existing bot/relay must remain running for incoming WhatsApp messages; the dashboard and the outbox worker are hosted in Vercel. Switching Meta to the verified production webhook remains a separate operator choice. Production uses the same Supabase project's transaction pooler, while the local server's original connection setting and worker remain in place.

The worker verifies database access and Chromium PDF generation at startup. Use `tools/safe_test.py` for pytest runs so connection details and local API credentials are redacted before output is displayed.

Vercel's daemon/container features are beta. The connected Hobby account's daemon quota is finite: the documented 420 GB-hours supports one 2 GiB worker for about nine continuous days per month. Check usage before extending a demo. No claim of production clinical certification or complete security is made by this setup.
