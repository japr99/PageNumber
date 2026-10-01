"""
Generador de PDF numerado para PageNumber
Genera PDFs con numeradoras a una o doble cara, con soporte para background image/PDF
"""

import sys

import fitz  # PyMuPDF
import os

import shutil
import re
import tempfile
import unicodedata
import logging
import math
from pathlib import Path
from typing import Dict, Optional, Callable, Tuple, List
from .font_manager import get_default_font_family
from .preferences import get_config_dir
from .constants import RIGHT_ANCHOR_VISUAL_COMP_PT
from .barcode_module import (
    get_barcode_rects,
    get_module_count,
    get_qr_rects,
    get_qr_module_count,
    get_qr_total_size,
    _pdf417_encode_safe,
    _pdf417_barcode_size,
    PDF417_DEFAULT_RATIO,
    get_pdf417_rects,
    get_pdf417_total_size,
    get_pdf417_barcode_width,
    encode_ean13,
    encode_ean8,
    encode_ean5,
    encode_itf14,
    get_ean13_module_count,
    get_ean8_module_count,
    get_ean5_module_count,
    EAN13_GUARD_MODULES,
    EAN8_GUARD_MODULES,
    UPCE_GUARD_MODULES,
    get_upce_module_count,
    validate_isbn13,
    _format_isbn13,
    ISBN_SIZE_OFFSET,
    validate_upca,
    encode_upca,
    validate_upce,
    encode_upce,
    validate_itf14,
    encode_itf14,
    validate_gtin13,
    get_itf14_module_count,
    ITF14_TOTAL_MODULES,
    calc_itf14_dimensions,
    format_itf14_hri,
    gtin13_to_gtin14,
    encode_code39,
    validate_code39,
    get_code39_module_count,
    get_datamatrix_rects,
    _format_hri_lines,
    preparar_cadena_gs1_datamatrix,
)
from .excel_manager import ExcelManager
from .excel_rows import excel_row_index
import builtins
from .error_logger import log_error

def _apply_text_case_filter(text: str, filter_type: str) -> str:
    if not text or not filter_type:
        return text
    if filter_type == "upper":
        return text.upper()
    elif filter_type == "lower":
        return text.lower()
    elif filter_type == "capitalize":
        return text[:1].upper() + text[1:] if text else text
    return text

# Silenciar prints de depuración en este módulo por defecto.
# Para activar, cambiar _PRINT_DEBUG = True durante desarrollo.
_PRINT_DEBUG = False
if not _PRINT_DEBUG:

    def _no_print(*args, **kwargs):
        return None

    print = _no_print

# Flag para debug de coordenadas Y en DORSO (independiente de _PRINT_DEBUG)
_DEBUG_DORSO_Y = False
if _DEBUG_DORSO_Y:

    def _debug_y(*args, **kwargs):
        import builtins

        builtins.print("[DEBUG_Y]", *args, **kwargs)

else:

    def _debug_y(*args, **kwargs):
        pass


logger = logging.getLogger(__name__)

# Caché global de fuentes: clave -> dict{fitz_name, font_obj, fontbuffer(optional)}
FONT_CACHE: Dict[Tuple[str, str], Dict] = {}

FONT_PT_TO_MM = 0.3528


def _font_cache_key(font_name: str, font_style: str) -> Tuple[str, str]:
    return (font_name.strip(), font_style.strip())


def _fallback_base14_fontname(font_name: str, font_style: str) -> str:
    """Selecciona una fuente Base-14 de PDF respetando estilo Bold/Italic.

    Se usa cuando no hay archivo de fuente cargable por runtime.
    """
    n = (font_name or "").lower()
    s = (font_style or "").lower()

    is_bold = any(t in s for t in ("bold", "black", "heavy", "semibold", "demi"))
    is_italic = any(t in s for t in ("italic", "oblique", "it", "obl"))

    if "times" in n:
        if is_bold and is_italic:
            return "timesbi"
        if is_bold:
            return "timesb"
        if is_italic:
            return "timesi"
        return "times"

    if "courier" in n:
        if is_bold and is_italic:
            return "courbi"
        if is_bold:
            return "courb"
        if is_italic:
            return "couri"
        return "cour"

    # Sans fallback por defecto (Helvetica family)
    if is_bold and is_italic:
        return "helvbi"
    if is_bold:
        return "helvb"
    if is_italic:
        return "helvi"
    return "helv"


def _ensure_font_cached(
    font_name: str,
    font_style: str,
    page: fitz.Page,
    font_path: Optional[str] = None,
    font_index: Optional[int] = None,
) -> Tuple[str, fitz.Font]:
    """
    Garantiza que la fuente solicitada esté cargada y registrada en PyMuPDF,
    utilizando la caché si está disponible. Devuelve (fitz_fontname, fitz.Font).

    Args:
        font_name: Nombre de la familia de fuente
        font_style: Estilo de la fuente (Regular, Bold, Italic, etc.)
        page: Página de PyMuPDF donde registrar la fuente
        font_path: Ruta opcional al archivo de fuente (resolved_font_path)
        font_index: Índice opcional para archivos TTC (resolved_font_index)
    """
    import hashlib

    key = _font_cache_key(font_name, font_style)

    # Si se proporciona font_path, verificar si coincide con la caché
    # Si es diferente, invalidar caché y cargar nueva fuente
    if font_path and key in FONT_CACHE:
        cached_path = FONT_CACHE[key].get("fontfile")
        if cached_path != font_path:
            print(
                f"[PDF FONT] Path cambió de '{cached_path}' a '{font_path}', invalidando caché"
            )
            del FONT_CACHE[key]

    if key in FONT_CACHE:
        entry = FONT_CACHE[key]
        fitz_name = entry.get("fitz_name")

        # Si la entrada cacheada es fallback (sin archivo/buffer), revalidar estilo.
        if not entry.get("fontbuffer") and not entry.get("fontfile"):
            expected_fallback = _fallback_base14_fontname(font_name, font_style)
            if fitz_name != expected_fallback:
                entry["fitz_name"] = expected_fallback
                entry["font_obj"] = fitz.Font(expected_fallback)
                fitz_name = expected_fallback

        # Intentar (re)registrar la fuente en el documento/página actual
        try:
            safe_name = fitz_name.replace(" ", "") if fitz_name else None
            # Preferir fontbuffer si está disponible
            if "fontbuffer" in entry and entry["fontbuffer"] is not None:
                try:
                    page.insert_font(
                        fontname=safe_name or fitz_name, fontbuffer=entry["fontbuffer"]
                    )
                except Exception as ex:
                    if _PRINT_DEBUG:
                        print(
                            f"[PDF FONT][WARN] No se pudo insertar fontbuffer en la página: {ex}"
                        )
            elif "fontfile" in entry and entry["fontfile"]:
                try:
                    page.insert_font(
                        fontname=safe_name or fitz_name, fontfile=entry["fontfile"]
                    )
                except Exception as ex:
                    if _PRINT_DEBUG:
                        print(
                            f"[PDF FONT][WARN] insert_font(fontfile) falló: {ex}. Intentando con fontbuffer..."
                        )
                    try:
                        with open(entry["fontfile"], "rb") as fh:
                            fb = fh.read()
                        page.insert_font(fontname=safe_name or fitz_name, fontbuffer=fb)
                        # Guardar buffer en caché para futuros usos
                        entry["fontbuffer"] = fb
                        print(
                            f"[PDF FONT] Fallback con fontbuffer OK, cacheada la buffer para {fitz_name}"
                        )
                    except Exception as ex2:
                        logger.exception("[PDF FONT] Fallback con fontbuffer falló")
        except Exception as ex:
            logger.exception("[PDF FONT] Error re-registrando fuente en página")

        # Construir un fitz.Font válido para métricas/uso
        try:
            if "fontbuffer" in entry and entry["fontbuffer"] is not None:
                font_obj = fitz.Font(fontbuffer=entry["fontbuffer"])
            else:
                default_fitz = _fallback_base14_fontname(font_name, font_style)
                font_obj = fitz.Font(entry.get("fitz_name") or default_fitz)
        except Exception:
            default_fitz = _fallback_base14_fontname(font_name, font_style)
            font_obj = fitz.Font(default_fitz)

        print(f"[PDF FONT] Usando fuente cacheada: {fitz_name}")
        return entry.get("fitz_name"), font_obj

    # Si no está en cache, intentar cargar la fuente
    fitz_fontname = None
    font_obj = None
    fontbuffer = None

    # PRIORIDAD 1: Usar font_path si se proporcionó (desde resolved_font_path)
    if font_path and os.path.exists(font_path):
        try:
            print(f"[PDF FONT] Cargando fuente desde resolved_font_path: {font_path}")
            # TTC: extraer el subfont correcto (el TTC completo cargado con
            # fontbuffer usa el subfont 0 = Regular, perdiendo Bold/Condensed/etc).
            if (
                font_path.lower().endswith((".ttc", ".otc"))
                and font_index is not None
            ):
                subfont = _extract_font_from_ttc(font_path, font_index)
                if subfont:
                    fontbuffer = subfont
                    print(
                        f"[PDF FONT] TTC extraído subfont index {font_index}: {len(fontbuffer)} bytes"
                    )
                else:
                    with open(font_path, "rb") as fh:
                        fontbuffer = fh.read()
            else:
                with open(font_path, "rb") as fh:
                    fontbuffer = fh.read()

            # Construir un nombre limpio para PyMuPDF
            safe_fontname = (font_name + font_style).replace(" ", "")

            # Registrar en la página
            try:
                page.insert_font(fontname=safe_fontname, fontbuffer=fontbuffer)
                fitz_fontname = safe_fontname
            except Exception as ex:
                if _PRINT_DEBUG:
                    print(
                        f"[PDF FONT][WARN] insert_font falló: {ex}, usando fitz.Font directo"
                    )
                fitz_fontname = safe_fontname

            # Crear objeto Font para métricas
            font_obj = fitz.Font(fontbuffer=fontbuffer)

            # Cachear
            FONT_CACHE[key] = {
                "fitz_name": fitz_fontname,
                "font_obj": font_obj,
                "fontbuffer": fontbuffer,
                "fontfile": font_path,
            }
            print(
                f"[PDF FONT] ✓ Fuente cargada y cacheada: {fitz_fontname} desde {os.path.basename(font_path)}"
            )
            return fitz_fontname, font_obj
        except Exception as e:
            logger.exception(
                "[PDF FONT] No se pudo cargar desde font_path '%s'", font_path
            )
            # Continuar con fallback

    # PRIORIDAD 2: Fallback a Fuente por Defecto
    default_family = get_default_font_family()
    print(f"[PDF FONT] Usando fallback {default_family} para {font_name}/{font_style}")
    fitz_fontname = _fallback_base14_fontname(font_name, font_style)
    font_obj = fitz.Font(fitz_fontname)
    FONT_CACHE[key] = {
        "fitz_name": fitz_fontname,
        "font_obj": font_obj,
    }

    print(f"[PDF FONT] Usando fuente: {fitz_fontname}")
    return fitz_fontname, font_obj


def preload_fonts(styles: Tuple[Dict, ...], page: Optional[fitz.Page] = None) -> None:
    """
    Pre-carga y cachea todas las fuentes referenciadas en `styles`.
    `styles` es un iterable de diccionarios `text_style`.
    Si `page` es None, se crea un documento temporal para registrar fuentes.
    """
    # Si no se provee página, crear un documento temporal para insertar fuentes
    need_close_doc = False
    doc = None
    try:
        if page is None:
            doc = fitz.open()
            page = doc.new_page()
            need_close_doc = True

        seen = set()
        for style in styles:
            fn = style.get("font_name", "Helvetica")
            fs = style.get("font_style", "Regular")
            key = _font_cache_key(fn, fs)
            if key in seen:
                continue
            seen.add(key)
            try:
                _ensure_font_cached(fn, fs, page)
            except Exception as e:
                builtins.print(f"[PRELOAD] Error al cachear fuente {fn} {fs}: {e}")
    finally:
        if need_close_doc and doc is not None:
            doc.close()


# ══════════════════════════════════════════════════════════════════════════════
# CONSTANTES Y CONVERSIONES
# ══════════════════════════════════════════════════════════════════════════════

# Constantes de conversión mm ↔ pt (puntos PostScript)
MM_TO_PT = 72.0 / 25.4  # 1 mm = 2.834645 pt
PT_TO_MM = 25.4 / 72.0  # 1 pt = 0.352778 mm


def mm_to_pt(mm: float) -> float:
    """Convierte milímetros a puntos PostScript"""
    return mm * MM_TO_PT


def pt_to_mm(pt: float) -> float:
    """Convierte puntos PostScript a milímetros"""
    return pt * PT_TO_MM


# ══════════════════════════════════════════════════════════════════════════════
# FUNCIONES DE CAJAS PDF (MediaBox, TrimBox, BleedBox)
# ══════════════════════════════════════════════════════════════════════════════


def set_pdf_boxes(
    page: fitz.Page, width_mm: float, height_mm: float, bleed_mm: float
) -> None:
    """
    Define las cajas PDF (MediaBox, TrimBox, BleedBox) en una página.

    IMPORTANTE para preimpresión:
    - MediaBox: Tamaño físico total (con sangre): width+bleed*2 × height+bleed*2
    - TrimBox: Tamaño de corte final (sin sangre): width × height
    - BleedBox: Área de sangre (igual que MediaBox)

    Args:
        page: Página de fitz donde definir las cajas
        width_mm: Ancho del documento en mm (sin sangre)
        height_mm: Alto del documento en mm (sin sangre)
        bleed_mm: Sangre en mm
    """
    # Convertir dimensiones a puntos
    width_pt = mm_to_pt(width_mm)
    height_pt = mm_to_pt(height_mm)
    bleed_pt = mm_to_pt(bleed_mm)

    # Solo definir TrimBox y BleedBox si hay sangre
    if bleed_mm > 0:
        # TrimBox: Área de corte final (offset por el bleed)
        trimbox = fitz.Rect(
            bleed_pt, bleed_pt, width_pt + bleed_pt, height_pt + bleed_pt
        )
        page.set_trimbox(trimbox)

        # BleedBox: Debe ser igual al MediaBox (que ya incluye el bleed)
        # Usamos el MediaBox actual de la página en lugar de recalcular
        mediabox = page.mediabox
        page.set_bleedbox(mediabox)


# ══════════════════════════════════════════════════════════════════════════════
# RENDERIZADO DE NUMERADORAS
# ══════════════════════════════════════════════════════════════════════════════


def _inject_thousands_separator(text: str, separator_type: str) -> str:
    """
    Inyecta separadores de millares en un texto arbitrario, contando solo dígitos.
    Ej: "001-234" -> "001-.234" (si separator='punto')
    """
    if separator_type == "normal" or not text:
        return text

    separators = {"punto": ".", "espacio": " ", "coma": ","}
    sep_char = separators.get(separator_type, "")
    if not sep_char:
        return text

    # Recorrer de derecha a izquierda
    result = []
    digit_count = 0
    pending_separator = False

    digits_only = [c for c in text if c.isdigit()]
    if not digits_only:
        return text

    for i, char in enumerate(reversed(text)):
        if char.isdigit():
            digit_count += 1
            result.append(char)

            if digit_count > 0 and digit_count % 3 == 0:
                remaining_text = text[: len(text) - 1 - i]
                if any(c.isdigit() for c in remaining_text):
                    result.append(sep_char)
        else:
            result.append(char)

    return "".join(reversed(result))


def apply_mask_format(number: str, mask: str, separator_type: str = "normal") -> str:
    """
    Aplica máscara simplificada (placeholder '0') y luego inyecta separadores.
    Replica la lógica de la UI para garantizar consistencia WYSIWYG.
    """
    str_number = str(number)

    if not mask:
        # Sin máscara, solo aplicar separador estándar si el número >= 1000
        try:
            val = float(str_number)
            if abs(val) < 1000:
                return str_number
        except ValueError:
            pass
        return _inject_thousands_separator(str_number, separator_type)

    # 1. Contar slots '0' (implícito)
    num_slots = mask.count("0")

    # 2. Padding del número
    if len(str_number) < num_slots:
        digits = str_number.zfill(num_slots)
    else:
        digits = str_number

    # 3. Si el número es más largo que la máscara, truncar a los primeros dígitos
    if len(digits) > num_slots:
        filled_digits = digits[:num_slots]
    else:
        filled_digits = digits

    # 4. Rellenar máscara
    result_chars = list(mask)
    digit_idx = len(filled_digits) - 1

    # Recorrer máscara de DERECHA a IZQUIERDA para llenar slots
    for i in range(len(result_chars) - 1, -1, -1):
        if result_chars[i] == "0":
            if digit_idx >= 0:
                result_chars[i] = filled_digits[digit_idx]
                digit_idx -= 1
            else:
                result_chars[i] = "0"

    base_result = "".join(result_chars)

    full_result = base_result

    # 6. Inyectar separadores solo si el valor numérico >= 1000 (HELP_NUMBER_FORMAT_RULE_AFTER)
    try:
        val = float(str_number)
        if abs(val) >= 1000:
            final_result = _inject_thousands_separator(full_result, separator_type)
        else:
            final_result = full_result
    except (ValueError, TypeError):
        final_result = full_result

    return final_result


def _build_pdf_segments(
    segments,
    font_obj,
    font_size,
    alignment,
    rotation,
    x_pt,
    y_pt,
    letter_spacing=0.0,
    prefix="",
    text_val="",
    suffix="",
    resolved_font_path=None,
):
    """
    Calcula métricas de posicionamiento compartidas entre numeradora y texto variable.
    Retorna: seg_widths, total_width, right_align_width,
             dir_x, dir_y, pdf_rotation, pen_x, pen_y, alignment.
    """
    alignment_map = {
        "izquierda": "left",
        "centro": "center",
        "derecha": "right",
        "left": "left",
        "center": "center",
        "right": "right",
    }
    align = alignment_map.get(alignment, "left")

    # Ancho por segmento: cada segmento (prefix/number/suffix) añade
    # letter_spacing ENTRE caracteres (n-1 huecos); letter_spacing==0 usa
    # text_length nativo. prefix_suffix_spacing va ENTRE segmentos, aparte.
    from .variable_text_measure import measure_text_advance_with_spacing

    seg_widths = []
    for seg in segments:
        if letter_spacing:
            seg_widths.append(
                measure_text_advance_with_spacing(
                    font_obj, seg["text"], font_size, letter_spacing
                )
            )
        else:
            seg_widths.append(font_obj.text_length(seg["text"], fontsize=font_size))

    # Ancho total con inter-segment spacing (el letter_spacing del número ya
    # va dentro de seg_widths; aquí solo se suman los gaps entre bloques).
    total_width = 0.0
    for i, sw in enumerate(seg_widths):
        total_width += sw
        if i < len(seg_widths) - 1:
            total_width += segments[i].get("spacing", 0.0)

    # Right-anchor: ancho basado en borde de tinta real de cada glifo
    right_align_width = total_width
    if align == "right":
        try:
            font_path_for_measure = resolved_font_path
            if font_path_for_measure and os.path.exists(str(font_path_for_measure)):
                from .metrics_analisys import DEFAULT_FONT_METRICS

                display_text = f"{prefix}{text_val}{suffix}"
                number_start = len(prefix)
                number_end = number_start + len(text_val)
                pen_pt = 0.0
                max_right_pt = 0.0
                for i, ch in enumerate(display_text):
                    char_metrics = DEFAULT_FONT_METRICS.measure_text(
                        str(font_path_for_measure), int(font_size), ch
                    )
                    char_left_pt = float(char_metrics.get("left_bearing", 0.0))
                    char_ink_width_pt = float(char_metrics.get("width", 0.0))
                    char_right_pt = pen_pt + char_left_pt + char_ink_width_pt
                    if char_right_pt > max_right_pt:
                        max_right_pt = char_right_pt
                    adv_pt = float(font_obj.text_length(ch, fontsize=font_size))
                    pen_pt += adv_pt
                    if letter_spacing != 0 and i < len(display_text) - 1:
                        pen_pt += letter_spacing
                right_align_width = max_right_pt
        except Exception:
            pass

        if RIGHT_ANCHOR_VISUAL_COMP_PT != 0:
            right_align_width = max(0.0, right_align_width - RIGHT_ANCHOR_VISUAL_COMP_PT)

    # Vectores de dirección por rotación
    rad = math.radians(rotation)
    dir_x = math.cos(rad)
    dir_y = math.sin(rad)
    pdf_rotation = -rotation

    # Punto inicial ajustado por alineación
    pen_x = x_pt
    pen_y = y_pt
    if align == "center":
        pen_x -= (total_width / 2) * dir_x
        pen_y -= (total_width / 2) * dir_y
    elif align == "right":
        pen_x -= right_align_width * dir_x
        pen_y -= right_align_width * dir_y

    return {
        "seg_widths": seg_widths,
        "total_width": total_width,
        "right_align_width": right_align_width,
        "dir_x": dir_x,
        "dir_y": dir_y,
        "pdf_rotation": pdf_rotation,
        "pen_x": pen_x,
        "pen_y": pen_y,
        "alignment": align,
    }


def render_numeradora_to_pdf(
    page: fitz.Page,
    raw_number: str,
    # ... (rest of signature same as before) ...
    x_mm: float,
    y_mm: float,
    bleed_mm: float,
    text_style: Dict,
    rotation: int,
    alignment: str,
    page_width_mm: float,
    page_height_mm: float,
    x_offset_mm: float = 0.0,  # Ajuste horizontal (mm) que el usuario puede especificar en la posición
) -> None:
    """
    Renderiza una numeradora en la página PDF.
    """
    if _PRINT_DEBUG:
        print("\n" + "=" * 80)
        print("RENDER_NUMERADORA_TO_PDF - PARÁMETROS RECIBIDOS")
        print("=" * 80)
        print(f"raw_number: '{raw_number}'")
        print(f"x_mm: {x_mm}, y_mm: {y_mm}")
        print(f"bleed_mm: {bleed_mm}")
        print(f"rotation: {rotation}")
        print(f"alignment: {alignment}")
        print(f"page_width_mm: {page_width_mm}, page_height_mm: {page_height_mm}")
        print(f"\nTEXT_STYLE completo:")
        for key, value in text_style.items():
            print(f"  {key}: {value}")
        print("=" * 80 + "\n")

    # Convertir coordenadas a puntos y agregar offset de bleed
    x_pt = mm_to_pt(x_mm + bleed_mm)
    y_pt = mm_to_pt(y_mm + bleed_mm)

    _debug_y(
        f"[render_numeradora_to_pdf] y_mm={y_mm} bleed={bleed_mm} y_pt={y_pt:.2f} (from top={y_pt*PT_TO_MM - bleed_mm:.2f}mm) x_offset_mm={x_offset_mm}"
    )

    # Aplicar ajuste horizontal por posición si lo hay (x_offset_mm)
    if x_offset_mm:
        adj_pt = mm_to_pt(x_offset_mm)
        x_pt += adj_pt
        if _PRINT_DEBUG:
            print(f"  x_offset_mm aplicado: {x_offset_mm}mm -> {adj_pt:.2f}pt")

    # MODIFICACIÓN: NO Invertir Y.
    # El análisis determinó que para corregir el posicionamiento espejo,
    # debemos tratar el sistema como Top-Left, coincidiendo con lo observado.

    # page_height_with_bleed_pt = mm_to_pt(page_height_mm + bleed_mm * 2)
    # y_pt = page_height_with_bleed_pt - y_pt

    # IMPORTANTE: PyMuPDF insert_text() usa la BASELINE del texto como referencia
    # El viewer usa la parte SUPERIOR (top) del bounding box del texto
    # Para compensar, necesitamos sumar el tamaño de fuente (altura del texto)
    # Esto mueve el baseline hacia abajo, colocando el top del texto en y_mm
    # Nota: Usaremos el font_size más adelante cuando esté disponible

    if _PRINT_DEBUG:
        print(f"CONVERSIÓN DE COORDENADAS (LOGICA TOP-LEFT APLICADA):")
        print(f"  x_mm={x_mm} + bleed_mm={bleed_mm} = {x_mm + bleed_mm}mm → {x_pt}pt")
        print(f"  y_mm={y_mm} + bleed_mm={bleed_mm} = {y_mm + bleed_mm}mm → {y_pt}pt")
        print(f"  [INFO] Se usa y_pt directo sin invertir (coincide con Viewer)\n")

    # Extraer datos de estilo
    font_name = text_style.get("font_name", "Helvetica")
    font_style = text_style.get(
        "font_style", "Regular"
    )  # "Regular", "Bold", "Italic", etc.
    font_size = text_style.get("font_size", 12)
    number_color = text_style.get("number_color", (0, 0, 0))
    prefix_color = text_style.get("prefix_color", number_color)
    suffix_color = text_style.get("suffix_color", number_color)
    prefix = text_style.get("prefix", "")
    suffix = text_style.get("suffix", "")
    letter_spacing = text_style.get("letter_spacing", 0.0)
    prefix_suffix_spacing = text_style.get("prefix_suffix_spacing", 0.0)

    # Extraer rutas de fuente resueltas (si están disponibles)
    resolved_font_path = text_style.get("resolved_font_path")
    resolved_font_index = text_style.get("resolved_font_index")

    if _PRINT_DEBUG:
        print(f"\n{'='*80}")
        print(
            f"[render_numeradora_to_pdf] TEXT_STYLE recibido tiene {len(text_style)} campos:"
        )
        print(f"  Claves: {list(text_style.keys())}")
        print(f"[render_numeradora_to_pdf] resolved_font_path: {resolved_font_path}")
        print(f"[render_numeradora_to_pdf] resolved_font_index: {resolved_font_index}")
        if resolved_font_path:
            print(
                f"[render_numeradora_to_pdf] ✓ Archivo existe: {Path(resolved_font_path).exists()}"
            )
        else:
            print(
                f"[render_numeradora_to_pdf] ⚠️ NO HAY resolved_font_path - usará fallback"
            )
        print(f"{'='*80}\n")

    # Mapear fuente (incluyendo estilo)
    fitz_fontname = _map_font_name(font_name, font_style)

    if _PRINT_DEBUG:
        print(f"DATOS EXTRAÍDOS DEL ESTILO:")
        print(
            f"  font_name: '{font_name}' font_style: '{font_style}' → fitz: '{fitz_fontname}'"
        )
        print(f"  font_size: {font_size}pt")
        print(f"  prefix: '{prefix}', suffix: '{suffix}'")
        print(
            f"  letter_spacing: {letter_spacing}pt, prefix_suffix_spacing: {prefix_suffix_spacing}pt"
        )
        print(f"  number_color: {number_color}")
        print(f"  prefix_color: {prefix_color}")
        print(f"  suffix_color: {suffix_color}\n")

    # Normalizar formatos de color variados a lo que PyMuPDF espera:
    # - RGB como hex string "#RRGGBB" -> (r,g,b) floats 0..1
    # - RGB tuple en 0..255 -> convert to 0..1
    # - RGB tuple en 0..1 -> keep
    # - CMYK tuple (4 vals) ya se entrega en 0..1 desde _get_text_style_data
    def _normalize_color(c):
        # CMYK (4 values) -> keep as-is
        try:
            if isinstance(c, (list, tuple)) and len(c) == 4:
                return tuple(float(v) for v in c)
            # Hex string
            if isinstance(c, str) and c.startswith("#"):
                h = c.lstrip("#")
                if len(h) == 6:
                    r = int(h[0:2], 16) / 255.0
                    g = int(h[2:4], 16) / 255.0
                    b = int(h[4:6], 16) / 255.0
                    return (r, g, b)
            # Tuple/list with 3 values: detect scale
            if isinstance(c, (list, tuple)) and len(c) == 3:
                vals = [float(v) for v in c]
                # If values look like 0..255 integers, scale down
                if max(vals) > 1.0:
                    return (vals[0] / 255.0, vals[1] / 255.0, vals[2] / 255.0)
                return tuple(vals)
        except Exception:
            pass
        # Fallback negro
        return (0.0, 0.0, 0.0)

    number_color = _normalize_color(number_color)
    prefix_color = _normalize_color(prefix_color)
    suffix_color = _normalize_color(suffix_color)

    if _PRINT_DEBUG:
        print(f"  prefix_color(normalized): {prefix_color}")
        print(f"  number_color(normalized): {number_color}")
        print(f"  suffix_color(normalized): {suffix_color}\n")

    # Construir string completo para calcular alignment
    full_text = f"{prefix}{raw_number}{suffix}"

    # ══════════════════════════════════════════════════════════════════════
    # MANEJO ROBUSTO DE FUENTES CON FITZ.FONT
    # ══════════════════════════════════════════════════════════════════════
    # En lugar de usar fitz_fontname (string) que puede fallar si la fuente no está registrada,
    # instanciamos un objeto fitz.Font explícito. Esto nos permite cargar desde archivo si es necesario
    # y usar ese objeto para TODOS los cálculos de métricas.

    # Usar caché de fuentes para evitar lecturas/extracciones repetidas desde disco
    try:
        fitz_fontname, font_obj = _ensure_font_cached(
            font_name,
            font_style,
            page,
            font_path=resolved_font_path,
            font_index=resolved_font_index,
        )
    except Exception as e:
        print(
            f"[WARN] Falló la carga en caché de la fuente '{font_name} {font_style}': {e}"
        )
        fitz_fontname = "helv"
        font_obj = fitz.Font("helv")

    # CALCULAR MÉTRICAS USANDO EL OBJETO FONT (Seguro)

    # CALCULAR MÉTRICAS USANDO EL OBJETO FONT (Seguro)
    try:
        text_length = font_obj.text_length(full_text, fontsize=font_size)

        prefix_width = font_obj.text_length(prefix, fontsize=font_size) if prefix else 0
        number_width = font_obj.text_length(raw_number, fontsize=font_size)
        suffix_width = font_obj.text_length(suffix, fontsize=font_size) if suffix else 0
    except Exception as e:
        builtins.print(f"[CRITICAL ERROR] Falló cálculo de métricas incluso con fallback: {e}")
        return

    # IMPORTANTE: fitz.get_text_length() NO incluye letter_spacing.
    # El interletraje se aplica a todos los segmentos (prefix/number/suffix),
    # entre caracteres (n-1 huecos por segmento).
    if letter_spacing != 0 and (raw_number or prefix or suffix):
        from .variable_text_measure import measure_text_advance_with_spacing

        number_width = measure_text_advance_with_spacing(
            font_obj, raw_number, font_size, letter_spacing
        )
        if prefix:
            prefix_width = measure_text_advance_with_spacing(
                font_obj, prefix, font_size, letter_spacing
            )
        if suffix:
            suffix_width = measure_text_advance_with_spacing(
                font_obj, suffix, font_size, letter_spacing
            )
        text_length = prefix_width + number_width + suffix_width

    if _PRINT_DEBUG:
        print(f"MEDIDAS DE TEXTO (Calculadas con objeto Font):")
        print(f"  prefix_width: {prefix_width}pt (con letter_spacing={letter_spacing})")
        print(f"  number_width: {number_width}pt (con letter_spacing={letter_spacing})")
        print(f"  suffix_width: {suffix_width}pt (con letter_spacing={letter_spacing})")
        print(f"  text_length (full): {text_length}pt\n")

    if _PRINT_DEBUG:
        print(f"ALINEACIÓN: {alignment}")
        print(f"Posición de referencia: x_pt={x_pt}pt, y_pt={y_pt}pt")
        print(
            f"  (debug) incoming x_mm={x_mm}mm, bleed_mm={bleed_mm}mm, x_pt(before offset)={x_pt:.2f}pt"
        )
        print(f"  (debug) received x_offset_mm argument = {x_offset_mm}mm")

    # ══════════════════════════════════════════════════════════════════════
    # RENDERIZADO CARÁCTER POR CARÁCTER (CMYK + letter-spacing manual)
    # ══════════════════════════════════════════════════════════════════════
    #
    # Usamos insert_text() renderizando cada carácter individualmente para:
    # 1. Soporte CMYK nativo (importante para impresión)
    # 2. Letter-spacing preciso (simulado manualmente)
    # 3. Sin cajas HTML visibles en el PDF
    # ══════════════════════════════════════════════════════════════════════

    # Documento padre (necesario para operaciones de Separation/SPOT)
    doc = page.parent

    # Determinar espacio de color por segmento
    color_space = text_style.get("color_space", "RGB")  # legacy fallback
    _seg_spaces = {
        "number": text_style.get("number_color_space", color_space),
        "prefix": text_style.get("prefix_color_space", color_space),
        "suffix": text_style.get("suffix_color_space", color_space),
    }

    if _PRINT_DEBUG:
        print(f"COLORES:")
        print(
            f"  Color spaces: number={_seg_spaces['number']}, prefix={_seg_spaces['prefix']}, suffix={_seg_spaces['suffix']}"
        )
        print(f"  prefix_color: {prefix_color}")
        print(f"  number_color: {number_color}")
        print(f"  suffix_color: {suffix_color}\n")

    # Para SPOT: preparar los Separation aliases (uno por segmento si tienen nombre distinto)
    # Los colores en `prefix_color`, `number_color`, `suffix_color` ya son CMYK en 0-1
    # (extraídos correctamente por _get_text_style_data para SPOT)
    _spot_aliases = {}  # mapeo nombre → alias
    _spot_names = {
        "number": text_style.get("number_color_name", "") or "",
        "prefix": text_style.get("prefix_color_name", "") or "",
        "suffix": text_style.get("suffix_color_name", "") or "",
    }
    _spot_tints = {
        "number": float(text_style.get("number_color_tint", 100.0)),
        "prefix": float(text_style.get("prefix_color_tint", 100.0)),
        "suffix": float(text_style.get("suffix_color_tint", 100.0)),
    }
    _spot_colors = {
        "number": number_color,
        "prefix": prefix_color,
        "suffix": suffix_color,
    }
    for seg_key, seg_color_01 in _spot_colors.items():
        if _seg_spaces[seg_key] != "SPOT":
            continue
        spot_name = _spot_names[seg_key]
        if not spot_name:
            # Sin nombre de tinta → renderizar como CMYK proceso (no crear Separation)
            continue
        if spot_name not in _spot_aliases:
            alias = _define_spot_colorspace(doc, page, spot_name, seg_color_01)
            _spot_aliases[spot_name] = alias

    # Construir lista de segmentos con su texto, color y spacing
    segments = []

    if prefix:
        segments.append(
            {
                "text": prefix,
                "color": prefix_color,
                "spacing": prefix_suffix_spacing if prefix_suffix_spacing != 0 else letter_spacing,
                "type": "prefix",
            }
        )

    segments.append(
        {
            "text": raw_number,
            "color": number_color,
            "spacing": prefix_suffix_spacing if prefix_suffix_spacing != 0 else letter_spacing,
            "type": "number",
        }
    )

    if suffix:
        segments.append(
            {
                "text": suffix,
                "color": suffix_color,
                "spacing": prefix_suffix_spacing if prefix_suffix_spacing != 0 else letter_spacing,
                "type": "suffix",
            }
        )

    # ── Posicionamiento compartido (reutilizado por texto variable) ──
    pdf_data = _build_pdf_segments(
        segments, font_obj, font_size, alignment, rotation,
        x_pt, y_pt,
        letter_spacing=letter_spacing,
        prefix=prefix, text_val=raw_number, suffix=suffix,
        resolved_font_path=resolved_font_path,
    )
    segment_widths = pdf_data["seg_widths"]
    total_width = pdf_data["total_width"]
    right_align_width = pdf_data["right_align_width"]
    dir_x = pdf_data["dir_x"]
    dir_y = pdf_data["dir_y"]
    pdf_rotation = pdf_data["pdf_rotation"]
    pen_x = pdf_data["pen_x"]
    pen_y = pdf_data["pen_y"]
    alignment_normalized = pdf_data["alignment"]

    if _PRINT_DEBUG:
        x_start = x_pt
        y_baseline = y_pt
        print(f"\nPOSICIONAMIENTO:")
        print(f"  x_pt: {x_pt:.2f}pt, y_pt: {y_pt:.2f}pt ({y_pt * PT_TO_MM:.2f}mm desde bottom)")
        print(f"  rotation: {rotation}°")
        print(f"  x_start: {x_start:.2f}pt, y_baseline: {y_baseline:.2f}pt")
        print(f"  total_width: {total_width:.2f}pt, alignment: {alignment_normalized}")
        if alignment_normalized == "right":
            print(f"  right_align_width: {right_align_width:.3f}pt")
        print(f"  Rotación Flet: {rotation}° (Vectores: dx={dir_x:.3f}, dy={dir_y:.3f})")
        print(f"  Rotación PDF: {pdf_rotation}°")
        print(f"  Punto Inicio: ({pen_x:.2f}, {pen_y:.2f})\n")

    char_count = 0

    for seg_idx, seg in enumerate(segments):
        seg_text = seg["text"]
        seg_color = seg["color"]
        # seg_spacing se ignora dentro del bloque, solo se usa para separar bloques si fuera necesario
        # Pero nuestra lógica de total_width ya sumó spacing.
        # Al renderizar el bloque entero, insert_text NO aplica spacing extra entre caracteres.

        if _PRINT_DEBUG:
            print(f"  Segmento {seg_idx + 1}: '{seg_text}' color={seg_color}")

        # Calcular ancho del segmento completo
        seg_width = segment_widths[seg_idx]

        # Renderizar BLOQUE COMPLETO
        point = fitz.Point(pen_x, pen_y)

        # Para SPOT: registrar xrefs actuales antes de la inserción
        spot_alias = None
        prev_xrefs = None
        seg_type = seg.get("type", "number")
        seg_is_spot = _seg_spaces.get(seg_type, "RGB") == "SPOT"
        if seg_is_spot:
            seg_spot_name = _spot_names.get(seg_type, "")
            spot_alias = _spot_aliases.get(seg_spot_name)
            if spot_alias:
                prev_xrefs = set(page.get_contents())

        try:
            # page.insert_text necesita el nombre registrado o una fuente base
            # Si hemos registrado la fuente arriba con insert_font(fontname=fitz_fontname, ...), esto funcionará
            if letter_spacing != 0 and seg_text:
                # Interletraje: renderizar cada segmento carácter a carácter,
                # avanzando el lápiz por text_length(ch) + letter_spacing a lo
                # largo de la dirección de rotación (replica el bloque + rotate).
                # El kerning nativo se pierde SOLO cuando letter_spacing != 0.
                cur_x, cur_y = pen_x, pen_y
                for ch in seg_text:
                    page.insert_text(
                        fitz.Point(cur_x, cur_y),
                        ch,
                        fontname=fitz_fontname,
                        fontsize=font_size,
                        color=seg_color,
                        rotate=pdf_rotation,
                    )
                    char_count += 1
                    # Para SPOT: inyectar operadores Separation en el nuevo stream de contenido
                    if seg_is_spot and spot_alias and prev_xrefs is not None:
                        spot_tint_pct = _spot_tints.get(seg.get("type", "number"), 100.0)
                        ok = _inject_spot_operators(
                            doc, page, spot_alias, prev_xrefs, spot_tint_pct
                        )
                        if ok:
                            if _PRINT_DEBUG:
                                print(
                                    f"    [SPOT] Separation '{seg_spot_name}' alias={spot_alias} tint={spot_tint_pct:.0f}% inyectado ok"
                                )
                        else:
                            if _PRINT_DEBUG:
                                print(
                                    f"    [SPOT] _inject_spot_operators no encontró operador k para '{seg_spot_name}'"
                                )
                        prev_xrefs = set(page.get_contents())
                    adv = float(font_obj.text_length(ch, fontsize=font_size)) + letter_spacing
                    cur_x += adv * dir_x
                    cur_y += adv * dir_y
            else:
                page.insert_text(
                    point,
                    seg_text,
                    fontname=fitz_fontname,
                    fontsize=font_size,
                    color=seg_color,
                    rotate=pdf_rotation,
                )
                char_count += len(seg_text)

                # Para SPOT: inyectar operadores Separation en el nuevo stream de contenido
                if seg_is_spot and spot_alias and prev_xrefs is not None:
                    spot_tint_pct = _spot_tints.get(seg.get("type", "number"), 100.0)
                    ok = _inject_spot_operators(
                        doc, page, spot_alias, prev_xrefs, spot_tint_pct
                    )
                    if ok:
                        if _PRINT_DEBUG:
                            print(
                                f"    [SPOT] Separation '{seg_spot_name}' alias={spot_alias} tint={spot_tint_pct:.0f}% inyectado ok"
                            )
                    else:
                        if _PRINT_DEBUG:
                            print(
                                f"    [SPOT] _inject_spot_operators no encontró operador k para '{seg_spot_name}'"
                            )

        except Exception as e:
            builtins.print(f"    ERROR renderizando segmento '{seg_text}': {e}")
            # Intentar re-registrar la fuente en esta página (por si falló previamente)
            try:
                cache_entry = FONT_CACHE.get(_font_cache_key(font_name, font_style))
                if cache_entry:
                    safe = cache_entry.get("fitz_name", "").replace(" ", "")
                    try:
                        if cache_entry.get("fontbuffer"):
                            page.insert_font(
                                fontname=safe or cache_entry.get("fitz_name"),
                                fontbuffer=cache_entry.get("fontbuffer"),
                            )
                            print(
                                f"    [PDF FONT] Re-registrado fontbuffer para {cache_entry.get('fitz_name')}"
                            )
                        elif cache_entry.get("fontfile"):
                            try:
                                page.insert_font(
                                    fontname=safe or cache_entry.get("fitz_name"),
                                    fontfile=cache_entry.get("fontfile"),
                                )
                                print(
                                    f"    [PDF FONT] Re-registrado fontfile para {cache_entry.get('fitz_name')}"
                                )
                            except Exception as ex_reg:
                                print(
                                    f"    [PDF FONT] Re-registrado fontfile falló: {ex_reg}. Intentando buffer..."
                                )
                                try:
                                    with open(cache_entry.get("fontfile"), "rb") as fh:
                                        fb = fh.read()
                                    page.insert_font(
                                        fontname=safe or cache_entry.get("fitz_name"),
                                        fontbuffer=fb,
                                    )
                                    cache_entry["fontbuffer"] = fb
                                    print(
                                        f"    [PDF FONT] Re-registrado via fontbuffer OK for {cache_entry.get('fitz_name')}"
                                    )
                                except Exception as ex_fb:
                                    print(
                                        f"    [PDF FONT] Re-registrado via fontbuffer falló: {ex_fb}"
                                    )
                    except Exception as ex_inner:
                        builtins.print(f"    [PDF FONT] Error durante re-registro: {ex_inner}")
            except Exception as ex2:
                builtins.print(f"    [PDF FONT] Re-registrado general falló: {ex2}")

            # Intento de rescate con Helvetica si falla el renderizado específico
            try:
                page.insert_text(
                    point,
                    seg_text,
                    fontname="helv",
                    fontsize=font_size,
                    color=seg_color,
                    rotate=pdf_rotation,
                )
                builtins.print(f"    -> Rescatado con Helvetica")
            except Exception as e2:
                builtins.print(f"    -> Rescate con Helvetica falló: {e2}")
                pass

        # Avanzar "lápiz" por el ancho del segmento + spacing entre segmentos.
        # No aplicar spacing tras el último segmento para evitar hueco de cola.
        spacing_after = seg["spacing"] if seg_idx < len(segments) - 1 else 0.0
        step = seg_width + spacing_after
        pen_x += step * dir_x
        pen_y += step * dir_y

    if _PRINT_DEBUG:
        print(f"  ✓ Renderizados {char_count} caracteres")
        print("=" * 80)
        print("RENDER COMPLETADO")
        print("=" * 80 + "\n")


_VT_LINE_SPACING_AUTO = 1.2  # interlineado por defecto = 1.2 × cuerpo (InDesign auto)


def _vt_line_spacing(pos_data):
    """Interlineado pt de pos_data para VT.

    Dato ausente (posiciones legacy) → AUTO 1.2×cuerpo: evita el apilado que
    producía line_spacing=0.0 en measure_vt_box. El 0 explícito del usuario
    se respeta (líneas montadas a propósito).
    """
    ls = pos_data.get("line_spacing")
    if ls is None:
        return _VT_LINE_SPACING_AUTO * float(pos_data.get("font_size", 12) or 12)
    return float(ls)


def render_variable_text_to_pdf(
    page: fitz.Page,
    text: str,
    x_mm: float,
    y_mm: float,
    bleed_mm: float,
    font_family: str,
    font_style: str,
    font_size: float,
    alignment: str,
    rotation: int,
    page_width_mm: float,
    page_height_mm: float,
    x_offset_mm: float = 0.0,
    resolved_font_path: str = None,
    resolved_font_index: int = None,
    letter_spacing: float = 0.0,
    prefix_suffix_spacing: float = 0.0,
    text_color: tuple = (0, 0, 0),
    text_color_cmyk: tuple = (0, 0, 0, 100),
    text_color_space: str = "RGB",
    text_color_name: str = "",
    text_color_tint: float = 100.0,
    prefix: str = "",
    suffix: str = "",
    prefix_suffix_color: tuple = (0, 0, 0),
    prefix_suffix_color_cmyk: tuple = (0, 0, 0, 100),
    prefix_suffix_color_space: str = "RGB",
    prefix_suffix_color_name: str = "",
    prefix_suffix_color_tint: float = 100.0,
    anchor: str = None,
    line_spacing: float = 0.0,
    text_alignment: str = "izquierda",
) -> None:
    """Renderiza un texto variable en el PDF (caja multilínea tight anclada a la guía)."""
    if _PRINT_DEBUG:
        print("\n" + "=" * 80)
        print("RENDER_VARIABLE_TEXT_TO_PDF (segmentos, sin morph)")
        print("=" * 80)
        print(f"text: '{text}'")
        print(f"x_mm: {x_mm}, y_mm: {y_mm}")
        print(f"bleed_mm: {bleed_mm}")
        print(f"font_family: {font_family}, font_style: {font_style}, font_size: {font_size}")
        print(f"prefix: '{prefix}', suffix: '{suffix}'")
        print(f"rotation: {rotation}, alignment: {alignment}")
        print(f"letter_spacing: {letter_spacing}pt, prefix_suffix_spacing: {prefix_suffix_spacing}pt")

    x_pt = mm_to_pt(x_mm + bleed_mm)
    y_pt = mm_to_pt(y_mm + bleed_mm)

    if x_offset_mm:
        x_pt += mm_to_pt(x_offset_mm)

    full_text = f"{prefix}{text}{suffix}"
    if not full_text.strip():
        if _PRINT_DEBUG:
            print("  [WARN] texto vacío, se omite")
        return

    # Si no hay resolved_font_path válido, resolverlo como el diálogo VT para
    # incrustar la fuente real (TrueType) en vez de caer a Base-14 "helv" sin incrustar.
    if not resolved_font_path or not os.path.exists(resolved_font_path):
        try:
            from utils import font_index_wrapper as font_index

            resolved_font_path, _ = font_index.find_font_file_for(
                font_family, font_style
            )
        except Exception:
            resolved_font_path = None

    # Si la ruta es TTC/OTC y no tenemos índice, calcularlo (como _resolve_profiles):
    # sin él, _ensure_font_cached lee el TTC completo → subfont 0 = Regular.
    if resolved_font_path and resolved_font_path.lower().endswith((".ttc", ".otc")):
        if resolved_font_index is None:
            try:
                resolved_font_index = _get_ttc_font_index(
                    resolved_font_path, font_style
                )
            except Exception:
                resolved_font_index = None

    try:
        fitz_fontname, font_obj = _ensure_font_cached(
            font_family, font_style, page,
            font_path=resolved_font_path, font_index=resolved_font_index,
        )
    except Exception as e:
        log_error(f"render_variable_text_to_pdf font cache fallback: {e}", exc_info=True)
        fitz_fontname = "helv"
        font_obj = fitz.Font("helv")

    def _normalize_color(c):
        if isinstance(c, (list, tuple)) and len(c) == 4:
            return tuple(float(v) for v in c)
        if isinstance(c, str) and c.startswith("#"):
            h = c.lstrip("#")
            if len(h) == 6:
                r, g, b = int(h[0:2], 16) / 255.0, int(h[2:4], 16) / 255.0, int(h[4:6], 16) / 255.0
                return (r, g, b)
        if isinstance(c, (list, tuple)) and len(c) == 3:
            vals = [float(v) for v in c]
            if max(vals) > 1.0:
                return (vals[0] / 255.0, vals[1] / 255.0, vals[2] / 255.0)
            return tuple(vals)
        return (0.0, 0.0, 0.0)

    text_color_norm = _normalize_color(text_color)
    ps_color_norm = _normalize_color(prefix_suffix_color)

    doc = page.parent

    _seg_spaces = {"text": text_color_space, "prefix_suffix": prefix_suffix_color_space}
    _spot_names = {"text": text_color_name or "", "prefix_suffix": prefix_suffix_color_name or ""}
    _spot_tints = {"text": float(text_color_tint), "prefix_suffix": float(prefix_suffix_color_tint)}

    def _to_cmyk_01(cmyk):
        vals = tuple(float(v) for v in cmyk)
        return tuple(v / 100.0 for v in vals) if any(v > 1.0 for v in vals) else vals

    text_cmyk_01 = _to_cmyk_01(text_color_cmyk)
    ps_cmyk_01 = _to_cmyk_01(prefix_suffix_color_cmyk)

    _spot_aliases = {}
    for seg_key in ("text", "prefix_suffix"):
        if _seg_spaces[seg_key] != "SPOT":
            continue
        spot_name = _spot_names[seg_key]
        if not spot_name:
            continue
        if spot_name not in _spot_aliases:
            cmyk_spot = text_cmyk_01 if seg_key == "text" else ps_cmyk_01
            alias = _define_spot_colorspace(doc, page, spot_name, cmyk_spot)
            _spot_aliases[spot_name] = alias

    # ── Caja multilínea tight (pt) + ancla + rotación alrededor de la guía ──
    from utils.variable_text_measure import (
        measure_vt_box,
        anchor_uv,
        vertical_anchor_offset,
    )

    # Migración legacy alignment (3) → anchor (9): fila central.
    if not anchor:
        anchor = {
            "izquierda": "centro_izquierda",
            "centro": "centro_centro",
            "derecha": "centro_derecha",
        }.get(alignment, "centro_izquierda")

    lines = full_text.split("\n")
    box = measure_vt_box(
        lines,
        resolved_font_path or "",
        float(font_size),
        line_spacing=float(line_spacing),
        letter_spacing=float(letter_spacing),
    )
    # La caja se ancla con las DOS componentes de la POSICIÓN (anchor 9):
    # text_alignment solo alinea líneas DENTRO de la caja (_align_off abajo).
    fx, fy = anchor_uv(anchor)

    # Origen de la caja (sin rotar): el punto (fx, vertical_anchor_offset) de la
    # caja coincide con la guía. El ancla vertical descansa sobre las letras
    # normales (baseline / tope de diseño), no sobre caracteres que cuelgan.
    box_left = x_pt - fx * box["box_w"]
    box_top = y_pt - vertical_anchor_offset(
        fy, box, resolved_font_path or "", float(font_size)
    )

    # Insertar cada línea: (box_left + left_bearing_i, box_top + baselines[i]).
    for line_idx, seg_text in enumerate(lines):
        if not seg_text:
            continue
        line_metrics = box["lines"][line_idx]
        baseline_y = box_top + box["baselines"][line_idx]

        # Punto de inserción: la tinta de la línea empieza en su left_bearing,
        # desplazada por la alineación (izq/centro/der) dentro de la caja.
        # spaced_width = tinta + n-1 huecos de interletraje (igual que box_w).
        _line_w = line_metrics.get("spaced_width", line_metrics["width"])
        if text_alignment == "derecha":
            _align_off = box["box_w"] - _line_w
        elif text_alignment == "centro":
            _align_off = (box["box_w"] - _line_w) / 2
        else:
            _align_off = 0.0
        pen_x = box_left - line_metrics["left_bearing"] + _align_off
        pen_y = baseline_y

        # Rotación de la caja alrededor de la guía (x_pt, y_pt).
        if rotation:
            rad = math.radians(rotation)
            dx = pen_x - x_pt
            dy = pen_y - y_pt
            pen_x = x_pt + dx * math.cos(rad) - dy * math.sin(rad)
            pen_y = y_pt + dx * math.sin(rad) + dy * math.cos(rad)

        draw_color = (
            text_cmyk_01 if text_color_space in ("SPOT", "CMYK") else text_color_norm
        )
        point = fitz.Point(pen_x, pen_y)

        spot_alias = None
        prev_xrefs = None
        if text_color_space == "SPOT" and text_color_name:
            spot_alias = _spot_aliases.get(text_color_name)
            if spot_alias:
                prev_xrefs = set(page.get_contents())

        try:
            if letter_spacing != 0:
                # Interletraje: render per-char (misma regla que numeradoras:
                # avance text_length(ch)+spacing a lo largo de la dirección de
                # rotación; el kerning nativo se pierde SOLO aquí).
                rad = math.radians(rotation)
                dir_x, dir_y = math.cos(rad), math.sin(rad)
                cur_x, cur_y = pen_x, pen_y
                for ch in seg_text:
                    page.insert_text(
                        fitz.Point(cur_x, cur_y), ch,
                        fontname=fitz_fontname, fontsize=font_size,
                        color=draw_color, rotate=-rotation,
                    )
                    if spot_alias and prev_xrefs is not None:
                        _inject_spot_operators(
                            doc, page, spot_alias, prev_xrefs, text_color_tint
                        )
                        prev_xrefs = set(page.get_contents())
                    adv = float(font_obj.text_length(ch, fontsize=font_size)) + letter_spacing
                    cur_x += adv * dir_x
                    cur_y += adv * dir_y
            else:
                page.insert_text(
                    point, seg_text,
                    fontname=fitz_fontname, fontsize=font_size,
                    color=draw_color, rotate=-rotation,
                )
                if spot_alias and prev_xrefs is not None:
                    _inject_spot_operators(doc, page, spot_alias, prev_xrefs, text_color_tint)
        except Exception as e:
            log_error(f"render_variable_text_to_pdf line '{seg_text}': {e}", exc_info=True)
            try:
                page.insert_text(
                    point, seg_text,
                    fontname="helv", fontsize=font_size,
                    color=draw_color, rotate=-rotation,
                )
            except Exception as e2:
                log_error(f"render_variable_text_to_pdf fallback '{seg_text}': {e2}", exc_info=True)


def _precompute_hri_geometry(hri_lines, font_path, ds_pt, line_spacing, gap_mm, position, code_w_mm):
    """Geometría del bloque HRI (código + texto) en mm — espejo de barcode_module.

    Compartido por DataMatrix, QR y PDF417. Devuelve dict con: total_text_mm,
    fb_off_mm (offset del primer baseline), line_h_mm (interlineado), canvas_w_mm
    (ancho total del bloque), box_w_mm (caja de texto), box_origin_mm y code_off_mm
    (ancla del código dentro del canvas).
    """
    from utils.barcode_module import get_font_text_metrics, get_hri_line_height
    _asc, _desc, _total = get_font_text_metrics(font_path)
    ds_mm = ds_pt * FONT_PT_TO_MM
    text_n = len(hri_lines)
    total_text_mm = text_n * _total * ds_mm * line_spacing  # fallback
    fb_off_mm = _asc * ds_mm  # fallback first baseline offset
    line_h_mm = _total * ds_mm * line_spacing  # fallback line height
    max_text_w_mm = 0.0
    canvas_w_mm = code_w_mm
    if hri_lines and ds_pt > 0:
        from PIL import ImageFont
        pm = 300.0 / 25.4
        pil_font = ImageFont.truetype(font_path, int(round(ds_pt * pm / 2.835)))
        pil_ascent, _pil_descent = pil_font.getmetrics()
        pil_lh = get_hri_line_height(font_path, pil_font.size)
        ft = pil_font.getbbox(hri_lines[0])[1]
        fb = pil_font.getbbox(hri_lines[-1])[3]
        total_text_mm = ((text_n - 1) * pil_lh * line_spacing + fb - ft) / pm
        fb_off_mm = (pil_ascent - ft) / pm
        line_h_mm = pil_lh / pm * line_spacing
        meas = fitz.Font(fontfile=font_path)
        max_text_w_mm = max(meas.text_length(line, fontsize=ds_pt) * 25.4 / 72.0 for line in hri_lines)
    if position in ("left", "right") and max_text_w_mm > 0:
        canvas_w_mm = max_text_w_mm + gap_mm + code_w_mm
        box_w_mm = max_text_w_mm
        if position == "left":
            code_off_mm = max_text_w_mm + gap_mm
            box_origin_mm = 0.0
        else:
            code_off_mm = 0.0
            box_origin_mm = code_w_mm + gap_mm
    else:
        canvas_w_mm = max(code_w_mm, max_text_w_mm)
        code_off_mm = (canvas_w_mm - code_w_mm) / 2.0
        box_w_mm = canvas_w_mm
        box_origin_mm = 0.0
    return {
        "total_text_mm": total_text_mm,
        "fb_off_mm": fb_off_mm,
        "line_h_mm": line_h_mm,
        "canvas_w_mm": canvas_w_mm,
        "box_w_mm": box_w_mm,
        "box_origin_mm": box_origin_mm,
        "code_off_mm": code_off_mm,
    }


def _draw_hri_text_to_page(page, lines, font_path, ds_pt, position, gap_mm, align, geo,
                           x_start, x_mm, y_mm, content_height, bar_height,
                           rotation, cos_a, sin_a, bleed_mm, text_fill_color):
    """Dibuja el texto HRI sobre el page — replica el bloque de DataMatrix."""
    if not lines or ds_pt <= 0:
        return
    fontname = f"HRI_{Path(font_path).stem}"
    if Path(font_path).exists():
        try:
            page.insert_font(fontname=fontname, fontfile=font_path)
        except Exception:
            fontname = None
    else:
        fontname = None

    meas = fitz.Font(fontfile=font_path)

    # Alineación 9 valores → vy (top/middle/bottom) + hx (left/center/right)
    vy, hx = ("bottom", "center")
    if align.startswith("top_"):
        vy = "top"
    elif align.startswith("middle_"):
        vy = "middle"
    if align.endswith("_left"):
        hx = "left"
    elif align.endswith("_right"):
        hx = "right"

    total_text_mm = geo["total_text_mm"]
    fb_off_mm = geo["fb_off_mm"]
    line_h_mm = geo["line_h_mm"]
    box_origin_mm = geo["box_origin_mm"]
    box_w_mm = geo["box_w_mm"]

    # Replica de _build_hri_canvas (barcode_module): con below/above, si el texto
    # es más ancho que el código (code_off > 0) y no va centrado, su caja se
    # restringe al ancho del CÓDIGO (no al canvas) para que left/right anclen al código.
    if position in ("below", "above") and hx != "center":
        _c_off = geo["code_off_mm"]
        if _c_off > 0:
            _c_w = geo["canvas_w_mm"] - 2 * _c_off
            if _c_w > 0:
                box_origin_mm = _c_off
                box_w_mm = _c_w

    for i, line in enumerate(lines):
        hri_w_pt = meas.text_length(line, fontsize=ds_pt)
        hri_w_mm = hri_w_pt * 25.4 / 72.0

        if position in ("left", "right"):
            # banda vertical del texto = bloque completo (content_height).
            # El canvas cuelga del ancla con gy = (canvas_h + code_h) / 2 (el código
            # está centrado verticalmente): la referencia no es y_mm sino el borde
            # del canvas = y_mm - (content_height + bar_height) / 2.
            if vy == "top":
                txt_top_mm = y_mm - (content_height + bar_height) / 2.0
            elif vy == "bottom":
                txt_top_mm = y_mm + (content_height - bar_height) / 2.0 - total_text_mm
            else:  # middle
                txt_top_mm = y_mm - bar_height / 2.0 - total_text_mm / 2.0
            digit_y = txt_top_mm + fb_off_mm + i * line_h_mm
        elif position == "above":
            digit_y = y_mm - total_text_mm - gap_mm - bar_height + fb_off_mm + i * line_h_mm
        else:
            digit_y = y_mm + gap_mm + fb_off_mm + i * line_h_mm

        # x dentro de la caja de texto invisible según alineación
        if hx == "right":
            hri_left_mm = x_start + box_origin_mm + box_w_mm - hri_w_mm
        elif hx == "left":
            hri_left_mm = x_start + box_origin_mm
        else:  # center
            hri_left_mm = x_start + box_origin_mm + (box_w_mm - hri_w_mm) / 2.0

        if rotation != 0:
            rel_x = hri_left_mm - x_mm
            rel_y = digit_y - y_mm
            rot_x = rel_x * cos_a - rel_y * sin_a
            rot_y = rel_x * sin_a + rel_y * cos_a
            fx = x_mm + rot_x
            fy = y_mm + rot_y
        else:
            fx = hri_left_mm
            fy = digit_y

        kwargs = dict(
            point=fitz.Point(
                (bleed_mm + fx) * 72.0 / 25.4,
                (bleed_mm + fy) * 72.0 / 25.4,
            ),
            text=line,
            fontsize=ds_pt,
            color=text_fill_color,
            rotate=-rotation,
        )
        if fontname:
            kwargs["fontname"] = fontname
        try:
            page.insert_text(**kwargs)
        except Exception:
            pass


def render_barcode_to_pdf(
    page: fitz.Page,
    pos_data: dict,
    bleed_mm: float,
    page_width_mm: float,
    page_height_mm: float,
    doc: fitz.Document = None,
) -> None:
    """
    Renderiza un codigo de barras en una pagina PDF, soportando
    RGB, CMYK y SPOT (tinta plana).

    Args:
        page: Pagina PDF donde renderizar
        pos_data: Datos de la posicion del barcode (x, y, barcode_value, bar_width, bar_height, color, ...)
        bleed_mm: Sangre en mm
        page_width_mm: Ancho de pagina sin sangre
        page_height_mm: Alto de pagina sin sangre
        doc: Documento PDF padre (necesario para SPOT)
    """
    x_mm = pos_data.get("x", 0)
    y_mm = pos_data.get("y", 0)
    _debug_y(
        f"[render_barcode_to_pdf] y_mm={y_mm} bleed={bleed_mm} page_h={page_height_mm} bar_h={pos_data.get('bar_height', 30.0)}"
    )
    value = pos_data.get("barcode_value", "") or pos_data.get("value", "")
    total_bar_width = float(pos_data.get("bar_width", 80.0))
    bar_height = pos_data.get("bar_height", 30.0)
    rotation = pos_data.get("rotation", 0)
    if isinstance(rotation, str):
        rotation = int(rotation.replace("\u00b0", "").strip())

    color_hex = pos_data.get("color", "#000000")
    raw_cmyk = pos_data.get("color_cmyk", None)
    color_space = pos_data.get("color_space", "RGB")
    color_name = pos_data.get("color_name", "")
    color_tint = float(pos_data.get("color_tint", 100.0))
    text_color_hex = pos_data.get("text_color", "#000000")
    text_raw_cmyk = pos_data.get("text_color_cmyk", None)
    text_color_space = pos_data.get("text_color_space", "RGB")
    text_color_name = pos_data.get("text_color_name", "")
    text_color_tint = float(pos_data.get("text_color_tint", 100.0))
    symbology = pos_data.get("symbology", "code128")
    is_qr = symbology == "qr"
    is_ean13 = symbology == "ean13"
    is_ean8 = symbology == "ean8"
    is_ean5 = symbology == "ean5"
    is_isbn13 = symbology == "isbn13"
    is_upca = symbology == "upca"
    is_upce = symbology == "upce"
    is_itf14 = symbology == "itf14"
    is_pdf417 = symbology == "pdf417"
    is_code39 = symbology == "code39"
    is_code128 = symbology == "code128"
    is_datamatrix = symbology in ("datamatrix", "datamatrix_gs1", "datamatrix_dl")

    if not value:
        return

    ean13_pattern = None
    ean13_fullcode = None
    ean8_pattern = None
    ean8_fullcode = None
    ean5_pattern = None
    ean5_fullcode = None
    ean5_digit_top_mm = 0.0
    isbn13_pattern = None
    isbn13_fullcode = None
    upca_pattern = None
    upca_fullcode = None
    upce_pattern = None
    upce_fullcode = None
    itf14_pattern = None
    itf14_fullcode = None
    code39_pattern = None
    code39_fullcode = None
    code128_fullcode = None
    try:
        from utils.barcode_module import (
            get_digit_advance_em,
            ean_hri_layout,
            get_ean13_font_ascender_ratio,
        )
        if is_qr:
            _qr_del_close = pos_data.get("qr_del_close", "|")
            _qr_encode_value = (
                value.replace(_qr_del_close, "\n")
                if pos_data.get("qr_del_close_newline", False)
                and _qr_del_close
                and value
                else value
            )
            n_modules = get_qr_module_count(_qr_encode_value)
            module_size = total_bar_width / n_modules
            rects = get_qr_rects(_qr_encode_value, module_size=module_size)
            total_content_size = get_qr_total_size(_qr_encode_value, module_size)
            # HRI (texto libre) — mismo patrón que DataMatrix
            from utils.barcode_module import resolve_font_path
            ds_pt = float(pos_data.get("barcode_font_size", 9.0))
            _qr_font_path = resolve_font_path(pos_data.get("barcode_font_family", "OCR-B"))
            qr_hri_gap_mm = float(pos_data.get("qr_hri_gap_mm", 2.0))
            qr_hri_position = pos_data.get("qr_hri_position", "below")
            _qr_hri_align = pos_data.get("qr_hri_align", "bottom_center") or "bottom_center"
            _qr_line_spacing = float(pos_data.get("qr_hri_line_spacing", 1.0) or 1.0)
            if _qr_line_spacing <= 0:
                _qr_line_spacing = 1.0
            _qr_del_open = pos_data.get("qr_del_open", "")
            _qr_hri_lines = _format_hri_lines(value, pos_data.get("barcode_font_family", "OCR-B"), ds_pt, total_content_size, open_del=_qr_del_open, close_del=_qr_del_close, symbology="qr") if value else []
            _qr_geo = _precompute_hri_geometry(_qr_hri_lines, _qr_font_path, ds_pt, _qr_line_spacing, qr_hri_gap_mm, qr_hri_position, total_content_size)
            _qr_total_text_mm = _qr_geo["total_text_mm"]
            _qr_canvas_w_mm = _qr_geo["canvas_w_mm"]
            _qr_box_w_mm = _qr_geo["box_w_mm"]
            _qr_box_origin_mm = _qr_geo["box_origin_mm"]
            _qr_code_off_mm = _qr_geo["code_off_mm"]
        elif is_ean13:
            ean13_pattern, ean13_fullcode = encode_ean13(value)
            module_width = total_bar_width / get_ean13_module_count()
            ds_pt = float(pos_data.get("barcode_font_size", 13.0))
            ds_mm = ds_pt * FONT_PT_TO_MM
            digit_pad = 0.3
            _ean13_el, _ean13_c_eff, bar_offset_mm, cw, _ean13_ds_eff = ean_hri_layout(
                "ean13",
                ean13_fullcode,
                module_width,
                ds_mm,
                pos_data.get("barcode_font_family", "OCR-B"),
            )
            guard_ext_mm = max(1.5, _ean13_ds_eff * (0.25 + get_ean13_font_ascender_ratio(pos_data.get("barcode_font_family", "OCR-B"))))
            total_content_size = cw
            rects = []
            x = 0.0
            i = 0
            while i < len(ean13_pattern):
                if ean13_pattern[i] == "0":
                    x += module_width
                    i += 1
                    continue
                w = module_width
                j = i + 1
                while j < len(ean13_pattern) and ean13_pattern[j] == "1":
                    w += module_width
                    j += 1
                is_guard = any(m in EAN13_GUARD_MODULES for m in range(i, j))
                rh = bar_height + (guard_ext_mm if is_guard else 0)
                rects.append((bar_offset_mm + x, -guard_ext_mm, w, rh))
                x += w
                i = j
        elif is_ean8:
            ean8_pattern, ean8_fullcode = encode_ean8(value)
            module_width = total_bar_width / get_ean8_module_count()
            ds_pt = float(pos_data.get("barcode_font_size", 13.0))
            ds_mm = ds_pt * FONT_PT_TO_MM
            _ean8_el, _ean8_c_eff, _ean8_boff, cw, _ean8_ds_eff = ean_hri_layout(
                "ean8",
                ean8_fullcode,
                module_width,
                ds_mm,
                pos_data.get("barcode_font_family", "OCR-B"),
            )
            guard_ext_mm = max(1.5, _ean8_ds_eff * (0.25 + get_ean13_font_ascender_ratio(pos_data.get("barcode_font_family", "OCR-B"))))
            total_content_size = cw
            rects = []
            x = 0.0
            i = 0
            while i < len(ean8_pattern):
                if ean8_pattern[i] == "0":
                    x += module_width
                    i += 1
                    continue
                w = module_width
                j = i + 1
                while j < len(ean8_pattern) and ean8_pattern[j] == "1":
                    w += module_width
                    j += 1
                is_guard = any(m in EAN8_GUARD_MODULES for m in range(i, j))
                rh = bar_height + (guard_ext_mm if is_guard else 0)
                rects.append((x, -guard_ext_mm, w, rh))
                x += w
                i = j
        elif is_ean5:
            ean5_pattern, ean5_fullcode = encode_ean5(value)
            module_width = total_bar_width / get_ean5_module_count()
            ds_pt = float(pos_data.get("barcode_font_size", 13.0))
            ds_mm = ds_pt * FONT_PT_TO_MM
            ean5_hri_gap_mm = float(pos_data.get("ean5_hri_gap_mm", 2.0))
            from utils.barcode_module import resolve_font_path, get_digit_advance_em, get_font_text_metrics
            _ean5_font_path = resolve_font_path(pos_data.get("barcode_font_family", "OCR-B"))
            _ean5_asc, _ean5_desc_neg, _ean5_total = get_font_text_metrics(_ean5_font_path)
            ean5_digit_top_mm = _ean5_asc * ds_mm + ean5_hri_gap_mm
            char_w_mm = ds_mm * get_digit_advance_em(pos_data.get("barcode_font_family", "OCR-B"))
            cw = 47 * module_width
            total_content_size = cw
            rects = []
            x = 0.0
            i = 0
            while i < len(ean5_pattern):
                if ean5_pattern[i] == "0":
                    x += module_width
                    i += 1
                    continue
                w = module_width
                j = i + 1
                while j < len(ean5_pattern) and ean5_pattern[j] == "1":
                    w += module_width
                    j += 1
                rects.append((x, ean5_digit_top_mm, w, bar_height))
                x += w
                i = j
        elif is_isbn13:
            isbn13_pattern, isbn13_fullcode = encode_ean13(value)
            module_width = total_bar_width / get_ean13_module_count()
            ds_pt = float(pos_data.get("barcode_font_size", 13.0))
            ds_mm = ds_pt * FONT_PT_TO_MM
            _isbn_el, _isbn_c_eff, bar_offset_mm, cw, _isbn_ds_eff = ean_hri_layout(
                "isbn13",
                isbn13_fullcode,
                module_width,
                ds_mm,
                pos_data.get("barcode_font_family", "OCR-B"),
            )
            guard_ext_mm = max(1.5, _isbn_ds_eff * (0.25 + get_ean13_font_ascender_ratio(pos_data.get("barcode_font_family", "OCR-B"))))
            total_content_size = cw
            rects = []
            x = 0.0
            i = 0
            while i < len(isbn13_pattern):
                if isbn13_pattern[i] == "0":
                    x += module_width
                    i += 1
                    continue
                w = module_width
                j = i + 1
                while j < len(isbn13_pattern) and isbn13_pattern[j] == "1":
                    w += module_width
                    j += 1
                is_guard = any(m in EAN13_GUARD_MODULES for m in range(i, j))
                rh = bar_height + (guard_ext_mm if is_guard else 0)
                rects.append((bar_offset_mm + x, -guard_ext_mm, w, rh))
                x += w
                i = j
        elif is_upca:
            upca_pattern, upca_fullcode = encode_upca(value)
            module_width = total_bar_width / get_ean13_module_count()
            ds_pt = float(pos_data.get("barcode_font_size", 13.0))
            ds_mm = ds_pt * FONT_PT_TO_MM
            _upca_el, _upca_c_eff, bar_offset_mm, cw, _upca_ds_eff = ean_hri_layout(
                "upca",
                upca_fullcode,
                module_width,
                ds_mm,
                pos_data.get("barcode_font_family", "OCR-B"),
            )
            guard_ext_mm = max(1.5, _upca_ds_eff * (0.25 + get_ean13_font_ascender_ratio(pos_data.get("barcode_font_family", "OCR-B"))))
            total_content_size = cw
            rects = []
            x = 0.0
            i = 0
            while i < len(upca_pattern):
                if upca_pattern[i] == "0":
                    x += module_width
                    i += 1
                    continue
                w = module_width
                j = i + 1
                while j < len(upca_pattern) and upca_pattern[j] == "1":
                    w += module_width
                    j += 1
                is_guard = any(m in EAN13_GUARD_MODULES for m in range(i, j))
                rh = bar_height + (guard_ext_mm if is_guard else 0)
                rects.append((bar_offset_mm + x, -guard_ext_mm, w, rh))
                x += w
                i = j
        elif is_upce:
            upce_pattern, upce_fullcode = encode_upce(value)
            module_width = total_bar_width / get_upce_module_count()
            ds_pt = float(pos_data.get("barcode_font_size", 13.0))
            ds_mm = ds_pt * FONT_PT_TO_MM
            _upce_el, _upce_c_eff, bar_offset_mm, cw, _upce_ds_eff = ean_hri_layout(
                "upce",
                upce_fullcode,
                module_width,
                ds_mm,
                pos_data.get("barcode_font_family", "OCR-B"),
            )
            guard_ext_mm = max(1.5, _upce_ds_eff * (0.25 + get_ean13_font_ascender_ratio(pos_data.get("barcode_font_family", "OCR-B"))))
            total_content_size = cw
            rects = []
            x = 0.0
            i = 0
            while i < len(upce_pattern):
                if upce_pattern[i] == "0":
                    x += module_width
                    i += 1
                    continue
                w = module_width
                j = i + 1
                while j < len(upce_pattern) and upce_pattern[j] == "1":
                    w += module_width
                    j += 1
                is_guard = any(m in UPCE_GUARD_MODULES for m in range(i, j))
                rh = bar_height + (guard_ext_mm if is_guard else 0)
                rects.append((x, -guard_ext_mm, w, rh))
                x += w
                i = j
        elif is_itf14:
            itf14_raw = value
            gtin_type = pos_data.get("itf14_gtin_type", "gtin14")
            if gtin_type == "gtin13":
                g13_valid, g13_msg = validate_gtin13(itf14_raw)
                if not g13_valid:
                    raise ValueError(g13_msg)
                itf14_raw = gtin13_to_gtin14(itf14_raw)
            else:
                g14_valid, g14_msg = validate_itf14(itf14_raw)
                if not g14_valid:
                    raise ValueError(g14_msg)
            printer_type = pos_data.get("itf14_printer_type", "flexografia")
            dims = calc_itf14_dimensions(total_bar_width, printer_type, float(pos_data.get("bar_height", 0)))
            itf14_quiet_zone_mm = dims["quiet_zone_mm"]
            itf14_bearer_w_mm = dims["bearer_thickness_mm"]
            itf14_bearer_sides = dims["bearer_sides"]
            bar_height = dims["bar_height"]
            itf14_bearer_off_mm = itf14_bearer_w_mm / 2
            itf14_hri_gap_mm = float(pos_data.get("itf14_hri_gap_mm", 0.0))
            itf14_pattern, itf14_fullcode = encode_itf14(itf14_raw)
            from utils.barcode_module import resolve_font_path, get_digit_advance_em, get_font_cap_height_ratio
            _itf14_font_path = resolve_font_path(pos_data.get("barcode_font_family", "OCR-B"))
            _itf14_cap = get_font_cap_height_ratio(_itf14_font_path)
            cw = dims["bar_content_width"]  # bar content width (total minus quiet zones and bearer)
            module_width = cw / get_itf14_module_count()
            ds_pt = float(pos_data.get("barcode_font_size", 13.0))
            ds_mm = ds_pt * FONT_PT_TO_MM
            char_w_mm = ds_mm * get_digit_advance_em(pos_data.get("barcode_font_family", "OCR-B"))
            cw = ITF14_TOTAL_MODULES * module_width  # bar content width
            off = itf14_bearer_off_mm
            total_content_size = cw + 2 * itf14_quiet_zone_mm + itf14_bearer_w_mm
            bars_start_x = itf14_bearer_off_mm + itf14_quiet_zone_mm
            rects = []
            x_bar = bars_start_x  # bars start inside bearer + quiet zone
            i = 0
            while i < len(itf14_pattern):
                if itf14_pattern[i] == "0":
                    x_bar += module_width
                    i += 1
                    continue
                w = module_width
                j = i + 1
                while j < len(itf14_pattern) and itf14_pattern[j] == "1":
                    w += module_width
                    j += 1
                rects.append((x_bar, off, w, bar_height - itf14_bearer_w_mm))
                x_bar += w
                i = j
        elif is_pdf417:
            pdf417_height_target = pos_data.get("pdf417_height") or bar_height

            _pdf417_del_close = pos_data.get("pdf417_del_close", "|")
            _pdf417_encode_value = (
                value.replace(_pdf417_del_close, "\n")
                if pos_data.get("pdf417_del_close_newline", False)
                and _pdf417_del_close
                and value
                else value
            )
            codes, actual_cols = _pdf417_encode_safe(_pdf417_encode_value, columns=6)
            n_rows = len(codes) if actual_cols > 0 else 0
            barcode_w_mod = _pdf417_barcode_size(codes)[0]
            module_width = total_bar_width / barcode_w_mod if barcode_w_mod > 0 else 0.3

            if pdf417_height_target and n_rows > 0:
                ratio = max(pdf417_height_target / (n_rows * module_width), PDF417_DEFAULT_RATIO)
            else:
                ratio = PDF417_DEFAULT_RATIO

            pdf417_h_mm = n_rows * module_width * ratio

            pdf417_w_mm = total_bar_width
            total_content_size = pdf417_w_mm
            rects = get_pdf417_rects(_pdf417_encode_value, module_width=module_width, ratio=ratio)
            # HRI (texto libre) — mismo patrón que DataMatrix
            from utils.barcode_module import resolve_font_path
            ds_pt = float(pos_data.get("barcode_font_size", 9.0))
            _pdf417_font_path = resolve_font_path(pos_data.get("barcode_font_family", "OCR-B"))
            pdf417_hri_gap_mm = float(pos_data.get("pdf417_hri_gap_mm", 2.0))
            pdf417_hri_position = pos_data.get("pdf417_hri_position", "below")
            _pdf417_hri_align = pos_data.get("pdf417_hri_align", "bottom_center") or "bottom_center"
            _pdf417_line_spacing = float(pos_data.get("pdf417_hri_line_spacing", 1.0) or 1.0)
            if _pdf417_line_spacing <= 0:
                _pdf417_line_spacing = 1.0
            _pdf417_del_open = pos_data.get("pdf417_del_open", "")
            _pdf417_hri_lines = _format_hri_lines(value, pos_data.get("barcode_font_family", "OCR-B"), ds_pt, pdf417_w_mm, open_del=_pdf417_del_open, close_del=_pdf417_del_close, symbology="pdf417") if value else []
            _pdf417_geo = _precompute_hri_geometry(_pdf417_hri_lines, _pdf417_font_path, ds_pt, _pdf417_line_spacing, pdf417_hri_gap_mm, pdf417_hri_position, pdf417_w_mm)
            _pdf417_total_text_mm = _pdf417_geo["total_text_mm"]
            _pdf417_canvas_w_mm = _pdf417_geo["canvas_w_mm"]
            _pdf417_box_w_mm = _pdf417_geo["box_w_mm"]
            _pdf417_box_origin_mm = _pdf417_geo["box_origin_mm"]
            _pdf417_code_off_mm = _pdf417_geo["code_off_mm"]
        elif is_datamatrix:
            dm_w_mm = float(pos_data.get("datamatrix_width", 20.0))
            dm_h_mm = float(pos_data.get("datamatrix_height", 20.0))
            _dm_del_close = pos_data.get("datamatrix_del_close", "|")
            _dm_encode_value = (
                value.replace(_dm_del_close, "\n")
                if pos_data.get("datamatrix_del_close_newline", False)
                and _dm_del_close
                and value
                else value
            )
            raw = preparar_cadena_gs1_datamatrix(_dm_encode_value)
            try:
                from pylibdmtx.pylibdmtx import encode as _dm_enc
                from PIL import Image as _PILImg
                formato = pos_data.get("datamatrix_format", "")
                if formato and formato != 'square':
                    encoded = _dm_enc(raw.encode('utf-8'), size=formato)
                else:
                    encoded = _dm_enc(raw.encode('utf-8'))
                # Get content pixel dimensions (remove quiet zone for accurate module width)
                _dm_tmp = _PILImg.frombytes('RGB', (encoded.width, encoded.height), encoded.pixels).convert('L')
                _dm_msk = _dm_tmp.point(lambda p: 255 if p < 128 else 0)
                _dm_cb = _dm_msk.getbbox()
                _dm_cw = (_dm_cb[2] - _dm_cb[0]) if _dm_cb else encoded.width
                dm_module_width = dm_w_mm / _dm_cw if _dm_cw > 0 else 0.255
            except Exception:
                dm_module_width = 0.255
            rects = get_datamatrix_rects(_dm_encode_value, module_width=dm_module_width, formato=pos_data.get("datamatrix_format", ""))
            # Pre-compute HRI for external box width (canvas = max(code, widest text line))
            from utils.barcode_module import resolve_font_path
            _dm_font_path = resolve_font_path(pos_data.get("barcode_font_family", "OCR-B"))
            ds_pt = float(pos_data.get("barcode_font_size", 9.0))
            dm_hri_gap_mm = float(pos_data.get("datamatrix_hri_gap_mm", 2.0))
            dm_hri_position = pos_data.get("datamatrix_hri_position", "below")
            _dm_hri_align = pos_data.get("datamatrix_hri_align", "bottom_center") or "bottom_center"
            _dm_line_spacing = float(pos_data.get("datamatrix_hri_line_spacing", 1.0) or 1.0)
            if _dm_line_spacing <= 0:
                _dm_line_spacing = 1.0
            _dm_del_open = pos_data.get("datamatrix_del_open", "")
            _dm_hri_lines = _format_hri_lines(value, pos_data.get("barcode_font_family", "OCR-B"), ds_pt, dm_w_mm, open_del=_dm_del_open, close_del=_dm_del_close, symbology=symbology) if value else []
            _dm_geo = _precompute_hri_geometry(_dm_hri_lines, _dm_font_path, ds_pt, _dm_line_spacing, dm_hri_gap_mm, dm_hri_position, dm_w_mm)
            _dm_total_text_mm = _dm_geo["total_text_mm"]
            _dm_canvas_w_mm = _dm_geo["canvas_w_mm"]
            _dm_code_off_mm = _dm_geo["code_off_mm"]
            total_content_size = _dm_canvas_w_mm
            bar_height = dm_h_mm
        elif is_code39:
            code39_pattern, code39_fullcode = encode_code39(value)
            code39_module_count = get_code39_module_count(value)
            module_width = total_bar_width / code39_module_count
            rects = []
            x_bar = 0.0
            i = 0
            while i < len(code39_pattern):
                if code39_pattern[i] == "0":
                    x_bar += module_width
                    i += 1
                    continue
                w = module_width
                j = i + 1
                while j < len(code39_pattern) and code39_pattern[j] == "1":
                    w += module_width
                    j += 1
                rects.append((x_bar, 0.0, w, bar_height))
                x_bar += w
                i = j
            total_content_size = total_bar_width
        else:
            total_modules = get_module_count(value)
            module_width = total_bar_width / total_modules
            rects = get_barcode_rects(
                value, module_width=module_width, bar_height=bar_height
            )
            total_content_size = total_bar_width
            code128_fullcode = value
    except Exception as e:
        import traceback
        builtins.print(f"[PDF-ITF14] ERROR: {e}")
        traceback.print_exc()
        return
    if not rects:
        return

    # Calcular x_start según alineación. Para los barcodes de imagen (QR/PDF417/DM)
    # el ancla horizontal es el BORDE DEL CÓDIGO (tamaño fijo), no el lienzo
    # (código+gap+HRI): el lienzo crece con el texto variable y anclarlo hacía
    # bailar el código alrededor de la guía. Igual que el visor
    # (_datamatrix_guide_mm): x_start = x - code_off - (borde del código según
    # alineación); el vertical sigue al código (content_height).
    # El resto de symbologías anclan sobre su caja completa (ancho fijo).
    alignment = pos_data.get("alignment", "izquierda")
    if is_datamatrix or is_qr or is_pdf417:
        _code_off = (
            _qr_code_off_mm if is_qr else
            _pdf417_code_off_mm if is_pdf417 else
            _dm_code_off_mm
        )
        # QR y PDF417: total_content_size = ancho del código; DM: dm_w_mm
        _code_w = dm_w_mm if is_datamatrix else total_content_size
        if alignment == "centro":
            x_start = x_mm - _code_off - _code_w / 2
        elif alignment == "derecha":
            x_start = x_mm - _code_off - _code_w
        else:
            x_start = x_mm - _code_off
    else:
        if alignment == "centro":
            x_start = x_mm - total_content_size / 2
        elif alignment == "derecha":
            x_start = x_mm - total_content_size
        else:
            x_start = x_mm

    # Normalizar color segun espacio
    def _hex_to_rgb(h: str):
        h = h.lstrip("#")
        return tuple(int(h[i : i + 2], 16) / 255.0 for i in (0, 2, 4))

    if color_space in ("CMYK", "SPOT"):
        if raw_cmyk:
            fill_color = tuple(float(v) / 100.0 for v in raw_cmyk)
        else:
            r, g, b = _hex_to_rgb(color_hex)
            from .color_picker import rgb_to_cmyk

            cmyk_100 = rgb_to_cmyk(r * 255, g * 255, b * 255)
            fill_color = tuple(v / 100.0 for v in cmyk_100)
    else:
        fill_color = _hex_to_rgb(color_hex)

    # Color del texto HRI (independiente del color de las barras)
    if text_color_space in ("CMYK", "SPOT"):
        if text_raw_cmyk:
            text_fill_color = tuple(float(v) / 100.0 for v in text_raw_cmyk)
        else:
            r, g, b = _hex_to_rgb(text_color_hex)
            from .color_picker import rgb_to_cmyk

            cmyk_100 = rgb_to_cmyk(r * 255, g * 255, b * 255)
            text_fill_color = tuple(v / 100.0 for v in cmyk_100)
    else:
        text_fill_color = _hex_to_rgb(text_color_hex)

    # Rotacion
    rad = math.radians(rotation)
    cos_a = math.cos(rad)
    sin_a = math.sin(rad)

    # Para SPOT: registrar content xrefs antes de dibujar
    spot_alias = None
    prev_xrefs = None
    is_spot = color_space == "SPOT" and bool(color_name) and doc is not None
    if is_spot:
        prev_xrefs = set(page.get_contents())
        spot_alias = _define_spot_colorspace(doc, page, color_name, fill_color)

    # Dibujar cada barra
    # Contrato geométrico (igual que Viewer):
    # - y_mm es la guía de referencia (borde INFERIOR del barcode en 0°)
    # - a 0°, las barras crecen hacia ARRIBA desde esa guía
    # - con rotación, giramos las 4 esquinas y usamos su bbox para evitar
    #   desplazamientos espurios (ej. salto lateral en 90°)
    content_height = (
        pdf417_h_mm if is_pdf417 else
        total_content_size if is_qr else
        (bar_height + ean5_digit_top_mm) if is_ean5 else
        bar_height
    )
    if is_datamatrix:
        if dm_hri_position in ("left", "right"):
            content_height = max(bar_height, _dm_total_text_mm)
        elif dm_hri_position == "above":
            content_height = _dm_total_text_mm + dm_hri_gap_mm + bar_height
        else:
            content_height = bar_height + dm_hri_gap_mm + _dm_total_text_mm
    if is_qr:
        if qr_hri_position in ("left", "right"):
            content_height = max(total_content_size, _qr_total_text_mm)
        elif qr_hri_position == "above":
            content_height = _qr_total_text_mm + qr_hri_gap_mm + total_content_size
        else:
            content_height = total_content_size + qr_hri_gap_mm + _qr_total_text_mm
    if is_pdf417:
        if pdf417_hri_position in ("left", "right"):
            content_height = max(pdf417_h_mm, _pdf417_total_text_mm)
        elif pdf417_hri_position == "above":
            content_height = _pdf417_total_text_mm + pdf417_hri_gap_mm + pdf417_h_mm
        else:
            content_height = pdf417_h_mm + pdf417_hri_gap_mm + _pdf417_total_text_mm
    if is_itf14:
        itf14_hri_position = pos_data.get("itf14_hri_position", "below")
        _itf14_y_off = 0.0
        if itf14_hri_position == "above":
            from utils.barcode_module import get_font_text_metrics
            _itf14_asc, _, _ = get_font_text_metrics(_itf14_font_path)
            _itf14_ry_offset = _itf14_asc * ds_mm + itf14_hri_gap_mm
            # El loop de barras ancla ry al top de la caja (el shift se cancela
            # con content_height y las barras quedan en la guía); los bearers
            # se dibujan aparte sin ese cancelo → necesitan el offset explícito.
            _itf14_y_off = _itf14_ry_offset
            content_height = _itf14_ry_offset + bar_height
            rects = [(rx, ry + _itf14_ry_offset, rw, rh) for rx, ry, rw, rh in rects]
        else:
            content_height = bar_height + itf14_hri_gap_mm + _itf14_cap * ds_mm
        if itf14_bearer_sides == "2":
            content_height -= itf14_bearer_off_mm
    if is_code39:
        code39_hri_gap_mm = float(pos_data.get("code39_hri_gap_mm", 2.0))
        code39_hri_position = pos_data.get("code39_hri_position", "below")
        from utils.barcode_module import resolve_font_path, get_digit_advance_em, get_font_text_metrics, get_font_cap_height_ratio
        _code39_font_path = resolve_font_path(pos_data.get("barcode_font_family", "OCR-B"))
        _code39_cap = get_font_cap_height_ratio(_code39_font_path)
        _code39_asc, _, _ = get_font_text_metrics(_code39_font_path)
        ds_pt = float(pos_data.get("barcode_font_size", 13.0))
        ds_mm = ds_pt * FONT_PT_TO_MM
        if code39_hri_position == "above":
            _code39_ry_offset = _code39_asc * ds_mm + code39_hri_gap_mm
            content_height = _code39_ry_offset + bar_height
            rects = [(rx, ry + _code39_ry_offset, rw, rh) for rx, ry, rw, rh in rects]
        else:
            content_height = bar_height + code39_hri_gap_mm + _code39_cap * ds_mm
    if is_code128:
        code128_hri_gap_mm = float(pos_data.get("code128_hri_gap_mm", 2.0))
        code128_hri_position = pos_data.get("code128_hri_position", "below")
        from utils.barcode_module import resolve_font_path, get_digit_advance_em, get_font_text_metrics, get_font_cap_height_ratio
        _code128_font_path = resolve_font_path(pos_data.get("barcode_font_family", "OCR-B"))
        _code128_cap = get_font_cap_height_ratio(_code128_font_path)
        _code128_asc, _, _ = get_font_text_metrics(_code128_font_path)
        ds_pt = float(pos_data.get("barcode_font_size", 13.0))
        ds_mm = ds_pt * FONT_PT_TO_MM
        if code128_hri_position == "above":
            _code128_ry_offset = _code128_asc * ds_mm + code128_hri_gap_mm
            content_height = _code128_ry_offset + bar_height
            rects = [(rx, ry + _code128_ry_offset, rw, rh) for rx, ry, rw, rh in rects]
        else:
            content_height = bar_height + code128_hri_gap_mm + _code128_cap * ds_mm
    _shape_batch = len(rects) > 10
    if _shape_batch:
        _shape = page.new_shape()

    for rx, ry, rw, rh in rects:
        bar_x = x_start + rx
        if is_qr:
            bar_x = x_start + _qr_code_off_mm + rx
            bar_y = y_mm - ry - rh
        elif is_pdf417:
            bar_x = x_start + _pdf417_code_off_mm + rx
            bar_y = y_mm - ry - rh
        elif is_datamatrix:
            bar_x = x_start + _dm_code_off_mm + rx
            # Alineación vertical anclada al CÓDIGO: la parte inferior del código queda
            # en la guía (y_mm); el HRI below cuelga por debajo de la guía.
            bar_y = y_mm - ry - rh
        else:
            bar_y = (y_mm - content_height) + ry

        if rotation != 0:
            corners = [
                (bar_x, bar_y),
                (bar_x + rw, bar_y),
                (bar_x + rw, bar_y + rh),
                (bar_x, bar_y + rh),
            ]
            rot_corners = []
            for cx, cy in corners:
                rel_x = cx - x_mm
                rel_y = cy - y_mm
                rot_x = rel_x * cos_a - rel_y * sin_a
                rot_y = rel_x * sin_a + rel_y * cos_a
                rot_corners.append((x_mm + rot_x, y_mm + rot_y))
            xs = [p[0] for p in rot_corners]
            ys = [p[1] for p in rot_corners]
            bar_x = min(xs)
            bar_y = min(ys)
            bar_w_mm = max(xs) - bar_x
            bar_h_mm = max(ys) - bar_y
        else:
            bar_w_mm = rw
            bar_h_mm = rh

        bx = (bleed_mm + bar_x) * 72.0 / 25.4
        by = (bleed_mm + bar_y) * 72.0 / 25.4
        bw = bar_w_mm * 72.0 / 25.4
        bh = bar_h_mm * 72.0 / 25.4

        if rx == 0 and ry == 0:
            _debug_y(
                f"[render_barcode_to_pdf] first bar: bar_x={bar_x:.2f} bar_y={bar_y:.2f} "
                f"(anchor_y={y_mm:.2f}, bar_h={bar_height:.2f}) bx={bx:.2f} by={by:.2f} "
                f"(from top={by/72*25.4 - bleed_mm:.2f}mm)"
            )

        if _shape_batch:
            _shape.draw_rect(fitz.Rect(bx, by, bx + bw, by + bh))
            _shape.finish(width=0, color=None, fill=fill_color)
        else:
            try:
                page.draw_rect(fitz.Rect(bx, by, bx + bw, by + bh),
                               color=None, fill=fill_color, width=0)
            except Exception:
                pass

    if _shape_batch:
        _shape.commit()

    # ITF-14: bearer bar
    if is_itf14 and rects:
        total_w_mm = total_content_size
        if itf14_bearer_sides == "4":
            bearer_rect_x = x_start + itf14_bearer_off_mm
            bearer_rect_y = y_mm - content_height + itf14_bearer_off_mm + _itf14_y_off
            bearer_rect_w = total_w_mm - itf14_bearer_w_mm
            bearer_rect_h = bar_height - itf14_bearer_w_mm
            if rotation != 0:
                corners = [
                    (bearer_rect_x, bearer_rect_y),
                    (bearer_rect_x + bearer_rect_w, bearer_rect_y),
                    (bearer_rect_x + bearer_rect_w, bearer_rect_y + bearer_rect_h),
                    (bearer_rect_x, bearer_rect_y + bearer_rect_h),
                ]
                rot_corners = []
                for cx, cy in corners:
                    rel_x = cx - x_mm
                    rel_y = cy - y_mm
                    rot_x = rel_x * cos_a - rel_y * sin_a
                    rot_y = rel_x * sin_a + rel_y * cos_a
                    rot_corners.append((x_mm + rot_x, y_mm + rot_y))
                xs = [p[0] for p in rot_corners]
                ys = [p[1] for p in rot_corners]
                bearer_rect_x = min(xs)
                bearer_rect_y = min(ys)
                bearer_rect_w = max(xs) - bearer_rect_x
                bearer_rect_h = max(ys) - bearer_rect_y
            bx = (bleed_mm + bearer_rect_x) * 72.0 / 25.4
            by = (bleed_mm + bearer_rect_y) * 72.0 / 25.4
            bw = bearer_rect_w * 72.0 / 25.4
            bh = bearer_rect_h * 72.0 / 25.4
            bearer_w_points = itf14_bearer_w_mm * 72.0 / 25.4
            try:
                page.draw_rect(fitz.Rect(bx, by, bx + bw, by + bh),
                               color=fill_color, fill=None, width=bearer_w_points)
            except Exception:
                pass
        else:
            # Top bar
            top_rect_x = x_start
            top_rect_y = y_mm - content_height + itf14_bearer_off_mm + _itf14_y_off
            top_rect_w = total_w_mm
            top_rect_h = itf14_bearer_w_mm
            if rotation != 0:
                corners = [
                    (top_rect_x, top_rect_y),
                    (top_rect_x + top_rect_w, top_rect_y),
                    (top_rect_x + top_rect_w, top_rect_y + top_rect_h),
                    (top_rect_x, top_rect_y + top_rect_h),
                ]
                rot_corners = []
                for cx, cy in corners:
                    rel_x = cx - x_mm
                    rel_y = cy - y_mm
                    rot_x = rel_x * cos_a - rel_y * sin_a
                    rot_y = rel_x * sin_a + rel_y * cos_a
                    rot_corners.append((x_mm + rot_x, y_mm + rot_y))
                xs = [p[0] for p in rot_corners]
                ys = [p[1] for p in rot_corners]
                top_rect_x = min(xs)
                top_rect_y = min(ys)
                top_rect_w = max(xs) - top_rect_x
                top_rect_h = max(ys) - top_rect_y
            bx = (bleed_mm + top_rect_x) * 72.0 / 25.4
            by = (bleed_mm + top_rect_y) * 72.0 / 25.4
            bw = top_rect_w * 72.0 / 25.4
            bh = top_rect_h * 72.0 / 25.4
            try:
                page.draw_rect(fitz.Rect(bx, by, bx + bw, by + bh),
                               color=fill_color, fill=fill_color, width=0)
            except Exception:
                pass
            # Bottom bar
            bot_rect_x = x_start
            bot_rect_y = y_mm - content_height + bar_height - itf14_bearer_off_mm - itf14_bearer_w_mm + _itf14_y_off
            bot_rect_w = total_w_mm
            bot_rect_h = itf14_bearer_w_mm
            if rotation != 0:
                corners = [
                    (bot_rect_x, bot_rect_y),
                    (bot_rect_x + bot_rect_w, bot_rect_y),
                    (bot_rect_x + bot_rect_w, bot_rect_y + bot_rect_h),
                    (bot_rect_x, bot_rect_y + bot_rect_h),
                ]
                rot_corners = []
                for cx, cy in corners:
                    rel_x = cx - x_mm
                    rel_y = cy - y_mm
                    rot_x = rel_x * cos_a - rel_y * sin_a
                    rot_y = rel_x * sin_a + rel_y * cos_a
                    rot_corners.append((x_mm + rot_x, y_mm + rot_y))
                xs = [p[0] for p in rot_corners]
                ys = [p[1] for p in rot_corners]
                bot_rect_x = min(xs)
                bot_rect_y = min(ys)
                bot_rect_w = max(xs) - bot_rect_x
                bot_rect_h = max(ys) - bot_rect_y
            bx = (bleed_mm + bot_rect_x) * 72.0 / 25.4
            by = (bleed_mm + bot_rect_y) * 72.0 / 25.4
            bw = bot_rect_w * 72.0 / 25.4
            bh = bot_rect_h * 72.0 / 25.4
            try:
                page.draw_rect(fitz.Rect(bx, by, bx + bw, by + bh),
                               color=fill_color, fill=fill_color, width=0)
            except Exception:
                pass

    # Para SPOT: inyectar operadores de tinta plana en los nuevos streams
    # Reemplazar TODOS los operadores 'k' (fill CMYK) no solo el ultimo
    if is_spot and spot_alias and prev_xrefs is not None:
        spot_tint_pct = max(0.0, min(100.0, float(color_tint)))
        current_xrefs = page.get_contents()
        new_xrefs = [x for x in current_xrefs if x not in prev_xrefs]
        if not new_xrefs:
            new_xrefs = [current_xrefs[-1]] if current_xrefs else []
        float_re = rb"[-+]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][-+]?[0-9]+)?"
        pattern = (
            rb"(?m)"
            + float_re
            + rb"\s+"
            + float_re
            + rb"\s+"
            + float_re
            + rb"\s+"
            + float_re
            + rb"\s+"
            + rb"k\b"
        )
        replacement = (f"/{spot_alias} cs\n{spot_tint_pct / 100.0:.6f} scn").encode(
            "latin-1"
        )
        for target_xref in new_xrefs:
            raw = doc.xref_stream(target_xref)
            if raw is None:
                continue
            modified = re.sub(pattern, replacement, raw)
            if modified != raw:
                doc.update_stream(target_xref, modified)

    # EAN-13 digit text (after bars)
    if is_ean13 and ean13_fullcode:
        ds_pt = float(pos_data.get("barcode_font_size", 13.0))
        ds_mm = ds_pt * FONT_PT_TO_MM
        font_family = pos_data.get("barcode_font_family", "OCR-B")

        # Map OCR font name to a font file for PyMuPDF
        ean13_font_map = {
            "OCR-A": "OCRA",
            "OCR-B": "OCRB",
            "OCR-B F": "OCRBF",
            "OCR-B L": "OCRBL",
        }
        font_key = ean13_font_map.get(font_family, "OCRB")

        from utils.barcode_module import resolve_font_path, get_digit_advance_em
        font_path = resolve_font_path(font_key=font_key)

        # Register font once before the digit loop
        ean13_fontname = f"EAN13_{font_key}"
        if Path(font_path).exists():
            try:
                page.insert_font(fontname=ean13_fontname, fontfile=str(font_path))
            except Exception:
                ean13_fontname = None
        else:
            ean13_fontname = None

        module_width = total_bar_width / get_ean13_module_count()
        _ean13_el, _ean13_c_eff, _ean13_boff, _ean13_cw, _ean13_ds_eff = ean_hri_layout(
            "ean13", ean13_fullcode, module_width, ds_mm, font_family
        )
        ean13_ds_pt = _ean13_ds_eff / FONT_PT_TO_MM
        digit_positions = [
            (digit, x_start + cx_mm - _ean13_c_eff / 2)
            for digit, cx_mm in _ean13_el
        ]

        # Baseline at y_mm so digits rest on the guide
        digit_y = y_mm
        for digit_char, dx in digit_positions:
            if rotation != 0:
                rel_x = dx - x_mm
                rel_y = digit_y - y_mm
                rot_x = rel_x * cos_a - rel_y * sin_a
                rot_y = rel_x * sin_a + rel_y * cos_a
                final_x = x_mm + rot_x
                final_y = y_mm + rot_y
            else:
                final_x = dx
                final_y = digit_y

            kwargs = dict(
                point=fitz.Point(
                    (bleed_mm + final_x) * 72.0 / 25.4,
                    (bleed_mm + final_y) * 72.0 / 25.4,
                ),
                text=digit_char,
                fontsize=ean13_ds_pt,
                color=text_fill_color,
                rotate=-rotation,
            )
            if ean13_fontname:
                kwargs["fontname"] = ean13_fontname
            try:
                page.insert_text(**kwargs)
            except Exception:
                pass

    # EAN-8 digit text (after bars)
    if is_ean8 and ean8_fullcode:
        ds_pt = float(pos_data.get("barcode_font_size", 13.0))
        ds_mm = ds_pt * FONT_PT_TO_MM
        font_family = pos_data.get("barcode_font_family", "OCR-B")

        ean8_font_map = {
            "OCR-A": "OCRA",
            "OCR-B": "OCRB",
            "OCR-B F": "OCRBF",
            "OCR-B L": "OCRBL",
        }
        font_key = ean8_font_map.get(font_family, "OCRB")

        from utils.barcode_module import resolve_font_path, get_digit_advance_em
        font_path = resolve_font_path(font_key=font_key)

        ean8_fontname = f"EAN8_{font_key}"
        if Path(font_path).exists():
            try:
                page.insert_font(fontname=ean8_fontname, fontfile=str(font_path))
            except Exception:
                ean8_fontname = None
        else:
            ean8_fontname = None

        module_width = total_bar_width / get_ean8_module_count()
        _ean8_el, _ean8_c_eff, _ean8_boff, _ean8_cw, _ean8_ds_eff = ean_hri_layout(
            "ean8", ean8_fullcode, module_width, ds_mm, font_family
        )
        ean8_ds_pt = _ean8_ds_eff / FONT_PT_TO_MM

        digit_positions = [
            (digit, x_start + cx_mm - _ean8_c_eff / 2)
            for digit, cx_mm in _ean8_el
        ]

        digit_y = y_mm
        for digit_char, dx in digit_positions:
            if rotation != 0:
                rel_x = dx - x_mm
                rel_y = digit_y - y_mm
                rot_x = rel_x * cos_a - rel_y * sin_a
                rot_y = rel_x * sin_a + rel_y * cos_a
                final_x = x_mm + rot_x
                final_y = y_mm + rot_y
            else:
                final_x = dx
                final_y = digit_y

            kwargs = dict(
                point=fitz.Point(
                    (bleed_mm + final_x) * 72.0 / 25.4,
                    (bleed_mm + final_y) * 72.0 / 25.4,
                ),
                text=digit_char,
                fontsize=ean8_ds_pt,
                color=text_fill_color,
                rotate=-rotation,
            )
            if ean8_fontname:
                kwargs["fontname"] = ean8_fontname
            try:
                page.insert_text(**kwargs)
            except Exception:
                pass

    # EAN-5 digit text (ABOVE bars)
    if is_ean5 and ean5_fullcode:
        ds_pt = float(pos_data.get("barcode_font_size", 13.0))
        ds_mm = ds_pt * FONT_PT_TO_MM
        font_family = pos_data.get("barcode_font_family", "OCR-B")

        ean5_font_map = {
            "OCR-A": "OCRA",
            "OCR-B": "OCRB",
            "OCR-B F": "OCRBF",
            "OCR-B L": "OCRBL",
        }
        font_key = ean5_font_map.get(font_family, "OCRB")

        from utils.barcode_module import resolve_font_path, get_digit_advance_em
        font_path = resolve_font_path(font_key=font_key)

        ean5_fontname = f"EAN5_{font_key}"
        if Path(font_path).exists():
            try:
                page.insert_font(fontname=ean5_fontname, fontfile=str(font_path))
            except Exception:
                ean5_fontname = None
        else:
            ean5_fontname = None

        char_w_mm = ds_mm * get_digit_advance_em(pos_data.get("barcode_font_family", "OCR-B"))
        module_width = total_bar_width / get_ean5_module_count()

        digit_positions = []
        zone_w = 47 / 5.0
        for idx in range(5):
            cm = (idx + 0.5) * zone_w
            digit_positions.append((ean5_fullcode[idx], x_start + cm * module_width - char_w_mm / 2))

        # Text baseline above bars
        digit_y = y_mm - bar_height - ean5_hri_gap_mm
        for digit_char, dx in digit_positions:
            if rotation != 0:
                rel_x = dx - x_mm
                rel_y = digit_y - y_mm
                rot_x = rel_x * cos_a - rel_y * sin_a
                rot_y = rel_x * sin_a + rel_y * cos_a
                final_x = x_mm + rot_x
                final_y = y_mm + rot_y
            else:
                final_x = dx
                final_y = digit_y

            kwargs = dict(
                point=fitz.Point(
                    (bleed_mm + final_x) * 72.0 / 25.4,
                    (bleed_mm + final_y) * 72.0 / 25.4,
                ),
                text=digit_char,
                fontsize=ds_pt,
                color=text_fill_color,
                rotate=-rotation,
            )
            if ean5_fontname:
                kwargs["fontname"] = ean5_fontname
            try:
                page.insert_text(**kwargs)
            except Exception:
                pass

    # ITF-14 digit text (below bars)
    if is_itf14 and itf14_fullcode:
        ds_pt = float(pos_data.get("barcode_font_size", 13.0))
        ds_mm = ds_pt * FONT_PT_TO_MM

        itf14_fontname = f"ITF14_{Path(_itf14_font_path).stem}"
        if Path(_itf14_font_path).exists():
            try:
                page.insert_font(fontname=itf14_fontname, fontfile=_itf14_font_path)
            except Exception:
                itf14_fontname = None
        else:
            itf14_fontname = None

        # HRI: formatted 5-block string centered below bars (métricas reales de la fuente)
        hri = format_itf14_hri(itf14_fullcode)
        meas = fitz.Font(fontfile=_itf14_font_path)
        hri_w_pt = meas.text_length(hri, fontsize=ds_pt)
        hri_w_mm = hri_w_pt * 25.4 / 72.0
        hri_center_mm = x_start + total_content_size / 2
        hri_left_mm = hri_center_mm - hri_w_mm / 2

        itf14_hri_position = pos_data.get("itf14_hri_position", "below")
        if itf14_hri_position == "above":
            digit_y = y_mm - bar_height - itf14_hri_gap_mm
        else:
            digit_y = y_mm
        if rotation != 0:
            rel_x = hri_left_mm - x_mm
            rel_y = digit_y - y_mm
            rot_x = rel_x * cos_a - rel_y * sin_a
            rot_y = rel_x * sin_a + rel_y * cos_a
            fx = x_mm + rot_x
            fy = y_mm + rot_y
        else:
            fx = hri_left_mm
            fy = digit_y

        kwargs = dict(
            point=fitz.Point(
                (bleed_mm + fx) * 72.0 / 25.4,
                (bleed_mm + fy) * 72.0 / 25.4,
            ),
            text=hri,
            fontsize=ds_pt,
            color=text_fill_color,
            rotate=-rotation,
        )
        if itf14_fontname:
            kwargs["fontname"] = itf14_fontname
        try:
            page.insert_text(**kwargs)
        except Exception:
            pass

    # Code 39 HRI text (below bars)
    if is_code39 and code39_fullcode:
        ds_pt = float(pos_data.get("barcode_font_size", 13.0))
        ds_mm = ds_pt * FONT_PT_TO_MM
        _code39_font_path = resolve_font_path(pos_data.get("barcode_font_family", "OCR-B"))

        code39_fontname = f"Code39_{Path(_code39_font_path).stem}"
        if Path(_code39_font_path).exists():
            try:
                page.insert_font(fontname=code39_fontname, fontfile=_code39_font_path)
            except Exception:
                code39_fontname = None
        else:
            code39_fontname = None

        meas = fitz.Font(fontfile=_code39_font_path)
        hri_w_pt = meas.text_length(code39_fullcode, fontsize=ds_pt)
        hri_w_mm = hri_w_pt * 25.4 / 72.0
        hri_center_mm = x_start + total_content_size / 2
        hri_left_mm = hri_center_mm - hri_w_mm / 2

        code39_hri_position = pos_data.get("code39_hri_position", "below")
        if code39_hri_position == "above":
            digit_y = y_mm - bar_height - code39_hri_gap_mm
        else:
            digit_y = y_mm
        if rotation != 0:
            rel_x = hri_left_mm - x_mm
            rel_y = digit_y - y_mm
            rot_x = rel_x * cos_a - rel_y * sin_a
            rot_y = rel_x * sin_a + rel_y * cos_a
            fx = x_mm + rot_x
            fy = y_mm + rot_y
        else:
            fx = hri_left_mm
            fy = digit_y

        kwargs = dict(
            point=fitz.Point(
                (bleed_mm + fx) * 72.0 / 25.4,
                (bleed_mm + fy) * 72.0 / 25.4,
            ),
            text=code39_fullcode,
            fontsize=ds_pt,
            color=text_fill_color,
            rotate=-rotation,
        )
        if code39_fontname:
            kwargs["fontname"] = code39_fontname
        try:
            page.insert_text(**kwargs)
        except Exception:
            pass

    # Code 128 HRI text
    if is_code128 and code128_fullcode:
        ds_pt = float(pos_data.get("barcode_font_size", 13.0))
        ds_mm = ds_pt * FONT_PT_TO_MM
        _code128_font_path = resolve_font_path(pos_data.get("barcode_font_family", "OCR-B"))

        code128_fontname = f"Code128_{Path(_code128_font_path).stem}"
        if Path(_code128_font_path).exists():
            try:
                page.insert_font(fontname=code128_fontname, fontfile=_code128_font_path)
            except Exception:
                code128_fontname = None
        else:
            code128_fontname = None

        meas = fitz.Font(fontfile=_code128_font_path)
        hri_w_pt = meas.text_length(code128_fullcode, fontsize=ds_pt)
        hri_w_mm = hri_w_pt * 25.4 / 72.0
        hri_center_mm = x_start + total_content_size / 2
        hri_left_mm = hri_center_mm - hri_w_mm / 2

        if code128_hri_position == "above":
            digit_y = y_mm - bar_height - code128_hri_gap_mm
        else:
            digit_y = y_mm
        if rotation != 0:
            rel_x = hri_left_mm - x_mm
            rel_y = digit_y - y_mm
            rot_x = rel_x * cos_a - rel_y * sin_a
            rot_y = rel_x * sin_a + rel_y * cos_a
            fx = x_mm + rot_x
            fy = y_mm + rot_y
        else:
            fx = hri_left_mm
            fy = digit_y

        kwargs = dict(
            point=fitz.Point(
                (bleed_mm + fx) * 72.0 / 25.4,
                (bleed_mm + fy) * 72.0 / 25.4,
            ),
            text=code128_fullcode,
            fontsize=ds_pt,
            color=text_fill_color,
            rotate=-rotation,
        )
        if code128_fontname:
            kwargs["fontname"] = code128_fontname
        try:
            page.insert_text(**kwargs)
        except Exception:
            pass

    # HRI text (below/above bars) — uses pre-computed values from content_height block
    if is_datamatrix and value and _dm_hri_lines:
        _draw_hri_text_to_page(page, _dm_hri_lines, _dm_font_path, ds_pt, dm_hri_position, dm_hri_gap_mm,
                               _dm_hri_align, _dm_geo, x_start, x_mm, y_mm, content_height, bar_height,
                               rotation, cos_a, sin_a, bleed_mm, text_fill_color)
    if is_qr and value and _qr_hri_lines:
        _draw_hri_text_to_page(page, _qr_hri_lines, _qr_font_path, ds_pt, qr_hri_position, qr_hri_gap_mm,
                               _qr_hri_align, _qr_geo, x_start, x_mm, y_mm, content_height, total_content_size,
                               rotation, cos_a, sin_a, bleed_mm, text_fill_color)
    if is_pdf417 and value and _pdf417_hri_lines:
        _draw_hri_text_to_page(page, _pdf417_hri_lines, _pdf417_font_path, ds_pt, pdf417_hri_position, pdf417_hri_gap_mm,
                               _pdf417_hri_align, _pdf417_geo, x_start, x_mm, y_mm, content_height, pdf417_h_mm,
                               rotation, cos_a, sin_a, bleed_mm, text_fill_color)

    # ISBN-13 digit text + ISBN label (after bars)
    if is_isbn13 and isbn13_fullcode:
        ds_pt = float(pos_data.get("barcode_font_size", 13.0))
        ds_mm = ds_pt * FONT_PT_TO_MM
        font_family = pos_data.get("barcode_font_family", "OCR-B")

        ean13_font_map = {
            "OCR-A": "OCRA",
            "OCR-B": "OCRB",
            "OCR-B F": "OCRBF",
            "OCR-B L": "OCRBL",
        }
        font_key = ean13_font_map.get(font_family, "OCRB")

        from utils.barcode_module import (
            resolve_font_path,
            get_digit_advance_em,
            get_ean13_font_descender_ratio,
        )
        font_path = resolve_font_path(font_key=font_key)

        ean13_fontname = f"ISBN13_{font_key}"
        if Path(font_path).exists():
            try:
                page.insert_font(fontname=ean13_fontname, fontfile=str(font_path))
            except Exception:
                ean13_fontname = None
        else:
            ean13_fontname = None

        module_width = total_bar_width / get_ean13_module_count()
        _isbn_el, _isbn_c_eff, _isbn_boff, _isbn_cw, _isbn_ds_eff = ean_hri_layout(
            "isbn13", isbn13_fullcode, module_width, ds_mm, font_family
        )
        isbn_ds_pt = _isbn_ds_eff / FONT_PT_TO_MM
        _isbn_label_ds_pt = max(1.0, ds_pt - ISBN_SIZE_OFFSET)
        _isbn_label_ds_mm = _isbn_label_ds_pt * FONT_PT_TO_MM

        digit_positions = [
            (digit, x_start + cx_mm - _isbn_c_eff / 2)
            for digit, cx_mm in _isbn_el
        ]

        digit_y = y_mm
        for digit_char, dx in digit_positions:
            if rotation != 0:
                rel_x = dx - x_mm
                rel_y = digit_y - y_mm
                rot_x = rel_x * cos_a - rel_y * sin_a
                rot_y = rel_x * sin_a + rel_y * cos_a
                final_x = x_mm + rot_x
                final_y = y_mm + rot_y
            else:
                final_x = dx
                final_y = digit_y

            kwargs = dict(
                point=fitz.Point(
                    (bleed_mm + final_x) * 72.0 / 25.4,
                    (bleed_mm + final_y) * 72.0 / 25.4,
                ),
                text=digit_char,
                fontsize=isbn_ds_pt,
                color=text_fill_color,
                rotate=-rotation,
            )
            if ean13_fontname:
                kwargs["fontname"] = ean13_fontname
            try:
                page.insert_text(**kwargs)
            except Exception:
                pass

        # ISBN label above bars (compact, centered)
        show_title = pos_data.get("isbn13_show_title", "Sí") == "Sí"
        if show_title:
            isbn_label = _format_isbn13(isbn13_fullcode)
            # Hueco visible = 0.25×cuerpo crudo (como los números), sin suelo: el texto se ancla
            # por línea base en PDF, así que se suma el descender del label al gap para que el
            # hueco coincida con el visor (siempre positivo: desc×label ≥ 0)
            isbn_gap_mm = (
                ds_pt * FONT_PT_TO_MM * 0.25
                + get_ean13_font_descender_ratio(font_family) * _isbn_label_ds_mm
            )
            isbn_y = y_mm - bar_height - guard_ext_mm - isbn_gap_mm
            isbn_center_x = x_start + bar_offset_mm + total_bar_width / 2
            if Path(font_path).exists():
                _isbn_measure_font = fitz.Font(fontfile=str(font_path))
                isbn_text_width_pt = _isbn_measure_font.text_length(isbn_label, fontsize=_isbn_label_ds_pt)
                isbn_text_width_mm = isbn_text_width_pt * 25.4 / 72.0
            else:
                isbn_text_width_mm = len(isbn_label) * (_isbn_label_ds_mm * 0.50)
            isbn_x = isbn_center_x - isbn_text_width_mm / 2

            if rotation != 0:
                rel_x = isbn_x - x_mm
                rel_y = isbn_y - y_mm
                rot_x = rel_x * cos_a - rel_y * sin_a
                rot_y = rel_x * sin_a + rel_y * cos_a
                final_x = x_mm + rot_x
                final_y = y_mm + rot_y
            else:
                final_x = isbn_x
                final_y = isbn_y

            kwargs = dict(
                point=fitz.Point(
                    (bleed_mm + final_x) * 72.0 / 25.4,
                    (bleed_mm + final_y) * 72.0 / 25.4,
                ),
                text=isbn_label,
                fontsize=_isbn_label_ds_pt,
                color=text_fill_color,
                rotate=-rotation,
            )
            if ean13_fontname:
                kwargs["fontname"] = ean13_fontname
            try:
                page.insert_text(**kwargs)
            except Exception:
                pass

    # UPC-A digit text (after bars)
    if is_upca and upca_fullcode:
        ds_pt = float(pos_data.get("barcode_font_size", 13.0))
        ds_mm = ds_pt * FONT_PT_TO_MM
        font_family = pos_data.get("barcode_font_family", "OCR-B")

        ean13_font_map = {
            "OCR-A": "OCRA",
            "OCR-B": "OCRB",
            "OCR-B F": "OCRBF",
            "OCR-B L": "OCRBL",
        }
        font_key = ean13_font_map.get(font_family, "OCRB")

        from utils.barcode_module import resolve_font_path, get_digit_advance_em
        font_path = resolve_font_path(font_key=font_key)

        ean13_fontname = f"UPCA_{font_key}"
        if Path(font_path).exists():
            try:
                page.insert_font(fontname=ean13_fontname, fontfile=str(font_path))
            except Exception:
                ean13_fontname = None
        else:
            ean13_fontname = None

        module_width = total_bar_width / get_ean13_module_count()
        _upca_el, _upca_c_eff, _upca_boff, _upca_cw, _upca_ds_eff = ean_hri_layout(
            "upca", upca_fullcode, module_width, ds_mm, font_family
        )
        upca_ds_pt = _upca_ds_eff / FONT_PT_TO_MM

        digit_positions = [
            (digit, x_start + cx_mm - _upca_c_eff / 2)
            for digit, cx_mm in _upca_el
        ]

        digit_y = y_mm
        for digit_char, dx in digit_positions:
            if rotation != 0:
                rel_x = dx - x_mm
                rel_y = digit_y - y_mm
                rot_x = rel_x * cos_a - rel_y * sin_a
                rot_y = rel_x * sin_a + rel_y * cos_a
                final_x = x_mm + rot_x
                final_y = y_mm + rot_y
            else:
                final_x = dx
                final_y = digit_y

            kwargs = dict(
                point=fitz.Point(
                    (bleed_mm + final_x) * 72.0 / 25.4,
                    (bleed_mm + final_y) * 72.0 / 25.4,
                ),
                text=digit_char,
                fontsize=upca_ds_pt,
                color=text_fill_color,
                rotate=-rotation,
            )
            if ean13_fontname:
                kwargs["fontname"] = ean13_fontname
            try:
                page.insert_text(**kwargs)
            except Exception:
                pass

    # UPC-E digit text (6 digits, centered, after bars)
    if is_upce and upce_fullcode:
        ds_pt = float(pos_data.get("barcode_font_size", 13.0))
        ds_mm = ds_pt * FONT_PT_TO_MM
        font_family = pos_data.get("barcode_font_family", "OCR-B")

        ean13_font_map = {
            "OCR-A": "OCRA",
            "OCR-B": "OCRB",
            "OCR-B F": "OCRBF",
            "OCR-B L": "OCRBL",
        }
        font_key = ean13_font_map.get(font_family, "OCRB")

        from utils.barcode_module import resolve_font_path, get_digit_advance_em
        font_path = resolve_font_path(font_key=font_key)

        ean13_fontname = f"UPCE_{font_key}"
        if Path(font_path).exists():
            try:
                page.insert_font(fontname=ean13_fontname, fontfile=str(font_path))
            except Exception:
                ean13_fontname = None
        else:
            ean13_fontname = None

        module_width = total_bar_width / get_upce_module_count()
        _upce_el, _upce_c_eff, _upce_boff, _upce_cw, _upce_ds_eff = ean_hri_layout(
            "upce", upce_fullcode.zfill(6), module_width, ds_mm, font_family
        )
        upce_ds_pt = _upce_ds_eff / FONT_PT_TO_MM

        digit_y = y_mm
        for digit_char, cx_mm in _upce_el:
            dx = x_start + cx_mm - _upce_c_eff / 2

            if rotation != 0:
                rel_x = dx - x_mm
                rel_y = digit_y - y_mm
                rot_x = rel_x * cos_a - rel_y * sin_a
                rot_y = rel_x * sin_a + rel_y * cos_a
                final_x = x_mm + rot_x
                final_y = y_mm + rot_y
            else:
                final_x = dx
                final_y = digit_y

            kwargs = dict(
                point=fitz.Point(
                    (bleed_mm + final_x) * 72.0 / 25.4,
                    (bleed_mm + final_y) * 72.0 / 25.4,
                ),
                text=digit_char,
                fontsize=upce_ds_pt,
                color=text_fill_color,
                rotate=-rotation,
            )
            if ean13_fontname:
                kwargs["fontname"] = ean13_fontname
            try:
                page.insert_text(**kwargs)
            except Exception:
                pass


def _map_font_name(font_name: str, font_style: str = "Regular") -> str:
    """
    Mapea nombres de fuentes comunes a nombres de fuentes de PyMuPDF.
    PyMuPDF soporta las 14 fuentes base de PDF más fuentes del sistema.

    Args:
        font_name: Nombre de la familia de fuente (ej: "Helvetica", "Times")
        font_style: Estilo de la fuente (ej: "Regular", "Bold", "Italic", "Bold Italic")
    """
    # Normalizar estilo
    style_lower = font_style.lower().replace(" ", "")
    # Normalizar sufijos raros (ej: 'BoldItalicMT' -> 'BoldItalic')
    if style_lower.endswith("mt"):
        style_lower = style_lower[:-2]

    # Fuentes base de PDF (siempre disponibles)
    # Mapeamos familia + estilo a código PyMuPDF
    base_fonts = {
        # Helvetica
        ("helvetica", "regular"): "helv",
        ("helvetica", "bold"): "hebo",
        ("helvetica", "italic"): "helo",
        ("helvetica", "oblique"): "helo",
        ("helvetica", "bolditalic"): "heBO",
        ("helvetica", "boldoblique"): "heBO",
        # Times
        ("times", "regular"): "tiro",
        ("times", "bold"): "tibo",
        ("times", "italic"): "tiit",
        ("times", "bolditalic"): "tibi",
        ("timesroman", "regular"): "tiro",
        ("times-roman", "regular"): "tiro",
        ("timesnewroman", "regular"): "tiro",
        ("timesnewroman", "bold"): "tibo",
        ("timesnewroman", "italic"): "tiit",
        ("timesnewroman", "bolditalic"): "tibi",
        # Courier
        ("courier", "regular"): "cour",
        ("courier", "bold"): "cobo",
        ("courier", "italic"): "coOl",
        ("courier", "oblique"): "coOl",
        ("courier", "bolditalic"): "coBO",
        ("courier", "boldoblique"): "coBO",
        # Symbol y ZapfDingbats
        ("symbol", "regular"): "symb",
        ("zapfdingbats", "regular"): "zadb",
    }

    # Normalizar nombre de familia (minúsculas, sin espacios ni guiones)
    family_normalized = font_name.lower().replace(" ", "").replace("-", "")

    # Buscar en fuentes base
    key = (family_normalized, style_lower)
    if key in base_fonts:
        return base_fonts[key]

    # Si el estilo NO es regular, evitar el fallback a Regular en base14.
    # Esto permite que PyMuPDF busque en fuentes del sistema (ej: Helvetica Light Oblique en macOS).
    regular_aliases = {"regular", "roman", "book", "normal", "medium"}
    if style_lower in regular_aliases:
        key_regular = (family_normalized, "regular")
        if key_regular in base_fonts:
            return base_fonts[key_regular]

    # Para fuentes del sistema, combinar familia + estilo
    # Esto ayuda a PyMuPDF a encontrar la variante correcta
    if style_lower and style_lower not in regular_aliases:
        return f"{font_name} {font_style}"

    return font_name


def _find_system_font_file(font_name: str, font_style: str = "Regular") -> tuple:
    """
    Busca el archivo de fuente en los directorios del sistema (macOS y Windows).
    Para archivos TTC (TrueType Collection), determina el índice correcto de la variante.

    Args:
        font_name: Nombre de la familia (ej: "Helvetica Neue")
        font_style: Estilo buscado (ej: "Bold", "Italic", "Bold Italic", "Regular")

    Returns:
        tuple: (font_path, font_index) donde font_index es para archivos TTC
               (None, 0) si no se encuentra
    """
    import os
    import sys

    # First: attempt to use CoreText / platform index helper to directly find font
    p = None
    p_idx = 0
    try:
        # Wrapper (con gestor_fuentes) en vez del módulo base: conoce fuentes
        # activadas por gestores externos (RightFont) y alias "Extended".
        from utils import font_index_wrapper as font_index

        p, status = font_index.find_font_file_for(font_name, font_style)
        if p:
            # Prepare to validate whether the found path actually matches the requested style
            style_lower = font_style.lower().replace(" ", "")
            matched_style = False
            # If TTC, attempt to determine index and inspect subfont
            if p.lower().endswith(".ttc"):
                try:
                    p_idx = _determine_ttc_index(p, font_style)
                    # Inspect TTC subfont name/subfamily if fontTools available
                    try:
                        from fontTools.ttLib import TTCollection

                        ttc = TTCollection(p)
                        if 0 <= p_idx < len(ttc):
                            font = ttc[p_idx]
                            name_table = font["name"]
                            subfamily = None
                            for record in name_table.names:
                                try:
                                    if record.nameID == 2:
                                        subfamily = record.toUnicode()
                                        break
                                except Exception:
                                    pass
                            if subfamily and style_lower in subfamily.lower().replace(
                                " ", ""
                            ):
                                matched_style = True
                    except Exception:
                        pass
                except Exception:
                    p_idx = 0
            else:
                # TTF/OTF: inspect name table for Subfamily (nameID 2)
                try:
                    from fontTools.ttLib import TTFont

                    tt = TTFont(p, lazy=True)
                    name_table = tt["name"]
                    subfamily = None
                    for record in name_table.names:
                        try:
                            if record.nameID == 2:
                                subfamily = record.toUnicode()
                                break
                        except Exception:
                            pass
                    try:
                        tt.close()
                    except Exception:
                        pass
                    if subfamily and style_lower in subfamily.lower().replace(" ", ""):
                        matched_style = True
                except Exception:
                    matched_style = False

            # If the indexed path seems to match the requested style, return it
            if matched_style:
                print(
                    f"[FONT SEARCH][CORETEXT] Found via index and style matched: {p} (status: {status})"
                )
                return (p, p_idx)
            else:
                # Keep as fallback, but continue scanning directories to find a better match
                print(
                    f"[FONT SEARCH][CORETEXT] Found via index: {p} (status: {status}) - style not confirmed, searching disk for better match"
                )
    except Exception:
        # ignore and continue to scanning directories
        p = None
        p_idx = 0

    # Determinar directorios de fuentes según plataforma
    if sys.platform == "darwin":  # macOS
        font_dirs = [
            os.path.expanduser("~/Library/Fonts"),
            "/Library/Fonts",
            "/System/Library/Fonts",
            "/System/Library/Fonts/Supplemental",
        ]
    elif sys.platform == "win32":  # Windows
        font_dirs = [
            os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts"),
            os.path.join(
                os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Windows", "Fonts"
            ),
        ]
    else:
        font_dirs = [
            os.path.expanduser("~/.local/share/fonts"),
            os.path.expanduser("~/.fonts"),
            "/usr/share/fonts",
            "/usr/local/share/fonts",
        ]

    # Normalizar nombre de familia buscado
    target_family = font_name.lower().replace(" ", "").replace("-", "")
    # Además obtener tokens individuales (ej: 'comic', 'sans', 'ms') para coincidencias más flexibles
    import re

    family_tokens = [t for t in re.split(r"[\s\-]+", font_name.lower()) if t]

    # Normalizar estilo buscado
    style_lower = font_style.lower().replace(" ", "")
    style_tokens = [t for t in re.split(r"[\s\-]+", font_style.lower()) if t]

    # Mapeo de estilos comunes
    style_keywords = {
        "regular": ["regular", "roman", "book", "normal", "medium"],
        "bold": ["bold", "black", "heavy", "semibold", "demibold"],
        "italic": ["italic", "oblique", "slanted"],
        "bolditalic": ["bolditalic", "boldoblique", "blackitalic", "bi", "z"],
    }

    # Determinar keywords a buscar
    search_keywords = style_keywords.get(style_lower, [style_lower])
    if style_lower == "bolditalic":
        search_keywords = ["bolditalic", "boldoblique", "blackitalic"]
    elif style_lower not in style_keywords and style_tokens:
        # Añadir tokens individuales para estilos compuestos (ej: "Light Oblique")
        search_keywords = list(dict.fromkeys([style_lower] + style_tokens))

    # Extensiones a buscar
    extensions = [".ttf", ".otf", ".ttc"]

    print(
        f"[FONT SEARCH] Buscando '{font_name}' estilo '{font_style}' (target: '{target_family}', keywords: {search_keywords})"
    )

    candidates = []  # Lista de (path, score, is_ttc)

    for folder in font_dirs:
        if not os.path.exists(folder):
            continue

        try:
            for filename in os.listdir(folder):
                if filename.startswith("."):
                    continue

                ext = os.path.splitext(filename)[1].lower()
                if ext not in extensions:
                    continue

                # Normalizar nombre de archivo
                fname_lower = filename.lower().replace(" ", "").replace("-", "")
                fname_base = os.path.splitext(fname_lower)[0]

                # Verificar si contiene alguno de los tokens de la familia (o prefijo para abreviaturas)
                # Permite "cour" para "courier" (mínimo 4 caracteres para evitar falsos positivos)
                def token_matches(fname, tokens):
                    for tok in tokens:
                        # Match exacto o prefijo significativo (≥4 chars)
                        if tok in fname:
                            return True
                        if len(tok) >= 4 and fname.startswith(tok[:4]):
                            return True
                    return False

                if not token_matches(fname_lower, family_tokens):
                    continue

                full_path = os.path.join(folder, filename)
                is_ttc = ext == ".ttc"

                # Calcular score de coincidencia de estilo
                score = 0

                # SCORING PRIMARIO: Coincidencia con tokens de familia (muy importante)
                # Tokens largos (>2 chars) son más significativos que tokens cortos como "ms"
                significant_tokens = [t for t in family_tokens if len(t) > 2]
                generic_tokens = [t for t in family_tokens if len(t) <= 2]

                # Dar score por coincidencias exactas y prefijos (para abreviaturas Windows)
                matched_significant = 0
                for tok in significant_tokens:
                    if tok in fname_lower:
                        matched_significant += 100  # Match exacto
                    elif len(tok) >= 4 and fname_lower.startswith(tok[:4]):
                        matched_significant += 80  # Prefijo (ej: "cour" para "courier")

                matched_generic = sum(
                    10 for tok in generic_tokens if tok in fname_lower
                )
                score += matched_significant + matched_generic

                # Si no hay ninguna coincidencia significativa (ni exacta ni prefijo),
                # descartar el candidato: los tokens genéricos de 1-2 chars ("b")
                # aceptan cualquier archivo (p. ej. KohinoorBangla para OCR-B).
                has_significant_match = any(
                    tok in fname_lower
                    or (len(tok) >= 4 and fname_lower.startswith(tok[:4]))
                    for tok in significant_tokens
                )
                if significant_tokens and not has_significant_match:
                    continue

                # Heurística Windows: priorizar sufijos típicos (ariali.ttf, arialbi.ttf, etc.)
                if sys.platform == "win32":
                    style_suffix_map = {
                        "regular": ["", "r"],
                        "bold": ["b", "bd", "bold"],
                        "italic": ["i", "it", "italic"],
                        "bolditalic": [
                            "bi",
                            "z",
                            "bolditalic",
                            "boldit",
                            "boldoblique",
                        ],
                    }
                    suffixes = style_suffix_map.get(style_lower, [])
                    for suf in suffixes:
                        if suf == "":
                            # archivo exactamente igual al nombre de la familia
                            if fname_base == target_family:
                                score += 40
                        else:
                            if fname_base.endswith(target_family + suf):
                                score += 50
                            elif fname_base.endswith(suf):
                                score += 30

                # Score por keywords
                for kw in search_keywords:
                    if kw in fname_base:
                        score += 10

                # Si es TTC, añadir pequeño bonus (reducido de 5 a 2)
                if is_ttc:
                    score += 2

                # Penalizaciones por estilos no deseados
                if style_lower == "regular":
                    if (
                        "bold" in fname_base
                        or "italic" in fname_base
                        or "oblique" in fname_base
                    ):
                        score -= 20
                elif style_lower == "bold":
                    if (
                        "italic" in fname_base or "oblique" in fname_base
                    ) and "bold" not in fname_base:
                        score -= 15
                elif style_lower == "italic":
                    if "bold" in fname_base:
                        score -= 15

                candidates.append((full_path, score, is_ttc))
                print(
                    f"[FONT SEARCH] Candidato: {filename} (score: {score}, ttc: {is_ttc})"
                )

        except Exception as e:
            if _PRINT_DEBUG:
                print(f"[WARN] Error escaneando {folder}: {e}")
            continue

    if not candidates:
        builtins.print(f"[FONT SEARCH] No se encontró archivo para: {font_name} {font_style}")
        # If we had a fallback from the platform index, return it
        if p:
            builtins.print(f"[FONT SEARCH] Usando fallback (index result): {p} (idx: {p_idx})")
            return (p, p_idx)
        return (None, 0)

    # Ordenar por score (mayor primero)
    candidates.sort(key=lambda x: x[1], reverse=True)

    # Intentar encontrar entre los candidatos uno cuya tabla 'name' (subfamily) coincida con el estilo
    from fontTools.ttLib import TTFont, TTCollection

    selected = None
    for full_path, score, is_ttc in candidates:
        try:
            if is_ttc:
                # Determinar índice y revisar subfamily
                idx = _get_ttc_font_index(full_path, font_style)
                try:
                    ttc = TTCollection(full_path)
                    if 0 <= idx < len(ttc):
                        font = ttc[idx]
                        name_table = font["name"]
                        subfamily = None
                        for record in name_table.names:
                            try:
                                if record.nameID == 2:
                                    subfamily = record.toUnicode()
                                    break
                            except Exception:
                                pass
                        if subfamily and style_lower in (
                            subfamily or ""
                        ).lower().replace(" ", ""):
                            selected = (full_path, idx)
                            print(
                                f"[FONT SEARCH] Seleccionado por subfamily TTC: {full_path} idx={idx} (score {score})"
                            )
                            break
                except Exception:
                    pass
            else:
                # TTF/OTF: revisar name table
                try:
                    tt = TTFont(full_path, lazy=True)
                    name_table = tt["name"]
                    subfamily = None
                    for record in name_table.names:
                        try:
                            if record.nameID == 2:
                                subfamily = record.toUnicode()
                                break
                        except Exception:
                            pass
                    try:
                        tt.close()
                    except Exception:
                        pass
                    if subfamily and style_lower in subfamily.lower().replace(" ", ""):
                        selected = (full_path, 0)
                        print(
                            f"[FONT SEARCH] Seleccionado por subfamily: {full_path} (score {score})"
                        )
                        break
                except Exception:
                    pass
        except Exception:
            continue

    if selected:
        return selected

    # Si no encontramos por subfamily, intentar heurística para estilos compuestos (Bold Italic)
    try:
        if "bold" in style_lower and "italic" in style_lower:
            # Preferir candidatos que indiquen 'bi'/'z'/'italic' en filename
            for full_path, score, is_ttc in candidates:
                fname_base = os.path.splitext(os.path.basename(full_path).lower())[0]
                if any(
                    tok in fname_base
                    for tok in ("bi", "z", "bolditalic", "boldit", "boldoblique", "ib")
                ):
                    if is_ttc:
                        idx = _get_ttc_font_index(full_path, font_style)
                        return (full_path, idx)
                    else:
                        return (full_path, 0)
            # Fallback: prefer italic candidates (contain 'i' or 'it' tokens)
            for full_path, score, is_ttc in candidates:
                fname_base = os.path.splitext(os.path.basename(full_path).lower())[0]
                if any(tok in fname_base for tok in ("it", "i", "italic", "oblique")):
                    if is_ttc:
                        idx = _get_ttc_font_index(full_path, font_style)
                        return (full_path, idx)
                    else:
                        return (full_path, 0)
            # Else prefer bold candidates
            for full_path, score, is_ttc in candidates:
                fname_base = os.path.splitext(os.path.basename(full_path).lower())[0]
                if any(tok in fname_base for tok in ("bd", "b", "bold")):
                    if is_ttc:
                        idx = _get_ttc_font_index(full_path, font_style)
                        return (full_path, idx)
                    else:
                        return (full_path, 0)
    except Exception:
        pass

    # Tomar el mejor candidato (fallback)
    best_path, best_score, is_ttc = candidates[0]
    print(f"[FONT SEARCH] Mejor candidato: {best_path} (score: {best_score})")

    # Si es TTC, buscar el índice correcto de la variante
    if is_ttc:
        font_index = _get_ttc_font_index(best_path, font_style)
        return (best_path, font_index)
    return (best_path, 0)

    return (best_path, 0)


def _get_ttc_font_index(ttc_path: str, font_style: str) -> int:
    try:
        from . import font_ttc

        return font_ttc.determine_ttc_index(ttc_path, font_style)
    except Exception as e:
        builtins.print(f"[TTC ERROR] Delegation failed: {e}")
        return 0


def _determine_ttc_index(ttc_path: str, font_style: str) -> int:
    try:
        from . import font_ttc

        return font_ttc.determine_ttc_index(ttc_path, font_style)
    except Exception as e:
        builtins.print(f"[TTC ERROR] Delegation failed: {e}")
        return 0


def _extract_font_from_ttc(ttc_path: str, font_index: int) -> Optional[bytes]:
    try:
        from . import font_ttc

        return font_ttc.extract_subfont_bytes(ttc_path, font_index)
    except Exception as e:
        builtins.print(f"[TTC EXTRACT ERROR] Delegation failed: {e}")
        return None


def register_font_file(font_name: str, font_style: str, font_path: str) -> None:
    """Register an externally assigned font file for immediate use in the session.

    This creates an entry in the FONT_CACHE so subsequent PDF generation can embed it.
    """
    try:
        key = _font_cache_key(font_name, font_style)
        try:
            font_obj = fitz.Font(fontfile=font_path)
        except Exception as e:
            builtins.print(f"[FONT REGISTER] Error creating fitz.Font: {e}")
            font_obj = None
        safe_name = (
            os.path.splitext(os.path.basename(font_path))[0].replace(" ", "")
            + "_assigned"
        )
        FONT_CACHE[key] = {
            "fitz_name": safe_name,
            "font_obj": font_obj,
            "fontfile": font_path,
        }
        print(
            f"[FONT REGISTER] Registered assigned font {font_name}/{font_style} -> {font_path}"
        )
    except Exception as ex:
        builtins.print(f"[FONT REGISTER] Failed to register font: {ex}")


# ══════════════════════════════════════════════════════════════════════════════
# BACKGROUND IMAGE/PDF
# ══════════════════════════════════════════════════════════════════════════════


def add_background_to_page(
    page: fitz.Page,
    image_config: Dict,
    page_width_mm: float,
    page_height_mm: float,
    bleed_mm: float,
    bg_pdf_doc: Optional[fitz.Document] = None,
) -> None:
    """
    Agrega imagen o PDF de fondo a la página.

    Args:
        page: Página de fitz donde agregar el fondo
        image_config: Configuración de la imagen de fondo:
            - image_path: str (ruta al archivo)
            - align_to: "physical" | "printable"
            - alignment_position: str (center, top_left, etc.)
            - offset_horizontal: float (en mm)
            - offset_vertical: float (en mm)
            - tile_enabled: bool
            - tiles_across: int
            - tiles_down: int
            - rotation: int (0, 90, 180, 270)
            - opacity: float (0.0-1.0)
        page_width_mm: Ancho de página sin bleed
        page_height_mm: Alto de página sin bleed
        bleed_mm: Sangre en mm
        bg_pdf_doc: Documento PDF ya abierto (para reutilizar y evitar abrir/cerrar múltiples veces)
    """
    if not image_config or "image_path" not in image_config:
        if _PRINT_DEBUG:
            print(
                f"[BG TRACE] add_background_to_page -> SKIP (sin config válida). image_config={bool(image_config)}"
            )
        return

    image_path = image_config["image_path"]
    if _PRINT_DEBUG:
        print(
            f"[BG TRACE] add_background_to_page -> config recibida. image_path='{image_path}'"
        )

    if not image_path:
        if _PRINT_DEBUG:
            print("[BG TRACE] add_background_to_page -> SKIP (image_path vacío)")
        return

    if not os.path.exists(image_path):
        builtins.print(f"[WARN] Archivo de fondo no encontrado: {image_path}")
        if _PRINT_DEBUG:
            print("[BG TRACE] add_background_to_page -> SKIP (archivo inexistente)")
        return

    # Determinar si es PDF o imagen
    is_pdf = image_path.lower().endswith(".pdf")
    if _PRINT_DEBUG:
        print(
            f"[BG TRACE] add_background_to_page -> APPLY ({'PDF' if is_pdf else 'IMAGE'})"
        )

    # Extraer configuración
    align_to = image_config.get("align_to", "physical")
    alignment_position = image_config.get("alignment_position", "center")
    offset_h_mm = image_config.get("offset_horizontal", 0.0)
    offset_v_mm = image_config.get("offset_vertical", 0.0)
    tile_enabled = image_config.get("tile_enabled", False)
    tiles_across = image_config.get("tiles_across", 1)
    tiles_down = image_config.get("tiles_down", 1)
    rotation = image_config.get("rotation", 0)
    opacity = image_config.get("opacity", 1.0)

    # Extraer configuración de escala
    scale_percentage = image_config.get("scale", 100.0)
    auto_fit = image_config.get("auto_fit", False)
    use_custom_size = image_config.get("use_custom_size", False)
    custom_width_mm = image_config.get("custom_width", 210.0)
    custom_height_mm = image_config.get("custom_height", 297.0)

    # Calcular área de referencia según align_to
    if align_to == "printable":
        # Área sin bleed (TrimBox)
        ref_x = mm_to_pt(bleed_mm)
        ref_y = mm_to_pt(bleed_mm)
        ref_width = mm_to_pt(page_width_mm)
        ref_height = mm_to_pt(page_height_mm)
    else:  # "physical"
        # Área completa con bleed (MediaBox)
        ref_x = 0
        ref_y = 0
        ref_width = mm_to_pt(page_width_mm + bleed_mm * 2)
        ref_height = mm_to_pt(page_height_mm + bleed_mm * 2)

    # IMPORTANTE: Calcular dimensiones objetivo con escala
    # Definir función auxiliar para calcular dimensiones
    def get_target_dimensions(orig_w_pt, orig_h_pt):
        # Determinar dimensiones efectivas según rotación
        is_rotated = rotation in [90, 270]

        # Dimensiones para calcular el ajuste (si está rotado, intercambiamos)
        calc_w = orig_h_pt if is_rotated else orig_w_pt
        calc_h = orig_w_pt if is_rotated else orig_h_pt

        if use_custom_size:
            # Tamaño personalizado directo (en mm, convertir a pt)
            # El usuario siempre especifica ancho/alto VISUALES
            return mm_to_pt(custom_width_mm), mm_to_pt(custom_height_mm)

        elif auto_fit:
            # Ajustar a la página (ref_width/ref_height)
            ratio_w = ref_width / calc_w if calc_w > 0 else 1.0
            ratio_h = ref_height / calc_h if calc_h > 0 else 1.0
            scale_factor = min(ratio_w, ratio_h)
        else:
            # Escala manual por porcentaje
            scale_factor = scale_percentage / 100.0

        # Calcular dimensiones finales del RECTÁNGULO DE DESTINO
        # Si está rotado, el ancho del rect será la altura original escalada
        final_w = calc_w * scale_factor
        final_h = calc_h * scale_factor

        return final_w, final_h

    if is_pdf:
        # Usar documento PDF ya abierto si se proporcionó, sino abrirlo
        if bg_pdf_doc is not None:
            src_doc = bg_pdf_doc
            should_close = False
        else:
            src_doc = fitz.open(image_path)
            should_close = True

        # Obtener el índice de página seleccionado por el usuario (guardado en config como "page")
        pdf_page_idx = image_config.get("page", 0)
        # Asegurar que el índice sea válido para el documento
        num_pages = len(src_doc)
        if pdf_page_idx < 0 or pdf_page_idx >= num_pages:
            pdf_page_idx = 0

        src_page = src_doc[pdf_page_idx]

        # Tamaño de la página fuente (MediaBox)
        media_rect = src_page.rect

        # Calcular dimensiones objetivo usando SIEMPRE la escala (o custom size convertida a escala)
        # La UI ya se encarga de calcular el porcentaje correcto para "Auto-Fit" o "Custom Size"
        # y nos lo pasa en 'scale_percentage'.
        # Aplicamos esa escala al MediaBox completo para mantener la consistencia.

        scale_factor = scale_percentage / 100.0

        # Aplicar escala
        target_w = media_rect.width * scale_factor
        target_h = media_rect.height * scale_factor

        # Si hay rotación de 90/270, intercambiamos dimensiones del RECTÁNGULO DE DESTINO
        # para que la imagen rotada quepa correctamente
        if rotation in [90, 270]:
            target_w, target_h = target_h, target_w

        # Calcular rectángulo de destino
        # Esto centrará el MediaBox escalado en la posición deseada
        dest_rect = _calculate_image_rect(
            ref_x,
            ref_y,
            ref_width,
            ref_height,
            target_w,
            target_h,
            alignment_position,
            offset_h_mm,
            offset_v_mm,
            tile_enabled,
            tiles_across,
            tiles_down,
        )

        # Insertar PDF usando show_pdf_page
        # IMPORTANTE: PyMuPDF usa rotación antihoraria, UI usa horaria
        # Invertir rotación: UI 90° (derecha) → PDF -90° (horaria en sistema antihorario)
        page.show_pdf_page(
            dest_rect,
            src_doc,
            pdf_page_idx,  # Número de página seleccionado por el usuario
            keep_proportion=True,
            overlay=False,
            rotate=-rotation,  # Invertir rotación
            clip=None,
        )

        # Solo cerrar si abrimos el documento en esta función
        if should_close:
            src_doc.close()
    else:
        # Cargar imagen
        img = fitz.Pixmap(image_path)

        # Calcular dimensiones escaladas
        target_w, target_h = get_target_dimensions(img.width, img.height)

        # Calcular rectángulo de destino
        dest_rect = _calculate_image_rect(
            ref_x,
            ref_y,
            ref_width,
            ref_height,
            target_w,
            target_h,
            alignment_position,
            offset_h_mm,
            offset_v_mm,
            tile_enabled,
            tiles_across,
            tiles_down,
        )

        # Insertar imagen
        # IMPORTANTE: PyMuPDF usa rotación antihoraria, UI usa horaria
        # Invertir rotación: UI 90° (derecha) → PDF -90° (horaria en sistema antihorario)
        page.insert_image(
            dest_rect,
            pixmap=img,
            overlay=False,  # Fondo, no overlay
            rotate=-rotation,  # Invertir rotación
            keep_proportion=True,
        )


def _calculate_image_rect(
    ref_x: float,
    ref_y: float,
    ref_width: float,
    ref_height: float,
    img_width: float,
    img_height: float,
    alignment: str,
    offset_h_mm: float,
    offset_v_mm: float,
    tile_enabled: bool,
    tiles_across: int,
    tiles_down: int,
) -> fitz.Rect:
    """
    Calcula el rectángulo donde colocar la imagen según alignment y offsets.
    Todos los parámetros en puntos excepto offsets (en mm).
    """
    # Convertir offsets a puntos
    offset_h_pt = mm_to_pt(offset_h_mm)
    offset_v_pt = mm_to_pt(offset_v_mm)

    # Si tile está habilitado, ajustar tamaño de imagen
    if tile_enabled:
        img_width = ref_width / tiles_across
        img_height = ref_height / tiles_down

    # Calcular posición según alignment
    # Alignment positions: center, top_left, top_center, top_right,
    #                      middle_left, middle_right,
    #                      bottom_left, bottom_center, bottom_right

    if alignment == "center":
        x = ref_x + (ref_width - img_width) / 2
        y = ref_y + (ref_height - img_height) / 2
    elif alignment == "top_left":
        x = ref_x
        y = ref_y
    elif alignment == "top_center":
        x = ref_x + (ref_width - img_width) / 2
        y = ref_y
    elif alignment == "top_right":
        x = ref_x + ref_width - img_width
        y = ref_y
    elif alignment == "middle_left":
        x = ref_x
        y = ref_y + (ref_height - img_height) / 2
    elif alignment == "middle_right":
        x = ref_x + ref_width - img_width
        y = ref_y + (ref_height - img_height) / 2
    elif alignment == "bottom_left":
        x = ref_x
        y = ref_y + ref_height - img_height
    elif alignment == "bottom_center":
        x = ref_x + (ref_width - img_width) / 2
        y = ref_y + ref_height - img_height
    elif alignment == "bottom_right":
        x = ref_x + ref_width - img_width
        y = ref_y + ref_height - img_height
    else:  # default: center
        x = ref_x + (ref_width - img_width) / 2
        y = ref_y + (ref_height - img_height) / 2

    # Aplicar offsets
    x += offset_h_pt
    y += offset_v_pt

    return fitz.Rect(x, y, x + img_width, y + img_height)


# ══════════════════════════════════════════════════════════════════════════════
# GENERACIÓN PRINCIPAL DE PDF
# ══════════════════════════════════════════════════════════════════════════════


def _subset_one_batch(bp: str) -> str:
    """Subset de fuentes de un lote. Un Document propio por llamada (hilo).

    Si falla, el fichero queda intacto para que el llamador aplique el
    subset final clásico como red de seguridad.
    """
    import time as _time

    _t0 = _time.monotonic()
    bdoc = fitz.open(bp)
    try:
        bdoc.subset_fonts()
        # Rápido: sin garbage ni deflate (el save final ya compacta).
        _tmp = bp + ".subset.tmp"
        bdoc.save(_tmp, garbage=0, deflate=False, clean=False)
    finally:
        bdoc.close()
    os.replace(_tmp, bp)
    return f"{os.path.basename(bp)}: {_time.monotonic() - _t0:.2f}s"


def _subset_batches_parallel(batch_files: list, progress=None) -> None:
    """Subset de cada lote en PROCESOS (1 lote → directo, sin pool).

    Hilos NO paralelizan aquí (MuPDF no suelta el GIL): 15 lotes salían
    en serie (~105s). Procesos → ~15-25s reales.
    progress(k, -n) tras cada lote: current=-3 (negativo → la UI pinta solo
    label+barra animada, SIN contador de lotes que el usuario no entiende)
    + checkpoint de cancelación (si no, imposible cancelar el subset).
    Propaga la excepción del primer lote (el llamador usa el subset final
    clásico como red de seguridad salvo cancelación).
    """
    n = len(batch_files)
    if n == 1:
        if progress:
            progress(-3, -1)
        if _PRINT_DEBUG:
            print(f"[BATCH] Subset lote único: {_subset_one_batch(batch_files[0])}")
        else:
            _subset_one_batch(batch_files[0])
        if progress:
            progress(-3, -1)
        return
    import concurrent.futures as _cf

    if progress:
        progress(-3, -n)
    workers = min(n, os.cpu_count() or 4)
    _ex = _cf.ProcessPoolExecutor(max_workers=workers)
    try:
        for _r in _ex.map(_subset_one_batch, batch_files):
            if progress:
                progress(-3, -n)
            if _PRINT_DEBUG:
                print(f"[BATCH] Subset listo ({_r})")
    except BaseException:
        # Cancel/error: no esperar a los lotes en curso (wait=False) o el
        # diálogo se colgaría justo al pulsar Cancelar.
        _ex.shutdown(wait=False, cancel_futures=True)
        raise
    else:
        _ex.shutdown(wait=True)


def generar_pdf_numerado(
    output_path: str,
    start_page: int,
    end_page: int,
    page_width_mm: float,
    page_height_mm: float,
    bleed_mm: float,
    double_sided: bool,
    cara_settings: Dict,
    dorso_settings: Dict,
    cara_positions: Dict,
    dorso_positions: Dict,
    text_style_manager,
    cara_background: Optional[Dict] = None,
    dorso_background: Optional[Dict] = None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    save_opts_final: Optional[Dict] = None,
    use_copy_grouping: bool = True,
    enable_subset_fonts: bool = True,
    copies: int = 1,
) -> str:
    """
    Genera el PDF numerado final.

    Args:
        output_path: Ruta donde guardar el PDF
        start_page: Página inicial (1-based)
        end_page: Página final (1-based)
        page_width_mm: Ancho de página sin bleed
        page_height_mm: Alto de página sin bleed
        bleed_mm: Sangre en mm
        double_sided: Si True, genera páginas intercaladas cara-dorso
        cara_settings: Dict con configuración global de CARA:
            - start: número inicial
            - increment: incremento entre números
            - copies: copias por número
            - reverse: si True, invertir orden
        dorso_settings: Dict con configuración global de DORSO (si double_sided)
        cara_positions: Dict de posiciones (numeradoras) de CARA {id: data}
        dorso_positions: Dict de posiciones de DORSO (si double_sided)
        text_style_manager: Gestor de estilos de texto (para obtener perfiles)
        cara_background: Config de imagen de fondo para CARA (opcional)
        dorso_background: Config de imagen de fondo para DORSO (opcional)
        progress_callback: Callback(current, total) para progreso (opcional)
        use_copy_grouping: Si True, la numeración usa 'copies' para repetir
            números por grupo (comportamiento histórico). Si False, cada
            page_num lógico avanza el número sin agrupar por copias.
        enable_subset_fonts: Si True, optimiza las fuentes (solo glifos usados)
            antes del guardado final para reducir el tamaño del PDF.
        copies: FUSIÓN — nº de copias físicas emitidas AL CREAR cada lógico
            (simplex: página ×N; duplex: par cara+dorso ×N → c,d,c,d...).
            Sustituye la antigua Phase 2 (merge_pdfs). El rango start/end son
            páginas LÓGICAS (el caller convierte el visible).

    Returns:
        Ruta del archivo generado

    Raises:
        InterruptedError: Si se cancela desde progress_callback
        Exception: Si hay error en la generación
    """
    print(f"\n{'='*80}")
    print(f"GENERANDO PDF NUMERADO")
    print(f"{'='*80}")
    print(f"Rango: {start_page} - {end_page}")
    print(f"Tamaño: {page_width_mm} × {page_height_mm} mm + {bleed_mm} mm sangre")
    print(f"Doble cara: {double_sided}")
    print(f"Posiciones CARA: {len(cara_positions)}")
    if _PRINT_DEBUG:
        print(
            f"[BG TRACE] generar_pdf_numerado -> entrada fondos: CARA={bool(cara_background)} DORSO={bool(dorso_background)}"
        )
    if double_sided:
        print(f"Posiciones DORSO: {len(dorso_positions)}")
    print(f"{'='*80}\n")

    # ═══════════════════════════════════════════════════════════════════════════
    # CARPETA TEMPORAL PARA LOTES
    # ═══════════════════════════════════════════════════════════════════════════
    # Se elimina al inicio (limpia restos de ejecuciones fallidas anteriores)
    # y al final (una vez copiado el PDF definitivo).
    BATCH_SIZE = 200  # páginas FÍSICAS por lote (con copies ya multiplicadas)
    copies = max(1, int(copies))
    # Opciones de guardado para reducir tamaño final sin perder contenido.
    SAVE_OPTS_BATCH = dict(garbage=0, deflate=False, clean=False)
    SAVE_OPTS_FINAL_DEFAULT = dict(garbage=4, deflate=True, clean=False, use_objstms=1)
    SAVE_OPTS_FINAL = save_opts_final or SAVE_OPTS_FINAL_DEFAULT
    output_existed_before = os.path.exists(output_path)
    final_saved = False
    doc_final = None
    temp_dir = get_config_dir() / "pdf_temp"
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
        if _PRINT_DEBUG:
            print(f"[BATCH] Carpeta temporal previa eliminada: {temp_dir}")
    temp_dir.mkdir(parents=True, exist_ok=True)
    if _PRINT_DEBUG:
        print(f"[BATCH] Carpeta temporal creada: {temp_dir}")

    batch_files: list = []
    batch_num = 0
    doc = fitz.open()  # batch: destino de los inserts ×copies (lote actual)
    src = fitz.open()  # tramo: render de lógicos; CONGELADO durante inserts
    if _PRINT_DEBUG:
        print(f"[BATCH] Generación por lotes de {BATCH_SIZE} págs físicas en {temp_dir}")

    # Abrir PDFs de fondo UNA SOLA VEZ para reutilizarlos (evita abrir/cerrar 1000+ veces)
    cara_bg_doc = None
    dorso_bg_doc = None

    try:
        # Abrir PDFs de fondo UNA SOLA VEZ para reutilizarlos en el bucle.
        # Si no se reutiliza, add_background_to_page abre/cierra el PDF por página
        # y PyMuPDF re-embebe la imagen del fondo en cada página → PDF gigante.
        def _get_bg_path(cfg):
            if not cfg:
                return ""
            src = cfg.get("image_path") or cfg.get("path") or ""
            # Preferir el PDF temporal optimizado (página ya extraída) si existe
            return cfg.get("pdf_temp_path") or src

        def _open_bg_doc(cfg):
            p = _get_bg_path(cfg)
            if p.lower().endswith(".pdf") and os.path.exists(p):
                return fitz.open(p)
            return None

        if cara_background:
            cara_bg_path = _get_bg_path(cara_background)
            if cara_bg_path.lower().endswith(".pdf") and os.path.exists(
                cara_bg_path
            ):
                cara_bg_doc = _open_bg_doc(cara_background)
                if _PRINT_DEBUG:
                    print(f"[BATCH] PDF de fondo cara abierto: {cara_bg_path}")
        if double_sided and dorso_background:
            dorso_bg_path = _get_bg_path(dorso_background)
            if dorso_bg_path.lower().endswith(".pdf") and os.path.exists(
                dorso_bg_path
            ):
                dorso_bg_doc = _open_bg_doc(dorso_background)
                if _PRINT_DEBUG:
                    print(f"[BATCH] PDF de fondo dorso abierto: {dorso_bg_path}")

        # Calcular total de páginas FÍSICAS a emitir (lógicos × caras × copies)
        num_pages = end_page - start_page + 1
        faces = 2 if double_sided else 1
        total_pdf_pages = num_pages * faces * copies
        # Lógicos por tramo: src se renderiza entero y se congela antes de
        # insertar ×copies (modificar src tras insertarlo rompe el Graftmap:
        # "source object number out of range" — comprobado en sonda).
        logicals_per_tramo = max(1, math.ceil(BATCH_SIZE / (copies * faces)))

        # Tamaño de página con bleed
        page_width_with_bleed = page_width_mm + (bleed_mm * 2)
        page_height_with_bleed = page_height_mm + (bleed_mm * 2)

        current_pdf_page = 0
        cancelled_by_user = False
        tramo_pages: list = []  # (lo,hi) de lógicos renderizados pendientes de insertar

        import time as _time

        _t_mark = _time.monotonic()

        # Generar páginas
        for page_num in range(start_page, end_page + 1):
            # ═══════════════════════════════════════════════════════════════════
            # PÁGINA CARA (render en src; la emisión ×copies va al final del lógico)
            # ═══════════════════════════════════════════════════════════════════
            # Crear página
            lo_idx = src.page_count
            pdf_page = src.new_page(
                width=mm_to_pt(page_width_with_bleed),
                height=mm_to_pt(page_height_with_bleed),
            )

            # Definir cajas PDF
            set_pdf_boxes(pdf_page, page_width_mm, page_height_mm, bleed_mm)

            # Agregar background si existe
            if cara_background:
                if _PRINT_DEBUG:
                    print(
                        f"[BG TRACE] página lógica {page_num} CARA -> llamando add_background_to_page"
                    )
                add_background_to_page(
                    pdf_page,
                    cara_background,
                    page_width_mm,
                    page_height_mm,
                    bleed_mm,
                    cara_bg_doc,  # Pasar documento ya abierto
                )
            else:
                if _PRINT_DEBUG:
                    print(
                        f"[BG TRACE] página lógica {page_num} CARA -> sin fondo (salta add_background_to_page)"
                    )

            # Renderizar posiciones de CARA - barcodes primero (capa inferior)
            for num_id, pos_data in cara_positions.items():
                pos_type = pos_data.get("type", "number")
                _debug_y(
                    f"[CARA loop] page={page_num} pos={num_id} type={pos_type} x={pos_data.get('x',0)} y={pos_data.get('y',0)}"
                )
                if pos_type == "barcode":
                    barcode_data = pos_data
                    if pos_data.get("value_source", "fixed") == "numbering":
                        # Para códigos con numeración interna, recalcular valor por página
                        # durante exportación PDF (no depender del valor estático de UI).
                        raw_barcode_number = _calculate_number_for_page(
                            page_num,
                            cara_settings,
                            pos_data,
                            use_copy_grouping=use_copy_grouping,
                        )
                        mask = pos_data.get("mask", "")
                        barcode_value = apply_mask_format(
                            raw_barcode_number, mask, "normal"
                        )
                        barcode_data = dict(pos_data)
                        barcode_data["barcode_value"] = barcode_value
                    elif pos_data.get("value_source", "fixed") == "excel":
                        excel_column = pos_data.get("excel_column", "")
                        if excel_column:
                            em = ExcelManager()
                            if em.is_loaded:
                                phys_page = page_num
                                start = cara_settings.get("start", 1)
                                end = cara_settings.get("end", 1000)
                                increment = cara_settings.get("increment", 1)
                                copies = cara_settings.get("copies", 1)
                                reverse = cara_settings.get("reverse", False)
                                row_index = excel_row_index(
                                    start,
                                    end,
                                    increment,
                                    copies,
                                    reverse,
                                    phys_page,
                                    use_copy_grouping=use_copy_grouping,
                                )
                                value = em.get_value_at(excel_column, row_index)
                                if value:
                                    barcode_data = dict(pos_data)
                                    barcode_data["barcode_value"] = value
                    elif pos_data.get("value_source", "fixed") == "fixed":
                        # VT personalizado: plantilla con <@<col>@> para QR/PDF417/DM
                        tmpl = pos_data.get("sample_value", "")
                        symb = pos_data.get("symbology", "")
                        if "<@<" in tmpl and symb in ("qr", "pdf417", "datamatrix"):
                            from utils.excel_manager import ExcelManager as _EMvt
                            em = _EMvt()
                            if em.is_loaded:
                                phys_page = page_num
                                start = cara_settings.get("start", 1)
                                end = cara_settings.get("end", 1000)
                                increment = cara_settings.get("increment", 1)
                                copies = cara_settings.get("copies", 1)
                                reverse = cara_settings.get("reverse", False)
                                row_index = excel_row_index(
                                    start, end, increment, copies, reverse, phys_page, use_copy_grouping=use_copy_grouping,
                                )

                                def _repl(m):
                                    col = m.group(1).strip()
                                    try:
                                        return em.get_value_at(col, row_index) or ""
                                    except Exception:
                                        return ""

                                resolved = re.sub(r"<@<([^>]+)>@>", _repl, tmpl)
                                barcode_data = dict(pos_data)
                                barcode_data["barcode_value"] = resolved

                    render_barcode_to_pdf(
                        page=pdf_page,
                        pos_data=barcode_data,
                        bleed_mm=bleed_mm,
                        page_width_mm=page_width_mm,
                        page_height_mm=page_height_mm,
                        doc=src,
                    )

            # Numeradoras y texto variable después (capa superior, como text_stack en viewer)
            for num_id, pos_data in cara_positions.items():
                pos_type = pos_data.get("type", "number")
                if pos_type == "barcode":
                    continue

                rotation_value = pos_data.get("rotation", 0)
                if isinstance(rotation_value, str):
                    rotation_value = int(rotation_value.replace("°", "").strip())

                if pos_type == "variable_text":
                    text_value = pos_data.get("sample_text", "")
                    if _PRINT_DEBUG:
                        print(f"[VT-PDF] pos_id={num_id} page={page_num} sample_text='{text_value}'")
                    # Resolver SIEMPRE los marcadores `<@<columna>@>` cuando haya
                    # Excel cargado (mismo comportamiento que el main/visor:
                    # _resolve_profile_vt_text). Independiente de value_source.
                    em = ExcelManager()
                    if em.is_loaded:
                        phys_page = page_num
                        start = cara_settings.get("start", 1)
                        end = cara_settings.get("end", 1000)
                        increment = cara_settings.get("increment", 1)
                        copies = cara_settings.get("copies", 1)
                        reverse = cara_settings.get("reverse", False)
                        row_index = excel_row_index(
                            start,
                            end,
                            increment,
                            copies,
                            reverse,
                            phys_page,
                            use_copy_grouping=use_copy_grouping,
                        )
                        if _PRINT_DEBUG:
                            print(f"[VT-PDF]  Excel is_loaded row_index={row_index} (start={start} inc={increment} copies={copies} reverse={reverse})")
                        try:
                            from utils.variable_text_measure import (
                                resolve_vt_text,
                            )

                            text_value = resolve_vt_text(
                                pos_data.get("sample_text", ""),
                                value_source=pos_data.get("value_source", "sample"),
                                excel_column=pos_data.get("excel_column", ""),
                                excel_manager=em,
                                row_index=row_index,
                                text_case_filter=pos_data.get("text_case_filter", ""),
                            )
                        except Exception as e:
                            if _PRINT_DEBUG:
                                print(f"[VT-PDF]  resolve_vt_text fallback: {e}")
                            excel_column = pos_data.get("excel_column", "")
                            if excel_column:
                                value = em.get_value_at(excel_column, row_index)
                                if value:
                                    text_value = _apply_text_case_filter(
                                        value,
                                        pos_data.get("text_case_filter", ""),
                                    )
                        if _PRINT_DEBUG:
                            print(f"[VT-PDF]  resolved='{text_value}'")
                    prefix = pos_data.get("prefix", "")
                    suffix = pos_data.get("suffix", "")
                    if _PRINT_DEBUG:
                        print(f"[VT-PDF]  FINAL text_value='{text_value}' prefix='{prefix}' suffix='{suffix}' full='{prefix}{text_value}{suffix}'")

                    render_variable_text_to_pdf(
                        pdf_page,
                        text_value,
                        pos_data.get("x", 0),
                        pos_data.get("y", 0),
                        bleed_mm,
                        font_family=pos_data.get("font_family", "Helvetica"),
                        font_style=pos_data.get("font_style", "Regular"),
                        font_size=float(pos_data.get("font_size", 12)),
                        alignment=pos_data.get("alignment", "izquierda"),
                        rotation=rotation_value,
                        page_width_mm=page_width_mm,
                        page_height_mm=page_height_mm,
                        x_offset_mm=pos_data.get("x_offset_mm", 0.0),
                        resolved_font_path=pos_data.get("resolved_font_path"),
                        resolved_font_index=pos_data.get("resolved_font_index"),
                        prefix=prefix,
                        suffix=suffix,
                        anchor=pos_data.get("anchor"),
                        line_spacing=_vt_line_spacing(pos_data),
                        letter_spacing=float(pos_data.get("letter_spacing", 0.0)),
                        text_alignment=pos_data.get("text_alignment", "izquierda"),

                        text_color=pos_data.get("text_color", "#000000"),
                        text_color_cmyk=pos_data.get("text_color_cmyk", (0, 0, 0, 100)),
                        text_color_space=pos_data.get("text_color_space", "RGB"),
                        text_color_name=pos_data.get("text_color_name", ""),
                        text_color_tint=pos_data.get("text_color_tint", 100.0),
                        prefix_suffix_color=pos_data.get(
                            "prefix_suffix_color", "#000000"
                        ),
                        prefix_suffix_color_cmyk=pos_data.get(
                            "prefix_suffix_color_cmyk", (0, 0, 0, 100)
                        ),
                        prefix_suffix_color_space=pos_data.get(
                            "prefix_suffix_color_space", "RGB"
                        ),
                        prefix_suffix_color_name=pos_data.get(
                            "prefix_suffix_color_name", ""
                        ),
                        prefix_suffix_color_tint=pos_data.get(
                            "prefix_suffix_color_tint", 100.0
                        ),
                    )
                else:
                    text_style_name = pos_data.get("text_style", "<Default>")
                    text_style = _get_text_style_data(
                        text_style_manager, text_style_name
                    )

                    raw_number = _calculate_number_for_page(
                        page_num,
                        cara_settings,
                        pos_data,
                        use_copy_grouping=use_copy_grouping,
                    )

                    mask = text_style.get("mask", "")
                    separator_type = text_style.get("thousands_separator", "normal")
                    raw_number = apply_mask_format(raw_number, mask, separator_type)

                    render_numeradora_to_pdf(
                        pdf_page,
                        raw_number,
                        pos_data.get("x", 0),
                        pos_data.get("y", 0),
                        bleed_mm,
                        text_style,
                        rotation_value,
                        pos_data.get("alignment", "left"),
                        page_width_mm,
                        page_height_mm,
                        pos_data.get("x_offset_mm", 0.0),
                    )

            # ═══════════════════════════════════════════════════════════════════
            # PÁGINA DORSO (si double_sided)
            # ═══════════════════════════════════════════════════════════════════

            if double_sided:
                # Crear página dorso
                pdf_page = src.new_page(
                    width=mm_to_pt(page_width_with_bleed),
                    height=mm_to_pt(page_height_with_bleed),
                )

                # Definir cajas PDF
                set_pdf_boxes(pdf_page, page_width_mm, page_height_mm, bleed_mm)

                # Agregar background si existe
                if dorso_background:
                    if _PRINT_DEBUG:
                        print(
                            f"[BG TRACE] página lógica {page_num} DORSO -> llamando add_background_to_page"
                        )
                    add_background_to_page(
                        pdf_page,
                        dorso_background,
                        page_width_mm,
                        page_height_mm,
                        bleed_mm,
                        dorso_bg_doc,  # Pasar documento ya abierto
                    )
                else:
                    if _PRINT_DEBUG:
                        print(
                            f"[BG TRACE] página lógica {page_num} DORSO -> sin fondo (salta add_background_to_page)"
                        )

                # Renderizar posiciones de DORSO - barcodes primero (capa inferior)
                for num_id, pos_data in dorso_positions.items():
                    pos_type = pos_data.get("type", "number")
                    _debug_y(
                        f"[DORSO loop] page={page_num} pos={num_id} type={pos_type} x={pos_data.get('x',0)} y={pos_data.get('y',0)}"
                    )
                    if pos_type == "barcode":
                        barcode_data = pos_data
                        if pos_data.get("value_source", "fixed") == "numbering":
                            # Para códigos con numeración interna, recalcular valor por página
                            # durante exportación PDF (no depender del valor estático de UI).
                            raw_barcode_number = _calculate_number_for_page(
                                page_num,
                                dorso_settings,
                                pos_data,
                                use_copy_grouping=use_copy_grouping,
                            )
                            mask = pos_data.get("mask", "")
                            barcode_value = apply_mask_format(
                                raw_barcode_number, mask, "normal"
                            )
                            barcode_data = dict(pos_data)
                            barcode_data["barcode_value"] = barcode_value
                        elif pos_data.get("value_source", "fixed") == "excel":
                            excel_column = pos_data.get("excel_column", "")
                            if excel_column:
                                em = ExcelManager()
                                if em.is_loaded:
                                    phys_page = page_num
                                    start = dorso_settings.get("start", 1)
                                    end = dorso_settings.get("end", 1000)
                                    increment = dorso_settings.get("increment", 1)
                                    copies = dorso_settings.get("copies", 1)
                                    reverse = dorso_settings.get("reverse", False)
                                    row_index = excel_row_index(
                                        start,
                                        end,
                                        increment,
                                        copies,
                                        reverse,
                                        phys_page,
                                        use_copy_grouping=use_copy_grouping,
                                    )
                                    value = em.get_value_at(excel_column, row_index)
                                    if value:
                                        barcode_data = dict(pos_data)
                                        barcode_data["barcode_value"] = value
                        elif pos_data.get("value_source", "fixed") == "fixed":
                            tmpl = pos_data.get("sample_value", "")
                            symb = pos_data.get("symbology", "")
                            if "<@<" in tmpl and symb in ("qr", "pdf417", "datamatrix"):
                                from utils.excel_manager import ExcelManager as _EMvt2
                                em = _EMvt2()
                                if em.is_loaded:
                                    phys_page = page_num
                                    start = dorso_settings.get("start", 1)
                                    end = dorso_settings.get("end", 1000)
                                    increment = dorso_settings.get("increment", 1)
                                    copies = dorso_settings.get("copies", 1)
                                    reverse = dorso_settings.get("reverse", False)
                                    row_index = excel_row_index(
                                        start, end, increment, copies, reverse, phys_page, use_copy_grouping=use_copy_grouping,
                                    )

                                    def _repl2(m):
                                        col = m.group(1).strip()
                                        try:
                                            return em.get_value_at(col, row_index) or ""
                                        except Exception:
                                            return ""

                                    resolved = re.sub(r"<@<([^>]+)>@>", _repl2, tmpl)
                                    barcode_data = dict(pos_data)
                                    barcode_data["barcode_value"] = resolved

                        render_barcode_to_pdf(
                            page=pdf_page,
                            pos_data=barcode_data,
                            bleed_mm=bleed_mm,
                            page_width_mm=page_width_mm,
                            page_height_mm=page_height_mm,
                            doc=src,
                        )

                # Numeradoras y texto variable después (capa superior)
                for num_id, pos_data in dorso_positions.items():
                    pos_type = pos_data.get("type", "number")
                    if pos_type == "barcode":
                        continue

                    rotation_value = pos_data.get("rotation", 0)
                    if isinstance(rotation_value, str):
                        rotation_value = int(rotation_value.replace("°", "").strip())

                    if pos_type == "variable_text":
                        text_value = pos_data.get("sample_text", "")
                        if _PRINT_DEBUG:
                            print(f"[VT-PDF-DORSO] pos_id={num_id} page={page_num} sample_text='{text_value}'")
                        # Resolver SIEMPRE los marcadores `<@<columna>@>` cuando haya
                        # Excel cargado (mismo comportamiento que el main/visor).
                        em = ExcelManager()
                        if em.is_loaded:
                            phys_page = page_num
                            start = dorso_settings.get("start", 1)
                            end = dorso_settings.get("end", 1000)
                            increment = dorso_settings.get("increment", 1)
                            copies = dorso_settings.get("copies", 1)
                            reverse = dorso_settings.get("reverse", False)
                            row_index = excel_row_index(
                                start,
                                end,
                                increment,
                                copies,
                                reverse,
                                phys_page,
                                use_copy_grouping=use_copy_grouping,
                            )
                            if _PRINT_DEBUG:
                                print(f"[VT-PDF-DORSO]  Excel is_loaded row_index={row_index} (start={start} inc={increment} copies={copies} reverse={reverse})")
                            try:
                                from utils.variable_text_measure import (
                                    resolve_vt_text,
                                )

                                text_value = resolve_vt_text(
                                    pos_data.get("sample_text", ""),
                                    value_source=pos_data.get("value_source", "sample"),
                                    excel_column=pos_data.get("excel_column", ""),
                                    excel_manager=em,
                                    row_index=row_index,
                                    text_case_filter=pos_data.get(
                                        "text_case_filter", ""
                                    ),
                                )
                            except Exception as e:
                                if _PRINT_DEBUG:
                                    print(f"[VT-PDF-DORSO]  resolve_vt_text fallback: {e}")
                                excel_column = pos_data.get("excel_column", "")
                                if excel_column:
                                    value = em.get_value_at(excel_column, row_index)
                                    if value:
                                        text_value = _apply_text_case_filter(
                                            value,
                                            pos_data.get("text_case_filter", ""),
                                        )
                        if _PRINT_DEBUG:
                            print(f"[VT-PDF-DORSO]  resolved='{text_value}'")
                        prefix = pos_data.get("prefix", "")
                        suffix = pos_data.get("suffix", "")
                        if _PRINT_DEBUG:
                            print(f"[VT-PDF-DORSO]  FINAL text_value='{text_value}' prefix='{prefix}' suffix='{suffix}' full='{prefix}{text_value}{suffix}'")

                        render_variable_text_to_pdf(
                            pdf_page,
                            text_value,
                            pos_data.get("x", 0),
                            pos_data.get("y", 0),
                            bleed_mm,
                            font_family=pos_data.get("font_family", "Helvetica"),
                            font_style=pos_data.get("font_style", "Regular"),
                            font_size=float(pos_data.get("font_size", 12)),
                            alignment=pos_data.get("alignment", "izquierda"),
                            rotation=rotation_value,
                            page_width_mm=page_width_mm,
                            page_height_mm=page_height_mm,
                            x_offset_mm=pos_data.get("x_offset_mm", 0.0),
                            resolved_font_path=pos_data.get("resolved_font_path"),
                            resolved_font_index=pos_data.get("resolved_font_index"),
                            prefix=prefix,
                            suffix=suffix,
                            letter_spacing=float(pos_data.get("letter_spacing", 0.0)),
                            text_alignment=pos_data.get("text_alignment", "izquierda"),
                            anchor=pos_data.get("anchor"),
                            line_spacing=_vt_line_spacing(pos_data),

                            text_color=pos_data.get("text_color", "#000000"),
                            text_color_cmyk=pos_data.get("text_color_cmyk", (0, 0, 0, 100)),
                            text_color_space=pos_data.get("text_color_space", "RGB"),
                            text_color_name=pos_data.get("text_color_name", ""),
                            text_color_tint=pos_data.get("text_color_tint", 100.0),
                            prefix_suffix_color=pos_data.get(
                                "prefix_suffix_color", "#000000"
                            ),
                            prefix_suffix_color_cmyk=pos_data.get(
                                "prefix_suffix_color_cmyk", (0, 0, 0, 100)
                            ),
                            prefix_suffix_color_space=pos_data.get(
                                "prefix_suffix_color_space", "RGB"
                            ),
                            prefix_suffix_color_name=pos_data.get(
                                "prefix_suffix_color_name", ""
                            ),
                            prefix_suffix_color_tint=pos_data.get(
                                "prefix_suffix_color_tint", 100.0
                            ),
                        )
                    else:
                        text_style_name = pos_data.get("text_style", "<Default>")
                        text_style = _get_text_style_data(
                            text_style_manager, text_style_name
                        )

                        raw_number = _calculate_number_for_page(
                            page_num,
                            dorso_settings,
                            pos_data,
                            use_copy_grouping=use_copy_grouping,
                        )

                        mask = text_style.get("mask", "")
                        separator_type = text_style.get("thousands_separator", "normal")
                        raw_number = apply_mask_format(raw_number, mask, separator_type)

                        render_numeradora_to_pdf(
                            pdf_page,
                            raw_number,
                            pos_data.get("x", 0),
                            pos_data.get("y", 0),
                            bleed_mm,
                            text_style,
                            rotation_value,
                            pos_data.get("alignment", "left"),
                            page_width_mm,
                        page_height_mm,
                        pos_data.get("x_offset_mm", 0.0),
                    )

            # ═══ EMISIÓN FUSIONADA (fase única, sustituye merge_pdfs) ═════════
            # Acumular el lógico (simplex: página; duplex: par c,d) y emitir
            # ×copies = c,d,c,d... al completar el TRAMO. src debe estar
            # CONGELADO durante todos los inserts: si se modifica tras usarse
            # como fuente, el Graftmap queda obsoleto → "source object number
            # out of range" (sonda). Por eso: render del tramo TODO → inserts
            # → reset src+batch juntos (nuevo graftmap por lote).
            hi_idx = src.page_count - 1
            tramo_pages.append((lo_idx, hi_idx))
            current_pdf_page += copies * faces
            if progress_callback:
                # Optimista (tras render, antes de insertar): avanza el
                # progreso durante el render (parte lenta) y checkpoint de
                # cancelación; los inserts van justo después.
                try:
                    progress_callback(current_pdf_page, total_pdf_pages)
                except InterruptedError:
                    print("[INFO] Generación cancelada por el usuario")
                    cancelled_by_user = True
                    break
            if len(tramo_pages) >= logicals_per_tramo:
                for _lo, _hi in tramo_pages:
                    for _ in range(copies):
                        # final=0 MANTIENE el Graftmap → fuentes compartidas
                        # entre las N copias (final=1 lo destruye tras el 1er).
                        doc.insert_pdf(src, from_page=_lo, to_page=_hi, final=0)
                tramo_pages = []
                # LOTE COMPLETO: guardar a disco, liberar RAM
                if doc.page_count > 0:
                    bp = str(temp_dir / f"batch_{batch_num}.pdf")
                    doc.save(bp, **SAVE_OPTS_BATCH)
                    batch_files.append(bp)
                    batch_num += 1
                    if _PRINT_DEBUG:
                        print(
                            f"[BATCH] Lote {batch_num} guardado (pág {current_pdf_page}/{total_pdf_pages})"
                        )
                doc.close()
                fitz.TOOLS.store_shrink(100)
                doc = fitz.open()
                src.close()
                src = fitz.open()

        if cancelled_by_user:
            # Cancelación durante el render: NO unir/subset/guardar. El raise
            # DENTRO del try activa el cleanup (temp + output parcial si no
            # existía antes) — el viejo flujo guardaba un parcial y luego
            # raise FUERA del try (dejaba archivo tras "cancelada").
            raise InterruptedError(
                f"PDF cancelado parcialmente ({current_pdf_page} páginas)"
            )

        # Emitir el tramo parcial pendiente y guardar el último lote
        if _PRINT_DEBUG:
            print(f"\n[BATCH] Guardando último lote y uniendo...")
        for _lo, _hi in tramo_pages:
            for _ in range(copies):
                doc.insert_pdf(src, from_page=_lo, to_page=_hi, final=0)
        tramo_pages = []
        if doc.page_count > 0:
            bp = str(temp_dir / f"batch_{batch_num}.pdf")
            doc.save(bp, **SAVE_OPTS_BATCH)
            batch_files.append(bp)
        doc.close()
        fitz.TOOLS.store_shrink(100)
        if src is not None:
            try:
                src.close()
            except Exception:
                pass
            src = None
        if _PRINT_DEBUG:
            builtins.print(f"[TIMING] Phase1 render+lotes: {_time.monotonic() - _t_mark:.2f}s ({current_pdf_page} pág)")
        _t_mark = _time.monotonic()

        # Cerrar PDFs de fondo
        if cara_bg_doc is not None:
            cara_bg_doc.close()
            if _PRINT_DEBUG:
                print(f"[BG] PDF de fondo CARA cerrado")
        if dorso_bg_doc is not None:
            dorso_bg_doc.close()
            if _PRINT_DEBUG:
                print(f"[BG] PDF de fondo DORSO cerrado")

        # Subset POR LOTE en paralelo (PROCESOS): cada batch_*.pdf ya está en
        # disco; un proceso por lote sí paraleliza (hilos salían en serie por
        # el GIL). La unión hereda los subsets (mismo resultado). Fallback:
        # subset final clásico (NO si es cancelación → propagar).
        _need_final_subset = True
        if enable_subset_fonts and batch_files:
            _t_subset = _time.monotonic()
            try:
                _subset_batches_parallel(batch_files, progress=progress_callback)
                _need_final_subset = False
            except InterruptedError:
                raise
            except Exception as e_par:
                builtins.print(f"[BATCH][WARN] subset paralelo falló ({e_par}): subset final clásico")
            if _PRINT_DEBUG:
                builtins.print(f"[TIMING] Phase1 subset lotes: {_time.monotonic() - _t_subset:.2f}s ({len(batch_files)} lotes)")
            _t_mark = _time.monotonic()

        # Fase final: progreso por paginas insertadas al unir lotes.
        # Importante: no reiniciar en 0 para evitar efecto visual de "loop".

        # Unir todos los lotes en el PDF final
        if _PRINT_DEBUG:
            print(f"[BATCH] Uniendo {len(batch_files)} lotes → {output_path}")
        doc_final = fitz.open()
        total_paginas_reales = 0
        total_batches = len(batch_files)
        for idx, bp in enumerate(batch_files):
            # Señal para UI: justo antes de insertar el último lote,
            # cambiar a modo "optimización final" (sin barra de progreso).
            if progress_callback and idx == total_batches - 1:
                progress_callback(-1, -total_pdf_pages)

            src = fitz.open(bp)
            try:
                doc_final.insert_pdf(src)
                total_paginas_reales += src.page_count
            finally:
                try:
                    src.close()
                except Exception:
                    pass
                src = None
            if progress_callback:
                progress_callback(total_paginas_reales, -total_pdf_pages)

        # Checkpoint de cancelación antes del post-proceso pesado final
        # (subset_fonts + save final). Permite abortar sin escribir output_path.
        if progress_callback:
            progress_callback(-2, -total_pdf_pages)
        if _PRINT_DEBUG:
            builtins.print(f"[TIMING] Phase1 union lotes: {_time.monotonic() - _t_mark:.2f}s ({len(batch_files)} lotes)")
        _t_mark = _time.monotonic()

        if enable_subset_fonts and _need_final_subset:
            try:
                doc_final.subset_fonts()
            except Exception as e_subset:
                if _PRINT_DEBUG:
                    print(f"[BATCH][WARN] subset_fonts falló: {e_subset}")
        if _PRINT_DEBUG:
            builtins.print(f"[TIMING] Phase1 subset_fonts: {_time.monotonic() - _t_mark:.2f}s")
        _t_mark = _time.monotonic()

        doc_final.save(output_path, **SAVE_OPTS_FINAL)
        if _PRINT_DEBUG:
            builtins.print(f"[TIMING] Phase1 save (garbage={SAVE_OPTS_FINAL.get('garbage')}): {_time.monotonic() - _t_mark:.2f}s")
        final_saved = True
        doc_final.close()
        doc_final = None
        fitz.TOOLS.store_shrink(100)

        # Eliminar carpeta temporal
        try:
            shutil.rmtree(temp_dir)
            if _PRINT_DEBUG:
                print(f"[BATCH] Carpeta temporal eliminada: {temp_dir}")
        except Exception as e_rm:
            if _PRINT_DEBUG:
                builtins.print(f"[BATCH][WARN] No se pudo eliminar carpeta temporal: {e_rm}")

    except Exception as ex:
        # Asegurar limpieza en caso de error
        if "doc" in locals():
            try:
                doc.close()
            except Exception:
                pass
        if "src" in locals() and src is not None:
            try:
                src.close()
            except Exception:
                pass
        if "doc_final" in locals() and doc_final is not None:
            try:
                doc_final.close()
            except Exception:
                pass
        if "cara_bg_doc" in locals() and cara_bg_doc is not None:
            try:
                if not getattr(cara_bg_doc, "is_closed", True):
                    cara_bg_doc.close()
            except Exception:
                pass
        if "dorso_bg_doc" in locals() and dorso_bg_doc is not None:
            try:
                if not getattr(dorso_bg_doc, "is_closed", True):
                    dorso_bg_doc.close()
            except Exception:
                pass
        # Limpiar carpeta temporal
        try:
            shutil.rmtree(temp_dir)
        except Exception:
            pass

        # Evitar dejar archivo final parcial tras cancelar durante fase final.
        # Solo borrar si NO existía antes de esta ejecución.
        if isinstance(ex, InterruptedError):
            try:
                if (
                    not final_saved
                    and not output_existed_before
                    and os.path.exists(output_path)
                ):
                    os.remove(output_path)
            except Exception:
                pass
        raise ex

    return output_path


def merge_pdfs(
    file_paths,
    output_path,
    print_mode,
    progress_callback=None,
    cancelado=None,
    save_opts=None,
):
    """
    Combina los PDFs de manera intercalada (copiado del flujo de
    PdfCopyCollector/COPY_COLLECT/pdf_merger.py, sin dependencias de esa app).

    Se usa insert_pdf por página para copiar objetos PDF nativos
    (más rápido que show_pdf_page y preserva todas las cajas).

    - simplex: P1 x N copias, P2 x N copias, ...
    - duplex:  (1a, 1b) x N copias, (2a, 2b) x N copias, ...
      (última página par: si las originales son impares se añade una página en
      blanco del mismo tamaño, igual que PdfCopyCollector).
    - insert_page: no soportado aquí (solo simplex/duplex).

    Args:
        file_paths: Lista de PDFs fuente; para copias pasar [mismo]*copies.
        output_path: Ruta del PDF final.
        print_mode: "simplex" o "duplex".
        progress_callback: Callback(pages_done, total_pages, phase_key,
            step_done, step_total) con la MISMA firma que PdfCopyCollector.
        cancelado: dict {"valor": bool} — si True en check, raise InterruptedError.
        save_opts: diccionario de opciones de guardado (garbage/deflate/clean).

    Returns:
        int: numero de paginas logicas por copia (logical_pages).
    """
    if not file_paths:
        raise ValueError("No files provided.")

    BATCH_SIZE = 200  # páginas por lote (mismo patrón que Phase 1; era 20 → 710 lotes)

    num_copies = len(file_paths)
    docs = []
    out_doc = None
    temp_dir = None
    batch_files = []

    def report_progress(done_pages, total_pages, phase_key, done_steps, total_steps):
        if progress_callback:
            progress_callback(
                done_pages, total_pages, phase_key, done_steps, total_steps
            )

    def check_cancelled():
        if cancelado and cancelado.get("valor"):
            raise InterruptedError("process_cancelled")

    try:
        docs = [fitz.open(fp) for fp in file_paths]
        check_cancelled()
        num_pages = len(docs[0])

        if print_mode == "simplex":
            logical_pages = num_pages
            total_ops = num_pages * num_copies
        else:  # duplex
            logical_pages = num_pages if num_pages % 2 == 0 else num_pages + 1
            total_ops = logical_pages * num_copies

        total_batches = max(1, math.ceil(total_ops / BATCH_SIZE))
        total_steps = total_ops + (total_batches * 2) + 1
        current_step = 0
        current_pages = 0
        current_batch_pages = 0
        batch_index = 0
        show_saving_before_last_page = (
            save_opts is not None and save_opts.get("garbage", 0) >= 4 and total_ops > 1
        )

        temp_base = get_config_dir() / "pdf_temp"
        try:
            temp_base.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.warning("No se pudo crear temp_base en config_dir: %s", e)
            temp_base = None

        if temp_base and temp_base.exists():
            temp_dir = Path(
                tempfile.mkdtemp(prefix="pn_copies_batches_", dir=str(temp_base))
            )
        else:
            temp_dir = Path(tempfile.mkdtemp(prefix="pn_copies_batches_"))

        out_doc = fitz.open()

        def flush_batch(force=False):
            nonlocal out_doc, current_batch_pages, batch_index, current_step
            check_cancelled()
            if out_doc is None or out_doc.page_count == 0:
                return
            if not force and current_batch_pages < BATCH_SIZE:
                return

            batch_path = temp_dir / f"batch_{batch_index:04d}.pdf"
            # intermedio: sin deflate/garbage — el save final ya comprime (Phase 1 idéntico)
            out_doc.save(str(batch_path), garbage=0, deflate=False, clean=False)
            out_doc.close()
            out_doc = None
            fitz.TOOLS.store_shrink(100)
            batch_files.append(batch_path)
            batch_index += 1
            current_batch_pages = 0
            current_step += 1
            report_progress(
                current_pages,
                total_ops,
                "progress_flushing",
                current_step,
                total_steps,
            )
            out_doc = fitz.open()

        def append_source_page(doc, page_index):
            nonlocal current_step, current_pages, current_batch_pages
            check_cancelled()
            if out_doc is None:
                raise ValueError("Documento de salida no inicializado.")
            if show_saving_before_last_page and current_pages == total_ops - 1:
                report_progress(
                    current_pages,
                    total_ops,
                    "progress_saving",
                    current_step,
                    total_steps,
                )
            # Copia nativa de objetos (insert_pdf): más rápida que
            # show_pdf_page y preserva TrimBox/BleedBox/ArtBox/CropBox
            # sin reajuste manual de coordenadas.
            out_doc.insert_pdf(doc, from_page=page_index, to_page=page_index)
            current_batch_pages += 1
            current_pages += 1
            current_step += 1
            report_progress(
                current_pages,
                total_ops,
                "progress_generating",
                current_step,
                total_steps,
            )
            flush_batch()

        def append_blank_page(width, height):
            nonlocal current_step, current_pages, current_batch_pages
            check_cancelled()
            if out_doc is None:
                raise ValueError("Documento de salida no inicializado.")
            if show_saving_before_last_page and current_pages == total_ops - 1:
                report_progress(
                    current_pages,
                    total_ops,
                    "progress_saving",
                    current_step,
                    total_steps,
                )
            out_doc.new_page(width=width, height=height)
            current_batch_pages += 1
            current_pages += 1
            current_step += 1
            report_progress(
                current_pages,
                total_ops,
                "progress_generating",
                current_step,
                total_steps,
            )
            flush_batch()

        import time as _time

        _t_mark = _time.monotonic()

        if print_mode == "simplex":
            for p_idx in range(num_pages):
                check_cancelled()
                for doc in docs:
                    append_source_page(doc, p_idx)

        else:  # duplex
            num_blocks = logical_pages // 2
            for b_idx in range(num_blocks):
                check_cancelled()
                p1_idx = b_idx * 2
                p2_idx = b_idx * 2 + 1

                for doc in docs:
                    # Primera página del bloque
                    page1 = doc[p1_idx]
                    append_source_page(doc, p1_idx)

                    # Segunda página del bloque
                    if p2_idx < num_pages:
                        append_source_page(doc, p2_idx)
                    else:
                        # Página en blanco del mismo tamaño que p1
                        append_blank_page(page1.rect.width, page1.rect.height)

        flush_batch(force=True)
        if out_doc is not None:
            out_doc.close()
            out_doc = None
        if _PRINT_DEBUG:
            builtins.print(f"[TIMING] Phase2 copia: {_time.monotonic() - _t_mark:.2f}s ({current_pages} pág, {len(docs)} copias)")
        _t_mark = _time.monotonic()

        final_doc = fitz.open()
        try:
            for batch_path in batch_files:
                check_cancelled()
                src = fitz.open(str(batch_path))
                try:
                    final_doc.insert_pdf(src)
                finally:
                    src.close()
                current_step += 1
                report_progress(
                    current_pages,
                    total_ops,
                    "progress_merging",
                    current_step,
                    total_steps,
                )

            check_cancelled()
            if _PRINT_DEBUG:
                builtins.print(f"[TIMING] Phase2 union lotes: {_time.monotonic() - _t_mark:.2f}s ({len(batch_files)} lotes)")
            _t_mark = _time.monotonic()
            garbage, deflate, clean, use_objstms = _resolve_save_options(save_opts)
            current_step += 1
            report_progress(
                current_pages,
                total_ops,
                "progress_saving",
                current_step,
                total_steps,
            )
            if garbage >= 2:
                try:
                    final_doc.subset_fonts()
                except Exception as exc:
                    logger.warning("[MERGE][WARN] subset_fonts falló: %s", exc)
            if _PRINT_DEBUG:
                builtins.print(f"[TIMING] Phase2 subset_fonts: {_time.monotonic() - _t_mark:.2f}s")
            _t_mark = _time.monotonic()
            final_doc.save(
                output_path, garbage=garbage, deflate=deflate, clean=clean, use_objstms=use_objstms
            )
            if _PRINT_DEBUG:
                builtins.print(f"[TIMING] Phase2 save final (garbage={garbage}): {_time.monotonic() - _t_mark:.2f}s")
        finally:
            final_doc.close()
            fitz.TOOLS.store_shrink(100)

        return logical_pages

    finally:
        if out_doc:
            out_doc.close()
        if temp_dir:
            try:
                shutil.rmtree(temp_dir)
            except Exception:
                logger.warning(
                    "No se pudo eliminar el directorio temporal: %s", temp_dir
                )
        for doc in docs:
            doc.close()


def _resolve_save_options(save_opts):
    """Normaliza opciones de guardado para mantener tipos estables."""
    opts = save_opts if isinstance(save_opts, dict) else {}

    try:
        garbage = int(opts.get("garbage", 4))
    except Exception:
        garbage = 4

    deflate = bool(opts.get("deflate", True))
    clean = bool(opts.get("clean", False))
    try:
        use_objstms = int(opts.get("use_objstms", 1))
    except Exception:
        use_objstms = 1
    return garbage, deflate, clean, use_objstms


def _calculate_number_for_page(
    page_num: int,
    face_settings: Dict,
    pos_data: Dict,
    use_copy_grouping: bool = True,
) -> str:
    """
    Calcula el número a mostrar en una página específica (solo el número, SIN prefix/suffix).

    Args:
        page_num: Número de página (1-based)
        face_settings: Configuración global de la cara (start, increment, copies, reverse)
        pos_data: Datos de la posición (add)

    Returns:
        String del número formateado con máscara (SIN prefix/suffix)
    """
    # Extraer configuración
    start = face_settings.get("start", 1)
    increment = face_settings.get("increment", 1)
    copies = face_settings.get("copies", 1)
    reverse = face_settings.get("reverse", False)
    end = face_settings.get("end", 1000)

    # Valor adicional de la numeradora — solo dígitos
    add = pos_data.get("add", 0)
    if isinstance(add, str):
        try:
            add_str = "".join(c for c in add if c.isdigit())
            add = int(add_str) if add_str else 0
        except:
            add = 0

    # Calcular índice del número (0-based).
    # - use_copy_grouping=True: comportamiento histórico (agrupa por copias)
    # - use_copy_grouping=False: cada página lógica avanza 1 número
    page_index = page_num - 1  # Convertir a 0-based
    num_index = page_index // copies if use_copy_grouping else page_index

    # Calcular número base
    if reverse:
        # Revertir: empezar desde el final
        total_numbers = (end - start) // increment + 1
        base_number = end - (num_index * increment)
    else:
        # Normal: empezar desde start
        base_number = start + (num_index * increment)

    # Agregar valor adicional de la numeradora
    final_number = base_number + add

    # Retornar solo el número formateado (sin prefix/suffix)
    # El prefix/suffix se añadirán en render_numeradora_to_pdf con sus colores
    return str(final_number)


def _format_number(number: int, prefix: str, suffix: str, mask: str) -> str:
    """
    Formatea un número con prefix, suffix y mask.

    Args:
        number: Número a formatear
        prefix: Prefijo a agregar
        suffix: Sufijo a agregar
        mask: Máscara de formato (ej: "0000" para 4 dígitos con ceros)

    Returns:
        String formateado
    """
    # Aplicar máscara si existe
    if mask:
        # Contar ceros en la máscara para determinar padding
        num_zeros = mask.count("0")
        if num_zeros > 0:
            number_str = str(number).zfill(num_zeros)
        else:
            number_str = str(number)
    else:
        number_str = str(number)

    # Agregar prefix y suffix
    return f"{prefix}{number_str}{suffix}"


# ============================================================================
# SOPORTE SEPARATION / SPOT COLOR
# ============================================================================


def _pdf_encode_name(name: str) -> str:
    """
    Codifica una cadena como nombre PDF (reemplaza caracteres con #XX).
    Caracteres a codificar: espacio y los no imprimibles/especiales de PDF.
    """
    result = []
    for ch in name:
        code = ord(ch)
        # Codificar espacios y caracteres que no son «regulares» en nombres PDF:
        # PDF spec §7.3.5: name chars excluding whitespace and delimiters
        if code <= 0x20 or code >= 0x7F or ch in "()/<>[]{}#%\\/":
            result.append(f"#{code:02X}")
        else:
            result.append(ch)
    return "".join(result)


def _define_spot_colorspace(
    doc: fitz.Document, page: fitz.Page, color_name: str, cmyk_01: tuple
) -> str:
    """
    Define un espacio de color Separation en los recursos de la página y
    devuelve el alias PDF (clave en Resources/ColorSpace) para usarlo con
    los operadores 'cs' y 'scn'.

    Estrategia robusta:
    1. La función tintTransform se crea como objeto PDF INDIRECTO (xref propio),
       evitando dicts anidados que xref_set_key no parsea bien.
    2. Se resuelven hasta dos niveles de indirección:
       - /Resources puede ser xref
       - /Resources/ColorSpace puede ser xref
    """
    import hashlib

    alias = "Cs" + hashlib.md5(color_name.encode("utf-8")).hexdigest()[:8].upper()

    c, m, y, k = [float(v) for v in cmyk_01]
    pdf_name = _pdf_encode_name(color_name)

    try:
        # ── 1. Crear la función tintTransform como objeto PDF indirecto ────────
        #    Type 2 (exponencial/lineal): f(t) = C0*(1-t^N) + C1*t^N  con N=1
        func_def = (
            f"<</FunctionType 2 /Domain [0 1] "
            f"/C0 [0 0 0 0] /C1 [{c:.6f} {m:.6f} {y:.6f} {k:.6f}] /N 1>>"
        )
        func_xref = doc.get_new_xref()
        doc.update_object(func_xref, func_def)

        # ── 2. Array Separation que referencia la función por xref ─────────────
        sep_array = f"[/Separation /{pdf_name} /DeviceCMYK {func_xref} 0 R]"

        # ── 3. Resolver /Resources (puede ser indirecto) ───────────────────────
        res_type, res_val = doc.xref_get_key(page.xref, "Resources")
        if res_type == "xref":
            res_xref = int(res_val.split()[0])
        else:
            # Resources inline en el page object
            res_xref = page.xref

        # ── 4. Resolver /Resources/ColorSpace (también puede ser indirecto) ────
        cs_type, cs_val = doc.xref_get_key(res_xref, "ColorSpace")
        if cs_type == "xref":
            cs_xref = int(cs_val.split()[0])
            doc.xref_set_key(cs_xref, alias, sep_array)
        else:
            # ColorSpace inline (o no existe → xref_set_key lo creará)
            # Necesitamos path notation relativa a res_xref
            if res_xref == page.xref:
                doc.xref_set_key(page.xref, f"Resources/ColorSpace/{alias}", sep_array)
            else:
                doc.xref_set_key(res_xref, f"ColorSpace/{alias}", sep_array)

        print(
            f"[SPOT_PDF] Separation OK: /{alias} → '{color_name}' "
            f"CMYK({c:.4f},{m:.4f},{y:.4f},{k:.4f}) func_xref={func_xref}"
        )

    except Exception as e:
        logger.exception("[SPOT_PDF] Error al definir Separation para '%s'", color_name)

    return alias


def _inject_spot_operators(
    doc: fitz.Document,
    page: fitz.Page,
    spot_alias: str,
    prev_content_xrefs: list,
    tint_pct: float = 100.0,
) -> bool:
    """
    Tras un `page.insert_text()`, encuentra el último content stream añadido
    y reemplaza el operador de color CMYK fill ('k') por los operadores de
    Separation ('cs' y 'scn'), de forma que el texto use la tinta plana.

    Args:
        doc:                  documento PyMuPDF
        page:                 página que contiene el texto
        spot_alias:           alias del Separation en Resources/ColorSpace
        prev_content_xrefs:   lista de xrefs de content streams ANTES de insert_text
        tint_pct:             porcentaje de tinta (0-100, default 100 = plena)

    Returns:
        True si se pudo reemplazar, False si no.
    """
    import re

    try:
        current_xrefs = page.get_contents()
        # Encontrar xref nuevo (el que insert_text acaba de añadir)
        new_xrefs = [x for x in current_xrefs if x not in prev_content_xrefs]
        if not new_xrefs:
            # insert_text puede reutilizar el último xref en lugar de crear uno nuevo
            new_xrefs = [current_xrefs[-1]] if current_xrefs else []
        if not new_xrefs:
            return False

        target_xref = new_xrefs[-1]
        raw = doc.xref_stream(target_xref)
        if raw is None:
            return False

        # Patrón: 4 números float + operador de color fill 'k' (minúscula).
        # PyMuPDF escribe los valores sin cero inicial: ".06 .24 .6 .07 k"
        # por tanto el patrón debe aceptar números que empiezan con punto.
        float_re = rb"[-+]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][-+]?[0-9]+)?"
        pattern = (
            rb"(?m)"
            + float_re
            + rb"\s+"
            + float_re
            + rb"\s+"
            + float_re
            + rb"\s+"
            + float_re
            + rb"\s+"
            + rb"k\b"  # operador fill CMYK (minúscula)
        )

        replacement = f"/{spot_alias} cs\n{tint_pct / 100.0:.6f} scn".encode("latin-1")

        # Reemplazar la ÚLTIMA ocurrencia (el texto más recientemente añadido al stream)
        # Esto evita que el operador k del prefijo sea reemplazado en lugar del del número
        matches = list(re.finditer(pattern, raw))
        if not matches:
            print(
                f"[SPOT_PDF] No se encontró operador CMYK 'k' en xref={target_xref} — "
                "el texto se renderizará con CMYK alternativo"
            )
            # Diagnóstico: mostrar primeros bytes del stream
            print(f"[SPOT_PDF] Primeros 300 bytes del stream: {raw[:300]!r}")
            return False

        last_match = matches[-1]
        modified = raw[: last_match.start()] + replacement + raw[last_match.end() :]

        doc.update_stream(target_xref, modified)
        print(
            f"[SPOT_PDF] ✓ Operadores CMYK→Separation reemplazados en xref={target_xref} "
            f"(alias=/{spot_alias})"
        )
        return True

    except Exception as e:
        logger.exception("[SPOT_PDF] Error en _inject_spot_operators")
        return False


def _get_text_style_data(text_style_manager, style_name: str) -> Dict:
    """
    Obtiene los datos de un estilo de texto del manager.

    Args:
        text_style_manager: Gestor de estilos de texto
        style_name: Nombre del perfil de estilo

    Returns:
        Dict con los datos del estilo en formato para renderizado PDF:
        - font_name: str
        - font_size: float
        - color_space: "RGB" o "CMYK"
        - number_color: tuple (3 o 4 valores normalizados 0-1)
        - prefix_color: tuple
        - suffix_color: tuple
        - letter_spacing: float
        - prefix_suffix_spacing: float
    """
    # Obtener todos los perfiles del manager
    profiles = text_style_manager.get_profiles()

    if _PRINT_DEBUG:
        print(
            f"\n[_get_text_style_data] Buscando estilo '{style_name}' entre {len(profiles)} perfiles"
        )

    # Buscar el perfil por nombre
    profile = None
    for p in profiles:
        if p.name == style_name:
            profile = p
            if _PRINT_DEBUG:
                print(f"[_get_text_style_data] ✓ Perfil encontrado: {profile.name}")
                print(f"  font_family: {profile.font_family}")
                print(f"  font_style: {profile.font_style}")
                print(
                    f"  resolved_font_path: {getattr(profile, 'resolved_font_path', 'NO EXISTE')}"
                )
                print(
                    f"  resolved_font_index: {getattr(profile, 'resolved_font_index', 'NO EXISTE')}"
                )
            break

    if not profile:
        # Si no se encuentra, usar el primero o crear uno por defecto
        if profiles:
            profile = profiles[0]
        else:
            # Estilo por defecto
            return {
                "font_name": "Helvetica",
                "font_size": 12.0,
                "color_space": "RGB",
                "number_color": (0, 0, 0),
                "prefix_color": (0, 0, 0),
                "suffix_color": (0, 0, 0),
                "letter_spacing": 0.0,
                "prefix_suffix_spacing": 0.0,
            }

    # Convertir colores según el espacio de color de cada segmento
    color_space = profile.color_space  # legacy / fallback
    num_space = getattr(profile, "number_color_space", color_space)
    pre_space = getattr(profile, "prefix_color_space", color_space)
    suf_space = getattr(profile, "suffix_color_space", color_space)

    def hex_to_rgb_normalized(hex_color):
        hex_color = hex_color.lstrip("#")
        r = int(hex_color[0:2], 16) / 255.0
        g = int(hex_color[2:4], 16) / 255.0
        b = int(hex_color[4:6], 16) / 255.0
        return (r, g, b)

    # Número
    if num_space in ("CMYK", "SPOT"):
        number_color = tuple(c / 100.0 for c in profile.number_color_cmyk)
    else:
        number_color = hex_to_rgb_normalized(profile.number_color)

    # Prefijo
    if pre_space in ("CMYK", "SPOT"):
        prefix_color = tuple(c / 100.0 for c in profile.prefix_color_cmyk)
    else:
        prefix_color = hex_to_rgb_normalized(profile.prefix_color)

    # Sufijo
    if suf_space in ("CMYK", "SPOT"):
        suffix_color = tuple(c / 100.0 for c in profile.suffix_color_cmyk)
    else:
        suffix_color = hex_to_rgb_normalized(profile.suffix_color)

    # Convertir datos del perfil a formato para PDF
    result = {
        "font_name": profile.font_family,
        "font_style": profile.font_style,  # "Regular", "Bold", "Italic", "Bold Italic", etc.
        "font_size": float(profile.font_size),
        "color_space": color_space,  # legacy
        "number_color_space": num_space,
        "prefix_color_space": pre_space,
        "suffix_color_space": suf_space,
        "number_color": number_color,
        "prefix_color": prefix_color,
        "suffix_color": suffix_color,
        "letter_spacing": profile.letter_spacing,
        "prefix_suffix_spacing": profile.prefix_suffix_spacing,
        "prefix": profile.prefix,
        "suffix": profile.suffix,
        "mask": profile.mask,
        "thousands_separator": (
            profile.thousands_separator
            if hasattr(profile, "thousands_separator")
            else "normal"
        ),
    }

    # Campos de nombre de color (para Separation/SPOT — y también como metadato en RGB/CMYK)
    result["number_color_name"] = getattr(profile, "number_color_name", "") or ""
    result["prefix_color_name"] = getattr(profile, "prefix_color_name", "") or ""
    result["suffix_color_name"] = getattr(profile, "suffix_color_name", "") or ""
    # Valores de tinte (0-100) para Separation/SPOT
    result["number_color_tint"] = float(getattr(profile, "number_color_tint", 100.0))
    result["prefix_color_tint"] = float(getattr(profile, "prefix_color_tint", 100.0))
    result["suffix_color_tint"] = float(getattr(profile, "suffix_color_tint", 100.0))
    # Para SPOT, pasar los CMYK originales (0-100) para poder definir la Separation
    if num_space == "SPOT":
        result["number_color_cmyk_100"] = tuple(profile.number_color_cmyk)
    if pre_space == "SPOT":
        result["prefix_color_cmyk_100"] = tuple(profile.prefix_color_cmyk)
    if suf_space == "SPOT":
        result["suffix_color_cmyk_100"] = tuple(profile.suffix_color_cmyk)

    # Incluir campos de resolución de fuente si están disponibles
    if hasattr(profile, "resolved_font_path") and profile.resolved_font_path:
        result["resolved_font_path"] = profile.resolved_font_path
        if _PRINT_DEBUG:
            print(
                f"[_get_text_style_data] ✓ resolved_font_path: {profile.resolved_font_path}"
            )

        # resolved_font_index solo es necesario para archivos TTC (múltiples fuentes en un archivo)
        # Para TTF/OTF individuales, será None (correcto)
        if (
            hasattr(profile, "resolved_font_index")
            and profile.resolved_font_index is not None
        ):
            result["resolved_font_index"] = profile.resolved_font_index
            if _PRINT_DEBUG:
                print(
                    f"[_get_text_style_data] ✓ resolved_font_index: {profile.resolved_font_index} (fuente TTC)"
                )
        else:
            if _PRINT_DEBUG:
                print(
                    f"[_get_text_style_data]   (no requiere índice - TTF/OTF individual)"
                )
    else:
        if _PRINT_DEBUG:
            print(
                f"[_get_text_style_data] ⚠️ NO tiene resolved_font_path - usará fallback"
            )

    if _PRINT_DEBUG:
        print(f"[_get_text_style_data] Resultado final: {len(result)} campos\n")

    return result
