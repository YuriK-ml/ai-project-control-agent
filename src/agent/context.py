import json
from datetime import date
from typing import Sequence

from src.canonical.model import ProjectSchedule
from src.workflows.model import ControlFinding


def _schedule_context(schedule: ProjectSchedule, findings: list[ControlFinding]) -> dict:
    codes_by_id = {item.id: item.code for item in schedule.items}
    context = {
        "version_id": schedule.version_id,
        "name": schedule.name,
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
                "id": item.id,
                "parent_id": item.parent_id,
            }
            for item in schedule.items
        ],
        "dependencies": [
            {
                "first_code": codes_by_id.get(dependency.first_item_id),
                "second_code": codes_by_id.get(dependency.second_item_id),
                "first_item_id": dependency.first_item_id,
                "second_item_id": dependency.second_item_id,
                "type": dependency.type.value,
                "lag": dependency.lag,
                "version_id": dependency.version_id,
                "direction_confirmed": dependency.direction_confirmed,
            }
            for dependency in schedule.dependencies
        ],
        "findings": [
            {
                "item_id": finding.item_id,
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
    return context


def build_context(
    schedules: Sequence[ProjectSchedule],
    findings: dict[str, list[ControlFinding]],
    as_of_date: date,
) -> str:
    if not schedules:
        raise ValueError("Выберите хотя бы один график.")
    versions = [schedule.version_id for schedule in schedules]
    if len(set(versions)) != len(versions):
        raise ValueError("Одна версия графика выбрана несколько раз.")
    context = {
        "as_of_date": as_of_date.isoformat(),
        "schedules": [
            _schedule_context(schedule, findings[schedule.version_id])
            for schedule in schedules
        ],
    }
    return json.dumps(context, ensure_ascii=False, separators=(",", ":"))
