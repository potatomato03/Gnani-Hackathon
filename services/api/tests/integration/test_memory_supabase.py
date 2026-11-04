"""Live check of patient memory against the real Supabase database. Writes synthetic rows under a throwaway
"test-" key and deletes them. Runs only with VOICERX_LIVE_SUPABASE=1 and SUPABASE_DB_URL in .env."""
import os
import uuid
from datetime import datetime, timezone

import psycopg
import pytest

from voicerx.agent.memory import SupabaseMemoryStore
from voicerx.contracts.documents import PatientDocument, ReportFinding, ReportReading
from voicerx.contracts.followup import MemoryItem
from voicerx.ingest.gnani import read_env

URL = read_env('SUPABASE_DB_URL')
pytestmark = pytest.mark.skipif(os.environ.get('VOICERX_LIVE_SUPABASE') != '1' or not URL,
                                reason='live Supabase check: set VOICERX_LIVE_SUPABASE=1')


@pytest.fixture
def key():
    patient_key = 'test-' + uuid.uuid4().hex[:12]
    yield patient_key
    with psycopg.connect(URL) as db:
        db.execute('delete from patient_memory where patient_key = %s', (patient_key,))
        db.execute('delete from patient_documents where patient_key = %s', (patient_key,))


def test_items_and_documents_round_trip(key):
    store = SupabaseMemoryStore(URL)
    at = datetime(2026, 11, 4, 10, tzinfo=timezone.utc)
    store.add([MemoryItem(id=f'{key}-1', patient_key=key, visit_ref='fam-001-a', kind='problem',
                          text='Problem reported. Patient wrote: «dizzy».', quote='dizzy', source='typed',
                          source_ref='r1', at=at)])
    store.add([MemoryItem(id=f'{key}-1', patient_key=key, visit_ref='fam-001-a', kind='problem', text='again',
                          quote=None, source='typed', source_ref='r1', at=at)])          # same id: ignored
    [got] = store.recent(key)
    assert got.kind == 'problem' and got.quote == 'dizzy' and got.synthetic is True
    reading = ReportReading(is_medical_report=True, report_type='CBC', report_date='2026-10-01',
                            transcription='Hb 10.2 g/dL', medicines_named=[],
                            findings=[ReportFinding(name='Hb', value='10.2', unit='g/dL', reference_range=None,
                                                    flag='low', quote='Hb 10.2')])
    doc = PatientDocument(id=f'{key}-d', patient_key=key, visit_ref='fam-001-a', mime='application/pdf',
                          sha256='f' * 64, pages=1, method='pdf_text', reading=reading, received_at=at)
    assert store.add_document(doc) is True and store.add_document(doc) is False
    assert store.documents(key)[0].reading.findings[0].flag == 'low'



def test_text_with_nul_characters_is_stored(key):
    """pypdf can return NUL characters, which Postgres text and jsonb refuse (found in the live check, 4 Nov)."""
    store = SupabaseMemoryStore(URL)
    at = datetime(2026, 11, 4, 10, tzinfo=timezone.utc)
    reading = ReportReading(is_medical_report=True, report_type='CBC\x00', report_date=None,
                            transcription='Hb\x00 10.2', medicines_named=[], findings=[])
    doc = PatientDocument(id=f'{key}-n', patient_key=key, visit_ref='v', mime='application/pdf', sha256='e' * 64,
                          pages=1, method='pdf_text', reading=reading, received_at=at)
    assert store.add_document(doc) is True
    assert store.documents(key)[0].reading.transcription == 'Hb 10.2'
    store.add([MemoryItem(id=f'{key}-n1', patient_key=key, visit_ref='v', kind='document_fact', text='Hb\x00: 10',
                          quote='Hb\x00 10', source='document', source_ref=None, at=at)])
    assert store.recent(key)[0].text == 'Hb: 10'
