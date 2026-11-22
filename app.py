import json
from argparse import ArgumentParser
from collections import Counter
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

from src.adapters.planr.adapter import SCHEDULE_NAMES, load_project_schedule
from src.agent.analyzer import SECTION_FIELDS, analyze_project
from src.agent.context import build_context
from src.agent.model import format_references
from src.workflows.schedule_actuality import check_schedule_actuality


def main() -> None:
    parser = ArgumentParser()
    parser.add_argument("--schedule", choices=SCHEDULE_NAMES, nargs="+", default=["schedule_01"])
    parser.add_argument("--show-context", action="store_true", help="Print the LLM input JSON and exit")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent
    load_dotenv(project_root / ".env")
    fixtures = project_root / "data/fixtures/planr"
    with (fixtures / "common" / "eps.json").open(encoding="utf-8-sig") as file:
        eps = json.load(file)
    try:
        schedules = [load_project_schedule(fixtures / key) for key in args.schedule]
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise SystemExit(str(error)) from error
    as_of_date = date(2026, 11, 14)
    findings = {
        schedule.version_id: check_schedule_actuality(schedule.items, as_of_date)
        for schedule in schedules
    }
    if args.show_context:
        print(build_context(
            schedules, findings, as_of_date
        ))
        return

    counts = Counter(finding.rule_id for group in findings.values() for finding in group)

    print(f"EPS entries: {len(eps)}")
    print(f"Schedule items: {sum(len(schedule.items) for schedule in schedules)}")
    print(f"As of (UTC): {as_of_date}")
    print(f"OVERDUE_INCOMPLETE: {counts['OVERDUE_INCOMPLETE']}")
    print(f"STATUS_PROGRESS_MISMATCH: {counts['STATUS_PROGRESS_MISMATCH']}")
    print("code | name | finish | progress | status | rule_id | days_overdue")
    for schedule in schedules:
        print(schedule.name)
        for finding in findings[schedule.version_id]:
            finish = finding.finish.date().isoformat() if finding.finish else "—"
            days = finding.days_overdue if finding.days_overdue is not None else "—"
            print(
                f"{finding.code or '—'} | {finding.name or '—'} | {finish} | "
                f"{finding.progress} | {finding.status or '—'} | {finding.rule_id} | {days}"
            )

    try:
        analysis = analyze_project(
            schedules, findings, as_of_date
        )
    except RuntimeError as error:
        raise SystemExit(str(error)) from error

    for section, field in SECTION_FIELDS.items():
        print(f"\n{section.replace('_', ' ').upper()}")
        entries = getattr(analysis, section)
        if not entries:
            print("—")
        for entry in entries:
            prefix = "[" + format_references(entry["references"], schedules) + "] "
            print(f"- {prefix}{entry[field]}")


if __name__ == "__main__":
    main()
