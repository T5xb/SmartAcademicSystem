"""
Vector store access: Supabase Postgres + pgvector.

Used by src/generate.py to build the index and by the app to query it.
See ARCHITECTURE.md §4.3-4.4 for why Postgres over Chroma, why the
session pooler is mandatory here, and why there is no ANN index.
"""

import logging
import os
from urllib.parse import urlsplit, urlunsplit

from llama_index.core import VectorStoreIndex
from llama_index.vector_stores.postgres import PGVectorStore
from sqlalchemy import create_engine, text

logger = logging.getLogger("uvicorn")

# Where source documents (PDFs, docx, txt...) live.
DATA_DIR = os.environ.get("DATA_DIR", "docs")

PGVECTOR_TABLE = os.environ.get("PGVECTOR_TABLE", "academic_advising")

EMBED_DIM = int(os.environ.get("EMBED_DIM", "1024"))

PGVECTOR_REAL_TABLE = f"data_{PGVECTOR_TABLE}"


def _require_db_url() -> str:
    url = os.getenv("SUPABASE_DB_URL")
    if not url:
        raise RuntimeError(
            "SUPABASE_DB_URL is missing in src/.env. Copy the Session "
            "pooler connection string from Supabase -> Connect -> Direct "
            "connection -> Session pooler."
        )
    return url


def sqlalchemy_urls(db_url: str | None = None) -> tuple[str, str]:
 
    parts = urlsplit(db_url or _require_db_url())
    netloc, path = parts.netloc, parts.path
    sync = urlunsplit(("postgresql+psycopg2", netloc, path, parts.query, ""))
    async_ = urlunsplit(
        ("postgresql+asyncpg", netloc, path, "prepared_statement_cache_size=0", "")
    )
    return sync, async_


def get_vector_store(perform_setup: bool = True) -> PGVectorStore:
  
    sync_url, async_url = sqlalchemy_urls()
    return PGVectorStore.from_params(
        connection_string=sync_url,
        async_connection_string=async_url,
        table_name=PGVECTOR_TABLE,
        embed_dim=EMBED_DIM,
        perform_setup=perform_setup,
       
        use_jsonb=True,
        
    )


def count_indexed_chunks() -> int:
    """Rows in the vector table, or 0 if it doesn't exist yet."""
    sync_url, _ = sqlalchemy_urls()
    engine = create_engine(sync_url)
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text(f'SELECT count(*) FROM "{PGVECTOR_REAL_TABLE}"')
            )
            return int(result.scalar() or 0)
    except Exception:
        
        logger.info(
            f"Vector table '{PGVECTOR_REAL_TABLE}' not readable yet -- "
            "treating as empty."
        )
        return 0
    finally:
        engine.dispose()


def reset_vector_table() -> None:
    """Drop the vector table if it exists, so generate.py can start fresh."""
    sync_url, _ = sqlalchemy_urls()
    engine = create_engine(sync_url)
    try:
        with engine.begin() as conn:
            conn.execute(text(f'DROP TABLE IF EXISTS "{PGVECTOR_REAL_TABLE}"'))
        logger.info(f"Dropped existing vector table '{PGVECTOR_REAL_TABLE}'")
    finally:
        engine.dispose()


def get_index():
    """The queryable index, or None if nothing has been indexed yet."""
    if count_indexed_chunks() == 0:
        return None
    logger.info(f"Loading index from Postgres table '{PGVECTOR_REAL_TABLE}'...")
    index = VectorStoreIndex.from_vector_store(get_vector_store(perform_setup=False))
    logger.info("Finished loading index from Postgres")
    return index
