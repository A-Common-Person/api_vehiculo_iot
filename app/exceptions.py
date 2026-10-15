class RecursoNoEncontradoError(Exception):
    """El vehículo o el comando no existe (se convertirá en HTTP 404)."""


class ReglaNegocioError(Exception):
    """El recurso existe pero no cumple una regla (se convertirá en HTTP 409)."""