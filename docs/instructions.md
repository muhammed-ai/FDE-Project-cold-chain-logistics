# FDE Project: Local Setup and Operations

Use this guide to prepare the local environment, populate the project's data stores, configure access, and launch the application. The sequence follows the dependencies between those components.

> This repository is based on the [Cold Chain Logistics FDE Project](https://github.com/nimowhyca/cold-chain-logistics-FDE-Project). The steps below have been adapted to describe this checkout; consult the upstream repository for its original materials and history.

## Project overview

The application brings together several sources and services to support cold-chain operations:

- load cold-chain fleet data into SQL Server
- index policy documents for compliance retrieval
- ask a chatbot questions about route conditions and potential cargo risks
- use an AI agent to combine telemetry, weather, and SOP guidance
- view the results in a Streamlit dashboard

---

# Step 1: Install prerequisites

Install or prepare the following before setting up the application:

- Docker Desktop installed
- Python 3.12 installed
- Git installed
- access to a terminal
- a SQL client such as VS Code SQL extension or Azure Data Studio

In a terminal opened at the project root, install the Python packages:

```bash
pip install -r requirements.txt
```

The SQL Server ODBC driver is also required for Python-to-database connections. Install the driver and its operating-system dependencies if they are not already available.

---

# Step 2: Launch SQL Server

The local SQL Server container provides the database used for the sample fleet records. Select the command for your environment.

## Option A: Local machine (macOS / Linux)

For Docker Desktop on macOS or Linux, run:

```bash
docker run -e "ACCEPT_EULA=Y" -e "MSSQL_SA_PASSWORD=FdeEnterprisePass123!" \
  -p 1433:1433 \
  --name legacy-mssql \
  -d mcr.microsoft.com/mssql/server:2022-latest
```

## Option B: Windows

In Windows PowerShell, use `^` to continue a command across lines:

```powershell
docker run -e "ACCEPT_EULA=Y" -e "MSSQL_SA_PASSWORD=FdeEnterprisePass123!" ^
  -p 1433:1433 --name legacy-mssql ^
  -d mcr.microsoft.com/mssql/server:2022-latest
```

## Option C: EC2 / VM with persistent storage

To retain database files when the container is removed or recreated, attach a Docker volume:

```bash
docker run -v mssql_data:/var/opt/mssql \
  -e "ACCEPT_EULA=Y" \
  -e "MSSQL_SA_PASSWORD=FdeEnterprisePass123!" \
  -p 1433:1433 \
  --name legacy-mssql \
  -d mcr.microsoft.com/mssql/server:2022-latest
```

### Confirm SQL Server is running

Run:

```bash
docker ps
```

Look for a running container named `legacy-mssql` in the output.

---

# Step 3: Open a SQL Server connection

Use Azure Data Studio or the VS Code SQL extension to connect to the container.

## Connection details

Enter the following connection values:

```text
Profile Name: legacy-mssql
Server name: localhost
Port: 1433
Authentication type: SQL Login
User name: sa
Password: FdeEnterprisePass123!
Trust server certificate: ON
Database: master
Encrypt: Optional or False
```

After the connection succeeds, check whether the raw telemetry table is present and populated:

```sql
SELECT COUNT(*) AS total_rows FROM dbo.TBL_SC_FLEET_HIST_RAW;
```

If SQL Server reports that the table does not exist, continue to Step 4 to import the CSV.

---

# Step 4: Import fleet telemetry

The source telemetry is provided as a CSV file. Import it into SQL Server before creating the agent's restricted view.

Run this command from the project root:

```bash
python3 scripts/ingest_legacy_data.py
```

The import script performs three main operations:

- reads the CSV file from the data folder
- maps the raw fields into the legacy database schema
- inserts the rows into the table `dbo.TBL_SC_FLEET_HIST_RAW`

The next database setup step uses this table as its source and exposes selected fields to the agent through a separate view.

---

# Step 5: Index compliance material

Fleet readings describe what is happening; the operating procedure (SOP) describes how staff should respond. This step makes those procedures searchable by the agent.

## Role of the SOP (Standard Operating Procedure)

Cold-chain decisions depend on both sensor readings and handling requirements. A dispatcher may need to determine:

- Is this temperature within the allowed range?
- Does this event count as a cold-chain incident?
- What should the dispatcher do next according to policy?
- Do we need to escalate this to a supervisor or compliance team?

SQL provides measured or calculated values such as temperature, route risk, and delay probability. The SOP supplies the procedures and thresholds used to interpret those values and select a response.

Without relevant policy context, an LLM may produce a plausible general answer that does not reflect the organization's actual procedure. Retrieving the SOP gives the agent material to reference when forming its response.

Policy source files for this repository are kept in `data/policy`.

## Pinecone's role

Pinecone is a hosted vector database. The ingestion script stores numerical representations of policy text there so that searches can find passages related by meaning, rather than requiring an exact phrase match.

For example, if someone asks:

> “What should we do when temperature exceeds the safe range?”

the search can locate policy passages about temperature excursions even if the SOP uses different wording. This meaning-based retrieval is commonly called semantic or vector search.

## How the agent uses the index

The policy index allows the agent to:

- search the SOP by meaning
- find the most relevant policy section quickly
- ground its answer in actual operational rules
- respond with policy-aware, compliance-safe recommendations

The ingestion process divides longer documents into passages. Pinecone can then return the passages most relevant to a question, instead of requiring the whole document to be supplied each time.

## Local embedding model requirements

With `Embeddings_model=LOCAL`, Python runs the embedding model on the computer executing the script. The model package and weights must be available on that computer.

For example, running `python3.11 scripts/ingest_sop_pinecone.py` on a laptop downloads or uses the model on that laptop. A separate server running the script needs its own access to the model files.

This differs from a hosted embedding service, where requests are sent to a remote provider instead of running the model locally.

## Configure Pinecone access

1. Sign in at https://app.pinecone.io/.
2. Create or select a Pinecone project.
3. Copy its API key.
4. Add the key to the project-root `.env` file.

Set the relevant environment variables. The values below illustrate the expected names; use credentials and settings for your own environment:

```env
PINECONE_API_KEY=your_key_here
SQL_SERVER_HOST=localhost
SQL_SERVER_PORT=1433
SQL_ADMIN_USER=sa
SQL_ADMIN_PASSWORD=FdeEnterprisePass123!
SQL_AGENT_USER=USR_FDE_RO
SQL_AGENT_PASSWORD=AgentPassword2026!
Agent_llm=OLLAMA
Embeddings_model=LOCAL
Local_Embedding_Model=BAAI/bge-m3
```

## Index the policy files

From the project root, start the ingestion script:

```bash
python scripts/ingest_sop_pinecone.py
```

The script reads files from `data/policy`, divides their content into passages, creates an embedding for each passage, and uploads the results to Pinecone. The agent searches these indexed passages at runtime.

After indexing, the agent can retrieve policy context for questions such as:

- “What are the compliance steps for an incident?”
- “What should an operator do if cargo temperature rises above threshold?”
- “Which SOP section covers a route delay with possible spoilage risk?”

This connects operational telemetry to the procedures used to interpret it.

---

# Step 6: Configure the agent's SQL access

This step creates a curated database view for agent queries and restricts the agent account from reading the raw source table directly.

Open this SQL script in your SQL client:

```text
scripts/setup_security_and_view.sql
```

Connect as a SQL administrator to the `master` database and execute the script in Azure Data Studio, SQL Server Management Studio, or the VS Code SQL editor.

The script sets up these database objects and permissions:

- a schema called `FDE_VIEWS`
- a view called `FDE_VIEWS.VW_ACTIVE_FLEET`
- a restricted login/user called `USR_FDE_RO`
- explicit deny rules for the raw table

The agent's database tool is intended to query the curated view rather than the underlying raw import. This separates the data the agent can use from the original table.

## Check the permissions

Reconnect using the agent account and try both queries. The first should return rows:

```sql
SELECT TOP 5 * FROM FDE_VIEWS.VW_ACTIVE_FLEET;
```

The second query is expected to be denied:
```sql
SELECT TOP 5 * FROM dbo.TBL_SC_FLEET_HIST_RAW;
```

---

# Step 7: Exercise the agent and its tools

Use this step to verify that the model can work with the project's data tools, rather than only checking that each service was installed.

Two files coordinate this behavior:

- `agent_tools.py`: this file defines the tools the AI can use
- `orchestrator.py`: this file decides when to call those tools and how to combine the results

At a high level:

- the AI is the decision-maker
- the tools are the helpers
- the orchestrator is the manager in charge of calling the right helper at the right time

## What the tools do

The agent tools in this project are:

- `query_telemetry_db`: reads live fleet/temperature data from SQL Server
- `fetch_corridor_conditions`: checks weather and route conditions for a location
- `search_compliance_sop`: searches the SOP documents in Pinecone for the relevant policy rule

The model can request one or more tools, receive their results, and use those results to form its response.

## Example request flow

If you ask:

```text
Find any active shipments near Los Angeles (Latitude ~33.8, Longitude ~-118.1). Check the local weather there, and tell me if the current cargo temperature violates the SOP for fresh perishables.
```

For that question, the agent may:

1. query the SQL database for nearby active shipments
2. check the weather for that location
3. look up the relevant SOP rule from Pinecone
4. compare the temperature and conditions to the policy
5. answer with a final recommendation

This flow combines operational records, current corridor conditions, and policy guidance for a single response.

## Start the command-line test loop

Run these commands from the project root. The first runs each tool's standalone checks; the second starts the interactive agent:

```bash
python src/agent_tools.py
python src/orchestrator.py
```

If the agent starts, enter a sample request at the `Dispatcher >` prompt. Depending on the question, it may need SQL Server, the Pinecone index, the configured LLM, or the weather API to be reachable.

## Requests to try

### Example prompt 1

```text
Find any active shipments near Los Angeles (Latitude ~33.8, Longitude ~-118.1). Check the local weather there, and tell me if the current cargo temperature violates the SOP for fresh perishables.
```

### Example prompt 2

```text
I'm a new dispatcher on the night shift. Can you quickly explain the difference between a Tier 1 and Tier 2 escalation?
```

### Example prompt 3

```text
Which vehicles have high risk and what is the recommended compliance action according to the SOP?
```

Check the response and tool activity to confirm the agent is retrieving the expected information. A full test requires the relevant services and data sources to be configured and available.

---

# Step 8: Create the agent audit table

Create a SQL Server table for records of the agent's activity. An audit log provides a trace of selected application events while a request is processed.

When the application runs, it can record information such as:

- which conversation session an event belongs to
- which part of the agent ran, such as the reasoner or a tool
- which tool was requested, such as SQL telemetry or SOP search
- the tool input, tool result, or final response text

These records help with reviewing tool usage and responses and diagnosing problems. The audit table stores application activity, not fleet telemetry.

Complete Steps 2 and 6 first. SQL Server must be running, and Step 6 must have created the `FDE_VIEWS` schema and `USR_FDE_RO` database user. Connect to the `master` database in your SQL client using an administrator account such as `sa` before running this SQL.

Open a new SQL query window and run:

```sql
CREATE TABLE FDE_VIEWS.AgentAuditLog (
    LogID INT IDENTITY(1,1) PRIMARY KEY,
    Timestamp DATETIME DEFAULT GETDATE(),
    SessionID VARCHAR(50),
    NodeExecuted VARCHAR(50),
    ToolName VARCHAR(100),
    Content NVARCHAR(MAX)
);

GRANT INSERT ON FDE_VIEWS.AgentAuditLog TO USR_FDE_RO;
```

`CREATE TABLE` creates the audit table. `GRANT INSERT` allows the restricted agent account to add entries; it does not grant read, update, or delete permissions. Run the table-creation statement once, and skip it if the table already exists.

During requests, the Streamlit application writes selected events to the table. An administrator can view stored entries from the Security & Audit Logs section of the UI.

**Data handling note:** the log can contain tool inputs and outputs and the model's final responses. These may include operational details or excerpts from retrieved records and SOPs. Treat the log as operational data and restrict access appropriately; never put passwords, API keys, or other secrets into prompts.

To verify the table was created, run this in the same database:

```sql
SELECT OBJECT_ID('FDE_VIEWS.AgentAuditLog', 'U') AS audit_table_id;
```

A non-`NULL` `audit_table_id` means SQL Server found the table.

---

# Step 9: Launch the web application

Start the Streamlit application to use the chat interface. It sends questions to the orchestrator, which can access the configured SQL, weather, and SOP tools.

Before starting it, confirm that SQL Server is running and that the setup steps for the data, Pinecone index, security view, and audit table have completed. The configured LLM must also be available: for example, start Ollama and ensure its configured model is installed if `Agent_llm=OLLAMA`, or configure the required credentials for a hosted model.

From the project root, run:

```bash
python3.11 -m streamlit run src/ui.py
```

The terminal prints the address where Streamlit is serving the app, commonly `http://localhost:8501`. Open that address in a browser. From the Dispatch Console, you can:

- chat with the agent
- inspect tool inputs
- review raw outputs
- open the Security & Audit Logs view to review activity recorded in Step 8

Leave the terminal open while using the app; it runs the local web server. Press `Ctrl+C` in that terminal to stop it.

For a basic check, submit a question and confirm that the agent responds. If the audit table and permissions are configured, open Security & Audit Logs to review the recorded events.

---

# Step 10: Optional Linux VM deployment

The commands below outline one way to run the interface on a remote Ubuntu VM. Adapt the repository URL, credentials, network rules, and service configuration to your environment before using this for deployment.

```bash
sudo apt update && sudo apt install -y python3-pip python3-venv git
cd /home/ubuntu
git clone https://github.com/nimowhyca/cold-chain-logistics-FDE-Project.git
cd cold-chain-logistics-FDE-Project
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
streamlit run src/ui.py
```

Install the Microsoft SQL Server ODBC driver and unixODBC packages required by the Python database connector:

```bash
curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | sudo gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg
curl -fsSL https://packages.microsoft.com/config/ubuntu/$(lsb_release -rs)/prod.list | sudo tee /etc/apt/sources.list.d/mssql-release.list
sudo apt-get update
sudo ACCEPT_EULA=Y apt-get install -y msodbcsql18
sudo apt-get install -y unixodbc-dev
```

For unattended operation, configure and enable a `systemd` service to manage the Streamlit process.

---

# Troubleshooting

## The browser shows “This page isn’t working” on localhost:1433

SQL Server does not serve web pages. Use a SQL client such as Azure Data Studio to connect to this port.

## Docker container is not running

Check:

```bash
docker ps -a
```

Then look at logs:

```bash
docker logs legacy-mssql
```

## The AI cannot find Pinecone documents

Make sure:

- the Pinecone API key is present in `.env`
- the ingestion script has completed successfully
- the index name matches the environment settings

## The database denies access

Confirm that `setup_security_and_view.sql` completed successfully and created the agent login/user and its permissions.

## Apple Silicon / macOS pyodbc error: missing ODBC library

If you are on Apple Silicon and the Python script fails before creating the table with an error similar to:

```text
ImportError: dlopen(...pyodbc...): Library not loaded: /opt/homebrew/opt/unixodbc/lib/libodbc.2.dylib
```

the operating system may not be able to locate the unixODBC library required by `pyodbc`.

Fix it with:

```bash
brew install unixodbc
export DYLD_LIBRARY_PATH="$(brew --prefix unixodbc)/lib:$DYLD_LIBRARY_PATH"
```

Open a new terminal session so it receives the updated library path, then retry the import:

```bash
python3 scripts/ingest_legacy_data.py
```

Installing or exposing the host ODBC library is separate from running SQL Server in Docker; the container can be healthy while Python still cannot load its local driver dependency.

## Setup sequence recap

The setup proceeds through these stages:

1. database setup
2. legacy data import
3. SOP indexing
4. security configuration
5. agent testing
6. UI launch

Completing the required stages makes the data sources, agent workflow, and web interface available for local testing.
