import logging
import os
import re
import unicodedata

from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()


def _load_documents(data_dir: str) -> list:
    
    from llama_index.core import Document
    from llama_index.core.readers import SimpleDirectoryReader

    from src.ocr_loader import is_ocr_page_marked, load_ocr_text_as_documents
    from src.pdf_loader import load_pdf_as_documents

    documents = []
    for root, _, files in os.walk(data_dir):
        for fname in files:
            fpath = os.path.join(root, fname)
            lower = fname.lower()
            if lower.endswith(".txt"):
                with open(fpath, encoding="utf-8") as f:
                    text = f.read()
                if is_ocr_page_marked(text):
                    documents.extend(load_ocr_text_as_documents(fpath, text))
                else:
                    documents.append(Document(text=text, metadata={"file_name": fpath}))
            elif lower.endswith(".pdf"):
                documents.extend(load_pdf_as_documents(fpath))

    reader = SimpleDirectoryReader(data_dir, recursive=True, exclude=["*.txt", "*.pdf"])
    documents.extend(reader.load_data())

    # Several PDFs (the study plans especially) store Arabic as presentation
    # forms (e.g. "ﻣﻘﺪﻣﺔ" instead of "مقدمة"). They look right but are different
    # code points, so the embedding never matched a student's question and
    # the model read them poorly. NFKC folds them back to normal letters.
    for doc in documents:
        text = doc.get_content()
        normalized = unicodedata.normalize("NFKC", text)
        if normalized != text:
            doc.set_content(normalized)
    return _split_faq(documents)


_FAQ_FILE_RE = re.compile(r"الأسئلة_الشائعة|[\\/]faqs[\\/]")
_QUESTION_LINE_RE = re.compile(r"^[^|#\n]{4,300}[؟?]$")


def _split_faq(documents: list) -> list:
    """
    One document per question and its answer in the FAQ files.

    Chunking them by size cut a question off from its answer and glued the
    answer to the end of an unrelated chunk ("متى يحصل الطالب على الإنذار
    الأكاديمي؟" ended a chunk about transfers), so it ranked too low to be
    retrieved (RAGAS context recall 0 in test TC-06).
    """
    from llama_index.core import Document

    out = []
    for doc in documents:
        if not _FAQ_FILE_RE.search(doc.metadata.get("file_name", "") or doc.metadata.get("file_path", "")):
            out.append(doc)
            continue
        blocks, current = [], []
        for line in doc.get_content().splitlines():
            if _QUESTION_LINE_RE.match(line.strip()) and current:
                blocks.append(current)
                current = []
            current.append(line)
        if current:
            blocks.append(current)
        for block in blocks:
            text = "\n".join(block).strip()
            if text:
                out.append(Document(text=text, metadata=dict(doc.metadata)))
    return out


def _check_embedding(expected_dim: int) -> None:
    """Embed one short text, so a model that is down or the wrong width fails here."""
    from llama_index.core import Settings

    try:
        vector = Settings.embed_model.get_text_embedding("اختبار")
    except Exception as e:
        raise RuntimeError(
            "The embedding model did not answer (is Ollama running?); "
            "the index was left unchanged."
        ) from e
    if len(vector) != expected_dim:
        raise RuntimeError(
            f"The embedding model returns {len(vector)} dimensions but EMBED_DIM is "
            f"{expected_dim}; the index was left unchanged."
        )


def generate_index():
    # Before importing src.index: it reads PGVECTOR_TABLE at import time, and
    # without the .env value it builds a table the server never reads.
    load_dotenv("src/.env")

    from llama_index.core import StorageContext, VectorStoreIndex

    from src.index import (
        DATA_DIR,
        EMBED_DIM,
        PGVECTOR_REAL_TABLE,
        count_indexed_chunks,
        get_vector_store,
        reset_vector_table,
    )
    from src.settings import init_settings

    init_settings(require_llm=False)

    logger.info(f"Loading documents from {DATA_DIR}")
    documents = _load_documents(DATA_DIR)
    logger.info(f"Loaded {len(documents)} document(s)")

    # Checked before the old table is dropped: if there is nothing to index,
    # or the embedding model is down, the index the server uses stays as it is.
    if not documents:
        raise RuntimeError(f"No documents found in {DATA_DIR}; the index was left unchanged.")
    _check_embedding(EMBED_DIM)

    reset_vector_table()
    storage_context = StorageContext.from_defaults(
        vector_store=get_vector_store(perform_setup=True)
    )

    logger.info("Creating new index")
    VectorStoreIndex.from_documents(
        documents,
        storage_context=storage_context,
        show_progress=True,
    )
    logger.info(
        f"Finished creating index in Postgres table '{PGVECTOR_REAL_TABLE}' "
        f"({count_indexed_chunks()} chunk(s))"
    )
