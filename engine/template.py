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
"""

from __future__ import annotations

# Ancla (x0 redondeado, y redondeado) -> (clave, etiqueta legible).
# Tomadas del PDF de referencia; la maquetación es idéntica en todos.
_ANCHORS = {
    (132, 670): ("fecha", "Fecha"),
    (414, 670): ("folio", "Folio de Negocio"),
    # Datos del Pensionado
    (52, 616): ("nombre", "Nombre(s)"),
    (227, 616): ("primer_apellido", "Primer Apellido"),
    (402, 616): ("segundo_apellido", "Segundo Apellido"),
    (52, 586): ("curp", "CURP"),
    (227, 586): ("nss", "NSS"),
    (402, 586): ("telefono_movil", "Teléfono Móvil"),
    (52, 556): ("correo", "Correo Electrónico"),
    (402, 556): ("ooad", "OOAD de Adscripción"),
    # Datos de Entidad Financiera
    (52, 503): ("ef_nombre", "Nombre Comercial"),
    (227, 502): ("ef_telefono", "Teléfono (Entidad)"),
    (402, 502): ("ef_correo", "Correo electrónico (Entidad)"),
    # Condiciones del Préstamo
    (52, 431): ("cat", "CAT con IVA"),
    (183, 431): ("monto", "Monto Solicitado"),
    (314, 431): ("descuento_mensual", "Descuento Mensual"),
    (445, 431): ("plazo", "Plazo"),
    (52, 401): ("importe_total", "Importe Total a Pagar"),
    (183, 401): ("fecha_primer_descuento", "Fecha del Primer Descuento"),
    (314, 401): ("vigencia_folio", "Fecha de Vigencia del Folio"),
    (445, 401): ("importe_recibir", "Importe a recibir"),
    # Préstamos por liquidar
    (50, 350): ("pl_entidad", "Entidad Financiera (a liquidar)"),
    (176, 350): ("pl_cat", "CAT con IVA (a liquidar)"),
    (307, 350): ("pl_monto", "Monto Solicitado (a liquidar)"),
    (438, 350): ("pl_descuento", "Descuento mensual (a liquidar)"),
    (176, 318): ("pl_descuentos_plazos", "Descuentos / Plazos"),
    (307, 318): ("pl_saldo_capital", "Saldo capital"),
    (438, 318): ("pl_clabe", "CLABE de la Entidad"),
}

_ANCHOR_TOL = 4.0  # holgura en puntos para casar una posición con un ancla


def _match_anchor(x: float, y: float):
    for (ax, ay), (key, label) in _ANCHORS.items():
        if abs(x - ax) <= _ANCHOR_TOL and abs(y - ay) <= _ANCHOR_TOL:
            return key, label
    return None


def _label_above(run, runs):
    """Etiqueta (run regular acabado en ':') justo encima, en la misma columna."""
    best = None
    best_dy = 99.0
    for other in runs:
        if other.bold or not other.text.strip().endswith(":"):
            continue
        dy = other.y - run.y
        if 6 <= dy <= 20 and abs(other.x0 - run.x0) <= 8:
            if dy < best_dy:
                best_dy = dy
                best = other.text.strip().rstrip(":")
    return best


def _is_value(run) -> bool:
    """¿Es un valor editable? Negrita, tamaño ~8, y no es una etiqueta."""
    text = run.text.strip()
    if not text:
        return False
    if not run.bold or abs(run.size - 8.0) > 0.6:
        return False
    if text.endswith(":"):
        return False
    return True


def list_fields(runs):
    """Devuelve la lista de campos editables detectados.

    Cada campo: {id, key, label, value, x, y, size}. `id` es el índice del run
    en la lista `runs`, que es lo que espera `core.apply_changes`.
    """
    fields = []
    seen_keys = {}
    for i, run in enumerate(runs):
        if not _is_value(run):
            continue
        match = _match_anchor(run.x0, run.y)
        if match:
            key, label = match
        else:
            label = _label_above(run, runs) or "Campo"
            key = f"campo_{i}"
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
            "value": run.text,
            "x": round(run.x0, 1),
            "y": round(run.y, 1),
            "size": run.size,
        })
    # orden de lectura: de arriba a abajo, izquierda a derecha
    fields.sort(key=lambda f: (-f["y"], f["x"]))
    return fields
