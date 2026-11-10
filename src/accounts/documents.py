"""
The admin's source-file management: list, upload, replace and remove the
documents the chatbot answers from (DATA_DIR), turn a scanned PDF into text
(OCR), and rebuild the index so the chatbot uses the new files.

A replaced or removed file is never deleted: it is moved to
DOCS_BACKUP_DIR (outside DATA_DIR, so it is not indexed), under a folder
named by the time of the change.

OCR and the index rebuild are slow (minutes) and heavy, so each runs as a
separate process, one at a time; the page polls GET /api/admin/index.
"""

import logging
import os
import re
import shutil
import subprocess
import sys
import threading
from datetime import datetime
from typing import Callable

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from . import store
from .db import now_iso
from .deps import require_admin

logger = logging.getLogger("gp2-documents")
router = APIRouter(prefix="/api/admin", dependencies=[Depends(require_admin)])

ALLOWED_EXTENSIONS = (".pdf", ".docx", ".txt", ".md")
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OCR_SCRIPT = os.path.join(PROJECT_DIR, "scripts", "ocr_pdf.py")
_OCR_PAGE = re.compile(r"^--- Page \d+ ---$", re.MULTILINE)

# Set by fastapi_app: reloads the chatbot's index after a rebuild.
on_index_rebuilt: Callable[[], None] | None = None


def data_dir() -> str:
    return os.path.realpath(os.environ.get("DATA_DIR", "docs"))


def backup_dir() -> str:
    return os.path.realpath(os.environ.get("DOCS_BACKUP_DIR", os.path.join("output", "replaced_docs")))


# ------------------------------------------------------------------ paths


def _resolve(relative: str) -> str:
    """The real path of `relative` inside DATA_DIR; anything outside is refused."""
    root = data_dir()
    relative = (relative or "").replace("\\", "/").strip("/")
    path = os.path.realpath(os.path.join(root, relative))
    if path != root and not path.startswith(root + os.sep):
        raise HTTPException(status_code=400, detail="This path is outside the documents folder.")
    return path


def _relative(path: str) -> str:
    return os.path.relpath(path, data_dir()).replace(os.sep, "/")


def _clean_name(filename: str) -> str:
    name = os.path.basename((filename or "").replace("\\", "/")).strip()
    name = re.sub(r'[<>:"|?*\x00-\x1f]', "", name).strip(" .")
    if not name or name.startswith("."):
        raise HTTPException(status_code=400, detail="This file name can't be used.")
    if not name.lower().endswith(ALLOWED_EXTENSIONS):
        raise HTTPException(
            status_code=415, detail="Only PDF, DOCX, TXT and MD files can be added to the documents."
        )
    return name


def _existing_file(relative: str) -> str:
    path = _resolve(relative)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="File not found.")
    return path


def _read_upload(upload: UploadFile) -> bytes:
    data = upload.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File is too large. The maximum size is 50MB.")
    if not data:
        raise HTTPException(status_code=400, detail="This file is empty.")
    return data


def _write(path: str, data: bytes) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # Written beside the target first, so a failed write leaves no half file.
    temp = path + ".uploading"
    with open(temp, "wb") as f:
        f.write(data)
    os.replace(temp, path)


def _move_to_backup(path: str, stamp: str) -> str:
    target = os.path.join(backup_dir(), stamp, os.path.relpath(path, data_dir()))
    os.makedirs(os.path.dirname(target), exist_ok=True)
    shutil.move(path, target)
    return target


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _mark_changed() -> None:
    store.set_meta("index_stale", "1")
    store.set_meta("docs_changed_at", now_iso())


def _file_info(path: str) -> dict:
    stat = os.stat(path)
    relative = _relative(path)
    return {
        "path": relative,
        "name": os.path.basename(path),
        "folder": os.path.dirname(relative),
        "size": stat.st_size,
        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
    }


def list_files() -> tuple[list[dict], list[str]]:
    files, folders = [], [""]
    root = data_dir()
    for folder, subfolders, names in os.walk(root):
        subfolders.sort()
        if folder != root:
            folders.append(_relative(folder))
        for name in sorted(names):
            if name.lower().endswith(ALLOWED_EXTENSIONS):
                files.append(_file_info(os.path.join(folder, name)))
    return files, folders


# ------------------------------------------------------------------- jobs


class _Job:
    """The one background job (index rebuild or OCR) and its last result."""

    def __init__(self):
        self.lock = threading.Lock()
        self.kind = ""
        self.target = ""
        self.status = "idle"   # idle | running | done | error
        self.message = ""
        self.started_at = ""
        self.finished_at = ""
        self.progress: Callable[[], str] | None = None

    def snapshot(self) -> dict:
        message = self.message
        if self.status == "running" and self.progress:
            try:
                message = self.progress() or message
            except OSError:
                pass
        return {
            "kind": self.kind, "target": self.target, "status": self.status,
            "message": message, "started_at": self.started_at, "finished_at": self.finished_at,
        }

    def start(self, kind: str, target: str, work: Callable[[], str], progress=None) -> None:
        with self.lock:
            if self.status == "running":
                raise HTTPException(
                    status_code=409, detail="Another job is still running. Wait for it to finish."
                )
            self.kind, self.target, self.status = kind, target, "running"
            self.message, self.started_at, self.finished_at = "", now_iso(), ""
            self.progress = progress
        threading.Thread(target=self._run, args=(work,), daemon=True).start()

    def _run(self, work: Callable[[], str]) -> None:
        try:
            message, status = work(), "done"
        except Exception as e:  # reported to the admin page, not raised
            logger.exception("Background job failed")
            message, status = str(e) or e.__class__.__name__, "error"
        with self.lock:
            self.message, self.status, self.finished_at = message, status, now_iso()


job = _Job()


def _run_process(args: list[str]) -> None:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    result = subprocess.run(
        args, cwd=PROJECT_DIR, env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    if result.returncode != 0:
        lines = [line for line in (result.stderr or result.stdout).splitlines() if line.strip()]
        raise RuntimeError(lines[-1] if lines else f"The process failed (exit {result.returncode}).")


def _rebuild_index() -> str:
    # Marked before the build: files that change while it runs are not in it.
    started = now_iso()
    _run_process([sys.executable, "-c", "from src.generate import generate_index; generate_index()"])
    if store.get_meta("docs_changed_at") <= started:
        store.set_meta("index_stale", "0")
    store.set_meta("index_built_at", now_iso())
    if on_index_rebuilt:
        on_index_rebuilt()
    return "The index was rebuilt. The chatbot now answers from the current documents."


def _ocr_work_path(text_path: str) -> str:
    # Unfinished OCR text is kept outside DATA_DIR, so a rebuild never indexes
    # half a document; the script resumes from it if a run was interrupted.
    return os.path.join(backup_dir(), "ocr_in_progress", os.path.relpath(text_path, data_dir()))


def _ocr(pdf_path: str, text_path: str) -> str:
    work_path = _ocr_work_path(text_path)
    os.makedirs(os.path.dirname(work_path), exist_ok=True)
    _run_process([sys.executable, OCR_SCRIPT, pdf_path, work_path])
    shutil.move(work_path, text_path)
    # The text replaces the scanned PDF as the indexed source (both in the
    # index would be the same document twice); the PDF goes to the backup.
    _move_to_backup(pdf_path, _stamp())
    _mark_changed()
    return f"Text extracted to {os.path.basename(text_path)}. Rebuild the index to use it."


def _ocr_progress(text_path: str) -> Callable[[], str]:
    def progress() -> str:
        with open(_ocr_work_path(text_path), encoding="utf-8") as f:
            pages = len(_OCR_PAGE.findall(f.read()))
        return f"{pages} page(s) read so far"

    return progress


# ----------------------------------------------------------------- routes


class PathRequest(BaseModel):
    path: str = Field(min_length=1, max_length=500)


def index_status() -> dict:
    return {
        "stale": store.get_meta("index_stale") == "1",
        "built_at": store.get_meta("index_built_at"),
        "job": job.snapshot(),
    }


@router.get("/files")
def files():
    found, folders = list_files()
    return {"files": found, "folders": folders, "index": index_status()}


@router.post("/files", status_code=201)
def upload(folder: str = Form(""), file: UploadFile = File(...)):
    """Add a new document. A file with the same name is not overwritten here."""
    target_folder = _resolve(folder)
    if not os.path.isdir(target_folder):
        raise HTTPException(status_code=404, detail="Folder not found.")
    path = os.path.join(target_folder, _clean_name(file.filename))
    if os.path.exists(path):
        raise HTTPException(
            status_code=409,
            detail="A file with this name is already in this folder. Use Replace on that file instead.",
        )
    _write(path, _read_upload(file))
    _mark_changed()
    return {"file": _file_info(path), "index": index_status()}


@router.post("/files/replace")
def replace(path: str = Form(...), keep_name: bool = Form(True), file: UploadFile = File(...)):
    """
    Put an updated document in the place of an existing one. The new file
    lands in the same folder; with `keep_name` it also keeps the old file's
    name (and takes the new file's type). The old file moves to the backup.
    """
    old_path = _existing_file(path)
    new_name = _clean_name(file.filename)
    if keep_name:
        stem = os.path.splitext(os.path.basename(old_path))[0]
        new_name = stem + os.path.splitext(new_name)[1].lower()
    new_path = os.path.join(os.path.dirname(old_path), new_name)
    if os.path.normcase(new_path) != os.path.normcase(old_path) and os.path.exists(new_path):
        raise HTTPException(
            status_code=409, detail="Another file in this folder already has the new file's name."
        )
    data = _read_upload(file)
    _move_to_backup(old_path, _stamp())
    _write(new_path, data)
    _mark_changed()
    return {"file": _file_info(new_path), "replaced": _relative(old_path), "index": index_status()}


@router.post("/files/remove")
def remove(req: PathRequest):
    """Take a document out of the chatbot's sources (moved to the backup)."""
    path = _existing_file(req.path)
    _move_to_backup(path, _stamp())
    _mark_changed()
    return {"removed": req.path, "index": index_status()}


@router.post("/files/ocr", status_code=202)
def ocr(req: PathRequest):
    """Read a scanned PDF into a text file the index can use (slow)."""
    pdf_path = _existing_file(req.path)
    if not pdf_path.lower().endswith(".pdf"):
        raise HTTPException(status_code=415, detail="Only PDF files can be read with OCR.")
    text_path = os.path.splitext(pdf_path)[0] + ".txt"
    if os.path.exists(text_path):
        raise HTTPException(
            status_code=409, detail="A text file with this name already exists beside the PDF."
        )
    job.start("ocr", req.path, lambda: _ocr(pdf_path, text_path), _ocr_progress(text_path))
    return {"index": index_status()}


@router.get("/index")
def index():
    return index_status()


@router.post("/index/rebuild", status_code=202)
def rebuild():
    job.start("rebuild", "", _rebuild_index)
    return {"index": index_status()}
