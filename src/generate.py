import logging
import os

from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()


def _load_documents(data_dir: str) -> list:
    """
    Load every document under data_dir.

    .txt and .pdf are loaded by hand instead of through
    SimpleDirectoryReader's defaults:
    - .txt: OCR'd files (see scripts/ocr_pdf.py) mark page boundaries as
      "--- Page N ---" text; splitting those into one Document per page
      here keeps a real page number in each chunk's metadata for citations.
    - .pdf: SimpleDirectoryReader's default PDFReader is pypdf-based, which
      garbles Arabic (RTL) text -- see src/pdf_loader.py for why. We
      extract with PyMuPDF instead, also split per page.

    Everything else (docx, ...) goes through SimpleDirectoryReader as usual.
    """
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
    return documents


def generate_index():
    """
    Index the documents in DATA_DIR into the persistent Chroma vector store.
    """
    import chromadb
    from llama_index.core import StorageContext, VectorStoreIndex
    from llama_index.vector_stores.chroma import ChromaVectorStore

    from src.index import CHROMA_COLLECTION, CHROMA_DIR, DATA_DIR
    from src.settings import init_settings

    load_dotenv()
    init_settings()

    logger.info(f"Loading documents from {DATA_DIR}")
    documents = _load_documents(DATA_DIR)
    logger.info(f"Loaded {len(documents)} document(s)")

    # Reset the collection so re-running `generate` doesn't accumulate
    # duplicate/stale chunks from a previous run.
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    try:
        client.delete_collection(CHROMA_COLLECTION)
    except Exception:
        pass
    collection = client.get_or_create_collection(CHROMA_COLLECTION)
    vector_store = ChromaVectorStore(chroma_collection=collection)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    logger.info("Creating new index")
    VectorStoreIndex.from_documents(
        documents,
        storage_context=storage_context,
        show_progress=True,
    )
    logger.info(
        f"Finished creating index in Chroma collection '{CHROMA_COLLECTION}' ({CHROMA_DIR})"
    )
