"""
Diálogo de configuración de textos variables con gestión de perfiles.
Reutiliza la lógica de tipografía de text_settings_dialog.py.
"""

from __future__ import annotations

import os
import re
import sys
import uuid
import logging
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import flet as ft

def _safe_page(ctrl):
    """Devuelve ctrl.page o None si no está montado (Flet 1.0: .page lanza RuntimeError)."""
    try:
        return ctrl.page
    except Exception:
        return None


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
from ui.dialog_utils import show_rename_profile_dialog, purge_stale_dialog, reopen_dialog
from ui.color_picker import ColorPicker
from ui.color_picker_dialog import ColorPickerDialog
from ui.guia_html_viewer import abrir_guia
from utils.preferences import (
    get_variable_text_profiles,
    save_variable_text_profiles,
)
from utils.constants import normalize_decimal_input
from utils.variable_text_measure import (
    _vt_hex_to_rgb,
    find_extreme_row,
    render_vt_image_b64,
    resolve_vt_text,
)


LINE_SPACING_AUTO = 1.2  # interlineado por defecto = 1.2 × cuerpo (InDesign auto)


def _fmt_pt(v: float) -> str:
    """Formatea tamaño de letra: '24' para enteros, '24.5' para fracciones."""
    return str(int(v)) if v == int(v) else f"{v:.1f}"

try:
    import fitz
except ImportError:
    fitz = None


# ============================================================================
# Shared measurement
# ============================================================================


def measure_text_lines(
    text: str, font_family: str, font_size: float, font_path: str = None
):
    """Mide cada línea de texto con PyMuPDF.
    font_path: ruta al archivo de fuente .ttf/.otf (prioritario).
              Si es None, intenta fontname como fallback.
    Returns dict with keys: line_widths_pt, max_width_pt, total_height_pt,
    line_height_pt, num_lines.
    """
    lines = text.split("\n") if text else [""]
    font_pdf = None
    if fitz:
        try:
            if font_path and os.path.exists(font_path):
                font_pdf = fitz.Font(fontfile=font_path)
            else:
                font_pdf = fitz.Font(fontname=font_family)
        except Exception:
            pass

    line_widths_pt = []
    for line in lines:
        if font_pdf:
            w = sum(float(font_pdf.text_length(ch, fontsize=font_size)) for ch in line)
        else:
            w = len(line) * font_size * 0.6
        line_widths_pt.append(w)

    max_width_pt = max(line_widths_pt) if line_widths_pt else 0

    if font_pdf:
        line_height_pt = font_size * (font_pdf.ascender - font_pdf.descender)
    else:
        line_height_pt = font_size * 1.2

    total_height_pt = len(lines) * line_height_pt

    return {
        "line_widths_pt": line_widths_pt,
        "max_width_pt": max_width_pt,
        "total_height_pt": total_height_pt,
        "line_height_pt": line_height_pt,
        "num_lines": len(lines),
    }


# ============================================================================
# Constantes
# ============================================================================

TEXT_CASE_FILTER_OPTIONS = [
    ("", t("Sin filtro")),
    ("upper", t("MAYÚSCULAS")),
    ("lower", t("minúsculas")),
    ("capitalize", t("Inicial mayúscula")),
]

VALUE_SOURCE_OPTIONS = [
    ("sample", t("Texto de muestra")),
    ("excel", t("Datos externos")),
]

# 9 puntos de anclaje de la caja de texto sobre las guías (diálogo = main = PDF).
ANCHOR_TOP_LEFT = "superior_izquierda"
ANCHOR_TOP_CENTER = "superior_centro"
ANCHOR_TOP_RIGHT = "superior_derecha"
ANCHOR_MID_LEFT = "centro_izquierda"
ANCHOR_MID_CENTER = "centro_centro"
ANCHOR_MID_RIGHT = "centro_derecha"
ANCHOR_BOTTOM_LEFT = "inferior_izquierda"
ANCHOR_BOTTOM_CENTER = "inferior_centro"
ANCHOR_BOTTOM_RIGHT = "inferior_derecha"

# Alineación del texto DENTRO de la caja (izquierda/centro/derecha).
# La caja abraza el texto por los 4 lados, así que el texto solo se alinea
# en horizontal; los 9 anclajes de la caja los gestiona el main (`anchor`).
TEXT_ALIGN_OPTIONS = [
    ("izquierda", t("izquierda")),
    ("centro", t("centro")),
    ("derecha", t("derecha")),
]
TEXT_ALIGN_KEYS = [o[0] for o in TEXT_ALIGN_OPTIONS]

ANCHORS = [
    ANCHOR_TOP_LEFT,
    ANCHOR_TOP_CENTER,
    ANCHOR_TOP_RIGHT,
    ANCHOR_MID_LEFT,
    ANCHOR_MID_CENTER,
    ANCHOR_MID_RIGHT,
    ANCHOR_BOTTOM_LEFT,
    ANCHOR_BOTTOM_CENTER,
    ANCHOR_BOTTOM_RIGHT,
]

# Etiqueta i18n de cada ancla (mismas claves que datamatrix, ya traducidas en lang.py).
ANCHOR_LABELS = {
    ANCHOR_TOP_LEFT: t("top_left"),
    ANCHOR_TOP_CENTER: t("top_center"),
    ANCHOR_TOP_RIGHT: t("top_right"),
    ANCHOR_MID_LEFT: t("middle_left"),
    ANCHOR_MID_CENTER: t("middle_center"),
    ANCHOR_MID_RIGHT: t("middle_right"),
    ANCHOR_BOTTOM_LEFT: t("bottom_left"),
    ANCHOR_BOTTOM_CENTER: t("bottom_center"),
    ANCHOR_BOTTOM_RIGHT: t("bottom_right"),
}


def get_anchor_options() -> list:
    """Opciones (anchor, etiqueta) para dropdown de posición, orden visual."""
    return [(a, ANCHOR_LABELS.get(a, a)) for a in ANCHORS]

# Migración del viejo `alignment` (3) a `anchor` (9): fila SUPERIOR.
# Decisión del usuario: el default al añadir un VT es superior izquierda,
# así que un perfil legacy sin anchor (o sin alignment) nunca cae a la fila central.
_ALIGN_TO_ANCHOR = {
    "izquierda": ANCHOR_TOP_LEFT,
    "centro": ANCHOR_TOP_CENTER,
    "derecha": ANCHOR_TOP_RIGHT,
}


def _normalize_anchor(value, default=ANCHOR_TOP_LEFT):
    if value in ANCHORS:
        return value
    return _ALIGN_TO_ANCHOR.get(value, default)


# ============================================================================
# VariableTextProfile dataclass
# ============================================================================


@dataclass
class VariableTextProfile:
    """Perfil de configuración para un texto variable."""

    id: str
    name: str
    font_family: str
    font_style: str
    font_size: float

    text_color: str = "#000000"
    text_color_cmyk: tuple = (0.0, 0.0, 0.0, 100.0)
    text_color_space: str = "RGB"
    text_color_name: str = ""
    text_color_tint: float = 100.0

    value_source: str = "sample"
    sample_text: str = "Texto de muestra"
    excel_column: str = ""
    text_case_filter: str = ""

    line_spacing: float = 0.0
    letter_spacing: float = 0.0
    text_alignment: str = "izquierda"
    anchor: str = "superior_izquierda"
    ls_migrated: bool = True

    @property
    def alignment(self):
        # ponytail: alias para las lecturas legacy de `profile.alignment`
        # (main_screen, viewer, integration) — el campo real es `text_alignment`.
        return self.text_alignment

    resolved_font_path: str = None
    resolved_font_index: int = 0
    resolved_status: str = None
    metricas: dict = None
    resolved_flet_alias: str = None

    def copy(self) -> "VariableTextProfile":
        import copy as copy_module

        return copy_module.copy(self)

    @staticmethod
    def apply_text_case_filter(text: str, filter_type: str) -> str:
        if not text or not filter_type:
            return text
        if filter_type == "upper":
            return text.upper()
        elif filter_type == "lower":
            return text.lower()
        elif filter_type == "capitalize":
            return text[:1].upper() + text[1:] if text else text
        return text

    @staticmethod
    def create_default(name: str = "<Default>") -> "VariableTextProfile":
        from utils.font_manager import get_default_font_family

        return VariableTextProfile(
            id=str(uuid.uuid4()),
            name=name,
            font_family=get_default_font_family(),
            font_style="Regular",
            font_size=12.0,
            line_spacing=LINE_SPACING_AUTO * 12.0,
            value_source="sample",
        )

    def to_dict(self) -> dict:
        d = asdict(self)
        d["text_color_cmyk"] = list(self.text_color_cmyk)
        for key in (
            "resolved_font_path",
            "resolved_font_index",
            "resolved_status",
            "metricas",
            "resolved_flet_alias",
        ):
            d.pop(key, None)
        return d

    @staticmethod
    def from_dict(data: dict) -> "VariableTextProfile":
        valid_fields = {
            "id",
            "name",
            "font_family",
            "font_style",
            "font_size",
            "text_color",
            "text_color_cmyk",
            "text_color_space",
            "text_color_name",
            "text_color_tint",
            "value_source",
            "sample_text",
            "excel_column",
            "text_case_filter",
            "line_spacing",
            "letter_spacing",
            "text_alignment",
            "anchor",
            "alignment",
            "ls_migrated",
            "resolved_font_path",
            "resolved_flet_alias",
            "resolved_status",
            "resolved_font_index",
        }
        data = {k: v for k, v in data.items() if k in valid_fields}

        if "text_color" not in data or data["text_color"] is None:
            data["text_color"] = "#000000"
        if "text_color_cmyk" not in data or data["text_color_cmyk"] is None:
            from ui.color_picker import hex2rgb, rgb_to_cmyk

            r, g, b = hex2rgb(data["text_color"])
            data["text_color_cmyk"] = rgb_to_cmyk(r, g, b)
        else:
            data["text_color_cmyk"] = tuple(data["text_color_cmyk"])

        for field, default in (
            ("text_color_space", "RGB"),
            ("text_color_name", ""),
            ("text_color_tint", 100.0),
            ("value_source", "sample"),
            ("sample_text", "Texto de muestra"),
            ("excel_column", ""),
            ("text_case_filter", ""),
            ("line_spacing", 0.0),
            ("letter_spacing", 0.0),
        ):
            if field not in data:
                data[field] = default

        data["line_spacing"] = float(data.get("line_spacing", 0.0) or 0.0)
        data["letter_spacing"] = float(data.get("letter_spacing", 0.0) or 0.0)
        # Migración única: perfiles guardados antes del modelo pt (line_spacing
        # aditivo, 0 = "tintas tocadas") → auto 1.2×cuerpo. El flag se serializa
        # en to_dict, así un 0 intencional del usuario ya no se re-migra.
        if not data.get("ls_migrated") and not data["line_spacing"]:
            data["line_spacing"] = LINE_SPACING_AUTO * float(
                data.get("font_size", 12.0) or 12.0
            )
        data["ls_migrated"] = True
        if "text_alignment" not in data or data["text_alignment"] not in TEXT_ALIGN_KEYS:
            data["text_alignment"] = "izquierda"
        data["anchor"] = _normalize_anchor(
            data.get("anchor"), _ALIGN_TO_ANCHOR.get(data.get("alignment"), ANCHOR_TOP_LEFT)
        )
        data.pop("alignment", None)

        return VariableTextProfile(**data)


# ============================================================================
# VariableTextProfileManager
# ============================================================================


class VariableTextProfileManager:
    """Gestor de perfiles de texto variable con interfaz de diálogo."""

    def __init__(
        self,
        page: ft.Page,
        on_profile_changed: Optional[Callable] = None,
        viewer_callback=None,
        excel_manager=None,
        on_row_change: Optional[Callable] = None,
        on_profile_renamed: Optional[Callable] = None,
    ):
        self.page = page
        self.on_profile_changed = on_profile_changed
        self.on_profile_renamed = on_profile_renamed
        self.viewer_callback = viewer_callback
        self.excel_manager = excel_manager
        self.on_row_change = on_row_change

        # Inicializar gestor de fuentes (misma lógica que TextStyleManager)
        from utils.font_manager import obtener_gestor

        self.gestor = obtener_gestor()

        self.profiles: list[VariableTextProfile] = [
            VariableTextProfile.create_default()
        ]
        self.selected_profile_index: int = 0
        self.current_profile: VariableTextProfile = self.profiles[0].copy()

        self.extracted_spot_colors: list = []
        self.color_picker_dialog = None
        self._color_target: Optional[str] = None

        # UI refs
        self.profile_list: Optional[ft.ListView] = None
        self.btn_new_profile: Optional[ft.IconButton] = None
        self.btn_delete_profile: Optional[ft.IconButton] = None
        self.btn_refresh_fonts: Optional[ft.IconButton] = None

        self._font_family_listview: Optional[ft.ListView] = None
        self._font_family_list: Optional[ft.Container] = None
        self._font_style_list: Optional[ft.Container] = None
        self._font_size_field: Optional[ft.TextField] = None
        self._value_source_dropdown: Optional[ft.Container] = None
        self._text_case_filter_dropdown: Optional[ft.Container] = None
        self._text_alignment_dropdown: Optional[ft.Container] = None
        self._line_spacing_field: Optional[ft.TextField] = None
        self._line_spacing_arrows: Optional[ft.Column] = None
        self._interlineado_auto = True
        self._btn_open_editor: Optional[ft.Button] = None
        self._vt_editor_state: Optional[dict] = None
        self._excel_columns: List[str] = []
        self._preview_text: Optional[ft.Text] = None
        self._preview_row_index: int = 0
        self._preview_row_prev: Optional[ft.Container] = None
        self._preview_row_counter: Optional[ft.TextField] = None
        self._preview_row_next: Optional[ft.Container] = None
        self._preview_row_nav: Optional[ft.Row] = None
        self._pending_initial_row: Optional[int] = None

        self._text_color_swatch: Optional[ft.Container] = None
        self.dialog: Optional[ft.AlertDialog] = None
        self.dialog_root_stack: Optional[ft.Stack] = None

        # Fuentes del sistema
        self.available_fonts: Optional[dict[str, list[str]]] = None
        self.available_fonts_status: dict = {}
        self.font_metrics_cache = None

        # Cargar fuentes y resolver perfiles en startup
        try:
            self.available_fonts = self._load_system_fonts()
            self._resolve_profiles()
        except Exception as e:
            print(f"[VAR_TEXT] Error inicializando fuentes: {e}")

        # Cargar perfiles desde preferencias (reemplaza self.profiles)
        self.load_from_preferences()

        # Resolver fuentes y cargar métricas para los perfiles ya cargados
        try:
            self._resolve_profiles()

            from utils.metrics_analisys import FontMetricsCache, cargar_metricas_perfiles

            self.font_metrics_cache = FontMetricsCache()
            fuentes_sistema = {}
            if self.available_fonts:
                for family, styles in self.available_fonts.items():
                    fuentes_sistema[family] = (
                        list(styles) if isinstance(styles, (list, set)) else [styles]
                    )
            cargar_metricas_perfiles(
                self.profiles,
                fuentes_sistema,
                self.font_metrics_cache,
                default_profile=None,
            )
        except Exception as e:
            print(f"[VAR_TEXT] Error cargando métricas: {e}")
            self.font_metrics_cache = None

    # ------------------------------------------------------------------
    # Font loading (reutiliza text_settings_dialog)
    # ------------------------------------------------------------------
    def _load_system_fonts(self) -> dict[str, list[str]]:
        """Carga fuentes del sistema usando font_index."""
        try:
            from utils import font_index_wrapper as font_index

            fonts = font_index.get_normalized_fonts()
            try:
                self.available_fonts_status = font_index.validate_cached_fonts(fonts)
            except Exception:
                self.available_fonts_status = {}
            return fonts
        except Exception as e:
            print(f"[VAR_TEXT] Error cargando fuentes: {e}")
            return {
                "Helvetica": ["Regular"],
                "Arial": ["Regular", "Bold", "Italic", "Bold Italic"],
            }

    def _ensure_fonts_loaded(self):
        if not self.available_fonts:
            self.available_fonts = self._load_system_fonts()

    def _refresh_system_fonts(self, force_reload=False):
        """Refresca el índice de fuentes del sistema (misma lógica que TextStyleManager)."""
        try:
            from utils import font_index_wrapper as font_index

            gestor = self.gestor
            if gestor:
                gestor.sincronizar_con_catalogo_sistema(skip_non_latin=True)
            self.available_fonts = font_index.get_normalized_fonts()
            try:
                self.available_fonts_status = font_index.validate_cached_fonts(
                    self.available_fonts
                )
            except Exception:
                self.available_fonts_status = {}
            self._resolve_profiles()
        except Exception as e:
            print(f"[VAR_TEXT] Error refrescando fuentes: {e}")
            if not self.available_fonts:
                self.available_fonts = self._load_system_fonts()

    def _resolve_profiles(self):
        """Resuelve rutas de fuentes para los perfiles (misma lógica que TextStyleManager)."""
        try:
            from utils import font_index_wrapper as font_index
            from utils import pdf_generator
        except Exception:
            return

        for profile in self.profiles:
            try:
                orig_path = getattr(profile, "resolved_font_path", None)
                p, status = font_index.find_font_file_for(
                    profile.font_family, profile.font_style
                )
                if (p is None or status == "missing") and orig_path and os.path.exists(orig_path):
                    p, status = orig_path, "installed"
                if (p is None or status == "missing") and " " in (profile.font_family or ""):
                    alias_family = profile.font_family.replace(" ", "")
                    p2, s2 = font_index.find_font_file_for(alias_family, profile.font_style)
                    if p2:
                        p, status = p2, s2
                if (p is None or status == "missing"):
                    from pathlib import Path as _P
                    fam = (profile.font_family or "").lower().replace(" ", "")
                    sty = (profile.font_style or "").lower().replace(" ", "")
                    for base in [_P.home() / "Documents" / "TIPOS", _P.home() / "Documents" / "TIPOS" / "Adobe Font Folio Fonts"]:
                        if not base.exists():
                            continue
                        for cand in base.rglob("*.otf"):
                            stem = cand.stem.lower().replace(" ", "")
                            if stem == f"{fam}-{sty}" or stem == f"{fam}{sty}":
                                p, status = str(cand), "installed"
                                break
                        if p:
                            break
                profile.resolved_font_path = p
                profile.resolved_status = status
                profile.resolved_font_index = 0
                if p and p.lower().endswith(".ttc"):
                    try:
                        profile.resolved_font_index = pdf_generator._get_ttc_font_index(
                            p, profile.font_style
                        )
                    except Exception:
                        profile.resolved_font_index = 0
                # Buscar en extracted_map
                try:
                    from utils import font_cache

                    base = font_cache.get_config_dir()
                    cache = font_cache.load_cache(base) or {}
                    em = cache.get("extracted_map", {}) or {}
                    key = f"{p}|{profile.resolved_font_index}" if p else None
                    if key and key in em:
                        entry = em.get(key) or {}
                        extracted = entry.get("extracted_path")
                        # Validar checksum del TTC original vs el guardado: si la
                        # fuente en esta ruta cambió, extraer_ttc_individual re-extrae
                        try:
                            extracted = self.gestor.extraer_ttc_individual(
                                p, profile.resolved_font_index
                            )
                        except Exception:
                            extracted = None
                        if extracted is not None:
                            extracted = str(extracted)
                        family_safe = profile.font_family.replace(" ", "")
                        style_safe = profile.font_style.replace(" ", "")
                        alias = f"{family_safe}-{style_safe}"
                        profile.resolved_flet_alias = alias
                        if extracted and Path(extracted).exists():
                            profile.resolved_font_path = extracted
                            profile.resolved_font_index = None
                            if hasattr(self.page, "fonts"):
                                if self.page.fonts is None:
                                    self.page.fonts = {}
                                if alias not in self.page.fonts:
                                    self.page.fonts[alias] = extracted
                    else:
                        # Fuentes .ttf/.otf directas (no TTC): registrar alias en page.fonts
                        # sin necesidad de extracted_map (misma lógica que text_settings_dialog).
                        if p and not p.lower().endswith((".ttc", ".otc")):
                            family_safe = profile.font_family.replace(" ", "")
                            style_safe = profile.font_style.replace(" ", "")
                            alias = f"{family_safe}-{style_safe}"
                            profile.resolved_flet_alias = alias
                            if hasattr(self.page, "fonts"):
                                if self.page.fonts is None:
                                    self.page.fonts = {}
                                if alias not in self.page.fonts:
                                    self.page.fonts[alias] = p
                except Exception:
                    pass
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Font style list update (reutiliza text_settings_dialog)
    # ------------------------------------------------------------------
    def _normalize_display_name(self, name: str) -> str:
        """Convierte nombre PostScript a etiqueta legible."""
        if not name:
            return "Regular"
        raw = name.strip()
        if not raw:
            return "Regular"

        family = (self.current_profile.font_family or "").strip()

        if "-" in raw:
            style_part = raw.split("-", 1)[1]
        else:
            family_compact = re.sub(r"[^a-z0-9]", "", family.lower())
            raw_compact = re.sub(r"[^a-z0-9]", "", raw.lower())
            if family_compact and raw_compact.startswith(family_compact):
                style_compact = raw_compact[len(family_compact) :]
                if not style_compact:
                    return "Regular"
                style_part = style_compact
            else:
                style_part = raw

        if not style_part:
            return "Regular"

        style_part = re.sub(
            r"(?i)(MT|PS|Std|Pro|BT|EF|OT|SC|Com|W[1-9])$", "", style_part
        ).strip(" -_")
        if not style_part:
            return "Regular"

        s = re.sub(r"([a-z])([A-Z])", r"\1 \2", style_part)
        s = re.sub(r"([A-Z]{2,})([A-Z][a-z])", r"\1 \2", s)
        tokens = [t.lower() for t in re.split(r"[\s_\-]+", s) if t]

        TK = {
            "italic": "Italic",
            "it": "Italic",
            "ita": "Italic",
            "oblique": "Oblique",
            "obl": "Oblique",
            "condensed": "Condensed",
            "cond": "Condensed",
            "narrow": "Narrow",
            "compressed": "Compressed",
            "extended": "Extended",
            "expanded": "Extended",
            "thin": "Thin",
            "hairline": "Thin",
            "light": "Light",
            "lt": "Light",
            "book": "Book",
            "roman": "Regular",
            "regular": "Regular",
            "medium": "Medium",
            "demi": "Semibold",
            "semibold": "Semibold",
            "bold": "Bold",
            "bd": "Bold",
            "black": "Black",
            "heavy": "Black",
        }
        NOISE = {"mt", "ps", "std", "pro", "bt", "ef", "ot", "sc", "com"}

        canonical = []
        for tok in tokens:
            if tok in NOISE:
                continue
            if tok in TK:
                canonical.append(TK[tok])
            else:
                canonical.append(tok.capitalize())

        if not canonical:
            return "Regular"

        order = {
            "Thin": 0,
            "Light": 1,
            "Book": 2,
            "Regular": 3,
            "Medium": 4,
            "Semibold": 5,
            "Bold": 6,
            "Black": 7,
        }
        weight_words = [w for w in canonical if w in order]
        style_words = [w for w in canonical if w not in order]

        if weight_words:
            weight_words.sort(key=lambda w: order.get(w, 99))
        if style_words:
            style_order = {
                "Italic": 0,
                "Oblique": 1,
                "Condensed": 2,
                "Narrow": 3,
                "Compressed": 4,
                "Extended": 5,
            }
            style_words.sort(key=lambda w: style_order.get(w, 99))

        result = " ".join(weight_words + style_words)
        return result if result else "Regular"

    def _update_font_style_list(self):
        """Actualiza la lista de estilos según la familia seleccionada."""
        if not self._font_style_list:
            return

        self._ensure_fonts_loaded()
        family = self.current_profile.font_family
        family_found = family in self.available_fonts
        available_styles = self.available_fonts.get(family, [])
        available_styles = list(
            dict.fromkeys(available_styles)
        )  # dedup igual que text_settings

        if not family_found:
            saved_style = self.current_profile.font_style or "Regular"
            tooltip_text = f"{family}: {saved_style}"
            self._font_style_list.content.controls = [
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Icon(
                                ft.Icons.WARNING_AMBER_OUTLINED,
                                size=14,
                                color="#cc8800",
                            ),
                            ft.Container(width=4),
                            ft.Text(
                                t("Fuente no instalada: {0}").format(family),
                                size=10,
                                color="#cc8800",
                                italic=True,
                                tooltip=tooltip_text,
                            ),
                        ]
                    ),
                    padding=ft.Padding.symmetric(horizontal=8, vertical=4),
                    bgcolor=FONDO_TEXTFIELDS_COLOR,
                    tooltip=tooltip_text,
                )
            ]
            if hasattr(self._font_style_list.content, "update"):
                self._font_style_list.content.update()
            self._font_style_list.update()
            return

        # Validar estilos instalados
        fam_statuses = {}
        try:
            from utils import font_index_wrapper as font_index

            fam_statuses = font_index.validate_cached_fonts(
                {family: available_styles}
            ).get(family, {})
        except Exception:
            pass

        # Mostrar el nombre raw del estilo (sin normalizar para evitar colapsos como Roman→Regular)
        controls = []
        hidden_count = 0
        hidden_styles = []
        for orig in available_styles:
            state = fam_statuses.get(orig, "installed")
            if state != "installed":
                hidden_count += 1
                hidden_styles.append(orig)
                continue
            is_selected = orig == self.current_profile.font_style
            row = ft.Row(
                [
                    ft.Text(orig, size=12, color=TEXTOS_FASE_1_COLOR,
                            weight=ft.FontWeight.BOLD if is_selected else ft.FontWeight.NORMAL),
                    ft.Container(width=6),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            )
            container = ft.Container(
                content=row,
                padding=ft.Padding.symmetric(horizontal=8, vertical=4),
                bgcolor=FONDO_CALCULO_FASE_1 if is_selected else FONDO_TEXTFIELDS_COLOR,
                data=orig,
                on_click=lambda e, s=orig: self._on_font_style_click(s),
            )
            controls.append(container)

        if hidden_count > 0:
            hidden_label = ", ".join(hidden_styles)
            tooltip_text = f"{family}: {hidden_label}"
            info = ft.Container(
                content=ft.Row(
                    [
                        ft.Icon(ft.Icons.INFO_OUTLINE, size=14, color="#888888"),
                        ft.Container(width=4),
                        ft.Text(
                            t(
                                "{0} estilo no disponible"
                                if hidden_count == 1
                                else "{0} estilos no disponibles"
                            ).format(hidden_count),
                            size=10,
                            color="#888888",
                            italic=True,
                            tooltip=tooltip_text,
                        ),
                    ]
                ),
                padding=ft.Padding.symmetric(horizontal=8, vertical=4),
                bgcolor=FONDO_TEXTFIELDS_COLOR,
                tooltip=tooltip_text,
            )
            controls.append(info)

        self._font_style_list.content.controls = controls
        if hasattr(self._font_style_list.content, "update"):
            self._font_style_list.content.update()
        self._font_style_list.update()

    def _on_font_family_change(self, family: str):
        """Callback cuando cambia la familia de fuente (misma lógica que TextStyleManager)."""
        self.current_profile.font_family = family
        self._ensure_fonts_loaded()

        available_styles = self.available_fonts.get(family, ["Regular"])

        # Validar estilos instalados
        try:
            from utils import font_index_wrapper as font_index

            fam_statuses = font_index.validate_cached_fonts(
                {family: available_styles}
            ).get(family, {})
            installed_styles = [
                s
                for s in available_styles
                if fam_statuses.get(s, "installed") == "installed"
            ]
            if not installed_styles:
                installed_styles = available_styles
            self.current_profile.font_style = (
                installed_styles[0] if installed_styles else "Regular"
            )
        except Exception:
            self.current_profile.font_style = (
                available_styles[0] if available_styles else "Regular"
            )

        # Resolver ruta de fuente + TTC + page.fonts + métricas
        try:
            from utils import font_index_wrapper as font_index
            from utils import pdf_generator

            font_path, status = font_index.find_font_file_for(
                family, self.current_profile.font_style
            )
            font_index_ttc = 0

            if font_path and status == "installed" and Path(font_path).exists():
                if font_path.lower().endswith(".ttc"):
                    try:
                        font_index_ttc = pdf_generator._get_ttc_font_index(
                            font_path, self.current_profile.font_style
                        )
                    except Exception:
                        font_index_ttc = 0
                    # Extraer TTC a TTF para Flet
                    try:
                        extracted_path = self.gestor.extraer_ttc_individual(
                            font_path, font_index_ttc
                        )
                        if extracted_path and extracted_path.exists():
                            font_path = str(extracted_path)
                            font_index_ttc = None
                            # Registrar en page.fonts
                            try:
                                gestor = self.gestor
                                familia_data = gestor.fuentes.get(family, {})
                                peso_encontrado = 400
                                italic_encontrado = False
                                for peso_key, italic_dict in familia_data.items():
                                    for italic_key, variante in italic_dict.items():
                                        if (
                                            variante.get("subfamilia")
                                            == self.current_profile.font_style
                                        ):
                                            peso_encontrado = variante.get("peso", 400)
                                            italic_encontrado = variante.get(
                                                "italic", False
                                            )
                                            break
                                alias = gestor.generar_alias_flet(
                                    family, peso_encontrado, italic_encontrado
                                )
                                if hasattr(self.page, "fonts"):
                                    if self.page.fonts is None:
                                        self.page.fonts = {}
                                    self.page.fonts[alias] = str(extracted_path)
                                    self.page.update()
                                    self.current_profile.resolved_flet_alias = alias
                            except Exception as reg_err:
                                print(f"[VAR_TEXT] Error registrando fuente: {reg_err}")
                    except Exception as e:
                        print(f"[VAR_TEXT] Error extrayendo TTC: {e}")
                else:
                    # TTF/OTF directa
                    try:
                        gestor = self.gestor
                        familia_data = gestor.fuentes.get(family, {})
                        peso_encontrado = 400
                        italic_encontrado = False
                        for peso_key, italic_dict in familia_data.items():
                            for italic_key, variante in italic_dict.items():
                                if (
                                    variante.get("subfamilia")
                                    == self.current_profile.font_style
                                ):
                                    peso_encontrado = variante.get("peso", 400)
                                    italic_encontrado = variante.get("italic", False)
                                    break
                        alias = gestor.generar_alias_flet(
                            family, peso_encontrado, italic_encontrado
                        )
                        if hasattr(self.page, "fonts"):
                            if self.page.fonts is None:
                                self.page.fonts = {}
                            self.page.fonts[alias] = str(font_path)
                            self.page.update()
                            self.current_profile.resolved_flet_alias = alias
                    except Exception as reg_err:
                        print(f"[VAR_TEXT] Error registrando TTF: {reg_err}")

                self.current_profile.resolved_font_path = font_path
                self.current_profile.resolved_font_index = font_index_ttc
                self.current_profile.resolved_status = status

                # Cargar métricas
                if hasattr(self, "font_metrics_cache") and self.font_metrics_cache:
                    try:
                        metric = self.font_metrics_cache.get_metrics(
                            str(font_path),
                            self.current_profile.font_size,
                            font_index_ttc,
                        )
                        if metric:
                            self.current_profile.metricas = metric.copy()
                    except Exception:
                        pass
            else:
                self.current_profile.resolved_font_path = None
                self.current_profile.resolved_font_index = 0
                self.current_profile.resolved_status = None
        except Exception as e:
            print(f"[VAR_TEXT] Error resolviendo fuente: {e}")
            self.current_profile.resolved_font_path = None
            self.current_profile.resolved_status = None

        self._update_font_family_list_selection()
        self._update_font_style_list()
        self._update_preview()
        self.page.update()

    def _on_refresh_fonts_click(self, e):
        """Recarga fuentes del sistema y re-resuelve perfiles."""
        self._refresh_system_fonts(force_reload=True)
        # Reconstruir la lista de familias
        if self._font_family_listview and self.available_fonts:
            font_families = sorted(self.available_fonts.keys(), key=str.lower)
            _sel = self.current_profile.font_family
            self._font_family_listview.controls = [
                ft.Container(
                    content=ft.Text(
                        family, size=12, color=TEXTOS_FASE_1_COLOR,
                        weight=ft.FontWeight.BOLD if family == _sel else ft.FontWeight.NORMAL,
                    ),
                    padding=ft.Padding.symmetric(horizontal=8, vertical=4),
                    bgcolor=(
                        FONDO_CALCULO_FASE_1
                        if family == _sel
                        else FONDO_TEXTFIELDS_COLOR
                    ),
                    on_click=lambda e, f=family: self._on_font_family_change(f),
                    key=f"font_family_{family}",
                    height=25,
                )
                for family in font_families
            ]
            self._font_family_listview.update()
        self._update_font_style_list()
        self.page.update()

    def _on_font_style_click(self, style_name: str):
        self.current_profile.font_style = style_name

        # Resolver ruta de fuente para el nuevo estilo (replica text_settings_dialog)
        try:
            from utils import font_index_wrapper as font_index
            from utils import pdf_generator

            family = self.current_profile.font_family
            font_path, status = font_index.find_font_file_for(family, style_name)
            font_index_ttc = 0

            if font_path and status == "installed" and Path(font_path).exists():
                if font_path.lower().endswith(".ttc"):
                    try:
                        font_index_ttc = pdf_generator._get_ttc_font_index(
                            font_path, style_name
                        )
                    except Exception:
                        font_index_ttc = 0
                    try:
                        extracted_path = self.gestor.extraer_ttc_individual(
                            font_path, font_index_ttc
                        )
                        if extracted_path and extracted_path.exists():
                            font_path = str(extracted_path)
                            font_index_ttc = None
                            try:
                                gestor = self.gestor
                                familia_data = gestor.fuentes.get(family, {})
                                peso_encontrado = 400
                                italic_encontrado = False
                                for peso_key, italic_dict in familia_data.items():
                                    for italic_key, variante in italic_dict.items():
                                        if variante.get("subfamilia") == style_name:
                                            peso_encontrado = variante.get("peso", 400)
                                            italic_encontrado = variante.get(
                                                "italic", False
                                            )
                                            break
                                alias = gestor.generar_alias_flet(
                                    family, peso_encontrado, italic_encontrado
                                )
                                if hasattr(self.page, "fonts"):
                                    if self.page.fonts is None:
                                        self.page.fonts = {}
                                    self.page.fonts[alias] = str(extracted_path)
                                    self.page.update()
                                    self.current_profile.resolved_flet_alias = alias
                            except Exception:
                                pass
                    except Exception:
                        pass
                else:
                    try:
                        gestor = self.gestor
                        familia_data = gestor.fuentes.get(family, {})
                        peso_encontrado = 400
                        italic_encontrado = False
                        for peso_key, italic_dict in familia_data.items():
                            for italic_key, variante in italic_dict.items():
                                if variante.get("subfamilia") == style_name:
                                    peso_encontrado = variante.get("peso", 400)
                                    italic_encontrado = variante.get("italic", False)
                                    break
                        alias = gestor.generar_alias_flet(
                            family, peso_encontrado, italic_encontrado
                        )
                        if hasattr(self.page, "fonts"):
                            if self.page.fonts is None:
                                self.page.fonts = {}
                            self.page.fonts[alias] = str(font_path)
                            self.page.update()
                            self.current_profile.resolved_flet_alias = alias
                    except Exception:
                        pass

                self.current_profile.resolved_font_path = font_path
                self.current_profile.resolved_font_index = font_index_ttc
                self.current_profile.resolved_status = status

                if hasattr(self, "font_metrics_cache") and self.font_metrics_cache:
                    try:
                        metric = self.font_metrics_cache.get_metrics(
                            str(font_path),
                            self.current_profile.font_size,
                            font_index_ttc,
                        )
                        if metric:
                            self.current_profile.metricas = metric.copy()
                    except Exception:
                        pass
        except Exception:
            pass

        self._update_font_style_list()
        self._update_preview()
        self.page.update()

    def _update_font_family_list_selection(self):
        """Actualiza la selección visual en la lista de familias (replica text_settings_dialog)."""
        if not self._font_family_list or not hasattr(self._font_family_list, "content"):
            return
        for item in self._font_family_list.content.controls:
            if isinstance(item, ft.Container) and isinstance(item.content, ft.Text):
                is_selected = item.content.value == self.current_profile.font_family
                item.bgcolor = (
                    FONDO_CALCULO_FASE_1 if is_selected else FONDO_TEXTFIELDS_COLOR
                )
                item.content.weight = (
                    ft.FontWeight.BOLD if is_selected else ft.FontWeight.NORMAL
                )
                item.update()

    # ------------------------------------------------------------------
    # Compact dropdown helper
    # ------------------------------------------------------------------
    def _create_compact_dropdown(
        self, options, value, width=140, height=20, on_change=None, text_size=11
    ):
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
    # Increment buttons (replica exacta de text_settings_dialog)
    # ------------------------------------------------------------------
    def _create_increment_buttons(
        self, field: ft.TextField, on_change_callback
    ) -> ft.Column:
        """Crea botones de incrementar/decrementar para un campo numérico"""

        def increment(e):
            try:
                current = float(field.value)
                field.value = str(current + 1)
                field.update()
                if on_change_callback:

                    class FakeEvent:
                        def __init__(self, control):
                            self.control = control

                    on_change_callback(FakeEvent(field))
            except:
                pass

        def decrement(e):
            try:
                current = float(field.value)
                field.value = str(current - 1)
                field.update()
                if on_change_callback:

                    class FakeEvent:
                        def __init__(self, control):
                            self.control = control

                    on_change_callback(FakeEvent(field))
            except:
                pass

        return ft.Column(
            [
                ft.IconButton(
                    icon=ft.Icons.ARROW_DROP_UP,
                    icon_size=16,
                    width=20,
                    height=20,
                    padding=0,
                    on_click=increment,
                    icon_color=TEXTO_COLOR_GENERICO,
                ),
                ft.IconButton(
                    icon=ft.Icons.ARROW_DROP_DOWN,
                    icon_size=16,
                    width=20,
                    height=20,
                    padding=0,
                    on_click=decrement,
                    icon_color=TEXTO_COLOR_GENERICO,
                ),
            ],
            spacing=0,
            tight=True,
        )

    # ------------------------------------------------------------------
    # Section wrapper
    # ------------------------------------------------------------------
    def _make_section(self, title, controls, width=None):
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
    # Profile management
    # ------------------------------------------------------------------
    def _create_profile_list_item(self, index, profile):
        is_selected = index == self.selected_profile_index
        bg = FONDO_CALCULO_FASE_1 if is_selected else None
        border_c = BOTONES_GENERICOS_COLOR if is_selected else BORDE_TEXTFIELDS_COLOR

        name_text = ft.Text(
            profile.name, size=12, color=TEXTO_COLOR_GENERICO, no_wrap=True, expand=True,
        )

        def on_tap(e, idx=index):
            self._save_current_profile()
            self._select_profile(idx)

        def on_double_tap(e, idx=index):
            if self.profiles[idx].name != "<Default>":
                self._rename_profile(idx)

        return ft.GestureDetector(
            content=ft.Container(
                content=ft.Row(
                    [name_text],
                    alignment=ft.MainAxisAlignment.START,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                padding=ft.Padding.symmetric(horizontal=8, vertical=4),
                border_radius=4,
                bgcolor=bg,
                border=ft.Border.all(1, border_c),
            ),
            on_tap=on_tap,
            on_double_tap=on_double_tap,
        )

    def _update_profile_list(self):
        if not self.profile_list:
            return
        self.profile_list.controls = [
            self._create_profile_list_item(i, p) for i, p in enumerate(self.profiles)
        ]

    def _select_profile(self, index):
        if index == self.selected_profile_index:
            return
        self.selected_profile_index = index
        self.current_profile = self.profiles[index].copy()
        self._load_profile_to_ui()
        self._update_profile_list()
        self._update_preview()
        self.page.update()

    def _save_current_profile(self):
        if self.current_profile:
            self.profiles[self.selected_profile_index] = self.current_profile.copy()

    def _rename_profile(self, index):
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
            counter += 1
            new_name = f"{base_name} {counter}"

        new_profile = self.current_profile.copy()
        new_profile.id = str(uuid.uuid4())
        new_profile.name = new_name

        self.profiles.append(new_profile)
        self.selected_profile_index = len(self.profiles) - 1
        self.current_profile = new_profile.copy()
        self._update_profile_list()
        self._load_profile_to_ui()
        self._update_preview()
        if self.on_profile_changed:
            self.on_profile_changed(self.current_profile)
        self.page.update()

    def _delete_profile(self, e):
        if self.profiles[self.selected_profile_index].name == "<Default>":
            return
        if len(self.profiles) <= 1:
            return

        def on_confirm_delete(ev):
            if popup_container in self.dialog_root_stack.controls:
                self.dialog_root_stack.controls.remove(popup_container)
            self.dialog_root_stack.update()
            del self.profiles[self.selected_profile_index]
            if self.selected_profile_index >= len(self.profiles):
                self.selected_profile_index = len(self.profiles) - 1
            self.current_profile = self.profiles[self.selected_profile_index].copy()
            self._update_profile_list()
            self._load_profile_to_ui()
            self._update_preview()
            self.page.update()

        def on_cancel_delete(ev):
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
                            t("Eliminar perfil"),
                            weight=ft.FontWeight.BOLD,
                            size=18,
                            color=TEXTO_COLOR_GENERICO,
                        ),
                        alignment=ft.Alignment.CENTER,
                    ),
                    ft.Container(height=10),
                    ft.Text(
                        t("Seguro que quieres eliminar este perfil?"),
                        color=TEXTO_COLOR_GENERICO,
                    ),
                    ft.Container(height=15),
                    ft.Row(
                        [
                            ft.Button(
                                t("Cancelar"),
                                on_click=on_cancel_delete,
                                width=110,
                                bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
                                style=_btn_style,
                            ),
                            ft.Button(
                                t("Eliminar"),
                                on_click=on_confirm_delete,
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
        self._update_font_family_list_selection()
        self._update_font_style_list()
        if self._font_size_field:
            self._font_size_field.value = f"{p.font_size:.1f}"
        if self._line_spacing_field:
            self._line_spacing_field.value = _fmt_pt(p.line_spacing)
        if self._letter_spacing_field:
            self._letter_spacing_field.value = _fmt_pt(p.letter_spacing)
        if self._text_alignment_dropdown:
            dd = self._text_alignment_dropdown.content.controls[0]
            for opt in TEXT_ALIGN_OPTIONS:
                if opt[0] == p.text_alignment:
                    dd.value = str(opt[1])
                    dd.data = p.text_alignment
                    break
        if self._text_color_swatch:
            self._text_color_swatch.bgcolor = self._tinted_display_color(
                p.text_color, p.text_color_tint, p.text_color_space
            )

        # Visibilidad origen de datos
        if self._value_source_dropdown:
            dd = self._value_source_dropdown.content.controls[0]
            for opt in VALUE_SOURCE_OPTIONS:
                if opt[0] == p.value_source:
                    dd.value = str(opt[1])
                    dd.data = p.value_source
                    break
        if self._text_case_filter_dropdown:
            self._text_case_filter_dropdown.visible = p.value_source == "excel"
        if self._preview_row_nav:
            self._preview_row_nav.visible = p.value_source == "excel"
            start_row = (
                self._pending_initial_row
                if self._pending_initial_row is not None
                else 0
            )
            self._pending_initial_row = None
            self._set_preview_row(start_row, update=False)
            dd = self._text_case_filter_dropdown.content.controls[0]
            dd.value = t(dd.data) if dd.data else t("Sin filtro")
            for opt in TEXT_CASE_FILTER_OPTIONS:
                if opt[0] == p.text_case_filter:
                    dd.value = opt[1] if isinstance(opt, tuple) else opt
                    dd.data = p.text_case_filter
                    break
            try:
                self._text_case_filter_dropdown.update()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Preview
    # ------------------------------------------------------------------
    def _build_preview_text(self):
        p = self.current_profile
        text = resolve_vt_text(
            p.sample_text,
            value_source=p.value_source,
            excel_manager=self.excel_manager,
            row_index=0,
            text_case_filter=p.text_case_filter,
        )
        if p.value_source == "excel" and not self.excel_manager:
            text = p.sample_text
        return text

    def _preview_row_count(self) -> int:
        if self.excel_manager and self.excel_manager.is_loaded:
            return max(0, int(self.excel_manager.row_count))
        return 0

    def set_initial_row(self, row_index: Optional[int]):
        """Fila (0-based) de la que parte el diálogo al abrirse (sync main→diálogo)."""
        self._pending_initial_row = max(0, row_index) if isinstance(row_index, int) else None

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
        """Sincroniza en vivo la página del main con la fila seleccionada (solo datos externos)."""
        if (
            self.on_row_change
            and self.current_profile.value_source == "excel"
            and self._preview_row_count() > 0
        ):
            try:
                self.on_row_change(self._preview_row_index + 1)
            except Exception:
                pass

    def _on_preview_row_field_submit(self):
        count = self._preview_row_count()
        try:
            val = int((self._preview_row_counter.value or "1").strip())
        except ValueError:
            val = 1
        self._set_preview_row(val - 1 if count > 0 else 0)

    def _update_preview(self):
        if not self._preview_text:
            return
        p = self.current_profile
        font_family_to_use = getattr(p, "resolved_flet_alias", None) or p.font_family
        style_lower = p.font_style.lower()
        bold = ft.FontWeight.BOLD if "bold" in style_lower else ft.FontWeight.NORMAL
        italic = "italic" in style_lower or "oblique" in style_lower
        align_map = {
            "izquierda": ft.TextAlign.LEFT,
            "centro": ft.TextAlign.CENTER,
            "derecha": ft.TextAlign.RIGHT,
        }

        if p.value_source == "sample":
            try:
                text_body = resolve_vt_text(
                    p.sample_text,
                    value_source="sample",
                    excel_manager=self.excel_manager,
                    row_index=self._preview_row_index,
                    text_case_filter=p.text_case_filter,
                )
            except Exception:
                text_body = p.sample_text
        elif p.value_source == "excel":
            try:
                text_body = resolve_vt_text(
                    p.sample_text,
                    value_source="excel",
                    excel_manager=self.excel_manager,
                    row_index=self._preview_row_index,
                    text_case_filter=p.text_case_filter,
                )
            except Exception:
                text_body = t("(sin datos)")
        else:
            text_body = t("(sin datos)")

        # Preview con el MISMO motor que el visor y el PDF (render_vt_image_b64):
        # tinta PIL real sobre la fuente resuelta, mismo grid de baselines de
        # measure_vt_box. El ft.Text queda como fallback sin fuente resuelta.
        display_hex = self._tinted_display_color(
            p.text_color, p.text_color_tint, p.text_color_space
        )
        b64 = ""
        try:
            b64, w_pt, h_pt, _bl = render_vt_image_b64(
                text_body.split("\n"),
                getattr(p, "resolved_font_path", None) or "",
                float(p.font_size or 12.0),
                line_spacing_pt=float(p.line_spacing or 0.0),
                letter_spacing_pt=float(getattr(p, "letter_spacing", 0.0) or 0.0),
                text_alignment=getattr(p, "text_alignment", "izquierda"),
                text_color=_vt_hex_to_rgb(display_hex),
            )
        except Exception:
            b64 = ""

        if b64:
            self._preview_image.src = b64
            self._preview_image.width = max(1.0, float(w_pt))
            self._preview_image.height = max(1.0, float(h_pt))
            self._preview_image.visible = True
            self._preview_text.visible = False
            if _safe_page(self._preview_text):
                self._preview_image.update()
                self._preview_text.update()
            return

        # Fallback Flutter (motor aproximado): camino legacy intacto.
        self._preview_image.visible = False
        self._preview_text.visible = True
        line_height_ratio = self._preview_line_height_ratio(p)

        # Preview idéntico al playground (flet_interlineado_test.py): value +
        # color en el widget + style con height y size juntos. Sin spans.
        self._preview_text.value = text_body
        self._preview_text.spans = []
        self._preview_text.color = self._tinted_display_color(
            p.text_color, p.text_color_tint, p.text_color_space
        )
        self._preview_text.style = ft.TextStyle(
            height=line_height_ratio,
            size=float(p.font_size or 12.0),
            letter_spacing=float(getattr(p, "letter_spacing", 0.0) or 0.0),
        )
        self._preview_text.font_family = font_family_to_use
        self._preview_text.weight = bold
        self._preview_text.italic = italic
        self._preview_text.text_align = align_map.get(getattr(p, "text_alignment", "izquierda"), ft.TextAlign.LEFT)
        self._preview_text.width = None
        if _safe_page(self._preview_text):
            self._preview_text.update()

    def _preview_line_height_ratio(self, p):
        # height = inter / cuerpo (igual que el playground). Floor no-cero:
        # Flutter trata height == 0.0 como "auto" (leading default de la fuente),
        # no como líneas montadas → a 0 saltaba al interlineado por defecto.
        cuerpo = float(p.font_size or 12.0)
        return max(float(p.line_spacing or 0.0) / cuerpo, 0.01)

    # ------------------------------------------------------------------
    # Color pickers
    # ------------------------------------------------------------------
    def _open_text_color_picker(self, e):
        p = self.current_profile
        self._color_target = "text_color"
        # El padre queda abierto debajo (el picker se apila encima) — no pop_dialog
        self.color_picker_dialog.open(
            p.text_color,
            p.text_color_cmyk,
            p.text_color_space,
            p.text_color_name,
            p.text_color_tint,
        )

    def _reopen_settings_dialog(self):
        """Reabre el diálogo de ajustes después de cerrar el color picker."""
        reopen_dialog(self.page, self.dialog)

    def _tinted_display_color(
        self, base_hex: str, tint_pct: float, color_space: str
    ) -> str:
        from ui.color_picker import hex2rgb
        if color_space != "SPOT" or tint_pct >= 99.9:
            return base_hex
        try:
            r0, g0, b0 = hex2rgb(base_hex)
            t = max(0.0, min(100.0, float(tint_pct))) / 100.0
            r = max(0, min(255, int(round(255 + (r0 - 255) * t))))
            g = max(0, min(255, int(round(255 + (g0 - 255) * t))))
            b = max(0, min(255, int(round(255 + (b0 - 255) * t))))
            return f"#{r:02x}{g:02x}{b:02x}"
        except Exception:
            return base_hex

    def _on_color_picker_selected(
        self,
        rgb_color: str,
        cmyk_color: tuple,
        color_space: str,
        color_name: str = "",
        tint: float = 100.0,
    ):
        p = self.current_profile
        display_color = self._tinted_display_color(rgb_color, tint, color_space)
        if self._color_target == "text_color":
            p.text_color = rgb_color
            p.text_color_cmyk = cmyk_color
            p.text_color_space = color_space
            p.text_color_name = color_name
            p.text_color_tint = tint
            if self._text_color_swatch:
                self._text_color_swatch.bgcolor = display_color
        self._update_preview()

    def set_extracted_spots(self, spots: list):
        self.extracted_spot_colors = spots or []
        if self.color_picker_dialog is not None:
            self.color_picker_dialog.set_extracted_spots(self.extracted_spot_colors)

    # ------------------------------------------------------------------
    # Preferences
    # ------------------------------------------------------------------
    def save_to_preferences(self):
        profiles_data = []
        for p in self.profiles:
            d = p.to_dict()
            if d.get("value_source") == "excel":
                d["value_source"] = "sample"
                d["excel_column"] = ""
            profiles_data.append(d)
        save_variable_text_profiles(profiles_data)

    def load_from_preferences(self):
        data_list = get_variable_text_profiles()
        if not data_list:
            self.profiles = [VariableTextProfile.create_default()]
        else:
            self.profiles = []
            seen_names = set()
            for d in data_list:
                try:
                    profile = VariableTextProfile.from_dict(d)
                    if profile.name in seen_names:
                        base = profile.name
                        counter = 2
                        while profile.name in seen_names:
                            profile.name = f"{base} ({counter})"
                            counter += 1
                    seen_names.add(profile.name)
                    self.profiles.append(profile)
                except Exception:
                    continue
        if not self.profiles:
            self.profiles = [VariableTextProfile.create_default()]
        self.selected_profile_index = 0
        self.current_profile = self.profiles[0].copy()

    def get_profiles(self):
        return self.profiles

    def set_excel_columns(self, columns: List[str]):
        self._excel_columns = columns

    # ------------------------------------------------------------------
    # Open dialog
    # ------------------------------------------------------------------
    def open(self):
        try:
            if self.gestor and self.gestor.check_font_system_changed():
                print("[VAR_TEXT] Cambios detectados, refrescando fuentes...")
                self._refresh_system_fonts()
            else:
                pass  # ponytail: skip noisy "no changes" log
        except Exception as e:
            print(f"[VAR_TEXT] Error refrescando fuentes al abrir: {e}")
            if not self.available_fonts:
                self.available_fonts = self._load_system_fonts()

        # Re-sincronizar current_profile con el perfil ya resuelto: _refresh_system_fonts
        # mutó profiles[i] (resolved_flet_alias, page.fonts) pero no la copia que se
        # tomó en open_variable_text_dialog antes de _resolve_profiles().
        # SOLO resolved_* si la copia viene stale — no re-copy completo (font_family
        # puede estar fuera de available_fonts → "Fuente no instalada").
        if 0 <= self.selected_profile_index < len(self.profiles):
            src = self.profiles[self.selected_profile_index]
            for _attr in (
                "resolved_font_path",
                "resolved_font_index",
                "resolved_status",
                "resolved_flet_alias",
                "metricas",
            ):
                if hasattr(src, _attr):
                    setattr(self.current_profile, _attr, getattr(src, _attr))

        # Inicializar ColorPickerDialog (una sola vez, mismo patrón que TextStyleManager)
        if self.color_picker_dialog is None:
            self.color_picker_dialog = ColorPickerDialog(
                page=self.page,
                on_color_selected=self._on_color_picker_selected,
                on_dismissed=self._reopen_settings_dialog,
            )
            if self.extracted_spot_colors:
                self.color_picker_dialog.set_extracted_spots(self.extracted_spot_colors)

        # Panel izquierdo
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
        self.btn_refresh_fonts = ft.IconButton(
            icon=ft.Icons.REFRESH,
            tooltip=t("Recargar fuentes del sistema"),
            icon_size=20,
            icon_color=TEXTO_COLOR_GENERICO,
            on_click=self._on_refresh_fonts_click,
        )
        self.profile_list = ft.ListView(
            controls=[
                self._create_profile_list_item(i, p)
                for i, p in enumerate(self.profiles)
            ],
            spacing=0,
            expand=True,
        )

        self._line_spacing_reset = ft.IconButton(
            icon=ft.Icons.RESTART_ALT,
            icon_size=14,
            width=18,
            height=18,
            padding=0,
            tooltip=t("Restablecer interlineado"),
            on_click=self._on_line_spacing_reset,
            icon_color=TEXTO_COLOR_GENERICO,
        )


        self._text_color_swatch = ft.Container(
            width=40,
            height=40,
            bgcolor=self._tinted_display_color(
                self.current_profile.text_color,
                self.current_profile.text_color_tint,
                self.current_profile.text_color_space,
            ),
            border_radius=4,
            border=ft.Border.all(2, BORDE_TEXTFIELDS_COLOR),
            on_click=self._open_text_color_picker,
            ink=True,
            tooltip=t("Color del texto"),
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
                                spacing=4,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.Divider(height=1, color=BORDE_TEXTFIELDS_COLOR),
                    self.profile_list,
                    ft.Divider(height=1, color=BORDE_TEXTFIELDS_COLOR),
                    ft.Column(
                        [
                            ft.Text(
                                t("Color Texto"), size=11, color=TEXTOS_FASE_1_COLOR
                            ),
                            self._text_color_swatch,
                        ],
                        spacing=4,
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

        # Seccion 1: Fuente (replica exacta de text_settings_dialog)
        font_families = sorted(self.available_fonts.keys(), key=str.lower)

        _sel = self.current_profile.font_family
        self._font_family_listview = ft.ListView(
            controls=[
                ft.Container(
                    content=ft.Text(
                        family, size=12, color=TEXTOS_FASE_1_COLOR,
                        weight=ft.FontWeight.BOLD if family == _sel else ft.FontWeight.NORMAL,
                    ),
                    padding=ft.Padding.symmetric(horizontal=8, vertical=4),
                    bgcolor=(
                        FONDO_CALCULO_FASE_1
                        if family == _sel
                        else FONDO_TEXTFIELDS_COLOR
                    ),
                    on_click=lambda e, f=family: self._on_font_family_change(f),
                    key=f"font_family_{family}",
                    height=25,
                )
                for family in font_families
            ],
            spacing=0,
        )
        self._font_family_list = ft.Container(
            content=self._font_family_listview,
            height=140,
            bgcolor=FONDO_TEXTFIELDS_COLOR,
        )

        self._font_style_list = ft.Container(
            content=ft.ListView(controls=[], spacing=0),
            height=140,
            bgcolor=FONDO_TEXTFIELDS_COLOR,
        )

        self._font_size_field = ft.TextField(
            value=f"{self.current_profile.font_size:.1f}",
            width=70,
            height=28,
            text_size=11,
            content_padding=ft.Padding(2, 0, 6, 0),
            filled=True,
            fill_color=FONDO_TEXTFIELDS_COLOR,
            text_style=ft.TextStyle(color=TEXTO_COLOR_GENERICO),
            on_change=self._on_font_size_change,border=ft.OutlineInputBorder(border_radius=3, side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)))

        self._text_alignment_dropdown = self._create_compact_dropdown(
            options=TEXT_ALIGN_OPTIONS,
            value=self.current_profile.text_alignment,
            width=110,
            height=28,
            text_size=11,
            on_change=self._on_text_alignment_changed,
        )

        self._line_spacing_field = ft.TextField(
            value=f"{self.current_profile.line_spacing:.2f}".rstrip("0").rstrip(".")
            if self.current_profile.line_spacing != int(self.current_profile.line_spacing)
            else f"{self.current_profile.line_spacing:.0f}",
            width=45,
            height=28,
            text_size=11,
            content_padding=ft.Padding(6, 0, 6, 0),
            filled=True,
            fill_color=FONDO_TEXTFIELDS_COLOR,
            text_style=ft.TextStyle(color=TEXTO_COLOR_GENERICO),
            on_change=self._on_line_spacing_change,border=ft.OutlineInputBorder(border_radius=4, side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)))

        def _ls_arrow(delta):
            def on_click(e):
                # Fuente de verdad = perfil (siempre float >= 0), no el campo
                # (Flet puede devolver None/""/stale tras update()). Igual que el
                # playground: clamp max(0.0, ...) → nunca puede bajar de 0 ni saltar.
                new_val = max(
                    0.0, round((self.current_profile.line_spacing or 0.0) + delta, 1)
                )
                self._line_spacing_field.value = (
                    f"{new_val:.1f}"
                    if new_val != int(new_val)
                    else str(int(new_val))
                )
                self._line_spacing_field.update()
                self._on_line_spacing_change(
                    type("_e", (), {"control": self._line_spacing_field})()
                )
            return on_click

        self._line_spacing_arrows = ft.Column(
            [
                ft.IconButton(
                    icon=ft.Icons.ARROW_DROP_UP,
                    icon_size=12,
                    width=14,
                    height=14,
                    padding=0,
                    on_click=_ls_arrow(0.5),
                    icon_color=TEXTO_COLOR_GENERICO,
                ),
                ft.IconButton(
                    icon=ft.Icons.ARROW_DROP_DOWN,
                    icon_size=12,
                    width=14,
                    height=14,
                    padding=0,
                    on_click=_ls_arrow(-0.5),
                    icon_color=TEXTO_COLOR_GENERICO,
                ),
            ],
            spacing=0,
            tight=True,
        )

        self._letter_spacing_field = ft.TextField(
            value=_fmt_pt(self.current_profile.letter_spacing),
            width=45,
            height=28,
            text_size=11,
            content_padding=ft.Padding(6, 0, 6, 0),
            filled=True,
            fill_color=FONDO_TEXTFIELDS_COLOR,
            text_style=ft.TextStyle(color=TEXTO_COLOR_GENERICO),
            on_change=self._on_letter_spacing_change,border=ft.OutlineInputBorder(border_radius=4, side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)))

        def _ls_arrow(delta):
            def on_click(e):
                # Fuente de verdad = perfil (siempre float >= 0), no el campo
                # (Flet puede devolver None/""/stale tras update()).
                new_val = round((self.current_profile.letter_spacing or 0.0) + delta, 1)
                self._letter_spacing_field.value = _fmt_pt(new_val)
                self._letter_spacing_field.update()
                self._on_letter_spacing_change(
                    type("_e", (), {"control": self._letter_spacing_field})()
                )
            return on_click

        self._letter_spacing_arrows = ft.Column(
            [
                ft.IconButton(
                    icon=ft.Icons.ARROW_DROP_UP,
                    icon_size=12,
                    width=14,
                    height=14,
                    padding=0,
                    on_click=_ls_arrow(0.1),
                    icon_color=TEXTO_COLOR_GENERICO,
                ),
                ft.IconButton(
                    icon=ft.Icons.ARROW_DROP_DOWN,
                    icon_size=12,
                    width=14,
                    height=14,
                    padding=0,
                    on_click=_ls_arrow(-0.1),
                    icon_color=TEXTO_COLOR_GENERICO,
                ),
            ],
            spacing=0,
            tight=True,
        )

        section_tipografia = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text(
                                t("Fuente"),
                                size=14,
                                weight=ft.FontWeight.BOLD,
                                color=TEXTO_COLOR_GENERICO,
                            ),
                            self.btn_refresh_fonts,
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.Divider(height=1, color=BORDE_TEXTFIELDS_COLOR),
                    ft.Row(
                        [
                            ft.Column(
                                [
                                    ft.Text(
                                        t("Familia"),
                                        size=13,
                                        weight=ft.FontWeight.BOLD,
                                        color=TEXTO_COLOR_GENERICO,
                                    ),
                                    self._font_family_list,
                                ],
                                spacing=4,
                                expand=True,
                            ),
                            ft.Column(
                                [
                                    ft.Text(
                                        t("Estilo"),
                                        size=13,
                                        weight=ft.FontWeight.BOLD,
                                        color=TEXTO_COLOR_GENERICO,
                                    ),
                                    self._font_style_list,
                                ],
                                spacing=4,
                                expand=True,
                            ),
                        ],
                        spacing=10,
                    ),
                    ft.Row(
                        [
                            ft.Text(
                                t("Cuerpo:"), size=12, color=TEXTOS_FASE_1_COLOR
                            ),
                            self._font_size_field,
                            self._create_increment_buttons(
                                self._font_size_field, self._on_font_size_change
                            ),
                            ft.Text(
                                t("Interletraje:"), size=12, color=TEXTOS_FASE_1_COLOR
                            ),
                            self._letter_spacing_field,
                            self._letter_spacing_arrows,
                            ft.Text(
                                t("Interlineado:"), size=12, color=TEXTOS_FASE_1_COLOR
                            ),
                            self._line_spacing_field,
                            self._line_spacing_arrows,
                            self._line_spacing_reset,
                            ft.Text(
                                t("Alineación:"), size=12, color=TEXTOS_FASE_1_COLOR
                            ),
                            self._text_alignment_dropdown,
                        ],
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                ],
                spacing=6,
                tight=True,
            ),
            padding=ft.Padding.all(4),
            bgcolor=FONDO_SECCIONES,
            border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
            border_radius=8,
        )

        # Seccion 2: Origen de datos
        self._value_source_dropdown = self._create_compact_dropdown(
            options=VALUE_SOURCE_OPTIONS,
            value=self.current_profile.value_source,
            width=200,
            height=28,
            text_size=11,
            on_change=self._update_value_source_dropdown,
        )
        self._text_case_filter_dropdown = self._create_compact_dropdown(
            options=TEXT_CASE_FILTER_OPTIONS,
            value=self.current_profile.text_case_filter,
            width=160,
            height=28,
            text_size=11,
            on_change=self._on_text_case_filter_changed,
        )
        self._text_case_filter_dropdown.visible = (
            self.current_profile.value_source == "excel"
        )

        self._btn_open_editor = ft.Button(
            t("Editor de datos"),
            on_click=self._open_vt_editor,
            width=150,
            height=30,
            bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
            style=ft.ButtonStyle(
                color={
                    ft.ControlState.DEFAULT: BOTONES_GENERICOS_COLOR,
                    "hovered": BOTONES_GENERICOS_HOVER_COLOR,
                },
                overlay_color=BOTONES_GENERICOS_OVERLAY_COLOR,
                padding=ft.Padding(0, 0, 0, 0),
                shape=ft.RoundedRectangleBorder(radius=10),
                text_style=ft.TextStyle(size=12),
            ),
        )

        section_origen = self._make_section(
            t("Origen de datos"),
            [
                ft.Row(
                    [
                        ft.Text(
                            t("Origen:"), size=12, color=TEXTOS_FASE_1_COLOR, width=70
                        ),
                        self._value_source_dropdown,
                        self._text_case_filter_dropdown,
                        self._btn_open_editor,
                    ],
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ],
        )

        # Seccion 3: Preview
        align_map = {
            "izquierda": ft.TextAlign.LEFT,
            "centro": ft.TextAlign.CENTER,
            "derecha": ft.TextAlign.RIGHT,
        }
        profile_align = getattr(
            self.current_profile, "text_alignment", "izquierda"
        )
        self._preview_text = ft.Text(
            value="",
            font_family=self.current_profile.font_family,
            text_align=align_map.get(profile_align, ft.TextAlign.LEFT),
            selectable=True,
        )
        # Preview PIL (misma fórmula que visor/PDF); alterna visibilidad con
        # _preview_text según haya fuente resuelta.
        self._preview_image = ft.Image(src="", visible=False, fit=ft.BoxFit.CONTAIN)
        preview_container = ft.Container(
            content=ft.Column(
                [self._preview_text, self._preview_image],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                tight=True,
                spacing=0,
            ),
            expand=True,
            alignment=ft.Alignment.CENTER,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
            border_radius=4,
            padding=12,
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

        def _on_preview_row_prev(e):
            self._set_preview_row(self._preview_row_index - 1)

        def _on_preview_row_next(e):
            self._set_preview_row(self._preview_row_index + 1)

        def _go_to_extreme_row(want_max):
            p = self.current_profile
            count = self._preview_row_count()
            if count < 1:
                return
            font_path = getattr(p, "resolved_font_path", None) or ""
            font_size = float(getattr(p, "font_size", 12.0) or 12.0)
            row = find_extreme_row(
                count,
                lambda i: resolve_vt_text(
                    p.sample_text,
                    value_source="excel",
                    excel_manager=self.excel_manager,
                    row_index=i,
                    text_case_filter=p.text_case_filter,
                ),
                font_path,
                font_size,
                want_max=want_max,
            )
            self._set_preview_row(row)

        def _on_preview_row_longest(e):
            _go_to_extreme_row(want_max=True)

        def _on_preview_row_shortest(e):
            _go_to_extreme_row(want_max=False)

        self._preview_row_prev = _row_nav_btn(
            ft.Icons.CHEVRON_LEFT, "Fila anterior", _on_preview_row_prev
        )
        self._preview_row_next = _row_nav_btn(
            ft.Icons.CHEVRON_RIGHT, "Fila siguiente", _on_preview_row_next
        )
        self._preview_row_longest = _row_nav_text_btn(
            t("Fila más ancha"), "Fila más ancha", _on_preview_row_longest
        )
        self._preview_row_shortest = _row_nav_text_btn(
            t("Fila más corta"), "Fila más corta", _on_preview_row_shortest
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
            visible=self.current_profile.value_source == "excel",
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
                            self._preview_row_nav,
                        ],
                        spacing=10,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.Divider(height=1, color=BORDE_TEXTFIELDS_COLOR),
                    preview_container,
                ],
                spacing=6,
                expand=True,
            ),
            bgcolor=FONDO_SECCIONES,
            border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
            border_radius=4,
            padding=ft.Padding.all(8),
        )

        right_panel = ft.Column(
            [
                section_tipografia,
                section_origen,
                section_preview,
            ],
            spacing=10,
            expand=True,
        )

        base_content = ft.Container(
            content=ft.Row(
                [
                    left_panel,
                    ft.Container(content=right_panel, expand=True),
                ],
                spacing=15,
                vertical_alignment=ft.CrossAxisAlignment.STRETCH,
            ),
            width=1250,
            height=700,
        )

        self.dialog_root_stack = ft.Stack(
            controls=[base_content], width=1250, height=700
        )

        def on_cancel(e):
            try:
                old = self.profiles[self.selected_profile_index]
                new = self.current_profile.copy()
                if not getattr(new, "resolved_flet_alias", None) and getattr(
                    old, "resolved_flet_alias", None
                ):
                    for _attr in (
                        "resolved_font_path",
                        "resolved_font_index",
                        "resolved_status",
                        "resolved_flet_alias",
                        "metricas",
                    ):
                        if getattr(old, _attr, None) is not None:
                            setattr(new, _attr, getattr(old, _attr))
                self.profiles[self.selected_profile_index] = new
                self.current_profile = new
            except Exception:
                pass
            if self.on_profile_changed:
                self.on_profile_changed(self.current_profile)
            self.page.pop_dialog()
            if self.viewer_callback:
                self.viewer_callback._redraw_all()

        def on_save_as_default(e):
            self.profiles[self.selected_profile_index] = self.current_profile.copy()
            self.save_to_preferences()
            snack = ft.SnackBar(
                content=ft.Text(
                    t("Perfiles guardados como plantilla para nuevos trabajos"),
                    color=SNACKBAR_COLOR_TEXTO,
                ),
                bgcolor=SUCCESS_COLOR,
                duration=2000,
            )
            self.page.show_dialog(snack)

        self.dialog = ft.AlertDialog(
            modal=True,
            inset_padding=0,
            title_padding=ft.Padding(10, 20, 10, 8),
            title=ft.Container(
                content=ft.Row(
                    [
                        ft.Container(width=40),
                        ft.Text(
                            t("Textos Variables"),
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
                            tooltip=t("Guía del texto variable"),
                            width=40,
                            height=40,
                            on_click=lambda e: abrir_guia(
                                self.page, "elementos/texto_variable"
                            ),
                        ),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=4,
                ),
                alignment=ft.Alignment.CENTER,
            ),
            content=self.dialog_root_stack,
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

        purge_stale_dialog(self.page, self.dialog)
        try:
            self.page.show_dialog(self.dialog)
        except RuntimeError:
            print("[VAR_TEXT_DIALOG] show_dialog: ya estaba en la pila (ignorado)")
        if self._pending_initial_row is not None:
            self._set_preview_row(self._pending_initial_row, update=False)
            self._pending_initial_row = None
        self._update_font_style_list()
        self._update_preview()
        self.page.update()

        # Hacer scroll a la familia de fuente seleccionada (replica text_settings_dialog)
        import asyncio

        async def do_scroll_async():
            await asyncio.sleep(0.3)
            if hasattr(self, "_font_family_listview") and self._font_family_listview:
                if self.current_profile.font_family in self.available_fonts:
                    try:
                        font_families = sorted(
                            self.available_fonts.keys(), key=str.lower
                        )
                        selected_index = font_families.index(
                            self.current_profile.font_family
                        )
                        item_height = 25
                        visible_height = 140
                        target_offset = (
                            (selected_index * item_height)
                            - (visible_height / 2)
                            + (item_height / 2)
                        )
                        total_items = len(self._font_family_listview.controls)
                        max_offset = max(
                            0, (total_items * item_height) - visible_height
                        )
                        safe_offset = max(0, min(target_offset, max_offset))
                        await self._font_family_listview.scroll_to(
                            offset=safe_offset, duration=300
                        )
                    except Exception:
                        pass
                    await asyncio.sleep(0.15)
                    self.page.update()

        self.page.run_task(do_scroll_async)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------
    def _on_font_size_change(self, e):
        """Callback cuando cambia el tamaño de fuente (replica text_settings_dialog)."""
        normalize_decimal_input(e)
        try:
            size = max(1.0, float(e.control.value))
            self.current_profile.font_size = size

            if self._font_size_field and e.control != self._font_size_field:
                self._font_size_field.value = str(size)
                self._font_size_field.update()

            # Modo auto: el interlineado sigue al cuerpo (1.2 × cuerpo)
            if self._interlineado_auto:
                self.current_profile.line_spacing = LINE_SPACING_AUTO * size
                if self._line_spacing_field:
                    self._line_spacing_field.value = _fmt_pt(
                        self.current_profile.line_spacing
                    )
                    self._line_spacing_field.update()

            # Recargar métrica con el nuevo tamaño de fuente
            if (
                hasattr(self.current_profile, "resolved_font_path")
                and self.current_profile.resolved_font_path
            ):
                if hasattr(self, "font_metrics_cache") and self.font_metrics_cache:
                    try:
                        metric = self.font_metrics_cache.get_metrics(
                            str(self.current_profile.resolved_font_path),
                            size,
                            getattr(self.current_profile, "resolved_font_index", 0),
                        )
                        if metric:
                            self.current_profile.metricas = metric.copy()
                    except Exception:
                        pass

            if not hasattr(self.current_profile, "metricas") or not isinstance(
                self.current_profile.metricas, dict
            ):
                self.current_profile.metricas = {}

            self.profiles[self.selected_profile_index] = self.current_profile.copy()
            if self.on_profile_changed:
                self.on_profile_changed(self.current_profile)
            if self.viewer_callback:
                self.viewer_callback._redraw_all()

            self._update_preview()
        except ValueError:
            pass

    def _on_text_alignment_changed(self, value):
        if value not in TEXT_ALIGN_KEYS:
            return
        self.current_profile.text_alignment = value
        self.profiles[self.selected_profile_index] = self.current_profile.copy()
        if self.on_profile_changed:
            self.on_profile_changed(self.current_profile)
        if self.viewer_callback:
            self.viewer_callback._redraw_all()
        self._update_preview()
        self.page.update()

    def _on_line_spacing_change(self, e):
        normalize_decimal_input(e)
        try:
            val = float(e.control.value)
        except (ValueError, TypeError):
            return
        if val < 0:
            val = 0.0
        self.current_profile.line_spacing = val
        self._interlineado_auto = False
        self.profiles[self.selected_profile_index] = self.current_profile.copy()
        if self.on_profile_changed:
            self.on_profile_changed(self.current_profile)
        if self.viewer_callback:
            self.viewer_callback._redraw_all()
        self._update_preview()
        self.page.update()

    def _on_letter_spacing_change(self, e):
        normalize_decimal_input(e)
        try:
            val = float(e.control.value)
        except (ValueError, TypeError):
            return
        self.current_profile.letter_spacing = val
        self.profiles[self.selected_profile_index] = self.current_profile.copy()
        if self.on_profile_changed:
            self.on_profile_changed(self.current_profile)
        if self.viewer_callback:
            self.viewer_callback._redraw_all()
        self._update_preview()
        self.page.update()

    def _on_line_spacing_reset(self, e):
        # "Normal" = auto = 1.2 × cuerpo (igual que el playground), no 0.
        self._line_spacing_field.value = _fmt_pt(
            LINE_SPACING_AUTO * float(self.current_profile.font_size or 12.0)
        )
        self._line_spacing_field.update()
        self._on_line_spacing_change(
            type("_e", (), {"control": self._line_spacing_field})()
        )
        self._interlineado_auto = True

    def _update_value_source_dropdown(self, value):
        if value == "excel" and not self._excel_columns:
            snack = ft.SnackBar(
                content=ft.Text(
                    t(
                        "No hay archivo de datos cargado. Cargue un archivo Excel o CSV primero."
                    ),
                    color=SNACKBAR_COLOR_TEXTO,
                ),
                bgcolor=SNACKBAR_COLOR_FONDO,
                duration=3000,
            )
            self.page.show_dialog(snack)
            texto_valor = self._value_source_dropdown.content.controls[0]
            for opt in VALUE_SOURCE_OPTIONS:
                if opt[0] == "sample":
                    texto_valor.value = opt[1]
                    texto_valor.data = "sample"
                    break
            texto_valor.update()
            value = "sample"
        self.current_profile.value_source = value
        if self._text_case_filter_dropdown:
            self._text_case_filter_dropdown.visible = value == "excel"
        if self._preview_row_nav:
            self._preview_row_nav.visible = value == "excel"
            self._set_preview_row(0, update=False)
        self.profiles[self.selected_profile_index] = self.current_profile.copy()
        if self.on_profile_changed:
            self.on_profile_changed(self.current_profile)
        if self.viewer_callback:
            self.viewer_callback._redraw_all()
        self._update_preview()
        self.page.update()

    def _on_text_case_filter_changed(self, value):
        self.current_profile.text_case_filter = value
        self.profiles[self.selected_profile_index] = self.current_profile.copy()
        if self.on_profile_changed:
            self.on_profile_changed(self.current_profile)
        if self.viewer_callback:
            self.viewer_callback._redraw_all()
        self._update_preview()
        self.page.update()

    # ------------------------------------------------------------------
    # Editor de datos (popup estilo datamatrix)
    # ------------------------------------------------------------------
    def _open_vt_editor(self, e):
        """Abre overlay para editar el texto del texto variable.
        En modo excel muestra además un dropdown de columnas que inserta
        el marcador <@columna@> (append; Flet 0.28.2 no expone cursor)."""
        old_value = self.current_profile.sample_text or ""
        is_excel = self.current_profile.value_source == "excel"

        tf = ft.TextField(
            value=old_value,
            multiline=True,
            expand=True,
            min_lines=10,
            max_lines=12,
            on_change=self._on_vt_editor_change,
            on_selection_change=self._on_vt_editor_selection_change,
            hint_text=t("Escribe el texto (los campos van dentro del texto)..."),
            autofocus=True,
            filled=True,
            fill_color=FONDO_TEXTFIELDS_COLOR,
            text_style=ft.TextStyle(color=TEXTO_COLOR_GENERICO, size=13),border=ft.OutlineInputBorder(border_radius=8, side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)))
        p_editor = self.current_profile
        font_family_to_use = (
            getattr(p_editor, "resolved_flet_alias", None) or p_editor.font_family
        )
        style_lower = p_editor.font_style.lower()
        preview = ft.Text(
            value="",
            size=float(p_editor.font_size or 12.0),
            color=TEXTO_COLOR_GENERICO,
            selectable=True,
            font_family=font_family_to_use,
            weight=ft.FontWeight.BOLD if "bold" in style_lower else ft.FontWeight.NORMAL,
            italic="italic" in style_lower or "oblique" in style_lower,
            style=ft.TextStyle(
                height=self._preview_line_height_ratio(p_editor),
                size=float(p_editor.font_size or 12.0),
                letter_spacing=float(getattr(p_editor, "letter_spacing", 0.0) or 0.0),
            ),
        )

        column_dd = None
        if is_excel:
            opts = [("", t("(sin seleccion)"))]
            for col in self._excel_columns:
                opts.append((col, col))
            column_dd = self._create_compact_dropdown(
                options=opts,
                value="",
                width=250,
                height=28,
                text_size=11,
                on_change=lambda val: self._on_vt_editor_insert_column(val),
            )

        self._vt_editor_state = {
            "tf": tf,
            "preview": preview,
            "old_value": old_value,
            "column_dd": column_dd,
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

        editor_column = ft.Column(
            [
                ft.Text(
                    t("Editor de texto"),
                    size=18,
                    weight=ft.FontWeight.BOLD,
                    color=TEXTO_COLOR_GENERICO,
                ),
                ft.Divider(height=1, color=BORDE_TEXTFIELDS_COLOR),
                ft.Container(height=8),
            ],
            spacing=6,
            tight=True,
        )
        if is_excel:
            editor_column.controls.append(
                ft.Row(
                    [
                        ft.Text(
                            t("Columna:"), size=12, color=TEXTOS_FASE_1_COLOR
                        ),
                        column_dd,
                    ],
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                )
            )
            editor_column.controls.append(ft.Container(height=4))
        editor_column.controls.extend(
            [
                tf,
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
                        ft.Button(
                            t("Cancelar"),
                            on_click=lambda e: self._close_vt_editor(restore=True),
                            width=110,
                            bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
                            style=_btn_style,
                        ),
                        ft.Button(
                            t("Aceptar"),
                            on_click=lambda e: self._close_vt_editor(restore=False),
                            width=110,
                            bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
                            style=_btn_style,
                        ),
                    ],
                    spacing=8,
                    alignment=ft.MainAxisAlignment.END,
                ),
            ]
        )

        popup = ft.Container(
            content=ft.Container(
                content=editor_column,
                padding=ft.Padding(24, 20, 24, 20),
                width=1000,
                height=640,
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
        self._on_vt_editor_change()

    def _on_vt_editor_change(self, e=None):
        st = getattr(self, "_vt_editor_state", None)
        if not st:
            return
        tf = st["tf"]
        value = tf.value or ""
        try:
            resolved = resolve_vt_text(
                value,
                value_source=self.current_profile.value_source,
                excel_manager=self.excel_manager,
                row_index=self._preview_row_index,
                text_case_filter=self.current_profile.text_case_filter,
            )
        except Exception:
            resolved = value
        st["preview"].value = resolved if resolved else t("(sin texto)")
        try:
            st["preview"].update()
        except Exception:
            pass

    def _on_vt_editor_selection_change(self, e):
        sel = getattr(e, "selection", None)
        if sel is not None and getattr(sel, "start", None) is not None:
            st = getattr(self, "_vt_editor_state", None)
            if st:
                st["sel_start"] = sel.start
                st["sel_end"] = sel.end

    def _on_vt_editor_insert_column(self, value):
        if not value:
            return
        st = getattr(self, "_vt_editor_state", None)
        if not st:
            return
        marker = f"<@<{value}>@>"
        cur = st["tf"].value or ""
        pos = st.get("sel_start")
        end = st.get("sel_end")
        if pos is None:
            pos = len(cur)
            end = pos
        if end is None:
            end = pos
        st["tf"].value = cur[:pos] + marker + cur[end:]
        try:
            st["tf"].update()
        except Exception:
            pass
        if st.get("column_dd"):
            dd = st["column_dd"].content.controls[0]
            dd.value = t("(sin seleccion)")
            dd.data = ""
            try:
                st["column_dd"].update()
            except Exception:
                pass
        self._on_vt_editor_change()

    def _close_vt_editor(self, restore=False):
        st = getattr(self, "_vt_editor_state", None)
        if not restore:
            if st and st.get("tf") is not None:
                self.current_profile.sample_text = st["tf"].value or ""
            self.profiles[self.selected_profile_index] = self.current_profile.copy()
            if self.on_profile_changed:
                self.on_profile_changed(self.current_profile)
            if self.viewer_callback:
                self.viewer_callback._redraw_all()
            self._update_preview()
        self._vt_editor_state = None
        if len(self.dialog_root_stack.controls) > 1:
            self.dialog_root_stack.controls.pop()
        self.dialog_root_stack.update()
        if self.page and self.dialog:
            self.dialog.update()
        self.page.update()
