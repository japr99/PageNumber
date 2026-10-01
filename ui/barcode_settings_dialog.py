"""
Dialogo de configuracion de codigos de barras con gestion de perfiles.
Estructura identica a TextStyleManager: panel izquierdo (lista de perfiles),
panel derecho (secciones), panel de color derecho.
"""

from __future__ import annotations

import os
import re
import sys
import uuid
from dataclasses import dataclass, asdict
from typing import Callable, Dict, List, Optional, Tuple

import flet as ft
from flet import canvas as cv

# Silenciar prints de depuración en este módulo por defecto.
# Para activar, cambiar _PRINT_DEBUG = True durante desarrollo.
_PRINT_DEBUG = False  # Debug desactivado
if not _PRINT_DEBUG:

    def _no_print(*args, **kwargs):
        return None

    print = _no_print

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from color_design import (
    TEXTO_COLOR_GENERICO,
    FONDO_APP,
    FONDO_TEXTFIELDS_COLOR,
    BORDE_TEXTFIELDS_COLOR,
    FONDO_SECCIONES,
    FONDO_ALERT_DIALOG,
    SUCCESS_COLOR,
    ERROR_COLOR,
    BOTONES_GENERICOS_COLOR,
    BOTONES_GENERICOS_TEXTO_COLOR,
    BOTONES_GENERICOS_HOVER_COLOR,
    BOTONES_GENERICOS_OVERLAY_COLOR,
    BOTONES_GENERICOS_FONDO_COLOR,
    FONDO_BLOQUE_RESUMEN_COLOR,
    FONDO_CALCULO_FASE_1,
    TEXTOS_FASE_1_COLOR,
    DROPDOWN_TEXT_STYLE_COLOR,
    DROPDOWN_FONDO_MENU_COLOR,
    DROPDOWN_TRAILING_ICON_COLOR,
    SNACKBAR_COLOR_TEXTO,
    SNACKBAR_COLOR_FONDO,
    SNACKBAR_COLOR_ERROR,
)
from i18n import t
from utils.barcode_module import (
    get_barcode_rects,
    get_module_count,
    get_qr_rects,
    get_qr_module_count,
    validate_code128,
    validate_qr,
    encode_ean13,
    validate_ean13,
    encode_ean8,
    validate_ean8,
    encode_ean5,
    validate_ean5,
    get_ean13_module_count,
    get_ean5_module_count,
    SYMBOLOGY_CONFIG,
    get_ean13_font_descender_ratio,
    get_ean13_font_ascender_ratio,
    get_digit_advance_em,
    validate_isbn13,
    _format_isbn13,
    ISBN_SIZE_OFFSET,
    validate_upca,
    encode_upca,
    validate_upce,
    encode_upce,
    validate_itf14,
    validate_gtin13,
    encode_itf14,
    ITF14_TOTAL_MODULES,
    gtin13_to_gtin14,
    calc_itf14_dimensions,
    format_itf14_hri,
    validate_pdf417,
    get_pdf417_image_b64,
    get_pdf417_barcode_width,
    get_pdf417_max_chars,
    get_qr_image_b64,
    get_max_chars_for_symbology,
    encode_code39,
    validate_code39,
    get_code39_module_count,
    validate_excel_column_for_code39,
    calcular_ancho_fijo_code128,
    calcular_minimo_qr,
    validar_columna_code128,
    validar_longitud_code128,
    validar_columna_qr,
    validar_longitud_qr,
    validar_longitud_code39,
    validar_columna_code39_longitud,
    get_code39_min_width,
    CODE39_MIN_HEIGHT_MM,
    validate_datamatrix,
    validar_columna_datamatrix,
    validar_columna_datamatrix_gs1,
    validar_columna_datamatrix_dl,
    get_datamatrix_image_b64,
    get_datamatrix_min_size,
    get_datamatrix_module_count,
    get_datamatrix_rects,
    get_datamatrix_possible_heights,
    _split_fields,
    detect_field_separator,
    _es_datamatrix_gs1,
    _is_datamatrix_family,
    _is_datamatrix_gs1_symb,
    _parse_gs1_hri,
    _system_font_family_name,
    EAN13_GUARD_MODULES,
    ean_hri_layout,
    ean_hri_max_ds_mm,
    EAN8_GUARD_MODULES,
    get_ean8_module_count,
    UPCE_GUARD_MODULES,
    get_upce_module_count,
    get_upca_module_count,
)
from ui.color_picker import ColorPicker
from ui.color_picker_dialog import ColorPickerDialog
from ui.guia_html_viewer import abrir_guia_barcode
from utils.constants import (
    normalize_decimal_input,
    convert_to_mm,
    format_unit,
)
from ui.interactive_viewer import _apply_mask
from ui.dialog_utils import show_rename_profile_dialog, purge_stale_dialog, reopen_dialog
from utils.variable_text_measure import find_extreme_row

# ============================================================================
# BarcodeProfile dataclass
# ============================================================================


def _normalize_hri_position(value, default: str = "below") -> str:
    """Normalize persisted/display values to internal enum above|below|left|right."""
    if value is None:
        return default
    v = str(value).strip().lower()
    mapping = {
        "above": "above",
        "below": "below",
        "left": "left",
        "right": "right",
        "bellow": "below",  # legacy typo observed in persisted profiles
        "superior": "above",
        "inferior": "below",
        "encima": "above",
        "debajo": "below",
        "arriba": "above",
        "abajo": "below",
        "izquierda": "left",
        "derecha": "right",
        "esquerra": "left",
        "dreta": "right",
    }
    return mapping.get(v, default)


@dataclass
class BarcodeProfile:
    id: str
    name: str
    symbology: str
    value_source: str
    sample_value: str
    excel_column: str
    bar_width: float = 80.0
    bar_height: float = 30.0
    mask: str = ""
    color: str = "#000000"
    color_cmyk: tuple = (0.0, 0.0, 0.0, 100.0)
    color_space: str = "RGB"
    color_name: str = ""
    color_tint: float = 100.0
    text_color: str = "#000000"
    text_color_cmyk: tuple = (0.0, 0.0, 0.0, 100.0)
    text_color_space: str = "RGB"
    text_color_name: str = ""
    text_color_tint: float = 100.0
    error_correction: str = "M"
    barcode_font_family: str = "OCR-B"
    barcode_font_size: float = 13.0
    barcode_font_auto: bool = True
    itf14_quiet_zone_mm: float = 10.16
    itf14_bearer_thickness_mm: float = 4.8
    itf14_bearer_sides: str = "4"
    itf14_gtin_type: str = "gtin14"
    itf14_indicator: str = "1"
    itf14_printer_type: str = "flexografia"
    itf14_hri_gap_mm: float = 2.0
    itf14_hri_position: str = "below"
    code39_hri_gap_mm: float = 2.0
    code39_hri_position: str = "below"
    code128_hri_gap_mm: float = 2.0
    code128_hri_position: str = "below"
    ean5_hri_gap_mm: float = 2.0
    isbn13_show_title: str = "Sí"
    pdf417_size: float = 65.0
    pdf417_height: float = 30.0
    pdf417_min_width: float = 0.0
    pdf417_min_height: float = 0.0
    pdf417_hri_gap_mm: float = 2.0
    pdf417_hri_position: str = "below"
    pdf417_hri_align: str = "bottom_center"
    pdf417_hri_line_spacing: float = 1.0
    pdf417_del_open: str = ""
    pdf417_del_close: str = ""
    pdf417_del_close_newline: bool = False
    datamatrix_width: float = 20.0
    datamatrix_height: float = 20.0
    datamatrix_format: str = ""
    datamatrix_hri_gap_mm: float = 2.0
    datamatrix_hri_position: str = "below"
    datamatrix_hri_align: str = "bottom_center"
    datamatrix_hri_line_spacing: float = 1.0
    datamatrix_min_width: float = 0.0
    datamatrix_min_height: float = 0.0
    datamatrix_longest_value: str = ""
    datamatrix_del_open: str = ""
    datamatrix_del_close: str = ""
    datamatrix_del_close_newline: bool = False
    code128_min_width: float = 0.0
    code39_min_width: float = 0.0
    qr_min_size: float = 0.0
    qr_hri_gap_mm: float = 2.0
    qr_hri_position: str = "below"
    qr_hri_align: str = "bottom_center"
    qr_hri_line_spacing: float = 1.0
    qr_del_open: str = ""
    qr_del_close: str = ""
    qr_del_close_newline: bool = False

    def copy(self) -> "BarcodeProfile":
        return BarcodeProfile(
            id=self.id,
            name=self.name,
            symbology=self.symbology,
            value_source=self.value_source,
            sample_value=self.sample_value,
            excel_column=self.excel_column,
            mask=self.mask,
            bar_width=self.bar_width,
            bar_height=self.bar_height,
            color=self.color,
            color_cmyk=self.color_cmyk,
            color_space=self.color_space,
            color_name=self.color_name,
            color_tint=self.color_tint,
            text_color=self.text_color,
            text_color_cmyk=self.text_color_cmyk,
            text_color_space=self.text_color_space,
            text_color_name=self.text_color_name,
            text_color_tint=self.text_color_tint,
            error_correction=self.error_correction,
            barcode_font_family=self.barcode_font_family,
            barcode_font_size=self.barcode_font_size,
            barcode_font_auto=self.barcode_font_auto,
            itf14_quiet_zone_mm=self.itf14_quiet_zone_mm,
            itf14_bearer_thickness_mm=self.itf14_bearer_thickness_mm,
            itf14_bearer_sides=self.itf14_bearer_sides,
            itf14_gtin_type=self.itf14_gtin_type,
            itf14_indicator=self.itf14_indicator,
            itf14_printer_type=self.itf14_printer_type,
            itf14_hri_gap_mm=self.itf14_hri_gap_mm,
            itf14_hri_position=self.itf14_hri_position,
            code39_hri_gap_mm=self.code39_hri_gap_mm,
            code39_hri_position=self.code39_hri_position,
            code128_hri_gap_mm=self.code128_hri_gap_mm,
            code128_hri_position=self.code128_hri_position,
            ean5_hri_gap_mm=self.ean5_hri_gap_mm,
            isbn13_show_title=self.isbn13_show_title,
            pdf417_size=self.pdf417_size,
            pdf417_height=self.pdf417_height,
            pdf417_min_width=self.pdf417_min_width,
            pdf417_min_height=self.pdf417_min_height,
            pdf417_hri_gap_mm=self.pdf417_hri_gap_mm,
            pdf417_hri_position=self.pdf417_hri_position,
            pdf417_hri_align=self.pdf417_hri_align,
            pdf417_hri_line_spacing=self.pdf417_hri_line_spacing,
            pdf417_del_open=self.pdf417_del_open,
            pdf417_del_close=self.pdf417_del_close,
            pdf417_del_close_newline=self.pdf417_del_close_newline,
            datamatrix_width=self.datamatrix_width,
            datamatrix_height=self.datamatrix_height,
            datamatrix_format=self.datamatrix_format,
            datamatrix_hri_gap_mm=self.datamatrix_hri_gap_mm,
            datamatrix_hri_position=self.datamatrix_hri_position,
            datamatrix_hri_align=self.datamatrix_hri_align,
            datamatrix_hri_line_spacing=self.datamatrix_hri_line_spacing,
            datamatrix_min_width=self.datamatrix_min_width,
            datamatrix_min_height=self.datamatrix_min_height,
            datamatrix_longest_value=self.datamatrix_longest_value,
            datamatrix_del_open=self.datamatrix_del_open,
            datamatrix_del_close=self.datamatrix_del_close,
            datamatrix_del_close_newline=self.datamatrix_del_close_newline,
            code128_min_width=self.code128_min_width,
            code39_min_width=self.code39_min_width,
            qr_min_size=self.qr_min_size,
            qr_hri_gap_mm=self.qr_hri_gap_mm,
            qr_hri_position=self.qr_hri_position,
            qr_hri_align=self.qr_hri_align,
            qr_hri_line_spacing=self.qr_hri_line_spacing,
            qr_del_open=self.qr_del_open,
            qr_del_close=self.qr_del_close,
            qr_del_close_newline=self.qr_del_close_newline,
        )

    @staticmethod
    def create_default(name: str = "<Default>") -> "BarcodeProfile":
        return BarcodeProfile(
            id=str(uuid.uuid4()),
            name=name,
            symbology="code128",
            value_source="fixed",
            sample_value="123ABC",
            excel_column="",
            mask="",
            bar_width=80.0,
            bar_height=30.0,
            color="#000000",
            error_correction="M",
            barcode_font_family="OCR-B",
            barcode_font_size=13.0,
        )

    def to_dict(self) -> dict:
        d = asdict(self)
        d["color_cmyk"] = list(self.color_cmyk)
        return d

    @staticmethod
    def from_dict(data: dict) -> "BarcodeProfile":
        valid_fields = {
            "id",
            "name",
            "symbology",
            "value_source",
            "sample_value",
            "excel_column",
            "bar_width",
            "bar_height",
            "mask",
            "color",
            "color_cmyk",
            "color_space",
            "color_name",
            "color_tint",
            "text_color",
            "text_color_cmyk",
            "text_color_space",
            "text_color_name",
            "text_color_tint",
            "error_correction",
            "barcode_font_family",
            "barcode_font_size",
            "barcode_font_auto",
            "itf14_quiet_zone_mm",
            "itf14_bearer_thickness_mm",
            "itf14_bearer_sides",
            "itf14_gtin_type",
            "itf14_indicator",
            "itf14_printer_type",
            "itf14_hri_gap_mm",
            "itf14_hri_position",
            "code39_hri_gap_mm",
            "code39_hri_position",
            "code128_hri_gap_mm",
            "code128_hri_position",
            "ean5_hri_gap_mm",
            "isbn13_show_title",
            "pdf417_size",
            "pdf417_height",
            "pdf417_min_width",
            "pdf417_min_height",
            "pdf417_hri_gap_mm",
            "pdf417_hri_position",
            "pdf417_hri_align",
            "pdf417_hri_line_spacing",
            "pdf417_del_open",
            "pdf417_del_close",
            "pdf417_del_close_newline",
            "datamatrix_width",
            "datamatrix_height",
            "datamatrix_format",
            "datamatrix_hri_gap_mm",
            "datamatrix_hri_position",
            "datamatrix_hri_align",
            "datamatrix_hri_line_spacing",
            "datamatrix_min_width",
            "datamatrix_min_height",
            "datamatrix_longest_value",
            "datamatrix_del_open",
            "datamatrix_del_close",
            "datamatrix_del_close_newline",
            "code128_min_width",
            "code39_min_width",
            "qr_min_size",
            "qr_hri_gap_mm",
            "qr_hri_position",
            "qr_hri_align",
            "qr_hri_line_spacing",
            "qr_del_open",
            "qr_del_close",
            "qr_del_close_newline",
        }
        data = {k: v for k, v in data.items() if k in valid_fields}
        if "color" not in data or data["color"] is None:
            data["color"] = "#000000"
        if "color_cmyk" not in data or data["color_cmyk"] is None:
            from ui.color_picker import hex2rgb, rgb_to_cmyk

            r, g, b = hex2rgb(data["color"])
            data["color_cmyk"] = rgb_to_cmyk(r, g, b)
        else:
            data["color_cmyk"] = tuple(data["color_cmyk"])
        if "color_space" not in data:
            data["color_space"] = "RGB"
        if "color_name" not in data:
            data["color_name"] = ""
        if "color_tint" not in data:
            data["color_tint"] = 100.0
        if "text_color" not in data or data["text_color"] is None:
            data["text_color"] = "#000000"
        if "text_color_cmyk" not in data or data["text_color_cmyk"] is None:
            from ui.color_picker import hex2rgb, rgb_to_cmyk

            r, g, b = hex2rgb(data["text_color"])
            data["text_color_cmyk"] = rgb_to_cmyk(r, g, b)
        else:
            data["text_color_cmyk"] = tuple(data["text_color_cmyk"])
        if "text_color_space" not in data:
            data["text_color_space"] = "RGB"
        if "text_color_name" not in data:
            data["text_color_name"] = ""
        if "text_color_tint" not in data:
            data["text_color_tint"] = 100.0
        if "mask" not in data:
            data["mask"] = ""
        if "error_correction" not in data:
            data["error_correction"] = "M"
        if "itf14_quiet_zone_mm" not in data:
            data["itf14_quiet_zone_mm"] = 10.16
        if "itf14_bearer_thickness_mm" not in data:
            data["itf14_bearer_thickness_mm"] = 4.8
        if "itf14_bearer_sides" not in data:
            data["itf14_bearer_sides"] = "4"
        if "itf14_gtin_type" not in data:
            data["itf14_gtin_type"] = "gtin14"
        if "itf14_indicator" not in data:
            data["itf14_indicator"] = "1"
        if "itf14_printer_type" not in data:
            data["itf14_printer_type"] = "flexografia"
        if "itf14_hri_gap_mm" not in data:
            data["itf14_hri_gap_mm"] = 2.0
        if "itf14_hri_position" not in data:
            data["itf14_hri_position"] = "below"
        data["itf14_hri_position"] = _normalize_hri_position(
            data.get("itf14_hri_position")
        )
        if "code39_hri_position" not in data:
            data["code39_hri_position"] = "below"
        data["code39_hri_position"] = _normalize_hri_position(
            data.get("code39_hri_position")
        )
        if "code128_hri_position" not in data:
            data["code128_hri_position"] = "below"
        data["code128_hri_position"] = _normalize_hri_position(
            data.get("code128_hri_position")
        )
        if "pdf417_size" not in data:
            data["pdf417_size"] = 65.0
        if "pdf417_height" not in data:
            data["pdf417_height"] = 30.0
        if "datamatrix_width" not in data:
            data["datamatrix_width"] = 20.0
        if "datamatrix_height" not in data:
            data["datamatrix_height"] = 20.0
        if "datamatrix_format" not in data:
            data["datamatrix_format"] = ""
        if "datamatrix_hri_gap_mm" not in data:
            data["datamatrix_hri_gap_mm"] = 2.0
        if "datamatrix_hri_position" not in data:
            data["datamatrix_hri_position"] = "below"
        data["datamatrix_hri_position"] = _normalize_hri_position(
            data.get("datamatrix_hri_position")
        )
        _DM_ALIGNS = {
            "top_left", "top_center", "top_right",
            "middle_left", "middle_center", "middle_right",
            "bottom_left", "bottom_center", "bottom_right",
        }
        if "datamatrix_hri_align" not in data:
            data["datamatrix_hri_align"] = "bottom_center"
        _align_val = str(data.get("datamatrix_hri_align", "bottom_center")).strip().lower()
        if _align_val not in _DM_ALIGNS:
            _align_val = "bottom_center"
        data["datamatrix_hri_align"] = _align_val
        if "datamatrix_hri_line_spacing" not in data:
            data["datamatrix_hri_line_spacing"] = 1.0
        try:
            data["datamatrix_hri_line_spacing"] = float(data["datamatrix_hri_line_spacing"])
        except (TypeError, ValueError):
            data["datamatrix_hri_line_spacing"] = 1.0
        if "pdf417_hri_gap_mm" not in data:
            data["pdf417_hri_gap_mm"] = 2.0
        if "pdf417_hri_position" not in data:
            data["pdf417_hri_position"] = "below"
        data["pdf417_hri_position"] = _normalize_hri_position(
            data.get("pdf417_hri_position")
        )
        if "pdf417_hri_align" not in data:
            data["pdf417_hri_align"] = "bottom_center"
        _align_val = str(data.get("pdf417_hri_align", "bottom_center")).strip().lower()
        if _align_val not in _DM_ALIGNS:
            _align_val = "bottom_center"
        data["pdf417_hri_align"] = _align_val
        if "pdf417_hri_line_spacing" not in data:
            data["pdf417_hri_line_spacing"] = 1.0
        try:
            data["pdf417_hri_line_spacing"] = float(data["pdf417_hri_line_spacing"])
        except (TypeError, ValueError):
            data["pdf417_hri_line_spacing"] = 1.0
        if "qr_hri_gap_mm" not in data:
            data["qr_hri_gap_mm"] = 2.0
        if "qr_hri_position" not in data:
            data["qr_hri_position"] = "below"
        data["qr_hri_position"] = _normalize_hri_position(
            data.get("qr_hri_position")
        )
        if "qr_hri_align" not in data:
            data["qr_hri_align"] = "bottom_center"
        _align_val = str(data.get("qr_hri_align", "bottom_center")).strip().lower()
        if _align_val not in _DM_ALIGNS:
            _align_val = "bottom_center"
        data["qr_hri_align"] = _align_val
        if "qr_hri_line_spacing" not in data:
            data["qr_hri_line_spacing"] = 1.0
        try:
            data["qr_hri_line_spacing"] = float(data["qr_hri_line_spacing"])
        except (TypeError, ValueError):
            data["qr_hri_line_spacing"] = 1.0
        for _dl_key, _dl_default in (
            ("datamatrix_del_open", ""),
            ("datamatrix_del_close", ""),
            ("datamatrix_del_close_newline", False),
            ("pdf417_del_open", ""),
            ("pdf417_del_close", ""),
            ("pdf417_del_close_newline", False),
            ("qr_del_open", ""),
            ("qr_del_close", ""),
            ("qr_del_close_newline", False),
        ):
            if _dl_key not in data:
                data[_dl_key] = _dl_default
        return BarcodeProfile(**data)


VALUE_SOURCE_OPTIONS = [
    ("fixed", t("Texto fijo")),
    ("excel", t("Columna datos externos")),
    ("numbering", t("Numeracion interna")),
]

SYMBOLOGY_OPTIONS = [
    ("qr", t("QR Code")),
    ("pdf417", t("PDF417")),
    ("datamatrix", t("DataMatrix")),
    ("datamatrix_gs1", t("GS1 DataMatrix")),
    ("datamatrix_dl", t("DataMatrix GS1 Digital Link")),
    ("code128", t("Code 128")),
    ("code39", t("Code 39")),
    ("ean5", t("EAN-5")),
    ("ean8", t("EAN-8")),
    ("ean13", t("EAN-13")),
    ("upca", t("UPC-A")),
    ("upce", t("UPC-E")),
    ("isbn13", t("ISBN-13")),
    ("itf14", t("ITF-14")),
]

ITF14_GTIN_OPTIONS = [
    ("gtin14", t("GTIN-14")),
    ("gtin13", t("GTIN-13")),
]
ITF14_PRINTER_OPTIONS = [
    ("flexografia", "Flexo"),
    ("termica", t("Térmica")),
    ("laser", t("Láser")),
]


# ============================================================================
# BarcodeProfileManager
# ============================================================================


class _FakeEvent:
    def __init__(self, control):
        self.control = control


class BarcodeProfileManager:
    """
    Gestor de perfiles de codigo de barras con interfaz de dialogo.
    Estructura identica a TextStyleManager: lista de perfiles + panel de configuracion.
    """

    def __init__(
        self,
        page: ft.Page,
        on_profile_changed: Optional[Callable] = None,
        viewer_callback=None,
        get_global_settings_fn: Optional[Callable] = None,
        excel_manager=None,
        get_unit_fn: Optional[Callable] = None,
        on_row_change: Optional[Callable] = None,
        on_profile_renamed: Optional[Callable] = None,
    ):
        self.page = page
        self.on_profile_changed = on_profile_changed
        self.on_profile_renamed = on_profile_renamed
        self.viewer_callback = viewer_callback
        self.get_global_settings = get_global_settings_fn or (lambda: {})
        self.excel_manager = excel_manager
        self._get_unit = get_unit_fn or (lambda: "mm")
        self.on_row_change = on_row_change

        # Estado
        self.profiles: list[BarcodeProfile] = [BarcodeProfile.create_default()]
        self.selected_profile_index: int = 0
        self.current_profile: BarcodeProfile = self.profiles[0]

        # Colores spot acumulados (propagados al picker)
        self.extracted_spot_colors: list = []
        self.color_picker_dialog = None  # creado de forma lazy
        self._color_target = "bar"  # "bar" | "text" — qué color edita el picker

        # UI refs - panel izquierdo
        self.profile_list: Optional[ft.ListView] = None
        self.btn_new_profile: Optional[ft.IconButton] = None
        self.btn_delete_profile: Optional[ft.IconButton] = None

        # UI refs - panel derecho
        self._symbology_dropdown: Optional[ft.Container] = None
        self._preview_row_index: int = 0
        self._pending_initial_row: Optional[int] = None
        self._preview_row_prev: Optional[ft.Container] = None
        self._preview_row_counter: Optional[ft.TextField] = None
        self._preview_row_next: Optional[ft.Container] = None
        self._preview_row_nav: Optional[ft.Row] = None
        self._value_source_dropdown: Optional[ft.Container] = None
        self._sample_field: Optional[ft.TextField] = None
        self._pdf417_sample_btn: Optional[ft.Button] = None
        self._generic_sample_btn: Optional[ft.Button] = None
        self._generic_old_value: str = ""
        self._generic_popup_tf: Optional[ft.TextField] = None
        self._generic_error_text: Optional[ft.Text] = None
        self._generic_error_container: Optional[ft.Container] = None
        self._generic_counter: Optional[ft.Text] = None
        self._generic_max_chars: int = 0
        self._qr_sample_btn: Optional[ft.Button] = None
        self._datamatrix_sample_btn: Optional[ft.Button] = None
        self._datamatrix_del_open_field: Optional[ft.TextField] = None
        self._datamatrix_del_close_field: Optional[ft.TextField] = None
        self._datamatrix_del_recalc_btn: Optional[ft.Button] = None
        self._datamatrix_gs1_label: Optional[ft.Text] = None
        self._gs1_by_symb: dict = {
            "datamatrix": False,
            "datamatrix_gs1": False,
            "datamatrix_dl": False,
            "qr": False,
            "pdf417": False,
        }
        self._field_popup: Optional[dict] = None
        self._datamatrix_possible: list = []
        self._excel_column_dropdown: Optional[ft.Container] = None
        self._excel_columns: List[str] = []
        self._mask_field: Optional[ft.TextField] = None
        self._mask_container: Optional[ft.Container] = None
        self._symbology_fields: Dict[str, ft.Control] = (
            {}
        )  # dynamic fields from SYMBOLOGY_CONFIG
        self._dim_fields_section: Optional[ft.Container] = None
        self._error_text: Optional[ft.Text] = None
        self._preview_container: Optional[ft.Container] = None
        self._preview_img: Optional[ft.Image] = None
        self._preview_canvas_mm: Optional[tuple] = None  # (canvas_w_mm, canvas_h_mm) QR/DM/PDF417

        # UI refs - color panel
        self._color_swatch_button: Optional[ft.Container] = None
        self._text_color_swatch_button: Optional[ft.Container] = None

        # Zoom
        self._zoom_value: float = 100.0
        self._zoom_slider: Optional[ft.Slider] = None
        self._zoom_label: Optional[ft.Text] = None

        # Dialogo
        self.dialog: Optional[ft.AlertDialog] = None
        self.dialog_root_stack: Optional[ft.Stack] = None

        # Enter key handler for PDF417 field validation (installed in open())
        self._pdf417_enter_target: Optional[ft.TextField] = None
        # Campo ancho DataMatrix con foco (confirma con Enter/blur)
        self._datamatrix_width_target: Optional[ft.TextField] = None
        # Campo de datos (muestra/máscara) con foco: el cálculo se hace al salir
        self._data_text_focus_target: Optional[ft.TextField] = None
        self._saved_keyboard_handler = None

        # Cargar perfiles desde preferencias
        self.load_from_preferences()

    # ------------------------------------------------------------------
    # Unit conversion helpers
    # ------------------------------------------------------------------
    def _unit_abbr(self) -> str:
        return {"mm": "mm", "px": "px", "pulgadas": "in", "picas": "pc"}.get(
            self._get_unit(), "mm"
        )

    def _display_mm(self, value_mm: float) -> str:
        return format_unit(value_mm, self._get_unit())

    def _save_to_mm(self, ui_value: str) -> float:
        return convert_to_mm(float(ui_value), self._get_unit())

    # ------------------------------------------------------------------
    # Enter key handler for PDF417 field validation
    # ------------------------------------------------------------------

    def _on_page_keyboard(self, e: ft.KeyboardEvent):
        if e.key in ("Enter", "Numpad Enter", "Tab"):
            if self._pdf417_enter_target is not None:
                self._on_pdf417_field_enter(self._pdf417_enter_target)
            elif self._data_text_focus_target is not None:
                self._on_data_text_commit()
        elif e.key == "Escape" and self._data_text_focus_target is not None:
            self._on_data_text_commit()

    def _on_data_text_commit(self, *_):
        """Punto único de cálculo al salir de muestra/máscara (blur, Enter o Tab)."""
        self._data_text_focus_target = None
        self._sync_fields_to_profile()
        self.current_profile.barcode_font_auto = True
        self._apply_datamatrix_font_auto()
        self._recalculate_minimums()
        self._on_preview_trigger(None)

    def _symb_del_keys(self) -> str:
        """Devuelve el symbology con separadores de campo (datamatrix/qr/pdf417) o ''."""
        symb = self.current_profile.symbology
        return (
            symb
            if (_is_datamatrix_family(symb) or symb in ("qr", "pdf417"))
            else ""
        )

    def _on_excel_column_changed(self, selected_data):
        """Columna de datos externos cambiada → recalcular el mínimo sobre la nueva columna."""
        self.current_profile.excel_column = selected_data or ""
        symb = self._symb_del_keys()
        if symb:
            if selected_data:
                if _is_datamatrix_family(symb):
                    self.current_profile.barcode_font_auto = True
                self._auto_detect_separators()
            else:
                self._gs1_by_symb[symb] = False
                self._apply_delims_visibility()
        self._on_preview_trigger(selected_data)
        self._recalculate_minimums()
        self._on_preview_trigger(None)
        if self.on_profile_changed:
            self.on_profile_changed(self.current_profile)

    def _on_datamatrix_delimiters_change(self, e=None):
        """Aplicar apertura/cierre editada al perfil y refrescar el preview."""
        symb = self._symb_del_keys()
        if not symb:
            return
        if self._datamatrix_del_open_field is not None:
            setattr(
                self.current_profile,
                f"{symb}_del_open",
                self._datamatrix_del_open_field.value or "",
            )
        if self._datamatrix_del_close_field is not None:
            setattr(
                self.current_profile,
                f"{symb}_del_close",
                self._datamatrix_del_close_field.value or "",
            )
        self._update_preview()
        if self.on_profile_changed:
            self.on_profile_changed(self.current_profile)

    def _on_del_close_newline_change(self, e):
        """Check 'Cierre = salto de línea': guarda en el perfil del symb y refresca."""
        symb = self._symb_del_keys()
        if not symb:
            return
        setattr(
            self.current_profile,
            f"{symb}_del_close_newline",
            bool(e.control.value),
        )
        self._update_preview()
        if self.on_profile_changed:
            self.on_profile_changed(self.current_profile)

    def _auto_detect_separators(self):
        """Propone apertura/cierre del symb actual analizando la similitud entre
        filas de la columna seleccionada. Los modos explícitos GS1/URI no necesitan
        separadores; el resto (texto libre/qr/pdf417) los propone."""
        symb = self._symb_del_keys()
        if not symb:
            return
        # Modos explícitos por ID: GS1 u URI → sin separadores propuestos
        if _is_datamatrix_gs1_symb(symb):
            self._gs1_by_symb[symb] = True
            self._apply_delims_visibility()
            return
        if symb == "datamatrix_dl":
            self._gs1_by_symb[symb] = False
            self._apply_delims_visibility()
            return
        # Texto libre / qr / pdf417: nunca GS1 por contenido
        values = self._get_datamatrix_values()
        self._gs1_by_symb[symb] = False
        if not values:
            self._apply_delims_visibility()
            if _is_datamatrix_family(symb):
                self._apply_datamatrix_font_auto()
            return
        open_del, close_del = detect_field_separator(values)
        setattr(self.current_profile, f"{symb}_del_open", open_del)
        setattr(self.current_profile, f"{symb}_del_close", close_del or "")
        self._apply_delims_visibility()
        if _is_datamatrix_family(symb):
            self._apply_datamatrix_font_auto()

    def _apply_datamatrix_font_auto(self):
        """Si el perfil está en modo auto, fija la fuente HRI por defecto según GS1:
        GS1 -> OCR-B; no GS1 -> fuente del sistema (Helvetica/Arial) para acentos."""
        p = self.current_profile
        if not _is_datamatrix_family(p.symbology) or not p.barcode_font_auto:
            return
        if _is_datamatrix_gs1_symb(p.symbology):
            target = "OCR-B"
        else:
            target = _system_font_family_name()
        if p.barcode_font_family == target:
            return
        p.barcode_font_family = target
        dd = self._symbology_fields.get("barcode_font_family")
        if dd is not None:
            try:
                t = dd.content.controls[0]
                t.value = target
                t.data = target
                t.update()
            except Exception:
                pass
        if self.on_profile_changed:
            self.on_profile_changed(p)

    def _on_datamatrix_recalc_click(self, e=None):
        """Restaura la auto-detección (separadores + fuente) de la columna actual."""
        if not self._symb_del_keys() or not self.current_profile.excel_column:
            return
        if _is_datamatrix_family(self.current_profile.symbology):
            self.current_profile.barcode_font_auto = True
        self._auto_detect_separators()
        self._update_preview()
        if self.on_profile_changed:
            self.on_profile_changed(self.current_profile)

    def _on_pdf417_field_enter(self, tf: ft.TextField):
        key = tf.data
        if key not in ("pdf417_size", "pdf417_height"):
            return
        normalize_decimal_input(_FakeEvent(tf))
        min_w, min_h = self._compute_pdf417_min_dimensions()
        self.current_profile.pdf417_min_width = min_w
        self.current_profile.pdf417_min_height = min_h
        val_str = tf.value
        if not val_str:
            min_val = str(self._display_mm(min_w if key == "pdf417_size" else min_h))
            tf.value = min_val
            tf.update()
        else:
            try:
                val_mm = self._save_to_mm(val_str)
            except (ValueError, TypeError):
                min_val = str(
                    self._display_mm(min_w if key == "pdf417_size" else min_h)
                )
                tf.value = min_val
                tf.update()
                val_mm = min_w if key == "pdf417_size" else min_h
            else:
                min_val_mm = min_w if key == "pdf417_size" else min_h
                if val_mm < min_val_mm:
                    val_mm = min_val_mm
                    tf.value = str(self._display_mm(min_val_mm))
                    tf.update()
            if key == "pdf417_size":
                self.current_profile.pdf417_size = val_mm
                self.current_profile.bar_width = val_mm
            else:
                self.current_profile.pdf417_height = val_mm
        # Only trigger preview without re-entering data-source branch
        self._on_preview_trigger(_FakeEvent(tf))

    def _on_datamatrix_field_enter(self, tf: ft.TextField):
        key = tf.data
        if key != "datamatrix_width":
            return
        normalize_decimal_input(_FakeEvent(tf))
        p = self.current_profile
        self._ensure_profile_minimums()
        min_w = p.datamatrix_min_width or 20.0
        print(
            f"[DM-MIN] field_enter key={key} input={tf.value!r} "
            f"min_w={min_w:.2f} cur={p.datamatrix_width:.2f}"
        )
        val_str = tf.value
        if not val_str:
            min_val = str(self._display_mm(min_w))
            tf.value = min_val
            tf.update()
        else:
            try:
                val_mm = self._save_to_mm(val_str)
            except (ValueError, TypeError):
                min_val = str(self._display_mm(min_w))
                tf.value = min_val
                tf.update()
                val_mm = min_w
            else:
                if val_mm < min_w:
                    val_mm = min_w
            if abs(val_mm - p.datamatrix_width) < 0.001:
                new_disp = str(self._display_mm(val_mm))
                if tf.value != new_disp:
                    tf.value = new_disp
                    tf.update()
                return
            p.datamatrix_width = val_mm
        self._on_datamatrix_height_recalculate()
        self._on_preview_trigger(_FakeEvent(tf))

    def _on_datamatrix_height_change(self, val: str, possible: list):
        """Called when user selects a height from the dropdown."""
        try:
            val_mm = float(val)
        except (ValueError, TypeError):
            return
        self.current_profile.datamatrix_height = val_mm
        for h, fmt in possible:
            if abs(h - val_mm) < 0.05:
                self.current_profile.datamatrix_format = fmt
                break
        self._on_preview_trigger(_FakeEvent(None))

    def _on_datamatrix_height_recalculate(self):
        """Recalculate height dropdown options when Ancho or data changes."""
        p = self.current_profile
        values = [p.datamatrix_longest_value] if p.datamatrix_longest_value else []
        if not values:
            values = [p.sample_value] if p.sample_value else [""]
        ancho = p.datamatrix_width or 20.0
        possible = get_datamatrix_possible_heights(values, ancho)
        if not possible:
            possible = [(20.0, "square")]
        self._datamatrix_possible = possible
        current_h = float(self.current_profile.datamatrix_height or 0)
        best_h, best_fmt = possible[0]
        for h, fmt in possible:
            if abs(h - (current_h or 0)) < abs(best_h - (current_h or 0)):
                best_h, best_fmt = h, fmt
        self.current_profile.datamatrix_height = best_h
        self.current_profile.datamatrix_format = best_fmt
        dd = self._get_field("datamatrix_height")
        if dd is None:
            return
        options = [(f"{h:.1f}", self._display_mm(h)) for h, fmt in possible]
        texto = dd.content.controls[0]
        texto.value = self._display_mm(best_h)
        texto.data = f"{best_h:.1f}"
        menu_btn = dd.content.controls[1]
        menu_btn.items = [
            ft.PopupMenuItem(content=label, data=data) for data, label in options
        ]
        for item in menu_btn.items:
            item.on_click = self._on_datamatrix_menu_click
        try:
            dd.update()
        except Exception:
            pass

    def _ensure_profile_minimums(self):
        """Rellena los mínimos cacheados del perfil si están vacíos (perfiles antiguos).

        NO toca ancho/alto actuales: los mínimos solo se reescriben al recalcular
        (`_recalculate_minimums`) cuando cambia la fuente de datos.
        """
        p = self.current_profile
        s = p.symbology
        if _is_datamatrix_family(s) and not (
            p.datamatrix_min_width and p.datamatrix_longest_value
        ):
            values = self._get_datamatrix_values()
            if values:
                p.datamatrix_min_width, p.datamatrix_min_height = (
                    get_datamatrix_min_size(values)
                )
                p.datamatrix_longest_value = max(
                    (v for v in values if v), key=len, default=""
                )
        elif s == "qr" and not p.qr_min_size:
            values = self._get_qr_values()
            if values:
                p.qr_min_size = calcular_minimo_qr(values)
        elif s == "code128" and not p.code128_min_width:
            values = self._get_code128_values()
            if values:
                p.code128_min_width = min(
                    165.10, calcular_ancho_fijo_code128(values)
                )
        elif s == "code39" and not p.code39_min_width:
            values = self._get_code39_values()
            if values:
                p.code39_min_width = get_code39_min_width(values)

    def _recalculate_minimums(self):
        """Actualiza los mínimos dinámicos de la fuente de datos actual y
        sube el tamaño hasta ese mínimo SOLO si el actual queda por debajo
        (nunca baja un tamaño elegido por el usuario).

        Se llama cuando cambia la fuente de datos (simbología, origen, columna,
        muestra o máscara). Solo aplica a simbologías con mínimo dinámico;
        las de mínimo fijo (EAN/UPC/ISBN/ITF-14) no dependen de los datos.
        """
        p = self.current_profile
        s = p.symbology
        if _is_datamatrix_family(s):
            values = self._get_datamatrix_values()
            min_w, min_h = (
                get_datamatrix_min_size(values) if values else (20.0, 20.0)
            )
            p.datamatrix_min_width = min_w
            p.datamatrix_min_height = min_h
            longest = max((v for v in values if v), key=len, default="")
            p.datamatrix_longest_value = longest
            if p.datamatrix_width is None or p.datamatrix_width < min_w:
                p.datamatrix_width = min_w
            self._set_field_value(
                "datamatrix_width", str(self._display_mm(p.datamatrix_width))
            )
            self._on_datamatrix_height_recalculate()
        elif s == "pdf417":
            min_w, min_h = self._compute_pdf417_min_dimensions()
            p.pdf417_min_width = min_w
            p.pdf417_min_height = min_h
            if p.pdf417_size is None or p.pdf417_size < min_w:
                p.pdf417_size = min_w
            if p.pdf417_height is None or p.pdf417_height < min_h:
                p.pdf417_height = min_h
            p.bar_width = p.pdf417_size
            self._set_field_value("pdf417_size", f"{p.pdf417_size:.1f}")
            self._set_field_value("pdf417_height", f"{p.pdf417_height:.1f}")
        elif s == "qr":
            values = self._get_qr_values()
            min_w = calcular_minimo_qr(values) if values else 20.0
            p.qr_min_size = min_w
            if p.bar_width is None or p.bar_width < min_w:
                p.bar_width = min_w
            p.bar_height = p.bar_width
            self._set_field_value("qr_size", self._display_mm(p.bar_width))
        elif s == "code128":
            values = self._get_code128_values()
            min_w = min(165.10, calcular_ancho_fijo_code128(values)) if values else 40.0
            p.code128_min_width = min_w
            if p.bar_width is None or p.bar_width < min_w:
                p.bar_width = min_w
            self._set_field_value("bar_width", str(self._display_mm(p.bar_width)))
        elif s == "code39":
            values = self._get_code39_values()
            min_w = get_code39_min_width(values) if values else 40.0
            p.code39_min_width = min_w
            if p.bar_width is None or p.bar_width < min_w:
                p.bar_width = min_w
            self._set_field_value("bar_width", self._display_mm(p.bar_width))
        try:
            self.dialog.update()
        except Exception:
            pass

    def _on_datamatrix_menu_click(self, e):
        """Handle click on a datamatrix height dropdown item."""
        selected_data = e.control.data
        selected_text = e.control.content
        dd = self._get_field("datamatrix_height")
        if dd is None:
            return
        texto = dd.content.controls[0]
        texto.value = selected_text
        texto.data = selected_data
        try:
            texto.update()
        except Exception:
            pass
        self._on_datamatrix_height_change(selected_data, self._datamatrix_possible)

    def _on_upca_field_enter(self, tf):
        key = tf.data
        if key not in ("bar_width", "bar_height"):
            return
        normalize_decimal_input(_FakeEvent(tf))
        raw = tf.value.strip()
        if not raw:
            return
        try:
            display_val = float(raw)
        except ValueError:
            return
        val_mm = self._save_to_mm(display_val)
        if key == "bar_width":
            val_mm = max(29.83, val_mm)
            self.current_profile.bar_width = val_mm
        else:
            val_mm = max(20.73, val_mm)
            self.current_profile.bar_height = val_mm
        tf.value = self._display_mm(val_mm)
        tf.update()
        self._on_preview_trigger(_FakeEvent(tf))

    def _on_upce_field_enter(self, tf):
        key = tf.data
        if key not in ("bar_width", "bar_height"):
            return
        normalize_decimal_input(_FakeEvent(tf))
        raw = tf.value.strip()
        if not raw:
            return
        try:
            display_val = float(raw)
        except ValueError:
            return
        val_mm = self._save_to_mm(display_val)
        if key == "bar_width":
            val_mm = max(17.69, val_mm)
            self.current_profile.bar_width = val_mm
        else:
            val_mm = max(20.73, val_mm)
            self.current_profile.bar_height = val_mm
        tf.value = self._display_mm(val_mm)
        tf.update()
        self._on_preview_trigger(_FakeEvent(tf))

    def _on_ean13_field_enter(self, tf):
        key = tf.data
        if key not in ("bar_width", "bar_height"):
            return
        normalize_decimal_input(_FakeEvent(tf))
        raw = tf.value.strip()
        if not raw:
            return
        try:
            display_val = float(raw)
        except ValueError:
            return
        val_mm = self._save_to_mm(display_val)
        if key == "bar_width":
            val_mm = max(29.83, val_mm)
            self.current_profile.bar_width = val_mm
        else:
            val_mm = max(20.73, val_mm)
            self.current_profile.bar_height = val_mm
        tf.value = self._display_mm(val_mm)
        tf.update()
        self._on_preview_trigger(_FakeEvent(tf))

    def _on_ean8_field_enter(self, tf):
        key = tf.data
        if key not in ("bar_width", "bar_height"):
            return
        normalize_decimal_input(_FakeEvent(tf))
        raw = tf.value.strip()
        if not raw:
            return
        try:
            display_val = float(raw)
        except ValueError:
            return
        val_mm = self._save_to_mm(display_val)
        if key == "bar_width":
            val_mm = max(21.38, val_mm)
            self.current_profile.bar_width = val_mm
        else:
            val_mm = max(17.05, val_mm)
            self.current_profile.bar_height = val_mm
        tf.value = self._display_mm(val_mm)
        tf.update()
        self._on_preview_trigger(_FakeEvent(tf))

    def _on_qr_field_enter(self, tf):
        key = tf.data
        if key != "qr_size":
            return
        normalize_decimal_input(_FakeEvent(tf))
        raw = tf.value.strip()
        if not raw:
            return
        try:
            display_val = float(raw)
        except ValueError:
            return
        val_mm = self._save_to_mm(display_val)
        # GS1: QR — mínimo dinámico según datos (cacheado en el perfil)
        self._ensure_profile_minimums()
        min_w = self.current_profile.qr_min_size or 20.0
        val_mm = max(min_w, val_mm)
        self.current_profile.bar_width = val_mm
        self.current_profile.bar_height = val_mm
        tf.value = self._display_mm(val_mm)
        tf.update()
        self._on_preview_trigger(_FakeEvent(tf))

    def _on_code128_field_enter(self, tf):
        key = tf.data
        if key not in ("bar_width", "bar_height"):
            return
        normalize_decimal_input(_FakeEvent(tf))
        raw = tf.value.strip()
        if not raw:
            return
        try:
            display_val = float(raw)
        except ValueError:
            return
        val_mm = self._save_to_mm(display_val)
        if key == "bar_width":
            # GS1: Code128 — mínimo dinámico según datos (cacheado en el perfil)
            self._ensure_profile_minimums()
            min_w = self.current_profile.code128_min_width or 40.0
            val_mm = max(min_w, min(165.10, val_mm))
            self.current_profile.bar_width = val_mm
        else:
            # GS1: Code128 alto 12–32mm
            val_mm = max(12.0, min(32.0, val_mm))
            self.current_profile.bar_height = val_mm
        tf.value = self._display_mm(val_mm)
        tf.update()
        self._on_preview_trigger(_FakeEvent(tf))

    def _on_code39_field_enter(self, tf):
        key = tf.data
        if key not in ("bar_width", "bar_height"):
            return
        normalize_decimal_input(_FakeEvent(tf))
        raw = tf.value.strip()
        if not raw:
            return
        try:
            display_val = float(raw)
        except ValueError:
            return
        val_mm = self._save_to_mm(display_val)
        if key == "bar_width":
            # GS1: Code39 — mínimo dinámico según datos (cacheado en el perfil)
            self._ensure_profile_minimums()
            min_w = self.current_profile.code39_min_width or 40.0
            val_mm = max(min_w, val_mm)
            self.current_profile.bar_width = val_mm
        else:
            # GS1: Code39 alto mínimo 15mm
            val_mm = max(CODE39_MIN_HEIGHT_MM, val_mm)
            self.current_profile.bar_height = val_mm
        tf.value = self._display_mm(val_mm)
        tf.update()
        self._on_preview_trigger(_FakeEvent(tf))

    def _on_ean5_field_enter(self, tf):
        key = tf.data
        if key not in ("bar_width", "bar_height"):
            return
        normalize_decimal_input(_FakeEvent(tf))
        raw = tf.value.strip()
        if not raw:
            return
        try:
            display_val = float(raw)
        except ValueError:
            return
        val_mm = self._save_to_mm(display_val)
        if key == "bar_width":
            # GS1: EAN-5 complementario 17.92–44.80mm
            val_mm = max(17.92, min(44.80, val_mm))
            self.current_profile.bar_width = val_mm
        else:
            # GS1: EAN-5 alto 20.73–51.82mm
            val_mm = max(20.73, min(51.82, val_mm))
            self.current_profile.bar_height = val_mm
        tf.value = self._display_mm(val_mm)
        tf.update()
        self._on_preview_trigger(_FakeEvent(tf))

    def _on_isbn13_field_enter(self, tf):
        key = tf.data
        if key not in ("bar_width", "bar_height"):
            return
        normalize_decimal_input(_FakeEvent(tf))
        raw = tf.value.strip()
        if not raw:
            return
        try:
            display_val = float(raw)
        except ValueError:
            return
        val_mm = self._save_to_mm(display_val)
        if key == "bar_width":
            # ISBN-13: mantener mínimo, sin techo para permitir tamaños mayores.
            val_mm = max(29.83, val_mm)
            self.current_profile.bar_width = val_mm
        else:
            # ISBN-13: mantener mínimo, sin techo para permitir tamaños mayores.
            val_mm = max(20.73, val_mm)
            self.current_profile.bar_height = val_mm
        tf.value = self._display_mm(val_mm)
        tf.update()
        self._on_preview_trigger(_FakeEvent(tf))

    def _on_itf14_field_enter(self, tf):
        key = tf.data
        normalize_decimal_input(_FakeEvent(tf))
        raw = tf.value.strip()
        if not raw:
            return
        try:
            display_val = float(raw)
        except ValueError:
            fallback = (
                self.current_profile.bar_width
                if key == "bar_width"
                else (self.current_profile.bar_height or 30.0)
            )
            tf.value = self._display_mm(fallback)
            tf.update()
            return
        val_mm = self._save_to_mm(display_val)
        printer = (
            self._itf14_printer_dd.content.controls[0].data
            if self._itf14_printer_dd
            else "flexografia"
        )
        if key == "bar_width":
            min_v = 89.25 if printer == "flexografia" else 71.40
            val_mm = max(min_v, val_mm)
            self.current_profile.bar_width = val_mm
        elif key == "bar_height":
            min_h = 32.00 if printer == "flexografia" else 12.70
            val_mm = max(min_h, val_mm)
            self.current_profile.bar_height = val_mm
        else:
            return
        tf.value = self._display_mm(val_mm)
        tf.update()
        self._set_field_value(key, self._display_mm(val_mm))
        self._on_preview_trigger(_FakeEvent(tf))

    # ------------------------------------------------------------------
    # Compact dropdown helper
    # ------------------------------------------------------------------
    def _create_compact_dropdown(
        self,
        options: list,
        value: str,
        width: int = 140,
        height: int = 20,
        on_change=None,
        text_size: int = 11,
    ) -> ft.Container:
        display_text = str(value)
        for opt in options:
            if isinstance(opt, tuple) and opt[0] == value:
                display_text = str(opt[1])
                break
            elif not isinstance(opt, tuple) and opt == value:
                display_text = str(opt)
                break

        texto_valor = ft.Text(
            display_text,
            size=text_size,
            color=DROPDOWN_TEXT_STYLE_COLOR,
            no_wrap=True,
            data=value,
        )

        def on_item_click(e):
            selected_text = e.control.content
            selected_data = (
                e.control.data if e.control.data is not None else selected_text
            )
            texto_valor.value = selected_text
            texto_valor.data = selected_data
            if on_change:
                on_change(selected_data)
            texto_valor.update()

        items = []
        for opt in options:
            if isinstance(opt, tuple):
                items.append(
                    ft.PopupMenuItem(
                        content=str(opt[1]), data=str(opt[0]), on_click=on_item_click
                    )
                )
            else:
                items.append(
                    ft.PopupMenuItem(
                        content=str(opt), data=str(opt), on_click=on_item_click
                    )
                )

        return ft.Container(
            width=width,
            height=height,
            padding=ft.Padding(2, 0, 2, 0),
            border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
            border_radius=3,
            bgcolor=FONDO_TEXTFIELDS_COLOR,
            content=ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=0,
                controls=[
                    texto_valor,
                    ft.PopupMenuButton(
                        content=ft.Icon(
                            ft.Icons.ARROW_DROP_DOWN,
                            size=16,
                            color=DROPDOWN_TRAILING_ICON_COLOR,
                        ),
                        padding=0,
                        splash_radius=0,
                        menu_position=ft.PopupMenuPosition.UNDER,
                        bgcolor=DROPDOWN_FONDO_MENU_COLOR,
                        shadow_color=BORDE_TEXTFIELDS_COLOR,
                        items=items,
                    ),
                ],
            ),
        )

    # ------------------------------------------------------------------
    # Section wrapper
    # ------------------------------------------------------------------
    def _make_section(self, title: str, controls: list, width=None) -> ft.Container:
        return ft.Container(
            width=width,
            content=ft.Column(
                [
                    ft.Text(
                        title,
                        size=12,
                        weight=ft.FontWeight.BOLD,
                        color=TEXTOS_FASE_1_COLOR,
                    ),
                    ft.Divider(height=1, color=BORDE_TEXTFIELDS_COLOR),
                    *controls,
                ],
                spacing=6,
            ),
            bgcolor=FONDO_SECCIONES,
            border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
            border_radius=4,
            padding=ft.Padding.all(4),
        )

    # ------------------------------------------------------------------
    # Symbology field helpers — read/write dynamic fields from SYMBOLOGY_CONFIG
    # ------------------------------------------------------------------
    def _get_field(self, key: str) -> Optional[ft.Control]:
        return self._symbology_fields.get(key)

    def _get_field_value(self, key: str):
        ctrl = self._get_field(key)
        if ctrl is None:
            return None
        if isinstance(ctrl, ft.TextField):
            return ctrl.value
        if hasattr(ctrl, "content") and hasattr(ctrl.content, "controls"):
            texto = ctrl.content.controls[0]
            return texto.data or texto.value
        return None

    def _set_field_value(self, key: str, value):
        ctrl = self._get_field(key)
        if ctrl is None:
            return
        if isinstance(ctrl, ft.TextField):
            ctrl.value = str(value)
            try:
                ctrl.update()
            except Exception:
                pass
        elif hasattr(ctrl, "content") and hasattr(ctrl.content, "controls"):
            texto = ctrl.content.controls[0]
            selected_data = str(value)
            if key in (
                "itf14_hri_position",
                "code39_hri_position",
                "code128_hri_position",
                "datamatrix_hri_position",
            ):
                selected_data = _normalize_hri_position(value)

            # For compact dropdowns, keep internal data and translated visible label in sync.
            selected_text = None
            try:
                popup = ctrl.content.controls[1]
                items = getattr(popup, "items", [])
                for item in items:
                    item_data = (
                        str(item.data) if item.data is not None else str(item.content)
                    )
                    item_text = str(item.content)
                    if item_data == selected_data or item_text == str(value):
                        selected_data = item_data
                        selected_text = item_text
                        break
                if selected_text is None:
                    try:
                        target = float(value)
                    except (ValueError, TypeError):
                        target = None
                    if target is not None:
                        best = None
                        best_diff = float("inf")
                        for item in items:
                            raw = item.data if item.data is not None else item.content
                            try:
                                diff = abs(float(raw) - target)
                            except (ValueError, TypeError):
                                continue
                            if diff < best_diff:
                                best_diff = diff
                                best = item
                        if best is not None:
                            selected_data = (
                                str(best.data) if best.data is not None else str(best.content)
                            )
                            selected_text = str(best.content)
            except Exception:
                pass

            texto.data = selected_data
            texto.value = selected_text if selected_text is not None else selected_data
            try:
                ctrl.update()
            except Exception:
                pass

    def _get_field_as_float(self, key: str, default: float = 0.0) -> float:
        v = self._get_field_value(key)
        if v is None:
            return default
        try:
            return float(v)
        except (ValueError, TypeError):
            return default

    def _build_dim_fields(self):
        """Build the dimension fields row from SYMBOLOGY_CONFIG for current symbology."""
        symb = self.current_profile.symbology
        config = SYMBOLOGY_CONFIG.get(symb)
        if not config:
            return ft.Row(spacing=6, visible=False)

        unit = self._get_unit()
        abbr = self._unit_abbr()
        self._symbology_fields.clear()
        sections: dict = {}
        row1 = []

        def _make_box(label, control, arrows=None):
            children = [label, control]
            if arrows is not None:
                children.append(arrows)
            return ft.Container(
                content=ft.Row(
                    children,
                    spacing=2 if arrows is not None else 4,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    tight=True,
                ),
                alignment=ft.Alignment.CENTER_LEFT,
            )

        for field in config["fields"]:
            key = field["key"]
            raw_label = t(field["label"])
            clean_label = re.sub(r"\s*\(mm\)\s*:?\s*$", "", raw_label).rstrip(":")
            if field["key"] == "datamatrix_height" or (
                field["type"] == "float"
                and field["key"] != "barcode_font_size"
                and not field.get("multiplier", False)
            ):
                label_text = f"{clean_label} ({abbr}):"
            else:
                label_text = f"{clean_label}:"
            label = ft.Text(label_text, size=12, color=TEXTOS_FASE_1_COLOR)
            target = sections.setdefault(field.get("section", ""), [])
            if key == "datamatrix_height":
                # Dynamic dropdown: calculate possible heights from data + Ancho
                p = self.current_profile
                values = [p.datamatrix_longest_value] if p.datamatrix_longest_value else []
                if not values:
                    values = [p.sample_value] if p.sample_value else [""]
                ancho = p.datamatrix_width or 20.0
                possible = get_datamatrix_possible_heights(values, ancho)
                if not possible:
                    possible = [(20.0, "square")]
                self._datamatrix_possible = possible
                options = [(f"{h:.1f}", self._display_mm(h)) for h, fmt in possible]
                current_h = float(
                    self.current_profile.datamatrix_height or possible[0][0]
                )
                current_val = f"{current_h:.1f}"
                dd = self._create_compact_dropdown(
                    options=options,
                    value=current_val,
                    width=80,
                    height=28,
                    text_size=11,
                    on_change=lambda val: self._on_datamatrix_height_change(
                        val, possible
                    ),
                )
                self._symbology_fields[key] = dd
                target.append(_make_box(label, dd))
            elif field["type"] == "dropdown":
                dd = self._create_compact_dropdown(
                    options=[(o, t(o)) for o in field["options"]],
                    value=str(self.current_profile.__dict__.get(key, field["default"])),
                    width=110 if key == "barcode_font_family" else 140 if key in ("datamatrix_hri_align", "qr_hri_align", "pdf417_hri_align") else 80,
                    height=28,
                    text_size=11,
                    on_change=lambda val, k=key: self._on_field_change(k, val),
                )
                self._symbology_fields[key] = dd
                target.append(_make_box(label, dd))
            else:
                if key == "qr_size":
                    raw_val = self.current_profile.bar_width
                else:
                    raw_val = self.current_profile.__dict__.get(key, field["default"])
                if (
                    field["key"] != "barcode_font_size"
                    and not field.get("multiplier", False)
                    and raw_val is not None
                ):
                    display_val = self._display_mm(float(raw_val))
                else:
                    display_val = str(raw_val) if raw_val is not None else ""
                tf = ft.TextField(
                    value=display_val,
                    width=60,
                    height=28,
                    text_size=11,
                    content_padding=ft.Padding(6, 0, 6, 0),
                    filled=True,
                    fill_color=FONDO_TEXTFIELDS_COLOR,
                    text_style=ft.TextStyle(color=TEXTO_COLOR_GENERICO),
                    on_change=self._on_preview_trigger,border=ft.OutlineInputBorder(border_radius=4, side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)))
                tf.data = key
                self._symbology_fields[key] = tf
                if self.current_profile.symbology == "pdf417" and key in (
                    "pdf417_size",
                    "pdf417_height",
                ):
                    tf.on_change = None
                    tf.on_submit = lambda e, tf=tf: self._on_pdf417_field_enter(tf)
                    tf.on_blur = lambda e, tf=tf: self._on_pdf417_field_enter(tf)
                    tf.on_focus = lambda e: setattr(self, "_pdf417_enter_target", tf)
                if self.current_profile.symbology == "upca" and key in (
                    "bar_width",
                    "bar_height",
                ):
                    tf.on_submit = lambda e, tf=tf: self._on_upca_field_enter(tf)
                    tf.on_blur = lambda e, tf=tf: self._on_upca_field_enter(tf)
                if self.current_profile.symbology == "upce" and key in (
                    "bar_width",
                    "bar_height",
                ):
                    tf.on_submit = lambda e, tf=tf: self._on_upce_field_enter(tf)
                    tf.on_blur = lambda e, tf=tf: self._on_upce_field_enter(tf)
                if self.current_profile.symbology == "ean13" and key in (
                    "bar_width",
                    "bar_height",
                ):
                    tf.on_submit = lambda e, tf=tf: self._on_ean13_field_enter(tf)
                    tf.on_blur = lambda e, tf=tf: self._on_ean13_field_enter(tf)
                if self.current_profile.symbology == "ean8" and key in (
                    "bar_width",
                    "bar_height",
                ):
                    tf.on_submit = lambda e, tf=tf: self._on_ean8_field_enter(tf)
                    tf.on_blur = lambda e, tf=tf: self._on_ean8_field_enter(tf)
                if self.current_profile.symbology == "qr" and key == "qr_size":
                    tf.on_submit = lambda e, tf=tf: self._on_qr_field_enter(tf)
                    tf.on_blur = lambda e, tf=tf: self._on_qr_field_enter(tf)
                if self.current_profile.symbology == "code128" and key in (
                    "bar_width",
                    "bar_height",
                ):
                    tf.on_submit = lambda e, tf=tf: self._on_code128_field_enter(tf)
                    tf.on_blur = lambda e, tf=tf: self._on_code128_field_enter(tf)
                if self.current_profile.symbology == "ean5" and key in (
                    "bar_width",
                    "bar_height",
                ):
                    tf.on_submit = lambda e, tf=tf: self._on_ean5_field_enter(tf)
                    tf.on_blur = lambda e, tf=tf: self._on_ean5_field_enter(tf)
                if self.current_profile.symbology == "isbn13" and key in (
                    "bar_width",
                    "bar_height",
                ):
                    tf.on_submit = lambda e, tf=tf: self._on_isbn13_field_enter(tf)
                    tf.on_blur = lambda e, tf=tf: self._on_isbn13_field_enter(tf)
                if self.current_profile.symbology == "itf14" and key in (
                    "bar_width",
                    "bar_height",
                ):
                    tf.on_submit = lambda e, tf=tf: self._on_itf14_field_enter(tf)
                    tf.on_blur = lambda e, tf=tf: self._on_itf14_field_enter(tf)
                if (
                    _is_datamatrix_family(self.current_profile.symbology)
                    and key == "datamatrix_width"
                ):
                    tf.on_change = None
                    tf.on_submit = lambda e, tf=tf: self._on_datamatrix_field_enter(tf)
                    tf.on_blur = lambda e, tf=tf: self._on_datamatrix_field_enter(tf)
                    tf.on_focus = lambda e: setattr(self, "_datamatrix_width_target", tf)
                if self.current_profile.symbology == "code39" and key in (
                    "bar_width",
                    "bar_height",
                ):
                    tf.on_submit = lambda e, tf=tf: self._on_code39_field_enter(tf)
                    tf.on_blur = lambda e, tf=tf: self._on_code39_field_enter(tf)

                arrows = None
                if field["type"] == "float":
                    if field.get("multiplier", False):
                        _step = 0.1
                    elif field["key"] != "barcode_font_size":
                        _step = float(self._display_mm(1.0))
                    else:
                        _step = 1.0

                    def _make_inc(k, step):
                        def inc(e):
                            try:
                                cur = float(self._symbology_fields[k].value)
                                if k == "barcode_font_size":
                                    max_pt = self._ean_max_body_pt()
                                    if max_pt is not None and cur + step > max_pt:
                                        return
                                if (
                                    _is_datamatrix_family(self.current_profile.symbology)
                                    and k == "datamatrix_width"
                                ):
                                    self._symbology_fields[k].value = f"{cur + step}"
                                    self._symbology_fields[k].update()
                                    self._on_datamatrix_field_enter(
                                        self._symbology_fields[k]
                                    )
                                    return
                                self._symbology_fields[k].value = f"{cur + step}"
                                self._symbology_fields[k].update()
                                self._on_preview_trigger(
                                    type(
                                        "_e", (), {"control": self._symbology_fields[k]}
                                    )()
                                )
                                if k in ("pdf417_size", "pdf417_height"):
                                    self._on_pdf417_field_enter(
                                        self._symbology_fields[k]
                                    )
                                if self.current_profile.symbology == "upca" and k in (
                                    "bar_width",
                                    "bar_height",
                                ):
                                    self._on_upca_field_enter(self._symbology_fields[k])
                                if self.current_profile.symbology == "upce" and k in (
                                    "bar_width",
                                    "bar_height",
                                ):
                                    self._on_upce_field_enter(self._symbology_fields[k])
                                if self.current_profile.symbology == "ean13" and k in (
                                    "bar_width",
                                    "bar_height",
                                ):
                                    self._on_ean13_field_enter(
                                        self._symbology_fields[k]
                                    )
                                if self.current_profile.symbology == "ean8" and k in (
                                    "bar_width",
                                    "bar_height",
                                ):
                                    self._on_ean8_field_enter(self._symbology_fields[k])
                                if (
                                    self.current_profile.symbology == "qr"
                                    and k == "qr_size"
                                ):
                                    self._on_qr_field_enter(self._symbology_fields[k])
                                if (
                                    self.current_profile.symbology == "code128"
                                    and k in ("bar_width", "bar_height")
                                ):
                                    self._on_code128_field_enter(
                                        self._symbology_fields[k]
                                    )
                                if self.current_profile.symbology == "ean5" and k in (
                                    "bar_width",
                                    "bar_height",
                                ):
                                    self._on_ean5_field_enter(self._symbology_fields[k])
                                if (
                                    self.current_profile.symbology == "isbn13"
                                    and k in ("bar_width", "bar_height")
                                ):
                                    self._on_isbn13_field_enter(
                                        self._symbology_fields[k]
                                    )
                                if (
                                    self.current_profile.symbology == "itf14"
                                    and k == "bar_width"
                                ):
                                    self._on_itf14_field_enter(
                                        self._symbology_fields[k]
                                    )
                                if (
                                    self.current_profile.symbology == "code39"
                                    and k in ("bar_width", "bar_height")
                                ):
                                    self._on_code39_field_enter(
                                        self._symbology_fields[k]
                                    )
                                if (
                                    _is_datamatrix_family(self.current_profile.symbology)
                                    and k in ("datamatrix_width", "datamatrix_height")
                                ):
                                    self._on_datamatrix_field_enter(
                                        self._symbology_fields[k]
                                    )
                            except (ValueError, TypeError):
                                return
                            except Exception:
                                pass

                        return inc

                    def _make_dec(k, step):
                        def dec(e):
                            try:
                                cur = float(self._symbology_fields[k].value)
                                if (
                                    _is_datamatrix_family(self.current_profile.symbology)
                                    and k == "datamatrix_width"
                                ):
                                    min_disp = float(
                                        self._display_mm(
                                            self.current_profile.datamatrix_min_width or 20.0
                                        )
                                    )
                                    new_disp = max(min_disp, cur - step)
                                    self._symbology_fields[k].value = f"{new_disp:g}"
                                    self._symbology_fields[k].update()
                                    if (
                                        new_disp <= min_disp + 0.001
                                        and cur <= min_disp + 0.001
                                    ):
                                        return
                                    self._on_datamatrix_field_enter(
                                        self._symbology_fields[k]
                                    )
                                    return
                                if k == "barcode_font_size":
                                    _EAN_FAMILY = (
                                        "ean13",
                                        "ean8",
                                        "ean5",
                                        "upca",
                                        "upce",
                                        "isbn13",
                                    )
                                    min_val = (
                                        1.0
                                        if self.current_profile.symbology
                                        in _EAN_FAMILY
                                        else 0.0
                                    )
                                else:
                                    min_val = (
                                        0.0
                                        if k
                                        in (
                                            "code39_hri_gap_mm",
                                            "itf14_hri_gap_mm",
                                            "code128_hri_gap_mm",
                                            "ean5_hri_gap_mm",
                                            "datamatrix_hri_gap_mm",
                                            "datamatrix_hri_line_spacing",
                                            "qr_hri_gap_mm",
                                            "qr_hri_line_spacing",
                                            "pdf417_hri_gap_mm",
                                            "pdf417_hri_line_spacing",
                                        )
                                        else 1.0
                                    )
                                self._symbology_fields[k].value = (
                                    f"{max(min_val, cur - step)}"
                                )
                                self._symbology_fields[k].update()
                                self._on_preview_trigger(
                                    type(
                                        "_e", (), {"control": self._symbology_fields[k]}
                                    )()
                                )
                                if k in ("pdf417_size", "pdf417_height"):
                                    self._on_pdf417_field_enter(
                                        self._symbology_fields[k]
                                    )
                                if self.current_profile.symbology == "upca" and k in (
                                    "bar_width",
                                    "bar_height",
                                ):
                                    self._on_upca_field_enter(self._symbology_fields[k])
                                if self.current_profile.symbology == "upce" and k in (
                                    "bar_width",
                                    "bar_height",
                                ):
                                    self._on_upce_field_enter(self._symbology_fields[k])
                                if self.current_profile.symbology == "ean13" and k in (
                                    "bar_width",
                                    "bar_height",
                                ):
                                    self._on_ean13_field_enter(
                                        self._symbology_fields[k]
                                    )
                                if self.current_profile.symbology == "ean8" and k in (
                                    "bar_width",
                                    "bar_height",
                                ):
                                    self._on_ean8_field_enter(self._symbology_fields[k])
                                if (
                                    self.current_profile.symbology == "qr"
                                    and k == "qr_size"
                                ):
                                    self._on_qr_field_enter(self._symbology_fields[k])
                                if (
                                    self.current_profile.symbology == "code128"
                                    and k in ("bar_width", "bar_height")
                                ):
                                    self._on_code128_field_enter(
                                        self._symbology_fields[k]
                                    )
                                if self.current_profile.symbology == "ean5" and k in (
                                    "bar_width",
                                    "bar_height",
                                ):
                                    self._on_ean5_field_enter(self._symbology_fields[k])
                                if (
                                    self.current_profile.symbology == "isbn13"
                                    and k in ("bar_width", "bar_height")
                                ):
                                    self._on_isbn13_field_enter(
                                        self._symbology_fields[k]
                                    )
                                if (
                                    self.current_profile.symbology == "itf14"
                                    and k == "bar_width"
                                ):
                                    self._on_itf14_field_enter(
                                        self._symbology_fields[k]
                                    )
                                if (
                                    self.current_profile.symbology == "code39"
                                    and k in ("bar_width", "bar_height")
                                ):
                                    self._on_code39_field_enter(
                                        self._symbology_fields[k]
                                    )
                                if (
                                    _is_datamatrix_family(self.current_profile.symbology)
                                    and k in ("datamatrix_width", "datamatrix_height")
                                ):
                                    self._on_datamatrix_field_enter(
                                        self._symbology_fields[k]
                                    )
                            except (ValueError, TypeError):
                                return
                            except Exception:
                                pass

                        return dec

                    arrows = ft.Column(
                        [
                            ft.IconButton(
                                icon=ft.Icons.ARROW_DROP_UP,
                                icon_size=12,
                                width=14,
                                height=14,
                                padding=0,
                                on_click=_make_inc(key, _step),
                                icon_color=TEXTO_COLOR_GENERICO,
                            ),
                            ft.IconButton(
                                icon=ft.Icons.ARROW_DROP_DOWN,
                                icon_size=12,
                                width=14,
                                height=14,
                                padding=0,
                                on_click=_make_dec(key, _step),
                                icon_color=TEXTO_COLOR_GENERICO,
                            ),
                        ],
                        spacing=0,
                        tight=True,
                    )

                target.append(_make_box(label, tf, arrows))

        if len(sections) > 1:
            return ft.Column(
                [
                    self._make_section(t(title), [ft.Row(boxes, spacing=4)])
                    for title, boxes in sections.items()
                ],
                spacing=6,
            )
        if sections:
            boxes = list(sections.values())[0]
            if "" in sections:
                # Sin agrupar por sección (el resto de simbologías): caja titulada
                return self._make_section(t("Dimensiones"), [ft.Row(boxes, spacing=4)])
            return ft.Row(boxes, spacing=4)
        return ft.Row(row1, spacing=4)

    def _on_field_change(self, key: str, value: str):
        """Called when a dynamic field (e.g. dropdown) changes."""
        self.current_profile.__dict__[key] = value
        if key == "barcode_font_family":
            self.current_profile.barcode_font_auto = False
        self._update_preview()

    def _create_profile_list_item(
        self, index: int, profile: BarcodeProfile
    ) -> ft.GestureDetector:
        is_selected = index == self.selected_profile_index
        is_default = profile.name == "<Default>"

        container = ft.Container(
            content=ft.Text(
                profile.name,
                size=12,
                color=TEXTOS_FASE_1_COLOR,
            ),
            padding=ft.Padding.symmetric(horizontal=8, vertical=4),
            bgcolor=FONDO_CALCULO_FASE_1 if is_selected else FONDO_TEXTFIELDS_COLOR,
        )

        def on_double_tap_handler(e, idx=index):
            if self.profiles[idx].name != "<Default>":
                self._rename_profile(idx)

        return ft.GestureDetector(
            content=container,
            on_tap=lambda e, idx=index: self._select_profile(idx),
            on_double_tap=on_double_tap_handler,
        )

    def _update_profile_list(self):
        if self.profile_list:
            self.profile_list.controls = [
                self._create_profile_list_item(i, p)
                for i, p in enumerate(self.profiles)
            ]
            self.profile_list.update()

    def _select_profile(self, index: int):
        if index == self.selected_profile_index:
            return
        self.selected_profile_index = index
        self.current_profile = self.profiles[index]
        self._load_profile_to_ui()
        self._update_profile_list()
        if self.on_profile_changed:
            self.on_profile_changed(self.current_profile)

    def _rename_profile(self, index: int):
        if self.profiles[index].name == "<Default>":
            return

        def _apply(index, new_name):
            old_name = self.profiles[index].name
            self.profiles[index].name = new_name
            if index == self.selected_profile_index:
                self.current_profile.name = new_name
            self._update_profile_list()
            if self.on_profile_renamed and old_name != new_name:
                self.on_profile_renamed(old_name, new_name)

        show_rename_profile_dialog(
            root_stack=self.dialog_root_stack,
            current_name=self.profiles[index].name,
            existing_names=[p.name for p in self.profiles],
            on_rename_success=lambda new_name: _apply(index, new_name),
        )

    def _create_new_profile(self, e):
        base_name = t("Nuevo perfil")
        counter = 1
        new_name = base_name
        while any(p.name == new_name for p in self.profiles):
            new_name = f"{base_name} {counter}"
            counter += 1
        original = (
            self.profiles[self.selected_profile_index]
            if self.profiles
            else self.current_profile
        )
        new_profile = original.copy()
        new_profile.id = str(uuid.uuid4())
        new_profile.name = new_name
        self.profiles.append(new_profile)
        self.selected_profile_index = len(self.profiles) - 1
        self.current_profile = new_profile
        self._update_profile_list()
        self._load_profile_to_ui()
        if self.on_profile_changed:
            self.on_profile_changed(self.current_profile)

    def _delete_profile(self, e):
        if self.profiles[self.selected_profile_index].name == "<Default>":
            return
        if len(self.profiles) <= 1:
            return
        deleted_name = self.profiles[self.selected_profile_index].name

        def confirm_delete(ev):
            if popup_container in self.dialog_root_stack.controls:
                self.dialog_root_stack.controls.remove(popup_container)
            self.dialog_root_stack.update()
            del self.profiles[self.selected_profile_index]
            self.selected_profile_index = max(0, self.selected_profile_index - 1)
            self.current_profile = self.profiles[self.selected_profile_index]
            self._update_profile_list()
            self._load_profile_to_ui()
            if self.on_profile_changed:
                self.on_profile_changed(self.current_profile)

        def cancel_delete(ev):
            if popup_container in self.dialog_root_stack.controls:
                self.dialog_root_stack.controls.remove(popup_container)
            self.dialog_root_stack.update()

        _btn_style = ft.ButtonStyle(
            color={
                ft.ControlState.DEFAULT: BOTONES_GENERICOS_COLOR,
                "hovered": BOTONES_GENERICOS_HOVER_COLOR,
            },
            overlay_color=BOTONES_GENERICOS_OVERLAY_COLOR,
            padding=ft.Padding(0, 0, 0, 0),
            shape=ft.RoundedRectangleBorder(radius=10),
        )

        popup_content = ft.Container(
            content=ft.Column(
                [
                    ft.Container(
                        content=ft.Text(
                            t("Eliminar Perfil"),
                            weight=ft.FontWeight.BOLD,
                            size=18,
                            color=TEXTO_COLOR_GENERICO,
                        ),
                        alignment=ft.Alignment.CENTER,
                    ),
                    ft.Container(height=10),
                    ft.Text(
                        t("Eliminar_confirmation_barcode").format(name=deleted_name),
                        color=TEXTO_COLOR_GENERICO,
                    ),
                    ft.Container(height=15),
                    ft.Row(
                        [
                            ft.Button(
                                t("Cancelar"),
                                on_click=cancel_delete,
                                width=110,
                                bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
                                style=_btn_style,
                            ),
                            ft.Button(
                                t("Eliminar"),
                                on_click=confirm_delete,
                                width=110,
                                bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
                                style=_btn_style,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                        spacing=15,
                    ),
                ],
                tight=True,
                spacing=0,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            width=380,
            padding=ft.Padding(24, 20, 24, 20),
            bgcolor=FONDO_ALERT_DIALOG,
            border_radius=12,
            border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
            shadow=ft.BoxShadow(
                spread_radius=2,
                blur_radius=15,
                color=(
                    ft.Colors.with_opacity(0.4, "#000000")
                    if hasattr(ft, "Colors")
                    else "#66000000"
                ),
            ),
        )

        popup_container = ft.Container(
            content=popup_content,
            alignment=ft.Alignment.TOP_CENTER,
            margin=ft.Margin.only(top=50),
        )

        self.dialog_root_stack.controls.append(popup_container)
        self.dialog_root_stack.update()

    # ------------------------------------------------------------------
    # Load profile to UI
    # ------------------------------------------------------------------
    def _load_profile_to_ui(self):
        p = self.current_profile
        # Sync symbology dropdown
        if self._symbology_dropdown:
            dd = self._symbology_dropdown.content.controls[0]
            for opt in SYMBOLOGY_OPTIONS:
                if opt[0] == p.symbology:
                    dd.value = opt[1]
                    dd.data = opt[0]
                    break
            try:
                self._symbology_dropdown.update()
            except Exception:
                pass
        if self._value_source_dropdown:
            dd = self._value_source_dropdown.content.controls[0]
            for opt in VALUE_SOURCE_OPTIONS:
                if opt[0] == p.value_source:
                    dd.value = opt[1]
                    dd.data = opt[0]
                    break
            try:
                self._value_source_dropdown.update()
            except Exception:
                pass
        self._update_value_source_visibility(p.value_source)
        if self._sample_field:
            self._sample_field.value = p.sample_value
            try:
                self._sample_field.update()
            except Exception:
                pass
        if self._mask_field:
            self._mask_field.value = p.mask
            try:
                self._mask_field.update()
            except Exception:
                pass
        self._update_section_visibility()
        if self._symb_del_keys() and p.value_source == "excel" and p.excel_column:
            self._auto_detect_separators()
            self._update_section_visibility()
        # Reload dynamic symbology fields (rebuilds content, update triggered inside)
        self._rebuild_dim_fields()
        # Sync profile values into the dynamic fields
        symb = p.symbology
        cfg = SYMBOLOGY_CONFIG.get(symb, {})
        for field in cfg.get("fields", []):
            key = field["key"]
            val = p.__dict__.get(key, field.get("default"))
            if val is not None:
                if field["type"] == "float" and key != "barcode_font_size":
                    self._set_field_value(key, self._display_mm(float(val)))
                else:
                    self._set_field_value(key, val)
        # Special: PDF417 size field — usa pdf417_size/pdf417_height (fallback a bar_* para legacy)
        if p.symbology == "pdf417":
            self._set_field_value(
                "pdf417_size",
                self._display_mm(
                    p.pdf417_size if p.pdf417_size is not None else p.bar_width
                ),
            )
            self._set_field_value(
                "pdf417_height",
                self._display_mm(
                    p.pdf417_height if p.pdf417_height is not None else p.bar_height
                ),
            )
        # Special: QR size is stored as bar_width (profile has no qr_size field)
        if p.symbology == "qr":
            self._set_field_value("qr_size", self._display_mm(p.bar_width))
        # Sync ITF-14 specific controls
        if p.symbology == "itf14":
            for dd_ctl, opts, cur_val in [
                (self._itf14_printer_dd, ITF14_PRINTER_OPTIONS, p.itf14_printer_type),
                (self._itf14_gtin_type_dd, ITF14_GTIN_OPTIONS, p.itf14_gtin_type),
            ]:
                if dd_ctl is not None:
                    inner = dd_ctl.content.controls[0]
                    for opt_val, opt_label in opts:
                        if opt_val == cur_val:
                            inner.value = opt_label
                            inner.data = opt_val
                            break
                    try:
                        dd_ctl.update()
                    except Exception:
                        pass
            if self._itf14_width_field is not None:
                self._itf14_width_field.value = self._display_mm(p.bar_width)
                try:
                    self._itf14_width_field.update()
                except Exception:
                    pass
            if self._itf14_height_field is not None:
                self._itf14_height_field.value = self._display_mm(p.bar_height or 30.0)
                try:
                    self._itf14_height_field.update()
                except Exception:
                    pass
            if self._itf14_body_field is not None:
                self._itf14_body_field.value = str(p.barcode_font_size)
                try:
                    self._itf14_body_field.update()
                except Exception:
                    pass
            if self._itf14_gap_field is not None:
                self._itf14_gap_field.value = self._display_mm(p.itf14_hri_gap_mm)
                try:
                    self._itf14_gap_field.update()
                except Exception:
                    pass
        # Code 39 fields are handled by SYMBOLOGY_CONFIG auto-generated dim fields — no custom sync needed
        if self._excel_column_dropdown is not None:
            dd = self._excel_column_dropdown.content.controls[0]
            if p.excel_column and p.excel_column in self._excel_columns:
                dd.value = p.excel_column
                dd.data = p.excel_column
            else:
                dd.value = t("(sin seleccion)")
                dd.data = ""
            try:
                self._excel_column_dropdown.update()
            except Exception:
                pass
        self._update_color_swatch()
        self._update_preview()

    # ------------------------------------------------------------------
    # Value source / excel visibility
    # ------------------------------------------------------------------
    def _apply_delims_visibility(self):
        """Visibilidad de los campos de separadores / botón Recalcular / etiqueta GS1.

        Solo se muestran los separadores con origen Excel + symbology con separadores
        (datamatrix/qr/pdf417) + columna seleccionada + datos no-GS1. Si la columna
        es GS1 se muestra la etiqueta 'Datos GS1 detectados' en su lugar. Sin
        columna → todo oculto. También recarga los valores desde el perfil del symb.
        La etiqueta GS1 también aparece cuando el valor de muestra fija es GS1.
        """
        symb = self._symb_del_keys()
        # Familia DataMatrix: modo explícito por ID (no auto-detección de contenido).
        #   datamatrix (texto libre) => nunca GS1 (separadores visibles)
        #   datamatrix_gs1           => siempre GS1 (etiqueta GS1, sin separadores)
        #   datamatrix_dl            => URI (sin separadores ni etiqueta GS1)
        mode_gs1 = _is_datamatrix_gs1_symb(symb)
        is_dl = symb == "datamatrix_dl"
        gs1 = mode_gs1
        if not _is_datamatrix_family(symb):
            # qr/pdf417: conservar auto-detección histórica por contenido
            gs1 = self._gs1_by_symb.get(symb, False)
            if not gs1 and self.current_profile.value_source == "fixed":
                sample = self._sample_field.value or ""
                gs1 = bool(sample) and _es_datamatrix_gs1(sample)
        if self._datamatrix_del_open_field is not None:
            self._datamatrix_del_open_field.value = (
                getattr(self.current_profile, f"{symb}_del_open", "") if symb else ""
            )
        if self._datamatrix_del_close_field is not None:
            self._datamatrix_del_close_field.value = (
                getattr(self.current_profile, f"{symb}_del_close", "|") if symb else "|"
            )
        if self._del_close_newline_check is not None:
            self._del_close_newline_check.value = bool(
                getattr(self.current_profile, f"{symb}_del_close_newline", False)
                if symb
                else False
            )
        show = (
            bool(symb)
            and self.current_profile.value_source == "excel"
            and bool(self.current_profile.excel_column)
            and not gs1
            and not is_dl
        )
        for field in (
            self._datamatrix_del_open_field,
            self._datamatrix_del_close_field,
            self._del_close_newline_row,
            self._datamatrix_del_recalc_btn,
        ):
            if field is not None:
                field.visible = show
                try:
                    field.update()
                except Exception:
                    pass
        if self._del_close_newline_check is not None:
            self._del_close_newline_check.visible = show
            try:
                self._del_close_newline_check.update()
            except Exception:
                pass
        if self._datamatrix_gs1_label is not None:
            self._datamatrix_gs1_label.visible = (
                bool(symb) and gs1 and mode_gs1
            )
            try:
                self._datamatrix_gs1_label.update()
            except Exception:
                pass

    def _update_value_source_visibility(self, value_source: str):
        if self._mask_container:
            self._mask_container.visible = value_source == "numbering"
            self._mask_container.update()
        if self._sample_field:
            self._sample_field.visible = False
            self._sample_field.update()
        if self._pdf417_sample_btn:
            self._pdf417_sample_btn.visible = (
                value_source == "fixed" and self.current_profile.symbology == "pdf417"
            )
            self._pdf417_sample_btn.update()
        if self._generic_sample_btn:
            self._generic_sample_btn.visible = (
                value_source == "fixed"
                and self.current_profile.symbology not in ("pdf417", "datamatrix", "qr")
            )
            self._generic_sample_btn.update()
        if self._qr_sample_btn:
            self._qr_sample_btn.visible = (
                value_source == "fixed" and self.current_profile.symbology == "qr"
            )
            self._qr_sample_btn.update()
        if self._datamatrix_sample_btn:
            self._datamatrix_sample_btn.visible = (
                value_source == "fixed"
                and _is_datamatrix_family(self.current_profile.symbology)
            )
            self._datamatrix_sample_btn.update()
        if self._excel_column_dropdown is not None:
            self._excel_column_dropdown.visible = value_source == "excel"
            try:
                self._excel_column_dropdown.update()
            except Exception:
                pass
        self._update_row_nav_visibility()
        self._apply_delims_visibility()

    def _update_value_source_dropdown(self, source=None):
        if source is None:
            source = self._value_source_dropdown.content.controls[0].data

        if source == "excel" and not self._excel_columns:
            self._show_error(
                t(
                    "No hay archivo de datos cargado. Cargue un archivo Excel o CSV primero."
                )
            )
            texto_valor = self._value_source_dropdown.content.controls[0]
            for opt in VALUE_SOURCE_OPTIONS:
                if opt[0] == "fixed":
                    texto_valor.value = opt[1]
                    texto_valor.data = "fixed"
                    break
            source = "fixed"

        self.current_profile.value_source = source
        if self.current_profile.symbology in ("code128", "code39", "qr", "ean5", "ean13", "ean8", "upca", "upce", "isbn13"):
            self.current_profile.bar_width = None
            self.current_profile.bar_height = None
        if self.current_profile.symbology == "pdf417":
            self.current_profile.pdf417_size = None
            self.current_profile.pdf417_height = None
        if _is_datamatrix_family(self.current_profile.symbology):
            self.current_profile.datamatrix_width = None
        # Al salir de "datos externos" se limpia la columna para no arrastrar datos obsoletos
        if source != "excel":
            self.current_profile.excel_column = ""
            if self._excel_column_dropdown is not None:
                excel_dd = self._excel_column_dropdown.content.controls[0]
                excel_dd.data = ""
                excel_dd.value = t("(sin seleccion)")
                try:
                    excel_dd.update()
                except Exception:
                    pass
        self._update_value_source_visibility(source)
        self._on_value_changed()
        if self.current_profile.symbology in (
            "datamatrix", "pdf417", "qr", "code128", "code39"
        ):
            self._recalculate_minimums()
        self._on_preview_trigger(None)
        if self.on_profile_changed:
            self.on_profile_changed(self.current_profile)
        self.page.update()

    # ------------------------------------------------------------------
    # PDF417 min dimensions computation
    # ------------------------------------------------------------------
    def _compute_pdf417_min_dimensions(self) -> Tuple[float, float]:
        """Scan all values for current data source, return (min_width_mm, min_height_mm)."""
        from utils.barcode_module import get_pdf417_min_dimensions

        profile = self.current_profile
        source = profile.value_source

        if source == "excel" and profile.excel_column:
            cols = (
                self.excel_manager.get_column_values(profile.excel_column)
                if self.excel_manager
                else []
            )
            if cols:
                return get_pdf417_min_dimensions(cols)
        elif source == "numbering":
            current_value = self._get_current_value()
            if current_value:
                return get_pdf417_min_dimensions([current_value])

        return get_pdf417_min_dimensions([profile.sample_value])

    def _get_code128_values(self) -> list:
        """Retorna lista de valores para calcular ancho Code128 mínimo."""
        profile = self.current_profile
        source = profile.value_source
        if source == "excel" and profile.excel_column:
            return (
                self.excel_manager.get_column_values(profile.excel_column)
                if self.excel_manager
                else []
            )
        elif source == "numbering":
            current_value = self._get_current_value()
            return [current_value] if current_value else []
        return [profile.sample_value] if profile.sample_value else []

    def _get_qr_values(self) -> list:
        """Retorna lista de valores para calcular tamaño QR mínimo."""
        profile = self.current_profile
        source = profile.value_source
        if source == "excel" and profile.excel_column:
            return (
                self.excel_manager.get_column_values(profile.excel_column)
                if self.excel_manager
                else []
            )
        elif source == "numbering":
            current_value = self._get_current_value()
            return [current_value] if current_value else []
        return [profile.sample_value] if profile.sample_value else []

    def _get_datamatrix_values(self) -> list:
        """Retorna lista de valores para calcular tamaño DataMatrix mínimo."""
        profile = self.current_profile
        source = profile.value_source
        if source == "excel" and profile.excel_column:
            return (
                self.excel_manager.get_column_values(profile.excel_column)
                if self.excel_manager
                else []
            )
        elif source == "numbering":
            current_value = self._get_current_value()
            return [current_value] if current_value else []
        return [profile.sample_value] if profile.sample_value else []

    def _get_code39_values(self) -> list:
        """Retorna lista de valores para calcular ancho mínimo Code39."""
        profile = self.current_profile
        source = profile.value_source
        if source == "excel" and profile.excel_column:
            return (
                self.excel_manager.get_column_values(profile.excel_column)
                if self.excel_manager
                else []
            )
        elif source == "numbering":
            current_value = self._get_current_value()
            return [current_value] if current_value else []
        return [profile.sample_value] if profile.sample_value else []

    # ------------------------------------------------------------------
    # Preview
    # ------------------------------------------------------------------
    def _get_current_value(self) -> str:
        source = self._value_source_dropdown.content.controls[0].data
        if source == "excel":
            if self.excel_manager and self.excel_manager.is_loaded:
                col = self.current_profile.excel_column
                if col:
                    val = self.excel_manager.get_value_at(col, self._preview_row_index)
                    if val:
                        return val
            return ""
        if source == "numbering":
            gs = self.get_global_settings()
            start = int(gs.get("start", 1))
            mask = self.current_profile.mask
            return _apply_mask(start, mask)
        # VT personalizado: plantilla con <@<col>@> para QR/PDF417/DM
        if source == "fixed":
            tmpl = self._sample_field.value or ""
            symb = self.current_profile.symbology or ""
            if "<@<" in tmpl and symb in ("qr", "pdf417", "datamatrix") and self.excel_manager and getattr(self.excel_manager, "is_loaded", False):
                import re

                def _r(m):
                    col = m.group(1).strip()
                    try:
                        return self.excel_manager.get_value_at(col, self._preview_row_index) or ""
                    except Exception:
                        return ""

                return re.sub(r"<@<([^>]+)>@>", _r, tmpl)
        return self._sample_field.value or ""

    def _preview_row_count(self) -> int:
        if self.excel_manager and self.excel_manager.is_loaded:
            return max(0, int(self.excel_manager.row_count))
        return 0

    def set_initial_row(self, row_index: Optional[int]):
        """Fila (0-based) de la que parte el diálogo al abrirse (sync main→diálogo)."""
        self._pending_initial_row = max(0, row_index) if isinstance(row_index, int) else None

    def _row_nav_enabled(self) -> bool:
        if self.current_profile.symbology not in ("qr", "datamatrix", "pdf417"):
            return False
        if self._preview_row_count() == 0:
            return False
        if self.current_profile.value_source == "excel":
            return True
        # VT personalizado fixed con marcadores y Excel cargado → también navegable
        if self.current_profile.value_source == "fixed":
            tmpl = self.current_profile.sample_value or self._sample_field.value or ""
            if "<@<" in tmpl:
                return True
        return False

    def _set_preview_row(self, index: int, update=True):
        count = self._preview_row_count()
        if count > 0:
            self._preview_row_index = max(0, min(index, count - 1))
        else:
            self._preview_row_index = 0
        if self._preview_row_counter:
            self._preview_row_counter.value = f"{self._preview_row_index + 1}"
            try:
                self._preview_row_counter.update()
            except Exception:
                pass
        if update:
            self._update_preview()
            self.page.update()
            self._notify_row_change()

    def _notify_row_change(self):
        if self.on_row_change and self._row_nav_enabled():
            try:
                self.on_row_change(self._preview_row_index + 1)
            except Exception:
                pass

    def _update_row_nav_visibility(self):
        if self._preview_row_nav is None:
            return
        self._preview_row_nav.visible = self._row_nav_enabled()
        try:
            self._preview_row_nav.update()
        except Exception:
            pass

    def _on_preview_row_field_submit(self):
        try:
            self._set_preview_row(int(self._preview_row_counter.value or "1") - 1)
        except Exception:
            pass

    def _go_to_extreme_row(self, want_max: bool):
        p = self.current_profile
        col = p.excel_column
        # VT personalizado: plantilla fixed con <@< + QR/PDF417/DM + Excel cargado
        is_vt = (
            p.value_source == "fixed"
            and "<@<" in (p.sample_value or "")
            and p.symbology in ("qr", "pdf417", "datamatrix")
            and self.excel_manager is not None
            and getattr(self.excel_manager, "is_loaded", False)
        )
        if not is_vt and not col:
            return
        count = self._preview_row_count()
        if count < 1:
            return
        font_path = ""
        from utils.barcode_module import resolve_font_path

        try:
            font_path = resolve_font_path(p.barcode_font_family) or ""
        except Exception:
            pass
        font_size = float(p.barcode_font_size if p.barcode_font_size is not None else 13.0)

        from utils.variable_text_measure import resolve_vt_text

        def _resolve_row(i):
            if is_vt:
                return (
                    resolve_vt_text(
                        p.sample_value or "",
                        value_source="fixed",
                        excel_column=col or "",
                        excel_manager=self.excel_manager,
                        row_index=i,
                    )
                    or ""
                )
            return self.excel_manager.get_value_at(col, i) or ""

        row = find_extreme_row(
            count,
            _resolve_row,
            font_path,
            font_size,
            want_max=want_max,
        )
        self._set_preview_row(row)

    def _build_preview(self) -> ft.Control:
        self._preview_img = None  # reset; set below for QR/PDF417
        self._preview_canvas_mm = None
        value = self._get_current_value()
        if not value:
            return ft.Container(
                content=ft.Text(t("Introduce un valor para previsualizar"), size=12),
                alignment=ft.Alignment.CENTER,
            )

        p = self.current_profile
        is_qr = p.symbology == "qr"

        if is_qr:
            # --- QR preview as PNG ---
            ok_len, len_msg = validar_longitud_qr(value)
            if not ok_len:
                return ft.Container(
                    content=ft.Text(
                        t("Error: {0}").format(len_msg), size=12, color=ERROR_COLOR
                    ),
                    alignment=ft.Alignment.CENTER,
                )
            sz = self.current_profile.bar_width or 80.0
            try:
                module_size = sz / get_qr_module_count(value)
            except Exception:
                module_size = 0.5

            # Generate QR as PNG (con HRI, patrón DataMatrix)
            try:
                bar_color = self._tinted_display_color(
                    p.color, p.color_tint, p.color_space
                )
                text_color = self._tinted_display_color(
                    p.text_color, p.text_color_tint, p.text_color_space
                )
                ds_pt = p.barcode_font_size if p.barcode_font_size is not None else 9.0
                gap_mm = p.qr_hri_gap_mm if p.qr_hri_gap_mm is not None else 2.0
                position = getattr(p, "qr_hri_position", "below")
                hri_align = getattr(p, "qr_hri_align", "bottom_center")
                hri_line_spacing = getattr(p, "qr_hri_line_spacing", 1.0)
                if hri_line_spacing is None:
                    hri_line_spacing = 1.0
                b64, _cw, _ch, _code_h = get_qr_image_b64(
                    value,
                    size_mm=sz,
                    font_family=p.barcode_font_family,
                    font_size=ds_pt,
                    hri_gap_mm=gap_mm,
                    hri_position=position,
                    fill_color=bar_color,
                    text_color=text_color,
                    hri_align=hri_align,
                    hri_line_spacing=float(hri_line_spacing),
                    del_open=p.qr_del_open or "",
                    del_close=p.qr_del_close if p.qr_del_close is not None else "|",
                    close_as_newline=bool(getattr(p, "qr_del_close_newline", False)),
                )

                zoom = self._zoom_value / 100.0
                PX_PER_MM = 3.78
                s = PX_PER_MM * zoom
                self._preview_canvas_mm = (_cw, _ch)
                img_control = ft.Image(
                    src=b64,
                    width=max(1, int(_cw * s)),
                    height=max(1, int(_ch * s)),
                    fit=ft.BoxFit.FILL,
                )
                self._preview_img = img_control
                return ft.Container(
                    content=img_control,
                    alignment=ft.Alignment.CENTER,
                )
            except Exception:
                self._preview_img = None
                return ft.Container(
                    content=ft.Text(
                        t("Error generando codigo"), size=12, color=ERROR_COLOR
                    ),
                    alignment=ft.Alignment.CENTER,
                )

        is_pdf417 = p.symbology == "pdf417"

        if is_pdf417:
            # --- PDF417 preview as PNG (same pattern as QR) ---
            valid, msg = validate_pdf417(value)
            if not valid:
                return ft.Container(
                    content=ft.Text(
                        t("Error: {0}").format(msg), size=12, color=ERROR_COLOR
                    ),
                    alignment=ft.Alignment.CENTER,
                )
            try:
                bar_width = p.bar_width or 65.0
                bar_color = self._tinted_display_color(
                    p.color, p.color_tint, p.color_space
                )
                text_color = self._tinted_display_color(
                    p.text_color, p.text_color_tint, p.text_color_space
                )
                ds_pt = p.barcode_font_size if p.barcode_font_size is not None else 9.0
                gap_mm = p.pdf417_hri_gap_mm if p.pdf417_hri_gap_mm is not None else 2.0
                position = getattr(p, "pdf417_hri_position", "below")
                hri_align = getattr(p, "pdf417_hri_align", "bottom_center")
                hri_line_spacing = getattr(p, "pdf417_hri_line_spacing", 1.0)
                if hri_line_spacing is None:
                    hri_line_spacing = 1.0
                b64, _cw, _ch, _code_h = get_pdf417_image_b64(
                    value,
                    bar_width=bar_width,
                    bar_color=bar_color,
                    target_height_mm=p.pdf417_height,
                    font_family=p.barcode_font_family,
                    font_size=ds_pt,
                    hri_gap_mm=gap_mm,
                    hri_position=position,
                    text_color=text_color,
                    hri_align=hri_align,
                    hri_line_spacing=float(hri_line_spacing),
                    del_open=p.pdf417_del_open or "",
                    del_close=p.pdf417_del_close
                    if p.pdf417_del_close is not None
                    else "|",
                    close_as_newline=bool(getattr(p, "pdf417_del_close_newline", False)),
                )

                zoom = self._zoom_value / 100.0
                PX_PER_MM = 3.78
                s = PX_PER_MM * zoom
                self._preview_canvas_mm = (_cw, _ch)
                img_control = ft.Image(
                    src=b64,
                    width=max(1, int(_cw * s)),
                    height=max(1, int(_ch * s)),
                    fit=ft.BoxFit.FILL,
                )
                self._preview_img = img_control
                return ft.Container(
                    content=img_control,
                    alignment=ft.Alignment.CENTER,
                )
            except Exception:
                self._preview_img = None
                return ft.Container(
                    content=ft.Text(
                        t("Error generando codigo"), size=12, color=ERROR_COLOR
                    ),
                    alignment=ft.Alignment.CENTER,
                )

        is_datamatrix = _is_datamatrix_family(p.symbology)

        if is_datamatrix:
            col_errs = getattr(self.current_profile, "_column_validation_errors", None) or []
            if col_errs:
                parts = [t("{0} fila(s) invalida(s)").format(len(col_errs))]
                for row_idx, msg in col_errs[:10]:
                    parts.append(t("Fila {0}: {1}").format(row_idx + 1, msg))
                if len(col_errs) > 10:
                    parts.append(t("... y {0} mas").format(len(col_errs) - 10))
                return ft.Container(
                    content=ft.Text(
                        "; ".join(parts),
                        size=11,
                        color=ERROR_COLOR,
                    ),
                    alignment=ft.Alignment.CENTER,
                )

            valid, msg = validate_datamatrix(value)
            if not valid:
                return ft.Container(
                    content=ft.Text(
                        t("Error: {0}").format(msg), size=12, color=ERROR_COLOR
                    ),
                    alignment=ft.Alignment.CENTER,
                )
            try:
                dm_w = p.datamatrix_width or 20.0
                dm_h = p.datamatrix_height or dm_w
                bar_color = self._tinted_display_color(
                    p.color, p.color_tint, p.color_space
                )
                text_color = self._tinted_display_color(
                    p.text_color, p.text_color_tint, p.text_color_space
                )
                font_family = self.current_profile.barcode_font_family
                ds_pt = p.barcode_font_size if p.barcode_font_size is not None else 9.0
                gap_mm = (
                    p.datamatrix_hri_gap_mm
                    if p.datamatrix_hri_gap_mm is not None
                    else 2.0
                )
                position = getattr(p, "datamatrix_hri_position", "below")
                hri_align = getattr(p, "datamatrix_hri_align", "bottom_center")
                hri_line_spacing = getattr(
                    p, "datamatrix_hri_line_spacing", 1.0
                )
                if hri_line_spacing is None:
                    hri_line_spacing = 1.0

                b64, _canvas_w, _canvas_h, _code_h = get_datamatrix_image_b64(
                    value,
                    width_mm=dm_w,
                    height_mm=dm_h,
                    font_family=font_family,
                    font_size=ds_pt,
                    hri_gap_mm=gap_mm,
                    hri_position=position,
                    hri_align=hri_align,
                    hri_line_spacing=float(hri_line_spacing),
                    fill_color=bar_color,
                    text_color=text_color,
                    formato=p.datamatrix_format,
                    del_open=p.datamatrix_del_open or "",
                    del_close=(
                        p.datamatrix_del_close
                        if p.datamatrix_del_close is not None
                        else "|"
                    ),
                    close_as_newline=bool(
                        getattr(p, "datamatrix_del_close_newline", False)
                    ),
                    symbology=p.symbology,
                )
                if not b64:
                    return ft.Container(
                        content=ft.Text(
                            t("Error generando codigo"), size=12, color=ERROR_COLOR
                        ),
                        alignment=ft.Alignment.CENTER,
                    )

                zoom = self._zoom_value / 100.0
                PX_PER_MM = 3.78
                s = PX_PER_MM * zoom
                self._preview_canvas_mm = (_canvas_w, _canvas_h)
                img_control = ft.Image(
                    src=b64,
                    width=max(1, int(_canvas_w * s)),
                    height=max(1, int(_canvas_h * s)),
                    fit=ft.BoxFit.FILL,
                )
                self._preview_img = img_control
                return ft.Container(
                    content=img_control,
                    alignment=ft.Alignment.CENTER,
                )
            except Exception:
                self._preview_img = None
                return ft.Container(
                    content=ft.Text(
                        t("Error generando codigo"), size=12, color=ERROR_COLOR
                    ),
                    alignment=ft.Alignment.CENTER,
                )

        is_ean13 = p.symbology == "ean13"

        if is_ean13:
            # --- EAN-13 preview — canvas in pixels (like test script) ---
            valid, msg = validate_ean13(value)
            if not valid:
                return ft.Container(
                    content=ft.Text(
                        t("Error: {0}").format(msg), size=12, color=ERROR_COLOR
                    ),
                    alignment=ft.Alignment.CENTER,
                )
            bw_mm = p.bar_width or 37.29
            bh = p.bar_height or 25.93
            ds_pt = p.barcode_font_size if p.barcode_font_size is not None else 13.0
            FONT_PT_TO_MM = 0.3528
            ds_mm = ds_pt * FONT_PT_TO_MM
            font_family = self.current_profile.barcode_font_family

            try:
                pattern, fullcode = encode_ean13(value)
            except Exception:
                return ft.Container(
                    content=ft.Text(
                        t("Error generando codigo"), size=12, color=ERROR_COLOR
                    ),
                    alignment=ft.Alignment.CENTER,
                )
            module_width_mm = bw_mm / get_ean13_module_count()
            elements, c_eff_mm, bar_offset_mm, cw_mm, ds_eff_mm = ean_hri_layout(
                "ean13", fullcode, module_width_mm, ds_mm, font_family
            )
            guard_ext = max(1.5, ds_eff_mm * (0.25 + get_ean13_font_ascender_ratio(font_family)))
            box_h_mm = bh + guard_ext

            zoom = self._zoom_value / 100.0
            display_w = 500 * zoom
            display_h = 200 * zoom
            fit_scale = (
                min(display_w / cw_mm, display_h / box_h_mm)
                if cw_mm > 0 and box_h_mm > 0
                else 1
            )

            s = fit_scale
            cw_px = cw_mm * s
            ch_px = box_h_mm * s
            module_width_px = module_width_mm * s
            guard_ext_px = guard_ext * s
            ds_px = ds_eff_mm * s
            c_eff_px = c_eff_mm * s
            bar_offset_px = bar_offset_mm * s
            bh_px = bh * s

            bar_color = self._tinted_display_color(p.color, p.color_tint, p.color_space)
            text_color = self._tinted_display_color(p.text_color, p.text_color_tint, p.text_color_space)
            shapes = []
            x_px = 0.0
            i = 0
            while i < len(pattern):
                if pattern[i] == "0":
                    x_px += module_width_px
                    i += 1
                    continue
                w_px = module_width_px
                j = i + 1
                while j < len(pattern) and pattern[j] == "1":
                    w_px += module_width_px
                    j += 1
                is_guard = any(m in EAN13_GUARD_MODULES for m in range(i, j))
                rh_px = bh_px + (guard_ext_px if is_guard else 0)
                bx_px = bar_offset_px + x_px
                shapes.append(
                    cv.Rect(
                        bx_px,
                        0,
                        w_px,
                        rh_px,
                        paint=ft.Paint(color=bar_color, style=ft.PaintingStyle.FILL),
                    )
                )
                x_px += w_px
                i = j

            positions = [(digit, cx_mm * s) for digit, cx_mm in elements]

            ts = ft.TextStyle(size=ds_px, color=text_color)
            if font_family:
                ts.font_family = font_family

            for i, (digit_char, cx_px) in enumerate(positions):
                dx_px = cx_px - c_eff_px / 2
                shapes.append(
                    cv.Text(
                        dx_px,
                        ch_px + ds_px * get_ean13_font_descender_ratio(font_family),
                        digit_char,
                        style=ts,
                        alignment=ft.Alignment.BOTTOM_LEFT,
                    )
                )

            preview_canvas = cv.Canvas(shapes, width=cw_px, height=ch_px)

            return ft.Container(
                content=preview_canvas,
                alignment=ft.Alignment.CENTER,
            )

        is_upca = p.symbology == "upca"

        if is_upca:
            # --- UPC-A preview — EAN-13 bars, 1+5+5+1 digit layout ---
            valid, msg = validate_upca(value)
            if not valid:
                return ft.Container(
                    content=ft.Text(
                        t("Error: {0}").format(msg), size=12, color=ERROR_COLOR
                    ),
                    alignment=ft.Alignment.CENTER,
                )
            bw_mm = p.bar_width or 60.0
            bh = p.bar_height or 30.0
            ds_pt = p.barcode_font_size if p.barcode_font_size is not None else 13.0
            FONT_PT_TO_MM = 0.3528
            ds_mm = ds_pt * FONT_PT_TO_MM
            font_family = self.current_profile.barcode_font_family
            try:
                pattern, fullcode = encode_upca(value)
            except Exception:
                return ft.Container(
                    content=ft.Text(
                        t("Error generando codigo"), size=12, color=ERROR_COLOR
                    ),
                    alignment=ft.Alignment.CENTER,
                )
            module_width_mm = bw_mm / get_ean13_module_count()
            elements, c_eff_mm, bar_offset_mm, cw_mm, ds_eff_mm = ean_hri_layout(
                "upca", fullcode, module_width_mm, ds_mm, font_family
            )
            guard_ext = max(1.5, ds_eff_mm * (0.25 + get_ean13_font_ascender_ratio(font_family)))
            box_h_mm = bh + guard_ext

            zoom = self._zoom_value / 100.0
            display_w = 500 * zoom
            display_h = 200 * zoom
            fit_scale = (
                min(display_w / cw_mm, display_h / box_h_mm)
                if cw_mm > 0 and box_h_mm > 0
                else 1
            )

            s = fit_scale
            cw_px = cw_mm * s
            ch_px = box_h_mm * s
            module_width_px = module_width_mm * s
            guard_ext_px = guard_ext * s
            ds_px = ds_eff_mm * s
            c_eff_px = c_eff_mm * s
            bar_offset_px = bar_offset_mm * s
            bh_px = bh * s

            bar_color = self._tinted_display_color(p.color, p.color_tint, p.color_space)
            text_color = self._tinted_display_color(p.text_color, p.text_color_tint, p.text_color_space)
            shapes = []
            x_px = 0.0
            i = 0
            while i < len(pattern):
                if pattern[i] == "0":
                    x_px += module_width_px
                    i += 1
                    continue
                w_px = module_width_px
                j = i + 1
                while j < len(pattern) and pattern[j] == "1":
                    w_px += module_width_px
                    j += 1
                is_guard = any(m in EAN13_GUARD_MODULES for m in range(i, j))
                rh_px = bh_px + (guard_ext_px if is_guard else 0)
                bx_px = bar_offset_px + x_px
                shapes.append(
                    cv.Rect(
                        bx_px,
                        0,
                        w_px,
                        rh_px,
                        paint=ft.Paint(color=bar_color, style=ft.PaintingStyle.FILL),
                    )
                )
                x_px += w_px
                i = j

            positions = [(digit, cx_mm * s) for digit, cx_mm in elements]

            ts = ft.TextStyle(size=ds_px, color=text_color)
            if font_family:
                ts.font_family = font_family

            for i, (digit_char, cx_px) in enumerate(positions):
                dx_px = cx_px - c_eff_px / 2
                shapes.append(
                    cv.Text(
                        dx_px,
                        ch_px + ds_px * get_ean13_font_descender_ratio(font_family),
                        digit_char,
                        style=ts,
                        alignment=ft.Alignment.BOTTOM_LEFT,
                    )
                )

            preview_canvas = cv.Canvas(shapes, width=cw_px, height=ch_px)

            return ft.Container(
                content=preview_canvas,
                alignment=ft.Alignment.CENTER,
            )

        is_upce = p.symbology == "upce"

        if is_upce:
            valid, msg = validate_upce(value)
            if not valid:
                return ft.Container(
                    content=ft.Text(
                        t("Error: {0}").format(msg), size=12, color=ERROR_COLOR
                    ),
                    alignment=ft.Alignment.CENTER,
                )
            bw_mm = p.bar_width or 44.0
            bh = p.bar_height or 30.0
            ds_pt = p.barcode_font_size if p.barcode_font_size is not None else 13.0
            FONT_PT_TO_MM = 0.3528
            ds_mm = ds_pt * FONT_PT_TO_MM
            font_family = self.current_profile.barcode_font_family

            try:
                pattern, fullcode = encode_upce(value)
            except Exception:
                return ft.Container(
                    content=ft.Text(
                        t("Error generando codigo"), size=12, color=ERROR_COLOR
                    ),
                    alignment=ft.Alignment.CENTER,
                )
            module_width_mm = bw_mm / get_upce_module_count()
            elements, c_eff_mm, bar_offset_mm, cw_mm, ds_eff_mm = ean_hri_layout(
                "upce", fullcode, module_width_mm, ds_mm, font_family
            )
            guard_ext = max(1.5, ds_eff_mm * (0.25 + get_ean13_font_ascender_ratio(font_family)))
            box_h_mm = bh + guard_ext

            zoom = self._zoom_value / 100.0
            display_w = 500 * zoom
            display_h = 200 * zoom
            fit_scale = (
                min(display_w / cw_mm, display_h / box_h_mm)
                if cw_mm > 0 and box_h_mm > 0
                else 1
            )

            s = fit_scale
            cw_px = cw_mm * s
            ch_px = box_h_mm * s
            module_width_px = module_width_mm * s
            guard_ext_px = guard_ext * s
            ds_px = ds_eff_mm * s
            c_eff_px = c_eff_mm * s
            bar_offset_px = bar_offset_mm * s
            bh_px = bh * s

            bar_color = self._tinted_display_color(p.color, p.color_tint, p.color_space)
            text_color = self._tinted_display_color(p.text_color, p.text_color_tint, p.text_color_space)
            shapes = []
            x_px = 0.0
            i = 0
            while i < len(pattern):
                if pattern[i] == "0":
                    x_px += module_width_px
                    i += 1
                    continue
                w_px = module_width_px
                j = i + 1
                while j < len(pattern) and pattern[j] == "1":
                    w_px += module_width_px
                    j += 1
                is_guard = any(m in UPCE_GUARD_MODULES for m in range(i, j))
                rh_px = bh_px + (guard_ext_px if is_guard else 0)
                bx_px = bar_offset_px + x_px
                shapes.append(
                    cv.Rect(
                        bx_px,
                        0,
                        w_px,
                        rh_px,
                        paint=ft.Paint(color=bar_color, style=ft.PaintingStyle.FILL),
                    )
                )
                x_px += w_px
                i = j

            ts = ft.TextStyle(size=ds_px, color=text_color)
            if font_family:
                ts.font_family = font_family

            for digit_char, cx_mm in elements:
                dx_px = cx_mm * s - c_eff_px / 2
                shapes.append(
                    cv.Text(
                        dx_px,
                        ch_px + ds_px * get_ean13_font_descender_ratio(font_family),
                        digit_char,
                        style=ts,
                        alignment=ft.Alignment.BOTTOM_LEFT,
                    )
                )

            preview_canvas = cv.Canvas(shapes, width=cw_px, height=ch_px)

            return ft.Container(
                content=preview_canvas,
                alignment=ft.Alignment.CENTER,
            )

        is_isbn13 = p.symbology == "isbn13"

        if is_isbn13:
            # --- ISBN-13 preview — EAN-13 bars + smaller "ISBN" text above ---
            valid, msg = validate_isbn13(value)
            if not valid:
                return ft.Container(
                    content=ft.Text(
                        t("Error: {0}").format(msg), size=12, color=ERROR_COLOR
                    ),
                    alignment=ft.Alignment.CENTER,
                )
            bw_mm = p.bar_width or 37.29
            bh = p.bar_height or 25.93
            ds_pt = p.barcode_font_size if p.barcode_font_size is not None else 13.0
            FONT_PT_TO_MM = 0.3528
            ds_mm = ds_pt * FONT_PT_TO_MM
            font_family = self.current_profile.barcode_font_family
            show_title = (
                getattr(self.current_profile, "isbn13_show_title", "Sí") == "Sí"
            )

            try:
                pattern, fullcode = encode_ean13(value)
            except Exception:
                return ft.Container(
                    content=ft.Text(
                        t("Error generando codigo"), size=12, color=ERROR_COLOR
                    ),
                    alignment=ft.Alignment.CENTER,
                )

            module_width_mm = bw_mm / get_ean13_module_count()
            elements, c_eff_mm, bar_offset_mm, cw_mm, ds_eff_mm = ean_hri_layout(
                "isbn13", fullcode, module_width_mm, ds_mm, font_family
            )
            guard_ext = max(1.5, ds_eff_mm * (0.25 + get_ean13_font_ascender_ratio(font_family)))
            # Label y hueco siguen al cuerpo CRUDO del campo (no al ds_eff capado por las barras):
            # el label es texto libre sobre las barras, no está limitado por el ancho del código
            isbn_ds_pt = max(1.0, ds_pt - ISBN_SIZE_OFFSET)
            isbn_ds_mm = isbn_ds_pt * FONT_PT_TO_MM
            # Separación = 0.25×cuerpo (mismo factor que los números), sin suelo:
            # debe bajar y subir con el cuerpo (el blanco inferior tampoco tiene suelo)
            isbn_gap_mm = ds_pt * FONT_PT_TO_MM * 0.25
            # Caja em del label (line-height) para que no quede recortado por arriba
            _isbn_line_ratio = get_ean13_font_ascender_ratio(
                font_family
            ) + get_ean13_font_descender_ratio(font_family)
            _isbn_label_h_mm = isbn_ds_mm * _isbn_line_ratio
            if show_title:
                box_h_mm = _isbn_label_h_mm + isbn_gap_mm + guard_ext + bh
            else:
                box_h_mm = guard_ext + bh

            zoom = self._zoom_value / 100.0
            display_w = 500 * zoom
            display_h = 200 * zoom
            fit_scale = (
                min(display_w / cw_mm, display_h / box_h_mm)
                if cw_mm > 0 and box_h_mm > 0
                else 1
            )

            s = fit_scale
            cw_px = cw_mm * s
            ch_px = box_h_mm * s
            module_width_px = module_width_mm * s
            guard_ext_px = guard_ext * s
            ds_px = ds_eff_mm * s
            isbn_ds_px = isbn_ds_mm * s
            _isbn_label_h_px = _isbn_label_h_mm * s
            c_eff_px = c_eff_mm * s
            bar_offset_px = bar_offset_mm * s
            bh_px = bh * s

            bars_top_px = (_isbn_label_h_px + isbn_gap_mm * s) if show_title else 0

            bar_color = self._tinted_display_color(p.color, p.color_tint, p.color_space)
            text_color = self._tinted_display_color(p.text_color, p.text_color_tint, p.text_color_space)
            shapes = []
            x_px = 0.0
            i = 0
            while i < len(pattern):
                if pattern[i] == "0":
                    x_px += module_width_px
                    i += 1
                    continue
                w_px = module_width_px
                j = i + 1
                while j < len(pattern) and pattern[j] == "1":
                    w_px += module_width_px
                    j += 1
                is_guard = any(m in EAN13_GUARD_MODULES for m in range(i, j))
                rh_px = bh_px + (guard_ext_px if is_guard else 0)
                bx_px = bar_offset_px + x_px
                shapes.append(
                    cv.Rect(
                        bx_px,
                        bars_top_px,
                        w_px,
                        rh_px,
                        paint=ft.Paint(color=bar_color, style=ft.PaintingStyle.FILL),
                    )
                )
                x_px += w_px
                i = j

            positions = [(digit, cx_mm * s) for digit, cx_mm in elements]

            if show_title:
                # ISBN text above bars (compact, centered)
                isbn_label = _format_isbn13(fullcode)
                isbn_ts = ft.TextStyle(
                    size=isbn_ds_px, color=text_color, font_family=font_family or None
                )
                isbn_cx = bar_offset_px + bw_mm * s / 2
                shapes.append(
                    cv.Text(
                        isbn_cx,
                        _isbn_label_h_px,
                        isbn_label,
                        style=isbn_ts,
                        alignment=ft.Alignment.BOTTOM_CENTER,
                        text_align=ft.TextAlign.CENTER,
                    )
                )

            # Digit text below bars
            ts = ft.TextStyle(size=ds_px, color=text_color)
            if font_family:
                ts.font_family = font_family

            for i, (digit_char, cx_px) in enumerate(positions):
                dx_px = cx_px - c_eff_px / 2
                shapes.append(
                    cv.Text(
                        dx_px,
                        ch_px + ds_px * get_ean13_font_descender_ratio(font_family),
                        digit_char,
                        style=ts,
                        alignment=ft.Alignment.BOTTOM_LEFT,
                    )
                )

            preview_canvas = cv.Canvas(shapes, width=cw_px, height=ch_px)

            return ft.Container(
                content=preview_canvas,
                alignment=ft.Alignment.CENTER,
            )

        is_ean8 = p.symbology == "ean8"

        if is_ean8:
            # --- EAN-8 preview — same rendering as EAN-13 but with 67 modules ---
            valid, msg = validate_ean8(value)
            if not valid:
                return ft.Container(
                    content=ft.Text(
                        t("Error: {0}").format(msg), size=12, color=ERROR_COLOR
                    ),
                    alignment=ft.Alignment.CENTER,
                )
            bw_mm = p.bar_width or 37.29
            bh = p.bar_height or 25.93
            ds_pt = p.barcode_font_size if p.barcode_font_size is not None else 13.0
            FONT_PT_TO_MM = 0.3528
            ds_mm = ds_pt * FONT_PT_TO_MM
            font_family = self.current_profile.barcode_font_family

            try:
                pattern, fullcode = encode_ean8(value)
            except Exception as e:
                return ft.Container(
                    content=ft.Text(
                        t("Error: {0} (value={1})").format(str(e)[:40], value),
                        size=12,
                        color=ERROR_COLOR,
                    ),
                    alignment=ft.Alignment.CENTER,
                )

            module_width_mm = bw_mm / get_ean8_module_count()
            elements, c_eff_mm, bar_offset_mm, cw_mm, ds_eff_mm = ean_hri_layout(
                "ean8", fullcode, module_width_mm, ds_mm, font_family
            )
            guard_ext = max(1.5, ds_eff_mm * (0.25 + get_ean13_font_ascender_ratio(font_family)))
            box_h_mm = bh + guard_ext

            zoom = self._zoom_value / 100.0
            display_w = 500 * zoom
            display_h = 200 * zoom
            fit_scale = (
                min(display_w / cw_mm, display_h / box_h_mm)
                if cw_mm > 0 and box_h_mm > 0
                else 1
            )

            s = fit_scale
            cw_px = cw_mm * s
            ch_px = box_h_mm * s
            module_width_px = module_width_mm * s
            guard_ext_px = guard_ext * s
            ds_px = ds_eff_mm * s
            c_eff_px = c_eff_mm * s
            bh_px = bh * s

            bar_color = self._tinted_display_color(p.color, p.color_tint, p.color_space)
            text_color = self._tinted_display_color(p.text_color, p.text_color_tint, p.text_color_space)
            shapes = []

            x_px = 0.0
            i = 0
            while i < len(pattern):
                if pattern[i] == "0":
                    x_px += module_width_px
                    i += 1
                    continue
                w_px = module_width_px
                j = i + 1
                while j < len(pattern) and pattern[j] == "1":
                    w_px += module_width_px
                    j += 1
                is_guard = any(m in EAN8_GUARD_MODULES for m in range(i, j))
                rh_px = bh_px + (guard_ext_px if is_guard else 0)
                bx_px = x_px
                shapes.append(
                    cv.Rect(
                        bx_px,
                        0,
                        w_px,
                        rh_px,
                        paint=ft.Paint(color=bar_color, style=ft.PaintingStyle.FILL),
                    )
                )
                x_px += w_px
                i = j

            positions = [(digit, cx_mm * s) for digit, cx_mm in elements]

            ts = ft.TextStyle(size=ds_px, color=text_color)
            if font_family:
                ts.font_family = font_family

            for i, (digit_char, cx_px) in enumerate(positions):
                dx_px = cx_px - c_eff_px / 2
                shapes.append(
                    cv.Text(
                        dx_px,
                        ch_px + ds_px * get_ean13_font_descender_ratio(font_family),
                        digit_char,
                        style=ts,
                        alignment=ft.Alignment.BOTTOM_LEFT,
                    )
                )

            preview_canvas = cv.Canvas(shapes, width=cw_px, height=ch_px)

            return ft.Container(
                content=preview_canvas,
                alignment=ft.Alignment.CENTER,
            )

        is_ean5 = p.symbology == "ean5"

        if is_ean5:
            # --- EAN-5 preview — digits ABOVE bars, no guard extensions ---
            valid, msg = validate_ean5(value)
            if not valid:
                return ft.Container(
                    content=ft.Text(
                        t("Error: {0}").format(msg), size=12, color=ERROR_COLOR
                    ),
                    alignment=ft.Alignment.CENTER,
                )
            bw_mm = p.bar_width or 30.0
            bh = p.bar_height or 25.0
            ds_pt = p.barcode_font_size if p.barcode_font_size is not None else 13.0
            FONT_PT_TO_MM = 0.3528
            ds_mm = ds_pt * FONT_PT_TO_MM
            font_family = self.current_profile.barcode_font_family
            from utils.barcode_module import (
                resolve_font_path,
                get_font_text_metrics,
            )

            _asc, _desc_neg, _total = get_font_text_metrics(
                resolve_font_path(font_family)
            )
            char_w_mm = ds_mm * 0.50
            gap_mm = p.ean5_hri_gap_mm if p.ean5_hri_gap_mm is not None else 2.0

            try:
                pattern, fullcode = encode_ean5(value)
            except Exception as e:
                return ft.Container(
                    content=ft.Text(
                        t("Error: {0} (value={1})").format(str(e)[:40], value),
                        size=12,
                        color=ERROR_COLOR,
                    ),
                    alignment=ft.Alignment.CENTER,
                )

            module_width_mm = bw_mm / get_ean5_module_count()
            box_h_mm = _asc * ds_mm + gap_mm + bh
            cw_mm = 47 * module_width_mm

            zoom = self._zoom_value / 100.0
            display_w = 500 * zoom
            display_h = 200 * zoom
            fit_scale = (
                min(display_w / cw_mm, display_h / (_asc * ds_mm + bh))
                if cw_mm > 0 and _asc * ds_mm + bh > 0
                else 1
            )

            s = fit_scale
            cw_px = cw_mm * s
            ch_px = box_h_mm * s
            module_width_px = module_width_mm * s
            ds_px = ds_mm * s
            char_w_px = char_w_mm * s
            bh_px = bh * s
            baseline_px = _asc * ds_px
            bar_top_px = baseline_px + gap_mm * s

            bar_color = self._tinted_display_color(p.color, p.color_tint, p.color_space)
            text_color = self._tinted_display_color(p.text_color, p.text_color_tint, p.text_color_space)
            shapes = []

            x_px = 0.0
            i = 0
            while i < len(pattern):
                if pattern[i] == "0":
                    x_px += module_width_px
                    i += 1
                    continue
                w_px = module_width_px
                j = i + 1
                while j < len(pattern) and pattern[j] == "1":
                    w_px += module_width_px
                    j += 1
                bx_px = x_px
                shapes.append(
                    cv.Rect(
                        bx_px,
                        bar_top_px,
                        w_px,
                        bh_px,
                        paint=ft.Paint(color=bar_color, style=ft.PaintingStyle.FILL),
                    )
                )
                x_px += w_px
                i = j

            # Digit positions: evenly spaced across total width
            zone_w = 47 / 5.0
            positions = []
            for idx in range(5):
                cm = (idx + 0.5) * zone_w
                positions.append((fullcode[idx], cm * module_width_px))

            ts = ft.TextStyle(size=ds_px, color=text_color)
            if font_family:
                ts.font_family = font_family

            if ds_px > 0:
                for digit_char, cx_px in positions:
                    dx_px = cx_px - char_w_px / 2
                    shapes.append(
                        cv.Text(
                            dx_px, 0, digit_char, style=ts, alignment=ft.Alignment.TOP_LEFT
                        )
                    )

            preview_canvas = cv.Canvas(shapes, width=cw_px, height=ch_px)

            return ft.Container(
                content=preview_canvas,
                alignment=ft.Alignment.CENTER,
            )

        is_itf14 = p.symbology == "itf14"

        if is_itf14:
            # --- ITF-14 preview — bars + bearer bar + digits below ---

            # Resolve según tipo GTIN
            raw_value = value
            gtin_type = p.itf14_gtin_type
            if gtin_type == "gtin13":
                valid, msg = validate_gtin13(raw_value)
                if not valid:
                    return ft.Container(
                        content=ft.Text(
                            t("Error: {0}").format(msg), size=12, color=ERROR_COLOR
                        ),
                        alignment=ft.Alignment.CENTER,
                    )
                raw_value = gtin13_to_gtin14(raw_value)
            else:
                if len(raw_value) != 14:
                    return ft.Container(
                        content=ft.Text(
                            t("Error: Debe tener 14 digitos (GTIN-14)"),
                            size=12,
                            color=ERROR_COLOR,
                        ),
                        alignment=ft.Alignment.CENTER,
                    )
                valid, msg = validate_itf14(raw_value)
                if not valid:
                    return ft.Container(
                        content=ft.Text(
                            t("Error: {0}").format(msg), size=12, color=ERROR_COLOR
                        ),
                        alignment=ft.Alignment.CENTER,
                    )
            bw_mm = p.bar_width or 65.0
            ds_pt = self.current_profile.barcode_font_size
            FONT_PT_TO_MM = 0.3528
            ds_mm = ds_pt * FONT_PT_TO_MM
            font_family = self.current_profile.barcode_font_family
            from utils.barcode_module import (
                resolve_font_path,
                get_font_cap_height_ratio,
                measure_text,
            )

            _font_path = resolve_font_path(font_family)
            _cap = get_font_cap_height_ratio(_font_path)
            _desc_abs = get_ean13_font_descender_ratio(font_family)
            digit_bottom_gap = p.itf14_hri_gap_mm
            position = getattr(p, "itf14_hri_position", "below")

            printer_type = p.itf14_printer_type
            dims = calc_itf14_dimensions(bw_mm, printer_type, p.bar_height or 0)
            bearer_w_mm = dims["bearer_thickness_mm"]
            quiet_zone_mm = dims["quiet_zone_mm"]
            bearer_sides = dims["bearer_sides"]
            bh = dims["bar_height"]
            cw_mm = dims["bar_content_width"]

            try:
                pattern, fullcode = encode_itf14(raw_value)
            except Exception as e:
                return ft.Container(
                    content=ft.Text(
                        t("Error: {0} (value={1})").format(str(e)[:40], raw_value),
                        size=12,
                        color=ERROR_COLOR,
                    ),
                    alignment=ft.Alignment.CENTER,
                )

            module_width_mm = cw_mm / ITF14_TOTAL_MODULES

            if position == "above":
                from utils.barcode_module import get_font_text_metrics

                _asc, _, _ = get_font_text_metrics(_font_path)
                box_h_mm = _asc * ds_mm + digit_bottom_gap + bh
            else:
                box_h_mm = bh + digit_bottom_gap + _cap * ds_mm
            if bearer_sides == "2":
                box_h_mm -= bearer_w_mm / 2
            total_vis_mm = cw_mm + 2 * quiet_zone_mm + bearer_w_mm

            zoom = self._zoom_value / 100.0
            PX_PER_MM = 3.78
            s = PX_PER_MM * zoom
            cw_px = cw_mm * s
            ch_px = box_h_mm * s
            total_vis_px = total_vis_mm * s
            quiet_zone_px = quiet_zone_mm * s
            module_width_px = module_width_mm * s
            ds_px = ds_mm * s
            bh_px = bh * s
            bearer_w_px = bearer_w_mm * s
            half_bearer_px = bearer_w_px / 2

            bars_start_x = half_bearer_px + quiet_zone_px

            bar_color = self._tinted_display_color(p.color, p.color_tint, p.color_space)
            text_color = self._tinted_display_color(p.text_color, p.text_color_tint, p.text_color_space)
            y_off_px = 0.0
            if position == "above":
                from utils.barcode_module import get_font_text_metrics

                _asc, _, _ = get_font_text_metrics(_font_path)
                y_off_px = (_asc * ds_mm + digit_bottom_gap) * s

            shapes = []

            if bearer_sides == "4":
                shapes.append(
                    cv.Rect(
                        half_bearer_px,
                        half_bearer_px + y_off_px,
                        cw_px + 2 * quiet_zone_px,
                        bh_px - bearer_w_px,
                        paint=ft.Paint(
                            color=bar_color,
                            style=ft.PaintingStyle.STROKE,
                            stroke_width=bearer_w_px,
                        ),
                    )
                )
            else:
                shapes.append(
                    cv.Rect(
                        0,
                        half_bearer_px + y_off_px,
                        total_vis_px,
                        bearer_w_px,
                        paint=ft.Paint(color=bar_color, style=ft.PaintingStyle.FILL),
                    )
                )
                shapes.append(
                    cv.Rect(
                        0,
                        bh_px - half_bearer_px - bearer_w_px + y_off_px,
                        total_vis_px,
                        bearer_w_px,
                        paint=ft.Paint(color=bar_color, style=ft.PaintingStyle.FILL),
                    )
                )

            # Bars
            x_px = bars_start_x
            i = 0
            while i < len(pattern):
                if pattern[i] == "0":
                    x_px += module_width_px
                    i += 1
                    continue
                w_px = module_width_px
                j = i + 1
                while j < len(pattern) and pattern[j] == "1":
                    w_px += module_width_px
                    j += 1
                bx_px = x_px
                shapes.append(
                    cv.Rect(
                        bx_px,
                        half_bearer_px + y_off_px,
                        w_px,
                        bh_px - bearer_w_px,
                        paint=ft.Paint(color=bar_color, style=ft.PaintingStyle.FILL),
                    )
                )
                x_px += w_px
                i = j

            hri = format_itf14_hri(fullcode)
            hri_w_px = measure_text(hri, _font_path, ds_px)
            hri_start_x = total_vis_px / 2 - hri_w_px / 2
            ts = ft.TextStyle(size=ds_px, color=text_color)
            if font_family:
                ts.font_family = font_family

            if position == "above":
                if ds_px > 0:
                    shapes.append(
                        cv.Text(
                            hri_start_x,
                            0,
                            hri,
                            style=ts,
                            alignment=ft.Alignment.TOP_LEFT,
                        )
                    )
            else:
                if ds_px > 0:
                    shapes.append(
                        cv.Text(
                            hri_start_x,
                            ch_px + _desc_abs * ds_px,
                            hri,
                            style=ts,
                            alignment=ft.Alignment.BOTTOM_LEFT,
                        )
                    )
            preview = cv.Canvas(shapes, width=total_vis_px, height=ch_px)
            return ft.Container(
                content=preview,
                alignment=ft.Alignment.CENTER,
            )

        # --- Code 39 preview — Canvas (mismo patrón que ITF-14) ---
        is_code39 = p.symbology == "code39"

        if is_code39:
            valid, msg = validate_code39(value)
            if not valid:
                return ft.Container(
                    content=ft.Text(
                        t("Error: {0}").format(msg), size=12, color=ERROR_COLOR
                    ),
                    alignment=ft.Alignment.CENTER,
                )
            ok_len, len_msg = validar_longitud_code39(value)
            if not ok_len:
                return ft.Container(
                    content=ft.Text(
                        t("Error: {0}").format(len_msg), size=12, color=ERROR_COLOR
                    ),
                    alignment=ft.Alignment.CENTER,
                )
            try:
                pattern, fullcode = encode_code39(value)
            except Exception as e:
                return ft.Container(
                    content=ft.Text(
                        t("Error: {0} (value={1})").format(str(e)[:40], value),
                        size=12,
                        color=ERROR_COLOR,
                    ),
                    alignment=ft.Alignment.CENTER,
                )
            bw_mm = p.bar_width or 80.0
            bh = p.bar_height or 30.0
            module_width_mm = bw_mm / len(pattern)

            FONT_PT_TO_MM = 0.3528
            ds_pt = p.barcode_font_size if p.barcode_font_size is not None else 13.0
            ds_mm = ds_pt * FONT_PT_TO_MM
            font_family = self.current_profile.barcode_font_family
            from utils.barcode_module import (
                resolve_font_path,
                get_font_cap_height_ratio,
                measure_text,
            )

            _font_path = resolve_font_path(font_family)
            gap_mm = p.code39_hri_gap_mm if p.code39_hri_gap_mm is not None else 2.0
            position = getattr(p, "code39_hri_position", "below")

            zoom = self._zoom_value / 100.0
            PX_PER_MM = 3.78
            s = PX_PER_MM * zoom
            ds_px = ds_mm * s

            bar_color = self._tinted_display_color(p.color, p.color_tint, p.color_space)
            text_color = self._tinted_display_color(p.text_color, p.text_color_tint, p.text_color_space)

            if position == "below":
                _cap = get_font_cap_height_ratio(_font_path)
                _desc_abs = get_ean13_font_descender_ratio(font_family)
                box_h_mm = bh + gap_mm + _cap * ds_mm
                cw_px = bw_mm * s
                ch_px = box_h_mm * s
                module_width_px = module_width_mm * s
                bh_px = bh * s

                shapes = []

                x_px = 0.0
                i = 0
                while i < len(pattern):
                    if pattern[i] == "0":
                        x_px += module_width_px
                        i += 1
                        continue
                    w_px = module_width_px
                    j = i + 1
                    while j < len(pattern) and pattern[j] == "1":
                        w_px += module_width_px
                        j += 1
                    shapes.append(
                        cv.Rect(
                            x_px,
                            0,
                            w_px,
                            bh_px,
                            paint=ft.Paint(
                                color=bar_color, style=ft.PaintingStyle.FILL
                            ),
                        )
                    )
                    x_px += w_px
                    i = j

                hri_w_px = measure_text(fullcode, _font_path, ds_px)
                hri_start_x = cw_px / 2 - hri_w_px / 2
                ts = ft.TextStyle(size=ds_px, color=text_color)
                if font_family:
                    ts.font_family = font_family
                if ds_px > 0:
                    shapes.append(
                        cv.Text(
                            hri_start_x,
                            ch_px + _desc_abs * ds_px,
                            fullcode,
                            style=ts,
                            alignment=ft.Alignment.BOTTOM_LEFT,
                        )
                    )
            else:
                from utils.barcode_module import get_font_text_metrics

                _asc, _, _ = get_font_text_metrics(_font_path)
                box_h_mm = _asc * ds_mm + gap_mm + bh
                cw_px = bw_mm * s
                ch_px = box_h_mm * s
                module_width_px = module_width_mm * s
                bar_top_px = _asc * ds_px + gap_mm * s

                shapes = []

                x_px = 0.0
                i = 0
                while i < len(pattern):
                    if pattern[i] == "0":
                        x_px += module_width_px
                        i += 1
                        continue
                    w_px = module_width_px
                    j = i + 1
                    while j < len(pattern) and pattern[j] == "1":
                        w_px += module_width_px
                        j += 1
                    shapes.append(
                        cv.Rect(
                            x_px,
                            bar_top_px,
                            w_px,
                            bh * s,
                            paint=ft.Paint(
                                color=bar_color, style=ft.PaintingStyle.FILL
                            ),
                        )
                    )
                    x_px += w_px
                    i = j

                hri_w_px = measure_text(fullcode, _font_path, ds_px)
                hri_start_x = cw_px / 2 - hri_w_px / 2
                ts = ft.TextStyle(size=ds_px, color=text_color)
                if font_family:
                    ts.font_family = font_family
                if ds_px > 0:
                    shapes.append(
                        cv.Text(
                            hri_start_x,
                            0,
                            fullcode,
                            style=ts,
                            alignment=ft.Alignment.TOP_LEFT,
                        )
                    )

            preview = cv.Canvas(shapes, width=cw_px, height=ch_px)
            return ft.Container(
                content=preview,
                alignment=ft.Alignment.CENTER,
            )

        # --- Code128 preview with HRI text ---
        valid, msg = validate_code128(value)
        if not valid:
            return ft.Container(
                content=ft.Text(
                    t("Error: {0}").format(msg), size=12, color=ERROR_COLOR
                ),
                alignment=ft.Alignment.CENTER,
            )
        ok_len, len_msg = validar_longitud_code128(value)
        if not ok_len:
            return ft.Container(
                content=ft.Text(
                    t("Error: {0}").format(len_msg), size=12, color=ERROR_COLOR
                ),
                alignment=ft.Alignment.CENTER,
            )
        bw_mm = p.bar_width or 80.0
        bh = p.bar_height or 30.0
        try:
            total_modules = get_module_count(value)
            module_width_mm = bw_mm / total_modules
        except Exception:
            module_width_mm = 0.33
        quiet_zone_mm = 10 * module_width_mm
        total_preview_mm = bw_mm + 2 * quiet_zone_mm

        bar_color = self._tinted_display_color(p.color, p.color_tint, p.color_space)
        text_color = self._tinted_display_color(p.text_color, p.text_color_tint, p.text_color_space)
        rects = get_barcode_rects(value, module_width=module_width_mm, bar_height=bh)
        if not rects:
            return ft.Container(
                content=ft.Text(
                    t("Error generando codigo"), size=12, color=ERROR_COLOR
                ),
                alignment=ft.Alignment.CENTER,
            )

        FONT_PT_TO_MM = 0.3528
        ds_pt = p.barcode_font_size if p.barcode_font_size is not None else 13.0
        ds_mm = ds_pt * FONT_PT_TO_MM
        font_family = self.current_profile.barcode_font_family
        gap_mm = p.code128_hri_gap_mm if p.code128_hri_gap_mm is not None else 2.0
        position = getattr(p, "code128_hri_position", "below")

        zoom = self._zoom_value / 100.0
        PX_PER_MM = 3.78
        s = PX_PER_MM * zoom
        ds_px = ds_mm * s
        qz_px = quiet_zone_mm * s

        from utils.barcode_module import resolve_font_path, measure_text

        _font_path = resolve_font_path(font_family)

        if position == "below":
            from utils.barcode_module import get_font_cap_height_ratio

            _cap = get_font_cap_height_ratio(_font_path)
            _desc_abs = get_ean13_font_descender_ratio(font_family)
            box_h_mm = bh + gap_mm + _cap * ds_mm
            cw_px = total_preview_mm * s
            ch_px = box_h_mm * s
            bh_px = bh * s

            shapes = []
            for rx, ry, rw, rh in rects:
                shapes.append(
                    cv.Rect(
                        qz_px + rx * s,
                        0,
                        rw * s,
                        bh_px,
                        paint=ft.Paint(color=bar_color, style=ft.PaintingStyle.FILL),
                    )
                )

            hri_w_px = measure_text(value, _font_path, ds_px)
            hri_start_x = cw_px / 2 - hri_w_px / 2
            ts = ft.TextStyle(size=ds_px, color=text_color)
            if font_family:
                ts.font_family = font_family
            if ds_px > 0:
                shapes.append(
                    cv.Text(
                        hri_start_x,
                        ch_px + _desc_abs * ds_px,
                        value,
                        style=ts,
                        alignment=ft.Alignment.BOTTOM_LEFT,
                    )
                )
        else:
            from utils.barcode_module import get_font_text_metrics

            _asc, _, _ = get_font_text_metrics(_font_path)
            box_h_mm = _asc * ds_mm + gap_mm + bh
            cw_px = total_preview_mm * s
            ch_px = box_h_mm * s

            shapes = []
            bar_top_px = _asc * ds_px + gap_mm * s
            for rx, ry, rw, rh in rects:
                shapes.append(
                    cv.Rect(
                        qz_px + rx * s,
                        bar_top_px,
                        rw * s,
                        bh * s,
                        paint=ft.Paint(color=bar_color, style=ft.PaintingStyle.FILL),
                    )
                )

            hri_w_px = measure_text(value, _font_path, ds_px)
            hri_start_x = cw_px / 2 - hri_w_px / 2
            ts = ft.TextStyle(size=ds_px, color=text_color)
            if font_family:
                ts.font_family = font_family
            if ds_px > 0:
                shapes.append(
                    cv.Text(
                        hri_start_x,
                        0,
                        value,
                        style=ts,
                        alignment=ft.Alignment.TOP_LEFT,
                    )
                )

        preview = cv.Canvas(shapes, width=cw_px, height=ch_px)
        return ft.Container(
            content=preview,
            alignment=ft.Alignment.CENTER,
        )

    def _on_zoom_change(self, e):
        self._zoom_value = float(e.control.value)
        if self._zoom_label:
            self._zoom_label.value = f"{int(self._zoom_value)}%"
            self._zoom_label.update()
        if self._preview_img and self._preview_canvas_mm:
            zoom = self._zoom_value / 100.0
            PX_PER_MM = 3.78
            s = PX_PER_MM * zoom
            cw_mm, ch_mm = self._preview_canvas_mm
            self._preview_img.width = max(1, int(cw_mm * s))
            self._preview_img.height = max(1, int(ch_mm * s))
            try:
                self._preview_img.update()
            except AssertionError:
                pass
        else:
            self._update_preview()

    def _rebuild_dim_fields(self):
        """Rebuild the dimension fields section from SYMBOLOGY_CONFIG."""
        self._ensure_profile_minimums()
        if self._dim_fields_section:
            self._symbology_fields.clear()
            self._dim_fields_section.content = None
            self._dim_fields_section.content = self._build_dim_fields()
            # After building fields, compute PDF417 min dimensions and set defaults
            if self.current_profile.symbology == "pdf417":
                min_w, min_h = self._compute_pdf417_min_dimensions()
                self.current_profile.pdf417_min_width = min_w
                self.current_profile.pdf417_min_height = min_h
                if self._get_field("pdf417_size"):
                    current_w = self.current_profile.pdf417_size
                    if current_w is None or current_w == 65.0 or current_w < min_w:
                        self._set_field_value("pdf417_size", f"{min_w:.1f}")
                        self.current_profile.pdf417_size = min_w
                        self.current_profile.bar_width = min_w
                if self._get_field("pdf417_height"):
                    current_h = self.current_profile.pdf417_height
                    if current_h is None or current_h == 30.0 or current_h < min_h:
                        self._set_field_value("pdf417_height", f"{min_h:.1f}")
                        self.current_profile.pdf417_height = min_h
            if self.current_profile.symbology == "upca":
                bw = self.current_profile.bar_width or 37.29
                self.current_profile.bar_width = max(29.83, bw)
                self._set_field_value(
                    "bar_width", str(self._display_mm(self.current_profile.bar_width))
                )
                bh = self.current_profile.bar_height or 25.91
                self.current_profile.bar_height = max(20.73, bh)
                self._set_field_value(
                    "bar_height", str(self._display_mm(self.current_profile.bar_height))
                )
            if self.current_profile.symbology == "upce":
                bw = self.current_profile.bar_width or 22.11
                self.current_profile.bar_width = max(17.69, bw)
                self._set_field_value(
                    "bar_width", str(self._display_mm(self.current_profile.bar_width))
                )
                bh = self.current_profile.bar_height or 25.91
                self.current_profile.bar_height = max(20.73, bh)
                self._set_field_value(
                    "bar_height", str(self._display_mm(self.current_profile.bar_height))
                )
            # GS1: QR — mínimo dinámico según datos (cacheado en el perfil)
            if self.current_profile.symbology == "qr":
                values = self._get_qr_values()
                min_w = self.current_profile.qr_min_size or 20.0
                if (
                    self.current_profile.bar_width is None
                    or self.current_profile.bar_width < min_w
                ):
                    self.current_profile.bar_width = min_w
                    self.current_profile.bar_height = min_w
                self._set_field_value(
                    "qr_size", str(self._display_mm(self.current_profile.bar_width))
                )
                # Validate character limit for QR
                if (
                    self.current_profile.value_source == "excel"
                    and self.current_profile.excel_column
                    and self.excel_manager
                ):
                    col_vals = self.excel_manager.get_column_values(
                        self.current_profile.excel_column
                    )
                    self.current_profile._column_validation_errors = validar_columna_qr(
                        col_vals
                    )
                elif self.current_profile.value_source in ("fixed", "numbering"):
                    if values:
                        ok, msg = validar_longitud_qr(values[0])
                        if not ok:
                            self.current_profile._column_validation_errors = [(0, msg)]
                        else:
                            self.current_profile._column_validation_errors = []
            # GS1: Code128 — ancho 40–165.10mm, mínimo dinámico según datos (cacheado)
            if self.current_profile.symbology == "code128":
                values = self._get_code128_values()
                min_w = self.current_profile.code128_min_width or 40.0
                new_min = min(165.10, min_w)
                print(
                    f"[REBUILD-C128] antes: bw={self.current_profile.bar_width} min_w={min_w} new_min={new_min} values={values}"
                )
                if (
                    self.current_profile.bar_width is None
                    or self.current_profile.bar_width < new_min
                ):
                    self.current_profile.bar_width = new_min
                    print(f"[REBUILD-C128] >>> SET bw={self.current_profile.bar_width}")
                self._set_field_value(
                    "bar_width", str(self._display_mm(self.current_profile.bar_width))
                )
                if (
                    self.current_profile.bar_height is None
                    or self.current_profile.bar_height < 12.0
                ):
                    self.current_profile.bar_height = 12.0
                self._set_field_value(
                    "bar_height", str(self._display_mm(self.current_profile.bar_height))
                )
                # Validate character limit when source is Excel column
                if (
                    self.current_profile.value_source == "excel"
                    and self.current_profile.excel_column
                    and self.excel_manager
                ):
                    col_vals = self.excel_manager.get_column_values(
                        self.current_profile.excel_column
                    )
                    self.current_profile._column_validation_errors = (
                        validar_columna_code128(col_vals)
                    )
                elif self.current_profile.value_source in ("fixed", "numbering"):
                    # Check sample/mask against limit
                    if values:
                        ok, msg = validar_longitud_code128(values[0])
                        if not ok:
                            self.current_profile._column_validation_errors = [(0, msg)]
                        else:
                            self.current_profile._column_validation_errors = []
            # GS1: Code39 — mínimo dinámico según datos (cacheado en el perfil)
            if self.current_profile.symbology == "code39":
                values = self._get_code39_values()
                min_w = self.current_profile.code39_min_width or 40.0
                if (
                    self.current_profile.bar_width is None
                    or self.current_profile.bar_width < min_w
                ):
                    self.current_profile.bar_width = min_w
                self._set_field_value(
                    "bar_width", str(self._display_mm(self.current_profile.bar_width))
                )
                if (
                    self.current_profile.bar_height is None
                    or self.current_profile.bar_height < CODE39_MIN_HEIGHT_MM
                ):
                    self.current_profile.bar_height = CODE39_MIN_HEIGHT_MM
                self._set_field_value(
                    "bar_height", str(self._display_mm(self.current_profile.bar_height))
                )
                if (
                    self.current_profile.value_source == "excel"
                    and self.current_profile.excel_column
                    and self.excel_manager
                ):
                    col_vals = self.excel_manager.get_column_values(
                        self.current_profile.excel_column
                    )
                    self.current_profile._column_validation_errors = (
                        validar_columna_code39_longitud(col_vals)
                    )
                elif self.current_profile.value_source in ("fixed", "numbering"):
                    if values:
                        ok, msg = validar_longitud_code39(values[0])
                        if not ok:
                            self.current_profile._column_validation_errors = [(0, msg)]
                        else:
                            self.current_profile._column_validation_errors = []
            # GS1: EAN-5 — rango GS1 17.92-44.80 x 20.73-51.82mm
            if self.current_profile.symbology == "ean5":
                self.current_profile.bar_width = max(
                    17.92, min(44.80, self.current_profile.bar_width or 17.92)
                )
                self.current_profile.bar_height = max(
                    20.73, min(51.82, self.current_profile.bar_height or 20.73)
                )
                self._set_field_value(
                    "bar_width", str(self._display_mm(self.current_profile.bar_width))
                )
                self._set_field_value(
                    "bar_height", str(self._display_mm(self.current_profile.bar_height))
                )
            # EAN-13 — mantener mínimos y permitir tamaños mayores.
            if self.current_profile.symbology == "ean13":
                self.current_profile.bar_width = max(
                    29.83, self.current_profile.bar_width or 29.83
                )
                self.current_profile.bar_height = max(
                    20.73, self.current_profile.bar_height or 20.73
                )
                self._set_field_value(
                    "bar_width", str(self._display_mm(self.current_profile.bar_width))
                )
                self._set_field_value(
                    "bar_height", str(self._display_mm(self.current_profile.bar_height))
                )
            # EAN-8 — mantener mínimos y permitir tamaños mayores.
            if self.current_profile.symbology == "ean8":
                self.current_profile.bar_width = max(
                    21.38, self.current_profile.bar_width or 21.38
                )
                self.current_profile.bar_height = max(
                    17.05, self.current_profile.bar_height or 17.05
                )
                self._set_field_value(
                    "bar_width", str(self._display_mm(self.current_profile.bar_width))
                )
                self._set_field_value(
                    "bar_height", str(self._display_mm(self.current_profile.bar_height))
                )
            # UPC-A — mantener mínimos y permitir tamaños mayores.
            if self.current_profile.symbology == "upca":
                self.current_profile.bar_width = max(
                    29.83, self.current_profile.bar_width or 29.83
                )
                self.current_profile.bar_height = max(
                    20.73, self.current_profile.bar_height or 20.73
                )
                self._set_field_value(
                    "bar_width", str(self._display_mm(self.current_profile.bar_width))
                )
                self._set_field_value(
                    "bar_height", str(self._display_mm(self.current_profile.bar_height))
                )
            # UPC-E — mantener mínimos y permitir tamaños mayores.
            if self.current_profile.symbology == "upce":
                self.current_profile.bar_width = max(
                    17.69, self.current_profile.bar_width or 17.69
                )
                self.current_profile.bar_height = max(
                    20.73, self.current_profile.bar_height or 20.73
                )
                self._set_field_value(
                    "bar_width", str(self._display_mm(self.current_profile.bar_width))
                )
                self._set_field_value(
                    "bar_height", str(self._display_mm(self.current_profile.bar_height))
                )
            # ISBN-13 — mantener mínimos y permitir tamaños mayores.
            if self.current_profile.symbology == "isbn13":
                self.current_profile.bar_width = max(
                    29.83, self.current_profile.bar_width or 29.83
                )
                self.current_profile.bar_height = max(
                    20.73, self.current_profile.bar_height or 20.73
                )
                self._set_field_value(
                    "bar_width", str(self._display_mm(self.current_profile.bar_width))
                )
                self._set_field_value(
                    "bar_height", str(self._display_mm(self.current_profile.bar_height))
                )
            # GS1: ITF-14 — dynamic limits per printer type
            if self.current_profile.symbology == "itf14":
                printer = self.current_profile.itf14_printer_type
                min_w, min_h = (
                    (89.25, 32.00) if printer == "flexografia" else (71.40, 12.70)
                )
                self.current_profile.bar_width = max(
                    min_w, self.current_profile.bar_width or min_w
                )
                self.current_profile.bar_height = max(
                    min_h, self.current_profile.bar_height or 0.0
                )
                self._set_field_value(
                    "bar_width", str(self._display_mm(self.current_profile.bar_width))
                )
                self._set_field_value(
                    "bar_height", str(self._display_mm(self.current_profile.bar_height))
                )
            if _is_datamatrix_family(self.current_profile.symbology):
                min_w = self.current_profile.datamatrix_min_width or 20.0
                min_h = self.current_profile.datamatrix_min_height or 20.0
                cur_w = self.current_profile.datamatrix_width
                if cur_w is None or cur_w < min_w:
                    self.current_profile.datamatrix_width = min_w
                    self._set_field_value(
                        "datamatrix_width", str(self._display_mm(min_w))
                    )
                self._on_datamatrix_height_recalculate()
            try:
                self._dim_fields_section.update()
            except Exception:
                pass

    def _update_section_visibility(self):
        """Show/hide dim and ITF-14 sections based on current symbology."""
        is_itf14 = self.current_profile.symbology == "itf14"
        if self._dim_fields_section is not None:
            self._dim_fields_section.visible = not is_itf14
            try:
                self._dim_fields_section.update()
            except Exception:
                pass
        if self._itf14_section is not None:
            self._itf14_section.visible = is_itf14
            try:
                self._itf14_section.update()
            except Exception:
                pass
        # Sync sample field / sample button visibility
        is_pdf417 = self.current_profile.symbology == "pdf417"
        is_qr = self.current_profile.symbology == "qr"
        is_datamatrix = _is_datamatrix_family(self.current_profile.symbology)
        src = self.current_profile.value_source
        if self._sample_field is not None:
            self._sample_field.visible = False
        if self._pdf417_sample_btn is not None:
            self._pdf417_sample_btn.visible = src == "fixed" and is_pdf417
        if self._generic_sample_btn is not None:
            self._generic_sample_btn.visible = (
                src == "fixed"
                and not is_pdf417
                and not is_qr
                and not is_datamatrix
            )
        if self._qr_sample_btn is not None:
            self._qr_sample_btn.visible = src == "fixed" and is_qr
        if self._datamatrix_sample_btn is not None:
            self._datamatrix_sample_btn.visible = src == "fixed" and is_datamatrix
        # Color texto HRI aplica a todas las simbologías con HRI.
        if self._text_color_container is not None:
            self._text_color_container.visible = self.current_profile.symbology not in ()
            try:
                self._text_color_container.update()
            except Exception:
                pass
        self._apply_delims_visibility()

    def _on_value_changed(self, e=None):
        source = (
            self._value_source_dropdown.content.controls[0].data
            if self._value_source_dropdown
            else "fixed"
        )
        symb = self.current_profile.symbology

        # Sync symbology from dropdown + force display text
        sd = self._symbology_dropdown.content.controls[0]
        new_symb = sd.data
        # Force the dropdown display text (Flet sometimes doesn't propagate from on_item_click)
        for opt in SYMBOLOGY_OPTIONS:
            if opt[0] == new_symb:
                sd.value = opt[1]
                sd.data = opt[0]
                break
        symb_changed = new_symb != symb
        self.current_profile.symbology = new_symb

        # Sync excel_column from dropdown to profile
        if self._excel_column_dropdown is not None:
            dd = self._excel_column_dropdown.content.controls[0]
            self.current_profile.excel_column = dd.data

        if symb_changed:
            # Reset shared barcode fields to defaults (in case new symbology doesn't define them)
            self.current_profile.barcode_font_size = 13.0
            self.current_profile.barcode_font_family = "OCR-B"
            # Apply SYMBOLOGY_CONFIG defaults (float + dropdown/string fields).
            # This prevents inheriting previous symbology values like HRI position.
            new_cfg = SYMBOLOGY_CONFIG.get(new_symb, {})
            for f in new_cfg.get("fields", []):
                if f["type"] == "float":
                    self.current_profile.__dict__[f["key"]] = float(f["default"])
                else:
                    default_val = f.get("default")
                    if f["key"] in (
                        "itf14_hri_position",
                        "code39_hri_position",
                        "code128_hri_position",
                        "datamatrix_hri_position",
                    ):
                        default_val = _normalize_hri_position(default_val)
                    self.current_profile.__dict__[f["key"]] = default_val
            # Also update the ITF-14 section widgets in UI (not rebuilt on symbology change)
            if self._itf14_body_field is not None:
                self._itf14_body_field.value = str(
                    self.current_profile.barcode_font_size
                )
            if self._itf14_gap_field is not None:
                self._itf14_gap_field.value = self._display_mm(
                    self.current_profile.itf14_hri_gap_mm
                )
            # Sync size fields to bar_width (so preview uses correct dimensions)
            if new_symb == "qr":
                self.current_profile.bar_width = None
                self.current_profile.bar_height = None
            elif new_symb == "pdf417":
                self.current_profile.bar_width = float(
                    self.current_profile.__dict__.get("pdf417_size", 65.0)
                )
            elif new_symb == "itf14":
                self.current_profile.itf14_printer_type = "flexografia"
                self.current_profile.itf14_gtin_type = "gtin14"
                self.current_profile.itf14_hri_position = "below"
                self.current_profile.itf14_hri_gap_mm = 2.0
                self.current_profile.barcode_font_size = 9.0
                self.current_profile.bar_width = 89.25
                self.current_profile.bar_height = 32.00
                # Sync printer dropdown
                if self._itf14_printer_dd is not None:
                    inner = self._itf14_printer_dd.content.controls[0]
                    for opt_val, opt_label in ITF14_PRINTER_OPTIONS:
                        if opt_val == "flexografia":
                            inner.value = opt_label
                            inner.data = opt_val
                            break
                    try:
                        self._itf14_printer_dd.update()
                    except Exception:
                        pass
                # Sync GTIN dropdown
                if self._itf14_gtin_type_dd is not None:
                    inner = self._itf14_gtin_type_dd.content.controls[0]
                    for opt_val, opt_label in ITF14_GTIN_OPTIONS:
                        if opt_val == "gtin14":
                            inner.value = opt_label
                            inner.data = opt_val
                            break
                    try:
                        self._itf14_gtin_type_dd.update()
                    except Exception:
                        pass
                # Sync position dropdown
                if self._itf14_pos_dd is not None:
                    inner = self._itf14_pos_dd.content.controls[0]
                    for opt_val, opt_label in [
                        ("above", t("above")),
                        ("below", t("below")),
                    ]:
                        if opt_val == "below":
                            inner.value = opt_label
                            inner.data = opt_val
                            break
                    try:
                        self._itf14_pos_dd.update()
                    except Exception:
                        pass
                # Sync dimension fields
                if self._itf14_width_field is not None:
                    self._itf14_width_field.value = self._display_mm(89.25)
                    try:
                        self._itf14_width_field.update()
                    except Exception:
                        pass
                if self._itf14_height_field is not None:
                    self._itf14_height_field.value = self._display_mm(32.00)
                    try:
                        self._itf14_height_field.update()
                    except Exception:
                        pass
                if self._itf14_body_field is not None:
                    self._itf14_body_field.value = "9.0"
                    try:
                        self._itf14_body_field.update()
                    except Exception:
                        pass
                if self._itf14_gap_field is not None:
                    self._itf14_gap_field.value = self._display_mm(2.0)
                    try:
                        self._itf14_gap_field.update()
                    except Exception:
                        pass
            elif _is_datamatrix_family(new_symb):
                self.current_profile.datamatrix_hri_position = "below"
                self.current_profile.datamatrix_hri_gap_mm = 2.0
                self.current_profile.barcode_font_size = 9.0
                self.current_profile.barcode_font_family = "OCR-B"
                self.current_profile.datamatrix_width = None
            elif new_symb == "code128":
                self.current_profile.bar_width = None
                self.current_profile.bar_height = None
            elif new_symb == "code39":
                self.current_profile.bar_width = None
                self.current_profile.bar_height = None
            elif new_symb in ("ean5", "ean13", "ean8", "upca", "upce", "isbn13"):
                self.current_profile.bar_width = None
                self.current_profile.bar_height = None
            # Auto-set sample value from config BEFORE rebuilding dim fields
            sample_fn = SYMBOLOGY_CONFIG.get(new_symb, {}).get("sample_value")
            if sample_fn:
                self._sample_field.value = sample_fn()
                self._sample_field.update()
                self.current_profile.sample_value = self._sample_field.value

            # Reset data source to defaults on symbology change
            self.current_profile.value_source = "fixed"
            self.current_profile.excel_column = ""
            self.current_profile.mask = ""
            # Separadores default vacíos (QR/PDF417/DataMatrix): sin detección de campo
            self.current_profile.__dict__[f"{new_symb}_del_open"] = ""
            self.current_profile.__dict__[f"{new_symb}_del_close"] = ""

            if self._value_source_dropdown:
                dd = self._value_source_dropdown.content.controls[0]
                for opt in VALUE_SOURCE_OPTIONS:
                    if opt[0] == "fixed":
                        dd.value = opt[1]
                        dd.data = opt[0]
                        break
                dd.update()

            if self._excel_column_dropdown is not None:
                self._excel_column_dropdown.visible = False
                excel_dd = self._excel_column_dropdown.content.controls[0]
                excel_dd.data = ""
                excel_dd.value = t("(sin seleccion)")
                excel_dd.update()

            if self._mask_field:
                self._mask_field.value = ""
                self._mask_field.update()
            if self._mask_container:
                self._mask_container.visible = False
                self._mask_container.update()

            self._update_section_visibility()
            self._rebuild_dim_fields()
            # Calcular el cuerpo HRI máximo que cabe (simbología/ancho default) y rellenar el campo
            max_pt = self._ean_max_body_pt()
            if max_pt is not None:
                self.current_profile.barcode_font_size = round(max_pt, 2)
                self._set_field_value("barcode_font_size", f"{round(max_pt, 2):g}")
            # Recalcular mínimos sobre los datos de muestra por defecto del nuevo código
            if new_symb in ("datamatrix", "pdf417", "qr", "code128", "code39"):
                self._recalculate_minimums()
            # Reset zoom to 100%
            self._zoom_value = 100.0
            if self._zoom_slider:
                self._zoom_slider.value = 100.0
            if self._zoom_label:
                self._zoom_label.value = "100%"
        else:
            self._rebuild_dim_fields()
            # Si es PDF417, forzar campos al mínimo calculado para el origen de datos actual
            if self.current_profile.symbology == "pdf417":
                mw = self.current_profile.pdf417_min_width
                mh = self.current_profile.pdf417_min_height
                if self._get_field("pdf417_size"):
                    if (
                        self.current_profile.pdf417_size is None
                        or self.current_profile.pdf417_size < mw
                    ):
                        self._set_field_value("pdf417_size", f"{mw:.1f}")
                        self.current_profile.pdf417_size = mw
                        self.current_profile.bar_width = mw
                if self._get_field("pdf417_height"):
                    if (
                        self.current_profile.pdf417_height is None
                        or self.current_profile.pdf417_height < mh
                    ):
                        self._set_field_value("pdf417_height", f"{mh:.1f}")
                        self.current_profile.pdf417_height = mh
            if self.current_profile.symbology == "upca":
                bw = self.current_profile.bar_width or 37.29
                self.current_profile.bar_width = max(29.83, bw)
                bh = self.current_profile.bar_height or 25.91
                self.current_profile.bar_height = max(20.73, bh)
            if self.current_profile.symbology == "upce":
                bw = self.current_profile.bar_width or 22.11
                self.current_profile.bar_width = max(17.69, bw)
                bh = self.current_profile.bar_height or 25.91
                self.current_profile.bar_height = max(20.73, bh)
            # GS1: Code128 — ancho mínimo cacheado en el perfil, max 165.10mm
            if self.current_profile.symbology == "code128":
                min_w = self.current_profile.code128_min_width or 40.0
                new_min = min(165.10, min_w)
                if (
                    self.current_profile.bar_width is None
                    or self.current_profile.bar_width < new_min
                ):
                    self.current_profile.bar_width = new_min
                self._set_field_value(
                    "bar_width", str(self._display_mm(self.current_profile.bar_width))
                )
                if (
                    self.current_profile.bar_height is None
                    or self.current_profile.bar_height < 12.0
                ):
                    self.current_profile.bar_height = max(
                        12.0, min(32.0, self.current_profile.bar_height or 30.0)
                    )
                self._set_field_value(
                    "bar_height", str(self._display_mm(self.current_profile.bar_height))
                )
            # GS1: QR — ancho mínimo cacheado en el perfil
            if self.current_profile.symbology == "qr":
                min_w = self.current_profile.qr_min_size or 20.0
                if (
                    self.current_profile.bar_width is None
                    or self.current_profile.bar_width < min_w
                ):
                    self.current_profile.bar_width = min_w
                    self.current_profile.bar_height = min_w
                self._set_field_value(
                    "qr_size", str(self._display_mm(self.current_profile.bar_width))
                )
            # GS1: Code39 — ancho mínimo cacheado en el perfil
            if self.current_profile.symbology == "code39":
                min_w = self.current_profile.code39_min_width or 40.0
                if (
                    self.current_profile.bar_width is None
                    or self.current_profile.bar_width < min_w
                ):
                    self.current_profile.bar_width = min_w
                self._set_field_value(
                    "bar_width", str(self._display_mm(self.current_profile.bar_width))
                )
                if (
                    self.current_profile.bar_height is None
                    or self.current_profile.bar_height < CODE39_MIN_HEIGHT_MM
                ):
                    self.current_profile.bar_height = CODE39_MIN_HEIGHT_MM
                self._set_field_value(
                    "bar_height", str(self._display_mm(self.current_profile.bar_height))
                )
            # GS1: EAN-5 — rango GS1 17.92-44.80 x 20.73-51.82mm
            if self.current_profile.symbology == "ean5":
                self.current_profile.bar_width = max(
                    17.92, min(44.80, self.current_profile.bar_width or 17.92)
                )
                self.current_profile.bar_height = max(
                    20.73, min(51.82, self.current_profile.bar_height or 20.73)
                )
                self._set_field_value(
                    "bar_width", str(self._display_mm(self.current_profile.bar_width))
                )
                self._set_field_value(
                    "bar_height", str(self._display_mm(self.current_profile.bar_height))
                )
            # EAN-13 — mantener mínimos y permitir tamaños mayores.
            if self.current_profile.symbology == "ean13":
                self.current_profile.bar_width = max(
                    29.83, self.current_profile.bar_width or 29.83
                )
                self.current_profile.bar_height = max(
                    20.73, self.current_profile.bar_height or 20.73
                )
                self._set_field_value(
                    "bar_width", str(self._display_mm(self.current_profile.bar_width))
                )
                self._set_field_value(
                    "bar_height", str(self._display_mm(self.current_profile.bar_height))
                )
            # EAN-8 — mantener mínimos y permitir tamaños mayores.
            if self.current_profile.symbology == "ean8":
                self.current_profile.bar_width = max(
                    21.38, self.current_profile.bar_width or 21.38
                )
                self.current_profile.bar_height = max(
                    17.05, self.current_profile.bar_height or 17.05
                )
                self._set_field_value(
                    "bar_width", str(self._display_mm(self.current_profile.bar_width))
                )
                self._set_field_value(
                    "bar_height", str(self._display_mm(self.current_profile.bar_height))
                )
            # UPC-A — mantener mínimos y permitir tamaños mayores.
            if self.current_profile.symbology == "upca":
                self.current_profile.bar_width = max(
                    29.83, self.current_profile.bar_width or 29.83
                )
                self.current_profile.bar_height = max(
                    20.73, self.current_profile.bar_height or 20.73
                )
                self._set_field_value(
                    "bar_width", str(self._display_mm(self.current_profile.bar_width))
                )
                self._set_field_value(
                    "bar_height", str(self._display_mm(self.current_profile.bar_height))
                )
            # UPC-E — mantener mínimos y permitir tamaños mayores.
            if self.current_profile.symbology == "upce":
                self.current_profile.bar_width = max(
                    17.69, self.current_profile.bar_width or 17.69
                )
                self.current_profile.bar_height = max(
                    20.73, self.current_profile.bar_height or 20.73
                )
                self._set_field_value(
                    "bar_width", str(self._display_mm(self.current_profile.bar_width))
                )
                self._set_field_value(
                    "bar_height", str(self._display_mm(self.current_profile.bar_height))
                )
            # ISBN-13 — mantener mínimos y permitir tamaños mayores.
            if self.current_profile.symbology == "isbn13":
                self.current_profile.bar_width = max(
                    29.83, self.current_profile.bar_width or 29.83
                )
                self.current_profile.bar_height = max(
                    20.73, self.current_profile.bar_height or 20.73
                )
                self._set_field_value(
                    "bar_width", str(self._display_mm(self.current_profile.bar_width))
                )
                self._set_field_value(
                    "bar_height", str(self._display_mm(self.current_profile.bar_height))
                )

        self._update_row_nav_visibility()
        self._update_preview()
        if self.on_profile_changed:
            self.on_profile_changed(self.current_profile)
        self.page.update()

    def _sync_fields_to_profile(self):
        """Sync all UI field values to current_profile without recalculation."""
        if self._sample_field:
            self.current_profile.sample_value = self._sample_field.value or ""
        if self._mask_field:
            self.current_profile.mask = self._mask_field.value or ""
        if self._value_source_dropdown:
            self.current_profile.value_source = (
                self._value_source_dropdown.content.controls[0].data
            )
        if self._excel_column_dropdown is not None:
            dd = self._excel_column_dropdown.content.controls[0]
            self.current_profile.excel_column = dd.data
        symb = self.current_profile.symbology
        cfg = SYMBOLOGY_CONFIG.get(symb, {})
        for field in cfg.get("fields", []):
            key = field["key"]
            val = self._get_field_value(key)
            if val is not None:
                try:
                    if field["type"] == "float":
                        if key == "barcode_font_size":
                            self.current_profile.__dict__[key] = float(val)
                        else:
                            self.current_profile.__dict__[key] = self._save_to_mm(val)
                    else:
                        try:
                            self.current_profile.__dict__[key] = float(val)
                        except (ValueError, TypeError):
                            self.current_profile.__dict__[key] = val
                except (ValueError, TypeError):
                    pass

    def _ean_max_body_pt(self):
        """Cuerpo HRI máximo (pt) que cabe en la zona para la simbología/ancho/fuente actuales."""
        sym = self.current_profile.symbology
        if sym not in ("ean13", "ean8", "upca", "upce", "isbn13"):
            return None
        cfg = SYMBOLOGY_CONFIG.get(sym, {})
        default_w = next(
            (f["default"] for f in cfg.get("fields", []) if f["key"] == "bar_width"),
            29.83,
        )
        bw = self.current_profile.bar_width or default_w
        font = self.current_profile.barcode_font_family or "OCR-B"
        if sym in ("ean13", "isbn13"):
            n_mod = get_ean13_module_count()
        elif sym == "ean8":
            n_mod = get_ean8_module_count()
        elif sym == "upca":
            n_mod = get_upca_module_count()
        else:
            n_mod = get_upce_module_count()
        module_mm = bw / n_mod
        max_mm = ean_hri_max_ds_mm(sym, module_mm, font)
        return max_mm / 0.3528

    def _on_preview_trigger(self, e=None):
        if e is not None and hasattr(e, "control") and e.control is not None:
            normalize_decimal_input(e)
            if getattr(e.control, "data", None) == "barcode_font_size":
                try:
                    new_val = float(e.control.value)
                except (ValueError, TypeError):
                    new_val = None
                if new_val is not None:
                    _EAN_FAMILY = ("ean13", "ean8", "ean5", "upca", "upce", "isbn13")
                    _min_pt = 1.0 if self.current_profile.symbology in _EAN_FAMILY else 0.0
                    if new_val < _min_pt:
                        e.control.value = f"{_min_pt:g}"
                        try:
                            e.control.update()
                        except Exception:
                            pass
                    else:
                        max_pt = self._ean_max_body_pt()
                        if max_pt is not None and new_val > max_pt:
                            prev = min(
                                self.current_profile.barcode_font_size or max_pt,
                                max_pt,
                            )
                            e.control.value = f"{round(prev, 2):g}"
                            try:
                                e.control.update()
                            except Exception:
                                pass
            if getattr(e.control, "data", None) in (
                "datamatrix_hri_line_spacing",
                "qr_hri_line_spacing",
                "pdf417_hri_line_spacing",
            ):
                try:
                    e.control.value = f"{round(float(e.control.value), 2):g}"
                    e.control.update()
                except (ValueError, TypeError):
                    pass
        self._sync_fields_to_profile()
        symb = self.current_profile.symbology
        max_pt = self._ean_max_body_pt()
        if max_pt is not None:
            cur = self.current_profile.barcode_font_size
            if cur is not None and cur > max_pt:
                    self.current_profile.barcode_font_size = round(max_pt, 2)
                    self._set_field_value("barcode_font_size", f"{round(max_pt, 2):g}")
        # Special: QR size maps to bar_width/bar_height
        if symb == "qr":
            qr_val = self._get_field_value("qr_size")
            if qr_val:
                try:
                    qr_mm = self._save_to_mm(qr_val)
                    self.current_profile.bar_width = qr_mm
                    self.current_profile.bar_height = qr_mm
                except (ValueError, TypeError):
                    pass
        # Special: PDF417 size maps to bar_width, validate dimensions
        if symb == "pdf417":
            pdf_val = self._get_field_value("pdf417_size")
            if pdf_val:
                try:
                    pdf_mm = self._save_to_mm(pdf_val)
                    self.current_profile.bar_width = pdf_mm
                except (ValueError, TypeError):
                    pass
            # Data source changed (text, column, source) → recalc both dimensions
            if (
                e is None
                or not hasattr(e, "control")
                or getattr(e.control, "data", None)
                not in ("pdf417_size", "pdf417_height")
            ):
                min_w, min_h = self._compute_pdf417_min_dimensions()
                self.current_profile.pdf417_min_width = min_w
                self.current_profile.pdf417_min_height = min_h
                if (
                    self.current_profile.pdf417_size is None
                    or self.current_profile.pdf417_size < min_w
                ):
                    self._set_field_value("pdf417_size", f"{min_w:.1f}")
                    self.current_profile.pdf417_size = min_w
                    self.current_profile.bar_width = min_w
                if (
                    self.current_profile.pdf417_height is None
                    or self.current_profile.pdf417_height < min_h
                ):
                    self._set_field_value("pdf417_height", f"{min_h:.1f}")
                    self.current_profile.pdf417_height = min_h
                # Force a full page update so field changes are visible
                try:
                    self.dialog.update()
                except Exception:
                    pass

        if self.current_profile.symbology == "upca":
            self.current_profile.bar_width = max(
                29.83, self.current_profile.bar_width or 37.29
            )
            self.current_profile.bar_height = max(
                20.73, self.current_profile.bar_height or 25.91
            )
        if self.current_profile.symbology == "upce":
            self.current_profile.bar_width = max(
                17.69, self.current_profile.bar_width or 22.11
            )
            self.current_profile.bar_height = max(
                20.73, self.current_profile.bar_height or 25.91
            )
        if self.current_profile.symbology == "ean5":
            self.current_profile.bar_width = max(
                17.92, self.current_profile.bar_width or 17.92
            )
            self.current_profile.bar_height = max(
                20.73, self.current_profile.bar_height or 20.73
            )
        if self.current_profile.symbology == "ean13":
            self.current_profile.bar_width = max(
                29.83, self.current_profile.bar_width or 29.83
            )
            self.current_profile.bar_height = max(
                20.73, self.current_profile.bar_height or 20.73
            )
        if self.current_profile.symbology == "ean8":
            self.current_profile.bar_width = max(
                21.38, self.current_profile.bar_width or 21.38
            )
            self.current_profile.bar_height = max(
                17.05, self.current_profile.bar_height or 17.05
            )
        if self.current_profile.symbology == "isbn13":
            self.current_profile.bar_width = max(
                29.83, self.current_profile.bar_width or 29.83
            )
            self.current_profile.bar_height = max(
                20.73, self.current_profile.bar_height or 20.73
            )
        # GS1: QR — mínimo dinámico según datos (cacheado en el perfil)
        if self.current_profile.symbology == "qr":
            if (
                e is None
                or not hasattr(e, "control")
                or getattr(e.control, "data", None) not in ("qr_size",)
            ):
                min_w = self.current_profile.qr_min_size or 20.0
                if (
                    self.current_profile.bar_width is None
                    or self.current_profile.bar_width < min_w
                ):
                    self.current_profile.bar_width = min_w
                    self.current_profile.bar_height = min_w
                self._set_field_value(
                    "qr_size", self._display_mm(self.current_profile.bar_width)
                )
                try:
                    self.dialog.update()
                except Exception:
                    pass
        # GS1: Code128 — ancho mínimo dinámico según datos (cacheado en el perfil)
        if self.current_profile.symbology == "code128":
            if (
                e is None
                or not hasattr(e, "control")
                or getattr(e.control, "data", None) not in ("bar_width", "bar_height")
            ):
                min_w = self.current_profile.code128_min_width or 40.0
                new_min = min(165.10, min_w)
                if (
                    self.current_profile.bar_width is None
                    or self.current_profile.bar_width < new_min
                ):
                    self.current_profile.bar_width = new_min
                self._set_field_value(
                    "bar_width", self._display_mm(self.current_profile.bar_width)
                )
                try:
                    self.dialog.update()
                except Exception:
                    pass
            self.current_profile.bar_height = max(
                12.0, min(32.0, self.current_profile.bar_height or 30.0)
            )
            self._set_field_value(
                "bar_height", self._display_mm(self.current_profile.bar_height)
            )
        # GS1: Code39 — ancho mínimo dinámico según datos (cacheado en el perfil)
        if self.current_profile.symbology == "code39":
            if (
                e is None
                or not hasattr(e, "control")
                or getattr(e.control, "data", None) not in ("bar_width", "bar_height")
            ):
                min_w = self.current_profile.code39_min_width or 40.0
                if (
                    self.current_profile.bar_width is None
                    or self.current_profile.bar_width < min_w
                ):
                    self.current_profile.bar_width = min_w
                self._set_field_value(
                    "bar_width", self._display_mm(self.current_profile.bar_width)
                )
                try:
                    self.dialog.update()
                except Exception:
                    pass
            self.current_profile.bar_height = max(
                CODE39_MIN_HEIGHT_MM, self.current_profile.bar_height or 30.0
            )
            self._set_field_value(
                "bar_height", self._display_mm(self.current_profile.bar_height)
            )
        # GS1: EAN-5 complementario 17.92–44.80 × 20.73–51.82mm
        if self.current_profile.symbology == "ean5":
            self.current_profile.bar_width = max(
                17.92, min(44.80, self.current_profile.bar_width or 30.0)
            )
            self.current_profile.bar_height = max(
                20.73, min(51.82, self.current_profile.bar_height or 25.0)
            )
        # ISBN-13: mantener mínimos y permitir tamaños mayores.
        if self.current_profile.symbology == "isbn13":
            self.current_profile.bar_width = max(
                29.83, self.current_profile.bar_width or 37.29
            )
            self.current_profile.bar_height = max(
                20.73, self.current_profile.bar_height or 25.91
            )
        # GS1: ITF-14 — dynamic limits per printer type
        if self.current_profile.symbology == "itf14":
            printer = self.current_profile.itf14_printer_type
            if printer == "flexografia":
                min_w, min_h = 89.25, 32.00
            else:
                min_w, min_h = 71.40, 12.70
            self.current_profile.bar_width = max(
                min_w, self.current_profile.bar_width or min_w
            )
            self.current_profile.bar_height = max(
                min_h, self.current_profile.bar_height or 0.0
            )
            if self._itf14_width_field is not None:
                self._itf14_width_field.value = self._display_mm(
                    self.current_profile.bar_width
                )
            if self._itf14_height_field is not None:
                self._itf14_height_field.value = self._display_mm(
                    self.current_profile.bar_height
                )

        # ITF-14: validate Excel column when column or GTIN type changes
        if (
            self.current_profile.symbology == "itf14"
            and self.current_profile.value_source == "excel"
            and self.current_profile.excel_column
        ):
            from utils.barcode_module import validate_excel_column_for_itf14

            values = (
                self.excel_manager.get_column_values(self.current_profile.excel_column)
                if self.excel_manager
                else []
            )
            self.current_profile._column_validation_errors = (
                validate_excel_column_for_itf14(
                    values, self.current_profile.itf14_gtin_type
                )
            )
        elif (
            self.current_profile.symbology == "code39"
            and self.current_profile.value_source == "excel"
            and self.current_profile.excel_column
        ):
            values = (
                self.excel_manager.get_column_values(self.current_profile.excel_column)
                if self.excel_manager
                else []
            )
            self.current_profile._column_validation_errors = (
                validate_excel_column_for_code39(values)
                + validar_columna_code39_longitud(values)
            )
        elif (
            self.current_profile.symbology == "code128"
            and self.current_profile.value_source == "excel"
            and self.current_profile.excel_column
        ):
            values = (
                self.excel_manager.get_column_values(self.current_profile.excel_column)
                if self.excel_manager
                else []
            )
            self.current_profile._column_validation_errors = validar_columna_code128(
                values
            )
        elif (
            self.current_profile.symbology == "qr"
            and self.current_profile.value_source == "excel"
            and self.current_profile.excel_column
        ):
            values = (
                self.excel_manager.get_column_values(self.current_profile.excel_column)
                if self.excel_manager
                else []
            )
            self.current_profile._column_validation_errors = validar_columna_qr(values)
        elif (
            self.current_profile.symbology == "datamatrix_gs1"
            and self.current_profile.value_source == "excel"
            and self.current_profile.excel_column
        ):
            values = (
                self.excel_manager.get_column_values(self.current_profile.excel_column)
                if self.excel_manager
                else []
            )
            self.current_profile._column_validation_errors = (
                validar_columna_datamatrix_gs1(values)
            )
        elif (
            self.current_profile.symbology == "datamatrix_dl"
            and self.current_profile.value_source == "excel"
            and self.current_profile.excel_column
        ):
            values = (
                self.excel_manager.get_column_values(self.current_profile.excel_column)
                if self.excel_manager
                else []
            )
            self.current_profile._column_validation_errors = (
                validar_columna_datamatrix_dl(values)
            )
        else:
            self.current_profile._column_validation_errors = []

        self._update_preview()
        if self.on_profile_changed:
            self.on_profile_changed(self.current_profile)

    def _update_preview(self):
        if self._preview_container and self.dialog:
            self._preview_container.content = self._build_preview()
            self._preview_container.update()

    # ------------------------------------------------------------------
    # Color picker
    # ------------------------------------------------------------------
    def _tinted_display_color(
        self, base_hex: str, tint_pct: float, color_space: str
    ) -> str:
        if color_space != "SPOT" or tint_pct >= 99.9:
            return base_hex
        try:
            val = base_hex.lstrip("#")
            if len(val) == 6:
                r0, g0, b0 = tuple(int(val[i : i + 2], 16) for i in (0, 2, 4))
            else:
                return base_hex
            t = max(0.0, min(100.0, float(tint_pct))) / 100.0
            r = max(0, min(255, int(round(255 + (r0 - 255) * t))))
            g = max(0, min(255, int(round(255 + (g0 - 255) * t))))
            b = max(0, min(255, int(round(255 + (b0 - 255) * t))))
            return f"#{r:02x}{g:02x}{b:02x}"
        except Exception:
            return base_hex

    def _update_color_swatch(self):
        if self._color_swatch_button:
            _display = self._tinted_display_color(
                self.current_profile.color,
                self.current_profile.color_tint,
                self.current_profile.color_space,
            )
            self._color_swatch_button.bgcolor = _display
            self._color_swatch_button.update()
        if self._text_color_swatch_button:
            _display = self._tinted_display_color(
                self.current_profile.text_color,
                self.current_profile.text_color_tint,
                self.current_profile.text_color_space,
            )
            self._text_color_swatch_button.bgcolor = _display
            self._text_color_swatch_button.update()

    def _open_color_picker(self, e):
        self._color_target = "bar"
        self._launch_color_picker()

    def _open_text_color_picker(self, e):
        self._color_target = "text"
        self._launch_color_picker()

    def _launch_color_picker(self):
        if self.color_picker_dialog is None:
            self.color_picker_dialog = ColorPickerDialog(
                page=self.page,
                on_color_selected=self._on_color_selected,
                on_dismissed=self._reopen_settings_dialog,
            )
            if self.extracted_spot_colors:
                self.color_picker_dialog.set_extracted_spots(self.extracted_spot_colors)

        p = self.current_profile
        if self._color_target == "text":
            rgb_color, cmyk_color, color_space = (
                p.text_color,
                p.text_color_cmyk,
                p.text_color_space,
            )
            color_name, tint = p.text_color_name, p.text_color_tint
        else:
            rgb_color, cmyk_color, color_space = p.color, p.color_cmyk, p.color_space
            color_name, tint = p.color_name, p.color_tint
        # El padre queda abierto debajo (el picker se apila encima) — no pop_dialog
        self.color_picker_dialog.open(
            rgb_color=rgb_color,
            cmyk_color=cmyk_color,
            color_space=color_space,
            color_name=color_name,
            tint=tint,
        )

    def _on_color_selected(
        self,
        rgb_color: str,
        cmyk_color: tuple,
        color_space: str,
        color_name: str = "",
        tint: float = 100.0,
    ):
        if self._color_target == "text":
            self.current_profile.text_color = rgb_color
            self.current_profile.text_color_cmyk = cmyk_color
            self.current_profile.text_color_space = color_space
            self.current_profile.text_color_name = color_name
            self.current_profile.text_color_tint = tint
        else:
            self.current_profile.color = rgb_color
            self.current_profile.color_cmyk = cmyk_color
            self.current_profile.color_space = color_space
            self.current_profile.color_name = color_name
            self.current_profile.color_tint = tint
        self._update_color_swatch()
        self._update_preview()

    def _reopen_settings_dialog(self):
        self._saved_keyboard_handler = self.page.on_keyboard_event
        self.page.on_keyboard_event = self._on_page_keyboard
        reopen_dialog(self.page, self.dialog)

    def set_extracted_spots(self, spots: list):
        self.extracted_spot_colors = spots or []
        if self.color_picker_dialog is not None:
            self.color_picker_dialog.set_extracted_spots(self.extracted_spot_colors)

    # ------------------------------------------------------------------
    # Save / Validate
    # ------------------------------------------------------------------
    def _on_save_click(self, e):
        name = self.current_profile.name.strip() if self.current_profile.name else ""
        if not name:
            self._show_error(t("El nombre del perfil es obligatorio"))
            return
        symb = self._symbology_dropdown.content.controls[0].data

        # Validate sample value
        if self._value_source_dropdown.content.controls[0].data == "fixed":
            sample_val = self._sample_field.value or ""
            if symb == "itf14":
                gtin_type = (
                    self._itf14_gtin_type_dd.content.controls[0].data
                    if self._itf14_gtin_type_dd
                    else "gtin14"
                )
                if gtin_type == "gtin13":
                    if len(sample_val) != 13 or not sample_val.isdigit():
                        self._show_error(
                            t(
                                "El valor debe tener exactamente 13 dígitos numéricos (GTIN-13)"
                            )
                        )
                        return
                else:
                    if len(sample_val) != 14 or not sample_val.isdigit():
                        self._show_error(
                            t(
                                "El valor debe tener exactamente 14 dígitos numéricos (GTIN-14)"
                            )
                        )
                        return
            validate_fn = SYMBOLOGY_CONFIG.get(symb, {}).get("validate")
            if validate_fn and symb != "itf14":
                valid, msg = validate_fn(sample_val)
                if not valid:
                    self._show_error(t("Valor de muestra inválido: {0}").format(msg))
                    return
            # code128: validar longitud máxima práctica
            if symb == "code128":
                ok_len, len_msg = validar_longitud_code128(sample_val)
                if not ok_len:
                    self._show_error(len_msg)
                    return
            # QR: validar longitud máxima práctica
            if symb == "qr":
                ok_len, len_msg = validar_longitud_qr(sample_val)
                if not ok_len:
                    self._show_error(len_msg)
                    return
            # Code39: validar longitud máxima práctica
            if symb == "code39":
                ok_len, len_msg = validar_longitud_code39(sample_val)
                if not ok_len:
                    self._show_error(len_msg)
                    return

        # ITF-14: validate width against printer type limits
        if symb == "itf14":
            try:
                width_val = self._save_to_mm(
                    self._get_field_value("bar_width") or self._itf14_width_field.value
                )
            except (ValueError, TypeError):
                width_val = 65.0
            printer = (
                self._itf14_printer_dd.content.controls[0].data
                if self._itf14_printer_dd
                else "flexografia"
            )
            abbr = self._unit_abbr()
            if printer == "flexografia":
                MIN_W = 89.25
            else:
                MIN_W = 71.40
            if width_val < MIN_W:
                self._show_error(
                    t("Para impresión {0} el ancho mínimo permitido es de {1}").format(
                        t(printer), f"{self._display_mm(MIN_W)} {abbr}"
                    )
                )
                return
            try:
                height_val = self._save_to_mm(self._itf14_height_field.value)
            except (ValueError, TypeError):
                height_val = 0.0
            min_h = 32.00 if printer == "flexografia" else 12.70
            height_val = max(min_h, height_val)
            self.current_profile.bar_height = height_val

        # Read all dynamic field values
        cfg = SYMBOLOGY_CONFIG.get(symb, {})
        for field in cfg.get("fields", []):
            key = field["key"]
            val = self._get_field_value(key)
            if val is not None:
                try:
                    if field["type"] == "float":
                        if key == "barcode_font_size":
                            self.current_profile.__dict__[key] = float(val)
                        else:
                            self.current_profile.__dict__[key] = self._save_to_mm(val)
                    else:
                        self.current_profile.__dict__[key] = val
                except (ValueError, TypeError):
                    pass

        if symb == "qr":
            qr_val = self._get_field_value("qr_size")
            if qr_val:
                try:
                    qr_mm = self._save_to_mm(qr_val)
                    self.current_profile.bar_width = qr_mm
                    self.current_profile.bar_height = qr_mm
                except (ValueError, TypeError):
                    pass

        if symb == "pdf417":
            pdf_val = self._get_field_value("pdf417_size")
            if pdf_val:
                try:
                    pdf_mm = self._save_to_mm(pdf_val)
                    self.current_profile.bar_width = pdf_mm
                except (ValueError, TypeError):
                    pass

        font_size = self._get_field_value("barcode_font_size")
        if font_size is not None:
            try:
                self.current_profile.barcode_font_size = float(font_size)
            except (ValueError, TypeError):
                pass

        self.current_profile.name = name
        self.current_profile.sample_value = self._sample_field.value or ""
        if self._mask_field:
            self.current_profile.mask = self._mask_field.value or ""
        self._update_profile_list()
        if self.on_profile_changed:
            self.on_profile_changed(self.current_profile)

    def _show_error(self, msg: str):
        """Muestra popup informativo en lugar de texto rojo."""
        self._show_info_popup(msg)

    def _show_info_popup(self, msg: str):
        """Muestra popup informativo centrado con shadow."""

        def on_close(e):
            self._remove_last_popup()

        _btn_style = ft.ButtonStyle(
            color={
                ft.ControlState.DEFAULT: BOTONES_GENERICOS_COLOR,
                "hovered": BOTONES_GENERICOS_HOVER_COLOR,
            },
            overlay_color=BOTONES_GENERICOS_OVERLAY_COLOR,
            padding=ft.Padding(0, 0, 0, 0),
            shape=ft.RoundedRectangleBorder(radius=10),
        )

        popup_content = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(
                                ft.Icons.WARNING_AMBER_ROUNDED, color="#FFC107", size=20
                            ),
                            ft.Text(
                                t("Aviso"),
                                weight=ft.FontWeight.BOLD,
                                size=16,
                                color=TEXTO_COLOR_GENERICO,
                            ),
                        ],
                        spacing=10,
                    ),
                    ft.Container(height=10),
                    ft.Text(
                        msg,
                        size=13,
                        color=TEXTO_COLOR_GENERICO,
                    ),
                    ft.Container(height=15),
                    ft.Row(
                        [
                            ft.Button(
                                t("Aceptar"),
                                on_click=on_close,
                                width=110,
                                bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
                                style=_btn_style,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),
                ],
                tight=True,
                spacing=0,
            ),
            width=450,
            padding=ft.Padding(24, 20, 24, 20),
            bgcolor=FONDO_ALERT_DIALOG,
            border_radius=12,
            border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
            shadow=ft.BoxShadow(
                spread_radius=2,
                blur_radius=15,
                color=ft.Colors.with_opacity(0.4, "#000000"),
            ),
        )

        popup_container = ft.Container(
            content=popup_content,
            alignment=ft.Alignment.CENTER,
            expand=True,
        )

        self.dialog_root_stack.controls.append(popup_container)
        self.dialog_root_stack.update()

    def _remove_last_popup(self):
        """Elimina el ultimo popup del stack."""
        if self.dialog_root_stack and len(self.dialog_root_stack.controls) > 1:
            self.dialog_root_stack.controls.pop()
            self.dialog_root_stack.update()

    def _open_field_split_sample_editor(self, e):
        """Editor de texto de muestra con separadores de campo (datamatrix/qr/pdf417).

        Apertura/cierre configurables + split en vivo de los campos detectados
        (misma UX que DataMatrix). Para PDF417 añade contador de caracteres.
        """
        symb = self.current_profile.symbology
        is_pdf417 = symb == "pdf417"
        old_value = self.current_profile.sample_value
        if is_pdf417:
            max_chars = get_pdf417_max_chars()
        else:
            max_chars = None
        current_text = old_value
        title = (
            t("Editar texto de muestra DataMatrix")
            if _is_datamatrix_family(symb)
            else t("Editar texto de muestra")
        )

        char_counter = ft.Text(
            f"{len(current_text)}/{max_chars}" if is_pdf417 else "",
            size=12,
            color=TEXTO_COLOR_GENERICO,
        )
        # VT diseño: para QR/PDF417/DM personalizado usar 10/12 como VT, si no mantener 15/8
        _is_vt_barcode = symb in ("qr", "pdf417", "datamatrix")
        text_field = ft.TextField(
            value=current_text,
            multiline=True,
            expand=True,
            min_lines=10 if _is_vt_barcode else (15 if is_pdf417 else 8),
            max_lines=12 if _is_vt_barcode else (15 if is_pdf417 else 8),
            max_length=max_chars if max_chars else None,
            on_change=lambda e: self._on_field_popup_change(),
            on_selection_change=self._on_barcode_vt_field_selection_change,
            hint_text=t("Escribe el texto (los campos van dentro del texto)...") if _is_vt_barcode else t("Escribe el código (los campos van dentro del texto)..."),
            autofocus=True,
            filled=True,
            fill_color=FONDO_TEXTFIELDS_COLOR,
            text_style=ft.TextStyle(color=TEXTO_COLOR_GENERICO, size=13),border=ft.OutlineInputBorder(border_radius=8, side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)))

        # Fila para insertar columna VT (solo QR/PDF417/DM personalizado con Excel cargado) — igual que VT
        column_insert_row = ft.Container()
        _vt_col_dd = None
        if symb in ("qr", "pdf417", "datamatrix") and getattr(self, "_excel_columns", None):
            if self._excel_columns:

                def _on_barcode_vt_col_change(val: str):
                    col = val or ""
                    if not col:
                        return
                    marker = f"<@<{col}>@>"
                    try:
                        cur = text_field.value or ""
                        pos = self._field_popup.get("sel_start")
                        end = self._field_popup.get("sel_end")
                        if pos is None:
                            pos = len(cur)
                            end = pos
                        if end is None:
                            end = pos
                        text_field.value = cur[:pos] + marker + cur[end:]
                        text_field.update()
                        self._on_field_popup_change()
                    except Exception:
                        pass
                    # Reset dropdown a placeholder como VT
                    try:
                        if _vt_col_dd is not None:
                            dd = _vt_col_dd.content.controls[0]
                            dd.value = t("(sin seleccion)")
                            dd.data = ""
                            _vt_col_dd.update()
                    except Exception:
                        pass

                _vt_col_dd = self._create_compact_dropdown(
                    options=[("", t("(sin seleccion)"))] + [(c, c) for c in self._excel_columns],
                    value="",
                    width=250,
                    height=28,
                    text_size=11,
                    on_change=_on_barcode_vt_col_change,
                )
                column_insert_row = ft.Row(
                    [ft.Text(t("Columna:"), size=12, color=TEXTOS_FASE_1_COLOR), _vt_col_dd],
                    spacing=8,
                    alignment=ft.MainAxisAlignment.START,
                )

        preview = ft.Text(
            value="",
            size=13,
            color=TEXTO_COLOR_GENERICO,
            selectable=True,
        )

        self._field_popup = {
            "symb": symb,
            "old_value": old_value,
            "tf": text_field,
            "preview": preview,
            "counter": char_counter if is_pdf417 else None,
            "max_chars": max_chars,
            "_vt_col_dd": _vt_col_dd,
            "sel_start": None,
            "sel_end": None,
        }

        _btn_style = ft.ButtonStyle(
            color={
                ft.ControlState.DEFAULT: BOTONES_GENERICOS_COLOR,
                "hovered": BOTONES_GENERICOS_HOVER_COLOR,
            },
            overlay_color=BOTONES_GENERICOS_OVERLAY_COLOR,
            padding=ft.Padding(0, 0, 0, 0),
            shape=ft.RoundedRectangleBorder(radius=10),
        )
        counter_row = []
        if is_pdf417:
            counter_row = [
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Icon(
                                ft.Icons.TEXT_FIELDS,
                                size=14,
                                color=TEXTO_COLOR_GENERICO,
                            ),
                            char_counter,
                            ft.Text(
                                t("Caracteres"),
                                size=12,
                                color=TEXTO_COLOR_GENERICO,
                            ),
                        ],
                        spacing=4,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                )
            ]
        popup = ft.Container(
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.Text(
                            title,
                            size=18,
                            weight=ft.FontWeight.BOLD,
                            color=TEXTO_COLOR_GENERICO,
                        ),
                        ft.Divider(height=1, color=BORDE_TEXTFIELDS_COLOR),
                        ft.Container(height=8),
                        column_insert_row,
                        ft.Container(height=4),
                        text_field,
                        ft.Container(height=4),
                        ft.Container(
                            content=preview,
                            bgcolor=FONDO_TEXTFIELDS_COLOR,
                            border_radius=8,
                            padding=10,
                            expand=True,
                            alignment=ft.Alignment.TOP_LEFT,
                            border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
                        ),
                        ft.Container(height=6),
                        ft.Row(
                            [
                                ft.Row(
                                    counter_row
                                    + [
                                        ft.Button(
                                            t("Cancelar"),
                                            on_click=lambda e: self._close_field_split_popup(
                                                restore=True
                                            ),
                                            width=110,
                                            bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
                                            style=_btn_style,
                                        ),
                                        ft.Button(
                                            t("Aceptar"),
                                            on_click=lambda e: self._close_field_split_popup(
                                                restore=False
                                            ),
                                            width=110,
                                            bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
                                            style=_btn_style,
                                        ),
                                    ],
                                    spacing=8,
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.END,
                        ),
                    ],
                    spacing=6,
                ),
                padding=ft.Padding(24, 20, 24, 20),
                width=1000 if _is_vt_barcode else 680,
                height=640 if _is_vt_barcode else (560 if not is_pdf417 else 600),
                bgcolor=FONDO_APP,
                border_radius=12,
                border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
                shadow=ft.BoxShadow(
                    spread_radius=2,
                    blur_radius=15,
                    color=ft.Colors.with_opacity(0.4, "#000000"),
                ),
            ),
            alignment=ft.Alignment.CENTER,
            expand=True,
        )
        self.dialog_root_stack.controls.append(popup)
        self.dialog_root_stack.update()
        self._on_field_popup_change()

    def _on_barcode_vt_field_selection_change(self, e):
        sel = getattr(e, "selection", None)
        if sel is not None and getattr(sel, "start", None) is not None:
            if getattr(self, "_field_popup", None):
                self._field_popup["sel_start"] = sel.start
                self._field_popup["sel_end"] = sel.end

    def _on_field_popup_change(self, e=None):
        """Actualiza el split en vivo del popup de muestra (campos detectados)."""
        st = self._field_popup
        if not st:
            return
        tf = st["tf"]
        preview = st["preview"]
        value = tf.value or ""
        # VT personalizado: si plantilla contiene <@<col>@> y es QR/PDF417/DM personalizado, previsualizar resuelto
        if st["symb"] in ("qr", "pdf417", "datamatrix") and "<@<" in value:
            if self.excel_manager and getattr(self.excel_manager, "is_loaded", False):
                import re

                def _vt_repl(m):
                    col = m.group(1).strip()
                    try:
                        v = self.excel_manager.get_value_at(col, self._preview_row_index) or ""
                    except Exception:
                        v = ""
                    return v

                resolved = re.sub(r"<@<([^>]+)>@>", _vt_repl, value)
                preview.value = resolved or t("(sin campos)")
            else:
                preview.value = value or t("(sin campos)")
            try:
                preview.update()
            except Exception:
                pass
            counter = st.get("counter")
            if counter is not None:
                # Contar sobre valor resuelto si hay Excel, sino plantilla
                try:
                    cval = resolved if "resolved" in locals() else value  # type: ignore
                except Exception:
                    cval = value
                counter.value = f"{len(cval)}/{st.get('max_chars') or 0}"
                try:
                    counter.update()
                except Exception:
                    pass
            return
        if (
            (st["symb"] == "datamatrix" and _es_datamatrix_gs1(value))
            or _is_datamatrix_gs1_symb(st["symb"])
        ):
            lines = ["({0}){1}".format(ai, val) for ai, val in _parse_gs1_hri(value)]
        else:
            lines = [l.strip() for l in value.split("\n") if l.strip()]
        preview.value = "\n".join(lines) if lines else t("(sin campos)")
        try:
            preview.update()
        except Exception:
            pass
        counter = st.get("counter")
        if counter is not None:
            counter.value = f"{len(value)}/{st.get('max_chars') or 0}"
            try:
                counter.update()
            except Exception:
                pass

    def _close_field_split_popup(self, restore=False):
        """Cierra el popup de muestra y aplica (o restaura) valor + separadores."""
        st = self._field_popup
        symb = st["symb"] if st else self.current_profile.symbology
        if restore:
            if st:
                self._sample_field.value = st["old_value"]
        else:
            tf = st["tf"] if st else None
            value = tf.value if tf else ""
            self._sample_field.value = value
            self.current_profile.sample_value = value
        self._field_popup = None
        if len(self.dialog_root_stack.controls) > 1:
            self.dialog_root_stack.controls.pop()
        self.dialog_root_stack.update()
        if not restore:
            if _is_datamatrix_family(symb):
                self.current_profile.barcode_font_auto = True
                self._apply_datamatrix_font_auto()
            self._on_preview_trigger()
            self._recalculate_minimums()
            self._apply_delims_visibility()
            if self.page and self.dialog:
                self.dialog.update()

    # ------------------------------------------------------------------
    # Editor de texto de muestra genérico (códigos SIN separación de campo:
    # code128, code39, ean*, upc*, isbn13, itf14). Contador de
    # caracteres tipo PDF417: bloquea al llegar al máximo. La validación
    # de formato/checksum ocurre al pulsar "Aceptar".
    # ------------------------------------------------------------------
    def _open_generic_sample_editor(self, e):
        """Abre overlay para editar el texto de muestra de códigos sin
        separación de campo. Muestra contador de caracteres (max_length
        bloquea el tecleo al llegar al límite). Al Aceptar se valida el
        formato; si no es correcto se muestra el error y no se cierra."""
        self._generic_old_value = self.current_profile.sample_value
        current_text = self._generic_old_value

        symb = self.current_profile.symbology
        self._generic_max_chars = get_max_chars_for_symbology(symb, current_text)
        self._generic_error_text = ft.Text(
            "", size=12, color=TEXTO_COLOR_GENERICO, visible=False
        )
        self._generic_error_container = ft.Container(
            content=ft.Row(
                [self._generic_error_text],
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            height=20,
            alignment=ft.Alignment.CENTER,
        )
        self._generic_counter = ft.Text(
            f"{len(current_text)}/{self._generic_max_chars}",
            size=12,
            color=TEXTO_COLOR_GENERICO,
        )
        text_field = ft.TextField(
            value=current_text,
            multiline=symb == "qr",
            expand=True,
            min_lines=15 if symb == "qr" else 2,
            max_lines=15 if symb == "qr" else 2,
            max_length=self._generic_max_chars,
            on_change=self._on_generic_text_change,
            hint_text=t("Escribe el texto..."),
            autofocus=True,
            filled=True,
            fill_color=FONDO_TEXTFIELDS_COLOR,
            text_style=ft.TextStyle(color=TEXTO_COLOR_GENERICO, size=13),border=ft.OutlineInputBorder(border_radius=8, side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)))

        self._generic_popup_tf = text_field
        _btn_style = ft.ButtonStyle(
            color={
                ft.ControlState.DEFAULT: BOTONES_GENERICOS_COLOR,
                "hovered": BOTONES_GENERICOS_HOVER_COLOR,
            },
            overlay_color=BOTONES_GENERICOS_OVERLAY_COLOR,
            padding=ft.Padding(0, 0, 0, 0),
            shape=ft.RoundedRectangleBorder(radius=10),
        )
        popup = ft.Container(
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.Text(
                            t("Editar texto de muestra"),
                            size=18,
                            weight=ft.FontWeight.BOLD,
                            color=TEXTO_COLOR_GENERICO,
                        ),
                        ft.Divider(height=1, color=BORDE_TEXTFIELDS_COLOR),
                        ft.Container(height=8),
                        text_field,
                        ft.Container(height=4),
                        self._generic_error_container,
                        ft.Row(
                            [
                                ft.Row(
                                    [
                                        ft.Icon(
                                            ft.Icons.TEXT_FIELDS,
                                            size=14,
                                            color=TEXTO_COLOR_GENERICO,
                                        ),
                                        self._generic_counter,
                                        ft.Text(
                                            t("Caracteres"),
                                            size=12,
                                            color=TEXTO_COLOR_GENERICO,
                                        ),
                                    ],
                                    spacing=4,
                                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                ),
                                ft.Row(
                                    [
                                        ft.Button(
                                            t("Cancelar"),
                                            on_click=lambda e: self._close_generic_sample_popup(
                                                restore=True
                                            ),
                                            width=110,
                                            bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
                                            style=_btn_style,
                                        ),
                                        ft.Button(
                                            t("Aceptar"),
                                            on_click=lambda e: self._close_generic_sample_popup(
                                                restore=False
                                            ),
                                            width=110,
                                            bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
                                            style=_btn_style,
                                        ),
                                    ],
                                    spacing=8,
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                    ],
                    expand=True,
                ),
                padding=ft.Padding(24, 20, 24, 20),
                width=560,
                height=380,
                bgcolor=FONDO_APP,
                border_radius=12,
                border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
                shadow=ft.BoxShadow(
                    spread_radius=2,
                    blur_radius=15,
                    color=ft.Colors.with_opacity(0.4, "#000000"),
                ),
            ),
            alignment=ft.Alignment.CENTER,
            expand=True,
        )
        self.dialog_root_stack.controls.append(popup)
        self.dialog_root_stack.update()

    def _on_generic_text_change(self, e):
        if self._generic_error_text is not None:
            self._generic_error_text.visible = False
            try:
                self._generic_error_container.update()
            except Exception:
                pass
        if self._generic_counter is not None and self._generic_popup_tf is not None:
            n = len(self._generic_popup_tf.value or "")
            self._generic_counter.value = f"{n}/{self._generic_max_chars}"
            try:
                self._generic_counter.update()
            except Exception:
                pass

    def _close_generic_sample_popup(self, restore=False):
        if restore:
            self._sample_field.value = self._generic_old_value
        else:
            value = self._generic_popup_tf.value if self._generic_popup_tf else ""
            valid, msg = self._validate_generic_sample(value)
            if not valid:
                if self._generic_error_text is not None:
                    self._generic_error_text.value = msg or t("Valor no valido")
                    self._generic_error_text.visible = True
                    try:
                        self._generic_error_container.update()
                    except Exception:
                        pass
                return
            self._sample_field.value = value
            self.current_profile.sample_value = value
        self._generic_old_value = ""
        self._generic_popup_tf = None
        self._generic_error_text = None
        self._generic_error_container = None
        self._generic_counter = None
        if len(self.dialog_root_stack.controls) > 1:
            self.dialog_root_stack.controls.pop()
        self.dialog_root_stack.update()
        if not restore:
            self._recalculate_minimums()
            self._on_preview_trigger()
            if self.page and self.dialog:
                self.dialog.update()

    def _validate_generic_sample(self, value: str):
        """Valida el texto de muestra según la simbología. La longitud ya la
        controla max_length del contador; aquí solo se valida formato/
        checksum con el validate_* de cada código. Code128 además comprueba
        longitud (límite dinámico por contenido). Si no hay validador
        (QR), se acepta."""
        symb = self.current_profile.symbology
        if symb == "code128":
            ok, msg = validate_code128(value)
            if not ok:
                return False, msg
            if value.strip():
                ok, msg = validar_longitud_code128(value)
                if not ok:
                    return False, msg
            return True, ""
        validators = {
            "code39": validate_code39,
            "ean13": validate_ean13,
            "ean8": validate_ean8,
            "ean5": validate_ean5,
            "upca": validate_upca,
            "upce": validate_upce,
            "isbn13": validate_isbn13,
            "itf14": validate_itf14,
        }
        # validate_ean13/validate_ean8 aceptan 12/7 (auto-checksum). El código
        # solo es legible con la longitud completa: exigir exacta en el diálogo.
        exact_length = {"ean13": 13, "ean8": 8}
        fn = validators.get(symb)
        if fn is None:
            return True, ""
        if not value.strip():
            return False, t("El valor no puede estar vacio")
        if symb in exact_length and len(value) != exact_length[symb]:
            return False, t("Debe tener exactamente {0} dígitos").format(
                exact_length[symb]
            )
        return fn(value)

    # ------------------------------------------------------------------
    # Editor de texto de muestra DataMatrix (diseño propio)
    # ------------------------------------------------------------------
    def _show_excel_column_invalid(self, value: str, error_msg: str):
        """Muestra popup cuando el valor de la columna Excel es incompatible con el barcode."""

        def on_close(e):
            self._remove_last_popup()

        _btn_style = ft.ButtonStyle(
            color={
                ft.ControlState.DEFAULT: BOTONES_GENERICOS_COLOR,
                "hovered": BOTONES_GENERICOS_HOVER_COLOR,
            },
            overlay_color=BOTONES_GENERICOS_OVERLAY_COLOR,
            padding=ft.Padding(0, 0, 0, 0),
            shape=ft.RoundedRectangleBorder(radius=10),
        )

        popup_content = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(
                                ft.Icons.WARNING_AMBER_ROUNDED, color="#FFC107", size=20
                            ),
                            ft.Text(
                                t("Columna incompatible"),
                                weight=ft.FontWeight.BOLD,
                                size=16,
                                color=TEXTO_COLOR_GENERICO,
                            ),
                        ],
                        spacing=10,
                    ),
                    ft.Container(height=10),
                    ft.Text(
                        t(
                            "El valor de la columna no es compatible con el codigo de barras seleccionado."
                        ),
                        size=13,
                        color=TEXTO_COLOR_GENERICO,
                    ),
                    ft.Container(height=5),
                    ft.Text(
                        t('Valor: "{0}"').format(value),
                        size=12,
                        color=TEXTO_COLOR_GENERICO,
                        italic=True,
                    ),
                    ft.Text(
                        t("Error: {0}").format(error_msg),
                        size=12,
                        color=ERROR_COLOR,
                    ),
                    ft.Container(height=15),
                    ft.Row(
                        [
                            ft.Button(
                                t("Volver"),
                                on_click=on_close,
                                width=110,
                                bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
                                style=_btn_style,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),
                ],
                tight=True,
                spacing=0,
            ),
            width=450,
            padding=ft.Padding(24, 20, 24, 20),
            bgcolor=FONDO_ALERT_DIALOG,
            border_radius=12,
            border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
            shadow=ft.BoxShadow(
                spread_radius=2,
                blur_radius=15,
                color=ft.Colors.with_opacity(0.4, "#000000"),
            ),
        )

        popup_container = ft.Container(
            content=popup_content,
            alignment=ft.Alignment.CENTER,
            expand=True,
        )

        self.dialog_root_stack.controls.append(popup_container)
        self.dialog_root_stack.update()

    # ------------------------------------------------------------------
    # Preferences persistence
    # ------------------------------------------------------------------
    def save_to_preferences(self):
        from utils.preferences import save_barcode_profiles

        profiles_data = []
        for profile in self.profiles:
            d = asdict(profile)
            # Si el perfil usa datos externos, guardarlo como fijo para reutilizar diseño
            if d.get("value_source") == "excel":
                d["value_source"] = "fixed"
                d["excel_column"] = ""
            profiles_data.append(d)
        save_barcode_profiles(profiles_data)

    def load_from_preferences(self):
        from utils.preferences import get_barcode_profiles

        profiles_data = get_barcode_profiles()
        if profiles_data:
            loaded = []
            used_names = set()
            for pd in profiles_data:
                p = BarcodeProfile.from_dict(pd)
                base_name = (p.name or "<Default>").strip()
                new_name = base_name
                suffix = 2
                while new_name in used_names:
                    new_name = f"{base_name} ({suffix})"
                    suffix += 1
                p.name = new_name
                used_names.add(new_name)
                loaded.append(p)
            if loaded:
                self.profiles = loaded
                self.selected_profile_index = 0
                self.current_profile = self.profiles[0]

    def get_profiles(self) -> list[BarcodeProfile]:
        return self.profiles

    # ------------------------------------------------------------------
    # Set excel columns
    # ------------------------------------------------------------------
    def set_excel_columns(self, columns: list):
        self._excel_columns = columns or []
        if self._excel_column_dropdown is not None:
            opts = [("", t("(sin seleccion)"))]
            for col in self._excel_columns:
                opts.append((col, col))
            dd = self._excel_column_dropdown.content.controls[0]
            opts_keys = [o[0] for o in opts]
            cur_val = dd.data if dd.data in opts_keys else ""
            self._excel_column_dropdown = self._create_compact_dropdown(
                options=opts,
                value=cur_val,
                width=180,
                height=28,
                text_size=11,
                on_change=self._on_excel_column_changed,
            )
            self._excel_column_dropdown.visible = (
                self.current_profile.value_source == "excel"
            )
            try:
                self._excel_column_dropdown.update()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Open dialog
    # ------------------------------------------------------------------
    def open(self):
        debug_trace_profile_setattr = False
        _orig_setattr = None
        if debug_trace_profile_setattr:
            import traceback as _tb

            _orig_setattr = BarcodeProfile.__setattr__

            def _trace_setattr(obj, name, val):
                if name in (
                    "bar_width",
                    "pdf417_size",
                    "bar_height",
                    "pdf417_height",
                    "datamatrix_width",
                ):
                    stack = _tb.format_stack()[-6:-1]
                    # print(
                    #     f"[TRACE_SETATTR] {name} = {val}  profile={obj.name} symb={obj.symbology}"
                    # )
                    for line in stack:
                        # print(f"  {line.rstrip()}")
                        pass
                _orig_setattr(obj, name, val)

            BarcodeProfile.__setattr__ = _trace_setattr
        # Panel izquierdo - Lista de perfiles + color
        self.btn_new_profile = ft.IconButton(
            icon=ft.Icons.ADD,
            tooltip=t("Nuevo perfil"),
            icon_size=20,
            icon_color=TEXTO_COLOR_GENERICO,
            on_click=self._create_new_profile,
        )
        self.btn_delete_profile = ft.IconButton(
            icon=ft.Icons.DELETE,
            tooltip=t("Eliminar Perfil"),
            icon_size=20,
            icon_color=TEXTO_COLOR_GENERICO,
            on_click=self._delete_profile,
        )
        self.profile_list = ft.ListView(
            controls=[
                self._create_profile_list_item(i, profile)
                for i, profile in enumerate(self.profiles)
            ],
            spacing=0,
            expand=True,
        )
        self._color_swatch_button = ft.Container(
            width=40,
            height=40,
            bgcolor=self.current_profile.color,
            border_radius=4,
            border=ft.Border.all(2, BORDE_TEXTFIELDS_COLOR),
            on_click=self._open_color_picker,
            ink=True,
            tooltip=t("Seleccionar color"),
        )
        self._text_color_swatch_button = ft.Container(
            width=40,
            height=40,
            bgcolor=self.current_profile.text_color,
            border_radius=4,
            border=ft.Border.all(2, BORDE_TEXTFIELDS_COLOR),
            on_click=self._open_text_color_picker,
            ink=True,
            tooltip=t("Color texto"),
        )
        color_bar_container = ft.Container(
            content=ft.Column(
                [
                    ft.Text(
                        t("Color Barras"),
                        size=11,
                        color=TEXTOS_FASE_1_COLOR,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    self._color_swatch_button,
                ],
                spacing=6,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            expand=True,
            padding=6,
        )
        self._text_color_container = ft.Container(
            content=ft.Column(
                [
                    ft.Text(
                        t("Color texto"),
                        size=11,
                        color=TEXTOS_FASE_1_COLOR,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    self._text_color_swatch_button,
                ],
                spacing=6,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            expand=True,
            padding=6,
        )
        left_panel = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text(
                                t("Perfiles"),
                                size=14,
                                weight=ft.FontWeight.BOLD,
                                color=TEXTO_COLOR_GENERICO,
                            ),
                            ft.Row(
                                [
                                    self.btn_new_profile,
                                    self.btn_delete_profile,
                                ],
                                spacing=6,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.Divider(height=1, color=BORDE_TEXTFIELDS_COLOR),
                    self.profile_list,
                    ft.Divider(height=1, color=BORDE_TEXTFIELDS_COLOR),
                    ft.Row(
                        [
                            color_bar_container,
                            self._text_color_container,
                        ],
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                ],
                spacing=8,
            ),
            width=250,
            padding=10,
            bgcolor=None,
            border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
            border_radius=8,
        )

        # Panel derecho - Secciones
        # Seccion 1: Simbologia
        self._symbology_dropdown = self._create_compact_dropdown(
            options=SYMBOLOGY_OPTIONS,
            value=self.current_profile.symbology,
            width=200,
            height=28,
            text_size=11,
            on_change=self._on_value_changed,
        )
        row_symbology = ft.Row(
            controls=[
                ft.Text(t("Simbologia:"), size=12, color=TEXTOS_FASE_1_COLOR, width=100),
                self._symbology_dropdown,
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        # Seccion 2: Valor
        self._value_source_dropdown = self._create_compact_dropdown(
            options=VALUE_SOURCE_OPTIONS,
            value=self.current_profile.value_source,
            width=200,
            height=28,
            text_size=11,
            on_change=self._update_value_source_dropdown,
        )
        self._mask_field = ft.TextField(
            label=t("Mascara"),
            value=self.current_profile.mask,
            width=170,
            height=28,
            text_size=13,
            content_padding=ft.Padding(4, 0, 4, 0),
            filled=True,
            fill_color=FONDO_TEXTFIELDS_COLOR,
            text_style=ft.TextStyle(color=TEXTO_COLOR_GENERICO),
            label_style=ft.TextStyle(size=11, color=TEXTO_COLOR_GENERICO),
            on_submit=self._on_data_text_commit,
            on_blur=self._on_data_text_commit,
            on_focus=lambda e: setattr(self, "_data_text_focus_target", self._mask_field),border=ft.OutlineInputBorder(border_radius=4, side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)))
        self._mask_container = ft.Container(
            content=self._mask_field,
            visible=self.current_profile.value_source == "numbering",
        )
        self._sample_field = ft.TextField(
            label=t("Valor de muestra"),
            value=self.current_profile.sample_value,
            expand=True,
            height=28,
            text_size=13,
            content_padding=ft.Padding(4, 0, 4, 0),
            filled=True,
            fill_color=FONDO_TEXTFIELDS_COLOR,
            text_style=ft.TextStyle(color=TEXTO_COLOR_GENERICO),
            label_style=ft.TextStyle(size=11, color=TEXTO_COLOR_GENERICO),
            on_submit=self._on_data_text_commit,
            on_blur=self._on_data_text_commit,
            on_focus=lambda e: setattr(self, "_data_text_focus_target", self._sample_field),
            visible=self.current_profile.value_source == "fixed"
            and self.current_profile.symbology != "pdf417",border=ft.OutlineInputBorder(border_radius=4, side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)))
        self._pdf417_sample_btn = ft.Button(
            content=t("Texto de ejemplo"),
            icon=ft.Icons.EDIT,
            on_click=self._open_field_split_sample_editor,
            height=28,
            width=220,
            style=ft.ButtonStyle(
                color={
                    ft.ControlState.DEFAULT: BOTONES_GENERICOS_COLOR,
                    "hovered": BOTONES_GENERICOS_HOVER_COLOR,
                },
                bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
                overlay_color=BOTONES_GENERICOS_OVERLAY_COLOR,
                padding=ft.Padding(8, 0, 8, 0),
                shape=ft.RoundedRectangleBorder(radius=4),
            ),
            visible=self.current_profile.value_source == "fixed"
            and self.current_profile.symbology == "pdf417",
        )
        self._generic_sample_btn = ft.Button(
            content=t("Texto de muestra"),
            icon=ft.Icons.EDIT,
            on_click=self._open_generic_sample_editor,
            height=28,
            width=220,
            style=ft.ButtonStyle(
                color={
                    ft.ControlState.DEFAULT: BOTONES_GENERICOS_COLOR,
                    "hovered": BOTONES_GENERICOS_HOVER_COLOR,
                },
                bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
                overlay_color=BOTONES_GENERICOS_OVERLAY_COLOR,
                padding=ft.Padding(8, 0, 8, 0),
                shape=ft.RoundedRectangleBorder(radius=4),
            ),
            visible=self.current_profile.value_source == "fixed"
            and self.current_profile.symbology not in ("pdf417", "datamatrix", "qr"),
        )
        self._qr_sample_btn = ft.Button(
            content=t("Texto de muestra"),
            icon=ft.Icons.EDIT,
            on_click=self._open_field_split_sample_editor,
            height=28,
            width=220,
            style=ft.ButtonStyle(
                color={
                    ft.ControlState.DEFAULT: BOTONES_GENERICOS_COLOR,
                    "hovered": BOTONES_GENERICOS_HOVER_COLOR,
                },
                bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
                overlay_color=BOTONES_GENERICOS_OVERLAY_COLOR,
                padding=ft.Padding(8, 0, 8, 0),
                shape=ft.RoundedRectangleBorder(radius=4),
            ),
            visible=self.current_profile.value_source == "fixed"
            and self.current_profile.symbology == "qr",
        )
        self._datamatrix_sample_btn = ft.Button(
            content=t("Texto de muestra"),
            icon=ft.Icons.EDIT,
            on_click=self._open_field_split_sample_editor,
            height=28,
            width=220,
            style=ft.ButtonStyle(
                color={
                    ft.ControlState.DEFAULT: BOTONES_GENERICOS_COLOR,
                    "hovered": BOTONES_GENERICOS_HOVER_COLOR,
                },
                bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
                overlay_color=BOTONES_GENERICOS_OVERLAY_COLOR,
                padding=ft.Padding(8, 0, 8, 0),
                shape=ft.RoundedRectangleBorder(radius=4),
            ),
            visible=self.current_profile.value_source == "fixed"
            and _is_datamatrix_family(self.current_profile.symbology),
        )
        excel_opts = [("", t("(sin seleccion)"))]
        for col in self._excel_columns:
            excel_opts.append((col, col))
        self._excel_column_dropdown = self._create_compact_dropdown(
            options=excel_opts,
            value=(
                self.current_profile.excel_column
                if self.current_profile.excel_column in self._excel_columns
                else ""
            ),
            width=180,
            height=28,
            text_size=11,
            on_change=self._on_excel_column_changed,
        )
        self._excel_column_dropdown.visible = (
            self.current_profile.value_source == "excel"
        )
        self._datamatrix_del_open_field = ft.TextField(
            label=t("Apertura"),
            value=self.current_profile.datamatrix_del_open or "",
            width=74,
            height=28,
            text_size=11,
            content_padding=ft.Padding(4, 0, 4, 0),
            filled=True,
            fill_color=FONDO_TEXTFIELDS_COLOR,
            text_style=ft.TextStyle(color=TEXTO_COLOR_GENERICO),
            label_style=ft.TextStyle(size=10, color=TEXTO_COLOR_GENERICO),
            on_change=self._on_datamatrix_delimiters_change,
            visible=self.current_profile.value_source == "excel"
            and _is_datamatrix_family(self.current_profile.symbology),border=ft.OutlineInputBorder(border_radius=4, side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)))
        self._datamatrix_del_close_field = ft.TextField(
            label=t("Cierre"),
            value=self.current_profile.datamatrix_del_close
            if self.current_profile.datamatrix_del_close is not None
            else "|",
            width=74,
            height=28,
            text_size=11,
            content_padding=ft.Padding(4, 0, 4, 0),
            filled=True,
            fill_color=FONDO_TEXTFIELDS_COLOR,
            text_style=ft.TextStyle(color=TEXTO_COLOR_GENERICO),
            label_style=ft.TextStyle(size=10, color=TEXTO_COLOR_GENERICO),
            on_change=self._on_datamatrix_delimiters_change,
            visible=self.current_profile.value_source == "excel"
            and _is_datamatrix_family(self.current_profile.symbology),border=ft.OutlineInputBorder(border_radius=4, side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)))
        self._datamatrix_del_recalc_btn = ft.Button(
            content=t("Recalcular"),
            icon=ft.Icons.REFRESH,
            on_click=self._on_datamatrix_recalc_click,
            height=28,
            style=ft.ButtonStyle(
                color={
                    ft.ControlState.DEFAULT: BOTONES_GENERICOS_COLOR,
                    "hovered": BOTONES_GENERICOS_HOVER_COLOR,
                },
                bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
                overlay_color=BOTONES_GENERICOS_OVERLAY_COLOR,
                padding=ft.Padding(8, 0, 8, 0),
                shape=ft.RoundedRectangleBorder(radius=4),
            ),
            visible=self.current_profile.value_source == "excel"
            and _is_datamatrix_family(self.current_profile.symbology),
        )
        self._datamatrix_gs1_label = ft.Text(
            t("Datos GS1 detectados"),
            size=12,
            weight=ft.FontWeight.BOLD,
            color=TEXTO_COLOR_GENERICO,
            visible=False,
        )
        self._del_close_newline_check = ft.Checkbox(
            value=bool(
                getattr(
                    self.current_profile,
                    f"{self._symb_del_keys()}_del_close_newline",
                    False,
                )
            ),
            active_color=BORDE_TEXTFIELDS_COLOR,
            check_color=TEXTOS_FASE_1_COLOR,
            fill_color=FONDO_TEXTFIELDS_COLOR,
            border_side=ft.BorderSide(1, BORDE_TEXTFIELDS_COLOR),
            splash_radius=0,
            on_change=self._on_del_close_newline_change,
            visible=False,
        )
        self._del_close_newline_row = ft.Row(
            controls=[
                self._del_close_newline_check,
                ft.Text(
                    t("Cierre = salto de línea"),
                    size=12,
                    color=TEXTO_COLOR_GENERICO,
                ),
            ],
            spacing=4,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            visible=False,
        )
        row_origen = ft.Row(
            controls=[
                ft.Text(
                    t("Origen de datos"),
                    size=12,
                    color=TEXTOS_FASE_1_COLOR,
                    width=100,
                ),
                self._value_source_dropdown,
                self._mask_container,
                self._sample_field,
                self._pdf417_sample_btn,
                self._generic_sample_btn,
                self._qr_sample_btn,
                self._datamatrix_sample_btn,
                self._excel_column_dropdown,
                self._datamatrix_gs1_label,
                self._datamatrix_del_open_field,
                self._datamatrix_del_close_field,
                self._del_close_newline_row,
                self._datamatrix_del_recalc_btn,
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        self._sample_field.visible = False  # fijo: se edita vía botón "Texto de muestra"
        section_simbologia = self._make_section(
            t("Simbologia y datos de entrada"),
            [
                row_symbology,
                ft.Divider(height=1, color=BORDE_TEXTFIELDS_COLOR),
                row_origen,
            ],
        )

        # Seccion 3: Dimensiones (dinámico desde SYMBOLOGY_CONFIG)
        # El wrapper es un Container neutro: _build_dim_fields devuelve las secciones
        # propias (cada una con su título) para datamatrix, o un _make_section
        # "Dimensiones" para el resto de simbologías.
        self._dim_fields_section = ft.Container(
            content=ft.Row(spacing=6),
            padding=ft.Padding.all(0),
        )

        # ── Seccion ITF-14 (solo visible para symbology=itf14) ──

        def _on_itf14_gtin_change(val):
            if val == "gtin13":
                self._sample_field.value = "0812345678907"
            else:
                self._sample_field.value = "10812345678908"
            self._sample_field.update()
            _sync_itf14_fields()
            self._update_preview()

        def _on_itf14_printer_change(val):
            if val == "flexografia":
                min_w, min_h = 89.25, 32.00
            else:
                min_w, min_h = 71.40, 12.70
            self.current_profile.bar_width = min_w
            self.current_profile.bar_height = min_h
            self._itf14_width_field.value = self._display_mm(min_w)
            self._itf14_width_field.update()
            self._set_field_value("bar_width", self._display_mm(min_w))
            self._itf14_height_field.value = self._display_mm(min_h)
            self._itf14_height_field.update()
            self._set_field_value("bar_height", self._display_mm(min_h))
            _sync_itf14_fields()
            self._update_preview()

        def _sync_itf14_fields():
            self.current_profile.itf14_gtin_type = (
                self._itf14_gtin_type_dd.content.controls[0].data
            )
            self.current_profile.itf14_printer_type = (
                self._itf14_printer_dd.content.controls[0].data
            )
            try:
                w = self._save_to_mm(self._itf14_width_field.value)
                self.current_profile.bar_width = w
                self._set_field_value("bar_width", self._display_mm(w))
            except (ValueError, TypeError):
                pass
            try:
                h = self._save_to_mm(self._itf14_height_field.value)
                self.current_profile.bar_height = h
                self._set_field_value("bar_height", self._display_mm(h))
            except (ValueError, TypeError):
                pass
            try:
                self.current_profile.barcode_font_size = float(
                    self._itf14_body_field.value
                )
            except (ValueError, TypeError):
                pass
            try:
                gap = self._save_to_mm(self._itf14_gap_field.value)
                if gap < 0:
                    gap = 0.0
                    self._itf14_gap_field.value = self._display_mm(0.0)
                    try:
                        self._itf14_gap_field.update()
                    except Exception:
                        pass
                self.current_profile.itf14_hri_gap_mm = gap
            except (ValueError, TypeError):
                pass

        def _on_itf14_field_change(e=None):
            if e is not None:
                normalize_decimal_input(e)
            _sync_itf14_fields()
            self._on_preview_trigger(None)

        # Helper para flechas inc/dec
        def _arrow_btn(tf, step, min_val):
            up = ft.IconButton(
                icon=ft.Icons.ARROW_DROP_UP,
                icon_size=12,
                width=14,
                height=14,
                padding=0,
                on_click=lambda e: _arrow_click(tf, step, min_val),
            )
            dn = ft.IconButton(
                icon=ft.Icons.ARROW_DROP_DOWN,
                icon_size=12,
                width=14,
                height=14,
                padding=0,
                on_click=lambda e: _arrow_click(tf, -step, min_val),
            )
            return ft.Column([up, dn], spacing=0)

        def _arrow_click(tf, delta, min_val):
            try:
                cur = float(tf.value)
            except (ValueError, TypeError):
                return
            new_val = max(min_val, cur + delta)
            # Formatear sin decimales para enteros, con 1 decimal para el resto
            tf.value = (
                f"{new_val:.1f}" if new_val != int(new_val) else str(int(new_val))
            )
            tf.update()
            self._on_itf14_field_enter(tf)
            _on_itf14_field_change()

        # Crear controls
        self._itf14_printer_dd = self._create_compact_dropdown(
            options=ITF14_PRINTER_OPTIONS,
            value=self.current_profile.itf14_printer_type,
            width=68,
            height=28,
            text_size=11,
            on_change=_on_itf14_printer_change,
        )
        self._itf14_gtin_type_dd = self._create_compact_dropdown(
            options=ITF14_GTIN_OPTIONS,
            value=self.current_profile.itf14_gtin_type,
            width=75,
            height=28,
            text_size=11,
            on_change=_on_itf14_gtin_change,
        )
        _itf14_width_tf = ft.TextField(
            value=self._display_mm(self.current_profile.bar_width),
            width=65,
            height=28,
            text_size=11,
            content_padding=ft.Padding(4, 0, 4, 0),
            filled=True,
            fill_color=FONDO_TEXTFIELDS_COLOR,
            text_style=ft.TextStyle(color=TEXTO_COLOR_GENERICO),
            data="bar_width",
            on_change=_on_itf14_field_change,
            on_submit=lambda e: self._on_itf14_field_enter(_itf14_width_tf),
            on_blur=lambda e: self._on_itf14_field_enter(_itf14_width_tf),border=ft.OutlineInputBorder(border_radius=4, side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)))
        self._itf14_width_field = _itf14_width_tf
        self._itf14_width_group = ft.Row(
            [
                self._itf14_width_field,
                _arrow_btn(self._itf14_width_field, float(self._display_mm(1.0)), 0.1),
            ],
            spacing=1,
        )
        _itf14_height_tf = ft.TextField(
            value=self._display_mm(self.current_profile.bar_height or 30.0),
            width=65,
            height=28,
            text_size=11,
            content_padding=ft.Padding(4, 0, 4, 0),
            filled=True,
            fill_color=FONDO_TEXTFIELDS_COLOR,
            text_style=ft.TextStyle(color=TEXTO_COLOR_GENERICO),
            data="bar_height",
            on_change=_on_itf14_field_change,
            on_submit=lambda e: self._on_itf14_field_enter(_itf14_height_tf),
            on_blur=lambda e: self._on_itf14_field_enter(_itf14_height_tf),border=ft.OutlineInputBorder(border_radius=4, side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)))
        self._itf14_height_field = _itf14_height_tf
        self._itf14_height_group = ft.Row(
            [
                self._itf14_height_field,
                _arrow_btn(self._itf14_height_field, 1.0, 0.1),
            ],
            spacing=1,
        )
        self._itf14_body_field = ft.TextField(
            value=str(self.current_profile.barcode_font_size),
            width=55,
            height=28,
            text_size=11,
            content_padding=ft.Padding(4, 0, 4, 0),
            filled=True,
            fill_color=FONDO_TEXTFIELDS_COLOR,
            text_style=ft.TextStyle(color=TEXTO_COLOR_GENERICO),
            on_change=_on_itf14_field_change,border=ft.OutlineInputBorder(border_radius=4, side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)))
        self._itf14_body_group = ft.Row(
            [self._itf14_body_field, _arrow_btn(self._itf14_body_field, 1.0, 0.0)],
            spacing=1,
        )
        self._itf14_gap_field = ft.TextField(
            value=self._display_mm(self.current_profile.itf14_hri_gap_mm),
            width=55,
            height=28,
            text_size=11,
            content_padding=ft.Padding(4, 0, 4, 0),
            filled=True,
            fill_color=FONDO_TEXTFIELDS_COLOR,
            text_style=ft.TextStyle(color=TEXTO_COLOR_GENERICO),
            on_change=_on_itf14_field_change,border=ft.OutlineInputBorder(border_radius=4, side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)))
        self._itf14_gap_group = ft.Row(
            [
                self._itf14_gap_field,
                _arrow_btn(self._itf14_gap_field, float(self._display_mm(1.0)), 0.0),
            ],
            spacing=1,
        )
        self._itf14_pos_dd = self._create_compact_dropdown(
            options=[("above", t("above")), ("below", t("below"))],
            value=str(self.current_profile.itf14_hri_position),
            width=70,
            height=28,
            text_size=11,
            on_change=lambda val, k="itf14_hri_position": self._on_field_change(k, val),
        )

        itf14_row = ft.Row(
            controls=[
                ft.Text(t("Impresora:"), size=11, color=TEXTOS_FASE_1_COLOR),
                self._itf14_printer_dd,
                ft.Container(
                    ft.Text(t("GTIN:"), size=11, color=TEXTOS_FASE_1_COLOR),
                    padding=ft.Padding.only(left=2),
                ),
                self._itf14_gtin_type_dd,
                ft.Container(
                    ft.Text(
                        f"{t('Ancho:')} ({self._unit_abbr()})",
                        size=11,
                        color=TEXTOS_FASE_1_COLOR,
                    ),
                    padding=ft.Padding.only(left=2),
                ),
                self._itf14_width_group,
                ft.Text(
                    f"{t('Alto:')} ({self._unit_abbr()})",
                    size=11,
                    color=TEXTOS_FASE_1_COLOR,
                ),
                self._itf14_height_group,
                ft.Text(t("Cuerpo:"), size=11, color=TEXTOS_FASE_1_COLOR),
                self._itf14_body_group,
                ft.Text(t("Posición:"), size=11, color=TEXTOS_FASE_1_COLOR),
                self._itf14_pos_dd,
                ft.Text(t("Distancia:"), size=11, color=TEXTOS_FASE_1_COLOR),
                self._itf14_gap_group,
            ],
            spacing=4,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        self._itf14_section = ft.Container(
            content=itf14_row,
            bgcolor=FONDO_SECCIONES,
            border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
            border_radius=4,
            padding=ft.Padding.all(8),
        )
        self._update_section_visibility()
        self._rebuild_dim_fields()
        # Restore UI fields from profile (override any _rebuild_dim_fields overwrites)
        _p = self.current_profile
        # print(
        #     f"[DBG OPEN] after _rebuild_dim_fields: bw={_p.bar_width} symb={_p.symbology} id={id(_p)}"
        # )
        _cfg = SYMBOLOGY_CONFIG.get(_p.symbology, {})
        for _f in _cfg.get("fields", []):
            _k = _f["key"]
            # qr_size no existe en el perfil: el tamaño QR vive en bar_width
            if _k == "qr_size":
                _v = _p.bar_width
            else:
                _v = _p.__dict__.get(_k, _f.get("default"))
            if _v is not None:
                if _f["type"] == "float" and _k != "barcode_font_size":
                    self._set_field_value(_k, self._display_mm(float(_v)))
                else:
                    self._set_field_value(_k, _v)
        # print(f"[DBG OPEN] after restore: bw={_p.bar_width}")

        # Seccion 4: Preview (expandible)
        self._zoom_slider = ft.Slider(
            min=25,
            max=400,
            value=self._zoom_value,
            width=120,
            height=24,
            on_change=self._on_zoom_change,
        )
        self._zoom_label = ft.Text(
            f"{int(self._zoom_value)}%", size=10, color=TEXTOS_FASE_1_COLOR
        )
        self._preview_container = ft.Container(
            expand=True,
            alignment=ft.Alignment.CENTER,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
            border_radius=4,
            padding=6,
            bgcolor="#FFFFFF",
        )
        def _row_nav_btn(icon, tooltip, on_click):
            return ft.Container(
                content=ft.Icon(icon, size=16, color=TEXTOS_FASE_1_COLOR),
                width=22,
                height=22,
                border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
                border_radius=11,
                bgcolor=FONDO_TEXTFIELDS_COLOR,
                alignment=ft.Alignment.CENTER,
                on_click=on_click,
                tooltip=t(tooltip),
            )

        def _row_nav_text_btn(label, tooltip, on_click):
            return ft.Container(
                content=ft.Text(label, size=10, weight=ft.FontWeight.BOLD, color=TEXTOS_FASE_1_COLOR),
                height=22,
                padding=ft.Padding(8, 0, 8, 0),
                border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
                border_radius=11,
                bgcolor=FONDO_TEXTFIELDS_COLOR,
                alignment=ft.Alignment.CENTER,
                on_click=on_click,
                tooltip=t(tooltip),
            )

        self._preview_row_prev = _row_nav_btn(
            ft.Icons.CHEVRON_LEFT, "Fila anterior", lambda e: self._set_preview_row(self._preview_row_index - 1)
        )
        self._preview_row_next = _row_nav_btn(
            ft.Icons.CHEVRON_RIGHT, "Fila siguiente", lambda e: self._set_preview_row(self._preview_row_index + 1)
        )
        self._preview_row_longest = _row_nav_text_btn(
            t("Fila más ancha"), "Fila más ancha", lambda e: self._go_to_extreme_row(want_max=True)
        )
        self._preview_row_shortest = _row_nav_text_btn(
            t("Fila más corta"), "Fila más corta", lambda e: self._go_to_extreme_row(want_max=False)
        )
        self._preview_row_counter = ft.TextField(
            value="1",
            width=52,
            height=24,
            text_size=11,
            content_padding=ft.Padding(2, 0, 6, 0),
            filled=True,
            fill_color=FONDO_TEXTFIELDS_COLOR,
            text_style=ft.TextStyle(color=TEXTO_COLOR_GENERICO),
            on_submit=lambda e: self._on_preview_row_field_submit(),border=ft.OutlineInputBorder(border_radius=4, side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)))
        self._preview_row_counter.text_align = ft.TextAlign.CENTER
        self._preview_row_nav = ft.Row(
            [
                self._preview_row_shortest,
                self._preview_row_longest,
                self._preview_row_prev,
                self._preview_row_counter,
                self._preview_row_next,
            ],
            spacing=4,
            visible=self._row_nav_enabled(),
        )

        section_preview = ft.Container(
            expand=True,
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text(
                                t("Previsualizacion"),
                                size=12,
                                weight=ft.FontWeight.BOLD,
                                color=TEXTOS_FASE_1_COLOR,
                            ),
                            ft.Container(expand=True),
                            self._zoom_slider,
                            self._zoom_label,
                            ft.Container(expand=True),
                            self._preview_row_nav,
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=4,
                    ),
                    ft.Divider(height=1, color=BORDE_TEXTFIELDS_COLOR),
                    self._preview_container,
                ],
                spacing=6,
                expand=True,
            ),
            bgcolor=FONDO_SECCIONES,
            border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
            border_radius=4,
            padding=ft.Padding.all(8),
        )

        # Error text
        self._error_text = ft.Text("", size=12, color=ERROR_COLOR, visible=False)

        right_panel = ft.Container(
            content=ft.Column(
                [
                    section_simbologia,
                    self._dim_fields_section,
                    self._itf14_section,
                    section_preview,
                    self._error_text,
                ],
                spacing=6,
                expand=True,
            ),
            width=780,
        )

        # Layout principal
        base_content = ft.Container(
            content=ft.Row(
                [
                    left_panel,
                    ft.Container(
                        content=right_panel,
                        expand=True,
                    ),
                ],
                spacing=15,
                vertical_alignment=ft.CrossAxisAlignment.STRETCH,
            ),
            width=1250,
            height=700,
        )

        self.dialog_root_stack = ft.Stack(
            controls=[base_content],
            width=1250,
            height=700,
        )
        dialog_content = self.dialog_root_stack

        # Botones
        def on_cancel(e):
            # on_cancel: nombre heredado que confunde — NO cancela. Es el handler del
            # botón "Volver", el único cierre del diálogo: confirma cambios y cierra.
            # Flush campos de tamaño que confirman solo con Enter/blur
            # (pdf417_size/height y datamatrix_width) antes de sincronizar.
            if self._pdf417_enter_target is not None:
                self._on_pdf417_field_enter(self._pdf417_enter_target)
            if getattr(self, "_datamatrix_width_target", None) is not None:
                self._on_datamatrix_field_enter(self._datamatrix_width_target)
            self._sync_fields_to_profile()
            print(f"[DBG CANCEL] symb={self.current_profile.symbology} qr_gap={self.current_profile.qr_hri_gap_mm} dm_gap={self.current_profile.datamatrix_hri_gap_mm} pdf_gap={self.current_profile.pdf417_hri_gap_mm} qr_field={self._get_field_value('qr_hri_gap_mm')!r} dm_field={self._get_field_value('datamatrix_hri_gap_mm')!r}")
            if self.on_profile_changed:
                self.on_profile_changed(self.current_profile)
            self.page.pop_dialog()

        def on_save_as_default(e):
            self._sync_fields_to_profile()
            self.save_to_preferences()
            snack = ft.SnackBar(
                content=ft.Text(
                    t("✓ Perfiles guardados como plantilla para nuevos trabajos"),
                    color=SNACKBAR_COLOR_TEXTO,
                ),
                bgcolor=SUCCESS_COLOR,
                duration=2000,
            )
            self.page.show_dialog(snack)

        self.dialog = ft.AlertDialog(
            modal=True,
            on_dismiss=lambda e: setattr(
                self.page, "on_keyboard_event", self._saved_keyboard_handler
            ),
            inset_padding=0,
            title_padding=ft.Padding(10, 20, 10, 8),
            title=ft.Container(
                content=ft.Row(
                    [
                        ft.Container(width=40),  # compensa el peso del icono derecho
                        ft.Text(
                            t("Perfiles de Codigo de Barras"),
                            size=18,
                            weight=ft.FontWeight.BOLD,
                            color=TEXTO_COLOR_GENERICO,
                            text_align=ft.TextAlign.CENTER,
                            expand=True,
                        ),
                        ft.IconButton(
                            icon=ft.Icons.HELP_OUTLINE,
                            icon_color=TEXTO_COLOR_GENERICO,
                            style=ft.ButtonStyle(
                                shape=ft.CircleBorder(),
                                padding=ft.Padding.all(4),
                                bgcolor=FONDO_SECCIONES,
                            ),
                            tooltip=t("Guía del código de barras"),
                            width=40,
                            height=40,
                            on_click=lambda e: abrir_guia_barcode(
                                self.page, self.current_profile.symbology
                            ),
                        ),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=4,
                ),
                alignment=ft.Alignment.CENTER,
            ),
            content=dialog_content,
            actions=[
                ft.Button(
                    t("Guardar en Preferencias"),
                    on_click=on_save_as_default,
                    tooltip=t(
                        "Guarda estos perfiles en preferencias para nuevos trabajos"
                    ),
                    width=170,
                    bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
                    style=ft.ButtonStyle(
                        color={
                            ft.ControlState.DEFAULT: BOTONES_GENERICOS_COLOR,
                            "hovered": BOTONES_GENERICOS_HOVER_COLOR,
                        },
                        overlay_color=BOTONES_GENERICOS_OVERLAY_COLOR,
                        padding=ft.Padding(0, 0, 0, 0),
                        shape=ft.RoundedRectangleBorder(radius=10),
                    ),
                ),
                ft.Button(
                    t("Volver"),
                    on_click=on_cancel,
                    width=110,
                    bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
                    style=ft.ButtonStyle(
                        color={
                            ft.ControlState.DEFAULT: BOTONES_GENERICOS_COLOR,
                            "hovered": BOTONES_GENERICOS_HOVER_COLOR,
                        },
                        overlay_color=BOTONES_GENERICOS_OVERLAY_COLOR,
                        padding=ft.Padding(0, 0, 0, 0),
                        shape=ft.RoundedRectangleBorder(radius=10),
                    ),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            bgcolor=FONDO_BLOQUE_RESUMEN_COLOR,
            content_padding=ft.Padding(10, 2, 10, 10),
            actions_padding=ft.Padding(10, 0, 10, 15),
        )

        self._saved_keyboard_handler = self.page.on_keyboard_event
        self.page.on_keyboard_event = self._on_page_keyboard
        purge_stale_dialog(self.page, self.dialog)
        try:
            self.page.show_dialog(self.dialog)
        except RuntimeError:
            print("[BARCODE_DIALOG] show_dialog: ya estaba en la pila (ignorado)")
        if self._pending_initial_row is not None:
            self._set_preview_row(self._pending_initial_row, update=False)
            self._pending_initial_row = None
        # print(
        #     f"[DBG PRE-PREVIEW] bw={self.current_profile.bar_width} ps={self.current_profile.pdf417_size}"
        # )
        self._on_preview_trigger(None)
        # print(
        #     f"[DBG POST-PREVIEW] bw={self.current_profile.bar_width} ps={self.current_profile.pdf417_size}"
        # )
        if debug_trace_profile_setattr and _orig_setattr is not None:
            BarcodeProfile.__setattr__ = _orig_setattr
        self.page.update()
