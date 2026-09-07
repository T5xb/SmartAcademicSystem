import logging
import os

import chromadb
from llama_index.core import VectorStoreIndex
from llama_index.vector_stores.chroma import ChromaVectorStore

logger = logging.getLogger("uvicorn")

# Where source documents (PDFs, docx, txt...) live. Shared by the indexer
# (src/generate.py) and the server (for browsing raw files).
DATA_DIR = os.environ.get("DATA_DIR", "docs")

# Persistent on-disk ChromaDB store for the vector index.
CHROMA_DIR = os.environ.get("CHROMA_DIR", "chroma_db")
CHROMA_COLLECTION = os.environ.get("CHROMA_COLLECTION", "academic_advising")


def get_chroma_collection():
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    return client.get_or_create_collection(CHROMA_COLLECTION)


def get_index():
    collection = get_chroma_collection()
    if collection.count() == 0:
        return None
    logger.info(f"Loading index from Chroma collection '{CHROMA_COLLECTION}' ({CHROMA_DIR})...")
    vector_store = ChromaVectorStore(chroma_collection=collection)
    index = VectorStoreIndex.from_vector_store(vector_store)
    logger.info("Finished loading index from Chroma")
    return index
