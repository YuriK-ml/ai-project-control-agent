from dataclasses import dataclass
from typing import TypedDict


class AttentionItem(TypedDict):
    codes: list[str]
    issue: str


class AnalysisItem(TypedDict):
    codes: list[str]
    conclusion: str


class MissingInformationItem(TypedDict):
    codes: list[str]
    information: str


class RecommendedCheck(TypedDict):
    codes: list[str]
    action: str


@dataclass
class ProjectAnalysis:
    attention_required: list[AttentionItem]
    analysis: list[AnalysisItem]
    missing_information: list[MissingInformationItem]
    recommended_checks: list[RecommendedCheck]
