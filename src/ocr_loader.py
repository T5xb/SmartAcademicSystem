"""
Loader for OCR'd text files produced by scripts/ocr_pdf.py.

Those files mark page boundaries as plain text ("--- Page N ---"), which a
generic text reader would just treat as content. This splits such a file
into one Document per page, with page_label set in metadata -- the same
metadata key llama-index's native PDFReader uses -- so retrieved chunks
can be cited with a real page number instead of just a document name.

Any file not in this format (docx, native PDFs, plain .txt without page
markers) is untouched; those go through SimpleDirectoryReader as usual,
which already attaches file_name (and, for native PDFs, page_label) itself.
"""

import re

from llama_index.core import Document

PAGE_SPLIT = re.compile(r"^--- Page (\d+) ---\s*$", re.MULTILINE)


def is_ocr_page_marked(text: str) -> bool:
    return bool(PAGE_SPLIT.search(text))


def load_ocr_text_as_documents(file_path: str, text: str) -> list[Document]:
    """Split OCR'd text with '--- Page N ---' markers into per-page Documents."""
    parts = PAGE_SPLIT.split(text)
    # re.split with a capturing group returns
    # [preamble, page_num_1, page_text_1, page_num_2, page_text_2, ...]
    preamble = parts[0].strip()
    documents = []
    if preamble:
        # Front-matter before the first page marker (e.g. our "partial
        # excerpt" disclaimer) -- keep it, but without a page number.
        documents.append(Document(text=preamble, metadata={"file_name": file_path}))

    for i in range(1, len(parts), 2):
        page_num = parts[i]
        page_text = parts[i + 1].strip()
        if not page_text:
            continue
        documents.append(
            Document(
                text=page_text,
                metadata={"file_name": file_path, "page_label": page_num},
            )
        )
    return documents
