"""Tests del motor: extracción de campos y reemplazo preservando estilo."""

from pathlib import Path

import pypdf

import engine

SAMPLE = Path(__file__).parent / "sample.pdf"


def _pdf():
    return SAMPLE.read_bytes()


def test_extract_expected_fields():
    fields = engine.get_fields(_pdf())
    by_label = {f["label"]: f["value"] for f in fields}
    # Debe detectar los campos clave con su valor exacto del PDF de referencia.
    assert by_label["Nombre(s)"] == "JUAN CARLOS"
    assert by_label["Primer Apellido"] == "LOPEZ"
    assert by_label["Segundo Apellido"] == "GARCIA"
    assert by_label["CURP"] == "XXXX000000XXXXXX00"
    assert by_label["Monto Solicitado"] == "$ 100,000.00"  # caso string-completo
    assert by_label["Correo Electrónico"] == "ejemplo@correo.com"
    assert len(fields) >= 25


def test_apply_changes_updates_only_targets():
    pdf = _pdf()
    fields = engine.get_fields(pdf)
    ids = {f["label"]: f["id"] for f in fields}

    changes = {
        ids["Nombre(s)"]: "PEDRO ANTONIO",
        ids["Primer Apellido"]: "GARCIA",
        ids["Monto Solicitado"]: "$ 999,999.99",
    }
    out = engine.apply_changes(pdf, changes)

    assert out.startswith(b"%PDF")
    new_fields = {f["label"]: f["value"] for f in engine.get_fields(out)}
    assert new_fields["Nombre(s)"] == "PEDRO ANTONIO"
    assert new_fields["Primer Apellido"] == "GARCIA"
    assert new_fields["Monto Solicitado"] == "$ 999,999.99"
    # Campos no tocados permanecen idénticos.
    assert new_fields["Segundo Apellido"] == "GARCIA"
    assert new_fields["CURP"] == "XXXX000000XXXXXX00"


def test_style_is_preserved():
    """Las fuentes del documento no deben cambiar tras el reemplazo."""
    pdf = _pdf()
    fields = engine.get_fields(pdf)
    ids = {f["label"]: f["id"] for f in fields}
    out = engine.apply_changes(pdf, {ids["Nombre(s)"]: "UN NOMBRE DISTINTO Y MAS LARGO"})

    def fonts(data):
        r = pypdf.PdfReader(__import__("io").BytesIO(data))
        return {str(v.get_object().get("/BaseFont")) for v in r.pages[0]["/Resources"]["/Font"].values()}

    assert fonts(pdf) == fonts(out)


def test_page_count_unchanged():
    import io
    pdf = _pdf()
    fields = engine.get_fields(pdf)
    out = engine.apply_changes(pdf, {fields[0]["id"]: "X"})
    assert len(pypdf.PdfReader(io.BytesIO(out)).pages) == len(pypdf.PdfReader(io.BytesIO(pdf)).pages)


# --- Compra de deuda / nuevo (JasperReports) --------------------------------
# Fixtures anonimizados: solo página 1, todos los valores son dummy.

COMPRA_DEUDA = Path(__file__).parent / "sample_compra_deuda.pdf"   # 2 préstamos por liquidar
ESCALADA = Path(__file__).parent / "sample_carta_escalada.pdf"     # escalada a carta (cm 0.93)


def _streams(data):
    """Todo el contenido decodificado de los streams del PDF."""
    import io
    r = pypdf.PdfReader(io.BytesIO(data))
    blob = b""
    for i in range(1, int(r.trailer["/Size"])):
        try:
            obj = r.get_object(i)
        except Exception:
            continue
        if obj is not None and hasattr(obj, "get_data"):
            blob += obj.get_data()
    return blob


def test_compra_deuda_fields():
    fields = engine.get_fields(COMPRA_DEUDA.read_bytes())
    by_label = {f["label"]: f["value"] for f in fields}
    assert by_label["Nombre(s)"] == "JUAN CARLOS"
    assert by_label["CURP"] == "XXXX000000XXXXXX00"
    assert by_label["Fecha"] == "02 de enero de 2025"
    assert by_label["Monto Solicitado"] == "$ 100,000.00"
    # Un bloque por préstamo que se compra.
    assert by_label["Entidad Financiera (a liquidar 1)"] == "ENTIDAD EJEMPLO"
    assert by_label["CLABE de la Entidad (a liquidar 2)"] == "000000000000000000"
    assert len(fields) == 35
    assert all(f["size"] == 8.0 for f in fields)


def test_compra_deuda_apply_changes():
    pdf = COMPRA_DEUDA.read_bytes()
    fields = engine.get_fields(pdf)
    ids = {f["label"]: f["id"] for f in fields}
    out = engine.apply_changes(pdf, {
        ids["Nombre(s)"]: "MARIA DE LOS ANGELES",
        ids["Monto Solicitado (a liquidar 2)"]: "$ 1,234.56",
    })
    new = {f["label"]: f["value"] for f in engine.get_fields(out)}
    assert new["Nombre(s)"] == "MARIA DE LOS ANGELES"
    assert new["Monto Solicitado (a liquidar 2)"] == "$ 1,234.56"
    assert new["Monto Solicitado (a liquidar 1)"] == "$ 50,000.00"
    assert new["Primer Apellido"] == "LOPEZ"
    # Mismo formato que el generador: la cadena completa en un solo Tj, y el
    # valor viejo no queda escondido en el archivo.
    blob = _streams(out)
    assert b"(MARIA DE LOS ANGELES) Tj" in blob
    assert b"JUAN CARLOS" not in blob


def test_centered_fields_keep_center():
    from engine import metrics
    pdf = COMPRA_DEUDA.read_bytes()
    before = {f["key"]: f for f in engine.get_fields(pdf)}
    out = engine.apply_changes(pdf, {
        before["fecha"]["id"]: "28 de septiembre de 2025",
        before["folio"]["id"]: "1-2",
    })
    after = {f["key"]: f for f in engine.get_fields(out)}
    for key in ("fecha", "folio"):
        assert before[key]["align"] == "center"
        c0 = before[key]["x"] + metrics.text_width(before[key]["value"], 8, True) / 2
        c1 = after[key]["x"] + metrics.text_width(after[key]["value"], 8, True) / 2
        assert abs(c0 - c1) < 0.2


def test_scaled_layout():
    """Copia escalada a tamaño carta con valores superpuestos fuera de la escala."""
    pdf = ESCALADA.read_bytes()
    fields = engine.get_fields(pdf)
    by_label = {f["label"]: f["value"] for f in fields}
    assert by_label["Nombre(s)"] == "JUAN CARLOS"
    assert by_label["Folio de Negocio"] == "00000000000-0"
    assert by_label["Importe a recibir"] == "$ 40,000.00"
    assert len(fields) == 21
    ids = {f["label"]: f["id"] for f in fields}
    out = engine.apply_changes(pdf, {ids["Nombre(s)"]: "PEDRO", ids["Plazo"]: "48 meses"})
    new = {f["label"]: f["value"] for f in engine.get_fields(out)}
    assert new["Nombre(s)"] == "PEDRO"
    assert new["Plazo"] == "48 meses"
    assert new["CURP"] == "XXXX000000XXXXXX00"
