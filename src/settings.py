"""
Model configuration: which LLM answers, and which model embeds text.

Everything here is driven by src/.env so no code change is needed to swap
provider or model. See ARCHITECTURE.md §4.1-4.2 and §4.7 for why each
value is what it is.
"""

import os

from llama_index.core import Settings
from llama_index.core.llms import LLM
from llama_index.embeddings.ollama import OllamaEmbedding

# Real context window of the default hosted model, from Groq's live model
# list (qwen/qwen3.8-27b). Stated explicitly because LlamaIndex falls back
# to 3900 for model ids it doesn't recognise, which would split our
# retrieved chunks across needless extra LLM calls.
HOSTED_CONTEXT_WINDOW = 131042

# Groq's free tier rejects a request whose *expected* output exceeds its
# per-minute budget; unset, that expectation is the model's full 16384.
# A grounded answer runs ~300 tokens.
MAX_ANSWER_TOKENS = 512


def _build_llm() -> LLM:
    """
    Build the answer-generation LLM chosen by LLM_PROVIDER.

    "hosted" (default when LLM_API_KEY is set): any OpenAI-compatible
        endpoint, via OpenAILike so the provider is swappable by env var.
    "ollama": fully-local fallback, and the baseline scripts/bench.py
        compares against.
    """
    provider = (os.getenv("LLM_PROVIDER") or "").strip().lower()
    if not provider:
        # Degrade to local answers rather than crashing if the key is gone.
        provider = "hosted" if os.getenv("LLM_API_KEY") else "ollama"

    # "groq"/"openai_like" accepted so an older .env keeps working.
    if provider in ("hosted", "openai_like", "groq"):
        from llama_index.llms.openai_like import OpenAILike

        api_key = os.getenv("LLM_API_KEY")
        if not api_key:
            raise RuntimeError(
                "LLM_PROVIDER=hosted but LLM_API_KEY is missing in src/.env. "
                "For Groq, get a free key at https://console.groq.com/keys, "
                "or set LLM_PROVIDER=ollama to run fully offline."
            )
        return OpenAILike(
            model=os.getenv("LLM_MODEL") or "qwen/qwen3.8-27b",
            api_base=os.getenv("LLM_API_BASE") or "https://api.groq.com/openai/v1",
            api_key=api_key,
            # OpenAILike defaults to False, which would use the legacy
            # /completions route that Groq does not serve.
            is_chat_model=True,
            # Low but non-zero: answers must stay faithful to the sources.
            temperature=0.1,
            timeout=90.0,
            max_tokens=MAX_ANSWER_TOKENS,
            # Ride out a rate-limit 429 instead of failing a live question.
            max_retries=3,
            context_window=int(
                os.getenv("LLM_CONTEXT_WINDOW") or HOSTED_CONTEXT_WINDOW
            ),
        )

    if provider == "ollama":
        from llama_index.llms.ollama import Ollama

        base_url = os.getenv("OLLAMA_BASE_URL")
        if not base_url:
            raise RuntimeError("OLLAMA_BASE_URL is missing in environment variables")
        return Ollama(
            model=os.getenv("MODEL") or "llama3.2:3b",
            base_url=base_url,
            request_timeout=180.0,
            # Deliberately small: this model's coherence degrades with more
            # context (at 8192 it started mixing languages into Arabic),
            # and a smaller window keeps the KV cache from being sized for
            # the model's full native context.
            context_window=4096,
        )

    raise RuntimeError(
        f"Unknown LLM_PROVIDER={provider!r} (expected 'hosted' or 'ollama')"
    )


def _build_embed_model():
    """
    Build the embedding model chosen by EMBEDDING_PROVIDER.

    Default is local Ollama running bge-m3 (multilingual — this is what
    makes the right Arabic article rank first). Note embeddings are
    computed per *query* as well as at index time, so the local option
    means a deployed instance still needs a reachable Ollama.

    Switching to hosted requires re-running `generate` and matching
    EMBED_DIM to the new model's vector width.
    """
    provider = (os.getenv("EMBEDDING_PROVIDER") or "ollama").strip().lower()

    if provider == "ollama":
        return OllamaEmbedding(
            model_name=os.getenv("EMBEDDING_MODEL") or "bge-m3",
            base_url=os.getenv("OLLAMA_BASE_URL") or "http://127.0.0.1:11434",
        )

    if provider == "openai":
        from llama_index.embeddings.openai import OpenAIEmbedding

        return OpenAIEmbedding(
            model=os.getenv("EMBEDDING_MODEL") or "text-embedding-3-small",
            api_key=os.getenv("OPENAI_API_KEY"),
        )

    raise RuntimeError(
        f"Unknown EMBEDDING_PROVIDER={provider!r} (expected 'ollama' or 'openai')"
    )


def init_settings(require_llm: bool = True):
    """
    Configure the global LlamaIndex Settings.

    require_llm=False skips the generation LLM: indexing only needs
    embeddings, so it must not fail because the LLM key isn't set yet.
    """
    if require_llm:
        Settings.llm = _build_llm()
    Settings.embed_model = _build_embed_model()

    # The default 1024 merged unrelated content into a single chunk (e.g. a
    # cover page plus a decree plus several definitions), which confused
    # the model even when the right fact was in context. The overlap keeps
    # an article from being cut mid-sentence.
    Settings.chunk_size = 400
    Settings.chunk_overlap = 80
