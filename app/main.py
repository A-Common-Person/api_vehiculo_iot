import logging

import pymysql
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.database import db
from app.exceptions import RecursoNoEncontradoError, ReglaNegocioError
from app.routers import consultas, demos, gestion, movimientos, ws

logger = logging.getLogger(__name__)

app = FastAPI(title="API Vehículo IoT", version="1.0.0")
app.include_router(movimientos.router)
app.include_router(demos.router)
app.include_router(ws.router)
app.include_router(consultas.router)
app.include_router(gestion.router)


@app.exception_handler(RecursoNoEncontradoError)
async def no_encontrado(request: Request, exc: RecursoNoEncontradoError):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(ReglaNegocioError)
async def regla_negocio(request: Request, exc: ReglaNegocioError):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(pymysql.err.IntegrityError)
async def error_integridad(request: Request, exc: pymysql.err.IntegrityError):
    logger.warning("Violación de integridad: %s", exc)
    return JSONResponse(
        status_code=409,
        content={"detail": "La operación viola una restricción de datos relacionados"},
    )

@app.exception_handler(pymysql.err.DataError)
async def error_datos(request: Request, exc: pymysql.err.DataError):
    logger.warning("Dato inválido para la base de datos: %s", exc)
    return JSONResponse(
        status_code=400,
        content={"detail": "Algún dato excede lo permitido por la base de datos"},
    )

@app.exception_handler(pymysql.MySQLError)
async def error_base_datos(request: Request, exc: pymysql.MySQLError):
    logger.error("Error de base de datos: %s", exc)
    return JSONResponse(
        status_code=503, content={"detail": "Base de datos no disponible"}
    )


@app.get("/health", tags=["Sistema"])
def health():
    return {"api": "ok", "database": "ok" if db.ping() else "error"}