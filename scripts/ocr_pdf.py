"""
One-off OCR utility: convert a scanned PDF to a plain-text file using
EasyOCR (Arabic + English), so it can be indexed by the RAG pipeline.

Memory-conscious and crash-resilient: writes each page's text to the
output file as soon as it's OCR'd (rather than holding everything in
memory and writing once at the end), and skips pages already present
in an existing output file -- so if it crashes partway (e.g. out of
memory) or is interrupted, re-running the same command resumes instead
of starting over and losing progress.

Usage:
    .venv/Scripts/python.exe scripts/ocr_pdf.py <input.pdf> <output.txt>
"""

import gc
import re
import sys
import time

import fitz  # pymupdf
import easyocr

PAGE_MARKER = re.compile(r"^--- Page (\d+) ---$", re.MULTILINE)


def already_done_pages(out_path: str) -> set[int]:
    try:
        with open(out_path, encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        return set()
    return {int(n) for n in PAGE_MARKER.findall(content)}


def ocr_pdf(pdf_path: str, out_path: str, dpi: int = 130, canvas_size: int = 1280) -> None:
    done = already_done_pages(out_path)
    if done:
        print(f"Resuming: {len(done)} page(s) already OCR'd in {out_path}", flush=True)

    reader = easyocr.Reader(["ar", "en"], gpu=False)
    doc = fitz.open(pdf_path)
    total = len(doc)

    # Append mode: each page is flushed to disk immediately, so a crash
    # (e.g. out-of-memory) never loses already-completed pages.
    with open(out_path, "a", encoding="utf-8") as out_f:
        for i, page in enumerate(doc):
            page_num = i + 1
            if page_num in done:
                continue

            t0 = time.time()
            # Lower DPI keeps the source image small, and a lower
            # canvas_size caps how large the detector resizes it to
            # internally (default 2560 -- its activation memory scales
            # with this squared, so halving it cuts memory ~4x). Both
            # together are what actually got this under the ~1GB single
            # allocations that kept OOM-crashing on this machine even with
            # several GB "free" (likely fragmentation/other apps' usage,
            # not truly available headroom).
            pix = page.get_pixmap(dpi=dpi)
            img_bytes = pix.tobytes("png")
            result = reader.readtext(
                img_bytes, detail=0, paragraph=True, canvas_size=canvas_size
            )
            text = "\n".join(result)

            out_f.write(f"--- Page {page_num} ---\n{text}\n\n")
            out_f.flush()

            # Release the page image and any per-page torch tensors before
            # the next iteration instead of letting them pile up.
            del pix, img_bytes, result
            gc.collect()

            print(
                f"page {page_num}/{total} done in {time.time() - t0:.1f}s, {len(text)} chars",
                flush=True,
            )

    print(f"Wrote OCR text to {out_path}")


if __name__ == "__main__":
    ocr_pdf(sys.argv[1], sys.argv[2])
