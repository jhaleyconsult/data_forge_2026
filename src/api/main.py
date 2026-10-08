"""FastAPI application entry point."""

from fastapi import FastAPI

from src.api.routes.check_in import router as check_in_router
from src.api.routes.check_out import router as check_out_router
from src.api.routes.current_care import router as current_care_router
from src.api.routes.status import router as status_router

app = FastAPI(title="Hospital Bed Turnover API")
app.include_router(check_in_router)
app.include_router(current_care_router)
app.include_router(check_out_router)
app.include_router(status_router)