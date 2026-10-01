"""
Integracion de barcodes en MainScreen.
Mantiene la logica de UI de barcodes separada de main_screen.py.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Tuple

import flet as ft

from color_design import (
    BORDE_TEXTFIELDS_COLOR,
    FONDO_SECCIONES,
    FONDO_TEXTFIELDS_COLOR,
    TEXTOS_FASE_1_COLOR,
    SUCCESS_COLOR,
    ERROR_COLOR,
)
from i18n import t
from ui.barcode_settings_dialog import (
    BarcodeProfile,
    BarcodeProfileManager,
)
from ui.excel_data_dialog import ExcelDataDialog


import re as _re_vt

def _resolve_barcode_vt_template(tmpl: str, excel_manager, row: int = 0) -> str:
    if "<@<" not in tmpl or not excel_manager or not getattr(excel_manager, "is_loaded", False):
        return tmpl

    def _r(m):
        col = m.group(1).strip()
        try:
            return excel_manager.get_value_at(col, row) or ""
        except Exception:
            return ""

    return _re_vt.sub(r"<@<([^>]+)>@>", _r, tmpl)


from utils.barcode_module import (
    calcular_minimo_qr,
    validate_code128,
    get_code39_min_width,
    CODE39_MIN_HEIGHT_MM,
)
from utils.excel_manager import ExcelManager


class BarcodeUIManager:
    """Gestiona la UI de barcodes en MainScreen.

    Se encarga de:
    - Crear/editar/eliminar posiciones de barcode
    - Abrir el dialogo de configuracion de barcode (BarcodeProfileManager)
    - Gestionar la carga de Excel
    - Sincronizar con el InteractiveViewer
    """

    def __init__(
        self,
        page: ft.Page,
        viewer,
        excel_manager: ExcelManager,
        get_current_face_fn: Callable[[], str],
        get_global_settings_fn: Callable[[], dict],
        get_unit_fn: Optional[Callable] = None,
    ):
        self.page = page
        self.viewer = viewer
        self.excel_manager = excel_manager
        self.get_current_face = get_current_face_fn
        self.get_global_settings = get_global_settings_fn

        # Barcode profile manager (replaces old dict + default_profile)
        self.profile_manager = BarcodeProfileManager(
            page=page,
            on_profile_changed=self._on_profile_changed,
            get_global_settings_fn=get_global_settings_fn,
            excel_manager=excel_manager,
            get_unit_fn=get_unit_fn,
            on_row_change=self._on_row_change,
        )

        # Callbacks
        self.on_barcode_added: Optional[Callable] = None
        self.on_barcode_removed: Optional[Callable] = None
        self.on_barcode_modified: Optional[Callable] = None
        self.on_project_modified: Optional[Callable] = None
        self.on_excel_cleared: Optional[Callable] = None
        self.on_excel_reloaded: Optional[Callable] = None
        self.on_row_change: Optional[Callable] = None

    def _on_row_change(self, row_number: int):
        """Reenvía el sync fila→página del diálogo al main."""
        if self.on_row_change:
            try:
                self.on_row_change(row_number)
            except Exception:
                pass

    def _on_profile_changed(self, profile: BarcodeProfile):
        """Callback cuando un perfil cambia en el manager."""
        if self.on_barcode_modified:
            self.on_barcode_modified(profile)

    def _find_profile(self, name: str) -> Optional[BarcodeProfile]:
        """Busca un perfil por nombre en el manager."""
        for p in self.profile_manager.get_profiles():
            if p.name == name:
                return p
        return None

    def add_barcode_position(
        self,
        x: float,
        y: float,
        profile_name: str = "<Default>",
        value: str = "",
        rotation: str = "0°",
        alignment: str = "izquierda",
        color: str = "#000000",
        color_cmyk: tuple = None,
        color_space: str = "RGB",
        color_name: str = "",
        color_tint: float = 100.0,
        text_color: str = "#000000",
        text_color_cmyk: tuple = None,
        text_color_space: str = "RGB",
        text_color_name: str = "",
        text_color_tint: float = 100.0,
        barcode_id: Optional[int] = None,
        auto_select: bool = True,
    ) -> int:
        """Anade un barcode en el viewer y devuelve su ID."""
        profile = self._find_profile(profile_name)
        if profile is None:
            profiles = self.profile_manager.get_profiles()
            profile = profiles[0] if profiles else BarcodeProfile.create_default()

        if color_cmyk is None:
            color_cmyk = profile.color_cmyk

        if text_color_cmyk is None:
            text_color_cmyk = getattr(profile, "text_color_cmyk", (0.0, 0.0, 0.0, 100.0))

        if not value:
            if profile.value_source == "excel" and profile.excel_column and self.excel_manager.is_loaded:
                first_val = self.excel_manager.get_value_at(profile.excel_column, 0)
                value = first_val or profile.sample_value
            elif (
                profile.value_source == "fixed"
                and "<@<" in (profile.sample_value or "")
                and profile.symbology in ("qr", "pdf417", "datamatrix")
                and self.excel_manager.is_loaded
            ):
                value = _resolve_barcode_vt_template(profile.sample_value, self.excel_manager, 0) or profile.sample_value
            else:
                value = profile.sample_value

        if profile.symbology == "upca":
            bw = profile.bar_width or 37.29
            bh = profile.bar_height or 25.91
            bar_width = max(29.83, min(74.58, bw))
            bar_height = max(20.73, min(51.82, bh))
        elif profile.symbology == "upce":
            bw = profile.bar_width or 22.11
            bh = profile.bar_height or 25.91
            bar_width = max(17.69, min(44.22, bw))
            bar_height = max(20.73, min(51.82, bh))
        elif profile.symbology == "qr":
            # GS1: QR — mínimo dinámico según datos
            vals = []
            if profile.value_source == "excel" and profile.excel_column and self.excel_manager.is_loaded:
                vals = self.excel_manager.get_column_values(profile.excel_column)
            elif profile.value_source == "numbering":
                vals = [value] if value else []
            elif profile.sample_value:
                if "<@<" in profile.sample_value and profile.symbology in ("qr", "pdf417", "datamatrix") and self.excel_manager.is_loaded:
                    # VT personalizado: resolver todas las filas para mínimo
                    try:
                        vals = [
                            _resolve_barcode_vt_template(profile.sample_value, self.excel_manager, r)
                            for r in range(self.excel_manager.row_count)
                        ]
                    except Exception:
                        vals = [profile.sample_value]
                else:
                    vals = [profile.sample_value]
            min_w = calcular_minimo_qr(vals) if vals else 20.0
            bar_width = max(min_w, profile.bar_width) if profile.bar_width is not None else min_w
            bar_height = bar_width
        elif profile.symbology == "code128":
            # GS1: Code128 ancho 40–165.10mm, alto 12–32mm
            bar_width = max(40.0, min(165.10, profile.bar_width)) if profile.bar_width is not None else 40.0
            bar_height = max(12.0, min(32.0, profile.bar_height)) if profile.bar_height is not None else 12.0
        elif profile.symbology == "ean5":
            # GS1: EAN-5 complementario 17.92–44.80 × 20.73–51.82mm
            bw = profile.bar_width or 17.92
            bh = profile.bar_height or 20.73
            bar_width = max(17.92, min(44.80, bw))
            bar_height = max(20.73, min(51.82, bh))
        elif profile.symbology == "ean13":
            # GS1: EAN-13 29.83–74.58 × 20.73–51.82mm
            bw = profile.bar_width or 29.83
            bh = profile.bar_height or 20.73
            bar_width = max(29.83, min(74.58, bw))
            bar_height = max(20.73, min(51.82, bh))
        elif profile.symbology == "ean8":
            # GS1: EAN-8 21.38–53.45 × 17.05–42.63mm
            bw = profile.bar_width or 21.38
            bh = profile.bar_height or 17.05
            bar_width = max(21.38, min(53.45, bw))
            bar_height = max(17.05, min(42.63, bh))
        elif profile.symbology == "isbn13":
            # GS1: ISBN-13 = EAN-13 29.83–74.58 × 20.73–51.82mm
            bw = profile.bar_width or 37.29
            bh = profile.bar_height or 25.91
            bar_width = max(29.83, min(74.58, bw))
            bar_height = max(20.73, min(51.82, bh))
        elif profile.symbology == "itf14":
            # GS1: ITF-14 — min size depends on printer type
            if profile.itf14_printer_type == "flexografia":
                min_w, min_h = 89.25, 32.00
            else:
                min_w, min_h = 71.40, 12.70
            bar_width = max(min_w, profile.bar_width or min_w)
            bar_height = max(min_h, profile.bar_height or 0.0)
        elif profile.symbology == "code39":
            # GS1: Code39 — ancho mínimo dinámico según datos, alto mínimo 15mm
            vals = []
            if profile.value_source == "excel" and profile.excel_column and self.excel_manager.is_loaded:
                vals = self.excel_manager.get_column_values(profile.excel_column)
            elif profile.value_source == "numbering":
                vals = [value] if value else []
            elif profile.sample_value:
                vals = [profile.sample_value]
            min_w = get_code39_min_width(vals) if vals else 40.0
            bar_width = max(min_w, profile.bar_width) if profile.bar_width is not None else min_w
            bar_height = max(CODE39_MIN_HEIGHT_MM, profile.bar_height) if profile.bar_height is not None else CODE39_MIN_HEIGHT_MM
        else:
            bar_width = profile.bar_width
            bar_height = profile.bar_height

        bid = self.viewer.add_barcode(
            x=x,
            y=y,
            value=value,
            symbology=profile.symbology,
            bar_width=bar_width,
            bar_height=bar_height,
            rotation=rotation,
            alignment=alignment,
            color=color or profile.color,
            color_cmyk=color_cmyk,
            color_space=color_space or profile.color_space,
            color_name=color_name or profile.color_name,
            color_tint=color_tint or profile.color_tint,
            text_color=text_color or getattr(profile, "text_color", "#000000"),
            text_color_cmyk=text_color_cmyk,
            text_color_space=text_color_space
            or getattr(profile, "text_color_space", "RGB"),
            text_color_name=text_color_name
            or getattr(profile, "text_color_name", ""),
            text_color_tint=text_color_tint
            or getattr(profile, "text_color_tint", 100.0),
            value_source=profile.value_source,
            mask=profile.mask,
            error_correction=profile.error_correction,
            barcode_font_family=getattr(profile, "barcode_font_family", "OCR-B"),
            barcode_font_size=getattr(profile, "barcode_font_size", 13.0),
            itf14_quiet_zone_mm=getattr(profile, "itf14_quiet_zone_mm", 10.16),
            itf14_bearer_thickness_mm=getattr(profile, "itf14_bearer_thickness_mm", 4.8),
            itf14_bearer_sides=getattr(profile, "itf14_bearer_sides", "4"),
            itf14_gtin_type=getattr(profile, "itf14_gtin_type", "gtin14"),
            itf14_printer_type=getattr(profile, "itf14_printer_type", "flexografia"),
            itf14_hri_gap_mm=getattr(profile, "itf14_hri_gap_mm", 2.0),
            itf14_hri_position=getattr(profile, "itf14_hri_position", "below"),
            isbn13_show_title=getattr(profile, "isbn13_show_title", "Sí"),
            ean5_hri_gap_mm=getattr(profile, "ean5_hri_gap_mm", 2.0),
            pdf417_height=getattr(profile, "pdf417_height", None),
            code39_hri_gap_mm=getattr(profile, "code39_hri_gap_mm", 2.0),
            code39_hri_position=getattr(profile, "code39_hri_position", "below"),
            code128_hri_gap_mm=getattr(profile, "code128_hri_gap_mm", 2.0),
            code128_hri_position=getattr(profile, "code128_hri_position", "below"),
            datamatrix_width=getattr(profile, "datamatrix_width", 20.0),
            datamatrix_height=getattr(profile, "datamatrix_height", 20.0),
            datamatrix_format=getattr(profile, "datamatrix_format", ""),
            datamatrix_hri_gap_mm=getattr(profile, "datamatrix_hri_gap_mm", 2.0),
            datamatrix_hri_position=getattr(profile, "datamatrix_hri_position", "below"),
            datamatrix_hri_align=getattr(profile, "datamatrix_hri_align", "bottom_center"),
            datamatrix_hri_line_spacing=getattr(profile, "datamatrix_hri_line_spacing", 1.0),
            qr_hri_gap_mm=getattr(profile, "qr_hri_gap_mm", 2.0),
            qr_hri_position=getattr(profile, "qr_hri_position", "below"),
            qr_hri_align=getattr(profile, "qr_hri_align", "bottom_center"),
            qr_hri_line_spacing=getattr(profile, "qr_hri_line_spacing", 1.0),
            qr_del_open=getattr(profile, "qr_del_open", "") or "",
            qr_del_close=getattr(profile, "qr_del_close", "|") or "|",
            qr_del_close_newline=bool(getattr(profile, "qr_del_close_newline", False)),
            pdf417_hri_gap_mm=getattr(profile, "pdf417_hri_gap_mm", 2.0),
            pdf417_hri_position=getattr(profile, "pdf417_hri_position", "below"),
            pdf417_hri_align=getattr(profile, "pdf417_hri_align", "bottom_center"),
            pdf417_hri_line_spacing=getattr(profile, "pdf417_hri_line_spacing", 1.0),
            pdf417_del_open=getattr(profile, "pdf417_del_open", "") or "",
            pdf417_del_close=getattr(profile, "pdf417_del_close", "|") or "|",
            pdf417_del_close_newline=bool(getattr(profile, "pdf417_del_close_newline", False)),
            profile_name=profile_name,
            auto_select=auto_select,
            barcode_id=barcode_id,
        )

        if self.on_barcode_added:
            self.on_barcode_added(bid, profile_name)

        return bid

    def remove_barcode_position(self, barcode_id: int):
        """Elimina un barcode del viewer."""
        self.viewer.remove_barcode(barcode_id)
        if self.on_barcode_removed:
            self.on_barcode_removed(barcode_id)

    def open_barcode_dialog(
        self,
        profile_name: Optional[str] = None,
        position_data: Optional[dict] = None,
        initial_row: Optional[int] = None,
    ):
        """Abre el dialogo de configuracion de barcode (BarcodeProfileManager)."""
        # Sincronizar columnas Excel antes de abrir
        columns = self.excel_manager.columns if self.excel_manager.is_loaded else []
        self.profile_manager.set_excel_columns(columns)

        # Si se pide un perfil especifico, seleccionarlo
        if profile_name:
            profiles = self.profile_manager.get_profiles()
            for i, p in enumerate(profiles):
                if p.name == profile_name:
                    self.profile_manager.selected_profile_index = i
                    self.profile_manager.current_profile = p
                    break

        self.profile_manager.set_initial_row(initial_row)
        # NOTA: El perfil es la fuente de verdad.
        # No sobreescribir campos del perfil con position_data,
        # pues pos_data de la otra cara puede tener valores obsoletos.
        self.profile_manager.open()

    def open_excel_dialog(self, vt_profile_manager=None):
        """Abre dialogo de gestion de datos externos con ListView."""
        dialog = ExcelDataDialog(
            page=self.page,
            excel_manager=self.excel_manager,
            get_global_settings_fn=self.get_global_settings,
            on_data_loaded=self._on_excel_data_loaded,
            on_modified=self.on_project_modified,
            on_excel_cleared=self.on_excel_cleared,
            barcode_profile_manager=self.profile_manager,
            vt_profile_manager=vt_profile_manager,
        )
        dialog.open()

    def _on_excel_data_loaded(self):
        """Callback cuando se confirma la carga de datos en el dialogo."""
        columns = self.excel_manager.columns if self.excel_manager.is_loaded else []
        self.profile_manager.set_excel_columns(columns)
        if self.on_excel_reloaded:
            self.on_excel_reloaded()

    def get_barcode_data_for_position(self, barcode_id: int) -> dict:
        """Obtiene datos de barcode para guardar en posicion."""
        data = self.viewer.get_barcode_data(barcode_id)
        if not data:
            return {}
        return {
            "type": "barcode",
            "barcode_value": data.get("value", ""),
            "sample_value": data.get("sample_value", ""),
            "symbology": data.get("symbology", "code128"),
            "bar_width": data.get("bar_width", 80.0),
            "bar_height": data.get("bar_height", 30.0),
            "color": data.get("color", "#000000"),
            "color_cmyk": data.get("color_cmyk"),
            "color_space": data.get("color_space", "RGB"),
            "color_name": data.get("color_name", ""),
            "color_tint": data.get("color_tint", 100.0),
            "text_color": data.get("text_color", "#000000"),
            "text_color_cmyk": data.get("text_color_cmyk"),
            "text_color_space": data.get("text_color_space", "RGB"),
            "text_color_name": data.get("text_color_name", ""),
            "text_color_tint": data.get("text_color_tint", 100.0),
            "value_source": data.get("value_source", "fixed"),
            "mask": data.get("mask", ""),
            "error_correction": data.get("error_correction", "M"),
            "barcode_font_family": data.get("barcode_font_family", "OCR-B"),
            "barcode_font_size": data.get("barcode_font_size", 13.0),
            "itf14_quiet_zone_mm": data.get("itf14_quiet_zone_mm", 10.16),
            "itf14_bearer_thickness_mm": data.get("itf14_bearer_thickness_mm", 4.8),
            "itf14_bearer_sides": data.get("itf14_bearer_sides", "4"),
            "itf14_gtin_type": data.get("itf14_gtin_type", "gtin14"),
            "itf14_indicator": data.get("itf14_indicator", "1"),
            "itf14_printer_type": data.get("itf14_printer_type", "flexografia"),
            "itf14_hri_gap_mm": data.get("itf14_hri_gap_mm", 0.0),
            "itf14_hri_position": data.get("itf14_hri_position", "below"),
            "code39_hri_gap_mm": data.get("code39_hri_gap_mm", 2.0),
            "code128_hri_gap_mm": data.get("code128_hri_gap_mm", 2.0),
            "ean5_hri_gap_mm": data.get("ean5_hri_gap_mm", 2.0),
            "pdf417_height": data.get("pdf417_height"),
            "pdf417_size": data.get("pdf417_size"),
            "datamatrix_width": data.get("datamatrix_width", 20.0),
            "datamatrix_height": data.get("datamatrix_height", 20.0),
            "datamatrix_format": data.get("datamatrix_format", ""),
            "datamatrix_hri_gap_mm": data.get("datamatrix_hri_gap_mm", 2.0),
            "datamatrix_hri_position": data.get("datamatrix_hri_position", "below"),
            "datamatrix_hri_align": data.get("datamatrix_hri_align", "bottom_center"),
            "datamatrix_hri_line_spacing": data.get("datamatrix_hri_line_spacing", 1.0),
            "datamatrix_del_open": data.get("datamatrix_del_open", "") or "",
            "datamatrix_del_close": data.get("datamatrix_del_close", "|") or "|",
            "datamatrix_del_close_newline": bool(data.get("datamatrix_del_close_newline", False)),
            "qr_hri_gap_mm": data.get("qr_hri_gap_mm", 2.0),
            "qr_hri_position": data.get("qr_hri_position", "below"),
            "qr_hri_align": data.get("qr_hri_align", "bottom_center"),
            "qr_hri_line_spacing": data.get("qr_hri_line_spacing", 1.0),
            "qr_del_open": data.get("qr_del_open", "") or "",
            "qr_del_close": data.get("qr_del_close", "|") or "|",
            "qr_del_close_newline": bool(data.get("qr_del_close_newline", False)),
            "pdf417_hri_gap_mm": data.get("pdf417_hri_gap_mm", 2.0),
            "pdf417_hri_position": data.get("pdf417_hri_position", "below"),
            "pdf417_hri_align": data.get("pdf417_hri_align", "bottom_center"),
            "pdf417_hri_line_spacing": data.get("pdf417_hri_line_spacing", 1.0),
            "pdf417_del_open": data.get("pdf417_del_open", "") or "",
            "pdf417_del_close": data.get("pdf417_del_close", "|") or "|",
            "pdf417_del_close_newline": bool(data.get("pdf417_del_close_newline", False)),
        }
