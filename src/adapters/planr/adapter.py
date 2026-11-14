import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.canonical.model import ScheduleItem


def _to_datetime(timestamp_ms: Optional[int]) -> Optional[datetime]:
    if timestamp_ms is None:
        return None
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)


def load_schedule(project_dir: Path) -> list[ScheduleItem]:
    with (project_dir / "wbs-attributes.json").open(encoding="utf-8-sig") as file:
        attribute_keys = {item["id"]: item["key"] for item in json.load(file)}

    with (project_dir / "wbs.json").open(encoding="utf-8-sig") as file:
        wbs = json.load(file)

    schedule = []
    for row in wbs:
        values = {
            attribute_keys[attribute_id]: value
            for attribute_id, value in row["values"].items()
            if attribute_id in attribute_keys
        }
        # The fixtures only show single codes. Keep relation strings intact.
        schedule.append(
            ScheduleItem(
                id=row["id"],
                code=values.get("code"),
                name=values.get("name"),
                type=row["type"],
                parent_id=row["parentId"],
                level=row["level"],
                start=_to_datetime(values.get("start")),
                finish=_to_datetime(values.get("finish")),
                target_start=_to_datetime(values.get("target-start")),
                target_finish=_to_datetime(values.get("target-finish")),
                progress=values.get("progress"),
                status=values.get("status"),
                predecessors=values.get("relation-in"),
                successors=values.get("relation-out"),
            )
        )
    return schedule
