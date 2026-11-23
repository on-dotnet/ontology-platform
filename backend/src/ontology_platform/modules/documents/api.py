"""HTTP routes of the documents module."""

from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["documents"])
