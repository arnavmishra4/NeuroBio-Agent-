import json
import sys
from langchain_core.messages import HumanMessage, AIMessage
from graph import agent


def extract_content(message) -> str:
    """Handle both plain string and Gemini's list-of-dicts content format."""
    if isinstance(message.content, str):
        return message.content
    if isinstance(message.content, list):
        return "\n".join(
            part.get("text", "")
            for part in message.content
            if isinstance(part, dict) and part.get("type") == "text"
        )
    return str(message.content)


def run_neurobio(payload_path: str) -> str:

    # 1. Load payload
    with open(payload_path, "r") as f:
        payload = json.load(f)

    # 2. Check if agent should even run
    if not payload["routing"]["neurobio_agent_should_run"]:
        return "Agent halted: M3 escalated and no cfDNA data. Human review required."

    # 3. Pull routing instructions
    instructions = "\n".join(payload["routing"]["agent_instructions"])
    if payload.get("consensus") and payload["consensus"].get("fires"):
        instructions += "\n" + payload["consensus"]["agent_instruction"]

    # 4. Unpack payload fields
    m2        = payload.get("m2") or {}
    m3        = payload.get("m3") or {}
    m5        = payload.get("m5") or {}
    deltas    = m2.get("deltas") or {}
    treatment = payload.get("treatment") or {}

    # 5. Build prompt
    prompt = f"""
You are a neuro-oncology research assistant analyzing a GBM patient scan.

PATIENT DATA:
- Progression class (tentative): {m3.get("progression_class")}
- M3 confidence: {m3.get("confidence")} (band: {m3.get("confidence_band")})
- Delta pattern flag: {m3.get("delta_pattern_flag")}
- Biophysical deltas: delta_mu_d={deltas.get("delta_mu_d")},
  delta_mu_r={deltas.get("delta_mu_r")},
  delta_gamma={deltas.get("delta_gamma")},
  over {deltas.get("delta_t_days")} days
- cfDNA result: {m5.get("clinical_subtype")}
  (confidence {m5.get("detection_confidence")})
- MGMT status: {treatment.get("known_mgmt_status")}
- IDH status:  {treatment.get("known_idh_status")}
- Regimen: {treatment.get("current_regimen")},
  {treatment.get("days_since_rt_end")} days post-RT,
  {treatment.get("tmz_cycles_completed")} TMZ cycles completed

AGENT INSTRUCTIONS FROM NEUROSIGHT:
{instructions}

TASK:
Step 1 — Write your initial hypothesis based on the patient data above,
          before doing any research.
Step 2 — Use the search tools to find evidence for or against it.
          You decide what to search and how many times.
Step 3 — State your final hypothesis (revised if needed), confidence level,
          one alternative you considered and ruled out, and all sources.
"""

    # 6. Build initial state and invoke
    initial_state = {
        "messages": [HumanMessage(content=prompt)],
        "task_id": payload.get("patient_id", "unknown"),
        "retry_count": 0,
        "is_complete": False,
    }

    result = agent.invoke(initial_state)

    # 7. Find the last AIMessage with actual text content
    final = None
    for m in reversed(result["messages"]):
        if isinstance(m, AIMessage):
            text = extract_content(m)
            if text.strip():        # skip empty AIMessages
                final = m
                break

    return extract_content(final) if final else "No AI response found."


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else r"NeuroAgent\neurosight_to_neurobio_payload.json"
    output = run_neurobio(path)

    patient_id = json.load(open(path)).get("patient_id", "unknown")
    print("=" * 70)
    print(f"PATIENT: {patient_id}")
    print("=" * 70)
    print(output)