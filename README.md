# Editor de Carta de Libranza

Editor web del **texto** de las Cartas de Libranza (PDF) sin alterar el estilo:
subes un PDF, se muestran sus campos, eliges cuáles cambiar y obtienes el mismo
PDF con los nuevos valores.

**Corre 100% en el navegador** con [Pyodide](https://pyodide.org) (Python
compilado a WebAssembly). No hay servidor ni backend: el PDF **nunca sale de tu
equipo**, no se sube a ningún sitio y no se almacena nada. Por eso puede
publicarse tal cual en GitHub Pages.

## Formatos soportados

| Formato | Generador | Cómo dibuja el texto |
|---|---|---|
| Renovación | Iceni Infix | Letra por letra: un `Tm` (escala 8) + `Tf 1` + `Tj` por glifo |
| Compra de deuda / nuevo préstamo | JasperReports (+ pdf-lib) | Cadena completa: `Tm` escala 1 + `Tf 8` + un `Tj` por valor |
| Copia escalada a carta | JasperReports + otro editor | Igual que la anterior dentro de un `cm` 0.93, con valores superpuestos |

En los tres la maquetación es la misma, y "Préstamos por liquidar" puede traer
uno o varios bloques (uno por préstamo que se compra).

## Cómo funciona

En la renovación el PDF dibuja cada valor **letra por letra**, con la posición
X absoluta de cada glifo; en compra de deuda cada valor es una cadena completa.
El motor detecta cuál es cada caso y reescribe el valor con la misma forma.

El motor (`engine/`, Python puro sobre `pypdf`):

1. Parsea el *content stream* a operaciones (`pypdf.ContentStream`).
2. Recorre las operaciones siguiendo el estado gráfico (fuente y tamaño vía
   `Tf`, posición vía `Tm`/`Td`, escala de página vía `cm`) para saber qué
   carácter se pinta, dónde y a qué tamaño (`Tf × Tm × CTM`).
3. Agrupa glifos contiguos en *runs* = los valores visibles.
4. Normaliza las posiciones a la maquetación de referencia (testigo: el título
   "Carta de Libranza"), detecta los campos editables (negrita, tamaño 8) y les
   asigna etiqueta y sección con una plantilla fija (`engine/template.py`).
5. Al reemplazar:
   - **cadena completa**: reescribe en su sitio el `Tj` (y el `Tm` si hay que
     recentrar), sin añadir operaciones;
   - **letra por letra**: elimina los glifos viejos y emite nuevos
     `Tm`/`Tf`/`Tj`, **recalculando la X de cada letra** con las métricas de
     Helvetica (`engine/metrics.py`).

   Fecha y Folio están centrados en su celda y se recentran. Fuente, tamaño,
   color y posición Y no se tocan, y el content stream viejo no se conserva en
   el archivo.

En la web, `index.html` carga Pyodide, instala `pypdf`, monta los archivos de
`engine/` y llama a `get_fields` / `apply_changes` directamente desde el
navegador.

## Estructura

```
index.html      Interfaz web + arranque de Pyodide (entrada de GitHub Pages)
.nojekyll       Evita que Jekyll oculte archivos como engine/__init__.py
engine/
  core.py       Extracción + reemplazo sobre el content stream
  metrics.py    Anchos de glifo de Helvetica / Helvetica-Bold
  template.py   Campos editables y sus etiquetas
tests/          Pruebas del motor (se ejecutan en local con Python)
  sample.pdf                 Renovación (Iceni), anonimizada
  sample_compra_deuda.pdf    Compra de deuda con 2 préstamos, anonimizada
  sample_carta_escalada.pdf  Copia escalada a carta, anonimizada
```

## Probar en local

Como es estático, basta un servidor de archivos (necesario para que el
navegador pueda `fetch` los `.py`; abrir el `index.html` con `file://` no
funciona):

```bash
python3 -m http.server 8000
# abre http://localhost:8000
```

## Tests del motor (en local)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest -q
```

## Publicar en GitHub Pages

1. Sube el repo (rama `main`).
2. En GitHub: **Settings → Pages → Build and deployment → Source: Deploy from a
   branch**, rama `main`, carpeta `/ (root)`.
3. La página quedará disponible en la URL que indique GitHub Pages.

## Notas / límites

- La plantilla está calibrada para la **página 1** de la Carta de Libranza
  (renovación y compra de deuda / nuevo). Si cambia la maquetación, hay que
  actualizar las anclas de `engine/template.py`. Si un PDF no se reconoce, la
  web lo indica en lugar de mostrar el formulario.
- Los fixtures de `tests/` solo llevan datos dummy: no subir cartas reales al
  repo (es público).
- La primera carga descarga Pyodide + pypdf (unos MB); tarda unos segundos. Las
  siguientes usan la caché del navegador.
- Los caracteres deben existir en la codificación WinAnsi (latin-1). El texto en
  español habitual está cubierto.
