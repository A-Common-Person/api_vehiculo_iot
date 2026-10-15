from fastapi import FastAPI

from app.database import db

app = FastAPI(title="API Vehículo IoT", version="1.0.0")


@app.get("/health", tags=["Sistema"])
def health():
    return {"api": "ok", "database": "ok" if db.ping() else "error"}