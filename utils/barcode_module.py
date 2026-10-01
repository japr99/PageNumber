"""
Módulo de códigos de barras vectoriales.
Genera rects (x, y, w, h) desde datos encoded de python-barcode.
Sin dependencias de imagen ni SVG.
"""

from __future__ import annotations

import functools
import math
from typing import List, Optional, Tuple

from barcode.codex import Code128 as _Code128
from barcode.codex import Code39 as _Code39
from barcode.ean import EAN13 as _EAN13
import qrcode as _qrcode
import qrcode.constants as _qrconst
import fitz
from pdf417gen import encode as _pdf417_encode
from pdf417gen.compaction.byte import compact_bytes as _pdf417_compact_bytes
from pdf417gen.encoding import encode_rows as _pdf417_encode_rows
from pdf417gen.encoding import get_padding as _pdf417_get_padding
from pdf417gen.encoding import validate_barcode_size as _pdf417_validate_barcode_size
from pdf417gen.error_correction import (
    compute_error_correction_code_words as _pdf417_compute_error_correction_code_words,
)
from pdf417gen import render_image as _pdf417_render
from pdf417gen.rendering import barcode_size as _pdf417_barcode_size
from pdf417gen.rendering import modules as _pdf417_modules
from pdf417gen.util import chunks as _pdf417_chunks
from pdf417gen.util import to_bytes as _pdf417_to_bytes

from i18n import t

# ── GS1 DataMatrix (optional) ──
try:
    from pylibdmtx.pylibdmtx import encode as _dm_encode
    from PIL import Image as _PILImage

    _HAS_DATAMATRIX = True
except ImportError:
    _HAS_DATAMATRIX = False

# ── EAN-13 ──
EAN13_TOTAL_MODULES = 95
EAN13_GUARD_MODULES = {0, 2, 46, 48, 92, 94}

# ── EAN-8 ──
# L-codes (same parity as EAN-13 A-set)
_EAN8_L_CODES = {
    "0": "0001101",
    "1": "0011001",
    "2": "0010011",
    "3": "0111101",
    "4": "0100011",
    "5": "0110001",
    "6": "0101111",
    "7": "0111011",
    "8": "0110111",
    "9": "0001011",
}
# R-codes (bitwise complement of L)
_EAN8_R_CODES = {
    "0": "1110010",
    "1": "1100110",
    "2": "1101100",
    "3": "1000010",
    "4": "1011100",
    "5": "1001110",
    "6": "1010000",
    "7": "1000100",
    "8": "1001000",
    "9": "1110100",
}

EAN8_TOTAL_MODULES = 67
EAN8_GUARD_MODULES = {0, 2, 32, 34, 64, 66}

# UPC-E: guards izquierdo "101" (0,2) y derecho "010101" (46,48,50). 51 modulos.
UPCE_TOTAL_MODULES = 51
UPCE_GUARD_MODULES = {0, 2, 46, 48, 50}

# Cada patrón en CODES128 son 11 módulos (1/0 por módulo)
# '1' = barra negra, '0' = espacio blanco
_MODULES_PER_CHAR = 11
_STOP_MODULES = 13  # STOP tiene 11 + trailing '11'


def _pattern_to_rects(
    pattern: str,
    module_width: float,
    bar_height: float,
) -> List[Tuple[float, float, float, float]]:
    rects: List[Tuple[float, float, float, float]] = []
    x: float = 0.0
    i = 0
    while i < len(pattern):
        if pattern[i] == "0":
            x += module_width
            i += 1
            continue
        # count consecutive '1's
        w = module_width
        j = i + 1
        while j < len(pattern) and pattern[j] == "1":
            w += module_width
            j += 1
        rects.append((x, 0.0, w, bar_height))
        x += w
        i = j
    return rects


def encode_code128(value: str) -> Tuple[str, List[int]]:
    """
    Encode a string value using Code128.

    Returns:
        (pattern_str, encoded_codes)
        pattern_str: string of '1' (bar) and '0' (space)
        encoded_codes: list of Code128 code values
    """
    code = _Code128(value)
    patterns = code.build()
    pattern = "".join(patterns)
    return pattern, code.encoded


def get_barcode_rects(
    value: str,
    module_width: float = 0.33,
    bar_height: float = 30.0,
) -> List[Tuple[float, float, float, float]]:
    """
    Generate vector rects for a Code128 barcode.

    Returns rects for BARS ONLY (no quiet zone).
    The first bar starts at rx=0, so total visual width = module_width * len(pattern).

    Args:
        value: Text to encode
        module_width: Width of one module in mm
        bar_height: Height of bars in mm

    Returns:
        List of (x, y, w, h) rects relative to barcode origin.
        x advances left-to-right, y is always 0 (caller applies positioning).
    """
    pattern, _ = encode_code128(value)

    rects = _pattern_to_rects(pattern, module_width, bar_height)
    return rects


def get_barcode_total_width(
    value: str,
    module_width: float = 0.33,
) -> float:
    """Calculate total width of bars (excluding quiet zones) in mm."""
    return get_module_count(value) * module_width


def get_module_count(value: str) -> int:
    """Return total number of modules (bars+spaces) for a Code128 barcode, excluding quiet zones."""
    pattern, _ = encode_code128(value)
    return len(pattern)


QUIET_ZONE_MODULES = 10


def get_quiet_zone_width(module_width: float) -> float:
    """Return width of one quiet zone in mm."""
    return QUIET_ZONE_MODULES * module_width


def validate_code128(value: str) -> Tuple[bool, str]:
    """Validate if a string can be encoded as Code128."""
    try:
        _Code128(value)
        return True, ""
    except Exception as e:
        return False, str(e)


import math


def calcular_ancho_fijo_code128(lista_valores_excel) -> float:
    """
    Calcula el ancho mínimo en mm para Code128 según la columna Excel.
    Usa la fórmula ISO: total_modulos = (11 * C) + 35 + 22.
    Code C comprime dígitos en pares (ceil(largo/2)).
    Code A/B no comprime (cada caracter cuenta 1).
    Mínimo GS1: 40mm.
    """
    texto_mas_largo = max(lista_valores_excel, key=lambda x: len(str(x)))
    cadena = str(texto_mas_largo).strip()
    largo_texto = len(cadena)

    if cadena.isdigit():
        C = math.ceil(largo_texto / 2)
    else:
        C = largo_texto

    total_modulos = (11 * C) + 35 + 22
    # Dimensión X (módulo mínimo) = 0.25mm
    #   - @203 DPI → 2 px
    #   - @300 DPI → 3 px  ← mínimo recomendado (3 px)
    X_MINIMA = 0.25
    ancho_minimo_mm = total_modulos * X_MINIMA

    return max(40.00, round(ancho_minimo_mm, 2))


def validar_longitud_code128(valor: str) -> Tuple[bool, str]:
    """
    Verifica si un valor cabe en Code128 a módulo mínimo 0.25mm
    dentro del ancho máximo 165.10mm (GS1).
    Límite práctico: ~54 chars texto, ~106 dígitos.
    """
    cadena = str(valor).strip()
    if not cadena:
        return True, ""
    try:
        modules = get_module_count(cadena)
    except Exception as e:
        return False, str(e)
    total_modules = modules + 22  # quiet zones (11 each side)
    max_modules = int(165.10 / 0.25)
    if total_modules > max_modules:
        tipo = "dígitos" if cadena.isdigit() else "texto"
        return False, (
            f"El valor tiene {len(cadena)} caracteres ({tipo}) y "
            f"excede el máximo para Code128 "
            f"(texto: ~54, dígitos: ~106)."
        )
    return True, ""


def validar_columna_code128(lista_valores: list) -> list:
    """
    Valida cada valor de una columna Excel contra el límite de caracteres Code128.
    Returns list of (row_index, error_msg) for invalid rows.
    """
    from i18n import t

    errors = []
    for i, v in enumerate(lista_valores):
        v = str(v).strip() if v else ""
        if not v:
            continue
        ok, msg = validar_longitud_code128(v)
        if not ok:
            errors.append((i, msg))
    return errors


# ── Code 39 ──

# Native Code39 chars: A-Z, 0-9, -, ., $, /, +, %, space
_NATIVE_CODE39_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-.$/+% ")

# Full ASCII Code 39 mapping (128 entries): non-native chars → two-char escape
# Reference: USS-39 / ANSI/AIM BC1-1995
#   $A-$Z = CTRL A-Z, %A-%E = CTRL [\]^_, /A-/O = punctuation
#   +A+Z = lowercase, %F-%T = remaining punct, %U = NUL, %V = @
FULL_ASCII_MAP: dict[str, str] = {
    "\x00": "%U",
}
# CTRL A-Z (0x01-0x1A) → $A..$Z
for _i in range(26):
    FULL_ASCII_MAP[chr(0x01 + _i)] = "$" + chr(0x41 + _i)
# CTRL [\]^_ (0x1B-0x1F) → %A..%E
for _k, _v in {0x1B: "%A", 0x1C: "%B", 0x1D: "%C", 0x1E: "%D", 0x1F: "%E"}.items():
    FULL_ASCII_MAP[chr(_k)] = _v
# Space, digits, A-Z native
FULL_ASCII_MAP[" "] = " "
for _c in "0123456789":
    FULL_ASCII_MAP[_c] = _c
for _c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
    FULL_ASCII_MAP[_c] = _c
# Punctuation /A-/O (0x21-0x2F), native overrides for $, -, ., +, /, %
for _k, _v in {
    "!": "/A",
    '"': "/B",
    "#": "/C",
    "$": "$",
    "%": "%",
    "&": "/F",
    "'": "/G",
    "(": "/H",
    ")": "/I",
    "*": "/J",
    "+": "+",
    ",": "/L",
    "-": "-",
    ".": ".",
    "/": "/",
}.items():
    FULL_ASCII_MAP[_k] = _v
# :;<=>?@
for _k, _v in {
    ":": "/Z",
    ";": "%F",
    "<": "%G",
    "=": "%H",
    ">": "%I",
    "?": "%J",
    "@": "%V",
}.items():
    FULL_ASCII_MAP[_k] = _v
# [\]^_ → %K..%O
for _k, _v in {
    "[": "%K",
    "\\": "%L",
    "]": "%M",
    "^": "%N",
    "_": "%O",
}.items():
    FULL_ASCII_MAP[_k] = _v
# ` (0x60)
FULL_ASCII_MAP["`"] = "%W"
# Lowercase a-z → +A..+Z
for _i, _c in enumerate("abcdefghijklmnopqrstuvwxyz"):
    FULL_ASCII_MAP[_c] = "+" + "ABCDEFGHIJKLMNOPQRSTUVWXYZ"[_i]
# {|}~ → %P..%S
for _k, _v in {
    "{": "%P",
    "|": "%Q",
    "}": "%R",
    "~": "%S",
}.items():
    FULL_ASCII_MAP[_k] = _v
# DEL
FULL_ASCII_MAP["\x7f"] = "%T"
del _i, _k, _v, _c


def _encode_code39_extended(value: str) -> str:
    result = []
    for c in value:
        mapped = FULL_ASCII_MAP.get(c)
        if mapped is None:
            raise ValueError(f"Caracter no soportado en Code 39 Extended: {repr(c)}")
        result.append(mapped)
    return "".join(result)


def encode_code39(value: str, add_checksum: bool = False) -> Tuple[str, str]:
    try:
        code = _Code39(value, add_checksum=add_checksum)
    except Exception:
        value = _encode_code39_extended(value)
        code = _Code39(value, add_checksum=add_checksum)
    pattern = "".join(code.build())
    return pattern, f"*{code.get_fullcode()}*"


def get_code39_module_count(value: str) -> int:
    pattern, _ = encode_code39(value)
    return len(pattern)


def validate_code39(value: str) -> Tuple[bool, str]:
    try:
        _Code39(value)
        return True, ""
    except Exception:
        try:
            _Code39(_encode_code39_extended(value))
            return True, ""
        except Exception as e:
            return False, str(e)


def validate_excel_column_for_code39(values: list) -> list:
    errors = []
    for i, v in enumerate(values):
        v = str(v).strip() if v else ""
        if not v:
            errors.append((i, t("Vacío")))
            continue
        ok, msg = validate_code39(v)
        if not ok:
            errors.append((i, msg))
    return errors


# ── Code39 summary ──
# - input: A-Z, 0-9, -, ., $, /, +, %, space
# - extended: Full ASCII via two-char escapes ($A..$Z, %A..%E, /A../O, +A..+Z)
# - checksum: disabled by default; user supplies their own if needed in Excel/fixed
# - max user data: 41 chars (displayed as *data* = 43 total)
# - narrow module: 0.25mm (min X-dim for printing)
# - min height: 15mm (GS1)
CODE39_MAX_CHARS = 41
CODE39_MIN_HEIGHT_MM = 15.0
CODE39_NARROW_MODULE_MM = 0.25


def validar_longitud_code39(valor: str) -> Tuple[bool, str]:
    """Verifica si un valor no excede el máximo de caracteres para Code39."""
    cadena = str(valor).strip()
    if not cadena:
        return True, ""
    if len(cadena) > CODE39_MAX_CHARS:
        return False, (
            f"El valor tiene {len(cadena)} caracteres. "
            f"El máximo para Code39 es de {CODE39_MAX_CHARS} caracteres "
            f"(43 incluyendo asteriscos de inicio/fin)."
        )
    return True, ""


def validar_columna_code39_longitud(lista_valores: list) -> list:
    """Valida cada valor de una columna Excel contra el límite de caracteres Code39.
    Returns list of (row_index, error_msg) for invalid rows."""
    errors = []
    for i, v in enumerate(lista_valores):
        v = str(v).strip() if v else ""
        if not v:
            continue
        ok, msg = validar_longitud_code39(v)
        if not ok:
            errors.append((i, msg))
    return errors


def get_code39_min_width(
    lista_valores_excel, narrow_mm: float = CODE39_NARROW_MODULE_MM
) -> float:
    """
    Calcula el ancho mínimo en mm para Code39 según la columna Excel.
    Usa el module_count real de la codificación.
    """
    texto_mas_largo = max(lista_valores_excel, key=lambda x: len(str(x)))
    cadena = str(texto_mas_largo).strip()
    modules = get_code39_module_count(cadena)
    return max(40.0, round(modules * narrow_mm, 2))


# ============================================================================
# QR Code support
# ============================================================================

QR_QUIET_ZONE_MODULES = 0
QR_ERROR_CORRECTION = "M"  # fixed: M (15% recovery)

_QR_EC_MAP = {
    "L": _qrconst.ERROR_CORRECT_L,
    "M": _qrconst.ERROR_CORRECT_M,
    "Q": _qrconst.ERROR_CORRECT_Q,
    "H": _qrconst.ERROR_CORRECT_H,
}


def get_qr_module_count(value: str, error_correction: str = QR_ERROR_CORRECTION) -> int:
    """Return the matrix size (N) for an N×N QR code encoding `value`."""
    ec = _QR_EC_MAP.get(error_correction, 0)
    qr = _qrcode.QRCode(error_correction=ec)
    qr.add_data(value)
    qr.make(fit=True)
    return qr.modules_count


def get_qr_total_size(
    value: str, module_size: float, error_correction: str = QR_ERROR_CORRECTION
) -> float:
    """Return total width/height in mm (square) including quiet zones."""
    n = get_qr_module_count(value, error_correction)
    total_modules = n + 2 * QR_QUIET_ZONE_MODULES
    return total_modules * module_size


def get_qr_rects(
    value: str,
    module_size: float,
    error_correction: str = QR_ERROR_CORRECTION,
) -> List[Tuple[float, float, float, float]]:
    """
    Generate vector rects for a QR code.

    Each rect is a black module (square) in the QR matrix.
    Quiet zone of 4 modules is included on all 4 sides.
    y=0 is the bottom edge of the QR code (same convention as Code128:
    content grows upward from y=0).

    Args:
        value: Text to encode
        module_size: Size of one module in mm
        error_correction: Fixed to "M" (15% recovery)

    Returns:
        List of (x, y, w, h) rects for black modules.
        All rects have w == h == module_size.
    """
    ec = _QR_EC_MAP.get(error_correction, 0)
    qr = _qrcode.QRCode(error_correction=ec)
    qr.add_data(value)
    qr.make(fit=True)
    matrix = qr.modules  # list[list[bool]]

    n = len(matrix)
    quiet = QR_QUIET_ZONE_MODULES
    rects: List[Tuple[float, float, float, float]] = []

    # Scan from bottom row upward so y=0 is bottom edge
    for row in range(n - 1, -1, -1):
        for col in range(n):
            if not matrix[row][col]:
                continue
            x = (quiet + col) * module_size
            # row goes from bottom: bottom row = row n-1 -> y=0+(quiet+0)
            # top row = row 0 -> y=(quiet+n-1) but QR uses inverted Y
            # Actually let's think carefully:
            # Matrix[0] = top row of QR, Matrix[n-1] = bottom row of QR
            # y=0 should be bottom of QR (that's the convention)
            # So: bottom QR row (row=n-1) -> y = quiet * module_size
            #     top QR row (row=0) -> y = (quiet + n - 1) * module_size
            y = (quiet + (n - 1 - row)) * module_size
            rects.append((x, y, module_size, module_size))

    return rects


def validate_qr(value: str) -> Tuple[bool, str]:
    """QR Code accepts any string. Always valid."""
    return True, ""


MAX_PRACTICO_QR = 200
"""Máximo práctico de caracteres para QR en etiquetas normales.
QR Versión 40 soporta hasta 2953 bytes, pero en etiquetas de impresión
más de 200 chars produce módulos muy densos y difícil lectura."""


def validar_longitud_qr(valor: str) -> Tuple[bool, str]:
    """Verifica si un valor no excede el máximo práctico de caracteres para QR."""
    cadena = str(valor).strip()
    if not cadena:
        return True, ""
    if len(cadena) > MAX_PRACTICO_QR:
        return False, (
            f"El valor tiene {len(cadena)} caracteres y excede el máximo "
            f"práctico de {MAX_PRACTICO_QR} para QR. "
            f"Será muy denso y costará escanearlo."
        )
    return True, ""


def validar_columna_qr(lista_valores: list) -> list:
    """Valida cada valor de una columna Excel contra el límite práctico de QR.
    Returns list of (row_index, error_msg) for invalid rows."""
    from i18n import t

    errors = []
    for i, v in enumerate(lista_valores):
        v = str(v).strip() if v else ""
        if not v:
            continue
        ok, msg = validar_longitud_qr(v)
        if not ok:
            errors.append((i, msg))
    return errors


def calcular_minimo_qr(lista_valores_excel) -> float:
    """Retorna el mínimo en mm para QR según el texto más largo de la lista."""
    texto_mas_largo = max(lista_valores_excel, key=lambda x: len(str(x)))
    largo_maximo = len(str(texto_mas_largo))
    if largo_maximo <= 25:
        return 10.0
    elif largo_maximo <= 60:
        return 15.0
    return 20.0


def validar_y_calcular_minimo_qr(
    lista_valores_excel, ancho_alto_usuario_mm: float
) -> Tuple[bool, str]:
    """
    Evalúa la columna del Excel y valida si el tamaño propuesto por el usuario
    es suficiente para soportar la densidad de los datos sin fallar en la lectura.
    # GS1: QR — matriz 21×21, módulo 0.25mm, zona silencio 4 módulos
    """
    minimo_requerido_mm = calcular_minimo_qr(lista_valores_excel)
    texto_mas_largo = max(lista_valores_excel, key=lambda x: len(str(x)))
    largo_maximo = len(str(texto_mas_largo))

    if ancho_alto_usuario_mm < minimo_requerido_mm:
        return False, (
            f"Error: El texto más largo de tu Excel tiene {largo_maximo} caracteres. "
            f"Para este volumen de datos, el tamaño mínimo del QR debe ser de {minimo_requerido_mm} mm."
        )

    return True, "Tamaño de QR válido para los datos actuales."


# ============================================================================
# PDF417 support
# ============================================================================

PDF417_DEFAULT_COLUMNS = 6
PDF417_DEFAULT_SECURITY_LEVEL = 2
PDF417_DEFAULT_RATIO = 3  # height/width ratio for modules


def _auto_ecl_pdf417(num_codewords: int) -> int:
    """Automatic security level based on total codewords.

    Level 2: <41 codewords, Level 3: 41-160, Level 4: 161-320, Level 5: 321+
    """
    if num_codewords < 41:
        return 2
    elif num_codewords <= 160:
        return 3
    elif num_codewords <= 320:
        return 4
    else:
        return 5


def validate_pdf417(value: str) -> Tuple[bool, str]:
    """PDF417 accepts any string. Always valid."""
    return True, ""


def _pdf417_encode_literal_bytes(
    value: str,
    columns: int = PDF417_DEFAULT_COLUMNS,
    security_level: int = None,
):
    """Encode using byte compaction to preserve literal digit strings like 0001."""
    sl = security_level if security_level is not None else PDF417_DEFAULT_SECURITY_LEVEL
    data_bytes = _pdf417_to_bytes(value, "utf-8")
    data_words = list(_pdf417_compact_bytes(data_bytes))
    byte_latch = 924 if len(data_bytes) % 6 == 0 else 901
    data_words = [byte_latch] + data_words
    data_count = len(data_words)

    ec_count = 2 ** (sl + 1)
    padding_words = _pdf417_get_padding(data_count, ec_count, columns)
    padding_count = len(padding_words)
    length_descriptor = data_count + padding_count + 1

    cw_count = data_count + ec_count + padding_count + 1
    row_count = math.ceil(cw_count / columns)
    _pdf417_validate_barcode_size(length_descriptor, row_count)

    extended_words = [length_descriptor] + data_words + padding_words
    ec_words = _pdf417_compute_error_correction_code_words(extended_words, sl)
    rows = list(_pdf417_chunks(extended_words + ec_words, columns))
    return list(_pdf417_encode_rows(rows, columns, sl))


def get_pdf417_barcode_width(value: str, columns: int = PDF417_DEFAULT_COLUMNS) -> int:
    """Return total barcode width in modules (including start/stop/quiet zones)."""
    codes, _ = _pdf417_encode_safe(value, columns)
    w, _ = _pdf417_barcode_size(codes)
    return w


@functools.lru_cache(maxsize=256)
def _pdf417_encode_safe(
    value: str, columns: int = PDF417_DEFAULT_COLUMNS, security_level: int = None
):
    """Encode PDF417, auto-reducing columns if text is too short (< 3 rows)."""
    sl = security_level if security_level is not None else PDF417_DEFAULT_SECURITY_LEVEL
    use_literal_bytes = isinstance(value, str) and value.isdigit()
    for cols in range(columns, 0, -1):
        try:
            if use_literal_bytes:
                codes = _pdf417_encode_literal_bytes(
                    value, columns=cols, security_level=sl
                )
            else:
                codes = _pdf417_encode(value, columns=cols, security_level=sl)
            if len(codes) >= cols * 3:
                return codes, cols
        except ValueError:
            continue
    if use_literal_bytes:
        return _pdf417_encode_literal_bytes(value, columns=1, security_level=sl), 1
    return _pdf417_encode(value, columns=1, security_level=sl), 1


def get_pdf417_field_min_height(
    values: list[str],
    bar_width_mm: float,
    columns: int = PDF417_DEFAULT_COLUMNS,
) -> float:
    """Scan all values, return the minimum height needed (max of all)."""
    min_h = 0.0
    for v in values:
        if not v:
            continue
        codes, actual_cols = _pdf417_encode_safe(v, columns)
        n_rows = len(codes)
        barcode_w_mod, _ = _pdf417_barcode_size(codes)
        module_width = bar_width_mm / barcode_w_mod if barcode_w_mod > 0 else 0.3
        h = n_rows * module_width * PDF417_DEFAULT_RATIO
        if h > min_h:
            min_h = h
    return min_h


PDF417_MIN_MODULE_MM = 0.5  # minimum legible module width


def get_pdf417_min_dimensions(
    values: List[str],
    columns: int = PDF417_DEFAULT_COLUMNS,
    min_module_width: float = PDF417_MIN_MODULE_MM,
) -> Tuple[float, float]:
    """Return (min_width_mm, min_height_mm) to encode all values
    at ratio=3 with the given module width.

    Args:
        values: List of strings to encode
        columns: Number of data codewords per row (1-30)
        min_module_width: Minimum module width in mm for legibility

    Returns:
        (min_width_mm, min_height_mm) tuple
    """
    entries = []
    for v in values:
        if not v:
            continue
        codes, _ = _pdf417_encode_safe(v, columns)
        entries.append((_pdf417_barcode_size(codes)[0], len(codes)))
    if not entries:
        return 1.0, 1.0

    max_w = max(w_mod for w_mod, _ in entries) * min_module_width

    max_h = 0.0
    for w_mod, n_rows in entries:
        module_width = max_w / w_mod
        h = n_rows * module_width * PDF417_DEFAULT_RATIO
        if h > max_h:
            max_h = h
    return max_w, max_h


def get_pdf417_total_size(
    value: str,
    bar_width_mm: float,
    columns: int = PDF417_DEFAULT_COLUMNS,
    ratio: float = PDF417_DEFAULT_RATIO,
    target_height_mm: Optional[float] = None,
) -> Tuple[float, float]:
    """Return (width, height) in mm for a PDF417 barcode.

    Args:
        value: Text to encode
        bar_width_mm: Total desired width in mm (including quiet zones)
        columns: Number of data codewords per row (1-30)
        ratio: Module height to width ratio (Y/X, must be >= 3)
        target_height_mm: If set, adjusts ratio to reach this height (won't go below ratio=3)

    Returns:
        (width_mm, height_mm) tuple
    """
    codes, actual_cols = _pdf417_encode_safe(value, columns)
    n_rows = len(codes) if actual_cols > 0 else 0
    barcode_w_mod, _ = _pdf417_barcode_size(codes)
    module_width = bar_width_mm / barcode_w_mod if barcode_w_mod > 0 else 0.3

    if target_height_mm is not None and n_rows > 0:
        ratio_needed = target_height_mm / (n_rows * module_width)
        ratio = max(ratio_needed, PDF417_DEFAULT_RATIO)

    module_height = module_width * ratio
    total_height = n_rows * module_height
    return bar_width_mm, total_height


def get_pdf417_rects(
    value: str,
    module_width: float,
    columns: int = PDF417_DEFAULT_COLUMNS,
    ratio: float = PDF417_DEFAULT_RATIO,
) -> List[Tuple[float, float, float, float]]:
    """
    Generate vector rects for a PDF417 barcode.

    Merges adjacent black modules horizontally (per row) and vertically
    (same x+width across consecutive rows) to minimize rect count
    and keep PDF rendering fast.

    y=0 is the bottom edge (same convention as QR/Code128).

    Args:
        value: Text to encode
        module_width: Width of one module in mm
        columns: Number of data codewords per row (1-30)
        ratio: Module height to width ratio (>= 3)

    Returns:
        List of (x, y, w, h) rects for black modules.
    """
    codes, actual_cols = _pdf417_encode_safe(value, columns)
    module_height = module_width * ratio
    w_mod, h_mod = _pdf417_barcode_size(codes)

    # 1. Group black modules by row
    row_modules: dict[int, list[int]] = {}
    for x_mod, y_mod in _pdf417_modules(codes):
        row_modules.setdefault(y_mod, []).append(x_mod)

    # 2. Horizontal merge per row → (x_mod, w_mods)
    row_runs: dict[int, list[tuple[int, int]]] = {}
    for y_mod, xs in row_modules.items():
        xs.sort()
        runs: list[tuple[int, int]] = []
        start = xs[0]
        end = xs[0]
        for x in xs[1:]:
            if x == end + 1:
                end = x
            else:
                runs.append((start, end - start + 1))
                start = x
                end = x
        runs.append((start, end - start + 1))
        row_runs[y_mod] = runs

    # 3. Vertical merge: group consecutive rows with same (x_mod, w_mods)
    # Flatten all runs into (y_mod, x_mod, w_mods)
    all_runs: list[tuple[int, int, int]] = []
    for y_mod, runs in row_runs.items():
        for x_mod, w_mods in runs:
            all_runs.append((y_mod, x_mod, w_mods))

    # Sort by x, then width, then y (ascending for vertical adjacency)
    all_runs.sort(key=lambda r: (r[1], r[2], r[0]))

    merged_runs: list[tuple[int, int, int, int]] = []  # (y_mod, x_mod, w_mods, h_mods)
    for y_mod, x_mod, w_mods in all_runs:
        if merged_runs:
            last = merged_runs[-1]
            # last is (ly, lx, lw, lh) where ly is the BOTTOM y_mod of the merged rect
            if last[1] == x_mod and last[2] == w_mods and last[0] + last[3] == y_mod:
                merged_runs[-1] = (last[0], last[1], last[2], last[3] + 1)
                continue
        merged_runs.append((y_mod, x_mod, w_mods, 1))

    # 4. Convert to mm rects
    rects: List[Tuple[float, float, float, float]] = []
    for y_mod, x_mod, w_mods, h_mods in merged_runs:
        rects.append(
            (
                x_mod * module_width,
                (h_mod - 1 - (y_mod + h_mods - 1)) * module_height,
                w_mods * module_width,
                h_mods * module_height,
            )
        )

    return rects


def get_pdf417_image_b64(
    value: str,
    bar_width: float,
    bar_color: str = "#000000",
    columns: int = PDF417_DEFAULT_COLUMNS,
    target_height_mm: float = None,
    font_family: str = "OCR-B",
    font_size: float = 9.0,
    hri_gap_mm: float = 2.0,
    hri_position: str = "below",
    text_color: str = "#000000",
    hri_align: str = "bottom_center",
    hri_line_spacing: float = 1.0,
    del_open: str = "",
    del_close: str = "|",
    close_as_newline: bool = False,
) -> str:
    """Generate PDF417 barcode as base64-encoded PNG image with optional HRI text.

    Args:
        value: Text to encode
        bar_width: Total desired width in mm
        bar_color: Foreground color as hex string
        columns: Number of data codewords per row
        target_height_mm: If set, image is resized to achieve this height
        font_family/font_size: Fuente del HRI (cuerpo 0 = sin HRI)
        hri_gap_mm/hri_position/hri_align/hri_line_spacing/text_color: Diseño HRI
        del_open/del_close: Separadores de campo (parten el texto en líneas HRI)

    Returns:
        (b64_str, canvas_w_mm, canvas_h_mm, code_h_mm) (HRI incluido en el canvas)
    """
    encode_value = (
        value.replace(del_close, "\n")
        if close_as_newline and del_close and value
        else value
    )
    codes, actual_cols = _pdf417_encode_safe(encode_value, columns)
    barcode_w_mod, _ = _pdf417_barcode_size(codes)
    PX_PER_MM = 300.0 / 25.4
    module_width = bar_width / barcode_w_mod if barcode_w_mod > 0 else 0.3
    scale = max(3, int(round(module_width * PX_PER_MM)))
    img = _pdf417_render(
        codes, scale=scale, ratio=3, padding=0, fg_color=bar_color, bg_color="#FFFFFF"
    )

    # Redimensionar a mm EXACTOS (patrón DataMatrix): ancho = bar_width, alto = target_height
    target_w_px = int(round(bar_width * PX_PER_MM))
    if target_height_mm is not None and target_height_mm > 0:
        target_h_px = int(round(target_height_mm * PX_PER_MM))
    else:
        target_h_px = int(round(img.height * target_w_px / img.width))
    if (target_w_px, target_h_px) != img.size:
        img = img.resize((target_w_px, target_h_px), 0)
    code_h_mm = target_h_px / PX_PER_MM

    img = img.convert("RGB")
    hri_lines = _format_hri_lines(
        value, font_family, font_size, bar_width, del_open, del_close, "pdf417"
    )
    b64, _cw, _ch, _chm = _build_hri_canvas(
        img, hri_lines, bar_width, code_h_mm, font_family, font_size,
        hri_gap_mm, hri_position, hri_align, hri_line_spacing, text_color,
    )
    return b64, _cw, _ch, _chm


# ============================================================================
# EAN-13 support
# ============================================================================


def encode_ean13(value: str) -> Tuple[str, str]:
    """Encode a value as EAN-13.

    Args:
        value: 12 or 13 digit string. If 12, checksum is calculated.

    Returns:
        (pattern_str, fullcode)
        pattern_str: string of '1' (bar) and '0' (space), 95 chars
        fullcode: 13-digit string
    """
    ean = _EAN13(value)
    pattern = "".join(ean.build())
    return pattern, ean.get_fullcode()


def validate_ean13(value: str) -> Tuple[bool, str]:
    """Validate if a string can be encoded as EAN-13."""
    if not value or not value.isdigit():
        return False, t("Solo se permiten dígitos")
    if len(value) not in (12, 13):
        return False, t("Debe tener 12 o 13 dígitos")
    if value[0] == "0":
        return False, t("El primer dígito no puede ser 0")
    try:
        ean = _EAN13(value)
        if len(value) == 13 and ean.get_fullcode() != value:
            return False, t("El dígito de control no coincide")
        return True, ""
    except Exception as e:
        return False, str(e)


def get_ean13_module_count() -> int:
    """EAN-13 has a fixed 95 modules (no quiet zone included)."""
    return EAN13_TOTAL_MODULES


# ── EAN-8 ──


def _ean8_checksum(value: str) -> str:
    """Calculate EAN-8 check digit from a 7-digit string."""
    if len(value) != 7 or not value.isdigit():
        return ""
    weights = (3, 1, 3, 1, 3, 1, 3)
    total = sum(int(d) * w for d, w in zip(value, weights))
    return str((10 - (total % 10)) % 10)


def encode_ean8(value: str) -> Tuple[str, str]:
    """Encode a value as EAN-8.

    Args:
        value: 7 or 8 digit string. If 7, checksum is calculated.

    Returns:
        (pattern_str, fullcode)
        pattern_str: string of '1' (bar) and '0' (space), 67 chars
        fullcode: 8-digit string
    """
    fullcode = value[:8].strip()
    if len(fullcode) == 7:
        fullcode += _ean8_checksum(fullcode)
    elif len(fullcode) >= 8:
        fullcode = fullcode[:7] + _ean8_checksum(fullcode[:7])

    left_digits = fullcode[:4]
    right_digits = fullcode[4:8]

    parts = ["101"]
    for d in left_digits:
        parts.append(_EAN8_L_CODES[d])
    parts.append("01010")
    for d in right_digits:
        parts.append(_EAN8_R_CODES[d])
    parts.append("101")

    return "".join(parts), fullcode


def validate_ean8(value: str) -> Tuple[bool, str]:
    """Validate if a string can be encoded as EAN-8."""
    if not value or not value.isdigit():
        return False, t("Solo se permiten dígitos")
    if len(value) not in (7, 8):
        return False, t("Debe tener 7 u 8 dígitos")
    if len(value) == 8:
        check = _ean8_checksum(value[:7])
        if value[7] != check:
            return False, t("El dígito de control no coincide")
    return True, ""


def get_ean8_module_count() -> int:
    """EAN-8 has a fixed 67 modules (no quiet zone included)."""
    return EAN8_TOTAL_MODULES


# ── EAN-5 (5-digit supplemental price code) ──
# Always used alongside EAN-13/UPC. No check digit.
# 47 modules: 1011 + 5×(7 data + 2 separator) — last separator omitted

EAN5_TOTAL_MODULES = 47

_EAN5_START = "1011"
_EAN5_SEP = "01"

# A (odd/L) and B (even/G) encoding — same as EAN-13 left-side
_EAN5_A_CODES = {
    "0": "0001101",
    "1": "0011001",
    "2": "0010011",
    "3": "0111101",
    "4": "0100011",
    "5": "0110001",
    "6": "0101111",
    "7": "0111011",
    "8": "0110111",
    "9": "0001011",
}
_EAN5_B_CODES = {
    "0": "0100111",
    "1": "0110011",
    "2": "0011011",
    "3": "0100001",
    "4": "0011101",
    "5": "0111001",
    "6": "0000101",
    "7": "0010001",
    "8": "0001001",
    "9": "0010111",
}

# Parity pattern per checksum index (0-9)
_EAN5_PARITY = (
    "BBAAA",
    "BABAA",
    "BAABA",
    "BAAAB",
    "ABBAA",
    "AABBA",
    "AAABB",
    "ABABA",
    "ABAAB",
    "AABAB",
)


def _ean5_checksum(value: str) -> int:
    """Weighted sum mod 10 for EAN-5 parity selection."""
    total = 0
    for i, d in enumerate(value):
        weight = 3 if i % 2 == 0 else 9
        total += int(d) * weight
    return total % 10


def encode_ean5(value: str) -> Tuple[str, str]:
    """Encode a 5-digit value as EAN-5 supplemental.

    Args:
        value: Exactly 5 digits.

    Returns:
        (pattern_str, fullcode)
        pattern_str: string of '1' (bar) and '0' (space), 47 chars
        fullcode: 5-digit string
    """
    fullcode = value[:5].strip()
    if len(fullcode) != 5 or not fullcode.isdigit():
        return "", ""

    chk = _ean5_checksum(fullcode)
    parity = _EAN5_PARITY[chk]
    code_map = {"A": _EAN5_A_CODES, "B": _EAN5_B_CODES}

    parts = [_EAN5_START]
    for i, d in enumerate(fullcode):
        if i > 0:
            parts.append(_EAN5_SEP)
        parts.append(code_map[parity[i]][d])

    return "".join(parts), fullcode


def validate_ean5(value: str) -> Tuple[bool, str]:
    """Validate if a string can be encoded as EAN-5."""
    if not value or not value.isdigit():
        return False, t("Solo se permiten dígitos")
    if len(value) != 5:
        return False, t("Debe tener exactamente 5 dígitos")
    return True, ""


def get_ean5_module_count() -> int:
    """EAN-5 has a fixed 47 modules (no quiet zone included)."""
    return EAN5_TOTAL_MODULES


# ── ISBN-13 (identical to EAN-13 barcode pattern, adds "ISBN" text above bars) ──


ISBN_SIZE_OFFSET = 2  # pt — ISBN text font size = barcode_font_size - ISBN_SIZE_OFFSET


def validate_isbn13(value: str) -> Tuple[bool, str]:
    """Validate if a string can be encoded as ISBN-13."""
    if not value or not value.isdigit():
        return False, t("Solo se permiten dígitos")
    if len(value) != 13:
        return False, t("Debe tener 13 dígitos")
    if value[:3] not in ("978", "979"):
        return False, t("Debe comenzar con 978 o 979")
    try:
        ean = _EAN13(value)
        if ean.get_fullcode() != value:
            return False, t("El dígito de control no coincide")
        return True, ""
    except Exception as e:
        return False, str(e)


def _format_isbn13(fullcode: str) -> str:
    """Format ISBN-13 with the ISBN prefix."""
    return f"ISBN {fullcode}"


# ── UPC-A support (uses EAN-13 encoding with "0" prefix) ──


def validate_upca(value: str) -> Tuple[bool, str]:
    """Validate if a string can be encoded as UPC-A (12 digits)."""
    if not value or not value.isdigit():
        return False, t("Solo se permiten dígitos")
    if len(value) != 12:
        return False, t("Debe tener 12 dígitos")
    try:
        ean13_value = "0" + value
        ean = _EAN13(ean13_value)
        if ean.get_fullcode() != ean13_value:
            return False, t("El dígito de control no coincide")
        return True, ""
    except Exception as e:
        return False, str(e)


def encode_upca(value: str) -> Tuple[str, str]:
    """Encode UPC-A using EAN-13 encoding (prepend "0").

    Args:
        value: 12-digit UPC-A string.

    Returns:
        (pattern_str, full12)
        pattern_str: string of '1' (bar) and '0' (space), 95 chars
        full12: 12-digit UPC-A code (no leading "0")
    """
    ean13_value = "0" + value.zfill(12)
    pattern, _ = encode_ean13(ean13_value)
    return pattern, value.zfill(12)


def get_upca_module_count() -> int:
    """UPC-A has a fixed 95 modules (same as EAN-13)."""
    return EAN13_TOTAL_MODULES


# ── UPC-E support (6 digits, zero-suppression, expands to UPC-A ──


def expandir_upce(upc_e: str) -> str:
    """Expand 6-digit UPC-E to 12-digit UPC-A using GS1 zero-suppression.

    Args:
        upc_e: 6-digit UPC-E (NSD + 5 data). NSD must be 0 or 1.

    Returns:
        12-digit UPC-A string (with check digit calculated internally).
    """
    d1, d2, d3, d4, d5, d6 = upc_e[0], upc_e[1], upc_e[2], upc_e[3], upc_e[4], upc_e[5]
    if d6 in ("0", "1", "2"):
        fabricante = d1 + d2 + d6 + "00"
        producto = "00" + d3 + d4 + d5
    elif d6 == "3":
        fabricante = d1 + d2 + d3 + "00"
        producto = "000" + d4 + d5
    elif d6 == "4":
        fabricante = d1 + d2 + d3 + d4 + "0"
        producto = "0000" + d5
    else:
        fabricante = d1 + d2 + d3 + d4 + d5
        producto = "0000" + d6
    base_11 = "0" + fabricante + producto
    suma_impares = sum(int(base_11[i]) for i in range(0, 11, 2))
    suma_pares = sum(int(base_11[i]) for i in range(1, 11, 2))
    total = (suma_impares * 3) + suma_pares
    digito_control = 0 if total % 10 == 0 else 10 - (total % 10)
    return base_11 + str(digito_control)


def validate_upce(value: str) -> Tuple[bool, str]:
    """Validate a 6-digit UPC-E code (first digit must be 0 or 1)."""
    if not value or not value.isdigit():
        return False, t("Solo se permiten dígitos")
    if len(value) != 6:
        return False, t("Debe tener 6 dígitos")
    if value[0] not in ("0", "1"):
        return False, t("El primer dígito debe ser 0 o 1")
    try:
        upca = expandir_upce(value)
        ean13_value = "0" + upca
        ean = _EAN13(ean13_value)
        if ean.get_fullcode() != ean13_value:
            return False, t("El dígito de control no coincide")
        return True, ""
    except Exception as e:
        return False, str(e)


def encode_upce(value: str) -> Tuple[str, str]:
    """Encode a 6-digit UPC-E value as a real 51-module pattern.

    UPC-E = "101" (left guard) + 6 digitos (42 modulos) + "010101" (right guard).
    Sin barra central. Los codigos de los 6 digitos se extraen del patron
    EAN-13 expandido (d1..d5 en modulos 10:44, d6 = primer digito derecho).

    Returns:
        (pattern_str, upce_str)
        pattern_str: string of '1'/'0', 51 chars
        upce_str: 6-digit UPC-E input
    """
    upce = value.zfill(6)
    upca = expandir_upce(upce)
    pattern, _ = encode_upca(upca)
    upce_pattern = pattern[:3] + pattern[10:45] + pattern[50:57] + "010101"
    return upce_pattern, upce


def get_upce_module_count() -> int:
    """UPC-E tiene 51 modulos fijos (sin zona de silencio)."""
    return 51


# ============================================================================
# ITF-14 support (Interleaved 2 of 5, 14 digits)
# ============================================================================

# I 2 of 5 encoding table: 5 elements per digit (0=narrow, 1=wide)
_I25_TABLE = {
    "0": "00110",
    "1": "10001",
    "2": "01001",
    "3": "11000",
    "4": "00101",
    "5": "10100",
    "6": "01100",
    "7": "00011",
    "8": "10010",
    "9": "01010",
}

ITF14_START = "1010"  # 4 modules
ITF14_STOP = "101"  # 3 modules
ITF14_PAIRS = 7  # 14 digits = 7 pairs
ITF14_TOTAL_MODULES = (
    ITF14_PAIRS * 14 + len(ITF14_START) + len(ITF14_STOP)
)  # 98+4+3=105
ITF14_BEARER_BAR_WIDTH_MM = 3.0  # bearer bar thickness


def validate_itf14(value: str) -> Tuple[bool, str]:
    """Validate a 14-digit ITF-14 (GTIN-14) value with checksum."""
    if not value or not value.isdigit():
        return False, t("Solo se permiten dígitos")
    if len(value) != 14:
        return False, t("Debe tener 14 dígitos")
    # GTIN-14 checksum (same algorithm as EAN-13: weights 3,1,3,1,...)
    total = 0
    for i, ch in enumerate(value[:-1]):
        weight = 3 if i % 2 == 0 else 1
        total += int(ch) * weight
    expected_checksum = (10 - (total % 10)) % 10
    if int(value[-1]) != expected_checksum:
        return False, t("El dígito de control no coincide")
    return True, ""


def validate_gtin13(value: str) -> Tuple[bool, str]:
    """Validate a 13-digit GTIN-13 value with checksum.

    Uses weights 3,1,3,1,... (consistent with gtin13_to_gtin14 and the
    14-digit GTIN-14 pattern — the data in Excel files follows this convention).
    """
    if not value or not value.isdigit():
        return False, t("Solo se permiten dígitos")
    if len(value) != 13:
        return False, t("Debe tener 13 dígitos")
    total = 0
    for i, ch in enumerate(value[:-1]):
        weight = 3 if i % 2 == 0 else 1
        total += int(ch) * weight
    expected_checksum = (10 - (total % 10)) % 10
    if int(value[-1]) != expected_checksum:
        return False, t("El dígito de control no coincide")
    return True, ""


def validate_excel_column_for_itf14(values: list, gtin_type: str) -> list:
    """Valida cada valor de una columna Excel contra las reglas GTIN.

    Args:
        values: Lista de strings (valores de la columna).
        gtin_type: "gtin13" o "gtin14".

    Returns:
        Lista de tuplas (row_index, error_msg) para filas inválidas.
    """
    errors = []
    for i, v in enumerate(values):
        v = str(v).strip() if v else ""
        if not v:
            errors.append((i, t("Vacío")))
            continue
        if gtin_type == "gtin13":
            ok, msg = validate_gtin13(v)
        else:
            ok, msg = validate_itf14(v)
        if not ok:
            errors.append((i, msg))
    return errors


def gtin13_to_gtin14(gtin13: str) -> str:
    """Convert a 13-digit GTIN-13 to a 14-digit GTIN-14 by prepending '0'.

    The 14-digit ITF-14 barcode always requires exactly 14 digits. When the source
    is a standard GTIN-13 (EAN-13), the GS1 specification says to add a leading
    zero to fill the 14-digit mold. The check digit is recalculated for the new
    14-digit number because the weights shift with the extra leading digit.

    Args:
        gtin13: 13-digit string (e.g. '8412345678901')

    Returns:
        14-digit string (e.g. '08412345678901')
    """
    raw = (
        "0" + gtin13[:-1]
    )  # 13 digits: leading 0 + first 12 of gtin13 (strip old check digit)
    total = 0
    for i, ch in enumerate(raw):
        weight = 3 if i % 2 == 0 else 1
        total += int(ch) * weight
    check = (10 - (total % 10)) % 10
    return raw + str(check)


def encode_itf14(value: str) -> Tuple[str, str]:
    """Encode a 14-digit ITF-14 value into an Interleaved 2 of 5 pattern.

    Args:
        value: 14-digit string (with checksum).

    Returns:
        (pattern_str, fullcode)
        pattern_str: '1' (bar) / '0' (space), 105 characters
        fullcode: 14-digit code
    """
    if not validate_itf14(value)[0]:
        raise ValueError(f"Invalid ITF-14 value: {value}")

    fullcode = value
    pattern = list(ITF14_START)

    for pair_idx in range(ITF14_PAIRS):
        d1 = value[pair_idx * 2]
        d2 = value[pair_idx * 2 + 1]
        bars = _I25_TABLE[d1]  # 5 elements for bars
        spaces = _I25_TABLE[d2]  # 5 elements for spaces
        # Interleave: bar1, space1, bar2, space2, ..., bar5, space5
        # 0/1 → narrow/wide for bars, same for spaces
        for i in range(5):
            if bars[i] == "0":
                pattern.append("1")  # narrow bar
            else:
                pattern.append("11")  # wide bar
            if spaces[i] == "0":
                pattern.append("0")  # narrow space
            else:
                pattern.append("00")  # wide space

    pattern.append(ITF14_STOP)
    return "".join(pattern), fullcode


def get_itf14_module_count() -> int:
    """ITF-14 has a fixed 105 modules (14 digits × 7 pairs × 14 + 4 start + 3 stop)."""
    return ITF14_TOTAL_MODULES


def format_itf14_hri(code14: str) -> str:
    """Format 14-digit ITF-14 code as 5 GS1 blocks: X XX XXXX XXXXXX X"""
    return f"{code14[0]} {code14[1:3]} {code14[3:7]} {code14[7:13]} {code14[13]}"


def calc_itf14_dimensions(
    width_mm: float, printer_type: str, user_bar_height: float = 0
) -> dict:
    """
    Calculate all ITF-14 rendering dimensions from total printed width and printer type.

    Bar height is independent of width — uses user_bar_height (clamped to GS1 minimum).
    Quiet zone and bearer bars are specific to each printer type.
    bar_content_width = total width minus quiet zones and bearer bars.

    Args:
        width_mm: Total printed width in mm (including quiet zones and bearer)
        printer_type: "flexografia", "termica", or "laser"
        user_bar_height: User-set bar height in mm (0 = use minimum)

    Returns:
        dict with keys:
          bearer_thickness_mm, quiet_zone_mm, bearer_sides,
          bar_height, scale, bar_content_width
    """
    ESCALA_BASE_WIDTH = 142.75
    scale = width_mm / ESCALA_BASE_WIDTH

    if printer_type == "flexografia":
        bar_height = max(32.00, user_bar_height)
    else:
        bar_height = max(12.70, user_bar_height)

    BEARER_PROPORTION = 4.8
    if printer_type == "flexografia":
        bearer_thickness = max(scale * BEARER_PROPORTION, 3.0)
        bearer_sides = "4"
    elif printer_type == "laser":
        bearer_thickness = max(scale * BEARER_PROPORTION, 2.0)
        bearer_sides = "4"
    else:  # "termica"
        bearer_thickness = max(scale * BEARER_PROPORTION, 1.0)
        bearer_sides = "2"

    quiet_zone_mm = scale * 10.16

    # Bar content width = total minus quiet zones and bearer
    bar_content_width = width_mm - 2 * quiet_zone_mm - bearer_thickness

    return {
        "bearer_thickness_mm": bearer_thickness,
        "quiet_zone_mm": quiet_zone_mm,
        "bearer_sides": bearer_sides,
        "bar_height": bar_height,
        "scale": scale,
        "bar_content_width": bar_content_width,
    }


def _system_font_family_name() -> str:
    """Nombre de la familia del sistema para el HRI: Helvetica en macOS, Arial en Windows."""
    import platform

    return "Helvetica" if platform.system() == "Darwin" else "Arial"


_SYSTEM_FONT_FAMILIES = ("Helvetica", "Helvetica Bold", "Arial", "Arial Bold")


def _system_family_base(font_family: str) -> str | None:
    """Devuelve la familia base del sistema ('Helvetica'/'Arial') si el nombre
    es una de las familias del sistema; None en caso contrario."""
    if font_family in _SYSTEM_FONT_FAMILIES:
        return font_family[: -len(" Bold")] if font_family.endswith(" Bold") else font_family
    return None


@functools.lru_cache(maxsize=8)
def _extract_ttc_face(ttc_path: str, bold: bool) -> str:
    """Extrae la cara regular/bold de un TTC (macOS Helvetica) a un TTF temporal cacheado.
    Necesario porque PyMuPDF no embebe una cara concreta de una colección."""
    from fontTools.ttLib import TTCollection
    import os
    import tempfile
    import hashlib

    ttc = TTCollection(ttc_path)
    want = "bold" if bold else "regular"
    idx = 0
    for i, font in enumerate(ttc.fonts):
        try:
            subfamily = (font["name"].getDebugName(2) or "").lower().replace(" ", "")
        except Exception:
            subfamily = ""
        if bold and want in subfamily:
            idx = i
            break
        if not bold and "bold" not in subfamily:
            idx = i
            break
    key = hashlib.md5(f"{os.path.basename(ttc_path)}-{idx}-{want}".encode()).hexdigest()[:10]
    out = os.path.join(tempfile.gettempdir(), f"tns_hri_{key}.ttf")
    if not os.path.exists(out):
        ttc.fonts[idx].save(out)
    return out


def _system_hri_ttf(family: str, bold: bool) -> str:
    """Ruta TTF concreta (normal/bold) de la familia del sistema en la plataforma actual.
    macOS Helvetica vive en un TTC -> se extrae la cara a un TTF temporal."""
    import os

    if family == "Arial":
        if os.name == "nt":
            base = r"C:\Windows\Fonts"
            return os.path.join(base, "arialbd.ttf" if bold else "arial.ttf")
        base = "/System/Library/Fonts/Supplemental"
        p = os.path.join(base, "Arial Bold.ttf" if bold else "Arial.ttf")
        return p if os.path.exists(p) else ""
    # Helvetica (solo macOS real): TTC -> extracción de cara
    for ttc in (
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/HelveticaNeue.ttc",
    ):
        if os.path.exists(ttc):
            return _extract_ttc_face(ttc, bold)
    return ""


def get_barcode_font_family_options() -> list:
    """Opciones del dropdown 'Fuente': OCR + la familia del sistema (normal y bold)."""
    fam = _system_font_family_name()
    return ["OCR-A", "OCR-B", "OCR-B F", "OCR-B L", fam, f"{fam} Bold"]


def resolve_font_path(font_family: str = "OCR-B", font_key: str | None = None) -> str:
    """Resuelve la ruta al .ttf de la fuente del HRI solicitada (OCR o del sistema)."""
    import os

    sys_base = _system_family_base(font_family)
    if sys_base and not font_key:
        _p = _system_hri_ttf(sys_base, font_family.endswith(" Bold"))
        if _p and os.path.exists(_p):
            return _p
    ean13_font_map = {
        "OCR-A": "OCRA",
        "OCR-B": "OCRB",
        "OCR-B F": "OCRBF",
        "OCR-B L": "OCRBL",
    }
    fk = font_key or ean13_font_map.get(font_family, "OCRB")
    from pathlib import Path
    import sys

    base_dir = (
        Path(sys._MEIPASS)
        if getattr(sys, "frozen", False)
        else Path(__file__).resolve().parent.parent
    )
    fp = (base_dir / "ocr-0.3.1" / f"{fk}.ttf").resolve()
    if not fp.exists():
        fp = (
            Path(__file__).resolve().parent.parent / "ocr-0.3.1" / f"{fk}.ttf"
        ).resolve()
    return str(fp)


def measure_text(text: str, font_path: str, font_size_pt: float) -> float:
    """Mide el ancho real del texto con la fuente TTF especificada a un font-size dado.
    Devuelve el ancho en puntos (equivalente a píxeles a 72dpi)."""
    f = fitz.Font(fontfile=font_path)
    return f.text_length(text, fontsize=font_size_pt)


@functools.lru_cache(maxsize=16)
def get_digit_advance_em(font_family: str = "OCR-B", font_key: str | None = None) -> float:
    """Avance real del dígito en ems (ancho del glifo) para la fuente HRI.
    OCR monoespaciado = 0.723 em; Arial/Helvetica = 0.556 em. Cae a 0.50 si no se puede medir."""
    import os

    path = resolve_font_path(font_family, font_key)
    if not path or not os.path.exists(path):
        return 0.50
    try:
        return fitz.Font(fontfile=path).text_length("0", fontsize=1000) / 1000.0
    except Exception:
        return 0.50


_PT_TO_MM = 0.3528

# ponytail: hueco minimo entre digitos (y entre digito y barra) fijo.
# Upgrade si el look no convence: derivarlo del ancho de tinta del glifo (fitz glyph bbox).
T_MIN_MM = 0.2


def _ean_hri_group_geometry(symbology):
    """Zonas HRI (modulo de inicio, nº de digitos) por simbologia."""
    if symbology in ("ean13", "isbn13"):
        return ((3, 6), (50, 6))
    if symbology == "upca":
        return ((7, 5), (54, 5))
    if symbology == "ean8":
        return ((3, 4), (36, 4))
    if symbology == "upce":
        return ((3, 6),)
    raise ValueError(f"Sin geometria HRI entre barras para {symbology}")


def ean_hri_max_ds_mm(symbology, module_mm, font_family, t_min_mm=T_MIN_MM):
    """Cuerpo HRI maximo (mm) que cabe en la zona con hueco t_min:
    el glifo renderizado no puede superar c_eff_max, asi que se limita el size."""
    advance = get_digit_advance_em(font_family)
    n = max(n for _, n in _ean_hri_group_geometry(symbology))
    c_eff_max = 7 * module_mm - (n + 1) * t_min_mm / n
    return c_eff_max / advance


def ean_hri_layout(
    symbology, fullcode, module_mm, ds_mm, font_family, t_min_mm=T_MIN_MM
):
    """Posiciones HRI (entre barras) con interletraje uniforme y barras ancladas.

    Un grupo de N digitos llena su zona (N*7 modulos) con hueco uniforme t:
        c_eff = min(c, 7m - (n+1)*t_min/n)      c = ds_mm * advance
        t     = n*(7m - c_eff)/(n+1)
    Hueco exterior (digito <-> barra) == hueco interior (digito <-> digito) == t.
    Devuelve (elements, c_eff_mm, bar_offset_mm, cw_mm, ds_eff_mm): elements =
    [(digito, center_x_mm)] con x relativa al canvas; las barras se dibujan en
    bar_offset + modulo*module_mm; ds_eff_mm es el cuerpo efectivo a renderizar
    (<= ds_mm; menor cuando el glifo no cabe en la zona con t_min)."""
    advance = get_digit_advance_em(font_family)
    m = module_mm
    bars_mm = (
        get_ean8_module_count() * m
        if symbology == "ean8"
        else get_upce_module_count() * m
        if symbology == "upce"
        else get_ean13_module_count() * m
    )
    # cuerpo 0 = sin HRI: solo barras, sin digitos ni desplazamiento.
    if ds_mm <= 0:
        return [], 0.0, 0.0, bars_mm, 0.0
    groups = _ean_hri_group_geometry(symbology)
    n = max(n for _, n in groups)
    ds_eff_mm = min(ds_mm, ean_hri_max_ds_mm(symbology, m, font_family, t_min_mm))
    c_eff = ds_eff_mm * advance
    t = n * (7 * m - c_eff) / (n + 1)

    has_leading = symbology in ("ean13", "isbn13", "upca")
    bar_offset = (c_eff + t) if has_leading else 0.0

    if symbology in ("ean13", "isbn13"):
        groups_iter = ((3, 6, fullcode[1:7]), (50, 6, fullcode[7:13]))
    elif symbology == "upca":
        groups_iter = ((7, 5, fullcode[1:6]), (54, 5, fullcode[6:11]))
    elif symbology == "ean8":
        groups_iter = ((3, 4, fullcode[0:4]), (36, 4, fullcode[4:8]))
    else:  # upce
        groups_iter = ((3, 6, fullcode[0:6]),)

    elements = []
    if has_leading:
        elements.append((fullcode[0], c_eff / 2))
    for start_mod, g_n, digits in groups_iter:
        left0 = bar_offset + start_mod * m + t
        pitch = c_eff + t
        for i, digit in enumerate(digits):
            elements.append((digit, left0 + i * pitch + c_eff / 2))

    trailing = (t + c_eff) if symbology == "upca" else 0.0
    if symbology == "upca":
        elements.append((fullcode[11], bar_offset + bars_mm + t + c_eff / 2))
    return elements, c_eff, bar_offset, bar_offset + bars_mm + trailing, ds_eff_mm


@functools.lru_cache(maxsize=4)
def get_font_ascender_ratio(font_path: str) -> float:
    """Retorna el ratio ascender/fontSize de la fuente. El ascender indica
    cuánto se eleva el texto desde la baseline (e.g. 0.7 = 70% del font-size)."""
    try:
        return fitz.Font(fontfile=font_path).ascender
    except Exception:
        return 0.7


# ponytail: mínimo de interlineado para que las fuentes del sistema (Helvetica/Arial ~1.0)
# respiren igual que OCR-B (~1.28); sin esto las líneas HRI quedan apretadas.
_HRI_LINE_HEIGHT_MIN_RATIO = 1.2


def get_hri_line_height(font_path: str, px_size: int) -> int:
    """Alto de línea del HRI en píxeles, con un ratio mínimo para fuentes del sistema."""
    try:
        fz = fitz.Font(fontfile=font_path)
        _r = fz.ascender - fz.descender
    except Exception:
        _r = 1.2
    return int(round(max(_r, _HRI_LINE_HEIGHT_MIN_RATIO) * px_size))


def get_font_text_metrics(font_path: str) -> tuple[float, float, float]:
    """Retorna (ascender, descender, total_height_ratio) de la fuente TTF.
    total_height = ascender - descender (e.g. OCR-B: ~1.274)."""
    try:
        f = fitz.Font(fontfile=font_path)
        return (f.ascender, f.descender, f.ascender - f.descender)
    except Exception:
        return (0.7, -0.2, 0.9)


@functools.lru_cache(maxsize=4)
def get_font_cap_height_ratio(font_path: str) -> float:
    """Lee OS/2.sCapHeight de la fuente TTF y retorna el ratio capHeight/em.

    Si no está disponible, mide el glyph bbox real de los dígitos para
    obtener el cap height exacto (OCR-B ~0.768, no 0.70).
    """
    try:
        from fontTools.ttLib import TTFont
        from fontTools.pens.boundsPen import BoundsPen

        font = TTFont(font_path)
        upm = font["head"].unitsPerEm if "head" in font else 2048
        cap = None
        if "OS/2" in font:
            os2 = font["OS/2"]
            if hasattr(os2, "sCapHeight") and os2.sCapHeight > 0:
                cap = os2.sCapHeight / upm
        if cap is None:
            glyph_set = font.getGlyphSet()
            cmap = font.getBestCmap()
            tops = []
            for ch in "0123456789":
                if ord(ch) in cmap:
                    glyph_name = cmap[ord(ch)]
                    pen = BoundsPen(glyph_set)
                    glyph_set[glyph_name].draw(pen)
                    if pen.bounds:
                        tops.append(pen.bounds[3])
            if tops:
                cap = sum(tops) / len(tops) / upm
            else:
                cap = 0.70
        font.close()
        return cap
    except Exception:
        return 0.70


# ============================================================================
# GS1 DataMatrix support
# ============================================================================

import re as _re

DM_MIN_MODULE_MM = (
    0.255  # 300 dpi → 0.255mm per module (GS1 spec: 10 modules minimum → 2.55mm)
)


_IAS_FIJAS = {
    "00": (18, "18 dígitos (SSCC)"),
    "01": (14, "14 dígitos (GTIN)"),
    "02": (14, "14 dígitos (CONTENT)"),
    "11": (6, "6 dígitos (YYMMDD)"),
    "12": (6, "6 dígitos (YYMMDD)"),
    "13": (6, "6 dígitos (YYMMDD)"),
    "15": (6, "6 dígitos (YYMMDD)"),
    "16": (6, "6 dígitos (YYMMDD)"),
    "17": (6, "6 dígitos (YYMMDD)"),
    "20": (2, "2 dígitos (variante)"),
    "254": (13, "13 dígitos (GLN)"),
    "402": (17, "17 dígitos (GSIN)"),
    "410": (13, "13 dígitos (GLN)"),
    "411": (13, "13 dígitos (GLN)"),
    "412": (13, "13 dígitos (GLN)"),
    "413": (13, "13 dígitos (GLN)"),
    "414": (13, "13 dígitos (GLN)"),
    "415": (13, "13 dígitos (GLN)"),
    "422": (3, "3 dígitos (país ISO)"),
}

_IAS_MEDIDA = {"310", "311", "312", "313", "314", "315", "316", "320", "330", "340"}


def _es_ai_fijo(ai: str):
    if ai in _IAS_FIJAS:
        return _IAS_FIJAS[ai]
    if len(ai) == 4 and ai[:3] in _IAS_MEDIDA:
        return (6, "6 dígitos (medida)")
    return None


# ── Familia DataMatrix ──
# Tres simbologías comparten campos/render; la UI común despacha por familia.
DATAMATRIX_FAMILY = ("datamatrix", "datamatrix_gs1", "datamatrix_dl")


def _is_datamatrix_family(sym: str) -> bool:
    """True si la simbología es de la familia DataMatrix (custom/gs1/dl)."""
    return sym in DATAMATRIX_FAMILY


def _is_datamatrix_gs1_symb(sym: str) -> bool:
    """True si la simbología valida/etiqueta como GS1 (element string)."""
    return sym in ("datamatrix_gs1",)


def _datamatrix_mode(symbology: str, value: str = "") -> str:
    """Modo de render de la familia DataMatrix: 'gs1' | 'dl' | 'text'.

    Por ID de simbología (explícito). Solo `datamatrix` (custom) conserva la
    auto-detección legacy para no romper perfiles ya guardados con formato GS1.
    """
    if symbology == "datamatrix_gs1":
        return "gs1"
    if symbology == "datamatrix_dl":
        return "dl"
    if symbology == "datamatrix" and _es_datamatrix_gs1(value):
        return "gs1"
    return "text"


def _parse_gs1_hri(value: str):
    """Parse GS1 HRI string like '(01)09506000117843(17)201231' into [(ai, value), ...]."""
    return _re.findall(r"\((\d{2,4})\)([^()\n]*)", value)


def _es_datamatrix_gs1(value: str) -> bool:
    """True si el valor EMPIEZA por un bloque (AI): '(01)09506000117843(17)201231' sí,
    '09506000117843(17)201231' o 'nota (10) lote' no (texto libre)."""
    return bool(_re.match(r"\(\d{2,4}\)", value))


def _split_fields(value: str, open_del: str = "", close_del: str = "|") -> list:
    """Parte un valor en campos según delimitador de apertura y cierre.

    Regla única: se quita la apertura inicial, se divide por (cierre + apertura)
    y se limpia el cierre final del último campo. Con ('' , '|') equivale a
    value.split('|') (comportamiento histórico). Con ambos vacíos devuelve el
    texto completo (un solo campo). Los valores GS1 (empiezan por (AI)) no se
    parten nunca.
    """
    if not value:
        return []
    if _es_datamatrix_gs1(value):
        return [value]
    open_del = open_del or ""
    close_del = close_del or ""
    sep = close_del + open_del
    if not sep:
        return [value]
    inner = value[len(open_del):] if open_del and value.startswith(open_del) else value
    parts = inner.split(sep)
    if close_del and parts and parts[-1].endswith(close_del):
        parts[-1] = parts[-1][: -len(close_del)]
    result = [p.strip() for p in parts if p.strip()]
    return result or ([value.strip()] if value.strip() else [])


# Candidatos (apertura, cierre) para auto-detectar el separador de campos.
_FIELD_SEPARATOR_CANDIDATES = [
    ("", "|"),
    ("", ";"),
    ("", ","),
    ("", "~"),
    ("", "\t"),
    ("", "\x1d"),
    ("<<", ">>"),
    ("[", "]"),
    ("{", "}"),
    ("#", "#"),
    ("<", ">"),
]


def detect_field_separator(rows, threshold: float = 0.6):
    """Propone (apertura, cierre) que separa los campos de unas filas de datos.

    Analiza la similitud de las filas: el candidato gana si un porcentaje alto de
    filas se parte en >1 campo y el nº de campos es consistente entre filas.
    Si ninguna fila es GS1 y no hay candidato claro, devuelve ('' , '|') (lo que
    el usuario edita a mano). Accuerdo ~90%; el override manual lo completa.
    """
    clean = [r.strip() for r in (rows or []) if r and str(r).strip()]
    if not clean or any(_es_datamatrix_gs1(r) for r in clean):
        return "", "|"
    best = ("", "|")
    best_score = 0.0
    for open_del, close_del in _FIELD_SEPARATOR_CANDIDATES:
        counts = []
        matched = 0
        for r in clean:
            n = len(_split_fields(r, open_del, close_del))
            counts.append(n)
            if n > 1:
                matched += 1
        if matched / len(clean) < threshold:
            continue
        consistency = 1.0 if len(set(counts)) == 1 else 0.0
        if consistency == 0.0:
            mn, mx = min(counts), max(counts)
            consistency = mn / mx if mx > 0 else 0.0
        score = consistency * (sum(counts) / len(counts))
        if score > best_score:
            best_score = score
            best = (open_del, close_del)
    return best


def validate_datamatrix(value: str) -> Tuple[bool, str]:
    """Validate DataMatrix input.

    Auto-detección:
    - Si el valor EMPIEZA por un bloque (AI) → validación GS1 completa.
    - Si no → texto libre: solo se comprueba que no esté vacío (puede usar |
      para separar líneas HRI sin validación GS1).
    """
    if not value or not value.strip():
        return False, t("Valor vacío")
    v = value.strip()
    if not _es_datamatrix_gs1(v):
        return True, ""
    elements = _parse_gs1_hri(v)
    if not elements:
        return False, t("Formato GS1 HRI inválido: use (AI)valor")
    for ai, val in elements:
        if not val:
            return False, t("AI {0} sin valor").format(ai)
        fijo = _es_ai_fijo(ai)
        if fijo:
            expected_len, desc = fijo
            if len(val) != expected_len:
                return False, t("AI {0} debe tener {1}").format(ai, desc)
            if not val.isdigit():
                return False, t("AI {0} debe ser numérico").format(ai)
    return True, ""


def validar_columna_datamatrix(values: list) -> list:
    """Valida cada valor de una columna Excel contra formato GS1 DataMatrix.
    Returns list of (row_index, error_msg) for invalid rows."""
    errors = []
    for i, v in enumerate(values):
        v = str(v).strip() if v else ""
        if not v:
            continue
        ok, msg = validate_datamatrix(v)
        if not ok:
            errors.append((i, msg))
    return errors


def validate_datamatrix_gs1(value: str) -> Tuple[bool, str]:
    """Validación GS1 estricta (datamatrix_gs1): el valor DEBE ser un element
    string GS1 `(AI)valor`. Sin rama de texto libre."""
    if not value or not value.strip():
        return False, t("Valor vacío")
    v = value.strip()
    if not _es_datamatrix_gs1(v):
        return False, t("Formato GS1 HRI inválido: use (AI)valor")
    elements = _parse_gs1_hri(v)
    if not elements:
        return False, t("Formato GS1 HRI inválido: use (AI)valor")
    for ai, val in elements:
        if not val:
            return False, t("AI {0} sin valor").format(ai)
        fijo = _es_ai_fijo(ai)
        if fijo:
            expected_len, desc = fijo
            if len(val) != expected_len:
                return False, t("AI {0} debe tener {1}").format(ai, desc)
            if not val.isdigit():
                return False, t("AI {0} debe ser numérico").format(ai)
    return True, ""


def validar_columna_datamatrix_gs1(values: list) -> list:
    """Valida cada valor de una columna Excel contra GS1 DataMatrix estricto."""
    errors = []
    for i, v in enumerate(values):
        v = str(v).strip() if v else ""
        if not v:
            continue
        ok, msg = validate_datamatrix_gs1(v)
        if not ok:
            errors.append((i, msg))
    return errors


def validate_datamatrix_dl(value: str) -> Tuple[bool, str]:
    """Validación GS1 Digital Link (datamatrix_dl): URI completa válida según biip."""
    if not value or not value.strip():
        return False, t("Valor vacío")
    v = value.strip()
    try:
        from biip.gs1_digital_link_uris import GS1DigitalLinkURI

        GS1DigitalLinkURI.parse(v)
        return True, ""
    except Exception as e:
        return False, t("URI GS1 Digital Link inválida: {0}").format(str(e))


def validar_columna_datamatrix_dl(values: list) -> list:
    """Valida cada valor de una columna Excel contra GS1 Digital Link URI."""
    errors = []
    for i, v in enumerate(values):
        v = str(v).strip() if v else ""
        if not v:
            continue
        ok, msg = validate_datamatrix_dl(v)
        if not ok:
            errors.append((i, msg))
    return errors


def _dm_symbol_modules(value: str, formato: str = "") -> Tuple[int, int]:
    """Return the real (rows, cols) module count of an encoded DataMatrix.

    pylibdmtx's `encoded.width/height` are IMAGE pixel dimensions (code +
    quiet zone + margin), not module counts. The module size is measured as
    the first black run of the top row (clock track) on the cropped content,
    then the cropped pixels are divided by it.
    """
    if not _HAS_DATAMATRIX:
        return 0, 0
    raw = preparar_cadena_gs1_datamatrix(value)
    try:
        if formato and formato != "square":
            encoded = _dm_encode(raw.encode("utf-8"), size=formato)
        else:
            encoded = _dm_encode(raw.encode("utf-8"))
        img = _PILImage.frombytes(
            "RGB", (encoded.width, encoded.height), encoded.pixels
        ).convert("L")
        mask = img.point(lambda p: 255 if p < 128 else 0)
        cb = mask.getbbox()
        if not cb:
            return 0, 0
        w = cb[2] - cb[0]
        h = cb[3] - cb[1]
        run = 0
        while run < w and img.getpixel((cb[0] + run, cb[1])) < 128:
            run += 1
        if run <= 0:
            return 0, 0
        return h // run, w // run
    except Exception:
        return 0, 0


def get_datamatrix_module_count(value: str) -> int:
    """Return the number of modules per side for a DataMatrix value."""
    rows, cols = _dm_symbol_modules(value)
    if rows == 0:
        return 14
    return max(rows, cols)


def get_datamatrix_min_size(values: list) -> Tuple[float, float]:
    """Scan all values, return (min_width_mm, min_height_mm) for the longest one."""
    if not _HAS_DATAMATRIX:
        return 20.0, 20.0
    max_modules = 0
    for v in values:
        if not v:
            continue
        rows, cols = _dm_symbol_modules(v)
        n = max(rows, cols)
        if n > max_modules:
            max_modules = n
    if max_modules == 0:
        return 20.0, 20.0
    min_mm = (max_modules + 2) * DM_MIN_MODULE_MM
    return min_mm, min_mm


def get_datamatrix_possible_heights(values: list, width_mm: float) -> list:
    """Return list of (height_mm, format_str) for the GS1 formats that fit the longest value.

    At most 3 options: the square (always first) + the 2 standard rectangular
    sizes (16x36, 16x48). Any rectangular size that doesn't fit the data or
    violates the GS1 X-dimension floor is omitted.
    """
    if not _HAS_DATAMATRIX or not values:
        return []

    longest = max((v for v in values if v), key=lambda v: len(v), default=None)
    if not longest:
        return []

    results = []

    # Square format (always offered — GS1 floor, never filtered)
    try:
        n_rows, n_cols = _dm_symbol_modules(longest)
        if n_cols > 0:
            alto = width_mm * n_rows / n_cols
            results.append((alto, "square"))
    except Exception:
        pass

    # Only the 2 standard rectangular sizes — GS1 X-dimension floor
    # (module >= DM_MIN_MODULE_MM) + exact fit for the data.
    for fmt in ("16x36", "16x48"):
        n_rows, n_cols = map(int, fmt.split("x"))
        if width_mm / n_cols < DM_MIN_MODULE_MM:
            continue
        if _dm_symbol_modules(longest, formato=fmt) != (n_rows, n_cols):
            continue
        results.append((width_mm * n_rows / n_cols, fmt))

    # Deduplicate heights (keep first = square if tie)
    seen = set()
    deduped = []
    for alto, fmt in results:
        key = round(alto, 2)
        if key not in seen:
            seen.add(key)
            deduped.append((alto, fmt))

    # Square first, rectangular formats in descending height order
    deduped.sort(key=lambda x: (x[1] != "square", -x[0]))
    return deduped


def _get_datamatrix_module_width(value: str, target_mm: float) -> float:
    """Calculate module width in mm for a target CODE width (no quiet zone)."""
    rows, cols = _dm_symbol_modules(value)
    n = max(rows, cols)
    return target_mm / n if n > 0 else DM_MIN_MODULE_MM


IAS_VARIABLES = [
    '10', '21', '22', '30', '240', '241', '242', '250', '251',
    '253', '255', '400', '401', '403', '420', '421'
]


def preparar_cadena_gs1_datamatrix(cadena_excel: str) -> str:
    if not _es_datamatrix_gs1(cadena_excel):
        # Texto libre: dato literal, se conserva tal cual (paréntesis incluidos).
        return cadena_excel
    bloques = _parse_gs1_hri(cadena_excel)
    data = ""
    for i, (ai, valor) in enumerate(bloques):
        data += ai + valor
        if i < len(bloques) - 1 and ai in IAS_VARIABLES:
            data += '\x1d'
    return data


def _img_to_b64(img) -> str:
    """Convierte una imagen PIL a PNG base64 con el blanco hecho transparente."""
    import base64
    import io

    img = img.convert("RGBA")
    datas = img.getdata()
    new_data = []
    for item in datas:
        if item[0] > 240 and item[1] > 240 and item[2] > 240:
            new_data.append((item[0], item[1], item[2], 0))
        else:
            new_data.append(item)
    img.putdata(new_data)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def _build_hri_canvas(
    code_box,
    hri_lines,
    code_w_mm,
    code_h_mm,
    font_family,
    font_size,
    hri_gap_mm,
    hri_position,
    hri_align,
    hri_line_spacing,
    text_color,
) -> tuple:
    """Compone code_box + HRI en un canvas PIL. Devuelve (b64, canvas_w_mm, canvas_h_mm, code_h_mm).

    font_size == 0 o sin líneas → solo el código (cuerpo 0 = sin HRI, toggle del texto).
    Compartido por DataMatrix, QR y PDF417.
    """
    from PIL import Image as _PILImage, ImageDraw, ImageFont

    PX_PER_MM = 300.0 / 25.4
    code_w, code_h = code_box.size

    if font_size == 0 or not hri_lines:
        return (_img_to_b64(code_box), code_w_mm, code_h_mm, code_h_mm)

    font_path = resolve_font_path(font_family)
    px_size = int(round(font_size * PX_PER_MM / 2.835))
    try:
        font = ImageFont.truetype(font_path, px_size)
    except Exception:
        font = ImageFont.load_default()

    line_h = get_hri_line_height(font_path, px_size)
    line_h_spaced = int(
        round(line_h * (hri_line_spacing if hri_line_spacing and hri_line_spacing > 0 else 1.0))
    )
    text_gap_px = int(round(hri_gap_mm * PX_PER_MM))

    # Ancho del texto (línea más ancha) y altura real del bloque
    max_line_w = max(font.getbbox(line)[2] - font.getbbox(line)[0] for line in hri_lines)
    first_top = font.getbbox(hri_lines[0])[1]
    last_bottom = font.getbbox(hri_lines[-1])[3]
    actual_text_h = (len(hri_lines) - 1) * line_h_spaced + last_bottom - first_top

    # Alineación de 9 valores: "top_left".."bottom_right" → vy (top/middle/bottom) + hx (left/center/right)
    vy, hx = ("bottom", "center")
    if hri_align.startswith("top_"):
        vy = "top"
    elif hri_align.startswith("middle_"):
        vy = "middle"
    if hri_align.endswith("_left"):
        hx = "left"
    elif hri_align.endswith("_right"):
        hx = "right"

    # Ancla: below/above apilan sobre Y (caja ancha = max(código, texto)).
    # left/right apilan sobre X (caja estrecha = ancho texto), código a un lado.
    stacked = hri_position in ("below", "above")
    if stacked:
        canvas_w = max(code_w, max_line_w)
        x_code = (canvas_w - code_w) // 2
        # Caja de texto SIEMPRE = lienzo completo: canvas_w ya es >= línea más
        # ancha, así ninguna línea se recorta (restringir al código cortaba).
        box_origin_x = 0
        box_w = canvas_w
        if hri_position == "below":
            y_code = 0
            band_top = code_h + text_gap_px
            band_h = actual_text_h
            canvas_h = code_h + text_gap_px + actual_text_h
        else:  # above
            band_top = 0
            band_h = actual_text_h
            y_code = actual_text_h + text_gap_px
            canvas_h = y_code + code_h
        line_step = line_h_spaced
    else:
        # left / right: el text box va a un lado del código
        canvas_w = max_line_w + text_gap_px + code_w
        canvas_h = max(code_h, actual_text_h)
        box_w = max_line_w
        line_step = line_h_spaced
        y_code = (canvas_h - code_h) // 2
        band_top = 0
        band_h = canvas_h
        if hri_position == "left":
            x_code = max_line_w + text_gap_px
            box_origin_x = 0
        else:  # right
            x_code = 0
            box_origin_x = code_w + text_gap_px

    canvas = _PILImage.new("RGB", (int(canvas_w), int(canvas_h)), (255, 255, 255))
    draw = ImageDraw.Draw(canvas)

    # Código
    canvas.paste(code_box, (x_code, y_code))

    # Texto HRI (alineado dentro de su caja invisible)
    for i, line in enumerate(hri_lines):
        bbox = font.getbbox(line)
        tw = bbox[2] - bbox[0]
        if hx == "left":
            lx = box_origin_x
        elif hx == "right":
            lx = box_origin_x + box_w - tw
        else:
            lx = box_origin_x + (box_w - tw) // 2
        if vy == "top":
            ly = band_top
        elif vy == "bottom":
            ly = band_top + (band_h - actual_text_h)
        else:
            ly = band_top + (band_h - actual_text_h) // 2
        ly += i * line_step
        draw.text((lx, ly - first_top), line, fill=text_color, font=font)

    canvas_w_mm = canvas_w / PX_PER_MM
    canvas_h_mm = canvas_h / PX_PER_MM
    return (_img_to_b64(canvas), canvas_w_mm, canvas_h_mm, code_h_mm)


def get_datamatrix_image_b64(
    value: str,
    width_mm: float = 20.0,
    height_mm: float = 20.0,
    font_family: str = "OCR-B",
    font_size: float = 9.0,
    hri_gap_mm: float = 2.0,
    hri_position: str = "below",
    fill_color: str = "#000000",
    text_color: str = "#000000",
    formato: str = "",
    del_open: str = "",
    del_close: str = "|",
    hri_align: str = "bottom_center",
    hri_line_spacing: float = 1.0,
    close_as_newline: bool = False,
    symbology: str = "datamatrix",
) -> tuple:
    """Generate DataMatrix barcode as base64-encoded PNG with optional HRI text.
    text_color: color del texto HRI (independiente del color del código).
    del_open/del_close: delimitadores de campo (para separar el HRI en líneas).
    Solo texto libre; los valores GS1 no se separan. Defaults ('', '|') = histórico.

    Returns (b64_str, canvas_w_mm, canvas_h_mm, code_h_mm).
    code_h_mm is the actual symbol height (cropped, before HRI text).
    """
    if not _HAS_DATAMATRIX:
        return ("", 0.0, 0.0, 0.0)
    encode_value = (
        value.replace(del_close, "\n")
        if close_as_newline and del_close and value and not _es_datamatrix_gs1(value)
        else value
    )
    raw = preparar_cadena_gs1_datamatrix(encode_value)
    PX_PER_MM = 300.0 / 25.4

    # Use provided format or auto-select
    encoded = None
    if formato and formato != "square":
        try:
            encoded = _dm_encode(raw.encode("utf-8"), size=formato)
        except Exception:
            pass
    if encoded is None:
        try:
            encoded = _dm_encode(raw.encode("utf-8"))
        except Exception:
            return ("", 0.0, 0.0, 0.0)

    dm_img = _PILImage.frombytes("RGB", (encoded.width, encoded.height), encoded.pixels)

    # Crop to content FIRST — remove quiet zone before scaling
    _gray = dm_img.convert("L")
    _mask = _gray.point(lambda p: 255 if p < 128 else 0)
    _cb = _mask.getbbox()
    if _cb:
        code_raw = dm_img.crop((_cb[0], _cb[1], _cb[2], _cb[3]))
    else:
        code_raw = dm_img
    code_raw_w, code_raw_h = code_raw.size

    # Scale cropped content to exactly width_mm × height_mm
    target_w_px = int(round(width_mm * PX_PER_MM))
    target_h_px = int(round(height_mm * PX_PER_MM))
    code_box = code_raw.resize((target_w_px, target_h_px), _PILImage.NEAREST)

    if fill_color and fill_color.lower() not in ("#000000", "black"):
        r, g, b = tuple(int(fill_color.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))
        _px = code_box.load()
        for y in range(code_box.height):
            for x in range(code_box.width):
                pr, pg, pb = _px[x, y]
                if pr < 128 and pg < 128 and pb < 128:
                    _px[x, y] = (r, g, b)

    code_h_mm = height_mm

    hri_lines = _format_hri_lines(
        value, font_family, font_size, width_mm, del_open, del_close, symbology
    )
    return _build_hri_canvas(
        code_box, hri_lines, width_mm, height_mm, font_family, font_size,
        hri_gap_mm, hri_position, hri_align, hri_line_spacing, text_color,
    )


def get_qr_image_b64(
    value: str,
    size_mm: float = 30.0,
    font_family: str = "OCR-B",
    font_size: float = 9.0,
    hri_gap_mm: float = 2.0,
    hri_position: str = "below",
    fill_color: str = "#000000",
    text_color: str = "#000000",
    hri_align: str = "bottom_center",
    hri_line_spacing: float = 1.0,
    del_open: str = "",
    del_close: str = "|",
    close_as_newline: bool = False,
) -> tuple:
    """Generate QR barcode as base64-encoded PNG image with optional HRI text.

    Returns (b64_str, canvas_w_mm, canvas_h_mm, code_h_mm).
    """
    from PIL import Image as _PILImage

    PX_PER_MM = 300.0 / 25.4
    encode_value = (
        value.replace(del_close, "\n")
        if close_as_newline and del_close and value
        else value
    )
    qr = _qrcode.QRCode(error_correction=_qrconst.ERROR_CORRECT_M, box_size=10, border=0)
    qr.add_data(encode_value)
    qr.make(fit=True)
    img = qr.make_image(fill_color=fill_color, back_color="white").convert("RGB")
    code_w_px = max(1, int(round(size_mm * PX_PER_MM)))
    code_box = img.resize((code_w_px, code_w_px), _PILImage.NEAREST)
    hri_lines = _format_hri_lines(
        value, font_family, font_size, size_mm, del_open, del_close, "qr"
    )
    return _build_hri_canvas(
        code_box, hri_lines, size_mm, size_mm, font_family, font_size,
        hri_gap_mm, hri_position, hri_align, hri_line_spacing, text_color,
    )


def _format_hri_lines(
    value: str,
    font_family: str,
    font_size: float,
    max_width_mm: float,
    open_del: str = "",
    close_del: str = "|",
    symbology: str = "",
) -> list:
    """Format HRI text into lines that fit within max_width_mm.

    Breaks only at AI group boundaries — never mid-value.
    """
    if not value:
        return []

    if _datamatrix_mode(symbology, value) != "gs1":
        # Texto libre: una línea HRI por campo (separados por delimitadores).
        lines = _split_fields(value, open_del, close_del)
        if "\n" in value:
            expanded = []
            for ln in lines:
                expanded.extend(ln.split("\n"))
            lines = [l.strip() for l in expanded if l.strip()]
        return lines or [value]

    groups = _parse_gs1_hri(value)

    # Join groups back with parens for display: ["(01)09506000117843", ...]
    ai_groups = ["({0}){1}".format(ai, val) for ai, val in groups]

    font_path = resolve_font_path(font_family)
    PX_PER_MM = 300.0 / 25.4
    try:
        from PIL import ImageFont

        font = ImageFont.truetype(font_path, int(round(font_size * PX_PER_MM / 2.835)))
    except Exception:
        return [value]

    max_px = max_width_mm * PX_PER_MM

    # Single group — check if it fits
    if len(ai_groups) == 1:
        bbox = font.getbbox(ai_groups[0])
        return ai_groups if (bbox[2] - bbox[0]) <= max_px else [ai_groups[0]]

    # One AI group per line — uniform across all symbologies.
    return ai_groups
    return lines


def get_datamatrix_rects(
    value: str,
    module_width: float,
    formato: str = "",
) -> List[Tuple[float, float, float, float]]:
    """Generate vector rects for a DataMatrix barcode (for PDF export)."""
    if not _HAS_DATAMATRIX:
        return []
    raw = preparar_cadena_gs1_datamatrix(value)
    try:
        if formato and formato != "square":
            encoded = _dm_encode(raw.encode("utf-8"), size=formato)
        else:
            encoded = _dm_encode(raw.encode("utf-8"))
    except Exception:
        return []

    from PIL import Image as _Img

    dm_img = _Img.frombytes(
        "RGB", (encoded.width, encoded.height), encoded.pixels
    ).convert("L")
    # Crop to content — remove quiet zone
    _mask = dm_img.point(lambda p: 255 if p < 128 else 0)
    _cb = _mask.getbbox()
    if _cb:
        dm_img = dm_img.crop((_cb[0], _cb[1], _cb[2], _cb[3]))
    cw, ch = dm_img.size
    rects = []
    for y in range(ch):
        x = 0
        while x < cw:
            px = dm_img.getpixel((x, y))
            if px < 128:  # black module
                w = 1
                while x + w < cw and dm_img.getpixel((x + w, y)) < 128:
                    w += 1
                rects.append(
                    (
                        x * module_width,
                        (ch - 1 - y) * module_width,
                        w * module_width,
                        module_width,
                    )
                )
                x += w
            else:
                x += 1
    return rects


# ============================================================================
# Symbology Configuration — defines fields per barcode type
# ============================================================================

_BARCODE_FONT_OPTIONS = get_barcode_font_family_options()

# Campos compartidos por las tres simbologías DataMatrix (custom/gs1/dl).
_DATAMATRIX_FIELDS = [
    {
        "key": "datamatrix_width",
        "label": "Ancho:",
        "type": "float",
        "default": 20.0,
        "section": "Código de barras",
    },
    {
        "key": "datamatrix_height",
        "label": "Alto:",
        "type": "dropdown",
        "options": [],
        "section": "Código de barras",
    },
    {
        "key": "barcode_font_family",
        "label": "Fuente:",
        "type": "dropdown",
        "options": _BARCODE_FONT_OPTIONS,
        "default": "OCR-B",
        "section": "Diseño del bloque de texto",
    },
    {
        "key": "barcode_font_size",
        "label": "Cuerpo:",
        "type": "float",
        "default": 9.0,
        "section": "Diseño del bloque de texto",
    },
    {
        "key": "datamatrix_hri_align",
        "label": "Alineación:",
        "type": "dropdown",
        "options": [
            "top_left", "top_center", "top_right",
            "middle_left", "middle_center", "middle_right",
            "bottom_left", "bottom_center", "bottom_right",
        ],
        "default": "bottom_center",
        "section": "Diseño del bloque de texto",
    },
    {
        "key": "datamatrix_hri_line_spacing",
        "label": "Interlineado:",
        "type": "float",
        "default": 1.0,
        "multiplier": True,
        "section": "Diseño del bloque de texto",
    },
    {
        "key": "datamatrix_hri_position",
        "label": "Posición:",
        "type": "dropdown",
        "options": ["left", "right", "above", "below"],
        "default": "below",
        "section": "Alineación del bloque de texto respecto al código de barras",
    },
    {
        "key": "datamatrix_hri_gap_mm",
        "label": "Distancia:",
        "type": "float",
        "default": 2.0,
        "section": "Alineación del bloque de texto respecto al código de barras",
    },
]

SYMBOLOGY_CONFIG = {
    "code128": {
        "label": "Code 128",
        "sample_value": lambda: "123ABC",
        "validate": validate_code128,
        "fields": [
            {"key": "bar_width", "label": "Ancho:", "type": "float", "default": 80.0},
            {"key": "bar_height", "label": "Alto:", "type": "float", "default": 30.0},
            {
                "key": "barcode_font_family",
                "label": "Fuente:",
                "type": "dropdown",
                "options": _BARCODE_FONT_OPTIONS,
                "default": "OCR-B",
            },
            {
                "key": "barcode_font_size",
                "label": "Cuerpo:",
                "type": "float",
                "default": 9.0,
            },
            {
                "key": "code128_hri_position",
                "label": "Posición:",
                "type": "dropdown",
                "options": ["above", "below"],
                "default": "below",
            },
            {
                "key": "code128_hri_gap_mm",
                "label": "Distancia:",
                "type": "float",
                "default": 2.0,
            },
        ],
    },
    "code39": {
        "label": "Code 39",
        "sample_value": lambda: "ABC-123",
        "validate": validate_code39,
        "fields": [
            {"key": "bar_width", "label": "Ancho:", "type": "float", "default": 80.0},
            {"key": "bar_height", "label": "Alto:", "type": "float", "default": 30.0},
            {
                "key": "barcode_font_family",
                "label": "Fuente:",
                "type": "dropdown",
                "options": _BARCODE_FONT_OPTIONS,
                "default": "OCR-B",
            },
            {
                "key": "barcode_font_size",
                "label": "Cuerpo:",
                "type": "float",
                "default": 9.0,
            },
            {
                "key": "code39_hri_position",
                "label": "Posición:",
                "type": "dropdown",
                "options": ["above", "below"],
                "default": "below",
            },
            {
                "key": "code39_hri_gap_mm",
                "label": "Distancia:",
                "type": "float",
                "default": 2.0,
            },
        ],
    },
    "qr": {
        "label": "QR Code",
        "sample_value": lambda: "https://ejemplo.com",
        "validate": validate_qr,
        "fields": [
            {
                "key": "qr_size",
                "label": "Tamaño (mm):",
                "type": "float",
                "default": 30.0,
            },
            {
                "key": "barcode_font_family",
                "label": "Fuente:",
                "type": "dropdown",
                "options": _BARCODE_FONT_OPTIONS,
                "default": "OCR-B",
                "section": "Diseño del bloque de texto",
            },
            {
                "key": "barcode_font_size",
                "label": "Cuerpo:",
                "type": "float",
                "default": 9.0,
                "section": "Diseño del bloque de texto",
            },
            {
                "key": "qr_hri_align",
                "label": "Alineación:",
                "type": "dropdown",
                "options": [
                    "top_left", "top_center", "top_right",
                    "middle_left", "middle_center", "middle_right",
                    "bottom_left", "bottom_center", "bottom_right",
                ],
                "default": "bottom_center",
                "section": "Diseño del bloque de texto",
            },
            {
                "key": "qr_hri_line_spacing",
                "label": "Interlineado:",
                "type": "float",
                "default": 1.0,
                "multiplier": True,
                "section": "Diseño del bloque de texto",
            },
            {
                "key": "qr_hri_position",
                "label": "Posición:",
                "type": "dropdown",
                "options": ["left", "right", "above", "below"],
                "default": "below",
                "section": "Alineación del bloque de texto respecto al código de barras",
            },
            {
                "key": "qr_hri_gap_mm",
                "label": "Distancia:",
                "type": "float",
                "default": 2.0,
                "section": "Alineación del bloque de texto respecto al código de barras",
            },
        ],
    },
    "ean13": {
        "label": "EAN-13",
        "sample_value": lambda: "5901234123457",
        "validate": validate_ean13,
        "fields": [
            {"key": "bar_width", "label": "Ancho:", "type": "float", "default": 60.0},
            {"key": "bar_height", "label": "Alto:", "type": "float", "default": 30.0},
            {
                "key": "barcode_font_family",
                "label": "Fuente:",
                "type": "dropdown",
                "options": _BARCODE_FONT_OPTIONS,
                "default": "OCR-B",
            },
            {
                "key": "barcode_font_size",
                "label": "Cuerpo:",
                "type": "float",
                "default": 9.0,
            },
        ],
    },
    "ean8": {
        "label": "EAN-8",
        "sample_value": lambda: "96385074",
        "validate": validate_ean8,
        "fields": [
            {"key": "bar_width", "label": "Ancho:", "type": "float", "default": 50.0},
            {"key": "bar_height", "label": "Alto:", "type": "float", "default": 20.0},
            {
                "key": "barcode_font_family",
                "label": "Fuente:",
                "type": "dropdown",
                "options": _BARCODE_FONT_OPTIONS,
                "default": "OCR-B",
            },
            {
                "key": "barcode_font_size",
                "label": "Cuerpo:",
                "type": "float",
                "default": 9.0,
            },
        ],
    },
    "ean5": {
        "label": "EAN-5",
        "sample_value": lambda: "50799",
        "validate": validate_ean5,
        "fields": [
            {"key": "bar_width", "label": "Ancho:", "type": "float", "default": 30.0},
            {"key": "bar_height", "label": "Alto:", "type": "float", "default": 25.0},
            {
                "key": "barcode_font_family",
                "label": "Fuente:",
                "type": "dropdown",
                "options": _BARCODE_FONT_OPTIONS,
                "default": "OCR-B",
            },
            {
                "key": "barcode_font_size",
                "label": "Cuerpo:",
                "type": "float",
                "default": 9.0,
            },
            {
                "key": "ean5_hri_gap_mm",
                "label": "Distancia:",
                "type": "float",
                "default": 2.0,
            },
        ],
    },
    "upca": {
        "label": "UPC-A",
        "sample_value": lambda: "012345678905",
        "validate": validate_upca,
        "fields": [
            {"key": "bar_width", "label": "Ancho:", "type": "float", "default": 60.0},
            {"key": "bar_height", "label": "Alto:", "type": "float", "default": 30.0},
            {
                "key": "barcode_font_family",
                "label": "Fuente:",
                "type": "dropdown",
                "options": _BARCODE_FONT_OPTIONS,
                "default": "OCR-B",
            },
            {
                "key": "barcode_font_size",
                "label": "Cuerpo:",
                "type": "float",
                "default": 9.0,
            },
        ],
    },
    "upce": {
        "label": "UPC-E",
        "sample_value": lambda: "012345",
        "validate": validate_upce,
        "fields": [
            {"key": "bar_width", "label": "Ancho:", "type": "float", "default": 44.0},
            {"key": "bar_height", "label": "Alto:", "type": "float", "default": 30.0},
            {
                "key": "barcode_font_family",
                "label": "Fuente:",
                "type": "dropdown",
                "options": _BARCODE_FONT_OPTIONS,
                "default": "OCR-B",
            },
            {
                "key": "barcode_font_size",
                "label": "Cuerpo:",
                "type": "float",
                "default": 9.0,
            },
        ],
    },
    "isbn13": {
        "label": "ISBN-13",
        "sample_value": lambda: "9780123456786",
        "validate": validate_isbn13,
        "fields": [
            {"key": "bar_width", "label": "Ancho:", "type": "float", "default": 70.0},
            {"key": "bar_height", "label": "Alto:", "type": "float", "default": 30.0},
            {
                "key": "barcode_font_family",
                "label": "Fuente:",
                "type": "dropdown",
                "options": _BARCODE_FONT_OPTIONS,
                "default": "OCR-B",
            },
            {
                "key": "barcode_font_size",
                "label": "Cuerpo:",
                "type": "float",
                "default": 9.0,
            },
            {
                "key": "isbn13_show_title",
                "label": "Cabecera:",
                "type": "dropdown",
                "options": ["Sí", "No"],
                "default": "Sí",
            },
        ],
    },
    "itf14": {
        "label": "ITF-14",
        "sample_value": lambda: "10812345678908",
        "validate": validate_itf14,
        "fields": [
            {"key": "bar_width", "label": "Ancho:", "type": "float", "default": 89.25},
            {"key": "bar_height", "label": "Alto:", "type": "float", "default": 32.0},
        ],
    },
    "pdf417": {
        "label": "PDF417",
        "sample_value": lambda: "Texto de ejemplo PDF417",
        "validate": validate_pdf417,
        "fields": [
            {
                "key": "pdf417_size",
                "label": "Ancho (mm):",
                "type": "float",
                "default": 65.0,
            },
            {
                "key": "pdf417_height",
                "label": "Alto (mm):",
                "type": "float",
                "default": 30.0,
            },
            {
                "key": "barcode_font_family",
                "label": "Fuente:",
                "type": "dropdown",
                "options": _BARCODE_FONT_OPTIONS,
                "default": "OCR-B",
                "section": "Diseño del bloque de texto",
            },
            {
                "key": "barcode_font_size",
                "label": "Cuerpo:",
                "type": "float",
                "default": 9.0,
                "section": "Diseño del bloque de texto",
            },
            {
                "key": "pdf417_hri_align",
                "label": "Alineación:",
                "type": "dropdown",
                "options": [
                    "top_left", "top_center", "top_right",
                    "middle_left", "middle_center", "middle_right",
                    "bottom_left", "bottom_center", "bottom_right",
                ],
                "default": "bottom_center",
                "section": "Diseño del bloque de texto",
            },
            {
                "key": "pdf417_hri_line_spacing",
                "label": "Interlineado:",
                "type": "float",
                "default": 1.0,
                "multiplier": True,
                "section": "Diseño del bloque de texto",
            },
            {
                "key": "pdf417_hri_position",
                "label": "Posición:",
                "type": "dropdown",
                "options": ["left", "right", "above", "below"],
                "default": "below",
                "section": "Alineación del bloque de texto respecto al código de barras",
            },
            {
                "key": "pdf417_hri_gap_mm",
                "label": "Distancia:",
                "type": "float",
                "default": 2.0,
                "section": "Alineación del bloque de texto respecto al código de barras",
            },
        ],
    },
    "datamatrix": {
        "label": "DataMatrix",
        "sample_value": lambda: "Texto ejemplo",
        "validate": validate_datamatrix,
        "fields": _DATAMATRIX_FIELDS,
    },
    "datamatrix_gs1": {
        "label": "GS1 DataMatrix",
        "sample_value": lambda: "(01)09506000117843(17)201231(10)1234AB(21)5678CD",
        "validate": validate_datamatrix_gs1,
        "fields": _DATAMATRIX_FIELDS,
    },
    "datamatrix_dl": {
        "label": "DataMatrix GS1 Digital Link",
        "sample_value": lambda: "https://id.gs1.org/01/10812345670018/10/PO0001?17=250202&21=00000001",
        "validate": validate_datamatrix_dl,
        "fields": _DATAMATRIX_FIELDS,
    },
}

# ── EAN-13 font descender cache ──
_EAN13_DESCENDER_CACHE: dict = {}
_EAN13_ASCENDER_CACHE: dict = {}


def get_ean13_font_descender_ratio(font_family: str = "OCR-B") -> float:
    """Lee el ratio descender/em desde las tablas de la fuente OCR (hhea/OS2).

    Usa la MISMA lógica que FontMetricsCache._calculate_metrics() para que
    el descender coincida con lo que Flet/Flutter usa internamente (hhea.descent
    o sTypoDescender si USE_TYPO_METRICS está activo).

    Retorna un valor float (ej. 0.20 = 20% del em-size por debajo de la baseline).
    Cachea el resultado por font_family para no leer el disco en cada redraw.
    """
    if font_family in _EAN13_DESCENDER_CACHE:
        return _EAN13_DESCENDER_CACHE[font_family]

    ean13_font_map = {
        "OCR-A": "OCRA",
        "OCR-B": "OCRB",
        "OCR-B F": "OCRBF",
        "OCR-B L": "OCRBL",
    }
    font_key = ean13_font_map.get(font_family, "OCRB")

    from pathlib import Path
    import sys

    base_dir = (
        Path(sys._MEIPASS)
        if getattr(sys, "frozen", False)
        else Path(__file__).resolve().parent.parent
    )
    font_path = (base_dir / "ocr-0.3.1" / f"{font_key}.ttf").resolve()
    if not font_path.exists():
        font_path = (
            Path(__file__).resolve().parent.parent / "ocr-0.3.1" / f"{font_key}.ttf"
        ).resolve()

    if not font_path.exists():
        _EAN13_DESCENDER_CACHE[font_family] = 0.20
        return 0.20

    try:
        from fontTools.ttLib import TTFont

        font = TTFont(str(font_path))
        upm = font["head"].unitsPerEm if "head" in font else 2048

        typo_desc = 0
        hhea_desc = 0
        use_typo = False

        if "OS/2" in font:
            os2 = font["OS/2"]
            typo_desc = os2.sTypoDescender
            use_typo = bool(os2.fsSelection & 0x80)

        if "hhea" in font:
            hhea_desc = font["hhea"].descent

        if use_typo:
            chosen_desc = typo_desc
        else:
            chosen_desc = hhea_desc if hhea_desc != 0 else typo_desc

        ratio = abs(chosen_desc) / upm
        font.close()
    except Exception:
        ratio = 0.20

    _EAN13_DESCENDER_CACHE[font_family] = ratio
    return ratio


def get_ean13_font_ascender_ratio(font_family: str = "OCR-B") -> float:
    """Lee el ratio ascender/em desde las tablas de la fuente OCR (hhea/OS2).

    Misma lógica que get_ean13_font_descender_ratio() para que coincida con lo
    que Flet/Flutter usa internamente. Retorna ej. 0.938 = 93.8% del em-size
    por encima de la baseline (OCR-B). Cachea por font_family.
    """
    if font_family in _EAN13_ASCENDER_CACHE:
        return _EAN13_ASCENDER_CACHE[font_family]

    ean13_font_map = {
        "OCR-A": "OCRA",
        "OCR-B": "OCRB",
        "OCR-B F": "OCRBF",
        "OCR-B L": "OCRBL",
    }
    font_key = ean13_font_map.get(font_family, "OCRB")

    from pathlib import Path
    import sys

    base_dir = (
        Path(sys._MEIPASS)
        if getattr(sys, "frozen", False)
        else Path(__file__).resolve().parent.parent
    )
    font_path = (base_dir / "ocr-0.3.1" / f"{font_key}.ttf").resolve()
    if not font_path.exists():
        font_path = (
            Path(__file__).resolve().parent.parent / "ocr-0.3.1" / f"{font_key}.ttf"
        ).resolve()

    if not font_path.exists():
        _EAN13_ASCENDER_CACHE[font_family] = 0.72
        return 0.72

    try:
        from fontTools.ttLib import TTFont

        font = TTFont(str(font_path))
        upm = font["head"].unitsPerEm if "head" in font else 2048

        typo_asc = 0
        hhea_asc = 0
        use_typo = False

        if "OS/2" in font:
            os2 = font["OS/2"]
            typo_asc = os2.sTypoAscender
            use_typo = bool(os2.fsSelection & 0x80)

        if "hhea" in font:
            hhea_asc = font["hhea"].ascent

        if use_typo:
            chosen_asc = typo_asc
        else:
            chosen_asc = hhea_asc if hhea_asc != 0 else typo_asc

        ratio = abs(chosen_asc) / upm
        font.close()
    except Exception:
        ratio = 0.72

    _EAN13_ASCENDER_CACHE[font_family] = ratio
    return ratio


@functools.lru_cache(maxsize=1)
def get_pdf417_max_chars(columns: int = PDF417_DEFAULT_COLUMNS) -> int:
    """Binary search for max chars fitting in pdf417 (≤50 rows)."""
    from pdf417gen import encode as _pdf417_encode

    lo, hi = 1, 2000
    while lo < hi:
        mid = (lo + hi + 1) // 2
        try:
            codes = _pdf417_encode(
                "a" * mid, columns=columns, security_level=PDF417_DEFAULT_SECURITY_LEVEL
            )
            if len(codes) <= 50:
                lo = mid
            else:
                hi = mid - 1
        except ValueError:
            hi = mid - 1
    return lo


# Límites de caracteres por simbología para el contador del diálogo "Texto de muestra".
def get_max_chars_for_symbology(symb: str, value: str = "") -> int:
    """Máximo de caracteres que admite cada simbología (para el contador).

    Longitud fija (EAN/UPC/ISBN/ITF-14) → su longitud exacta.
    Code 39 → CODE39_MAX_CHARS. QR → MAX_PRACTICO_QR.
    Code 128 → dinámico: binary search del máximo de chars que caben a
    módulo mínimo dentro del ancho GS1 (texto ≈54, dígitos ≈106).
    """
    fixed = {
        "ean5": 5,
        "upce": 6,
        "ean8": 8,
        "upca": 12,
        "ean13": 13,
        "isbn13": 13,
        "itf14": 14,
    }
    if symb in fixed:
        return fixed[symb]
    if symb == "code39":
        return CODE39_MAX_CHARS
    if symb == "qr":
        return MAX_PRACTICO_QR
    if symb == "code128":
        cadena = str(value).strip()
        test_char = "0" if cadena.isdigit() else "a"
        max_modules = int(165.10 / 0.25) - 22  # 165.10mm GS1, quiet zones 22 módulos
        lo, hi = 0, 2000
        while lo < hi:
            mid = (lo + hi + 1) // 2
            try:
                modules = get_module_count(test_char * mid)
            except Exception:
                hi = mid - 1
                continue
            if modules <= max_modules:
                lo = mid
            else:
                hi = mid - 1
        return lo
    return 2000  # fallback: sin límite conocido
