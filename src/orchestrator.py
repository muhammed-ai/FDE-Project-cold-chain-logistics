import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage, SystemMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.memory import MemorySaver

"""Connect the selected language model to the project's tools and run the chat loop."""

# ==========================================
# 1. SETUP & PATH RESOLUTION
# ==========================================
script_dir = Path(__file__).resolve().parent
project_root = script_dir.parents[0]

if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.agent_tools import query_telemetry_db, fetch_corridor_conditions, search_compliance_sop

load_dotenv(project_root / ".env")

class AgentState(TypedDict):
    # LangGraph passes this shared message history between the model and tool steps.
    messages: Annotated[list[BaseMessage], add_messages]

# ==========================================
# 2. FACTORY INITIALIZATION: AGENT REASONER LLM
# ==========================================

# This setting selects the chat/reasoning model. Embeddings are configured separately.
AGENT_LLM_SETTING = os.getenv("Agent_llm", "OLLAMA").strip().upper()

if AGENT_LLM_SETTING == "OPENAI":
    print("🤖 Brain Mode: Utilizing Cloud OpenAI Reasoner (gpt-4o)...")
    from langchain_openai import ChatOpenAI
    llm = ChatOpenAI(model="gpt-4o", temperature=0)

elif AGENT_LLM_SETTING == "DEEPSEEK":
    print("🐳 Brain Mode: Utilizing Flagship DeepSeek Cloud Reasoner (deepseek-v4-pro)...")
    from langchain_openai import ChatOpenAI
    
    # Fully updated to match 2026 DeepSeek API parameters and endpoint contracts
    llm = ChatOpenAI(
        model="deepseek-v4-flash",                           # deepseek-v4-flash, deepseek-v4-pro
        temperature=0,
        openai_api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url="https://api.deepseek.com",     # Fixed connection string url endpoint
        max_tokens=2048,                                   # Gives the deep reasoner plenty of output runway
        # extra_body={
        #     "thinking": {"type": "enabled"},              # Activates DeepSeek Deep-Thinking mode
        #     "reasoning_effort": "high"                     # Drives maximal reasoning depth for logic maps
        # }
    )

else:  # FALLBACK / DEFAULT RUNNER MODE
    print("🤗 Brain Mode: Local Fallback Activated. Binding Local Ollama (qwen2.5:7b)...")
    try:
        from langchain_ollama import ChatOllama
    except ImportError as exc:
        raise ImportError(
            "The installed LangChain version no longer includes the old Ollama import path. "
            "Install the supported package with: python3.11 -m pip install langchain-ollama"
        ) from exc
    llm = ChatOllama(model="qwen2.5:7b", temperature=0, num_predict=1024)

fde_tools = [query_telemetry_db, fetch_corridor_conditions, search_compliance_sop]
# Tool binding tells the model which Python functions are available during reasoning.
# This does not execute the tools by itself; the model returns a tool-call request,
# the ToolNode runs the matching function, and its result is sent back through the graph.
llm_with_tools = llm.bind_tools(fde_tools)

# ==========================================
# 3. GRAPH ARCHITECTURE ASSEMBLY
# ==========================================
def reasoning_node(state: AgentState):
    # The state is a shared message history. reasoning_node appends the model's
    # latest response, which can be text, a tool request, or another reasoning step.
    response = llm_with_tools.invoke(state["messages"])
    return {"messages": [response]}

print("⚙️ Compiling LangGraph FDE Orchestrator...")
# StateGraph defines the workflow as a small state machine. AgentState is the data
# type carried between its nodes, while add_messages controls how message lists merge.
graph_builder = StateGraph(AgentState)
graph_builder.add_node("reasoner", reasoning_node)
# ToolNode maps tool names to the Python functions in fde_tools and executes requests.
graph_builder.add_node("tools", ToolNode(fde_tools))

# A user turn follows this path:
#   START -> reasoner -> tool requested? -> tools -> reasoner -> final answer
# tools_condition examines the reasoner's latest message. It sends tool calls to the
# tools node and ends the turn when the model has enough information to answer.
graph_builder.add_edge(START, "reasoner")
graph_builder.add_conditional_edges("reasoner", tools_condition)
graph_builder.add_edge("tools", "reasoner")

# MemorySaver keeps conversations in memory for the lifetime of this process.
# The thread_id passed by the caller groups messages into a separate conversation.
# MemorySaver is not a database and does not persist histories after the process stops.

# compile() turns the graph definition into a runnable agent object used by both
# the terminal chat loop and the Streamlit UI.
fde_agent = graph_builder.compile(checkpointer=MemorySaver())

# ==========================================
# 4. CHAT LOOP TESTING PANEL
# ==========================================
if __name__ == "__main__":
    print("\n" + "="*55)
    print("🚀 FDE Supply Chain Orchestrator State Machine Online")
    print(f"   Configured Execution: [LLM: {AGENT_LLM_SETTING}] -> [Embeddings: {os.getenv('Embeddings_model', 'LOCAL')}] ")
    print("="*55 + "\n")
    
    # system_prompt.txt defines the agent's role, required tool order, and output format.
    # It acts as a system instruction for the terminal-test conversation rather than as a
    # Python function. The model sees its text before processing the dispatcher's question.
    prompt_path = project_root / "src" / "prompts" / "system_prompt.txt"
    try:
        with open(prompt_path, "r", encoding="utf-8") as f:
            system_instructions = f.read()
    except FileNotFoundError:
        # This fallback keeps the terminal usable if the prompt file is missing, but it
        # omits the project's intended role, operational sequence, and response template.
        print(f"Error: Could not find {prompt_path}")
        system_instructions = "You are a helpful AI assistant." # Basic fallback

    # SystemMessage marks this content as high-level instructions for the model. It
    # establishes role and output constraints; it is separate from HumanMessage input.
    system_prompt = SystemMessage(content=system_instructions)
    
    # Reusing one thread_id preserves this terminal chat's history between user turns.
    # Different IDs create different conversations and therefore different message context.
    thread_config = {"configurable": {"thread_id": "production_test_1"}}

    # Invoking the graph with only the system message initializes the thread and allows
    # MemorySaver to establish the conversation state before the chat loop begins.
    fde_agent.invoke({"messages": [system_prompt]}, config=thread_config)
    
    while True:
        user_input = input("\nDispatcher > ")
        if user_input.lower() in ['exit', 'quit']:
            break
            
        # A dispatcher prompt is converted to a human/user message. The graph appends it
        # to the saved history, so later turns can use earlier context in the same thread.
        events = fde_agent.stream({"messages": [("user", user_input)]}, config=thread_config, stream_mode="updates")
        for event in events:
            for node_name, node_state in event.items():
                if node_name == "tools":
                    print("   [System] 🔄 Retrieving external data elements via ToolNode...")
                elif node_name == "reasoner":
                    latest_msg = node_state["messages"][-1]
                    if latest_msg.content:
                        print(f"\n🤗 FDE Agent:\n{latest_msg.content}")