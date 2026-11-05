"""Hospital, doctor and registration routes for the private demo workspace."""
from datetime import datetime
from uuid import uuid4

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from ..agent.whatsapp import digits
from ..agent.prescription_audio import LANGUAGES
from . import auth
from .db import all_rows, audit, one, transaction
from .private_access import encrypt_phone
from .repo import patient_summary


class DoctorInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    name: str=Field(min_length=2,max_length=100)
    specialty: str=Field(min_length=2,max_length=80)
    registration_no: str=Field(default='',max_length=60)


class PatientInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    name: str=Field(min_length=2,max_length=120)
    phone: str=Field(min_length=8,max_length=24)
    language: str
    doctor_id: str
    sex: str=Field(default='',max_length=20)
    birth_year: int
    allergy_status: str='unknown'
    allergies: list[str]=Field(default_factory=list,max_length=20)
    recording_consent: bool=False
    ai_consent: bool=False
    whatsapp_consent: bool=False


def admin(session):
    if not session.get('operator_admin'):
        raise auth.Forbidden('Workspace administration requires the private admin login.')


def install(app,state,session_of,ApiError):
    @app.get('/api/v1/workspace/hospitals')
    def hospitals(request:Request):
        s=session_of(request);admin(s)
        with transaction() as conn:
            items=all_rows(conn,'select o.id,o.name from app.organisations o join app.memberships m on m.organisation_id=o.id '
                           'where m.user_id=%s and o.archived_at is null order by o.name',(s['operator_id'],))
        return {'items':items}

    @app.get('/api/v1/workspace/hospitals/{hospital_id}/doctors')
    def doctors(request:Request,hospital_id:str):
        s=session_of(request);admin(s)
        with transaction() as conn:
            hospital=one(conn,'select o.id,o.name from app.organisations o join app.memberships m on m.organisation_id=o.id '
                         'where o.id=%s and m.user_id=%s and o.archived_at is null',(hospital_id,s['operator_id']))
            if not hospital:
                raise ApiError(404,'not_found','Hospital not found.')
            rows=all_rows(conn,"select u.id,u.display_name,u.specialty,u.registration_no from app.users u join app.memberships m "
                          "on m.user_id=u.id where m.organisation_id=%s and m.role='doctor' and u.disabled_at is null "
                          'order by u.display_name',(hospital_id,))
        return {'hospital':hospital,'items':rows}

    @app.post('/api/v1/workspace/hospitals/{hospital_id}/doctors',status_code=201)
    def add_doctor(request:Request,hospital_id:str,body:DoctorInput):
        s=session_of(request);admin(s)
        name=body.name.strip();specialty=body.specialty.strip()
        if len(name)<2 or len(specialty)<2:
            raise ApiError(422,'invalid_doctor','Enter the doctor name and specialty.')
        with transaction() as conn:
            member=one(conn,'select m.user_id from app.memberships m join app.organisations o on o.id=m.organisation_id '
                       'where m.user_id=%s and m.organisation_id=%s and o.archived_at is null',(s['operator_id'],hospital_id))
            if not member:
                raise ApiError(404,'not_found','Hospital not found.')
            did='doctor-'+uuid4().hex[:16]
            conn.execute('insert into app.users(id,display_name,specialty,registration_no,synthetic) values(%s,%s,%s,%s,true)',
                         (did,name,specialty.strip().lower().replace(' ','_'),body.registration_no.strip() or None))
            conn.execute("insert into app.memberships(user_id,organisation_id,role) values(%s,%s,'doctor')",(did,hospital_id))
            audit(conn,s['operator_id'],hospital_id,'workspace.doctor_onboarded','user',did,{'shared_demo_account':True})
        return {'id':did,'display_name':name,'specialty':specialty}

    @app.post('/api/v1/workspace/select')
    async def select(request:Request):
        s=session_of(request);admin(s)
        body=await request.json();oid=str(body.get('hospital_id',''));did=body.get('doctor_id')
        with transaction() as conn:
            member=one(conn,'select m.user_id,o.id,o.name from app.memberships m join app.organisations o on o.id=m.organisation_id '
                       'where m.user_id=%s and m.organisation_id=%s and o.archived_at is null',(s['operator_id'],oid))
            if not member:
                raise ApiError(404,'not_found','Hospital not found.')
            if did and not one(conn,"select m.user_id from app.memberships m join app.users u on u.id=m.user_id "
                               "where m.user_id=%s and m.organisation_id=%s and m.role='doctor' and u.disabled_at is null",(did,oid)):
                raise ApiError(404,'not_found','Doctor not found in this hospital.')
            auth.end_session(conn,request.cookies.get(auth.COOKIE))
            token=auth.create_session(conn,did or s['operator_id'],oid,operator_id=s['operator_id'])
            current=auth.load_session(conn,token)
            audit(conn,s['operator_id'],oid,'workspace.scope_selected','user',did,{'shared_demo_account':True})
            selected_doctors=all_rows(conn,"select u.id,u.display_name,u.specialty,u.registration_no from app.users u join app.memberships m "
                                     "on m.user_id=u.id where m.organisation_id=%s and m.role='doctor' and u.disabled_at is null "
                                     'order by u.display_name',(oid,)) if not did else None
        view=auth.session_view(current)
        if selected_doctors is not None:
            view['workspace']={'hospital':{'id':member['id'],'name':member['name']},'items':selected_doctors}
        response=JSONResponse(view)
        response.set_cookie(auth.COOKIE,token,httponly=True,samesite='strict',secure=request.url.scheme=='https',
                            max_age=7200,path='/')
        return response

    @app.post('/api/v1/patients',status_code=201)
    def register_patient(request:Request,body:PatientInput):
        s=session_of(request);auth.require(s,'register')
        number=digits(body.phone)
        if len(number)==10:
            number='91'+number
        if not 10<=len(number)<=15 or not body.name.strip():
            raise ApiError(422,'invalid_patient','Enter a name and a valid phone number with country code.')
        if body.language not in LANGUAGES:
            raise ApiError(422,'invalid_language','Choose a supported patient language.')
        if not 1900<=body.birth_year<=datetime.now().year:
            raise ApiError(422,'invalid_birth_year','Enter a valid birth year.')
        if body.sex not in ('M','F','other'):
            raise ApiError(422,'invalid_sex','Record the patient sex for the prescription.')
        if body.allergy_status not in ('unknown','nka','known') or (body.allergy_status=='known' and not any(x.strip() for x in body.allergies)):
            raise ApiError(422,'invalid_allergies','Enter known allergies or choose unknown / no known allergies.')
        if not body.ai_consent:
            raise ApiError(422,'consent_required','Confirm consent to AI processing for this test.')
        channel=state['followup'].channel
        if body.whatsapp_consent and (not channel or not channel.allowed(number)):
            raise ApiError(422,'recipient_not_enabled','For this demo, enter the registered Meta test recipient number.')
        consents=['ai_processing']+(['recording'] if body.recording_consent else [])+(['followup_whatsapp'] if body.whatsapp_consent else [])
        with transaction() as conn:
            if not one(conn,"select m.user_id from app.memberships m join app.users u on u.id=m.user_id where "
                       "m.user_id=%s and m.organisation_id=%s and m.role='doctor' and u.disabled_at is null",(body.doctor_id,s['organisation_id'])):
                raise ApiError(422,'invalid_doctor','Select an onboarded doctor from this hospital.')
            pid='patient-'+uuid4().hex[:16];mrn='P-'+uuid4().hex[:8].upper()
            row=one(conn,'insert into app.patients(id,organisation_id,mrn,name,sex,birth_year,language_pref,allergy_status,'
                    'allergies,consents,synthetic,assigned_doctor_id,phone_encrypted,phone_last4,registered_by) '
                    'values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,true,%s,%s,%s,%s) returning *',
                    (pid,s['organisation_id'],mrn,body.name.strip(),body.sex or None,body.birth_year,body.language,
                     body.allergy_status,[x.strip()[:120] for x in body.allergies if x.strip()],consents,body.doctor_id,
                     encrypt_phone(number),number[-4:],s.get('operator_id') or s['user_id']))
            if body.whatsapp_consent:
                conn.execute('insert into app.patient_contact_requests(patient_id,organisation_id,expected_contact) values(%s,%s,%s)',
                             (pid,s['organisation_id'],channel.contact(number)))
            audit(conn,s.get('operator_id') or s['user_id'],s['organisation_id'],'patient.registered','patient',pid,
                  {'doctor_id':body.doctor_id,'language':body.language,'whatsapp_consent':body.whatsapp_consent,'test_record':True})
        return {'patient':{**patient_summary(row),'phone_last4':number[-4:]}}
