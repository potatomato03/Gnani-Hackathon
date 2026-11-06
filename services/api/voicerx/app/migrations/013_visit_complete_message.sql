-- On approval the patient's phone first gets a short "visit complete, report coming" text, then the PDF (runbook D-140).
-- Widen only the kind checks; existing rows and states are unchanged, and older code still satisfies the new checks.
alter table app.patient_deliveries drop constraint if exists patient_deliveries_kind_check;
alter table app.patient_deliveries add constraint patient_deliveries_kind_check
  check (kind in ('report_pdf','prescription_voice','visit_complete'));
alter table app.clinic_report_jobs drop constraint if exists clinic_report_jobs_kind_check;
alter table app.clinic_report_jobs add constraint clinic_report_jobs_kind_check
  check (kind in ('report_pdf','voice_option','prescription_voice','visit_complete'));
