import requests
from langchain_core.tools import tool


# ─────────────────────────────────────────────────────────────────────
# 1. PubMed — primary literature search
# ─────────────────────────────────────────────────────────────────────
@tool
def search_pubmed(query: str) -> str:
    """Search PubMed for peer-reviewed papers. 
    IMPORTANT: Use short 2-5 keyword queries only (e.g. 'MGMT GBM TMZ resistance', 
    'pseudoprogression GBM IDH-wildtype', 'cfDNA glioma liquid biopsy').
    Do NOT use long sentences or phrases — PubMed requires every word to match.
    You can call this multiple times with different short queries."""

    search_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {
        "db": "pubmed",
        "term": query,        # short keywords only
        "retmax": 5,
        "retmode": "json",
        "sort": "relevance",
        # removed "field": "tiab" — not a valid esearch param
    }
    r = requests.get(search_url, params=params, timeout=15)
    ids = r.json()["esearchresult"]["idlist"]

    if not ids:
        return f"No PubMed results found for '{query}'. Try a shorter query with 2-4 keywords."

    fetch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    params = {
        "db": "pubmed",
        "id": ",".join(ids),
        "rettype": "abstract",
        "retmode": "text",
    }
    r = requests.get(fetch_url, params=params, timeout=15)
    return r.text[:3000]


# ─────────────────────────────────────────────────────────────────────
# 2. ClinicalTrials.gov — recruiting/relevant trials
# ─────────────────────────────────────────────────────────────────────
@tool
def search_clinical_trials(query: str) -> str:
    """Search ClinicalTrials.gov for active or recruiting trials related to
    a condition, drug, gene status, or treatment combination. Use this to
    find trials a patient might be eligible for, or to see what treatment
    approaches are currently under investigation."""

    url = "https://clinicaltrials.gov/api/v2/studies"
    params = {
        "query.term": query,
        "pageSize": 5,
        "fields": "NCTId,BriefTitle,OverallStatus,Condition,InterventionName,BriefSummary",
    }
    r = requests.get(url, params=params, timeout=15)
    data = r.json()
    studies = data.get("studies", [])

    if not studies:
        return f"No clinical trials found for '{query}'."

    out = []
    for s in studies:
        proto = s.get("protocolSection", {})
        ident = proto.get("identificationModule", {})
        status = proto.get("statusModule", {})
        out.append(
            f"NCT ID: {ident.get('nctId')}\n"
            f"Title: {ident.get('briefTitle')}\n"
            f"Status: {status.get('overallStatus')}\n"
        )

    return "\n".join(out)[:3000]


# ─────────────────────────────────────────────────────────────────────
# 3. bioRxiv — latest preprints
# ─────────────────────────────────────────────────────────────────────
@tool
def search_biorxiv(query: str) -> str:
    """Search bioRxiv for recent preprints on a biological mechanism or
    topic. Use this when you want the most recent, not-yet-peer-reviewed
    research — useful for cutting-edge mechanisms that may not yet be in
    PubMed. Note: bioRxiv's API is date-range based rather than full-text
    search, so this returns recent preprints that you can scan for
    relevance to the query."""

    url = "https://api.biorxiv.org/details/biorxiv/2024-01-01/2025-12-31/0"
    r = requests.get(url, timeout=15)
    data = r.json()
    collection = data.get("collection", [])

    if not collection:
        return f"No bioRxiv results retrieved (query context: '{query}')."

    out = []
    for paper in collection[:5]:
        out.append(
            f"Title: {paper.get('title')}\n"
            f"Date: {paper.get('date')}\n"
            f"Abstract: {paper.get('abstract', '')[:300]}\n"
        )

    return "\n".join(out)[:3000]


# ─────────────────────────────────────────────────────────────────────
# 4. OMIM — gene <-> disease associations
# ─────────────────────────────────────────────────────────────────────
@tool
def search_omim(gene_or_disease: str) -> str:
    """Search OMIM (Online Mendelian Inheritance in Man) for gene-disease
    associations. Use this when you need to understand the genetic basis
    or known disease associations of a specific gene (e.g. MGMT, EGFR,
    IDH1) or condition. Requires an OMIM API key (set OMIM_API_KEY)."""

    import os
    api_key = os.environ.get("OMIM_API_KEY", "")
    if not api_key:
        return (
            "OMIM API key not configured. Set OMIM_API_KEY environment "
            "variable to enable this tool. Skipping OMIM search for "
            f"'{gene_or_disease}'."
        )

    url = "https://api.omim.org/api/entry/search"
    params = {
        "search": gene_or_disease,
        "limit": 5,
        "format": "json",
        "apiKey": api_key,
    }
    r = requests.get(url, params=params, timeout=15)
    data = r.json()

    entries = data.get("omim", {}).get("searchResponse", {}).get("entryList", [])
    if not entries:
        return f"No OMIM results found for '{gene_or_disease}'."

    out = []
    for e in entries:
        entry = e.get("entry", {})
        out.append(
            f"MIM Number: {entry.get('mimNumber')}\n"
            f"Title: {entry.get('titles', {}).get('preferredTitle')}\n"
        )

    return "\n".join(out)[:3000]


# ─────────────────────────────────────────────────────────────────────
# 5. DrugBank — drug mechanisms / interactions
# ─────────────────────────────────────────────────────────────────────
@tool
def search_drugbank(drug_name: str) -> str:
    """Look up a drug's mechanism of action, target, and known interactions
    via DrugBank. Use this when the hypothesis involves a specific drug
    (e.g. Temozolomide) and you need its pharmacological mechanism.
    Requires a DrugBank API key (set DRUGBANK_API_KEY)."""

    import os
    api_key = os.environ.get("DRUGBANK_API_KEY", "")
    if not api_key:
        return (
            "DrugBank API key not configured. Set DRUGBANK_API_KEY "
            "environment variable to enable this tool. Skipping DrugBank "
            f"search for '{drug_name}'."
        )

    url = "https://api.drugbank.com/v1/drug_interactions"
    headers = {"Authorization": api_key}
    params = {"q": drug_name}
    r = requests.get(url, headers=headers, params=params, timeout=15)

    if r.status_code != 200:
        return f"DrugBank lookup failed for '{drug_name}' (status {r.status_code})."

    return r.text[:3000]


# ─────────────────────────────────────────────────────────────────────
# 6. Internal FAISS RAG — RANO, Zetterberg, curated GBM papers
#    (Agent RAG index — built separately, path provided below)
# ─────────────────────────────────────────────────────────────────────

# NOTE: Set this to the path of your pre-built Agent RAG FAISS index.
AGENT_RAG_INDEX_PATH = "NeuroAgent\NeuroBio_faiss_index"

_agent_rag_retriever = None


def _get_agent_rag_retriever():
    """Lazy-load the FAISS retriever so it's only loaded once, on first use."""
    global _agent_rag_retriever
    if _agent_rag_retriever is None:
        from langchain_community.vectorstores import FAISS
        from langchain_huggingface import HuggingFaceEmbeddings
        # Swap embedding model below for whatever was used to BUILD the index.
        embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
        vectorstore = FAISS.load_local(
            AGENT_RAG_INDEX_PATH,
            embeddings,
            allow_dangerous_deserialization=True,
        )
        _agent_rag_retriever = vectorstore.as_retriever(search_kwargs={"k": 4})
    return _agent_rag_retriever


@tool
def query_agent_rag(query: str) -> str:
    """Search the curated internal research library (RANO criteria,
    Zetterberg cfDNA papers, and other pre-vetted GBM literature) via
    FAISS retrieval. Use this for grounded, pre-vetted reference material
    in addition to live PubMed/bioRxiv search."""

    retriever = _get_agent_rag_retriever()
    docs = retriever.invoke(query)

    if not docs:
        return f"No results found in Agent RAG index for '{query}'."

    out = []
    for d in docs:
        source = d.metadata.get("source", "unknown")
        out.append(f"[Source: {source}]\n{d.page_content[:600]}")

    return "\n\n".join(out)[:3000]


# ─────────────────────────────────────────────────────────────────────
# Tool registry — imported by nodes.py for bind_tools()
# ─────────────────────────────────────────────────────────────────────
all_tools = [
    search_pubmed,
    search_clinical_trials,
    search_biorxiv,
    search_omim,
    search_drugbank,
    query_agent_rag,
]