from datetime import date

from conftest import REPO_ROOT
from voicerx.contracts.extraction import ResolvedMedication
from voicerx.contracts.extraction import CheckedExtraction
from voicerx.contracts.medication import AsNeeded, Dose, Duration, Frequency, Grid, Start, Taper, TaperStep
from voicerx.pipeline.assemble import (build_header, current_medicine_lines, medicine_row, product_label,
                                       table_medicines)
from voicerx.reference import load_reference

REF = load_reference(REPO_ROOT)
VISIT = date(2026, 10, 5)


def rx(**changes):
    base = dict(id="rx1", action="start", spoken_name="Dolo six fifty", match="exact", product_id="p-dolo-650",
                candidate_ids=["p-dolo-650"], dose=Dose(amount="1", unit="tablet"), schedule=AsNeeded(type="as_needed"),
                food="after_food", duration=Duration(value=3, unit="day"), start=Start(), route=None,
                unresolved=[], quotes={})
    return ResolvedMedication(**{**base, **changes})


def test_combination_label_lists_every_component():
    assert product_label(REF.products["p-augmentin-625"]) == \
        "AUGMENTIN 625 DUO TAB (AMOXYCILLIN+CLAVULANIC ACID) 500MG+125MG"


def test_as_needed_row():
    row = medicine_row(rx(), REF, VISIT)
    assert row.label == "DOLO 650 TAB (PARACETAMOL) 650MG"
    assert row.grid == ["-", "-", "-", "-"]
    assert row.detail == "1 tablet, when needed, after food, for 3 days, start not stated"


def test_once_daily_never_gets_a_slot_and_missing_quantity_is_printed():
    row = medicine_row(rx(product_id="p-telma-40", spoken_name="Telma forty", dose=None, food=None,
                          schedule=Frequency(type="frequency", times=1, period="day"),
                          duration=Duration(value=30, unit="day")), REF, VISIT)
    assert row.grid == ["-", "-", "-", "-"]
    assert row.detail == ("Quantity not stated, once daily, time not specified, food timing not stated, "
                          "for 30 days, start not stated")
    assert "missing_quantity" in row.flags


def test_explicit_night_dose_fills_the_grid():
    row = medicine_row(rx(product_id="p-montair-lc", schedule=Grid(type="grid", m="0", a="0", e="0", n="1")), REF, VISIT)
    assert row.grid == ["0", "0", "0", "1"]


def test_ambiguous_medicine_asks_the_doctor_to_choose():
    row = medicine_row(rx(match="ambiguous", product_id=None, candidate_ids=["p-pan-40", "p-pan-d"]), REF, VISIT)
    assert row.label == ("Doctor to choose: PAN 40 TAB (PANTOPRAZOLE) 40MG or "
                         "PAN-D CAP (DOMPERIDONE+PANTOPRAZOLE) 30MG+40MG")


def test_new_prescriptions_never_appear_as_current_medicines():
    checked = CheckedExtraction(transcript_sha256="x", kept=[], dropped=[], corrections=[], issues=[],
                                medications=[rx(), rx(id="rx2", action="history", product_id="p-atorva-10")])
    assert current_medicine_lines(checked, REF) == ["Past: ATORVA TAB (ATORVASTATIN) 10MG"]


def test_header_comes_from_the_records_with_three_allergy_wordings():
    assert build_header("pat-012", "doc-001", VISIT, REF).allergy_text == "Known allergies: penicillin"
    assert build_header("pat-001", "doc-001", VISIT, REF).allergy_text == "No known allergies"
    assert build_header("pat-006", "doc-001", VISIT, REF).allergy_text == "Allergy status not recorded"


def test_taper_detail_keeps_each_steps_time_of_day():
    morning = Grid(type="grid", m="1", a="0", e="0", n="0")
    steps = [TaperStep(dose=Dose(amount=a, unit="tablet"), duration=Duration(value=3, unit="day"), when=morning)
             for a in ("2", "1")]
    row = medicine_row(rx(product_id="p-wysolone-10", dose=None, duration=None,
                          schedule=Taper(type="taper", steps=steps)), REF, VISIT)
    assert row.grid == ["-", "-", "-", "-"]
    assert row.detail == ("2 tablets in the morning for 3 days, then 1 tablet in the morning for 3 days, "
                          "after food, start not stated")
    assert "missing_quantity" not in row.flags


def test_continued_medicine_is_in_the_table_and_the_current_list():
    checked = CheckedExtraction(transcript_sha256="x", kept=[], dropped=[], corrections=[], issues=[],
                                medications=[rx(id="rx3", action="continue", product_id="p-telma-40")])
    assert [m.id for m in table_medicines(checked)] == ["rx3"]
    assert current_medicine_lines(checked, REF) == ["Continuing: TELMA 40 TAB (TELMISARTAN) 40MG"]


def test_draft_freezes_the_records_and_products_it_used(draft_report):
    assert (draft_report.version, draft_report.predecessor_hash, draft_report.resolutions) == (1, None, [])
    assert draft_report.record_snapshot["patient"] == REF.patients["pat-001"]
    assert set(draft_report.products_used) == {"p-dolo-650"}
