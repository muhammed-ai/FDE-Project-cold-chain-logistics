"""
Purpose:
    Load the raw cold-chain telemetry CSV into a legacy Microsoft SQL Server table.

Why this is needed:
    The AI agent is not allowed to query the messy raw table directly. This script creates
    the legacy data source that the later security-view layer can sanitize and expose safely.
"""

from pathlib import Path
import pandas as pd
import urllib
import os
from sqlalchemy import create_engine
from dotenv import load_dotenv

# Find the project folder relative to this script so paths work regardless of
# which directory the terminal is currently using.
script_dir = Path(__file__).resolve().parent
project_root = script_dir.parents[0]

load_dotenv(project_root / ".env")

data_path = project_root / "data" / "raw" / "dynamic_supply_chain_logistics_dataset.csv"

db_host = os.getenv("SQL_SERVER_HOST", "localhost")
db_port = os.getenv("SQL_SERVER_PORT", "1433")
db_user = os.getenv("SQL_ADMIN_USER")
db_password = os.getenv("SQL_ADMIN_PASSWORD")

# 1. Read the source CSV that contains the fleet telemetry records.
print(f"Loading CSV from {data_path}...")
df = pd.read_csv(data_path)

# 2. Rename selected readable CSV columns to mimic the older field names used
# by a legacy enterprise system.
legacy_mapping = {
    'timestamp': 'TS_UTC',
    'vehicle_gps_latitude': 'V_LAT',
    'vehicle_gps_longitude': 'V_LON',
    'iot_temperature': 'IOT_TEMP_VAL_C',
    'cargo_condition_status': 'CGO_COND_CD',
    'risk_classification': 'RISK_CLS_TXT',
    'delay_probability': 'DELAY_PROB_DEC',
    'port_congestion_level': 'PRT_CNG_LVL',
    'route_risk_level': 'RT_RSK_IDX'
}

# Keep only the fields needed by this demo, then apply the legacy column names.
df_legacy = df[list(legacy_mapping.keys())].rename(columns=legacy_mapping)

# Add a fake ingestion flag to make it look like an automated legacy system
df_legacy['SYS_INGEST_FLAG'] = 'Y'

# 3. Connect to the local SQL Server using administrator credentials from .env.
print("Connecting to legacy MSSQL Database...")
# Use the pyodbc driver. (Ensure you have ODBC Driver 17 or 18 for SQL Server installed on your OS)
connection_string = (
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER={db_host},{db_port};"
        f"DATABASE=master;"
        f"UID={db_user};"
        f"PWD={db_password};"
        f"Encrypt=no;"
        f"TrustServerCertificate=yes;"
    )

params = urllib.parse.quote_plus(connection_string)

engine = create_engine(f"mssql+pyodbc:///?odbc_connect={params}")

# 4. Replace the demo raw table with this CSV's rows. Later setup creates a
# separate safe view for the agent to read instead of exposing this raw table.
table_name = 'TBL_SC_FLEET_HIST_RAW'
print(f"Ingesting into {table_name}. This may take a minute...")
df_legacy.to_sql(table_name, engine, if_exists='replace', index=False, schema='dbo')

print("✅ Legacy data ingestion complete!")