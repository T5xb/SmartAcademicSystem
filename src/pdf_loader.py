"""
PDF text extraction via PyMuPDF, used instead of llama-index's default
PDFReader (which is backed by pypdf).

pypdf extracts PDF text in the order runs appear in the file's content
stream, without applying Unicode BIDI reordering. For Arabic (right-to-
left) PDFs this often comes out visually scrambled -- individual words
readable, but their order, and sometimes digit/word groupings, wrong.
PyMuPDF extracts Arabic in correct reading order, so we use it directly
instead.

One Document per page (page_label set in metadata), matching the
convention src/ocr_loader.py uses for OCR'd text -- both feed the same
downstream citation logic (src/citation.py).
"""

import logging

import fitz  # pymupdf
from llama_index.core import Document

logger = logging.getLogger("uvicorn")

# A page with fewer real characters than this almost certainly has no
# extractable text layer (i.e. it's a scanned image), not that its actual
# content is this short -- skip it rather than index near-nothing.
MIN_CHARS_PER_PAGE = 20


def load_pdf_as_documents(file_path: str) -> list[Document]:
    documents = []
    doc = fitz.open(file_path)
    for i, page in enumerate(doc):
        text = page.get_text().strip()
        if len(text) < MIN_CHARS_PER_PAGE:
            logger.warning(
                f"{file_path} page {i + 1}: only {len(text)} char(s) extracted -- "
                "likely a scanned page with no text layer; run scripts/ocr_pdf.py "
                "on it separately and add the OCR'd .txt file instead."
            )
            continue
        documents.append(
            Document(text=text, metadata={"file_name": file_path, "page_label": str(i + 1)})
        )
    return documents
