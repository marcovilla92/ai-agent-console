"""
HTML page routes for the dashboard UI.

Serves Jinja2 templates with Pico CSS styling and Alpine.js interactivity.
All routes require HTTP Basic Auth.
"""
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from src.server.dependencies import verify_credentials

TEMPLATE_DIR = Path(__file__).resolve().parent.parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

view_router = APIRouter(
    tags=["views"],
    dependencies=[Depends(verify_credentials)],
)


@view_router.get("/", response_class=HTMLResponse)
async def task_list_page(request: Request):
    """Task list page with create form."""
    return templates.TemplateResponse(request, "task_list.html")


@view_router.get("/tasks/{task_id}/view", response_class=HTMLResponse)
async def task_detail_page(request: Request, task_id: int):
    """Task detail page (template renders, data loaded client-side)."""
    return templates.TemplateResponse(
        request, "task_detail.html", context={"task_id": task_id}
    )
