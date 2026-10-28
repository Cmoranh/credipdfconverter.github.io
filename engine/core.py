"""
Motor de extracción y reemplazo de texto sobre el PDF de Carta de Libranza.

Idea central
------------
Hay dos generadores de la Carta de Libranza y el motor soporta ambos:

  * **Iceni Infix** (renovaciones): dibuja el texto letra por letra, cada
    glifo con su propia matriz de texto (`Tm`, escala 8) y `Tf` de tamaño 1.
    No hay una cadena `(MARIO ALBERTO)` que sustituir: hay `(M) Tj`,
    `(A) Tj`, ... cada una posicionada.
  * **JasperReports** (compra de deuda, nuevos): cada valor es una cadena
    completa `(MARIO ALBERTO) Tj` con `Tm` de escala 1 y `Tf` de tamaño 8.
    Algunas copias vienen además escaladas a carta con un `cm` global.

Por eso el tamaño efectivo es `Tf × escala(Tm) × escala(CTM)` y las posiciones
se calculan en espacio de página (aplicando la CTM).

Por eso el reemplazo "solo del string" consiste en:
  1. Parsear el content stream a operaciones estructuradas (pypdf ContentStream).
  2. Recorrerlas manteniendo el estado gráfico (fuente activa vía `Tf`, matriz
     de texto vía `Tm`) para saber qué carácter se pinta y dónde.
  3. Agrupar glifos contiguos en "runs" (los valores visibles).
  4. Para reemplazar un run: eliminar sus operaciones y emitir nuevas
     `Tm`/`Tf`/`Tj` en el mismo punto del stream, con la misma forma que el
     original (letra por letra o cadena completa), recalculando la X con las
     métricas Helvetica. Fuente, tamaño, color y coordenada Y NO se tocan.
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
    x: float               # posición en espacio de página (CTM aplicada)
    y: float
    size: float            # tamaño efectivo en página: Tf × escala Tm × escala CTM
    font_res: str          # p.ej. "/F3"
    bold: bool
    char: str              # carácter (puede ser >1 si vino de un Tj multi-char)
    raw_x: float = 0.0     # posición tal cual la fija `Tm` (sin CTM)
    raw_y: float = 0.0
    tm_scale: float = 1.0  # escala de la matriz de texto
    tf_size: float = 1.0   # tamaño indicado en `Tf`


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

    @property
    def raw_size(self) -> float:
        """Tamaño en el espacio del stream (antes de la CTM)."""
        g = self.glyphs[0]
        return g.tf_size * g.tm_scale


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


def _mul(m, n):
    """Producto de matrices afines de PDF [a b c d e f]: m × n."""
    a, b, c, d, e, f = m
    A, B, C, D, E, F = n
    return [
        a * A + b * C, a * B + b * D,
        c * A + d * C, c * B + d * D,
        e * A + f * C + E, e * B + f * D + F,
    ]


_IDENTITY = [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]


def _walk(cs: ContentStream, bold_map: dict) -> list:
    """Recorre las operaciones y devuelve la lista de glifos con estado."""
    glyphs: list = []
    ctm = list(_IDENTITY)
    ctm_stack: list = []
    tm = list(_IDENTITY)
    tlm = list(_IDENTITY)   # matriz de línea (base de Td)
    font_res = None
    tf_size = 1.0
    last_tm_index = -1

    for idx, (operands, operator) in enumerate(cs.operations):
        op = operator.decode() if isinstance(operator, bytes) else operator

        if op == "q":
            ctm_stack.append(list(ctm))
        elif op == "Q":
            ctm = ctm_stack.pop() if ctm_stack else list(_IDENTITY)
        elif op == "cm":
            ctm = _mul([float(v) for v in operands], ctm)
        elif op == "Tf":
            font_res = str(operands[0])
            tf_size = float(operands[1])
        elif op == "Tm":
            tm = [float(v) for v in operands]
            tlm = list(tm)
            last_tm_index = idx
        elif op == "BT":
            tm = list(_IDENTITY)
            tlm = list(_IDENTITY)
            last_tm_index = -1
        elif op in ("Td", "TD"):
            # desplazamiento relativo respecto a la matriz de línea
            tlm = _mul([1.0, 0.0, 0.0, 1.0, float(operands[0]), float(operands[1])], tlm)
            tm = list(tlm)
            last_tm_index = -1
        elif op in ("Tj", "TJ"):
            if op == "Tj":
                parts = [operands[0]]
            else:
                parts = list(operands[0])
            text = "".join(
                _to_text(e) for e in parts
                if not isinstance(e, (int, float, NumberObject, FloatObject))
            )
            bold = bool(bold_map.get(font_res, metrics.is_bold(font_res or "")))
            tm_scale = abs(float(tm[0])) or abs(float(tm[3])) or 1.0
            ctm_scale = abs(ctm[0] * ctm[3] - ctm[1] * ctm[2]) ** 0.5 or 1.0
            x = tm[4] * ctm[0] + tm[5] * ctm[2] + ctm[4]
            y = tm[4] * ctm[1] + tm[5] * ctm[3] + ctm[5]
            glyphs.append(
                Glyph(
                    op_index=idx,
                    tm_index=last_tm_index,
                    x=x,
                    y=y,
                    size=abs(tf_size) * tm_scale * ctm_scale,
                    font_res=font_res or "/F1",
                    bold=bold,
                    char=text,
                    raw_x=float(tm[4]),
                    raw_y=float(tm[5]),
                    tm_scale=tm_scale,
                    tf_size=tf_size,
                )
            )
            # Tras pintar, la matriz de texto avanza el ancho de lo pintado.
            advance = 0.0
            for e in parts:
                if isinstance(e, (int, float, NumberObject, FloatObject)):
                    advance -= float(e) / 1000.0 * tf_size
                else:
                    advance += metrics.text_width(_to_text(e), tf_size, bold)
            tm = _mul([1.0, 0.0, 0.0, 1.0, advance, 0.0], tm)
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


class _Literal(ByteStringObject):
    """Cadena literal `(...)` como las del documento (pypdf escribiría `<hex>`)."""

    def write_to_stream(self, stream, encryption_key=None) -> None:
        data = bytes(self).replace(b"\\", b"\\\\")
        data = data.replace(b"(", b"\\(").replace(b")", b"\\)")
        stream.write(b"(" + data + b")")


def _start_x(run: Run, new_text: str, align: str) -> float:
    """X inicial (espacio del stream) del texto nuevo según la alineación."""
    x = run.glyphs[0].raw_x
    if align == "center":
        old_w = metrics.text_width(run.text, run.raw_size, run.bold)
        new_w = metrics.text_width(new_text, run.raw_size, run.bold)
        x += (old_w - new_w) / 2.0
    return x


def _emit_replacement_ops(run: Run, new_text: str, align: str = "left") -> list:
    """Genera las operaciones Tm/Tf/Tj para pintar `new_text` letra por letra.

    Es la forma del generador Iceni (un `Tm`/`Tf`/`Tj` por glifo). Mantiene Y,
    tamaño (`Tf` y escala de `Tm`) y fuente del run original; solo recalcula
    la X de cada letra con las métricas de la fuente.
    """
    g0 = run.glyphs[0]
    scale = g0.tm_scale
    x = _start_x(run, new_text, align)
    y = g0.raw_y
    ops = []
    for ch in new_text:
        matrix = [
            FloatObject(scale), NumberObject(0), NumberObject(0),
            FloatObject(scale), FloatObject(round(x, 3)), FloatObject(round(y, 3)),
        ]
        ops.append((ArrayObject(matrix), b"Tm"))
        ops.append((ArrayObject([NameObject(run.font_res), FloatObject(g0.tf_size)]), b"Tf"))
        ops.append((ArrayObject([_Literal(ch.encode("latin-1", "replace"))]), b"Tj"))
        x += metrics.char_width(ch, run.raw_size, run.bold)
    return ops


def apply_changes(pdf_bytes: bytes, changes: dict, page_index: int = 0,
                  align: dict | None = None) -> bytes:
    """Aplica {run_id: nuevo_valor} y devuelve el PDF resultante en bytes.

    `run_id` es el índice del run tal y como lo devuelve `list_fields`.
    `align` opcional: {run_id: "center"} para los valores centrados en su celda.
    No se escribe nada en disco.
    """
    reader, page, cs, runs = extract_runs(pdf_bytes, page_index)
    align = {int(k): v for k, v in (align or {}).items()}

    # Cuántos glifos cuelgan de cada `Tm`: un `Tm` solo se toca si todos los
    # glifos que posiciona pertenecen al run que se reemplaza.
    tm_refs: dict = {}
    for r in runs:
        for g in r.glyphs:
            if g.tm_index >= 0:
                tm_refs[g.tm_index] = tm_refs.get(g.tm_index, 0) + 1

    drop = set()
    dropped_refs: dict = {}
    inserts = {}   # posición de inserción -> lista de nuevas ops
    replace = {}   # posición -> operación que sustituye a la original
    for run_id, new_value in changes.items():
        run = runs[int(run_id)]
        if new_value == run.text:
            continue
        run_align = align.get(int(run_id), "left")
        g0 = run.glyphs[0]

        # Cadena completa en un solo Tj con su propio Tm (JasperReports): se
        # reescriben esas dos operaciones en su sitio, sin añadir ninguna.
        if len(run.glyphs) == 1 and g0.tm_index >= 0 and tm_refs.get(g0.tm_index) == 1:
            x = _start_x(run, new_value, run_align)
            if abs(x - g0.raw_x) > 1e-6:
                operands, _ = cs.operations[g0.tm_index]
                matrix = ArrayObject(list(operands))
                matrix[4] = FloatObject(round(x, 3))
                replace[g0.tm_index] = (matrix, b"Tm")
            if new_value:
                replace[g0.op_index] = (
                    ArrayObject([_Literal(new_value.encode("latin-1", "replace"))]), b"Tj")
            else:
                drop.add(g0.op_index)
            continue

        # Letra por letra (Iceni): se quitan los glifos viejos y se pintan los
        # nuevos donde se pintaba el original (tras su color, dentro de su BT).
        for g in run.glyphs:
            drop.add(g.op_index)
            if g.tm_index >= 0:
                dropped_refs[g.tm_index] = dropped_refs.get(g.tm_index, 0) + 1
        anchor = min(g.op_index for g in run.glyphs)
        inserts[anchor] = _emit_replacement_ops(run, new_value, run_align)
    for tm_index, count in dropped_refs.items():
        if count == tm_refs.get(tm_index):
            drop.add(tm_index)

    # Reconstruir la lista de operaciones respetando el orden original.
    new_operations = []
    for idx, operation in enumerate(cs.operations):
        if idx in inserts:
            new_operations.extend(inserts[idx])
        if idx in drop:
            continue
        new_operations.append(replace.get(idx, operation))

    cs.operations = new_operations

    writer = pypdf.PdfWriter(clone_from=reader)
    stream = _rebuilt_stream(cs, writer)
    writer.pages[page_index][NameObject("/Contents")] = stream
    # El content stream viejo queda huérfano: no debe viajar en el PDF nuevo.
    _drop_unreferenced(writer)

    out = BytesIO()
    writer.write(out)
    return out.getvalue()


def _drop_unreferenced(writer) -> None:
    """Quita del writer los objetos que ya nadie referencia (pypdf >= 4.3)."""
    if not hasattr(writer, "compress_identical_objects"):
        return
    try:
        writer.compress_identical_objects(remove_duplicates=False, remove_unreferenced=True)
    except TypeError:  # pypdf < 6 usa los nombres anteriores de los parámetros
        writer.compress_identical_objects(remove_identicals=False, remove_orphans=True)


def _rebuilt_stream(cs: ContentStream, writer):
    """Serializa el ContentStream modificado y lo añade como objeto del writer."""
    from pypdf.generic import DecodedStreamObject

    data = cs.get_data()
    stream = DecodedStreamObject()
    stream.set_data(data)
    return writer._add_object(stream)
