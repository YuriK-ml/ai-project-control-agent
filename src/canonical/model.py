from dataclasses import dataclass
from datetime import datetime
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
