"""
Métricas de anchura (advance widths) de las fuentes estándar Helvetica.

Los valores están en unidades de 1/1000 de em (el estándar de los AFM de
Adobe). El ancho real de un glifo = width[char] / 1000 * font_size.

Se usan para recalcular la posición X de cada letra cuando se reemplaza un
valor, de forma que el texto nuevo mantenga un espaciado natural — igual que
lo tendría el generador original. Helvetica y Helvetica-Bold comparten muchos
anchos pero no todos, por eso hay dos tablas.

Las claves usan el carácter ya decodificado (latin-1 / WinAnsi). Los acentos
frecuentes en español se incluyen explícitamente.
"""

# Helvetica (regular) — WinAnsi
_HELVETICA = {
    ' ': 278, '!': 278, '"': 355, '#': 556, '$': 556, '%': 889, '&': 667,
    "'": 191, '(': 333, ')': 333, '*': 389, '+': 584, ',': 278, '-': 333,
    '.': 278, '/': 278, '0': 556, '1': 556, '2': 556, '3': 556, '4': 556,
    '5': 556, '6': 556, '7': 556, '8': 556, '9': 556, ':': 278, ';': 278,
    '<': 584, '=': 584, '>': 584, '?': 556, '@': 1015, 'A': 667, 'B': 667,
    'C': 722, 'D': 722, 'E': 667, 'F': 611, 'G': 778, 'H': 722, 'I': 278,
    'J': 500, 'K': 667, 'L': 556, 'M': 833, 'N': 722, 'O': 778, 'P': 667,
    'Q': 778, 'R': 722, 'S': 667, 'T': 611, 'U': 722, 'V': 667, 'W': 944,
    'X': 667, 'Y': 667, 'Z': 611, '[': 278, '\\': 278, ']': 278, '^': 469,
    '_': 556, '`': 333, 'a': 556, 'b': 556, 'c': 500, 'd': 556, 'e': 556,
    'f': 278, 'g': 556, 'h': 556, 'i': 222, 'j': 222, 'k': 500, 'l': 222,
    'm': 833, 'n': 556, 'o': 556, 'p': 556, 'q': 556, 'r': 333, 's': 500,
    't': 278, 'u': 556, 'v': 500, 'w': 722, 'x': 500, 'y': 500, 'z': 500,
    '{': 334, '|': 260, '}': 334, '~': 584,
    # Acentuadas frecuentes en español (WinAnsi)
    'á': 556, 'é': 556, 'í': 278, 'ó': 556, 'ú': 556, 'ñ': 556, 'ü': 556,
    'Á': 667, 'É': 667, 'Í': 278, 'Ó': 778, 'Ú': 722, 'Ñ': 722, 'Ü': 722,
    '¿': 611, '¡': 333, 'º': 365, 'ª': 370, '°': 400,
}

# Helvetica-Bold — WinAnsi
_HELVETICA_BOLD = {
    ' ': 278, '!': 333, '"': 474, '#': 556, '$': 556, '%': 889, '&': 722,
    "'": 238, '(': 333, ')': 333, '*': 389, '+': 584, ',': 278, '-': 333,
    '.': 278, '/': 278, '0': 556, '1': 556, '2': 556, '3': 556, '4': 556,
    '5': 556, '6': 556, '7': 556, '8': 556, '9': 556, ':': 333, ';': 333,
    '<': 584, '=': 584, '>': 584, '?': 611, '@': 975, 'A': 722, 'B': 722,
    'C': 722, 'D': 722, 'E': 667, 'F': 611, 'G': 778, 'H': 722, 'I': 278,
    'J': 556, 'K': 722, 'L': 611, 'M': 833, 'N': 722, 'O': 778, 'P': 667,
    'Q': 778, 'R': 722, 'S': 667, 'T': 611, 'U': 722, 'V': 667, 'W': 944,
    'X': 667, 'Y': 667, 'Z': 611, '[': 333, '\\': 278, ']': 333, '^': 584,
    '_': 556, '`': 333, 'a': 556, 'b': 611, 'c': 556, 'd': 611, 'e': 556,
    'f': 333, 'g': 611, 'h': 611, 'i': 278, 'j': 278, 'k': 556, 'l': 278,
    'm': 889, 'n': 611, 'o': 611, 'p': 611, 'q': 611, 'r': 389, 's': 556,
    't': 333, 'u': 611, 'v': 556, 'w': 778, 'x': 556, 'y': 556, 'z': 500,
    '{': 389, '|': 280, '}': 389, '~': 584,
    'á': 556, 'é': 556, 'í': 278, 'ó': 611, 'ú': 611, 'ñ': 611, 'ü': 611,
    'Á': 722, 'É': 667, 'Í': 278, 'Ó': 778, 'Ú': 722, 'Ñ': 722, 'Ü': 722,
    '¿': 611, '¡': 333, 'º': 365, 'ª': 370, '°': 400,
}

_DEFAULT_WIDTH = 556  # ancho de reserva para un glifo desconocido


def is_bold(font_name: str) -> bool:
    """Heurística: ¿el recurso de fuente corresponde a una variante Bold?

    En este documento las fuentes se referencian como /F1, /F2, /F3. El mapeo
    real fuente->negrita se resuelve en core.py leyendo el diccionario de
    fuentes de la página; esta función es el fallback por nombre.
    """
    n = font_name.lower()
    return "bold" in n or n.endswith("b")


def char_width(char: str, font_size: float, bold: bool = False) -> float:
    """Ancho de avance de un carácter, en unidades de usuario del PDF."""
    table = _HELVETICA_BOLD if bold else _HELVETICA
    return table.get(char, _DEFAULT_WIDTH) / 1000.0 * font_size


def text_width(text: str, font_size: float, bold: bool = False) -> float:
    """Ancho total de una cadena."""
    return sum(char_width(c, font_size, bold) for c in text)
