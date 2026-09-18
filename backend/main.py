from fastapi import FastAPI

from backend.api.health import router as health_router
from backend.api.webhook import router as webhook_router


app = FastAPI(
    title="TCC Financeiro",
    version="1.0.0"
)

app.include_router(webhook_router)
app.include_router(health_router)


@app.get("/")
def inicio():
    return {"status": "online"}


@app.get("/ping")
def ping():
    return {"message": "pong"}
