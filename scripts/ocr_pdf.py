
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
          
            pix = page.get_pixmap(dpi=dpi)
            img_bytes = pix.tobytes("png")
            result = reader.readtext(
                img_bytes, detail=0, paragraph=True, canvas_size=canvas_size
            )
            text = "\n".join(result)

            out_f.write(f"--- Page {page_num} ---\n{text}\n\n")
            out_f.flush()

            
            del pix, img_bytes, result
            gc.collect()

            print(
                f"page {page_num}/{total} done in {time.time() - t0:.1f}s, {len(text)} chars",
                flush=True,
            )

    print(f"Wrote OCR text to {out_path}")


if __name__ == "__main__":
    ocr_pdf(sys.argv[1], sys.argv[2])
