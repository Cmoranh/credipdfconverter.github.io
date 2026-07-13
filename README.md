# Editor de Carta de Libranza

Editor web del **texto** de las Cartas de Libranza (PDF) sin alterar el estilo:
subes un PDF, se muestran sus campos, eliges cuáles cambiar y obtienes el mismo
PDF con los nuevos valores.

**Corre 100% en el navegador** con [Pyodide](https://pyodide.org) (Python
compilado a WebAssembly). No hay servidor ni backend: el PDF **nunca sale de tu
equipo**, no se sube a ningún sitio y no se almacena nada. Por eso puede
publicarse tal cual en GitHub Pages.

## Cómo funciona

El PDF (generado por Iceni Infix) dibuja cada valor **letra por letra**, con la
posición X absoluta de cada glifo. Por eso "cambiar el string" no es una
sustitución de texto plano: hay que recolocar cada letra nueva.

El motor (`engine/`, Python puro sobre `pypdf`):

1. Parsea el *content stream* a operaciones (`pypdf.ContentStream`).
2. Recorre las operaciones siguiendo el estado gráfico (fuente vía `Tf`,
   posición vía `Tm`) para saber qué carácter se pinta y dónde.
3. Agrupa glifos contiguos en *runs* = los valores visibles.
4. Detecta los campos editables (negrita, tamaño 8) y les asigna una etiqueta
   legible con una plantilla fija (`engine/template.py`).
5. Al reemplazar, elimina las operaciones del valor viejo y emite nuevas
   `Tm`/`Tf`/`Tj`, **recalculando la X de cada letra** con las métricas de
   Helvetica (`engine/metrics.py`). Fuente, tamaño, color y posición Y no se
   tocan.

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

- La plantilla está calibrada para la **página 1** de la Carta de Libranza tal
  como la genera el emisor actual. Si cambia la maquetación, hay que actualizar
  las anclas de `engine/template.py`.
- La primera carga descarga Pyodide + pypdf (unos MB); tarda unos segundos. Las
  siguientes usan la caché del navegador.
- Los caracteres deben existir en la codificación WinAnsi (latin-1). El texto en
  español habitual está cubierto.
