"""Motor de edición de texto para Cartas de Libranza (sin almacenamiento)."""

from .core import apply_changes, extract_runs  # noqa: F401
from .template import list_fields  # noqa: F401


def get_fields(pdf_bytes: bytes, page_index: int = 0):
    """Atajo: bytes de PDF -> lista de campos editables."""
    _, _, _, runs = extract_runs(pdf_bytes, page_index)
    return list_fields(runs)
