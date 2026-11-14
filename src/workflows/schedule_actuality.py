from datetime import date

from src.canonical.model import ScheduleItem
from src.workflows.model import ControlFinding


def check_schedule_actuality(
    items: list[ScheduleItem], as_of_date: date
) -> list[ControlFinding]:
    """Check the schedule as of a UTC calendar date."""
    findings = []
    for item in items:
        if item.progress is None or not item.progress < 100:
            continue

        if item.finish is not None:
            finish_date = item.finish.date()
            if finish_date < as_of_date:
                findings.append(
                    ControlFinding(
                        rule_id="OVERDUE_INCOMPLETE",
                        item_id=item.id,
                        code=item.code,
                        name=item.name,
                        type=item.type,
                        finish=item.finish,
                        progress=item.progress,
                        status=item.status,
                        days_overdue=(as_of_date - finish_date).days,
                        message="Срок элемента графика истёк, выполнение не завершено.",
                    )
                )

        if item.status == "completed":
            findings.append(
                ControlFinding(
                    rule_id="STATUS_PROGRESS_MISMATCH",
                    item_id=item.id,
                    code=item.code,
                    name=item.name,
                    type=item.type,
                    finish=item.finish,
                    progress=item.progress,
                    status=item.status,
                    days_overdue=None,
                    message="Статус элемента — completed, но прогресс меньше 100%.",
                )
            )
    return findings
