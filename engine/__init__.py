"""Motor de edición de texto para Cartas de Libranza (sin almacenamiento)."""

__version__ = "1.3.0"  # mantener igual que index.html y CHANGELOG.md

from . import core
from .core import extract_runs  # noqa: F401
from .template import list_fields  # noqa: F401


def get_fields(pdf_bytes: bytes, page_index: int = 0):
    """Atajo: bytes de PDF -> lista de campos editables."""
    _, _, _, runs = extract_runs(pdf_bytes, page_index)
    return list_fields(runs)


def apply_changes(pdf_bytes: bytes, changes: dict, page_index: int = 0) -> bytes:
    """Aplica {id: nuevo_valor}; los campos centrados (Fecha, Folio) se recentran."""
    align = {
        f["id"]: f["align"]
        for f in get_fields(pdf_bytes, page_index)
        if f["align"] != "left"
    }
    return core.apply_changes(pdf_bytes, changes, page_index, align=align)
