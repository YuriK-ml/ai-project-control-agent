import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.canonical.model import DependencyType, ProjectSchedule, ScheduleDependency, ScheduleItem


SCHEDULE_NAMES = {
    "schedule_01": "График 01",
    "schedule_02": "График 02",
    "schedule_03": "График 03",
}


def _to_datetime(timestamp_ms: Optional[int]) -> Optional[datetime]:
    if timestamp_ms is None:
        return None
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)


def load_schedule(
    project_dir: Path, *, attributes_path: Optional[Path] = None
) -> list[ScheduleItem]:
    if attributes_path is None:
        attributes_path = project_dir / "wbs-attributes.json"
    with attributes_path.open(encoding="utf-8-sig") as file:
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
        # Preserve the original WBS relation strings.
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


def _matches_direction(predecessor: ScheduleItem, successor: ScheduleItem) -> bool:
    return (
        predecessor.code in (successor.predecessors or "").split(";")
        and successor.code in (predecessor.successors or "").split(";")
    )


def _read_relations(schedule_dir: Path) -> list[dict]:
    with (schedule_dir / "relations.json").open(encoding="utf-8-sig") as file:
        return json.load(file)


def load_schedule_names(fixtures: Path) -> dict[str, str]:
    """Resolve display names from EPS using the version IDs in relations."""
    names = SCHEDULE_NAMES.copy()
    try:
        with (fixtures / "common" / "eps.json").open(encoding="utf-8-sig") as file:
            nodes = {node["id"]: node for node in json.load(file)}
    except (OSError, ValueError, KeyError, TypeError):
        return names

    for key in names:
        try:
            version_id = _version_id(_read_relations(fixtures / key))
        except (OSError, ValueError, KeyError, TypeError):
            continue
        names[key] = _schedule_name(nodes, version_id, names[key])
    return names


def _version_id(relations: list[dict]) -> str:
    if not relations:
        raise ValueError("Ограничение MVP: relations.json пустой, определить версию графика невозможно.")
    versions = {relation["versionId"] for relation in relations}
    if len(versions) != 1:
        raise ValueError("Неоднозначность: relations.json содержит разные versionId.")
    version_id = next(iter(versions))
    if not isinstance(version_id, str) or not version_id.strip():
        raise ValueError("В relations.json отсутствует корректный versionId.")
    return version_id


def _schedule_name(nodes: dict, version_id: str, fallback: str) -> str:
    version = nodes.get(version_id)
    if version is None or version.get("type") != "version":
        return fallback
    parent = nodes.get(version.get("parentId"))
    if parent is not None and parent.get("type") == "schedule":
        name = parent.get("name")
        if isinstance(name, str) and name.strip():
            return name
    return fallback


def load_project_schedule(schedule_dir: Path) -> ProjectSchedule:
    relations = _read_relations(schedule_dir)
    version_id = _version_id(relations)
    fallback = SCHEDULE_NAMES.get(schedule_dir.name, schedule_dir.name)
    try:
        with (schedule_dir.parent / "common" / "eps.json").open(encoding="utf-8-sig") as file:
            nodes = {node["id"]: node for node in json.load(file)}
    except (OSError, ValueError, KeyError, TypeError):
        nodes = {}
    name = _schedule_name(nodes, version_id, fallback)
    items = load_schedule(
        schedule_dir,
        attributes_path=schedule_dir.parent / "common" / "wbs-attributes.json",
    )

    items_by_id = {item.id: item for item in items}
    code_counts = Counter(item.code for item in items)
    dependencies = []
    for relation in relations:
        first_id, second_id = relation["wbsId"], relation["linkedWbsId"]
        first, second = items_by_id.get(first_id), items_by_id.get(second_id)
        direction_confirmed = False
        if first and second and code_counts[first.code] == code_counts[second.code] == 1:
            forward = _matches_direction(first, second)
            backward = _matches_direction(second, first)
            direction_confirmed = forward != backward
            if backward and direction_confirmed:
                first_id, second_id = second_id, first_id
        dependencies.append(
            ScheduleDependency(
                first_item_id=first_id,
                second_item_id=second_id,
                type=DependencyType(relation["type"]),
                lag=relation["lag"],
                version_id=relation["versionId"],
                direction_confirmed=direction_confirmed,
            )
        )
    return ProjectSchedule(version_id=version_id, name=name, items=items, dependencies=dependencies)
