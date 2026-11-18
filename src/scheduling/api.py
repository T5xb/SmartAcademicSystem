"""FastAPI routes for the study-schedule page (frontend/schedule-page)."""
import io
import logging
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from src.accounts import store
from src.accounts.deps import current_user

from . import service

logger = logging.getLogger("gp2-scheduler")
router = APIRouter(prefix="/api/schedule", tags=["schedule"])

MAX_UPLOAD_BYTES = 15 * 1024 * 1024
TIME_PATTERN = r"^([01]\d|2[0-4]):[0-5]\d$"


class GenerateRequest(BaseModel):
    courses: List[str] = Field(max_length=15)
    locks: Dict[str, str] = Field(default_factory=dict)
    time_from: str = Field("00:00", pattern=TIME_PATTERN)
    time_to: str = Field("24:00", pattern=TIME_PATTERN)
    min_days_off: int = Field(0, ge=0, le=4)
    include_closed: bool = False
    # Only sent after a transcript import; null means "history unknown".
    completed_courses: Optional[List[str]] = None
    max_credit_hours: int = Field(service.DEFAULT_MAX_CREDITS, ge=1, le=30)
    prefer_morning: bool = False
    preferred_instructors: Dict[str, str] = Field(default_factory=dict)
    limit: int = Field(service.MAX_SCHEDULES, ge=1, le=service.MAX_SCHEDULES)


@router.get("/courses")
def courses():
    return service.catalog()


# Plain `def` (not async): the solver and the PDF parser are CPU-bound, so
# FastAPI runs them in its thread pool instead of blocking the chat endpoint.
@router.post("/generate")
def generate(req: GenerateRequest):
    try:
        return service.generate(
            req.courses, locks=req.locks, time_from=req.time_from, time_to=req.time_to,
            min_days_off=req.min_days_off, include_closed=req.include_closed,
            completed_courses=req.completed_courses, max_credit_hours=req.max_credit_hours,
            prefer_morning=req.prefer_morning,
            preferred_instructors=req.preferred_instructors, limit=req.limit,
        )
    except service.ScheduleRequestError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/transcript")
def transcript(file: UploadFile = File(...), user: dict = Depends(current_user)):
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=415, detail="Please upload the transcript as a PDF file.")
    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File is too large. The maximum size is 15MB.")
    try:
        result = service.import_transcript(io.BytesIO(data))
    except Exception:
        logger.exception("Transcript parsing failed")
        raise HTTPException(
            status_code=422,
            detail="Could not read this PDF. Upload the text-based transcript exported from the university system.",
        )
    # Kept in the student's profile: the schedule page reloads it on the next
    # sign-in, and the advisor sees it.
    if user["role"] == "student" and result["parsed_courses"]:
        store.update_profile(user["id"], {"transcript": result})
    return result


# ---------------------------------------------------------------- admin: the offered courses (Excel)
# The admin downloads the courses, sections, times, CRNs and seats as an Excel
# file, edits it and uploads it back; the schedule page uses it at once.

from datetime import datetime as _datetime  # noqa: E402

from fastapi.responses import Response  # noqa: E402

from src.accounts.deps import require_admin  # noqa: E402

from . import offerings  # noqa: E402

admin_router = APIRouter(prefix="/api/admin/courses", tags=["admin"])
MAX_EXCEL_BYTES = 5 * 1024 * 1024
XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

_READ_ERRORS = {
    "not_excel": "This is not an Excel file. Upload the .xlsx file downloaded from this page.",
    "no_header": "The file has no course rows.",
    "empty": "The file has no course rows.",
}


def _summary() -> dict:
    data = service.current_offerings()
    sections = []
    for c in data:
        for s in c["sections"]:
            closed = s.get("capacity") is not None and (s.get("enrolled") or 0) >= s["capacity"]
            sections.append({
                "code": c["code"], "name": c["name"], "credits": c["credits"],
                "section": s["id"], "crn": s["crn"], "instructor": s.get("instructor") or "",
                "capacity": s.get("capacity"), "enrolled": s.get("enrolled") or 0, "closed": closed,
                "meetings": s["meetings"],
            })
    return {
        **service.source_info(),
        "courses": len(data),
        "sections": len(sections),
        "closed": sum(1 for s in sections if s["closed"]),
        "rows": sections,
    }


@admin_router.get("")
def offered_courses(_: dict = Depends(require_admin)):
    return _summary()


@admin_router.get("/excel")
def download_excel(_: dict = Depends(require_admin)):
    data = offerings.to_excel(service.current_offerings())
    name = f"course-offerings-{_datetime.now():%Y-%m-%d}.xlsx"
    return Response(data, media_type=XLSX_TYPE,
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@admin_router.post("/excel")
def upload_excel(file: UploadFile = File(...), user: dict = Depends(require_admin)):
    if not (file.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(status_code=415, detail="Please upload the course file as .xlsx (Excel).")
    data = file.file.read(MAX_EXCEL_BYTES + 1)
    if len(data) > MAX_EXCEL_BYTES:
        raise HTTPException(status_code=413, detail="File is too large. The maximum size is 5MB.")
    try:
        courses, problems = offerings.parse_excel(data)
    except offerings.OfferingsError as e:
        code = str(e)
        if code.startswith("missing_columns:"):
            raise HTTPException(status_code=422, detail=f"The file is missing these columns: {code.split(':', 1)[1]}")
        raise HTTPException(status_code=422, detail=_READ_ERRORS.get(code, _READ_ERRORS["not_excel"]))
    if problems:
        # Nothing is saved; the page lists each problem with its row.
        return {"saved": False, "problems": problems[:200], "total_problems": len(problems)}
    offerings.save(courses, user["name"])
    service.refresh(force=True)
    logger.info("Course offerings replaced by %s: %d courses", user["username"], len(courses))
    return {"saved": True, **_summary()}


@admin_router.post("/reset")
def reset_to_default(user: dict = Depends(require_admin)):
    offerings.clear_saved()
    service.refresh(force=True)
    logger.info("Course offerings reset to the built-in data by %s", user["username"])
    return {"saved": True, **_summary()}
