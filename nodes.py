from langchain_core.messages import ToolMessage
from config import llm
from tools import all_tools


llm_with_tools = llm.bind_tools(all_tools)
tools_map = {t.name : t for t in all_tools}

max_iterations = 3 

def call_llm(state):
    response = llm_with_tools.invoke(state["messages"])
    return {
        "messages":[response],
        "retry_count": state["retry_count"]+1,
    }

def run_tools(state):
    last = state["messages"][-1]
    results = []  # must be a plain list

    for tool_call in last.tool_calls:
        fn = tools_map[tool_call["name"]]
        try:
            result = fn.invoke(tool_call["args"])
        except Exception as e:
            result = f"Tool '{tool_call['name']}' failed: {e}"

        results.append(
            ToolMessage(content=str(result), tool_call_id=tool_call["id"])
        )

    return {"messages": results}  # return the list, operator.add appends it


def should_continue(state):
    last = state["messages"][-1]
    if state['retry_count'] >= max_iterations:
        return "end"
    
    if getattr(last,"tool_calls",None):
        return "tools"
    
    return "end"