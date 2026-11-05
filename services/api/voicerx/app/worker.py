"""A durable worker over the runs and artifacts tables (DESIGN.md section 11).

Work is claimed with a lease (FOR UPDATE SKIP LOCKED), so a crashed worker's job is picked up again when its
lease runs out. Attempts are bounded, and a provider's daily limit waits and retries instead of failing.
"""
from datetime import datetime, timezone
from hashlib import sha256
import json
import logging
import threading
from pathlib import Path

from psycopg.types.json import Jsonb

from ..exports.fhir import build_bundles
from ..exports.patient_box import build_patient_box
from ..exports.pdf.render import html_to_pdf, render_html
from ..llm.client import QuotaExhausted, build_client
from ..reference import load_reference
from ..speech.prisma import PrismaError, decode_audio, transcribe
from .clinical import StageFailed, current_ids, process_typed, reference_for
from .config import REPO_ROOT, read_env
from .db import audit, one, transaction
from .repo import approved_reports, clinic_record, doctor_record, parse_report, patient_record, report_row
from ..pipeline.complete import load_generics
from ..standard import load_rules
from .shortlist import conditions_in, make_shortlist
from .suggest import catalog_product, clinic_index, finder_for, shared_index, suggest

log = logging.getLogger('voicerx.worker')
LEASE = '10 minutes'
# Where a pooled run keeps not_before and lease_until, out of reach of workers from before pools (runbook D-132).
NEVER = datetime(9000, 1, 1, tzinfo=timezone.utc)
TEMPLATES = Path(__file__).resolve().parents[1] / 'exports/templates/lang'


def claim_run(conn, pool):
    """The next due run of this deployment's pool (runbook D-132). Pooled runs keep not_before and lease_until at
    the year 9000 so workers from before pools never take them; due_at and pool_lease_until do that job here."""
    return one(conn, f'''
        update app.runs set state = 'running', attempts = attempts + 1, pool_lease_until = now() + interval '{LEASE}',
               updated_at = now()
        where id = (select id from app.runs
                    where pool = %s and ((state in ('queued', 'retry_wait') and due_at <= now())
                                         or (state = 'running' and pool_lease_until < now()))
                    order by created_at limit 1 for update skip locked)
        returning *''', (pool,))


def claim_artifact(conn):
    return one(conn, f'''
        update app.artifacts set state = 'running', attempts = attempts + 1, updated_at = now()
        where id = (select id from app.artifacts
                    where (state = 'pending') or (state = 'running' and updated_at < now() - interval '{LEASE}')
                    order by created_at limit 1 for update skip locked)
        returning *''')


def is_adult(patient, visit_date):
    return bool(patient.get('birth_year')) and visit_date.year - patient['birth_year'] >= 18


def shortlist_for(conn, client, checked, organisation_id, formulary, adult):
    pools = [shared_index(conn, formulary), clinic_index(conn, organisation_id)]
    conditions = conditions_in(checked)
    lookup = lambda pid: catalog_product(conn, organisation_id, pid, formulary)
    items, method = make_shortlist(client, conditions, pools, load_generics(REPO_ROOT), load_rules(REPO_ROOT), lookup, adult)
    return conditions, items, method


def save_shortlist(conn, encounter_id, conditions, items, method):
    conn.execute('insert into app.medicine_shortlists (encounter_id, conditions, items, method) values (%s, %s, %s, %s) '
                 'on conflict (encounter_id) do update set conditions = excluded.conditions, items = excluded.items, '
                 'method = excluded.method, created_at = now()', (encounter_id, conditions, Jsonb(items), Jsonb(method)))


class Worker(threading.Thread):
    def __init__(self, settings, client=None, transcriber=None, followup=None):
        super().__init__(name='voicerx-worker', daemon=True)
        self.settings = settings
        self.client = client
        self.followup = followup
        self.transcriber = transcriber or (lambda samples, language: transcribe(samples, language, read_env()['GNANI_API_KEY']))
        self.reference = load_reference(REPO_ROOT)
        self.stopping = threading.Event()

    def stop(self):
        self.stopping.set()

    def run(self):
        while not self.stopping.is_set():
            try:
                worked = self.tick()
            except Exception:
                log.exception('worker tick failed')
                worked = False
            if not worked:
                self.stopping.wait(1.0)

    def tick(self):
        # Give inbound patient events a turn even while extraction/export jobs are arriving.
        followed = self.followup.tick() if self.followup else False
        return self.next_run() or self.next_artifact() or followed

    def llm(self):
        if self.client is None:
            self.client = build_client(REPO_ROOT / '.env', self.settings.artifacts_dir / 'cache', only=self.settings.llm_provider)
        return self.client

    def next_run(self):
        with transaction() as conn:
            run = claim_run(conn, self.settings.worker_pool)
        if run is None:
            return False
        steps = run['steps']
        writing = threading.Lock()

        def on_step(key, state):
            with writing:  # suggestions report from their own thread
                for step in steps:
                    if step['key'] == key:
                        step['state'] = state
                with transaction() as conn:
                    conn.execute(f"update app.runs set steps = %s, stage = %s, pool_lease_until = now() + interval '{LEASE}', "
                                 'updated_at = now() where id = %s', (Jsonb(steps), key, run['id']))

        with transaction() as conn:
            context = one(conn, '''
                select e.*, s.text, s.kind, s.language, s.file_name from app.encounters e
                join app.sources s on s.id = %s where e.id = %s''', (run['source_id'], run['encounter_id']))
            patient = one(conn, 'select * from app.patients where id = %s', (context['patient_id'],))
            doctor = one(conn, 'select * from app.users where id = %s', (context['clinician_id'],))
            clinic = one(conn, 'select * from app.organisations where id = %s', (context['organisation_id'],))
            history = approved_reports(conn, context['patient_id'], before_encounter=context['id'])
        reference = reference_for(self.reference, patient_record(patient), doctor_record(doctor, clinic['id']),
                                  clinic_record(clinic))
        side, threads = {}, []

        def suggest_meanwhile(checked):
            # The suggestions and the medicine picker's shortlist need only the checked extraction, so they
            # run while the report is written (runbook D-131).
            jobs = {'found': lambda: self.suggestions(checked, transcript, context, on_step),
                    'shortlist': lambda: self.save_shortlist(checked, context, patient)}
            for name, job in jobs.items():
                threads.append(threading.Thread(name='voicerx-' + name, daemon=True,
                                                target=lambda name=name, job=job: side.update({name: job()})))
                threads[-1].start()

        def suggestions_found():
            # The draft waits for the suggestions it shows; the picker's shortlist saves itself when ready.
            for thread in threads[:1]:
                thread.join()
            return side.get('found', {})

        try:
            transcript = context['text'] if context['kind'] == 'typed' else self.transcript(run, context, on_step)
            draft = process_typed(context['id'], transcript, patient['id'], doctor['id'], context['visit_date'],
                                  self.llm(), reference, current_ids(history), on_step, rules=load_rules(REPO_ROOT),
                                  generics=load_generics(REPO_ROOT), finder=self.finder(context, patient),
                                  on_checked=suggest_meanwhile)
        except StageFailed as failure:
            suggestions_found()
            self.fail(run, steps, failure)
            return True
        suggestions = suggestions_found()
        with transaction() as conn:
            conn.execute('insert into app.report_versions (encounter_id, version, status, report, content_hash, run_id, '
                         "created_by) values (%s, %s, 'draft', %s, %s, %s, %s)",
                         (context['id'], draft.version, Jsonb(draft.model_dump(mode='json')), draft.content_hash,
                          run['id'], run['created_by']))
            for medication_id, (heard, items, method) in suggestions.items():
                conn.execute('insert into app.medicine_suggestions (encounter_id, medication_id, heard, suggestions, method) '
                             'values (%s, %s, %s, %s, %s) on conflict (encounter_id, medication_id) do update set '
                             'heard = excluded.heard, suggestions = excluded.suggestions, method = excluded.method',
                             (context['id'], medication_id, heard, Jsonb(items), Jsonb(method)))
            conn.execute("update app.encounters set state = 'in_review', current_version = %s where id = %s",
                         (draft.version, context['id']))
            conn.execute("update app.runs set state = 'succeeded', stage = null, draft_version = %s, error = null, "
                         'pool_lease_until = null, updated_at = now() where id = %s', (draft.version, run['id']))
            audit(conn, None, context['organisation_id'], 'run.succeeded', 'encounter', context['id'],
                  {'run_id': run['id'], 'version': draft.version,
                   'blocking': sum(i.severity == 'block' for i in draft.issues)})
        return True

    def finder(self, context, patient):
        """Looks up the clinic's earlier choices and clear matches, each in its own short transaction; a failure
        leaves that medicine for the doctor, never the run. An adult's unnamed form means the tablet (D-120)."""
        adult = is_adult(patient, context['visit_date'])

        def find(rx):
            try:
                with transaction() as conn:
                    return finder_for(conn, context['organisation_id'], self.reference.products, adult)(rx)
            except Exception:
                log.exception('matching %s failed; left for the doctor', rx.spoken_name)
                return None
        return find

    def save_shortlist(self, checked, context, patient):
        found = self.shortlist(checked, context, patient)
        if found:
            try:
                with transaction() as conn:
                    save_shortlist(conn, context['id'], *found)
            except Exception:
                log.exception('saving the shortlist failed for %s', context['id'])

    def shortlist(self, checked, context, patient):
        """(conditions, items, method) for the medicine picker; a failure costs only the list."""
        try:
            with transaction() as conn:
                return shortlist_for(conn, self.llm(), checked, context['organisation_id'], self.reference.products,
                                     is_adult(patient, context['visit_date']))
        except Exception:
            log.exception('shortlist failed for %s', context['id'])
            return None

    def suggestions(self, checked, transcript, context, on_step):
        """Ranked suggestions for every medicine not matched exactly. A failure here costs the suggestions,
        never the draft."""
        unclear = [m for m in checked.medications if m.match != 'exact']
        if not unclear:
            on_step('suggesting', 'skipped')
            return {}
        on_step('suggesting', 'running')
        found = {}
        try:
            with transaction() as conn:
                for rx in unclear:
                    items, method = suggest(conn, self.llm(), transcript, rx, checked,
                                            context['organisation_id'], self.reference.products)
                    found[rx.id] = (rx.spoken_name, items, method)
        except Exception:
            log.exception('suggestions failed for %s', context['id'])
            on_step('suggesting', 'failed')
            return {}
        on_step('suggesting', 'succeeded')
        return found

    def transcript(self, run, context, on_step):
        """Prisma's transcript of the recording; a retried run reuses the one it already paid for."""
        if run['transcript']:
            on_step('transcribing', 'succeeded')
            return run['transcript']
        on_step('transcribing', 'running')
        path = self.settings.artifacts_dir / context['id'] / 'sources' / context['file_name']
        try:
            if path.exists():
                data=path.read_bytes()
            else:
                with transaction() as conn:
                    stored=one(conn,'select * from app.source_files where source_id=%s',(run['source_id'],))
                if not stored or sha256(bytes(stored['data'])).hexdigest()!=stored['sha256']:
                    raise ValueError('Stored recording fingerprint failed.')
                data=bytes(stored['data'])
            text, meta = self.transcriber(decode_audio(data), context['language'])
        except PrismaError as error:
            on_step('transcribing', 'failed')
            raise StageFailed('transcribing', str(error)) from error
        except Exception as error:
            on_step('transcribing', 'failed')
            raise StageFailed('transcribing', f'{type(error).__name__}: {error}') from error
        with transaction() as conn:
            conn.execute('update app.runs set transcript = %s, transcript_meta = %s where id = %s',
                         (text, Jsonb(meta), run['id']))
        on_step('transcribing', 'succeeded')
        return text

    def fail(self, run, steps, failure):
        cause = failure.__cause__
        transient = isinstance(cause, QuotaExhausted) or getattr(cause, 'transient', False)
        waiting = transient and run['attempts'] < run['max_attempts']
        message = 'A provider is busy or at its limit; this will retry.' if waiting else (
            f'Stopped at "{failure.stage}": {str(failure)[:300]}')
        for step in steps:
            if step['state'] in ('running', 'failed'):
                step['state'] = 'pending' if waiting else 'failed'
        with transaction() as conn:
            conn.execute(
                "update app.runs set state = %s, steps = %s, error = %s, pool_lease_until = null, "
                "due_at = now() + make_interval(secs => %s), updated_at = now() where id = %s",
                ('retry_wait' if waiting else 'failed', Jsonb(steps), message, 60 * run['attempts'], run['id']))
            if not waiting:
                conn.execute("update app.encounters set state = 'failed' where id = %s", (run['encounter_id'],))
            audit(conn, None, None, 'run.' + ('retry_wait' if waiting else 'failed'), 'run', run['id'],
                  {'stage': failure.stage})

    def next_artifact(self):
        with transaction() as conn:
            artifact = claim_artifact(conn)
            if artifact is None:
                return False
            report = parse_report(report_row(conn, artifact['encounter_id'], artifact['version'], 'approved'))
        folder = self.settings.artifacts_dir / artifact['encounter_id'] / f"v{artifact['version']}"
        folder.mkdir(parents=True, exist_ok=True)
        try:
            if artifact['kind'] == 'report_pdf':
                path = html_to_pdf(render_html(report, build_patient_box(report, TEMPLATES)), folder / 'report_approved.pdf')
            elif artifact['kind'] == 'fhir_bundles':
                path = folder / 'fhir_bundles.json'
                path.write_text(json.dumps(build_bundles(report), ensure_ascii=False, indent=2), encoding='utf-8')
            else:
                raise ValueError(f"unsupported artifact kind {artifact['kind']}")
        except Exception as error:
            final = artifact['attempts'] >= 3
            with transaction() as conn:
                conn.execute('update app.artifacts set state = %s, error = %s, updated_at = now() where id = %s',
                             ('failed' if final else 'pending', f'{type(error).__name__}: {error}'[:300], artifact['id']))
            return True
        digest = sha256(path.read_bytes()).hexdigest()
        with transaction() as conn:
            conn.execute('insert into app.artifact_files(artifact_id,sha256,data) values(%s,%s,%s) '
                         'on conflict(artifact_id) do update set sha256=excluded.sha256,data=excluded.data',
                         (artifact['id'],digest,path.read_bytes()))
            if artifact['kind']=='report_pdf':
                conn.execute('insert into app.report_files(encounter_id,version,sha256,data) values(%s,%s,%s,%s) '
                             'on conflict(encounter_id,version) do update set sha256=excluded.sha256,data=excluded.data',
                             (artifact['encounter_id'],artifact['version'],digest,path.read_bytes()))
            conn.execute("update app.artifacts set state = 'ready', file_name = %s, sha256 = %s, error = null, "
                         'updated_at = now() where id = %s', (path.name, digest, artifact['id']))
        return True
