import json
from argparse import ArgumentParser
from collections import Counter
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

from src.adapters.planr.adapter import load_schedule
from src.agent.analyzer import SECTION_FIELDS, analyze_project
from src.agent.context import build_context
from src.workflows.schedule_actuality import check_schedule_actuality


def main() -> None:
    parser = ArgumentParser()
    parser.add_argument("--show-context", action="store_true", help="Print the LLM input JSON and exit")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent
    load_dotenv(project_root / ".env")
    project_dir = project_root / "data/fixtures/planr/project_01"
    with (project_dir / "eps.json").open(encoding="utf-8-sig") as file:
        eps = json.load(file)
    schedule = load_schedule(project_dir)
    as_of_date = date(2026, 11, 14)
    findings = check_schedule_actuality(schedule, as_of_date)
    if args.show_context:
        print(build_context(schedule, findings, as_of_date))
        return

    counts = Counter(finding.rule_id for finding in findings)

    print(f"EPS entries: {len(eps)}")
    print(f"Schedule items: {len(schedule)}")
    print(f"As of (UTC): {as_of_date}")
    print(f"OVERDUE_INCOMPLETE: {counts['OVERDUE_INCOMPLETE']}")
    print(f"STATUS_PROGRESS_MISMATCH: {counts['STATUS_PROGRESS_MISMATCH']}")
    print("code | name | finish | progress | status | rule_id | days_overdue")
    for finding in findings:
        finish = finding.finish.date().isoformat() if finding.finish else "—"
        days = finding.days_overdue if finding.days_overdue is not None else "—"
        print(
            f"{finding.code or '—'} | {finding.name or '—'} | {finish} | "
            f"{finding.progress} | {finding.status or '—'} | {finding.rule_id} | {days}"
        )

    try:
        analysis = analyze_project(schedule, findings, as_of_date)
    except RuntimeError as error:
        raise SystemExit(str(error)) from error

    for section, field in SECTION_FIELDS.items():
        print(f"\n{section.replace('_', ' ').upper()}")
        entries = getattr(analysis, section)
        if not entries:
            print("—")
        for entry in entries:
            codes = ", ".join(entry["codes"])
            prefix = f"[{codes}] " if codes else ""
            print(f"- {prefix}{entry[field]}")


if __name__ == "__main__":
    main()
