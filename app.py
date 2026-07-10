"""
API HTTP del editor de Cartas de Libranza.

Sin almacenamiento: los PDF nunca tocan disco. El cliente sube el PDF, recibe
los campos, edita, y vuelve a enviar el PDF con los cambios para recibir el
resultado. Todo vive en memoria durante la petición.

Endpoints
---------
GET  /            -> interfaz web (web/index.html)
POST /api/extract -> multipart {file} -> {fields: [...]}
POST /api/apply   -> multipart {file, changes(JSON)} -> application/pdf
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response

import engine

app = FastAPI(title="Editor de Carta de Libranza", version="1.0.0")

_WEB = Path(__file__).parent / "web"
_MAX_BYTES = 20 * 1024 * 1024  # 20 MB de tope defensivo


def _read_pdf(file: UploadFile) -> bytes:
    data = file.file.read()
    if not data:
        raise HTTPException(400, "Archivo vacío.")
    if len(data) > _MAX_BYTES:
        raise HTTPException(413, "El archivo supera el tamaño máximo permitido.")
    if not data.startswith(b"%PDF"):
        raise HTTPException(400, "El archivo no es un PDF válido.")
    return data


@app.get("/")
def index():
    return FileResponse(_WEB / "index.html")


@app.post("/api/extract")
def extract(file: UploadFile = File(...)):
    """Devuelve los campos editables detectados en el PDF."""
    pdf = _read_pdf(file)
    try:
        fields = engine.get_fields(pdf)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(422, f"No se pudo procesar el PDF: {exc}")
    return {"fields": fields, "count": len(fields)}


@app.post("/api/apply")
def apply(file: UploadFile = File(...), changes: str = Form(...)):
    """Aplica los cambios y devuelve el PDF modificado (sin guardar nada)."""
    pdf = _read_pdf(file)
    try:
        raw = json.loads(changes)
    except json.JSONDecodeError:
        raise HTTPException(400, "El campo 'changes' no es JSON válido.")
    if not isinstance(raw, dict):
        raise HTTPException(400, "'changes' debe ser un objeto {id: valor}.")

    # normalizar claves a int (los ids de campo son índices de run)
    changes_map = {}
    for key, value in raw.items():
        try:
            changes_map[int(key)] = str(value)
        except (TypeError, ValueError):
            raise HTTPException(400, f"Id de campo inválido: {key!r}")

    try:
        out = engine.apply_changes(pdf, changes_map)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(422, f"No se pudo generar el PDF: {exc}")

    return Response(
        content=out,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="libranza_modificada.pdf"'},
    )
