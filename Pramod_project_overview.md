# IDAMP — Intent-Driven Agentic Medallion Pipeline
### Project Overview

---

## What It Does

IDAMP is a multi-agent data engineering pipeline with a Streamlit web interface. The user uploads raw CSV files, states a business question in plain English, and the system automatically processes the data through three quality layers — Bronze, Silver, and Gold — before generating an executive HTML report that directly answers the question.

The pipeline pauses at each layer for human review of the generated transformation rules (STTM). An auto-approve toggle is available to skip manual review when needed.

---

## LLM Used

| Component | Model | Provider |
|---|---|---|
| All agents | claude-sonnet-4-5 | Anthropic API |

The model is configured via `.env` and can be swapped without changing any agent code.

---

## Agent Architecture

The system uses six specialist agents coordinated by a Supervisor Orchestrator.

```
User Upload + Business Intent
        |
        v
  Supervisor Orchestrator
  (ReAct loop — plans which agents to call and in what order)
        |
   Phase 1   -->  Profiler Agent  -->  STTM Agent (Bronze rules)
        |                                        |
   [Human review / auto-approve]                 |
        |<----------------------------------------
   Phase 2   -->  Bronze Agent   -->  STTM Agent (Silver rules)
        |                                        |
   [Human review / auto-approve]                 |
        |<----------------------------------------
   Phase 3   -->  Silver Agent   -->  STTM Agent (Gold rules)
        |                                        |
   [Human review / auto-approve]                 |
        |<----------------------------------------
   Phase 4   -->  Gold Agent     -->  Reporter Agent
                                            |
                                     HTML Report
```

### Profiler Agent
Reads uploaded CSV files and produces a statistical profile — column types, null counts, unique values, sample data, and semantic meaning. Output is saved as a JSON profile used by downstream agents.

### STTM Agent
Generates Source-to-Target Mapping rules for each pipeline layer. Given the data profile and business intent, it writes a CSV of transformation rules that the layer agents execute. Called once per layer with a different goal each time.

### Bronze Agent
Applies the Bronze STTM rules to raw CSVs: renames columns, casts types, injects metadata columns (`_load_timestamp`, `_source_file`), and writes Parquet files. No null handling at this stage — faithful copy of the source.

### Silver Agent
Applies the Silver STTM rules to Bronze Parquet: handles nulls (drop/fill), deduplicates rows, standardises date formats to YYYY-MM-DD, normalises text, and injects a surrogate key column. Output is clean, trusted Parquet.

### Gold Agent
Joins Silver Parquet files, applies aggregations (sum, avg, count, max, min), and materialises analytics-ready Gold Parquet tables — one per target defined in the STTM.

### Reporter Agent
Loads Gold tables into an in-memory DuckDB database, writes SQL to answer the business question, and renders an HTML report with Plotly charts and a written executive summary.

### Supervisor Orchestrator
An autonomous LangGraph ReAct agent that coordinates the other agents as tools. It does not follow a fixed script — it reasons about the pipeline state at each phase and decides which agents to invoke and in what order.

---

## Tech Stack

| Layer | Technology |
|---|---|
| UI | Streamlit |
| Orchestration | LangGraph, LangChain |
| LLM Integration | langchain-anthropic |
| Data Processing | pandas, pyarrow |
| Analytics SQL | DuckDB |
| Visualisation | Plotly |
| Vector Memory | ChromaDB |
| Config | python-dotenv |

---

## Pipeline Data Flow

```
Raw CSV  ->  Landing Zone
             Bronze Parquet  (data/bronze_layer/)
             Silver Parquet  (data/silver_layer/)
             Gold Parquet    (data/gold_layer/)
             HTML Report     (reports/)
```

Each run is identified by a unique `run_id`. Every generated file, audit log, and agent trace includes this ID so a complete run can be traced end to end.

---

## Human-in-the-Loop Control

The pipeline is designed with three approval checkpoints — one after each STTM is generated (Bronze, Silver, Gold). At each checkpoint the user can inspect the transformation rules, edit them in a table, and approve before the layer executes.

An **Auto-approve toggle** is available in the UI for fast runs or demos. When enabled, the pipeline reads the generated STTM, displays it briefly, and automatically advances to the next stage without waiting for a button click. The toggle can be switched on or off at any point; turning it off mid-run restores manual control from the next checkpoint onward.

This design keeps the human in control of data quality while giving the option to run end-to-end unattended when the pipeline is already trusted.

---

## Key Design Decisions

**Tool closures** — file paths and run IDs are captured in Python closures at tool creation time, so the LLM never needs to reproduce them as arguments. This eliminates hallucination risk on paths.

**STTM as the contract** — transformation rules are written to a CSV before execution. This gives the human a clear checkpoint: approve the recipe before the data is processed.

**ReAct pattern** — every agent follows Inspect → Plan → Act → Verify. The inspect tool runs first (read-only), the agent forms a plan, then the execution tool runs. The LLM never acts blindly.
