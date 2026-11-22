from dataclasses import dataclass
from typing import Optional, Sequence, TypedDict

from src.canonical.model import ProjectSchedule


class ItemReference(TypedDict):
    version_id: str
    item_id: Optional[str]
    code: Optional[str]


class AttentionItem(TypedDict):
    references: list[ItemReference]
    issue: str


class AnalysisItem(TypedDict):
    references: list[ItemReference]
    conclusion: str


class MissingInformationItem(TypedDict):
    references: list[ItemReference]
    information: str


class RecommendedCheck(TypedDict):
    references: list[ItemReference]
    action: str


@dataclass
class ProjectAnalysis:
    attention_required: list[AttentionItem]
    analysis: list[AnalysisItem]
    missing_information: list[MissingInformationItem]
    recommended_checks: list[RecommendedCheck]


def format_references(references: list[ItemReference], schedules: Sequence[ProjectSchedule]) -> str:
    names = {schedule.version_id: schedule.name for schedule in schedules}
    groups: dict[str, list[ItemReference]] = {}
    for reference in references:
        groups.setdefault(reference["version_id"], []).append(reference)

    labels = []
    for version_id, group in groups.items():
        label = names[version_id]
        if all(reference["item_id"] is not None for reference in group):
            codes = ", ".join(reference["code"] or "без кода" for reference in group)
            label += " — работы " + codes
        labels.append(label)
    return "\n".join(labels)
