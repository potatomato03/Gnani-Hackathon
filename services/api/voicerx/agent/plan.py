"""Build the follow-up plan from an approved report. Code only: no model sets a date or a time."""
from datetime import date, datetime, time, timedelta, timezone

from ..contracts.followup import FollowUpPlan, FollowUpTouch
from ..contracts.medication import AsNeeded, Duration, Taper
from ..pipeline.assemble import table_medicines

IST = timezone(timedelta(hours=5, minutes=30), 'IST')
WINDOW = (time(9), time(20))          # scheduled messages only inside these local hours (runbook D-107)
CHECK_TIME = time(10)                 # scheduled check-ins go out at 10:00 IST
MAX_TOUCHES = 5                       # per visit, summary included
DAYS = {'day': 1, 'week': 7, 'month': 30}
QUESTION_ORDER = ('tolerance', 'symptom_status', 'adherence', 'review_attendance')
# When two touches fall on one day, the later stage of care names the merged touch.
KIND_RANK = {'summary': 0, 'tolerance': 1, 'progress': 2, 'end_of_course': 3, 'review': 4}


def in_window(moment: datetime) -> datetime:
    """Move a moment into the next allowed sending window, in IST."""
    local = moment.astimezone(IST)
    if local.time() < WINDOW[0]:
        return datetime.combine(local.date(), WINDOW[0], IST)
    if local.time() > WINDOW[1]:
        return datetime.combine(local.date() + timedelta(days=1), WINDOW[0], IST)
    return local


def course_days(rx):
    if isinstance(rx.schedule, Taper):
        return sum(step.duration.value * DAYS[step.duration.unit] for step in rx.schedule.steps)
    if isinstance(rx.duration, Duration):
        return rx.duration.value * DAYS[rx.duration.unit]
    return None


def start_day(rx, visit_date: date) -> date:
    if rx.start.condition == 'tomorrow':
        return visit_date + timedelta(days=1)
    if rx.start.condition == 'date' and rx.start.date:
        return rx.start.date
    return visit_date


def plan_followups(visit, channel='simulated') -> FollowUpPlan:
    approved = visit.approved
    if approved.status != 'approved':
        raise ValueError('follow-ups start only from an approved report')
    visit_date = approved.header.visit_date
    medicines = [m for m in table_medicines(approved.checked) if m.match == 'exact' and m.product_id]
    regular = [m for m in medicines if not isinstance(m.schedule, AsNeeded)]

    def at(day):
        return datetime.combine(day, CHECK_TIME, IST)

    candidates = []  # (kind, due, questions, medicine ids)
    new = [m for m in medicines if m.action in ('start', 'change')]
    if new:
        first = min(start_day(m, visit_date) for m in new)
        candidates.append(('tolerance', at(first + timedelta(days=2)), ['tolerance'], [m.id for m in new]))
    followup_questions = ['symptom_status'] + (['adherence'] if regular else [])
    courses = [(m, course_days(m)) for m in medicines if course_days(m)]
    if courses:
        longest, length = max(courses, key=lambda pair: pair[1])
        if length >= 7:
            candidates.append(('progress', at(start_day(longest, visit_date) + timedelta(days=length // 2)),
                               followup_questions, [longest.id]))
        ends = {}
        for rx, length in courses:
            ends.setdefault(start_day(rx, visit_date) + timedelta(days=length - 1), []).append(rx.id)
        for day, ids in ends.items():
            candidates.append(('end_of_course', at(day), followup_questions, ids))
    if visit.review_date and visit.review_date - timedelta(days=2) > visit_date:
        candidates.append(('review', at(visit.review_date - timedelta(days=2)), ['review_attendance'], []))

    merged = {}
    for kind, due, questions, ids in sorted(candidates, key=lambda c: (c[1], KIND_RANK[c[0]])):
        day = due.astimezone(IST).date()
        if day <= visit_date:
            continue
        if day in merged:
            old_kind, old_due, old_questions, old_ids = merged[day]
            kind = max(old_kind, kind, key=KIND_RANK.get)
            questions = [q for q in QUESTION_ORDER if q in old_questions or q in questions]
            ids = list(dict.fromkeys(old_ids + ids))
            due = old_due
        merged[day] = (kind, due, list(questions), list(ids))

    touches = [FollowUpTouch(id='t0-summary', kind='summary', due_at=in_window(approved.approved_at),
                             medicine_ids=[m.id for m in medicines])]
    for index, (day, (kind, due, questions, ids)) in enumerate(sorted(merged.items()), start=1):
        status = 'planned' if len(touches) < MAX_TOUCHES else 'skipped'
        touches.append(FollowUpTouch(id=f't{index}-{kind}', kind=kind, due_at=due, questions=questions,
                                     medicine_ids=ids, status=status))
    return FollowUpPlan(visit_ref=approved.case_id, report_hash=approved.content_hash,
                        patient_id=approved.header.patient_id, channel=channel, language=approved.language_pref,
                        touches=touches)
