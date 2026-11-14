import os
from datetime import date
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from src.adapters.planr.adapter import load_schedule
from src.agent.analyzer import SECTION_FIELDS, analyze_project
from src.workflows.schedule_actuality import check_schedule_actuality


SECTION_LABELS = {
    "attention_required": "Требует внимания",
    "analysis": "Анализ",
    "missing_information": "Недостающая информация",
    "recommended_checks": "Рекомендуемые проверки",
}


def main() -> None:
    project_root = Path(__file__).resolve().parent
    load_dotenv(project_root / ".env")
    fixtures = project_root / "data/fixtures/planr"
    projects = sorted(path.name for path in fixtures.glob("*") if path.is_dir())

    st.set_page_config(page_title="AI Project Control Agent")
    st.title("AI Project Control Agent")
    st.caption("Интеллектуальный контроль исполнения проекта")
    st.image(str(project_root / "assets/project_control_hero.png"), width="stretch")
    if not projects:
        st.info("Проекты в data/fixtures/planr не найдены.")
        return

    project = st.selectbox("Проект", projects)
    as_of_date = st.date_input("Дата анализа", value=date.today())
    if not st.button("Запустить контроль проекта", type="primary"):
        return

    with st.spinner("Выполняется контроль проекта..."):
        try:
            schedule = load_schedule(fixtures / project)
            findings = check_schedule_actuality(schedule, as_of_date)
        except (OSError, ValueError, KeyError, TypeError):
            st.error("Не удалось прочитать или обработать данные выбранного проекта.")
            return

        left, right = st.columns(2)
        left.metric("Элементов графика", len(schedule))
        right.metric("Найдено контрольных отклонений", len(findings))

        st.header("Контрольные проверки")
        if findings:
            st.dataframe(
                [
                    {
                        "Код": finding.code,
                        "Название": finding.name,
                        "Окончание (UTC)": finding.finish.date().isoformat() if finding.finish else None,
                        "Прогресс, %": finding.progress,
                        "Статус": finding.status,
                        "Правило": finding.rule_id,
                        "Дней просрочки": finding.days_overdue,
                    }
                    for finding in findings
                ],
                hide_index=True,
            )
        else:
            st.info("Контрольные отклонения не выявлены.")

        st.header("AI-анализ проекта")
        if not os.environ.get("OPENAI_API_KEY"):
            st.error("Укажите OPENAI_API_KEY в файле .env в корне проекта.")
            return
        try:
            analysis = analyze_project(schedule, findings, as_of_date)
        except Exception:
            st.error("Не удалось выполнить AI-анализ. Проверьте настройки OpenAI и повторите запуск.")
            return

    for section, label in SECTION_LABELS.items():
        entries = getattr(analysis, section)
        if entries:
            st.subheader(label)
            for entry in entries:
                codes = ", ".join(entry["codes"])
                prefix = f"[{codes}] " if codes else ""
                st.text(f"{prefix}{entry[SECTION_FIELDS[section]]}")


if __name__ == "__main__":
    main()
