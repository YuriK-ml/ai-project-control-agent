import json
import os
from datetime import date
from pathlib import Path

from src.agent.context import build_context
from src.agent.model import ProjectAnalysis
from src.canonical.model import ScheduleItem
from src.workflows.model import ControlFinding


MODEL = "gpt-6-luna"
SECTION_FIELDS = {
    "attention_required": "issue",
    "analysis": "conclusion",
    "missing_information": "information",
    "recommended_checks": "action",
}


def analyze_project(
    schedule: list[ScheduleItem], findings: list[ControlFinding], as_of_date: date
) -> ProjectAnalysis:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY не задан. Укажите его в файле .env в корне проекта "
            "или в переменной окружения."
        )

    from openai import APIError, OpenAI

    context = build_context(schedule, findings, as_of_date)
    prompt = (Path(__file__).parent / "prompts/project_analysis.txt").read_text(encoding="utf-8")
    properties = {
        section: {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "codes": {"type": "array", "items": {"type": "string"}},
                    field: {"type": "string"},
                },
                "required": ["codes", field],
                "additionalProperties": False,
            },
        }
        for section, field in SECTION_FIELDS.items()
    }
    with OpenAI(api_key=api_key, max_retries=0) as client:
        try:
            response = client.responses.create(
                model=MODEL,
                instructions=prompt,
                input=context,
                store=False,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "project_analysis",
                        "strict": True,
                        "schema": {
                            "type": "object",
                            "properties": properties,
                            "required": list(properties),
                            "additionalProperties": False,
                        },
                    }
                },
            )
        except APIError as error:
            raise RuntimeError(f"Ошибка OpenAI API ({type(error).__name__}).") from None
    if response.status != "completed" or not response.output_text:
        raise RuntimeError(f"OpenAI returned no complete structured analysis (status: {response.status}).")
    return ProjectAnalysis(**json.loads(response.output_text))
