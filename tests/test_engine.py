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
