"""FastAPI routes for the study-schedule page (frontend/schedule-page)."""
import io
import logging
from typing import Dict, List, Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

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
def transcript(file: UploadFile = File(...)):
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=415, detail="Please upload the transcript as a PDF file.")
    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File is too large. The maximum size is 15MB.")
    try:
        return service.import_transcript(io.BytesIO(data))
    except Exception:
        logger.exception("Transcript parsing failed")
        raise HTTPException(
            status_code=422,
            detail="Could not read this PDF. Upload the text-based transcript exported from the university system.",
        )
