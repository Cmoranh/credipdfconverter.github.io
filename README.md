# Editor de Carta de Libranza

Sistema web para editar el **texto** de las Cartas de Libranza (PDF) sin alterar
el estilo: se sube un PDF, se muestran sus campos, eliges cuáles cambiar y se
devuelve el mismo PDF con los nuevos valores. **No se almacena nada** — el PDF
entra y sale en memoria durante la petición.

## Cómo funciona

El PDF (generado por Iceni Infix) dibuja cada valor **letra por letra**, con la
posición X absoluta de cada glifo. Por eso "cambiar el string" no es una
sustitución de texto plano: hay que recolocar cada letra nueva.

El motor (`engine/`):

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

## Estructura

```
engine/
  core.py       Extracción + reemplazo sobre el content stream
  metrics.py    Anchos de glifo de Helvetica / Helvetica-Bold
  template.py   Campos editables y sus etiquetas
app.py          API FastAPI (/api/extract, /api/apply)
web/index.html  Interfaz web (subir, previsualizar, editar, descargar)
tests/          Pruebas del motor
```

## Ejecutar

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --reload --port 8000
```

Abre <http://localhost:8000>.

## Tests

```bash
pip install pytest
pytest -q
```

## Notas / límites

- La plantilla está calibrada para la **página 1** de la Carta de Libranza tal
  como la genera el emisor actual. Si cambia la maquetación, hay que actualizar
  las anclas de `engine/template.py`.
- Solo se procesa la primera página (es la única con datos variables).
- Los caracteres deben existir en la codificación WinAnsi (latin-1). El texto
  en español habitual está cubierto.
