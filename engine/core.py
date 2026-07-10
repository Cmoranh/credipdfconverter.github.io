"""
Motor de extracción y reemplazo de texto sobre el PDF de Carta de Libranza.

Idea central
------------
El PDF (generado por Iceni Infix) dibuja el texto letra por letra, cada glifo
con su propia matriz de texto (`Tm`) y su posición X absoluta. No hay una
cadena `(MARIO ALBERTO)` que podamos sustituir a lo bruto: hay `(M) Tj`,
`(A) Tj`, ... cada una posicionada.

Por eso el reemplazo "solo del string" consiste en:
  1. Parsear el content stream a operaciones estructuradas (pypdf ContentStream).
  2. Recorrerlas manteniendo el estado gráfico (fuente activa vía `Tf`, matriz
     de texto vía `Tm`) para saber qué carácter se pinta y dónde.
  3. Agrupar glifos contiguos en "runs" (los valores visibles).
  4. Para reemplazar un run: eliminar sus operaciones y emitir nuevas
     `Tm`/`Tf`/`Tj`, recalculando la X de cada letra con las métricas Helvetica.
     Fuente, tamaño, color y coordenada Y NO se tocan.
  5. Reserializar el stream. Nada se guarda en disco: bytes entran, bytes salen.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO
from typing import Iterable

import pypdf
from pypdf.generic import (
    ArrayObject,
    ByteStringObject,
    ContentStream,
    FloatObject,
    NameObject,
    NumberObject,
)

from . import metrics

# Tolerancia vertical para considerar que dos glifos están en la misma línea.
_Y_TOL = 1.0
# Hueco horizontal (en puntos) por encima del cual dos glifos se consideran
# de campos/columnas distintas y NO se agrupan en el mismo run.
_GAP_SPLIT = 12.0


@dataclass
class Glyph:
    """Un carácter pintado, con su posición y la operación que lo dibuja."""

    op_index: int          # índice en ContentStream.operations del `Tj`/`TJ`
    tm_index: int          # índice del `Tm` que lo posiciona (-1 si no aplica)
    x: float
    y: float
    size: float            # tamaño efectivo (de la escala de la matriz)
    font_res: str          # p.ej. "/F3"
    bold: bool
    char: str              # carácter (puede ser >1 si vino de un Tj multi-char)


@dataclass
class Run:
    """Secuencia contigua de glifos: un valor visible en el documento."""

    text: str
    x0: float
    y: float
    size: float
    font_res: str
    bold: bool
    glyphs: list = field(default_factory=list)

    @property
    def op_indices(self) -> list:
        return [g.op_index for g in self.glyphs]


def _to_text(obj) -> str:
    """Decodifica un operando de cadena de PDF a str (latin-1 / WinAnsi)."""
    if isinstance(obj, bytes):
        return obj.decode("latin-1")
    if isinstance(obj, str):
        return obj
    try:
        return bytes(obj).decode("latin-1")
    except Exception:
        return str(obj)


def _font_bold_map(page) -> dict:
    """Mapa recurso-de-fuente -> es_negrita, leyendo /Resources /Font."""
    result = {}
    try:
        fonts = page["/Resources"]["/Font"]
    except Exception:
        return result
    for res_name, ref in fonts.items():
        try:
            base = str(ref.get_object().get("/BaseFont", ""))
        except Exception:
            base = ""
        result[str(res_name)] = "bold" in base.lower()
    return result


def _walk(cs: ContentStream, bold_map: dict) -> list:
    """Recorre las operaciones y devuelve la lista de glifos con estado."""
    glyphs: list = []
    tm = [1.0, 0, 0, 1.0, 0.0, 0.0]
    font_res = None
    last_tm_index = -1

    for idx, (operands, operator) in enumerate(cs.operations):
        op = operator.decode() if isinstance(operator, bytes) else operator

        if op == "Tf":
            font_res = str(operands[0])
        elif op == "Tm":
            tm = [float(v) for v in operands]
            last_tm_index = idx
        elif op == "BT":
            tm = [1.0, 0, 0, 1.0, 0.0, 0.0]
            last_tm_index = -1
        elif op in ("Td", "TD"):
            # desplazamiento relativo respecto a la matriz actual
            tm[4] += float(operands[0])
            tm[5] += float(operands[1])
            last_tm_index = -1
        elif op in ("Tj", "TJ"):
            if op == "Tj":
                text = _to_text(operands[0])
            else:
                text = "".join(
                    _to_text(e) for e in operands[0]
                    if not isinstance(e, (int, float, NumberObject, FloatObject))
                )
            size = abs(float(tm[0])) or abs(float(tm[3])) or 1.0
            bold = bold_map.get(font_res, metrics.is_bold(font_res or ""))
            glyphs.append(
                Glyph(
                    op_index=idx,
                    tm_index=last_tm_index,
                    x=float(tm[4]),
                    y=float(tm[5]),
                    size=size,
                    font_res=font_res or "/F1",
                    bold=bool(bold),
                    char=text,
                )
            )
    return glyphs


def _group_runs(glyphs: list) -> list:
    """Agrupa glifos contiguos (misma línea, sin huecos grandes) en runs."""
    runs: list = []
    cur: Run | None = None
    prev_end_x = None

    for g in glyphs:
        w = metrics.text_width(g.char, g.size, g.bold)
        same_line = cur is not None and abs(g.y - cur.y) <= _Y_TOL
        # Un valor se lee de izquierda a derecha: nunca retrocede en X. Un
        # salto hacia la izquierda (o un hueco grande) indica otro campo/columna.
        gap = (g.x - prev_end_x) if prev_end_x is not None else None
        contiguous = (
            same_line
            and g.size == cur.size
            and gap is not None
            and -1.0 <= gap <= _GAP_SPLIT
        )
        if contiguous:
            cur.text += g.char
            cur.glyphs.append(g)
        else:
            if cur is not None:
                runs.append(cur)
            cur = Run(
                text=g.char, x0=g.x, y=g.y, size=g.size,
                font_res=g.font_res, bold=g.bold, glyphs=[g],
            )
        prev_end_x = g.x + w
    if cur is not None:
        runs.append(cur)
    return runs


def extract_runs(pdf_bytes: bytes, page_index: int = 0):
    """Devuelve (reader, page, cs, runs) para la página indicada."""
    reader = pypdf.PdfReader(BytesIO(pdf_bytes))
    page = reader.pages[page_index]
    cs = ContentStream(page.get_contents(), reader)
    bold_map = _font_bold_map(page)
    glyphs = _walk(cs, bold_map)
    runs = _group_runs(glyphs)
    return reader, page, cs, runs


def _emit_replacement_ops(run: Run, new_text: str) -> list:
    """Genera las operaciones Tm/Tf/Tj para pintar `new_text` en el sitio del run.

    Mantiene Y, tamaño y fuente del run original; solo recalcula la X de cada
    carácter con las métricas de la fuente.
    """
    ops = []
    size = run.size
    x = run.x0
    y = run.y
    for ch in new_text:
        matrix = [
            FloatObject(size), NumberObject(0), NumberObject(0),
            FloatObject(size), FloatObject(round(x, 3)), FloatObject(round(y, 3)),
        ]
        ops.append((ArrayObject(matrix), b"Tm"))
        ops.append((ArrayObject([NameObject(run.font_res), NumberObject(1)]), b"Tf"))
        ops.append((ArrayObject([ByteStringObject(ch.encode("latin-1", "replace"))]), b"Tj"))
        x += metrics.char_width(ch, size, run.bold)
    return ops


def apply_changes(pdf_bytes: bytes, changes: dict, page_index: int = 0) -> bytes:
    """Aplica {run_id: nuevo_valor} y devuelve el PDF resultante en bytes.

    `run_id` es el índice del run tal y como lo devuelve `list_fields`.
    No se escribe nada en disco.
    """
    reader, page, cs, runs = extract_runs(pdf_bytes, page_index)

    # Índices de operación que hay que eliminar, y dónde insertar los nuevos.
    drop = set()
    inserts = {}  # posición de inserción -> lista de nuevas ops
    for run_id, new_value in changes.items():
        run = runs[int(run_id)]
        if new_value == run.text:
            continue
        op_positions = []
        for g in run.glyphs:
            if g.tm_index >= 0:
                drop.add(g.tm_index)
            drop.add(g.op_index)
            op_positions.append(g.tm_index if g.tm_index >= 0 else g.op_index)
        anchor = min(op_positions)
        inserts[anchor] = _emit_replacement_ops(run, new_value)

    # Reconstruir la lista de operaciones respetando el orden original.
    new_operations = []
    for idx, operation in enumerate(cs.operations):
        if idx in inserts:
            new_operations.extend(inserts[idx])
        if idx in drop:
            continue
        new_operations.append(operation)

    cs.operations = new_operations

    writer = pypdf.PdfWriter(clone_from=reader)
    stream = _rebuilt_stream(cs, writer)
    writer.pages[page_index][NameObject("/Contents")] = stream

    out = BytesIO()
    writer.write(out)
    return out.getvalue()


def _rebuilt_stream(cs: ContentStream, writer):
    """Serializa el ContentStream modificado y lo añade como objeto del writer."""
    from pypdf.generic import DecodedStreamObject

    data = cs.get_data()
    stream = DecodedStreamObject()
    stream.set_data(data)
    return writer._add_object(stream)
