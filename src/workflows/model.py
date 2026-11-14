from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Union


@dataclass
class ControlFinding:
    rule_id: str
    item_id: str
    code: Optional[str]
    name: Optional[str]
    type: str
    finish: Optional[datetime]
    progress: Union[int, float]
    status: Optional[str]
    days_overdue: Optional[int]
    message: str
