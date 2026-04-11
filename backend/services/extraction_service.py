# extraction_service.py — watsonx text extraction (stub)
# Stub — set ENABLE_EXTRACTION=true to activate
# Endpoint: POST {WATSONX_URL}/ml/v1/text/extractions?version=2023-10-25
# Handles: PDFs with tables (financial statements, tax returns, rent rolls)
#
# Pipeline:
#   Upload PDF -> save binary -> POST /ml/v1/text/extractions (async)
#     -> poll for completion -> store {filename}.extracted.json
#     -> AI action prompts call get_extracted_text() instead of raw binary
import os


def extract_document(file_path: str) -> str | None:
    """
    Submits file to watsonx text extraction API.
    Polls for completion, stores result as {file_path}.extracted.json.
    Returns path to extracted JSON, or None if extraction disabled.
    """
    if not os.getenv("ENABLE_EXTRACTION", "false").lower() == "true":
        return None
    raise NotImplementedError("Extraction service stub — activate ENABLE_EXTRACTION=true")


def get_extracted_text(file_path: str) -> str | None:
    """
    Reads {file_path}.extracted.json and returns plain text if it exists.
    Used by context assembler to prefer extracted content over raw binary.
    """
    extracted_path = file_path + ".extracted.json"
    if os.path.exists(extracted_path):
        pass
    return None
