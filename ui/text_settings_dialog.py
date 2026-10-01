"""
Diálogo de configuración de estilos de texto para numeración.
Permite crear y editar perfiles de texto con fuente, tamaño, color, prefijo, sufijo y máscara.
"""

import flet as ft

def _safe_page(ctrl):
    """Devuelve ctrl.page o None si no está montado (Flet 1.0: .page lanza RuntimeError)."""
    try:
        return ctrl.page
    except Exception:
        return None

from dataclasses import dataclass, asdict
from typing import Optional, Callable
import uuid
import sys
import os
import json
from pathlib import Path
import re
import logging

# Silenciar prints de depuración en este módulo por defecto.
# Para activar, cambiar _PRINT_DEBUG = True durante desarrollo.
_PRINT_DEBUG = False
if not _PRINT_DEBUG:

    def _no_print(*args, **kwargs):
        return None

    print = _no_print


def _fmt_pt(v: float) -> str:
    """Formatea tamaño de letra: '24' para enteros, '24.5' para fracciones."""
    return str(int(v)) if v == int(v) else f"{v:.1f}"


# Añadir el directorio padre al path para importar color_design
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from color_design import (
    TEXTO_COLOR_GENERICO,
    FONDO_APP,
    FONDO_TEXTFIELDS_COLOR,
    BORDE_TEXTFIELDS_COLOR,
    FONDO_SECCIONES,  # Kept from original
    FONDO_ALERT_DIALOG,  # Kept from original
    DROPDOWN_FONDO_MENU_COLOR,
    SUCCESS_COLOR,
    ERROR_COLOR,
    BOTONES_GENERICOS_COLOR,
    BOTONES_GENERICOS_TEXTO_COLOR,
    BOTONES_GENERICOS_HOVER_COLOR,
    BOTONES_GENERICOS_OVERLAY_COLOR,
    BOTONES_GENERICOS_FONDO_COLOR,
    FONDO_BLOQUE_RESUMEN_COLOR,
    FONDO_HEADER_FASE_1,
    FONDO_CALCULO_FASE_1,
    TEXTOS_FASE_1_COLOR,
    DROPDOWN_TEXT_STYLE_COLOR,
    DROPDOWN_TRAILING_ICON_COLOR,
    SNACKBAR_COLOR_TEXTO,
    SNACKBAR_COLOR_FONDO,
    SNACKBAR_COLOR_ERROR,
)

from .color_picker import ColorPicker
from .color_picker_dialog import ColorPickerDialog
from ui.dialog_utils import show_rename_profile_dialog, purge_stale_dialog, reopen_dialog
from ui.guia_html_viewer import abrir_guia
from utils.metrics_analisys import FontMetricsCache, cargar_metricas_perfiles
from utils.font_manager import get_default_font_family
from utils.constants import normalize_decimal_input

# Internacionalización
from i18n import t
from utils.preferences import get_last_file_dialog_path, set_last_file_dialog_path


@dataclass
class TextStyle:
    """Estilo de texto para numeración

    NOTA: Se añaden campos transitorios para almacenar la resolución de la
    fuente en disco (`resolved_font_path`, `resolved_font_index`). Estos
    campos se usan en tiempo de ejecución y NO deben persistirse en las
    preferencias (se filtran antes de guardar).
    """

    id: str  # UUID único
    name: str  # Nombre del perfil
    font_family: str  # Familia de fuente
    font_style: str  # "Regular", "Bold", "Italic", "Bold Italic"
    font_size: float  # Tamaño en puntos

    # Espacio de color para el PDF (legacy, se mantiene para compatibilidad)
    color_space: str = "RGB"  # "RGB" | "CMYK" | "SPOT"

    # Espacio de color independiente por segmento
    number_color_space: str = "RGB"  # "RGB" | "CMYK" | "SPOT"
    prefix_color_space: str = "RGB"  # "RGB" | "CMYK" | "SPOT"
    suffix_color_space: str = "RGB"  # "RGB" | "CMYK" | "SPOT"

    # Nombre del color (para SPOT/tinta plana). Para RGB/CMYK se genera automáticamente.
    number_color_name: str = ""  # p.ej. "PANTONE 485 C"
    prefix_color_name: str = ""
    suffix_color_name: str = ""

    # Colores en RGB (hex) - siempre guardados
    number_color: str = "#000000"  # Color de los números (#RRGGBB)
    prefix_color: str = "#000000"  # Color del prefijo (#RRGGBB)
    suffix_color: str = "#000000"  # Color del sufijo (#RRGGBB)

    # Colores en CMYK (0-100) - siempre guardados
    number_color_cmyk: tuple = (0.0, 0.0, 0.0, 100.0)  # (c, m, y, k)
    prefix_color_cmyk: tuple = (0.0, 0.0, 0.0, 100.0)  # (c, m, y, k)
    suffix_color_cmyk: tuple = (0.0, 0.0, 0.0, 100.0)  # (c, m, y, k)

    # Porcentaje de tinta para colores planos SPOT (0-100, default 100 = tinta plena)
    number_color_tint: float = 100.0
    prefix_color_tint: float = 100.0
    suffix_color_tint: float = 100.0

    letter_spacing: float = 0.0  # Espaciado entre letras de los números
    prefix_suffix_spacing: float = 0.0  # Espaciado entre letras del prefijo/sufijo
    prefix: str = ""  # Texto prefijo
    suffix: str = ""  # Texto sufijo
    mask: str = "0000"  # Máscara de formato
    mask_placeholder: str = "0"  # Carácter placeholder
    digit_placeholder: int = 0  # Posición del dígito placeholder (0-9)
    thousands_separator: str = (
        "normal"  # Separador de millares: "normal", "punto", "espacio", "coma"
    )

    # Deprecado: mantener para compatibilidad con archivos antiguos
    color: str = "#000000"  # Color legacy (usar number_color)

    # Campos transitorios (runtime only)
    resolved_font_path: str = None
    resolved_font_index: int = 0
    resolved_status: str = None  # 'installed' | 'activated-only' | None
    metricas: dict = None  # Almacena las métricas cargadas en memoria
    # Alias registrado en Flet (si se extrajo/registró para el session)
    resolved_flet_alias: str = None

    @staticmethod
    def create_default() -> "TextStyle":
        """Crea un estilo por defecto"""
        return TextStyle(
            id=str(uuid.uuid4()),
            name="<Default>",
            font_family=get_default_font_family(),
            font_style="Regular",
            font_size=12,
            color_space="RGB",
            number_color_space="RGB",
            prefix_color_space="RGB",
            suffix_color_space="RGB",
            number_color_name="",
            prefix_color_name="",
            suffix_color_name="",
            number_color="#000000",
            prefix_color="#000000",
            suffix_color="#000000",
            number_color_cmyk=(0.0, 0.0, 0.0, 100.0),
            prefix_color_cmyk=(0.0, 0.0, 0.0, 100.0),
            suffix_color_cmyk=(0.0, 0.0, 0.0, 100.0),
            number_color_tint=100.0,
            prefix_color_tint=100.0,
            suffix_color_tint=100.0,
            letter_spacing=0.0,
            prefix_suffix_spacing=0.0,
            prefix="",
            suffix="",
            mask="0000",
            mask_placeholder="0",
            digit_placeholder=0,
            thousands_separator="normal",
            color="#000000",  # Legacy
        )

    def copy(self) -> "TextStyle":
        """Crea una copia del estilo preservando campos transitorios"""
        import copy as copy_module

        return copy_module.copy(self)


class TextStyleManager:
    """Gestor de estilos de texto con interfaz de diálogo"""

    def __init__(
        self,
        page: ft.Page,
        on_style_changed: Optional[Callable[[TextStyle], None]] = None,
        viewer_callback=None,
        on_profile_renamed: Optional[Callable] = None,
    ):
        self.page = page
        self.on_style_changed = on_style_changed
        self.on_profile_renamed = on_profile_renamed
        self.viewer_callback = (
            viewer_callback  # Para redibujar el viewer al cerrar diálogo
        )

        # Inicializar gestor de fuentes
        from utils.font_manager import obtener_gestor

        self.gestor = obtener_gestor()

        # Inicializar font_metrics_cache desde el inicio (puede ser None si hay errores)
        self.font_metrics_cache = None

        # Estado - se inicializa con default, luego se carga desde preferencias
        self.profiles: list[TextStyle] = [TextStyle.create_default()]
        self.selected_profile_index: int = 0
        self._last_color_pick = None
        self.current_style: TextStyle = self.profiles[0].copy()

        # Número de muestra para la vista previa (se cargará desde preferencias)
        # `preview_sample_number` mantiene el valor numérico (int) para cálculos,
        # `preview_sample_number_raw` mantiene la representación textual exacta
        # introducida por el usuario (permite conservar ceros iniciales como '0001').
        self.preview_sample_number: int = 1234
        self.preview_sample_number_raw: str = "1234"

        # Colores spot acumulados de los PDFs cargados (propagados al picker)
        self.extracted_spot_colors: list = []
        self.color_picker_dialog = None  # creado de forma lazy al abrir el diálogo

        # Cargar perfiles desde preferencias globales
        self.load_from_preferences()

        # Preparar fuentes y resolver perfiles AHORA para que el perfil <Default>
        # esté listo para usar inmediatamente al arrancar la app (sin abrir el diálogo)
        try:
            print(
                "[TEXT_STYLE] Inicializando fuentes y resolviendo perfiles en startup..."
            )
            # Cargar índice de fuentes (usa CoreText en macOS o matplotlib en fallback)
            self.available_fonts = self._load_system_fonts()
            # available_fonts_status puede ser establecido por _load_system_fonts
            # Resolver rutas para los perfiles cargados para tener resolved_* disponibles
            try:
                self._resolve_profiles()
            except Exception as e:
                print(f"[TEXT_STYLE] _resolve_profiles fallo en startup: {e}")

            # Cargar métricas de fuentes para todos los perfiles
            try:
                print("[TEXT_STYLE] Cargando métricas de fuentes para perfiles...")
                # Preparar estructura de fuentes del sistema: {family: [styles]}
                fuentes_sistema = {}
                if self.available_fonts:
                    for family, styles in self.available_fonts.items():
                        fuentes_sistema[family] = (
                            list(styles)
                            if isinstance(styles, (list, set))
                            else [styles]
                        )

                # Crear cache de métricas y GUARDAR COMO ATRIBUTO
                self.font_metrics_cache = FontMetricsCache()

                # Cargar métricas para todos los perfiles
                cargar_metricas_perfiles(
                    self.profiles,
                    fuentes_sistema,
                    self.font_metrics_cache,
                    default_profile=None,  # Función buscará <Default> automáticamente
                )
            except Exception as e:
                print(f"[TEXT_STYLE] Error al cargar métricas de fuentes: {e}")
        except Exception as e:
            print(
                f"[TEXT_STYLE] No se pudieron inicializar las fuentes en startup: {e}"
            )

        # Fuentes del sistema (si ya se cargaron arriba se mantienen)
        self.available_fonts: Optional[dict[str, list[str]]] = (
            self.available_fonts if hasattr(self, "available_fonts") else None
        )
        # Mantener/crear estructura de estados de validación de fuentes si no existe
        self.available_fonts_status: dict = getattr(self, "available_fonts_status", {})

        # UI Components - Panel izquierdo
        self.profile_list: Optional[ft.ListView] = None
        self.btn_new_profile: Optional[ft.IconButton] = None
        self.btn_delete_profile: Optional[ft.IconButton] = None
        self.btn_help: Optional[ft.IconButton] = None

        # UI Components - Panel derecho (Fuente)
        self.font_family_list: Optional[ft.ListView] = None
        self.font_style_list: Optional[ft.ListView] = None
        self.font_size_field: Optional[ft.TextField] = None
        self.color_picker_button: Optional[ft.Container] = None

        # UI Components - Panel derecho (Prefijo/Sufijo)
        self.prefix_field: Optional[ft.TextField] = None
        self.suffix_field: Optional[ft.TextField] = None

        # UI Components - Panel derecho (Máscara)
        self.mask_field: Optional[ft.TextField] = None
        self.digit_placeholder_field: Optional[ft.TextField] = None

        # UI Components - Vista previa
        self.preview_text: Optional[ft.Text] = None

        # Diálogo
        self.dialog: Optional[ft.AlertDialog] = None

    def _load_system_fonts(self) -> dict[str, list[str]]:
        """Carga las fuentes del sistema usando gestor_fuentes con normalización.

        Prioriza el uso de gestor_fuentes para obtener estilos normalizados.
        Si no está disponible, usa font_index con lógica básica de normalización.
        """
        print("[FONT] Cargando fuentes del sistema con normalización...")

        try:
            # Intentar usar el gestor de fuentes mejorado
            from utils import font_index_wrapper as font_index

            # Usar get_normalized_fonts que internamente usa gestor_fuentes si está disponible
            fonts = font_index.get_normalized_fonts()

            # Validar fuentes para obtener estados (installed/activated-only/missing)
            try:
                self.available_fonts_status = font_index.validate_cached_fonts(fonts)
                print(
                    f"[FONT] Estados de validación obtenidos para {len(self.available_fonts_status)} familias"
                )
            except Exception as e:
                print(f"[FONT] Error al validar estados: {e}")
                self.available_fonts_status = {}

            print(f"[FONT] ✓ Cargadas {len(fonts)} familias con estilos normalizados")

            # Mostrar ejemplo de normalización para debug
            if fonts and "[FONT_FAMILY]" in str(
                self.page.route
            ):  # Solo si estamos en debug
                familia_ejemplo = next(iter(fonts.keys()))
                estilos_ejemplo = fonts[familia_ejemplo]
                print(
                    f"[FONT] Ejemplo: {familia_ejemplo} → {len(estilos_ejemplo)} estilos: {estilos_ejemplo[:5]}..."
                )

            return dict(sorted(fonts.items()))

        except Exception as e:
            print(f"[FONT] Error con gestor_fuentes, usando fallback básico: {e}")

            # Fallback: usar build_font_index directamente sin normalización avanzada
            try:
                from utils import font_index

                idx = font_index.build_font_index()
                fonts = {}

                for family, entries in idx.items():
                    styles = set()
                    for e in entries:
                        nm = (e.get("name") or "").strip()
                        fname = os.path.basename(e.get("path") or "")
                        style_raw = None

                        # Extraer estilo del nombre
                        if nm and nm.lower().startswith(family.lower()):
                            style_raw = nm[len(family) :].strip("- ").strip()
                        elif "-" in nm:
                            style_raw = nm.split("-", 1)[-1]
                        else:
                            # Buscar tokens de estilo
                            s = nm.lower()
                            if any(
                                tok in s
                                for tok in (
                                    "bold",
                                    "italic",
                                    "oblique",
                                    "black",
                                    "light",
                                    "thin",
                                    "condensed",
                                    "medium",
                                )
                            ):
                                for tok in (
                                    "Bold",
                                    "Italic",
                                    "Oblique",
                                    "Black",
                                    "Light",
                                    "Thin",
                                    "Condensed",
                                    "Medium",
                                ):
                                    if tok.lower() in s:
                                        style_raw = tok
                                        break
                            else:
                                s2 = fname.lower()
                                for tok in (
                                    "bold",
                                    "italic",
                                    "oblique",
                                    "black",
                                    "light",
                                    "thin",
                                    "condensed",
                                    "medium",
                                ):
                                    if tok in s2:
                                        style_raw = tok.capitalize()
                                        break

                        # Normalizar sufijos (ej: 'BoldItalicMT' -> 'Bold Italic')
                        s = style_raw or "Regular"
                        s = re.sub(r"MT$", "", s, flags=re.IGNORECASE)
                        if " " not in s and any(ch.isupper() for ch in s[1:]):
                            s = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", s)
                        s = (
                            " ".join(
                                w.capitalize() for w in re.split(r"[\s_\-]+", s.strip())
                            )
                            or "Regular"
                        )
                        style = s
                        styles.add(style)

                    if not styles:
                        styles.add("Regular")

                    # Orden preferido de estilos
                    style_order = {
                        "Regular": 0,
                        "Bold": 1,
                        "Italic": 2,
                        "Oblique": 2,
                        "Bold Italic": 3,
                        "Bold Oblique": 3,
                        "Light": 4,
                        "Thin": 5,
                        "Black": 6,
                    }
                    fonts[family] = sorted(styles, key=lambda s: style_order.get(s, 99))

                # Validar estados
                try:
                    self.available_fonts_status = font_index.validate_cached_fonts(
                        fonts
                    )
                except Exception:
                    self.available_fonts_status = {}

                print(f"[FONT] Cargadas {len(fonts)} familias (fallback básico)")
                return dict(sorted(fonts.items()))

            except Exception as e2:
                print(
                    f"[FONT] Error en fallback básico: {e2}, usando fuentes por defecto"
                )

                # Último fallback: fuentes básicas hardcoded
                return {
                    "Helvetica": ["Regular", "Bold", "Italic", "Bold Italic"],
                    "Arial": ["Regular", "Bold", "Italic", "Bold Italic"],
                    "Times New Roman": ["Regular", "Bold", "Italic", "Bold Italic"],
                    "Courier New": ["Regular", "Bold", "Italic", "Bold Italic"],
                }

    def _refresh_system_fonts(self, force_reload=False):
        """
        Recarga las fuentes del sistema usando gestor_fuentes con normalización.
        Actualiza available_fonts y available_fonts_status.

        Args:
            force_reload: Si True, fuerza recarga completa ignorando cache.
                         Si False, solo recarga si gestor lo considera necesario.
        """
        print("[FONT REFRESH] 🔄 Actualizando índice de fuentes del sistema...")

        try:
            # Forzar recarga usando el nuevo sistema
            from utils import font_index_wrapper as font_index
            from utils.font_manager import obtener_gestor

            gestor = obtener_gestor()

            if force_reload:
                print(
                    "[FONT REFRESH] Recarga forzada contra catálogo actual del sistema"
                )

            sync_result = gestor.sincronizar_con_catalogo_sistema(skip_non_latin=True)
            cambios = sync_result.get("cambios", {}) or {}
            if not any(cambios.values()):
                print("[FONT REFRESH] ✓ Sin cambios reales en el catálogo del sistema")

            # Obtener fuentes normalizadas
            self.available_fonts = font_index.get_normalized_fonts()

            # Validar estados
            try:
                self.available_fonts_status = font_index.validate_cached_fonts(
                    self.available_fonts
                )
                print(
                    f"[FONT REFRESH] ✓ Estados validados para {len(self.available_fonts_status)} familias"
                )
            except Exception as e:
                print(f"[FONT REFRESH] ⚠️ Error validando estados: {e}")
                self.available_fonts_status = {}

            print(f"[FONT REFRESH] ✓ {len(self.available_fonts)} familias recargadas")

        except Exception as e:
            print(f"[FONT REFRESH] ❌ Error: {e}, usando método de respaldo")
            # Fallback: recargar con método básico
            try:
                self.available_fonts = self._load_system_fonts()
            except Exception as e2:
                print(f"[FONT REFRESH] ❌ Fallback también falló: {e2}")
                self.available_fonts_status = {}

        # Tras refrescar índices, re-resolver perfiles para tener rutas actualizadas
        try:
            self._resolve_profiles()
        except Exception as e:
            print(f"[FONT REFRESH] ⚠️ Error resolviendo perfiles: {e}")

    def _resolve_profiles(self):
        """Resolve font file paths for the current profiles and cache them on the profile

        Uses `PageNumber.utils.font_index.find_font_file_for()` for a lightweight check
        and `pdf_generator` helpers to determine TTC indexes when needed.
        """
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
                # Fallback Myriad Pro / custom TIPOS: si no está indexada pero el path original existe, conservarlo
                if (p is None or status == "missing") and orig_path and os.path.exists(orig_path):
                    p, status = orig_path, "installed"
                # Alias sin espacio: "MyriadPro" vs "Myriad Pro"
                if (p is None or status == "missing") and " " in (profile.font_family or ""):
                    alias_family = profile.font_family.replace(" ", "")
                    p2, s2 = font_index.find_font_file_for(alias_family, profile.font_style)
                    if p2:
                        p, status = p2, s2
                # Fallback directo a Documents/TIPOS si aún no encontrada (Myriad Pro de Adobe Folio)
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
                # Intent: si ya existe una extracción persistente en extracted_map, asignar el
                # alias Flet correspondiente y registrar la ruta en `page.fonts` para uso inmediato.
                try:
                    from utils import font_cache
                    from pathlib import Path

                    base = font_cache.get_config_dir()
                    cache = font_cache.load_cache(base) or {}
                    em = cache.get("extracted_map", {}) or {}
                    key = f"{p}|{profile.resolved_font_index}" if p else None
                    print(
                        f"[FONT RESOLVE] Perfil '{profile.name}': {profile.font_family} {profile.font_style}"
                    )
                    print(f"  TTC original: {p}")
                    print(f"  TTC index: {profile.resolved_font_index}")
                    print(f"  Cache key: {key}")
                    if key and key in em:
                        entry = em.get(key) or {}
                        orig = entry.get("original_path") or p or ""
                        idx = str(profile.resolved_font_index or 0)

                        # Generar alias usando familia-estilo (mismo formato que _on_font_style_change)
                        family_safe = profile.font_family.replace(" ", "")
                        style_safe = profile.font_style.replace(" ", "")
                        alias = f"{family_safe}-{style_safe}"
                        profile.resolved_flet_alias = alias

                        extracted = entry.get("extracted_path")
                        # Validar checksum del TTC original vs el guardado: si la
                        # fuente en esta ruta cambió, extraer_ttc_individual re-extrae
                        try:
                            extracted = self.gestor.extraer_ttc_individual(
                                p, profile.resolved_font_index
                            )
                        except Exception as ex:
                            print(f"  ⚠️ Error re-extracción: {ex}")
                            extracted = None
                        if extracted is not None:
                            extracted = str(extracted)
                        print(f"  Extraído (con checksum): {extracted}")
                        print(f"  Alias generado: {alias}")

                        # ✨ ACTUALIZAR resolved_font_path al archivo extraído para métricas correctas
                        if extracted and Path(extracted).exists():
                            print(
                                f"  ✅ ANTES: resolved_font_path = {profile.resolved_font_path}"
                            )
                            profile.resolved_font_path = (
                                extracted  # ← Usar TTF extraído en vez de TTC original
                            )
                            profile.resolved_font_index = (
                                None  # Ya no es TTC, es TTF individual
                            )
                            print(
                                f"  ✅ DESPUÉS: resolved_font_path = {profile.resolved_font_path}"
                            )
                            print(
                                f"  ✅ Actualizado a archivo extraído: {Path(extracted).name}"
                            )
                        else:
                            print(f"  ⚠️ Archivo extraído no existe: {extracted}")

                        try:
                            if extracted and _safe_page(self):
                                # Asegurar que page.fonts existe antes de registrar
                                if (
                                    not hasattr(self.page, "fonts")
                                    or self.page.fonts is None
                                ):
                                    self.page.fonts = {}
                                    print(
                                        f"  ✨ Inicializado page.fonts como dict vacío"
                                    )

                                # Registrar en page.fonts si no existe
                                if alias not in self.page.fonts:
                                    try:
                                        self.page.fonts[alias] = extracted
                                        print(
                                            f"  ✓ Registrado en page.fonts: {alias} -> {Path(extracted).name}"
                                        )
                                    except Exception as reg_ex:
                                        print(
                                            f"  ⚠️ Error registrando en page.fonts: {reg_ex}"
                                        )
                                else:
                                    print(f"  ℹ️ Ya existe en page.fonts: {alias}")
                        except Exception as font_ex:
                            print(f"  ⚠️ Error al registrar fuente: {font_ex}")
                    else:
                        print(f"  ⚠️ NO encontrado en extracted_map")
                        # Para fuentes .ttf/.otf directas (no TTC), registrar directamente
                        # en page.fonts sin necesidad de extracted_map
                        if p and not p.lower().endswith((".ttc", ".otc")):
                            family_safe = profile.font_family.replace(" ", "")
                            style_safe = profile.font_style.replace(" ", "")
                            alias = f"{family_safe}-{style_safe}"
                            profile.resolved_flet_alias = alias
                            print(f"  ✓ Fuente directa (.ttf/.otf): alias={alias}")
                            try:
                                if _safe_page(self):
                                    if (
                                        not hasattr(self.page, "fonts")
                                        or self.page.fonts is None
                                    ):
                                        self.page.fonts = {}
                                    if alias not in self.page.fonts:
                                        self.page.fonts[alias] = p
                                        print(
                                            f"  ✓ Registrado en page.fonts: {alias} -> {Path(p).name}"
                                        )
                                    else:
                                        print(f"  ℹ️ Ya existe en page.fonts: {alias}")
                            except Exception as reg_ex:
                                print(
                                    f"  ⚠️ Error registrando fuente directa: {reg_ex}"
                                )
                except Exception as ex:
                    print(f"  ❌ Error en resolución: {ex}")
                    # No bloquear la resolución si la cache no está disponible
                    pass
            except Exception:
                profile.resolved_font_path = None
                profile.resolved_status = None
                profile.resolved_font_index = 0

        print(f"[FONT RESOLVE] Resueltas rutas para {len(self.profiles)} perfiles")

    def _on_assign_style(self, family: str, style: str):
        """Inicia el flujo para que el usuario asigne manualmente un archivo de fuente a un estilo."""
        print(f"[FONT ASSIGN] Asignar archivo para {family} / {style}")
        # Guardar en pending para el callback
        self._pending_assign = {"family": family, "style": style}
        # Crear FilePicker y abrirlo
        picker = ft.FilePicker(on_result=self._on_assign_file_result)
        self.page.services.append(picker)
        picker.pick_files(
            allow_multiple=False,
            file_type=ft.FilePickerFileType.FILES,
            allowed_extensions=["ttf", "otf", "ttc"],
            initial_directory=get_last_file_dialog_path(),
        )
        self.page.update()

    def _on_assign_file_result(self, e: ft.FilePickerResultEvent):
        """Callback del FilePicker al asignar archivo. Copia el archivo a config/fonts y refresca índice."""
        try:
            if not hasattr(self, "_pending_assign") or not self._pending_assign:
                print("[FONT ASSIGN] Ninguna asignación pendiente")
                return
            family = self._pending_assign["family"]
            style = self._pending_assign["style"]
            # Archivo seleccionado
            if not e.files:
                print("[FONT ASSIGN] Usuario canceló selección")
                return
            src = e.files[0].path
            set_last_file_dialog_path(src)
            print(f"[FONT ASSIGN] Usuario seleccionó: {src} para {family}/{style}")
            try:
                # Validate path (no copy), then register for immediate use in session
                from utils import font_index_wrapper as font_index
                from utils import pdf_generator

                valid_path = font_index.assign_font_file(family, style, src)
                pdf_generator.register_font_file(family, style, valid_path)
                print(f"[FONT ASSIGN] Registrada para sesión: {valid_path}")
            except Exception as ex:
                print(f"[FONT ASSIGN] Error registrando fuente: {ex}")

            # Refrescar índice y UI
            self._refresh_system_fonts()
            # Re-resolver perfiles para actualizar resolved_* en los estilos
            try:
                self._resolve_profiles()
            except Exception:
                pass
            self._update_font_style_list()
            self.page.update()
        except Exception as ex:
            print(f"[FONT ASSIGN] Error: {ex}")

    def _create_textfield(
        self,
        label: str,
        value: str = "",
        width: Optional[float] = None,
        multiline: bool = False,
        max_length: Optional[int] = None,
        on_change: Optional[Callable] = None,
        disabled: bool = False,
    ) -> ft.TextField:
        """Crea un TextField con estilo consistente"""
        return ft.TextField(
            label=label,
            value=value,
            width=width,
            height=28,
            multiline=multiline,
            max_length=max_length,
            on_change=on_change,
            disabled=disabled,
            text_size=11,
            content_padding=ft.Padding(2, 0, 6, 0),
            filled=True,
            fill_color=FONDO_TEXTFIELDS_COLOR,
            text_style=ft.TextStyle(color=TEXTO_COLOR_GENERICO),
            label_style=ft.TextStyle(size=11, color=TEXTO_COLOR_GENERICO),border=ft.OutlineInputBorder(border_radius=3, side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)))

    def _create_increment_buttons(
        self, field: ft.TextField, on_change_callback, step=1
    ) -> ft.Column:
        """Crea botones de incrementar/decrementar para un campo numérico"""

        def increment(e):
            try:
                current = float(field.value)
                field.value = str(round(current + step, 1))
                field.update()
                if on_change_callback:
                    # Crear un evento simulado con el control del field
                    class FakeEvent:
                        def __init__(self, control):
                            self.control = control

                    on_change_callback(FakeEvent(field))
            except:
                pass

        def decrement(e):
            try:
                current = float(field.value)
                field.value = str(round(current - step, 1))
                field.update()
                if on_change_callback:
                    # Crear un evento simulado con el control del field
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

    def _create_profile_list_item(
        self, index: int, profile: TextStyle
    ) -> ft.GestureDetector:
        """Crea un item de la lista de perfiles"""
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

    def _select_profile(self, index: int):
        """Selecciona un perfil de la lista"""
        print(f"[PROFILE] Seleccionando perfil {index}: {self.profiles[index].name}")
        if index == self.selected_profile_index:
            print(f"[PROFILE] Ya estaba seleccionado, ignorando")
            return

        # Guardar los cambios del perfil actual antes de cambiar
        if self.selected_profile_index is not None:
            print(
                f"[PROFILE] Guardando cambios del perfil anterior {self.selected_profile_index}: {self.profiles[self.selected_profile_index].name}"
            )
            print(
                f"[PROFILE]   ANTES: {self.profiles[self.selected_profile_index].font_family} {self.profiles[self.selected_profile_index].font_size}pt"
            )
            self.profiles[self.selected_profile_index] = self.current_style.copy()
            print(
                f"[PROFILE]   DESPUÉS: {self.profiles[self.selected_profile_index].font_family} {self.profiles[self.selected_profile_index].font_size}pt"
            )

        self.selected_profile_index = index
        self.current_style = self.profiles[index].copy()
        print(f"[PROFILE] Cargando UI para perfil {self.current_style.name}")
        self._load_style_to_ui()
        print(f"[PROFILE] Actualizando lista de perfiles")
        self._update_profile_list()
        print(f"[PROFILE] Selección completada")

    def _rename_profile(self, index: int):
        if self.profiles[index].name == "<Default>":
            return

        def _apply(index, new_name):
            old_name = self.profiles[index].name
            self.profiles[index].name = new_name
            if index == self.selected_profile_index:
                self.current_style.name = new_name
            self._update_profile_list()
            if self.on_profile_renamed and old_name != new_name:
                self.on_profile_renamed(old_name, new_name)

        show_rename_profile_dialog(
            root_stack=self.dialog_root_stack,
            current_name=self.profiles[index].name,
            existing_names=[p.name for p in self.profiles],
            on_rename_success=lambda new_name: _apply(index, new_name),
        )

    def _update_profile_list(self):
        """Actualiza la lista de perfiles"""
        if self.profile_list:
            self.profile_list.controls = [
                self._create_profile_list_item(i, profile)
                for i, profile in enumerate(self.profiles)
            ]
            self.profile_list.update()

    def _tinted_display_color(
        self, base_hex: str, tint_pct: float, color_space: str
    ) -> str:
        """Devuelve el color hex con el tinte aplicado para previsualización o botones."""
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
        except Exception as e:
            print(
                f"[TINT_ERROR] Fallo en _tinted_display_color: base={base_hex} error={e}"
            )
            return base_hex

    def _load_style_to_ui(self):
        """Carga el estilo actual en los campos de UI"""
        # print(f"[LOAD_STYLE] Cargando estilo: {self.current_style.font_family} {self.current_style.font_size}pt")

        # Fuente
        if self.font_family_list and self.font_family_list.content:
            # print(f"[LOAD_STYLE] font_family_list existe: {self.font_family_list}")
            # print(f"[LOAD_STYLE] Tipo de content: {type(self.font_family_list.content)}")

            # Seleccionar familia de fuente
            for i, control in enumerate(self.font_family_list.content.controls):
                if isinstance(control, ft.Container):
                    text_widget = control.content
                    if isinstance(text_widget, ft.Text):
                        is_selected = (
                            text_widget.value == self.current_style.font_family
                        )
                        # if is_selected:
                        #     print(f"[LOAD_STYLE] Encontrada fuente seleccionada en índice {i}: {text_widget.value}")
                        text_widget.weight = (
                            ft.FontWeight.BOLD if is_selected else ft.FontWeight.NORMAL
                        )
                        control.bgcolor = (
                            FONDO_CALCULO_FASE_1
                            if is_selected
                            else FONDO_TEXTFIELDS_COLOR
                        )
            self.font_family_list.update()
            # print(f"[LOAD_STYLE] Lista actualizada")

            # Hacer scroll a la fuente seleccionada de forma asincrónica
            if hasattr(self, "font_family_listview") and self.font_family_listview:
                if self.current_style.font_family in self.available_fonts:
                    import asyncio

                    async def do_scroll_async():
                        # Pequeño delay para que el ListView esté listo
                        await asyncio.sleep(0.1)

                        try:
                            # Obtener lista de familias ORDENADA (igual que la lista visual)
                            font_families = sorted(
                                self.available_fonts.keys(), key=str.lower
                            )
                            selected_index = font_families.index(
                                self.current_style.font_family
                            )

                            # Usar la altura fija que definimos en el Container (30px)
                            item_height = 25
                            visible_height = 140

                            # Centrar el item en la lista:
                            # offset = (index * item_height) - (visible_height / 2) + (item_height / 2)
                            target_offset = (
                                (selected_index * item_height)
                                - (visible_height / 2)
                                + (item_height / 2)
                            )

                            # Limitar offset
                            total_items = len(self.font_family_listview.controls)
                            max_offset = max(
                                0, (total_items * item_height) - visible_height
                            )
                            safe_offset = max(0, min(target_offset, max_offset))

                            print(f"[SCROLL] Font: {self.current_style.font_family}")
                            print(
                                f"[SCROLL] Index: {selected_index}, Item height: {item_height}px"
                            )
                            print(
                                f"[SCROLL] Target offset: {target_offset:.1f}px -> Safe offset: {safe_offset:.1f}px"
                            )

                            await self.font_family_listview.scroll_to(
                                offset=safe_offset, duration=300
                            )
                            print(f"[SCROLL] Ejecutado correctamente")

                        except Exception as e:
                            print(f"[SCROLL] Error: {e}")
                            # import traceback
                            # traceback.print_exc()

                        await asyncio.sleep(0.15)
                        self.page.update()

                    # Ejecutar scroll de forma asincrónica
                    self.page.run_task(do_scroll_async)
                # else:
                #     print(f"[LOAD_STYLE] Fuente {self.current_style.font_family} no encontrada en available_fonts")
            # else:
            #     print(f"[LOAD_STYLE] font_family_listview NO existe o está None")
        # else:
        #     print(f"[LOAD_STYLE] font_family_list NO existe o está None")

        if self.font_style_list:
            self._update_font_style_list()

        if self.font_size_field:
            self.font_size_field.value = str(self.current_style.font_size)
            self.font_size_field.update()

        if self.letter_spacing_field:
            self.letter_spacing_field.value = str(self.current_style.letter_spacing)
            self.letter_spacing_field.update()

        if self.prefix_suffix_spacing_field:
            self.prefix_suffix_spacing_field.value = str(
                self.current_style.prefix_suffix_spacing
            )
            self.prefix_suffix_spacing_field.update()

        # Actualizar botones de color
        if hasattr(self, "number_color_button"):
            self.number_color_button.bgcolor = self._tinted_display_color(
                self.current_style.number_color,
                getattr(self.current_style, "number_color_tint", 100.0),
                getattr(
                    self.current_style,
                    "number_color_space",
                    self.current_style.color_space,
                ),
            )
            self.number_color_button.update()

        if hasattr(self, "prefix_suffix_color_button"):
            # Mostrar el color del prefijo por defecto
            self.prefix_suffix_color_button.bgcolor = self._tinted_display_color(
                self.current_style.prefix_color,
                getattr(self.current_style, "prefix_color_tint", 100.0),
                getattr(
                    self.current_style,
                    "prefix_color_space",
                    self.current_style.color_space,
                ),
            )
            self.prefix_suffix_color_button.update()

        # Actualizar dropdown de separador de millares
        if (
            hasattr(self, "thousands_separator_dropdown")
            and self.thousands_separator_dropdown
        ):
            separator_value = (
                self.current_style.thousands_separator
                if hasattr(self.current_style, "thousands_separator")
                else "normal"
            )
            self.thousands_separator_dropdown.value = separator_value
            self.thousands_separator_dropdown.update()

        # Prefijo/Sufijo
        if self.prefix_field:
            self.prefix_field.value = self.current_style.prefix
            self.prefix_field.update()

        if self.suffix_field:
            self.suffix_field.value = self.current_style.suffix
            self.suffix_field.update()

        # Máscara
        if self.mask_field:
            self.mask_field.value = self.current_style.mask
            self.mask_field.update()

        if self.digit_placeholder_field:
            digit_placeholder_value = (
                self.current_style.digit_placeholder
                if hasattr(self.current_style, "digit_placeholder")
                else 0
            )
            self.digit_placeholder_field.value = str(digit_placeholder_value)
            self.digit_placeholder_field.update()

            # Sincronizar mask_placeholder con digit_placeholder
            self.current_style.mask_placeholder = str(digit_placeholder_value)

        # Nº Muestra
        if hasattr(self, "sample_number_field") and self.sample_number_field:
            # Mostrar la representación raw (mantiene ceros iniciales)
            self.sample_number_field.value = str(self.preview_sample_number_raw)
            self.sample_number_field.update()

        # Actualizar vista previa
        self._update_preview()

    def _update_font_style_list(self):
        """Actualiza la lista de estilos según la familia seleccionada"""
        if not self.font_style_list:
            return

        # Asegurar que available_fonts esté cargado
        if not self.available_fonts:
            print(
                "[FONT_STYLE] ¡ADVERTENCIA! available_fonts es None, cargando fuentes..."
            )
            self.available_fonts = self._load_system_fonts()
        else:
            print(
                f"[FONT_STYLE] Usando fuentes ya cargadas ({len(self.available_fonts)} familias)"
            )

        family_found = self.current_style.font_family in self.available_fonts
        available_styles = self.available_fonts.get(self.current_style.font_family, [])

        # Si la familia no está instalada en este equipo, mostrar aviso específico
        if not family_found:
            print(
                f"[FONT_STYLE] Familia '{self.current_style.font_family}' no instalada en este equipo"
            )
            saved_style = self.current_style.font_style or "Regular"
            tooltip_text = f"{self.current_style.font_family}: {saved_style}"
            self.font_style_list.content.controls = [
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
                                t("Fuente no instalada: {0}").format(
                                    self.current_style.font_family
                                ),
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
            return

        # Función local para normalizar nombres para display (sin tocar el nombre original usado internamente)
        def _normalize_display_name(name: str) -> str:
            """Convierte un nombre PostScript de estilo a etiqueta legible tipo FontBook/Adobe."""
            if not name:
                return "Regular"
            raw = name.strip()
            if not raw:
                return "Regular"

            family = (self.current_style.font_family or "").strip()

            # ── 1. Extraer la parte de estilo ────────────────────────────────
            # Convenio PostScript: FamilyVariant-StyleName (un solo guión)
            if "-" in raw:
                style_part = raw.split("-", 1)[1]
            else:
                # Sin guión: intentar quitar el prefijo de familia compacto
                family_compact = re.sub(r"[^a-z0-9]", "", family.lower())
                raw_compact = re.sub(r"[^a-z0-9]", "", raw.lower())
                if family_compact and raw_compact.startswith(family_compact):
                    style_compact = raw_compact[len(family_compact) :]
                    if not style_compact:
                        return "Regular"
                    # Reconstruct tokens from compact lowercase form
                    style_part = style_compact  # all lower, no separators
                else:
                    # El nombre ya es un estilo legible (e.g. "Light", "Bold Oblique")
                    # devuelto por el gestor; procesarlo directamente como style_part
                    style_part = raw

            if not style_part:
                return "Regular"

            # ── 2. Eliminar sufijos de foundry/tamaño óptico al final ────────
            # e.g. "BoldMT" → "Bold", "ItalicMT" → "Italic"
            style_part = re.sub(
                r"(?i)(MT|PS|Std|Pro|BT|EF|OT|SC|Com|W[1-9])$", "", style_part
            ).strip(" -_")
            if not style_part:
                return "Regular"

            # ── 3. Tokenizar: separar camelCase y delimitadores ──────────────
            s = re.sub(r"([a-z])([A-Z])", r"\1 \2", style_part)  # camelCase
            s = re.sub(r"([A-Z]{2,})([A-Z][a-z])", r"\1 \2", s)  # ABCDef → ABC Def
            tokens = [t.lower() for t in re.split(r"[\s_\-]+", s) if t]

            # ── 4. Tabla de tokens → etiqueta canónica ───────────────────────
            TK = {
                # oblicuos
                "italic": "Italic",
                "it": "Italic",
                "ita": "Italic",
                "oblique": "Oblique",
                "obl": "Oblique",
                "ob": "Oblique",
                "inclined": "Oblique",
                # anchura
                "condensed": "Condensed",
                "cond": "Condensed",
                "cn": "Condensed",
                "cd": "Condensed",
                "narrow": "Narrow",
                "nar": "Narrow",
                "compressed": "Compressed",
                "extended": "Extended",
                "expand": "Extended",
                "expanded": "Extended",
                "wide": "Extended",
                # pesos
                "thin": "Thin",
                "hairline": "Thin",
                "light": "Light",
                "lt": "Light",
                "book": "Book",
                "roman": "Regular",
                "regular": "Regular",
                "normal": "Regular",
                "rg": "Regular",
                "medium": "Medium",
                "med": "Medium",
                "demi": "Semibold",
                "demibold": "Semibold",
                "semibold": "Semibold",
                "sb": "Semibold",
                "bold": "Bold",
                "bd": "Bold",
                "black": "Black",
                "heavy": "Black",
            }
            # Tokens a ignorar (códigos de foundry, ruido)
            NOISE = {
                "mt",
                "ps",
                "std",
                "pro",
                "bt",
                "ef",
                "ot",
                "sc",
                "com",
                "ltstd",
                "display",
                "text",
                "caption",
                "subhead",
                "poster",
                "w1",
                "w2",
                "w3",
                "w4",
                "w5",
                "w6",
                "w7",
                "w8",
                "w9",
                "a",
                "e",  # letras sueltas de ruido
            }

            result = []
            i = 0
            while i < len(tokens):
                t = tokens[i]

                # "extra" / "ultra" / "x" → prefijo para el token siguiente
                if t in ("extra", "ultra", "x"):
                    prefix = "Ultra" if t == "ultra" else "Extra"
                    if i + 1 < len(tokens):
                        nxt = tokens[i + 1]
                        mapped_nxt = TK.get(nxt)
                        if mapped_nxt is not None:
                            result.append(f"{prefix} {mapped_nxt}")
                            i += 2
                            continue
                    i += 1
                    continue

                # "semi"/"demi" + "bold" → "Semibold"
                if (
                    t in ("semi", "demi")
                    and i + 1 < len(tokens)
                    and tokens[i + 1] == "bold"
                ):
                    result.append("Semibold")
                    i += 2
                    continue

                if t in NOISE:
                    i += 1
                    continue

                mapped = TK.get(t)
                if mapped is not None:
                    result.append(mapped)
                elif len(t) > 2 and not re.match(r"^[0-9]+$", t):
                    result.append(t.capitalize())
                i += 1

            if not result:
                return "Regular"

            # Desduplicar entradas consecutivas idénticas
            deduped = [result[0]]
            for r in result[1:]:
                if r != deduped[-1]:
                    deduped.append(r)

            label = " ".join(deduped)

            # "Regular Italic" → "Italic"; "Regular Condensed" → "Condensed"
            parts = label.split()
            if "Regular" in parts and len(parts) > 1:
                parts.remove("Regular")
                label = " ".join(parts)

            return label or "Regular"

        # Mantener todos los estilos originales; no deduplicar por etiqueta visual.
        # Dos variantes distintas pueden compartir etiqueta (ej: "Regular") y ocultarlas
        # rompe selección/resolución de fuente.
        style_pairs = []
        display_counts = {}
        for orig in available_styles:
            disp = _normalize_display_name(orig)
            display_counts[disp] = display_counts.get(disp, 0) + 1
            style_pairs.append((orig, disp))

        # Limpiar controles anteriores
        self.font_style_list.content.controls.clear()

        # Crear nuevos controles usando el nombre de display, pero aplicando el estilo original al cambiar
        controls = []
        # Obtener estados validados para la familia actual (si existen)
        fam_statuses = (
            self.available_fonts_status.get(self.current_style.font_family, {})
            if hasattr(self, "available_fonts_status")
            else {}
        )

        # Si no tenemos estados validados para esta familia, pedir validación puntual
        if not fam_statuses:
            try:
                from utils import font_index_wrapper as font_index

                fam_statuses = font_index.validate_cached_fonts(
                    {self.current_style.font_family: available_styles}
                ).get(self.current_style.font_family, {})
                # Guardar para uso futuro
                if not hasattr(self, "available_fonts_status"):
                    self.available_fonts_status = {}
                self.available_fonts_status[self.current_style.font_family] = (
                    fam_statuses
                )
                print(
                    f"[FONT_STYLE] Validated statuses for family '{self.current_style.font_family}': {fam_statuses}"
                )
            except Exception as e:
                print(f"[FONT_STYLE] No se pudo validar estados de fonts: {e}")

        # Ya no necesitamos canonicalizar - usaremos comparación directa
        # current_canonical = self._canonical_style(self.current_style.font_style)

        # Filtrar solo estilos instalados para evitar que el usuario seleccione variantes no físicas
        filtered_style_pairs = []
        hidden_count = 0
        hidden_styles = []
        for orig, disp in style_pairs:
            state = fam_statuses.get(orig, "installed")
            if state == "installed":
                filtered_style_pairs.append((orig, disp))
            else:
                hidden_count += 1
                hidden_styles.append(disp or orig)

        if hidden_count:
            print(
                f"[FONT_STYLE] Ocultando {hidden_count} estilos no instalados para "
                f"'{self.current_style.font_family}': {hidden_styles}"
            )

        # Desduplicar: fuentes TTC pueden listar el mismo estilo varias veces
        seen = set()
        deduped = []
        for orig, disp in filtered_style_pairs:
            key = (orig, disp)
            if key not in seen:
                seen.add(key)
                deduped.append((orig, disp))
        filtered_style_pairs = deduped

        for orig, disp in filtered_style_pairs:
            # Comparar DIRECTAMENTE los nombres de estilo (no usar canonical que agrupa)
            is_selected = (orig == self.current_style.font_style) or (
                self.current_style.font_style == "" and disp == "Regular"
            )

            # Si hay etiquetas repetidas, añadir el original para desambiguar en UI.
            disp_ui = disp if display_counts.get(disp, 0) <= 1 else f"{disp} ({orig})"

            row = ft.Row(
                [
                    ft.Text(disp_ui, size=12, color=TEXTOS_FASE_1_COLOR,
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
                on_click=lambda e, s=orig: self._on_font_style_change(s),
            )
            controls.append(container)

        # Si ocultamos estilos, añadir un aviso informativo (solo lectura)
        if hidden_count > 0:
            hidden_label = ", ".join(hidden_styles)
            tooltip_text = f"{self.current_style.font_family}: {hidden_label}"
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

        self.font_style_list.content.controls = controls

    def _canonical_style(self, token: str) -> str:
        """Helper: normaliza un token de estilo a la forma canonical usada internamente.

        Reglas más explícitas para evitar falsos positivos (ej. 'Black' confundido con
        'Bold' por coincidencias en el primer carácter). Priorizar keywords completas
        ('black', 'bold', 'italic', 'oblique', etc.) y abreviaturas comunes.
        """
        if not token:
            return "Regular"
        s = re.sub(r"[^a-z]", "", token.lower())

        # Priorizar 'black' explícitamente (peso muy fuerte)
        if "black" in s:
            if "italic" in s or "oblique" in s or "bi" in s:
                return "Black Italic"
            return "Black"

        # Bold (evitar usar startswith('b') que encendía con 'black')
        if "bold" in s or "bd" in s or s == "b" or s.endswith("bd"):
            if "italic" in s or "oblique" in s or "bi" in s or s.endswith("i"):
                return "Bold Italic"
            return "Bold"

        # Italic / Oblique
        if "italic" in s or "oblique" in s or "bi" in s or s.endswith("i"):
            return "Italic"

        # Light / Thin
        if "light" in s or s.startswith("li") or s == "l":
            return "Light"
        if "thin" in s:
            return "Thin"

        # Semibold / Condensed
        if "semibold" in s or "demibold" in s or s == "sb":
            return "Semibold"
        if "condensed" in s or "cond" in s:
            return "Condensed"

        # Fallback: Title-case parts of the original token
        return (
            " ".join(w.capitalize() for w in re.split(r"[\s_\-]+", token.strip()))
            or "Regular"
        )

    def _on_font_family_change(self, family: str):
        """Callback cuando cambia la familia de fuente"""
        self.current_style.font_family = family

        # Asegurar que available_fonts esté cargado
        if not self.available_fonts:
            self.available_fonts = self._load_system_fonts()

        # Obtener estilos disponibles para esta familia
        available_styles = self.available_fonts.get(family, ["Regular"])

        # DEBUG: Imprimir estilos disponibles
        print(
            f"[FONT_FAMILY] {family} tiene {len(available_styles)} estilos: {available_styles}"
        )

        # VALIDAR qué estilos están realmente instalados antes de seleccionar
        try:
            from utils import font_index_wrapper as font_index

            fam_statuses = font_index.validate_cached_fonts(
                {family: available_styles}
            ).get(family, {})

            # Filtrar solo estilos instalados
            installed_styles = [
                s
                for s in available_styles
                if fam_statuses.get(s, "installed") == "installed"
            ]

            if not installed_styles:
                # Fallback si ningún estilo está validado como instalado
                print(
                    f"[FONT_FAMILY] ⚠️ No hay estilos instalados validados para {family}, usando lista completa"
                )
                installed_styles = available_styles
            else:
                print(f"[FONT_FAMILY] Estilos instalados: {installed_styles}")

            # Seleccionar el primer estilo instalado
            first_installed = installed_styles[0] if installed_styles else "Regular"
            self.current_style.font_style = first_installed

        except Exception as e:
            # Si falla la validación, usar el primer estilo disponible como fallback
            print(
                f"[FONT_FAMILY] Error validando estilos: {e}, usando primer estilo disponible"
            )
            self.current_style.font_style = available_styles[0]

        # Resolver ruta de fuente y cargar métrica para la nueva familia
        print(
            f"[FONT_FAMILY] Resolviendo fuente para {family}/{self.current_style.font_style}"
        )
        try:
            from utils import font_index_wrapper as font_index
            from utils import pdf_generator

            # Resolver la ruta de fuente
            font_path, status = font_index.find_font_file_for(
                family, self.current_style.font_style
            )
            font_index_ttc = 0

            if font_path and status == "installed" and Path(font_path).exists():
                if font_path.lower().endswith(".ttc"):
                    try:
                        font_index_ttc = pdf_generator._get_ttc_font_index(
                            font_path, self.current_style.font_style
                        )
                    except Exception:
                        font_index_ttc = 0

                    # EXTRAER TTC a TTF individual para Flet
                    try:
                        # Guardar índice TTC antes de actualizar font_path
                        ttc_index_original = font_index_ttc

                        extracted_path = self.gestor.extraer_ttc_individual(
                            font_path, font_index_ttc
                        )
                        if extracted_path and extracted_path.exists():
                            font_path = str(extracted_path)
                            font_index_ttc = None  # Ya no es TTC, es TTF individual
                            print(f"[FONT_FAMILY] TTC extraído: {extracted_path.name}")

                            # REGISTRAR en page.fonts para que Flet pueda usar la fuente
                            try:
                                from utils.font_manager import obtener_gestor

                                gestor = obtener_gestor()
                                familia_data = gestor.fuentes.get(family, {})
                                peso_encontrado = 400
                                italic_encontrado = False
                                for peso_key, italic_dict in familia_data.items():
                                    for italic_key, variante in italic_dict.items():
                                        if (
                                            variante.get("subfamilia")
                                            == self.current_style.font_style
                                        ):
                                            peso_encontrado = variante.get("peso", 400)
                                            italic_encontrado = variante.get(
                                                "italic", False
                                            )
                                            break
                                alias = gestor.generar_alias_flet(
                                    family, peso_encontrado, italic_encontrado
                                )
                                if _safe_page(self) is not None and hasattr(
                                    self.page, "fonts"
                                ):
                                    if self.page.fonts is None:
                                        self.page.fonts = {}
                                    self.page.fonts[alias] = str(extracted_path)
                                    self.page.update()  # Forzar carga de fuente antes de preview
                                    self.current_style.resolved_flet_alias = alias
                                    print(
                                        f"[FONT_FAMILY] Registrado en page.fonts: {alias} -> {extracted_path.name}"
                                    )
                            except Exception as reg_err:
                                logging.warning(
                                    f"[FONT_FAMILY] No se pudo registrar fuente en page.fonts: {reg_err}"
                                )
                        else:
                            logging.warning(
                                f"[FONT_FAMILY] No se pudo extraer TTC {font_path} índice {font_index_ttc}"
                            )
                    except Exception as e:
                        logging.error(
                            f"[FONT_FAMILY] Error extrayendo TTC {font_path}: {e}",
                            exc_info=True,
                        )
                else:
                    # Fuente TTF/OTF directa - también registrar en page.fonts
                    try:
                        from utils.font_manager import obtener_gestor

                        gestor = obtener_gestor()
                        familia_data = gestor.fuentes.get(family, {})
                        peso_encontrado = 400
                        italic_encontrado = False
                        for peso_key, italic_dict in familia_data.items():
                            for italic_key, variante in italic_dict.items():
                                if (
                                    variante.get("subfamilia")
                                    == self.current_style.font_style
                                ):
                                    peso_encontrado = variante.get("peso", 400)
                                    italic_encontrado = variante.get("italic", False)
                                    break
                        alias = gestor.generar_alias_flet(
                            family, peso_encontrado, italic_encontrado
                        )
                        if _safe_page(self) is not None and hasattr(self.page, "fonts"):
                            if self.page.fonts is None:
                                self.page.fonts = {}
                            self.page.fonts[alias] = str(font_path)
                            self.page.update()  # Forzar carga de fuente antes de preview
                            self.current_style.resolved_flet_alias = alias
                            print(
                                f"[FONT_FAMILY] Registrado TTF/OTF en page.fonts: {alias} -> {Path(font_path).name}"
                            )
                    except Exception as reg_err:
                        logging.warning(
                            f"[FONT_FAMILY] No se pudo registrar fuente TTF/OTF en page.fonts: {reg_err}"
                        )

                # Guardar datos de resolución en current_style
                self.current_style.resolved_font_path = font_path
                self.current_style.resolved_font_index = font_index_ttc
                self.current_style.resolved_status = status

                # Cargar métrica para esta fuente si hay cache disponible
                print(
                    f"[FONT_FAMILY] Intentando cargar métricas: cache={hasattr(self, 'font_metrics_cache')}, cache_not_none={self.font_metrics_cache is not None if hasattr(self, 'font_metrics_cache') else False}"
                )
                if hasattr(self, "font_metrics_cache") and self.font_metrics_cache:
                    try:
                        print(
                            f"[FONT_FAMILY] Llamando font_metrics_cache.get_metrics({font_path}, {self.current_style.font_size}, {font_index_ttc})"
                        )
                        metric = self.font_metrics_cache.get_metrics(
                            str(font_path), self.current_style.font_size, font_index_ttc
                        )
                        print(f"[FONT_FAMILY] Métrica devuelta: {metric}")
                        if metric:
                            # Guardar TODO el objeto metric en 'metricas' para que el viewer lo encuentre
                            self.current_style.metricas = metric.copy()
                            print(
                                f"[FONT_FAMILY] ✓ Métrica cargada y guardada en current_style.metricas"
                            )
                            print(
                                f"  baseline_top={metric.get('baseline_to_top', 0):.2f}, baseline_bottom={metric.get('baseline_to_bottom', 0):.2f}"
                            )
                            print(
                                f"  font_path en metrics: {metric.get('font_path',' N/A')}"
                            )
                        else:
                            print(f"[FONT_FAMILY] ⚠️ get_metrics devolvió None o vacío")
                    except Exception as e:
                        print(f"[FONT_FAMILY] ⚠️ Error cargando métrica: {e}")
                        import traceback

                        traceback.print_exc()
                else:
                    print(f"[FONT_FAMILY] ⚠️ Sin cache de métricas disponible")
            else:
                print(
                    f"[FONT_FAMILY] Fuente no usable para {family}/{self.current_style.font_style} (status={status}, path={font_path})"
                )
                # Limpiar resolución para evitar que otros componentes intenten usar una ruta inválida.
                self.current_style.resolved_font_path = None
                self.current_style.resolved_font_index = 0
                self.current_style.resolved_status = status or "missing"
        except Exception as e:
            print(f"[FONT_FAMILY] Error resolviendo fuente: {e}")

        # GARANTIZAR que metricas siempre existe (aunque sea vacío)
        if not hasattr(self.current_style, "metricas") or not isinstance(
            self.current_style.metricas, dict
        ):
            self.current_style.metricas = {}

        # Actualizar selección visual en la lista de familias
        if self.font_family_list and hasattr(self.font_family_list, "content"):
            for item in self.font_family_list.content.controls:
                if isinstance(item, ft.Container) and isinstance(item.content, ft.Text):
                    is_selected = item.content.value == family
                    item.bgcolor = (
                        FONDO_CALCULO_FASE_1 if is_selected else FONDO_TEXTFIELDS_COLOR
                    )
                    item.content.weight = (
                        ft.FontWeight.BOLD if is_selected else ft.FontWeight.NORMAL
                    )
                    item.update()

        self._update_font_style_list()
        self._update_preview()

        # Guardar en tiempo real
        self.profiles[self.selected_profile_index] = self.current_style.copy()

        # Notificar cambio en tiempo real para actualizar el visor
        if self.on_style_changed:
            self.on_style_changed(self.current_style, self.editing_numeradora_id)

    def _on_font_style_change(self, style: str):
        """Callback cuando cambia el estilo de fuente"""

        # Normalizar el token de estilo seleccionado a un nombre canonical
        def _canonical_style(token: str) -> str:
            if not token:
                return "Regular"
            s = re.sub(r"[^a-z]", "", token.lower())
            # Mapear patrones comunes
            if "bold" in s or "bd" in s or s.endswith("b") or s.startswith("b"):
                # comprobar si también indica italic
                if "italic" in s or "oblique" in s or "bi" in s or s.endswith("i"):
                    return "Bold Italic"
                return "Bold"
            if "italic" in s or "oblique" in s or "bi" in s or s.endswith("i"):
                return "Italic"
            if "light" in s or s.startswith("l") or s == "li":
                return "Light"
            if s == "z":
                return "Bold"
            # fallback: title-case the token
            return (
                " ".join(w.capitalize() for w in re.split(r"[\s_\-]+", token.strip()))
                or "Regular"
            )

        # Simplificado: usar el estilo exacto, sin canonical
        available_styles = (
            self.available_fonts.get(self.current_style.font_family, ["Regular"])
            if self.available_fonts
            else ["Regular"]
        )

        if style in available_styles:
            # El estilo existe exactamente - usarlo
            self.current_style.font_style = style
            print(f"[FONT_STYLE] Seleccionado estilo exacto: '{style}'")
        else:
            # El estilo no existe - usar el primero disponible
            fallback = available_styles[0] if available_styles else "Regular"
            self.current_style.font_style = fallback
            print(
                f"[FONT_STYLE] Estilo '{style}' no encontrado, usando fallback: '{fallback}'"
            )

        # Resolver ruta de fuente y cargar métrica para el nuevo estilo
        print(
            f"[FONT_STYLE] Resolviendo fuente para {self.current_style.font_family}/{self.current_style.font_style}"
        )
        try:
            from utils import font_index_wrapper as font_index
            from utils import pdf_generator

            # Resolver la ruta de fuente
            font_path, status = font_index.find_font_file_for(
                self.current_style.font_family, self.current_style.font_style
            )
            font_index_ttc = 0

            if font_path:
                if font_path.lower().endswith(".ttc"):
                    try:
                        font_index_ttc = pdf_generator._get_ttc_font_index(
                            font_path, self.current_style.font_style
                        )
                    except Exception:
                        font_index_ttc = 0

                    # EXTRAER TTC a TTF individual para Flet
                    try:
                        # Guardar índice TTC antes de actualizar font_path
                        ttc_index_original = font_index_ttc

                        extracted_path = self.gestor.extraer_ttc_individual(
                            font_path, font_index_ttc
                        )
                        if extracted_path and extracted_path.exists():
                            font_path = str(extracted_path)
                            font_index_ttc = None  # Ya no es TTC, es TTF individual
                            print(f"[FONT_STYLE] TTC extraído: {extracted_path.name}")

                            # REGISTRAR en page.fonts para que Flet pueda usar la fuente
                            try:
                                from utils.font_manager import obtener_gestor

                                gestor = obtener_gestor()
                                familia_data = gestor.fuentes.get(
                                    self.current_style.font_family, {}
                                )
                                peso_encontrado = 400
                                italic_encontrado = False
                                for peso_key, italic_dict in familia_data.items():
                                    for italic_key, variante in italic_dict.items():
                                        if (
                                            variante.get("subfamilia")
                                            == self.current_style.font_style
                                        ):
                                            peso_encontrado = variante.get("peso", 400)
                                            italic_encontrado = variante.get(
                                                "italic", False
                                            )
                                            break
                                alias = gestor.generar_alias_flet(
                                    self.current_style.font_family,
                                    peso_encontrado,
                                    italic_encontrado,
                                )
                                if _safe_page(self) is not None and hasattr(
                                    self.page, "fonts"
                                ):
                                    if self.page.fonts is None:
                                        self.page.fonts = {}
                                    self.page.fonts[alias] = str(extracted_path)
                                    self.page.update()  # Forzar carga de fuente antes de preview
                                    self.current_style.resolved_flet_alias = alias
                                    print(
                                        f"[FONT_STYLE] Registrado en page.fonts: {alias} -> {extracted_path.name}"
                                    )
                            except Exception as reg_err:
                                logging.warning(
                                    f"[FONT_STYLE] No se pudo registrar fuente en page.fonts: {reg_err}"
                                )
                        else:
                            logging.warning(
                                f"[FONT_STYLE] No se pudo extraer TTC {font_path} índice {font_index_ttc}"
                            )
                    except Exception as e:
                        logging.error(
                            f"[FONT_STYLE] Error extrayendo TTC {font_path}: {e}",
                            exc_info=True,
                        )
                else:
                    # Fuente TTF/OTF directa - también registrar en page.fonts
                    try:
                        from utils.font_manager import obtener_gestor

                        gestor = obtener_gestor()
                        familia_data = gestor.fuentes.get(
                            self.current_style.font_family, {}
                        )
                        peso_encontrado = 400
                        italic_encontrado = False
                        for peso_key, italic_dict in familia_data.items():
                            for italic_key, variante in italic_dict.items():
                                if (
                                    variante.get("subfamilia")
                                    == self.current_style.font_style
                                ):
                                    peso_encontrado = variante.get("peso", 400)
                                    italic_encontrado = variante.get("italic", False)
                                    break
                        alias = gestor.generar_alias_flet(
                            self.current_style.font_family,
                            peso_encontrado,
                            italic_encontrado,
                        )
                        if _safe_page(self) is not None and hasattr(self.page, "fonts"):
                            if self.page.fonts is None:
                                self.page.fonts = {}
                            self.page.fonts[alias] = str(font_path)
                            self.page.update()  # Forzar carga de fuente antes de preview
                            self.current_style.resolved_flet_alias = alias
                            print(
                                f"[FONT_STYLE] Registrado TTF/OTF en page.fonts: {alias} -> {Path(font_path).name}"
                            )
                    except Exception as reg_err:
                        logging.warning(
                            f"[FONT_STYLE] No se pudo registrar fuente TTF/OTF en page.fonts: {reg_err}"
                        )

                # Guardar datos de resolución en current_style
                self.current_style.resolved_font_path = font_path
                self.current_style.resolved_font_index = font_index_ttc
                self.current_style.resolved_status = status

                # Cargar métrica para esta fuente si hay cache disponible
                if hasattr(self, "font_metrics_cache") and self.font_metrics_cache:
                    try:
                        metric = self.font_metrics_cache.get_metrics(
                            str(font_path), self.current_style.font_size, font_index_ttc
                        )
                        if metric:
                            # Guardar TODO el objeto metric en 'metricas' para que el viewer lo encuentre
                            self.current_style.metricas = metric.copy()
                            print(
                                f"[FONT_STYLE] Métrica cargada: baseline_top={metric.get('baseline_to_top', 0):.2f}, baseline_bottom={metric.get('baseline_to_bottom', 0):.2f}, left={metric.get('left_bearing', 0):.2f}, width={metric.get('width', 0):.2f}"
                            )
                    except Exception as e:
                        print(f"[FONT_STYLE] Error cargando métrica: {e}")
            else:
                print(
                    f"[FONT_STYLE] No se encontró fuente para {self.current_style.font_family}/{self.current_style.font_style}"
                )
        except Exception as e:
            print(f"[FONT_STYLE] Error resolviendo fuente: {e}")

        # Persistir el estilo en el perfil activo para que el cambio sea inmediato
        if (
            self.selected_profile_index is not None
            and 0 <= self.selected_profile_index < len(self.profiles)
        ):
            self.profiles[self.selected_profile_index] = self.current_style.copy()
            self._update_profile_list()

        # Actualizar selección visual en la lista de estilos
        if self.font_style_list and hasattr(self.font_style_list, "content"):
            # Usar comparación directa de nombres de estilo (no canonical)
            for item in self.font_style_list.content.controls:
                if not isinstance(item, ft.Container):
                    continue
                item_style = getattr(item, "data", None)

                # Detectar si el content es Text (viejo) o Row (nuevo con botón)
                text_control = None
                if isinstance(item.content, ft.Text):
                    text_control = item.content
                elif (
                    hasattr(item.content, "controls")
                    and len(item.content.controls) > 0
                    and isinstance(item.content.controls[0], ft.Text)
                ):
                    text_control = item.content.controls[0]

                # Comparar directamente los nombres de estilo (exactos)
                is_selected = item_style == style
                item.bgcolor = (
                    FONDO_CALCULO_FASE_1 if is_selected else FONDO_TEXTFIELDS_COLOR
                )
                if text_control is not None:
                    text_control.weight = (
                        ft.FontWeight.BOLD if is_selected else ft.FontWeight.NORMAL
                    )
                    # No llamar a item.content.update() aquí (puede causar error si no está montado en la página)
                try:
                    item.update()
                except AssertionError:
                    # Control no añadido a página en entorno de pruebas; ignorar
                    pass

        # GARANTIZAR que metricas siempre existe (aunque sea vacío)
        if not hasattr(self.current_style, "metricas") or not isinstance(
            self.current_style.metricas, dict
        ):
            self.current_style.metricas = {}

        # DEBUG: Verificar alias antes de preview
        alias_debug = getattr(self.current_style, "resolved_flet_alias", None)
        print(f"[DEBUG] Antes de _update_preview: resolved_flet_alias={alias_debug}")

        self._update_preview()

        # Guardar en tiempo real
        self.profiles[self.selected_profile_index] = self.current_style.copy()

        # Notificar cambio en tiempo real para actualizar el visor
        if self.on_style_changed:
            self.on_style_changed(self.current_style, self.editing_numeradora_id)

    def _on_font_size_change(self, e):
        """Callback cuando cambia el tamaño de fuente"""
        normalize_decimal_input(e)
        try:
            size = max(1.0, round(float(e.control.value), 1))
            self.current_style.font_size = size

            if self.font_size_field and e.control != self.font_size_field:
                self.font_size_field.value = str(size)
                self.font_size_field.update()

            # Recargar métrica con el nuevo tamaño de fuente
            print(f"[FONT_SIZE] Tamaño cambiado a {size}pt, recargando métrica...")

            # IMPORTANTE: Primero resolver la ruta de la fuente si no está resuelta
            if (
                not hasattr(self.current_style, "resolved_font_path")
                or not self.current_style.resolved_font_path
            ):
                try:
                    from utils import font_index_wrapper as font_index
                    from utils import pdf_generator

                    p, status = font_index.find_font_file_for(
                        self.current_style.font_family, self.current_style.font_style
                    )
                    self.current_style.resolved_font_path = p
                    self.current_style.resolved_status = status
                    self.current_style.resolved_font_index = 0
                    if p and p.lower().endswith(".ttc"):
                        try:
                            self.current_style.resolved_font_index = (
                                pdf_generator._get_ttc_font_index(
                                    p, self.current_style.font_style
                                )
                            )
                        except Exception:
                            self.current_style.resolved_font_index = 0
                    print(f"[FONT_SIZE] Ruta resuelta: {p}")
                except Exception as ex:
                    print(f"[FONT_SIZE] ⚠️ No se pudo resolver fuente: {ex}")

            # Ahora cargar métricas
            if (
                hasattr(self.current_style, "resolved_font_path")
                and self.current_style.resolved_font_path
            ):
                if hasattr(self, "font_metrics_cache") and self.font_metrics_cache:
                    try:
                        metric = self.font_metrics_cache.get_metrics(
                            str(self.current_style.resolved_font_path),
                            size,  # NOTA: get_metrics ignora esto ahora (siempre 12pt)
                            getattr(self.current_style, "resolved_font_index", 0),
                        )
                        if metric:
                            # Guardar TODO el objeto metric en 'metricas' para que el viewer lo encuentre
                            self.current_style.metricas = metric.copy()
                            print(
                                f"[FONT_SIZE] Métrica recargada: baseline_top={metric.get('baseline_to_top', 0):.2f}, baseline_bottom={metric.get('baseline_to_bottom', 0):.2f}, left={metric.get('left_bearing', 0):.2f}, width={metric.get('width', 0):.2f}"
                            )
                    except Exception as ex:
                        print(
                            f"[FONT_SIZE] ⚠️ No se pudo cargar métrica para {size}pt: {ex} (continuando sin métrica)"
                        )

            # GARANTIZAR que metricas siempre existe (aunque sea vacío)
            if not hasattr(self.current_style, "metricas") or not isinstance(
                self.current_style.metricas, dict
            ):
                self.current_style.metricas = {}

            # Guardar en tiempo real en memoria
            # Reemplazar el perfil COMPLETO (sin usar copy() que pierde metricas)
            self.profiles[self.selected_profile_index] = self.current_style

            # Actualizar el perfil en el gestor de texto
            if self.on_style_changed:
                self.on_style_changed(self.current_style)

            # Redibujar el viewer en tiempo real
            if self.viewer_callback:
                self.viewer_callback._redraw_all()

            self._update_preview()
        except ValueError:
            pass

    def _on_letter_spacing_change(self, e):
        """Callback cuando cambia el interletraje (letter_spacing)"""
        normalize_decimal_input(e)
        try:
            value = round(float(e.control.value), 1)
            self.current_style.letter_spacing = value

            # Re-sincronizar el campo siempre: el redondeo puede dejar el campo
            # con un valor no redondeado, que rompería el siguiente incremento.
            if self.letter_spacing_field is not None:
                display = str(value)
                if self.letter_spacing_field.value != display:
                    self.letter_spacing_field.value = display
                    self.letter_spacing_field.update()

            # Guardar en tiempo real en memoria
            self.profiles[self.selected_profile_index] = self.current_style

            if self.on_style_changed:
                self.on_style_changed(self.current_style)

            if self.viewer_callback:
                self.viewer_callback._redraw_all()

            self._update_preview()
        except ValueError:
            pass

    def _reopen_settings_dialog(self):
        """Reabre el diálogo de ajustes de texto después de cerrar el color picker."""
        reopen_dialog(self.page, self.dialog)

    def _on_number_color_click(self):
        """Abre el selector de color para números"""
        self._color_target = "number"
        # El padre queda abierto debajo (el picker se apila encima) — no pop_dialog
        self.color_picker_dialog.open(
            self.current_style.number_color,
            self.current_style.number_color_cmyk,
            getattr(
                self.current_style, "number_color_space", self.current_style.color_space
            ),
            self.current_style.number_color_name,
            getattr(self.current_style, "number_color_tint", 100.0),
        )

    def _on_prefix_suffix_color_click(self):
        """Abre el selector de color para prefijo/sufijo"""
        self._color_target = "prefix_suffix"
        # Mostrar el color actual según el modo
        mode = self.color_apply_mode_value
        if mode == "prefix":
            current_color = self.current_style.prefix_color
            current_cmyk = self.current_style.prefix_color_cmyk
            current_name = self.current_style.prefix_color_name
            current_tint = getattr(self.current_style, "prefix_color_tint", 100.0)
            current_space = getattr(
                self.current_style, "prefix_color_space", self.current_style.color_space
            )
        elif mode == "suffix":
            current_color = self.current_style.suffix_color
            current_cmyk = self.current_style.suffix_color_cmyk
            current_name = self.current_style.suffix_color_name
            current_tint = getattr(self.current_style, "suffix_color_tint", 100.0)
            current_space = getattr(
                self.current_style, "suffix_color_space", self.current_style.color_space
            )
        else:  # "both"
            current_color = self.current_style.prefix_color
            current_cmyk = self.current_style.prefix_color_cmyk
            current_name = self.current_style.prefix_color_name
            current_tint = getattr(self.current_style, "prefix_color_tint", 100.0)
            current_space = getattr(
                self.current_style, "prefix_color_space", self.current_style.color_space
            )
        # El padre queda abierto debajo (el picker se apila encima) — no pop_dialog
        self.color_picker_dialog.open(
            current_color, current_cmyk, current_space, current_name, current_tint
        )

    def _on_color_selected(
        self,
        rgb_color: str,
        cmyk_color: tuple,
        color_space: str,
        color_name: str = "",
        tint: float = 100.0,
    ):
        """Callback cuando se selecciona un color en el ColorPickerDialog"""
        self._last_color_pick = (rgb_color, cmyk_color, color_name, tint, color_space)
        # Actualizar color_space legacy para compatibilidad
        self.current_style.color_space = color_space

        if self._color_target == "number":
            self.current_style.number_color = rgb_color
            self.current_style.number_color_cmyk = cmyk_color
            self.current_style.number_color_name = color_name
            self.current_style.number_color_tint = tint
            self.current_style.number_color_space = color_space
            print(
                f"DEBUG: _on_color_selected called! space={color_space}, base={rgb_color}, tint={tint}"
            )
            if hasattr(self, "number_color_button") and self.number_color_button:
                # Mostrar color tintado en el botón (para SPOT), base para otros
                _display = self._tinted_display_color(rgb_color, tint, color_space)
                self.number_color_button.bgcolor = _display
                self.number_color_button.update()

            # Sincronizar colores dependientes según el modo, para mantener la regla
            # "el que no este seleccionado usa el color de las numeradoras"
            mode = getattr(self, "color_apply_mode_value", "both")
            if mode == "prefix":
                # Sufijo sigue al número
                self.current_style.suffix_color = rgb_color
                self.current_style.suffix_color_cmyk = cmyk_color
                self.current_style.suffix_color_name = color_name
                self.current_style.suffix_color_tint = tint
                self.current_style.suffix_color_space = color_space
            elif mode == "suffix":
                # Prefijo sigue al número
                self.current_style.prefix_color = rgb_color
                self.current_style.prefix_color_cmyk = cmyk_color
                self.current_style.prefix_color_name = color_name
                self.current_style.prefix_color_tint = tint
                self.current_style.prefix_color_space = color_space

        elif self._color_target == "prefix_suffix":
            mode = self.color_apply_mode_value
            num_color = self.current_style.number_color
            num_cmyk = self.current_style.number_color_cmyk
            num_name = self.current_style.number_color_name
            num_space = getattr(
                self.current_style, "number_color_space", self.current_style.color_space
            )

            # Actualizar el picker con el nuevo color
            if (
                hasattr(self, "prefix_suffix_color_button")
                and self.prefix_suffix_color_button
            ):
                _display = self._tinted_display_color(rgb_color, tint, color_space)
                self.prefix_suffix_color_button.bgcolor = _display
                self.prefix_suffix_color_button.update()

            # Aplicar el color según el modo seleccionado
            if mode == "prefix":
                # Prefijo usa el nuevo color, Sufijo usa color de número
                self.current_style.prefix_color = rgb_color
                self.current_style.prefix_color_cmyk = cmyk_color
                self.current_style.prefix_color_name = color_name
                self.current_style.prefix_color_tint = tint
                self.current_style.prefix_color_space = color_space
                self.current_style.suffix_color = num_color
                self.current_style.suffix_color_cmyk = num_cmyk
                self.current_style.suffix_color_name = num_name
                self.current_style.suffix_color_space = num_space

            elif mode == "suffix":
                # Sufijo usa el nuevo color, Prefijo usa color de número
                self.current_style.suffix_color = rgb_color
                self.current_style.suffix_color_cmyk = cmyk_color
                self.current_style.suffix_color_name = color_name
                self.current_style.suffix_color_tint = tint
                self.current_style.suffix_color_space = color_space
                self.current_style.prefix_color = num_color
                self.current_style.prefix_color_cmyk = num_cmyk
                self.current_style.prefix_color_name = num_name
                self.current_style.prefix_color_space = num_space

            else:  # "both"
                # Ambos usan el nuevo color
                self.current_style.prefix_color = rgb_color
                self.current_style.prefix_color_cmyk = cmyk_color
                self.current_style.prefix_color_name = color_name
                self.current_style.prefix_color_tint = tint
                self.current_style.prefix_color_space = color_space
                self.current_style.suffix_color = rgb_color
                self.current_style.suffix_color_cmyk = cmyk_color
                self.current_style.suffix_color_name = color_name
                self.current_style.suffix_color_tint = tint
                self.current_style.suffix_color_space = color_space

        self._update_preview()
        # Guardar cambios en el perfil actual y notificar al viewer para que aplique inmediatamente
        try:
            self.profiles[self.selected_profile_index] = self.current_style.copy()
        except Exception:
            pass
        if self.on_style_changed:
            self.on_style_changed(self.current_style, self.editing_numeradora_id)
        # No forzamos guardar en preferencias por cada cambio; el usuario puede usar "Guardar en Preferencias" cuando quiera.

    def _on_prefix_change(self, e):
        """Callback cuando cambia el prefijo"""
        self.current_style.prefix = e.control.value
        self._update_preview()

        # Guardar en tiempo real
        self.profiles[self.selected_profile_index] = self.current_style

        # Notificar cambio
        if self.on_style_changed:
            self.on_style_changed(self.current_style, self.editing_numeradora_id)

    def _on_suffix_change(self, e):
        """Callback cuando cambia el sufijo"""
        self.current_style.suffix = e.control.value
        self._update_preview()

        # Guardar en tiempo real
        self.profiles[self.selected_profile_index] = self.current_style

        # Notificar cambio
        if self.on_style_changed:
            self.on_style_changed(self.current_style, self.editing_numeradora_id)

    def _on_mask_change(self, e):
        """Callback cuando cambia la máscara"""
        self.current_style.mask = e.control.value
        self._update_preview()

        # Guardar en tiempo real
        self.profiles[self.selected_profile_index] = self.current_style.copy()

        # Notificar cambio en tiempo real para actualizar el visor
        if self.on_style_changed:
            self.on_style_changed(self.current_style, self.editing_numeradora_id)

    def _on_mask_placeholder_change(self, e):
        """Callback cuando cambia el placeholder de máscara"""
        value = e.control.value
        if len(value) > 1:
            value = value[0]
            e.control.value = value
            e.control.update()
        self.current_style.mask_placeholder = value if value else "*"

        # Actualizar el campo UI para asegurar sincronización
        if self.mask_placeholder_field and self.mask_placeholder_field != e.control:
            self.mask_placeholder_field.value = self.current_style.mask_placeholder
            self.mask_placeholder_field.update()

        self._update_preview()

        # Guardar en tiempo real
        self.profiles[self.selected_profile_index] = self.current_style.copy()

        # Notificar cambio en tiempo real para actualizar el visor
        if self.on_style_changed:
            self.on_style_changed(self.current_style, self.editing_numeradora_id)

    def _on_sample_number_change(self, e):
        """Callback cuando cambia el número de muestra"""
        try:
            # Limpiar posibles separadores antes de parsear
            val_raw = e.control.value
            # Guardar exactamente lo que escribió el usuario (mantener ceros iniciales)
            self.preview_sample_number_raw = val_raw

            val_str = val_raw.replace(".", "").replace(",", "").replace(" ", "")
            if not val_str:
                return

            number = int(val_str)
            if number >= 0:
                # Valor numérico para cálculos/preview
                self.preview_sample_number = number
                self._update_preview()
        except ValueError:
            pass

    def _on_digit_placeholder_change(self, e):
        """Callback cuando cambia el digit placeholder"""
        try:
            value = int(e.control.value)
            if 0 <= value <= 9:
                self.current_style.digit_placeholder = value
                # Sincronizar mask_placeholder con el dígito
                self.current_style.mask_placeholder = str(value)
                self._update_preview()
                # Guardar en tiempo real
                self.profiles[self.selected_profile_index] = self.current_style.copy()
                # Notificar cambio en tiempo real
                if self.on_style_changed:
                    self.on_style_changed(
                        self.current_style, self.editing_numeradora_id
                    )
        except ValueError:
            pass

    def _apply_thousands_separator(self, number_str: str, separator_type: str) -> str:
        """
        Aplica el separador de millares al número.

        Args:
            number_str: Número como string
            separator_type: Tipo de separador ('normal', 'punto', 'espacio', 'coma')

        Returns:
            Número formateado con separadores
        """
        if separator_type == "normal" or not number_str:
            return number_str

        # Solo aplicar si el valor numérico es >= 1000
        try:
            val = float(number_str)
            if abs(val) < 1000:
                return number_str
        except ValueError:
            pass

        # Determinar el separador
        separators = {"punto": ".", "espacio": " ", "coma": ","}
        separator = separators.get(separator_type, "")

        if not separator:
            return number_str

        # Aplicar separador de millares de derecha a izquierda
        # Solo a la parte entera (antes del punto decimal si existe)
        parts = number_str.split(".")
        integer_part = parts[0]

        # Insertar separador cada 3 dígitos desde la derecha
        result = []
        for i, digit in enumerate(reversed(integer_part)):
            if i > 0 and i % 3 == 0:
                result.append(separator)
            result.append(digit)

        formatted_integer = "".join(reversed(result))

        # Reconstruir con parte decimal si existe
        if len(parts) > 1:
            return formatted_integer + "." + parts[1]
        else:
            return formatted_integer

    def _inject_thousands_separator(self, text: str, separator_type: str) -> str:
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

        # Contar dígitos totales para saber si poner separadores
        digits_only = [c for c in text if c.isdigit()]
        if not digits_only:
            return text

        pending_separator = False
        for i, char in enumerate(reversed(text)):
            if char.isdigit():
                digit_count += 1
                result.append(char)

                # Si hemos llegado a un múltiplo de 3 y quedan más dígitos por venir
                if digit_count > 0 and digit_count % 3 == 0:
                    # Verificar si quedan más dígitos a la IZQUIERDA
                    remaining_left = text[: len(text) - 1 - i]
                    if any(c.isdigit() for c in remaining_left):
                        result.append(sep_char)
            else:
                result.append(char)

        return "".join(reversed(result))

    def _apply_mask(
        self, number: int, mask: str, separator_type: str = "normal"
    ) -> str:
        """
        Aplica máscara simplificada (placeholder '0') y luego inyecta separadores.
        Input: number (int), mask (str pattern), separator_type.
        """
        # Retornar el número como entero (o string de dígitos) para que el viewer aplique máscara
        return number

    def _update_preview(self):
        """Actualiza la vista previa del texto con tres colores usando spans"""
        # Si el control de vista previa no está inicializado aún, salir
        if not hasattr(self, "preview_text") or self.preview_text is None:
            return

        # DEBUG: Información del estilo actual
        print(f"[PREVIEW DEBUG] ====== _update_preview llamado ======")
        print(f"[PREVIEW DEBUG] current_style id: {id(self.current_style)}")
        print(f"[PREVIEW DEBUG] font_family: {self.current_style.font_family}")
        print(f"[PREVIEW DEBUG] font_style: {self.current_style.font_style}")
        print(
            f"[PREVIEW DEBUG] resolved_flet_alias: {getattr(self.current_style, 'resolved_flet_alias', 'NO EXISTE')}"
        )
        print(
            f"[PREVIEW DEBUG] resolved_font_path: {getattr(self.current_style, 'resolved_font_path', 'NO EXISTE')}"
        )
        if (
            self.selected_profile_index is not None
            and 0 <= self.selected_profile_index < len(self.profiles)
        ):
            profile = self.profiles[self.selected_profile_index]
            print(
                f"[PREVIEW DEBUG] profile[{self.selected_profile_index}] id: {id(profile)}"
            )
            print(
                f"[PREVIEW DEBUG] profile.resolved_flet_alias: {getattr(profile, 'resolved_flet_alias', 'NO EXISTE')}"
            )
        print(f"[PREVIEW DEBUG] ========================================")

        # Número de ejemplo
        example_number = self.preview_sample_number

        # Obtener configuración de separador
        separator_type = (
            self.current_style.thousands_separator
            if hasattr(self.current_style, "thousands_separator")
            else "normal"
        )
        mask = self.current_style.mask

        # Aplicar formato completo (máscara y/o separadores)
        # La lógica de máscara y separador se ha movido al viewer, aquí solo se prepara el número
        # para que el viewer lo procese.
        # Para la vista previa, necesitamos simularlo.

        str_number = str(example_number)

        if not mask:
            # Sin máscara, solo aplicar separador estándar
            formatted = self._apply_thousands_separator(str_number, separator_type)
        else:
            # 1. Contar slots '0'
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
                    formatted = self._inject_thousands_separator(
                        full_result, separator_type
                    )
                else:
                    formatted = full_result
            except (ValueError, TypeError):
                formatted = full_result

        # Mapear estilos a propiedades de Flet
        style_lower = self.current_style.font_style.lower()

        # Primero intentar mapeo directo para fuentes con nomenclatura W# (Hiragino, etc.)
        import re

        w_match = re.search(r"w(\d)", style_lower)
        if w_match:
            w_number = int(w_match.group(1))
            # Mapear W0-W9 a FontWeight
            weight_map = {
                0: ft.FontWeight.W_100,
                1: ft.FontWeight.W_200,
                2: ft.FontWeight.W_300,
                3: ft.FontWeight.W_300,
                4: ft.FontWeight.W_400,
                5: ft.FontWeight.W_500,
                6: ft.FontWeight.W_600,
                7: ft.FontWeight.W_700,
                8: ft.FontWeight.W_800,
                9: ft.FontWeight.W_900,
            }
            weight = weight_map.get(w_number, ft.FontWeight.NORMAL)
        # Si no es W#, usar detección por palabras clave
        elif "black" in style_lower:
            weight = ft.FontWeight.W_900
        elif "bold" in style_lower or "negrita" in style_lower:
            weight = ft.FontWeight.BOLD
        elif "semibold" in style_lower or "medium" in style_lower:
            weight = ft.FontWeight.W_600
        elif "light" in style_lower or "fina" in style_lower:
            weight = ft.FontWeight.W_300
        elif "thin" in style_lower or "ultralight" in style_lower:
            weight = ft.FontWeight.W_100
        else:
            weight = ft.FontWeight.NORMAL

        # Determinar italic/oblique
        is_italic = (
            "italic" in style_lower
            or "oblique" in style_lower
            or "cursiva" in style_lower
            or "oblicua" in style_lower
        )

        # Construir spans para texto con múltiples colores
        text_spans = []

        # Determinar qué font_family usar: alias Flet si está disponible, sino nombre de familia
        font_family_to_use = (
            getattr(self.current_style, "resolved_flet_alias", None)
            or self.current_style.font_family
        )

        # DEBUG
        print(
            f"[DEBUG PREVIEW] font_family_to_use={font_family_to_use}, resolved_flet_alias={getattr(self.current_style, 'resolved_flet_alias', None)}"
        )

        # Si hay alias Flet, el .ttf ya contiene el estilo - NO especificar weight/italic
        # Si no hay alias, construir dict con weight/italic
        use_alias = (
            hasattr(self.current_style, "resolved_flet_alias")
            and self.current_style.resolved_flet_alias
        )

        # Construir spans POR CARÁCTER para texto con múltiples colores.
        # OJO: Flutter aplica letterSpacing DESPUÉS de cada carácter (incluido el
        # último de cada span y el último del texto). Con un span por segmento se
        # generarían huecos no deseados en los límites prefijo→número,
        # número→sufijo y tras el último carácter. Con un span por carácter solo
        # se aplica letter_spacing cuando el siguiente carácter pertenece al
        # MISMO segmento (n-1 huecos por segmento), igual que en el viewer.
        number_start = len(self.current_style.prefix)
        number_end = number_start + len(formatted)
        preview_display = (
            f"{self.current_style.prefix}{formatted}{self.current_style.suffix}"
        )

        for i, ch in enumerate(preview_display):
            if i < number_start:
                style_kwargs = {
                    "size": self.current_style.font_size,
                    "color": self._tinted_display_color(
                        self.current_style.prefix_color,
                        getattr(self.current_style, "prefix_color_tint", 100.0),
                        getattr(
                            self.current_style,
                            "prefix_color_space",
                            self.current_style.color_space,
                        ),
                    ),
                    "font_family": font_family_to_use,
                }
            elif i < number_end:
                style_kwargs = {
                    "size": self.current_style.font_size,
                    "color": self._tinted_display_color(
                        self.current_style.number_color,
                        getattr(self.current_style, "number_color_tint", 100.0),
                        getattr(
                            self.current_style,
                            "number_color_space",
                            self.current_style.color_space,
                        ),
                    ),
                    "font_family": font_family_to_use,
                }
            else:
                style_kwargs = {
                    "size": self.current_style.font_size,
                    "color": self._tinted_display_color(
                        self.current_style.suffix_color,
                        getattr(self.current_style, "suffix_color_tint", 100.0),
                        getattr(
                            self.current_style,
                            "suffix_color_space",
                            self.current_style.color_space,
                        ),
                    ),
                    "font_family": font_family_to_use,
                }
            if not use_alias:
                style_kwargs["weight"] = weight
                style_kwargs["italic"] = is_italic
            # letter_spacing SOLO si hay un carácter siguiente en el mismo
            # segmento; en los límites prefijo→número y número→sufijo va
            # prefix_suffix_spacing (misma semántica que el viewer y el PDF)
            _char_ls = 0.0
            if i < len(preview_display) - 1:
                if i == number_start - 1 or i == number_end - 1:
                    if self.current_style.prefix_suffix_spacing != 0:
                        _char_ls = self.current_style.prefix_suffix_spacing
                    elif self.current_style.letter_spacing != 0:
                        _char_ls = self.current_style.letter_spacing
                elif self.current_style.letter_spacing != 0:
                    _char_ls = self.current_style.letter_spacing
            style_kwargs["letter_spacing"] = _char_ls
            text_spans.append(ft.TextSpan(ch, ft.TextStyle(**style_kwargs)))

        # Actualizar el widget de vista previa
        self.preview_text.spans = text_spans
        self.preview_text.size = self.current_style.font_size

        print(f"[PREVIEW] Total spans creados: {len(text_spans)}")
        print(
            f"[PREVIEW] page.fonts tiene '{font_family_to_use}': {font_family_to_use in self.page.fonts if self.page.fonts else False}"
        )
        if self.page.fonts and font_family_to_use in self.page.fonts:
            print(f"[PREVIEW] Ruta registrada: {self.page.fonts[font_family_to_use]}")

        # Solo actualizar si los controles ya están en la página
        if _safe_page(self.preview_text):
            self.preview_text.update()

    def _create_new_profile(self, e):
        """Crea un nuevo perfil"""
        # Crear nombre único
        base_name = t("Nuevo perfil")
        counter = 1
        new_name = base_name

        while any(p.name == new_name for p in self.profiles):
            new_name = f"{base_name} {counter}"
            counter += 1

        # Crear nuevo perfil basado en el actual
        new_profile = self.current_style.copy()
        new_profile.id = str(uuid.uuid4())
        new_profile.name = new_name

        self.profiles.append(new_profile)
        self.selected_profile_index = len(self.profiles) - 1
        self.current_style = new_profile.copy()

        self._update_profile_list()
        self._load_style_to_ui()

        # Notificar cambio para actualizar dropdown en UI principal
        if self.on_style_changed:
            self.on_style_changed(self.current_style)

    def _on_refresh_fonts_click(self, e):
        """Callback del botón de recarga de fuentes"""
        print("[REFRESH_FONTS] 🔄 Iniciando recarga de fuentes del sistema...")

        try:
            # Mostrar indicador visual (cambiar icono temporalmente)
            self.btn_refresh_fonts.icon = ft.Icons.HOURGLASS_EMPTY
            self.btn_refresh_fonts.disabled = True
            self.page.update()

            # Recargar fuentes
            self._refresh_system_fonts()

            # Actualizar listas de familias y estilos en UI
            self._rebuild_font_lists()

            # Recargar métricas para los perfiles
            try:
                print("[REFRESH_FONTS] Recargando métricas de fuentes...")
                fuentes_sistema = {}
                if self.available_fonts:
                    for family, styles in self.available_fonts.items():
                        fuentes_sistema[family] = (
                            list(styles)
                            if isinstance(styles, (list, set))
                            else [styles]
                        )

                if (
                    not hasattr(self, "font_metrics_cache")
                    or self.font_metrics_cache is None
                ):
                    self.font_metrics_cache = FontMetricsCache()

                cargar_metricas_perfiles(
                    self.profiles,
                    fuentes_sistema,
                    self.font_metrics_cache,
                    default_profile=None,
                )
                print("[REFRESH_FONTS] ✓ Métricas recargadas")
            except Exception as me:
                print(f"[REFRESH_FONTS] ⚠️ Error recargando métricas: {me}")

            # Restaurar icono y habilitar botón
            self.btn_refresh_fonts.icon = ft.Icons.REFRESH
            self.btn_refresh_fonts.disabled = False

            # Mostrar mensaje de éxito
            num_familias = len(self.available_fonts) if self.available_fonts else 0
            print(
                f"[REFRESH_FONTS] ✓ Recarga completada: {num_familias} familias disponibles"
            )

            # Opcional: Mostrar notificación temporal en UI
            snack = ft.SnackBar(
                content=ft.Text(
                    t("✓ Fuentes actualizadas: {0} familias disponibles").format(
                        num_familias
                    ),
                    color=SNACKBAR_COLOR_TEXTO,
                ),
                bgcolor=SUCCESS_COLOR,
                duration=2000,
            )
            self.page.show_dialog(snack)

            self.page.update()

        except Exception as ex:
            print(f"[REFRESH_FONTS] ❌ Error recargando fuentes: {ex}")
            import traceback

            traceback.print_exc()

            # Restaurar botón en caso de error
            self.btn_refresh_fonts.icon = ft.Icons.REFRESH
            self.btn_refresh_fonts.disabled = False

            # Mostrar error en UI
            error_snack = ft.SnackBar(
                content=ft.Text(t("❌ Error al recargar fuentes: {0}").format(str(ex)), color=SNACKBAR_COLOR_TEXTO),
                bgcolor=SNACKBAR_COLOR_ERROR,
                duration=3000,
            )
            self.page.show_dialog(error_snack)

            self.page.update()

    def _rebuild_font_lists(self):
        """Reconstruye las listas de familias y estilos en la UI tras recarga"""
        try:
            # Reconstruir lista de familias
            if self.font_family_listview and self.available_fonts:
                font_families = sorted(self.available_fonts.keys(), key=str.lower)
                _sel = self.current_style.font_family
                self.font_family_listview.controls = [
                    ft.Container(
                        content=ft.Text(
                            family,
                            size=12,
                            color=TEXTOS_FASE_1_COLOR,
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
                        height=30,
                    )
                    for family in font_families
                ]
                self.font_family_listview.update()

            # Reconstruir lista de estilos para la familia actual
            self._update_font_style_list()

            print("[REBUILD_FONT_LISTS] ✓ Listas de fuentes reconstruidas")
        except Exception as e:
            print(f"[REBUILD_FONT_LISTS] ❌ Error: {e}")

    def _delete_profile(self, e):
        """Elimina el perfil seleccionado"""
        # No permitir eliminar el perfil <Default>
        if self.profiles[self.selected_profile_index].name == "<Default>":
            print("[DELETE] No se puede eliminar el perfil <Default>")
            return

        if len(self.profiles) <= 1:
            print("[DELETE] No se puede eliminar el último perfil")
            return

        deleted_style_name = self.profiles[self.selected_profile_index].name
        print(f"[DELETE] Iniciando eliminación de perfil '{deleted_style_name}'")

        def confirm_delete(ev):
            print(f"[DELETE] Confirmado - Eliminando perfil '{deleted_style_name}'")

            if popup_container in self.dialog_root_stack.controls:
                self.dialog_root_stack.controls.remove(popup_container)
            self.dialog_root_stack.update()

            # Eliminar el perfil
            del self.profiles[self.selected_profile_index]
            self.selected_profile_index = max(0, self.selected_profile_index - 1)
            self.current_style = self.profiles[self.selected_profile_index].copy()
            self._update_profile_list()
            self._load_style_to_ui()

            # Notificar el cambio para actualizar las numeradoras que usaban este estilo
            deleted_style = TextStyle(
                id="",
                name=deleted_style_name,
                font_family="Helvetica",
                font_style="Regular",
                font_size=12.0,
                color="#000000",
                letter_spacing=0.0,
                prefix_suffix_spacing=0.0,
                prefix="",
                suffix="",
                mask="0000",
                mask_placeholder="0",
                digit_placeholder=0,
            )

            if self.on_style_changed:
                print(f"[DELETE] Notificando eliminación de '{deleted_style_name}'")
                self.on_style_changed(deleted_style, None)
            else:
                print(f"[DELETE] ADVERTENCIA: on_style_changed es None")

        def cancel_delete(ev):
            if popup_container in self.dialog_root_stack.controls:
                self.dialog_root_stack.controls.remove(popup_container)
            self.dialog_root_stack.update()
            print(f"[DELETE] Cancelado")

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
                        t(
                            "¿Eliminar el perfil '{0}'?\n\nLas numeradoras que lo usen cambiarán a '<Default>'."
                        ).format(deleted_style_name),
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

    def _show_help(self, e):
        """Muestra ayuda sobre el uso de máscaras"""
        help_dialog = ft.AlertDialog(
            title=ft.Text(t("Ayuda - Máscaras de Formato")),
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.Text(
                            t(
                                "Las máscaras permiten formatear números con un patrón específico."
                            ),
                            size=13,
                        ),
                        ft.Divider(height=10),
                        ft.Text(t("Ejemplos:"), weight=ft.FontWeight.BOLD, size=13),
                        ft.Text(t("• Máscara: ******-*"), size=12),
                        ft.Text(t("  Número: 1234 → Resultado: ***123-4"), size=12),
                        ft.Text(t("• Máscara: ****/**/**"), size=12),
                        ft.Text(t("  Número: 123456 → Resultado: **12/34/56"), size=12),
                        ft.Divider(height=10),
                        ft.Text(
                            t(
                                "El carácter placeholder (por defecto '*') se reemplaza con dígitos del número de derecha a izquierda."
                            ),
                            size=12,
                        ),
                    ],
                    tight=True,
                    spacing=5,
                ),
                width=400,
            ),
            actions=[
                ft.TextButton(
                    t("Cerrar"),
                    on_click=lambda e: self.page.pop_dialog(),
                )
            ],
        )

        self.page.show_dialog(help_dialog)

    def open_settings_dialog(self, numeradora_id=None, style_name=None):
        """
        Abre el diálogo de configuración de texto

        Args:
            numeradora_id: ID de la numeradora (si se abre desde doble clic)
            style_name: Nombre del estilo a cargar (si se abre desde numeradora)
        """
        print("[TEXT_DIALOG] Iniciando apertura del diálogo...")

        # Guardar el ID de la numeradora para actualizar al guardar
        self.editing_numeradora_id = numeradora_id

        # Si se proporciona un style_name, buscar y seleccionar ese perfil
        if style_name:
            for i, profile in enumerate(self.profiles):
                if profile.name == style_name:
                    self.selected_profile_index = i
                    self.current_style = profile.copy()
                    print(
                        f"[TEXT_DIALOG] Cargando estilo '{style_name}' de numeradora {numeradora_id}"
                    )
                    break

        print(
            "[TEXT_DIALOG] Comprobando cambios en fuentes del sistema..."
        )

        try:
            if self.gestor.check_font_system_changed():
                print("[TEXT_DIALOG] Cambios detectados, refrescando fuentes...")
                self._refresh_system_fonts()
            else:
                pass  # ponytail: skip noisy "no changes" log
        except Exception as e:
            print(f"[TEXT_DIALOG] Error refrescando fuentes: {e}")
            if self.available_fonts is None:
                self.available_fonts = self._load_system_fonts()

        # Registrar en Flet las fuentes necesarias para los perfiles (extracción temporal si es TTC)
        try:
            from utils import font_ttc, font_cache

            # Directorio para extracciones en sesión (persistente en 'extracted')
            extracted_dir = font_cache.extracted_dir(font_cache.get_config_dir())
            extracted_dir.mkdir(parents=True, exist_ok=True)

            for profile in self.profiles:
                # Si ya tenemos alias, saltar
                if getattr(profile, "resolved_flet_alias", None):
                    continue

                # Preferir ruta resuelta si existe
                ruta = getattr(profile, "resolved_font_path", None)
                idx = getattr(profile, "resolved_font_index", 0) or 0

                if not ruta:
                    continue

                try:
                    safe_name = (profile.font_family or "font").replace(" ", "")
                    out_name = f"{safe_name}_idx{idx}.ttf"
                    out_path = str(extracted_dir / out_name)

                    if ruta.lower().endswith((".ttc", ".otc")):
                        ok = font_ttc.extract_subfont_to_file(ruta, idx, out_path)
                        if not ok:
                            continue
                    else:
                        # si es ttf/otf, usar directamente
                        out_path = ruta

                    # Registrar alias en Flet (si page disponible)
                    if _safe_page(self) is not None:
                        alias = f"{safe_name}__{idx}"
                        try:
                            # Registrar sólo si no existe
                            if alias not in getattr(self.page, "fonts", {}):
                                self.page.fonts[alias] = out_path
                                # No forzar page.update() excesivo aquí; se hará al abrir el diálogo
                        except Exception:
                            # Algunos entornos no exponen page.fonts; ignorar
                            pass
                        profile.resolved_flet_alias = alias
                        # Persist extracted mapping so future opens don't re-extract
                        try:
                            cache_dir = font_cache.get_config_dir()
                            font_cache.add_extracted_entry(
                                cache_dir, ruta, int(idx), out_path
                            )
                        except Exception:
                            pass
                except Exception as ex:
                    print(
                        f"[TEXT_DIALOG] Error registrando fuente para perfil {profile.name}: {ex}"
                    )
        except Exception as e:
            print(f"[TEXT_DIALOG] Error recargando métricas: {e}")
            self.font_metrics_cache = None

        # Merge SOLO resolved_* de profiles[selected] → current_style (sin re-copy
        # completo: no tocar font_family — un re-copy forzado marcaba "Fuente no
        # instalada" si profiles[selected] tenía una familia fuera de available_fonts).
        # Evita que on_cancel pise el perfil ya resuelto con la copia stale de apertura.
        try:
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
                        setattr(self.current_style, _attr, getattr(src, _attr))
        except Exception as e:
            print(f"[TEXT_DIALOG] Error mergeando resolved_* en open: {e}")

        # Panel izquierdo - Lista de perfiles
        self.btn_new_profile = ft.IconButton(
            icon=ft.Icons.ADD,
            tooltip=t("Nuevo perfil"),
            icon_size=20,
            icon_color=TEXTO_COLOR_GENERICO,
            on_click=self._create_new_profile,
        )

        self.btn_delete_profile = ft.IconButton(
            icon=ft.Icons.DELETE,
            tooltip=t("Eliminar perfil"),
            icon_size=20,
            icon_color=TEXTO_COLOR_GENERICO,
            on_click=self._delete_profile,
        )

        # Nuevo: Botón para recargar fuentes del sistema
        self.btn_refresh_fonts = ft.IconButton(
            icon=ft.Icons.REFRESH,
            tooltip=t("Recargar fuentes del sistema"),
            icon_size=20,
            icon_color=TEXTO_COLOR_GENERICO,
            on_click=self._on_refresh_fonts_click,
        )

        self.profile_list = ft.ListView(
            controls=[
                self._create_profile_list_item(i, profile)
                for i, profile in enumerate(self.profiles)
            ],
            spacing=0,
            expand=True,
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
                ],
                spacing=8,
            ),
            width=250,
            padding=10,
            bgcolor=None,
            border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
            border_radius=8,
        )

        # Panel derecho - Configuración
        # Sección: Fuente
        font_families = sorted(self.available_fonts.keys(), key=str.lower)

        _sel = self.current_style.font_family
        self.font_family_listview = ft.ListView(
            controls=[
                ft.Container(
                    content=ft.Text(
                        family,
                        size=12,
                        color=TEXTOS_FASE_1_COLOR,
                        weight=ft.FontWeight.BOLD if family == _sel else ft.FontWeight.NORMAL,
                    ),
                    padding=ft.Padding.symmetric(horizontal=8, vertical=4),
                    bgcolor=(
                        FONDO_CALCULO_FASE_1
                        if family == _sel
                        else FONDO_TEXTFIELDS_COLOR
                    ),
                    on_click=lambda e, f=family: self._on_font_family_change(f),
                    key=f"font_family_{family}",  # Agregar key para scroll_to
                    height=25,  # Altura fija para cálculo de scroll preciso
                )
                for family in font_families
            ],
            spacing=0,
        )

        self.font_family_list = ft.Container(
            content=self.font_family_listview,
            height=140,
            bgcolor=FONDO_TEXTFIELDS_COLOR,
        )

        self.font_style_list = ft.Container(
            content=ft.ListView(
                controls=[],
                spacing=0,
            ),
            height=140,
            bgcolor=FONDO_TEXTFIELDS_COLOR,
        )

        self.font_size_field = self._create_textfield(
            label=t("Tamaño"),
            value=str(self.current_style.font_size),
            width=90,
            on_change=self._on_font_size_change,
        )

        self.letter_spacing_field = self._create_textfield(
            label=t("Interletraje"),
            value=str(self.current_style.letter_spacing),
            width=90,
            on_change=self._on_letter_spacing_change,
        )

        # Botones de color
        self.number_color_button = ft.Container(
            width=40,
            height=40,
            bgcolor=self.current_style.number_color,
            border_radius=4,
            border=ft.Border.all(2, BORDE_TEXTFIELDS_COLOR),
            on_click=lambda e: self._on_number_color_click(),
            ink=True,
            tooltip=t("Color de números"),
        )

        self.prefix_suffix_color_button = ft.Container(
            width=40,
            height=40,
            bgcolor=self.current_style.prefix_color,
            border_radius=4,
            border=ft.Border.all(2, BORDE_TEXTFIELDS_COLOR),
            on_click=lambda e: self._on_prefix_suffix_color_click(),
            ink=True,
            tooltip=t("Color de prefijo/sufijo"),
        )

        # Dropdown para seleccionar a qué aplicar el color (prefijo/sufijo)
        self.color_apply_mode_value = "both"
        color_mode_text = ft.Text(
            t("Ambos"),
            size=11,
            color=DROPDOWN_TEXT_STYLE_COLOR,
            no_wrap=True,
        )

        def on_color_mode_change(text_value):
            mode_map = {
                t("Prefijo"): "prefix",
                t("Sufijo"): "suffix",
                t("Ambos"): "both",
            }
            new_mode = mode_map.get(text_value, "both")
            self.color_apply_mode_value = new_mode
            color_mode_text.value = text_value
            color_mode_text.update()

            # Aplicar la lógica de distribución de colores según el modo seleccionado
            # El color del picker NO cambia, pero sí A QUÉ se aplica
            last_pick = getattr(self, "_last_color_pick", None)
            if last_pick:
                picker_color, picker_cmyk, picker_name, picker_tint, picker_space = (
                    last_pick
                )
            else:
                from ui.color_picker import hex2rgb, rgb_to_cmyk

                picker_color = self.prefix_suffix_color_button.bgcolor
                picker_cmyk = rgb_to_cmyk(*hex2rgb(picker_color))
                picker_name = ""
                picker_tint = 100.0
                picker_space = "RGB"
            num_color = self.current_style.number_color
            num_cmyk = self.current_style.number_color_cmyk
            num_name = self.current_style.number_color_name
            num_tint = self.current_style.number_color_tint
            num_space = self.current_style.number_color_space

            def _apply(seg, color, cmyk, name, tint, space):
                setattr(self.current_style, f"{seg}_color", color)
                setattr(self.current_style, f"{seg}_color_cmyk", cmyk)
                setattr(self.current_style, f"{seg}_color_name", name)
                setattr(self.current_style, f"{seg}_color_tint", tint)
                setattr(self.current_style, f"{seg}_color_space", space)

            if new_mode == "prefix":
                # Prefijo usa el color del picker, Sufijo usa color de número
                _apply("prefix", picker_color, picker_cmyk, picker_name, picker_tint, picker_space)
                _apply("suffix", num_color, num_cmyk, num_name, num_tint, num_space)

            elif new_mode == "suffix":
                # Sufijo usa el color del picker, Prefijo usa color de número
                _apply("suffix", picker_color, picker_cmyk, picker_name, picker_tint, picker_space)
                _apply("prefix", num_color, num_cmyk, num_name, num_tint, num_space)

            else:  # "both"
                # Ambos usan el color del picker
                _apply("prefix", picker_color, picker_cmyk, picker_name, picker_tint, picker_space)
                _apply("suffix", picker_color, picker_cmyk, picker_name, picker_tint, picker_space)

            self._update_preview()

            # Guardar en tiempo real
            self.profiles[self.selected_profile_index] = self.current_style.copy()

            # Notificar cambio
            if self.on_style_changed:
                self.on_style_changed(self.current_style, self.editing_numeradora_id)

        def on_mode_item_click(e):
            on_color_mode_change(e.control.content)

        self.color_apply_mode = ft.Container(
            width=100,
            height=20,
            padding=ft.Padding(6, 0, 2, 0),
            border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
            border_radius=3,
            bgcolor=FONDO_TEXTFIELDS_COLOR,
            content=ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=0,
                controls=[
                    color_mode_text,
                    ft.PopupMenuButton(
                        content=ft.Icon(
                            ft.Icons.ARROW_DROP_DOWN,
                            size=16,
                            color=DROPDOWN_TRAILING_ICON_COLOR,
                        ),
                        padding=0,
                        icon_size=16,
                        splash_radius=8,
                        menu_position=ft.PopupMenuPosition.UNDER,
                        bgcolor=DROPDOWN_FONDO_MENU_COLOR,
                        shadow_color=BORDE_TEXTFIELDS_COLOR,
                        items=[
                            ft.PopupMenuItem(
                                content=t("Prefijo"), on_click=on_mode_item_click
                            ),
                            ft.PopupMenuItem(
                                content=t("Sufijo"), on_click=on_mode_item_click
                            ),
                            ft.PopupMenuItem(
                                content=t("Ambos"), on_click=on_mode_item_click
                            ),
                        ],
                    ),
                ],
            ),
        )

        color_nums_container = ft.Container(
            content=ft.Column(
                [
                    ft.Text(
                        t("Números"),
                        size=11,
                        color=TEXTOS_FASE_1_COLOR,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    self.number_color_button,
                ],
                spacing=6,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            expand=True,
            padding=6,
        )

        color_prefix_suffix_container = ft.Container(
            content=ft.Column(
                [
                    ft.Text(
                        t("Prefijo/Sufijo"),
                        size=11,
                        color=TEXTOS_FASE_1_COLOR,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    self.prefix_suffix_color_button,
                ],
                spacing=6,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            expand=True,
            padding=6,
        )

        left_panel.content.controls.extend([
            ft.Divider(height=1, color=BORDE_TEXTFIELDS_COLOR),
            ft.Row(
                [
                    color_nums_container,
                    color_prefix_suffix_container,
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            ft.Row(
                [self.color_apply_mode],
                alignment=ft.MainAxisAlignment.CENTER,
            ),
        ])

        # Inicializar ColorPickerDialog (si no estaba creado ya)
        if self.color_picker_dialog is None:
            self.color_picker_dialog = ColorPickerDialog(
                page=self.page,
                on_color_selected=self._on_color_selected,
                on_dismissed=self._reopen_settings_dialog,
            )
            # Propagar spots acumulados que llegaron antes de abrir el diálogo
            if self.extracted_spot_colors:
                self.color_picker_dialog.set_extracted_spots(self.extracted_spot_colors)
        self._color_target = "number"  # "number" o "prefix_suffix"

        font_section = ft.Container(
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
                                    self.font_family_list,
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
                                    self.font_style_list,
                                ],
                                spacing=4,
                                expand=True,
                            ),
                        ],
                        spacing=10,
                    ),
                    ft.Row(
                        [
                            self.font_size_field,
                            self._create_increment_buttons(
                                self.font_size_field, self._on_font_size_change
                            ),
                            self.letter_spacing_field,
                            self._create_increment_buttons(
                                self.letter_spacing_field,
                                self._on_letter_spacing_change,
                                step=0.1,
                            ),
                        ],
                        spacing=10,
                        alignment=ft.MainAxisAlignment.START,
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

        # Sección: Prefijo/Sufijo
        self.prefix_field = self._create_textfield(
            label=t("Prefijo"),
            value=self.current_style.prefix,
            width=180,
            on_change=self._on_prefix_change,
        )

        self.suffix_field = self._create_textfield(
            label=t("Sufijo"),
            value=self.current_style.suffix,
            width=180,
            on_change=self._on_suffix_change,
        )

        # COMENTADO: Fritz no soporta interletraje (prefix_suffix_spacing)
        # self.prefix_suffix_spacing_field = self._create_textfield(
        #     label="Interletraje",
        #     value=str(self.current_style.prefix_suffix_spacing),
        #     width=70,
        #     on_change=self._on_prefix_suffix_spacing_change,
        # )
        self.prefix_suffix_spacing_field = None

        self.sample_number_field = self._create_textfield(
            label=t("Nº Muestra"),
            value=str(self.preview_sample_number),
            width=90,
            on_change=self._on_sample_number_change,
        )

        # Dropdown para separador de millares
        current_sep = (
            self.current_style.thousands_separator
            if hasattr(self.current_style, "thousands_separator")
            else "normal"
        )
        self.thousands_separator_text = ft.Text(
            t(current_sep),
            size=12,
            color=TEXTO_COLOR_GENERICO,
            no_wrap=True,
        )

        def on_thousands_separator_change(data_value):
            self.current_style.thousands_separator = data_value
            self.thousands_separator_text.value = t(data_value)
            self.thousands_separator_text.update()
            self._update_preview()
            # Guardar cambios en perfil y notificar viewer para aplicar formato en vivo
            try:
                self.profiles[self.selected_profile_index] = self.current_style.copy()
            except Exception:
                pass
            if self.on_style_changed:
                self.on_style_changed(self.current_style, self.editing_numeradora_id)

        def on_separator_item_click(e):
            on_thousands_separator_change(e.control.data)

        self.thousands_separator_dropdown = ft.Container(
            width=95,
            height=32,
            padding=ft.Padding(8, 0, 2, 0),
            border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
            border_radius=3,
            bgcolor=FONDO_TEXTFIELDS_COLOR,
            content=ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=0,
                controls=[
                    self.thousands_separator_text,
                    ft.PopupMenuButton(
                        content=ft.Icon(
                            ft.Icons.ARROW_DROP_DOWN,
                            size=16,
                            color=TEXTO_COLOR_GENERICO,
                        ),
                        padding=0,
                        icon_size=16,
                        splash_radius=8,
                        menu_position=ft.PopupMenuPosition.UNDER,
                        bgcolor=FONDO_TEXTFIELDS_COLOR,
                        items=[
                            ft.PopupMenuItem(
                                data="normal",
                                content=t("normal"),
                                on_click=on_separator_item_click,
                            ),
                            ft.PopupMenuItem(
                                data="punto",
                                content=t("punto"),
                                on_click=on_separator_item_click,
                            ),
                            ft.PopupMenuItem(
                                data="espacio",
                                content=t("espacio"),
                                on_click=on_separator_item_click,
                            ),
                            ft.PopupMenuItem(
                                data="coma",
                                content=t("coma"),
                                on_click=on_separator_item_click,
                            ),
                        ],
                    ),
                ],
            ),
        )

        # Botón de ayuda para el separador de millares y máscara
        def show_separator_help(e):
            help_text = t("HELP_NUMBER_FORMAT")
            help_rule_label = t("HELP_NUMBER_FORMAT_RULE_LABEL")
            help_rule_after = t("HELP_NUMBER_FORMAT_RULE_AFTER")

            table_rows = [
                ("000", "1", "001", t("HELP_NUMBER_FORMAT_TABLE_ROW_1_EXPLANATION")),
                (
                    "000",
                    "1000",
                    "1.000",
                    t("HELP_NUMBER_FORMAT_TABLE_ROW_2_EXPLANATION"),
                ),
                (
                    "000000",
                    "1",
                    "000001",
                    t("HELP_NUMBER_FORMAT_TABLE_ROW_3_EXPLANATION"),
                ),
                (
                    "000000",
                    "1000001",
                    "1.000.001",
                    t("HELP_NUMBER_FORMAT_TABLE_ROW_4_EXPLANATION"),
                ),
                (
                    "0-0-0",
                    "1",
                    "0-0-1",
                    t("HELP_NUMBER_FORMAT_TABLE_ROW_5_EXPLANATION"),
                ),
                (
                    "0-0-0",
                    "1000",
                    "1.0-0-0",
                    t("HELP_NUMBER_FORMAT_TABLE_ROW_6_EXPLANATION"),
                ),
            ]

            table_header_style = ft.TextStyle(
                weight=ft.FontWeight.W_600,
                color=TEXTO_COLOR_GENERICO,
                size=13,
            )
            table_cell_style = ft.TextStyle(color=TEXTO_COLOR_GENERICO, size=13)

            # Ancho: STRETCH en los padres da constraints tight al DataTable
            # (Flutter). expand=True en DataTable estiraría la ALTURA de las
            # filas → tabla deforme; solo se quiere ancho full y alto intrínseco.
            table = ft.DataTable(
                border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
                border_radius=8,
                vertical_lines=ft.BorderSide(1, BORDE_TEXTFIELDS_COLOR),
                horizontal_lines=ft.BorderSide(1, BORDE_TEXTFIELDS_COLOR),
                heading_row_color=ft.Colors.with_opacity(0.08, TEXTO_COLOR_GENERICO),
                column_spacing=24,
                horizontal_margin=12,
                columns=[
                    ft.DataColumn(
                        ft.Text(
                            t("HELP_NUMBER_FORMAT_TABLE_COL_MASK"),
                            style=table_header_style,
                        )
                    ),
                    ft.DataColumn(
                        ft.Text(
                            t("HELP_NUMBER_FORMAT_TABLE_COL_NUMBER"),
                            style=table_header_style,
                        )
                    ),
                    ft.DataColumn(
                        ft.Text(
                            t("HELP_NUMBER_FORMAT_TABLE_COL_RESULT"),
                            style=table_header_style,
                        )
                    ),
                    ft.DataColumn(
                        ft.Text(
                            t("HELP_NUMBER_FORMAT_TABLE_COL_EXPLANATION"),
                            style=table_header_style,
                        )
                    ),
                ],
                rows=[
                    ft.DataRow(
                        cells=[
                            ft.DataCell(ft.Text(mask, style=table_cell_style)),
                            ft.DataCell(ft.Text(number, style=table_cell_style)),
                            ft.DataCell(ft.Text(result, style=table_cell_style)),
                            ft.DataCell(ft.Text(explanation, style=table_cell_style)),
                        ]
                    )
                    for mask, number, result, explanation in table_rows
                ],
            )

            help_sheet = ft.BottomSheet(
                content=ft.Container(
                    content=ft.Column(
                        [
                            ft.Container(
                                content=ft.Column(
                                    [
                                        ft.Text(
                                            t("Ayuda: Máscara y Formato de Números"),
                                            weight=ft.FontWeight.BOLD,
                                            size=16,
                                            color=TEXTO_COLOR_GENERICO,
                                        ),
                                        ft.Divider(
                                            height=1,
                                            color=BORDE_TEXTFIELDS_COLOR,
                                        ),
                                    ],
                                    spacing=6,
                                    tight=True,
                                ),
                            ),
                            ft.Container(
                                padding=ft.Padding.only(top=10),
                                content=ft.Column(
                                    [
                                        ft.Text(
                                            selectable=True,
                                            size=13,
                                            no_wrap=False,
                                            spans=[
                                                ft.TextSpan(
                                                    help_text,
                                                    style=ft.TextStyle(
                                                        color=TEXTO_COLOR_GENERICO,
                                                        size=13,
                                                    ),
                                                ),
                                                ft.TextSpan(
                                                    help_rule_label,
                                                    style=ft.TextStyle(
                                                        color=TEXTO_COLOR_GENERICO,
                                                        size=13,
                                                        weight=ft.FontWeight.BOLD,
                                                    ),
                                                ),
                                                ft.TextSpan(
                                                    help_rule_after,
                                                    style=ft.TextStyle(
                                                        color=TEXTO_COLOR_GENERICO,
                                                        size=13,
                                                    ),
                                                ),
                                            ],
                                        ),
                                        ft.Container(
                                            height=20
                                        ),  # Espacio entre texto y tabla
                                        ft.Text(
                                            t("HELP_NUMBER_FORMAT_TABLE_TITLE"),
                                            weight=ft.FontWeight.W_600,
                                            size=14,
                                            color=TEXTO_COLOR_GENERICO,
                                        ),
                                        ft.Container(
                                            content=table,
                                            bgcolor=FONDO_TEXTFIELDS_COLOR,
                                            border=ft.Border.all(
                                                1, BORDE_TEXTFIELDS_COLOR
                                            ),
                                            border_radius=8,
                                            padding=10,
                                        ),
                                    ],
                                    spacing=10,
                                    tight=True,
                                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                                ),
                            ),
                        ],
                        spacing=10,
                        tight=True,
                        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                    ),
                    # Aumentar espacio inferior para que el texto no quede pegado al borde
                    padding=ft.Padding.only(left=20, right=20, top=20, bottom=20),
                    # Añadir margen inferior extra para separar visualmente del borde
                    margin=ft.Margin.only(bottom=100),
                    # Full width del sheet; el alto lo da el contenido (scrollable)
                    expand=True,
                    # bgcolor=FONDO_ALERT_DIALOG,
                ),
                open=True,
                # Quita el cap a media altura: el sheet crece con el contenido
                scrollable=True,
                bgcolor=FONDO_ALERT_DIALOG,
            )
            # Flet 1.0: BottomSheet es DialogControl → show_dialog (overlay queda
            # debajo del AlertDialog y la ayuda no se veía).
            self.page.show_dialog(help_sheet)

        mask_help_button = ft.IconButton(
            icon=ft.Icons.HELP_OUTLINE,
            icon_color=TEXTO_COLOR_GENERICO,
            icon_size=20,
            style=ft.ButtonStyle(
                shape=ft.CircleBorder(),
                padding=ft.Padding.all(4),
                bgcolor=FONDO_SECCIONES,
            ),
            tooltip=t("Ayuda sobre la máscara y el formato"),
            on_click=show_separator_help,
        )

        separator_help_button = ft.IconButton(
            icon=ft.Icons.HELP_OUTLINE,
            icon_size=20,
            tooltip=t("Ayuda sobre el separador de millares"),
            on_click=show_separator_help,
        )

        prefix_suffix_section = ft.Container(
            content=ft.Column(
                [
                    ft.Text(
                        t("Prefijo y Sufijo"),
                        size=14,
                        weight=ft.FontWeight.BOLD,
                        color=TEXTO_COLOR_GENERICO,
                    ),
                    ft.Divider(height=1, color=BORDE_TEXTFIELDS_COLOR),
                    ft.Row(
                        [
                            self.prefix_field,
                            self.suffix_field,
                            # COMENTADO: Fritz no soporta interletraje
                            # self.prefix_suffix_spacing_field,
                            # self._create_increment_buttons(self.prefix_suffix_spacing_field, self._on_prefix_suffix_spacing_change),
                            self.sample_number_field,
                        ],
                        spacing=10,
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

        # Sección: Máscara
        self.mask_field = self._create_textfield(
            label=t("Máscara (ej: 000-000)"),
            value=self.current_style.mask,
            width=150,
            on_change=self._on_mask_change,
        )

        # ELIMINADO: Placeholder configurable y su ayuda
        # Ahora el placeholder es implícitamente '0'

        mask_section = ft.Container(
            content=ft.Column(
                [
                    ft.Text(
                        t("Máscara de Formato"),
                        size=14,
                        weight=ft.FontWeight.BOLD,
                        color=TEXTO_COLOR_GENERICO,
                    ),
                    ft.Divider(height=1, color=BORDE_TEXTFIELDS_COLOR),
                    ft.Row(
                        [
                            self.mask_field,
                            mask_help_button,
                            ft.Text(
                                t("Caracter miles:"),
                                size=11,
                                color=TEXTO_COLOR_GENERICO,
                            ),
                            self.thousands_separator_dropdown,
                        ],
                        spacing=3,
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

        # Sección: Vista previa
        self.preview_text = ft.Text(
            "",
            size=self.current_style.font_size,
            no_wrap=False,
            text_align=ft.TextAlign.CENTER,
        )

        self._update_preview()
        preview_section = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Container(expand=True),
                    self.preview_text,
                    ft.Container(expand=True),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=0,
            ),
            padding=5,
            # bgcolor=FONDO_SECCIONES,
            bgcolor=ft.Colors.WHITE,  # Fondo blanco para resaltar la vista previa
            border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
            border_radius=8,
            expand=True,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
        )

        right_panel = ft.Column(
            [
                font_section,
                prefix_suffix_section,
                mask_section,
                preview_section,
            ],
            spacing=10,
            expand=True,
        )

        # Contenido base del diálogo
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
                alignment=ft.MainAxisAlignment.START,
                vertical_alignment=ft.CrossAxisAlignment.STRETCH,
            ),
            width=1250,  # Mismo tamaño que diálogo VT/códigos
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
            # Guardar el estado del perfil actual antes de cerrar (por seguridad)
            try:
                old = self.profiles[self.selected_profile_index]
                new = self.current_style.copy()
                # No pisar resolved_* si la copia viene stale (fuente missing al
                # copiar en open) y el perfil ya resuelto tiene alias/ruta.
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
                self.current_style = new
            except Exception:
                pass

            # Notificar cambio para que el viewer aplique los estilos recientes
            if self.on_style_changed:
                self.on_style_changed(self.current_style, self.editing_numeradora_id)

            print(f"[DIALOG] Volviendo (cerrando diálogo)")
            self.page.pop_dialog()
            # Redibujar el viewer con las nuevas métricas
            if self.viewer_callback:
                self.viewer_callback._redraw_all()

        def on_save_as_default(e):
            """Guarda todos los perfiles actuales como default en preferencias globales"""
            # IMPORTANTE: Asegurar que el perfil actual está actualizado en la lista
            self.profiles[self.selected_profile_index] = self.current_style
            # Sincronizar número de muestra raw desde el campo (por si no hubo on_change)
            try:
                if hasattr(self, "sample_number_field") and self.sample_number_field:
                    self.preview_sample_number_raw = str(self.sample_number_field.value)
            except Exception:
                pass

            # Guardar en preferencias globales (para nuevos trabajos)
            self.save_to_preferences()
            print(f"[DIALOG] Perfiles guardados como plantilla en preferencias")

            # Mostrar confirmación
            snack = ft.SnackBar(
                content=ft.Text(
                    t("✓ Perfiles guardados como plantilla para nuevos trabajos"),
                    color=SNACKBAR_COLOR_TEXTO,
                ),
                bgcolor=SUCCESS_COLOR,
                duration=2000,
            )
            self.page.show_dialog(snack)
            # NOTA: NO cerramos el diálogo, solo guardamos y mostramos confirmación

        # Crear diálogo
        self.dialog = ft.AlertDialog(
            modal=True,  # Permitir interacción con el viewer mientras el diálogo está abierto
            inset_padding=0,  # Mismo patrón que diálogo VT: sin inset, el Stack fija 1250×700
            title_padding=ft.Padding(10, 20, 10, 8),
            title=ft.Container(
                content=ft.Row(
                    [
                        ft.Container(width=40),
                        ft.Text(
                            t("Ajustes de numeradoras"),
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
                            tooltip=t("Guía de numeradoras"),
                            width=40,
                            height=40,
                            on_click=lambda e: abrir_guia(
                                self.page, "elementos/numeros"
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
                    width=180,
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
            content_padding=ft.Padding(20, 10, 20, 10),
            actions_padding=ft.Padding(20, 0, 20, 15),
        )

        print("[TEXT_DIALOG] Diálogo creado, abriendo...")
        # Basura de aperturas anteriores (p.ej. tras color picker) bloquearía show_dialog
        purge_stale_dialog(self.page, self.dialog)
        # Abrir diálogo con show_dialog (Flet 1.0: síncrono, sin update() explícito)
        try:
            self.page.show_dialog(self.dialog)
        except RuntimeError:
            print("[TEXT_DIALOG] show_dialog: ya estaba en la pila (ignorado)")
        # Asegurar que el campo Nº Muestra muestre la representación raw al abrir
        try:
            if hasattr(self, "sample_number_field") and self.sample_number_field:
                self.sample_number_field.value = str(self.preview_sample_number_raw)
        except Exception:
            pass

        # Actualizar lista de estilos después de que el diálogo esté en la página
        self._update_font_style_list()

        print("[TEXT_DIALOG] Diálogo abierto correctamente")
        # Hacer scroll a la familia de fuente seleccionada
        import asyncio

        async def do_scroll_async():
            # Esperar a que el diálogo esté completamente renderizado
            await asyncio.sleep(0.3)

            if hasattr(self, "font_family_listview") and self.font_family_listview:
                if self.current_style.font_family in self.available_fonts:
                    try:
                        # Obtener lista de familias ORDENADA (igual que la lista visual)
                        font_families = sorted(
                            self.available_fonts.keys(), key=str.lower
                        )
                        selected_index = font_families.index(
                            self.current_style.font_family
                        )

                        # Usar la altura fija que definimos en el Container (30px)
                        item_height = 25
                        visible_height = 140

                        # Centrar el item en la lista:
                        target_offset = (
                            (selected_index * item_height)
                            - (visible_height / 2)
                            + (item_height / 2)
                        )

                        # Limitar offset
                        total_items = len(self.font_family_listview.controls)
                        max_offset = max(
                            0, (total_items * item_height) - visible_height
                        )
                        safe_offset = max(0, min(target_offset, max_offset))

                        print(f"[SCROLL] Font: {self.current_style.font_family}")
                        print(
                            f"[SCROLL] Index: {selected_index}, Offset: {safe_offset:.1f}px (Centered)"
                        )

                        # scroll_to() solo acepta: offset, delta, scroll_key, duration, curve
                        await self.font_family_listview.scroll_to(
                            offset=safe_offset, duration=300
                        )
                        print(f"[SCROLL] Ejecutado correctamente")
                    except Exception as e:
                        print(f"[SCROLL] Error: {e}")
                        # import traceback
                        # traceback.print_exc()

                    await asyncio.sleep(0.15)
                    self.page.update()

        # Ejecutar scroll después de un breve delay
        self.page.run_task(do_scroll_async)

        print("[TEXT_DIALOG] Diálogo abierto correctamente")

    def get_current_style(self) -> TextStyle:
        """Retorna el estilo actual"""
        return self.current_style.copy()

    def set_style(self, style: TextStyle):
        """Establece un estilo"""
        self.current_style = style.copy()

        # Buscar si existe en los perfiles
        for i, profile in enumerate(self.profiles):
            if profile.id == style.id:
                self.selected_profile_index = i
                break

        if self.dialog and self.dialog.open:
            self._load_style_to_ui()

    def set_extracted_spots(self, spots: list):
        """
        Recibe los colores spot extraídos del PDF cargado.
        Los almacena y los propaga al ColorPickerDialog si ya existe.
        Si el dialog aún no fue creado, los spots se propagarán al crearlo.
        """
        self.extracted_spot_colors = spots or []
        if self.color_picker_dialog is not None:
            self.color_picker_dialog.set_extracted_spots(self.extracted_spot_colors)

    def get_profiles(self) -> list[TextStyle]:
        """Retorna todos los perfiles"""
        profiles = [p.copy() for p in self.profiles]

        # DEBUG: Verificar que los perfiles tienen resolved_font_path
        print("\n" + "=" * 80)
        print("DEBUG get_profiles() - PERFILES DEVUELTOS")
        print("=" * 80)
        for i, profile in enumerate(profiles):
            print(f"\nPerfil {i}: {profile.name}")
            print(f"  font_family: {profile.font_family}")
            print(f"  font_style: {profile.font_style}")
            print(f"  font_size: {profile.font_size}")
            print(
                f"  resolved_font_path: {getattr(profile, 'resolved_font_path', 'NO EXISTE')}"
            )
            print(
                f"  resolved_font_index: {getattr(profile, 'resolved_font_index', 'NO EXISTE')}"
            )
            print(
                f"  resolved_flet_alias: {getattr(profile, 'resolved_flet_alias', 'NO EXISTE')}"
            )
        print("=" * 80 + "\n")

        return profiles

    def get_profile(self, name: str) -> TextStyle:
        """Retorna un perfil por nombre o id.

        Si no se encuentra, devuelve el estilo actual o el perfil <Default>.
        Esta función evita AttributeError en clientes que aún llaman a
        `get_profile(name)` en lugar de `get_profiles()`.
        """
        if not name:
            return self.get_current_style()
        # Buscar coincidencia exacta por nombre o id
        for p in self.profiles:
            if p.name == name or p.id == name:
                return p.copy()
        # Buscar coincidencia parcial por nombre (case-insensitive)
        for p in self.profiles:
            if name.lower() in p.name.lower():
                return p.copy()
        # Fallback al estilo actual o al default
        return self.get_current_style()

    def load_profiles(self, profiles: list[TextStyle]):
        """Carga una lista de perfiles"""
        if not profiles:
            self.profiles = [TextStyle.create_default()]
        else:
            self.profiles = [p.copy() for p in profiles]

        self.selected_profile_index = 0
        self.current_style = self.profiles[0].copy()

        if self.dialog and self.dialog.open:
            self._update_profile_list()
            self._load_style_to_ui()

    def get_config(self) -> dict:
        """
        Retorna la configuración de perfiles para guardar en el archivo de trabajo
        IMPORTANTE: Esto se guarda en el archivo .pagenumber del proyecto
        """
        # Filtrar campos transitorios antes de serializar
        profiles_data = []
        for profile in self.profiles:
            d = asdict(profile)
            # Eliminar TODOS los campos transient/resolved (no deben persistirse)
            d.pop("resolved_font_path", None)
            d.pop("resolved_font_index", None)
            d.pop("resolved_status", None)
            d.pop("metricas", None)
            d.pop("resolved_flet_alias", None)
            profiles_data.append(d)

        return {
            "profiles": profiles_data,
            "selected_profile_index": self.selected_profile_index,
            # Guardar únicamente el valor numérico en la configuración del proyecto
            "preview_sample_number": self.preview_sample_number,
        }

    def load_config(self, config: dict):
        """
        Carga configuración desde un diccionario (al cargar proyecto)
        IMPORTANTE: Esto sobrescribe los perfiles actuales con los del proyecto
        """
        if not config:
            self.profiles = [TextStyle.create_default()]
            self.selected_profile_index = 0
            self.current_style = self.profiles[0].copy()
            self.preview_sample_number = 1001
            return

        # Cargar perfiles desde el diccionario
        profiles_data = config.get("profiles", [])
        if profiles_data:
            # Migración: añadir campos per-segment color_space si faltan
            for pd in profiles_data:
                old_sp = pd.get("color_space", "RGB")
                if "number_color_space" not in pd:
                    pd["number_color_space"] = old_sp
                if "prefix_color_space" not in pd:
                    pd["prefix_color_space"] = old_sp
                if "suffix_color_space" not in pd:
                    pd["suffix_color_space"] = old_sp
            self.profiles = [
                TextStyle(**profile_dict) for profile_dict in profiles_data
            ]
        else:
            self.profiles = [TextStyle.create_default()]

        # Cargar índice seleccionado
        self.selected_profile_index = config.get("selected_profile_index", 0)

        # Cargar número de muestra
        self.preview_sample_number = config.get("preview_sample_number", 1234)

        # Validar índice
        if self.selected_profile_index >= len(self.profiles):
            self.selected_profile_index = 0

        self.current_style = self.profiles[self.selected_profile_index].copy()

        # Resolver rutas de fuentes (cache en memoria) para evitar búsquedas repetidas
        try:
            self._resolve_profiles()
        except Exception:
            pass

        # Actualizar UI si el diálogo está abierto
        if self.dialog and self.dialog.open:
            self._update_profile_list()
            self._load_style_to_ui()

        print(
            f"[TEXT_STYLE] Configuración cargada desde proyecto: {len(self.profiles)} perfiles"
        )

    def _migrate_fonts_to_prefs(self):
        """Copia las fuentes de los perfiles actuales de fonts_temp a fonts_prefs.

        Se llama desde save_to_preferences() para que las fuentes persistan
        entre sesiones. Retorna un dict {profile_index: new_path} con las rutas
        migradas en fonts_prefs.
        """
        migrated = {}
        try:
            from utils import font_cache, font_ttc
            from pathlib import Path
            import shutil

            cache_dir = font_cache.get_config_dir()
            prefs_dir = font_cache.prefs_dir(cache_dir)
            prefs_dir.mkdir(parents=True, exist_ok=True)
            extracted_dir = font_cache.extracted_dir(cache_dir)

            for i, profile in enumerate(self.profiles):
                resolved = getattr(profile, "resolved_font_path", None)
                if not resolved:
                    continue
                resolved_p = Path(resolved)
                if not resolved_p.exists():
                    continue

                # Si ya está en fonts_prefs, no hace falta mover
                try:
                    if resolved_p.parent.resolve() == prefs_dir.resolve():
                        migrated[i] = str(resolved_p)
                        print(
                            f"[SAVE_PREFS] Perfil {i} ({profile.name}): fuente ya en fonts_prefs ✓"
                        )
                        continue
                except Exception:
                    pass

                # Generar nombre descriptivo para fonts_prefs
                fam = (profile.font_family or "font").replace(" ", "")
                style = (profile.font_style or "Regular").replace(" ", "")
                dest_name = f"{fam}_{style}.ttf"
                dest_path = prefs_dir / dest_name

                try:
                    shutil.copy2(str(resolved_p), str(dest_path))
                    migrated[i] = str(dest_path)
                    print(
                        f"[SAVE_PREFS] Perfil {i} ({profile.name}): copiado {resolved_p.name} → fonts_prefs/{dest_name}"
                    )

                    # Actualizar extracted_map en font_cache para apuntar a fonts_prefs
                    original_ruta = None
                    idx = getattr(profile, "resolved_font_index", 0) or 0
                    # Intentar obtener la ruta original del TTC/OTC
                    try:
                        from utils import font_index_wrapper as font_index

                        p, _ = font_index.find_font_file_for(
                            profile.font_family, profile.font_style
                        )
                        if p:
                            original_ruta = p
                    except Exception:
                        pass
                    if original_ruta:
                        font_cache.add_extracted_entry(
                            cache_dir, original_ruta, int(idx), str(dest_path)
                        )

                except Exception as ex:
                    print(
                        f"[SAVE_PREFS] ⚠️ Error copiando fuente para perfil {i}: {ex}"
                    )

        except Exception as e:
            print(f"[SAVE_PREFS] ⚠️ Error migrando fuentes a fonts_prefs: {e}")
            import traceback

            traceback.print_exc()
        return migrated

    def save_to_preferences(self):
        """
        Guarda los perfiles actuales en las preferencias globales de la aplicación
        IMPORTANTE: Esto se guarda en preferences.json y se usa como plantilla para nuevos trabajos
        Solo se ejecuta cuando el usuario hace clic en "Guardar como Default"
        """
        from utils.preferences import (
            save_text_style_profiles,
            save_preference,
        )

        # PASO 1: Migrar fuentes de fonts_temp a fonts_prefs
        migrated = self._migrate_fonts_to_prefs()

        # PASO 2: Serializar perfiles incluyendo resolved_font_path migrado
        profiles_data = []
        for i, profile in enumerate(self.profiles):
            d = asdict(profile)
            # Eliminar campos transient que NO deben persistirse
            d.pop("resolved_status", None)
            d.pop("metricas", None)
            d.pop("resolved_flet_alias", None)

            # Persistir resolved_font_path SOLO si apunta a fonts_prefs
            if i in migrated:
                d["resolved_font_path"] = migrated[i]
                d["resolved_font_index"] = 0  # Ya es TTF extraído, index siempre 0
            else:
                d.pop("resolved_font_path", None)
                d.pop("resolved_font_index", None)
            profiles_data.append(d)

        print(f"[SAVE_PREFS] Guardando {len(self.profiles)} perfiles:")
        for i, profile in enumerate(self.profiles):
            in_prefs = "✓ fonts_prefs" if i in migrated else "⚠️ sin fuente migrada"
            print(
                f"[SAVE_PREFS]   {i}: {profile.name} - {profile.font_family} {profile.font_style} [{in_prefs}]"
            )
        save_text_style_profiles(profiles_data)

        # Guardar número de muestra: almacenar tanto la representación raw (para preservar ceros)
        # como el valor numérico por compatibilidad
        save_preference(
            "preview_sample_number_raw", str(self.preview_sample_number_raw)
        )
        save_preference("preview_sample_number", int(self.preview_sample_number))

        print(
            f"[SAVE_PREFS] {len(self.profiles)} perfiles y número de muestra guardados en preferencias globales"
        )

    def load_from_preferences(self):
        """
        Carga los perfiles desde las preferencias globales.
        Se usa solo al iniciar la app o crear un nuevo trabajo
        """
        from utils.preferences import get_text_style_profiles, get_preference

        profiles_data = get_text_style_profiles()

        print(f"[LOAD_PREFS] Datos cargados: {profiles_data}")

        # Cargar número de muestra: preferir la representación raw para preservar ceros
        raw = get_preference("preview_sample_number_raw", None)
        if raw is not None:
            try:
                self.preview_sample_number_raw = str(raw)
                # parse numeric value también
                val = (
                    raw.replace(".", "").replace(",", "").replace(" ", "")
                    if isinstance(raw, str)
                    else str(int(raw))
                )
                self.preview_sample_number = int(val)
            except Exception:
                # fallback al valor numérico clásico
                self.preview_sample_number = get_preference(
                    "preview_sample_number", 1234
                )
                self.preview_sample_number_raw = str(self.preview_sample_number)
        else:
            # Compatibilidad con versiones antiguas que guardaban solo int
            self.preview_sample_number = get_preference("preview_sample_number", 1234)
            self.preview_sample_number_raw = str(self.preview_sample_number)

        if profiles_data:
            # Migrar datos antiguos
            for profile_dict in profiles_data:
                # Migración de letter_spacing
                if "letter_spacing" not in profile_dict:
                    profile_dict["letter_spacing"] = 0.0
                if "prefix_suffix_spacing" not in profile_dict:
                    profile_dict["prefix_suffix_spacing"] = 0.0
                if "digit_placeholder" not in profile_dict:
                    profile_dict["digit_placeholder"] = 0
                if "thousands_separator" not in profile_dict:
                    profile_dict["thousands_separator"] = "normal"

                # Migración 'Helvetica' -> 'Arial' en Windows
                if os.name == "nt" and profile_dict.get("font_family") == "Helvetica":
                    profile_dict["font_family"] = "Arial"
                    print(
                        f"[MIGRATE] Perfil '{profile_dict.get('name')}': Helvetica → Arial (Windows)"
                    )

                # Migración de colores: convertir color único a tres colores
                if "number_color" not in profile_dict:
                    # Archivo antiguo con un solo color
                    old_color = profile_dict.get("color", "#000000")
                    profile_dict["number_color"] = old_color
                    profile_dict["prefix_color"] = old_color
                    profile_dict["suffix_color"] = old_color
                    profile_dict["color"] = old_color  # Mantener para compatibilidad
                    print(
                        f"[MIGRATE] Perfil '{profile_dict.get('name')}': {old_color} → 3 colores"
                    )

                # Migración a color_space + CMYK
                if "color_space" not in profile_dict:
                    profile_dict["color_space"] = "RGB"
                    print(
                        f"[MIGRATE] Perfil '{profile_dict.get('name')}': añadido color_space=RGB"
                    )

                # Migración a color_space por segmento
                old_space = profile_dict.get("color_space", "RGB")
                if "number_color_space" not in profile_dict:
                    profile_dict["number_color_space"] = old_space
                if "prefix_color_space" not in profile_dict:
                    profile_dict["prefix_color_space"] = old_space
                if "suffix_color_space" not in profile_dict:
                    profile_dict["suffix_color_space"] = old_space

                # Migración a campos de nombre de color
                if "number_color_name" not in profile_dict:
                    profile_dict["number_color_name"] = ""
                if "prefix_color_name" not in profile_dict:
                    profile_dict["prefix_color_name"] = ""
                if "suffix_color_name" not in profile_dict:
                    profile_dict["suffix_color_name"] = ""

                if "number_color_cmyk" not in profile_dict:
                    from ui.color_picker import hex2rgb, rgb_to_cmyk

                    # Convertir RGB a CMYK para cada color
                    r, g, b = hex2rgb(profile_dict["number_color"])
                    profile_dict["number_color_cmyk"] = rgb_to_cmyk(r, g, b)

                    r, g, b = hex2rgb(profile_dict["prefix_color"])
                    profile_dict["prefix_color_cmyk"] = rgb_to_cmyk(r, g, b)

                    r, g, b = hex2rgb(profile_dict["suffix_color"])
                    profile_dict["suffix_color_cmyk"] = rgb_to_cmyk(r, g, b)
                    print(
                        f"[MIGRATE] Perfil '{profile_dict.get('name')}': generados valores CMYK"
                    )

            self.profiles = [
                TextStyle(**profile_dict) for profile_dict in profiles_data
            ]
            print(f"[LOAD_PREFS] {len(self.profiles)} perfiles cargados:")
            for i, profile in enumerate(self.profiles):
                print(
                    f"[LOAD_PREFS]   {i}: {profile.name} - {profile.font_family} {profile.font_size}pt - id:{profile.id}"
                )
        else:
            # Si no hay perfiles guardados, crear el default
            self.profiles = [TextStyle.create_default()]
            print("[LOAD_PREFS] Creado perfil <Default> inicial (primera vez)")

        # IMPORTANTE: Resolver rutas de fuentes y recargar métricas
        self._resolve_profiles()

        # Recargar métricas después de resolver las rutas
        for i, profile in enumerate(self.profiles):
            try:
                from utils.metrics_analisys import DEFAULT_FONT_METRICS

                if profile.resolved_font_path:
                    metric = DEFAULT_FONT_METRICS.get_metrics(
                        str(profile.resolved_font_path),
                        profile.font_size,
                        getattr(profile, "resolved_font_index", 0),
                    )
                    if metric:
                        profile.metricas = metric.copy()
                        print(
                            f"[LOAD_PREFS]   Perfil {i} ({profile.name}): Métricas recargadas ✓"
                        )
            except Exception as ex:
                print(f"[LOAD_PREFS]   Perfil {i}: ⚠️ Error al recargar métricas: {ex}")

        self.selected_profile_index = 0
        self.current_style = self.profiles[0].copy()

        # Actualizar UI si el diálogo está abierto
        if hasattr(self, "dialog") and self.dialog and self.dialog.open:
            self._update_profile_list()
            self._load_style_to_ui()
