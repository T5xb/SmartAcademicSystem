import logging
import os
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
    return documents


def generate_index():
   
    from llama_index.core import StorageContext, VectorStoreIndex

    from src.index import (
        DATA_DIR,
        PGVECTOR_REAL_TABLE,
        count_indexed_chunks,
        get_vector_store,
        reset_vector_table,
    )
    from src.settings import init_settings

    load_dotenv("src/.env")
    
    init_settings(require_llm=False)

    logger.info(f"Loading documents from {DATA_DIR}")
    documents = _load_documents(DATA_DIR)
    logger.info(f"Loaded {len(documents)} document(s)")

   
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
