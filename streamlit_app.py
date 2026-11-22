import os
from datetime import date
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from src.adapters.planr.adapter import SCHEDULE_NAMES, load_project_schedule, load_schedule_names
from src.agent.analyzer import SECTION_FIELDS, analyze_project
from src.agent.model import format_references
from src.agent.letters import generate_letters
from src.workflows.schedule_actuality import check_schedule_actuality


SECTION_LABELS = {
    "attention_required": "Требует внимания",
    "analysis": "Анализ",
    "missing_information": "Недостающая информация",
    "recommended_checks": "Рекомендуемые проверки",
}


def render_knowledge_base(project_root: Path) -> None:
    with st.expander("База знаний (RAG)"):
        try:
            from src.rag.index import VectorIndex
            from src.rag.search import search

            index = VectorIndex(project_root / "data/chroma_db")
            stats = index.stats()
        except Exception:
            st.error("Не удалось открыть базу знаний. Проверьте зависимости и локальный индекс.")
            return
        if st.button("Построить индекс", key="rag_build"):
            try:
                with st.spinner("Индексируются нормативные документы..."):
                    stats = index.build(project_root / "data/documents")
                st.success(
                    f"Индекс построен. Документов: {stats['documents']}, "
                    f"фрагментов: {stats['chunks']}."
                )
            except Exception:
                st.error("Индексация не выполнена. Проверьте DOCX, зависимости и доступ к OpenAI.")
        st.caption(
            f"Индекс: {'доступен' if stats['available'] else 'отсутствует или пуст'}. "
            f"Фрагментов: {stats['chunks']}."
        )
        query = st.text_input("Запрос к нормативным документам", key="rag_query")
        if st.button("Найти в документах", key="rag_search"):
            try:
                with st.spinner("Поиск нормативных фрагментов..."):
                    results = search(index, query)
                if not results:
                    st.info("Фрагменты не найдены.")
                for result in results:
                    st.caption(result["source"])
                    st.text(result["text"])
            except ValueError as error:
                st.info(str(error))
            except Exception:
                st.error("Поиск недоступен. Проверьте локальный индекс и доступ к OpenAI.")


def render_control_results(schedules, findings) -> None:
    left, right = st.columns(2)
    left.metric("Элементов графика", sum(len(schedule.items) for schedule in schedules))
    right.metric("Найдено контрольных отклонений", sum(map(len, findings.values())))

    st.header("Контрольные проверки")
    if any(findings.values()):
        for schedule in schedules:
            if not findings[schedule.version_id]:
                continue
            if len(schedules) > 1:
                st.subheader(schedule.name)
            st.dataframe(
                [
                    {
                        "График": schedule.name,
                        "Код": finding.code,
                        "Название": finding.name,
                        "Окончание (UTC)": finding.finish.date().isoformat() if finding.finish else None,
                        "Прогресс, %": finding.progress,
                        "Статус": finding.status,
                        "Правило": finding.rule_id,
                        "Дней просрочки": finding.days_overdue,
                    }
                    for finding in findings[schedule.version_id]
                ],
                hide_index=True,
                column_config={"График": None},
            )
    else:
        st.info("Контрольные отклонения не выявлены.")


def main() -> None:
    project_root = Path(__file__).resolve().parent
    load_dotenv(project_root / ".env")
    fixtures = project_root / "data/fixtures/planr"

    st.set_page_config(page_title="AI Project Control Agent")
    st.title("AI Project Control Agent")
    st.caption("Интеллектуальный контроль исполнения проекта")
    st.image(str(project_root / "assets/project_control_hero.png"), width="stretch")
    render_knowledge_base(project_root)
    if not any((fixtures / key).is_dir() for key in SCHEDULE_NAMES):
        st.info("Графики в data/fixtures/planr не найдены.")
        return

    if "schedule_names" not in st.session_state:
        st.session_state["schedule_names"] = load_schedule_names(fixtures)
    schedule_names = st.session_state["schedule_names"]
    schedule_keys = st.multiselect(
        "Графики", list(schedule_names), default=["schedule_01"],
        format_func=schedule_names.__getitem__,
    )
    as_of_date = st.date_input("Дата анализа", value=date.today())
    use_rag = st.checkbox("Использовать RAG (корпоративные регламенты)", value=False)
    selection = (tuple(sorted(schedule_keys)), as_of_date, use_rag)
    saved = st.session_state.get("project_analysis")
    if saved is not None and saved["selection"] != selection:
        st.session_state.pop("project_analysis", None)
        st.session_state.pop("project_letters", None)
    run_analysis = st.button("Провести анализ", type="primary", disabled=not schedule_keys)
    if not schedule_keys:
        return

    if run_analysis:
        st.session_state.pop("project_analysis", None)
        st.session_state.pop("project_letters", None)
        with st.spinner("Выполняется контроль проекта..."):
            try:
                schedules = [load_project_schedule(fixtures / key) for key in schedule_keys]
                findings = {
                    schedule.version_id: check_schedule_actuality(schedule.items, as_of_date)
                    for schedule in schedules
                }
            except ValueError as error:
                st.error(str(error))
                return
            except (OSError, KeyError, TypeError):
                st.error("Не удалось прочитать или обработать данные выбранного графика.")
                return

            render_control_results(schedules, findings)

            st.header("AI-анализ проекта")
            if not os.environ.get("OPENAI_API_KEY"):
                st.error("Укажите OPENAI_API_KEY в файле .env в корне проекта.")
                return
            normative_context = None
            if use_rag:
                try:
                    from src.rag.index import VectorIndex
                    from src.rag.search import search

                    query = (
                        "Требования корпоративных регламентов к контролю исполнения проекта: "
                        "базовые и целевые сроки, актуальные сроки, контрольные события и вехи, "
                        "зависимости работ, фактическое выполнение и актуализация графика."
                    )
                    rules = {
                        finding.rule_id for entries in findings.values() for finding in entries
                    }
                    if "OVERDUE_INCOMPLETE" in rules:
                        query += " Незавершённые работы с истёкшим сроком и действия при отклонении сроков."
                    if "STATUS_PROGRESS_MISMATCH" in rules:
                        query += " Согласованность статуса завершения и процента выполнения работ."
                    fragments = search(VectorIndex(project_root / "data/chroma_db"), query, top_k=3)
                    if not fragments or any(
                        not fragment["text"].strip() or not fragment["source"].strip()
                        for fragment in fragments
                    ):
                        raise ValueError("Нормативные фрагменты не найдены.")
                    normative_context = "\n\n".join(
                        f"Источник: {fragment['source']}\n{fragment['text']}"
                        for fragment in fragments
                    )
                except Exception:
                    st.error(
                        "Анализ с RAG невозможен: нормативная база недоступна или поиск завершился ошибкой. "
                        "Проверьте наличие непустого индекса и доступ к OpenAI Embeddings."
                    )
                    return
            try:
                analysis = analyze_project(
                    schedules, findings, as_of_date, normative_context=normative_context
                )
            except RuntimeError as error:
                st.error(str(error))
                return
            except Exception:
                st.error("Не удалось выполнить AI-анализ. Проверьте настройки OpenAI и повторите запуск.")
                return

        st.session_state["project_analysis"] = {
            "selection": selection,
            "schedules": schedules,
            "findings": findings,
            "analysis": analysis,
        }
    else:
        saved = st.session_state.get("project_analysis")
        if saved is None:
            return
        schedules = saved["schedules"]
        findings = saved["findings"]
        analysis = saved["analysis"]
        render_control_results(schedules, findings)
        st.header("AI-анализ проекта")

    for section, label in SECTION_LABELS.items():
        entries = getattr(analysis, section)
        if entries:
            st.subheader(label)
            for entry in entries:
                if len(schedules) == 1:
                    references = entry["references"]
                    if all(reference["item_id"] is not None for reference in references):
                        codes = ", ".join(reference["code"] or "без кода" for reference in references)
                        st.text("Работы " + codes)
                else:
                    st.text(format_references(entry["references"], schedules))
                st.text(entry[SECTION_FIELDS[section]])

    st.header("Подготовленные письма")
    if st.button("Подготовить письма"):
        st.session_state.pop("project_letters", None)
        try:
            with st.spinner("Подготавливаются черновики писем..."):
                st.session_state["project_letters"] = generate_letters(
                    schedules, findings, analysis, as_of_date
                )
        except Exception:
            st.error("Не удалось подготовить письма. Результаты анализа сохранены. Повторите попытку.")
    names_by_version = {schedule.version_id: schedule.name for schedule in schedules}
    for letter in st.session_state.get("project_letters", []):
        st.subheader(names_by_version[letter["version_id"]])
        st.code(
            f"Тема: {letter['subject']}\n\n{letter['body']}",
            language=None, wrap_lines=True,
        )


if __name__ == "__main__":
    main()
