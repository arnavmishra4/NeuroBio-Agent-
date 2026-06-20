from typing import TypedDict, List, Annotated
import operator

class AgentState(TypedDict):
    messages: Annotated[list, operator.add]
    task_id: str
    retry_count:int
    is_complete: bool