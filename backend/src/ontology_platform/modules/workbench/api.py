"""HTTP routes of the workbench module."""

from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["workbench"])
