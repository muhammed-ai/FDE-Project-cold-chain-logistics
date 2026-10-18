# FDE Project: Cold-Chain Logistics

A cold-chain logistics intelligence project that combines fleet telemetry, live corridor weather, and compliance SOP retrieval to help operations teams make faster, safer decisions during route disruptions and temperature anomalies.

The system is designed as an AI-powered dispatch assistant that can:

- query telemetry from a Microsoft SQL Server dataset
- check external corridor conditions via a live weather API
- retrieve policy guidance from a Pinecone vector index
- reason over those inputs using a LangGraph agent
- present a business-ready incident summary in a Streamlit console

## Project purpose

This project simulates an enterprise cold-chain monitoring workflow where a dispatcher can ask operational questions such as:

- Which active shipments are near a region of concern?
- Are cargo temperatures violating fresh-perishable thresholds?
- What does the compliance SOP recommend in this scenario?
- Should the shipment be rerouted, inspected, or escalated?

The project is intentionally structured around the idea of "chatting with enterprise data" rather than just exposing raw tables or static dashboards.

## Core architecture

### 1. Data ingestion layer
The repo includes scripts to ingest:

- raw logistics telemetry into a legacy SQL Server table
- operational SOP/policy documents into a Pinecone vector database

Relevant files:

- [scripts/ingest_legacy_data.py](scripts/ingest_legacy_data.py)
- [scripts/ingest_sop_pinecone.py](scripts/ingest_sop_pinecone.py)

### 2. Tool-based AI agent
The business logic is implemented through tools in [src/agent_tools.py](src/agent_tools.py):

- query_telemetry_db: executes authorized SELECT statements against the fleet telemetry view
- fetch_corridor_conditions: pulls live weather data from Open-Meteo for a coordinate set
- search_compliance_sop: searches the indexed SOP content stored in Pinecone

These tools are bound to an LLM in the orchestrator.

### 3. LangGraph orchestration
The orchestrator in [src/orchestrator.py](src/orchestrator.py) creates a stateful conversational graph using LangGraph:

- reasoner node: the model decides whether it needs tools
- tools node: executes relevant tools
- loop: continues reasoning until it can answer the user

The project supports multiple reasoning backends through configuration:

- OpenAI
- DeepSeek
- local Ollama fallback

### 4. Streamlit control center
The application UI in [src/ui.py](src/ui.py) is a dispatch dashboard with:

- a chat-driven incident assistant
- expandable trace panels for tool inputs and outputs
- audit logging of node/tool execution
- admin-only log viewer access

## Data and compliance flow

The intended workflow is:

1. query telemetry first
2. fetch environmental corridor conditions
3. retrieve relevant SOP / compliance context
4. synthesize an operational recommendation

The system prompt in [src/prompts/system_prompt.txt](src/prompts/system_prompt.txt) enforces this sequence and standardizes the final answer format.

## Repository structure

- [README.md](README.md) — project overview and setup
- [requirements.txt](requirements.txt) — Python dependencies
- [docs/instrutions.md](docs/instrutions.md) — operational setup and deployment guide
- [scripts/](scripts/) — data ingestion and database setup utilities
- [src/](src/) — agent logic, orchestration, UI, and prompts
- [data/](data/) — raw telemetry and policy documents

## Tech stack

- Python 3.12
- Streamlit
- LangChain / LangGraph
- OpenAI / DeepSeek / Ollama
- Pinecone vector search
- Microsoft SQL Server via pyodbc / SQLAlchemy
- pandas and other data tooling

## Setup highlights

The workflow described in [docs/instrutions.md](docs/instrutions.md) includes:

- spinning up a local MSSQL container
- loading legacy fleet data
- indexing SOP policy documents into Pinecone
- creating restricted SQL views and agent permissions
- running the orchestrator locally
- launching the Streamlit UI with streamlit run src/ui.py

## Typical usage

After setup, the project is normally used in a terminal or UI session by asking questions such as:

- Find active shipments near Los Angeles and check if the cargo temperature violates fresh-perishable SOP thresholds.
- Explain lane disruption risk for a route with high wind and congestion.
- Tell me what action should be taken for a shipment that is approaching a temperature breach.

## Notes

This repository is best understood as an operational AI prototype for cold-chain logistics rather than a generic template project. It is designed to demonstrate how LLM reasoning, vector retrieval, and enterprise telemetry can be connected into a dispatch-level decision support workflow.

## Run locally

From the project root:

```bash
pip install -r requirements.txt
streamlit run src/ui.py
```

To run the local orchestrator directly:

```bash
python src/orchestrator.py
```

## Deployment note

The project documentation also includes instructions for deploying the Streamlit console to a Linux VM and running it as a systemd service, which makes it suitable for a lightweight internal operations deployment.
