from contextlib import asynccontextmanager
import logging

import pymysql
from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import ORIGENES_CLIENTE, settings
from app.database import db
from app.exceptions import RecursoNoEncontradoError, ReglaNegocioError
from app.routers import administracion, autenticacion, consultas, demos, gestion, movimientos, ws, ws_autenticado
from app.routers import control_prueba, editor_demos, ws_control, ws_dispositivo
from app.services.control_service import control

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(_app):
    yield
    await control.detener_demos()


app = FastAPI(title="API Vehículo IoT", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ORIGENES_CLIENTE,
    allow_methods=["GET", "POST", "PUT", "DELETE"] if settings.administracion_habilitada else ["GET", "POST"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)

if settings.administracion_habilitada:
    app.include_router(autenticacion.router)
    app.include_router(administracion.router)
    app.include_router(ws_autenticado.router)
    app.include_router(ws_dispositivo.router)
    app.include_router(ws_control.router)
    app.include_router(control_prueba.router)
    app.include_router(editor_demos.router)
else:
    app.include_router(movimientos.router)
    app.include_router(demos.router)
    app.include_router(ws.router)
app.include_router(consultas.router)
if not settings.administracion_habilitada:
    app.include_router(gestion.router)


@app.exception_handler(RequestValidationError)
async def error_validacion(request: Request, exc: RequestValidationError):
    if request.url.path == "/auth/login":
        return JSONResponse(status_code=422, content={"detail": "Revisa el correo y la contraseña"})
    if request.method == "POST" and request.url.path == "/administracion/clientes":
        return JSONResponse(status_code=422, content={"detail": "Revisa el nombre, el correo y la contraseña del cliente"})
    return await request_validation_exception_handler(request, exc)


@app.exception_handler(RecursoNoEncontradoError)
async def no_encontrado(request: Request, exc: RecursoNoEncontradoError):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(ReglaNegocioError)
async def regla_negocio(request: Request, exc: ReglaNegocioError):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(pymysql.err.IntegrityError)
async def error_integridad(request: Request, exc: pymysql.err.IntegrityError):
    logger.warning("Violación de integridad MySQL, código %s", exc.args[0])
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
