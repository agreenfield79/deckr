# embeddings_service.py — watsonx embeddings (stub)
# Stub — activate in post-MVP when semantic search is wired
# Endpoint: POST {WATSONX_URL}/ml/v1/text/embeddings?version=2024-05-31
# Model: ibm/slate-125m-english-rtrvr
#
# Planned use cases:
#   1. Workspace semantic search — embed all markdown files, search by meaning not keyword
#   2. Smart context injection — retrieve only the most relevant document chunks per AI prompt
#   3. Missing items detection — compare uploaded doc embeddings to expected doc type embeddings


def embed_texts(texts: list[str]) -> list[list[float]]:
    raise NotImplementedError("Embeddings service not yet activated")


def embed_workspace_files() -> dict[str, list[float]]:
    raise NotImplementedError("Embeddings service not yet activated")


def find_relevant_files(query: str, top_k: int = 5) -> list[str]:
    raise NotImplementedError("Embeddings service not yet activated")
