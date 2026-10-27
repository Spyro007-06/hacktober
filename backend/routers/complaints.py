"""Complaint endpoints (POST /api/complaints is P0, Phase 3; the P1 list,
escalate and mode endpoints are not planned yet)."""
from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["complaints"])
