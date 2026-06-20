<div align="center">

# 🧬 NeuroBio Agent

### NeuroSight tells you *what*. This tells you *why* — and what to do next.

![Backbone](https://img.shields.io/badge/LLM-Gemini%202.5%20Flash-4285F4?style=for-the-badge)
![Framework](https://img.shields.io/badge/LangGraph-StateGraph-1C3C3C?style=for-the-badge)
![Tools](https://img.shields.io/badge/Live%20Tools-6-2ea44f?style=for-the-badge)
![Status](https://img.shields.io/badge/Status-Validated%20End--to--End-success?style=for-the-badge)

*The reasoning layer of [NeuroSight](#) — takes structured model outputs and turns them into a falsifiable biological hypothesis, grounded in live literature, with an explicit safety gate that knows when *not* to answer.*

</div>

---

## 🩺 The Problem This Solves

Every other model in NeuroSight produces a classification. M1 segments. M3 says "true progression" or "pseudoprogression." M5 says "GBM" or "healthy." None of them say *why* — what the underlying biological mechanism is, what the literature says about this specific pattern, or what a clinician should actually consider next. NeuroBio Agent sits on top of all of them and closes that gap: it takes the structured numeric output from M2/M3/M5, forms an explicit hypothesis, goes and checks that hypothesis against live PubMed, ClinicalTrials.gov, bioRxiv, and a curated internal corpus, and returns a revised, sourced, confidence-rated conclusion.

It is not a chatbot wrapped around the pipeline. It's a bounded reasoning loop with a hard iteration cap, a tool-failure-tolerant execution layer, and — the part worth being loudest about — **an explicit off-switch.** If the upstream routing payload says the case needs a human, the agent does not run at all. More on that below.

---

## 📊 At a Glance

| | |
|---|---|
| **Role** | Reasoning layer over NeuroSight's M2/M3/M5 outputs |
| **Orchestration** | LangGraph `StateGraph`, 2 nodes (`llm`, `tools`), conditional loop |
| **LLM backbone** | Gemini 2.5 Flash, tool-bound |
| **Tools available** | 6 (PubMed, ClinicalTrials.gov, bioRxiv, OMIM, DrugBank, internal FAISS RAG) |
| **Live by default** | 4 of 6 (OMIM and DrugBank require API keys not currently configured) |
| **Reasoning loop bound** | Hard cap of 3 LLM calls per case |
| **Input** | Structured JSON routing payload from upstream NeuroSight pipeline |
| **Output** | Hypothesis, confidence, ruled-out alternative, sources |
| **Validation** | Confirmed end-to-end against a real sample patient payload (NS-00421) |

---

## 🧠 What Makes This an Agent, Not a Pipeline

| Property | How it's actually implemented |
|---|---|
| **Forms an explicit, falsifiable hypothesis** | The system prompt requires a Step 1 hypothesis *before* any tool is called — so search results test the hypothesis rather than retroactively justify it |
| **Decides its own tool use** | `llm.bind_tools(all_tools)` — Gemini chooses which of the 6 tools to call, with what query, and how many times, with no hardcoded tool order |
| **Loops** | `llm → tools → llm` via LangGraph conditional edges, repeating until the model stops requesting tools |
| **Knows when to stop** | Two real conditions, not a learned convergence detector: the model naturally stops issuing tool calls once it has enough evidence, *or* a hard cap of 3 LLM iterations forces termination regardless — a safety net against runaway loops, not an open-ended search |
| **Survives tool failure** | Every tool call is wrapped in try/except inside `run_tools` — a single failed API call becomes a readable error message the LLM can route around, not a crashed run |
| **Final answer is sourced** | Step 3 of the prompt explicitly requires all sources alongside the revised hypothesis and confidence level |

---

## 🔁 Reasoning Loop

```
        ┌─────────────────────────────────────┐
        │   Entry: structured clinical prompt   │
        │   (M2 deltas + M3 class + M5 + Rx)    │
        └────────────────┬──────────────────────┘
                          ▼
                  ┌───────────────┐
            ┌────▶│      llm      │  Gemini 2.5 Flash, tool-bound
            │     └───────┬───────┘
            │             │
            │     tool_calls present?  ──No──▶  END (return final hypothesis)
            │             │ Yes
            │             ▼
            │     ┌───────────────┐
            └─────┤     tools     │  runs each requested tool, catches failures
                  └───────────────┘

  Hard stop: retry_count ≥ 3  →  END regardless of pending tool calls
```

This is the standard ReAct tool-calling pattern, deliberately bounded. Three LLM calls is enough to cover the prompt's own structure — initial hypothesis, evidence-gathering, revised conclusion — without the latency or cost risk of an unbounded agent loop.

---

## 🔧 The Six Tools

| Tool | Source | Status | What it actually does |
|---|---|---|---|
| `search_pubmed` | NCBI E-utilities | ✅ Live | Real keyword search (`esearch` → `efetch`), returns abstract text. Prompted to require short 2–5 keyword queries since PubMed's search requires exact term matches |
| `search_clinical_trials` | ClinicalTrials.gov API v2 | ✅ Live | Searches active/recruiting trials by condition, drug, or gene status |
| `search_biorxiv` | bioRxiv public API | ⚠️ Live, but date-range only | bioRxiv's API doesn't support full-text query search — this pulls recent preprints from a fixed date window and asks the model to scan for relevance, exactly as documented in the tool's own docstring |
| `search_omim` | OMIM | 🔒 Requires `OMIM_API_KEY` | Gene–disease association lookup. Degrades gracefully — returns an informative "not configured" message rather than failing, so the agent can reason around its absence |
| `search_drugbank` | DrugBank | 🔒 Requires `DRUGBANK_API_KEY` | Drug mechanism/interaction lookup. Same graceful-degradation pattern as OMIM |
| `query_agent_rag` | Internal FAISS index | ✅ Live | Curated, pre-vetted corpus (RANO criteria, Zetterberg cfDNA literature). Lazy-loaded singleton retriever (`sentence-transformers/all-MiniLM-L6-v2`, k=4) so the index loads once per process, not once per call |

Two of six tools are off by default until credentials are added — worth knowing going in, not discovering later. The four live tools (PubMed, ClinicalTrials.gov, bioRxiv, internal RAG) already give the agent real literature, real trials, and a curated clinical reference set to reason against.

---

## 📥 What Feeds the Agent

The agent doesn't see a raw MRI or a raw cfDNA file — it receives a structured routing payload assembled by the upstream NeuroSight pipeline, synthesizing every model's output into one prompt:

| Source | Fields |
|---|---|
| **M2** (Fisher-KPP PINN) | `delta_mu_d`, `delta_mu_r`, `delta_gamma`, `delta_t_days` — biophysical growth-rate change between scans |
| **M3** (progression classifier) | `progression_class`, `confidence`, `confidence_band`, `delta_pattern_flag` |
| **M5** (cfDNA / Pleiades) | `clinical_subtype`, `detection_confidence` |
| **Treatment context** | `known_mgmt_status`, `known_idh_status`, `current_regimen`, `days_since_rt_end`, `tmz_cycles_completed` |
| **Routing** | `agent_instructions` — explicit guidance injected by upstream pipeline logic |
| **Consensus** | `agent_instruction` — additional instruction injected only if upstream models agree (`consensus.fires`) |

That's genuine multi-modal synthesis: imaging-derived biophysics, a classifier's confidence-banded output, a liquid-biopsy result, and treatment history, fused into a single clinical reasoning prompt — not just one model's number handed to an LLM.

---

## 🛑 The Safety Gate

Before any reasoning happens, `run_neurobio()` checks one field:

```python
if not payload["routing"]["neurobio_agent_should_run"]:
    return "Agent halted: M3 escalated and no cfDNA data. Human review required."
```

If the upstream pipeline determines a case is ambiguous enough that the classifier escalated and there's no cfDNA cross-check available, **the agent doesn't run at all.** It doesn't produce a lower-confidence guess — it explicitly defers to a human. This is the single most important design decision in this repo. A clinical AI system that always produces an answer, even when it shouldn't, is a known failure mode in this space; one that knows its own evidentiary limits and says so is not.

---

## 📝 The Reasoning Prompt

The prompt structure mirrors actual differential-diagnosis methodology rather than a generic "summarize this" instruction:

> **Step 1** — Write your initial hypothesis based on the patient data above, before doing any research.
> **Step 2** — Use the search tools to find evidence for or against it. You decide what to search and how many times.
> **Step 3** — State your final hypothesis (revised if needed), confidence level, one alternative you considered and ruled out, and all sources.

Forcing the hypothesis to be written *before* tool access is the part that matters — it means the evidence-gathering step is genuinely testing a stated position rather than being used to retroactively construct support for whatever the model would have said anyway.

---

## 🔧 Engineering Notes

| Detail | Why it's there |
|---|---|
| `extract_content()` helper in `main.py` | Gemini returns message content as a list of dicts (`[{"type": "text", "text": ...}]`) rather than a plain string in some cases — this normalizes both formats so downstream code doesn't need to know which one it got |
| Skipping empty `AIMessage`s when extracting the final answer | A tool-calling turn produces an `AIMessage` with `tool_calls` but no text — `main.py` walks backward through the message history to find the last one that actually has content |
| Lazy-loaded FAISS retriever (`_get_agent_rag_retriever`) | Module-level singleton, loaded once on first call rather than once per tool invocation — meaningful cost at the embedding-model load step |
| Try/except around every individual tool call | One failed HTTP request (timeout, rate limit, malformed response) becomes a `ToolMessage` the LLM can read and reason around, instead of crashing the entire graph run |

---

## 🔗 Role in NeuroSight

In the full system's decision architecture, NeuroBio Agent is **Decision 6 of 7** — it runs after upstream routing has already resolved segmentation quality (M1), PINN convergence (M2), and classifier confidence (M3), and after RAG retrieval quality (M4) and consensus checking (Decision 7) have been evaluated. By the time a payload reaches this repo, the hard upstream decisions about *whether* the case is even reasoning-ready have already been made — this agent's job starts after that gate, not before it.

| Stage | Model | Role |
|---|---|---|
| M1 | Res-U-Net | Segments tumor sub-regions from MRI |
| M2 | Fisher-KPP PINN | Simulates patient-specific tumor growth |
| M3 | XGBoost + MLP | Classifies progression vs. pseudoprogression |
| M4 | RAG report generator | Produces structured clinical research brief |
| M5 | Pleiades / cfDNA transformer | Classifies glioma subtype from plasma cfDNA |
| **NeuroBio Agent** | **LangGraph + Gemini 2.5 Flash (this repo)** | **Reasons over M2/M3/M5 outputs, forms and tests a biological hypothesis, defers to a human when evidence is insufficient** |

---

## ⚠️ Honest Limitations

| # | Limitation | Detail |
|---|---|---|
| 1 | bioRxiv tool isn't true full-text search | bioRxiv's public API only supports date-range pulls, not query-based search — the agent gets recent preprints and has to judge relevance itself. Disclosed directly in the tool's own docstring, not a hidden gap |
| 2 | 2 of 6 tools require API keys not currently set | OMIM and DrugBank degrade gracefully but are inactive out of the box |
| 3 | No persistence across sessions | Each `agent.invoke()` call is a fresh, isolated state — there's no checkpointer on the compiled graph, so nothing carries over between patient runs despite this being part of the system's longer-term design intent |
| 4 | Hard 3-iteration cap | A genuinely complex case could need more than 3 LLM turns to fully resolve — the cap protects against runaway cost/latency but could in principle cut off a case mid-investigation |
| 5 | No automated grounding check | The prompt requires sources for every claim, but nothing programmatically verifies that the final hypothesis text is actually traceable to a real tool result — grounding is enforced by prompt instruction, not by a verification step |
| 6 | `is_complete` field unused | Declared in `AgentState` but never read or set anywhere in the current graph logic — vestigial |
| 7 | CLI only surfaces the final message | The full reasoning trace (every hypothesis, tool call, and tool result) lives in LangGraph's message state and is fully inspectable, but `main.py`'s default output only prints the last synthesized answer, not the intermediate steps |

---

## 📁 Repository Structure

```
.
├── config.py     # LLM client (Gemini 2.5 Flash) via langchain_google_genai
├── state.py      # AgentState TypedDict — messages, task_id, retry_count, is_complete
├── tools.py      # 6 tool definitions: PubMed, ClinicalTrials.gov, bioRxiv, OMIM, DrugBank, FAISS RAG
├── nodes.py      # call_llm, run_tools, should_continue — the graph's node logic
├── graph.py      # LangGraph StateGraph wiring: llm ⇄ tools, conditional routing
├── main.py       # run_neurobio() — loads payload, builds prompt, invokes graph, extracts answer
└── README.md
```

---

## 📚 References

- RANO (Response Assessment in Neuro-Oncology) criteria — clinical reference corpus for the internal RAG index.
- Zetterberg, H., et al. — cfDNA / liquid biopsy literature underlying the internal RAG corpus.
- LangGraph — graph-based agent orchestration framework.
- NCBI E-utilities, ClinicalTrials.gov API v2, bioRxiv API, OMIM, DrugBank — external tool data sources.

---

<div align="center">

[M1 — Segmentation](#) → [M2 — Growth PINN](#) → [M3 — Progression Classifier](#) → [M4 — RAG Reporting](#) → [M5 — cfDNA Classifier](#)

**reasoned over by NeuroBio Agent (this repo)**

</div>
