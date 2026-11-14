import json
from datetime import date

from src.canonical.model import ScheduleItem
from src.workflows.model import ControlFinding


def build_context(
    schedule: list[ScheduleItem], findings: list[ControlFinding], as_of_date: date
) -> str:
    codes_by_id = {item.id: item.code for item in schedule}
    context = {
        "as_of_date": as_of_date.isoformat(),
        "schedule": [
            {
                "code": item.code,
                "name": item.name,
                "type": item.type,
                "parent_code": codes_by_id.get(item.parent_id),
                "level": item.level,
                "start": item.start.isoformat() if item.start is not None else None,
                "finish": item.finish.isoformat() if item.finish is not None else None,
                "target_start": item.target_start.isoformat() if item.target_start is not None else None,
                "target_finish": item.target_finish.isoformat() if item.target_finish is not None else None,
                "progress": item.progress,
                "status": item.status,
                "predecessors": item.predecessors,
                "successors": item.successors,
            }
            for item in schedule
        ],
        "findings": [
            {
                "rule_id": finding.rule_id,
                "code": finding.code,
                "name": finding.name,
                "finish": finding.finish.isoformat() if finding.finish is not None else None,
                "progress": finding.progress,
                "status": finding.status,
                "days_overdue": finding.days_overdue,
                "message": finding.message,
            }
            for finding in findings
        ],
    }
    return json.dumps(context, ensure_ascii=False, separators=(",", ":"))
