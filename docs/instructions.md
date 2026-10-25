# FDE Project Setup Guide

This guide documents the project setup process in the recommended order. Follow the steps below to configure the environment, load the data, and run the application.

## What this project does

This project lets you:

- load cold-chain fleet data into SQL Server
- index policy documents for compliance retrieval
- ask a chatbot questions about route conditions and potential cargo risks
- use an AI agent to combine telemetry, weather, and SOP guidance
- view the results in a Streamlit dashboard

---

# Step 1: Prepare your environment

Before you begin, make sure you have:

- Docker Desktop installed
- Python 3.12 installed
- Git installed
- access to a terminal
- a SQL client such as VS Code SQL extension or Azure Data Studio

Open a terminal in the project root and install Python dependencies:

```bash
pip install -r requirements.txt
```

If you do not have the required database driver installed, install it before running the project.

---

# Step 2: Start the Microsoft SQL Server container

The project uses a local Microsoft SQL Server container to simulate the enterprise data source.

## Option A: Local machine (macOS / Linux)

Use this if you are running Docker Desktop on your own computer.

```bash
docker run -e "ACCEPT_EULA=Y" -e "MSSQL_SA_PASSWORD=FdeEnterprisePass123!" \
  -p 1433:1433 \
  --name legacy-mssql \
  -d mcr.microsoft.com/mssql/server:2022-latest
```

## Option B: Windows

If you are on Windows and writing the command across multiple lines, use the caret style:

```powershell
docker run -e "ACCEPT_EULA=Y" -e "MSSQL_SA_PASSWORD=FdeEnterprisePass123!" ^
  -p 1433:1433 --name legacy-mssql ^
  -d mcr.microsoft.com/mssql/server:2022-latest
```

## Option C: EC2 / VM with persistent storage

Use this if you want your SQL data to survive container restarts:

```bash
docker run -v mssql_data:/var/opt/mssql \
  -e "ACCEPT_EULA=Y" \
  -e "MSSQL_SA_PASSWORD=FdeEnterprisePass123!" \
  -p 1433:1433 \
  --name legacy-mssql \
  -d mcr.microsoft.com/mssql/server:2022-latest
```

### Verify the container started

Run:

```bash
docker ps
```

You should see a container named `legacy-mssql` running.

---

# Step 3: Connect to the database

You can connect with the VS Code SQL extension or Azure Data Studio.

## Connection details

Use these settings:

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

After connecting, run this query to confirm the database is working:

```sql
SELECT COUNT(*) AS total_rows FROM dbo.TBL_SC_FLEET_HIST_RAW;
```

If this fails, the dataset has not been loaded yet. Continue to the next step.

---

# Step 4: Load the raw telemetry dataset

This project contains a raw CSV dataset that must be imported into SQL Server.

From the project root, run:

```bash
python3 scripts/ingest_legacy_data.py
```

What this script does:

- reads the CSV file from the data folder
- maps the raw fields into the legacy database schema
- inserts the rows into the table `dbo.TBL_SC_FLEET_HIST_RAW`

This is needed because the system expects a legacy enterprise-style table to exist before the AI layer can safely work with it.

---

# Step 5: Set up the compliance knowledge base

This step is very important because the AI system is not only looking at live fleet data. It also needs to follow the company’s rules and procedures.

## Why the SOP (Standard Operating Procedures ) is needed

The system is meant to help with cold-chain operations, where a small mistake can become a serious compliance issue. A vehicle may be running normally on paper, but the real question is:

- Is this temperature within the allowed range?
- Does this event count as a cold-chain incident?
- What should the dispatcher do next according to policy?
- Do we need to escalate this to a supervisor or compliance team?

Those questions are not answered by SQL data alone. SQL gives you the facts, such as current temperature, route risk, or delay probability. The SOP gives you the rules that explain what the facts mean and what action is required.

Without the SOP, the agent would be guessing. It might give a general answer, but it would not be grounded in the actual operating policy for the business.

In this project, the SOP documents are stored in the `data/policy` folder. They are used to teach the AI the compliance logic.

## What is Pinecone?

Pinecone is a cloud vector database. In simple terms, it stores text in a special format that makes it easy to search by meaning, not just by exact words.

For example, if someone asks:

> “What should we do when temperature exceeds the safe range?”

the system does not need to match the exact words “temperature exceeds the safe range.” It can search for similar content in the policy documents and retrieve the relevant SOP section.

This is called semantic search or vector search.

## Why Pinecone is used here

The project stores policy documents in Pinecone so the AI can:

- search the SOP by meaning
- find the most relevant policy section quickly
- ground its answer in actual operational rules
- respond with policy-aware, compliance-safe recommendations

This is useful because SOP documents are long and detailed. Pinecone helps the AI find the right chunk of text instead of reading the whole document manually every time.

## Important note for local models

This setup is using a local embedding model for the fallback path. That means the model must already be installed on the same machine where the Python script is running.

In other words, if you run `python3.11 scripts/ingest_sop_pinecone.py` on your laptop, then the model files need to be available on that laptop. If you try to run the script on a different machine or server without the model installed, the ingestion will fail or the app will not be able to create the vector embeddings correctly.

This is different from a cloud-based service, where the model is hosted remotely. In this local mode, the embedding model is downloaded and used directly on the device running the script.

## Create your Pinecone key

1. Go to https://app.pinecone.io/
2. Create or open an index/project
3. Copy your API key
4. Add it to your `.env` file

Your `.env` file should include values similar to:

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

## Run the SOP ingestion script

From the project root, run:

```bash
python scripts/ingest_sop_pinecone.py
```

What this script does:

- reads the policy files in the `data/policy` directory
- splits the policy text into smaller chunks
- converts each chunk into embeddings
- stores those embeddings in Pinecone
- makes them available for retrieval during agent conversations

Why this matters:

The AI can now answer questions like:

- “What are the compliance steps for an incident?”
- “What should an operator do if cargo temperature rises above threshold?”
- “Which SOP section covers a route delay with possible spoilage risk?”

instead of giving a generic answer based only on training data.

This is the step that connects operational data with business rules and compliance policy.

---

# Step 6: Create the secure SQL view for the agent

This step creates a clean, read-only view for the AI agent and blocks direct access to the messy raw table.

Open the SQL file:

```text
scripts/setup_security_and_view.sql
```

Then run it in SQL Server Management tools or the VS Code SQL editor.

This script creates:

- a schema called `FDE_VIEWS`
- a view called `FDE_VIEWS.VW_ACTIVE_FLEET`
- a restricted login/user called `USR_FDE_RO`
- explicit deny rules for the raw table

Why this matters:

The AI should only access clean, curated data, not the messy legacy table that contains the raw ingestion output.

## Validate the security layer

Connect with the agent profile and test these queries:

```sql
SELECT TOP 5 * FROM FDE_VIEWS.VW_ACTIVE_FLEET;
```

This should work.

```sql
SELECT TOP 5 * FROM dbo.TBL_SC_FLEET_HIST_RAW;
```

This should fail.

---

# Step 7: Test the core agent tools

This is the step where you check whether the system really works as an AI assistant instead of just having separate pieces installed.

The project has two main parts here:

- `agent_tools.py`: this file defines the tools the AI can use
- `orchestrator.py`: this file decides when to call those tools and how to combine the results

Think of it like this:

- the AI is the decision-maker
- the tools are the helpers
- the orchestrator is the manager in charge of calling the right helper at the right time

## What the tools do

The agent tools in this project are:

- `query_telemetry_db`: reads live fleet/temperature data from SQL Server
- `fetch_corridor_conditions`: checks weather and route conditions for a location
- `search_compliance_sop`: searches the SOP documents in Pinecone for the relevant policy rule

So when you ask a question, the model can gather facts from multiple sources and then answer more intelligently.

## Example of how it works

If you ask:

```text
Find any active shipments near Los Angeles (Latitude ~33.8, Longitude ~-118.1). Check the local weather there, and tell me if the current cargo temperature violates the SOP for fresh perishables.
```

the agent may do this:

1. query the SQL database for nearby active shipments
2. check the weather for that location
3. look up the relevant SOP rule from Pinecone
4. compare the temperature and conditions to the policy
5. answer with a final recommendation

This is the main idea behind the whole project: combining operational data + weather + compliance policy into one useful decision support agent.

## Run the files

From the project root, run:

```bash
python src/agent_tools.py
python src/orchestrator.py
```

If these run without errors, you have confirmed that the tools and the agent orchestration are connected correctly.

## Example prompts to test

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

If the agent answers with information from SQL, weather, and the SOP document, then Step 7 is working correctly.

---

# Step 8: Set up the audit log table

This step creates a place in SQL Server to record the agent's activity. An audit log is a history of what the application did while handling a request.

When the application runs, it can record information such as:

- which conversation session an event belongs to
- which part of the agent ran, such as the reasoner or a tool
- which tool was requested, such as SQL telemetry or SOP search
- the tool input, tool result, or final response text

The audit log is useful for reviewing how an answer was produced, troubleshooting failed requests, and understanding which data sources the agent used. It is separate from the fleet telemetry table: it records agent activity, not shipment data.

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

The `CREATE TABLE` statement creates the log table. The `GRANT INSERT` statement gives the restricted agent account permission to add log entries; it does not itself grant permissions to read, update, or delete those entries. Run this setup once; if the table already exists, do not run the `CREATE TABLE` statement again.

The Streamlit application writes audit entries to this table while requests are processed. The Security & Audit Logs view reads and displays the stored entries after an administrator authenticates.

**Data handling note:** the log can contain tool inputs and outputs and the model's final responses. These may include operational details or excerpts from retrieved records and SOPs. Treat the log as operational data and restrict access appropriately; never put passwords, API keys, or other secrets into prompts.

To verify the table was created, run this in the same database:

```sql
SELECT OBJECT_ID('FDE_VIEWS.AgentAuditLog', 'U') AS audit_table_id;
```

A non-`NULL` `audit_table_id` means SQL Server found the table.

---

# Step 9: Run the user interface

This step launches the project's Streamlit web application. The interface is the main place to send questions to the agent; it connects the chat screen to the orchestrator and its SQL, weather, and SOP tools.

Before starting it, confirm that SQL Server is running and that the setup steps for the data, Pinecone index, security view, and audit table have completed. The configured LLM must also be available: for example, start Ollama and ensure its configured model is installed if `Agent_llm=OLLAMA`, or configure the required credentials for a hosted model.

From the project root, run:

```bash
python3.11 -m streamlit run src/ui.py
```

Streamlit prints a local URL in the terminal, usually `http://localhost:8501`. Open that address in a browser. The Dispatch Console lets you:

- chat with the agent
- inspect tool inputs
- review raw outputs
- open the Security & Audit Logs view to review activity recorded in Step 8

Keep the terminal running while you use the application; it hosts the local web server. To stop the server, focus that terminal and press `Ctrl+C`.

To check that the interface is working, submit a question that uses one or more of the configured data sources and confirm that the agent displays a response. If audit logging is configured, inspect the Security & Audit Logs view to see the recorded activity.

---

# Step 10: Optional deployment on a Linux VM

The project also includes a deployment example for running the UI on a remote Linux machine.

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

Then install the required Microsoft SQL ODBC driver:

```bash
curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | sudo gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg
curl -fsSL https://packages.microsoft.com/config/ubuntu/$(lsb_release -rs)/prod.list | sudo tee /etc/apt/sources.list.d/mssql-release.list
sudo apt-get update
sudo ACCEPT_EULA=Y apt-get install -y msodbcsql18
sudo apt-get install -y unixodbc-dev
```

Finally, create a systemd service file to keep the Streamlit app running in the background.

---

# Common troubleshooting tips

## The browser shows “This page isn’t working” on localhost:1433

This is normal. SQL Server is not a web app. You must connect with a SQL client, not a browser.

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

Check that the security script ran successfully and the agent login was created.

## Apple Silicon / macOS pyodbc error: missing ODBC library

If you are on Apple Silicon and the Python script fails before creating the table with an error similar to:

```text
ImportError: dlopen(...pyodbc...): Library not loaded: /opt/homebrew/opt/unixodbc/lib/libodbc.2.dylib
```

then your system is missing the `unixodbc` library that `pyodbc` needs.

Fix it with:

```bash
brew install unixodbc
export DYLD_LIBRARY_PATH="$(brew --prefix unixodbc)/lib:$DYLD_LIBRARY_PATH"
```

Then reopen the terminal and rerun:

```bash
python3 scripts/ingest_legacy_data.py
```

This issue is common on Apple Silicon because the ODBC library is not installed by default, even when SQL Server is already running.

---

# Final note

If you follow the steps in order, you will move from:

1. database setup
2. legacy data import
3. SOP indexing
4. security configuration
5. agent testing
6. UI launch

to a working cold-chain logistics decision-support system.
