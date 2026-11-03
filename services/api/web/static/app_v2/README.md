# app_v2

The visual design based on the `4nov.zip` design supplied on 4 November 2026. It is the interface the server
opens at http://127.0.0.1:8000/ (runbook D-124).

The original interface is kept and still works at http://127.0.0.1:8000/v1.

Only the look differs. Both pages load the same application script (`/static/app.js`) and the original
stylesheet (`/static/app.css`) as the base; app_v2 adds:

- `app.css`: the new design, layered over the base stylesheet.
- `presentation.js`: decorative initials, a read-only Record / Check / Approve indicator, focus navigation,
  text sizing and pausable background motion. Preferences last for this page load; no storage or API calls.

So every feature and every fix to the workflow (sign-in, patients, recording, upload, typed consultation,
report review and editing, the medicine picker, approval, PDF and FHIR exports) applies to both pages at once,
and both reach the same records.

The ZIP's proposed password login, hospital accounts and WhatsApp follow-ups are not implemented. Its mock data,
assumed API contracts and replacement prescription editor are not used.

## End-to-end verification

A synthetic typed consultation was submitted from app_v2 for synthetic patient `pat-030`, encounter
`enc-dae1a9408ec9`. The worker produced a source-linked narrative and a recognised Dolo 650 prescription with the
dictated instructions. A wording correction was saved as draft version 2, then approved. Both export jobs became
ready; the approved PDF and FHIR JSON downloaded through the normal links. That run used typed input, not a new
recording.
