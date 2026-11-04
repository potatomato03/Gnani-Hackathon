"""A real authenticated correction round trip, using rollback-only synthetic records."""
from uuid import uuid4

from psycopg.types.json import Jsonb

from test_dashboard_followup import world, pytestmark
from voicerx.contracts.issues import Issue
from voicerx.pipeline.assemble import content_hash


def test_correct_click_saves_a_new_audited_version_without_editing_the_finding(world, draft_report):
    w = world
    draft = draft_report.model_copy(deep=True)
    eid = 'enc-confirm-' + uuid4().hex[:10]
    draft.case_id = eid
    draft.header.patient_id = w['patient']
    draft.record_snapshot['patient']['patient_id'] = w['patient']
    draft.record_snapshot['clinic']['clinic_id'] = w['org']
    flag = Issue(code='negation_mismatch', severity='block', target='x1', message='Check present or absent')
    draft.issues.append(flag)
    draft.checked.issues.append(flag.model_copy())
    draft.content_hash = content_hash(draft)
    original = draft.model_dump(mode='json')
    w['conn'].execute("insert into app.encounters(id,organisation_id,patient_id,clinician_id,visit_date,state,current_version) "
                     "values(%s,%s,%s,%s,%s,'in_review',1)", (eid,w['org'],w['patient'],w['doc'],draft.header.visit_date))
    w['conn'].execute("insert into app.report_versions(encounter_id,version,status,report,content_hash) values(%s,1,'draft',%s,%s)",
                     (eid,Jsonb(original),draft.content_hash))
    path = f'/api/v1/encounters/{eid}'
    view = w['client'].get(path+'/report').json()
    assert 'confirm_interpretation' in view['issue_views'][0]['actions'] and not view['can_approve']
    body = {'expected_version':1,'expected_content_hash':draft.content_hash,'resolutions':[
        {'action':'confirm_interpretation','target':'x1','value':{'code':'negation_mismatch'},
         'reason':'Confirmed correct as written by the doctor.'}]}
    csrf = w['client'].headers.pop('X-CSRF-Token')
    assert w['client'].post(path+'/resolutions',json=body).status_code == 403
    w['client'].headers['X-CSRF-Token'] = csrf
    response = w['client'].post(path+'/resolutions',json=body)
    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved['version'] == 2 and saved['blocking_count'] == 0 and saved['can_approve']
    assert saved['report']['sections'] == original['sections']
    assert saved['report']['checked']['kept'] == original['checked']['kept']
    resolution = saved['report']['resolutions'][-1]
    assert resolution['action'] == 'confirm_interpretation' and w['doc'] in resolution['by']
    assert resolution['at']
    assert w['conn'].execute("select report from app.report_versions where encounter_id=%s and version=1 and status='draft'",(eid,)).fetchone()['report'] == original
    assert w['client'].post(path+'/resolutions',json=body).status_code == 409
    audit = w['conn'].execute("select detail from app.audit_events where entity_id=%s and action='draft.corrected'",(eid,)).fetchone()
    assert audit['detail']['actions'] == ['confirm_interpretation']
