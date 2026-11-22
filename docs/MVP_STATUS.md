# MVP Status

## Implemented

| Capability | Confirmed behavior |
| --- | --- |
| PLAN-R data loading | Local JSON WBS, relations, attribute dictionary and EPS |
| Schedule selection | Three configured local fixture directories; one or several may be selected |
| Canonical data | Separate in-memory schedules with version-scoped items and dependencies |
| Python checks | Overdue incomplete items and completed-status/progress mismatches |
| Management analysis | One joint OpenAI Responses request, four report sections and validated references |
| Optional corporate RAG | Local DOCX ingestion, persistent ChromaDB, OpenAI embeddings and vector retrieval |
| Analysis modes | Original schedule-only context or three retrieved regulatory excerpts |
| Project letters | One manual request creates a separate Russian draft for every selected schedule |
| UI state | Successful report retained for letter preparation; changed inputs invalidate prior results |
| Existing CLI | Single/multiple schedule analysis and API-free context inspection |

## Sources and integration status

PLAN-R is represented by saved JSON API responses on the local filesystem. Live API connectivity, pagination and scheduled synchronization have not been implemented. EPS provides schedule names using the version ID found in relations. A dataset without relations is outside the current MVP.

Corporate knowledge comes from locally approved DOCX. The index stores source filenames and extracted chunks. `text-embedding-3-small` is used for document and query embeddings. Search is vector-only with three results; hybrid search remains experimental.

Microsoft Project Server 2019 / ISUP connectivity, other corporate systems, contact directories and email delivery are future work.

## Analysis and letters

Python establishes formal data conditions. The AI layer adds management-oriented interpretation and checks the complete supplied canonical schedule. Current/target schedule dates do not establish actual dates or an approved baseline.

Letters are a separate step after successful analysis. The generator receives project-isolated saved results, without another graph analysis or regulatory search. Output correspondence is checked by version ID. A project without supported concerns can receive a short neutral letter.

The schema validates structure and identity, rather than factual correctness of generated prose. A user must verify drafts before copying or sending them manually.

## Verification

The automated suite is run with:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Verification uses synthetic schedules and DOCX, real temporary ChromaDB persistence, embedding stubs and mocked OpenAI responses. Coverage includes:

- Existing date/status/progress checks and canonical relations.
- Single and multiple schedules with colliding codes and local identifiers.
- Joint context, one shared analysis request and reference validation.
- DOCX paragraphs/tables, chunk overlap, metadata, persistence and rebuild failure.
- RAG-off compatibility, RAG-on context and blocking unavailable retrieval.
- One or three letter drafts, version correspondence and isolated inputs.
- Letter preparation without repeated loading, checking, AI analysis or retrieval.
- Draft reset, stale-selection invalidation and generation failure recovery.

Python 3.11 is the verified local runtime. No paid API calls are part of automated verification.

Stage 4.3 verification passed all 42 automated tests. An additional Streamlit AppTest
used synthetic schedules and mocked APIs to confirm single/three-project drafts,
both RAG modes, snapshot reuse, and draft reset after reanalysis.

## Current limitations

Operation requires manual actions and approved local data. Analysis results and letters live in the current Streamlit session.

A selected graph must have one distinct version ID in nonempty relations. Cross-schedule dependency processing is unsupported.

API request size limits apply. Retrieval can rank a direct requirement below the first three candidates. DOCX table geometry, text embedded in images and automatic numbering may be lost. Clause numbers are cited only when present in available evidence.

Shared multi-version report observations remain visible in the joint report but are excluded from separate letter inputs. Contact discovery, approval tracking, sending and autonomous follow-up are not implemented.

## Publication boundary

Corporate fixtures and DOCX, indexes, personal information and secrets must remain local. Use synthetic or explicitly publication-approved anonymized datasets for demonstrations. Competition concept documents and presentation materials have separate ownership and are outside this implementation stage.
