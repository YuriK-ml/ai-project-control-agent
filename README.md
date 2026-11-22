# AI Project Control Agent

A manually operated MVP for reviewing project schedules, identifying management-significant issues, and preparing separate Russian email drafts for schedule owners.

The application combines deterministic Python checks with one joint AI analysis of selected schedules. Optional retrieval from local corporate documents provides regulatory context. Users review the report before explicitly requesting letter drafts.

## Capabilities

- Load locally saved PLAN-R WBS, relations, attributes and EPS JSON responses.
- Review one or several schedules on a shared analysis date.
- Detect overdue incomplete items and completed-status/progress mismatches.
- Produce one structured management report covering all selected schedules.
- Optionally retrieve three corporate regulatory excerpts for the analysis.
- Prepare one separate email draft per selected schedule from the saved results.
- Inspect and copy drafts in Streamlit.

## Architecture

```text
Local PLAN-R JSON -> Adapter -> Canonical schedules -> Python checks
                                   |                       |
                                   +---- Joint AI analysis-+
                                              ^
Approved DOCX -> Local ChromaDB -> Optional retrieval
                                              |
                                       Saved report
                                              |
                              Prepare letters (manual action)
                                              |
                              Separate drafts for human review
```

| Component | Location |
| --- | --- |
| PLAN-R adapter | `src/adapters/planr/adapter.py` |
| In-memory canonical model | `src/canonical/model.py` |
| Deterministic checks | `src/workflows/` |
| Context and AI analyzer | `src/agent/context.py`, `src/agent/analyzer.py` |
| Corporate retrieval | `src/rag/` |
| Letter generator | `src/agent/letters.py` |
| Manual interface | `streamlit_app.py` |
| Existing CLI | `app.py` |

See [Architecture](docs/ARCHITECTURE.md), [MVP status](docs/MVP_STATUS.md), and [Roadmap](docs/ROADMAP.md).

## Installation

Python 3.11 is the verified development environment. Install dependencies in a virtual environment.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Set `OPENAI_API_KEY` in the local `.env`, or supply it through the environment. Existing environment values take precedence. The configured analysis and letter model is `gpt-6-luna`; access to that model is required. Corporate retrieval uses `text-embedding-3-small`.

Analysis, letter generation, document embeddings and query embeddings can incur API charges. Tests use synthetic documents and mocked API responses.

## Local data

Real project data, corporate DOCX, secrets and vector indexes are excluded from Git. Obtain approved local inputs before running the application. A fresh checkout does not include a ready-to-run corporate dataset.

```text
data/
  fixtures/planr/
    common/
      eps.json
      wbs-attributes.json
    schedule_01/
      wbs.json
      relations.json
    schedule_02/
      wbs.json
      relations.json
    schedule_03/
      wbs.json
      relations.json
  documents/
    <approved-document>.docx
  chroma_db/
    <generated local index>
```

The three fixture directories are registered in the current selection list. The canonical model accepts a collection of arbitrary length. Each selected dataset must have at least one relation and exactly one distinct `versionId`. Its display name resolves through the EPS version node and parent schedule node. Missing EPS names use technical fallback labels.

PLAN-R JSON is loaded from disk. Direct API ingestion and pagination are future work.

## Streamlit workflow

```powershell
.\.venv\Scripts\python.exe -m streamlit run streamlit_app.py
```

The interface and generated letters are in Russian.

1. Select schedules and an analysis date.
2. Leave **«Использовать RAG (корпоративные регламенты)»** unchecked for the existing schedule-only analysis, or enable it to include retrieved regulations.
3. Click **«Провести анализ»**.
4. Review deterministic findings and the unified AI report.
5. Click **«Подготовить письма»** to request a separate draft for each selected schedule.
6. Use the copy control in each draft's code block. Check all facts and wording before using a letter.

The report retains four sections: `attention_required`, `analysis`, `missing_information`, and `recommended_checks`. References use version and item IDs internally; the interface displays schedule names and work codes.

The latest successful analysis is kept in the Streamlit session. Letter preparation reuses that snapshot without loading schedules, rerunning checks, repeating the main AI analysis, or retrieving regulations. It makes one additional model request for the complete letter set. A generation error leaves the analysis available for retry.

Starting another analysis clears previous drafts. Changing the schedule selection, date or RAG mode invalidates the saved analysis and drafts. Session state is temporary. After changing local fixture files, rerun the analysis; restart the session to refresh cached selection names.

## Corporate knowledge base

Place approved DOCX in `data/documents/`. Open **«База знаний (RAG)»**, click **«Построить индекс»**, and then use **«Найти в документах»** for retrieval-only testing.

The loader reads paragraphs and tables, including nested tables, in document order. It creates chunks of up to 1,000 characters with 200-character overlap and source filenames. ChromaDB persists the index in `data/chroma_db/`. Rebuilding publishes the replacement only after all chunks are saved. A normal application rerun does not regenerate document embeddings.

With RAG enabled for analysis, a shared query covers schedule dates, milestones, dependencies, execution and updates, with extra wording for detected overdue items or status mismatches. Three vector-search results are supplied to the existing analysis call. Unavailable, empty or failed retrieval blocks that analysis instead of silently falling back. The knowledge-base panel remains independently usable.

Letters may use regulatory conclusions already present in their project's analysis. They do not perform another retrieval.

## Existing CLI

```powershell
.\.venv\Scripts\python.exe app.py --schedule schedule_01
.\.venv\Scripts\python.exe app.py --schedule schedule_01 schedule_02 schedule_03
.\.venv\Scripts\python.exe app.py --schedule schedule_01 schedule_02 --show-context
```

The CLI retains its existing fixed analysis date of 2026-11-14. `--show-context` prints the schedule context without an API request. RAG analysis selection and letter preparation are available through Streamlit.

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Tests use synthetic schedules, artificial DOCX, local temporary ChromaDB indexes and embedding/LLM stubs. They cover the existing schedule rules, reference isolation, retrieval, analysis modes and letter lifecycle.

## Limitations and publication

- Operation is manual. There is no autonomous control loop or email delivery.
- Dependencies are evaluated within their own schedules. Cross-schedule dependencies are unsupported.
- Schedule dates are distinct from actual dates. Target dates alone do not establish an approved baseline.
- AI output requires human review. Structured output validation cannot establish the factual correctness of every sentence.
- Letter inputs exclude observations referencing several versions, because their free text can contain another project's facts. Such observations remain in the joint report.
- Vector retrieval is approximate and incomplete. It can miss the most relevant requirement in the first three results.
- DOCX extraction does not preserve table geometry or reconstruct missing Word numbering. Images, headers, footers and text boxes may be omitted.
- A failed process may leave a RAG `build.lock`; remove it only after confirming no build is running.
- API context limits constrain practical dataset size. There is no automatic batching of the joint analysis.
- Public demonstrations must use synthetic or explicitly approved anonymized inputs. Review screenshots, pasted reports and copied drafts for confidential information.

Competition cards, business canvases, extended concepts and presentation materials are maintained separately.
