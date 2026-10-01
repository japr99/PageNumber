"""
Constantes de la aplicación PageNumber
"""

from i18n import t

# Unidades de medida
UNIT_MM = "mm"
UNIT_PX = "px"

# Las unidades traducibles se definen como claves internas estables.
# NO usar t() aquí: constants.py se importa antes de set_language().
# Usar get_unit_inches() / get_unit_picas() en la UI cuando necesites el string traducido.
UNIT_INCHES = "pulgadas"  # clave interna — se traduce al construir la UI
UNIT_PICAS = "picas"  # clave interna — se traduce al construir la UI


def get_unit_inches() -> str:
    """Devuelve el nombre de la unidad 'pulgadas' en el idioma activo."""
    return t("pulgadas")


def get_unit_picas() -> str:
    """Devuelve el nombre de la unidad 'picas' en el idioma activo."""
    return t("picas")


def get_units() -> list:
    """Devuelve la lista de unidades de medida con los nombres traducidos."""
    return [UNIT_MM, get_unit_inches(), get_unit_picas()]


# Rotaciones disponibles
ROTATIONS = ["0°", "90°", "180°", "270°"]

# Alineamientos
# Las claves internas son los strings en español (idioma base).
# Comparaciones como `if self.current_unit == UNIT_INCHES` siguen funcionando.
ALIGNMENT_LEFT = "izquierda"  # clave interna estable
ALIGNMENT_CENTER = "centro"  # clave interna estable
ALIGNMENT_RIGHT = "derecha"  # clave interna estable


def get_alignments() -> list:
    """Devuelve la lista de alineamientos con las tuplas (clave_, texto_traducido)."""
    return [
        (ALIGNMENT_LEFT, t("izquierda")),
        (ALIGNMENT_CENTER, t("centro")),
        (ALIGNMENT_RIGHT, t("derecha")),
    ]


ALIGNMENTS = [ALIGNMENT_LEFT, ALIGNMENT_CENTER, ALIGNMENT_RIGHT]

# Estilo de texto por defecto
DEFAULT_TEXT_STYLE_ID = "default"
DEFAULT_TEXT_STYLE_NAME = "<Default>"

# Tamaños de página estándar (ancho x alto en mm)
PAGE_SIZES = {
    "A6": (105.0, 148.0),
    "A5": (148.0, 210.0),
    "A4": (210.0, 297.0),
    "A3": (297.0, 420.0),
    "SRA3": (320.0, 450.0),
    "Letter": (215.9, 279.4),
    "Legal": (215.9, 355.6),
    "Tabloid": (279.4, 431.8),
}

# Tamaño de página por defecto
DEFAULT_PAGE_SIZE_NAME = "A4"
DEFAULT_PAGE_WIDTH_MM = PAGE_SIZES["A4"][0]
DEFAULT_PAGE_HEIGHT_MM = PAGE_SIZES["A4"][1]
DEFAULT_BLEED_MM = 0.0  # Sangre por defecto (bleed)

# Escala para visualización en pantalla (mm a píxeles)
# EXACTAMENTE como impo_ui.py: 1 píxel por mm
SCREEN_SCALE = 1.0


def mm_to_screen_pixels(mm):
    """Convierte milímetros a píxeles de pantalla para visualización"""
    return mm * SCREEN_SCALE


def screen_pixels_to_mm(pixels):
    """Convierte píxeles de pantalla a milímetros"""
    return pixels / SCREEN_SCALE


# Conversión mm a puntos PDF (72 DPI)
MM_TO_POINTS = 72.0 / 25.4


def mm_to_points(mm):
    """Convierte milímetros a puntos PDF (72 DPI)"""
    return mm * MM_TO_POINTS


def points_to_mm(points):
    """Convierte puntos PDF (72 DPI) a milímetros"""
    return points / MM_TO_POINTS


# Tamaño de página por defecto en píxeles de pantalla
DEFAULT_PAGE_WIDTH_PIXELS = mm_to_screen_pixels(DEFAULT_PAGE_WIDTH_MM)
DEFAULT_PAGE_HEIGHT_PIXELS = mm_to_screen_pixels(DEFAULT_PAGE_HEIGHT_MM)

# Zoom (factores multiplicativos del zoom automático, como impo_ui.py)
MIN_ZOOM = 0.5  # 0.5x (permite reducir hasta 50% del zoom automático)
MAX_ZOOM = 5.0  # 5.0x (máximo zoom)
DEFAULT_ZOOM = 0.96  # 0.96x (4% de margen, igual que impo_ui.py)
ZOOM_STEP = 1.2  # Factor para aumentar/reducir zoom (×1.2 o ÷1.2)

# Reglas (rulers) - ACTIVAR/DESACTIVAR
ENABLE_RULERS = True  # Cambiar a False para desactivar las reglas

# Unidades de medida para las reglas
UNIT_CM = "cm"
# UNIT_PICAS ya está definido como "picas" (clave interna estable) arriba.
# NO redefinir aquí con t() — rompería las comparaciones en convert_to_mm/convert_from_mm.

RULER_UNITS = {
    UNIT_MM: {
        "name": t("Milímetros"),
        "to_mm": 1.0,
        "major_tick": 10,  # marca mayor cada 10mm (1cm)
        "minor_tick": 5,  # marca media cada 5mm
        "tiny_tick": 1,  # marca menor cada 1mm
        "label_divisor": 10,  # mostrar número cada 10mm
    },
    UNIT_INCHES: {
        "name": t("Pulgadas"),
        "to_mm": 25.4,
        "major_tick": 1,  # marca mayor cada 1"
        "minor_tick": 0.5,  # marca media cada 1/2"
        "tiny_tick": 0.0625,  # marca menor cada 1/16"
        "label_divisor": 1,  # mostrar número cada 1"
    },
    UNIT_PICAS: {
        "name": t("Picas"),
        "to_mm": 4.233,  # 1 pica = 1/6 inch
        "major_tick": 1,  # marca mayor cada 1 pica
        "minor_tick": 0.5,  # marca media cada 0.5 picas (6 puntos)
        "tiny_tick": 0.5,  # marca menor cada 0.5 picas
        "label_divisor": 1,  # mostrar número cada 1 pica
    },
}

# Configuración de numeración por defecto
DEFAULT_START_NUMBER = 1
DEFAULT_END_NUMBER = 125
DEFAULT_INCREMENT = 1
DEFAULT_COPIES = 1

# Posición por defecto para nuevas numeradoras (en mm)
# TODO: Estos valores deberían guardarse en las preferencias del usuario
DEFAULT_POSITION_OFFSET_X = 20  # 20mm desde la izquierda
DEFAULT_POSITION_OFFSET_Y = 20  # 20mm desde arriba

# --- Corrección visual (ajuste fino X) ---
# Estos ratios compensan el "bearing" (espacio en blanco lateral de los glifos)
# y permiten un ajuste manual para que el texto toque visualmente las guías.
# El valor es un factor del tamaño de fuente (ej: 0.08 = 8% del font_size).

# VISOR (Pantalla/Flet):
# IZQUIERDA: Desplaza el texto a la IZQUIERDA (Suma al bearing real).
# CENTRO: Desplaza el texto a la IZQUIERDA (Suma a la mitad del bearing).
# DERECHA: Desplaza el texto a la DERECHA (Empuja el final del texto hacia afuera).
VISUAL_CORRECTION_LEFT = 0.08
VISUAL_CORRECTION_CENTER = 0.00
VISUAL_CORRECTION_RIGHT = 0.04

# PDF (Exportación):
# Misma lógica que el visor para garantizar sincronía WYSIWYG.
# Si el PDF sale distinto al visor, ajustar estos ratios por separado.
PDF_VISUAL_CORRECTION_LEFT = 0.08
PDF_VISUAL_CORRECTION_CENTER = 0.00
PDF_VISUAL_CORRECTION_RIGHT = 0.04

# Calibración visual del anclaje derecho (pt tipográficos).
# Se resta al ancho de anclaje por tinta para empujar el texto ligeramente a la derecha
# cuando el borde visual final del glifo no coincide con el bbox reportado por PyMuPDF.
# Valor inicial de prueba; ajustar en pasos de 0.05 según validación visual.
RIGHT_ANCHOR_VISUAL_COMP_PT = 0.00

# Ajustes visuales de baseline (offset vertical fino) por rotación
# Valores en fracción del tamaño de fuente (font_size). Se añaden a
# `baseline_offset` durante el cálculo de posicionamiento del texto.
# Por defecto 0.0 — ajustar según pruebas WYSIWYG.
VISUAL_BASELINE_ADJUST_0 = 0.00
VISUAL_BASELINE_ADJUST_90 = 0.00
VISUAL_BASELINE_ADJUST_180 = 0.00
VISUAL_BASELINE_ADJUST_270 = 0.00


# Factores de conversión de unidades
# IMPORTANTE: Todos los datos internos se almacenan en MM
MM_PER_CM = 10.0
MM_PER_INCH = 25.4
MM_PER_PICA = 4.233  # 1 pica = 1/6 inch


def convert_to_mm(value, from_unit):
    """
    Convierte un valor de cualquier unidad a milímetros

    Args:
        value: Valor numérico a convertir
        from_unit: Unidad de origen (UNIT_MM, UNIT_CM, UNIT_INCHES, UNIT_PICAS, UNIT_PX)

    Returns:
        Valor convertido a milímetros
    """
    if from_unit == UNIT_MM:
        return value
    elif from_unit == UNIT_CM:
        return value * MM_PER_CM
    elif from_unit == UNIT_INCHES:
        return value * MM_PER_INCH
    elif from_unit == UNIT_PICAS:
        return value * MM_PER_PICA
    elif from_unit == UNIT_PX:
        return screen_pixels_to_mm(value)
    return value


def normalize_decimal_input(e):
    """Reemplaza coma por punto en campos de entrada decimal."""
    val = e.control.value
    if val is not None and "," in str(val):
        e.control.value = str(val).replace(",", ".")
        e.control.update()


def convert_from_mm(value_mm, to_unit):
    """
    Convierte un valor de milímetros a cualquier unidad

    Args:
        value_mm: Valor en milímetros
        to_unit: Unidad de destino (UNIT_MM, UNIT_CM, UNIT_INCHES, UNIT_PICAS, UNIT_PX)

    Returns:
        Valor convertido a la unidad especificada
    """
    if to_unit == UNIT_MM:
        return value_mm
    elif to_unit == UNIT_CM:
        return value_mm / MM_PER_CM
    elif to_unit == UNIT_INCHES:
        return value_mm / MM_PER_INCH
    elif to_unit == UNIT_PICAS:
        return value_mm / MM_PER_PICA
    elif to_unit == UNIT_PX:
        return mm_to_screen_pixels(value_mm)
    return value_mm


def format_unit(value_mm, unit):
    """mm → unidad con decimales según unidad: pulgadas 3, resto 2."""
    dec = 3 if unit == UNIT_INCHES else 2
    return f"{convert_from_mm(value_mm, unit):.{dec}f}"
