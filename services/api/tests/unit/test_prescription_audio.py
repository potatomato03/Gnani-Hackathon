from datetime import date
import pytest

from voicerx.agent.gate import GateRefused
from voicerx.agent.prescription_audio import prescription_text, requested_language, requested_voice
from voicerx.contracts.medication import Dose, Duration, Frequency, Grid, Start, Taper, TaperStep
from voicerx.pipeline.assemble import content_hash


def test_native_audio_contains_all_approved_dimensions_without_inventing_times(approved_report):
    rx=approved_report.checked.medications[0]
    rx.schedule=Frequency(times=2,period='week')
    rx.route='oral'
    rx.start=Start(condition='date',date=date(2026,11,5))
    approved_report.content_hash=content_hash(approved_report)
    text=prescription_text(approved_report,'hi-IN')
    assert '650' in text and 'PARACETAMOL' in text
    assert '1 गोली' in text and '3 दिन' in text
    assert 'हफ़्ते में 2 बार' in text and 'मुँह से' in text
    assert '2026-11-05' in text and 'खाने के बाद' in text
    assert 'सुबह' not in text and 'शाम' not in text
    assert 'अभी जाँच नहीं' in text


@pytest.mark.parametrize('language',['en-IN','hi-IN','ta-IN','te-IN','gu-IN'])
def test_each_supported_native_language_preserves_brand_dose_and_duration(approved_report,language):
    text=prescription_text(approved_report,language)
    assert '650' in text and '1' in text and '3' in text


def test_audio_refuses_a_changed_or_unsupported_record(approved_report):
    approved_report.medicines[0].detail='Changed after approval'
    with pytest.raises(GateRefused):prescription_text(approved_report,'hi-IN')


def test_request_is_explicit_and_defaults_to_native_language():
    assert requested_voice('voice') and requested_voice('audio in Tamil')
    assert requested_voice(button='menu_voice')
    assert not requested_voice('How do I take Dolo?')
    assert requested_language('voice','hi-IN')=='hi-IN'
    assert requested_language('audio in Tamil','hi-IN')=='ta-IN'


def test_taper_steps_and_stopped_medicines_are_not_lost(approved_report):
    rx=approved_report.checked.medications[0]
    rx.schedule=Taper(steps=[TaperStep(dose=Dose(amount='2',unit='tablet'),duration=Duration(value=3,unit='day'),
                                      when=Grid(m='2',a='0',e='0',n='0')),
                            TaperStep(dose=Dose(amount='1',unit='tablet'),duration=Duration(value=5,unit='day'))])
    stopped=rx.model_copy(deep=True);stopped.id='rx-stop';stopped.action='stop'
    approved_report.checked.medications.append(stopped)
    approved_report.content_hash=content_hash(approved_report)
    text=prescription_text(approved_report,'en-IN')
    assert '2 tablet' in text and '3 days' in text and '1 tablet' in text and '5 days' in text
    assert 'morning: 2' in text and 'Stopped by the doctor' in text


def test_explicit_start_condition_wins_over_an_unused_date(approved_report):
    approved_report.checked.medications[0].start=Start(condition='tomorrow',date=date(2026,11,5))
    approved_report.content_hash=content_hash(approved_report)
    text=prescription_text(approved_report,'en-IN')
    assert 'Start: tomorrow' in text and 'from 2026-11-05' not in text
