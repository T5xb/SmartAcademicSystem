import os

from llama_index.core import Settings
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.llms.ollama import Ollama


def init_settings():
    base_url = os.getenv("OLLAMA_BASE_URL")
    if not base_url:
        raise RuntimeError("OLLAMA_BASE_URL is missing in environment variables")
    llm_model = os.getenv("MODEL") or "llama3.2:3b"
    embed_model = os.getenv("EMBEDDING_MODEL") or "nomic-embed-text"

    Settings.llm = Ollama(
        model=llm_model,
        base_url=base_url,
        request_timeout=120.0,
        # Cap the context window so the KV cache doesn't try to allocate
        # memory sized for the model's full (e.g. 128K) native context.
        # Tried raising this to 8192 to avoid multi-step "refine" synthesis;
        # it made output *more* incoherent (the model started mixing in
        # other languages), so keeping it at 4096 -- this model's coherence
        # degrades with more context, not less.
        context_window=4096,
    )
    Settings.embed_model = OllamaEmbedding(model_name=embed_model, base_url=base_url)

    # Default chunk_size (1024) was mixing unrelated content into one chunk
    # (e.g. a cover page + a decree + several definitions all in one 1200+
    # char block), which confused the small local LLM at answer time even
    # when the right fact was in context. Smaller, more focused chunks
    # retrieve and get used more accurately.
    Settings.chunk_size = 400
    Settings.chunk_overlap = 80
