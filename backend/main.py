import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.auth import router as auth_router
from backend.api.dashboard import router as dashboard_router
from backend.api.goals import router as goals_router
from backend.api.health import router as health_router
from backend.api.insights import router as insights_router
from backend.api.notifications import router as notifications_router
from backend.api.settings import router as settings_router
from backend.api.transactions import router as transactions_router
from backend.api.webhook import router as webhook_router


app = FastAPI(
    title="FinControl AI",
    version="1.0.0"
)

default_origins = {"http://localhost:3000", "http://127.0.0.1:3000"}
configured_origins = {
    origin.strip().rstrip("/")
    for origin in os.getenv("ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
}
app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(default_origins | configured_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    expose_headers=["Content-Disposition"],
)

app.include_router(webhook_router)
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(goals_router)
app.include_router(insights_router)
app.include_router(settings_router)
app.include_router(notifications_router)
app.include_router(transactions_router)


@app.get("/")
def inicio():
    return {"status": "online"}


@app.get("/ping")
def ping():
    return {"message": "pong"}
