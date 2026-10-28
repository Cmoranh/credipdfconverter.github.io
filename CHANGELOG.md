# Cambios

Versionado [semántico](https://semver.org/lang/es/): `feat` sube la versión
menor, `fix`/`style` la de parche. La versión se muestra en la cabecera de la
web y vive en `engine/__init__.py` (`__version__`), `index.html` y aquí; el
test `test_version_in_sync` comprueba que coincidan.

## 1.3.0 — 2026-10-28

- Formulario agrupado por secciones (Encabezado, Pensionado, Entidad,
  Condiciones, Préstamos por liquidar).
- Aviso de "formato de PDF no reconocido" en lugar de un formulario vacío.
- Versión visible en la cabecera, enlazada a este archivo.

## 1.2.0 — 2026-10-28

- Soporte de cartas de **compra de deuda / nuevo préstamo** (JasperReports):
  valores como cadena completa, reescritos en su sitio.
- Soporte de copias escaladas a tamaño carta (normalización con el título
  "Carta de Libranza" como testigo).
- "Préstamos por liquidar" con uno o varios bloques.
- Fecha y Folio se recentran al editarlos.
- Fixtures de prueba anonimizados para los nuevos formatos.

## 1.1.1 — 2026-07-13

- Identidad visual de Banco Bancrea (colores, logo y barra de acento).

## 1.1.0 — 2026-07-13

- Sitio 100% estático con Pyodide para GitHub Pages; se elimina el backend
  FastAPI. El PDF se procesa en el navegador.

## 1.0.0 — 2026-07-10

- Primera versión: editor de Carta de Libranza (renovación). Extrae los
  campos, edita el texto conservando el estilo y regenera el PDF sin
  almacenar nada.
