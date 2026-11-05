"""Authenticated 3 MB parts keep long recordings below Vercel's per-request payload limit."""
from math import ceil
from uuid import uuid4

from fastapi import Request
from . import auth
from .db import one,all_rows,transaction
from .repo import get_encounter

PART=3*1024*1024
MAX=40*1024*1024


def install(app,session_of,ApiError,store_audio,audio_types,languages):
    def owned(conn,session,uid):
        row=one(conn,'select u.* from app.audio_uploads u join app.encounters e on e.id=u.encounter_id '
                'where u.id=%s and u.user_id=%s and e.organisation_id=%s and u.expires_at>now() for update of u',
                (uid,session['user_id'],session['organisation_id']))
        if not row:
            raise ApiError(404,'not_found','Upload not found or expired.')
        return row

    @app.post('/api/v1/encounters/{eid}/audio-uploads',status_code=201)
    async def begin(request:Request,eid:str):
        s=session_of(request);auth.require(s,'capture');body=await request.json()
        size=body.get('size');media=body.get('media_type');language=body.get('language')
        if not isinstance(size,int) or isinstance(size,bool) or not 0<size<=MAX or media not in audio_types or language not in languages:
            raise ApiError(422,'invalid_audio','Choose a supported recording under 40 MB.')
        if body.get('recording_consent') is not True:
            raise ApiError(422,'consent_required','Confirm consent to the recording.')
        with transaction() as conn:
            encounter=get_encounter(conn,s['organisation_id'],eid)
            if not encounter:
                raise ApiError(404,'not_found','Visit not found.')
            if encounter['state'] not in ('open','failed'):
                raise ApiError(409,'source_locked','This visit has already been processed.')
            conn.execute('delete from app.audio_uploads where expires_at<now()')
            count=one(conn,'select count(*) as n from app.audio_uploads where user_id=%s and source_id is null',(s['user_id'],))['n']
            if count>=3:
                raise ApiError(429,'too_many_uploads','Finish the existing upload or wait for it to expire.')
            uid='upload-'+uuid4().hex
            conn.execute('insert into app.audio_uploads(id,encounter_id,user_id,media_type,language,size_bytes) values(%s,%s,%s,%s,%s,%s)',
                         (uid,eid,s['user_id'],media,language,size))
        return {'id':uid,'part_bytes':PART}

    @app.put('/api/v1/audio-uploads/{uid}/parts/{part}')
    async def part(request:Request,uid:str,part:int):
        s=session_of(request);auth.require(s,'capture')
        with transaction() as conn:
            row=owned(conn,s,uid)
        if row['source_id'] or not 0<=part<ceil(row['size_bytes']/PART):
            raise ApiError(422,'invalid_part','Invalid upload part.')
        expected=min(PART,row['size_bytes']-part*PART);data=bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data)>expected:
                raise ApiError(413,'part_too_large','Upload part exceeds its expected size.')
        if len(data)!=expected:
            raise ApiError(422,'incomplete_part','Upload part has an unexpected size.')
        with transaction() as conn:
            row=owned(conn,s,uid)
            if row['source_id']:
                raise ApiError(409,'upload_complete','Upload is already complete.')
            conn.execute('insert into app.audio_upload_chunks(upload_id,part,data) values(%s,%s,%s) '
                         'on conflict(upload_id,part) do update set data=excluded.data',(uid,part,bytes(data)))
        return {'ok':True}

    @app.post('/api/v1/audio-uploads/{uid}/complete')
    async def complete(request:Request,uid:str):
        s=session_of(request);auth.require(s,'capture')
        with transaction() as conn:
            row=owned(conn,s,uid)
            if row['source_id']:
                source=one(conn,'select id,version,language,duration_s from app.sources where id=%s',(row['source_id'],))
                return {**source,'duration_s':float(source['duration_s'])}
            chunks=all_rows(conn,'select part,data from app.audio_upload_chunks where upload_id=%s order by part',(uid,))
            if len(chunks)!=ceil(row['size_bytes']/PART) or [c['part'] for c in chunks]!=list(range(len(chunks))):
                raise ApiError(422,'incomplete_upload','Some recording parts have not arrived.')
            data=b''.join(bytes(c['data']) for c in chunks)
            if len(data)!=row['size_bytes']:
                raise ApiError(422,'incomplete_upload','The uploaded recording size does not match.')
            result=await store_audio(s,row['encounter_id'],row['media_type'],row['language'],data)
            conn.execute('update app.audio_uploads set source_id=%s where id=%s',(result['id'],uid))
            conn.execute('delete from app.audio_upload_chunks where upload_id=%s',(uid,))
        return result
