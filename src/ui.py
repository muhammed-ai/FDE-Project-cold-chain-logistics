import os
import sys
import uuid
import json
import urllib
from pathlib import Path
from dotenv import load_dotenv
import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from langchain_core.messages import HumanMessage, ToolMessage

# Streamlit interface for chatting with the agent and reviewing its audit trail.

# ==========================================
# 1. IMMEDIATE PATH & ENVIRONMENT RESOLUTION
# ==========================================
# Resolve paths from this file's location, not the terminal's current folder.
script_dir = Path(__file__).resolve().parent  # points to src/
project_root = script_dir.parent              # climbs to project root

if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

load_dotenv(project_root / ".env")

# Import the graph assembled by the orchestrator; the UI sends user messages to it.
from src.orchestrator import fde_agent

# ==========================================
# 2. SQL CREDENTIALS MAPPING FROM .ENV
# ==========================================
# The chat agent uses a restricted SQL account; secrets are read from .env rather
# than being written into the source code.
db_host = os.getenv("SQL_SERVER_HOST", "localhost")
db_port = os.getenv("SQL_SERVER_PORT", "1433")
db_user = os.getenv("SQL_AGENT_USER", "USR_FDE_RO")
db_password = os.getenv("SQL_AGENT_PASSWORD")

# Create a reusable SQLAlchemy engine for audit writes. SQLAlchemy manages the
# database connection through the installed SQL Server ODBC driver.
connection_string = (
    f"DRIVER={{ODBC Driver 18 for SQL Server}};"
    f"SERVER={db_host},{db_port};"
    f"DATABASE=master;"
    f"UID={db_user};"
    f"PWD={db_password};"
    f"Encrypt=no;"
    f"TrustServerCertificate=yes;"
)

log_params = urllib.parse.quote_plus(connection_string)

log_engine = create_engine(f"mssql+pyodbc:///?odbc_connect={log_params}")

def write_audit_log(session_id, node_name, tool_name, content):
    """Silently writes agent execution traces to the SQL audit table using agent permissions."""
    # Audit failures are reported but do not stop the user-facing chat response.
    try:
        # Parameterized SQL keeps values separate from the SQL command text.
        with log_engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO FDE_VIEWS.AgentAuditLog (SessionID, NodeExecuted, ToolName, Content)
                VALUES (:session_id, :node_name, :tool_name, :content)
            """), {
                "session_id": session_id,
                "node_name": node_name,
                "tool_name": tool_name,
                "content": content
            })
            conn.commit()
    except Exception as e:
        print(f"Audit Log Failed (Silent): {e}")

# ==========================================
# 3. PAGE CONFIGURATION & ENTERPRISE THEME
# ==========================================
# Set the browser page title, icon, layout, and initial sidebar state before
# rendering Streamlit widgets.
st.set_page_config(
    page_title="FDE Supply Chain Dispatch Console",
    page_icon="🧊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Give the operations console its own visual identity while keeping Streamlit's
# widgets and all existing interactions intact.
st.markdown("""
<style>
    .stApp {
        --paper: light-dark(#f2f1e9, #111816);
        --surface: light-dark(#fffefa, #1b2420);
        --ink: light-dark(#1c2a25, #e8eee7);
        --muted: light-dark(#63716a, #aab8ad);
        --line: light-dark(#d9ded5, #35443b);
        --pine: light-dark(#244d3b, #193b2c);
        --mint: light-dark(#dcead8, #26382d);
        --citrus: light-dark(#d6e764, #e0ed83);
        --coral: light-dark(#d9674c, #f08a70);
        --sidebar: light-dark(#e6e9df, #18211d);
        --hero-ink: light-dark(#f5f4e9, #f1f4eb);
        --hero-muted: light-dark(#d1ddd0, #c2d0c3);
        --surface-soft: color-mix(in srgb, var(--surface) 80%, transparent);
        --grid-line: color-mix(in srgb, var(--pine) 4%, transparent);
        background-color: var(--paper);
        background-image: linear-gradient(var(--grid-line) 1px, transparent 1px),
                          linear-gradient(90deg, var(--grid-line) 1px, transparent 1px);
        background-size: 32px 32px;
        color: var(--ink);
    }
    [data-testid="stHeader"] { background: color-mix(in srgb, var(--paper) 92%, transparent); }
    [data-testid="stMainBlockContainer"], .block-container {
        max-width: 1280px;
        padding-top: 3.4rem !important;
        padding-bottom: 5rem !important;
    }
    h1, h2, h3 { color: var(--ink); letter-spacing: 0 !important; }
    h1 { font-family: "Avenir Next", "Trebuchet MS", sans-serif; font-weight: 700; }
    p, li, label, [data-testid="stCaptionContainer"] { color: var(--muted); }

    [data-testid="stSidebar"] {
        background: var(--sidebar);
        border-right: 1px solid var(--line);
    }
    [data-testid="stSidebar"] > div:first-child { padding-top: 1.5rem; }
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h1 {
        font-size: 1.05rem;
        line-height: 1.1;
    }
    [data-testid="stSidebar"] [data-testid="stRadio"] label { color: var(--ink); }
    [data-testid="stSidebar"] [data-testid="stButton"] button {
        border: 1px solid var(--line);
        color: var(--pine);
        background: transparent;
    }
    [data-testid="stSidebar"] [data-testid="stButton"] button:hover {
        border-color: var(--coral);
        color: var(--coral);
    }

    .brand-copy { padding-top: .35rem; color: var(--pine); }
    .brand-name { font-size: .9rem; font-weight: 800; letter-spacing: .04em; }
    .brand-sub { margin-top: .12rem; color: var(--muted); font-size: .65rem; text-transform: uppercase; }

    .console-hero {
        display: flex;
        align-items: flex-end;
        justify-content: space-between;
        gap: 2rem;
        padding: 1.8rem 2rem 1.7rem;
        margin: 0 0 1.2rem;
        border-radius: 5px;
        background: var(--pine);
        color: var(--hero-ink);
        box-shadow: 0 14px 34px rgba(28, 42, 37, .12);
    }
    .console-hero h1 {
        margin: .35rem 0 .25rem;
        color: var(--hero-ink);
        font-family: "Avenir Next", "Trebuchet MS", sans-serif;
        font-size: clamp(2rem, 4vw, 3.3rem);
        line-height: 1.04;
    }
    .console-hero p { max-width: 42rem; margin: .55rem 0 0; color: var(--hero-muted); }
    .hero-kicker, .hero-index {
        color: var(--citrus);
        font-size: .7rem;
        font-weight: 800;
        letter-spacing: .12em;
        text-transform: uppercase;
    }
    .hero-index { align-self: flex-start; white-space: nowrap; }

    .service-strip {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: .7rem;
        margin: 0 0 1.6rem;
    }
    .service-tile {
        display: flex;
        justify-content: space-between;
        gap: .7rem;
        padding: .9rem 1rem;
        border: 1px solid var(--line);
        border-radius: 4px;
        background: var(--surface-soft);
    }
    .service-label { color: var(--muted); font-size: .66rem; font-weight: 800; letter-spacing: .1em; }
    .service-value { margin-top: .25rem; color: var(--ink); font-size: .92rem; font-weight: 700; }
    .service-index { color: var(--coral); font-size: .72rem; font-weight: 800; }

    [data-testid="stChatMessage"] {
        border: 1px solid var(--line);
        border-radius: 5px;
        background: var(--surface);
        box-shadow: 0 5px 16px rgba(28, 42, 37, .035);
        color: var(--ink);
    }
    [data-testid="stChatMessage"] p { color: var(--ink); }
    [data-testid="stChatInput"] textarea {
        border-color: var(--line);
        border-radius: 5px;
        background: var(--surface);
        color: var(--ink);
    }
    [data-testid="stChatInput"] textarea:focus { border-color: var(--pine); }
    [data-testid="stBottom"],
    [data-testid="stBottom"] > div,
    [data-testid="stBottomBlockContainer"],
    .stChatFloatingInputContainer {
        background: var(--paper) !important;
    }
    [data-testid="stChatInput"] { background: var(--paper); }
    [data-testid="stChatInput"] button {
        border-radius: 4px;
        background: var(--pine);
        color: var(--hero-ink);
    }
    [data-testid="stExpander"] {
        border-color: var(--line);
        border-radius: 4px;
        background: var(--surface-soft);
    }
    [data-testid="stStatusWidget"] {
        border-color: var(--line);
        border-radius: 4px;
        background: var(--mint);
    }
    [data-testid="stForm"] {
        border: 1px solid var(--line);
        border-radius: 5px;
        background: var(--surface);
    }
    [data-testid="stDataFrame"] {
        border: 1px solid var(--line);
        border-radius: 4px;
    }
    .stMarkdown code { background-color: var(--mint) !important; color: var(--ink) !important; }

</style>
""", unsafe_allow_html=True)

# ==========================================
# 4. MULTI-USER STATE & THREAD MANAGEMENT
# ==========================================
# Streamlit reruns this file after interactions. Keep each conversation's visible
# messages with its own LangGraph thread ID so histories can be switched safely.
if "conversations" not in st.session_state:
    initial_thread_id = st.session_state.get("thread_id", str(uuid.uuid4()))
    initial_messages = st.session_state.get("ui_messages", [])
    st.session_state.conversations = {
        initial_thread_id: {"label": "Chat 1", "messages": initial_messages}
    }
    st.session_state.history_counter = 1
    st.session_state.thread_id = initial_thread_id

if st.session_state.thread_id not in st.session_state.conversations:
    st.session_state.thread_id = next(iter(st.session_state.conversations))

if "history_counter" not in st.session_state:
    st.session_state.history_counter = len(st.session_state.conversations)

# Rename labels from older app sessions after the terminology changes.
for chat_number, conversation in enumerate(st.session_state.conversations.values(), start=1):
    conversation["label"] = f"Chat {chat_number}"

# ==========================================
# 5. SIDEBAR NAVIGATION & METADATA
# ==========================================
# The sidebar shows app navigation, lets a user switch between saved histories,
# and provides actions for starting or clearing a conversation.
with st.sidebar:
    logo_column, brand_column = st.columns([0.85, 2.4])
    with logo_column:
        st.image("https://cdn-icons-png.flaticon.com/512/2830/2830305.png", width=52)
    with brand_column:
        st.markdown("""
        <div class="brand-copy">
            <div class="brand-name">COLDCHAIN DISPATCH</div>
            <div class="brand-sub">Cold-chain intelligence</div>
        </div>
        """, unsafe_allow_html=True)
    
    app_mode = st.radio("System Mode", ["🧊 Dispatch Console", "🛡️ Security & Audit Logs"])
    
    st.markdown("---")
    history_ids = list(st.session_state.conversations)
    selected_thread_id = st.selectbox(
        "Chat history",
        options=history_ids,
        index=history_ids.index(st.session_state.thread_id),
        format_func=lambda history_id: st.session_state.conversations[history_id]["label"],
    )
    if selected_thread_id != st.session_state.thread_id:
        st.session_state.thread_id = selected_thread_id
        st.rerun()

    st.caption(f"Session Token: `{st.session_state.thread_id[:8]}...`")
    st.markdown(f"**Reasoning Architecture:** `{os.getenv('Agent_llm', 'DEEPSEEK')}`")
    
    st.markdown("---")
    if st.button("＋ New chat", use_container_width=True):
        # Keep existing conversations and create a fresh, independently remembered thread.
        st.session_state.history_counter += 1
        new_thread_id = str(uuid.uuid4())
        st.session_state.conversations[new_thread_id] = {
            "label": f"Chat {st.session_state.history_counter}",
            "messages": [],
        }
        st.session_state.thread_id = new_thread_id
        st.rerun()

    if st.button("Clear current chat", use_container_width=True):
        # Remove only the selected conversation from this browser session, then
        # create a fresh thread so LangGraph cannot reuse its previous context.
        st.session_state.conversations.pop(st.session_state.thread_id, None)
        st.session_state.history_counter += 1
        new_thread_id = str(uuid.uuid4())
        st.session_state.conversations[new_thread_id] = {
            "label": f"Chat {st.session_state.history_counter}",
            "messages": [],
        }
        st.session_state.thread_id = new_thread_id
        st.rerun()

thread_config = {"configurable": {"thread_id": st.session_state.thread_id}}
active_messages = st.session_state.conversations[st.session_state.thread_id]["messages"]

# ==========================================
# 6. VIEW ROUTING (DISPATCH VS AUDIT)
# ==========================================

if app_mode == "🧊 Dispatch Console":
    # ------------------------------------------
    # TAB 1: CHAT UI & AGENT EXECUTION
    # ------------------------------------------
    st.markdown("""
    <section class="console-hero">
        <div>
            <div class="hero-kicker">Dispatch intelligence / Cold chain</div>
            <h1>Keep every<br>shipment in range.</h1>
            <p>Ask about fleet telemetry, corridor conditions, and handling procedures in one operational workspace.</p>
        </div>
        <div class="hero-index">Operations desk&nbsp; / &nbsp;01</div>
    </section>
    <section class="service-strip">
        <div class="service-tile"><div><div class="service-label">FLEET SIGNAL</div><div class="service-value">SQL Server</div></div><div class="service-index">01</div></div>
        <div class="service-tile"><div><div class="service-label">POLICY MEMORY</div><div class="service-value">SOP retrieval</div></div><div class="service-index">02</div></div>
        <div class="service-tile"><div><div class="service-label">MODEL ROUTING</div><div class="service-value">""" + os.getenv('Agent_llm', 'OLLAMA').upper() + """</div></div><div class="service-index">03</div></div>
    </section>
    """, unsafe_allow_html=True)

    # Redraw earlier turns each time Streamlit reruns the page. Saved traces make
    # tool requests and results inspectable after the response has completed.
    for entry in active_messages:
        with st.chat_message(entry["role"], avatar="👤" if entry["role"] == "user" else "🤖"):
            if "traces" in entry:
                for trace in entry["traces"]:
                    if trace["type"] == "tool_input":
                        st.markdown(f"**⚡ Intent Recognized:** `{trace['name']}`")
                        with st.expander(f"📥 View Generated Input ({trace['name']})", expanded=False):
                            st.json(trace["args"])
                    elif trace["type"] == "tool_output":
                        with st.expander(f"📤 View Raw Output ({trace['name']})", expanded=False):
                            st.code(trace["content"], language="text")
            st.markdown(entry["content"])

    if user_input := st.chat_input("Message ColdChain Dispatch about fleet, routes, or compliance..."):
        # Save and display the new user turn before asking the agent to process it.
        active_messages.append({"role": "user", "content": user_input})
        with st.chat_message("user", avatar="👤"):
            st.markdown(user_input)

        with st.chat_message("assistant", avatar="🤖"):
            # Keep the final answer and current tool trace separate while this
            # request runs; they are saved into the conversation afterward.
            final_response = ""
            current_traces = [] 
            
            with st.status("🧠 Initializing Core Reasoner Node...", expanded=True) as status:
                # Stream graph events so the interface can display each tool request,
                # tool result, and final model response as they happen.
                events = fde_agent.stream(
                    {"messages": [HumanMessage(content=user_input)]}, 
                    config=thread_config,
                    stream_mode="updates"
                )
                
                for event in events:
                    for node_name, node_state in event.items():
                        
                        if node_name == "reasoner":
                            latest_msg = node_state["messages"][-1]
                            
                            # The model asks for a tool by returning its name and arguments.
                            if hasattr(latest_msg, "tool_calls") and latest_msg.tool_calls:
                                status.update(label="🧠 Agent generated tool parameters...")
                                for tool_call in latest_msg.tool_calls:
                                    st.markdown(f"**⚡ Intent Recognized:** `{tool_call['name']}`")
                                    with st.expander(f"📥 View Generated Input ({tool_call['name']})", expanded=False):
                                        st.json(tool_call['args'])
                                    
                                    current_traces.append({
                                        "type": "tool_input",
                                        "name": tool_call['name'],
                                        "args": tool_call['args']
                                    })
                                    
                                    write_audit_log(
                                        session_id=st.session_state.thread_id,
                                        node_name="reasoner",
                                        tool_name=tool_call['name'],
                                        content=json.dumps(tool_call['args'])
                                    )
                            
                            # A message with content is displayed as the assistant's answer.
                            if latest_msg.content:
                                final_response = latest_msg.content
                                status.update(label="📝 Generating Operational Resolution Report...")
                                
                                write_audit_log(
                                    session_id=st.session_state.thread_id,
                                    node_name="reasoner_final",
                                    tool_name="LLM Text Synthesis",
                                    content=final_response
                                )
                                
                        elif node_name == "tools":
                            # ToolNode events contain the outputs returned by SQL,
                            # weather, or SOP search tools.
                            status.update(label="🔧 Executing Enterprise Subsystem Tools...")
                            for msg in node_state.get("messages", []):
                                if isinstance(msg, ToolMessage):
                                    with st.expander(f"📤 View Raw Output ({msg.name})", expanded=False):
                                        st.code(msg.content, language="text")
                                        
                                    current_traces.append({
                                        "type": "tool_output",
                                        "name": msg.name,
                                        "content": msg.content
                                    })
                                    
                                    write_audit_log(
                                        session_id=st.session_state.thread_id,
                                        node_name="tools",
                                        tool_name=msg.name,
                                        content=msg.content
                                    )
                
                status.update(label="Incident Matrix Evaluation Complete", state="complete", expanded=False)
                
            # Render and save a completed answer. If the graph produced no answer,
            # show a fallback message instead of leaving the assistant area blank.
            if final_response:
                st.markdown(final_response)
                active_messages.append({
                    "role": "assistant",
                    "content": final_response,
                    "traces": current_traces
                })
            else:
                error_fallback = "⚠️ Execution Timeout: System engine encountered an unresolved processing edge case."
                st.error(error_fallback)


elif app_mode == "🛡️ Security & Audit Logs":
    # ------------------------------------------
    # TAB 2: AUDIT LOG VIEWER (REQUIRES ADMIN CREDENTIALS FROM .ENV OR INPUT)
    # ------------------------------------------
    st.markdown("""
    <section class="console-hero">
        <div>
            <div class="hero-kicker">Governance / Event history</div>
            <h1>Audit trail</h1>
            <p>Review recorded agent actions and responses for this dispatch workspace.</p>
        </div>
        <div class="hero-index">Security desk&nbsp; / &nbsp;02</div>
    </section>
    """, unsafe_allow_html=True)
    
    st.markdown("### Database Authorization Gate")
    st.markdown("Enter high-privilege administrative credentials (defined in `.env` as `SQL_ADMIN_USER`) to query audit logs.")
    
    # Streamlit forms submit these fields together when the administrator clicks
    # the button, avoiding a database query on every keystroke.
    with st.form("admin_auth_form"):
        col1, col2 = st.columns(2)
        with col1:
            input_user = st.text_input("Admin Username", value=os.getenv("SQL_ADMIN_USER", ""))
        with col2:
            input_pass = st.text_input("Admin Password", type="password", value="")
            
        submit_admin = st.form_submit_button("Authenticate & Load Logs", use_container_width=True)

    if submit_admin:
        # The audit viewer requires admin credentials; chat uses the restricted account.
        expected_admin_user = os.getenv("SQL_ADMIN_USER")
        expected_admin_pass = os.getenv("SQL_ADMIN_PASSWORD")
        
        if input_user == expected_admin_user and input_pass == expected_admin_pass:
            try:
                # Build a separate connection with admin credentials because the
                # restricted chat account is not intended to read audit records.
                admin_params = urllib.parse.quote_plus(
                    "DRIVER={ODBC Driver 18 for SQL Server};"
                    f"SERVER={db_host},{db_port};"
                    "DATABASE=master;"
                    f"UID={input_user};"
                    f"PWD={input_pass};"
                    "Encrypt=no;"
                    "TrustServerCertificate=yes;"
                )
                admin_engine = create_engine(f"mssql+pyodbc:///?odbc_connect={admin_params}")
                
                with admin_engine.connect() as conn:
                    # Show newest audit events first so recent agent activity is easiest to inspect.
                    query = """
                        SELECT LogID, Timestamp, SessionID, NodeExecuted, ToolName, Content 
                        FROM FDE_VIEWS.AgentAuditLog 
                        ORDER BY Timestamp DESC
                    """
                    df = pd.read_sql(query, conn)
                
                st.success("✅ Authenticated successfully as Admin.")
                
                if not df.empty:
                    # Present the query result as a sortable table in the browser.
                    st.dataframe(
                        df,
                        column_config={
                            "LogID": st.column_config.NumberColumn("ID", format="%d"),
                            "Timestamp": st.column_config.DatetimeColumn("Execution Time", format="DD/MM/YYYY-h:mm a"),
                            "SessionID": "Session Token",
                            "NodeExecuted": "Graph Node",
                            "ToolName": "Tool Triggered",
                            "Content": "Raw Payload Data"
                        },
                        hide_index=True,
                        use_container_width=True,
                        height=600
                    )
                else:
                    st.info("No audit logs found in the database. Run a query in the Dispatch Console first.")
                    
            except Exception as e:
                st.error(f"Database Query Failed: {e}")
        else:
            st.error("❌ Invalid Administrator Credentials.")