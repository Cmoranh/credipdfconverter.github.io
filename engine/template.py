"""
Plantilla de campos editables de la Carta de Libranza.

Como todos los PDF son idénticos salvo los datos, los valores editables se
reconocen de forma fiable por dos señales combinadas:

  * son texto en **negrita** de tamaño 8 (los datos rellenados), y
  * **no** terminan en ":" (eso son etiquetas, no valores).

Encima de esa detección automática se aplica una capa de ETIQUETAS CURADAS:
un mapa de ancla (x, y) -> nombre humano en español, para que la web muestre
"Nombre(s)", "CURP", "Monto Solicitado"... en vez de coordenadas. Si un valor
no coincide con ninguna ancla, se intenta emparejar con la etiqueta que tiene
justo encima en la misma columna; si tampoco, se usa un nombre genérico.

Así el sistema es a la vez robusto (detección por estilo) y legible (labels).

Formatos soportados
-------------------
La maquetación es la misma en renovación (Iceni) y en compra de deuda / nuevo
(JasperReports), pero hay copias escaladas a tamaño carta. Antes de comparar
con las anclas, todas las posiciones se NORMALIZAN a la maquetación de
referencia (609×850) usando como testigo el título "Carta de Libranza".

"Préstamos por liquidar" puede tener varios bloques (uno por préstamo que se
compra); cada bloque baja 66 pt respecto al anterior.
"""

from __future__ import annotations

from . import metrics

# Testigo de maquetación: título "Carta de Libranza" en la referencia.
_REF_TITLE = "Carta de Libranza"
_REF_TITLE_X = 262.55
_REF_TITLE_Y = 707.47
_REF_TITLE_SIZE = 10.0

_PENSIONADO = "Datos del Pensionado"
_ENTIDAD = "Datos de Entidad Financiera"
_CONDICIONES = "Condiciones del Préstamo"
_LIQUIDAR = "Préstamos por liquidar"

# Ancla (x0 redondeado, y redondeado) -> (clave, etiqueta legible, sección).
# Tomadas del PDF de referencia; la maquetación es idéntica en todos.
_ANCHORS = {
    # Datos del Pensionado
    (52, 616): ("nombre", "Nombre(s)", _PENSIONADO),
    (227, 616): ("primer_apellido", "Primer Apellido", _PENSIONADO),
    (402, 616): ("segundo_apellido", "Segundo Apellido", _PENSIONADO),
    (52, 586): ("curp", "CURP", _PENSIONADO),
    (227, 586): ("nss", "NSS", _PENSIONADO),
    (402, 586): ("telefono_movil", "Teléfono Móvil", _PENSIONADO),
    (52, 556): ("correo", "Correo Electrónico", _PENSIONADO),
    (402, 556): ("ooad", "OOAD de Adscripción", _PENSIONADO),
    # Datos de Entidad Financiera
    (52, 503): ("ef_nombre", "Nombre Comercial", _ENTIDAD),
    (227, 502): ("ef_telefono", "Teléfono (Entidad)", _ENTIDAD),
    (402, 502): ("ef_correo", "Correo electrónico (Entidad)", _ENTIDAD),
    # Condiciones del Préstamo
    (52, 431): ("cat", "CAT con IVA", _CONDICIONES),
    (183, 431): ("monto", "Monto Solicitado", _CONDICIONES),
    (314, 431): ("descuento_mensual", "Descuento Mensual", _CONDICIONES),
    (445, 431): ("plazo", "Plazo", _CONDICIONES),
    (52, 401): ("importe_total", "Importe Total a Pagar", _CONDICIONES),
    (183, 401): ("fecha_primer_descuento", "Fecha del Primer Descuento", _CONDICIONES),
    (314, 401): ("vigencia_folio", "Fecha de Vigencia del Folio", _CONDICIONES),
    (445, 401): ("importe_recibir", "Importe a recibir", _CONDICIONES),
}

# Valores centrados en su celda: se reconocen por su CENTRO (la X inicial
# depende del largo del texto) y al editarlos se recentran.
_CENTERED_ANCHORS = {
    (172.5, 670): ("fecha", "Fecha", "Encabezado"),
    (442.5, 670): ("folio", "Folio de Negocio", "Encabezado"),
}

# Préstamos por liquidar: dos filas por bloque; el bloque k (desde 0) está
# _PL_STEP * k puntos más abajo que el primero.
_PL_STEP = 66.0
_PL_ROWS = (
    (350.0, {
        50: ("entidad", "Entidad Financiera"),
        176: ("cat", "CAT con IVA"),
        307: ("monto", "Monto Solicitado"),
        438: ("descuento", "Descuento mensual"),
    }),
    (318.0, {
        176: ("descuentos_plazos", "Descuentos / Plazos"),
        307: ("saldo_capital", "Saldo capital"),
        438: ("clabe", "CLABE de la Entidad"),
    }),
)
_PL_TOP = 360.0  # por encima de esto no hay préstamos por liquidar

_ANCHOR_TOL = 4.0  # holgura en puntos para casar una posición con un ancla


class _View:
    """Un run visto en coordenadas de la maquetación de referencia."""

    __slots__ = ("run", "x0", "y", "size", "text", "bold")

    def __init__(self, run, x0, y, size):
        self.run = run
        self.x0 = x0
        self.y = y
        self.size = size
        self.text = run.text
        self.bold = run.bold


def _normalize(runs):
    """Lleva los runs a la maquetación de referencia usando el título como testigo."""
    scale, dx, dy = 1.0, 0.0, 0.0
    for run in runs:
        if run.bold and run.text.strip() == _REF_TITLE:
            scale = (run.size / _REF_TITLE_SIZE) or 1.0
            dx = run.x0 - _REF_TITLE_X * scale
            dy = run.y - _REF_TITLE_Y * scale
            break
    return [
        _View(r, (r.x0 - dx) / scale, (r.y - dy) / scale, r.size / scale)
        for r in runs
    ]


def _match_anchor(v):
    for (ax, ay), match in _ANCHORS.items():
        if abs(v.x0 - ax) <= _ANCHOR_TOL and abs(v.y - ay) <= _ANCHOR_TOL:
            return match
    center = v.x0 + metrics.text_width(v.text, v.size, v.bold) / 2.0
    for (cx, cy), match in _CENTERED_ANCHORS.items():
        if abs(center - cx) <= _ANCHOR_TOL and abs(v.y - cy) <= _ANCHOR_TOL:
            return match
    return None


def _match_liquidar(v):
    """(bloque 1..n, clave, etiqueta) si el valor cae en Préstamos por liquidar."""
    if v.y > _PL_TOP:
        return None
    for row_y, cols in _PL_ROWS:
        k = round((row_y - v.y) / _PL_STEP)
        if k < 0 or abs(v.y - (row_y - k * _PL_STEP)) > _ANCHOR_TOL:
            continue
        for cx, (key, label) in cols.items():
            if abs(v.x0 - cx) <= _ANCHOR_TOL:
                return k + 1, key, label
    return None


def _label_above(v, views):
    """Etiqueta (run regular acabado en ':') justo encima, en la misma columna."""
    best = None
    best_dy = 99.0
    for other in views:
        if other.bold or not other.text.strip().endswith(":"):
            continue
        dy = other.y - v.y
        if 6 <= dy <= 20 and abs(other.x0 - v.x0) <= 8:
            if dy < best_dy:
                best_dy = dy
                best = other.text.strip().rstrip(":")
    return best


def _is_value(v) -> bool:
    """¿Es un valor editable? Negrita, tamaño ~8, y no es una etiqueta."""
    text = v.text.strip()
    if not text:
        return False
    if not v.bold or abs(v.size - 8.0) > 0.6:
        return False
    if text.endswith(":"):
        return False
    return True


def list_fields(runs):
    """Devuelve la lista de campos editables detectados.

    Cada campo: {id, key, label, section, align, value, x, y, size}. `id` es el
    índice del run en la lista `runs`, que es lo que espera
    `core.apply_changes`. `x`/`y` están en la maquetación de referencia.
    """
    views = _normalize(runs)
    candidates = [(i, v) for i, v in enumerate(views) if _is_value(v)]
    liquidar = {i: _match_liquidar(v) for i, v in candidates}
    n_blocks = max((m[0] for m in liquidar.values() if m), default=0)

    fields = []
    seen_keys = {}
    for i, v in candidates:
        align = "left"
        match = _match_anchor(v)
        if match:
            key, label, section = match
            if (key, label, section) in _CENTERED_ANCHORS.values():
                align = "center"
        elif liquidar[i]:
            block, key, label = liquidar[i]
            if n_blocks > 1:
                key = f"pl{block}_{key}"
                label = f"{label} (a liquidar {block})"
                section = f"{_LIQUIDAR} · Préstamo {block}"
            else:
                key = f"pl_{key}"
                label = f"{label} (a liquidar)"
                section = _LIQUIDAR
        else:
            label = _label_above(v, views) or "Campo"
            key = f"campo_{i}"
            section = "Otros campos"
        # desambiguar claves repetidas (p.ej. dos "BANCO BANCREA")
        if key in seen_keys:
            seen_keys[key] += 1
            key = f"{key}_{seen_keys[key]}"
        else:
            seen_keys[key] = 0
        fields.append({
            "id": i,
            "key": key,
            "label": label,
            "section": section,
            "align": align,
            "value": v.text,
            "x": round(v.x0, 1),
            "y": round(v.y, 1),
            "size": round(v.size, 2),
        })
    # orden de lectura: de arriba a abajo, izquierda a derecha
    fields.sort(key=lambda f: (-f["y"], f["x"]))
    return fields
