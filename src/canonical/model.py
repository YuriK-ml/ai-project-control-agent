from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional, Union


@dataclass
class ScheduleItem:
    id: str
    code: Optional[str]
    name: Optional[str]
    type: str
    parent_id: Optional[str]
    level: int
    start: Optional[datetime]
    finish: Optional[datetime]
    progress: Optional[Union[int, float]]
    status: Optional[str]
    predecessors: Optional[str]
    successors: Optional[str]
    target_start: Optional[datetime] = None
    target_finish: Optional[datetime] = None


class DependencyType(str, Enum):
    FINISH_TO_START = "fs"
    START_TO_START = "ss"
    FINISH_TO_FINISH = "ff"
    START_TO_FINISH = "sf"


@dataclass(frozen=True)
class ScheduleDependency:
    """The first item precedes the second when direction is confirmed."""

    first_item_id: str
    second_item_id: str
    type: DependencyType
    lag: Optional[Union[int, float]]
    version_id: str
    direction_confirmed: bool


@dataclass
class ProjectSchedule:
    version_id: str
    name: str
    items: list[ScheduleItem]
    dependencies: list[ScheduleDependency]
