from langgraph.graph import StateGraph, END
from state import AgentState
from nodes import call_llm, run_tools, should_continue

graph = StateGraph(AgentState)

graph.add_node("llm", call_llm)
graph.add_node("tools", run_tools)

graph.set_entry_point("llm")

graph.add_conditional_edges(
    "llm",
    should_continue,
    {
        "tools": "tools",
        "end": END,
    },
)

graph.add_edge("tools", "llm")
agent = graph.compile()