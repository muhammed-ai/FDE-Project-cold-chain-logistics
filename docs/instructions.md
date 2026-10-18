# FDE Project Setup Guide

This guide is written for beginners and follows the project in the correct order. If you are setting this up for the first time, follow the steps below in sequence.

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

Now run the agent scripts in the project root or from the source folder.

```bash
python src/agent_tools.py
python src/orchestrator.py
```

These are the core AI components:

- `agent_tools.py`: defines the telemetry, weather, and SOP tools
- `orchestrator.py`: connects the tools to the LLM and decides when to call them

You can test it with prompts like:

## Example prompt 1

```text
Find any active shipments near Los Angeles (Latitude ~33.8, Longitude ~-118.1). Check the local weather there, and tell me if the current cargo temperature violates the SOP for fresh perishables.
```

## Example prompt 2

```text
I'm a new dispatcher on the night shift. Can you quickly explain the difference between a Tier 1 and Tier 2 escalation?
```

---

# Step 8: Set up the audit log table

This creates a small table where the app writes execution traces for the AI agent.

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

Why this is needed:

It lets the system track which tool was triggered, what data was passed in, and what the model returned.

---

# Step 9: Run the user interface

Start the Streamlit dashboard:

```bash
streamlit run src/ui.py
```

This opens the cold-chain dispatch console where you can:

- chat with the agent
- inspect tool inputs
- review raw outputs
- open security and audit views

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
