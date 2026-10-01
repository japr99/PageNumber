"""
Pantalla principal de PageNumber
Basada en pantalla_principal.html
"""

import flet as ft
import sys
import os
import math
import platform
import tempfile
import json
import gc
import base64
import gzip
import threading
import asyncio
from typing import Optional, List, Tuple
from dataclasses import asdict

# Control para escritura de JSON de depuración al guardar PNB
# Poner a False para desactivar la creación automática de *_DEBUG.json
SAVE_DEBUG_JSON = False

# Silenciar prints de depuración en este módulo por defecto.
# Para activar, cambiar _PRINT_DEBUG = True durante desarrollo.
_PRINT_DEBUG = False
# Flag para mensajes de estado (p. ej. logs de "_mark_modified") — desactivado por defecto.
_PRINT_STATE = False
if not _PRINT_DEBUG:

    def _no_print(*args, **kwargs):
        return None

    print = _no_print


def _fmt_pt(v: float) -> str:
    """Formatea tamaño de letra: '24' para enteros, '24.5' para fracciones."""
    return str(int(v)) if v == int(v) else f"{v:.1f}"


# Añadir el directorio padre al path para importar color_design
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from resource_path import get_resource_path
from color_design import (
    TEXTO_COLOR_GENERICO,
    FONDO_APP,
    FONDO_TEXTFIELDS_COLOR,
    BORDE_TEXTFIELDS_COLOR,
    DROPDOWN_TEXT_STYLE_COLOR,
    DROPDOWN_FONDO_MENU_COLOR,
    DROPDOWN_TRAILING_ICON_COLOR,
    FONDO_CALCULO_FASE_1,
    FONDO_SECCIONES,
    TEXTOS_FASE_1_COLOR,
    BOTONES_GENERICOS_TEXTO_COLOR,
    BOTONES_GENERICOS_COLOR,
    BOTONES_GENERICOS_HOVER_COLOR,
    BOTONES_GENERICOS_OVERLAY_COLOR,
    BOTONES_GENERICOS_FONDO_COLOR,
    FONDO_ALERT_DIALOG,
    CHECKBOX_FILL_COLOR,
    set_tema_manual,
    actualizar_colores,
    definir_constantes_color,
    tema_flet,
    ICONO_PREF_COLOR,
    SNACKBAR_COLOR_TEXTO,
    SNACKBAR_COLOR_FONDO,
    SUCCESS_COLOR,
    SNACKBAR_COLOR_ERROR,
)

from utils.constants import (
    UNIT_MM,
    UNIT_PX,
    UNIT_INCHES,
    UNIT_PICAS,
    ROTATIONS,
    ALIGNMENTS,
    ALIGNMENT_LEFT,
    get_alignments,
    get_units,
    DEFAULT_START_NUMBER,
    DEFAULT_END_NUMBER,
    DEFAULT_INCREMENT,
    DEFAULT_COPIES,
    DEFAULT_POSITION_OFFSET_X,
    DEFAULT_POSITION_OFFSET_Y,
    MIN_ZOOM,
    MAX_ZOOM,
    DEFAULT_ZOOM,
    ZOOM_STEP,
    ENABLE_RULERS,
    convert_to_mm,
    convert_from_mm,
    format_unit,
    DEFAULT_PAGE_WIDTH_MM,
    DEFAULT_PAGE_HEIGHT_MM,
    DEFAULT_BLEED_MM,
    DEFAULT_PAGE_SIZE_NAME,
    PAGE_SIZES,
    normalize_decimal_input,
)
from utils.constants import get_unit_inches, get_unit_picas

from utils.preferences import (
    get_custom_page_sizes,
    save_custom_page_sizes,
    get_startup_settings,
    save_startup_settings,
    get_default_position_settings,
    save_default_position_settings,
    get_rendering_tuning_settings,
    save_rendering_tuning_settings,
    get_last_backgrounds,
    save_last_backgrounds,
    get_background_cache_dir,
    save_preference,
    get_preference,
    get_last_file_dialog_path,
    set_last_file_dialog_path,
)

from ui.interactive_viewer import InteractiveViewer, _apply_mask
from ui.background_image import BackgroundImageManager, UNITS
from ui.text_settings_dialog import TextStyleManager, TextStyle
from ui.pdf_export_dialog import PDFExportDialog
from ui.barcode_main_integration import BarcodeUIManager
from ui.barcode_settings_dialog import BarcodeProfile
from utils.barcode_module import _is_datamatrix_family
from ui.variable_text_settings_dialog import (
    ANCHORS,
    get_anchor_options,
    LINE_SPACING_AUTO,
    VariableTextProfile,
    VariableTextProfileManager,
)
from utils.variable_text_measure import (
    measure_vt_box,
    resolve_vt_text,
    extract_used_columns,
    DEFAULT_ANCHOR,
)
from ui.variable_text_main_integration import VariableTextUIManager
from utils.excel_manager import ExcelManager
from utils.excel_rows import excel_row_index
from utils.pdf_generator import generar_pdf_numerado
from shutdown_dialog import mostrar_dialogo_cierre
from fiery_export import generar_archivo_fiery

# Internacionalización
from i18n import t, set_language
import i18n as i18n


def _unit_abbr(unit_key: str) -> str:
    """Abreviatura fija (no traducible) para una clave de unidad."""
    return {
        UNIT_MM: "mm",
        UNIT_PX: "px",
        UNIT_INCHES: "in",
        UNIT_PICAS: "pc",
    }.get(unit_key, str(unit_key))


class _FakeEvent:
    def __init__(self, control):
        self.control = control


class MainScreen:
    """Pantalla principal de PageNumber"""

    def __init__(self, page: ft.Page):
        self.page = page
        self.zoom_value = DEFAULT_ZOOM
        # Estado para interacción de slider (zoom en vivo)
        self._zoom_user_changed = False
        self._zoom_timer = None
        self.selected_position = None

        # Estado del proyecto (FASE 0: Normalización 'Sin título')
        self.project_name = t("Sin título")  # Nombre del proyecto actual
        self.current_project_path = (
            None  # Ruta del proyecto guardado (None = no guardado)
        )
        self.project_modified = False  # Track si hay cambios sin guardar
        self._saved_state_snapshot = None  # Snapshot del estado guardado
        self._ui_mounted = (
            False  # Se activa en build() cuando la UI está añadida a la página
        )
        self._exit_after_save = False  # Flag para salir después de guardar
        self._new_after_save = False  # Flag para crear nuevo después de guardar
        self._open_after_save = False  # Flag para abrir archivo después de guardar
        self._closing_in_progress = False  # Evita cierres dobles desde rutas distintas
        self._close_watchdog_timer = None

        # Unidad actual (estado global de la app)
        self.current_unit = UNIT_MM

        # Configuración de página (estado global)
        self.page_size_name = DEFAULT_PAGE_SIZE_NAME
        self.page_width_mm = DEFAULT_PAGE_WIDTH_MM
        self.page_height_mm = DEFAULT_PAGE_HEIGHT_MM
        self.bleed_mm = DEFAULT_BLEED_MM

        # Tamaños personalizados del usuario (cargar desde preferencias)
        self.custom_sizes = get_custom_page_sizes()
        print(
            f"[PREFERENCES] Tamaños personalizados cargados: {len(self.custom_sizes)}"
        )

        # Cargar configuración de inicio desde preferencias
        startup_settings = get_startup_settings()
        self.current_unit = startup_settings.get("unit", UNIT_MM)

        # Aplicar tamaño de página guardado si existe
        saved_page_size = startup_settings.get("page_size", DEFAULT_PAGE_SIZE_NAME)
        if saved_page_size in PAGE_SIZES:
            self.page_size_name = saved_page_size
            self.page_width_mm, self.page_height_mm = PAGE_SIZES[saved_page_size]
        elif saved_page_size in self.custom_sizes:
            self.page_size_name = saved_page_size
            self.page_width_mm, self.page_height_mm = self.custom_sizes[saved_page_size]
        # Si no se encuentra, mantiene los valores por defecto inicializados antes

        # La sangre NO se guarda en preferencias, es específica del proyecto
        # Se quedará en DEFAULT_BLEED_MM hasta que se cargue un proyecto

        # Cargar valores por defecto para nuevas numeradoras
        default_pos_settings = get_default_position_settings()
        self.default_offset_x = default_pos_settings.get(
            "offset_x", DEFAULT_POSITION_OFFSET_X
        )
        self.default_offset_y = default_pos_settings.get(
            "offset_y", DEFAULT_POSITION_OFFSET_Y
        )
        self.default_alignment = default_pos_settings.get("alignment", ALIGNMENTS[0])
        self.default_rotation = default_pos_settings.get("rotation", ROTATIONS[0])

        print(
            f"[PREFERENCES] Configuración inicial: unit={self.current_unit}, page={self.page_size_name}, bleed={self.bleed_mm}mm"
        )
        print(
            f"[PREFERENCES] Defaults: offset=({self.default_offset_x}, {self.default_offset_y}), align={self.default_alignment}, rot={self.default_rotation}"
        )

        # Página actual (para navegación)
        self.current_page = 1

        # ===== CONFIGURACIÓN DE DOBLE CARA =====
        # Estado de doble cara
        self.double_sided_enabled = False
        self.current_face = "CARA"  # "CARA" o "DORSO"

        # Configuración GLOBAL (compartida por ambas caras - CARA y DORSO)
        # start, end, increment, copies son iguales para ambas caras
        self.global_settings = {
            "start": DEFAULT_START_NUMBER,
            "end": DEFAULT_END_NUMBER,
            "increment": DEFAULT_INCREMENT,
            "copies": DEFAULT_COPIES,
            "reverse": False,
        }

        # Copias espejo de reverse (el padre/autoridad es global_settings).
        # face_settings lleva la copia solo para pasar la data correcta (PDF merge).
        self.face_settings = {
            "CARA": {
                "reverse": False,
            },
            "DORSO": {
                "reverse": False,
            },
        }

        # Diccionario de posiciones para cada cara: {cara: {num_id: {"name": "Posición 1", "item": widget}}}
        # Solo contiene datos INDIVIDUALES de cada numeradora
        self.positions = {"CARA": {}, "DORSO": {}}
        self.next_position_number = {"CARA": 1, "DORSO": 1}

        # Calcular dimensiones del viewer basado en el tamaño de la ventana
        # Ventana real: 1470x860 (definida en page_number_app.py)
        # Panel izquierdo: 320px + paddings/divider: ~30px = 350px
        window_width = 1470
        window_height = 860

        self.viewer_width = window_width - 350  # 1120px
        # Altura: page_info (52px) + bottom padding del right_panel (5px) = 57px
        self.viewer_height = window_height - 57  # ~803px

        # Gestores de imagen de fondo para cara y dorso
        self.extracted_spot_colors: list = (
            []
        )  # Acumulado de spots de todos los PDFs cargados
        self.background_image_managers = {
            "CARA": BackgroundImageManager(
                page,
                on_change=self._on_background_image_change,
                on_spot_colors_found=self._on_spot_colors_found,
            ),
            "DORSO": BackgroundImageManager(
                page,
                on_change=self._on_background_image_change,
                on_spot_colors_found=self._on_spot_colors_found,
            ),
        }
        # Proporcionar al manager una función para leer la unidad global actual
        for mgr in self.background_image_managers.values():
            try:
                mgr.set_unit_getter(lambda unit_source=self: unit_source.current_unit)
            except Exception:
                pass

        # Cargar fondos de la sesión anterior (temporal en preferencias)
        last_backgrounds = get_last_backgrounds()
        print(f"[INIT] Cargando fondos de sesión: {list(last_backgrounds.keys())}")
        if last_backgrounds.get("CARA"):
            print(f"  [INIT] Cargando CARA: {last_backgrounds['CARA'].get('path')}")
            self.background_image_managers["CARA"].load_config(last_backgrounds["CARA"])
        if last_backgrounds.get("DORSO"):
            print(f"  [INIT] Cargando DORSO: {last_backgrounds['DORSO'].get('path')}")
            self.background_image_managers["DORSO"].load_config(
                last_backgrounds["DORSO"]
            )

        # Después de cargar, verificar si realmente se cargó algo (load_config ahora valida)
        print(
            f"  [INIT] Estado tras validación: CARA={self.background_image_managers['CARA'].image_loaded}, DORSO={self.background_image_managers['DORSO'].image_loaded}"
        )

        # Establecer tamaño de página para ambos gestores
        for manager in self.background_image_managers.values():
            manager.set_app_page_size(self.page_width_mm, self.page_height_mm)

        # IMPORTANTE: Inicializar gestor de fuentes ANTES de cargar perfiles de texto
        # para que las fuentes estén disponibles cuando se resuelvan los perfiles
        print("[INIT] Inicializando gestor de fuentes antes de cargar perfiles...")
        try:
            from utils import font_index_wrapper

            # Forzar inicialización explícita del gestor con todas las fuentes del sistema
            font_index_wrapper.inicializar_gestor_explicito()
            print("[INIT] ✓ Gestor de fuentes inicializado correctamente")
        except Exception as e:
            print(f"[INIT] ⚠ Error al inicializar gestor de fuentes: {e}")

        # Gestor de estilos de texto (ahora el gestor de fuentes ya está cargado)
        self.text_style_manager = TextStyleManager(
            page,
            on_style_changed=self._on_text_style_updated,
            on_profile_renamed=self._on_text_style_renamed,
        )

        # Asegurar que las fuentes de los perfiles estén extraídas (para TTCs)
        try:
            print("[INIT] Verificando extracción de fuentes de perfiles...")
            from utils import font_index_wrapper

            gestor = font_index_wrapper.obtener_gestor()
            gestor.ensure_preferences_fonts()

            # IMPORTANTE: Registrar fuentes extraídas en page.fonts para que Flet las renderice
            # Llamar a _resolve_profiles() del TextStyleManager para actualizar resolved_font_path
            # y resolved_flet_alias correctamente
            print("[INIT] Registrando fuentes extraídas en Flet...")
            self.text_style_manager._resolve_profiles()

            # Debug: mostrar qué fuentes están registradas
            if page.fonts:
                print(
                    f"[INIT] Fuentes registradas en page.fonts: {list(page.fonts.keys())}"
                )
            else:
                print("[INIT] page.fonts es None o vacío")

            # Debug: mostrar resolved_flet_alias de cada perfil
            for prof in self.text_style_manager.profiles:
                alias = getattr(prof, "resolved_flet_alias", "N/A")
                print(f"[INIT]   Perfil '{prof.name}': resolved_flet_alias='{alias}'")

            print("[INIT] ✓ Fuentes de perfiles verificadas y registradas en Flet")
        except Exception as e:
            print(f"[INIT] ⚠ Error al verificar fuentes de perfiles: {e}")
            import traceback

            traceback.print_exc()

        # Obtener perfiles de estilos disponibles
        self.available_text_styles = [
            p.name for p in self.text_style_manager.get_profiles()
        ]
        print(f"[INIT] Estilos de texto disponibles: {self.available_text_styles}")

        # Cargar métricas de todos los perfiles al inicio para que estén disponibles
        # cuando se usan desde el dropdown o el viewer (sin haber abierto el diálogo)
        try:
            from utils.metrics_analisys import (
                FontMetricsCache,
                cargar_metricas_perfiles,
            )
            from utils import font_index_wrapper as font_index

            fuentes_sistema = font_index.get_normalized_fonts()
            font_metrics_cache = FontMetricsCache()

            # Buscar perfil default
            default_profile = None
            for profile in self.text_style_manager.profiles:
                if profile.name == "<Default>":
                    default_profile = profile
                    break

            cargar_metricas_perfiles(
                self.text_style_manager.profiles,
                fuentes_sistema,
                font_metrics_cache,
                default_profile=default_profile,
            )
            print(
                f"[INIT] Métricas de fuentes cargadas para {len(self.text_style_manager.profiles)} perfiles"
            )

            # También cargar métricas para perfiles de texto variable
            if (
                hasattr(self, "variable_text_ui_manager")
                and self.variable_text_ui_manager
            ):
                vt_profiles = self.variable_text_ui_manager.profile_manager.profiles
                cargar_metricas_perfiles(
                    vt_profiles,
                    fuentes_sistema,
                    font_metrics_cache,
                    default_profile=None,
                )
                print(
                    f"[INIT] Métricas cargadas para {len(vt_profiles)} perfiles de texto variable"
                )
        except Exception as e:
            print(f"[INIT] ⚠️ Error cargando métricas de perfiles: {e}")

        # Crear FilePickers para guardar/cargar proyectos
        self.save_file_picker = ft.FilePicker(on_result=self._save_file_result)
        self.load_file_picker = ft.FilePicker(on_result=self._load_file_result)

        # Variables para detección de doble click en items de la lista
        self._last_clicked_item = None
        self._last_click_item_time = 0.0

        # Ruta del PDF de previsualización (temporal y fijo)
        self._preview_temp_dir = os.path.join(tempfile.gettempdir(), "pagenumber_app")
        os.makedirs(self._preview_temp_dir, exist_ok=True)
        self._preview_temp_path = os.path.join(
            self._preview_temp_dir, "preview_page.pdf"
        )
        # Eliminar previo si existe (inicio limpio)
        try:
            if os.path.exists(self._preview_temp_path):
                os.remove(self._preview_temp_path)
        except Exception:
            pass
        self.package_folder_picker = ft.FilePicker(
            on_result=self._package_folder_result
        )
        self.bg_missing_file_picker = ft.FilePicker(
            on_result=self._on_bg_missing_pick_result
        )
        self.excel_missing_file_picker = ft.FilePicker(
            on_result=self._on_excel_missing_pick_result
        )
        # Option to include fonts in package
        self._package_include_fonts = False

        self._pending_missing_backgrounds: List[Tuple[str, dict]] = []
        self._pending_missing_bg_face: Optional[str] = None
        self._pending_missing_bg_config: Optional[dict] = None
        self._pending_missing_bg_overlay_ref: Optional[list] = None

        # Excel faltante al cargar proyecto: {project_data, missing_path, overlay_ref}
        self._pending_missing_excel: Optional[dict] = None

        print(f"[INIT] Viewer inicial: {self.viewer_width}x{self.viewer_height}px")

        # Crear visor interactivo con dimensiones calculadas
        self.interactive_viewer = InteractiveViewer(
            page,
            self.viewer_width,
            self.viewer_height,
            on_position_update=self._on_position_moved,
            on_select=self._on_viewer_select,
            page_size_name=self.page_size_name,
            text_style_manager=self.text_style_manager,
        )

        # Pasar el viewer al gestor de estilos para que redibuje al cerrar el diálogo
        self.text_style_manager.viewer_callback = self.interactive_viewer

        # Conectar callback de doble clic para abrir diálogo de texto
        self.interactive_viewer.on_double_click_callback = (
            self._on_numeradora_double_click
        )

        # Aplicar el tamaño de página correcto (incluyendo custom sizes que no están en PAGE_SIZES)
        if self.page_size_name not in PAGE_SIZES:
            # Es un tamaño personalizado, aplicarlo manualmente
            self.interactive_viewer.set_page_size(
                self.page_width_mm + (self.bleed_mm * 2),
                self.page_height_mm + (self.bleed_mm * 2),
                self.bleed_mm,
            )

        # Snap magnético activado por defecto
        self.magnetic_snap_active = True
        self.interactive_viewer.magnetic_snap_active = True
        try:
            self.interactive_viewer.magnetic_snap_threshold = float(
                get_preference("magnetic_snap_threshold", 5.0)
            )
        except Exception:
            pass

        # Crear componentes
        self._create_components()

        # Inicializar gestores de Excel y Barcode (después del viewer)
        self.excel_manager = ExcelManager()
        self.barcode_ui_manager = BarcodeUIManager(
            page=page,
            viewer=self.interactive_viewer,
            excel_manager=self.excel_manager,
            get_current_face_fn=lambda: self.current_face,
            get_global_settings_fn=lambda: self.global_settings,
            get_unit_fn=lambda: self.current_unit,
        )
        if self.interactive_viewer.position_guides is None:
            from ui.position_guides import PositionGuides
            self.position_guides = PositionGuides()
            self.interactive_viewer.position_guides = self.position_guides
        self.interactive_viewer._get_guides_face_fn = (
            lambda: self.current_face
        )
        # Conectar callbacks de barcodes
        self.barcode_ui_manager.on_barcode_modified = self._on_barcode_modified
        self.barcode_ui_manager.on_project_modified = self._mark_modified
        self.barcode_ui_manager.on_excel_cleared = self._on_excel_cleared
        self.barcode_ui_manager.on_excel_reloaded = self._recalculate_pdf417_heights
        self.interactive_viewer.on_barcode_double_click_callback = (
            self._on_barcode_double_click
        )
        # Pasar el viewer al gestor de perfiles de barcode para que redibuje al cerrar el diálogo
        self.barcode_ui_manager.profile_manager.viewer_callback = (
            self.interactive_viewer
        )
        # Pasar el profile_manager al viewer para sync de bc_data en redraw (igual que text_style_manager)
        self.interactive_viewer.barcode_profile_manager = self.barcode_ui_manager.profile_manager
        # Renombrado de perfiles: las referencias van por nombre → propagar al post_data
        self.barcode_ui_manager.profile_manager.on_profile_renamed = (
            self._on_barcode_profile_renamed
        )
        self.barcode_ui_manager.on_row_change = self._go_to_page

        # Poblar dropdown de perfiles de barcode
        self._populate_barcode_profile_dropdown()

        # Inicializar VariableTextUIManager
        self.variable_text_ui_manager = VariableTextUIManager(
            page=page,
            viewer=self.interactive_viewer,
            excel_manager=self.excel_manager,
        )
        self.variable_text_ui_manager.on_project_modified = self._mark_modified
        self.variable_text_ui_manager.on_vt_profile_changed = (
            self._on_vt_profile_changed
        )
        # Renombrado de perfiles: las referencias van por nombre → propagar al post_data
        self.variable_text_ui_manager.profile_manager.on_profile_renamed = (
            self._on_vt_profile_renamed
        )
        self.interactive_viewer.on_variable_text_double_click_callback = (
            self._on_variable_text_double_click
        )
        self.interactive_viewer.vt_profile_manager = self.variable_text_ui_manager.profile_manager
        self.variable_text_ui_manager.on_row_change = self._go_to_page

        # Poblar dropdown de perfiles de texto variable
        self._populate_variable_text_profile_dropdown()

        # Estado inicial: sin selección (no hacer update, aún no están en la página)
        self._common_fields.visible = False
        self._number_fields.visible = False
        self._barcode_fields.visible = False
        self._variable_text_fields.visible = False

        # PDF417 focused field tracking for keyboard event handler
        self._pdf417_focused_field: Optional[ft.TextField] = None

        # Active barcode profile reference (direct, avoids string lookup)
        self._active_barcode_profile = None

    def _create_generic_button(
        self, text: str, on_click, width: int = 110
    ) -> ft.Button:
        """Crea un botón con el estilo genérico usado en impo_ui"""
        return ft.Button(
            text,
            on_click=on_click,
            width=width,
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
        )

    def _get_default_position_data(self):
        """
        Retorna los valores por defecto para una nueva posición
        Solo incluye parámetros INDIVIDUALES de cada numeradora
        Los datos globales (start, end, increment, etc.) están en face_settings
        La unidad (unit) es un estado global en self.current_unit
        """
        return {
            # Posicionamiento (usando offsets de preferencias)
            "x": self.default_offset_x,
            "y": self.default_offset_y,
            # Medidas (coherente con x, y)
            "vertical": str(self.default_offset_y),
            "horizontal": str(self.default_offset_x),
            "add": "0",  # Valor que se suma al número base (ej: 0, 100, 200)
            # Formato (usando valores de preferencias)
            "rotation": self.default_rotation,
            "alignment": self.default_alignment,
            "text_style": "<Default>",
            "letter_spacing": 0,  # Espaciado entre letras (modificable en pantalla de diseño)
            # Formato de número (máscaras)
            "prefix": "",  # Texto antes del número (ej: "N-")
            "suffix": "",  # Texto después del número (ej: "-END")
            "mask": "0000",  # Máscara de formateo (ej: "0000" → "0001", "0125")
            "mask_placeholder": "0",  # Carácter para rellenar
            "locked": False,  # Bloqueo de capa
        }

    def _create_components(self):
        """Crea todos los componentes de la UI"""

        # ===== PANEL IZQUIERDO =====

        # Lista de posiciones (vacía inicialmente)
        self.positions_list = ft.ListView(
            spacing=0,
            expand=True,
        )

        # Botones +/- para posiciones
        self.btn_add_position = ft.Container(
            content=ft.Stack(
                [
                    ft.Icon(ft.Icons.ADD, size=14),
                ],
                alignment=ft.Alignment.CENTER,
            ),
            width=24,
            height=20,
            border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
            border_radius=3,
            bgcolor=FONDO_TEXTFIELDS_COLOR,
            on_click=self._on_add_position,
        )

        self.btn_remove_position = ft.Container(
            content=ft.Stack(
                [
                    ft.Icon(ft.Icons.REMOVE, size=14),
                ],
                alignment=ft.Alignment.CENTER,
            ),
            width=24,
            height=20,
            border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
            border_radius=3,
            bgcolor=FONDO_TEXTFIELDS_COLOR,
            on_click=self._on_remove_position,
        )

        # Sección de posiciones
        self.position_type_dropdown = self._create_dropdown_compact(
            options=[
                ("number", t("Número")),
                ("variable_text", t("Texto Variable")),
                ("barcode", t("Código de barras")),
            ],
            value="number",
            width=130,
        )
        self.positions_section = ft.Container(
            expand=1,
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text(
                                t("Posiciones"),
                                size=14,
                                weight=ft.FontWeight.BOLD,
                                color=TEXTOS_FASE_1_COLOR,
                            ),
                            self.position_type_dropdown,
                            self.btn_add_position,
                            self.btn_remove_position,
                        ],
                        spacing=4,
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),
                    ft.Container(
                        content=self.positions_list,
                        border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
                        border_radius=4,
                        expand=True,
                    ),
                ],
                spacing=8,
            ),
            bgcolor=FONDO_SECCIONES,
            border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
            border_radius=4,
            padding=10,
        )

        # Configuración de medidas (incluye unidades para reglas si están habilitadas)
        # Usar la lista `UNITS` (clave, etiqueta) para que el dropdown mantenga la clave interna
        if not ENABLE_RULERS:
            unit_options = [
                u
                for u in UNITS
                if (isinstance(u, tuple) and u[0] in (UNIT_MM,))
                or (not isinstance(u, tuple) and u in (UNIT_MM,))
            ]
        else:
            unit_options = [
                u
                for u in UNITS
                if (isinstance(u, tuple) and u[0] in (UNIT_MM, UNIT_INCHES, UNIT_PICAS))
                or (
                    not isinstance(u, tuple) and u in (UNIT_MM, UNIT_INCHES, UNIT_PICAS)
                )
            ]

        # Nota: El selector de unidad global se muestra ahora en el diálogo de Preferencias.
        # `self.current_unit` sigue existiendo como estado compartido.

        self.vertical_field = self._create_textfield(
            "0", width=140, on_change=self._on_vertical_change
        )
        self.horizontal_field = self._create_textfield(
            "0", width=140, on_change=self._on_horizontal_change
        )
        self.add_field = self._create_textfield(
            "0", width=140, on_change=self._on_add_change
        )
        self.add_field.input_filter = ft.InputFilter(
            allow=True, regex_string=r"[0-9]", replacement_string=""
        )
        self.add_field.on_blur = self._on_add_blur

        self.rotation_dropdown = self._create_dropdown_compact(
            ROTATIONS,
            ROTATIONS[0],
            width=140,
            on_change=self._on_rotation_change,
        )

        self.alignment_dropdown = self._create_dropdown_compact(
            get_alignments(),
            ALIGNMENT_LEFT,  # default usando la clave interna
            width=140,
            on_change=self._on_alignment_change,
        )
        self.alignment_dropdown.data = {"on_change": self._on_alignment_change}

        self.text_style_dropdown = self._create_dropdown_compact(
            self.available_text_styles,
            (
                self.available_text_styles[0]
                if self.available_text_styles
                else "<Default>"
            ),
            width=140,
            on_change=self._on_text_style_change,
        )

        # Inicializar los campos de posición como deshabilitados (no hay selección al inicio)
        self.horizontal_field.disabled = True
        self.vertical_field.disabled = True
        self.add_field.disabled = True
        self.rotation_dropdown.disabled = True
        self.alignment_dropdown.disabled = True
        self.text_style_dropdown.disabled = True

        self._offset_h_label = ft.Text(
            f"Offset H ({_unit_abbr(self.current_unit)}):",
            size=11,
            color=TEXTOS_FASE_1_COLOR,
            width=120,
        )
        self._offset_v_label = ft.Text(
            f"Offset V ({_unit_abbr(self.current_unit)}):",
            size=11,
            color=TEXTOS_FASE_1_COLOR,
            width=120,
        )

        # --- Numeración: control de tamaño de letra ---
        self._num_font_size_field = ft.TextField(
            value="12",
            width=70,
            height=20,
            text_size=11,
            content_padding=ft.Padding(2, 0, 6, 0),
            filled=True,
            fill_color=FONDO_TEXTFIELDS_COLOR,
            text_style=ft.TextStyle(color=TEXTO_COLOR_GENERICO),
            on_change=self._on_num_font_size_change,border=ft.OutlineInputBorder(border_radius=3, side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)))
        self._num_font_size_up = ft.Container(
            width=20,
            height=20,
            border_radius=3,
            alignment=ft.Alignment.CENTER,
            ink=True,
            on_click=self._on_num_font_size_inc,
            content=ft.Icon(
                ft.Icons.KEYBOARD_ARROW_UP, size=14, color=TEXTO_COLOR_GENERICO
            ),
        )
        self._num_font_size_down = ft.Container(
            width=20,
            height=20,
            border_radius=3,
            alignment=ft.Alignment.CENTER,
            ink=True,
            on_click=self._on_num_font_size_dec,
            content=ft.Icon(
                ft.Icons.KEYBOARD_ARROW_DOWN, size=14, color=TEXTO_COLOR_GENERICO
            ),
        )
        self._num_font_size_row = ft.Container(
            content=ft.Row(
                [
                    self._num_font_size_field,
                    self._num_font_size_up,
                    self._num_font_size_down,
                ],
                spacing=2,
            ),
            width=140,
            alignment=ft.Alignment.CENTER_RIGHT,
        )

        # --- Numeración: control de interletraje ---
        self._num_letter_spacing_field = ft.TextField(
            value="0",
            width=70,
            height=20,
            text_size=11,
            content_padding=ft.Padding(2, 0, 6, 0),
            filled=True,
            fill_color=FONDO_TEXTFIELDS_COLOR,
            text_style=ft.TextStyle(color=TEXTO_COLOR_GENERICO),
            on_change=self._on_num_letter_spacing_change,border=ft.OutlineInputBorder(border_radius=3, side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)))
        self._num_letter_spacing_up = ft.Container(
            width=20,
            height=20,
            border_radius=3,
            alignment=ft.Alignment.CENTER,
            ink=True,
            on_click=self._on_num_letter_spacing_inc,
            content=ft.Icon(
                ft.Icons.KEYBOARD_ARROW_UP, size=14, color=TEXTO_COLOR_GENERICO
            ),
        )
        self._num_letter_spacing_down = ft.Container(
            width=20,
            height=20,
            border_radius=3,
            alignment=ft.Alignment.CENTER,
            ink=True,
            on_click=self._on_num_letter_spacing_dec,
            content=ft.Icon(
                ft.Icons.KEYBOARD_ARROW_DOWN, size=14, color=TEXTO_COLOR_GENERICO
            ),
        )
        self._num_letter_spacing_row = ft.Container(
            content=ft.Row(
                [
                    self._num_letter_spacing_field,
                    self._num_letter_spacing_up,
                    self._num_letter_spacing_down,
                ],
                spacing=2,
            ),
            width=140,
            alignment=ft.Alignment.CENTER_RIGHT,
        )

        # Línea separadora antes del dropdown de Perfil — una por grupo (Flet no permite padre compartido)
        self._separator_line = ft.Divider(
            height=5, thickness=1, color=BORDE_TEXTFIELDS_COLOR, visible=False
        )
        self._separator_line_bc = ft.Divider(
            height=5, thickness=1, color=BORDE_TEXTFIELDS_COLOR, visible=False
        )
        self._separator_line_vt = ft.Divider(
            height=5, thickness=1, color=BORDE_TEXTFIELDS_COLOR, visible=False
        )

        # Campos específicos de numeración (dentro de measures_section)
        self._number_fields = ft.Column(
            [
                self._create_form_row(t("Añadir:"), self.add_field),
                self._separator_line,
                self._create_form_row(t("Perfil:"), self.text_style_dropdown),
                self._create_form_row(t("Tamaño:"), self._num_font_size_row),
                self._create_form_row(t("Interletraje:"), self._num_letter_spacing_row),
            ],
            spacing=4,
            visible=False,
        )

        # Dropdown de perfiles de código de barras
        self._barcode_profile_dropdown = self._create_dropdown_compact(
            ["<Default>"],
            "<Default>",
            width=140,
            on_change=self._on_barcode_profile_change,
        )

        # Campos de código de barras (usados dentro de measures_section)
        self.bar_width_field = self._create_textfield(
            "80.0", width=70, on_change=self._on_bar_width_change
        )
        self.bar_width_field.on_submit = self._on_bar_width_apply
        self.bar_width_field.on_blur = self._on_bar_width_apply
        self.bar_width_up = ft.Container(
            width=20,
            height=20,
            border_radius=3,
            alignment=ft.Alignment.CENTER,
            ink=True,
            on_click=self._on_bar_width_inc,
            content=ft.Icon(
                ft.Icons.KEYBOARD_ARROW_UP, size=14, color=TEXTO_COLOR_GENERICO
            ),
        )
        self.bar_width_down = ft.Container(
            width=20,
            height=20,
            border_radius=3,
            alignment=ft.Alignment.CENTER,
            ink=True,
            on_click=self._on_bar_width_dec,
            content=ft.Icon(
                ft.Icons.KEYBOARD_ARROW_DOWN, size=14, color=TEXTO_COLOR_GENERICO
            ),
        )
        self.bar_width_row = ft.Container(
            content=ft.Row(
                [self.bar_width_field, self.bar_width_up, self.bar_width_down],
                spacing=2,
            ),
            width=140,
            alignment=ft.Alignment.CENTER_RIGHT,
        )

        self.bar_height_field = self._create_textfield(
            "30.0", width=70, on_change=self._on_bar_height_change
        )
        self.bar_height_field.on_submit = self._on_bar_height_apply
        self.bar_height_field.on_blur = self._on_bar_height_apply
        self.bar_height_up = ft.Container(
            width=20,
            height=20,
            border_radius=3,
            alignment=ft.Alignment.CENTER,
            ink=True,
            on_click=self._on_bar_height_inc,
            content=ft.Icon(
                ft.Icons.KEYBOARD_ARROW_UP, size=14, color=TEXTO_COLOR_GENERICO
            ),
        )
        self.bar_height_down = ft.Container(
            width=20,
            height=20,
            border_radius=3,
            alignment=ft.Alignment.CENTER,
            ink=True,
            on_click=self._on_bar_height_dec,
            content=ft.Icon(
                ft.Icons.KEYBOARD_ARROW_DOWN, size=14, color=TEXTO_COLOR_GENERICO
            ),
        )
        self.bar_height_row = ft.Container(
            content=ft.Row(
                [self.bar_height_field, self.bar_height_up, self.bar_height_down],
                spacing=2,
            ),
            width=140,
            alignment=ft.Alignment.CENTER_RIGHT,
        )

        self.qr_size_field = self._create_textfield(
            "30.0", width=70, on_change=self._on_qr_size_change
        )
        self.qr_size_field.on_submit = self._on_qr_size_blur
        self.qr_size_field.on_blur = self._on_qr_size_blur
        self._qr_size_up = ft.Container(
            width=20,
            height=20,
            border_radius=3,
            alignment=ft.Alignment.CENTER,
            ink=True,
            on_click=self._on_qr_size_inc,
            content=ft.Icon(
                ft.Icons.KEYBOARD_ARROW_UP, size=14, color=TEXTO_COLOR_GENERICO
            ),
        )
        self._qr_size_down = ft.Container(
            width=20,
            height=20,
            border_radius=3,
            alignment=ft.Alignment.CENTER,
            ink=True,
            on_click=self._on_qr_size_dec,
            content=ft.Icon(
                ft.Icons.KEYBOARD_ARROW_DOWN, size=14, color=TEXTO_COLOR_GENERICO
            ),
        )
        self.qr_size_row = ft.Container(
            content=ft.Row(
                [self.qr_size_field, self._qr_size_up, self._qr_size_down],
                spacing=2,
            ),
            width=140,
            alignment=ft.Alignment.CENTER_RIGHT,
        )

        # PDF417 height field (only shown when symbology == pdf417)
        self._pdf417_height_field = self._create_textfield(
            "30.0", width=70, on_change=None
        )
        self._pdf417_height_field.on_focus = lambda e: self._on_pdf417_focus_changed(
            self._pdf417_height_field
        )
        self._pdf417_height_field.on_blur = self._on_pdf417_blur
        self._pdf417_height_up = ft.Container(
            width=20,
            height=20,
            border_radius=3,
            alignment=ft.Alignment.CENTER,
            ink=True,
            on_click=self._on_pdf417_height_inc,
            content=ft.Icon(
                ft.Icons.KEYBOARD_ARROW_UP, size=14, color=TEXTO_COLOR_GENERICO
            ),
        )
        self._pdf417_height_down = ft.Container(
            width=20,
            height=20,
            border_radius=3,
            alignment=ft.Alignment.CENTER,
            ink=True,
            on_click=self._on_pdf417_height_dec,
            content=ft.Icon(
                ft.Icons.KEYBOARD_ARROW_DOWN, size=14, color=TEXTO_COLOR_GENERICO
            ),
        )
        self._pdf417_height_row = ft.Container(
            content=ft.Row(
                [
                    self._pdf417_height_field,
                    self._pdf417_height_up,
                    self._pdf417_height_down,
                ],
                spacing=2,
            ),
            width=140,
            alignment=ft.Alignment.CENTER_RIGHT,
        )

        # PDF417 width field (separado de qr_size_field, solo visible para PDF417)
        self._pdf417_width_field = self._create_textfield(
            "30.0", width=70, on_change=None
        )
        self._pdf417_width_field.on_focus = lambda e: self._on_pdf417_focus_changed(
            self._pdf417_width_field
        )
        self._pdf417_width_field.on_blur = self._on_pdf417_blur
        self._pdf417_width_up = ft.Container(
            width=20,
            height=20,
            border_radius=3,
            alignment=ft.Alignment.CENTER,
            ink=True,
            on_click=self._on_pdf417_width_inc,
            content=ft.Icon(
                ft.Icons.KEYBOARD_ARROW_UP, size=14, color=TEXTO_COLOR_GENERICO
            ),
        )
        self._pdf417_width_down = ft.Container(
            width=20,
            height=20,
            border_radius=3,
            alignment=ft.Alignment.CENTER,
            ink=True,
            on_click=self._on_pdf417_width_dec,
            content=ft.Icon(
                ft.Icons.KEYBOARD_ARROW_DOWN, size=14, color=TEXTO_COLOR_GENERICO
            ),
        )
        self._pdf417_width_row = ft.Container(
            content=ft.Row(
                [
                    self._pdf417_width_field,
                    self._pdf417_width_up,
                    self._pdf417_width_down,
                ],
                spacing=2,
            ),
            width=140,
            alignment=ft.Alignment.CENTER_RIGHT,
        )

        # ITF-14 body (font size) and gap fields
        self._itf14_body_field = self._create_textfield(
            "13.0", width=70, on_change=self._on_itf14_body_change
        )
        self._itf14_body_field.on_blur = self._on_body_gap_blur
        self._itf14_body_up = ft.Container(
            width=20,
            height=20,
            border_radius=3,
            alignment=ft.Alignment.CENTER,
            ink=True,
            on_click=self._on_itf14_body_inc,
            content=ft.Icon(
                ft.Icons.KEYBOARD_ARROW_UP, size=14, color=TEXTO_COLOR_GENERICO
            ),
        )
        self._itf14_body_down = ft.Container(
            width=20,
            height=20,
            border_radius=3,
            alignment=ft.Alignment.CENTER,
            ink=True,
            on_click=self._on_itf14_body_dec,
            content=ft.Icon(
                ft.Icons.KEYBOARD_ARROW_DOWN, size=14, color=TEXTO_COLOR_GENERICO
            ),
        )
        self._itf14_body_row = ft.Container(
            content=ft.Row(
                [self._itf14_body_field, self._itf14_body_up, self._itf14_body_down],
                spacing=2,
            ),
            width=140,
            alignment=ft.Alignment.CENTER_RIGHT,
        )
        self._itf14_gap_field = self._create_textfield(
            "0.0", width=70, on_change=self._on_itf14_gap_change
        )
        self._itf14_gap_field.on_blur = self._on_body_gap_blur
        self._itf14_gap_up = ft.Container(
            width=20,
            height=20,
            border_radius=3,
            alignment=ft.Alignment.CENTER,
            ink=True,
            on_click=self._on_itf14_gap_inc,
            content=ft.Icon(
                ft.Icons.KEYBOARD_ARROW_UP, size=14, color=TEXTO_COLOR_GENERICO
            ),
        )
        self._itf14_gap_down = ft.Container(
            width=20,
            height=20,
            border_radius=3,
            alignment=ft.Alignment.CENTER,
            ink=True,
            on_click=self._on_itf14_gap_dec,
            content=ft.Icon(
                ft.Icons.KEYBOARD_ARROW_DOWN, size=14, color=TEXTO_COLOR_GENERICO
            ),
        )
        self._itf14_gap_row = ft.Container(
            content=ft.Row(
                [self._itf14_gap_field, self._itf14_gap_up, self._itf14_gap_down],
                spacing=2,
            ),
            width=140,
            alignment=ft.Alignment.CENTER_RIGHT,
        )

        # Code 39 body (font size) and gap fields
        self._code39_body_field = self._create_textfield(
            "13.0", width=70, on_change=self._on_code39_body_change
        )
        self._code39_body_field.on_blur = self._on_body_gap_blur
        self._code39_body_up = ft.Container(
            width=20,
            height=20,
            border_radius=3,
            alignment=ft.Alignment.CENTER,
            ink=True,
            on_click=self._on_code39_body_inc,
            content=ft.Icon(
                ft.Icons.KEYBOARD_ARROW_UP, size=14, color=TEXTO_COLOR_GENERICO
            ),
        )
        self._code39_body_down = ft.Container(
            width=20,
            height=20,
            border_radius=3,
            alignment=ft.Alignment.CENTER,
            ink=True,
            on_click=self._on_code39_body_dec,
            content=ft.Icon(
                ft.Icons.KEYBOARD_ARROW_DOWN, size=14, color=TEXTO_COLOR_GENERICO
            ),
        )
        self._code39_body_row = ft.Container(
            content=ft.Row(
                [self._code39_body_field, self._code39_body_up, self._code39_body_down],
                spacing=2,
            ),
            width=140,
            alignment=ft.Alignment.CENTER_RIGHT,
        )
        self._code39_gap_field = self._create_textfield(
            "2.0", width=70, on_change=self._on_code39_gap_change
        )
        self._code39_gap_field.on_blur = self._on_body_gap_blur
        self._code39_gap_up = ft.Container(
            width=20,
            height=20,
            border_radius=3,
            alignment=ft.Alignment.CENTER,
            ink=True,
            on_click=self._on_code39_gap_inc,
            content=ft.Icon(
                ft.Icons.KEYBOARD_ARROW_UP, size=14, color=TEXTO_COLOR_GENERICO
            ),
        )
        self._code39_gap_down = ft.Container(
            width=20,
            height=20,
            border_radius=3,
            alignment=ft.Alignment.CENTER,
            ink=True,
            on_click=self._on_code39_gap_dec,
            content=ft.Icon(
                ft.Icons.KEYBOARD_ARROW_DOWN, size=14, color=TEXTO_COLOR_GENERICO
            ),
        )
        self._code39_gap_row = ft.Container(
            content=ft.Row(
                [self._code39_gap_field, self._code39_gap_up, self._code39_gap_down],
                spacing=2,
            ),
            width=140,
            alignment=ft.Alignment.CENTER_RIGHT,
        )

        # Code 128 body (font size) and gap fields
        self._code128_body_field = self._create_textfield(
            "13.0", width=70, on_change=self._on_code128_body_change
        )
        self._code128_body_field.on_blur = self._on_body_gap_blur
        self._code128_body_up = ft.Container(
            width=20,
            height=20,
            border_radius=3,
            alignment=ft.Alignment.CENTER,
            ink=True,
            on_click=self._on_code128_body_inc,
            content=ft.Icon(
                ft.Icons.KEYBOARD_ARROW_UP, size=14, color=TEXTO_COLOR_GENERICO
            ),
        )
        self._code128_body_down = ft.Container(
            width=20,
            height=20,
            border_radius=3,
            alignment=ft.Alignment.CENTER,
            ink=True,
            on_click=self._on_code128_body_dec,
            content=ft.Icon(
                ft.Icons.KEYBOARD_ARROW_DOWN, size=14, color=TEXTO_COLOR_GENERICO
            ),
        )
        self._code128_body_row = ft.Container(
            content=ft.Row(
                [
                    self._code128_body_field,
                    self._code128_body_up,
                    self._code128_body_down,
                ],
                spacing=2,
            ),
            width=140,
            alignment=ft.Alignment.CENTER_RIGHT,
        )
        self._code128_gap_field = self._create_textfield(
            "2.0", width=70, on_change=self._on_code128_gap_change
        )
        self._code128_gap_field.on_blur = self._on_body_gap_blur
        self._code128_gap_up = ft.Container(
            width=20,
            height=20,
            border_radius=3,
            alignment=ft.Alignment.CENTER,
            ink=True,
            on_click=self._on_code128_gap_inc,
            content=ft.Icon(
                ft.Icons.KEYBOARD_ARROW_UP, size=14, color=TEXTO_COLOR_GENERICO
            ),
        )
        self._code128_gap_down = ft.Container(
            width=20,
            height=20,
            border_radius=3,
            alignment=ft.Alignment.CENTER,
            ink=True,
            on_click=self._on_code128_gap_dec,
            content=ft.Icon(
                ft.Icons.KEYBOARD_ARROW_DOWN, size=14, color=TEXTO_COLOR_GENERICO
            ),
        )
        self._code128_gap_row = ft.Container(
            content=ft.Row(
                [self._code128_gap_field, self._code128_gap_up, self._code128_gap_down],
                spacing=2,
            ),
            width=140,
            alignment=ft.Alignment.CENTER_RIGHT,
        )

        # EAN-5 body (font size) and gap fields
        self._ean5_body_field = self._create_textfield(
            "13.0", width=70, on_change=self._on_ean5_body_change
        )
        self._ean5_body_field.on_blur = self._on_body_gap_blur
        self._ean5_body_up = ft.Container(
            width=20,
            height=20,
            border_radius=3,
            alignment=ft.Alignment.CENTER,
            ink=True,
            on_click=self._on_ean5_body_inc,
            content=ft.Icon(
                ft.Icons.KEYBOARD_ARROW_UP, size=14, color=TEXTO_COLOR_GENERICO
            ),
        )
        self._ean5_body_down = ft.Container(
            width=20,
            height=20,
            border_radius=3,
            alignment=ft.Alignment.CENTER,
            ink=True,
            on_click=self._on_ean5_body_dec,
            content=ft.Icon(
                ft.Icons.KEYBOARD_ARROW_DOWN, size=14, color=TEXTO_COLOR_GENERICO
            ),
        )
        self._ean5_body_row = ft.Container(
            content=ft.Row(
                [self._ean5_body_field, self._ean5_body_up, self._ean5_body_down],
                spacing=2,
            ),
            width=140,
            alignment=ft.Alignment.CENTER_RIGHT,
        )
        self._ean5_gap_field = self._create_textfield(
            "2.0", width=70, on_change=self._on_ean5_gap_change
        )
        self._ean5_gap_field.on_blur = self._on_body_gap_blur
        self._ean5_gap_up = ft.Container(
            width=20,
            height=20,
            border_radius=3,
            alignment=ft.Alignment.CENTER,
            ink=True,
            on_click=self._on_ean5_gap_inc,
            content=ft.Icon(
                ft.Icons.KEYBOARD_ARROW_UP, size=14, color=TEXTO_COLOR_GENERICO
            ),
        )
        self._ean5_gap_down = ft.Container(
            width=20,
            height=20,
            border_radius=3,
            alignment=ft.Alignment.CENTER,
            ink=True,
            on_click=self._on_ean5_gap_dec,
            content=ft.Icon(
                ft.Icons.KEYBOARD_ARROW_DOWN, size=14, color=TEXTO_COLOR_GENERICO
            ),
        )
        self._ean5_gap_row = ft.Container(
            content=ft.Row(
                [self._ean5_gap_field, self._ean5_gap_up, self._ean5_gap_down],
                spacing=2,
            ),
            width=140,
            alignment=ft.Alignment.CENTER_RIGHT,
        )

        # Generic body (font size) for UPC-A, UPC-E, EAN-13, EAN-8, ISBN-13
        self._generic_body_field = self._create_textfield(
            "13.0", width=70, on_change=self._on_generic_body_change
        )
        self._generic_body_field.on_blur = self._on_body_gap_blur
        self._generic_body_up = ft.Container(
            width=20,
            height=20,
            border_radius=3,
            alignment=ft.Alignment.CENTER,
            ink=True,
            on_click=self._on_generic_body_inc,
            content=ft.Icon(
                ft.Icons.KEYBOARD_ARROW_UP, size=14, color=TEXTO_COLOR_GENERICO
            ),
        )
        self._generic_body_down = ft.Container(
            width=20,
            height=20,
            border_radius=3,
            alignment=ft.Alignment.CENTER,
            ink=True,
            on_click=self._on_generic_body_dec,
            content=ft.Icon(
                ft.Icons.KEYBOARD_ARROW_DOWN, size=14, color=TEXTO_COLOR_GENERICO
            ),
        )
        self._generic_body_row = ft.Container(
            content=ft.Row(
                [
                    self._generic_body_field,
                    self._generic_body_up,
                    self._generic_body_down,
                ],
                spacing=2,
            ),
            width=140,
            alignment=ft.Alignment.CENTER_RIGHT,
        )

        # Campos específicos de código de barras (dentro de measures_section)
        abbr = _unit_abbr(self.current_unit)
        self._lbl_ancho = ft.Text(
            t("Ancho ({0})").format(abbr), size=11, color=TEXTOS_FASE_1_COLOR, width=120
        )
        self._lbl_alto = ft.Text(
            t("Alto ({0})").format(abbr), size=11, color=TEXTOS_FASE_1_COLOR, width=120
        )
        self._lbl_tamano = ft.Text(
            t("Tamaño ({0})").format(abbr),
            size=11,
            color=TEXTOS_FASE_1_COLOR,
            width=120,
        )
        self._lbl_pdf417_altura = ft.Text(
            t("Alto ({0})").format(abbr), size=11, color=TEXTOS_FASE_1_COLOR, width=120
        )
        self._alto_form_row = ft.Row(
            [self._lbl_alto, self.bar_height_row],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )
        self._itf14_settings_row = ft.Column(
            [
                ft.Row(
                    [
                        ft.Text(
                            t("Cuerpo:"), size=11, color=TEXTOS_FASE_1_COLOR, width=120
                        ),
                        self._itf14_body_row,
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                ft.Row(
                    [
                        ft.Text(
                            t("Distancia:"),
                            size=11,
                            color=TEXTOS_FASE_1_COLOR,
                            width=120,
                        ),
                        self._itf14_gap_row,
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
            ],
            spacing=4,
            visible=False,
        )
        self._code39_settings_row = ft.Column(
            [
                ft.Row(
                    [
                        ft.Text(
                            t("Cuerpo:"), size=11, color=TEXTOS_FASE_1_COLOR, width=120
                        ),
                        self._code39_body_row,
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                ft.Row(
                    [
                        ft.Text(
                            t("Distancia:"),
                            size=11,
                            color=TEXTOS_FASE_1_COLOR,
                            width=120,
                        ),
                        self._code39_gap_row,
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
            ],
            spacing=4,
            visible=False,
        )
        self._code128_settings_row = ft.Column(
            [
                ft.Row(
                    [
                        ft.Text(
                            t("Cuerpo:"), size=11, color=TEXTOS_FASE_1_COLOR, width=120
                        ),
                        self._code128_body_row,
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                ft.Row(
                    [
                        ft.Text(
                            t("Distancia:"),
                            size=11,
                            color=TEXTOS_FASE_1_COLOR,
                            width=120,
                        ),
                        self._code128_gap_row,
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
            ],
            spacing=4,
            visible=False,
        )
        # DataMatrix body (font size) and gap fields
        self._datamatrix_body_field = self._create_textfield(
            "9.0", width=70, on_change=self._on_datamatrix_body_change
        )
        self._datamatrix_body_field.on_blur = self._on_body_gap_blur
        self._datamatrix_body_up = ft.Container(
            width=20,
            height=20,
            border_radius=3,
            alignment=ft.Alignment.CENTER,
            ink=True,
            on_click=self._on_datamatrix_body_inc,
            content=ft.Icon(
                ft.Icons.KEYBOARD_ARROW_UP, size=14, color=TEXTO_COLOR_GENERICO
            ),
        )
        self._datamatrix_body_down = ft.Container(
            width=20,
            height=20,
            border_radius=3,
            alignment=ft.Alignment.CENTER,
            ink=True,
            on_click=self._on_datamatrix_body_dec,
            content=ft.Icon(
                ft.Icons.KEYBOARD_ARROW_DOWN, size=14, color=TEXTO_COLOR_GENERICO
            ),
        )
        self._datamatrix_body_row = ft.Container(
            content=ft.Row(
                [
                    self._datamatrix_body_field,
                    self._datamatrix_body_up,
                    self._datamatrix_body_down,
                ],
                spacing=2,
            ),
            width=140,
            alignment=ft.Alignment.CENTER_RIGHT,
        )
        self._datamatrix_gap_field = self._create_textfield(
            "2.0", width=70, on_change=self._on_datamatrix_gap_change
        )
        self._datamatrix_gap_field.on_blur = self._on_body_gap_blur
        self._datamatrix_gap_up = ft.Container(
            width=20,
            height=20,
            border_radius=3,
            alignment=ft.Alignment.CENTER,
            ink=True,
            on_click=self._on_datamatrix_gap_inc,
            content=ft.Icon(
                ft.Icons.KEYBOARD_ARROW_UP, size=14, color=TEXTO_COLOR_GENERICO
            ),
        )
        self._datamatrix_gap_down = ft.Container(
            width=20,
            height=20,
            border_radius=3,
            alignment=ft.Alignment.CENTER,
            ink=True,
            on_click=self._on_datamatrix_gap_dec,
            content=ft.Icon(
                ft.Icons.KEYBOARD_ARROW_DOWN, size=14, color=TEXTO_COLOR_GENERICO
            ),
        )
        self._datamatrix_gap_row = ft.Container(
            content=ft.Row(
                [
                    self._datamatrix_gap_field,
                    self._datamatrix_gap_up,
                    self._datamatrix_gap_down,
                ],
                spacing=2,
            ),
            width=140,
            alignment=ft.Alignment.CENTER_RIGHT,
        )
        # DataMatrix/QR/PDF417 interlineado (line spacing) — debajo de Cuerpo, como en el diálogo
        self._datamatrix_hri_line_spacing_field = self._create_textfield(
            "1.0", width=70, on_change=self._on_datamatrix_hri_line_spacing_change
        )
        self._datamatrix_hri_line_spacing_field.on_blur = self._on_body_gap_blur
        self._datamatrix_hri_line_spacing_up = ft.Container(
            width=20,
            height=20,
            border_radius=3,
            alignment=ft.Alignment.CENTER,
            ink=True,
            on_click=self._on_datamatrix_hri_line_spacing_inc,
            content=ft.Icon(
                ft.Icons.KEYBOARD_ARROW_UP, size=14, color=TEXTO_COLOR_GENERICO
            ),
        )
        self._datamatrix_hri_line_spacing_down = ft.Container(
            width=20,
            height=20,
            border_radius=3,
            alignment=ft.Alignment.CENTER,
            ink=True,
            on_click=self._on_datamatrix_hri_line_spacing_dec,
            content=ft.Icon(
                ft.Icons.KEYBOARD_ARROW_DOWN, size=14, color=TEXTO_COLOR_GENERICO
            ),
        )
        self._datamatrix_hri_line_spacing_row = ft.Container(
            content=ft.Row(
                [
                    self._datamatrix_hri_line_spacing_field,
                    self._datamatrix_hri_line_spacing_up,
                    self._datamatrix_hri_line_spacing_down,
                ],
                spacing=2,
            ),
            width=140,
            alignment=ft.Alignment.CENTER_RIGHT,
        )
        # Posición del bloque HRI respecto al código — compartida por
        # qr/datamatrix/pdf417/code128/code39/itf14 (opciones según simbología)
        self._hri_position_dd = self._create_dropdown_compact(
            options=[],
            value="",
            width=140,
            on_change=self._on_hri_position_change,
        )
        # Alineación del HRI dentro de su caja — 9 posiciones (top/middle/bottom × left/center/right)
        # solo para qr/datamatrix/pdf417
        self._hri_align_dd = self._create_dropdown_compact(
            options=[],
            value="",
            width=140,
            on_change=self._on_hri_align_change,
        )
        # DataMatrix height dropdown (dynamic based on ancho + values)
        self._datamatrix_height_options: list = []
        self._datamatrix_height_dd = self._create_dropdown_compact(
            options=[],
            value="",
            width=70,
            on_change=self._on_datamatrix_height_change,
        )
        self._datamatrix_alto_row = ft.Row(
            [
                ft.Text(
                    t("Alto ({0}):").format(_unit_abbr(self.current_unit)),
                    size=11,
                    color=TEXTOS_FASE_1_COLOR,
                    width=120,
                ),
                ft.Container(
                    content=self._datamatrix_height_dd,
                    width=140,
                    alignment=ft.Alignment.CENTER_LEFT,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            visible=False,
        )
        # Fila común de Cuerpo/Distancia (QR, DataMatrix y PDF417 la comparten).
        # Un solo contenedor: un control Flet no puede vivir en varios padres,
        # antes se insertaba en 3 columnas y el valor asignado no refrescaba.
        # Posición HRI vive aquí debajo de Interlineado; visible para los 6 códigos.
        self._cuerpo_row = ft.Row(
            [
                ft.Text(
                    t("Cuerpo:"), size=11, color=TEXTOS_FASE_1_COLOR, width=120
                ),
                self._datamatrix_body_row,
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )
        self._alineacion_row = ft.Row(
            [
                ft.Text(
                    t("Alineación:"),
                    size=11,
                    color=TEXTOS_FASE_1_COLOR,
                    width=120,
                ),
                self._hri_align_dd,
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )
        self._interlineado_row = ft.Row(
            [
                ft.Text(
                    t("Interlineado:"),
                    size=11,
                    color=TEXTOS_FASE_1_COLOR,
                    width=120,
                ),
                self._datamatrix_hri_line_spacing_row,
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )
        self._posicion_hri_row = ft.Row(
            [
                ft.Text(
                    t("Posición:"),
                    size=11,
                    color=TEXTOS_FASE_1_COLOR,
                    width=120,
                ),
                self._hri_position_dd,
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )
        self._distancia_row = ft.Row(
            [
                ft.Text(
                    t("Distancia:"),
                    size=11,
                    color=TEXTOS_FASE_1_COLOR,
                    width=120,
                ),
                self._datamatrix_gap_row,
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )
        self._body_gap_row = ft.Column(
            [
                self._cuerpo_row,
                self._alineacion_row,
                self._interlineado_row,
                self._posicion_hri_row,
                self._distancia_row,
            ],
            spacing=4,
            visible=False,
        )
        self._ean5_settings_row = ft.Column(
            [
                ft.Row(
                    [
                        ft.Text(
                            t("Cuerpo:"), size=11, color=TEXTOS_FASE_1_COLOR, width=120
                        ),
                        self._ean5_body_row,
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                ft.Row(
                    [
                        ft.Text(
                            t("Distancia:"),
                            size=11,
                            color=TEXTOS_FASE_1_COLOR,
                            width=120,
                        ),
                        self._ean5_gap_row,
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
            ],
            spacing=4,
            visible=False,
        )
        self._generic_body_settings_row = ft.Column(
            [
                ft.Row(
                    [
                        ft.Text(
                            t("Cuerpo:"), size=11, color=TEXTOS_FASE_1_COLOR, width=120
                        ),
                        self._generic_body_row,
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
            ],
            spacing=4,
            visible=False,
        )
        self._dim_barcode_row = ft.Column(
            [
                ft.Row(
                    [self._lbl_ancho, self.bar_width_row],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                self._alto_form_row,
                self._datamatrix_alto_row,
                self._itf14_settings_row,
                self._code39_settings_row,
                self._code128_settings_row,
                self._ean5_settings_row,
                self._generic_body_settings_row,
            ],
            spacing=4,
        )
        self._dim_qr_row = ft.Column(
            [
                ft.Row(
                    [self._lbl_tamano, self.qr_size_row],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
            ],
            spacing=4,
            visible=False,
        )
        self._dim_pdf417_row = ft.Column(
            [
                ft.Row(
                    [self._lbl_tamano, self._pdf417_width_row],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                ft.Row(
                    [self._lbl_pdf417_altura, self._pdf417_height_row],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
            ],
            spacing=4,
            visible=False,
        )
        self._barcode_fields = ft.Column(
            [
                self._separator_line_bc,
                self._create_form_row(t("Perfil:"), self._barcode_profile_dropdown),
                self._dim_barcode_row,
                self._dim_qr_row,
                self._dim_pdf417_row,
                self._body_gap_row,
            ],
            spacing=4,
            visible=False,
        )

        # Dropdown de perfiles de texto variable
        self._variable_text_profile_dropdown = self._create_dropdown_compact(
            ["<Default>"],
            "<Default>",
            width=140,
            on_change=self._on_variable_text_profile_change,
        )

        # --- Texto variable: control de tamaño de letra ---
        self._vt_font_size_field = ft.TextField(
            value="12",
            width=48,
            height=20,
            text_size=11,
            content_padding=ft.Padding(2, 0, 6, 0),
            filled=True,
            fill_color=FONDO_TEXTFIELDS_COLOR,
            text_style=ft.TextStyle(color=TEXTO_COLOR_GENERICO),
            on_change=self._on_vt_font_size_change,border=ft.OutlineInputBorder(border_radius=3, side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)))
        self._vt_font_size_up = ft.Container(
            width=20,
            height=20,
            border_radius=3,
            alignment=ft.Alignment.CENTER,
            ink=True,
            on_click=self._on_vt_font_size_inc,
            content=ft.Icon(
                ft.Icons.KEYBOARD_ARROW_UP, size=14, color=TEXTO_COLOR_GENERICO
            ),
        )
        self._vt_font_size_down = ft.Container(
            width=20,
            height=20,
            border_radius=3,
            alignment=ft.Alignment.CENTER,
            ink=True,
            on_click=self._on_vt_font_size_dec,
            content=ft.Icon(
                ft.Icons.KEYBOARD_ARROW_DOWN, size=14, color=TEXTO_COLOR_GENERICO
            ),
        )
        self._vt_font_size_row = ft.Container(
            content=ft.Row(
                [
                    self._vt_font_size_field,
                    self._vt_font_size_up,
                    self._vt_font_size_down,
                ],
                spacing=2,
            ),
            width=140,
            alignment=ft.Alignment.CENTER_RIGHT,
        )

        # --- Texto variable: interlineado (cuerpo + flechas) ---
        self._vt_line_spacing_auto = True
        self._vt_line_spacing_field = ft.TextField(
            value="14.4",
            width=48,
            height=20,
            text_size=11,
            content_padding=ft.Padding(2, 0, 6, 0),
            filled=True,
            fill_color=FONDO_TEXTFIELDS_COLOR,
            text_style=ft.TextStyle(color=TEXTO_COLOR_GENERICO),
            on_change=self._on_vt_line_spacing_change,border=ft.OutlineInputBorder(border_radius=3, side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)))
        self._vt_line_spacing_up = ft.Container(
            width=20,
            height=20,
            border_radius=3,
            alignment=ft.Alignment.CENTER,
            ink=True,
            on_click=self._on_vt_line_spacing_inc,
            content=ft.Icon(
                ft.Icons.KEYBOARD_ARROW_UP, size=14, color=TEXTO_COLOR_GENERICO
            ),
        )
        self._vt_line_spacing_down = ft.Container(
            width=20,
            height=20,
            border_radius=3,
            alignment=ft.Alignment.CENTER,
            ink=True,
            on_click=self._on_vt_line_spacing_dec,
            content=ft.Icon(
                ft.Icons.KEYBOARD_ARROW_DOWN, size=14, color=TEXTO_COLOR_GENERICO
            ),
        )
        self._vt_line_spacing_reset = ft.Container(
            width=20,
            height=20,
            border_radius=3,
            alignment=ft.Alignment.CENTER,
            ink=True,
            on_click=self._on_vt_line_spacing_reset,
            content=ft.Icon(
                ft.Icons.RESTART_ALT, size=14, color=TEXTO_COLOR_GENERICO
            ),
            tooltip=t("Restablecer interlineado"),
        )
        self._vt_line_spacing_row = ft.Container(
            content=ft.Row(
                [
                    self._vt_line_spacing_field,
                    self._vt_line_spacing_up,
                    self._vt_line_spacing_down,
                    self._vt_line_spacing_reset,
                ],
                spacing=2,
            ),
            width=140,
            alignment=ft.Alignment.CENTER_RIGHT,
        )

        # --- Texto variable: interletraje (cuerpo + flechas ±0.1, negativos ok) ---
        self._vt_letter_spacing_field = ft.TextField(
            value="0",
            width=48,
            height=20,
            text_size=11,
            content_padding=ft.Padding(2, 0, 6, 0),
            filled=True,
            fill_color=FONDO_TEXTFIELDS_COLOR,
            text_style=ft.TextStyle(color=TEXTO_COLOR_GENERICO),
            on_change=self._on_vt_letter_spacing_change,border=ft.OutlineInputBorder(border_radius=3, side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)))
        self._vt_letter_spacing_up = ft.Container(
            width=20,
            height=20,
            border_radius=3,
            alignment=ft.Alignment.CENTER,
            ink=True,
            on_click=self._on_vt_letter_spacing_inc,
            content=ft.Icon(
                ft.Icons.KEYBOARD_ARROW_UP, size=14, color=TEXTO_COLOR_GENERICO
            ),
        )
        self._vt_letter_spacing_down = ft.Container(
            width=20,
            height=20,
            border_radius=3,
            alignment=ft.Alignment.CENTER,
            ink=True,
            on_click=self._on_vt_letter_spacing_dec,
            content=ft.Icon(
                ft.Icons.KEYBOARD_ARROW_DOWN, size=14, color=TEXTO_COLOR_GENERICO
            ),
        )
        self._vt_letter_spacing_row = ft.Container(
            content=ft.Row(
                [
                    self._vt_letter_spacing_field,
                    self._vt_letter_spacing_up,
                    self._vt_letter_spacing_down,
                ],
                spacing=2,
            ),
            width=140,
            alignment=ft.Alignment.CENTER_RIGHT,
        )

        # --- Texto variable: alineación del texto dentro de la caja (3, del diálogo) ---
        self._vt_text_alignment_dropdown = self._create_dropdown_compact(
            get_alignments(),
            ALIGNMENT_LEFT,
            width=140,
            on_change=self._on_vt_text_alignment_change,
        )

        # Campos específicos de texto variable (dentro de measures_section)
        self._variable_text_fields = ft.Column(
            [
                self._separator_line_vt,
                self._create_form_row(
                    t("Perfil:"), self._variable_text_profile_dropdown
                ),
                self._create_form_row(t("Cuerpo:"), self._vt_font_size_row),
                self._create_form_row(t("Interletraje:"), self._vt_letter_spacing_row),
                self._create_form_row(t("Interlineado:"), self._vt_line_spacing_row),
                self._create_form_row(
                    t("Alineación:"), self._vt_text_alignment_dropdown
                ),
            ],
            spacing=4,
            visible=False,
        )

        # Campos comunes de posición (Offset H/V, Rotar, Alineamiento/Posición)
        self._alignment_row_label = ft.Text(
            t("Alineamiento:"),
            size=11,
            color=TEXTOS_FASE_1_COLOR,
            width=120,
        )
        self._common_fields = ft.Column(
            [
                ft.Row(
                    [self._offset_h_label, self.horizontal_field],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                ft.Row(
                    [self._offset_v_label, self.vertical_field],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                self._create_form_row(t("Rotar:"), self.rotation_dropdown),
                ft.Row(
                    [self._alignment_row_label, self.alignment_dropdown],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
            ],
            spacing=4,
            visible=False,
        )

        self.measures_section = ft.Container(
            content=ft.Column(
                [
                    self._common_fields,
                    self._number_fields,
                    self._barcode_fields,
                    self._variable_text_fields,
                ],
                spacing=4,
            ),
            bgcolor=FONDO_SECCIONES,
            border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
            border_radius=4,
            padding=10,
            height=316,
            width=390,
        )

        # Ajustes de numeración
        self.start_field = self._create_textfield(
            str(DEFAULT_START_NUMBER), width=140, on_change=self._on_start_change
        )
        self.end_field = self._create_textfield(
            str(DEFAULT_END_NUMBER), width=140, on_change=self._on_end_change
        )
        self.increment_field = self._create_textfield(
            str(DEFAULT_INCREMENT), width=140, on_change=self._on_increment_change
        )
        self.copies_field = self._create_textfield(
            str(DEFAULT_COPIES), width=140, on_change=self._on_copies_change
        )
        self.pages_field = self._create_textfield(
            str(DEFAULT_END_NUMBER * DEFAULT_COPIES), width=140, read_only=True
        )

        self.reverse_checkbox = ft.Checkbox(
            value=False,
            active_color=BORDE_TEXTFIELDS_COLOR,
            check_color=TEXTOS_FASE_1_COLOR,
            fill_color=FONDO_TEXTFIELDS_COLOR,
            border_side=ft.BorderSide(1, BORDE_TEXTFIELDS_COLOR),
            splash_radius=0,
            on_change=self._on_reverse_change,
        )

        self.numbering_section = ft.Container(
            content=ft.Column(
                [
                    ft.Text(
                        t("Ajustes de numeración"),
                        size=11,
                        weight=ft.FontWeight.W_600,
                        color=TEXTOS_FASE_1_COLOR,
                    ),
                    self._create_form_row(t("Comienzo:"), self.start_field),
                    self._create_form_row(t("Fin:"), self.end_field),
                    self._create_form_row(t("Incremento:"), self.increment_field),
                    self._create_form_row(t("Copias:"), self.copies_field),
                    self._create_form_row(t("Número de páginas:"), self.pages_field),
                    ft.Row(
                        [
                            ft.Text(
                                t("Invertir orden:"), size=11, color=TEXTOS_FASE_1_COLOR
                            ),
                            self.reverse_checkbox,
                        ],
                        alignment=ft.MainAxisAlignment.START,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                ],
                spacing=4,
            ),
            bgcolor=FONDO_SECCIONES,
            border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
            border_radius=4,
            padding=ft.Padding.symmetric(vertical=10, horizontal=12),
        )

        # Indicador de doble cara activada (inicialmente oculto)
        # Usa OVERLAY para fondo (negro en día, blanco en noche) y TEXTO_COLOR para texto (inverso)
        self._double_sided_text = ft.Text(
            t("Doble cara activado."),
            size=14,
            weight=ft.FontWeight.BOLD,
            color=BOTONES_GENERICOS_TEXTO_COLOR,
            text_align=ft.TextAlign.CENTER,
        )
        self.double_sided_indicator = ft.Container(
            content=ft.Row(
                [
                    ft.Container(
                        content=self._double_sided_text,
                        alignment=ft.Alignment.CENTER,
                        expand=True,
                    )
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=BOTONES_GENERICOS_OVERLAY_COLOR,
            border_radius=4,
            padding=ft.Padding(0, 0, 0, 0),
            alignment=ft.Alignment.CENTER,
            height=40,
            visible=False,  # Inicialmente oculto
        )

        # Crear iconos principales antes de usarlos en la fila superior
        self.icon_new_project = ft.Container(
            content=ft.Icon(
                ft.Icons.NOTE_ADD_OUTLINED, size=24, color=TEXTOS_FASE_1_COLOR
            ),
            width=40,
            height=40,
            border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
            border_radius=4,
            bgcolor=FONDO_TEXTFIELDS_COLOR,
            alignment=ft.Alignment.CENTER,
            on_click=self._on_new_project,
            tooltip=t("Nuevo trabajo"),
        )
        self.icon_load_project_icon = ft.Icon(
            ft.Icons.FILE_OPEN_OUTLINED, size=24, color=TEXTOS_FASE_1_COLOR
        )
        self.icon_load_project = ft.Container(
            content=self.icon_load_project_icon,
            width=40,
            height=40,
            border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
            border_radius=4,
            bgcolor=FONDO_TEXTFIELDS_COLOR,
            alignment=ft.Alignment.CENTER,
            on_click=self._on_load_project,
            tooltip=t("Cargar trabajo"),
        )
        self.icon_save_project = ft.Container(
            content=ft.Icon(ft.Icons.SAVE_OUTLINED, size=24, color=TEXTOS_FASE_1_COLOR),
            width=40,
            height=40,
            border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
            border_radius=4,
            bgcolor=FONDO_TEXTFIELDS_COLOR,
            alignment=ft.Alignment.CENTER,
            on_click=self._on_save_project,
            tooltip=t("Guardar trabajo"),
        )
        self.icon_save_as_project = ft.Container(
            content=ft.Icon(
                ft.Icons.SAVE_AS_OUTLINED, size=24, color=TEXTOS_FASE_1_COLOR
            ),
            width=40,
            height=40,
            border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
            border_radius=4,
            bgcolor=FONDO_TEXTFIELDS_COLOR,
            alignment=ft.Alignment.CENTER,
            on_click=self._on_save_as_project,
            tooltip=t("Guardar trabajo como"),
        )
        self.icon_package_project = ft.Container(
            content=ft.Icon(
                ft.Icons.FOLDER_COPY_OUTLINED, size=24, color=TEXTOS_FASE_1_COLOR
            ),
            width=40,
            height=40,
            border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
            border_radius=4,
            bgcolor=FONDO_TEXTFIELDS_COLOR,
            alignment=ft.Alignment.CENTER,
            ink=True,
            on_click=self._on_package_project,
            tooltip=t("Empaquetar proyecto en carpeta"),
        )

        # Fila horizontal de iconos principales (nuevo, cargar, guardar, empaquetar)
        self.top_icons_row = ft.Container(
            content=ft.Row(
                [
                    self.icon_new_project,
                    self.icon_load_project,
                    self.icon_save_project,
                    self.icon_save_as_project,
                    self.icon_package_project,
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=5,
            ),
            width=240,
            height=44,
            padding=ft.Padding.only(top=0, left=0, right=0, bottom=0),
            bgcolor=FONDO_APP,
        )

        # Panel izquierdo completo (ahora con los iconos principales arriba)
        self.left_panel = ft.Container(
            content=ft.Column(
                [
                    ft.Container(height=4),
                    self.top_icons_row,
                    ft.Container(height=3),
                    self.positions_section,
                    ft.Container(height=8),
                    self.measures_section,
                    ft.Container(height=8),
                    self.numbering_section,
                    ft.Container(height=8),
                    ft.Container(
                        content=self.double_sided_indicator,
                        height=20,  # preservar espacio cuando el indicador está oculto
                    ),
                    ft.Container(height=8),
                ],
                spacing=0,
            ),
            width=320,
            padding=ft.Padding.only(
                top=0, left=10, right=10, bottom=0
            ),  # Reducido el top
            bgcolor=FONDO_APP,
            alignment=ft.Alignment.TOP_CENTER,
        )

        # ===== COLUMNA DE ICONOS =====

        # Nota: la creación de los iconos principales ya se realizó previamente
        # (evitamos duplicar instancias que rompen las actualizaciones visuales).
        # (duplicado eliminado)

        # Ahora el resto de iconos
        icons_spec = [
            (
                "icon_double_sided",
                ft.Icons.COPY_ALL_OUTLINED,
                self._on_toggle_double_sided,
                t("Activar/Desactivar doble cara"),
            ),
            (
                "icon_paper_settings",
                ft.Icons.DESCRIPTION_OUTLINED,
                self._on_open_paper_settings,
                t("Ajustes de papel"),
            ),
            (
                "icon_variable_text_settings",
                ft.Icons.TEXT_FIELDS,
                self._on_open_variable_text_settings,
                t("Ajustes de textos variables"),
            ),
            (
                "icon_barcode_settings",
                ft.CupertinoIcons.BARCODE,
                self._on_open_barcode_settings,
                t("Ajustes de código de barras"),
            ),
            (
                "icon_excel",
                ft.Icons.TABLE_CHART,
                self._on_open_excel,
                t("Cargar archivo de datos (Excel/CSV)"),
            ),
            (
                "icon_image_settings",
                ft.Icons.IMAGE_OUTLINED,
                self._on_open_image_settings,
                t("Ajustes de imagen"),
            ),
            (
                "icon_remove_background",
                ft.Icons.DELETE_OUTLINE,
                self._on_remove_background,
                t("Eliminar imagen de fondo"),
            ),
            (
                "icon_load_background",
                ft.Icons.ADD_PHOTO_ALTERNATE_OUTLINED,
                self._on_load_background,
                t("Cargar PDF o Imagen de fondo"),
            ),
            (
                "icon_exit_app",
                ft.Icons.EXIT_TO_APP,
                self._on_exit_app,
                t("Salir de la aplicación"),
            ),
            (
                "icon_export_pdf",
                ft.Icons.PRINT,
                self._on_export_pdf,
                t("Exportar a PDF"),
            ),
            (
                "icon_preview_page",
                ft.CupertinoIcons.DOC_TEXT_VIEWFINDER,
                self._on_preview_current_page,
                t("Generar PDF vista previa (página actual)"),
            ),
            (
                "icon_preferences",
                ft.Icons.SETTINGS,
                self._on_open_preferences,
                t("Preferencias"),
            ),
        ]
        for name, icon_const, handler, tooltip in icons_spec:
            cont = ft.Container(
                content=ft.Icon(
                    icon_const,
                    size=24 if name != "icon_preview_page" else 22,
                    color=TEXTOS_FASE_1_COLOR,
                ),
                width=40,
                height=40,
                border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
                border_radius=4,
                bgcolor=FONDO_TEXTFIELDS_COLOR,
                alignment=ft.Alignment.CENTER,
                on_click=handler,
                tooltip=tooltip,
            )
            setattr(self, name, cont)

        # Icono de ajustes de texto (numeración) — usa imagen en vez de icono
        _img_path = get_resource_path(os.path.join("assets", "001_2.png"))
        self.icon_text_settings = ft.Container(
            content=ft.Container(
                content=ft.Image(
                    src=_img_path,
                    width=28,
                    height=28,
                    fit=ft.BoxFit.CONTAIN,
                    color=TEXTOS_FASE_1_COLOR,
                ),
                bgcolor=FONDO_TEXTFIELDS_COLOR,
            ),
            width=40,
            height=40,
            border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
            border_radius=4,
            bgcolor=FONDO_TEXTFIELDS_COLOR,
            alignment=ft.Alignment.CENTER,
            on_click=self._on_open_text_settings,
            tooltip=t("Ajustes de numeradoras"),
        )

        # Icono unificado cara/dorso - se adapta automaticamente
        self.icon_face = ft.Container(
            content=ft.Row(
                [
                    ft.Icon(
                        ft.Icons.DESCRIPTION_OUTLINED,
                        size=16,
                        color=TEXTOS_FASE_1_COLOR,
                    ),
                    ft.Text(
                        t("C"),
                        size=12,
                        color=TEXTOS_FASE_1_COLOR,
                        weight=ft.FontWeight.BOLD,
                    ),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=2,
            ),
            width=40,
            height=40,
            border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
            border_radius=4,
            bgcolor=FONDO_TEXTFIELDS_COLOR,
            alignment=ft.Alignment.CENTER,
            on_click=self._on_toggle_face,
            tooltip=t("Cara"),
            disabled=True,
        )

        # Determinar icono inicial basado en el tema actual
        es_oscuro = tema_flet == ft.ThemeMode.DARK
        icono_tema = ft.Icons.LIGHT_MODE if es_oscuro else ft.Icons.DARK_MODE

        self.icon_theme_toggle = ft.Container(
            content=ft.Icon(icono_tema, size=24, color=TEXTOS_FASE_1_COLOR),
            width=40,
            height=40,
            border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
            border_radius=4,
            bgcolor=FONDO_TEXTFIELDS_COLOR,
            alignment=ft.Alignment.CENTER,
            on_click=self._on_toggle_theme,
            tooltip=t("Cambiar modo día/noche"),
        )

        # Diálogo de información local duplicado (independiente de `app_ui_items`)
        def crear_dialogo_info_local(page):
            try:
                w = int(page.width * 0.9) if getattr(page, "width", None) else 1000
            except Exception:
                w = 1000
            try:
                h = int(page.height * 0.85) if getattr(page, "height", None) else 700
            except Exception:
                h = 700
            w = max(600, w)
            h = max(300, h)

            contenido = ft.Container(
                ft.Column(
                    [
                        ft.Text(
                            "Juan Antonio Picornell Richarte",
                            size=18,
                            weight=ft.FontWeight.BOLD,
                        ),
                        ft.Text(t("PAGE_NUMBER_VERSION"), size=16),
                        ft.Row(
                            [
                                ft.Container(
                                    content=ft.Icon(
                                        ft.Icons.COFFEE, size=18, color=ICONO_PREF_COLOR
                                    ),
                                    margin=ft.Margin.only(top=2),
                                ),
                                ft.Text(
                                    spans=[
                                        ft.TextSpan(
                                            t("INVITE_COFFEE"),
                                            url="https://paypal.me/japr99",
                                            style=ft.TextStyle(
                                                color=TEXTO_COLOR_GENERICO,
                                                decoration=ft.TextDecoration.UNDERLINE,
                                                weight=ft.FontWeight.BOLD,
                                            ),
                                        )
                                    ],
                                    size=14,
                                ),
                            ],
                            spacing=6,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        ft.Container(height=10),
                        ft.Text(
                            t("INFO_PAGENUMBER"),
                            size=14,
                        ),
                        ft.Divider(height=1, color=BORDE_TEXTFIELDS_COLOR),
                        ft.Container(height=10),
                        ft.Text(
                            spans=[
                                ft.TextSpan(
                                    t("LICENSE_NOTICE").rsplit(
                                        "gnu.org/licenses/agpl-3.0.html", 1
                                    )[0]
                                ),
                                ft.TextSpan(
                                    "gnu.org/licenses/agpl-3.0.html",
                                    url="https://www.gnu.org/licenses/agpl-3.0.html",
                                    style=ft.TextStyle(
                                        color=TEXTO_COLOR_GENERICO,
                                        decoration=ft.TextDecoration.UNDERLINE,
                                        weight=ft.FontWeight.BOLD,
                                    ),
                                ),
                            ],
                            size=12,
                        ),
                    ],
                    spacing=8,
                    scroll="auto",
                ),
                width=w,
                height=h,
                padding=ft.Padding(12, 8, 12, 8),
            )

            dialogo = ft.AlertDialog(
                modal=True,
                title=ft.Text(
                    t("Información"),
                    weight=ft.FontWeight.BOLD,
                    size=24,
                    text_align=ft.TextAlign.CENTER,
                ),
                content=contenido,
                actions=[
                    ft.Button(
                        content=t("Volver"),
                        on_click=lambda e: e.page.pop_dialog(),
                        width=110,
                        bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
                        style=ft.ButtonStyle(
                            color={
                                ft.ControlState.DEFAULT: BOTONES_GENERICOS_COLOR,
                                ft.ControlState.HOVERED: BOTONES_GENERICOS_HOVER_COLOR,
                            },
                            overlay_color=BOTONES_GENERICOS_OVERLAY_COLOR,
                            padding=ft.Padding(0, 0, 0, 0),
                            shape=ft.RoundedRectangleBorder(radius=10),
                        ),
                    ),
                ],
                bgcolor=FONDO_ALERT_DIALOG,
                actions_alignment=ft.MainAxisAlignment.END,
            )
            return dialogo

        self.icon_info = ft.Container(
            content=ft.Icon(ft.Icons.INFO_OUTLINED, size=24, color=TEXTOS_FASE_1_COLOR),
            width=40,
            height=40,
            border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
            border_radius=4,
            bgcolor=FONDO_TEXTFIELDS_COLOR,
            alignment=ft.Alignment.CENTER,
            on_click=lambda e: e.page.show_dialog(crear_dialogo_info_local(e.page)),
            tooltip=t("Información"),
        )

        # (Removed) botón de depuración: borrar preferencias y cerrar la app

        # ...eliminado: la creación de self.top_icons_row ya está antes de self.left_panel...

        # Columna de iconos (ya sin los iconos principales)
        self.icons_column = ft.Container(
            content=ft.Column(
                [
                    ft.Divider(height=1, thickness=2, color=TEXTOS_FASE_1_COLOR),
                    # Iconos de doble cara
                    self.icon_paper_settings,
                    ft.Divider(height=1, thickness=2, color=TEXTOS_FASE_1_COLOR),
                    self.icon_double_sided,
                    self.icon_face,
                    ft.Divider(height=1, thickness=2, color=TEXTOS_FASE_1_COLOR),
                    self.icon_text_settings,
                    self.icon_variable_text_settings,
                    self.icon_barcode_settings,
                    self.icon_excel,
                    ft.Divider(height=1, thickness=2, color=TEXTOS_FASE_1_COLOR),
                    self.icon_load_background,
                    self.icon_image_settings,
                    self.icon_remove_background,
                    ft.Divider(height=1, thickness=2, color=TEXTOS_FASE_1_COLOR),
                    # Iconos de archivo
                    self.icon_preview_page,
                    self.icon_export_pdf,
                    ft.Divider(height=1, thickness=2, color=TEXTOS_FASE_1_COLOR),
                    self.icon_theme_toggle,
                    ft.Divider(height=1, thickness=2, color=TEXTOS_FASE_1_COLOR),
                    self.icon_info,
                    ft.Divider(height=1, thickness=2, color=TEXTOS_FASE_1_COLOR),
                    ft.Container(expand=True),  # Espaciador flexible
                    self.icon_preferences,
                    self.icon_exit_app,
                    # Bloque informativo (nombre y año) estilo consistente con los iconos del menú
                    ft.Container(
                        content=ft.Column(
                            [
                                ft.Text(
                                    "JAPR",
                                    size=12,
                                    weight=ft.FontWeight.BOLD,
                                    color=TEXTO_COLOR_GENERICO,
                                    text_align=ft.TextAlign.CENTER,
                                ),
                                ft.Divider(
                                    height=1,
                                    thickness=1,
                                    color=TEXTO_COLOR_GENERICO,
                                    opacity=0.3,
                                ),
                                ft.Text(
                                    "2026",
                                    size=12,
                                    weight=ft.FontWeight.BOLD,
                                    color=TEXTO_COLOR_GENERICO,
                                    text_align=ft.TextAlign.CENTER,
                                ),
                            ],
                            spacing=2,
                            alignment=ft.MainAxisAlignment.CENTER,
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        width=40,
                        height=40,
                        border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
                        border_radius=4,
                        bgcolor=FONDO_TEXTFIELDS_COLOR,
                        alignment=ft.Alignment.CENTER,
                        margin=ft.Margin(0, 8, 0, 0),
                        visible=False,
                    ),
                ],
                spacing=5,
            ),
            width=50,
            padding=ft.Padding.only(top=0, left=5, right=5, bottom=5),
            bgcolor=FONDO_APP,
        )

        # ===== PANEL DERECHO =====

        # Información de página (texto actualizable)
        self.page_size_text = ft.Text(
            t("Tamaño de página: {0}").format(
                f"{DEFAULT_PAGE_WIDTH_MM:.0f} x {DEFAULT_PAGE_HEIGHT_MM:.0f} mm"
            ),
            size=11,
            weight=ft.FontWeight.W_600,
            color=TEXTOS_FASE_1_COLOR,
        )

        self.preview_page_field = self._create_textfield(
            "1", width=70, on_change=self._on_preview_page_change
        )
        self.preview_page_field.text_align = ft.TextAlign.CENTER
        self.preview_page_field.on_blur = self._on_preview_page_blur
        # Ajustar padding vertical para centrar el número dentro del campo
        try:
            # Restaurar padding vertical por defecto para centrar correctamente
            self.preview_page_field.content_padding = ft.Padding(2, 0, 6, 0)
        except Exception:
            pass
        self.total_pages_text = ft.Text(
            t("de {0}").format(DEFAULT_END_NUMBER * DEFAULT_COPIES),
            size=11,
            color=TEXTOS_FASE_1_COLOR,
        )

        # Botones de navegación de páginas
        self.btn_prev_page = ft.Container(
            content=ft.Icon(ft.Icons.CHEVRON_LEFT, size=16, color=TEXTOS_FASE_1_COLOR),
            width=24,
            height=24,
            border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
            border_radius=12,
            bgcolor=FONDO_TEXTFIELDS_COLOR,
            alignment=ft.Alignment.CENTER,
            on_click=lambda e: self._navigate_page(-1),
            tooltip=t("Página anterior"),
        )

        self.btn_next_page = ft.Container(
            content=ft.Icon(ft.Icons.CHEVRON_RIGHT, size=16, color=TEXTOS_FASE_1_COLOR),
            width=24,
            height=24,
            border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
            border_radius=12,
            bgcolor=FONDO_TEXTFIELDS_COLOR,
            alignment=ft.Alignment.CENTER,
            on_click=lambda e: self._navigate_page(1),
            tooltip=t("Página siguiente"),
        )

        # --- Controles de zoom y navegación: deben crearse antes de usarse en page_info ---
        # Botón pequeño para mostrar/ocultar guías de ajuste (líneas vertical/horizontal)
        guides_initial = getattr(self.interactive_viewer, "show_guides", True)
        self.btn_toggle_guides = ft.Container(
            content=ft.Icon(
                ft.Icons.VISIBILITY if guides_initial else ft.Icons.VISIBILITY_OFF,
                size=int(self.interactive_viewer.corner_size * 0.6),
                color=(
                    TEXTOS_FASE_1_COLOR
                    if guides_initial
                    else BOTONES_GENERICOS_TEXTO_COLOR
                ),
            ),
            width=int(self.interactive_viewer.corner_size),
            height=int(self.interactive_viewer.corner_size),
            border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
            border_radius=4,
            bgcolor=(
                FONDO_TEXTFIELDS_COLOR
                if guides_initial
                else BOTONES_GENERICOS_OVERLAY_COLOR
            ),
            alignment=ft.Alignment.CENTER,
            on_click=self._on_toggle_guides,
            tooltip=t("Mostrar/ocultar guías"),
        )
        # Botones compactos (24x24) para guías y snap — después del slider en zoom_controls
        snap_initial = getattr(self.interactive_viewer, "magnetic_snap_active", True)
        guides_color = (
            TEXTOS_FASE_1_COLOR if guides_initial else BOTONES_GENERICOS_TEXTO_COLOR
        )
        guides_bg = (
            FONDO_TEXTFIELDS_COLOR
            if guides_initial
            else BOTONES_GENERICOS_OVERLAY_COLOR
        )
        snap_color = (
            BOTONES_GENERICOS_TEXTO_COLOR if snap_initial else TEXTOS_FASE_1_COLOR
        )
        snap_bg = (
            BOTONES_GENERICOS_OVERLAY_COLOR if snap_initial else FONDO_TEXTFIELDS_COLOR
        )
        self.btn_toggle_guides_compact = ft.Container(
            content=ft.Icon(ft.Icons.VISIBILITY, size=16, color=guides_color),
            width=24,
            height=24,
            border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
            border_radius=4,
            bgcolor=guides_bg,
            alignment=ft.Alignment.CENTER,
            on_click=self._on_toggle_guides,
            tooltip=t("Mostrar/ocultar guías"),
        )
        self.btn_toggle_snap_compact = ft.Container(
            content=ft.Icon(ft.Icons.COMPRESS_OUTLINED, size=16, color=snap_color),
            width=24,
            height=24,
            border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
            border_radius=4,
            bgcolor=snap_bg,
            alignment=ft.Alignment.CENTER,
            on_click=self._on_toggle_snap,
            tooltip=t("Activar/desactivar snap magnético"),
        )
        # === Trío genérico de GUÍAS (magnético · visibilidad · bloqueo) ===
        # Independientes de los botones de posiciones/números: operan sobre
        # position_guides (set_snap_all / set_show / set_locked_all — ambas
        # caras). Clon del patrón compact 2804-2825, mismo borde/radius.
        # position_guides se crea en __init__ DESPUÉS de _create_components (:543),
        # así que aquí se lee tolerante con los defaults de PositionGuides.
        _pg = getattr(self, "position_guides", None)
        magnetic_initial = getattr(_pg, "snap_active", True)
        visibility_initial = getattr(_pg, "show", True)
        lock_initial = getattr(_pg, "locked", False)
        magnetic_color = (
            BOTONES_GENERICOS_TEXTO_COLOR if magnetic_initial else TEXTOS_FASE_1_COLOR
        )
        magnetic_bg = (
            BOTONES_GENERICOS_OVERLAY_COLOR if magnetic_initial else FONDO_TEXTFIELDS_COLOR
        )
        visibility_color = (
            BOTONES_GENERICOS_TEXTO_COLOR if visibility_initial else TEXTOS_FASE_1_COLOR
        )
        visibility_bg = (
            BOTONES_GENERICOS_OVERLAY_COLOR if visibility_initial else FONDO_TEXTFIELDS_COLOR
        )
        lock_color = (
            BOTONES_GENERICOS_TEXTO_COLOR if lock_initial else TEXTOS_FASE_1_COLOR
        )
        lock_bg = (
            BOTONES_GENERICOS_OVERLAY_COLOR if lock_initial else FONDO_TEXTFIELDS_COLOR
        )
        self.btn_toggle_guides_magnetic_compact = ft.Container(
            content=ft.Icon(ft.Icons.COMPRESS_OUTLINED, size=16, color=magnetic_color),
            width=24,
            height=24,
            border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
            border_radius=4,
            bgcolor=magnetic_bg,
            alignment=ft.Alignment.CENTER,
            on_click=self._on_toggle_guides_magnetic,
            tooltip=t("Activar/desactivar snap magnético a guías"),
        )
        self.btn_toggle_guides_visibility_compact = ft.Container(
            content=ft.Icon(ft.Icons.POWER_SETTINGS_NEW, size=16, color=visibility_color),
            width=24,
            height=24,
            border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
            border_radius=4,
            bgcolor=visibility_bg,
            alignment=ft.Alignment.CENTER,
            on_click=self._on_toggle_guides_visibility,
            tooltip=t("Activar/desactivar guías de posición"),
        )
        self.btn_toggle_guides_lock_compact = ft.Container(
            content=ft.Icon(ft.Icons.LOCK_OUTLINED, size=16, color=lock_color),
            width=24,
            height=24,
            border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
            border_radius=4,
            bgcolor=lock_bg,
            alignment=ft.Alignment.CENTER,
            on_click=self._on_toggle_guides_lock,
            tooltip=t("Bloquear/desbloquear guías de posición"),
        )
        # Botón de reset (posición y zoom) — estilo consistente con los iconos de menú
        self.btn_reset_view = ft.Container(
            content=ft.Icon(
                ft.Icons.CENTER_FOCUS_STRONG,
                size=int(self.interactive_viewer.corner_size * 0.6),
                color=TEXTOS_FASE_1_COLOR,
            ),
            width=int(self.interactive_viewer.corner_size),
            height=int(self.interactive_viewer.corner_size),
            border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
            border_radius=4,
            bgcolor=FONDO_TEXTFIELDS_COLOR,
            alignment=ft.Alignment.CENTER,
            on_click=lambda e: self._reset_view(),
            tooltip=t("Resetear vista"),
        )
        # Versión compacta temprana del botón reset (24x24) para usar en el encabezado
        # y evitar referencias a atributos no creados aún.
        self.btn_reset_view_compact = ft.Container(
            content=ft.Icon(
                ft.Icons.CENTER_FOCUS_STRONG, size=16, color=TEXTOS_FASE_1_COLOR
            ),
            width=24,
            height=24,
            border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
            border_radius=4,
            bgcolor=FONDO_TEXTFIELDS_COLOR,
            alignment=ft.Alignment.CENTER,
            on_click=lambda e: self._reset_view(),
            tooltip=t("Resetear vista"),
        )
        # Slider compacto usado en el encabezado (height=20)
        self.zoom_slider = ft.Slider(
            min=MIN_ZOOM,
            max=MAX_ZOOM,
            value=DEFAULT_ZOOM,
            divisions=40,
            height=35,
            on_change=self._on_zoom_change,  # CAMBIO: aplicar zoom en vivo durante arrastre
            on_change_end=self._on_zoom_change_end,
            expand=True,
            # Evitar overlay/halo grande al hover: hacerlo transparente y quitar padding
            overlay_color=ft.Colors.TRANSPARENT,
            padding=ft.Padding(0, 0, 0, 0),
            thumb_color=TEXTOS_FASE_1_COLOR,
        )
        self.zoom_slider_container = ft.Container(
            content=self.zoom_slider,
            width=200,
        )
        # Controles de zoom compactos iniciales (usados en page_info)
        self.zoom_controls = ft.Row(
            [
                self.btn_reset_view_compact,
                self.zoom_slider_container,
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=8,
        )
        # Iconos compactos de guías y snap — centrados entre slider y navegación
        self.iconos_compactos = ft.Row(
            [
                self.btn_toggle_guides_compact,
                self.btn_toggle_snap_compact,
                # Barra de separación: 2 botones de posiciones (izq) | 3 de guías (der)
                ft.VerticalDivider(width=1, color=BORDE_TEXTFIELDS_COLOR),
                self.btn_toggle_guides_magnetic_compact,
                self.btn_toggle_guides_visibility_compact,
                self.btn_toggle_guides_lock_compact,
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        # Nota: la definición compacta del slider y zoom_controls se crea
        # más abajo para evitar duplicados y asegurar que `page_info`
        # reciba la instancia final (compacta) del control.
        # Panel superior: Tamaño de página a la izquierda, controles de zoom en el centro, contador a la derecha
        self.page_info = ft.Container(
            content=ft.Row(
                [
                    # Izquierda: Tamaño de página
                    self.page_size_text,
                    # Centro: controles de zoom (slider + reset)
                    self.zoom_controls,
                    # Centro-derecha: iconos compactos (guias + snap)
                    self.iconos_compactos,
                    # Derecha: Navegación de páginas
                    ft.Row(
                        [
                            self.btn_prev_page,
                            ft.Text(t("Página:"), size=11, color=TEXTOS_FASE_1_COLOR),
                            self.preview_page_field,
                            self.total_pages_text,
                            self.btn_next_page,
                        ],
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=2,
            ),
            height=52,  # Altura fija para el panel superior
            alignment=ft.Alignment.CENTER,
            padding=0,
        )

        # Visor interactivo
        # Caja gris vacía en la esquina donde se juntan las reglas
        try:
            self.interactive_viewer.corner_space = ft.Container(
                width=self.interactive_viewer.corner_size,
                height=self.interactive_viewer.corner_size,
                bgcolor=ft.Colors.GREY_300,
            )
        except Exception:
            pass

        self.viewer = self.interactive_viewer.build()

        # Asegurar que `page_info` use la instancia final de `zoom_controls`
        # === RESETEAR ESTADO DE MODIFICADO TRAS CARGAR PREFERENCIAS ===
        self.project_modified = False
        self._saved_state_snapshot = self._create_state_snapshot()
        print("[INIT] Estado de modificado reseteado tras cargar preferencias")
        try:
            if hasattr(self, "page_info") and self.page_info is not None:
                self.page_info.content.controls[1] = self.zoom_controls
                try:
                    self.page_info.update()
                except Exception:
                    pass
        except Exception:
            pass

        # Panel derecho completo
        self.right_panel = ft.Container(
            content=ft.Column(
                [
                    self.page_info,  # Row compacto en una línea (ahora incluye los controles de zoom)
                    # Viewer con expand para ocupar todo el espacio disponible
                    self.viewer,
                    # self.zoom_controls,  # Ya no se muestra abajo
                ],
                spacing=0,
                expand=True,
            ),  # Spacing reducido de 10 a 5
            bgcolor=FONDO_APP,
            padding=ft.Padding.only(top=0, left=5, right=5, bottom=5),
            expand=True,
        )

        # ===== LAYOUT PRINCIPAL =====

        self.main_content = ft.Row(
            [
                self.icons_column,
                ft.VerticalDivider(width=1, color=BORDE_TEXTFIELDS_COLOR),
                self.left_panel,
                ft.VerticalDivider(width=1, color=BORDE_TEXTFIELDS_COLOR),
                self.right_panel,
            ],
            spacing=0,
            expand=True,
        )

        # Aplicar la unidad guardada a las reglas al arranque (el viewer siempre
        # arranca con UNIT_MM; hay que sincronizarlo con la preferencia del usuario).
        if ENABLE_RULERS and self.current_unit != UNIT_MM:
            try:
                self.interactive_viewer.set_ruler_unit(self.current_unit)
            except Exception:
                pass

        # Inicializar estado del botón de ajustes (desactivado al inicio, sin update)
        self._update_image_settings_button_state(do_update=False)

    def _create_textfield(
        self,
        value: str,
        width: int = 140,
        read_only: bool = False,
        disabled: bool = False,
        on_change=None,
        text_size: int = 11,
    ) -> ft.TextField:
        """Crea un TextField con estilo consistente"""
        return ft.TextField(
            value=value,
            width=width,
            height=20,
            text_size=text_size,
            content_padding=ft.Padding(2, 0, 6, 0),
            filled=True,
            fill_color=FONDO_TEXTFIELDS_COLOR,
            read_only=read_only,
            disabled=disabled,
            text_style=ft.TextStyle(color=TEXTO_COLOR_GENERICO),
            on_change=on_change,border=ft.OutlineInputBorder(border_radius=3, side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)))

    def _on_toggle_guides(self, e):
        """Handler para alternar visibilidad de guías en el viewer."""
        try:
            current = getattr(self.interactive_viewer, "show_guides", True)
            new = not current
            if hasattr(self.interactive_viewer, "set_show_guides"):
                self.interactive_viewer.set_show_guides(new)
            else:
                self.interactive_viewer.show_guides = new
                if hasattr(self.interactive_viewer, "_redraw_all"):
                    self.interactive_viewer._redraw_all()

            icon = ft.Icons.VISIBILITY if new else ft.Icons.VISIBILITY_OFF
            new_color = TEXTOS_FASE_1_COLOR if new else BOTONES_GENERICOS_TEXTO_COLOR
            new_bg = FONDO_TEXTFIELDS_COLOR if new else BOTONES_GENERICOS_OVERLAY_COLOR
            # Actualizar icono de esquina (corner_space)
            self.btn_toggle_guides.content = ft.Icon(
                icon,
                size=int(self.interactive_viewer.corner_size * 0.6),
                color=new_color,
            )
            self.btn_toggle_guides.bgcolor = new_bg
            # Actualizar icono compacto del toolbar
            self.btn_toggle_guides_compact.content = ft.Icon(
                icon,
                size=16,
                color=new_color,
            )
            self.btn_toggle_guides_compact.bgcolor = new_bg
            try:
                self.btn_toggle_guides.update()
            except Exception:
                pass
            try:
                self.btn_toggle_guides_compact.update()
            except Exception:
                pass
        except Exception as ex:
            print(f"[ERROR] Toggle guides failed: {ex}")

    def _on_toggle_snap(self, e):
        """Handler para alternar snap magnético en el viewer."""
        try:
            new = not getattr(self, "magnetic_snap_active", True)
            self.magnetic_snap_active = new
            if hasattr(self.interactive_viewer, "magnetic_snap_active"):
                self.interactive_viewer.magnetic_snap_active = new
            new_color = BOTONES_GENERICOS_TEXTO_COLOR if new else TEXTOS_FASE_1_COLOR
            new_bg = BOTONES_GENERICOS_OVERLAY_COLOR if new else FONDO_TEXTFIELDS_COLOR
            self.btn_toggle_snap_compact.content = ft.Icon(
                ft.Icons.COMPRESS_OUTLINED,
                size=16,
                color=new_color,
            )
            self.btn_toggle_snap_compact.bgcolor = new_bg
            try:
                self.btn_toggle_snap_compact.update()
            except Exception:
                pass
        except Exception as ex:
            print(f"[ERROR] Toggle snap failed: {ex}")

    def _on_toggle_guides_magnetic(self, e):
        """Handler genérico (ambas caras): snap magnético a guías. INDEPENDIENTE de visibilidad y bloqueo."""
        try:
            pg = getattr(self, "position_guides", None)
            new = not getattr(pg, "snap_active", True)
            if pg is not None and hasattr(pg, "set_snap_all"):
                pg.set_snap_all(new)
            new_color = BOTONES_GENERICOS_TEXTO_COLOR if new else TEXTOS_FASE_1_COLOR
            new_bg = BOTONES_GENERICOS_OVERLAY_COLOR if new else FONDO_TEXTFIELDS_COLOR
            self.btn_toggle_guides_magnetic_compact.content = ft.Icon(
                ft.Icons.COMPRESS_OUTLINED,
                size=16,
                color=new_color,
            )
            self.btn_toggle_guides_magnetic_compact.bgcolor = new_bg
            try:
                self.btn_toggle_guides_magnetic_compact.update()
            except Exception:
                pass
        except Exception as ex:
            print(f"[ERROR] Toggle guides magnetic failed: {ex}")

    def _on_toggle_guides_visibility(self, e):
        """Handler genérico (ambas caras): activar/desactivar guías. Al desactivar,
        el snap efectivo cae (el viewer exige show) pero la memoria del botón
        magnético queda intacta; al reactivar, el snap vuelve según ese botón."""
        try:
            pg = getattr(self, "position_guides", None)
            new = not getattr(pg, "show", True)
            if pg is not None and hasattr(pg, "set_show"):
                pg.set_show(new)
            # Solo guías de posición: el dibujo gatea por pg.show (:4862).
            # NO tocar viewer.set_show_guides — ese flag es de las líneas
            # guía de los elementos (posiciones) y lo posee su botón izquierdo.
            if hasattr(self.interactive_viewer, "_redraw_all"):
                self.interactive_viewer._redraw_all()
            icon = ft.Icons.POWER_SETTINGS_NEW if new else ft.Icons.POWER_OFF
            new_color = BOTONES_GENERICOS_TEXTO_COLOR if new else TEXTOS_FASE_1_COLOR
            new_bg = BOTONES_GENERICOS_OVERLAY_COLOR if new else FONDO_TEXTFIELDS_COLOR
            self.btn_toggle_guides_visibility_compact.content = ft.Icon(
                icon,
                size=16,
                color=new_color,
            )
            self.btn_toggle_guides_visibility_compact.bgcolor = new_bg
            try:
                self.btn_toggle_guides_visibility_compact.update()
            except Exception:
                pass
        except Exception as ex:
            print(f"[ERROR] Toggle guides visibility failed: {ex}")

    def _on_toggle_guides_lock(self, e):
        """Handler genérico (ambas caras): bloquear/desbloquear guías. INDEPENDIENTE de snap y visibilidad."""
        try:
            pg = getattr(self, "position_guides", None)
            new = not getattr(pg, "locked", False)
            if pg is not None and hasattr(pg, "set_locked_all"):
                pg.set_locked_all(new)
            if hasattr(self.interactive_viewer, "_redraw_all"):
                self.interactive_viewer._redraw_all()
            icon = ft.Icons.LOCK_OUTLINED if new else ft.Icons.LOCK_OPEN
            new_color = BOTONES_GENERICOS_TEXTO_COLOR if new else TEXTOS_FASE_1_COLOR
            new_bg = BOTONES_GENERICOS_OVERLAY_COLOR if new else FONDO_TEXTFIELDS_COLOR
            self.btn_toggle_guides_lock_compact.content = ft.Icon(
                icon,
                size=16,
                color=new_color,
            )
            self.btn_toggle_guides_lock_compact.bgcolor = new_bg
            try:
                self.btn_toggle_guides_lock_compact.update()
            except Exception:
                pass
        except Exception as ex:
            print(f"[ERROR] Toggle guides lock failed: {ex}")

    def _fmt_mm(self, value_mm: float, unit: str = None) -> str:
        """Formatea un valor en mm a una unidad con decimales fijos (2; 3 en pulgadas)."""
        unit = unit or self.current_unit
        return format_unit(value_mm, unit)

    def _create_dropdown_compact(
        self,
        options: list,
        value: str,
        width: int = 140,
        on_change=None,
        text_size: int = 11,
    ) -> ft.Container:
        """Crea un Dropdown compacto con altura fija de 20px igual a los textfields"""
        # Encontrar el texto a mostrar basándose en el valor inicial (puede ser tupla o string)
        display_text = str(value)
        for opt in options:
            if isinstance(opt, tuple) and opt[0] == value:
                # Resolver etiquetas traducibles (p. ej. UNIT_INCHES / UNIT_PICAS)
                candidate = opt[1]
                if candidate == UNIT_INCHES:
                    display_text = str(get_unit_inches())
                elif candidate == UNIT_PICAS:
                    display_text = str(get_unit_picas())
                else:
                    display_text = str(candidate)
                break
            elif not isinstance(opt, tuple) and opt == value:
                display_text = str(opt)
                break

        texto_valor = ft.Text(
            display_text,
            size=text_size,
            color=DROPDOWN_TEXT_STYLE_COLOR,
            no_wrap=True,
            expand=True,
            overflow=ft.TextOverflow.ELLIPSIS,
            data=value,  # La clave real subyacente
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
                # Traducir la etiqueta mostrada cuando la tupla contiene una clave traducible
                label = opt[1]
                if label == UNIT_INCHES:
                    label = get_unit_inches()
                elif label == UNIT_PICAS:
                    label = get_unit_picas()
                items.append(
                    ft.PopupMenuItem(
                        content=str(label), data=str(opt[0]), on_click=on_item_click
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
            height=20,
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
                        # icon_size=16,
                        splash_radius=0,
                        menu_position=ft.PopupMenuPosition.UNDER,
                        bgcolor=DROPDOWN_FONDO_MENU_COLOR,
                        shadow_color=BORDE_TEXTFIELDS_COLOR,
                        items=items,
                        tooltip=t("Abrir el menu"),
                    ),
                ],
            ),
        )

    def _create_form_row(self, label: str, control: ft.Control) -> ft.Row:
        """Crea una fila de formulario con label y control"""
        return ft.Row(
            [
                ft.Text(label, size=11, color=TEXTOS_FASE_1_COLOR, width=120),
                control,
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

    def _set_dropdown_value(self, dropdown, options, value):
        """Muestra la etiqueta del valor en un dropdown compacto sin reconstruir items."""
        display = str(value)
        for opt in options:
            if isinstance(opt, tuple) and opt[0] == value:
                display = str(opt[1])
                break
            elif not isinstance(opt, tuple) and opt == value:
                display = str(opt)
                break
        dropdown.content.controls[0].value = display
        dropdown.content.controls[0].data = value

    def _set_alignment_dropdown_options(self, options, value):
        """Reconstruye las opciones del dropdown compartido Alineamiento/Posición."""
        dropdown = self.alignment_dropdown
        texto_valor = dropdown.content.controls[0]
        menu = dropdown.content.controls[1]

        display_text = str(value)
        for opt in options:
            if isinstance(opt, tuple) and opt[0] == value:
                display_text = str(opt[1])
                break
            elif not isinstance(opt, tuple) and opt == value:
                display_text = str(opt)
                break
        texto_valor.value = display_text
        texto_valor.data = value

        def on_item_click(e):
            selected_text = e.control.content
            selected_data = (
                e.control.data if e.control.data is not None else selected_text
            )
            texto_valor.value = selected_text
            texto_valor.data = selected_data
            if dropdown.data is not None and "on_change" in dropdown.data:
                dropdown.data["on_change"](selected_data)
            texto_valor.update()

        menu.items = []
        for opt in options:
            if isinstance(opt, tuple):
                menu.items.append(
                    ft.PopupMenuItem(
                        content=str(opt[1]), data=str(opt[0]), on_click=on_item_click
                    )
                )
            else:
                menu.items.append(
                    ft.PopupMenuItem(
                        content=str(opt), data=str(opt), on_click=on_item_click
                    )
                )

    def _update_position_fields_state(self):
        """Habilita o deshabilita los campos de posición según si hay una posición seleccionada"""
        has_selection = self.selected_position is not None

        # Campos de texto
        self.horizontal_field.disabled = not has_selection
        self.vertical_field.disabled = not has_selection
        self.add_field.disabled = not has_selection

        # Dropdowns
        self.rotation_dropdown.disabled = not has_selection
        self.alignment_dropdown.disabled = not has_selection
        self.text_style_dropdown.disabled = not has_selection

        # Actualizar visualización
        self.horizontal_field.update()
        self.vertical_field.update()
        self.add_field.update()
        self.rotation_dropdown.update()
        self.alignment_dropdown.update()
        self.text_style_dropdown.update()

    def _toggle_sections_by_type(self, pos_type: str):
        """Muestra/oculta los grupos de campos dentro de measures_section según el tipo de posición.
        Si pos_type es None, oculta todo (nada seleccionado)."""
        has_selection = pos_type is not None
        self._separator_line.visible = has_selection
        self._separator_line_bc.visible = has_selection
        self._separator_line_vt.visible = has_selection
        self._common_fields.visible = has_selection
        self._number_fields.visible = pos_type == "number"
        self._barcode_fields.visible = pos_type == "barcode"
        self._variable_text_fields.visible = pos_type == "variable_text"

        try:
            self.measures_section.update()
        except Exception:
            pass

    def _update_barcode_dimensions_visibility(self):
        """Muestra/oculta Ancho+Alto vs Tamaño según la simbología del barcode seleccionado."""
        if self.selected_position is None:
            return
        bc_data = self.interactive_viewer.get_barcode_data(self.selected_position)
        sym = bc_data.get("symbology", "") if bc_data else ""
        is_qr = sym == "qr"
        is_itf14 = sym == "itf14"
        is_code39 = sym == "code39"
        is_code128 = sym == "code128"
        is_ean5 = sym == "ean5"
        is_upca = sym == "upca"
        is_upce = sym == "upce"
        is_ean13 = sym == "ean13"
        is_ean8 = sym == "ean8"
        is_isbn13 = sym == "isbn13"
        is_pdf417 = sym == "pdf417"
        is_datamatrix = _is_datamatrix_family(sym)
        self._dim_barcode_row.visible = not is_qr and not is_pdf417
        self._dim_qr_row.visible = is_qr
        self._dim_pdf417_row.visible = is_pdf417
        if hasattr(self, "_body_gap_row") and self._body_gap_row is not None:
            stacked = is_qr or is_datamatrix or is_pdf417
            has_hri_pos = (
                stacked or is_code128 or is_code39 or is_itf14
            )
            self._cuerpo_row.visible = stacked
            self._alineacion_row.visible = stacked
            self._interlineado_row.visible = stacked
            self._distancia_row.visible = stacked
            self._posicion_hri_row.visible = has_hri_pos
            self._body_gap_row.visible = has_hri_pos
            if has_hri_pos:
                self._sync_hri_position_dropdown(sym)
            if stacked:
                self._sync_hri_align_dropdown(sym)
            self._body_gap_row.update()
        if is_pdf417:
            self._lbl_tamano.value = t("Ancho ({0})").format(
                _unit_abbr(self.current_unit)
            )
        else:
            self._lbl_tamano.value = t("Tamaño ({0})").format(
                _unit_abbr(self.current_unit)
            )
        self._lbl_tamano.update()
        if hasattr(self, "_alto_form_row") and self._alto_form_row is not None:
            self._alto_form_row.visible = not is_pdf417 and not is_datamatrix
            self._alto_form_row.update()
        if (
            hasattr(self, "_datamatrix_alto_row")
            and self._datamatrix_alto_row is not None
        ):
            self._datamatrix_alto_row.visible = is_datamatrix
            self._datamatrix_alto_row.update()
        if (
            hasattr(self, "_itf14_settings_row")
            and self._itf14_settings_row is not None
        ):
            self._itf14_settings_row.visible = is_itf14
            self._itf14_settings_row.update()
        if (
            hasattr(self, "_code39_settings_row")
            and self._code39_settings_row is not None
        ):
            self._code39_settings_row.visible = is_code39
            self._code39_settings_row.update()
        if (
            hasattr(self, "_code128_settings_row")
            and self._code128_settings_row is not None
        ):
            self._code128_settings_row.visible = is_code128
            self._code128_settings_row.update()
        if hasattr(self, "_ean5_settings_row") and self._ean5_settings_row is not None:
            self._ean5_settings_row.visible = is_ean5
            self._ean5_settings_row.update()
        if (
            hasattr(self, "_generic_body_settings_row")
            and self._generic_body_settings_row is not None
        ):
            self._generic_body_settings_row.visible = (
                is_upca or is_upce or is_ean13 or is_ean8 or is_isbn13
            )
            self._generic_body_settings_row.update()
        self._dim_barcode_row.update()
        self._dim_qr_row.update()
        self._dim_pdf417_row.update()
        # Sync shared body/gap when symbology changes
        # Fuente de verdad: el perfil activo (bc_data puede estar obsoleto hasta
        # que _redraw_all sincroniza perfil->bc_data).
        _p = getattr(self, "_active_barcode_profile", None)
        if _p is not None:
            body_val = str(
                _p.barcode_font_size if _p.barcode_font_size is not None else 13.0
            )
            _sym = _p.symbology
            if _sym == "code39":
                gap_mm = (
                    _p.code39_hri_gap_mm if _p.code39_hri_gap_mm is not None else 2.0
                )
            elif _sym == "itf14":
                gap_mm = (
                    _p.itf14_hri_gap_mm if _p.itf14_hri_gap_mm is not None else 2.0
                )
            elif _sym == "code128":
                gap_mm = (
                    _p.code128_hri_gap_mm if _p.code128_hri_gap_mm is not None else 2.0
                )
            elif _sym == "ean5":
                gap_mm = (
                    _p.ean5_hri_gap_mm if _p.ean5_hri_gap_mm is not None else 2.0
                )
            elif _sym == "qr":
                gap_mm = _p.qr_hri_gap_mm if _p.qr_hri_gap_mm is not None else 2.0
            elif _sym == "pdf417":
                gap_mm = (
                    _p.pdf417_hri_gap_mm if _p.pdf417_hri_gap_mm is not None else 2.0
                )
            elif _is_datamatrix_family(_sym):
                gap_mm = (
                    _p.datamatrix_hri_gap_mm
                    if _p.datamatrix_hri_gap_mm is not None
                    else 2.0
                )
            else:
                gap_mm = 0.0
            # Interlineado (line spacing) — solo QR/DM/PDF417
            if _sym == "qr":
                line_spacing = _p.qr_hri_line_spacing if _p.qr_hri_line_spacing is not None else 1.0
            elif _sym == "pdf417":
                line_spacing = _p.pdf417_hri_line_spacing if _p.pdf417_hri_line_spacing is not None else 1.0
            elif _is_datamatrix_family(_sym):
                line_spacing = _p.datamatrix_hri_line_spacing if _p.datamatrix_hri_line_spacing is not None else 1.0
            else:
                line_spacing = 1.0
        elif bc_data:
            body_val = str(bc_data.get("barcode_font_size", 13.0))
            if is_code39:
                gap_mm = float(bc_data.get("code39_hri_gap_mm", 2.0))
            elif is_itf14:
                gap_mm = float(bc_data.get("itf14_hri_gap_mm", 2.0))
            elif is_code128:
                gap_mm = float(bc_data.get("code128_hri_gap_mm", 2.0))
            elif is_ean5:
                gap_mm = float(bc_data.get("ean5_hri_gap_mm", 2.0))
            elif is_qr:
                gap_mm = float(bc_data.get("qr_hri_gap_mm", 2.0))
            elif is_pdf417:
                gap_mm = float(bc_data.get("pdf417_hri_gap_mm", 2.0))
            elif is_datamatrix:
                gap_mm = float(bc_data.get("datamatrix_hri_gap_mm", 2.0))
            else:
                gap_mm = 0.0
            if is_qr:
                line_spacing = float(bc_data.get("qr_hri_line_spacing", 1.0))
            elif is_pdf417:
                line_spacing = float(bc_data.get("pdf417_hri_line_spacing", 1.0))
            elif is_datamatrix:
                line_spacing = float(bc_data.get("datamatrix_hri_line_spacing", 1.0))
            else:
                line_spacing = 1.0
        if bc_data or _p is not None:
            self._itf14_body_field.value = body_val
            self._code39_body_field.value = body_val
            self._code128_body_field.value = body_val
            self._datamatrix_body_field.value = body_val
            self._ean5_body_field.value = body_val
            self._generic_body_field.value = body_val
            self._itf14_gap_field.value = self._fmt_mm(gap_mm)
            self._datamatrix_gap_field.value = self._fmt_mm(gap_mm)
            self._datamatrix_hri_line_spacing_field.value = f"{line_spacing:.1f}"
            self._itf14_body_field.update()
            self._code39_body_field.update()
            self._code128_body_field.update()
            self._datamatrix_body_field.update()
            self._ean5_body_field.update()
            self._generic_body_field.update()
            self._itf14_gap_field.update()
            self._datamatrix_gap_field.update()
            self._datamatrix_hri_line_spacing_field.update()

    def _on_select_position(self, num_id, from_viewer=False):
        """
        Selecciona una posición de la lista
        Actualiza el resaltado visual y la selección en el viewer
        Carga los datos de la posición en los controles UI

        Args:
            num_id: ID de la posición a seleccionar
            from_viewer: True si la selección viene del viewer (evita bucle infinito)
        """
        print(
            f"[DEBUG] _on_select_position llamado con num_id={num_id}, from_viewer={from_viewer}"
        )
        current_positions = self._get_current_positions()
        print(
            f"[DEBUG] Posiciones disponibles en {self.current_face}: {list(current_positions.keys())}"
        )
        print(f"[DEBUG] selected_position actual: {self.selected_position}")

        # Si ya está seleccionada esta posición, no hacer nada (evitar parpadeo)
        if self.selected_position == num_id:
            print(f"[DEBUG] Posición {num_id} ya está seleccionada, no hacer nada")
            return

        # IMPORTANTE: Recorrer TODA la lista y desactivar todos los items
        for pos_id, pos_data in current_positions.items():
            try:
                pos_data["item"].bgcolor = FONDO_TEXTFIELDS_COLOR  # No seleccionado: claro
                pos_data["item"].update()
            except (AssertionError, RuntimeError):
                pass

        # Actualizar variable de selección
        self.selected_position = num_id

        # Habilitar campos de posición
        self._update_position_fields_state()

        # Activar solo el item seleccionado
        if num_id in current_positions:
            position_name = current_positions[num_id]["name"]
            current_item = current_positions[num_id]["item"]
            try:
                current_item.bgcolor = FONDO_CALCULO_FASE_1  # Seleccionado: oscuro
                current_item.update()
            except (AssertionError, RuntimeError):
                pass
            print(f"[DEBUG] Seleccionada posición nueva: {num_id} ({position_name})")

        # Si la selección viene del viewer, asegurar que el item esté a la vista
        if from_viewer and num_id in current_positions:
            async def _do_scroll_to_position():
                await self.positions_list.scroll_to(
                    scroll_key=f"position_{num_id}", duration=300
                )

            self.page.run_task(_do_scroll_to_position)

        # Seleccionar en el viewer solo si NO viene del viewer (evitar bucle)
        if not from_viewer:
            pos_type = current_positions[num_id].get("type", "number")
            if pos_type == "barcode":
                self.interactive_viewer._select_barcode(num_id)
            elif pos_type == "variable_text":
                self.interactive_viewer._select_variable_text(num_id)
            else:
                self.interactive_viewer._select_numeradora(num_id)

        # Mostrar/ocultar secciones según tipo y cargar datos (tanto desde viewer como desde lista)
        if num_id in current_positions:
            pos_type = current_positions[num_id].get("type", "number")
            self._toggle_sections_by_type(pos_type)
            try:
                self._load_position_data_to_ui(num_id)
            except AssertionError:
                pass
            if pos_type == "barcode":
                try:
                    self._update_barcode_dimensions_visibility()
                except AssertionError:
                    pass
            print(f"Posición seleccionada: {current_positions[num_id]['name']}")

    def _on_viewer_select(self, num_id):
        """
        Callback llamado cuando se selecciona o deselecciona una posición desde el viewer
        Actualiza la selección en la lista sin volver a llamar al viewer

        Args:
            num_id: ID de la posición seleccionada, o None si se deseleccionó
        """
        if num_id is None:
            # Deseleccionar: quitar resaltado de todos los items
            current_positions = self._get_current_positions()
            for pos_id, pos_data in current_positions.items():
                try:
                    pos_data["item"].bgcolor = (
                        FONDO_TEXTFIELDS_COLOR  # No seleccionado: claro
                    )
                    pos_data["item"].update()
                except (AssertionError, RuntimeError):
                    pass

            # Limpiar selección
            self.selected_position = None

            # Deshabilitar campos de posición
            self._update_position_fields_state()

            # Ocultar grupos internos (la caja se queda visible)
            self._toggle_sections_by_type(None)

            print("[MAIN_SCREEN] Todas las numeradoras deseleccionadas")
        else:
            # Seleccionar normalmente
            self._on_select_position(num_id, from_viewer=True)

    def _update_position_param(self, param_name, value):
        """
        Actualiza un parámetro de la posición seleccionada

        Args:
            param_name: Nombre del parámetro ("x", "y", "alignment", etc.)
            value: Nuevo valor del parámetro
        """
        print(
            f"[UPDATE_PARAM] param_name={param_name}, value={value}, selected_position={self.selected_position}"
        )
        if self.selected_position is None:
            print(f"[UPDATE_PARAM] No hay posición seleccionada")
            return

        current_positions = self._get_current_positions()
        if self.selected_position in current_positions:
            current_positions[self.selected_position][param_name] = value
            print(
                f"[UPDATE_PARAM] Posición {self.selected_position} - {param_name} = {value}"
            )
            print(
                f"[UPDATE_PARAM] Diccionario completo: {current_positions[self.selected_position]}"
            )
        else:
            print(
                f"[UPDATE_PARAM] Posición {self.selected_position} no encontrada en positions de {self.current_face}"
            )

    def _propagate_to_same_profile(self, profile_name, updates):
        ids = self.interactive_viewer.get_barcode_ids_by_profile(profile_name)
        if not ids:
            return ids
        current_positions = self._get_current_positions()
        for pid in ids:
            bd = self.interactive_viewer.get_barcode_data(pid)
            if bd is not None:
                bd.update(updates)
                self.interactive_viewer.invalidate_barcode_render_cache(pid)
            if pid in current_positions:
                current_positions[pid].update(updates)
        return ids

    def _save_current_ui_to_position(self, num_id):
        """
        Guarda los valores actuales de la UI en una posición específica
        NOTA: Solo guarda valores INDIVIDUALES (add, prefix, suffix, mask, etc.)
        Los valores globales (start, end, increment, copies, reverse) están en global_settings

        Args:
            num_id: ID de la posición donde guardar los valores
        """
        current_positions = self._get_current_positions()
        if num_id not in current_positions:
            return

        print(
            f"[SAVE_UI_TO_POS] Guardando valores individuales de UI en posición {num_id}"
        )

        # Ya no guardamos start, end, increment, copies, reverse porque son globales en global_settings
        # Solo preservamos valores que ya existan en la posición (coordinadas, alignment, etc.)
        # que fueron establecidos en la creación de la posición

        print(
            f"[SAVE_UI_TO_POS] Valores individuales preservados (coordenadas, alignment, etc.)"
        )

    def _load_position_data_to_ui(self, num_id):
        """
        Carga los datos de una posición en los controles de la UI

        Args:
            num_id: ID de la posición a cargar
        """
        current_positions = self._get_current_positions()
        if num_id not in current_positions:
            return

        pos_data = current_positions[num_id]

        # Obtener coordenadas (las coordenadas están siempre en mm)
        x_mm = pos_data.get("x", 0)
        y_mm = pos_data.get("y", 0)

        # Convertir de mm a la unidad seleccionada (global) para mostrar en la UI
        vertical_converted = convert_from_mm(y_mm, self.current_unit)
        horizontal_converted = convert_from_mm(x_mm, self.current_unit)

        # Formatear según la unidad
        if self.current_unit == UNIT_PX:
            vertical_str = f"{vertical_converted:.1f}"
            horizontal_str = f"{horizontal_converted:.1f}"
        else:
            vertical_str = f"{vertical_converted:.4f}"
            horizontal_str = f"{horizontal_converted:.4f}"

        # Cargar medidas (la unidad global ahora se gestiona desde Preferencias)
        self.vertical_field.value = vertical_str
        self.horizontal_field.value = horizontal_str
        self.add_field.value = pos_data.get("add", "0")
        self.rotation_dropdown.content.controls[0].value = pos_data.get(
            "rotation", ROTATIONS[0]
        )
        self.text_style_dropdown.content.controls[0].value = pos_data.get(
            "text_style", "<Default>"
        )

        # Cargar datos específicos según tipo
        pos_type = pos_data.get("type", "number")

        # Actualizar dropdown de tipo de posición
        if pos_type == "number":
            type_display = t("Número")
        elif pos_type == "barcode":
            type_display = t("Código de barras")
        else:
            type_display = t("Texto Variable")
        self.position_type_dropdown.content.controls[0].value = type_display
        self.position_type_dropdown.content.controls[0].data = pos_type

        # Dropdown compartido: Alineamiento (9 anclas para texto variable,
        # 3 opciones para número/barcode). Misma etiqueta para todos.
        self._alignment_row_label.value = t("Alineamiento:")
        if pos_type == "variable_text":
            anchor = pos_data.get("anchor", pos_data.get("alignment", DEFAULT_ANCHOR))
            self._set_alignment_dropdown_options(get_anchor_options(), anchor)
        else:
            align_val = pos_data.get("alignment", ALIGNMENT_LEFT)
            self._set_alignment_dropdown_options(get_alignments(), align_val)
        self._alignment_row_label.update()

        if pos_type == "barcode":
            profile_name = pos_data.get("profile_name", "<Default>")
            self._barcode_profile_dropdown.content.controls[0].value = profile_name
            self._barcode_profile_dropdown.content.controls[0].data = profile_name
            self._barcode_profile_dropdown.update()
            p = self._get_active_barcode_profile()
            self._active_barcode_profile = p
            if p:
                self._on_barcode_profile_change(profile_name, _mark=False, _redraw=False)
            else:
                bw_mm = pos_data.get("bar_width", 80.0)
                bh_mm = pos_data.get("bar_height", 30.0)
                pw_mm = pos_data.get("pdf417_size", 80.0)
                ph_mm = pos_data.get("pdf417_height", 30.0)
                gap_mm = float(pos_data.get("itf14_hri_gap_mm", 2.0))
                code39_gap_mm = float(pos_data.get("code39_hri_gap_mm", 2.0))
                if pos_data.get("symbology") == "itf14":
                    printer = pos_data.get("itf14_printer_type", "flexografia")
                    min_h = 32.00 if printer == "flexografia" else 12.70
                    bh_mm = max(min_h, bh_mm)
                self.bar_width_field.value = self._fmt_mm(bw_mm, self.current_unit)
                self.bar_height_field.value = self._fmt_mm(bh_mm, self.current_unit)
                self.qr_size_field.value = self._fmt_mm(bw_mm, self.current_unit)
                self._pdf417_width_field.value = self._fmt_mm(pw_mm, self.current_unit)
                self._pdf417_height_field.value = self._fmt_mm(ph_mm, self.current_unit)
                self._itf14_body_field.value = str(
                    pos_data.get("barcode_font_size", 13.0)
                )
                self._itf14_gap_field.value = self._fmt_mm(gap_mm, self.current_unit)
                self._datamatrix_body_field.value = str(
                    pos_data.get("barcode_font_size", 9.0)
                )
                dm_gap_mm = float(pos_data.get("datamatrix_hri_gap_mm", 2.0))
                self._datamatrix_gap_field.value = self._fmt_mm(
                    dm_gap_mm, self.current_unit
                )
                # Interlineado fallback (sin perfil)
                sym = pos_data.get("symbology", "")
                if sym == "qr":
                    ls = float(pos_data.get("qr_hri_line_spacing", 1.0))
                elif sym == "pdf417":
                    ls = float(pos_data.get("pdf417_hri_line_spacing", 1.0))
                elif _is_datamatrix_family(sym):
                    ls = float(pos_data.get("datamatrix_hri_line_spacing", 1.0))
                else:
                    ls = 1.0
                self._datamatrix_hri_line_spacing_field.value = f"{ls:.1f}"
                self._update_datamatrix_height_options()
            self._update_barcode_dimensions_visibility()
        elif pos_type == "variable_text":
            profile_name = pos_data.get("profile_name", "<Default>")
            self._variable_text_profile_dropdown.content.controls[0].value = (
                profile_name
            )
            self._variable_text_profile_dropdown.content.controls[0].data = profile_name
            self._vt_font_size_field.value = _fmt_pt(pos_data.get("font_size", 12.0))
            self._vt_line_spacing_field.value = _fmt_pt(
                pos_data.get("line_spacing", 14.4)
            )
            self._vt_letter_spacing_field.value = _fmt_pt(
                pos_data.get("letter_spacing", 0.0)
            )
            self._set_dropdown_value(
                self._vt_text_alignment_dropdown,
                get_alignments(),
                pos_data.get("text_alignment", ALIGNMENT_LEFT),
            )
            self._vt_line_spacing_auto = True
        else:
            # Cargar numeración desde global_settings (valores compartidos por ambas caras)
            self.start_field.value = str(
                self.global_settings.get("start", DEFAULT_START_NUMBER)
            )
            self.end_field.value = str(
                self.global_settings.get("end", DEFAULT_END_NUMBER)
            )
            self.increment_field.value = str(
                self.global_settings.get("increment", DEFAULT_INCREMENT)
            )
            self.copies_field.value = str(
                self.global_settings.get("copies", DEFAULT_COPIES)
            )

            # Cargar reverse desde global_settings (pertenece a la app, no a la cara)
            self.reverse_checkbox.value = self.global_settings.get("reverse", False)

            # Cargar tamaño de letra desde el perfil TextStyle activo
            profile_name = self.text_style_dropdown.content.controls[0].value
            fs = 12
            if profile_name and hasattr(self, "text_style_manager"):
                for p in self.text_style_manager.profiles:
                    if p.name == profile_name:
                        fs = p.font_size
                        break
            self._num_font_size_field.value = _fmt_pt(fs)

            # Cargar interletraje desde el perfil TextStyle activo
            ls = 0.0
            if profile_name and hasattr(self, "text_style_manager"):
                for p in self.text_style_manager.profiles:
                    if p.name == profile_name:
                        ls = getattr(p, "letter_spacing", 0.0) or 0.0
                        break
            self._num_letter_spacing_field.value = _fmt_pt(ls)

        # Actualizar controles
        self.vertical_field.update()
        self.horizontal_field.update()
        self.add_field.update()
        self.rotation_dropdown.update()
        self.alignment_dropdown.update()
        self.text_style_dropdown.update()
        self.position_type_dropdown.update()
        if pos_type == "barcode":
            self.bar_width_field.update()
            self.bar_height_field.update()
            self.qr_size_field.update()
            self._pdf417_height_field.update()
            self._barcode_profile_dropdown.update()
        elif pos_type == "variable_text":
            self._vt_font_size_field.update()
            self._vt_line_spacing_field.update()
            self._vt_letter_spacing_field.update()
            self._vt_text_alignment_dropdown.update()
            self._variable_text_profile_dropdown.update()
        else:
            self._num_font_size_field.update()
            self._num_letter_spacing_field.update()
            self.start_field.update()
            self.end_field.update()
            self.increment_field.update()
            self.copies_field.update()
            self.reverse_checkbox.update()

        # Calcular el total de páginas basado en los valores cargados
        self._calculate_total_pages()

    def _on_position_moved(self, num_id, new_x, new_y):
        """
        Callback llamado cuando una posición se mueve por drag
        Actualiza las coordenadas en el diccionario y los textfields de la UI

        Args:
            num_id: ID de la posición movida
            new_x: Nueva coordenada X en mm
            new_y: Nueva coordenada Y en mm
        """
        current_positions = self._get_current_positions()
        if num_id in current_positions:
            # Guardar coordenadas en mm (formato interno)
            current_positions[num_id]["x"] = new_x
            current_positions[num_id]["y"] = new_y

            # Si esta posición está seleccionada, actualizar los textfields de la UI
            if self.selected_position == num_id:
                # Convertir de mm a la unidad seleccionada (global)
                vertical_converted = convert_from_mm(new_y, self.current_unit)
                horizontal_converted = convert_from_mm(new_x, self.current_unit)

                # Formatear según la unidad
                if self.current_unit == UNIT_PX:
                    vertical_value = f"{vertical_converted:.1f}"
                    horizontal_value = f"{horizontal_converted:.1f}"
                else:
                    vertical_value = f"{vertical_converted:.4f}"
                    horizontal_value = f"{horizontal_converted:.4f}"

                # Actualizar textfields
                self.vertical_field.value = vertical_value
                self.horizontal_field.value = horizontal_value
                self.vertical_field.update()
                self.horizontal_field.update()

                # Actualizar en el diccionario (solo valores de UI)
                current_positions[num_id]["vertical"] = vertical_value
                current_positions[num_id]["horizontal"] = horizontal_value

            # Marcar proyecto como modificado
            self._mark_modified()

            # Mensaje de posición (silenciado por defecto porque es repetitivo)
            if _PRINT_STATE:
                print(f"Posición {num_id} movida a ({new_x:.1f}, {new_y:.1f}) mm")

    def _on_alignment_change(self, alignment_value):
        """
        Maneja el cambio de alineación
        Actualiza el diccionario y el viewer

        Args:
            alignment_value: String con el valor de alineación ("izquierda", "centro", "derecha")
        """
        # Actualizar diccionario
        self._update_position_param("alignment", alignment_value)

        # Actualizar vista si hay posición seleccionada
        if self.selected_position is not None:
            current_positions = self._get_current_positions()
            pos_type = current_positions.get(self.selected_position, {}).get(
                "type", "number"
            )
            if pos_type == "barcode":
                self.interactive_viewer.update_barcode_post_data_visual(
                    self.selected_position, alignment=alignment_value
                )
            elif pos_type == "variable_text":
                anchor = self._normalize_anchor_value(alignment_value)
                current_positions[self.selected_position]["anchor"] = anchor
                self.interactive_viewer.set_variable_text_alignment(
                    self.selected_position, anchor
                )
            else:
                self.interactive_viewer.set_alignment(
                    self.selected_position, alignment_value
                )
            print(f"Posición {self.selected_position}: alignment = {alignment_value}")

            # Marcar proyecto como modificado solo si había posición seleccionada
            self._mark_modified()

    def _normalize_anchor_value(self, value):
        """Normaliza un valor del dropdown Posición a un anchor (9) válido."""
        for opt in get_anchor_options():
            if value in (opt[0], opt[1]):
                return opt[0]
        return value

    def _resolve_profile_vt_text(self, profile) -> str:
        """Resuelve el texto final del perfil VT (marcadores `<@<col>@>`)."""
        row_index = 0
        if hasattr(self, "excel_manager") and self.excel_manager:
            phys_page = self.current_page
            phys_start = self.global_settings.get("start", 1)
            phys_end = self.global_settings.get("end", 125)
            phys_inc = self.global_settings.get("increment", 1)
            phys_copies = self.global_settings.get("copies", 1)
            reverse = self.global_settings.get("reverse", False)
            row_index = excel_row_index(
                phys_start, phys_end, phys_inc, phys_copies, reverse, phys_page
            )
        try:
            return resolve_vt_text(
                profile.sample_text,
                value_source=getattr(profile, "value_source", "sample"),
                excel_column=getattr(profile, "excel_column", ""),
                excel_manager=getattr(self, "excel_manager", None),
                row_index=row_index,
                text_case_filter=getattr(profile, "text_case_filter", ""),
            )
        except Exception:
            return profile.sample_text

    def _get_active_barcode_profile(self):
        """Returns the currently selected BarcodeProfile object, or None."""
        try:
            profile_name = self._barcode_profile_dropdown.content.controls[0].data
            if profile_name and hasattr(self, "barcode_ui_manager"):
                for p in self.barcode_ui_manager.profile_manager.profiles:
                    if p.name == profile_name:
                        return p
        except (AttributeError, IndexError, ValueError):
            pass
        return None

    def _generic_body_max_pt(self):
        """Cuerpo HRI máximo (pt) que cabe para el perfil seleccionado (espejo del diálogo)."""
        p = self._get_active_barcode_profile()
        if p is None or p.symbology not in ("ean13", "ean8", "upca", "upce", "isbn13"):
            return None
        try:
            from utils.barcode_module import (
                SYMBOLOGY_CONFIG,
                ean_hri_max_ds_mm,
                get_ean13_module_count,
                get_ean8_module_count,
                get_upca_module_count,
                get_upce_module_count,
            )
        except ImportError:
            return None
        cfg = SYMBOLOGY_CONFIG.get(p.symbology, {})
        default_w = next(
            (f["default"] for f in cfg.get("fields", []) if f["key"] == "bar_width"),
            29.83,
        )
        bw = p.bar_width or default_w
        font = p.barcode_font_family or "OCR-B"
        if p.symbology in ("ean13", "isbn13"):
            n_mod = get_ean13_module_count()
        elif p.symbology == "ean8":
            n_mod = get_ean8_module_count()
        elif p.symbology == "upca":
            n_mod = get_upca_module_count()
        else:
            n_mod = get_upce_module_count()
        module_mm = bw / n_mod
        max_mm = ean_hri_max_ds_mm(p.symbology, module_mm, font)
        return max_mm / 0.3528

    def _resolve_profile_values(self, p):
        """Valores actuales del perfil (columna, sample o numeración)."""
        if p.value_source == "excel" and p.excel_column:
            if (
                hasattr(self, "excel_manager")
                and self.excel_manager
                and self.excel_manager.is_loaded
            ):
                return self.excel_manager.get_column_values(p.excel_column)
            return []
        if p.value_source == "numbering":
            if self.selected_position is not None:
                try:
                    n = self._calculate_number_for_numeradora(self.selected_position)
                    if n is not None:
                        return [_apply_mask(n, p.mask)]
                except Exception:
                    return []
            return []
        return [p.sample_value] if p.sample_value else []

    def _recalc_profile_minimums(self, p):
        """Rellena los mínimos cacheados del perfil si están vacíos (perfiles antiguos).

        NO toca ancho/alto actuales: los mínimos solo se reescriben al recalcular
        cuando cambia la fuente de datos.
        """
        if not p:
            return
        s = p.symbology
        if _is_datamatrix_family(s) and not (
            p.datamatrix_min_width and p.datamatrix_longest_value
        ):
            from utils.barcode_module import get_datamatrix_min_size

            values = self._resolve_profile_values(p)
            if values:
                p.datamatrix_min_width, p.datamatrix_min_height = (
                    get_datamatrix_min_size(values)
                )
                p.datamatrix_longest_value = max(
                    (v for v in values if v), key=len, default=""
                )
        elif s == "qr" and not p.qr_min_size:
            from utils.barcode_module import calcular_minimo_qr

            values = self._resolve_profile_values(p)
            if values:
                p.qr_min_size = calcular_minimo_qr(values)
        elif s == "code128" and not p.code128_min_width:
            from utils.barcode_module import calcular_ancho_fijo_code128

            values = self._resolve_profile_values(p)
            if values:
                p.code128_min_width = min(
                    165.10, calcular_ancho_fijo_code128(values)
                )
        elif s == "code39" and not p.code39_min_width:
            from utils.barcode_module import get_code39_min_width

            values = self._resolve_profile_values(p)
            if values:
                p.code39_min_width = get_code39_min_width(values)


    def _update_barcode_profile_size(self):
        """Propaga bar_width/bar_height actuales al perfil de barcode seleccionado.
        Los valores vienen de UI en current_unit; se convierten a mm para almacenar."""
        try:
            profile_name = self._barcode_profile_dropdown.content.controls[0].data
            if profile_name and hasattr(self, "barcode_ui_manager"):
                for p in self.barcode_ui_manager.profile_manager.profiles:
                    if p.name == profile_name:
                        if (
                            self.selected_position is not None
                            and self.interactive_viewer.get_barcode_data(
                                self.selected_position
                            )
                            and self.interactive_viewer.get_barcode_data(
                                self.selected_position
                            ).get("symbology")
                            == "pdf417"
                        ):
                            print(
                                f"[PROFILE SAVE] pdf417: width_field={self._pdf417_width_field.value!r} height_field={self._pdf417_height_field.value!r}"
                            )
                            p.bar_width = convert_to_mm(
                                float(self._pdf417_width_field.value), self.current_unit
                            )
                            p.pdf417_size = p.bar_width
                            p.bar_height = convert_to_mm(
                                float(self._pdf417_height_field.value),
                                self.current_unit,
                            )
                            p.pdf417_height = p.bar_height
                            print(
                                f"[PROFILE SAVE] saved: pdf417_size={p.pdf417_size} pdf417_height={p.pdf417_height}"
                            )
                        else:
                            if _is_datamatrix_family(p.symbology):
                                p.datamatrix_width = convert_to_mm(
                                    float(self.bar_width_field.value), self.current_unit
                                )
                            else:
                                p.bar_width = convert_to_mm(
                                    float(self.bar_width_field.value), self.current_unit
                                )
                                p.bar_height = convert_to_mm(
                                    float(self.bar_height_field.value),
                                    self.current_unit,
                                )
                        try:
                            if p.symbology == "code39":
                                p.barcode_font_size = float(
                                    self._code39_body_field.value
                                )
                            elif p.symbology == "code128":
                                p.barcode_font_size = float(
                                    self._code128_body_field.value
                                )
                            elif _is_datamatrix_family(p.symbology):
                                p.barcode_font_size = float(
                                    self._datamatrix_body_field.value
                                )
                            elif p.symbology in ("qr", "pdf417"):
                                p.barcode_font_size = float(
                                    self._datamatrix_body_field.value
                                )
                            elif p.symbology == "ean5":
                                p.barcode_font_size = float(self._ean5_body_field.value)
                            elif p.symbology in (
                                "upca",
                                "upce",
                                "ean13",
                                "ean8",
                                "isbn13",
                            ):
                                p.barcode_font_size = float(
                                    self._generic_body_field.value
                                )
                            else:
                                p.barcode_font_size = float(
                                    self._itf14_body_field.value
                                )
                        except (ValueError, TypeError):
                            pass
                        try:
                            p.itf14_hri_gap_mm = convert_to_mm(
                                float(self._itf14_gap_field.value), self.current_unit
                            )
                        except (ValueError, TypeError):
                            pass
                        try:
                            p.code39_hri_gap_mm = convert_to_mm(
                                float(self._code39_gap_field.value), self.current_unit
                            )
                        except (ValueError, TypeError):
                            pass
                        try:
                            p.code128_hri_gap_mm = convert_to_mm(
                                float(self._code128_gap_field.value), self.current_unit
                            )
                        except (ValueError, TypeError):
                            pass

                        try:
                            p.ean5_hri_gap_mm = convert_to_mm(
                                float(self._ean5_gap_field.value), self.current_unit
                            )
                        except (ValueError, TypeError):
                            pass
                        try:
                            gap_val_mm = convert_to_mm(
                                float(self._datamatrix_gap_field.value),
                                self.current_unit,
                            )
                            if p.symbology == "qr":
                                p.qr_hri_gap_mm = gap_val_mm
                            elif p.symbology == "pdf417":
                                p.pdf417_hri_gap_mm = gap_val_mm
                            else:
                                p.datamatrix_hri_gap_mm = gap_val_mm
                        except (ValueError, TypeError):
                            pass
                        break
        except (ValueError, AttributeError):
            pass

    def _on_bar_width_change(self, e, finalize=False):
        """Callback cuando cambia el ancho del código de barras."""
        normalize_decimal_input(e)
        value = e.control.value
        try:
            bar_width_user = float(value)
        except (ValueError, TypeError):
            if not finalize:
                return
            prev = 80.0
            bc_data = (
                self.interactive_viewer.get_barcode_data(self.selected_position)
                if self.selected_position
                else None
            )
            if bc_data and bc_data.get("bar_width"):
                prev = bc_data["bar_width"]
            elif (
                self._active_barcode_profile and self._active_barcode_profile.bar_width
            ):
                prev = self._active_barcode_profile.bar_width
            e.control.value = self._fmt_mm(prev)
            e.control.update()
            return
        bar_width_mm = convert_to_mm(bar_width_user, self.current_unit)

        # Clamp width by symbology only when applying (blur/submit/inc-dec)
        if finalize and self.selected_position is not None:
            _p = self._get_active_barcode_profile()
            self._recalc_profile_minimums(_p)
            bc_data = self.interactive_viewer.get_barcode_data(self.selected_position)
            sym = bc_data.get("symbology", "") if bc_data else ""
            if sym == "pdf417":
                min_w, _ = self._get_pdf417_min_from_profile()
                if min_w > 0 and bar_width_mm < min_w:
                    bar_width_mm = min_w
            elif sym == "upca":
                # UPC-A: mantener mínimo, sin techo para permitir tamaños mayores.
                bar_width_mm = max(29.83, bar_width_mm)
            elif sym == "upce":
                # UPC-E: mantener mínimo, sin techo para permitir tamaños mayores.
                bar_width_mm = max(17.69, bar_width_mm)
            elif sym == "ean13":
                # EAN-13: mantener mínimo, sin techo para permitir tamaños mayores.
                bar_width_mm = max(29.83, bar_width_mm)
            elif sym == "ean8":
                # EAN-8: mantener mínimo, sin techo para evitar reducción inesperada.
                bar_width_mm = max(21.38, bar_width_mm)
            # GS1: Code128 — mínimo dinámico cacheado en el perfil, max 165.10mm
            elif sym == "code128":
                p = self._get_active_barcode_profile()
                min_w = (p.code128_min_width or 40.0) if p else 40.0
                bar_width_mm = max(min_w, min(165.10, bar_width_mm))
            # GS1: EAN-5 complementario 17.92–44.80mm
            elif sym == "ean5":
                bar_width_mm = max(17.92, min(44.80, bar_width_mm))
            # ISBN-13: mantener mínimo, sin techo para permitir tamaños mayores.
            elif sym == "isbn13":
                bar_width_mm = max(29.83, bar_width_mm)
            # GS1: ITF-14 — dynamic limits per printer type
            elif sym == "itf14":
                printer = (
                    bc_data.get("itf14_printer_type", "flexografia")
                    if bc_data
                    else "flexografia"
                )
                if printer == "flexografia":
                    min_w = 89.25
                else:
                    min_w = 71.40
                bar_width_mm = max(min_w, bar_width_mm)
            # GS1: Code39 — ancho mínimo dinámico cacheado en el perfil
            elif sym == "code39":
                p = self._get_active_barcode_profile()
                min_w = (p.code39_min_width or 40.0) if p else 40.0
                bar_width_mm = max(min_w, bar_width_mm)
            # GS1: DataMatrix — mínimo dinámico cacheado en el perfil
            elif _is_datamatrix_family(sym):
                p = self._get_active_barcode_profile()
                min_w = (p.datamatrix_min_width or 20.0) if p else 20.0
                bar_width_mm = max(min_w, bar_width_mm)

        if not finalize:
            return True

        p = self._get_active_barcode_profile()
        prev_w = (
            p.datamatrix_width
            if p and _is_datamatrix_family(p.symbology)
            else (p.bar_width if p else None)
        )
        if prev_w is not None and abs(bar_width_mm - prev_w) < 0.001:
            e.control.value = self._fmt_mm(bar_width_mm)
            e.control.update()
            return False

        if p:
            if _is_datamatrix_family(p.symbology):
                p.datamatrix_width = bar_width_mm
            else:
                p.bar_width = bar_width_mm
            if p.symbology == "qr":
                p.bar_height = bar_width_mm
            if p.symbology == "pdf417":
                p.pdf417_size = bar_width_mm

        if self.selected_position is not None:
            bc_data = self.interactive_viewer.get_barcode_data(self.selected_position)
            if bc_data is not None:
                if _is_datamatrix_family(bc_data.get("symbology")):
                    bc_data["datamatrix_width"] = bar_width_mm
                    self._update_position_param("datamatrix_width", bar_width_mm)
                    self._update_datamatrix_height_options()
                    if p and _is_datamatrix_family(p.symbology):
                        bc_data["datamatrix_height"] = p.datamatrix_height
                        bc_data["datamatrix_format"] = p.datamatrix_format
                        self._update_position_param(
                            "datamatrix_height", p.datamatrix_height
                        )
                else:
                    bc_data["bar_width"] = bar_width_mm
                self.interactive_viewer.invalidate_barcode_render_cache(
                    self.selected_position
                )
                self._mark_modified()

        self._update_position_param("bar_width", bar_width_mm)

        e.control.value = self._fmt_mm(bar_width_mm)
        e.control.update()
        return True

    def _on_bar_width_apply(self, e):
        if self._on_bar_width_change(e, finalize=True) is False:
            return
        if self.selected_position is not None:
            bc_data = self.interactive_viewer.get_barcode_data(self.selected_position)
            if bc_data is not None:
                self.interactive_viewer.invalidate_barcode_render_cache(
                    self.selected_position
                )
                _profile_ids = None
                _profile_name = bc_data.get("profile_name")
                if _profile_name:
                    _sym = bc_data.get("symbology", "")
                    if _is_datamatrix_family(_sym):
                        _profile_ids = self._propagate_to_same_profile(_profile_name, {"datamatrix_width": bc_data.get("datamatrix_width")})
                    else:
                        _profile_ids = self._propagate_to_same_profile(_profile_name, {"bar_width": bc_data.get("bar_width")})
                try:
                    self.interactive_viewer._redraw_all(force=True, only_barcode_ids=_profile_ids)
                except AssertionError:
                    pass

    def _on_bar_height_change(self, e, finalize=False):
        """Callback cuando cambia el alto del código de barras."""
        normalize_decimal_input(e)
        value = e.control.value
        try:
            bar_height_user = float(value)
        except (ValueError, TypeError):
            if not finalize:
                return
            prev = 30.0
            bc_data = (
                self.interactive_viewer.get_barcode_data(self.selected_position)
                if self.selected_position
                else None
            )
            if bc_data and bc_data.get("bar_height"):
                prev = bc_data["bar_height"]
            elif (
                self._active_barcode_profile and self._active_barcode_profile.bar_height
            ):
                prev = self._active_barcode_profile.bar_height
            e.control.value = self._fmt_mm(prev)
            e.control.update()
            return
        bar_height_mm = convert_to_mm(bar_height_user, self.current_unit)

        # Clamp height by symbology only when applying (blur/submit/inc-dec)
        if finalize and self.selected_position is not None:
            bc_data = self.interactive_viewer.get_barcode_data(self.selected_position)
            sym = bc_data.get("symbology", "") if bc_data else ""
            if sym in ("upca", "upce"):
                # UPC-A/UPC-E: mantener mínimo, sin techo para permitir tamaños mayores.
                bar_height_mm = max(20.73, bar_height_mm)
            elif sym == "ean13":
                # EAN-13: mantener mínimo, sin techo para permitir tamaños mayores.
                bar_height_mm = max(20.73, bar_height_mm)
            elif sym == "ean8":
                # EAN-8: mantener mínimo, sin techo para permitir tamaños mayores.
                bar_height_mm = max(17.05, bar_height_mm)
            # GS1: Code128 alto 12–32mm
            elif sym == "code128":
                bar_height_mm = max(12.0, min(32.0, bar_height_mm))
            # GS1: EAN-5 20.73–51.82mm
            elif sym == "ean5":
                bar_height_mm = max(20.73, min(51.82, bar_height_mm))
            # ISBN-13: mantener mínimo, sin techo para permitir tamaños mayores.
            elif sym == "isbn13":
                bar_height_mm = max(20.73, bar_height_mm)
            # GS1: ITF-14 — dynamic min height per printer type
            elif sym == "itf14":
                printer = (
                    bc_data.get("itf14_printer_type", "flexografia")
                    if bc_data
                    else "flexografia"
                )
                min_h = 32.00 if printer == "flexografia" else 12.70
                bar_height_mm = max(min_h, bar_height_mm)
            # GS1: Code39 alto mínimo 15mm
            elif sym == "code39":
                from utils.barcode_module import CODE39_MIN_HEIGHT_MM

                bar_height_mm = max(CODE39_MIN_HEIGHT_MM, bar_height_mm)

        p = self._get_active_barcode_profile()
        if p:
            if _is_datamatrix_family(p.symbology):
                p.datamatrix_height = bar_height_mm
            else:
                p.bar_height = bar_height_mm

        if self.selected_position is not None:
            bc_data = self.interactive_viewer.get_barcode_data(self.selected_position)
            if bc_data is not None:
                if _is_datamatrix_family(bc_data.get("symbology")):
                    bc_data["datamatrix_height"] = bar_height_mm
                else:
                    bc_data["bar_height"] = bar_height_mm
                self._mark_modified()

        self._update_position_param("bar_height", bar_height_mm)

        if finalize:
            e.control.value = self._fmt_mm(bar_height_mm)
            e.control.update()

    def _on_bar_height_apply(self, e):
        self._on_bar_height_change(e, finalize=True)
        if self.selected_position is not None:
            bc_data = self.interactive_viewer.get_barcode_data(self.selected_position)
            if bc_data is not None:
                _profile_ids = None
                _profile_name = bc_data.get("profile_name")
                if _profile_name:
                    _sym = bc_data.get("symbology", "")
                    if _is_datamatrix_family(_sym):
                        _profile_ids = self._propagate_to_same_profile(_profile_name, {"datamatrix_height": bc_data.get("datamatrix_height")})
                    else:
                        _profile_ids = self._propagate_to_same_profile(_profile_name, {"bar_height": bc_data.get("bar_height")})
                try:
                    self.interactive_viewer._redraw_all(force=True, only_barcode_ids=_profile_ids)
                except AssertionError:
                    pass

    def _on_body_gap_blur(self, e):
        if self.selected_position is not None:
            bc_data = self.interactive_viewer.get_barcode_data(self.selected_position)
            if bc_data is not None:
                _profile_ids = None
                _profile_name = bc_data.get("profile_name")
                if _profile_name:
                    _updates = {}
                    for _f in ("barcode_font_size", "itf14_hri_gap_mm", "itf14_hri_position",
                               "code39_hri_gap_mm",
                               "code128_hri_gap_mm", "ean5_hri_gap_mm", "datamatrix_hri_gap_mm",
                               "datamatrix_hri_position", "datamatrix_hri_align",
                               "datamatrix_hri_line_spacing",
                               "code39_hri_position",
                               "code128_hri_position", "ean5_hri_position", "isbn13_show_title",
                               "qr_hri_gap_mm", "qr_hri_position", "qr_hri_align",
                               "qr_hri_line_spacing",
                               "pdf417_hri_gap_mm", "pdf417_hri_position", "pdf417_hri_align",
                               "pdf417_hri_line_spacing"):
                        if _f in bc_data:
                            _updates[_f] = bc_data[_f]
                    _profile_ids = self._propagate_to_same_profile(_profile_name, _updates)
                try:
                    self.interactive_viewer._redraw_all(force=True, only_barcode_ids=_profile_ids)
                except AssertionError:
                    pass

    def _on_bar_width_inc(self, e):
        """Incrementa ancho del código de barras."""
        try:
            val = max(1.0, float(self.bar_width_field.value) + 1)
        except (ValueError, TypeError):
            val = 80.0
        self.bar_width_field.value = f"{self._fmt_mm(val)}"
        self.bar_width_field.update()

        class _FakeEvent:
            def __init__(self, control):
                self.control = control

        self._on_bar_width_apply(_FakeEvent(self.bar_width_field))

    def _on_bar_width_dec(self, e):
        """Decrementa ancho del código de barras."""
        try:
            val = max(1.0, float(self.bar_width_field.value) - 1)
        except (ValueError, TypeError):
            val = 80.0
        self.bar_width_field.value = f"{self._fmt_mm(val)}"
        self.bar_width_field.update()

        class _FakeEvent:
            def __init__(self, control):
                self.control = control

        self._on_bar_width_apply(_FakeEvent(self.bar_width_field))

    def _on_bar_height_inc(self, e):
        """Incrementa alto del código de barras."""
        try:
            val = max(1.0, float(self.bar_height_field.value) + 1)
        except (ValueError, TypeError):
            val = 30.0
        self.bar_height_field.value = f"{val:.1f}"
        self.bar_height_field.update()

        class _FakeEvent:
            def __init__(self, control):
                self.control = control

        self._on_bar_height_apply(_FakeEvent(self.bar_height_field))

    def _on_bar_height_dec(self, e):
        """Decrementa alto del código de barras."""
        try:
            val = max(1.0, float(self.bar_height_field.value) - 1)
        except (ValueError, TypeError):
            val = 30.0
        self.bar_height_field.value = f"{val:.1f}"
        self.bar_height_field.update()

        class _FakeEvent:
            def __init__(self, control):
                self.control = control

        self._on_bar_height_apply(_FakeEvent(self.bar_height_field))

    def _get_qr_values_main(self) -> list:
        """Obtiene valores para calcular mínimo QR desde main_screen."""
        p = self._get_active_barcode_profile()
        if not p:
            return []
        if p.value_source == "excel" and p.excel_column:
            if self.excel_manager and self.excel_manager.is_loaded:
                return self.excel_manager.get_column_values(p.excel_column)
            return []
        elif p.value_source == "numbering":
            from utils.barcode_module import get_pdf417_max_chars

            return ["X" * get_pdf417_max_chars()]
        return [p.sample_value] if p.sample_value else []

    def _on_qr_size_change(self, e):
        normalize_decimal_input(e)
        value = e.control.value
        try:
            size_user = float(value)
        except (ValueError, TypeError):
            return
        size_mm = convert_to_mm(size_user, self.current_unit)
        # Sin clamp ni write-back mientras se escribe (patrón
        # _on_bar_width_change finalize=False): el mínimo solo se aplica
        # en blur/submit (_on_qr_size_blur). Si no, teclear "3" saltaba a 10.
        p = self._get_active_barcode_profile()
        if p:
            p.bar_width = size_mm
            p.bar_height = size_mm

        if self.selected_position is not None:
            bc_data = self.interactive_viewer.get_barcode_data(self.selected_position)
            if bc_data is not None:
                bc_data["bar_width"] = size_mm
                bc_data["bar_height"] = size_mm
                _profile_ids = None
                _profile_name = bc_data.get("profile_name")
                if _profile_name:
                    _profile_ids = self._propagate_to_same_profile(_profile_name, {"bar_width": size_mm, "bar_height": size_mm})
                if _profile_ids:
                    self.interactive_viewer._redraw_all(force=True, only_barcode_ids=_profile_ids)
                self._mark_modified()

        self._update_position_param("bar_width", size_mm)
        self._update_position_param("bar_height", size_mm)

    def _on_qr_size_blur(self, e):
        normalize_decimal_input(e)

        value = e.control.value
        try:
            size_user = float(value)
        except (ValueError, TypeError):
            # Vacío/inválido al salir → restaurar último tamaño bueno
            prev = None
            if self.selected_position is not None:
                bc_data = self.interactive_viewer.get_barcode_data(self.selected_position)
                if bc_data and bc_data.get("bar_width"):
                    prev = bc_data["bar_width"]
            if prev is None:
                p = self._get_active_barcode_profile()
                prev = p.bar_width if p else None
            if prev is None:
                prev = 10.0
            e.control.value = self._fmt_mm(prev)
            e.control.update()
            return
        size_mm = convert_to_mm(size_user, self.current_unit)
        # GS1: QR — mínimo dinámico según datos
        from utils.barcode_module import calcular_minimo_qr

        values = self._get_qr_values_main()
        min_w = calcular_minimo_qr(values) if values else 20.0
        size_mm = max(min_w, size_mm)

        e.control.value = self._fmt_mm(size_mm)
        e.control.update()
        p = self._get_active_barcode_profile()
        if p:
            p.bar_width = size_mm
            p.bar_height = size_mm

        if self.selected_position is not None:
            bc_data = self.interactive_viewer.get_barcode_data(self.selected_position)
            if bc_data is not None:
                bc_data["bar_width"] = size_mm
                bc_data["bar_height"] = size_mm
                _profile_ids = None
                _profile_name = bc_data.get("profile_name")
                if _profile_name:
                    _profile_ids = self._propagate_to_same_profile(_profile_name, {"bar_width": size_mm, "bar_height": size_mm})
                if _profile_ids:
                    self.interactive_viewer._redraw_all(force=True, only_barcode_ids=_profile_ids)
                self._mark_modified()

        self._update_position_param("bar_width", size_mm)
        self._update_position_param("bar_height", size_mm)

    def _on_qr_size_inc(self, e):
        try:
            # GS1: QR mínimo 20mm
            val = max(20.0, float(self.qr_size_field.value) + 1)
        except (ValueError, TypeError):
            val = 30.0
        self.qr_size_field.value = f"{val:.1f}"
        self.qr_size_field.update()

        class _FakeEvent:
            def __init__(self, control):
                self.control = control

        fe = _FakeEvent(self.qr_size_field)
        self._on_qr_size_blur(fe)

    def _on_qr_size_dec(self, e):
        try:
            # GS1: QR mínimo 20mm
            val = max(20.0, float(self.qr_size_field.value) - 1)
        except (ValueError, TypeError):
            val = 30.0
        self.qr_size_field.value = f"{val:.1f}"
        self.qr_size_field.update()

        class _FakeEvent:
            def __init__(self, control):
                self.control = control

        fe = _FakeEvent(self.qr_size_field)
        self._on_qr_size_blur(fe)

    def _on_pdf417_width_inc(self, e):
        try:
            val = max(1.0, float(self._pdf417_width_field.value) + 1)
        except (ValueError, TypeError):
            val = 30.0
        self._pdf417_width_field.value = f"{val:.1f}"
        self._pdf417_width_field.update()
        self._on_pdf417_field_enter(self._pdf417_width_field)

    def _on_pdf417_width_dec(self, e):
        try:
            val = max(1.0, float(self._pdf417_width_field.value) - 1)
        except (ValueError, TypeError):
            val = 30.0
        self._pdf417_width_field.value = f"{val:.1f}"
        self._pdf417_width_field.update()
        self._on_pdf417_field_enter(self._pdf417_width_field)

    # ── PDF417 dimension handlers ──

    def _get_pdf417_min_dimensions_current(self) -> Tuple[float, float]:
        """Return (min_width_mm, min_height_mm) for the selected PDF417 position."""
        from utils.barcode_module import get_pdf417_min_dimensions

        if self.selected_position is None:
            return 65.0, 30.0
        bc_data = self.interactive_viewer.get_barcode_data(self.selected_position)
        if not bc_data:
            return 65.0, 30.0
        vs = bc_data.get("value_source", "fixed")
        if vs == "excel":
            col = bc_data.get("excel_column", "")
            if col and self.excel_manager and self.excel_manager.is_loaded:
                vals = self.excel_manager.get_column_values(col)
                if vals:
                    return get_pdf417_min_dimensions(vals)
        elif vs == "numbering":
            value = bc_data.get("value")
            if not value:
                number = self._calculate_number_for_numeradora(self.selected_position)
                value = _apply_mask(number, bc_data.get("mask", ""))
            if value:
                return get_pdf417_min_dimensions([value])
        value = bc_data.get("value", "Texto de ejemplo PDF417")
        return get_pdf417_min_dimensions([value])

    def _get_pdf417_min_from_profile(self) -> Tuple[float, float]:
        """Read pdf417_min_width/height from the selected barcode profile.
        Falls back to _get_pdf417_min_dimensions_current() if profile not found or values are 0.
        """
        try:
            dd = self._barcode_profile_dropdown.content.controls[0]
            profile_name = dd.data
            if profile_name and hasattr(self, "barcode_ui_manager"):
                for p in self.barcode_ui_manager.profile_manager.profiles:
                    if p.name == profile_name:
                        mw, mh = p.pdf417_min_width, p.pdf417_min_height
                        if mw > 0 and mh > 0:
                            return mw, mh
        except Exception:
            pass
        return self._get_pdf417_min_dimensions_current()

    def _on_pdf417_height_change(self, e):
        """Original on_change handler (PDF417). Clamps and redraws."""
        normalize_decimal_input(e)
        try:
            h_user = float(e.control.value)
        except (ValueError, TypeError):
            return
        h_mm = convert_to_mm(h_user, self.current_unit)
        _, min_h = self._get_pdf417_min_from_profile()
        if h_mm < min_h:
            h_mm = min_h
            self._pdf417_height_field.value = self._fmt_mm(min_h)
            self._pdf417_height_field.update()
        p = self._get_active_barcode_profile()
        if p:
            p.pdf417_height = h_mm
        self._update_position_param("pdf417_height", h_mm)
        if self.selected_position is not None:
            bc_data = self.interactive_viewer.get_barcode_data(self.selected_position)
            if bc_data is not None:
                bc_data["pdf417_height"] = h_mm
                _profile_ids = None
                _profile_name = bc_data.get("profile_name")
                if _profile_name:
                    _profile_ids = self._propagate_to_same_profile(_profile_name, {"pdf417_height": h_mm})
                if _profile_ids:
                    self.interactive_viewer._redraw_all(force=True, only_barcode_ids=_profile_ids)
                self._mark_modified()

    def _on_pdf417_height_blur(self, e):
        """Clamp and redraw on blur/submit."""
        normalize_decimal_input(e)
        try:
            h_user = float(e.control.value)
        except (ValueError, TypeError):
            return
        h_mm = convert_to_mm(h_user, self.current_unit)
        _, min_h = self._get_pdf417_min_from_profile()
        if h_mm < min_h:
            h_mm = min_h
            self._pdf417_height_field.value = self._fmt_mm(min_h)
            self._pdf417_height_field.update()
        p = self._get_active_barcode_profile()
        if p:
            p.pdf417_height = h_mm
        self._update_position_param("pdf417_height", h_mm)
        if self.selected_position is not None:
            bc_data = self.interactive_viewer.get_barcode_data(self.selected_position)
            if bc_data is not None:
                bc_data["pdf417_height"] = h_mm
                _profile_ids = None
                _profile_name = bc_data.get("profile_name")
                if _profile_name:
                    _profile_ids = self._propagate_to_same_profile(_profile_name, {"pdf417_height": h_mm})
                if _profile_ids:
                    self.interactive_viewer._redraw_all(force=True, only_barcode_ids=_profile_ids)
                self._mark_modified()

    # ------------------------------------------------------------------
    # Enter key handler for PDF417 field validation
    # ------------------------------------------------------------------

    def _on_pdf417_page_keyboard(self, e: ft.KeyboardEvent):
        if (
            e.key in ("Enter", "Numpad Enter", "Tab")
            and self._pdf417_focused_field is not None
        ):
            self._on_pdf417_field_enter(self._pdf417_focused_field)
            self._pdf417_focused_field = None

    def _on_pdf417_page_click(self, e: ft.ControlEvent):
        if self._pdf417_focused_field is not None and e.control not in (
            self._pdf417_width_field,
            self._pdf417_height_field,
        ):
            self._on_pdf417_field_enter(self._pdf417_focused_field)
            self._pdf417_focused_field = None

    def _on_pdf417_blur(self, e):
        self._on_pdf417_field_enter(e.control)
        self._pdf417_focused_field = None

    def _on_pdf417_focus_changed(self, tf: ft.TextField):
        prev = self._pdf417_focused_field
        self._pdf417_focused_field = tf
        if prev is not None and prev is not tf:
            self._on_pdf417_field_enter(prev)

    def _on_pdf417_field_enter(self, tf: ft.TextField):
        normalize_decimal_input(_FakeEvent(tf))
        min_w, min_h = self._get_pdf417_min_from_profile()
        val_str = tf.value
        is_width = tf is self._pdf417_width_field
        print(
            f"  [MAIN ENTER] key={'width' if is_width else 'height'} val_str={val_str!r} min_w={min_w} min_h={min_h} unit={self.current_unit}"
        )
        if not val_str:
            min_val_mm = min_w if is_width else min_h
            tf.value = self._fmt_mm(min_val_mm)
            tf.update()
            val_mm = min_val_mm
        else:
            try:
                val_mm = convert_to_mm(float(val_str), self.current_unit)
            except (ValueError, TypeError):
                print(f"  [MAIN ENTER] parse error for {val_str!r}")
                min_val_mm = min_w if is_width else min_h
                tf.value = self._fmt_mm(min_val_mm)
                tf.update()
                val_mm = min_val_mm
            else:
                min_val_mm = min_w if is_width else min_h
                print(
                    f"  [MAIN ENTER] val_mm={val_mm} min_val_mm={min_val_mm} display_mm={convert_from_mm(min_val_mm, self.current_unit)}"
                )
                if val_mm < min_val_mm:
                    val_mm = min_val_mm
                    tf.value = self._fmt_mm(min_val_mm)
                    tf.update()
                    print(f"  [MAIN ENTER] CLAMPED to {tf.value}")
        if is_width:
            p = self._get_active_barcode_profile()
            if p:
                p.bar_width = val_mm
                p.pdf417_size = val_mm
            if self.selected_position is not None:
                bc_data = self.interactive_viewer.get_barcode_data(
                    self.selected_position
                )
                if bc_data is not None:
                    bc_data["bar_width"] = val_mm
                    bc_data["pdf417_size"] = val_mm
                    _profile_ids = None
                    _profile_name = bc_data.get("profile_name")
                    if _profile_name:
                        _profile_ids = self._propagate_to_same_profile(_profile_name, {"bar_width": val_mm, "pdf417_size": val_mm})
                    if _profile_ids:
                        self.interactive_viewer._redraw_all(force=True, only_barcode_ids=_profile_ids)
                    self._mark_modified()
            self._update_position_param("bar_width", val_mm)
            self._update_position_param("pdf417_size", val_mm)
        else:
            p = self._get_active_barcode_profile()
            if p:
                p.pdf417_height = val_mm
            if self.selected_position is not None:
                bc_data = self.interactive_viewer.get_barcode_data(
                    self.selected_position
                )
                if bc_data is not None:
                    bc_data["pdf417_height"] = val_mm
                    _profile_ids = None
                    _profile_name = bc_data.get("profile_name")
                    if _profile_name:
                        _profile_ids = self._propagate_to_same_profile(_profile_name, {"pdf417_height": val_mm})
                    if _profile_ids:
                        self.interactive_viewer._redraw_all(force=True, only_barcode_ids=_profile_ids)
                    self._mark_modified()
            self._update_position_param("pdf417_height", val_mm)

    def _on_pdf417_height_inc(self, e):
        try:
            val = float(self._pdf417_height_field.value) + 1
        except (ValueError, TypeError):
            val = 30.0
        self._pdf417_height_field.value = f"{val:.1f}"
        self._pdf417_height_field.update()

        class _FE:
            def __init__(self, control):
                self.control = control

        fe = _FE(self._pdf417_height_field)
        self._on_pdf417_height_change(fe)
        self._on_pdf417_height_blur(fe)

    def _on_pdf417_height_dec(self, e):
        try:
            val = float(self._pdf417_height_field.value) - 1
        except (ValueError, TypeError):
            val = 30.0
        self._pdf417_height_field.value = f"{val:.1f}"
        self._pdf417_height_field.update()

        class _FE:
            def __init__(self, control):
                self.control = control

        fe = _FE(self._pdf417_height_field)
        self._on_pdf417_height_change(fe)
        self._on_pdf417_height_blur(fe)

    def _on_itf14_body_change(self, e):
        """Callback cuando cambia el cuerpo (font size) de ITF-14."""
        normalize_decimal_input(e)
        try:
            val = float(e.control.value)
        except (ValueError, TypeError):
            return
        self._update_position_param("barcode_font_size", val)
        p = self._get_active_barcode_profile()
        if p:
            p.barcode_font_size = val
        if self.selected_position is not None:
            bc_data = self.interactive_viewer.get_barcode_data(self.selected_position)
            if bc_data is not None:
                bc_data["barcode_font_size"] = val
                self._mark_modified()
                self._update_barcode_profile_size()

    def _on_itf14_gap_change(self, e):
        """Callback cuando cambia la distancia HRI de ITF-14."""
        normalize_decimal_input(e)
        try:
            val_user = float(e.control.value)
        except (ValueError, TypeError):
            return
        val_mm = convert_to_mm(val_user, self.current_unit)
        if val_mm < 0:
            val_mm = 0.0
            e.control.value = self._fmt_mm(0.0)
            try:
                e.control.update()
            except Exception:
                pass
        self._update_position_param("itf14_hri_gap_mm", val_mm)
        p = self._get_active_barcode_profile()
        if p:
            p.itf14_hri_gap_mm = val_mm
        if self.selected_position is not None:
            bc_data = self.interactive_viewer.get_barcode_data(self.selected_position)
            if bc_data is not None:
                bc_data["itf14_hri_gap_mm"] = val_mm
                self._mark_modified()
                self._update_barcode_profile_size()

    def _on_itf14_body_inc(self, e):
        """Incrementa cuerpo (font size) de ITF-14."""
        try:
            val = max(0.0, float(self._itf14_body_field.value) + 0.5)
        except (ValueError, TypeError):
            val = 13.0
        self._itf14_body_field.value = f"{val:.1f}"
        self._itf14_body_field.update()

        class _FakeEvent:
            def __init__(self, control):
                self.control = control

        self._on_itf14_body_change(_FakeEvent(self._itf14_body_field))
        self._on_body_gap_blur(None)

    def _on_itf14_body_dec(self, e):
        """Decrementa cuerpo (font size) de ITF-14."""
        try:
            val = max(0.0, float(self._itf14_body_field.value) - 0.5)
        except (ValueError, TypeError):
            val = 13.0
        self._itf14_body_field.value = f"{val:.1f}"
        self._itf14_body_field.update()

        class _FakeEvent:
            def __init__(self, control):
                self.control = control

        self._on_itf14_body_change(_FakeEvent(self._itf14_body_field))
        self._on_body_gap_blur(None)

    def _on_itf14_gap_inc(self, e):
        """Incrementa distancia HRI de ITF-14."""
        try:
            val = max(0.0, float(self._itf14_gap_field.value) + 0.5)
        except (ValueError, TypeError):
            val = 0.0
        self._itf14_gap_field.value = f"{val:.1f}"
        self._itf14_gap_field.update()

        class _FakeEvent:
            def __init__(self, control):
                self.control = control

        self._on_itf14_gap_change(_FakeEvent(self._itf14_gap_field))
        self._on_body_gap_blur(None)

    def _on_itf14_gap_dec(self, e):
        """Decrementa distancia HRI de ITF-14."""
        try:
            val = max(0.0, float(self._itf14_gap_field.value) - 0.5)
        except (ValueError, TypeError):
            val = 0.0
        self._itf14_gap_field.value = f"{val:.1f}"
        self._itf14_gap_field.update()

        class _FakeEvent:
            def __init__(self, control):
                self.control = control

        self._on_itf14_gap_change(_FakeEvent(self._itf14_gap_field))
        self._on_body_gap_blur(None)

    # ── Code 39 callbacks ──────────────────────────────────────────────────

    def _on_code39_body_change(self, e):
        """Callback cuando cambia el cuerpo (font size) de Code 39."""
        normalize_decimal_input(e)
        try:
            val = float(e.control.value)
        except (ValueError, TypeError):
            return
        self._update_position_param("barcode_font_size", val)
        p = self._get_active_barcode_profile()
        if p:
            p.barcode_font_size = val
        if self.selected_position is not None:
            bc_data = self.interactive_viewer.get_barcode_data(self.selected_position)
            if bc_data is not None:
                bc_data["barcode_font_size"] = val
                self._mark_modified()
                self._update_barcode_profile_size()

    def _on_code39_gap_change(self, e):
        """Callback cuando cambia la distancia HRI de Code 39."""
        normalize_decimal_input(e)
        try:
            val_user = float(e.control.value)
        except (ValueError, TypeError):
            return
        val_mm = convert_to_mm(val_user, self.current_unit)
        if val_mm < 0:
            val_mm = 0.0
            e.control.value = self._fmt_mm(0.0)
            try:
                e.control.update()
            except Exception:
                pass
        self._update_position_param("code39_hri_gap_mm", val_mm)
        p = self._get_active_barcode_profile()
        if p:
            p.code39_hri_gap_mm = val_mm
        if self.selected_position is not None:
            bc_data = self.interactive_viewer.get_barcode_data(self.selected_position)
            if bc_data is not None:
                bc_data["code39_hri_gap_mm"] = val_mm
                self._mark_modified()
                self._update_barcode_profile_size()

    def _on_code39_body_inc(self, e):
        """Incrementa cuerpo (font size) de Code 39."""
        try:
            val = max(0.0, float(self._code39_body_field.value) + 0.5)
        except (ValueError, TypeError):
            val = 13.0
        self._code39_body_field.value = f"{val:.1f}"
        self._code39_body_field.update()

        class _FakeEvent:
            def __init__(self, control):
                self.control = control

        self._on_code39_body_change(_FakeEvent(self._code39_body_field))
        self._on_body_gap_blur(None)

    def _on_code39_body_dec(self, e):
        """Decrementa cuerpo (font size) de Code 39."""
        try:
            val = max(0.0, float(self._code39_body_field.value) - 0.5)
        except (ValueError, TypeError):
            val = 13.0
        self._code39_body_field.value = f"{val:.1f}"
        self._code39_body_field.update()

        class _FakeEvent:
            def __init__(self, control):
                self.control = control

        self._on_code39_body_change(_FakeEvent(self._code39_body_field))
        self._on_body_gap_blur(None)

    def _on_code39_gap_inc(self, e):
        """Incrementa distancia HRI de Code 39."""
        try:
            val = max(0.0, float(self._code39_gap_field.value) + 0.5)
        except (ValueError, TypeError):
            val = 0.0
        self._code39_gap_field.value = f"{val:.1f}"
        self._code39_gap_field.update()

        class _FakeEvent:
            def __init__(self, control):
                self.control = control

        self._on_code39_gap_change(_FakeEvent(self._code39_gap_field))
        self._on_body_gap_blur(None)

    def _on_code39_gap_dec(self, e):
        """Decrementa distancia HRI de Code 39."""
        try:
            val = max(0.0, float(self._code39_gap_field.value) - 0.5)
        except (ValueError, TypeError):
            val = 0.0
        self._code39_gap_field.value = f"{val:.1f}"
        self._code39_gap_field.update()

        class _FakeEvent:
            def __init__(self, control):
                self.control = control

        self._on_code39_gap_change(_FakeEvent(self._code39_gap_field))
        self._on_body_gap_blur(None)

    def _on_code128_body_change(self, e):
        """Callback cuando cambia el cuerpo (font size) de Code 128."""
        normalize_decimal_input(e)
        try:
            val = float(e.control.value)
        except (ValueError, TypeError):
            return
        self._update_position_param("barcode_font_size", val)
        p = self._get_active_barcode_profile()
        if p:
            p.barcode_font_size = val
        if self.selected_position is not None:
            bc_data = self.interactive_viewer.get_barcode_data(self.selected_position)
            if bc_data is not None:
                bc_data["barcode_font_size"] = val
                self._mark_modified()
                self._update_barcode_profile_size()

    def _on_code128_gap_change(self, e):
        """Callback cuando cambia la distancia HRI de Code 128."""
        normalize_decimal_input(e)
        try:
            val_user = float(e.control.value)
        except (ValueError, TypeError):
            return
        val_mm = convert_to_mm(val_user, self.current_unit)
        if val_mm < 0:
            val_mm = 0.0
            e.control.value = self._fmt_mm(0.0)
            try:
                e.control.update()
            except Exception:
                pass
        self._update_position_param("code128_hri_gap_mm", val_mm)
        p = self._get_active_barcode_profile()
        if p:
            p.code128_hri_gap_mm = val_mm
        if self.selected_position is not None:
            bc_data = self.interactive_viewer.get_barcode_data(self.selected_position)
            if bc_data is not None:
                bc_data["code128_hri_gap_mm"] = val_mm
                self._mark_modified()
                self._update_barcode_profile_size()

    def _on_code128_body_inc(self, e):
        try:
            val = max(0.0, float(self._code128_body_field.value) + 0.5)
        except (ValueError, TypeError):
            val = 13.0
        self._code128_body_field.value = f"{val:.1f}"
        self._code128_body_field.update()

        class _FakeEvent:
            def __init__(self, control):
                self.control = control

        self._on_code128_body_change(_FakeEvent(self._code128_body_field))
        self._on_body_gap_blur(None)

    def _on_code128_body_dec(self, e):
        try:
            val = max(0.0, float(self._code128_body_field.value) - 0.5)
        except (ValueError, TypeError):
            val = 13.0
        self._code128_body_field.value = f"{val:.1f}"
        self._code128_body_field.update()

        class _FakeEvent:
            def __init__(self, control):
                self.control = control

        self._on_code128_body_change(_FakeEvent(self._code128_body_field))
        self._on_body_gap_blur(None)

    def _on_code128_gap_inc(self, e):
        try:
            val = max(0.0, float(self._code128_gap_field.value) + 0.5)
        except (ValueError, TypeError):
            val = 0.0
        self._code128_gap_field.value = f"{val:.1f}"
        self._code128_gap_field.update()

        class _FakeEvent:
            def __init__(self, control):
                self.control = control

        self._on_code128_gap_change(_FakeEvent(self._code128_gap_field))
        self._on_body_gap_blur(None)

    def _on_code128_gap_dec(self, e):
        try:
            val = max(0.0, float(self._code128_gap_field.value) - 0.5)
        except (ValueError, TypeError):
            val = 0.0
        self._code128_gap_field.value = f"{val:.1f}"
        self._code128_gap_field.update()

        class _FakeEvent:
            def __init__(self, control):
                self.control = control

        self._on_code128_gap_change(_FakeEvent(self._code128_gap_field))
        self._on_body_gap_blur(None)

    def _on_datamatrix_body_change(self, e):
        normalize_decimal_input(e)
        try:
            val = float(e.control.value)
        except (ValueError, TypeError):
            return
        self._update_position_param("barcode_font_size", val)
        p = self._get_active_barcode_profile()
        if p:
            p.barcode_font_size = val
        if self.selected_position is not None:
            bc_data = self.interactive_viewer.get_barcode_data(self.selected_position)
            if bc_data is not None:
                bc_data["barcode_font_size"] = val
                self.interactive_viewer.invalidate_barcode_render_cache(
                    self.selected_position
                )
                self._mark_modified()
                self._update_barcode_profile_size()

    _HRI_ALIGN_OPTIONS = (
        "top_left", "top_center", "top_right",
        "middle_left", "middle_center", "middle_right",
        "bottom_left", "bottom_center", "bottom_right",
    )

    def _sync_hri_align_dropdown(self, sym):
        """Reconstruye el dropdown Alineación HRI con opciones/valor de la simbología."""
        options = self._HRI_ALIGN_OPTIONS
        key = f"{sym}_hri_align"
        p = self._get_active_barcode_profile()
        val = getattr(p, key, None) if p is not None else None
        if val is None and self.selected_position is not None:
            bc = self.interactive_viewer.get_barcode_data(self.selected_position)
            val = bc.get(key, None) if bc else None
        if val is None and self.selected_position is not None:
            pdata = self._get_current_positions().get(self.selected_position, {})
            val = pdata.get(key, None)
        if val not in options:
            val = "bottom_center"
        self._hri_align_dd = self._create_dropdown_compact(
            options=[(o, t(o)) for o in options],
            value=val,
            width=140,
            on_change=self._on_hri_align_change,
        )
        row = getattr(self, "_alineacion_row", None)
        if row is not None and len(row.controls) > 1:
            row.controls[1] = self._hri_align_dd
        try:
            row.update()
        except Exception:
            pass

    def _on_hri_align_change(self, selected_key):
        """Cambia la alineación del HRI (perfil + pos_data + bc_data + visor)."""
        if self.selected_position is None:
            return
        bc = self.interactive_viewer.get_barcode_data(self.selected_position)
        sym = bc.get("symbology") if bc else ""
        allowed = self._HRI_ALIGN_OPTIONS
        val = str(selected_key) if str(selected_key) in allowed else "bottom_center"
        key = f"{sym}_hri_align"
        self._update_position_param(key, val)
        p = self._get_active_barcode_profile()
        if p is not None and hasattr(p, key):
            setattr(p, key, val)
        bc_data = self.interactive_viewer.get_barcode_data(self.selected_position)
        if bc_data is not None:
            bc_data[key] = val
            self._mark_modified()
            self._on_body_gap_blur(None)

    def _sync_hri_position_dropdown(self, sym):
        """Reconstruye el dropdown Posición HRI con opciones/valor de la simbología."""
        options_by_sym = {
            "qr": ("left", "right", "above", "below"),
            "pdf417": ("left", "right", "above", "below"),
            "datamatrix": ("left", "right", "above", "below"),
            "datamatrix_gs1": ("left", "right", "above", "below"),
            "datamatrix_dl": ("left", "right", "above", "below"),
            "code128": ("above", "below"),
            "code39": ("above", "below"),
            "itf14": ("above", "below"),
        }
        options = options_by_sym.get(sym)
        if not options:
            return
        key = f"{sym}_hri_position"
        p = self._get_active_barcode_profile()
        val = getattr(p, key, None) if p is not None else None
        if val is None and self.selected_position is not None:
            bc = self.interactive_viewer.get_barcode_data(self.selected_position)
            val = bc.get(key, None) if bc else None
        if val is None and self.selected_position is not None:
            pdata = self._get_current_positions().get(self.selected_position, {})
            val = pdata.get(key, None)
        if val not in options:
            val = "below"
        self._hri_position_dd = self._create_dropdown_compact(
            options=[(o, t(o)) for o in options],
            value=val,
            width=140,
            on_change=self._on_hri_position_change,
        )
        # Sustituir en la fila padre (controls[1] es el dropdown)
        row = getattr(self, "_posicion_hri_row", None)
        if row is not None and len(row.controls) > 1:
            row.controls[1] = self._hri_position_dd
        try:
            row.update()
        except Exception:
            pass

    def _on_hri_position_change(self, selected_key):
        """Cambia la posición del bloque HRI (perfil + pos_data + bc_data + tamaño)."""
        if self.selected_position is None:
            return
        bc = self.interactive_viewer.get_barcode_data(self.selected_position)
        sym = bc.get("symbology") if bc else ""
        allowed = (
            ("left", "right", "above", "below")
            if (_is_datamatrix_family(sym) or sym in ("qr", "pdf417"))
            else ("above", "below")
        )
        val = str(selected_key) if str(selected_key) in allowed else "below"
        key = f"{sym}_hri_position"
        self._update_position_param(key, val)
        p = self._get_active_barcode_profile()
        if p is not None and hasattr(p, key):
            setattr(p, key, val)
        bc_data = self.interactive_viewer.get_barcode_data(self.selected_position)
        if bc_data is not None:
            bc_data[key] = val
            self._mark_modified()
            self._update_barcode_profile_size()
            # Propaga al mismo perfil + _redraw_all(force) (mismo camino que Cuerpo/Distancia)
            self._on_body_gap_blur(None)

    def _on_datamatrix_gap_change(self, e):
        normalize_decimal_input(e)
        try:
            val_user = float(e.control.value)
        except (ValueError, TypeError):
            return
        val_mm = convert_to_mm(val_user, self.current_unit)
        if val_mm < 0:
            val_mm = 0.0
            e.control.value = self._fmt_mm(0.0)
            try:
                e.control.update()
            except Exception:
                pass
        key = "datamatrix_hri_gap_mm"
        if self.selected_position is not None:
            bc = self.interactive_viewer.get_barcode_data(self.selected_position)
            sym = bc.get("symbology") if bc else ""
            if sym == "qr":
                key = "qr_hri_gap_mm"
            elif sym == "pdf417":
                key = "pdf417_hri_gap_mm"
        self._update_position_param(key, val_mm)
        p = self._get_active_barcode_profile()
        print(f"[DBG GAPCHANGE] key={key} val_mm={val_mm} p_is_none={p is None}")
        if p:
            if key == "qr_hri_gap_mm":
                p.qr_hri_gap_mm = val_mm
            elif key == "pdf417_hri_gap_mm":
                p.pdf417_hri_gap_mm = val_mm
            else:
                p.datamatrix_hri_gap_mm = val_mm
        if self.selected_position is not None:
            bc_data = self.interactive_viewer.get_barcode_data(self.selected_position)
            if bc_data is not None:
                bc_data[key] = val_mm
                self.interactive_viewer.invalidate_barcode_render_cache(
                    self.selected_position
                )
                self._mark_modified()
                self._update_barcode_profile_size()

    def _on_datamatrix_body_inc(self, e):
        try:
            val = max(0.0, float(self._datamatrix_body_field.value) + 0.5)
        except (ValueError, TypeError):
            val = 9.0
        self._datamatrix_body_field.value = f"{val:.1f}"
        self._datamatrix_body_field.update()

        class _FakeEvent:
            def __init__(self, control):
                self.control = control

        self._on_datamatrix_body_change(_FakeEvent(self._datamatrix_body_field))
        self._on_body_gap_blur(None)

    def _on_datamatrix_body_dec(self, e):
        try:
            val = max(0.0, float(self._datamatrix_body_field.value) - 0.5)
        except (ValueError, TypeError):
            val = 9.0
        self._datamatrix_body_field.value = f"{val:.1f}"
        self._datamatrix_body_field.update()

        class _FakeEvent:
            def __init__(self, control):
                self.control = control

        self._on_datamatrix_body_change(_FakeEvent(self._datamatrix_body_field))
        self._on_body_gap_blur(None)

    def _on_datamatrix_gap_inc(self, e):
        try:
            val = max(0.0, float(self._datamatrix_gap_field.value) + 0.5)
        except (ValueError, TypeError):
            val = 0.0
        self._datamatrix_gap_field.value = f"{val:.1f}"
        self._datamatrix_gap_field.update()

        class _FakeEvent:
            def __init__(self, control):
                self.control = control

        self._on_datamatrix_gap_change(_FakeEvent(self._datamatrix_gap_field))
        self._on_body_gap_blur(None)

    def _on_datamatrix_gap_dec(self, e):
        try:
            val = max(0.0, float(self._datamatrix_gap_field.value) - 0.5)
        except (ValueError, TypeError):
            val = 0.0
        self._datamatrix_gap_field.value = f"{val:.1f}"
        self._datamatrix_gap_field.update()

        class _FakeEvent:
            def __init__(self, control):
                self.control = control

        self._on_datamatrix_gap_change(_FakeEvent(self._datamatrix_gap_field))
        self._on_body_gap_blur(None)

    def _on_datamatrix_hri_line_spacing_change(self, e):
        normalize_decimal_input(e)
        try:
            val = float(e.control.value)
        except (ValueError, TypeError):
            return
        if val < 0:
            val = 0.0
            e.control.value = f"{val:.1f}"
            try:
                e.control.update()
            except Exception:
                pass
        key = "datamatrix_hri_line_spacing"
        if self.selected_position is not None:
            bc = self.interactive_viewer.get_barcode_data(self.selected_position)
            sym = bc.get("symbology") if bc else ""
            if sym == "qr":
                key = "qr_hri_line_spacing"
            elif sym == "pdf417":
                key = "pdf417_hri_line_spacing"
        self._update_position_param(key, val)
        p = self._get_active_barcode_profile()
        if p:
            if key == "qr_hri_line_spacing":
                p.qr_hri_line_spacing = val
            elif key == "pdf417_hri_line_spacing":
                p.pdf417_hri_line_spacing = val
            else:
                p.datamatrix_hri_line_spacing = val
        if self.selected_position is not None:
            bc_data = self.interactive_viewer.get_barcode_data(self.selected_position)
            if bc_data is not None:
                bc_data[key] = val
                self.interactive_viewer.invalidate_barcode_render_cache(
                    self.selected_position
                )
                self._mark_modified()
                self._update_barcode_profile_size()

    def _on_datamatrix_hri_line_spacing_inc(self, e):
        try:
            val = round(max(0.0, float(self._datamatrix_hri_line_spacing_field.value) + 0.1), 1)
        except (ValueError, TypeError):
            val = 1.0
        self._datamatrix_hri_line_spacing_field.value = f"{val:.1f}"
        self._datamatrix_hri_line_spacing_field.update()

        class _FakeEvent:
            def __init__(self, control):
                self.control = control

        self._on_datamatrix_hri_line_spacing_change(_FakeEvent(self._datamatrix_hri_line_spacing_field))
        self._on_body_gap_blur(None)

    def _on_datamatrix_hri_line_spacing_dec(self, e):
        try:
            val = round(max(0.0, float(self._datamatrix_hri_line_spacing_field.value) - 0.1), 1)
        except (ValueError, TypeError):
            val = 1.0
        self._datamatrix_hri_line_spacing_field.value = f"{val:.1f}"
        self._datamatrix_hri_line_spacing_field.update()

        class _FakeEvent:
            def __init__(self, control):
                self.control = control

        self._on_datamatrix_hri_line_spacing_change(_FakeEvent(self._datamatrix_hri_line_spacing_field))
        self._on_body_gap_blur(None)

    def _update_datamatrix_height_options(self):
        """Recalculate height dropdown options when Ancho or data changes."""
        from utils.barcode_module import get_datamatrix_possible_heights

        p = self._get_active_barcode_profile()
        if not p or not _is_datamatrix_family(p.symbology):
            return
        self._recalc_profile_minimums(p)
        ancho = p.datamatrix_width or 20.0
        values = []
        if p.datamatrix_longest_value:
            values = [p.datamatrix_longest_value]
        if not values and p.sample_value:
            values = [p.sample_value]
        if not values:
            values = [""]
        possible = get_datamatrix_possible_heights(values, ancho)
        if not possible:
            possible = [(20.0, "square")]
        self._datamatrix_height_options = possible
        options = [
            (f"{h:.1f}", self._fmt_mm(h))
            for h, fmt in possible
        ]
        current_h = float(p.datamatrix_height or 0)
        best_h, best_fmt = possible[0]
        for h, fmt in possible:
            if abs(h - (current_h or 0)) < abs(best_h - (current_h or 0)):
                best_h, best_fmt = h, fmt
        p.datamatrix_height = best_h
        p.datamatrix_format = best_fmt
        # Rebuild the dropdown widget
        self._datamatrix_height_dd = self._create_dropdown_compact(
            options=options,
            value=f"{best_h:.1f}",
            width=70,
            on_change=self._on_datamatrix_height_change,
        )
        # Refresh label with current unit
        if alto_row := getattr(self, "_datamatrix_alto_row", None):
            if alto_row.controls:
                alto_row.controls[0].value = t("Alto ({0}):").format(
                    _unit_abbr(self.current_unit)
                )
                try:
                    alto_row.controls[0].update()
                except Exception:
                    pass
        # Replace in parent row — controls[1] is the Container wrapper
        alto_row = self._datamatrix_alto_row
        if alto_row.controls and len(alto_row.controls) > 1:
            wrapper = alto_row.controls[1]
            if hasattr(wrapper, "content"):
                wrapper.content = self._datamatrix_height_dd
        try:
            alto_row.update()
        except Exception:
            pass

    def _on_datamatrix_height_change(self, e):
        """Callback when user selects a height from the DM height dropdown."""
        val_str = (
            e
            if isinstance(e, str)
            else (e.control.data if hasattr(e.control, "data") else e.control.value)
        )
        try:
            val_mm = float(val_str)
        except (ValueError, TypeError):
            return
        p = self._get_active_barcode_profile()
        if p:
            p.datamatrix_height = val_mm
            for h, fmt in self._datamatrix_height_options:
                if abs(h - val_mm) < 0.05:
                    p.datamatrix_format = fmt
                    break
        self._update_position_param("datamatrix_height", val_mm)
        if self.selected_position is not None:
            bc_data = self.interactive_viewer.get_barcode_data(self.selected_position)
            if bc_data is not None:
                bc_data["datamatrix_height"] = val_mm
                _dm_fmt = None
                for h, fmt in self._datamatrix_height_options:
                    if abs(h - val_mm) < 0.05:
                        bc_data["datamatrix_format"] = fmt
                        _dm_fmt = fmt
                        break
                self.interactive_viewer.invalidate_datamatrix_cache(
                    self.selected_position
                )
                _profile_ids = None
                _profile_name = bc_data.get("profile_name")
                if _profile_name:
                    _updates = {"datamatrix_height": val_mm}
                    if _dm_fmt:
                        _updates["datamatrix_format"] = _dm_fmt
                    _profile_ids = self._propagate_to_same_profile(_profile_name, _updates)
                if _profile_ids:
                    self.interactive_viewer._redraw_all(force=True, only_barcode_ids=_profile_ids)
                self._mark_modified()
                self._update_barcode_profile_size()

    def _on_ean5_body_change(self, e):
        normalize_decimal_input(e)
        try:
            val = float(e.control.value)
        except (ValueError, TypeError):
            return
        if val < 1.0:
            val = 1.0
            e.control.value = "1.0"
            try:
                e.control.update()
            except Exception:
                pass
        self._update_position_param("barcode_font_size", val)
        p = self._get_active_barcode_profile()
        if p:
            p.barcode_font_size = val
        if self.selected_position is not None:
            bc_data = self.interactive_viewer.get_barcode_data(self.selected_position)
            if bc_data is not None:
                bc_data["barcode_font_size"] = val
                self._mark_modified()
                self._update_barcode_profile_size()

    def _on_generic_body_change(self, e):
        normalize_decimal_input(e)
        try:
            val = float(e.control.value)
        except (ValueError, TypeError):
            return
        p = self._get_active_barcode_profile()
        if val < 1.0:
            val = 1.0
            e.control.value = "1.0"
            try:
                e.control.update()
            except Exception:
                pass
        max_pt = self._generic_body_max_pt()
        if max_pt is not None and val > max_pt:
            prev = min(
                p.barcode_font_size if p else max_pt,
                max_pt,
            )
            e.control.value = f"{round(prev, 2):g}"
            try:
                e.control.update()
            except Exception:
                pass
            return
        self._update_position_param("barcode_font_size", val)
        if p:
            p.barcode_font_size = val
        if self.selected_position is not None:
            bc_data = self.interactive_viewer.get_barcode_data(self.selected_position)
            if bc_data is not None:
                bc_data["barcode_font_size"] = val
                self._mark_modified()
                self._update_barcode_profile_size()

    def _on_generic_body_inc(self, e):
        try:
            val = max(1.0, float(self._generic_body_field.value) + 0.5)
        except (ValueError, TypeError):
            val = 13.0
        max_pt = self._generic_body_max_pt()
        if max_pt is not None and val > max_pt:
            return
        self._generic_body_field.value = f"{val:.1f}"
        self._generic_body_field.update()

        class _FakeEvent:
            def __init__(self, control):
                self.control = control

        self._on_generic_body_change(_FakeEvent(self._generic_body_field))
        self._on_body_gap_blur(None)

    def _on_generic_body_dec(self, e):
        try:
            val = max(1.0, float(self._generic_body_field.value) - 0.5)
        except (ValueError, TypeError):
            val = 13.0
        self._generic_body_field.value = f"{val:.1f}"
        self._generic_body_field.update()

        class _FakeEvent:
            def __init__(self, control):
                self.control = control

        self._on_generic_body_change(_FakeEvent(self._generic_body_field))
        self._on_body_gap_blur(None)

    def _on_ean5_gap_change(self, e):
        normalize_decimal_input(e)
        try:
            val_user = float(e.control.value)
        except (ValueError, TypeError):
            return
        val_mm = convert_to_mm(val_user, self.current_unit)
        if val_mm < 0:
            val_mm = 0.0
            e.control.value = self._fmt_mm(0.0)
            try:
                e.control.update()
            except Exception:
                pass
        self._update_position_param("ean5_hri_gap_mm", val_mm)
        p = self._get_active_barcode_profile()
        if p:
            p.ean5_hri_gap_mm = val_mm
        if self.selected_position is not None:
            bc_data = self.interactive_viewer.get_barcode_data(self.selected_position)
            if bc_data is not None:
                bc_data["ean5_hri_gap_mm"] = val_mm
                self._mark_modified()
                self._update_barcode_profile_size()

    def _on_ean5_body_inc(self, e):
        try:
            val = max(1.0, float(self._ean5_body_field.value) + 0.5)
        except (ValueError, TypeError):
            val = 13.0
        self._ean5_body_field.value = f"{val:.1f}"
        self._ean5_body_field.update()

        class _FakeEvent:
            def __init__(self, control):
                self.control = control

        self._on_ean5_body_change(_FakeEvent(self._ean5_body_field))
        self._on_body_gap_blur(None)

    def _on_ean5_body_dec(self, e):
        try:
            val = max(1.0, float(self._ean5_body_field.value) - 0.5)
        except (ValueError, TypeError):
            val = 13.0
        self._ean5_body_field.value = f"{val:.1f}"
        self._ean5_body_field.update()

        class _FakeEvent:
            def __init__(self, control):
                self.control = control

        self._on_ean5_body_change(_FakeEvent(self._ean5_body_field))
        self._on_body_gap_blur(None)

    def _on_ean5_gap_inc(self, e):
        try:
            val = max(0.0, float(self._ean5_gap_field.value) + 0.5)
        except (ValueError, TypeError):
            val = 0.0
        self._ean5_gap_field.value = f"{val:.1f}"
        self._ean5_gap_field.update()

        class _FakeEvent:
            def __init__(self, control):
                self.control = control

        self._on_ean5_gap_change(_FakeEvent(self._ean5_gap_field))
        self._on_body_gap_blur(None)

    def _on_ean5_gap_dec(self, e):
        try:
            val = max(0.0, float(self._ean5_gap_field.value) - 0.5)
        except (ValueError, TypeError):
            val = 0.0
        self._ean5_gap_field.value = f"{val:.1f}"
        self._ean5_gap_field.update()

        class _FakeEvent:
            def __init__(self, control):
                self.control = control

        self._on_ean5_gap_change(_FakeEvent(self._ean5_gap_field))
        self._on_body_gap_blur(None)

    # ── Font size helpers ──────────────────────────────────────────────────

    def _update_num_font_size(self, new_size):
        """Actualiza font_size del TextStyle perfil activo + redibuja."""
        profile_name = self.text_style_dropdown.content.controls[0].value
        if profile_name and hasattr(self, "text_style_manager"):
            for p in self.text_style_manager.profiles:
                if p.name == profile_name:
                    p.font_size = new_size
                    break
        self.interactive_viewer._redraw_all()
        self._mark_modified()

    def _update_vt_font_size(self, new_size):
        """Actualiza font_size en perfil + pos_data de todas las VT con ese perfil."""
        profile_name = self._variable_text_profile_dropdown.content.controls[0].value
        if profile_name and hasattr(self, "variable_text_ui_manager"):
            for p in self.variable_text_ui_manager.profile_manager.profiles:
                if p.name == profile_name:
                    p.font_size = new_size
                    break
        current_positions = self._get_current_positions()
        for pos_id, pdata in current_positions.items():
            if pdata.get("type") == "variable_text" and pdata.get("profile_name") == profile_name:
                pdata["font_size"] = new_size
        spacing = LINE_SPACING_AUTO * new_size
        self._vt_line_spacing_field.value = _fmt_pt(spacing)
        self._vt_line_spacing_field.update()
        for pos_id, pdata in current_positions.items():
            if pdata.get("type") == "variable_text" and pdata.get("profile_name") == profile_name:
                pdata["line_spacing"] = spacing
        if profile_name and hasattr(self, "variable_text_ui_manager"):
            for p in self.variable_text_ui_manager.profile_manager.profiles:
                if p.name == profile_name:
                    p.line_spacing = spacing
                    break
        self._mark_modified()
        try:
            self.interactive_viewer._redraw_all()
        except AssertionError:
            pass

    # ── Numeración font size callbacks ─────────────────────────────────────

    def _on_num_font_size_change(self, e):
        """Callback cuando cambia el tamaño de letra (numeración)."""
        normalize_decimal_input(e)
        try:
            size = max(1.0, float(e.control.value))
        except (ValueError, TypeError):
            return
        self._update_position_param("font_size", size)
        self._update_num_font_size(size)

    def _on_num_font_size_inc(self, e):
        """Incrementa tamaño de letra de numeración."""
        try:
            size = max(1.0, float(self._num_font_size_field.value) + 1)
        except (ValueError, TypeError):
            size = 12.0
        self._num_font_size_field.value = _fmt_pt(size)
        self._num_font_size_field.update()
        self._update_position_param("font_size", size)
        self._update_num_font_size(size)

    def _on_num_font_size_dec(self, e):
        """Decrementa tamaño de letra de numeración."""
        try:
            size = max(1.0, float(self._num_font_size_field.value) - 1)
        except (ValueError, TypeError):
            size = 12.0
        self._num_font_size_field.value = _fmt_pt(size)
        self._num_font_size_field.update()
        self._update_position_param("font_size", size)
        self._update_num_font_size(size)

    # ── Numeración interletraje callbacks ─────────────────────────────────

    def _on_num_letter_spacing_change(self, e):
        """Callback cuando cambia el interletraje (numeración)."""
        normalize_decimal_input(e)
        try:
            value = float(e.control.value)
        except (ValueError, TypeError):
            return
        # Re-sincronizar el campo: el redondeo evita que quede un valor
        # no formateado que rompería el siguiente incremento/decremento.
        display = _fmt_pt(value)
        if self._num_letter_spacing_field.value != display:
            self._num_letter_spacing_field.value = display
            self._num_letter_spacing_field.update()
        self._update_num_letter_spacing(value)

    def _on_num_letter_spacing_inc(self, e):
        """Incrementa interletraje de numeración."""
        try:
            value = round(float(self._num_letter_spacing_field.value) + 0.1, 1)
        except (ValueError, TypeError):
            value = 0.0
        self._num_letter_spacing_field.value = _fmt_pt(value)
        self._num_letter_spacing_field.update()
        self._update_num_letter_spacing(value)

    def _on_num_letter_spacing_dec(self, e):
        """Decrementa interletraje de numeración."""
        try:
            value = round(float(self._num_letter_spacing_field.value) - 0.1, 1)
        except (ValueError, TypeError):
            value = 0.0
        self._num_letter_spacing_field.value = _fmt_pt(value)
        self._num_letter_spacing_field.update()
        self._update_num_letter_spacing(value)

    def _update_num_letter_spacing(self, new_value):
        """Actualiza letter_spacing del TextStyle perfil activo + redibuja."""
        profile_name = self.text_style_dropdown.content.controls[0].value
        if profile_name and hasattr(self, "text_style_manager"):
            for p in self.text_style_manager.profiles:
                if p.name == profile_name:
                    p.letter_spacing = new_value
                    break
        self.interactive_viewer._redraw_all()
        self._mark_modified()

    # ── Texto variable font size callbacks ─────────────────────────────────

    def _on_vt_font_size_change(self, e):
        """Callback cuando cambia el tamaño de letra (texto variable)."""
        normalize_decimal_input(e)
        try:
            size = float(e.control.value)
        except (ValueError, TypeError):
            return
        self._update_position_param("font_size", size)
        self._update_vt_font_size(size)

    def _on_vt_font_size_inc(self, e):
        """Incrementa tamaño de letra de texto variable."""
        try:
            size = float(self._vt_font_size_field.value) + 1
        except (ValueError, TypeError):
            size = 12.0
        self._vt_font_size_field.value = str(size)
        self._vt_font_size_field.update()
        self._update_position_param("font_size", size)
        self._update_vt_font_size(size)

    def _on_vt_font_size_dec(self, e):
        """Decrementa tamaño de letra de texto variable."""
        try:
            size = max(1.0, float(self._vt_font_size_field.value) - 1)
        except (ValueError, TypeError):
            size = 12.0
        self._vt_font_size_field.value = str(size)
        self._vt_font_size_field.update()
        self._update_position_param("font_size", size)
        self._update_vt_font_size(size)

    def _update_vt_line_spacing(self, new_spacing):
        """Actualiza line_spacing en perfil + pos_data de todas las VT con ese perfil."""
        profile_name = self._variable_text_profile_dropdown.content.controls[0].value
        if profile_name and hasattr(self, "variable_text_ui_manager"):
            for p in self.variable_text_ui_manager.profile_manager.profiles:
                if p.name == profile_name:
                    p.line_spacing = new_spacing
                    break
        current_positions = self._get_current_positions()
        for pos_id, pdata in current_positions.items():
            if pdata.get("type") == "variable_text" and pdata.get("profile_name") == profile_name:
                pdata["line_spacing"] = new_spacing
        self._mark_modified()
        try:
            self.interactive_viewer._redraw_all()
        except AssertionError:
            pass

    def _on_vt_line_spacing_change(self, e):
        """Callback cuando cambia el interlineado de texto variable (pt, como el diálogo)."""
        normalize_decimal_input(e)
        try:
            spacing = float(e.control.value)
        except (ValueError, TypeError):
            return
        if spacing < 0:
            spacing = 0.0
        self._vt_line_spacing_auto = False
        self._update_position_param("line_spacing", spacing)
        self._update_vt_line_spacing(spacing)

    def _on_vt_line_spacing_inc(self, e):
        try:
            spacing = max(0.0, round((float(self._vt_line_spacing_field.value) or 0.0) + 0.5, 1))
        except (ValueError, TypeError):
            spacing = 1.0
        self._vt_line_spacing_auto = False
        self._vt_line_spacing_field.value = _fmt_pt(spacing)
        self._vt_line_spacing_field.update()
        self._update_position_param("line_spacing", spacing)
        self._update_vt_line_spacing(spacing)

    def _on_vt_line_spacing_dec(self, e):
        try:
            spacing = max(0.0, round((float(self._vt_line_spacing_field.value) or 0.0) - 0.5, 1))
        except (ValueError, TypeError):
            spacing = 1.0
        self._vt_line_spacing_auto = False
        self._vt_line_spacing_field.value = _fmt_pt(spacing)
        self._vt_line_spacing_field.update()
        self._update_position_param("line_spacing", spacing)
        self._update_vt_line_spacing(spacing)

    def _on_vt_line_spacing_reset(self, e):
        """Restablece el interlineado al valor auto (1.2 × cuerpo), como el diálogo."""
        try:
            cuerpo = float(self._vt_font_size_field.value) or 12.0
        except (ValueError, TypeError):
            cuerpo = 12.0
        spacing = LINE_SPACING_AUTO * cuerpo
        self._vt_line_spacing_auto = True
        self._vt_line_spacing_field.value = _fmt_pt(spacing)
        self._vt_line_spacing_field.update()
        self._update_position_param("line_spacing", spacing)
        self._update_vt_line_spacing(spacing)

    def _update_vt_letter_spacing(self, new_spacing):
        """Actualiza letter_spacing en perfil + pos_data de todas las VT con ese perfil."""
        profile_name = self._variable_text_profile_dropdown.content.controls[0].value
        if profile_name and hasattr(self, "variable_text_ui_manager"):
            for p in self.variable_text_ui_manager.profile_manager.profiles:
                if p.name == profile_name:
                    p.letter_spacing = new_spacing
                    break
        current_positions = self._get_current_positions()
        for pos_id, pdata in current_positions.items():
            if pdata.get("type") == "variable_text" and pdata.get("profile_name") == profile_name:
                pdata["letter_spacing"] = new_spacing
        self._mark_modified()
        try:
            self.interactive_viewer._redraw_all()
        except AssertionError:
            pass

    def _on_vt_letter_spacing_change(self, e):
        """Callback cuando cambia el interletraje de texto variable (pt, como el diálogo)."""
        normalize_decimal_input(e)
        try:
            value = float(e.control.value)
        except (ValueError, TypeError):
            return
        # Re-sincronizar el campo: el redondeo evita que quede un valor
        # no formateado que rompería el siguiente incremento/decremento.
        display = _fmt_pt(value)
        if self._vt_letter_spacing_field.value != display:
            self._vt_letter_spacing_field.value = display
            self._vt_letter_spacing_field.update()
        self._update_position_param("letter_spacing", value)
        self._update_vt_letter_spacing(value)

    def _on_vt_letter_spacing_inc(self, e):
        """Incrementa interletraje de texto variable (±0.1, negativos permitidos)."""
        try:
            value = round(float(self._vt_letter_spacing_field.value) + 0.1, 1)
        except (ValueError, TypeError):
            value = 0.0
        self._vt_letter_spacing_field.value = _fmt_pt(value)
        self._vt_letter_spacing_field.update()
        self._update_position_param("letter_spacing", value)
        self._update_vt_letter_spacing(value)

    def _on_vt_letter_spacing_dec(self, e):
        """Decrementa interletraje de texto variable (±0.1, negativos permitidos)."""
        try:
            value = round(float(self._vt_letter_spacing_field.value) - 0.1, 1)
        except (ValueError, TypeError):
            value = 0.0
        self._vt_letter_spacing_field.value = _fmt_pt(value)
        self._vt_letter_spacing_field.update()
        self._update_position_param("letter_spacing", value)
        self._update_vt_letter_spacing(value)

    def _update_vt_text_alignment(self, value):
        """Alineación = propiedad del PERFIL: actualiza p.text_alignment y todas
        las VT de ese perfil (pos_data + vd). Solo alinea el texto DENTRO de la
        caja; colocar la caja vs la guía es la Posición (anchor, post_data)."""
        profile_name = self._variable_text_profile_dropdown.content.controls[0].value
        if profile_name and hasattr(self, "variable_text_ui_manager"):
            for p in self.variable_text_ui_manager.profile_manager.profiles:
                if p.name == profile_name:
                    p.text_alignment = value
                    break
        current_positions = self._get_current_positions()
        for pos_id, pdata in current_positions.items():
            if pdata.get("type") == "variable_text" and pdata.get("profile_name") == profile_name:
                pdata["text_alignment"] = value
                vt_data = self.interactive_viewer.get_variable_text_data(pos_id)
                if vt_data is not None:
                    vt_data["text_alignment"] = value
        try:
            self.interactive_viewer._redraw_all()
        except AssertionError:
            pass
        self._mark_modified()

    def _on_vt_text_alignment_change(self, value):
        """Callback cuando cambia la alineación del texto dentro de la caja VT."""
        self._update_vt_text_alignment(value)

    def _on_rotation_change(self, rotation_value):
        """
        Maneja el cambio de rotación
        Actualiza el diccionario y el viewer

        Args:
            rotation_value: String con el valor de rotación ("0°", "90°", "180°", "270°")
        """
        # Actualizar diccionario
        self._update_position_param("rotation", rotation_value)

        # Actualizar vista si hay posición seleccionada
        if self.selected_position is not None:
            current_positions = self._get_current_positions()
            pos_type = current_positions.get(self.selected_position, {}).get(
                "type", "number"
            )
            if pos_type == "barcode":
                self.interactive_viewer.update_barcode_post_data_visual(
                    self.selected_position, rotation=rotation_value
                )
            elif pos_type == "variable_text":
                self.interactive_viewer.set_variable_text_rotation(
                    self.selected_position, rotation_value
                )
            else:
                self.interactive_viewer.set_rotation(
                    self.selected_position, rotation_value
                )
            print(f"Posición {self.selected_position}: rotation = {rotation_value}")

            # Marcar proyecto como modificado solo si había posición seleccionada
            self._mark_modified()

    def _on_unit_change(self, unit_value):
        """Callback cuando cambia la unidad (estado global)"""
        # Guardar en estado global
        old_unit = self.current_unit
        self.current_unit = unit_value

        # Actualizar los gestores de imagen de fondo (por si cambió el papel por defecto)
        for manager in self.background_image_managers.values():
            manager.set_app_page_size(self.page_width_mm, self.page_height_mm)

        # Guardar en preferencias (sin bleed, que es parte del proyecto)
        save_startup_settings(self.page_size_name, unit_value)

        # Actualizar texto de tamaño de página según la unidad
        self._update_page_size_text()

        # Actualizar unidad de las reglas si están habilitadas (siempre, aunque no haya numeradora)
        if ENABLE_RULERS:
            self.interactive_viewer.set_ruler_unit(unit_value)

        # Marcar proyecto como modificado
        self._mark_modified()

        # Actualizar etiqueta de unidad de medida
        self._update_unit_label()

        # Si no hay posición seleccionada, solo actualizamos las reglas y el tamaño
        if self.selected_position is None:
            return

        # Obtener la unidad anterior
        pos_data = self._get_current_position(self.selected_position)
        if not pos_data:
            return

        # Actualizar la unidad en el diccionario
        self._update_position_param("unit", unit_value)

        # Reconvertir los valores mostrados en la UI
        # Los valores internos (x, y) están siempre en mm
        x_mm = pos_data.get("x", 0)
        y_mm = pos_data.get("y", 0)

        # Convertir de mm a la nueva unidad para mostrar en la UI
        vertical_converted = convert_from_mm(y_mm, unit_value)
        horizontal_converted = convert_from_mm(x_mm, unit_value)

        # Formatear según la unidad
        if unit_value == UNIT_PX:
            vertical_str = f"{vertical_converted:.1f}"
            horizontal_str = f"{horizontal_converted:.1f}"
        else:
            vertical_str = f"{vertical_converted:.4f}"
            horizontal_str = f"{horizontal_converted:.4f}"

        # Actualizar los textfields de posición
        self.vertical_field.value = vertical_str
        self.horizontal_field.value = horizontal_str

        # Actualizar valores en el diccionario (solo UI, no cambian x/y que están en mm)
        pos_data["vertical"] = vertical_str
        pos_data["horizontal"] = horizontal_str

        # Actualizar controles
        self.vertical_field.update()
        self.horizontal_field.update()

        # Reconvertir valores de dimensiones de código de barras (mm → nueva unidad)
        if pos_data.get("type") == "barcode":
            p = self._get_active_barcode_profile()
            if p:
                bw_mm = p.bar_width
                bh_mm = p.bar_height
                pw_mm = p.pdf417_size if p.pdf417_size is not None else p.bar_width
                ph_mm = p.pdf417_height if p.pdf417_height is not None else p.bar_height
                gap_mm = p.itf14_hri_gap_mm
                code39_gap_mm = p.code39_hri_gap_mm
                code128_gap_mm = p.code128_hri_gap_mm
                ean5_gap_mm = p.ean5_hri_gap_mm
                dm_gap_mm = p.datamatrix_hri_gap_mm
                qr_gap_mm = p.qr_hri_gap_mm
                pdf417_gap_mm = p.pdf417_hri_gap_mm
            else:
                bw_mm = pos_data.get("bar_width", 80.0)
                bh_mm = pos_data.get("bar_height", 30.0)
                pw_mm = pos_data.get("pdf417_size", 80.0)
                ph_mm = pos_data.get("pdf417_height", 30.0)
                gap_mm = pos_data.get("itf14_hri_gap_mm", 2.0)
                code39_gap_mm = float(pos_data.get("code39_hri_gap_mm", 2.0))
                code128_gap_mm = float(pos_data.get("code128_hri_gap_mm", 2.0))
                ean5_gap_mm = float(pos_data.get("ean5_hri_gap_mm", 2.0))
                dm_gap_mm = float(pos_data.get("datamatrix_hri_gap_mm", 2.0))
                qr_gap_mm = float(pos_data.get("qr_hri_gap_mm", 2.0))
                pdf417_gap_mm = float(pos_data.get("pdf417_hri_gap_mm", 2.0))
            self.bar_width_field.value = self._fmt_mm(bw_mm, unit_value)
            self.bar_height_field.value = self._fmt_mm(bh_mm, unit_value)
            self.qr_size_field.value = self._fmt_mm(bw_mm, unit_value)
            self._pdf417_width_field.value = self._fmt_mm(pw_mm, unit_value)
            self._pdf417_height_field.value = self._fmt_mm(ph_mm, unit_value)
            self._itf14_gap_field.value = self._fmt_mm(gap_mm, unit_value)
            self._code39_gap_field.value = self._fmt_mm(code39_gap_mm, unit_value)
            self._code128_gap_field.value = self._fmt_mm(code128_gap_mm, unit_value)
            self._ean5_gap_field.value = self._fmt_mm(ean5_gap_mm, unit_value)
            sym = pos_data.get("symbology")
            if sym == "qr":
                gap_mm = qr_gap_mm
            elif sym == "pdf417":
                gap_mm = pdf417_gap_mm
            elif _is_datamatrix_family(sym):
                gap_mm = dm_gap_mm
            self._datamatrix_gap_field.value = self._fmt_mm(gap_mm, unit_value)
            if _is_datamatrix_family(pos_data.get("symbology")):
                self._update_datamatrix_height_options()
            self.bar_width_field.update()
            self.bar_height_field.update()
            self.qr_size_field.update()
            self._pdf417_width_field.update()
            self._pdf417_height_field.update()
            self._itf14_gap_field.update()
            self._code39_gap_field.update()
            self._code128_gap_field.update()
            self._ean5_gap_field.update()
            self._datamatrix_gap_field.update()
            body_val = (
                str(p.barcode_font_size)
                if p
                else str(pos_data.get("barcode_font_size", 13.0))
            )
            self._code39_body_field.value = body_val
            self._code128_body_field.value = body_val
            self._datamatrix_body_field.value = body_val
            self._ean5_body_field.value = body_val
            self._generic_body_field.value = body_val
            self._itf14_body_field.value = body_val
            self._code39_body_field.update()
            self._code128_body_field.update()
            self._datamatrix_body_field.update()
            self._ean5_body_field.update()
            self._generic_body_field.update()
            self._itf14_body_field.update()

    def _update_unit_label(self):
        """Actualiza las etiquetas de offset con la unidad de medida activa."""
        try:
            abbr = _unit_abbr(self.current_unit)
            # Actualizar labels de offset en la sección de medidas
            try:
                self._offset_h_label.value = f"Offset H ({abbr}):"
                self._offset_v_label.value = f"Offset V ({abbr}):"
                try:
                    self._offset_h_label.update()
                    self._offset_v_label.update()
                except Exception:
                    pass
            except Exception:
                pass
            # Actualizar labels de dimensión de código de barras
            try:
                self._lbl_ancho.value = t("Ancho ({0})").format(abbr)
                self._lbl_alto.value = t("Alto ({0})").format(abbr)
                bc_data = (
                    self.interactive_viewer.get_barcode_data(self.selected_position)
                    if self.selected_position
                    else None
                )
                sym = bc_data.get("symbology", "") if bc_data else ""
                self._lbl_tamano.value = t(
                    "Ancho ({0})" if sym == "pdf417" else "Tamaño ({0})"
                ).format(abbr)
                try:
                    self._lbl_ancho.update()
                    self._lbl_alto.update()
                    self._lbl_tamano.update()
                except Exception:
                    pass
            except Exception:
                pass
        except Exception:
            pass

    def _on_vertical_change(self, e):
        """Callback cuando cambia la posición vertical"""
        normalize_decimal_input(e)
        value = e.control.value
        self._update_position_param("vertical", value)

        # Actualizar posición Y en el viewer
        if self.selected_position is not None:
            try:
                # Convertir valor a float
                y_value = float(value)

                # Obtener la posición actual
                current_positions = self._get_current_positions()
                pos_data = current_positions[self.selected_position]
                pos_type = pos_data.get("type", "number")

                # Convertir de la unidad actual (global) a mm (formato interno)
                y_mm = convert_to_mm(y_value, self.current_unit)
                x_mm = pos_data.get("x", 10)

                if pos_type == "barcode":
                    self.interactive_viewer.update_barcode_post_data_visual(
                        self.selected_position, y_mm=y_mm
                    )
                elif pos_type == "variable_text":
                    self.interactive_viewer.update_variable_text_position(
                        self.selected_position, x_mm, y_mm
                    )
                else:
                    self.interactive_viewer.update_numeradora_position(
                        self.selected_position, x_mm, y_mm
                    )

                pos_data["y"] = y_mm

                # Marcar proyecto como modificado
                self._mark_modified()

            except ValueError:
                # Valor inválido, ignorar
                pass

    def _on_horizontal_change(self, e):
        """Callback cuando cambia la posición horizontal"""
        normalize_decimal_input(e)
        value = e.control.value
        self._update_position_param("horizontal", value)

        # Actualizar posición X en el viewer
        if self.selected_position is not None:
            try:
                # Convertir valor a float
                x_value = float(value)

                # Obtener la posición actual
                current_positions = self._get_current_positions()
                pos_data = current_positions[self.selected_position]
                pos_type = pos_data.get("type", "number")

                # Convertir de la unidad actual (global) a mm (formato interno)
                x_mm = convert_to_mm(x_value, self.current_unit)
                y_mm = pos_data.get("y", 10)

                if pos_type == "barcode":
                    self.interactive_viewer.update_barcode_post_data_visual(
                        self.selected_position, x_mm=x_mm
                    )
                elif pos_type == "variable_text":
                    self.interactive_viewer.update_variable_text_position(
                        self.selected_position, x_mm, y_mm
                    )
                else:
                    self.interactive_viewer.update_numeradora_position(
                        self.selected_position, x_mm, y_mm
                    )

                pos_data["x"] = x_mm

                # Marcar proyecto como modificado
                self._mark_modified()

            except ValueError:
                # Valor inválido, ignorar
                pass

    def _on_add_change(self, e):
        """Callback cuando cambia el valor 'añadir' — solo dígitos"""
        # Filtrar pegado: solo [0-9]
        raw = e.control.value or ""
        value_str = "".join(c for c in raw if c.isdigit())
        if value_str != raw:
            e.control.value = value_str
            try:
                e.control.update()
            except Exception:
                pass
        if not value_str:
            # Permitir edición temporal vacía (como start/end)
            self._update_position_param("add", "")
            return

        self._update_position_param("add", value_str)
        value = value_str
        # Sincronizar a 2 caras si comparten text_style (mismo valor en ambas caras)
        try:
            cur_text_style = None
            if self.selected_position is not None:
                cur_pos = self._get_current_positions().get(self.selected_position, {})
                cur_text_style = cur_pos.get("text_style")
            if cur_text_style:
                for face in ("CARA", "DORSO"):
                    for pid, pdata in self.positions.get(face, {}).items():
                        if pid == self.selected_position:
                            continue
                        if pdata.get("type") == "number" and pdata.get("text_style") == cur_text_style:
                            pdata["add"] = value_str
        except Exception:
            pass

        # Actualizar números en visor para todos los sincronizados + seleccionado
        if self.selected_position is not None:
            # Refrescar todas las numeradoras que comparten estilo (ambas caras)
            # — solo la cara visible toca el viewer (ids colisionan)
            try:
                if cur_text_style:
                    real_face = self.current_face
                    for face in ("CARA", "DORSO"):
                        for pid, pdata in self.positions.get(face, {}).items():
                            if pdata.get("type") == "number" and pdata.get("text_style") == cur_text_style:
                                if face != real_face:
                                    continue
                                prev_face = self.current_face
                                try:
                                    self.current_face = face
                                    ns = self._calculate_number_for_numeradora(pid)
                                    self.interactive_viewer.set_number(pid, ns, redraw=False)
                                finally:
                                    self.current_face = prev_face
                    self.interactive_viewer._redraw_all(force=True)
                else:
                    number_str = self._calculate_number_for_numeradora(self.selected_position)
                    self.interactive_viewer.set_number(self.selected_position, number_str)
            except Exception:
                number_str = self._calculate_number_for_numeradora(self.selected_position)
                self.interactive_viewer.set_number(self.selected_position, number_str)

        # Marcar proyecto como modificado
        self._mark_modified()

    def _on_add_blur(self, e):
        """Restaura '0' si el campo queda vacío al perder foco."""
        try:
            val = e.control.value.strip() if e.control.value else ""
            if not val:
                e.control.value = "0"
                try:
                    e.control.update()
                except Exception:
                    pass
                self._update_position_param("add", "0")
                # Sincronizar a 2 caras si comparten text_style
                try:
                    cur_text_style = None
                    if self.selected_position is not None:
                        cur_pos = self._get_current_positions().get(self.selected_position, {})
                        cur_text_style = cur_pos.get("text_style")
                    if cur_text_style:
                        for face in ("CARA", "DORSO"):
                            for pid, pdata in self.positions.get(face, {}).items():
                                if pid == self.selected_position:
                                    continue
                                if pdata.get("type") == "number" and pdata.get("text_style") == cur_text_style:
                                    pdata["add"] = "0"
                except Exception:
                    pass
                if self.selected_position is not None:
                    try:
                        if cur_text_style:
                            real_face = self.current_face
                            for face in ("CARA", "DORSO"):
                                for pid, pdata in self.positions.get(face, {}).items():
                                    if pdata.get("type") == "number" and pdata.get("text_style") == cur_text_style:
                                        if face != real_face:
                                            continue
                                        prev_face = self.current_face
                                        try:
                                            self.current_face = face
                                            ns = self._calculate_number_for_numeradora(pid)
                                            self.interactive_viewer.set_number(pid, ns, redraw=False)
                                        finally:
                                            self.current_face = prev_face
                            self.interactive_viewer._redraw_all(force=True)
                        else:
                            number_str = self._calculate_number_for_numeradora(self.selected_position)
                            self.interactive_viewer.set_number(self.selected_position, number_str)
                    except Exception:
                        number_str = self._calculate_number_for_numeradora(self.selected_position)
                        self.interactive_viewer.set_number(self.selected_position, number_str)
                    self._mark_modified()
        except Exception:
            pass

    def _on_text_style_change(self, style_value):
        """Callback cuando cambia el estilo de texto"""
        print(f"[TEXT_STYLE_CHANGE] Cambio de estilo a: {style_value}")
        self._update_position_param("text_style", style_value)

        # Actualizar estilo de la numeradora seleccionada en el viewer
        if self.selected_position is not None:
            print(
                f"[TEXT_STYLE_CHANGE] Aplicando estilo '{style_value}' a numeradora {self.selected_position}"
            )
            print(
                f"[TEXT_STYLE_CHANGE] Tipo de interactive_viewer: {type(self.interactive_viewer)}"
            )
            print(
                f"[TEXT_STYLE_CHANGE] Tiene update_numeradora_style?: {hasattr(self.interactive_viewer, 'update_numeradora_style')}"
            )
            try:
                self.interactive_viewer.update_numeradora_style(
                    self.selected_position, style_value
                )

                # Marcar proyecto como modificado
                self._mark_modified()
                print(
                    f"[TEXT_STYLE_CHANGE] update_numeradora_style completado sin excepciones"
                )
            except Exception as e:
                print(
                    f"[TEXT_STYLE_CHANGE] ¡ERROR! Excepción al actualizar estilo: {e}"
                )
                import traceback

                traceback.print_exc()

            # Actualizar nombre en la lista
            current_positions = self._get_current_positions()
            if self.selected_position in current_positions:
                item = current_positions[self.selected_position].get("item")
                if item:
                    item.content.controls[1].value = style_value
                    item.update()
                current_positions[self.selected_position]["name"] = style_value

            # Actualizar campo de tamaño de letra con el valor del perfil
            saved = self._num_font_size_field.on_change
            self._num_font_size_field.on_change = None
            fs = 12
            if hasattr(self, "text_style_manager"):
                for p in self.text_style_manager.profiles:
                    if p.name == style_value:
                        fs = p.font_size
                        break
            self._num_font_size_field.value = _fmt_pt(fs)
            self._num_font_size_field.update()
            self._num_font_size_field.on_change = saved

            # Actualizar campo de interletraje con el valor del perfil
            saved_ls = self._num_letter_spacing_field.on_change
            self._num_letter_spacing_field.on_change = None
            ls = 0.0
            if hasattr(self, "text_style_manager"):
                for p in self.text_style_manager.profiles:
                    if p.name == style_value:
                        ls = getattr(p, "letter_spacing", 0.0) or 0.0
                        break
            self._num_letter_spacing_field.value = _fmt_pt(ls)
            self._num_letter_spacing_field.update()
            self._num_letter_spacing_field.on_change = saved_ls
        else:
            print(f"[TEXT_STYLE_CHANGE] No hay numeradora seleccionada")

    def _on_start_change(self, e):
        """Callback cuando cambia el número de inicio (global para ambas caras)"""
        try:
            value_str = e.control.value.strip()
            if not value_str:
                # Permitir edición temporal vacía sin forzar restauración
                return

            value = int(value_str)
            # Actualizar en global_settings (compartido por ambas caras)
            self.global_settings["start"] = value

            # Regla: Fin nunca puede ser menor que Comienzo.
            current_end = self.global_settings.get("end", DEFAULT_END_NUMBER)
            if current_end < value:
                self.global_settings["end"] = value
                self.end_field.value = str(value)
                self.end_field.update()

            self._calculate_total_pages()
            self._update_all_numeradoras()
            # FASE 4: Marcar como modificado
            self._mark_modified()
        except ValueError:
            # Permitir estados intermedios no válidos mientras el usuario escribe
            pass

    def _on_end_change(self, e):
        """Callback cuando cambia el número final (global para ambas caras)"""
        try:
            value_str = e.control.value.strip()
            if not value_str:
                # Permitir edición temporal vacía sin forzar restauración
                return

            value = int(value_str)
            start_value = self.global_settings.get("start", DEFAULT_START_NUMBER)

            # Regla: Fin no puede ser menor que Comienzo.
            if value < start_value:
                # Permitir escritura intermedia (p. ej. start=2001, escribir "3", "30", "300").
                if len(value_str) < len(str(start_value)):
                    return
                value = start_value
                e.control.value = str(value)
                e.control.update()

            # Actualizar en global_settings (compartido por ambas caras)
            self.global_settings["end"] = value
            self._calculate_total_pages()
            self._update_all_numeradoras()
            # FASE 4: Marcar como modificado
            self._mark_modified()
        except ValueError:
            # Permitir estados intermedios no válidos mientras el usuario escribe
            pass

    def _on_increment_change(self, e):
        """Callback cuando cambia el incremento (global para ambas caras)"""
        try:
            value_str = e.control.value.strip()
            if not value_str:
                # Permitir edición temporal vacía sin forzar restauración
                return

            value = int(value_str)
            if value > 0:
                # Actualizar en global_settings (compartido por ambas caras)
                self.global_settings["increment"] = value
                # Sincronizar copias espejo para PDF merge
                self.face_settings["CARA"]["increment"] = value
                self.face_settings["DORSO"]["increment"] = value
                self._calculate_total_pages()
                # Increment global afecta a numeradoras y barcodes con numbering en ambas caras
                # — solo la cara visible toca el viewer (ids colisionan CARA pos6/DORSO pos6)
                real_face = self.current_face
                prev_face = real_face
                for face in ("CARA", "DORSO"):
                    self.current_face = face
                    self._update_all_numeradoras(update_viewer=(face == real_face))
                self.current_face = prev_face
                self.interactive_viewer._redraw_all(force=True)
                # FASE 4: Marcar como modificado
                self._mark_modified()
            else:
                # Si es 0 o negativo, restaurar el valor actual
                e.control.value = str(
                    self.global_settings.get("increment", DEFAULT_INCREMENT)
                )
                e.control.update()
        except ValueError:
            # Si el valor no es válido, restaurar el valor actual
            e.control.value = str(
                self.global_settings.get("increment", DEFAULT_INCREMENT)
            )
            e.control.update()

    def _on_copies_change(self, e):
        """Callback cuando cambia el número de copias (global para ambas caras)"""
        try:
            value_str = e.control.value.strip()
            if not value_str:
                # Permitir edición temporal vacía sin forzar restauración
                return

            value = int(value_str)
            if value > 0:
                # Actualizar en global_settings (compartido por ambas caras)
                self.global_settings["copies"] = value
                self._calculate_total_pages()
                self._update_all_numeradoras()
                # FASE 4: Marcar como modificado
                self._mark_modified()
            else:
                # Si es 0 o negativo, restaurar el valor actual
                e.control.value = str(
                    self.global_settings.get("copies", DEFAULT_COPIES)
                )
                e.control.update()
        except ValueError:
            # Si el valor no es válido, restaurar el valor actual
            e.control.value = str(self.global_settings.get("copies", DEFAULT_COPIES))
            e.control.update()

    def _on_reverse_change(self, e):
        """Callback cuando cambia invertir orden (pertenece a la app, global para ambas caras)"""
        value = e.control.value
        # El padre/autoridad es global_settings; face_settings son copias espejo
        self.global_settings["reverse"] = value
        self.face_settings["CARA"]["reverse"] = value
        self.face_settings["DORSO"]["reverse"] = value
        # reverse global afecta a numeradoras/barcodes/VT con datos Excel en ambas caras
        real_face = self.current_face
        prev_face = real_face
        for face in ("CARA", "DORSO"):
            self.current_face = face
            self._update_all_numeradoras(update_viewer=(face == real_face))
        self.current_face = prev_face
        self.interactive_viewer._redraw_all(force=True)
        # FASE 4: Marcar como modificado
        self._mark_modified()

    def _calculate_total_pages(self):
        """Calcula el total de páginas basado en start, end, increment y copies (global para ambas caras)"""
        try:
            # Obtener valores globales (compartidos por ambas caras)
            start = self.global_settings.get("start", 1)
            end = self.global_settings.get("end", 1)
            increment = self.global_settings.get("increment", 1)
            copies = self.global_settings.get("copies", 1)

            # Validar que increment no sea 0
            if increment == 0:
                increment = 1

            # Calcular cantidad de números en el rango [start, end] con incremento
            numeros_en_rango = ((end - start) // increment) + 1

            # Total de páginas = números en rango * copias
            total = numeros_en_rango * copies

            # Actualizar campo de páginas
            self.pages_field.value = str(total)
            self.pages_field.update()

            # Actualizar texto "de X"
            self.total_pages_text.value = t("de {0}").format(total)
            self.total_pages_text.update()

            # Si la página actual es mayor que el total, volver a la última
            if self.current_page > total:
                self.current_page = max(1, total)
                self.preview_page_field.value = str(self.current_page)
                self.preview_page_field.update()

        except (ValueError, ZeroDivisionError):
            self.pages_field.value = "1"
            self.pages_field.update()
            self.total_pages_text.value = t("de {0}").format(1)
            self.total_pages_text.update()

    def _on_add_position(self, e):
        """
        Agrega una nueva posición (numeración o código de barras)
        según el valor del dropdown de tipo de posición.
        Crea la posición en el viewer y actualiza la lista.
        """
        position_type = (
            self.position_type_dropdown.content.controls[0].data
            if self.position_type_dropdown and self.position_type_dropdown.content
            else "number"
        )

        # Deseleccionar posición actual antes de añadir
        if self.selected_position is not None:
            _cp = self._get_current_positions()
            _old = _cp.get(self.selected_position)
            if _old is not None:
                try:
                    _old["item"].bgcolor = FONDO_TEXTFIELDS_COLOR
                    _old["item"].update()
                except (AssertionError, RuntimeError):
                    pass
                _old_type = _old.get("type")
                if _old_type == "barcode":
                    self.interactive_viewer._update_selection_visual(
                        self.selected_position, "barcode", False
                    )
                elif _old_type == "variable_text":
                    self.interactive_viewer._update_selection_visual(
                        self.selected_position, "variable_text", False
                    )
                elif _old_type == "number":
                    self.interactive_viewer._update_selection_visual(
                        self.selected_position, "number", False
                    )
            self.interactive_viewer.selected_barcode_id = None
            self.interactive_viewer.selected_variable_text_id = None
            self.interactive_viewer.selected_id = None
            self.interactive_viewer._update_fine_adjust_visibility()
            self.selected_position = None
            self._update_position_fields_state()

        # Obtener valores por defecto
        default_data = self._get_default_position_data()

        # Verificar si ya existe una posición en las coordenadas por defecto
        offset_increment = 10  # mm
        x_offset = self.page_width_mm / 2
        y_offset = self.page_height_mm / 2

        position_occupied = True
        while position_occupied:
            position_occupied = False
            current_positions = self._get_current_positions()
            for pid, pos_data in current_positions.items():
                if pos_data.get("x") == x_offset and pos_data.get("y") == y_offset:
                    position_occupied = True
                    x_offset += offset_increment
                    y_offset += offset_increment
                    break

        default_data["x"] = x_offset
        default_data["y"] = y_offset
        default_data["horizontal"] = str(x_offset)
        default_data["vertical"] = str(y_offset)

        position_id = self._get_current_next_position_number()

        if position_type == "barcode":
            profile = self.barcode_ui_manager._find_profile("<Default>")
            if profile is None:
                profiles = self.barcode_ui_manager.profile_manager.get_profiles()
                if profiles:
                    profile = profiles[0]
                else:
                    from ui.barcode_settings_dialog import (
                        BarcodeProfile as _BarcodeProfile,
                    )

                    profile = _BarcodeProfile.create_default()
            position_name = profile.name
            # Resolver valor inicial según página actual
            bc_initial_value = profile.sample_value
            if profile.value_source == "excel" and profile.excel_column:
                phys_page = self.current_page
                ps = self.global_settings.get("start", 1)
                pi = self.global_settings.get("increment", 1)
                pc = self.global_settings.get("copies", 1)
                bc_initial_value = (
                    self.excel_manager.get_value_at(
                        profile.excel_column,
                        ps + ((phys_page - 1) // pc) * pi - 1,
                    )
                    or profile.sample_value
                )
            elif profile.value_source == "numbering":
                n = self._calculate_number_for_numeradora(position_id)
                bc_initial_value = _apply_mask(n, profile.mask)
            elif (
                profile.value_source == "fixed"
                and "<@<" in (profile.sample_value or "")
                and profile.symbology in ("qr", "pdf417", "datamatrix")
                and self.excel_manager.is_loaded
            ):
                # VT personalizado: resolver la plantilla con la fila de la página
                # actual desde el primer render (mismo patrón que variable_text).
                phys_page = self.current_page
                ps = self.global_settings.get("start", 1)
                pi = self.global_settings.get("increment", 1)
                pc = self.global_settings.get("copies", 1)
                row_index = ps + ((phys_page - 1) // pc) * pi - 1
                bc_initial_value = (
                    resolve_vt_text(
                        profile.sample_value,
                        value_source="fixed",
                        excel_column=profile.excel_column or "",
                        excel_manager=self.excel_manager,
                        row_index=row_index,
                    )
                    or profile.sample_value
                )
            bid = self.barcode_ui_manager.add_barcode_position(
                x=x_offset,
                y=y_offset,
                rotation=default_data["rotation"],
                alignment=default_data["alignment"],
                color=profile.color,
                color_cmyk=profile.color_cmyk,
                color_space=profile.color_space,
                color_name=profile.color_name,
                color_tint=profile.color_tint,
                text_color=profile.text_color,
                text_color_cmyk=profile.text_color_cmyk,
                text_color_space=profile.text_color_space,
                text_color_name=profile.text_color_name,
                text_color_tint=profile.text_color_tint,
                value=bc_initial_value,
                barcode_id=position_id,
                auto_select=False,
            )
            resolved_value = bc_initial_value
            extra_data = {
                "type": "barcode",
                "barcode_value": resolved_value,
                "sample_value": profile.sample_value,
                "symbology": profile.symbology,
                "bar_width": (
                    profile.datamatrix_width
                    if _is_datamatrix_family(profile.symbology)
                    else profile.bar_width
                ),
                "bar_height": (
                    profile.datamatrix_height
                    if _is_datamatrix_family(profile.symbology)
                    else profile.bar_height
                ),
                "color": profile.color,
                "color_cmyk": list(profile.color_cmyk),
                "color_space": profile.color_space,
                "color_name": profile.color_name,
                "color_tint": profile.color_tint,
                "text_color": profile.text_color,
                "text_color_cmyk": list(profile.text_color_cmyk),
                "text_color_space": profile.text_color_space,
                "text_color_name": profile.text_color_name,
                "text_color_tint": profile.text_color_tint,
                "profile_name": profile.name,
                "value_source": profile.value_source,
                "error_correction": profile.error_correction,
                "mask": profile.mask,
                "excel_column": profile.excel_column,
                "barcode_font_family": profile.barcode_font_family,
                "barcode_font_size": profile.barcode_font_size,
                "itf14_quiet_zone_mm": profile.itf14_quiet_zone_mm,
                "itf14_bearer_thickness_mm": profile.itf14_bearer_thickness_mm,
                "itf14_bearer_sides": profile.itf14_bearer_sides,
                "itf14_gtin_type": profile.itf14_gtin_type,
                "itf14_printer_type": profile.itf14_printer_type,
                "itf14_hri_gap_mm": profile.itf14_hri_gap_mm,
                "itf14_hri_position": profile.itf14_hri_position,
                "code39_hri_gap_mm": profile.code39_hri_gap_mm,
                "code128_hri_gap_mm": profile.code128_hri_gap_mm,
                "ean5_hri_gap_mm": profile.ean5_hri_gap_mm,
                "datamatrix_width": profile.datamatrix_width,
                "datamatrix_height": profile.datamatrix_height,
                "datamatrix_format": profile.datamatrix_format,
                "datamatrix_hri_gap_mm": profile.datamatrix_hri_gap_mm,
                "datamatrix_hri_position": profile.datamatrix_hri_position,
                "datamatrix_hri_align": getattr(profile, "datamatrix_hri_align", "bottom_center"),
                "datamatrix_hri_line_spacing": getattr(profile, "datamatrix_hri_line_spacing", 1.0),
                "datamatrix_del_open": profile.datamatrix_del_open,
                "datamatrix_del_close": profile.datamatrix_del_close,
                "qr_hri_gap_mm": getattr(profile, "qr_hri_gap_mm", 2.0),
                "qr_hri_position": getattr(profile, "qr_hri_position", "below"),
                "qr_hri_align": getattr(profile, "qr_hri_align", "bottom_center"),
                "qr_hri_line_spacing": getattr(profile, "qr_hri_line_spacing", 1.0),
                "qr_del_open": getattr(profile, "qr_del_open", "") or "",
                "qr_del_close": getattr(profile, "qr_del_close", "|") or "|",
                "pdf417_hri_gap_mm": getattr(profile, "pdf417_hri_gap_mm", 2.0),
                "pdf417_hri_position": getattr(profile, "pdf417_hri_position", "below"),
                "pdf417_hri_align": getattr(profile, "pdf417_hri_align", "bottom_center"),
                "pdf417_hri_line_spacing": getattr(profile, "pdf417_hri_line_spacing", 1.0),
                "pdf417_del_open": getattr(profile, "pdf417_del_open", "") or "",
                "pdf417_del_close": getattr(profile, "pdf417_del_close", "|") or "|",
            }
        elif position_type == "variable_text":
            profile = self.variable_text_ui_manager._find_profile("<Default>")
            if profile is None:
                profiles = self.variable_text_ui_manager.profile_manager.get_profiles()
                profile = (
                    profiles[0] if profiles else VariableTextProfile.create_default()
                )
            position_name = profile.name
            # Resolver marcadores `<@<col>@>` con la fila de la página actual
            # (mismo patrón que _on_variable_text_profile_change y la carga del
            # proyecto): con Excel cargado se resuelven SIEMPRE, para que la
            # posición nueva muestre los datos reales desde el primer render y
            # no las etiquetas hasta pulsar sobre ella.
            vt_initial_text = self._resolve_profile_vt_text(profile)
            vt_id = self.variable_text_ui_manager.add_variable_text_position(
                x=x_offset,
                y=y_offset,
                rotation=default_data["rotation"],
                alignment=default_data["alignment"],
                profile_name=profile.name,
                auto_select=False,
                variable_text_id=position_id,
                text=vt_initial_text,
            )
            extra_data = {
                "type": "variable_text",
                "profile_name": profile.name,
                "font_family": profile.font_family,
                "font_style": profile.font_style,
                "font_size": profile.font_size,
                "text_color": profile.text_color,
                "text_color_cmyk": list(profile.text_color_cmyk),
                "text_color_space": profile.text_color_space,
                "text_color_name": profile.text_color_name,
                "text_color_tint": profile.text_color_tint,
                "value_source": profile.value_source,
                "sample_text": profile.sample_text,
                "excel_column": profile.excel_column,
                "text_case_filter": profile.text_case_filter,
                "resolved_font_path": getattr(profile, "resolved_font_path", None),
                "text_alignment": profile.alignment,
                "line_spacing": profile.line_spacing,
                "letter_spacing": getattr(profile, "letter_spacing", 0.0),
                "anchor": getattr(profile, "anchor", ANCHORS[0]),
                "metricas": getattr(profile, "metricas", None),
            }
        else:
            current_text_style = (
                self.text_style_dropdown.content.controls[0].value
                if self.text_style_dropdown
                else "<Default>"
            )
            position_name = current_text_style
            num_id = self.interactive_viewer.add_numeradora(
                num_id=position_id,
                x=default_data["x"],
                y=default_data["y"],
                alignment=default_data["alignment"],
                text_style_name=current_text_style,
                auto_select=False,
            )
            extra_data = {
                "type": "number",
                "text_style": current_text_style,
            }

        # Función de click para este item específico (doble click abre diálogo)
        def on_item_click(e, item_num_id=position_id):
            import time

            now = time.time()
            if (
                self._last_clicked_item == item_num_id
                and now - self._last_click_item_time < 0.4
            ):
                self._last_clicked_item = None
                self._last_click_item_time = 0.0
                pos_type = (
                    self.positions.get(self.current_face, {})
                    .get(item_num_id, {})
                    .get("type", "number")
                )
                if pos_type == "barcode":
                    self._on_barcode_double_click(item_num_id)
                elif pos_type == "variable_text":
                    self._on_variable_text_double_click(item_num_id)
                else:
                    self._on_numeradora_double_click(item_num_id)
            else:
                self._last_clicked_item = item_num_id
                self._last_click_item_time = now
                self._on_select_position(item_num_id)

        bgcolor_inicial = (
            FONDO_CALCULO_FASE_1
            if self.selected_position is None
            else FONDO_TEXTFIELDS_COLOR
        )

        icon_name = {
            "barcode": ft.CupertinoIcons.BARCODE,
            "variable_text": ft.Icons.TEXT_FIELDS,
        }.get(position_type, ft.Icons.TEXT_FIELDS)

        lock_button = ft.IconButton(
            icon=ft.Icons.LOCK_OPEN,
            icon_size=14,
            icon_color=TEXTOS_FASE_1_COLOR,
            data="lock_toggle",
            on_click=lambda e, pid=position_id: self._toggle_item_lock(pid),
            width=22,
            height=22,
            padding=0,
        )
        _icon_img_path = get_resource_path(os.path.join("assets", "001_2.png"))
        position_item = ft.Container(
            key=f"position_{position_id}",
            content=ft.Row(
                controls=[
                    (
                        ft.Image(
                            src=_icon_img_path,
                            width=14,
                            height=14,
                            fit=ft.BoxFit.CONTAIN,
                            color=TEXTOS_FASE_1_COLOR,
                        )
                        if position_type == "number"
                        else ft.Icon(
                            icon=icon_name,
                            size=14,
                            color=TEXTOS_FASE_1_COLOR,
                        )
                    ),
                    ft.Text(
                        position_name,
                        size=12,
                        color=TEXTOS_FASE_1_COLOR,
                        expand=True,
                    ),
                    lock_button,
                ],
                spacing=6,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            padding=ft.Padding.symmetric(horizontal=8, vertical=4),
            border=ft.Border.only(
                bottom=ft.BorderSide(1, BORDE_TEXTFIELDS_COLOR)
            ),
            bgcolor=bgcolor_inicial,
            on_click=on_item_click,
        )

        position_data = {
            "name": position_name,
            "item": position_item,
            **default_data,
            **extra_data,
        }
        self._set_current_position(position_id, position_data)

        self.positions_list.controls.insert(0, position_item)
        self._increment_current_position_number()
        self.positions_list.update()

        print(f"[DEBUG] Seleccionando automáticamente nueva posición {position_id}")
        self._save_current_ui_to_position(position_id)
        self._on_select_position(position_id)

        if position_type == "number":
            number_str = self._calculate_number_for_numeradora(position_id)
            self.interactive_viewer.set_number(position_id, number_str)
        elif position_type == "barcode" and profile.value_source == "numbering":
            number = self._calculate_number_for_numeradora(position_id)
            masked_value = _apply_mask(number, profile.mask)
            self.interactive_viewer.set_barcode_value(
                position_id, masked_value, redraw=False
            )
            current_positions = self._get_current_positions()
            if position_id in current_positions:
                current_positions[position_id]["barcode_value"] = masked_value
        elif (
            position_type == "barcode"
            and profile.value_source == "excel"
            and profile.excel_column
        ):
            phys_page = self.current_page
            phys_start = self.global_settings.get("start", 1)
            phys_end = self.global_settings.get("end", 125)
            phys_inc = self.global_settings.get("increment", 1)
            phys_copies = self.global_settings.get("copies", 1)
            reverse = self.global_settings.get("reverse", False)
            phys_row = excel_row_index(
                phys_start, phys_end, phys_inc, phys_copies, reverse, phys_page
            )
            first_value = self.excel_manager.get_value_at(
                profile.excel_column, phys_row
            )
            if first_value:
                self.interactive_viewer.set_barcode_value(
                    position_id, first_value, redraw=False
                )
                current_positions = self._get_current_positions()
                if position_id in current_positions:
                    current_positions[position_id]["barcode_value"] = first_value

        self._mark_modified()
        print(f"Posición '{position_name}' creada con ID: {position_id}")
        print(
            f"  Datos main_screen: {self._get_current_positions().get(position_id, {})}"
        )

    def _toggle_item_lock(self, position_id):
        """Alterna el bloqueo/desbloqueo de una posicion en la lista y el viewer."""
        current_positions = self._get_current_positions()
        if position_id not in current_positions:
            return
        pos_data = current_positions[position_id]
        locked = not pos_data.get("locked", False)
        pos_data["locked"] = locked
        if self.interactive_viewer:
            self.interactive_viewer.set_item_locked(position_id, locked)
        item = pos_data.get("item")
        if item and hasattr(item, "content"):
            row = item.content
            for ctrl in row.controls:
                if isinstance(ctrl, ft.IconButton) and ctrl.data == "lock_toggle":
                    ctrl.icon = ft.Icons.LOCK if locked else ft.Icons.LOCK_OPEN
                    break
            item.update()
        self._mark_modified()

    def _on_remove_position(self, e):
        """
        Elimina la posición seleccionada
        Elimina del viewer y de la lista
        """
        if self.selected_position is None:
            print("No hay posición seleccionada")
            return

        num_id = self.selected_position

        current_positions = self._get_current_positions()
        if num_id not in current_positions:
            print(f"Posición {num_id} no encontrada")
            return

        # Obtener datos de la posición
        position_data = current_positions[num_id]
        position_name = position_data["name"]
        position_item = position_data["item"]

        # Eliminar del viewer según el tipo
        pos_type = position_data.get("type", "number")
        if pos_type == "barcode":
            self.interactive_viewer.remove_barcode(num_id)
        elif pos_type == "variable_text":
            self.interactive_viewer.remove_variable_text(num_id)
        else:
            self.interactive_viewer.remove_numeradora(num_id)

        # Eliminar de la lista visual
        self.positions_list.controls.remove(position_item)
        self.positions_list.update()

        # Eliminar del diccionario
        del current_positions[num_id]

        # Limpiar selección
        self.selected_position = None
        self._update_position_fields_state()
        self._toggle_sections_by_type(None)

        # Marcar como modificado
        self._mark_modified()

        print(f"Posición '{position_name}' eliminada")

    def _on_zoom_change(self, e):
        """Maneja el cambio de zoom (en vivo durante arrastre)."""
        new_value = round(float(e.control.value), 2)
        self.zoom_value = new_value

        # Marcar que el usuario está interactuando y aplicar vista rápida
        self._zoom_user_changed = True
        try:
            self.interactive_viewer.set_zoom_live(new_value)
        except Exception:
            # Fallback a la ruta completa si algo falla
            try:
                self.interactive_viewer.set_zoom(new_value)
            except Exception:
                pass

        # Reiniciar temporizador para detectar fin de interacción
        if getattr(self, "_zoom_timer", None):
            try:
                self._zoom_timer.cancel()
            except Exception:
                pass
        self._zoom_timer = threading.Timer(
            0.5, lambda: self._zoom_change_final(new_value)
        )
        self._zoom_timer.daemon = True
        self._zoom_timer.start()

    def _on_zoom_change_end(self, e):
        """Al soltar el slider: redraw completo inmediato (reglas incluidas) sin esperar el timer."""
        # Cancelar el timer pendiente para evitar doble disparo
        if getattr(self, "_zoom_timer", None):
            try:
                self._zoom_timer.cancel()
            except Exception:
                pass
            self._zoom_timer = None
        # Redraw final al instante
        try:
            final_value = round(float(e.control.value), 2)
            self._zoom_change_final(final_value)
        except Exception:
            pass

    def _zoom_change_final(self, final_value=None):
        """Ejecuta la ruta completa de zoom cuando el usuario deja de interactuar."""
        if final_value is None:
            final_value = getattr(self.zoom_slider, "value", DEFAULT_ZOOM)

        # Reset flag y temporizador
        self._zoom_user_changed = False
        self._zoom_timer = None

        # Aplicar el zoom definitivo (ruta completa)
        try:
            self.zoom_value = round(float(final_value), 2)
            self.interactive_viewer.set_zoom(self.zoom_value)
        except Exception:
            pass

    def _zoom_change(self, direction: str):
        """Cambia el zoom multiplicando o dividiendo por ZOOM_STEP

        Args:
            direction: "in" para zoom in (×1.2), "out" para zoom out (÷1.2)
        """
        if direction == "in":
            new_value = min(MAX_ZOOM, self.zoom_value * ZOOM_STEP)
        else:  # "out"
            new_value = max(MIN_ZOOM, self.zoom_value / ZOOM_STEP)

        # Redondear a 2 decimales
        new_value = round(new_value, 2)

        # Cancelar temporizador si hay interacción de usuario en curso
        if getattr(self, "_zoom_timer", None):
            try:
                self._zoom_timer.cancel()
            except Exception:
                pass
            self._zoom_timer = None

        self.zoom_slider.value = new_value
        self.zoom_value = new_value
        # self.zoom_label.value = f"{new_value:.1f}x"
        self.zoom_slider.update()
        # self.zoom_label.update()
        # Aplicar zoom al visor
        self.interactive_viewer.set_zoom(new_value)

    def _reset_view(self):
        """Resetea la posición y zoom a valores originales"""
        # Resetear zoom
        self.zoom_value = DEFAULT_ZOOM
        self.zoom_slider.value = DEFAULT_ZOOM
        # self.zoom_label.value = f"{DEFAULT_ZOOM:.1f}x"
        try:
            # Cancelar temporizador de slider si existe
            if getattr(self, "_zoom_timer", None):
                try:
                    self._zoom_timer.cancel()
                except Exception:
                    pass
                self._zoom_timer = None
            self.zoom_slider.update()
        except AssertionError:
            # El slider no está en la página todavía
            pass
        # self.zoom_label.update()

        # Resetear vista en el interactive_viewer
        self.interactive_viewer.reset_view()

    def _calculate_number_for_numeradora(self, num_id):
        """
        Calcula el número a mostrar para una numeradora según la página actual
        Aplica prefijo, sufijo y máscara

        Fórmula: start + (página_actual - 1) × increment + add

        Args:
            num_id: ID de la numeradora

        Returns:
            String con el número formateado (ej: "N-0001-END")
        """
        current_positions = self._get_current_positions()
        if num_id not in current_positions:
            return "1"

        pos_data = current_positions[num_id]

        # Obtener valores globales (compartidos por ambas caras)
        start = self.global_settings.get("start", 1)
        end = self.global_settings.get("end", 125)
        increment = self.global_settings.get("increment", 1)
        copies = self.global_settings.get("copies", 1)

        # Obtener reverse de la app (global, pertenece al padre no a la cara)
        reverse = self.global_settings.get("reverse", False)

        # Obtener valores individuales de esta posición específica — solo dígitos
        try:
            raw_add = str(pos_data.get("add", "0") or "0")
            add_str = "".join(c for c in raw_add if c.isdigit())
            add = int(add_str) if add_str else 0
        except (ValueError, AttributeError):
            add = 0

        prefix = pos_data.get("prefix", "")
        suffix = pos_data.get("suffix", "")
        mask = pos_data.get("mask", "0000")
        mask_placeholder = pos_data.get("mask_placeholder", "0")

        # Calcular número base considerando copias
        # Si copies=2: páginas 1,2 → número start; páginas 3,4 → número start+increment
        # Fórmula: determinar el índice del ciclo usando división entera
        index_en_ciclo = (self.current_page - 1) // copies

        if reverse:
            # Modo invertido: página 1 muestra el número mayor (end)
            # Calcular cuántos números hay en el rango
            numeros_en_rango = ((end - start) // increment) + 1
            # Invertir el índice
            index_invertido = numeros_en_rango - 1 - index_en_ciclo
            number = start + index_invertido * increment + add
        else:
            # Modo normal: página 1 muestra el número menor (start)
            number = start + index_en_ciclo * increment + add

        print(
            f"[CALC NUM] num_id={num_id}, page={self.current_page}, start={start}, end={end}, inc={increment}, copies={copies}, add={add}, reverse={reverse}"
        )
        print(
            f"[CALC NUM] index_en_ciclo={(self.current_page - 1)}//{copies}={index_en_ciclo}, number={number}"
        )

        # Retornar el número como entero para que el viewer aplique máscara, prefijo y sufijo
        return number

    def _update_all_numeradoras(self, update_viewer: bool = True):
        """
        Actualiza el número mostrado en todas las numeradoras y barcodes
        con numeración interna o datos Excel según la página actual

        update_viewer=False actualiza solo pos_data (cara oculta); evita
        escribir ids colisionados (pos 6 en CARA y DORSO) en el viewer visible
        """
        current_positions = self._get_current_positions()
        # Guard: viewer solo tiene controles de la cara visible; ids compartidos entre CARA/DORSO
        # escriben solo si el id existe en la cara mostrada — pos_data se actualiza siempre
        v_barcodes = self.interactive_viewer.barcodes
        v_nums = self.interactive_viewer.numeradoras
        v_vts = self.interactive_viewer.variable_texts
        for pos_id, pos_data in current_positions.items():
            pos_type = pos_data.get("type", "number")
            if pos_type == "number":
                number_str = self._calculate_number_for_numeradora(pos_id)
                if update_viewer and pos_id in v_nums:
                    self.interactive_viewer.set_number(
                        pos_id, str(number_str), redraw=False
                    )
            elif pos_type == "barcode":
                # Fuente de verdad: perfil (single source of truth), pos_data puede estar stale tras icono main
                profile = None
                try:
                    pn = pos_data.get("profile_name", "<Default>")
                    if hasattr(self, "barcode_ui_manager") and pn:
                        profile = self.barcode_ui_manager._find_profile(pn)
                except Exception:
                    profile = None
                vs = profile.value_source if profile is not None else pos_data.get("value_source", "fixed")
                mask = profile.mask if profile is not None else pos_data.get("mask", "")
                if vs == "numbering":
                    number = self._calculate_number_for_numeradora(pos_id)
                    masked_value = _apply_mask(number, mask)
                    if update_viewer and pos_id in v_barcodes:
                        self.interactive_viewer.set_barcode_value(
                            pos_id, masked_value, redraw=False
                        )
                    # Sincronizar pos_data stale al vuelo (fix proyectos viejos / icono main)
                    if profile is not None:
                        pos_data["value_source"] = profile.value_source
                        pos_data["mask"] = profile.mask
                    pos_data["barcode_value"] = masked_value
                elif vs == "excel":
                    excel_column = profile.excel_column if profile is not None else pos_data.get("excel_column", "")
                    if profile is not None:
                        pos_data["value_source"] = profile.value_source
                        pos_data["excel_column"] = profile.excel_column or ""
                    if excel_column and self.excel_manager.is_loaded:
                        phys_page = self.current_page
                        start = self.global_settings.get("start", 1)
                        end = self.global_settings.get("end", 125)
                        increment = self.global_settings.get("increment", 1)
                        copies = self.global_settings.get("copies", 1)
                        reverse = self.global_settings.get("reverse", False)
                        row_index = excel_row_index(
                            start, end, increment, copies, reverse, phys_page
                        )
                        value = self.excel_manager.get_value_at(excel_column, row_index)
                        if value:
                            if update_viewer and pos_id in v_barcodes:
                                self.interactive_viewer.set_barcode_value(
                                    pos_id, value, redraw=False
                                )
                            pos_data["barcode_value"] = value
                elif vs == "fixed":
                    # VT personalizado: QR/PDF417/DM con plantilla <@<col>@>
                    # Fuente de verdad: pos_data.sample_value (como VT guarda
                    # pos_data.sample_text); el profile es respaldo para proyectos viejos.
                    if profile is not None and profile.sample_value:
                        pos_data["sample_value"] = profile.sample_value
                    tmpl = (pos_data.get("sample_value", "") or "") or (
                        profile.sample_value if profile is not None else ""
                    )
                    symb = (profile.symbology if profile is not None else pos_data.get("symbology", "")) or ""
                    if "<@<" in tmpl and symb in ("qr", "pdf417", "datamatrix") and self.excel_manager.is_loaded:
                        phys_page = self.current_page
                        start = self.global_settings.get("start", 1)
                        end = self.global_settings.get("end", 125)
                        increment = self.global_settings.get("increment", 1)
                        copies = self.global_settings.get("copies", 1)
                        reverse = self.global_settings.get("reverse", False)
                        row_index = excel_row_index(start, end, increment, copies, reverse, phys_page)
                        resolved = resolve_vt_text(
                            tmpl,
                            value_source="fixed",
                            excel_column=pos_data.get("excel_column", "") or "",
                            excel_manager=self.excel_manager,
                            row_index=row_index,
                        )
                        if update_viewer and pos_id in v_barcodes:
                            self.interactive_viewer.set_barcode_value(pos_id, resolved, redraw=False)
                        pos_data["barcode_value"] = resolved
            elif pos_type == "variable_text":
                sample_text = pos_data.get("sample_text", "")
                has_excel = (
                    hasattr(self, "excel_manager")
                    and self.excel_manager
                    and self.excel_manager.is_loaded
                )
                # Re-resolver marcadores `<@<col>@>` con la fila de la página actual
                # (mismo patrón que el texto variable de DataMatrix).
                if has_excel and sample_text:
                    phys_page = self.current_page
                    start = self.global_settings.get("start", 1)
                    end = self.global_settings.get("end", 125)
                    increment = self.global_settings.get("increment", 1)
                    copies = self.global_settings.get("copies", 1)
                    reverse = self.global_settings.get("reverse", False)
                    row_index = excel_row_index(
                        start, end, increment, copies, reverse, phys_page
                    )
                    value = resolve_vt_text(
                        sample_text,
                        value_source=pos_data.get("value_source", "sample"),
                        excel_column=pos_data.get("excel_column", ""),
                        excel_manager=self.excel_manager,
                        row_index=row_index,
                        text_case_filter=pos_data.get("text_case_filter", ""),
                    )
                    if update_viewer and pos_id in v_vts:
                        self.interactive_viewer.set_variable_text_value(
                            pos_id, value, redraw=False
                        )
        if update_viewer:
            self.interactive_viewer._redraw_all(force=True)

    def _on_preview_page_change(self, e):
        """
        Callback cuando el usuario cambia manualmente el número de página
        """
        try:
            page_num = int(e.control.value)

            # Calcular total de páginas usando valores globales (compartidas por ambas caras)
            start = self.global_settings.get("start", 1)
            end = self.global_settings.get("end", 1)
            increment = self.global_settings.get("increment", 1)
            copies = self.global_settings.get("copies", 1)
            if increment == 0:
                increment = 1
            numeros_en_rango = ((end - start) // increment) + 1
            total_pages = numeros_en_rango * copies

            # Validar límites
            if page_num < 1:
                page_num = 1
            elif page_num > total_pages:
                page_num = total_pages

            # Si es diferente a la página actual, navegar
            if page_num != self.current_page:
                self.current_page = page_num
                self.preview_page_field.value = str(self.current_page)
                self.preview_page_field.update()
                self._update_all_numeradoras()
                print(f"[PAGE_FIELD] Navegado a página {self.current_page}")
        except ValueError:
            # ponytail: no restaurar aquí — dejar que el usuario siga escribiendo.
            # La restauración se hace en _on_preview_page_blur al salir del campo.
            pass

    def _on_preview_page_blur(self, e):
        """Valida y restaura el valor al salir del campo (blur)."""
        try:
            val = int(e.control.value) if e.control.value and e.control.value.strip() else self.current_page
            start = self.global_settings.get("start", 1)
            end = self.global_settings.get("end", 1)
            increment = self.global_settings.get("increment", 1)
            copies = self.global_settings.get("copies", 1)
            if increment == 0:
                increment = 1
            total_pages = ((end - start) // increment + 1) * copies
            val = max(1, min(val, total_pages))
        except ValueError:
            val = self.current_page
        if val != self.current_page:
            self.current_page = val
            self._update_all_numeradoras()
        self.preview_page_field.value = str(self.current_page)
        self.preview_page_field.update()

    def _navigate_page(self, direction):
        """
        Navega entre páginas (anterior/siguiente)

        Args:
            direction: -1 para página anterior, 1 para página siguiente
        """
        # Obtener valores globales (compartidos por ambas caras)
        start = self.global_settings.get("start", 1)
        end = self.global_settings.get("end", 1)
        increment = self.global_settings.get("increment", 1)
        copies = self.global_settings.get("copies", 1)

        if increment == 0:
            increment = 1
        numeros_en_rango = ((end - start) // increment) + 1
        total_pages = numeros_en_rango * copies

        print(
            f"[NAVIGATE] direction={direction}, current_page={self.current_page}, total_pages={total_pages}"
        )

        # Calcular nueva página
        new_page = self.current_page + direction

        # Validar límites
        if new_page < 1:
            new_page = 1
        elif new_page > total_pages:
            new_page = total_pages

        # Si no cambió, no hacer nada
        if new_page == self.current_page:
            print(f"[NAVIGATE] No hay cambio, página sigue siendo {self.current_page}")
            return

        # Actualizar página actual
        self.current_page = new_page
        print(f"[NAVIGATE] Nueva página: {self.current_page}")

        # Actualizar campo de página
        self.preview_page_field.value = str(self.current_page)
        self.preview_page_field.update()

        # Actualizar números de todas las numeradoras
        self._update_all_numeradoras()

    def _current_excel_row_index(self) -> int:
        """Fila (0-based) de Excel que corresponde a la página actual (inversa de la fórmula del main)."""
        start = self.global_settings.get("start", 1)
        increment = self.global_settings.get("increment", 1)
        copies = self.global_settings.get("copies", 1)
        return start + ((self.current_page - 1) // copies) * increment - 1

    def _go_to_page(self, page_num):
        """Navega a una página absoluta (con clamp) — usado por el sync fila→página del diálogo."""
        try:
            page_num = int(page_num)
        except (TypeError, ValueError):
            return
        start = self.global_settings.get("start", 1)
        end = self.global_settings.get("end", 1)
        increment = self.global_settings.get("increment", 1)
        copies = self.global_settings.get("copies", 1)
        if increment == 0:
            increment = 1
        numeros_en_rango = ((end - start) // increment) + 1
        total_pages = numeros_en_rango * copies
        page_num = max(1, min(page_num, total_pages))
        if page_num == self.current_page:
            return
        self.current_page = page_num
        self.preview_page_field.value = str(self.current_page)
        try:
            self.preview_page_field.update()
        except Exception:
            pass
        self._update_all_numeradoras()

    def on_page_resize(self, e=None):
        """Callback cuando cambia el tamaño de la ventana"""
        try:
            # Flet 1.0: PageResizeEvent trae width/height explícitos; fallback a page.width/height
            w = getattr(e, "width", None) or self.page.width
            h = getattr(e, "height", None) or self.page.height
            # Recalcular dimensiones del viewer
            new_width = int(w - 350) if w else self.viewer_width
            # page_info (52px) + bottom padding del right_panel (5px) = 57px
            new_height = int(h - 57) if h else self.viewer_height

            # Debounce: durante el drag solo guardamos el tamaño pendiente;
            # al soltar (0.2s sin eventos) se aplica UN solo resize completo.
            self._pending_viewer_size = (new_width, new_height)
            if getattr(self, "_resize_task", None) is None:
                self._resize_task = self.page.run_task(self._apply_resize_debounced)
        except Exception as ex:
            print(f"[ERROR] Error en resize: {ex}")

    async def _apply_resize_debounced(self):
        try:
            await asyncio.sleep(0.2)
            pending = self._pending_viewer_size
            self._pending_viewer_size = None
            if pending:
                new_width, new_height = pending
                if new_width != self.viewer_width or new_height != self.viewer_height:
                    self.viewer_width = new_width
                    self.viewer_height = new_height
                    print(f"[RESIZE] Nuevo tamaño viewer: {new_width}x{new_height}px")
                    self.interactive_viewer.set_viewer_size(new_width, new_height)
        finally:
            self._resize_task = None

    def _on_open_paper_settings(self, e):
        """Abre el diálogo de ajustes de papel"""
        print("[DIALOG] Abriendo diálogo de ajustes de papel...")

        # Usar la unidad global actual
        current_unit = self.current_unit

        # Variable para almacenar el tamaño y orientación seleccionados temporalmente
        temp_width = self.page_width_mm
        temp_height = self.page_height_mm
        temp_orientation = (
            "Vertical" if self.page_width_mm <= self.page_height_mm else "Horizontal"
        )

        # Crear opciones del dropdown: tamaños predefinidos + personalizados + "Gestionar tamaños personalizados"
        page_size_options = list(PAGE_SIZES.keys())

        # Añadir tamaños personalizados si existen (ordenados por área mayor->menor)
        if self.custom_sizes:
            sorted_names = sorted(
                self.custom_sizes.keys(),
                key=lambda n: (self.custom_sizes[n][0] * self.custom_sizes[n][1]),
                reverse=False,
            )
            page_size_options.append("─────────────")
            page_size_options.extend(sorted_names)

        page_size_options.append("─────────────")
        page_size_options.append(t("Gestionar tamaños personalizados..."))

        # Determinar tamaño actual (simplemente usar el que tiene la app)
        current_size = self.page_size_name

        print(f"[DIALOG] Tamaño actual de la app: {self.page_size_name}")
        print(f"[DIALOG] Opciones disponibles: {page_size_options}")
        print(f"[DIALOG] Tamaño a mostrar en dropdown: {current_size}")

        # Orientación: usar dos Checkboxes estilizadas (diseño de la app)
        def set_orientation(new_orientation):
            nonlocal temp_width, temp_height, temp_orientation
            if new_orientation != temp_orientation:
                # Intercambiar ancho y alto si cambia la orientación
                temp_width, temp_height = temp_height, temp_width
                temp_orientation = new_orientation
            vertical_cb.value = temp_orientation == "Vertical"
            horizontal_cb.value = temp_orientation == "Horizontal"
            try:
                vertical_cb.update()
                horizontal_cb.update()
            except Exception:
                pass

        vertical_cb = ft.Checkbox(
            label=t("Vertical"),
            value=(temp_orientation == "Vertical"),
            active_color=BORDE_TEXTFIELDS_COLOR,
            check_color=TEXTOS_FASE_1_COLOR,
            label_style=ft.TextStyle(color=TEXTOS_FASE_1_COLOR, size=14),
            fill_color=FONDO_TEXTFIELDS_COLOR,
            border_side=ft.BorderSide(1, BORDE_TEXTFIELDS_COLOR),
            splash_radius=0,
            on_change=lambda e: set_orientation("Vertical"),
        )

        horizontal_cb = ft.Checkbox(
            label=t("Horizontal"),
            value=(temp_orientation == "Horizontal"),
            active_color=BORDE_TEXTFIELDS_COLOR,
            check_color=TEXTOS_FASE_1_COLOR,
            label_style=ft.TextStyle(color=TEXTOS_FASE_1_COLOR, size=14),
            fill_color=FONDO_TEXTFIELDS_COLOR,
            border_side=ft.BorderSide(1, BORDE_TEXTFIELDS_COLOR),
            splash_radius=0,
            on_change=lambda e: set_orientation("Horizontal"),
        )

        orientation_group = ft.Row([vertical_cb, horizontal_cb], spacing=8)

        # Dropdown de tamaños
        def on_size_change(size_name):
            nonlocal temp_width, temp_height, temp_orientation

            if size_name == "─────────────":
                # Separador, no hacer nada
                return
            elif size_name == t("Gestionar tamaños personalizados..."):
                # Abrir diálogo de gestión de tamaños personalizados
                # Guardar el tamaño actual (antes de la selección) para restaurarlo después
                current_selected = current_size
                # Pasar el callback para aplicar el tamaño seleccionado
                self._open_custom_sizes_dialog(
                    size_dropdown, current_selected, on_size_change
                )
                return
            elif size_name in PAGE_SIZES:
                # Usar el tamaño TAL CUAL está definido
                temp_width, temp_height = PAGE_SIZES[size_name]
            elif size_name in self.custom_sizes:
                # Usar el tamaño TAL CUAL está definido
                temp_width, temp_height = self.custom_sizes[size_name]

            # Actualizar la orientación según el tamaño actual
            temp_orientation = "Vertical" if temp_width <= temp_height else "Horizontal"
            # Actualizar checkboxes que representan la orientación
            try:
                set_orientation(temp_orientation)
            except Exception:
                pass

        size_dropdown = self._create_dropdown_compact(
            page_size_options,
            current_size,
            width=250,
            on_change=on_size_change,
            text_size=14,
        )

        # Campo de sangre (bleed) - convertir de mm a unidad actual
        bleed_converted = convert_from_mm(self.bleed_mm, current_unit)
        if current_unit == UNIT_PX:
            bleed_str = f"{bleed_converted:.1f}"
        else:
            bleed_str = f"{bleed_converted:.4f}"

        def _on_normalize_bleed(e):
            normalize_decimal_input(e)

        bleed_field = self._create_textfield(
            bleed_str,
            width=100,
            text_size=14,
            on_change=_on_normalize_bleed,
        )

        # Botón OK
        def on_ok(e):
            try:
                # Aplicar valores
                self.page_width_mm = temp_width
                self.page_height_mm = temp_height

                # Convertir bleed de la unidad actual a mm
                bleed_value = float(bleed_field.value)
                self.bleed_mm = convert_to_mm(bleed_value, current_unit)

                # Determinar nombre del tamaño
                selected_size = size_dropdown.content.controls[0].value
                if selected_size in PAGE_SIZES or selected_size in self.custom_sizes:
                    self.page_size_name = selected_size
                else:
                    self.page_size_name = t("Personalizado")

                # Actualizar texto de tamaño de página en la UI
                self._update_page_size_text()

                # Actualizar el viewer con el nuevo tamaño
                self.interactive_viewer.set_page_size(
                    self.page_width_mm + (self.bleed_mm * 2),
                    self.page_height_mm + (self.bleed_mm * 2),
                    self.bleed_mm,
                )

                # NO guardar en preferencias aquí - el tamaño de preferencias solo se cambia
                # en el diálogo de preferencias, no al cambiar el tamaño de la página actual

                # Marcar proyecto como modificado
                self._mark_modified()

                # Cerrar diálogo
                try:
                    self.page.pop_dialog()
                except Exception:
                    dialog.open = False
                    self.page.update()

                # Actualizar los gestores de imagen de fondo con el nuevo tamaño
                for manager in self.background_image_managers.values():
                    manager.set_app_page_size(self.page_width_mm, self.page_height_mm)

                print(
                    f"[PAPER] Tamaño aplicado: {self.page_width_mm}x{self.page_height_mm} mm + sangre {self.bleed_mm} mm"
                )
            except ValueError:
                print("[ERROR] Valores inválidos en campos de papel")

        btn_ok = self._create_generic_button(t("Aceptar"), on_ok)

        def on_cancel(e):
            try:
                self.page.pop_dialog()
            except Exception:
                dialog.open = False
                self.page.update()

        btn_cancel = self._create_generic_button(t("Cancelar"), on_cancel)

        # Crear diálogo principal
        dialog = ft.AlertDialog(
            title=ft.Container(
                content=ft.Text(
                    t("Ajustes de papel"),
                    size=20,
                    weight=ft.FontWeight.BOLD,
                    color=TEXTO_COLOR_GENERICO,
                    text_align=ft.TextAlign.CENTER,
                ),
                alignment=ft.Alignment.CENTER,
            ),
            content=ft.Container(
                content=ft.Column(
                    [
                        # Paper Size
                        ft.Row(
                            [
                                ft.Text(
                                    t("Tamaño:"),
                                    size=14,
                                ),
                                size_dropdown,
                            ],
                            alignment=ft.MainAxisAlignment.START,
                        ),
                        ft.Divider(height=1),
                        # Orientation
                        ft.Row(
                            [
                                ft.Text(
                                    t("Orientación:"),
                                    size=14,
                                ),
                                orientation_group,
                            ],
                            alignment=ft.MainAxisAlignment.START,
                            spacing=8,
                        ),
                        ft.Divider(height=1),
                        # Sangre (Bleed) - una sola fila: etiqueta a la izquierda, campo+unidad a la derecha
                        ft.Row(
                            [
                                ft.Text(t("Sangre:"), size=14),
                                bleed_field,
                                ft.Text(t(current_unit), size=14),
                            ],
                            alignment=ft.MainAxisAlignment.START,
                            spacing=8,
                        ),
                    ],
                    spacing=12,
                    tight=True,
                ),
                width=450,
                padding=ft.Padding(10, 10, 10, 20),
            ),
            actions=[
                btn_cancel,
                btn_ok,
            ],
            actions_alignment=ft.MainAxisAlignment.CENTER,
            content_padding=ft.Padding(10, 10, 10, 0),
            actions_padding=ft.Padding(0, 0, 0, 10),
            bgcolor=FONDO_ALERT_DIALOG,
            modal=True,
        )

        # Mostrar diálogo
        try:
            self.page.show_dialog(dialog)
        except Exception:
            # Fallback: método alternativo
            try:
                self.page.dialog = dialog
                self.page.dialog.open = True
                self.page.update()
            except Exception as ex:
                print(f"[ERROR] No se pudo abrir el diálogo: {ex}")

    def _open_custom_sizes_dialog(
        self, size_dropdown=None, previous_selection=None, on_size_change_callback=None
    ):
        """Abre un BottomSheet para gestión de tamaños personalizados

        Args:
            size_dropdown: Referencia al dropdown de tamaños para actualizar después
            previous_selection: El tamaño que estaba seleccionado antes de abrir este dialog
            on_size_change_callback: Callback para aplicar el tamaño seleccionado
        """
        # Usar la unidad global actual
        current_unit = self.current_unit

        # Usar los tamaños personalizados de la instancia

        # Lista de tamaños personalizados
        # Ordenar por área (mayor a menor) y escoger selección inicial
        if self.custom_sizes:
            sorted_names = sorted(
                self.custom_sizes.keys(),
                key=lambda n: (self.custom_sizes[n][0] * self.custom_sizes[n][1]),
                reverse=False,
            )
            # Si se pasó una selección previa y pertenece a los personalizados, usarla; si no, usar el primero del ordenamiento
            if previous_selection and previous_selection in self.custom_sizes:
                initial_selected = previous_selection
            else:
                initial_selected = sorted_names[0]
            selected_custom = [initial_selected]

            # Campos de edición
            name_field = self._create_textfield(
                initial_selected,
                width=200,
                text_size=14,
            )

            # Convertir valores a unidad actual usando el tamaño seleccionado
            width_mm, height_mm = self.custom_sizes[initial_selected]
            width_converted = convert_from_mm(width_mm, current_unit)
            height_converted = convert_from_mm(height_mm, current_unit)
        else:
            # Si no hay tamaños personalizados, crear lista y campos vacíos
            sorted_names = []
            selected_custom = [""]
            name_field = self._create_textfield("", width=200, text_size=14)
            # Valores por defecto (A4)
            width_converted = convert_from_mm(210, current_unit)
            height_converted = convert_from_mm(297, current_unit)

        if current_unit == UNIT_PX:
            width_str = f"{width_converted:.1f}"
            height_str = f"{height_converted:.1f}"
        else:
            width_str = f"{width_converted:.2f}"
            height_str = f"{height_converted:.2f}"

        def _on_normalize_dim(e):
            normalize_decimal_input(e)

        width_field = self._create_textfield(
            width_str,
            width=100,
            text_size=14,
            on_change=_on_normalize_dim,
        )
        height_field = self._create_textfield(
            height_str,
            width=100,
            text_size=14,
            on_change=_on_normalize_dim,
        )

        # Etiqueta de unidad traducida para mostrar en los campos (mostrar "inches" en inglés, etc.)
        if current_unit == UNIT_INCHES:
            display_unit = get_unit_inches()
        elif current_unit == UNIT_PICAS:
            display_unit = get_unit_picas()
        else:
            display_unit = current_unit

        # Lista de tamaños (similar a la lista de numeradoras)
        sizes_list = ft.ListView(
            spacing=0,
            height=240,  # Altura reducida
            expand=False,
        )

        def create_size_item(size_name):
            def on_click(e):
                selected_custom[0] = size_name
                width_mm, height_mm = self.custom_sizes[size_name]
                # Convertir a unidad actual
                width_converted = convert_from_mm(width_mm, current_unit)
                height_converted = convert_from_mm(height_mm, current_unit)

                name_field.value = size_name
                if current_unit == UNIT_PX:
                    width_field.value = f"{width_converted:.1f}"
                    height_field.value = f"{height_converted:.1f}"
                else:
                    width_field.value = f"{width_converted:.2f}"
                    height_field.value = f"{height_converted:.2f}"

                name_field.update()
                width_field.update()
                height_field.update()
                # Actualizar selección visual (selected: dark, others: light)
                for item in sizes_list.controls:
                    item.bgcolor = (
                        FONDO_CALCULO_FASE_1
                        if item.data == size_name
                        else FONDO_TEXTFIELDS_COLOR
                    )
                    item.update()

            return ft.Container(
                content=ft.Text(size_name, size=12, color=TEXTOS_FASE_1_COLOR),
                padding=ft.Padding.symmetric(horizontal=8, vertical=4),
                border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
                border_radius=3,
                bgcolor=(
                    FONDO_CALCULO_FASE_1
                    if size_name == selected_custom[0]
                    else FONDO_TEXTFIELDS_COLOR
                ),
                on_click=on_click,
                data=size_name,
            )

        # Poblar la lista inicial (usar el mismo orden que el dropdown)
        sorted_names = sorted(self.custom_sizes.keys())
        for name in sorted_names:
            sizes_list.controls.append(create_size_item(name))

        # Botón + (añadir nuevo)
        def on_add(e):
            try:
                # Crear nuevo tamaño - convertir de unidad actual a mm
                w_input = float(width_field.value)
                h_input = float(height_field.value)
                w_mm = convert_to_mm(w_input, current_unit)
                h_mm = convert_to_mm(h_input, current_unit)

                # Usar nombre personalizado si existe, sino generar automáticamente en mm
                new_name = (
                    name_field.value.strip()
                    if name_field.value.strip()
                    else f"{w_mm:.0f}x{h_mm:.0f}"
                )

                if new_name not in self.custom_sizes:
                    self.custom_sizes[new_name] = (w_mm, h_mm)
                    # Recalcular orden y reconstruir la lista (mayor->menor por área)
                    sorted_names = sorted(
                        self.custom_sizes.keys(),
                        key=lambda n: (
                            self.custom_sizes[n][0] * self.custom_sizes[n][1]
                        ),
                        reverse=False,
                    )
                    selected_custom[0] = new_name
                    sizes_list.controls = [
                        create_size_item(name) for name in sorted_names
                    ]
                    sizes_list.update()
                    # Actualizar el campo nombre con el nombre usado
                    name_field.value = new_name
                    name_field.update()
                    # Si venimos de un dropdown en el diálogo de papel, actualizarlo inmediatamente
                    if size_dropdown:
                        page_size_options = list(PAGE_SIZES.keys())
                        if self.custom_sizes:
                            # Usar el orden calculado (mayor->menor por área)
                            page_size_options.append("─────────────")
                            page_size_options.extend(sorted_names)
                        page_size_options.append("─────────────")
                        page_size_options.append(
                            t("Gestionar tamaños personalizados...")
                        )

                        # Reconstruir items del PopupMenuButton y actualizar el texto visible
                        dropdown_row = size_dropdown.content
                        texto_control = dropdown_row.controls[0]
                        popup_button = dropdown_row.controls[1]

                        def _make_on_click(opt):
                            def _on_click(e):
                                try:
                                    texto_control.value = opt
                                    texto_control.update()
                                    if on_size_change_callback:
                                        on_size_change_callback(opt)
                                except Exception:
                                    pass

                            return _on_click

                        popup_button.items = [
                            ft.PopupMenuItem(content=opt, on_click=_make_on_click(opt))
                            for opt in page_size_options
                        ]
                        texto_control.value = new_name
                        popup_button.update()
                        size_dropdown.update()
                    print(
                        f"[CUSTOM SIZE] Añadido: {new_name} ({w_mm:.1f}x{h_mm:.1f} mm)"
                    )
                else:
                    print(f"[ERROR] El nombre '{new_name}' ya existe")
            except ValueError:
                print("[ERROR] Valores inválidos en campos de tamaño")

        # Botón duplicar
        def on_duplicate(e):
            if selected_custom[0] and selected_custom[0] in self.custom_sizes:
                w_mm, h_mm = self.custom_sizes[selected_custom[0]]
                # Generar nombre único
                base_name = selected_custom[0]
                counter = 2
                new_name = f"{base_name} (copia)"
                while new_name in self.custom_sizes:
                    new_name = f"{base_name} (copia {counter})"
                    counter += 1

                self.custom_sizes[new_name] = (w_mm, h_mm)
                # Recalcular orden y reconstruir la lista, seleccionando la copia
                sorted_names = sorted(
                    self.custom_sizes.keys(),
                    key=lambda n: (self.custom_sizes[n][0] * self.custom_sizes[n][1]),
                    reverse=False,
                )
                selected_custom[0] = new_name
                sizes_list.controls = [create_size_item(name) for name in sorted_names]
                sizes_list.update()

                # Actualizar campos con el nuevo tamaño duplicado - convertir a unidad actual
                w_converted = convert_from_mm(w_mm, current_unit)
                h_converted = convert_from_mm(h_mm, current_unit)

                name_field.value = new_name
                if current_unit == UNIT_PX:
                    width_field.value = f"{w_converted:.1f}"
                    height_field.value = f"{h_converted:.1f}"
                else:
                    width_field.value = f"{w_converted:.2f}"
                    height_field.value = f"{h_converted:.2f}"

                name_field.update()
                width_field.update()
                height_field.update()
                print(f"[CUSTOM SIZE] Duplicado: {new_name}")

        # Botón - (eliminar)
        def on_remove(e):
            if selected_custom[0] and selected_custom[0] in self.custom_sizes:
                del self.custom_sizes[selected_custom[0]]
                # Recalcular orden y determinar nueva selección
                if self.custom_sizes:
                    sorted_names = sorted(
                        self.custom_sizes.keys(),
                        key=lambda n: (
                            self.custom_sizes[n][0] * self.custom_sizes[n][1]
                        ),
                        reverse=False,
                    )
                    selected_custom[0] = sorted_names[0]
                else:
                    sorted_names = []
                    selected_custom[0] = None

                # Reconstruir lista con la selección ya fijada
                sizes_list.controls = [create_size_item(name) for name in sorted_names]
                sizes_list.update()

                if selected_custom[0]:
                    width_mm, height_mm = self.custom_sizes[selected_custom[0]]
                    # Convertir a unidad actual
                    width_converted = convert_from_mm(width_mm, current_unit)
                    height_converted = convert_from_mm(height_mm, current_unit)

                    name_field.value = selected_custom[0]
                    if current_unit == UNIT_PX:
                        width_field.value = f"{width_converted:.1f}"
                        height_field.value = f"{height_converted:.1f}"
                    else:
                        width_field.value = f"{width_converted:.2f}"
                        height_field.value = f"{height_converted:.2f}"

                    name_field.update()
                    width_field.update()
                    height_field.update()
                else:
                    name_field.value = ""

                    # Valores por defecto A4 - convertir a unidad actual
                    default_w = convert_from_mm(210, current_unit)
                    default_h = convert_from_mm(297, current_unit)

                    if current_unit == UNIT_PX:
                        width_field.value = f"{default_w:.1f}"
                        height_field.value = f"{default_h:.1f}"
                    else:
                        width_field.value = format_unit(210, current_unit)
                        height_field.value = format_unit(297, current_unit)

                    name_field.update()
                    width_field.update()
                    height_field.update()
                print(f"[CUSTOM SIZE] Eliminado")

        btn_add = ft.Container(
            content=ft.Stack(
                [
                    ft.Icon(ft.Icons.ADD, size=16),
                ],
                alignment=ft.Alignment.CENTER,
            ),
            width=30,
            height=24,
            border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
            border_radius=3,
            bgcolor=FONDO_TEXTFIELDS_COLOR,
            on_click=on_add,
        )

        btn_duplicate = ft.Container(
            content=ft.Stack(
                [
                    ft.Icon(ft.Icons.CONTENT_COPY, size=14),
                ],
                alignment=ft.Alignment.CENTER,
            ),
            width=30,
            height=24,
            border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
            border_radius=3,
            bgcolor=FONDO_TEXTFIELDS_COLOR,
            on_click=on_duplicate,
        )

        btn_remove = ft.Container(
            content=ft.Stack(
                [
                    ft.Icon(ft.Icons.REMOVE, size=16),
                ],
                alignment=ft.Alignment.CENTER,
            ),
            width=30,
            height=24,
            border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
            border_radius=3,
            bgcolor=FONDO_TEXTFIELDS_COLOR,
            on_click=on_remove,
        )

        # Botones OK/Cancel
        def on_ok(e):
            # Guardar tamaños personalizados en preferencias
            save_custom_page_sizes(self.custom_sizes)

            # Si hay un dropdown de tamaños (se abrió desde el diálogo de papel)
            if size_dropdown:
                # Reconstruir opciones del dropdown con los tamaños actualizados (ordenados)
                page_size_options = list(PAGE_SIZES.keys())
                if self.custom_sizes:
                    sorted_names = sorted(
                        self.custom_sizes.keys(),
                        key=lambda n: (
                            self.custom_sizes[n][0] * self.custom_sizes[n][1]
                        ),
                        reverse=False,
                    )
                    page_size_options.append("─────────────")
                    page_size_options.extend(sorted_names)
                page_size_options.append("─────────────")
                page_size_options.append(t("Gestionar tamaños personalizados..."))

                # Obtener referencia al dropdown real y reconstruir sus items
                dropdown_row = size_dropdown.content
                texto_control = dropdown_row.controls[0]
                popup_button = dropdown_row.controls[1]

                def _make_on_click(opt):
                    def _on_click(e):
                        try:
                            texto_control.value = opt
                            texto_control.update()
                            if on_size_change_callback:
                                on_size_change_callback(opt)
                        except Exception:
                            pass

                    return _on_click

                popup_button.items = [
                    ft.PopupMenuItem(content=opt, on_click=_make_on_click(opt))
                    for opt in page_size_options
                ]

                # Si hay un tamaño seleccionado en la lista, usarlo
                if selected_custom[0] and selected_custom[0] in self.custom_sizes:
                    texto_control.value = selected_custom[0]
                    print(
                        f"[CUSTOM SIZE] Seleccionando en dropdown: {selected_custom[0]}"
                    )
                    size_dropdown.update()
                    if on_size_change_callback:
                        on_size_change_callback(selected_custom[0])
                elif previous_selection and previous_selection in page_size_options:
                    texto_control.value = previous_selection
                    size_dropdown.update()
                else:
                    texto_control.value = page_size_options[0]
                    size_dropdown.update()

            # Cerrar BottomSheet
            bottom_sheet.open = False
            bottom_sheet.update()

        def on_cancel(e):
            # Restaurar la selección anterior en el dropdown si existe
            if size_dropdown and previous_selection:
                size_dropdown.content.controls[0].value = previous_selection
                size_dropdown.update()

            # Cerrar BottomSheet
            bottom_sheet.open = False
            bottom_sheet.update()

        btn_ok = self._create_generic_button(t("Aceptar"), on_ok)

        btn_cancel = self._create_generic_button(t("Cancelar"), on_cancel)

        # BottomSheet de tamaños personalizados (en lugar de diálogo)
        bottom_sheet = ft.BottomSheet(
            content=ft.Container(
                content=ft.Column(
                    [
                        # Título
                        ft.Container(
                            content=ft.Text(
                                t("Tamaños personalizados"),
                                size=18,
                                weight=ft.FontWeight.BOLD,
                                color=TEXTO_COLOR_GENERICO,
                                text_align=ft.TextAlign.CENTER,
                            ),
                            alignment=ft.Alignment.CENTER,
                        ),
                        ft.Container(height=10),
                        # Contenido
                        ft.Row(
                            [
                                # Columna izquierda: lista de tamaños
                                ft.Column(
                                    [
                                        ft.Container(
                                            content=sizes_list,
                                            width=220,
                                            bgcolor=FONDO_SECCIONES,
                                            border=ft.Border.all(
                                                1, BORDE_TEXTFIELDS_COLOR
                                            ),
                                            border_radius=4,
                                            padding=4,
                                        ),
                                        ft.Row(
                                            [btn_add, btn_duplicate, btn_remove],
                                            spacing=4,
                                            alignment=ft.MainAxisAlignment.START,
                                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                        ),
                                    ],
                                    spacing=8,
                                ),
                                ft.VerticalDivider(width=1),
                                # Columna derecha: campos de edición
                                ft.Column(
                                    [
                                        ft.Text(
                                            t(
                                                "Dejar en blanco para usar el tamaño como nombre."
                                            ),
                                            size=11,
                                            color=TEXTOS_FASE_1_COLOR,
                                            italic=True,
                                        ),
                                        ft.Row(
                                            [
                                                ft.Text(
                                                    t("Nombre:"), size=14, width=60
                                                ),
                                                name_field,
                                            ]
                                        ),
                                        ft.Row(
                                            [
                                                ft.Text(t("Ancho:"), size=14, width=60),
                                                width_field,
                                                ft.Text(
                                                    display_unit,
                                                    size=14,
                                                    color=TEXTOS_FASE_1_COLOR,
                                                ),
                                            ]
                                        ),
                                        ft.Row(
                                            [
                                                ft.Text(t("Alto:"), size=14, width=60),
                                                height_field,
                                                ft.Text(
                                                    display_unit,
                                                    size=14,
                                                    color=TEXTOS_FASE_1_COLOR,
                                                ),
                                            ]
                                        ),
                                    ],
                                    spacing=12,
                                ),
                            ],
                            spacing=20,
                        ),
                        ft.Container(height=10),
                        # Botones
                        ft.Row(
                            [
                                btn_cancel,
                                btn_ok,
                            ],
                            alignment=ft.MainAxisAlignment.CENTER,
                        ),
                    ],
                    spacing=5,
                    tight=True,
                ),
                bgcolor=FONDO_ALERT_DIALOG,
                padding=20,
                width=650,
                margin=ft.Margin.only(bottom=50),
                border_radius=10,
            ),
            open=True,
            dismissible=False,
            bgcolor=FONDO_ALERT_DIALOG,
        )

        # Mostrar BottomSheet
        self.page.overlay.append(bottom_sheet)
        self.page.update()

    def _show_missing_fonts_dialog(self, missing_fonts):
        """Muestra un diálogo modal cuando faltan fuentes del trabajo cargado."""
        if not missing_fonts:
            return

        missing_list_text = "\n".join(f"- {item}" for item in missing_fonts)
        dialog_ref = {"dialog": None}

        def close_dialog(e):
            if dialog_ref["dialog"] is not None:
                self.page.pop_dialog()

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Row(
                [
                    ft.Icon(
                        ft.Icons.WARNING_AMBER_OUTLINED,
                        color=TEXTOS_FASE_1_COLOR,
                        size=24,
                    ),
                    ft.Text(
                        t("Fuentes faltantes en el trabajo"),
                        color=TEXTOS_FASE_1_COLOR,
                    ),
                ],
                spacing=8,
            ),
            content=ft.Column(
                [
                    ft.Text(
                        t(
                            "Este trabajo usa fuentes que no están instaladas en este equipo."
                        ),
                        color=TEXTOS_FASE_1_COLOR,
                    ),
                    ft.Text(t("Fuentes afectadas:"), color=TEXTOS_FASE_1_COLOR),
                    ft.Text(
                        missing_list_text,
                        selectable=True,
                        color=TEXTOS_FASE_1_COLOR,
                    ),
                    ft.Text(
                        t(
                            "Instale estas fuentes y despues abra 'Ajustes de texto' o use otras fuentes."
                        ),
                        color=TEXTOS_FASE_1_COLOR,
                    ),
                ],
                spacing=8,
                tight=True,
            ),
            actions=[
                ft.TextButton(t("Cancelar"), on_click=close_dialog),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            bgcolor=FONDO_ALERT_DIALOG,
        )
        dialog_ref["dialog"] = dialog
        self.page.show_dialog(dialog)

    def _show_font_loading_message(self):
        self._loading_snackbar = ft.SnackBar(
            content=ft.Text(
                t("Cargando tipos de letra..."), color=SNACKBAR_COLOR_TEXTO
            ),
            bgcolor=SNACKBAR_COLOR_FONDO,
            open=True,
            duration=None,
        )
        self.page.overlay.append(self._loading_snackbar)
        self.page.update()

    def _hide_font_loading_message(self):
        if hasattr(self, "_loading_snackbar") and self._loading_snackbar:
            self._loading_snackbar.open = False
            self.page.update()

    def _on_open_text_settings(self, e):
        """Abre el diálogo de ajustes de texto"""
        self._show_font_loading_message()
        # Si hay una numeradora seleccionada, abrir el diálogo con ese estilo
        if self.selected_position is not None:
            numeradora_data = self.interactive_viewer.get_numeradora_data(
                self.selected_position
            )
            if numeradora_data is None:
                self.text_style_manager.open_settings_dialog()
                self._hide_font_loading_message()
                return
            text_style_name = numeradora_data.get("text_style_name", "<Default>")
            print(
                f"[TEXT_SETTINGS] Abriendo con numeradora {self.selected_position}, estilo: {text_style_name}"
            )
            self.text_style_manager.open_settings_dialog(
                numeradora_id=self.selected_position, style_name=text_style_name
            )
        else:
            # Abrir sin numeradora específica
            print(f"[TEXT_SETTINGS] Abriendo sin numeradora seleccionada")
            self.text_style_manager.open_settings_dialog()
        self._hide_font_loading_message()

    # ── Renombrado de perfiles: propagación por nombre ─────────────────────
    # Los perfiles/estilos se referencian por NOMBRE en pos_data y vd; al renombrar
    # desde un diálogo hay que reescribir las referencias en AMBAS caras y refrescar
    # la UI (dropdowns, lista de posiciones, panel de la posición seleccionada).

    def _rebuild_text_style_dropdown(self, preferred_value=None):
        """Reconstruye los items del dropdown compacto de estilos de texto.
        preferred_value fija el valor mostrado; None conserva el valor actual."""
        # El dropdown compacto tiene estructura: Container > Row > [Text, PopupMenuButton]
        row_controls = self.text_style_dropdown.content.controls
        texto_valor = row_controls[0]  # El Text que muestra el valor
        popup_button = row_controls[1]  # El PopupMenuButton con los items
        profile_names = [p.name for p in self.text_style_manager.get_profiles()]

        def on_item_click(e):
            texto_valor.value = e.control.content
            self._on_text_style_change(e.control.content)
            texto_valor.update()

        popup_button.items = [
            ft.PopupMenuItem(
                content=name,
                on_click=on_item_click,
            )
            for name in profile_names
        ]
        new_value = (
            preferred_value if preferred_value is not None else texto_valor.value
        )
        if new_value not in profile_names:
            new_value = profile_names[0] if profile_names else "<Default>"
        texto_valor.value = new_value
        self.text_style_dropdown.update()

    def _rename_position_refs(
        self, face_positions, pos_type, key, old_name, new_name
    ):
        """Reescribe una referencia por nombre en pos_data de una cara y en el
        Text del item correspondiente de la lista de posiciones."""
        for pdata in face_positions.values():
            if pdata.get("type") != pos_type or pdata.get(key) != old_name:
                continue
            pdata[key] = new_name
            if pdata.get("name") == old_name:
                pdata["name"] = new_name
            try:
                txt = pdata["item"].content.controls[1]
                if getattr(txt, "value", None) == old_name:
                    txt.value = new_name
            except (AttributeError, KeyError, IndexError):
                pass

    def _reload_selected_position_panel(self, pos_type):
        """Recarga el panel de campos si la posición seleccionada es de ese tipo."""
        if self.selected_position is None:
            return
        pdata = self._get_current_positions().get(self.selected_position)
        if pdata is not None and pdata.get("type") == pos_type:
            self._load_position_data_to_ui(self.selected_position)

    def _on_vt_profile_renamed(self, old_name, new_name):
        """Perfil VT renombrado en el diálogo: actualizar referencias y UI."""
        for face in ("CARA", "DORSO"):
            self._rename_position_refs(
                self.positions[face],
                "variable_text",
                "profile_name",
                old_name,
                new_name,
            )
        for vt_id in list(self.interactive_viewer.variable_texts.keys()):
            vd = self.interactive_viewer.get_variable_text_data(vt_id)
            if vd is not None and vd.get("profile_name") == old_name:
                vd["profile_name"] = new_name
        self._populate_variable_text_profile_dropdown()
        self._reload_selected_position_panel("variable_text")
        self._mark_modified()

    def _on_barcode_profile_renamed(self, old_name, new_name):
        """Perfil de barcode renombrado en el diálogo: referencias y UI."""
        for face in ("CARA", "DORSO"):
            self._rename_position_refs(
                self.positions[face], "barcode", "profile_name", old_name, new_name
            )
        for bid in list(self.interactive_viewer.barcodes.keys()):
            bd = self.interactive_viewer.get_barcode_data(bid)
            if bd is not None and bd.get("profile_name") == old_name:
                bd["profile_name"] = new_name
        self._populate_barcode_profile_dropdown()
        self._reload_selected_position_panel("barcode")
        self._mark_modified()

    def _on_text_style_renamed(self, old_name, new_name):
        """Estilo de texto (numeración) renombrado en el diálogo: refs y UI."""
        for num_data in self.interactive_viewer.numeradoras.values():
            nd = num_data.get("data")
            if isinstance(nd, dict) and nd.get("text_style_name") == old_name:
                nd["text_style_name"] = new_name
        for face in ("CARA", "DORSO"):
            self._rename_position_refs(
                self.positions[face], "number", "text_style", old_name, new_name
            )
        if self.text_style_dropdown:
            current_display = self.text_style_dropdown.content.controls[0].value
            self._rebuild_text_style_dropdown(
                new_name if current_display == old_name else None
            )
        self._reload_selected_position_panel("number")
        self._mark_modified()

    def _populate_barcode_profile_dropdown(self):
        """Refresca el dropdown de perfiles de código de barras."""
        if not hasattr(self, "barcode_ui_manager") or not self.barcode_ui_manager:
            return
        profiles = self.barcode_ui_manager.profile_manager.get_profiles()
        profile_names = [p.name for p in profiles] or ["<Default>"]

        # Rebuild dropdown items
        dropdown_btn = self._barcode_profile_dropdown.content.controls[1]
        dropdown_btn.items = [
            ft.PopupMenuItem(
                content=name, data=name, on_click=self._on_barcode_profile_click
            )
            for name in profile_names
        ]

    def _on_barcode_profile_click(self, e):
        """Item click handler for barcode profile dropdown."""
        selected_name = e.control.data
        texto_valor = self._barcode_profile_dropdown.content.controls[0]
        texto_valor.value = selected_name
        texto_valor.data = selected_name
        texto_valor.update()
        self._on_barcode_profile_change(selected_name)

    def _on_barcode_profile_change(self, profile_name, _mark=True, _redraw=True):
        """Callback cuando se selecciona un perfil de barcode en el dropdown.
        Carga TODOS los atributos del perfil (tamaño y color) en el viewer y pos_data.
        _mark=False suprime _mark_modified() para llamadas desde _load_position_data_to_ui.
        _redraw=False omite _redraw_all (usar cuando solo se carga UI, no se cambia el perfil).
        """
        if self.selected_position is None or not hasattr(self, "barcode_ui_manager"):
            return

        profile = self.barcode_ui_manager._find_profile(profile_name)
        print(
            f"[PROF_CHANGE] profile_name={profile_name!r} found={profile is not None} id={id(profile) if profile else None} bar_width={profile.bar_width if profile else 'N/A'} bar_height={profile.bar_height if profile else 'N/A'} bf_size={profile.barcode_font_size if profile else 'N/A'}"
        )
        if profile is None:
            return

        self._active_barcode_profile = profile

        # Primero visibilidad, luego valores (los controles deben estar visibles
        # para que Flet renderice correctamente el valor seteado)
        self._update_barcode_dimensions_visibility()

        # Actualizar campos UI con tamaño del perfil (convertir mm → unidad actual)
        print(
            f"[PROF-BW] profile.bar_width={profile.bar_width} symb={profile.symbology}"
        )
        self.bar_width_field.value = self._fmt_mm(profile.bar_width, self.current_unit)
        bh = profile.bar_height
        if profile.symbology == "itf14" and self.selected_position is not None:
            bc_data = self.interactive_viewer.get_barcode_data(self.selected_position)
            printer = (
                bc_data.get("itf14_printer_type", "flexografia")
                if bc_data
                else "flexografia"
            )
            min_h = 32.00 if printer == "flexografia" else 12.70
            bh = max(min_h, bh or 0)
        self.bar_height_field.value = self._fmt_mm(bh, self.current_unit)
        self.bar_width_field.value = self._fmt_mm(profile.bar_width, self.current_unit)
        self.bar_height_field.value = self._fmt_mm(bh, self.current_unit)
        if _is_datamatrix_family(profile.symbology):
            self.bar_width_field.value = self._fmt_mm(
                profile.datamatrix_width, self.current_unit
            )
            self.bar_height_field.value = self._fmt_mm(
                profile.datamatrix_height, self.current_unit
            )
        if profile.symbology == "pdf417":
            self._pdf417_width_field.value = self._fmt_mm(
                profile.pdf417_size, self.current_unit
            )
            self._pdf417_height_field.value = self._fmt_mm(
                profile.pdf417_height, self.current_unit
            )
        else:
            self.qr_size_field.value = self._fmt_mm(
                profile.bar_width, self.current_unit
            )
        self.bar_width_field.update()
        self.bar_height_field.update()
        if profile.symbology == "pdf417":
            self._pdf417_width_field.update()
            self._pdf417_height_field.update()
        else:
            self.qr_size_field.update()
        body_val = (
            profile.barcode_font_size if profile.barcode_font_size is not None else 13.0
        )
        self._itf14_body_field.value = str(body_val)
        if profile.symbology == "code39":
            gap_mm = (
                profile.code39_hri_gap_mm
                if profile.code39_hri_gap_mm is not None
                else 2.0
            )
        else:
            gap_mm = (
                profile.itf14_hri_gap_mm
                if profile.itf14_hri_gap_mm is not None
                else 2.0
            )
        self._itf14_gap_field.value = self._fmt_mm(gap_mm, self.current_unit)
        self._itf14_body_field.update()
        self._itf14_gap_field.update()
        # Also update Code39-specific textfields
        self._code39_body_field.value = str(body_val)
        c39_gap_mm = (
            profile.code39_hri_gap_mm if profile.code39_hri_gap_mm is not None else 2.0
        )
        self._code39_gap_field.value = self._fmt_mm(c39_gap_mm, self.current_unit)
        self._code39_body_field.update()
        self._code39_gap_field.update()
        # Also update Code128-specific textfields
        self._code128_body_field.value = str(body_val)
        c128_gap_mm = (
            profile.code128_hri_gap_mm
            if profile.code128_hri_gap_mm is not None
            else 2.0
        )
        self._code128_gap_field.value = self._fmt_mm(c128_gap_mm, self.current_unit)
        self._code128_body_field.update()
        self._code128_gap_field.update()
        # Also update EAN-5-specific textfields
        self._ean5_body_field.value = str(body_val)
        self._generic_body_field.value = str(body_val)
        self._datamatrix_body_field.value = str(body_val)
        ean5_gap_mm = (
            profile.ean5_hri_gap_mm if profile.ean5_hri_gap_mm is not None else 2.0
        )
        self._ean5_gap_field.value = self._fmt_mm(ean5_gap_mm, self.current_unit)
        self._ean5_body_field.update()
        self._generic_body_field.update()
        self._datamatrix_body_field.update()
        self._ean5_gap_field.update()
        dm_gap_mm = (
            profile.datamatrix_hri_gap_mm
            if profile.datamatrix_hri_gap_mm is not None
            else 2.0
        )
        if profile.symbology == "qr":
            gap_mm = (
                profile.qr_hri_gap_mm if profile.qr_hri_gap_mm is not None else 2.0
            )
        elif profile.symbology == "pdf417":
            gap_mm = (
                profile.pdf417_hri_gap_mm
                if profile.pdf417_hri_gap_mm is not None
                else 2.0
            )
        else:
            gap_mm = dm_gap_mm
        self._datamatrix_gap_field.value = self._fmt_mm(gap_mm, self.current_unit)
        self._datamatrix_gap_field.update()
        # Interlineado — solo QR/DM/PDF417
        if profile.symbology == "qr":
            ls = profile.qr_hri_line_spacing if profile.qr_hri_line_spacing is not None else 1.0
        elif profile.symbology == "pdf417":
            ls = profile.pdf417_hri_line_spacing if profile.pdf417_hri_line_spacing is not None else 1.0
        elif _is_datamatrix_family(profile.symbology):
            ls = profile.datamatrix_hri_line_spacing if profile.datamatrix_hri_line_spacing is not None else 1.0
        else:
            ls = 1.0
        self._datamatrix_hri_line_spacing_field.value = f"{ls:.1f}"
        self._datamatrix_hri_line_spacing_field.update()
        if _is_datamatrix_family(profile.symbology):
            self._update_datamatrix_height_options()

        # Actualizar en el viewer (perfil y valor)
        bc_data = self.interactive_viewer.get_barcode_data(self.selected_position)
        # Resolver valor ANTES de redibujar
        resolved_value = None
        if (
            profile.value_source == "excel"
            and profile.excel_column
            and hasattr(self, "excel_manager")
            and self.excel_manager
            and self.excel_manager.is_loaded
        ):
            phys_page = self.current_page
            phys_start = self.global_settings.get("start", 1)
            phys_end = self.global_settings.get("end", 125)
            phys_inc = self.global_settings.get("increment", 1)
            phys_copies = self.global_settings.get("copies", 1)
            reverse = self.global_settings.get("reverse", False)
            phys_row = excel_row_index(
                phys_start, phys_end, phys_inc, phys_copies, reverse, phys_page
            )
            resolved_value = self.excel_manager.get_value_at(
                profile.excel_column, phys_row
            )
        elif profile.value_source == "numbering":
            number = self._calculate_number_for_numeradora(self.selected_position)
            resolved_value = _apply_mask(number, profile.mask)
        elif profile.value_source == "fixed":
            resolved_value = profile.sample_value
            if (
                "<@<" in (profile.sample_value or "")
                and profile.symbology in ("qr", "pdf417", "datamatrix")
                and hasattr(self, "excel_manager")
                and self.excel_manager
                and self.excel_manager.is_loaded
            ):
                # VT personalizado: resolver la plantilla con la fila de la página actual
                phys_page = self.current_page
                ps = self.global_settings.get("start", 1)
                pi = self.global_settings.get("increment", 1)
                pc = self.global_settings.get("copies", 1)
                phys_row = ps + ((phys_page - 1) // pc) * pi - 1
                resolved_value = (
                    resolve_vt_text(
                        profile.sample_value,
                        value_source="fixed",
                        excel_column=profile.excel_column or "",
                        excel_manager=self.excel_manager,
                        row_index=phys_row,
                    )
                    or profile.sample_value
                )
        if resolved_value:
            self.interactive_viewer.set_barcode_value(
                self.selected_position, resolved_value, redraw=False
            )
        if bc_data is not None:
            bc_data["profile_name"] = profile_name
            bc_data["barcode_font_size"] = profile.barcode_font_size
            if profile.symbology == "qr":
                bc_data["qr_hri_gap_mm"] = profile.qr_hri_gap_mm
                bc_data["qr_hri_line_spacing"] = profile.qr_hri_line_spacing
            elif profile.symbology == "pdf417":
                bc_data["pdf417_hri_gap_mm"] = profile.pdf417_hri_gap_mm
                bc_data["pdf417_hri_line_spacing"] = profile.pdf417_hri_line_spacing
            elif _is_datamatrix_family(profile.symbology):
                bc_data["datamatrix_hri_gap_mm"] = profile.datamatrix_hri_gap_mm
                bc_data["datamatrix_hri_line_spacing"] = profile.datamatrix_hri_line_spacing
            self.interactive_viewer.invalidate_barcode_render_cache(
                self.selected_position
            )

        # Actualizar en pos_data (profile_name + valor + value_source + excel_column para persistencia)
        current_positions = self._get_current_positions()
        if self.selected_position in current_positions:
            current_positions[self.selected_position]["profile_name"] = profile_name
            current_positions[self.selected_position]["value_source"] = profile.value_source
            current_positions[self.selected_position]["excel_column"] = (
                profile.excel_column if profile.value_source == "excel" else None
            )
            current_positions[self.selected_position]["barcode_font_size"] = profile.barcode_font_size
            if profile.symbology == "qr":
                current_positions[self.selected_position]["qr_hri_gap_mm"] = profile.qr_hri_gap_mm
                current_positions[self.selected_position]["qr_hri_line_spacing"] = profile.qr_hri_line_spacing
            elif profile.symbology == "pdf417":
                current_positions[self.selected_position]["pdf417_hri_gap_mm"] = profile.pdf417_hri_gap_mm
                current_positions[self.selected_position]["pdf417_hri_line_spacing"] = profile.pdf417_hri_line_spacing
            elif _is_datamatrix_family(profile.symbology):
                current_positions[self.selected_position]["datamatrix_hri_gap_mm"] = profile.datamatrix_hri_gap_mm
                current_positions[self.selected_position]["datamatrix_hri_line_spacing"] = profile.datamatrix_hri_line_spacing
            if resolved_value:
                current_positions[self.selected_position][
                    "barcode_value"
                ] = resolved_value
            if profile.sample_value is not None:
                current_positions[self.selected_position][
                    "sample_value"
                ] = profile.sample_value
            # Actualizar nombre en la lista
            item = current_positions[self.selected_position].get("item")
            if item:
                item.content.controls[1].value = profile_name
                item.update()
            current_positions[self.selected_position]["name"] = profile_name

        if _redraw:
            try:
                self.interactive_viewer._redraw_all(
                    force=True,
                    only_barcode_ids=[self.selected_position]
                )
            except AssertionError:
                pass

        if _mark:
            self._mark_modified()
        self._update_barcode_dimensions_visibility()

    def _on_barcode_modified(self, profile):
        """Callback cuando un perfil de barcode se modifica en el diálogo."""
        print(f"[DBG MOD] profile={profile.name!r} symb={profile.symbology} qr_gap={profile.qr_hri_gap_mm} dm_gap={profile.datamatrix_hri_gap_mm} pdf_gap={profile.pdf417_hri_gap_mm}")
        self._populate_barcode_profile_dropdown()
        # Fan-out a TODAS las caras/posiciones que usen este perfil, sin gate
        # por selección (fix icono main A vs post_data/C). Viewer solo cara visible (ids colisionan).
        real_face = self.current_face
        for face in ("CARA", "DORSO"):
            face_positions = self.positions.get(face, {})
            for pos_id, pdata in list(face_positions.items()):
                if pdata.get("type") != "barcode" or pdata.get("profile_name") != profile.name:
                    continue
                # Resolver valor por posición (numbering necesita add per-pos vía _calculate)
                new_value = profile.sample_value
                if profile.value_source == "numbering":
                    # Necesita face temporal para calcular bien con global increment
                    prev_face = self.current_face
                    try:
                        self.current_face = face
                        number = self._calculate_number_for_numeradora(pos_id)
                    finally:
                        self.current_face = prev_face
                    new_value = _apply_mask(number, profile.mask)
                elif profile.value_source == "excel" and profile.excel_column:
                    phys_page = self.current_page
                    phys_start = self.global_settings.get("start", 1)
                    phys_end = self.global_settings.get("end", 125)
                    phys_inc = self.global_settings.get("increment", 1)
                    phys_copies = self.global_settings.get("copies", 1)
                    reverse = self.global_settings.get("reverse", False)
                    phys_row = excel_row_index(
                        phys_start, phys_end, phys_inc, phys_copies, reverse, phys_page
                    )
                    first_value = self.excel_manager.get_value_at(
                        profile.excel_column, phys_row
                    )
                    if first_value:
                        new_value = first_value
                elif (
                    profile.value_source == "fixed"
                    and "<@<" in (profile.sample_value or "")
                    and profile.symbology in ("qr", "pdf417", "datamatrix")
                    and self.excel_manager.is_loaded
                ):
                    # VT personalizado: resolver la plantilla con la fila de la página actual
                    # (mismo patrón que la creación :6911 y _update_all_numeradoras).
                    phys_page = self.current_page
                    ps = self.global_settings.get("start", 1)
                    pi = self.global_settings.get("increment", 1)
                    pc = self.global_settings.get("copies", 1)
                    phys_row = ps + ((phys_page - 1) // pc) * pi - 1
                    new_value = (
                        resolve_vt_text(
                            profile.sample_value,
                            value_source="fixed",
                            excel_column=profile.excel_column or "",
                            excel_manager=self.excel_manager,
                            row_index=phys_row,
                        )
                        or profile.sample_value
                    )
                # Viewer solo si es la cara visible (ids colisionan CARA6/DORSO6)
                if face == real_face:
                    bc = self.interactive_viewer.get_barcode_data(pos_id)
                    if bc is not None:
                        bc["profile_name"] = profile.name
                        bc["mask"] = profile.mask
                        self.interactive_viewer.set_barcode_value(
                            pos_id, new_value, redraw=False
                        )
                        self.interactive_viewer.invalidate_barcode_render_cache(pos_id)
                pdata["profile_name"] = profile.name
                pdata["name"] = profile.name
                pdata["barcode_value"] = new_value
                pdata["value_source"] = profile.value_source
                pdata["mask"] = profile.mask
                if profile.sample_value is not None:
                    pdata["sample_value"] = profile.sample_value
                if profile.value_source == "excel" and profile.excel_column:
                    pdata["excel_column"] = profile.excel_column
                else:
                    pdata.pop("excel_column", None)
                if self.selected_position == pos_id:
                    item = pdata.get("item")
                    if item:
                        try:
                            item.content.controls[1].value = profile.name
                            item.update()
                        except Exception:
                            pass
        if self.selected_position is not None:
            current_positions = self._get_current_positions()
            pos_data = current_positions.get(self.selected_position)
            if pos_data and pos_data.get("type") == "barcode":
                self._load_position_data_to_ui(self.selected_position)
                if _is_datamatrix_family(profile.symbology):
                    self._update_datamatrix_height_options()
        self.interactive_viewer._redraw_all(force=True)
        self._mark_modified()

    def _on_barcode_double_click(self, barcode_id: int):
        """Abre diálogo de barcode al hacer doble clic con el perfil de ese barcode"""
        print(f"[BARCODE] Doble clic en barcode {barcode_id}")
        # Flush focused PDF417 field to profile before reading pos_data for dialog
        if self._pdf417_focused_field is not None:
            self._on_pdf417_field_enter(self._pdf417_focused_field)
        current_positions = self._get_current_positions()
        pos_data = current_positions.get(barcode_id, {})
        profile_name = pos_data.get("profile_name", "<Default>")
        # Seleccionar la posición antes de abrir el diálogo para que los cambios se apliquen correctamente
        if self.selected_position != barcode_id:
            self._on_select_position(barcode_id)
        self.barcode_ui_manager.open_barcode_dialog(
            profile_name=profile_name,
            position_data=pos_data,
            initial_row=self._current_excel_row_index(),
        )

    def _on_variable_text_double_click(self, vt_id: int):
        """Abre diálogo de texto variable al hacer doble clic con el perfil de ese texto"""
        print(f"[VAR_TEXT] Doble clic en texto variable {vt_id}")

        self._show_font_loading_message()
        current_positions = self._get_current_positions()
        pos_data = current_positions.get(vt_id, {})
        profile_name = pos_data.get("profile_name", "<Default>")
        if self.selected_position != vt_id:
            self._on_select_position(vt_id)
        self.variable_text_ui_manager.open_variable_text_dialog(
            profile_name=profile_name,
            position_data=pos_data,
            target_vt_id=vt_id,
            initial_row=self._current_excel_row_index(),
        )
        self._hide_font_loading_message()

    def _on_vt_profile_changed(self, profile, target_vt_id=None):
        """Callback cuando un perfil de texto variable se modifica en el diálogo."""
        self._populate_variable_text_profile_dropdown()
        current_positions = self._get_current_positions()
        updated_vt_ids = []

        def _resolve_vt_text() -> str:
            return self._resolve_profile_vt_text(profile)

        selected_vt_id = (
            target_vt_id if isinstance(target_vt_id, int) else self.selected_position
        )

        for vt_id, pos_data in current_positions.items():
            if pos_data.get("type") != "variable_text":
                continue
            matches_profile = pos_data.get("profile_name", "<Default>") == profile.name
            is_selected_vt = selected_vt_id is not None and vt_id == selected_vt_id
            if not matches_profile and not is_selected_vt:
                continue

            resolved_text = _resolve_vt_text()

            vt_data = self.interactive_viewer.get_variable_text_data(vt_id)
            if vt_data is not None:
                vt_data["text"] = resolved_text
                vt_data["profile_name"] = profile.name
                vt_data["text_alignment"] = profile.alignment

            pos_data.update(
                {
                    "profile_name": profile.name,
                    "name": profile.name,
                    "text": resolved_text,
                    "sample_text": profile.sample_text,
                    "font_family": profile.font_family,
                    "font_style": profile.font_style,
                    "font_size": profile.font_size,
                    "text_color": profile.text_color,
                    "text_color_cmyk": list(profile.text_color_cmyk),
                    "text_color_space": profile.text_color_space,
                    "text_color_name": profile.text_color_name,
                    "text_color_tint": profile.text_color_tint,
                    "value_source": profile.value_source,
                    "excel_column": profile.excel_column,
                    "text_case_filter": profile.text_case_filter,
                    "resolved_font_path": getattr(profile, "resolved_font_path", None),
                    "text_alignment": profile.alignment,
                    "line_spacing": profile.line_spacing,
                    "letter_spacing": getattr(profile, "letter_spacing", 0.0),
                    "metricas": getattr(profile, "metricas", None),
                }
            )

            item = pos_data.get("item")
            if item:
                try:
                    item.content.controls[1].value = profile.name
                except Exception:
                    pass

            updated_vt_ids.append(vt_id)

        if updated_vt_ids:
            self.interactive_viewer._redraw_all(force=True)
            try:
                self.positions_list.update()
            except AssertionError:
                # Puede ocurrir durante transiciones de diálogo en Flet cuando el control aún no está montado.
                pass
        self._mark_modified()
        # Sincronizar dropdown y campo de tamaño con el perfil modificado
        current_name = self._variable_text_profile_dropdown.content.controls[0]
        current_name.value = profile.name
        current_name.data = profile.name
        try:
            self._variable_text_profile_dropdown.update()
        except AssertionError:
            pass
        saved = self._vt_font_size_field.on_change
        self._vt_font_size_field.on_change = None
        self._vt_font_size_field.value = str(profile.font_size)
        try:
            self._vt_font_size_field.update()
        except AssertionError:
            pass
        self._vt_font_size_field.on_change = saved

        # Refrescar el resto de campos VT de la UI (dropdown Posición 9 anclas,
        # Interlineado, Alineación) con los datos del perfil aplicado.
        if self.selected_position is not None:
            sel_pos = self._get_current_positions().get(self.selected_position, {})
            if sel_pos.get("type") == "variable_text":
                try:
                    self._load_position_data_to_ui(self.selected_position)
                except Exception:
                    pass

    def _on_variable_text_profile_change(self, profile_name):
        """Callback cuando se selecciona un perfil de texto variable en el dropdown."""
        if self.selected_position is None or not hasattr(
            self, "variable_text_ui_manager"
        ):
            return
        profile = self.variable_text_ui_manager._find_profile(profile_name)
        if profile is None:
            return
        vt_data = self.interactive_viewer.get_variable_text_data(self.selected_position)
        if vt_data is not None:
            vt_data["text"] = self._resolve_profile_vt_text(profile)
            vt_data["profile_name"] = profile_name
            vt_data["text_alignment"] = profile.alignment
            self.interactive_viewer._redraw_all()
        current_positions = self._get_current_positions()
        if self.selected_position in current_positions:
            text_val = self._resolve_profile_vt_text(profile)
            current_positions[self.selected_position].update(
                {
                    "profile_name": profile_name,
                    "text": text_val,
                    "sample_text": profile.sample_text,
                    "font_family": profile.font_family,
                    "font_style": profile.font_style,
                    "font_size": profile.font_size,
                    "text_color": profile.text_color,
                    "text_color_cmyk": list(profile.text_color_cmyk),
                    "text_color_space": profile.text_color_space,
                    "text_color_name": profile.text_color_name,
                    "text_color_tint": profile.text_color_tint,
                    "value_source": getattr(profile, "value_source", "sample"),
                    "excel_column": getattr(profile, "excel_column", ""),
                    "text_case_filter": getattr(profile, "text_case_filter", ""),
                    "resolved_font_path": getattr(profile, "resolved_font_path", None),
                    "text_alignment": profile.alignment,
                    "line_spacing": getattr(profile, "line_spacing", 14.4),
                    "letter_spacing": getattr(profile, "letter_spacing", 0.0),
                    "metricas": getattr(profile, "metricas", None),
                }
            )
            # Actualizar nombre en la lista
            item = current_positions[self.selected_position].get("item")
            if item:
                try:
                    item.content.controls[1].value = profile_name
                    item.update()
                except AssertionError:
                    pass
            current_positions[self.selected_position]["name"] = profile_name
        self._mark_modified()
        # Sincronizar campo de tamaño de letra con el perfil
        saved = self._vt_font_size_field.on_change
        self._vt_font_size_field.on_change = None
        self._vt_font_size_field.value = str(profile.font_size)
        try:
            self._vt_font_size_field.update()
        except AssertionError:
            pass
        self._vt_font_size_field.on_change = saved

        # Sincronizar interlineado (modo auto) y alineación con el perfil
        self._vt_line_spacing_field.value = _fmt_pt(
            getattr(profile, "line_spacing", LINE_SPACING_AUTO * profile.font_size)
        )
        self._vt_line_spacing_auto = True
        self._vt_letter_spacing_field.value = _fmt_pt(
            getattr(profile, "letter_spacing", 0.0)
        )
        try:
            self._vt_line_spacing_field.update()
        except AssertionError:
            pass
        try:
            self._vt_letter_spacing_field.update()
        except AssertionError:
            pass
        try:
            self._vt_text_alignment_dropdown.update()
        except AssertionError:
            pass
        self._set_dropdown_value(
            self._vt_text_alignment_dropdown,
            get_alignments(),
            profile.alignment,
        )
        # Ancla del dropdown compartido: la posición manda (post_data), no el perfil.
        sel_anchor = (
            self._get_current_positions()
            .get(self.selected_position, {})
            .get("anchor", DEFAULT_ANCHOR)
        )
        self._set_alignment_dropdown_options(get_anchor_options(), sel_anchor)

    def _populate_variable_text_profile_dropdown(self):
        """Refresca el dropdown de perfiles de texto variable."""
        if (
            not hasattr(self, "variable_text_ui_manager")
            or not self.variable_text_ui_manager
        ):
            return
        profiles = self.variable_text_ui_manager.profile_manager.get_profiles()
        profile_names = [p.name for p in profiles] or ["<Default>"]
        dropdown_btn = self._variable_text_profile_dropdown.content.controls[1]
        dropdown_btn.items = [
            ft.PopupMenuItem(
                content=name, data=name, on_click=self._on_variable_text_profile_click
            )
            for name in profile_names
        ]

    def _on_variable_text_profile_click(self, e):
        """Item click handler for variable text profile dropdown."""
        selected_name = e.control.data
        texto_valor = self._variable_text_profile_dropdown.content.controls[0]
        texto_valor.value = selected_name
        texto_valor.data = selected_name
        texto_valor.update()
        self._on_variable_text_profile_change(selected_name)

    def _on_open_excel(self, e):
        """Abre selector de archivo Excel"""
        self.barcode_ui_manager.open_excel_dialog(
            vt_profile_manager=self.variable_text_ui_manager.profile_manager
        )

    def _on_open_barcode_settings(self, e):
        """Abre diálogo de configuración de barcodes con el perfil seleccionado si hay"""
        # Flush focused PDF417 field to profile before reading pos_data for dialog
        if self._pdf417_focused_field is not None:
            self._on_pdf417_field_enter(self._pdf417_focused_field)
        profile_name = "<Default>"
        pos_data = {}
        if self.selected_position is not None:
            current_positions = self._get_current_positions()
            pos_data = current_positions.get(self.selected_position, {})
            if pos_data.get("type") == "barcode":
                profile_name = pos_data.get("profile_name", "<Default>")
        self.barcode_ui_manager.open_barcode_dialog(
            profile_name=profile_name,
            position_data=pos_data,
            initial_row=self._current_excel_row_index(),
        )

    def _on_open_variable_text_settings(self, e):
        """Abre diálogo de configuración de textos variables"""
        self._show_font_loading_message()
        profile_name = "<Default>"
        pos_data = {}
        if self.selected_position is not None:
            current_positions = self._get_current_positions()
            pos_data = current_positions.get(self.selected_position, {})
            if pos_data.get("type") == "variable_text":
                profile_name = pos_data.get("profile_name", "<Default>")
        self.variable_text_ui_manager.open_variable_text_dialog(
            profile_name=profile_name,
            position_data=pos_data,
            target_vt_id=(
                self.selected_position
                if pos_data.get("type") == "variable_text"
                else None
            ),
            initial_row=self._current_excel_row_index(),
        )
        self._hide_font_loading_message()

    def _on_numeradora_double_click(self, num_id: int):
        """Callback cuando se hace doble clic en una numeradora"""
        print(f"[DIALOG] Doble clic en numeradora {num_id} - abriendo diálogo de texto")

        self._show_font_loading_message()
        # Obtener datos de la numeradora del viewer
        numeradora_data = self.interactive_viewer.get_numeradora_data(num_id)
        text_style_name = numeradora_data.get("text_style_name", "<Default>")

        # Abrir el diálogo y cargar el estilo de esta numeradora
        self.text_style_manager.open_settings_dialog(
            numeradora_id=num_id, style_name=text_style_name
        )
        self._hide_font_loading_message()

    def _initialize_text_style_dropdown(self):
        """Inicializa el dropdown de estilos de texto con los perfiles disponibles"""
        profiles = self.text_style_manager.get_profiles()
        profile_names = [p.name for p in profiles]

        if self.text_style_dropdown:
            self.text_style_dropdown.content.controls[0].options = [
                ft.dropdown.Option(name) for name in profile_names
            ]
            # Establecer el primer perfil como seleccionado
            self.text_style_dropdown.content.controls[0].value = (
                profile_names[0] if profile_names else "<Default>"
            )
            # No llamar update() aquí - el control aún no está en la página
            print(
                f"[TEXT_STYLE] Dropdown inicializado con {len(profile_names)} perfiles: {profile_names}"
            )

    def _on_text_style_updated(
        self, style: TextStyle, numeradora_id: Optional[int] = None
    ):
        """Callback cuando se actualiza un estilo de texto"""
        try:
            family = getattr(style, "font_family", "Unknown")
            fontstyle = getattr(style, "font_style", "Regular")
        except Exception:
            family = "Unknown"
            fontstyle = "Regular"
        print(
            f"[TEXT_STYLE] _on_text_style_updated llamado: style={style.name} ({family} {fontstyle}), numeradora_id={numeradora_id}"
        )

        # Actualizar el dropdown con los perfiles disponibles
        profiles = self.text_style_manager.get_profiles()
        profile_names = [p.name for p in profiles]

        print(f"[TEXT_STYLE] Perfiles disponibles: {profile_names}")

        # Si el estilo no está en la lista de perfiles, significa que fue eliminado
        # Actualizar todas las numeradoras que lo usan a "<Default>"
        if style.name not in profile_names:
            print(
                f"[TEXT_STYLE] Estilo '{style.name}' eliminado, actualizando numeradoras a <Default>"
            )
            for num_id in list(self.interactive_viewer.numeradoras.keys()):
                num_data = self.interactive_viewer.numeradoras[num_id]
                if num_data["data"].get("text_style_name") == style.name:
                    print(
                        f"[TEXT_STYLE] Numeradora {num_id} usaba '{style.name}', cambiando a <Default>"
                    )
                    self.interactive_viewer.update_numeradora_style(num_id, "<Default>")

        # Actualizar opciones del dropdown compacto
        if self.text_style_dropdown:
            self._rebuild_text_style_dropdown(style.name)

        # Sincronizar campos del panel (tamaño e interletraje) con el perfil
        if self.selected_position is not None:
            positions = self._get_current_positions()
            if self.selected_position in positions:
                pos_type = positions[self.selected_position].get("type")
                if pos_type == "number":
                    saved_fs = self._num_font_size_field.on_change
                    self._num_font_size_field.on_change = None
                    self._num_font_size_field.value = _fmt_pt(getattr(style, "font_size", 12))
                    self._num_font_size_field.update()
                    self._num_font_size_field.on_change = saved_fs
                    saved_ls = self._num_letter_spacing_field.on_change
                    self._num_letter_spacing_field.on_change = None
                    self._num_letter_spacing_field.value = _fmt_pt(getattr(style, "letter_spacing", 0.0) or 0.0)
                    self._num_letter_spacing_field.update()
                    self._num_letter_spacing_field.on_change = saved_ls

        # Si se está editando una numeradora específica, actualizar su estilo
        if numeradora_id is not None:
            # Actualizar el text_style_name de la numeradora en el viewer
            self.interactive_viewer.update_numeradora_style(numeradora_id, style.name)
            print(
                f"[TEXT_STYLE] Numeradora {numeradora_id} actualizada con estilo '{style.name}'"
            )

            # También actualizar la posición en los datos del proyecto (usado por el generador de PDF)
            try:
                pos = self._get_current_position(numeradora_id)
                if pos:
                    pos["text_style"] = style.name
                    pos["name"] = style.name
                    self._set_current_position(numeradora_id, pos)
                    print(
                        f"[TEXT_STYLE] Guardado estilo '{style.name}' en posición {numeradora_id}"
                    )

                    item = pos.get("item")
                    if item:
                        item.content.controls[1].value = style.name
                        item.update()
            except Exception as e:
                print(
                    f"[TEXT_STYLE] Error guardando estilo en posición {numeradora_id}: {e}"
                )

        # Actualizar visualización del texto en el viewer
        if hasattr(self, "interactive_viewer") and self.interactive_viewer:
            self.interactive_viewer._redraw_all()

        # FASE 4: Marcar como modificado
        self._mark_modified()

        try:
            family = getattr(style, "font_family", "Unknown")
            fontstyle = getattr(style, "font_style", "Regular")
        except Exception:
            family = "Unknown"
            fontstyle = "Regular"
        print(
            f"[TEXT_STYLE] Estilo actualizado: {style.name} ({family} {fontstyle}), visor redibujado"
        )

    def _on_open_image_settings(self, e):
        """Abre el diálogo de ajustes de imagen de fondo"""
        print("[DIALOG] Abriendo diálogo de ajustes de imagen...")

        current_manager = self._get_current_background_image_manager()
        if current_manager.image_loaded:
            current_manager.open_positioning_dialog()
        else:
            # Mostrar mensaje o simplemente no hacer nada
            print("[INFO] No hay imagen de fondo cargada")

    def _update_image_settings_button_state(self, do_update=True):
        """Actualiza el estado de los botones de imagen según si hay imagen cargada en la cara actual"""
        current_manager = self._get_current_background_image_manager()
        has_image = current_manager.image_loaded

        # Actualizar botón de ajustes de imagen
        self.icon_image_settings.disabled = not has_image
        if has_image:
            self.icon_image_settings.bgcolor = BOTONES_GENERICOS_OVERLAY_COLOR
            self.icon_image_settings.content.color = BOTONES_GENERICOS_TEXTO_COLOR
        else:
            self.icon_image_settings.bgcolor = FONDO_TEXTFIELDS_COLOR
            self.icon_image_settings.content.color = TEXTOS_FASE_1_COLOR

        # Actualizar botón de eliminar imagen
        self.icon_remove_background.disabled = not has_image
        if has_image:
            self.icon_remove_background.bgcolor = BOTONES_GENERICOS_OVERLAY_COLOR
            self.icon_remove_background.content.color = BOTONES_GENERICOS_TEXTO_COLOR
        else:
            self.icon_remove_background.bgcolor = FONDO_TEXTFIELDS_COLOR
            self.icon_remove_background.content.color = TEXTOS_FASE_1_COLOR

        if do_update:
            self.icon_image_settings.update()
            self.icon_remove_background.update()

    async def _on_load_background(self, e):
        """Abre el diálogo para cargar imagen de fondo"""
        print("[DIALOG] Abriendo diálogo para cargar imagen de fondo...")
        current_manager = self._get_current_background_image_manager()
        await current_manager.open_file_picker()

    def _on_remove_background(self, e):
        """Elimina la imagen de fondo de la cara actual"""
        print(f"[IMAGE] Eliminando imagen de fondo de {self.current_face}")
        current_manager = self._get_current_background_image_manager()

        # Limpiar imagen del manager
        current_manager.clear_image()

        # Sincronizar (esto actualizará viewer, botones y borrará caché física)
        self._on_background_image_change()

        print(f"[IMAGE] Imagen de fondo eliminada de {self.current_face}")

    def _on_exit_app(self, e):
        """Maneja el botón de salir - verifica si hay cambios antes de cerrar"""
        print("[EXIT] Usuario presionó botón Salir")

        # Verificar REALMENTE comparando snapshots
        self._verify_modification_state()

        if self.project_modified:
            # Hay cambios sin guardar, mostrar diálogo
            print("[EXIT] Hay cambios sin guardar, mostrando diálogo")
            self._show_unsaved_changes_dialog()
        else:
            # Sin cambios, salir directamente
            print("[EXIT] Sin cambios, cerrando aplicación")
            # Eliminar archivo de previsualización temporal si existe
            try:
                if hasattr(self, "_preview_temp_path") and os.path.exists(
                    self._preview_temp_path
                ):
                    os.remove(self._preview_temp_path)
            except Exception:
                pass
            self._close_app_con_dialogo()

    def _close_app_con_dialogo(self):
        """Muestra el aviso final, limpia temporales y cierra la aplicación."""
        if getattr(self, "_closing_in_progress", False):
            return
        self._closing_in_progress = True

        try:
            mostrar_dialogo_cierre(self.page, t)
        except Exception:
            pass

        def _cancelar_watchdog_cierre():
            try:
                if self._close_watchdog_timer is not None:
                    self._close_watchdog_timer.cancel()
            except Exception:
                pass
            self._close_watchdog_timer = None

        def _activar_watchdog_cierre_windows(timeout_seg=2.0):
            if not sys.platform.startswith("win"):
                return

            def _forzar_salida_por_timeout():
                try:
                    print(
                        "[WINDOW CLOSE] Timeout de cierre agotado, forzando salida del proceso en Windows"
                    )
                except Exception:
                    pass
                try:
                    os._exit(0)
                except Exception:
                    pass

            _cancelar_watchdog_cierre()
            try:
                timer = threading.Timer(timeout_seg, _forzar_salida_por_timeout)
                timer.daemon = True
                self._close_watchdog_timer = timer
                timer.start()
            except Exception:
                pass

        async def _finalizar_cierre_async():
            try:
                # Ocultar primero la ventana reduce la percepción de bloqueo al cerrar.
                self.page.window.visible = False
                self.page.update()
            except Exception:
                pass

            _activar_watchdog_cierre_windows(timeout_seg=2.0)

            try:
                # Ceder un ciclo al loop para que Flet procese el último update.
                await asyncio.sleep(0.05)
            except Exception:
                pass

            try:
                if hasattr(self, "_preview_temp_path") and os.path.exists(
                    self._preview_temp_path
                ):
                    os.remove(self._preview_temp_path)
            except Exception:
                pass

            # Cancelar timer de zoom si estaba pendiente para no retener el cierre.
            try:
                if getattr(self, "_zoom_timer", None):
                    self._zoom_timer.cancel()
                    self._zoom_timer = None
            except Exception:
                pass

            try:
                # Flet 1.0: window.destroy() es async -> hay que esperarlo para que el cierre se ejecute
                await self.page.window.destroy()
            except Exception:
                pass
            finally:
                _cancelar_watchdog_cierre()

        try:
            self.page.run_task(_finalizar_cierre_async)
        except Exception:
            # Fallback defensivo si run_task no está disponible.
            def _fallback_cierre():
                _activar_watchdog_cierre_windows(timeout_seg=2.0)
                try:
                    if hasattr(self, "_preview_temp_path") and os.path.exists(
                        self._preview_temp_path
                    ):
                        os.remove(self._preview_temp_path)
                except Exception:
                    pass
                try:
                    # Fallback desde hilo: no se puede await, programar el coroutine en el loop de la página
                    _loop = getattr(self.page, "loop", None)
                    if _loop is not None:
                        _loop.create_task(self.page.window.destroy())
                except Exception:
                    pass
                finally:
                    _cancelar_watchdog_cierre()

            timer_fallback = threading.Timer(0.05, _fallback_cierre)
            timer_fallback.daemon = True
            timer_fallback.start()

    def _on_delete_preferences(self, e):
        """(Removed) antiguamente borraba preferencias y cerraba la app.
        Esta acción ahora está disponible desde el diálogo de Preferencias.
        """
        print("[PREFERENCES] _on_delete_preferences deprecated")

    def _show_unsaved_changes_dialog(self):
        """Muestra diálogo cuando hay cambios sin guardar al intentar salir"""

        async def save_and_exit(e):
            """Guardar proyecto y cerrar aplicación"""
            close_dialog()

            if self.current_project_path:
                # Ya tiene ruta, guardar directamente
                try:
                    # Forzar guardado en .pnb (anular guardado JSON de depuración)
                    if self.current_project_path.endswith(".pnb"):
                        pnb_path = self.current_project_path
                    else:
                        pnb_path = (
                            os.path.splitext(self.current_project_path)[0] + ".pnb"
                        )
                        self.current_project_path = pnb_path
                        self.project_name = os.path.basename(pnb_path)
                        name_without_ext = os.path.splitext(self.project_name)[0]
                        self.page.title = f"PageNumber - {name_without_ext}"
                        self.page.update()

                    self._save_project_to_pnb(pnb_path)

                    print("[EXIT] Proyecto guardado, cerrando aplicación")
                    self._close_app_con_dialogo()
                except Exception as ex:
                    print(f"[ERROR] Error al guardar: {ex}")
                    error_text = ft.Text(
                        t("Error al guardar: {0}").format(str(ex)),
                        color=SNACKBAR_COLOR_TEXTO,
                    )
                    self.page.overlay.append(
                        ft.SnackBar(
                            content=error_text, bgcolor=SNACKBAR_COLOR_ERROR, open=True
                        )
                    )
                    self.page.update()
                    return
            else:
                # No tiene ruta, abrir diálogo de guardar
                # Marcar que después de guardar hay que cerrar
                self._exit_after_save = True
                saved_path = await self.save_file_picker.save_file(
                    dialog_title=t("Guardar antes de salir"),
                    file_name=f"{self.project_name}.pnb",
                    file_type=ft.FilePickerFileType.CUSTOM,
                    allowed_extensions=["pnb", "json"],
                    initial_directory=get_last_file_dialog_path(),
                )
                await self._save_file_result(saved_path)

        def exit_without_saving(e):
            """Cerrar sin guardar cambios"""
            close_dialog()
            print("[EXIT] Saliendo sin guardar cambios")
            self._close_app_con_dialogo()

        def cancel_exit(e):
            """Cancelar salida, volver a la app"""
            close_dialog()
            print("[EXIT] Salida cancelada")

        def close_dialog():
            """Helper para cerrar el diálogo"""
            try:
                self.page.pop_dialog()
            except Exception:
                unsaved_dialog.open = False
                self.page.update()

        # Crear diálogo
        unsaved_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Container(
                content=ft.Text(
                    t("Cambios sin guardar"),
                    size=18,
                    weight=ft.FontWeight.BOLD,
                    color=TEXTO_COLOR_GENERICO,
                    text_align=ft.TextAlign.CENTER,
                ),
                alignment=ft.Alignment.CENTER,
            ),
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.Text(
                            t("Tienes cambios sin guardar en el proyecto."),
                            size=14,
                            weight=ft.FontWeight.BOLD,
                            color=TEXTO_COLOR_GENERICO,
                            text_align=ft.TextAlign.CENTER,
                        ),
                        ft.Container(height=10),
                        ft.Text(
                            t("¿Qué deseas hacer?"),
                            size=14,
                            color=TEXTO_COLOR_GENERICO,
                            text_align=ft.TextAlign.CENTER,
                            weight=ft.FontWeight.BOLD,
                        ),
                    ],
                    spacing=5,
                    tight=True,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                width=400,
                padding=20,
            ),
            actions=[
                ft.Button(
                    t("Cancelar"),
                    on_click=cancel_exit,
                    width=120,
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
                    t("Salir sin guardar"),
                    on_click=exit_without_saving,
                    width=150,
                    bgcolor=ft.Colors.RED_700,
                    style=ft.ButtonStyle(
                        color={ft.ControlState.DEFAULT: ft.Colors.WHITE},
                        padding=ft.Padding(0, 0, 0, 0),
                        shape=ft.RoundedRectangleBorder(radius=10),
                    ),
                ),
                ft.Button(
                    t("Guardar y salir"),
                    on_click=save_and_exit,
                    width=140,
                    bgcolor=ft.Colors.GREEN_700,
                    style=ft.ButtonStyle(
                        color={ft.ControlState.DEFAULT: ft.Colors.WHITE},
                        padding=ft.Padding(0, 0, 0, 0),
                        shape=ft.RoundedRectangleBorder(radius=10),
                    ),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            bgcolor=FONDO_ALERT_DIALOG,
        )

        self.page.show_dialog(unsaved_dialog)

    def _on_window_event(self, e):
        """Maneja eventos de ventana - captura intento de cierre con botón X

        Añadimos trazas adicionales y reforzamos la prevención de cierre para
        asegurarnos de que el diálogo de 'cambios sin guardar' se muestre siempre
        cuando corresponda y que la ventana no se cierre sin confirmación.
        """
        # Flet 1.0: WindowEvent expone e.type (enum WindowEventType, CLOSE="close").
        # Legacy 0.28: la info llegaba como string en e.data.
        ev_type = getattr(e, "type", None)
        ev_type_str = (str(getattr(ev_type, "value", ev_type)) or "").lower()
        try:
            edata = e.data
        except Exception:
            edata = None
        # print(f"[WINDOW EVENT] recibido e={e!r} e.type={ev_type!r} e.data={edata!r} prevent_close={getattr(self.page.window,'prevent_close',None)})")

        is_close = "close" in ev_type_str or (
            isinstance(edata, str) and "close" in edata.lower()
        )

        if not is_close:
            return

        if getattr(self, "_closing_in_progress", False):
            return
        print("[WINDOW] Usuario intentó cerrar con botón X (evento detectado)")

        # Verificar si hay cambios comparando snapshots
        self._verify_modification_state()
        print(f"[WINDOW] Estado proyecto: project_modified={self.project_modified}")

        if self.project_modified:
            # Hay cambios sin guardar, reforzar bloqueo y mostrar diálogo
            print(
                "[WINDOW] Hay cambios sin guardar, mostrando diálogo y previniendo cierre"
            )
            try:
                # Reforzar flag prevent_close para evitar que el cierre continúe
                self.page.window.prevent_close = True
            except Exception:
                pass
            self._show_unsaved_changes_dialog()
            return
        else:
            # Sin cambios, permitir cierre
            print("[WINDOW] Sin cambios, cerrando aplicación")
            try:
                # Permitir cierre por defecto y destruir ventana
                self.page.window.prevent_close = False
            except Exception:
                pass
            self._close_app_con_dialogo()
            return

        # Si el evento no es 'close', loguear para diagnóstico
        # print(f"[WINDOW EVENT] Evento no gestionado por _on_window_event: {edata!r}")

    def _on_new_project(self, e):
        """Crea un nuevo proyecto limpio (verificar cambios si los hay)"""
        print("[NEW] Solicitando nuevo proyecto")
        # Verificar estado real y mostrar diálogo adecuado
        # Si hay cambios sin guardar, usar el diálogo con opciones de guardar/descartar
        # Si no hay cambios, mostrar diálogo sencillo de confirmación
        self._verify_modification_state()
        if self.project_modified:
            self._show_new_project_dialog()
        else:
            self._show_confirm_new_project_dialog()

    def _show_new_project_dialog(self):
        """Muestra diálogo cuando hay cambios sin guardar al crear nuevo proyecto"""

        async def save_and_new(e):
            """Guardar proyecto actual y crear nuevo"""
            close_dialog()

            if self.current_project_path:
                # Ya tiene ruta, guardar directamente
                try:
                    # Forzar guardado en .pnb (anular guardado JSON de depuración)
                    if self.current_project_path.endswith(".pnb"):
                        pnb_path = self.current_project_path
                    else:
                        pnb_path = (
                            os.path.splitext(self.current_project_path)[0] + ".pnb"
                        )
                        self.current_project_path = pnb_path
                        self.project_name = os.path.basename(pnb_path)
                        name_without_ext = os.path.splitext(self.project_name)[0]
                        self.page.title = f"PageNumber - {name_without_ext}"
                        self.page.update()

                    self._save_project_to_pnb(pnb_path)

                    print("[NEW] Proyecto guardado, creando nuevo")
                    self._reset_to_default_project()
                except Exception as ex:
                    print(f"[ERROR] Error al guardar: {ex}")
                    return
            else:
                # No tiene ruta, abrir diálogo de guardar
                # Marcar que después de guardar hay que crear nuevo
                self._new_after_save = True
                saved_path = await self.save_file_picker.save_file(
                    dialog_title=t("Guardar antes de crear nuevo"),
                    file_name=f"{self.project_name}.pnb",
                    file_type=ft.FilePickerFileType.CUSTOM,
                    allowed_extensions=["pnb", "json"],
                    initial_directory=get_last_file_dialog_path(),
                )
                await self._save_file_result(saved_path)

        def new_without_saving(e):
            """Crear nuevo sin guardar cambios"""
            close_dialog()
            print("[NEW] Creando nuevo sin guardar cambios")
            self._reset_to_default_project()

        def cancel_new(e):
            """Cancelar nuevo proyecto"""
            close_dialog()
            print("[NEW] Nuevo proyecto cancelado")

        def close_dialog():
            """Helper para cerrar el diálogo"""
            new_dialog.open = False
            self.page.update()

        # Crear diálogo
        new_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Container(
                content=ft.Text(
                    t("Cambios sin guardar"),
                    size=18,
                    weight=ft.FontWeight.BOLD,
                    color=TEXTO_COLOR_GENERICO,
                    text_align=ft.TextAlign.CENTER,
                ),
                alignment=ft.Alignment.CENTER,
            ),
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.Text(
                            t("Tienes cambios sin guardar en el proyecto actual."),
                            size=14,
                            color=TEXTO_COLOR_GENERICO,
                            weight=ft.FontWeight.BOLD,
                            text_align=ft.TextAlign.CENTER,
                        ),
                        ft.Container(height=10),
                        ft.Text(
                            t("¿Qué deseas hacer?"),
                            size=11,
                            color=TEXTO_COLOR_GENERICO,
                            text_align=ft.TextAlign.CENTER,
                            weight=ft.FontWeight.BOLD,
                        ),
                    ],
                    spacing=5,
                    tight=True,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                width=400,
                padding=20,
            ),
            actions=[
                ft.Button(
                    t("Cancelar"),
                    on_click=cancel_new,
                    width=120,
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
                    t("Nuevo sin guardar"),
                    on_click=new_without_saving,
                    width=150,
                    bgcolor=ft.Colors.RED_700,
                    style=ft.ButtonStyle(
                        color={ft.ControlState.DEFAULT: ft.Colors.WHITE},
                        padding=ft.Padding(0, 0, 0, 0),
                        shape=ft.RoundedRectangleBorder(radius=10),
                    ),
                ),
                ft.Button(
                    t("Guardar y nuevo"),
                    on_click=save_and_new,
                    width=140,
                    bgcolor=ft.Colors.GREEN_700,
                    style=ft.ButtonStyle(
                        color={ft.ControlState.DEFAULT: ft.Colors.WHITE},
                        padding=ft.Padding(0, 0, 0, 0),
                        shape=ft.RoundedRectangleBorder(radius=10),
                    ),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            bgcolor=FONDO_ALERT_DIALOG,
        )

        self.page.show_dialog(new_dialog)

    def _show_open_project_dialog(self):
        """Muestra diálogo cuando hay cambios sin guardar al abrir un proyecto."""

        async def save_and_open(e):
            close_dialog()
            if self.current_project_path:
                try:
                    if self.current_project_path.endswith(".pnb"):
                        pnb_path = self.current_project_path
                    else:
                        pnb_path = (
                            os.path.splitext(self.current_project_path)[0] + ".pnb"
                        )
                        self.current_project_path = pnb_path
                        self.project_name = os.path.basename(pnb_path)
                        name_without_ext = os.path.splitext(self.project_name)[0]
                        self.page.title = f"PageNumber - {name_without_ext}"
                        self.page.update()
                    self._save_project_to_pnb(pnb_path)
                    await self._open_load_file_picker()
                except Exception as ex:
                    print(f"[ERROR] Error al guardar: {ex}")
            else:
                self._open_after_save = True
                saved_path = await self.save_file_picker.save_file(
                    dialog_title=t("Guardar antes de abrir"),
                    file_name=f"{self.project_name}.pnb",
                    file_type=ft.FilePickerFileType.CUSTOM,
                    allowed_extensions=["pnb", "json"],
                    initial_directory=get_last_file_dialog_path(),
                )
                await self._save_file_result(saved_path)

        async def open_without_saving(e):
            close_dialog()
            print("[OPEN] Abriendo sin guardar cambios")
            await self._open_load_file_picker()

        def cancel_open(e):
            close_dialog()
            print("[OPEN] Abrir cancelado")

        def close_dialog():
            open_dialog.open = False
            self.page.update()

        open_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Container(
                content=ft.Text(
                    t("Cambios sin guardar"),
                    size=18,
                    weight=ft.FontWeight.BOLD,
                    color=TEXTO_COLOR_GENERICO,
                    text_align=ft.TextAlign.CENTER,
                ),
                alignment=ft.Alignment.CENTER,
            ),
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.Text(
                            t("Tienes cambios sin guardar en el proyecto actual."),
                            size=14,
                            color=TEXTO_COLOR_GENERICO,
                            weight=ft.FontWeight.BOLD,
                            text_align=ft.TextAlign.CENTER,
                        ),
                        ft.Container(height=10),
                        ft.Text(
                            t("¿Qué deseas hacer?"),
                            size=11,
                            color=TEXTO_COLOR_GENERICO,
                            text_align=ft.TextAlign.CENTER,
                            weight=ft.FontWeight.BOLD,
                        ),
                    ],
                    spacing=5,
                    tight=True,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                width=400,
                padding=20,
            ),
            actions=[
                ft.Button(
                    t("Cancelar"),
                    on_click=cancel_open,
                    width=120,
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
                    t("Abrir sin guardar"),
                    on_click=open_without_saving,
                    width=150,
                    bgcolor=ft.Colors.RED_700,
                    style=ft.ButtonStyle(
                        color={ft.ControlState.DEFAULT: ft.Colors.WHITE},
                        padding=ft.Padding(0, 0, 0, 0),
                        shape=ft.RoundedRectangleBorder(radius=10),
                    ),
                ),
                ft.Button(
                    t("Guardar y abrir"),
                    on_click=save_and_open,
                    width=140,
                    bgcolor=ft.Colors.GREEN_700,
                    style=ft.ButtonStyle(
                        color={ft.ControlState.DEFAULT: ft.Colors.WHITE},
                        padding=ft.Padding(0, 0, 0, 0),
                        shape=ft.RoundedRectangleBorder(radius=10),
                    ),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            bgcolor=FONDO_ALERT_DIALOG,
        )

        self.page.show_dialog(open_dialog)

    def _show_confirm_new_project_dialog(self):
        """Muestra un diálogo simple para confirmar creación de nuevo proyecto
        cuando el proyecto actual está guardado o no tiene cambios.
        """

        def confirm_new(e):
            confirm_dialog.open = False
            try:
                self._reset_to_default_project()
            except Exception as ex:
                print(f"[ERROR] Al crear nuevo proyecto: {ex}")
            self.page.update()

        def cancel(e):
            confirm_dialog.open = False
            self.page.update()

        confirm_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Container(
                content=ft.Text(
                    t("Crear nuevo proyecto"),
                    size=18,
                    weight=ft.FontWeight.BOLD,
                    color=TEXTO_COLOR_GENERICO,
                    text_align=ft.TextAlign.CENTER,
                ),
                alignment=ft.Alignment.CENTER,
            ),
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.Text(
                            t(
                                "El proyecto actual está guardado o sin cambios. ¿Deseas crear un nuevo proyecto?"
                            ),
                            size=14,
                            color=TEXTO_COLOR_GENERICO,
                            text_align=ft.TextAlign.CENTER,
                        ),
                        ft.Container(height=10),
                        ft.Text(
                            t(
                                "Esta acción cerrará el proyecto actual y creará uno vacío."
                            ),
                            size=12,
                            color=TEXTO_COLOR_GENERICO,
                            text_align=ft.TextAlign.CENTER,
                        ),
                    ],
                    spacing=6,
                    tight=True,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                width=420,
                padding=20,
            ),
            actions=[
                ft.Button(
                    t("Cancelar"),
                    on_click=cancel,
                    width=120,
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
                    t("Crear nuevo"),
                    on_click=confirm_new,
                    width=140,
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
            bgcolor=FONDO_ALERT_DIALOG,
        )

        self.page.show_dialog(confirm_dialog)

    def _reset_to_default_project(self):
        """Resetea la interfaz a un proyecto vacío 'Sin título'"""
        print("[NEW] Creando proyecto nuevo 'Sin título'")

        # Limpiar datos globales
        self.global_settings = {
            "start": DEFAULT_START_NUMBER,
            "end": DEFAULT_END_NUMBER,
            "increment": DEFAULT_INCREMENT,
            "copies": DEFAULT_COPIES,
            "reverse": False,
        }

        # Limpiar posiciones en ambas caras
        self.positions = {"CARA": {}, "DORSO": {}}

        # Limpiar Excel cargado
        self.excel_manager.clear()

        # Resetear contadores de posiciones
        self.next_position_number = {"CARA": 1, "DORSO": 1}

        # Deseleccionar posición actual
        self.selected_position = None

        # Limpiar imágenes de fondo (incluyendo caché física y preferencias)
        from utils.preferences import (
            delete_background_cache,
            reset_last_backgrounds,
        )

        for face in ["CARA", "DORSO"]:
            if face in self.background_image_managers:
                self.background_image_managers[face].clear_image()

        delete_background_cache()
        reset_last_backgrounds()

        # Refrescar visor de imagen de fondo (ahora estará vacío)
        if hasattr(self, "interactive_viewer"):
            self.interactive_viewer.set_background(None)

        # Actualizar botones de imagen
        self._update_image_settings_button_state(do_update=False)

        # Cargar estilos de texto desde preferencias (en lugar de limpiar)
        self.text_style_manager.load_from_preferences()
        self.available_text_styles = [p.name for p in self.text_style_manager.profiles]
        print(
            f"[NEW] Estilos de texto cargados desde preferencias: {len(self.text_style_manager.profiles)} perfiles"
        )

        # Cargar perfiles de texto variable desde preferencias
        self.variable_text_ui_manager.profile_manager.load_from_preferences()
        self._populate_variable_text_profile_dropdown()
        print(
            f"[NEW] Perfiles de texto variable cargados desde preferencias: {len(self.variable_text_ui_manager.profile_manager.profiles)} perfiles"
        )

        # Cargar perfiles de código de barras desde preferencias
        self.barcode_ui_manager.profile_manager.load_from_preferences()
        self._populate_barcode_profile_dropdown()
        print(
            f"[NEW] Perfiles de código de barras cargados desde preferencias: {len(self.barcode_ui_manager.profile_manager.profiles)} perfiles"
        )

        # Limpiar colores spot extraídos de PDFs del proyecto anterior
        self.extracted_spot_colors = []
        if hasattr(self, "text_style_manager"):
            self.text_style_manager.set_extracted_spots(self.extracted_spot_colors)
        if hasattr(self, "barcode_ui_manager"):
            self.barcode_ui_manager.profile_manager.set_extracted_spots(
                self.extracted_spot_colors
            )
        if hasattr(self, "variable_text_ui_manager"):
            self.variable_text_ui_manager.profile_manager.set_extracted_spots(
                self.extracted_spot_colors
            )

        # Resolver rutas de fuentes para los perfiles cargados (sin rebuild de metrics)
        # Refrescar catálogo primero: al cargar prefs del nuevo trabajo las fuentes
        # del sistema pueden haber cambiado desde el arranque del proceso.
        try:
            self.text_style_manager._refresh_system_fonts()
        except Exception as e:
            print(f"[NEW] ⚠️ Refresh fuentes del sistema: {e}")
        try:
            self.text_style_manager._resolve_profiles()
        except Exception as e:
            print(f"[NEW] ⚠️ Error resolviendo perfiles de texto: {e}")
        try:
            if getattr(self, "variable_text_ui_manager", None) is not None:
                self.variable_text_ui_manager.profile_manager._refresh_system_fonts()
        except Exception as e:
            print(f"[NEW] ⚠️ Refresh fuentes VT: {e}")
        try:
            self.variable_text_ui_manager.profile_manager._resolve_profiles()
        except Exception as e:
            print(f"[NEW] ⚠️ Error resolviendo perfiles VT: {e}")

        # Resetear configuración de caras
        self.face_settings = {
            "CARA": {"reverse": False},
            "DORSO": {"reverse": False},
        }

        # Cargar configuración de página desde preferencias
        startup_settings = get_startup_settings()
        self.current_unit = startup_settings.get("unit", UNIT_MM)

        # Aplicar tamaño de página guardado si existe
        saved_page_size = startup_settings.get("page_size", DEFAULT_PAGE_SIZE_NAME)
        if saved_page_size in PAGE_SIZES:
            self.page_size_name = saved_page_size
            self.page_width_mm, self.page_height_mm = PAGE_SIZES[saved_page_size]
        elif saved_page_size in self.custom_sizes:
            self.page_size_name = saved_page_size
            self.page_width_mm, self.page_height_mm = self.custom_sizes[saved_page_size]
        else:
            # Default a A4 si no se encuentra
            self.page_size_name = DEFAULT_PAGE_SIZE_NAME
            self.page_width_mm = DEFAULT_PAGE_WIDTH_MM
            self.page_height_mm = DEFAULT_PAGE_HEIGHT_MM

        # El bleed siempre resetea a default (no se guarda en preferencias)
        self.bleed_mm = DEFAULT_BLEED_MM

        # Actualizar tamaño de página en el viewer
        self.interactive_viewer.set_page_size(
            self.page_width_mm + (self.bleed_mm * 2),
            self.page_height_mm + (self.bleed_mm * 2),
            self.bleed_mm,
        )
        self._reset_view()

        # La unidad global se mantiene en `self.current_unit` (selección en Preferencias)

        # Actualizar unidad de las reglas si están habilitadas
        if ENABLE_RULERS:
            self.interactive_viewer.set_ruler_unit(self.current_unit)

        print(
            f"[NEW] Configuración desde preferencias: unit={self.current_unit}, page={self.page_size_name}, bleed={self.bleed_mm}mm"
        )

        # Resetear estado del proyecto
        self.project_name = t("Sin título")
        self.current_project_path = None
        self.project_modified = False
        self._saved_state_snapshot = None

        # Actualizar título de ventana
        self.page.title = t("PageNumber - Sin título")

        # Actualizar campos de UI
        self.start_field.value = str(DEFAULT_START_NUMBER)
        self.end_field.value = str(DEFAULT_END_NUMBER)
        self.increment_field.value = str(DEFAULT_INCREMENT)
        self.copies_field.value = str(DEFAULT_COPIES)
        self.reverse_checkbox.value = False
        self.reverse_checkbox.update()

        # Actualizar texto de tamaño de página
        self._update_page_size_text()

        # Apagar doble cara: el toggle no solo colorea, deja estado interno
        # (disabled, indicador, cara). Restaurar estado apagado completo.
        self.double_sided_enabled = False
        self.icon_face.disabled = True
        self.icon_double_sided.bgcolor = FONDO_TEXTFIELDS_COLOR
        self.icon_double_sided.content.color = TEXTOS_FASE_1_COLOR
        self.icon_face.bgcolor = FONDO_TEXTFIELDS_COLOR
        self.icon_face.content.controls[0].color = TEXTOS_FASE_1_COLOR
        self.icon_face.content.controls[1].color = TEXTOS_FASE_1_COLOR
        self.double_sided_indicator.visible = False

        # Resetear cara actual a CARA y actualizar
        self.current_face = "CARA"
        self._update_face_button()
        self._refresh_current_face()

        # Resetear número de página a 1 (mismo patrón que _load_project_data)
        self.current_page = 1
        self.preview_page_field.value = "1"

        # Actualizar estado visual de botones
        self._update_project_state_ui()
        self._update_image_settings_button_state()

        # Actualizar toda la página
        self.page.update()

        # Forzar recolección de basura para liberar memoria de objetos huérfanos
        gc.collect()

        print("[NEW] Proyecto nuevo creado: 'Sin título'")

    async def _on_save_project(self, e):
        """Guarda el trabajo actual en un archivo"""

        # Si ya tiene ruta guardada, guardar directamente sin diálogo
        if self.current_project_path:
            print(f"[FILE] Guardando directamente en: {self.current_project_path}")
            try:
                # Forzar guardado en .pnb (anular guardado JSON de depuración)
                if self.current_project_path.endswith(".pnb"):
                    pnb_path = self.current_project_path
                else:
                    pnb_path = os.path.splitext(self.current_project_path)[0] + ".pnb"
                    self.current_project_path = pnb_path
                    self.project_name = os.path.basename(pnb_path)
                    name_without_ext = os.path.splitext(self.project_name)[0]
                    self.page.title = f"PageNumber - {name_without_ext}"
                    self.page.update()

                self._save_project_to_pnb(pnb_path)

                # FASE 2: Actualizar estado después de guardar
                self._saved_state_snapshot = self._create_state_snapshot()
                self.project_modified = False
                self._update_project_state_ui()

                print(f"[SAVE] Proyecto guardado exitosamente")
                print(f"[STATE] Snapshot actualizado después de guardar")

                # Mostrar mensaje de confirmación
                print("[SNACKBAR] Mostrando mensaje de guardado")
                success_snackbar = ft.SnackBar(
                    content=ft.Text(
                        t("✓ Archivo guardado correctamente"),
                        color=SNACKBAR_COLOR_TEXTO,
                        size=14,
                    ),
                    bgcolor=SUCCESS_COLOR,
                    open=True,
                )
                self.page.overlay.append(success_snackbar)
                self.page.update()
                print("[SNACKBAR] Mensaje mostrado")

            except Exception as ex:
                print(f"[ERROR] Error al guardar: {ex}")
                # Mostrar mensaje de error
                error_snackbar = ft.SnackBar(
                    content=ft.Text(
                        t("Error al guardar: {0}").format(str(ex)),
                        color=SNACKBAR_COLOR_TEXTO,
                    ),
                    bgcolor=SNACKBAR_COLOR_ERROR,
                    open=True,
                )
                self.page.overlay.append(error_snackbar)
                self.page.update()
            return

        # Si no tiene ruta (Sin título), abrir diálogo
        print("[FILE] Abriendo diálogo para guardar proyecto nuevo")
        base_name = os.path.splitext(self.project_name)[0]
        default_name = f"{base_name}.pnb"

        saved_path = await self.save_file_picker.save_file(
            dialog_title=t("Guardar proyecto"),
            file_name=default_name,
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["pnb", "json"],
            initial_directory=get_last_file_dialog_path(),
        )
        await self._save_file_result(saved_path)

    async def _on_save_as_project(self, e):
        """Abre el diálogo de guardar como para elegir una nueva ubicación/nombre"""
        print("[FILE] Abriendo diálogo 'Guardar como'")

        # Sugerir el nombre actual sin duplicar extensión
        base_name = os.path.splitext(self.project_name)[0]
        default_name = f"{base_name}.pnb"

        saved_path = await self.save_file_picker.save_file(
            dialog_title=t("Guardar trabajo como:"),
            file_name=default_name,
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["pnb", "json"],
            initial_directory=get_last_file_dialog_path(),
        )
        await self._save_file_result(saved_path)

    async def _on_load_project(self, e):
        """Carga un trabajo desde un archivo"""
        self._verify_modification_state()
        if self.project_modified:
            self._show_open_project_dialog()
        else:
            await self._open_load_file_picker()

    async def _open_load_file_picker(self):
        """Abre el file picker para cargar proyecto."""
        print("[FILE] Abriendo diálogo para cargar proyecto")
        files = await self.load_file_picker.pick_files(
            dialog_title=t("Cargar proyecto"),
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["pnb", "json"],
            allow_multiple=False,
            initial_directory=get_last_file_dialog_path(),
        )
        self._load_file_result(files)

    def _on_package_project(self, e):
        """Abre diálogo para empaquetar proyecto en carpeta"""

        # Verificar que el proyecto haya sido guardado y que no haya cambios sin guardar
        if not self.current_project_path or self.project_modified:
            # Mensaje distinto si hay cambios sin guardar
            if self.project_modified:
                title_text = t("Cambios sin guardar")
                message_text = t(
                    "Tienes cambios sin guardar. Guarda el proyecto antes de empaquetarlo."
                )
            else:
                title_text = t("Guardar proyecto primero")
                message_text = t("Debes guardar el proyecto antes de empaquetarlo.")

            warning_dialog = ft.AlertDialog(
                modal=True,
                title=ft.Container(
                    content=ft.Text(
                        title_text,
                        size=18,
                        weight=ft.FontWeight.BOLD,
                        color=TEXTO_COLOR_GENERICO,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    alignment=ft.Alignment.CENTER,
                ),
                content=ft.Container(
                    content=ft.Column(
                        [
                            ft.Text(
                                message_text,
                                size=16,
                                color=TEXTO_COLOR_GENERICO,
                                weight=ft.FontWeight.BOLD,
                                text_align=ft.TextAlign.CENTER,
                            ),
                        ],
                        spacing=5,
                        tight=True,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    width=420,
                    padding=20,
                ),
                actions=[],
                actions_alignment=ft.MainAxisAlignment.CENTER,
                bgcolor=FONDO_ALERT_DIALOG,
            )

            cancel_button = ft.Button(
                t("Entendido"),
                on_click=lambda e: (
                    setattr(warning_dialog, "open", False),
                    self.page.update(),
                ),
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
                width=110,
            )

            # Añadir botón al diálogo (solo informar)
            warning_dialog.actions = [cancel_button]

            self.page.show_dialog(warning_dialog)
            return

        print("[PACKAGE] Abriendo diálogo de empaquetado")
        # Inicializar flags si no existen
        self._package_include_fonts = getattr(self, "_package_include_fonts", False)

        # Debug inmediato: listar estilos usados y perfiles disponibles para diagnóstico
        try:
            used_style_names_tmp = set()
            for face in ["CARA", "DORSO"]:
                positions = self.positions.get(face, {})
                for num_id, pos in positions.items():
                    ts = pos.get("text_style") or pos.get("text_style_name")
                    if ts:
                        used_style_names_tmp.add(ts)
            profiles_tmp = (
                {
                    p.name: (
                        p.font_family,
                        p.font_style,
                        getattr(p, "resolved_font_path", None),
                    )
                    for p in self.text_style_manager.get_profiles()
                }
                if self.text_style_manager
                else {}
            )
            print(
                f"[PACKAGE DEBUG] Dialog open - used_style_names={sorted(used_style_names_tmp)}"
            )
            print(f"[PACKAGE DEBUG] Dialog open - profiles_available={profiles_tmp}")
            print(
                f"[PACKAGE DEBUG] Dialog open - include_fonts_flag={self._package_include_fonts}"
            )
        except Exception as ex:
            print(f"[PACKAGE DEBUG] Error preparando debug info: {ex}")

        # Crear diálogo
        async def on_select_folder(e):
            folder = await self.package_folder_picker.get_directory_path(
                dialog_title=t("Seleccionar carpeta destino")
            )
            self._package_folder_result(folder)

        def on_package(e):
            if (
                not hasattr(self, "_selected_package_folder")
                or not self._selected_package_folder
            ):
                # Mostrar error
                error_text.value = t("Debes seleccionar una carpeta destino")
                error_text.visible = True
                self.page.update()
                return

            try:
                include_fonts = getattr(self, "_package_include_fonts", False)
                self._execute_package_project(
                    self._selected_package_folder, include_fonts=include_fonts
                )
                self.page.update()
                print("[PACKAGE] Proyecto empaquetado exitosamente")
            except Exception as ex:
                print(f"[ERROR] Error al empaquetar: {ex}")
                error_text.value = t("⚠️ Error: {0}").format(str(ex))
                error_text.visible = True
                self.page.update()

        def on_cancel(e):
            package_dialog.open = False
            self.page.update()

        error_text = ft.Text("", size=11, color=ft.Colors.RED_400, visible=False)

        # Texto para mostrar la ruta seleccionada
        self._package_path_text = ft.Text(
            t("Ninguna carpeta seleccionada"),
            size=12,
            color=TEXTO_COLOR_GENERICO,
            italic=True,
            max_lines=2,
            overflow=ft.TextOverflow.ELLIPSIS,
            width=400,
        )

        package_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Container(
                content=ft.Text(
                    t("Empaquetar Proyecto"),
                    size=18,
                    weight=ft.FontWeight.BOLD,
                    color=TEXTO_COLOR_GENERICO,
                    text_align=ft.TextAlign.CENTER,
                ),
                alignment=ft.Alignment.CENTER,
            ),
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.Text(
                            t(
                                "Selecciona la carpeta donde adjuntar los archivos del proyecto:"
                            ),
                            size=14,
                            color=TEXTO_COLOR_GENERICO,
                            weight=ft.FontWeight.BOLD,
                        ),
                        ft.Container(height=15),
                        ft.Button(
                            t("Seleccionar carpeta destino"),
                            on_click=on_select_folder,
                            width=400,
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
                        ft.Container(
                            content=self._package_path_text,
                            height=40,
                            padding=ft.Padding(4, 4, 4, 0),
                        ),
                        ft.Container(height=5),
                        # Checkbox: Include fonts + target platform selector
                        # Checkbox: Include fonts (explicit control to ensure visibility)
                        ft.Container(
                            content=ft.Column(
                                [
                                    ft.Text(
                                        t("Opciones de empaquetado"),
                                        size=14,
                                        weight=ft.FontWeight.BOLD,
                                        color=TEXTO_COLOR_GENERICO,
                                    ),
                                    ft.Container(height=6),
                                    ft.Row(
                                        [
                                            ft.Checkbox(
                                                value=getattr(
                                                    self,
                                                    "_package_include_fonts",
                                                    False,
                                                ),
                                                active_color=BORDE_TEXTFIELDS_COLOR,
                                                check_color=TEXTOS_FASE_1_COLOR,
                                                fill_color=FONDO_TEXTFIELDS_COLOR,
                                                border_side=ft.BorderSide(
                                                    1, BORDE_TEXTFIELDS_COLOR
                                                ),
                                                splash_radius=0,
                                                on_change=lambda e: (
                                                    setattr(
                                                        self,
                                                        "_package_include_fonts",
                                                        e.control.value,
                                                    ),
                                                    setattr(
                                                        self,
                                                        "_package_include_fonts_checkbox",
                                                        e.control,
                                                    ),
                                                    print(
                                                        f"[PACKAGE DEBUG] include_fonts toggled -> {e.control.value}"
                                                    ),
                                                    self.page.update(),
                                                ),
                                            ),
                                            ft.Text(
                                                t(
                                                    "Incluir tipos de letra en carpeta (fonts/)"
                                                ),
                                                size=14,
                                                color=TEXTOS_FASE_1_COLOR,
                                            ),
                                        ],
                                        alignment=ft.MainAxisAlignment.START,
                                        spacing=0,
                                    ),
                                    ft.Container(height=6),
                                    ft.Text(
                                        t(
                                            "Nota: Las tipografías se copian solo para archivar el trabajo; no se enlazan al proyecto."
                                        ),
                                        size=14,
                                        color=TEXTO_COLOR_GENERICO,
                                    ),
                                ],
                                tight=True,
                            )
                        ),
                        error_text,
                    ],
                    spacing=5,
                    tight=True,
                ),
                width=500,
                padding=20,
            ),
            actions=[
                ft.Button(
                    t("Cancelar"),
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
                ft.Button(
                    t("Adjuntar archivos en carpeta"),
                    on_click=on_package,
                    width=220,
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
            actions_alignment=ft.MainAxisAlignment.CENTER,
            bgcolor=FONDO_ALERT_DIALOG,
        )

        # Guardar referencia al diálogo para actualizar desde callback
        self._package_dialog = package_dialog
        self._package_error_text = error_text

        self.page.show_dialog(package_dialog)

    def _package_folder_result(self, e):
        """Callback cuando se selecciona carpeta para empaquetar"""
        path = getattr(e, "path", e)
        if path:
            self._selected_package_folder = path
            self._package_error_text.visible = False
            # Mostrar la ruta seleccionada en el diálogo
            if hasattr(self, "_package_path_text"):
                self._package_path_text.value = path
                self._package_path_text.italic = False
            self.page.update()
            print(f"[PACKAGE] Carpeta seleccionada: {path}")

    def _update_project_state_ui(self):
        """Actualiza el estado visual de iconos según estado del proyecto (3 estados)"""
        print(
            f"[UI] _update_project_state_ui: project_modified={self.project_modified}, _ui_mounted={getattr(self, '_ui_mounted', False)}"
        )

        # Estado 1: Sin proyecto / Proyecto nuevo (Sin título)
        # Estado 2: Proyecto guardado/cargado sin cambios
        # Estado 3: Proyecto modificado (naranja)

        # ICONO CARGAR: no cambiar fondo (mantener apariencia constante)
        # Dejamos el icono con estilo por defecto para evitar cambios visuales inesperados
        if not hasattr(self, "icon_load_project"):
            pass

        # ICONO GUARDAR: Solo cambia a naranja si hay cambios.
        # Cuando el trabajo está guardado (no modificado) se muestra fondo blanco.
        if self.project_modified:
            # Modificado - naranja
            self.icon_save_project.bgcolor = ft.Colors.ORANGE_700
            self.icon_save_project.content.color = ft.Colors.WHITE
        elif self.current_project_path or self.project_name != t("Sin título"):
            # Proyecto guardado/cargado y sin modificaciones - mantener apariencia por defecto
            # No usar detección de tema aquí: solo mostrar naranja cuando hay modificaciones.
            self.icon_save_project.bgcolor = FONDO_TEXTFIELDS_COLOR
            self.icon_save_project.content.color = TEXTOS_FASE_1_COLOR
        else:
            # Sin proyecto - colores normales
            self.icon_save_project.bgcolor = FONDO_TEXTFIELDS_COLOR
            self.icon_save_project.content.color = TEXTOS_FASE_1_COLOR

        # ICONO GUARDAR COMO / EMPAQUETAR: mantener apariencia consistente
        if hasattr(self, "icon_save_as_project"):
            self.icon_save_as_project.bgcolor = FONDO_TEXTFIELDS_COLOR
            self.icon_save_as_project.content.color = TEXTOS_FASE_1_COLOR

        self.icon_package_project.bgcolor = FONDO_TEXTFIELDS_COLOR
        self.icon_package_project.content.color = TEXTOS_FASE_1_COLOR

        # Actualizar UI (solo si la UI ya fue montada en la página)
        if hasattr(self, "icon_load_project") and getattr(self, "_ui_mounted", False):
            try:
                self.icon_load_project.update()
            except (AssertionError, RuntimeError):
                pass
            try:
                self.icon_save_project.update()
            except (AssertionError, RuntimeError):
                pass
            try:
                if hasattr(self, "icon_save_as_project"):
                    self.icon_save_as_project.update()
            except (AssertionError, RuntimeError):
                pass
            try:
                self.icon_package_project.update()
            except (AssertionError, RuntimeError):
                pass

    def _create_state_snapshot(self):
        """Crea un snapshot del estado actual del proyecto para comparación"""
        import copy
        from dataclasses import asdict

        return {
            "global_settings": copy.deepcopy(self.global_settings),
            "page_width_mm": self.page_width_mm,
            "page_height_mm": self.page_height_mm,
            "bleed_mm": self.bleed_mm,
            "page_size_name": self.page_size_name,
            "double_sided_enabled": self.double_sided_enabled,
            "current_face": self.current_face,
            "positions_CARA": copy.deepcopy(
                {
                    k: {k2: v2 for k2, v2 in v.items() if k2 != "item"}
                    for k, v in self.positions["CARA"].items()
                }
            ),
            "positions_DORSO": copy.deepcopy(
                {
                    k: {k2: v2 for k2, v2 in v.items() if k2 != "item"}
                    for k, v in self.positions["DORSO"].items()
                }
            ),
            "face_settings_CARA": copy.deepcopy(self.face_settings["CARA"]),
            "face_settings_DORSO": copy.deepcopy(self.face_settings["DORSO"]),
            "text_styles": [asdict(p) for p in self.text_style_manager.profiles],
            "bg_CARA": self.background_image_managers["CARA"].get_image_config(),
            "bg_DORSO": self.background_image_managers["DORSO"].get_image_config(),
        }

    def _mark_modified(self):
        """Marca rápidamente que hubo un cambio (flag simple para eventos).
        Añade prints informativos indicando el origen y el conteo de posiciones.
        """
        # Obtener caller para diagnóstico
        caller = "unknown"
        try:
            import inspect

            caller = inspect.stack()[1].function
        except Exception:
            pass

        # Información de debug mínima
        positions_count = 0
        try:
            positions_count = len(self.positions.get("CARA", {})) + len(
                self.positions.get("DORSO", {})
            )
        except Exception:
            positions_count = -1

        if not self.project_modified:
            self.project_modified = True
            print(
                f"[STATE] Proyecto marcado como modificado (caller={caller}, positions={positions_count}, path={self.current_project_path}, name={self.project_name})"
            )
            self._update_project_state_ui()
        else:
            # Mensaje de estado silenciado por ser ruidoso durante operaciones frecuentes
            if _PRINT_STATE:
                print(
                    f"[STATE] _mark_modified llamado por {caller} pero ya estaba marcado (positions={positions_count}, path={self.current_project_path}, name={self.project_name})"
                )

    def _verify_modification_state(self):
        """
        Verifica REALMENTE si hay cambios comparando con snapshot guardado.
        Esta es la ÚNICA función que determina el estado de modificación.
        Retorna True si hay cambios, False si no los hay.
        """

        # Si existe un snapshot guardado (incluso para proyectos sin ruta), comparar con él
        if self._saved_state_snapshot is not None:
            current_state = self._create_state_snapshot()
            was_modified = self.project_modified
            self.project_modified = current_state != self._saved_state_snapshot

            # Solo actualizar UI si cambió el estado
            if was_modified != self.project_modified:
                self._update_project_state_ui()
                print(
                    f"[STATE] Verificación: {'SIN cambios' if not self.project_modified else 'CON cambios'}"
                )

            return self.project_modified

        # Caso 2: Proyecto "Sin título" - verificar si hay contenido O cambios en configuración
        elif not self.current_project_path:
            # Verificar si hay posiciones creadas
            has_positions = (
                len(self.positions["CARA"]) > 0 or len(self.positions["DORSO"]) > 0
            )

            # Verificar si hay imágenes de fondo
            has_images = (
                self.background_image_managers["CARA"].image_path is not None
                or self.background_image_managers["DORSO"].image_path is not None
            )

            # Verificar si se cambió la unidad desde el valor por defecto
            has_unit_change = self.current_unit != UNIT_MM

            # Verificar si se cambió el tamaño de página desde el valor por defecto (A4: 210x297mm)
            has_size_change = (
                self.page_width_mm != DEFAULT_PAGE_WIDTH_MM
                or self.page_height_mm != DEFAULT_PAGE_HEIGHT_MM
                or self.page_size_name != DEFAULT_PAGE_SIZE_NAME
            )

            # Verificar si se cambió el bleed desde el valor por defecto (3mm)
            has_bleed_change = self.bleed_mm != DEFAULT_BLEED_MM

            # Verificar cambios en configuración global (vs valores por defecto)
            has_config_change = (
                self.global_settings.get("start", DEFAULT_START_NUMBER)
                != DEFAULT_START_NUMBER
                or self.global_settings.get("end", DEFAULT_END_NUMBER)
                != DEFAULT_END_NUMBER
                or self.global_settings.get("increment", DEFAULT_INCREMENT)
                != DEFAULT_INCREMENT
                or self.global_settings.get("copies", DEFAULT_COPIES) != DEFAULT_COPIES
                or self.global_settings.get("reverse", False) != False
            )

            was_modified = self.project_modified
            self.project_modified = (
                has_positions
                or has_images
                or has_unit_change
                or has_size_change
                or has_bleed_change
                or has_config_change
            )

            if was_modified != self.project_modified:
                self._update_project_state_ui()
                print(
                    f"[STATE] Verificación 'Sin título': {'SIN cambios' if not self.project_modified else 'CON cambios'}"
                )

            return self.project_modified

        # Caso 3: Estado indeterminado (no debería ocurrir)
        return self.project_modified

    async def _save_file_result(self, e):
        """Callback cuando se selecciona archivo para guardar"""
        path = getattr(e, "path", e)
        if path:
            set_last_file_dialog_path(path)
            try:
                # Asegurar que el path tenga extensión (en Windows puede no tenerla)
                file_path = path
                # Forzar uso de extensión .pnb (anular .json de depuración)
                if not file_path.endswith(".pnb"):
                    file_path = os.path.splitext(file_path)[0] + ".pnb"
                    print(f"[SAVE] Forzando extensión .pnb: {file_path}")

                # Guardar siempre en PNB
                self._save_project_to_pnb(file_path)

                # Actualizar ruta y nombre del proyecto guardado
                self.current_project_path = file_path
                self.project_name = os.path.basename(file_path)

                # Actualizar título de ventana (sin extensión)
                name_without_ext = os.path.splitext(self.project_name)[0]
                self.page.title = f"PageNumber - {name_without_ext}"
                self.page.update()  # IMPORTANTE: refrescar título de ventana

                # FASE 2: Crear snapshot del estado guardado
                self._saved_state_snapshot = self._create_state_snapshot()
                self.project_modified = False

                # Actualizar estado visual
                self._update_project_state_ui()

                print(f"[SAVE] Proyecto guardado exitosamente: {file_path}")
                print(f"[STATE] Snapshot creado después de guardar")

                # Mostrar mensaje de confirmación
                success_snackbar = ft.SnackBar(
                    content=ft.Text(
                        t("✓ Archivo guardado correctamente"),
                        color=SNACKBAR_COLOR_TEXTO,
                        size=14,
                    ),
                    bgcolor=SUCCESS_COLOR,
                    open=True,
                )

                self.page.overlay.append(success_snackbar)
                self.page.update()

                # Si estamos guardando antes de salir, cerrar ahora
                if hasattr(self, "_exit_after_save") and self._exit_after_save:
                    self._exit_after_save = False
                    print("[EXIT] Guardado completado, cerrando aplicación")
                    self._close_app_con_dialogo()
                    return

                # Si estamos guardando antes de crear nuevo, crear nuevo ahora
                if hasattr(self, "_new_after_save") and self._new_after_save:
                    self._new_after_save = False
                    print("[NEW] Guardado completado, creando nuevo proyecto")
                    self._reset_to_default_project()
                    return

                # Si estamos guardando antes de abrir, abrir file picker ahora
                if hasattr(self, "_open_after_save") and self._open_after_save:
                    self._open_after_save = False
                    print("[OPEN] Guardado completado, abriendo proyecto")
                    await self._open_load_file_picker()
                    return

            except Exception as ex:
                print(f"[ERROR] Error al guardar proyecto: {ex}")
                import traceback

                traceback.print_exc()
                # Mostrar mensaje de error
                error_snackbar = ft.SnackBar(
                    content=ft.Text(
                        t("Error al guardar: {0}").format(str(ex)),
                        color=SNACKBAR_COLOR_TEXTO,
                    ),
                    bgcolor=SNACKBAR_COLOR_ERROR,
                    open=True,
                )
                self.page.overlay.append(error_snackbar)
                self.page.update()
        else:
            # Usuario canceló el FilePicker
            print("[SAVE] FilePicker cancelado por usuario")

            # Si había un flujo pendiente (salir o nuevo), volver a mostrar el diálogo correspondiente
            if hasattr(self, "_exit_after_save") and self._exit_after_save:
                self._exit_after_save = False
                print(
                    "[EXIT] Guardado cancelado, volviendo a mostrar diálogo de salida"
                )
                self._show_unsaved_changes_dialog()
            elif hasattr(self, "_new_after_save") and self._new_after_save:
                self._new_after_save = False
                print(
                    "[NEW] Guardado cancelado, volviendo a mostrar diálogo de nuevo proyecto"
                )
                self._show_new_project_dialog()
            elif hasattr(self, "_open_after_save") and self._open_after_save:
                self._open_after_save = False
                print("[OPEN] Guardado cancelado, volviendo a mostrar diálogo de abrir")
                self._show_open_project_dialog()

    def _load_file_result(self, e):
        """Callback cuando se selecciona archivo para cargar"""
        files = getattr(e, "files", e) or []
        if files:
            file_path = files[0].path
            set_last_file_dialog_path(file_path)
            try:
                # Detectar extensión y usar el método apropiado
                if file_path.endswith(".pnb"):
                    self._load_project_from_pnb(file_path)
                else:
                    self._load_project_from_file(file_path)

                # Actualizar ruta y nombre del proyecto cargado
                self.current_project_path = file_path
                self.project_name = os.path.basename(file_path)

                # Actualizar título de ventana (sin extensión)
                name_without_ext = os.path.splitext(self.project_name)[0]
                self.page.title = f"PageNumber - {name_without_ext}"
                self.page.update()  # IMPORTANTE: refrescar título de ventana

                # FASE 2: Crear snapshot del estado recién cargado
                self._saved_state_snapshot = self._create_state_snapshot()
                self.project_modified = False

                # Actualizar estado visual
                self._update_project_state_ui()

                print(f"[LOAD] Proyecto cargado exitosamente: {file_path}")
                print(f"[STATE] Snapshot creado después de cargar")
                # TODO: Mostrar snackbar de éxito
            except Exception as ex:
                print(f"[ERROR] Error al cargar proyecto: {ex}")
                import traceback

                traceback.print_exc()
                # TODO: Mostrar snackbar de error

    def _save_project_to_file(self, file_path: str):
        """Guarda todos los datos del proyecto en un archivo JSON"""
        print(f"[SAVE] Guardando proyecto en: {file_path}")

        # Recolectar nombres de perfiles realmente usados por las posiciones
        _used_text_styles = set()
        _used_barcode_profiles = set()
        _used_vt_profiles = set()
        for face_positions in self.positions.values():
            for pos_data in face_positions.values():
                ptype = pos_data.get("type", "number")
                if ptype == "number":
                    _used_text_styles.add(pos_data.get("text_style", "<Default>"))
                elif ptype == "barcode":
                    _used_barcode_profiles.add(
                        pos_data.get("profile_name", "<Default>")
                    )
                elif ptype == "variable_text":
                    _used_vt_profiles.add(pos_data.get("profile_name", "<Default>"))

        # Construir sección perfiles unificada (v2) — sin transitorios (Myriad Pro se pierde si se guarda path absoluto)
        perfiles = {}
        if _used_text_styles:
            perfiles["numeros"] = {}
            for p in self.text_style_manager.profiles:
                if p.name not in _used_text_styles:
                    continue
                d = asdict(p)
                d.pop("resolved_font_path", None)
                d.pop("resolved_font_index", None)
                d.pop("resolved_status", None)
                d.pop("metricas", None)
                d.pop("resolved_flet_alias", None)
                perfiles["numeros"][p.name] = d
        if _used_barcode_profiles:
            perfiles["codigos de barras"] = {
                p.name: p.to_dict()
                for p in self.barcode_ui_manager.profile_manager.profiles
                if p.name in _used_barcode_profiles
            }
        if _used_vt_profiles:
            perfiles["textos variables"] = {
                p.name: p.to_dict()
                for p in self.variable_text_ui_manager.profile_manager.profiles
                if p.name in _used_vt_profiles
            }

        # Serializar posiciones (v2: solo geometría + referencia al perfil)
        def serialize_positions(positions_dict):
            serialized = {}
            for pos_id, pos_data in positions_dict.items():
                base = {"type": pos_data.get("type", "number")}
                ptype = base["type"]
                if ptype == "number":
                    base["text_style"] = pos_data.get("text_style", "<Default>")
                    base["add"] = pos_data.get("add", "0")
                elif ptype in ("barcode", "variable_text"):
                    base["profile_name"] = pos_data.get("profile_name", "<Default>")
                    if ptype == "variable_text":
                        base["anchor"] = pos_data.get("anchor", "superior_izquierda")
                base["x"] = pos_data.get("x", 10)
                base["y"] = pos_data.get("y", 10)
                base["rotation"] = pos_data.get("rotation", 0)
                base["alignment"] = pos_data.get("alignment", "izquierda")
                base["locked"] = pos_data.get("locked", False)
                serialized[pos_id] = base
            return serialized

        # Construir estructura de datos
        project_data = {
            "version": "2.0",
            "double_sided_enabled": self.double_sided_enabled,
            "current_face": self.current_face,
            "paper_settings": {
                "width": self.page_width_mm,
                "height": self.page_height_mm,
                "bleed": self.bleed_mm,
                "size_name": self.page_size_name,
                "unit": self.current_unit,
            },
            "global_settings": self.global_settings,
            "CARA": {
                "positions": serialize_positions(self.positions["CARA"]),
                "face_settings": self.face_settings["CARA"],
                "background_image": self.background_image_managers[
                    "CARA"
                ].get_image_config(),
            },
        }

        if self.double_sided_enabled:
            project_data["DORSO"] = {
                "positions": serialize_positions(self.positions["DORSO"]),
                "face_settings": self.face_settings["DORSO"],
                "background_image": self.background_image_managers[
                    "DORSO"
                ].get_image_config(),
            }

        # Perfiles unificados (v2)
        if perfiles:
            project_data["perfiles"] = perfiles

        # Excel: guardar siempre si hay Excel cargado
        if self.excel_manager.is_loaded:
            project_data["excel_path"] = self.excel_manager.filepath

        # Guardar a archivo
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(project_data, f, indent=2, ensure_ascii=False)

        print(
            f"[SAVE] Proyecto guardado con {len(self.positions['CARA'])} posiciones en CARA y {len(self.positions['DORSO'])} en DORSO"
        )

    def _save_project_to_pnb(self, file_path: str):
        """Guarda todos los datos del proyecto en formato binario comprimido .pnb"""
        print(f"[SAVE] Guardando proyecto en formato PNB: {file_path}")

        # Recolectar nombres de perfiles realmente usados por las posiciones
        _used_text_styles = set()
        _used_barcode_profiles = set()
        _used_vt_profiles = set()
        for face_positions in self.positions.values():
            for pos_data in face_positions.values():
                ptype = pos_data.get("type", "number")
                if ptype == "number":
                    _used_text_styles.add(pos_data.get("text_style", "<Default>"))
                elif ptype == "barcode":
                    _used_barcode_profiles.add(
                        pos_data.get("profile_name", "<Default>")
                    )
                elif ptype == "variable_text":
                    _used_vt_profiles.add(pos_data.get("profile_name", "<Default>"))

        # Construir sección perfiles unificada (v2) — sin transitorios (Myriad Pro se pierde si se guarda path absoluto)
        perfiles = {}
        if _used_text_styles:
            perfiles["numeros"] = {}
            for p in self.text_style_manager.profiles:
                if p.name not in _used_text_styles:
                    continue
                d = asdict(p)
                d.pop("resolved_font_path", None)
                d.pop("resolved_font_index", None)
                d.pop("resolved_status", None)
                d.pop("metricas", None)
                d.pop("resolved_flet_alias", None)
                perfiles["numeros"][p.name] = d
        if _used_barcode_profiles:
            perfiles["codigos de barras"] = {
                p.name: p.to_dict()
                for p in self.barcode_ui_manager.profile_manager.profiles
                if p.name in _used_barcode_profiles
            }
        if _used_vt_profiles:
            perfiles["textos variables"] = {
                p.name: p.to_dict()
                for p in self.variable_text_ui_manager.profile_manager.profiles
                if p.name in _used_vt_profiles
            }

        # Serializar posiciones (v2: solo geometría + referencia al perfil)
        def serialize_positions(positions_dict):
            serialized = {}
            for pos_id, pos_data in positions_dict.items():
                base = {"type": pos_data.get("type", "number")}
                ptype = base["type"]
                if ptype == "number":
                    base["text_style"] = pos_data.get("text_style", "<Default>")
                    base["add"] = pos_data.get("add", "0")
                elif ptype in ("barcode", "variable_text"):
                    base["profile_name"] = pos_data.get("profile_name", "<Default>")
                    if ptype == "variable_text":
                        base["anchor"] = pos_data.get("anchor", "superior_izquierda")
                base["x"] = pos_data.get("x", 10)
                base["y"] = pos_data.get("y", 10)
                base["rotation"] = pos_data.get("rotation", 0)
                base["alignment"] = pos_data.get("alignment", "izquierda")
                base["locked"] = pos_data.get("locked", False)
                serialized[pos_id] = base
            return serialized

        # Construir estructura de datos
        project_data = {
            "version": "2.0",
            "double_sided_enabled": self.double_sided_enabled,
            "current_face": self.current_face,
            "paper_settings": {
                "width": self.page_width_mm,
                "height": self.page_height_mm,
                "bleed": self.bleed_mm,
                "size_name": self.page_size_name,
                "unit": self.current_unit,
            },
            "global_settings": self.global_settings,
            "CARA": {
                "positions": serialize_positions(self.positions["CARA"]),
                "face_settings": self.face_settings["CARA"],
                "background_image": self.background_image_managers[
                    "CARA"
                ].get_image_config(),
            },
        }

        if self.double_sided_enabled:
            project_data["DORSO"] = {
                "positions": serialize_positions(self.positions["DORSO"]),
                "face_settings": self.face_settings["DORSO"],
                "background_image": self.background_image_managers[
                    "DORSO"
                ].get_image_config(),
            }

        # Perfiles unificados (v2)
        if perfiles:
            project_data["perfiles"] = perfiles

        # Excel: guardar siempre si hay Excel cargado
        if self.excel_manager.is_loaded:
            project_data["excel_path"] = self.excel_manager.filepath

        # Convertir a JSON string
        json_string = json.dumps(project_data, ensure_ascii=False)

        # Comprimir con gzip
        json_bytes = json_string.encode("utf-8")
        compressed_data = gzip.compress(json_bytes, compresslevel=9)

        # Codificar en base64
        encoded_data = base64.b64encode(compressed_data)

        # Guardar a archivo binario
        with open(file_path, "wb") as f:
            f.write(encoded_data)

        print(
            f"[SAVE] Proyecto PNB guardado con {len(self.positions['CARA'])} posiciones en CARA y {len(self.positions['DORSO'])} en DORSO"
        )
        print(
            f"[SAVE] Tamaño original: {len(json_bytes)} bytes, comprimido: {len(encoded_data)} bytes"
        )

        # ========== DEPURACIÓN: Guardar también en JSON legible ==========
        if SAVE_DEBUG_JSON:
            debug_json_path = os.path.splitext(file_path)[0] + "_DEBUG.json"
            try:
                with open(debug_json_path, "w", encoding="utf-8") as f:
                    json.dump(project_data, f, indent=2, ensure_ascii=False)
                print(f"[DEBUG] JSON de depuración guardado en: {debug_json_path}")
            except Exception as e:
                print(f"[DEBUG] Error al guardar JSON de depuración: {e}")

    def _load_project_from_pnb(self, file_path: str):
        """Carga todos los datos del proyecto desde un archivo .pnb (binario comprimido)"""
        print(f"[LOAD] Cargando proyecto desde formato PNB: {file_path}")

        # Leer archivo binario
        with open(file_path, "rb") as f:
            encoded_data = f.read()

        # Decodificar desde base64
        compressed_data = base64.b64decode(encoded_data)

        # Descomprimir
        json_bytes = gzip.decompress(compressed_data)

        # Convertir a JSON
        json_string = json_bytes.decode("utf-8")
        project_data = json.loads(json_string)

        # Usar el mismo código de carga que _load_project_from_file
        self._load_project_data(project_data, file_path)

        print(f"[LOAD] Proyecto PNB cargado exitosamente")

    def _resolve_image_path(
        self, saved_path: str, project_file_path: str
    ) -> Optional[str]:
        """
        Resuelve la ruta de una imagen usando estrategia de búsqueda:
        1. Intentar ruta absoluta original
        2. Buscar en el directorio del proyecto
        3. Retornar None si no se encuentra

        Args:
            saved_path: Ruta guardada en el proyecto
            project_file_path: Ruta del archivo de proyecto (.pnb o .json)

        Returns:
            Ruta resuelta o None si no se encuentra
        """
        if not saved_path:
            return None

        # 1. Intentar ruta original
        if os.path.exists(saved_path):
            print(f"[RESOLVE] Imagen encontrada en ruta original: {saved_path}")
            return saved_path

        # 2. Buscar en el directorio del proyecto
        filename = os.path.basename(saved_path)
        project_dir = os.path.dirname(os.path.abspath(project_file_path))
        alternative_path = os.path.join(project_dir, filename)

        if os.path.exists(alternative_path):
            print(
                f"[RESOLVE] Imagen encontrada en directorio del proyecto: {alternative_path}"
            )
            return alternative_path

        # 3. No encontrada
        print(f"[RESOLVE] ⚠️ Imagen no encontrada: {saved_path}")
        print(f"[RESOLVE]    Buscado también en: {alternative_path}")
        return None

    def _show_missing_excel_dialog(self):
        """Popup cuando el Excel del proyecto no se encuentra. Ofrece buscar/cargar
        un archivo o continuar sin él (los perfiles no se degradan)."""
        from color_design import (
            FONDO_ALERT_DIALOG,
            BORDE_TEXTFIELDS_COLOR,
            TEXTO_COLOR_GENERICO,
            BOTONES_GENERICOS_COLOR,
            BOTONES_GENERICOS_HOVER_COLOR,
            BOTONES_GENERICOS_OVERLAY_COLOR,
            BOTONES_GENERICOS_FONDO_COLOR,
        )
        from i18n import t

        pending = self._pending_missing_excel
        if not pending:
            return
        missing_path = pending.get("missing_path")
        project_data = pending.get("project_data", {})
        filename = os.path.basename(missing_path) if missing_path else ""

        _btn_style = ft.ButtonStyle(
            color={
                ft.ControlState.DEFAULT: BOTONES_GENERICOS_COLOR,
                "hovered": BOTONES_GENERICOS_HOVER_COLOR,
            },
            overlay_color=BOTONES_GENERICOS_OVERLAY_COLOR,
            padding=ft.Padding(0, 0, 0, 0),
            shape=ft.RoundedRectangleBorder(radius=10),
        )

        async def on_browse(e):
            # Ocultar el diálogo base; el estado persiste para procesar el resultado.
            if pending.get("overlay_ref") and pending["overlay_ref"][0] in self.page.overlay:
                self.page.overlay.remove(pending["overlay_ref"][0])
                self.page.update()
            files = await self.excel_missing_file_picker.pick_files(
                allow_multiple=False,
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["xlsx", "xls", "csv"],
                dialog_title=t("Seleccionar archivo Excel"),
                initial_directory=get_last_file_dialog_path(),
            )
            self._on_excel_missing_pick_result(files)

        def on_skip(e):
            # Continuar sin Excel: los perfiles conservan su vinculación a la
            # columna (no se degradan); el visor muestra la muestra hasta cargar uno.
            self._finalize_excel_missing_load()

        body_children = [
            ft.Row(
                [
                    ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, color="#FFC107", size=20),
                    ft.Text(
                        t("excel_missing_title"),
                        weight=ft.FontWeight.BOLD,
                        size=16,
                        color=TEXTO_COLOR_GENERICO,
                    ),
                ],
                spacing=10,
            ),
            ft.Container(height=10),
            ft.Text(
                t("excel_missing_message").format(filename=filename),
                size=13,
                color=TEXTO_COLOR_GENERICO,
            ),
        ]

        required = self._collect_required_excel_columns(project_data)
        if required:
            body_children.append(ft.Container(height=8))
            body_children.append(
                ft.Text(
                    t("excel_missing_columns_needed").format(
                        ", ".join(sorted(required))
                    ),
                    size=12,
                    color=TEXTO_COLOR_GENERICO,
                )
            )

        body_children.append(ft.Container(height=8))
        body_children.append(
            ft.Text(
                t("excel_missing_profiles_note"),
                size=12,
                color=TEXTO_COLOR_GENERICO,
                italic=True,
            )
        )
        body_children.append(ft.Container(height=15))
        body_children.append(
            ft.Row(
                [
                    ft.Button(
                        t("excel_missing_browse"),
                        on_click=on_browse,
                        width=150,
                        bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
                        style=_btn_style,
                    ),
                    ft.Button(
                        t("continue"),
                        on_click=on_skip,
                        width=150,
                        bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
                        style=_btn_style,
                    ),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=15,
            )
        )

        popup_content = ft.Container(
            content=ft.Column(
                body_children,
                tight=True,
                spacing=0,
            ),
            width=460,
            padding=ft.Padding(24, 20, 24, 20),
            bgcolor=FONDO_ALERT_DIALOG,
            border_radius=12,
            border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
        )

        overlay = ft.Container(
            content=ft.Stack(
                [
                    ft.GestureDetector(
                        on_tap=on_skip,
                        content=ft.Container(
                            expand=True,
                            bgcolor=ft.Colors.with_opacity(0.45, TEXTO_COLOR_GENERICO),
                        ),
                    ),
                    ft.Container(
                        content=popup_content,
                        alignment=ft.Alignment.CENTER,
                        expand=True,
                    ),
                ],
            ),
            expand=True,
        )

        pending["overlay_ref"] = [overlay]
        self.page.overlay.append(overlay)
        self.page.update()

    def _on_excel_missing_pick_result(self, e):
        """Callback al elegir un Excel para sustituir el faltante del proyecto."""
        files = getattr(e, "files", e) or []
        if not files or not files[0].path:
            self._show_missing_excel_dialog()
            return
        path = files[0].path
        set_last_file_dialog_path(path)

        ok, msg = self.excel_manager.load(path)
        if not ok:
            self._show_excel_missing_aux_popup(
                t("Error al cargar archivo"), msg, reopen=True
            )
            return

        required = self._collect_required_excel_columns(
            self._pending_missing_excel.get("project_data", {})
            if self._pending_missing_excel else {}
        )
        if required:
            missing = required - set(self.excel_manager.columns)
            if missing:
                self._show_excel_missing_aux_popup(
                    t("excel_missing_cols_title"),
                    t("excel_missing_cols_message").format(
                        ", ".join(sorted(missing))
                    ),
                    reopen=True,
                )
                return

        self._apply_excel_columns_to_managers()

        # Validar filas vs páginas necesarias (mismo patrón que la carga)
        needed = self._get_required_rows_count()
        rows = self.excel_manager.row_count
        if rows < needed:
            missing_pages = needed - rows
            self._show_excel_missing_aux_popup(
                t("Menos filas que paginas"),
                t("El archivo tiene {0} filas pero hay {1} paginas.\nLas {2} paginas sin datos no tendran texto variable.\n\n¿Desea continuar?").format(rows, needed, missing_pages),
                on_accept=self._finalize_excel_missing_load,
            )
        elif rows > needed:
            extra = rows - needed
            self._show_excel_missing_aux_popup(
                t("Mas filas que paginas"),
                t("El archivo tiene {0} filas pero solo hay {1} paginas.\nSe perderan las {2} filas restantes.\n\n¿Desea continuar?").format(rows, needed, extra),
                on_accept=self._finalize_excel_missing_load,
            )
        else:
            self._finalize_excel_missing_load()

    def _get_required_rows_count(self) -> int:
        """Número de filas/páginas necesarias según global_settings (copia de
        _calculate_total_pages pero devolviendo el valor)."""
        try:
            start = self.global_settings.get("start", 1)
            end = self.global_settings.get("end", 1)
            increment = self.global_settings.get("increment", 1)
            copies = self.global_settings.get("copies", 1)
            if increment == 0:
                increment = 1
            numeros_en_rango = ((end - start) // increment) + 1
            return numeros_en_rango * copies
        except (ValueError, ZeroDivisionError):
            return 1

    def _finalize_excel_missing_load(self):
        """Cierra todos los overlays del flujo y limpia el estado excel faltante."""
        pending = self._pending_missing_excel
        if pending:
            for key in ("overlay_ref", "aux_ref"):
                ref = pending.get(key)
                if ref and ref[0] in self.page.overlay:
                    self.page.overlay.remove(ref[0])
            self.page.update()
        self._pending_missing_excel = None
        self._redraw_excel_dependent_ui()

    def _show_excel_missing_aux_popup(self, title: str, message: str, on_accept=None, reopen=False):
        """Popup encima del flujo: solo Aceptar (error) o Aceptar/Cancelar (confirmación).
        reopen=True → el diálogo base de búsqueda vuelve a mostrarse al cancelar."""
        from color_design import (
            FONDO_ALERT_DIALOG,
            BORDE_TEXTFIELDS_COLOR,
            TEXTO_COLOR_GENERICO,
            BOTONES_GENERICOS_COLOR,
            BOTONES_GENERICOS_HOVER_COLOR,
            BOTONES_GENERICOS_OVERLAY_COLOR,
            BOTONES_GENERICOS_FONDO_COLOR,
        )
        from i18n import t

        _btn_style = ft.ButtonStyle(
            color={ft.ControlState.DEFAULT: BOTONES_GENERICOS_COLOR, "hovered": BOTONES_GENERICOS_HOVER_COLOR},
            overlay_color=BOTONES_GENERICOS_OVERLAY_COLOR,
            padding=ft.Padding(0, 0, 0, 0),
            shape=ft.RoundedRectangleBorder(radius=10),
        )

        def _close():
            if aux_ref and aux_ref[0] in self.page.overlay:
                self.page.overlay.remove(aux_ref[0])
                self.page.update()

        def on_ok(e):
            _close()
            if on_accept:
                on_accept()
            elif reopen:
                self._show_missing_excel_dialog()

        def on_cancel(e):
            _close()
            self._show_missing_excel_dialog()

        buttons = [
            ft.Button(t("Aceptar"), on_click=on_ok, width=110,
                bgcolor=BOTONES_GENERICOS_FONDO_COLOR, style=_btn_style)
        ]
        if on_accept:
            buttons.insert(0, ft.Button(t("Cancelar"), on_click=on_cancel, width=110,
                bgcolor=BOTONES_GENERICOS_FONDO_COLOR, style=_btn_style))

        popup_content = ft.Container(
            content=ft.Column(
                [
                    ft.Text(title, weight=ft.FontWeight.BOLD, size=16, color=TEXTO_COLOR_GENERICO),
                    ft.Container(height=10),
                    ft.Text(message, size=13, color=TEXTO_COLOR_GENERICO),
                    ft.Container(height=15),
                    ft.Row(buttons, alignment=ft.MainAxisAlignment.CENTER, spacing=15),
                ],
                tight=True,
                spacing=0,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            width=420,
            padding=ft.Padding(24, 20, 24, 20),
            bgcolor=FONDO_ALERT_DIALOG,
            border_radius=12,
            border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
        )
        aux_overlay = ft.Container(
            content=ft.Stack(
                [
                    ft.GestureDetector(
                        on_tap=(on_cancel if on_accept else on_ok),
                        content=ft.Container(expand=True, bgcolor=ft.Colors.with_opacity(0.45, TEXTO_COLOR_GENERICO)),
                    ),
                    ft.Container(content=popup_content, alignment=ft.Alignment.CENTER, expand=True),
                ],
            ),
            expand=True,
        )
        aux_ref = [aux_overlay]
        if self._pending_missing_excel:
            self._pending_missing_excel["aux_ref"] = aux_ref
        self.page.overlay.append(aux_overlay)
        self.page.update()

    def _redraw_excel_dependent_ui(self):
        """Re-render tras cargar el Excel: numeradoras y viewer."""
        try:
            self._update_all_numeradoras()
        except Exception:
            pass
        try:
            if getattr(self, "viewer_callback", None):
                self.viewer_callback._redraw_all()
        except Exception:
            pass
        try:
            self.page.update()
        except Exception:
            pass

    def _on_bg_missing_pick_result(self, e):
        """Callback cuando el usuario selecciona un archivo en el diálogo de fondo perdido."""
        files = getattr(e, "files", e) or []
        if not files or not files[0].path:
            return

        face_name = self._pending_missing_bg_face
        config = self._pending_missing_bg_config
        if not face_name or not config:
            return

        path = files[0].path
        set_last_file_dialog_path(path)
        manager = self.background_image_managers[face_name]
        manager.image_path = path
        manager.source_type = "pdf" if path.lower().endswith(".pdf") else "image"
        manager.image_loaded = True
        try:
            manager._generate_base64()
        except Exception as ex:
            print(f"[LOAD] Error generando base64 para fondo: {ex}")
            manager.image_loaded = False

        if manager.image_loaded:
            self._on_background_image_change()

        if (
            self._pending_missing_bg_overlay_ref
            and self._pending_missing_bg_overlay_ref[0]
        ):
            try:
                self.page.overlay.remove(self._pending_missing_bg_overlay_ref[0])
            except Exception:
                pass
            self.page.update()

        self._pending_missing_bg_face = None
        self._pending_missing_bg_config = None
        self._pending_missing_bg_overlay_ref = None

        self._show_next_missing_background_dialog()

    def _show_next_missing_background_dialog(self):
        """Muestra el siguiente diálogo de fondo perdido en la cola."""
        if not self._pending_missing_backgrounds:
            return

        face_name, config = self._pending_missing_backgrounds.pop(0)
        saved_path = config.get("path", "")

        from color_design import (
            FONDO_ALERT_DIALOG,
            BORDE_TEXTFIELDS_COLOR,
            TEXTO_COLOR_GENERICO,
            BOTONES_GENERICOS_COLOR,
            BOTONES_GENERICOS_HOVER_COLOR,
            BOTONES_GENERICOS_OVERLAY_COLOR,
            BOTONES_GENERICOS_FONDO_COLOR,
        )
        from i18n import t

        filename = os.path.basename(saved_path)

        overlay_ref: list = [None]

        def _close():
            if overlay_ref[0] and overlay_ref[0] in self.page.overlay:
                try:
                    self.page.overlay.remove(overlay_ref[0])
                    self.page.update()
                except Exception:
                    pass

        def _on_skip(e):
            _close()
            self._show_next_missing_background_dialog()

        async def _on_browse(e):
            self._pending_missing_bg_face = face_name
            self._pending_missing_bg_config = config
            self._pending_missing_bg_overlay_ref = overlay_ref
            files = await self.bg_missing_file_picker.pick_files(
                allow_multiple=False,
                allowed_extensions=["pdf", "png", "jpg", "jpeg", "bmp"],
                dialog_title=t("Seleccionar fondo para {face}").format(face=face_name),
                initial_directory=get_last_file_dialog_path(),
            )
            self._on_bg_missing_pick_result(files)

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
                    ft.Icon(
                        ft.Icons.WARNING_AMBER_ROUNDED,
                        color=TEXTO_COLOR_GENERICO,
                        size=24,
                    ),
                    ft.Container(height=8),
                    ft.Text(
                        t("background_missing_title"),
                        weight=ft.FontWeight.BOLD,
                        size=16,
                        color=TEXTO_COLOR_GENERICO,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    ft.Container(height=14),
                    ft.Text(
                        t("background_missing_message").format(
                            face=face_name, filename=filename
                        ),
                        size=13,
                        color=TEXTO_COLOR_GENERICO,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    ft.Container(height=24),
                    ft.Row(
                        [
                            ft.Button(
                                t("browse"),
                                on_click=_on_browse,
                                width=140,
                                bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
                                style=_btn_style,
                            ),
                            ft.Button(
                                t("continue_without"),
                                on_click=_on_skip,
                                width=140,
                                bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
                                style=_btn_style,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                        spacing=24,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                tight=True,
                spacing=0,
            ),
            width=450,
            padding=ft.Padding(36, 28, 36, 28),
            bgcolor=FONDO_ALERT_DIALOG,
            border_radius=12,
        )

        overlay = ft.Container(
            content=ft.Stack(
                [
                    ft.GestureDetector(
                        on_tap=_on_skip,
                        content=ft.Container(
                            expand=True,
                            bgcolor=ft.Colors.with_opacity(0.45, TEXTO_COLOR_GENERICO),
                        ),
                    ),
                    ft.Container(
                        content=popup_content,
                        alignment=ft.Alignment.CENTER,
                        expand=True,
                    ),
                ],
            ),
            expand=True,
        )

        overlay_ref[0] = overlay
        self.page.overlay.append(overlay)
        self.page.update()

    def _load_project_from_file(self, file_path: str):
        """Carga todos los datos del proyecto desde un archivo JSON"""
        print(f"[LOAD] Cargando proyecto desde: {file_path}")

        # Leer archivo
        with open(file_path, "r", encoding="utf-8") as f:
            project_data = json.load(f)

        # Usar método común de carga
        self._load_project_data(project_data, file_path)

    def _collect_required_excel_columns(self, project_data: dict) -> set:
        """Columnas (por nombre) que el proyecto necesita del Excel, leídas del
        diccionario crudo SIN mutar los perfiles (para no perder config)."""
        required: set = set()
        for p in project_data.get("barcode_profiles", []):
            if p.get("value_source") == "excel" and p.get("excel_column"):
                required.add(p["excel_column"])
        for p in project_data.get("variable_text_profiles", []):
            if p.get("excel_column"):
                required.add(p["excel_column"])
            required.update(extract_used_columns(p.get("sample_text", "")))
        return required

    def _apply_excel_columns_to_managers(self):
        """Aplica las columnas del Excel cargado a managers de barcode y VT."""
        columns = self.excel_manager.columns if self.excel_manager.is_loaded else []
        if hasattr(self, "barcode_ui_manager"):
            self.barcode_ui_manager.profile_manager.set_excel_columns(columns)
            for _bp in self.barcode_ui_manager.profile_manager.profiles:
                if _bp.value_source == "excel":
                    self._recalc_profile_minimums(_bp)
        if hasattr(self, "variable_text_ui_manager"):
            self.variable_text_ui_manager.profile_manager.set_excel_columns(columns)

    def _load_project_data(self, project_data: dict, project_file_path: str = None):
        """Método común para cargar datos del proyecto desde un diccionario

        Args:
            project_data: Datos del proyecto
            project_file_path: Ruta del archivo de proyecto (para resolver imágenes)
        """

        # Limpiar datos del proyecto anterior
        self.extracted_spot_colors = []
        if hasattr(self, "text_style_manager"):
            self.text_style_manager.set_extracted_spots(self.extracted_spot_colors)
        if hasattr(self, "barcode_ui_manager"):
            self.barcode_ui_manager.profile_manager.set_extracted_spots(
                self.extracted_spot_colors
            )
        if hasattr(self, "variable_text_ui_manager"):
            self.variable_text_ui_manager.profile_manager.set_extracted_spots(
                self.extracted_spot_colors
            )

        # Limpiar Excel cargado anteriormente
        self.excel_manager.clear()

        # Resetear configuración de caras (evita heredar reverse del proyecto anterior
        # si el archivo cargado no trae face_settings)
        self.face_settings = {
            "CARA": {"reverse": False},
            "DORSO": {"reverse": False},
        }

        # Verificar versión
        version_str = project_data.get("version", "1.0")
        try:
            version = tuple(int(p) for p in version_str.split("."))
        except (ValueError, AttributeError):
            version = (1, 0)
        print(f"[LOAD] Versión del archivo: {version_str}")

        # Normaliza nombres de perfiles para evitar colisiones internas del proyecto.
        # Importante: esto NO mezcla con preferencias; solo sanea lo que viene en el archivo.
        def _ensure_unique_profile_names(profiles, profile_kind: str):
            used_names = set()
            renamed = []
            for p in profiles:
                base_name = (getattr(p, "name", "") or "<Default>").strip()
                new_name = base_name
                suffix = 2
                while new_name in used_names:
                    new_name = f"{base_name} ({suffix})"
                    suffix += 1
                if new_name != base_name:
                    try:
                        p.name = new_name
                        renamed.append((base_name, new_name))
                    except Exception:
                        pass
                used_names.add(new_name)

            if renamed:
                print(
                    f"[LOAD] ⚠️ Detectados nombres duplicados en perfiles de {profile_kind}. "
                    f"Renombrados: {renamed}"
                )
            return profiles

        # Cargar configuración global
        self.double_sided_enabled = project_data.get("double_sided_enabled", False)
        self.current_face = project_data.get("current_face", "CARA")

        # Cargar paper settings
        paper = project_data.get("paper_settings", {})
        self.page_width_mm = paper.get("width", DEFAULT_PAGE_WIDTH_MM)
        self.page_height_mm = paper.get("height", DEFAULT_PAGE_HEIGHT_MM)
        self.bleed_mm = paper.get("bleed", DEFAULT_BLEED_MM)
        self.page_size_name = paper.get("size_name", DEFAULT_PAGE_SIZE_NAME)
        self.current_unit = paper.get("unit", UNIT_MM)

        # La unidad global se mantiene en `self.current_unit` (selección en Preferencias)

        # Actualizar unidad de las reglas si están habilitadas
        if ENABLE_RULERS:
            self.interactive_viewer.set_ruler_unit(self.current_unit)

        # Cargar configuración global (numeración)
        loaded_global = project_data.get("global_settings", {})
        if loaded_global:
            self.global_settings.update(loaded_global)

            # reverse pertenece a la app (padre): garantizar key y sincronizar
            # las copias espejo de face_settings para pasar la data correcta.
            self.global_settings.setdefault("reverse", False)
            self.face_settings["CARA"]["reverse"] = self.global_settings["reverse"]
            self.face_settings["DORSO"]["reverse"] = self.global_settings["reverse"]

            # Actualizar UI con valores cargados (importante!)
            self.start_field.value = str(
                self.global_settings.get("start", DEFAULT_START_NUMBER)
            )
            self.end_field.value = str(
                self.global_settings.get("end", DEFAULT_END_NUMBER)
            )
            self.increment_field.value = str(
                self.global_settings.get("increment", DEFAULT_INCREMENT)
            )
            self.copies_field.value = str(
                self.global_settings.get("copies", DEFAULT_COPIES)
            )

            self.start_field.update()
            self.end_field.update()
            self.increment_field.update()
            self.copies_field.update()

            # Recalcular páginas
            self._calculate_total_pages()

        # v2: convertir perfiles unificados a formato v1 para reutilizar carga existente
        if version >= (2, 0) and "perfiles" in project_data:
            perfiles = project_data["perfiles"]
            if "numeros" in perfiles:
                project_data["text_styles"] = [
                    {"name": name, **data} for name, data in perfiles["numeros"].items()
                ]
            if "codigos de barras" in perfiles:
                project_data["barcode_profiles"] = [
                    {"name": name, **data}
                    for name, data in perfiles["codigos de barras"].items()
                ]
            if "textos variables" in perfiles:
                project_data["variable_text_profiles"] = [
                    {"name": name, **data}
                    for name, data in perfiles["textos variables"].items()
                ]

        # Cargar text styles
        # Verificar explícitamente si existe la clave, incluso si es lista vacía
        if "text_styles" in project_data:
            styles_data = project_data["text_styles"]
            try:
                from ui.text_settings_dialog import TextStyle

                # Obtener campos válidos de TextStyle para filtrar (compatibilidad)
                valid_fields = TextStyle.__dataclass_fields__.keys()

                new_profiles = []
                for style_dict in styles_data:
                    # Migración: trabajos viejos guardaban font_name, ahora es font_family
                    if "font_name" in style_dict and "font_family" not in style_dict:
                        style_dict = dict(style_dict)
                        style_dict["font_family"] = style_dict.pop("font_name")
                    # Filtrar claves que no pertenecen al dataclass actual
                    filtered_dict = {
                        k: v for k, v in style_dict.items() if k in valid_fields
                    }

                    # Manejar caso de thousands_separator si falta (aunque tiene default en clase, aseguramos)
                    if "thousands_separator" not in filtered_dict:
                        filtered_dict["thousands_separator"] = "normal"

                    new_profiles.append(TextStyle(**filtered_dict))

                new_profiles = _ensure_unique_profile_names(new_profiles, "texto")

                if new_profiles:
                    self.text_style_manager.profiles = new_profiles
                    self.text_style_manager.selected_profile_index = 0
                    self.text_style_manager.current_style = new_profiles[0].copy()
                    self.available_text_styles = [
                        p.name for p in self.text_style_manager.profiles
                    ]
                    print(
                        f"[LOAD] Perfiles de texto sobrescritos con datos del proyecto: {len(new_profiles)} perfiles"
                    )

                    # Resolver rutas de fuentes para los perfiles cargados
                    try:
                        # Fuentes del sistema pueden haber cambiado desde el arranque
                        # (p.ej. activadas en un gestor de fuentes externo) — el
                        # chequeo de faltantes usa available_fonts (foto del startup).
                        try:
                            self.text_style_manager._refresh_system_fonts()
                        except Exception as e_refresh:
                            print(
                                f"[LOAD] ⚠️ Refresh fuentes del sistema: {e_refresh}"
                            )

                        self.text_style_manager._resolve_profiles()
                        print(
                            "[LOAD] Perfiles resueltos y fuentes registradas correctamente."
                        )

                        # Validar fuentes del proyecto contra las instaladas en el equipo
                        fuentes_sistema = self.text_style_manager.available_fonts or {}
                        missing_fonts = []
                        for profile in new_profiles:
                            if profile.font_family not in fuentes_sistema:
                                entry = (
                                    f"{profile.font_family} ({profile.font_style})"
                                )
                                if entry not in missing_fonts:
                                    missing_fonts.append(entry)
                        if missing_fonts:
                            missing_list = ", ".join(missing_fonts)
                            print(
                                f"[LOAD] ⚠️ Fuentes no instaladas en este equipo: {missing_list}"
                            )
                            self._show_missing_fonts_dialog(missing_fonts)
                    except Exception as e:
                        print(f"[LOAD] ⚠️ Error resolviendo perfiles: {e}")
                else:
                    print("[LOAD] La lista de estilos en el archivo estaba vacía")

            except Exception as e:
                print(
                    f"[LOAD] ¡ERROR CRÍTICO! Fallo al deserializar estilos de texto: {e}"
                )
                import traceback

                traceback.print_exc()
        else:
            print(
                "[LOAD] No se encontraron datos de 'text_styles' en el proyecto (usando defaults actuales)"
            )

        # Cargar perfiles de código de barras
        if "barcode_profiles" in project_data:
            profiles_data = project_data["barcode_profiles"]
            try:
                new_profiles = []
                for pd in profiles_data:
                    new_profiles.append(BarcodeProfile.from_dict(pd))

                new_profiles = _ensure_unique_profile_names(
                    new_profiles, "código de barras"
                )

                if new_profiles:
                    self.barcode_ui_manager.profile_manager.profiles = new_profiles
                    self.barcode_ui_manager.profile_manager.selected_profile_index = 0
                    self.barcode_ui_manager.profile_manager.current_profile = (
                        new_profiles[0]
                    )
                    print(
                        f"[LOAD] Perfiles de código de barras sobrescritos con datos del proyecto: {len(new_profiles)} perfiles"
                    )

                    # Refrescar el dropdown
                    self._populate_barcode_profile_dropdown()
            except Exception as e:
                print(
                    f"[LOAD] ¡ERROR CRÍTICO! Fallo al deserializar perfiles de código de barras: {e}"
                )
                import traceback

                traceback.print_exc()
        else:
            print(
                "[LOAD] No se encontraron datos de 'barcode_profiles' en el proyecto (usando defaults actuales)"
            )

        # Cargar perfiles de texto variable
        if "variable_text_profiles" in project_data:
            profiles_data = project_data["variable_text_profiles"]
            try:
                from ui.variable_text_settings_dialog import (
                    VariableTextProfile,
                )

                new_profiles = []
                for pd in profiles_data:
                    new_profiles.append(VariableTextProfile.from_dict(pd))

                new_profiles = _ensure_unique_profile_names(
                    new_profiles, "texto variable"
                )

                if new_profiles:
                    self.variable_text_ui_manager.profile_manager.profiles = (
                        new_profiles
                    )
                    self.variable_text_ui_manager.profile_manager.selected_profile_index = (
                        0
                    )
                    self.variable_text_ui_manager.profile_manager.current_profile = (
                        new_profiles[0].copy()
                    )
                    print(
                        f"[LOAD] Perfiles de texto variable sobrescritos con datos del proyecto: {len(new_profiles)} perfiles"
                    )

                    self._populate_variable_text_profile_dropdown()
            except Exception as e:
                print(
                    f"[LOAD] ¡ERROR CRÍTICO! Fallo al deserializar perfiles de texto variable: {e}"
                )
                import traceback

                traceback.print_exc()
        else:
            print(
                "[LOAD] No se encontraron datos de 'variable_text_profiles' en el proyecto (usando defaults actuales)"
            )

        # Resolver rutas de fuentes para perfiles de texto variable
        if hasattr(self, "variable_text_ui_manager") and self.variable_text_ui_manager:
            try:
                self.variable_text_ui_manager.profile_manager._refresh_system_fonts()
            except Exception as e:
                print(f"[LOAD] ⚠️ Refresh fuentes VT: {e}")
            self.variable_text_ui_manager.profile_manager._resolve_profiles()

        # Cargar datos de Excel si existe la ruta en el proyecto
        excel_path = project_data.get("excel_path")
        if excel_path:
            # Resolver la ruta (puede ser relativa al proyecto)
            resolved_path = self._resolve_image_path(excel_path, project_file_path)
            if resolved_path:
                ok, msg = self.excel_manager.load(resolved_path)
                if ok:
                    self._apply_excel_columns_to_managers()
                    print(f"[LOAD] Excel cargado: {resolved_path} ({msg})")
                else:
                    # No degradar aún: ofrecer buscar/cargar el archivo (post-carga).
                    print(f"[LOAD] Error al cargar Excel: {msg}")
                    self._pending_missing_excel = {
                        "project_data": project_data,
                        "missing_path": resolved_path,
                    }
            else:
                print(f"[LOAD] Archivo Excel no encontrado: {excel_path}")
                self._pending_missing_excel = {
                    "project_data": project_data,
                    "missing_path": excel_path,
                }

        # Cargar datos de CARA (convertir keys de string a int)
        cara_data = project_data.get("CARA", {})
        cara_positions = cara_data.get("positions", {})
        self.positions["CARA"] = {int(k): v for k, v in cara_positions.items()}
        self.face_settings["CARA"] = cara_data.get(
            "face_settings", self.face_settings["CARA"]
        )
        bg_cara = cara_data.get("background_image", {})
        if bg_cara:
            # Siempre intentar cargar la configuración (puede tener base64 ya incluido)
            if bg_cara.get("path") and project_file_path:
                # Intentar resolver ruta pero no bloquear si falla
                resolved_path = self._resolve_image_path(
                    bg_cara["path"], project_file_path
                )
                if resolved_path:
                    bg_cara["path"] = resolved_path
                else:
                    self._pending_missing_backgrounds.append(("CARA", bg_cara))

            # Cargar al manager (él decidirá si genera el base64 o usa el existente)
            self.background_image_managers["CARA"].load_config(bg_cara)
        else:
            # Limpiar si el proyecto no trae fondo para esta cara
            self.background_image_managers["CARA"].clear_image()

        # Cargar datos de DORSO (convertir keys de string a int)
        dorso_data = project_data.get("DORSO", {})
        dorso_positions = dorso_data.get("positions", {})
        self.positions["DORSO"] = {int(k): v for k, v in dorso_positions.items()}
        self.face_settings["DORSO"] = dorso_data.get(
            "face_settings", self.face_settings["DORSO"]
        )

        # v2: expandir datos de perfil inline en posiciones
        if version >= (2, 0):
            from dataclasses import asdict

            for face in ("CARA", "DORSO"):
                for pos_id, pos_data in self.positions.get(face, {}).items():
                    if not isinstance(pos_data, dict):
                        continue
                    ptype = pos_data.get("type", "number")
                    if ptype == "number":
                        style_name = pos_data.get("text_style", "<Default>")
                        profile = next(
                            (
                                p
                                for p in self.text_style_manager.profiles
                                if p.name == style_name
                            ),
                            None,
                        )
                        if profile:
                            for k, v in asdict(profile).items():
                                pos_data.setdefault(k, v)
                    elif ptype == "barcode":
                        pname = pos_data.get("profile_name", "<Default>")
                        profile = self.barcode_ui_manager._find_profile(pname)
                        if profile:
                            for k, v in profile.to_dict().items():
                                pos_data.setdefault(k, v)
                    elif ptype == "variable_text":
                        pname = pos_data.get("profile_name", "<Default>")
                        profile = self.variable_text_ui_manager._find_profile(pname)
                        if profile:
                            for k, v in profile.to_dict().items():
                                pos_data.setdefault(k, v)

        # Migration v1: sync pos_data dimension overrides into profiles
        if version < (2, 0):
            try:
                for face in ("CARA", "DORSO"):
                    for pos_id, pos_data in self.positions.get(face, {}).items():
                        if (
                            pos_data.get("type") == "barcode"
                            and "bar_width" in pos_data
                        ):
                            profile_name = pos_data.get("profile_name", "<Default>")
                            profile = self.barcode_ui_manager._find_profile(
                                profile_name
                            )
                            if profile:
                                bw = pos_data["bar_width"]
                                if profile.bar_width != bw:
                                    profile.bar_width = bw
                                    profile.pdf417_size = bw
                                    print(
                                        f"[LOAD MIGRATE] Pos {pos_id}: bar_width {profile.bar_width} → {bw}"
                                    )
                                bh = pos_data.get("bar_height", 30.0)
                                if profile.bar_height != bh:
                                    profile.bar_height = bh
                                    profile.pdf417_height = bh
                                    print(
                                        f"[LOAD MIGRATE] Pos {pos_id}: bar_height {profile.bar_height} → {bh}"
                                    )
            except Exception as e:
                print(f"[LOAD MIGRATE] Warning: {e}")

        # Validar referencias de perfil en posiciones cargadas.
        # Si una posición apunta a un nombre inexistente, usar fallback seguro.
        try:
            valid_text_styles = {p.name for p in self.text_style_manager.profiles}
        except Exception:
            valid_text_styles = {"<Default>"}

        try:
            valid_barcode_profiles = {
                p.name for p in self.barcode_ui_manager.profile_manager.profiles
            }
        except Exception:
            valid_barcode_profiles = {"<Default>"}

        try:
            valid_variable_text_profiles = {
                p.name for p in self.variable_text_ui_manager.profile_manager.profiles
            }
        except Exception:
            valid_variable_text_profiles = {"<Default>"}

        for face in ["CARA", "DORSO"]:
            for _, pos_data in self.positions[face].items():
                pos_data.setdefault("locked", False)
                pos_type = pos_data.get("type", "number")
                if pos_type == "barcode":
                    profile_name = pos_data.get("profile_name", "<Default>")
                    if profile_name not in valid_barcode_profiles:
                        fallback = "<Default>"
                        if (
                            fallback not in valid_barcode_profiles
                            and valid_barcode_profiles
                        ):
                            fallback = next(iter(valid_barcode_profiles))
                        pos_data["profile_name"] = fallback
                        print(
                            f"[LOAD] ⚠️ Barcode con perfil inexistente '{profile_name}', "
                            f"usando '{fallback}'"
                        )
                elif pos_type == "variable_text":
                    profile_name = pos_data.get("profile_name", "<Default>")
                    if profile_name not in valid_variable_text_profiles:
                        fallback = "<Default>"
                        if (
                            fallback not in valid_variable_text_profiles
                            and valid_variable_text_profiles
                        ):
                            fallback = next(iter(valid_variable_text_profiles))
                        pos_data["profile_name"] = fallback
                        print(
                            f"[LOAD] ⚠️ Texto variable con perfil inexistente '{profile_name}', "
                            f"usando '{fallback}'"
                        )
                    final_pname = pos_data.get("profile_name", "<Default>")
                    vt_profile = self.variable_text_ui_manager._find_profile(
                        final_pname
                    )
                    if vt_profile:
                        pos_data.setdefault(
                            "text_case_filter",
                            getattr(vt_profile, "text_case_filter", ""),
                        )
                else:
                    style_name = pos_data.get("text_style", "<Default>")
                    if style_name not in valid_text_styles:
                        fallback = "<Default>"
                        if fallback not in valid_text_styles and valid_text_styles:
                            fallback = next(iter(valid_text_styles))
                        pos_data["text_style"] = fallback
                        print(
                            f"[LOAD] ⚠️ Numeradora con estilo inexistente '{style_name}', "
                            f"usando '{fallback}'"
                        )

        bg_dorso = dorso_data.get("background_image", {})
        if bg_dorso:
            # Siempre intentar cargar la configuración
            if bg_dorso.get("path") and project_file_path:
                # Intentar resolver ruta
                resolved_path = self._resolve_image_path(
                    bg_dorso["path"], project_file_path
                )
                if resolved_path:
                    bg_dorso["path"] = resolved_path
                else:
                    self._pending_missing_backgrounds.append(("DORSO", bg_dorso))

            # Cargar al manager
            self.background_image_managers["DORSO"].load_config(bg_dorso)
        else:
            # Limpiar si el proyecto no trae fondo para esta cara
            self.background_image_managers["DORSO"].clear_image()

        # Sincronizar con preferencias globales (como archivo físico)
        try:
            cache_dir = get_background_cache_dir()
            for face in ["CARA", "DORSO"]:
                manager = self.background_image_managers[face]
                if manager.image_loaded:
                    cache_path = os.path.join(cache_dir, f"cache_bg_{face.lower()}.png")
                    # Asegurar que el manager tenga generado el base64 temporal
                    try:
                        # método interno: genera `image_base64` usado por el viewer
                        manager._generate_base64()
                    except Exception:
                        pass
                    manager.save_preview_to_file(cache_path)

            # Guardar configuraciones (sin base64 para no inflar el JSON)
            cara_config = self.background_image_managers["CARA"].get_image_config()
            dorso_config = self.background_image_managers["DORSO"].get_image_config()

            # Limpiar base64 para las preferencias globales
            if "base64" in cara_config:
                del cara_config["base64"]
            if "base64" in dorso_config:
                del dorso_config["base64"]

            save_last_backgrounds(cara_config, dorso_config)
        except Exception as e:
            print(f"[PREFERENCES] Error al sincronizar fondos tras carga: {e}")

        # Actualizar next_position_number
        if self.positions["CARA"]:
            max_id_cara = max([int(k) for k in self.positions["CARA"].keys()])
            self.next_position_number["CARA"] = max_id_cara + 1
        if self.positions["DORSO"]:
            max_id_dorso = max([int(k) for k in self.positions["DORSO"].keys()])
            self.next_position_number["DORSO"] = max_id_dorso + 1

        # Actualizar tamaño de página en el viewer (necesita tamaño total con sangre)
        self.interactive_viewer.set_page_size(
            self.page_width_mm + (self.bleed_mm * 2),
            self.page_height_mm + (self.bleed_mm * 2),
            self.bleed_mm,
        )
        # Resetear vista completa (zoom + centrado)
        self._reset_view()
        self._update_page_size_text()

        # Actualizar estado de doble cara en UI primero
        if self.double_sided_enabled:
            self.icon_face.disabled = False
            self.icon_double_sided.bgcolor = BOTONES_GENERICOS_OVERLAY_COLOR
            self.icon_double_sided.content.color = BOTONES_GENERICOS_TEXTO_COLOR
            self.double_sided_indicator.visible = True
        else:
            self.icon_face.disabled = True
            self.icon_double_sided.bgcolor = FONDO_TEXTFIELDS_COLOR
            self.icon_double_sided.content.color = TEXTOS_FASE_1_COLOR
            self.double_sided_indicator.visible = False

        # Recrear los items de UI para cada posición cargada
        for face in ["CARA", "DORSO"]:
            for num_id, pos_data in self.positions[face].items():
                pos_type = pos_data.get("type", "number")
                if pos_type in ("barcode", "variable_text"):
                    position_name = pos_data.get(
                        "profile_name", pos_data.get("name", f"Posición {num_id}")
                    )
                else:
                    position_name = pos_data.get(
                        "text_style", pos_data.get("name", f"Posición {num_id}")
                    )

                # Función de click para este item específico (doble click abre diálogo)
                def on_item_click(e, item_num_id=num_id, item_face=face):
                    if self.current_face != item_face:
                        return
                    import time

                    now = time.time()
                    if (
                        self._last_clicked_item == item_num_id
                        and now - self._last_click_item_time < 0.4
                    ):
                        self._last_clicked_item = None
                        self._last_click_item_time = 0.0
                        pos_type = (
                            self.positions.get(item_face, {})
                            .get(item_num_id, {})
                            .get("type", "number")
                        )
                        if pos_type == "barcode":
                            self._on_barcode_double_click(item_num_id)
                        elif pos_type == "variable_text":
                            self._on_variable_text_double_click(item_num_id)
                        else:
                            self._on_numeradora_double_click(item_num_id)
                    else:
                        self._last_clicked_item = item_num_id
                        self._last_click_item_time = now
                        self._on_select_position(item_num_id)

                # Crear item visual para la lista
                pos_type = pos_data.get("type", "number")
                icon_name = {
                    "barcode": ft.CupertinoIcons.BARCODE,
                    "variable_text": ft.Icons.TEXT_FIELDS,
                }.get(pos_type, ft.Icons.TEXT_FIELDS)
                is_locked = pos_data.get("locked", False)
                lock_button = ft.IconButton(
                    icon=ft.Icons.LOCK if is_locked else ft.Icons.LOCK_OPEN,
                    icon_size=14,
                    icon_color=TEXTOS_FASE_1_COLOR,
                    data="lock_toggle",
                    on_click=lambda e, pid=num_id: self._toggle_item_lock(pid),
                    width=22,
                    height=22,
                    padding=0,
                )
                _icon_img_path = get_resource_path(os.path.join("assets", "001_2.png"))
                position_item = ft.Container(
                    key=f"position_{num_id}",
                    content=ft.Row(
                        controls=[
                            (
                                ft.Image(
                                    src=_icon_img_path,
                                    width=14,
                                    height=14,
                                    fit=ft.BoxFit.CONTAIN,
                                    color=TEXTOS_FASE_1_COLOR,
                                )
                                if pos_type == "number"
                                else ft.Icon(
                                    icon=icon_name,
                                    size=14,
                                    color=TEXTOS_FASE_1_COLOR,
                                )
                            ),
                            ft.Text(
                                position_name,
                                size=12,
                                color=TEXTOS_FASE_1_COLOR,
                                expand=True,
                            ),
                            lock_button,
                        ],
                        spacing=6,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    padding=ft.Padding.symmetric(horizontal=8, vertical=4),
                    border=ft.Border.only(
                        bottom=ft.BorderSide(1, BORDE_TEXTFIELDS_COLOR)
                    ),
                    bgcolor=FONDO_CALCULO_FASE_1,
                    on_click=on_item_click,
                )

                # Guardar referencia al item en los datos
                pos_data["item"] = position_item

        # Resetear página actual a 1
        self.current_page = 1
        self.preview_page_field.value = "1"

        # Refrescar la cara actual (esto actualiza la lista visible y restaura numeradoras en viewer)
        # auto_select=False para no seleccionar nada al cargar un trabajo
        self._refresh_current_face(auto_select=False)

        # Actualizar texto de tamaño de página
        self._update_page_size_text()

        # Actualizar controles de doble cara
        self.icon_double_sided.update()
        self.icon_face.update()
        self.double_sided_indicator.update()

        # Actualizar toda la página
        self.page.update()

        print(
            f"[LOAD] Proyecto cargado: {len(self.positions['CARA'])} posiciones en CARA, {len(self.positions['DORSO'])} en DORSO"
        )

        # Iniciar diálogos secuenciales para fondos perdidos
        if self._pending_missing_backgrounds:
            self._show_next_missing_background_dialog()

        # Si falta el Excel del proyecto, ofrecer buscar/cargar uno
        if self._pending_missing_excel:
            self._show_missing_excel_dialog()

    def _on_open_preferences(self, e):
        """Abre el diálogo de preferencias"""
        print("[DIALOG] Abrir preferencias")

        # Dropdown de tamaño de página por defecto
        # Crear opciones: tamaños predefinidos + personalizados
        default_page_size_options = list(PAGE_SIZES.keys())
        if self.custom_sizes:
            # Ordenar personalizados por área (mayor->menor) para el dropdown de preferencias
            pref_sorted = sorted(
                self.custom_sizes.keys(),
                key=lambda n: (self.custom_sizes[n][0] * self.custom_sizes[n][1]),
                reverse=False,
            )
            default_page_size_options.append("─────────────")
            default_page_size_options.extend(pref_sorted)

        # Obtener el tamaño por defecto actual de las preferencias
        startup_settings = get_startup_settings()
        current_default_size = startup_settings.get("page_size", DEFAULT_PAGE_SIZE_NAME)
        current_default_unit = startup_settings.get("unit", UNIT_MM)

        default_page_size_dropdown = self._create_dropdown_compact(
            default_page_size_options,
            current_default_size,
            width=150,
            text_size=14,
        )

        # Contenedor mutable para los campos de offset (se rellenan tras su creación,
        # pero el handler se define aquí para pasarlo al dropdown).
        _pref_offset_refs = []  # [offset_x_field, offset_y_field]
        _pref_prev_unit = [current_default_unit]  # unidad activa dentro del diálogo
        # Labels dinámicas de offset (se actualizan al cambiar la unidad en el diálogo)
        _pref_ox_label = [
            ft.Text(
                f"Offset X ({_unit_abbr(current_default_unit)}):",
                size=11,
                color=TEXTO_COLOR_GENERICO,
            )
        ]
        _pref_oy_label = [
            ft.Text(
                f"Offset Y ({_unit_abbr(current_default_unit)}):",
                size=11,
                color=TEXTO_COLOR_GENERICO,
            )
        ]

        def _on_unit_change_in_dialog(new_unit):
            """Actualiza la visualización de los offsets según la nueva unidad.

            Lee el valor actual del textfield (que puede haber sido editado por
            el usuario), lo convierte a mm usando la unidad activa en el diálogo
            (_pref_prev_unit[0]) y luego lo muestra en la nueva unidad.
            Una sola conversión: valor_visible → mm → nueva_unidad.
            No hay pérdida por encadenamiento porque _pref_prev_unit[0] siempre
            refleja la unidad del valor actualmente visible en el campo.
            """
            if len(_pref_offset_refs) < 2:
                return
            ox_field, oy_field = _pref_offset_refs[0], _pref_offset_refs[1]
            prev_unit = _pref_prev_unit[0]
            try:
                # Convertir el valor visible actual a mm (respetando ediciones del usuario)
                x_mm = convert_to_mm(float(ox_field.value or "0"), prev_unit)
                y_mm = convert_to_mm(float(oy_field.value or "0"), prev_unit)
                # Convertir de mm a la nueva unidad
                x_new = convert_from_mm(x_mm, new_unit)
                y_new = convert_from_mm(y_mm, new_unit)
                fmt = ".1f" if new_unit == UNIT_PX else ".4f"
                ox_field.value = f"{x_new:{fmt}}"
                oy_field.value = f"{y_new:{fmt}}"
                try:
                    ox_field.update()
                    oy_field.update()
                except Exception:
                    pass
                _pref_prev_unit[0] = new_unit
                # Actualizar los labels de offset con la nueva abreviatura
                try:
                    abbr = _unit_abbr(new_unit)
                    _pref_ox_label[0].value = f"Offset X ({abbr}):"
                    _pref_oy_label[0].value = f"Offset Y ({abbr}):"
                    try:
                        _pref_ox_label[0].update()
                        _pref_oy_label[0].update()
                    except Exception:
                        pass
                except Exception:
                    pass
            except Exception:
                pass

        # Dropdown de unidades por defecto
        default_unit_dropdown = self._create_dropdown_compact(
            UNITS,
            current_default_unit,
            width=100,
            text_size=14,
            on_change=_on_unit_change_in_dialog,
        )

        # Dropdown de idioma (nuevo)
        language_options = i18n.get_language_options()

        # Handler: pedir reinicio para aplicar el cambio de idioma
        def _on_language_change(selected_code):
            if selected_code == i18n.get_lang():
                return

            # Crear diálogo de reinicio
            def _do_restart(e):
                # Persistir la selección de idioma y cerrar la app.
                # NO llamar set_language() aquí: el idioma nuevo se aplica
                # al arranque siguiente; así el diálogo de "cambios sin guardar"
                # se muestra en el idioma actual de la sesión.
                try:
                    save_preference("language", selected_code)
                except Exception:
                    pass

                # Invocar el flujo de salida existente para respetar comprobaciones
                try:
                    # Reutilizar lógica existente que verifica cambios y guarda
                    self._on_exit_app(None)
                except Exception:
                    try:
                        import os as _os

                        _os._exit(0)
                    except Exception:
                        pass

            def _do_later(e):
                # Guardar la preferencia seleccionada y cerrar el diálogo.
                try:
                    try:
                        save_preference("language", selected_code)
                    except Exception:
                        pass
                except Exception:
                    pass

                # Actualizar el texto mostrado del dropdown al valor guardado
                try:
                    texto = language_dropdown.content.controls[0]
                    display = next(
                        (
                            lbl
                            for code, lbl in language_options
                            if code == selected_code
                        ),
                        str(selected_code),
                    )
                    texto.value = display
                    texto.data = selected_code
                    texto.update()
                except Exception:
                    pass

                try:
                    self.page.pop_dialog()
                except Exception:
                    try:
                        restart_dialog.open = False
                        self.page.update()
                    except Exception:
                        pass

            restart_dialog = ft.AlertDialog(
                modal=True,
                title=ft.Container(
                    content=ft.Text(
                        t("Restart Required"),
                        size=16,
                        weight=ft.FontWeight.BOLD,
                        color=TEXTO_COLOR_GENERICO,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    alignment=ft.Alignment.CENTER,
                ),
                content=ft.Container(
                    content=ft.Column(
                        [
                            ft.Container(height=6),
                            ft.Text(
                                t("Please close the app to apply the language change"),
                                size=14,
                                color=TEXTOS_FASE_1_COLOR,
                                text_align=ft.TextAlign.CENTER,
                            ),
                            ft.Container(height=6),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    width=400,
                    height=100,
                    padding=20,
                ),
                actions=[
                    ft.Button(
                        t("Más tarde"),
                        on_click=_do_later,
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
                    ft.Button(
                        t("Cerrar app"),
                        on_click=_do_restart,
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
                actions_alignment=ft.MainAxisAlignment.CENTER,
                bgcolor=FONDO_ALERT_DIALOG,
            )

            # Usar el mismo patrón que otros diálogos
            try:
                self.page.show_dialog(restart_dialog)
            except Exception:
                try:
                    restart_dialog.open = True
                    self.page.update()
                except Exception as ex2:
                    print(f"[ERROR] No se pudo abrir diálogo reinicio: {ex2}")

        print(
            f"[PREFS_DEBUG] i18n.get_lang() al abrir preferencias: {i18n.get_lang()!r}"
        )
        print(f"[PREFS_DEBUG] lang_options: {language_options}")
        language_dropdown = self._create_dropdown_compact(
            language_options,
            i18n.get_lang(),
            width=120,
            text_size=14,
            on_change=_on_language_change,
        )

        # Crear campos para los valores por defecto - convertir a unidad actual
        offset_x_converted = convert_from_mm(
            self.default_offset_x, current_default_unit
        )
        offset_y_converted = convert_from_mm(
            self.default_offset_y, current_default_unit
        )
        tuning_settings = get_rendering_tuning_settings()
        is_windows_env = platform.system() == "Windows"

        if current_default_unit == UNIT_PX:
            offset_x_str = f"{offset_x_converted:.1f}"
            offset_y_str = f"{offset_y_converted:.1f}"
        else:
            offset_x_str = f"{offset_x_converted:.4f}"
            offset_y_str = f"{offset_y_converted:.4f}"

        def _on_normalize(e):
            normalize_decimal_input(e)

        offset_x_field = self._create_textfield(
            offset_x_str,
            width=120,
            text_size=14,
            on_change=_on_normalize,
        )

        offset_y_field = self._create_textfield(
            offset_y_str,
            width=120,
            text_size=14,
            on_change=_on_normalize,
        )

        fine_adjust_step_field = self._create_textfield(
            f"{float(tuning_settings.get('fine_adjust_step_mm', 0.1)):.3f}",
            width=120,
            text_size=14,
            on_change=_on_normalize,
        )

        magnetic_snap_threshold_field = self._create_textfield(
            str(get_preference("magnetic_snap_threshold", 5.0)),
            width=120,
            text_size=14,
            on_change=_on_normalize,
        )

        # Registrar los campos en el contenedor forward para el handler de unidad
        _pref_offset_refs.extend([offset_x_field, offset_y_field])

        # Dropdown de alineación (usando dropdown compacto personalizado)
        alignment_dropdown = self._create_dropdown_compact(
            get_alignments(),
            self.default_alignment,
            width=140,
            text_size=14,
        )

        # Dropdown de rotación (usando dropdown compacto personalizado)
        rotation_dropdown = self._create_dropdown_compact(
            ROTATIONS,
            self.default_rotation,
            width=100,
            text_size=14,
        )

        def on_ok(e):
            """Guardar cambios en preferencias"""
            try:

                def _parse_float_input(raw_value, field_label):
                    """Admite coma o punto decimal y rechaza valores vacíos."""
                    text = str(raw_value).strip()
                    if not text:
                        raise ValueError(f"{field_label} no puede estar vacío")
                    try:
                        return float(text.replace(",", "."))
                    except ValueError as ex:
                        raise ValueError(f"{field_label} debe ser numérico") from ex

                def _validate_range(value, minimum, maximum, field_label):
                    if value < minimum or value > maximum:
                        raise ValueError(
                            f"{field_label} fuera de rango ({minimum} a {maximum})"
                        )

                # Validar y obtener valores - convertir de la unidad activa en
                # el diálogo (_pref_prev_unit[0]) a mm.  NO usar current_default_unit
                # porque el usuario puede haber cambiado la unidad dentro del diálogo.
                active_unit_in_dialog = _pref_prev_unit[0]
                new_offset_x_input = _parse_float_input(
                    offset_x_field.value, "Offset X"
                )
                new_offset_y_input = _parse_float_input(
                    offset_y_field.value, "Offset Y"
                )
                fine_adjust_step_mm = _parse_float_input(
                    fine_adjust_step_field.value, "Ajuste fino (mm)"
                )
                new_offset_x = round(
                    convert_to_mm(new_offset_x_input, active_unit_in_dialog), 6
                )
                new_offset_y = round(
                    convert_to_mm(new_offset_y_input, active_unit_in_dialog), 6
                )

                _validate_range(fine_adjust_step_mm, 0.01, 1.0, "Ajuste fino (mm)")

                # Snap magnético: leer y validar umbral
                magnetic_snap_threshold = _parse_float_input(
                    magnetic_snap_threshold_field.value, "Umbral guías magnéticas (px)"
                )
                _validate_range(
                    magnetic_snap_threshold, 1.0, 100.0, "Umbral guías magnéticas (px)"
                )

                # padding ratio y min px son constantes globales (no editables desde UI)
                windows_text_width_padding_ratio = float(
                    tuning_settings.get("windows_text_width_padding_ratio", 0.20)
                )
                windows_text_width_padding_min_px = float(
                    tuning_settings.get("windows_text_width_padding_min_px", 2.0)
                )

                # Obtener valores de dropdowns compactos (usando .data si está disponible como internal value)
                new_alignment = (
                    alignment_dropdown.content.controls[0].data
                    if alignment_dropdown.content.controls[0].data is not None
                    else alignment_dropdown.content.controls[0].value
                )
                new_rotation = (
                    rotation_dropdown.content.controls[0].data
                    if rotation_dropdown.content.controls[0].data is not None
                    else rotation_dropdown.content.controls[0].value
                )
                new_default_page_size = (
                    default_page_size_dropdown.content.controls[0].data
                    if default_page_size_dropdown.content.controls[0].data is not None
                    else default_page_size_dropdown.content.controls[0].value
                )
                new_default_unit = (
                    default_unit_dropdown.content.controls[0].data
                    if default_unit_dropdown.content.controls[0].data is not None
                    else default_unit_dropdown.content.controls[0].value
                )

                # Actualizar valores en memoria
                self.default_offset_x = new_offset_x
                self.default_offset_y = new_offset_y
                self.default_alignment = new_alignment
                self.default_rotation = new_rotation

                # Guardar en preferencias
                saved_position_ok = save_default_position_settings(
                    new_offset_x, new_offset_y, new_alignment, new_rotation
                )

                saved_tuning_ok = save_rendering_tuning_settings(
                    fine_adjust_step_mm,
                    windows_text_width_padding_ratio,
                    windows_text_width_padding_min_px,
                )

                # Guardar tamaño de página y unidad por defecto
                saved_startup_ok = save_startup_settings(
                    new_default_page_size, new_default_unit
                )

                if not (saved_position_ok and saved_tuning_ok and saved_startup_ok):
                    raise ValueError(
                        t(
                            "No se pudieron guardar todas las preferencias. Revisa permisos de escritura."
                        )
                    )

                # Guardar umbral de snap magnético
                save_preference("magnetic_snap_threshold", magnetic_snap_threshold)
                try:
                    self.interactive_viewer.magnetic_snap_threshold = float(
                        magnetic_snap_threshold
                    )
                except Exception:
                    pass

                # Actualizar los gestores de imagen de fondo con el nuevo tamaño por defecto
                for manager in self.background_image_managers.values():
                    manager.set_app_page_size(self.page_width_mm, self.page_height_mm)
                # Aplicar la nueva unidad por defecto a la aplicación inmediatamente
                try:
                    self.current_unit = new_default_unit
                    # Actualizar reglas y texto de tamaño de página
                    if ENABLE_RULERS:
                        self.interactive_viewer.set_ruler_unit(self.current_unit)
                    self._update_page_size_text()
                    self._update_unit_label()

                    # Refrescar los campos de offset si hay una posición seleccionada
                    if self.selected_position is not None:
                        self._load_position_data_to_ui(self.selected_position)

                    # Aplicar calibración del visor inmediatamente
                    self.interactive_viewer.reload_runtime_tuning_settings()

                except Exception as ex:
                    print(f"[PREFERENCES] Error al aplicar nueva unidad: {ex}")

                print(
                    f"[PREFERENCES] Valores por defecto guardados: offset=({new_offset_x}, {new_offset_y}), align={new_alignment}, rot={new_rotation}"
                )
                print(
                    f"[PREFERENCES] Tamaño y unidad por defecto guardados: {new_default_page_size}, {new_default_unit}"
                )
                print(
                    "[PREFERENCES] Calibración guardada: "
                    f"fine={fine_adjust_step_mm}, "
                    f"win_ratio={windows_text_width_padding_ratio}, "
                    f"win_min={windows_text_width_padding_min_px}, "
                    f"snap_px={magnetic_snap_threshold}"
                )

                # Comprobar checkboxes de borrado (variables `cb_*` definidas más abajo)
                try:
                    any_delete = bool(
                        (
                            cb_delete_general
                            and getattr(cb_delete_general, "value", False)
                        )
                        or (
                            cb_delete_prefs and getattr(cb_delete_prefs, "value", False)
                        )
                        or (cb_delete_main and getattr(cb_delete_main, "value", False))
                    )
                except Exception:
                    any_delete = False

                if any_delete:
                    # Ejecutar borrados granulares importando funciones desde preferences
                    try:
                        from utils.preferences import (
                            delete_font_cache_general,
                            delete_font_cache_prefs,
                            delete_main_preferences,
                        )
                    except Exception:
                        delete_font_cache_general = delete_font_cache_prefs = (
                            delete_main_preferences
                        ) = None

                    results = []
                    if (
                        cb_delete_general
                        and getattr(cb_delete_general, "value", False)
                        and delete_font_cache_general
                    ):
                        results.append(("font_cache", delete_font_cache_general()))
                    if (
                        cb_delete_prefs
                        and getattr(cb_delete_prefs, "value", False)
                        and delete_font_cache_prefs
                    ):
                        results.append(("fonts_prefs", delete_font_cache_prefs()))
                    if (
                        cb_delete_main
                        and getattr(cb_delete_main, "value", False)
                        and delete_main_preferences
                    ):
                        results.append(("preferences.json", delete_main_preferences()))

                    print(f"[PREFERENCES] Deletion results: {results}")

                    # Cerrar diálogo y la aplicación
                    try:
                        self.page.pop_dialog()
                    except Exception:
                        try:
                            dialog.open = False
                            if getattr(self.page, "dialog", None) is dialog:
                                self.page.dialog = None
                            if dialog in getattr(self.page, "overlay", []):
                                self.page.overlay.remove(dialog)
                            self.page.update()
                        except Exception:
                            pass
                    try:
                        if hasattr(self, "_preview_temp_path") and os.path.exists(
                            self._preview_temp_path
                        ):
                            os.remove(self._preview_temp_path)
                    except Exception:
                        pass
                    try:
                        self._close_app_con_dialogo()
                    except Exception:
                        pass
                    return

                # Cerrar diálogo normalmente
                try:
                    self.page.pop_dialog()
                except Exception:
                    try:
                        dialog.open = False
                        if getattr(self.page, "dialog", None) is dialog:
                            self.page.dialog = None
                        if dialog in getattr(self.page, "overlay", []):
                            self.page.overlay.remove(dialog)
                        self.page.update()
                    except Exception:
                        pass

            except ValueError as ex:
                print(f"[ERROR] Valores inválidos en preferencias: {ex}")
                try:
                    self.page.overlay.append(
                        ft.SnackBar(
                            content=ft.Text(str(ex), color=SNACKBAR_COLOR_TEXTO),
                            bgcolor=SNACKBAR_COLOR_ERROR,
                            open=True,
                        )
                    )
                    self.page.update()
                except Exception:
                    pass

        def on_cancel(e):
            """Cerrar sin guardar"""
            try:
                self.page.pop_dialog()
            except Exception:
                try:
                    dialog.open = False
                    if getattr(self.page, "dialog", None) is dialog:
                        self.page.dialog = None
                    if dialog in getattr(self.page, "overlay", []):
                        self.page.overlay.remove(dialog)
                    self.page.update()
                except Exception:
                    pass

        # Definir checkboxes antes de construir el contenido del diálogo
        cb_delete_general = ft.Checkbox(
            label=t("Eliminar caché temporal tipos de letra."),
            value=False,
            active_color=BORDE_TEXTFIELDS_COLOR,
            check_color=TEXTOS_FASE_1_COLOR,
            label_style=ft.TextStyle(size=12, color=TEXTOS_FASE_1_COLOR),
            fill_color=FONDO_TEXTFIELDS_COLOR,
            border_side=ft.BorderSide(1, BORDE_TEXTFIELDS_COLOR),
            splash_radius=0,
        )

        cb_delete_prefs = ft.Checkbox(
            label=t("Eliminar tipos de letra de preferencias"),
            value=False,
            active_color=BORDE_TEXTFIELDS_COLOR,
            check_color=TEXTOS_FASE_1_COLOR,
            label_style=ft.TextStyle(size=12, color=TEXTOS_FASE_1_COLOR),
            fill_color=FONDO_TEXTFIELDS_COLOR,
            border_side=ft.BorderSide(1, BORDE_TEXTFIELDS_COLOR),
            splash_radius=0,
        )

        cb_delete_main = ft.Checkbox(
            label=t("Resetear app, elimina todas las preferencias."),
            value=False,
            active_color=BORDE_TEXTFIELDS_COLOR,
            check_color=TEXTOS_FASE_1_COLOR,
            label_style=ft.TextStyle(
                size=12, color=ft.Colors.RED_300, weight=ft.FontWeight.BOLD
            ),
            fill_color=FONDO_TEXTFIELDS_COLOR,
            border_side=ft.BorderSide(1, BORDE_TEXTFIELDS_COLOR),
            splash_radius=0,
        )

        # Agrupar checkboxes en columna coherente con el estilo del diálogo
        checkboxes_column = ft.Column(
            [
                cb_delete_general,
                cb_delete_prefs,
                cb_delete_main,
            ],
            spacing=0,
            horizontal_alignment=ft.CrossAxisAlignment.START,
        )

        def on_open_log(e):
            try:
                from utils.error_logger import get_log_path
                import subprocess, platform, os

                lp = get_log_path()
                if not lp.exists():
                    print(f"[LOG] No existe archivo de log en {lp}")
                    return
                sistema = platform.system()
                if sistema == "Darwin":
                    subprocess.run(["open", str(lp)])
                elif sistema == "Windows":
                    os.startfile(str(lp))
                else:
                    subprocess.run(["xdg-open", str(lp)])
            except Exception as ex:
                print(f"[LOG] Error abriendo log de errores: {ex}")

        left_position_container = ft.Container(
            width=290,
            padding=ft.Padding.all(8),
            border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
            border_radius=6,
            bgcolor=FONDO_TEXTFIELDS_COLOR,
            content=ft.Column(
                [
                    ft.Text(
                        t("Posición número"),
                        size=12,
                        weight=ft.FontWeight.BOLD,
                        color=TEXTO_COLOR_GENERICO,
                    ),
                    ft.Row(
                        [
                            ft.Column(
                                [
                                    _pref_ox_label[0],
                                    offset_x_field,
                                ],
                                spacing=2,
                                width=120,
                            ),
                            ft.Column(
                                [
                                    _pref_oy_label[0],
                                    offset_y_field,
                                ],
                                spacing=2,
                                width=120,
                            ),
                        ],
                        spacing=15,
                        alignment=ft.MainAxisAlignment.START,
                    ),
                    ft.Container(height=8),
                    ft.Column(
                        [
                            ft.Text(
                                t("Paso ajuste fino (mm)"),
                                size=11,
                                color=TEXTO_COLOR_GENERICO,
                            ),
                            fine_adjust_step_field,
                        ],
                        spacing=2,
                        width=140,
                    ),
                ],
                spacing=0,
            ),
        )

        position_numbers_block = ft.Container(
            padding=ft.Padding.all(8),
            border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
            border_radius=8,
            width=720,
            content=ft.Column(
                [
                    ft.Text(
                        t("Posición inicial números:").rstrip(":"),
                        size=13,
                        weight=ft.FontWeight.BOLD,
                        color=TEXTO_COLOR_GENERICO,
                    ),
                    ft.Row(
                        [
                            left_position_container,
                        ],
                        spacing=0,
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.START,
                    ),
                ],
                spacing=8,
            ),
        )

        format_numbers_block = ft.Container(
            padding=ft.Padding.all(8),
            border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
            border_radius=8,
            width=235,
            content=ft.Column(
                [
                    ft.Text(
                        t("Formato números:").rstrip(":"),
                        size=13,
                        weight=ft.FontWeight.BOLD,
                        color=TEXTO_COLOR_GENERICO,
                    ),
                    ft.Row(
                        [
                            ft.Column(
                                [
                                    ft.Text(
                                        t("Alineación"),
                                        size=11,
                                        color=TEXTO_COLOR_GENERICO,
                                    ),
                                    alignment_dropdown,
                                ],
                                spacing=2,
                                width=120,
                            ),
                            ft.Column(
                                [
                                    ft.Text(
                                        t("Rotación"),
                                        size=11,
                                        color=TEXTO_COLOR_GENERICO,
                                    ),
                                    rotation_dropdown,
                                ],
                                spacing=2,
                                width=90,
                            ),
                        ],
                        spacing=8,
                        alignment=ft.MainAxisAlignment.START,
                    ),
                ],
                spacing=8,
            ),
        )

        # Referencia de ancho: el separador manda.
        top_blocks_spacing = 10
        separator_reference_width = 710
        top_block_width = (separator_reference_width - top_blocks_spacing) / 2

        general_defaults_block = ft.Container(
            padding=ft.Padding.all(8),
            border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
            border_radius=8,
            width=top_block_width,
            height=216,
            content=ft.Column(
                [
                    ft.Text(
                        t("Configuración general"),
                        size=13,
                        weight=ft.FontWeight.BOLD,
                        color=TEXTO_COLOR_GENERICO,
                    ),
                    ft.Row(
                        [
                            ft.Column(
                                [
                                    ft.Text(
                                        t("Idioma:"),
                                        size=11,
                                        weight=ft.FontWeight.BOLD,
                                        color=TEXTO_COLOR_GENERICO,
                                    ),
                                    language_dropdown,
                                ],
                                width=100,
                            ),
                        ],
                        spacing=8,
                    ),
                    ft.Row(
                        [
                            ft.Column(
                                [
                                    ft.Text(
                                        t("Tamaño de página por defecto:"),
                                        size=11,
                                        weight=ft.FontWeight.BOLD,
                                        color=TEXTO_COLOR_GENERICO,
                                    ),
                                    default_page_size_dropdown,
                                ],
                                width=200,
                            ),
                            ft.Column(
                                [
                                    ft.Text(
                                        t("Unidad medida"),
                                        size=11,
                                        weight=ft.FontWeight.BOLD,
                                        color=TEXTO_COLOR_GENERICO,
                                    ),
                                    default_unit_dropdown,
                                ],
                                width=180,
                            ),
                        ],
                        spacing=15,
                        alignment=ft.MainAxisAlignment.START,
                    ),
                    ft.Container(height=8),
                    ft.Row(
                        [
                            ft.Column(
                                [
                                    ft.Text(
                                        t("Umbral guías magnéticas (px)"),
                                        size=11,
                                        weight=ft.FontWeight.BOLD,
                                        color=TEXTO_COLOR_GENERICO,
                                    ),
                                    magnetic_snap_threshold_field,
                                ],
                                spacing=2,
                                width=180,
                            ),
                        ],
                        spacing=15,
                        alignment=ft.MainAxisAlignment.START,
                    ),
                ],
                spacing=8,
                horizontal_alignment=ft.CrossAxisAlignment.START,
            ),
        )

        position_numbers_right_block = ft.Container(
            padding=ft.Padding.all(8),
            border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
            border_radius=8,
            width=top_block_width,
            height=216,
            content=ft.Column(
                [
                    ft.Text(
                        t("Posición inicial números:").rstrip(":"),
                        size=13,
                        weight=ft.FontWeight.BOLD,
                        color=TEXTO_COLOR_GENERICO,
                    ),
                    ft.Text(
                        t("Posición número"),
                        size=12,
                        weight=ft.FontWeight.BOLD,
                        color=TEXTO_COLOR_GENERICO,
                    ),
                    ft.Row(
                        [
                            ft.Column(
                                [
                                    _pref_ox_label[0],
                                    offset_x_field,
                                ],
                                spacing=2,
                                width=120,
                            ),
                            ft.Column(
                                [
                                    _pref_oy_label[0],
                                    offset_y_field,
                                ],
                                spacing=2,
                                width=120,
                            ),
                        ],
                        spacing=15,
                        alignment=ft.MainAxisAlignment.START,
                    ),
                    ft.Container(height=8),
                    ft.Column(
                        [
                            ft.Text(
                                t("Paso ajuste fino (mm)"),
                                size=11,
                                color=TEXTO_COLOR_GENERICO,
                            ),
                            fine_adjust_step_field,
                        ],
                        spacing=2,
                        width=140,
                    ),
                ],
                spacing=8,
                horizontal_alignment=ft.CrossAxisAlignment.START,
            ),
        )

        # Crear contenido del diálogo
        dialog_content = ft.Column(
            [
                # BLOQUE DE IMPOSICIÓN (centrado)
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Row(
                                [
                                    general_defaults_block,
                                    position_numbers_right_block,
                                ],
                                spacing=top_blocks_spacing,
                                alignment=ft.MainAxisAlignment.START,
                                vertical_alignment=ft.CrossAxisAlignment.START,
                            ),
                            ft.Container(height=10),
                            ft.Row(
                                [
                                    format_numbers_block,
                                ],
                                spacing=10,
                                alignment=ft.MainAxisAlignment.START,
                                vertical_alignment=ft.CrossAxisAlignment.START,
                            ),
                        ],
                        spacing=8,
                        horizontal_alignment=ft.CrossAxisAlignment.START,
                    ),
                    alignment=ft.Alignment.CENTER,
                    width=separator_reference_width,
                ),
                ft.Container(height=14),
                ft.Container(
                    width=separator_reference_width,
                    alignment=ft.Alignment.CENTER,
                    content=ft.Divider(height=10, color=TEXTO_COLOR_GENERICO),
                ),
                ft.Container(height=8),
                # BLOQUE DE LIMPIEZA DE CACHES
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Text(
                                t("Eliminar datos y cachés:").rstrip(":"),
                                size=16,
                                weight=ft.FontWeight.BOLD,
                                color=TEXTO_COLOR_GENERICO,
                            ),
                            ft.Text(
                                t("Selecciona las opciones que deseas eliminar."),
                                size=14,
                                color=TEXTO_COLOR_GENERICO,
                            ),
                            ft.Text(
                                t("Si se ejecuta alguna, la aplicación se cerrará."),
                                size=14,
                                color=TEXTO_COLOR_GENERICO,
                            ),
                        ],
                        spacing=4,
                        horizontal_alignment=ft.CrossAxisAlignment.START,
                    ),
                    width=separator_reference_width,
                    padding=ft.Padding.all(0),
                    alignment=ft.Alignment.TOP_LEFT,
                ),
                ft.Container(height=15),
                # (checkboxes insertadas fuera para evitar errores de sintaxis)
            ],
            spacing=0,
            tight=True,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )

        # Crear diálogo
        dialog = ft.AlertDialog(
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.Text(
                            t("Preferencias"),
                            size=18,
                            weight=ft.FontWeight.BOLD,
                            color=TEXTO_COLOR_GENERICO,
                            text_align=ft.TextAlign.CENTER,
                        ),
                        dialog_content,
                        ft.Container(
                            width=separator_reference_width,
                            alignment=ft.Alignment.TOP_LEFT,
                            content=checkboxes_column,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.START,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                alignment=ft.Alignment.CENTER,
                width=800,
                padding=16,
            ),
            actions=[
                self._create_generic_button(t("Cancelar"), on_cancel),
                self._create_generic_button(
                    t("Abrir log de errores"), on_open_log, width=180
                ),
                self._create_generic_button(t("Guardar"), on_ok),
            ],
            actions_padding=ft.Padding(0, 0, 0, 18),
            actions_alignment=ft.MainAxisAlignment.CENTER,
            bgcolor=FONDO_ALERT_DIALOG,
            modal=True,
        )

        # Abrir diálogo
        try:
            self.page.show_dialog(dialog)
        except Exception:
            self.page.dialog = dialog
            self.page.dialog.open = True
            self.page.update()

    def _on_toggle_theme(self, e):
        """Cambia entre modo día y noche"""
        # Alternar el tema basado en el estado actual de la página
        if self.page.theme_mode == ft.ThemeMode.DARK:
            nuevo_tema = "claro"
            nuevo_tema_flet = ft.ThemeMode.LIGHT
            nuevo_icono = (
                ft.Icons.DARK_MODE
            )  # En modo claro, mostrar icono de luna (para cambiar a oscuro)
        else:
            nuevo_tema = "oscuro"
            nuevo_tema_flet = ft.ThemeMode.DARK
            nuevo_icono = (
                ft.Icons.LIGHT_MODE
            )  # En modo oscuro, mostrar icono de sol (para cambiar a claro)

        # Establecer el tema manualmente
        set_tema_manual(nuevo_tema, nuevo_tema_flet)

        # Aplicar inmediatamente a la página
        self.page.theme_mode = nuevo_tema_flet
        self.page.theme, self.page.dark_theme = definir_constantes_color()

        # Actualizar colores globales
        try:
            actualizar_colores()
        except Exception as ex:
            print(f"[ERROR] No se pudo actualizar colores: {ex}")

        # Actualizar el icono del botón
        self.icon_theme_toggle.content.name = nuevo_icono

        # Actualizar toda la página para reflejar el nuevo tema
        self.page.update()

        print(f"[THEME] Tema cambiado a: {nuevo_tema}")

    # ===== MÉTODOS PARA DOBLE CARA =====

    def _on_toggle_double_sided(self, e):
        """Activa o desactiva el modo de doble cara"""
        self.double_sided_enabled = not self.double_sided_enabled

        if self.double_sided_enabled:
            # Activar doble cara
            print(f"[DOUBLE_SIDED] Activando modo doble cara")
            self.icon_face.disabled = False
            self.icon_double_sided.bgcolor = BOTONES_GENERICOS_OVERLAY_COLOR
            self.icon_double_sided.content.color = BOTONES_GENERICOS_TEXTO_COLOR
            self.icon_face.bgcolor = BOTONES_GENERICOS_OVERLAY_COLOR
            self.icon_face.content.controls[0].color = BOTONES_GENERICOS_TEXTO_COLOR
            self.icon_face.content.controls[1].color = BOTONES_GENERICOS_TEXTO_COLOR
            self.double_sided_indicator.visible = True
            self._update_face_button()
        else:
            # Desactivar doble cara - siempre volver a CARA
            print(f"[DOUBLE_SIDED] Desactivando modo doble cara")
            self.icon_face.disabled = True
            self.icon_double_sided.bgcolor = FONDO_TEXTFIELDS_COLOR
            self.icon_double_sided.content.color = TEXTOS_FASE_1_COLOR
            self.icon_face.bgcolor = FONDO_TEXTFIELDS_COLOR
            self.icon_face.content.controls[0].color = TEXTOS_FASE_1_COLOR
            self.icon_face.content.controls[1].color = TEXTOS_FASE_1_COLOR
            self.current_face = "CARA"
            self._update_face_button()
            self.double_sided_indicator.visible = False

        # Actualizar iconos
        try:
            self.icon_double_sided.update()
            self.icon_face.update()
            self.double_sided_indicator.update()
        except AssertionError as e:
            print(f"[UI_UPDATE] Algunas actualizaciones de iconos fallaron: {e}")

        # Marcar como modificado por acción de usuario
        self._mark_modified()

        # Actualizar la interfaz para reflejar el cambio
        self._refresh_current_face(auto_select=False)

    def _update_face_button(self):
        """Actualiza el icono, texto y indicador según la cara actual"""
        label = t("C") if self.current_face == "CARA" else t("D")
        tooltip = t("Cara") if self.current_face == "CARA" else t("Dorso")
        face_name = "CARA" if self.current_face == "CARA" else "DORSO"
        self.icon_face.content.controls[1].value = label
        self.icon_face.tooltip = tooltip
        if self.double_sided_enabled:
            self._double_sided_text.value = (
                f"{t('Doble cara activado.')} {t(face_name)}"
            )

    def _on_toggle_face(self, e):
        """Alterna entre cara y dorso cuando doble cara está activado"""
        if not self.double_sided_enabled:
            return

        new_face = "DORSO" if self.current_face == "CARA" else "CARA"
        print(f"[DOUBLE_SIDED] Cambiando a {new_face}")
        self.current_face = new_face
        self._update_face_button()
        self._refresh_current_face(auto_select=False)

    def _refresh_current_face(self, auto_select=True):
        """Refresca la interfaz para mostrar la cara/dorso actual
        Args:
            auto_select: Si True, selecciona automáticamente la primera posición
        """
        print(f"[DOUBLE_SIDED] Refrescando interfaz para: {self.current_face}")

        # Actualizar colores del botón de cara/dorso
        if self.double_sided_enabled:
            self.icon_face.bgcolor = BOTONES_GENERICOS_OVERLAY_COLOR
            self.icon_face.content.controls[0].color = BOTONES_GENERICOS_TEXTO_COLOR
            self.icon_face.content.controls[1].color = BOTONES_GENERICOS_TEXTO_COLOR
            self._update_face_button()
            self.icon_face.update()
            self.double_sided_indicator.update()

        # Limpiar selección actual
        self.selected_position = None
        self._toggle_sections_by_type(None)

        # Resetear dropdown de alineación para que no muestre valor residual de la otra cara
        texto_align = self.alignment_dropdown.content.controls[0]
        texto_align.value = t("izquierda")
        texto_align.data = ALIGNMENT_LEFT
        texto_align.update()
        self._update_position_fields_state()

        # CRÍTICO: Limpiar y restaurar numeradoras del viewer
        self._clear_viewer_numeradoras()
        self._restore_viewer_numeradoras()

        # Actualizar lista de posiciones
        self.positions_list.controls.clear()
        current_positions = self._get_current_positions()
        for num_id, pos_data in current_positions.items():
            self.positions_list.controls.append(pos_data["item"])
        self.positions_list.update()

        # Flet 1.0 congela (propaga _frozen) los items reconciliados por key
        # cuando dos instancias distintas comparten key (cara2 reutiliza ids
        # de cara1, o recarga de proyecto recrea los items). Los items de la
        # lista deben seguir mutables (bgcolor de selección): quitar el
        # marcador. Patrón que usa el propio Flet (use_dialog hace del dialog._frozen).
        for _pd in current_positions.values():
            _it = _pd.get("item")
            if _it is not None and hasattr(_it, "_frozen"):
                del _it._frozen

        # Reverse pertenece a la app (global_settings), no a la cara — siempre sincronizar
        self.reverse_checkbox.value = self.global_settings.get("reverse", False)
        self.reverse_checkbox.update()

        # Seleccionar automáticamente la primera posición si existe
        if current_positions:
            if auto_select:
                first_position_id = min(current_positions.keys())
                self._on_select_position(first_position_id)
        else:
            # Si no hay posiciones, actualizar campos con valores globales y por cara
            self.start_field.value = str(self.global_settings["start"])
            self.end_field.value = str(self.global_settings["end"])
            self.increment_field.value = str(self.global_settings["increment"])
            self.copies_field.value = str(self.global_settings["copies"])

            # Actualizar UI
            self.start_field.update()
            self.end_field.update()
            self.increment_field.update()
            self.copies_field.update()

            # Recalcular páginas
            self._calculate_total_pages()

        # Actualizar imagen de fondo del viewer
        self._refresh_viewer()

        # Actualizar estado de botones de imagen (por cara) - con update visual
        self._update_image_settings_button_state(do_update=True)

        self.page.update()
        print(f"[DOUBLE_SIDED] Interfaz actualizada para: {self.current_face}")

    def _get_current_positions(self):
        """Retorna el diccionario de posiciones de la cara actual"""
        return self.positions[self.current_face]

    def _get_physical_page(self) -> int:
        """Calcula página física desde página lógica y cara actual"""
        if self.double_sided_enabled:
            return (self.current_page - 1) * 2 + (
                1 if self.current_face == "CARA" else 2
            )
        return self.current_page

    def _get_current_face_settings(self):
        """Retorna la configuración de la cara actual"""
        return self.face_settings[self.current_face]

    def _get_current_next_position_number(self):
        """Retorna el siguiente número de posición para la cara actual"""
        return self.next_position_number[self.current_face]

    def _increment_current_position_number(self):
        """Incrementa el contador de posición para la cara actual"""
        self.next_position_number[self.current_face] += 1

    def _get_current_background_image_manager(self):
        """Retorna el gestor de imagen de fondo de la cara actual"""
        return self.background_image_managers[self.current_face]

    def _set_current_position(self, num_id, data):
        """Establece los datos de una posición en la cara actual"""
        current_positions = self._get_current_positions()
        current_positions[num_id] = data

    def _get_current_position(self, num_id):
        """Obtiene los datos de una posición en la cara actual"""
        current_positions = self._get_current_positions()
        return current_positions.get(num_id, {})

    def _clear_viewer_numeradoras(self):
        """Limpia todas las numeradoras y barcodes del viewer actual"""
        # Limpiar numeradoras
        if hasattr(self.interactive_viewer, "numeradoras"):
            num_ids = list(self.interactive_viewer.numeradoras.keys())
            for num_id in num_ids:
                self.interactive_viewer.remove_numeradora(num_id)
            print(f"[VIEWER] Limpiadas {len(num_ids)} numeradoras del viewer")

        # Limpiar barcodes
        if hasattr(self.interactive_viewer, "barcodes"):
            bc_ids = list(self.interactive_viewer.barcodes.keys())
            for bc_id in bc_ids:
                self.interactive_viewer.remove_barcode(bc_id)
            print(f"[VIEWER] Limpiados {len(bc_ids)} barcodes del viewer")

        # Limpiar textos variables
        if hasattr(self.interactive_viewer, "variable_texts"):
            vt_ids = list(self.interactive_viewer.variable_texts.keys())
            for vt_id in vt_ids:
                self.interactive_viewer.remove_variable_text(vt_id)
            print(f"[VIEWER] Limpiados {len(vt_ids)} textos variables del viewer")

    def _restore_viewer_numeradoras(self):
        """Restaura las numeradoras y barcodes de la cara actual al viewer"""
        current_positions = self._get_current_positions()

        for num_id, pos_data in current_positions.items():
            pos_type = pos_data.get("type", "number")

            if pos_type == "barcode":
                profile_name = pos_data.get("profile_name", "<Default>")
                if self.current_face == "DORSO":
                    print(
                        f"[RESTORE] DORSO pid={num_id} profile_name={profile_name!r} vs={pos_data.get('value_source','?')} ec={pos_data.get('excel_column','?')} bv={pos_data.get('barcode_value','?')!r}"
                    )
                # Resolver campos del perfil desde el BarcodeProfile real (single source of truth)
                profile = (
                    self.barcode_ui_manager._find_profile(profile_name)
                    if hasattr(self, "barcode_ui_manager") and profile_name
                    else None
                )
                if profile is not None:
                    symbology = profile.symbology
                    bar_width = profile.bar_width
                    bar_height = profile.bar_height
                    color = profile.color
                    color_cmyk = (
                        tuple(profile.color_cmyk) if profile.color_cmyk else None
                    )
                    color_space = profile.color_space
                    color_name = profile.color_name
                    color_tint = profile.color_tint
                    text_color = profile.text_color
                    text_color_cmyk = (
                        tuple(profile.text_color_cmyk)
                        if getattr(profile, "text_color_cmyk", None)
                        else None
                    )
                    text_color_space = profile.text_color_space
                    text_color_name = profile.text_color_name
                    text_color_tint = profile.text_color_tint
                    value_source = profile.value_source
                    mask = profile.mask
                    error_correction = profile.error_correction
                    barcode_font_family = profile.barcode_font_family
                    barcode_font_size = profile.barcode_font_size
                    itf14_quiet_zone_mm = profile.itf14_quiet_zone_mm
                    itf14_bearer_thickness_mm = profile.itf14_bearer_thickness_mm
                    itf14_bearer_sides = profile.itf14_bearer_sides
                    itf14_gtin_type = profile.itf14_gtin_type
                    itf14_printer_type = profile.itf14_printer_type
                    itf14_hri_gap_mm = profile.itf14_hri_gap_mm
                    itf14_hri_position = profile.itf14_hri_position
                    code39_hri_gap_mm = profile.code39_hri_gap_mm
                    code39_hri_position = profile.code39_hri_position
                    code128_hri_gap_mm = profile.code128_hri_gap_mm
                    code128_hri_position = profile.code128_hri_position
                    ean5_hri_gap_mm = profile.ean5_hri_gap_mm
                    isbn13_show_title = profile.isbn13_show_title
                    pdf417_height = profile.pdf417_height
                    pdf417_size = profile.pdf417_size
                    datamatrix_width = profile.datamatrix_width
                    datamatrix_height = profile.datamatrix_height
                    datamatrix_format = profile.datamatrix_format
                    datamatrix_hri_gap_mm = profile.datamatrix_hri_gap_mm
                    datamatrix_hri_position = profile.datamatrix_hri_position
                    datamatrix_hri_align = getattr(profile, "datamatrix_hri_align", "bottom_center")
                    datamatrix_hri_line_spacing = getattr(profile, "datamatrix_hri_line_spacing", 1.0)
                    datamatrix_del_open = profile.datamatrix_del_open
                    datamatrix_del_close = (
                        profile.datamatrix_del_close
                        if profile.datamatrix_del_close is not None
                        else ""
                    )
                    qr_del_open = getattr(profile, "qr_del_open", "") or ""
                    qr_del_close = getattr(profile, "qr_del_close", "") or ""
                    pdf417_del_open = getattr(profile, "pdf417_del_open", "") or ""
                    pdf417_del_close = getattr(profile, "pdf417_del_close", "") or ""
                else:
                    raw_cmyk = pos_data.get("color_cmyk", None)
                    color_cmyk = tuple(raw_cmyk) if raw_cmyk is not None else None
                    value_source = pos_data.get("value_source", "fixed")
                    mask = pos_data.get("mask", "")
                    symbology = pos_data.get("symbology", "code128")
                    bar_width = float(pos_data.get("bar_width", 80.0))
                    bar_height = float(pos_data.get("bar_height", 30.0))
                    color = pos_data.get("color", "#000000")
                    color_space = pos_data.get("color_space", "RGB")
                    color_name = pos_data.get("color_name", "")
                    color_tint = pos_data.get("color_tint", 100.0)
                    text_color = pos_data.get("text_color", "#000000")
                    text_color_cmyk = pos_data.get("text_color_cmyk", None)
                    text_color_space = pos_data.get("text_color_space", "RGB")
                    text_color_name = pos_data.get("text_color_name", "")
                    text_color_tint = pos_data.get("text_color_tint", 100.0)
                    error_correction = pos_data.get("error_correction", "M")
                    barcode_font_family = pos_data.get("barcode_font_family", "OCR-B")
                    barcode_font_size = pos_data.get("barcode_font_size", 13.0)
                    itf14_quiet_zone_mm = pos_data.get("itf14_quiet_zone_mm", 10.16)
                    itf14_bearer_thickness_mm = pos_data.get(
                        "itf14_bearer_thickness_mm", 4.8
                    )
                    itf14_bearer_sides = pos_data.get("itf14_bearer_sides", "4")
                    itf14_gtin_type = pos_data.get("itf14_gtin_type", "gtin14")
                    itf14_printer_type = pos_data.get(
                        "itf14_printer_type", "flexografia"
                    )
                    itf14_hri_gap_mm = float(pos_data.get("itf14_hri_gap_mm", 2.0))
                    itf14_hri_position = pos_data.get("itf14_hri_position", "below")
                    code39_hri_gap_mm = float(pos_data.get("code39_hri_gap_mm", 2.0))
                    code39_hri_position = pos_data.get("code39_hri_position", "below")
                    code128_hri_gap_mm = float(pos_data.get("code128_hri_gap_mm", 2.0))
                    ean5_hri_gap_mm = float(pos_data.get("ean5_hri_gap_mm", 2.0))
                    isbn13_show_title = pos_data.get("isbn13_show_title", "Sí")
                    pdf417_height = pos_data.get("pdf417_height")
                    pdf417_size = pos_data.get("pdf417_size")
                    datamatrix_width = float(pos_data.get("datamatrix_width", 20.0))
                    datamatrix_height = float(pos_data.get("datamatrix_height", 20.0))
                    datamatrix_format = pos_data.get("datamatrix_format", "")
                    datamatrix_hri_gap_mm = float(
                        pos_data.get("datamatrix_hri_gap_mm", 2.0)
                    )
                    datamatrix_hri_position = pos_data.get(
                        "datamatrix_hri_position", "below"
                    )
                    datamatrix_del_open = pos_data.get("datamatrix_del_open", "")
                    datamatrix_del_close = pos_data.get("datamatrix_del_close", "")
                    qr_del_open = pos_data.get("qr_del_open", "")
                    qr_del_close = pos_data.get("qr_del_close", "")
                    pdf417_del_open = pos_data.get("pdf417_del_open", "")
                    pdf417_del_close = pos_data.get("pdf417_del_close", "")
                # Si es PDF417, usar pdf417_size como width y pdf417_height como height
                if symbology == "pdf417" and value_source != "excel":
                    if pdf417_size is not None:
                        bar_width = float(pdf417_size)
                    if pdf417_height is not None:
                        bar_height = float(pdf417_height)
                # Recalculate PDF417 min dimensions from actual Excel data on load
                if symbology == "pdf417" and value_source == "excel":
                    ec = pos_data.get("excel_column", "")
                    if ec and self.excel_manager and self.excel_manager.is_loaded:
                        try:
                            from utils.barcode_module import (
                                get_pdf417_min_dimensions,
                            )

                            all_vals = self.excel_manager.get_column_values(ec)
                            if all_vals:
                                min_w, min_h = get_pdf417_min_dimensions(all_vals)
                                bar_width = min_w
                                pdf417_height = min_h
                        except Exception:
                            pass
                if symbology == "upca":
                    bw = float(bar_width) if bar_width else 37.29
                    bh = float(bar_height) if bar_height else 25.91
                    bar_width = max(29.83, bw)
                    bar_height = max(20.73, bh)
                if symbology == "upce":
                    bw = float(bar_width) if bar_width else 22.11
                    bh = float(bar_height) if bar_height else 25.91
                    bar_width = max(17.69, bw)
                    bar_height = max(20.73, bh)
                if symbology == "ean5":
                    bw = float(bar_width) if bar_width else 17.92
                    bh = float(bar_height) if bar_height else 20.73
                    bar_width = max(17.92, bw)
                    bar_height = max(20.73, bh)
                if symbology == "ean13":
                    bw = float(bar_width) if bar_width else 29.83
                    bh = float(bar_height) if bar_height else 20.73
                    bar_width = max(29.83, bw)
                    bar_height = max(20.73, bh)
                if symbology == "ean8":
                    bw = float(bar_width) if bar_width else 21.38
                    bh = float(bar_height) if bar_height else 17.05
                    bar_width = max(21.38, bw)
                    bar_height = max(17.05, bh)
                if symbology == "isbn13":
                    bw = float(bar_width) if bar_width else 29.83
                    bh = float(bar_height) if bar_height else 20.73
                    bar_width = max(29.83, bw)
                    bar_height = max(20.73, bh)
                # Calcular valor correcto ANTES de add_barcode
                bc_value = pos_data.get("barcode_value", "")
                if profile is not None:
                    if value_source == "numbering":
                        number = self._calculate_number_for_numeradora(num_id)
                        bc_value = _apply_mask(number, mask)
                    elif value_source == "excel":
                        excel_column = pos_data.get("excel_column", "")
                        if excel_column and self.excel_manager.is_loaded:
                            phys_page = self.current_page
                            start = self.global_settings.get("start", 1)
                            end = self.global_settings.get("end", 125)
                            increment = self.global_settings.get("increment", 1)
                            copies = self.global_settings.get("copies", 1)
                            reverse = self.global_settings.get("reverse", False)
                            row_index = excel_row_index(
                                start, end, increment, copies, reverse, phys_page
                            )
                            val = self.excel_manager.get_value_at(
                                excel_column, row_index
                            )
                            if val:
                                bc_value = val
                    elif (
                        value_source == "fixed"
                        and "<@<" in (pos_data.get("sample_value", "") or "")
                        and symbology in ("qr", "pdf417", "datamatrix")
                        and self.excel_manager.is_loaded
                    ):
                        # VT personalizado: resolver la plantilla guardada con la fila actual
                        phys_page = self.current_page
                        start = self.global_settings.get("start", 1)
                        end = self.global_settings.get("end", 125)
                        increment = self.global_settings.get("increment", 1)
                        copies = self.global_settings.get("copies", 1)
                        reverse = self.global_settings.get("reverse", False)
                        row_index = excel_row_index(
                            start, end, increment, copies, reverse, phys_page
                        )
                        bc_value = (
                            resolve_vt_text(
                                pos_data.get("sample_value", ""),
                                value_source="fixed",
                                excel_column=pos_data.get("excel_column", "") or "",
                                excel_manager=self.excel_manager,
                                row_index=row_index,
                            )
                            or pos_data.get("sample_value", "")
                        )
                    else:
                        bc_value = profile.sample_value
                pos_data["barcode_value"] = bc_value

                self.interactive_viewer.add_barcode(
                    x=pos_data.get("x", 10),
                    y=pos_data.get("y", 10),
                    value=bc_value,
                    symbology=symbology,
                    bar_width=float(bar_width),
                    bar_height=float(bar_height),
                    rotation=pos_data.get("rotation", 0),
                    alignment=pos_data.get("alignment", "centro"),
                    color=color,
                    color_cmyk=color_cmyk,
                    color_space=color_space,
                    color_name=color_name,
                    color_tint=color_tint,
                    text_color=text_color,
                    text_color_cmyk=text_color_cmyk,
                    text_color_space=text_color_space,
                    text_color_name=text_color_name,
                    text_color_tint=text_color_tint,
                    value_source=value_source,
                    mask=mask,
                    error_correction=error_correction,
                    barcode_font_family=barcode_font_family,
                    barcode_font_size=barcode_font_size,
                    itf14_quiet_zone_mm=itf14_quiet_zone_mm,
                    itf14_bearer_thickness_mm=itf14_bearer_thickness_mm,
                    itf14_bearer_sides=itf14_bearer_sides,
                    itf14_gtin_type=itf14_gtin_type,
                    itf14_printer_type=itf14_printer_type,
                    itf14_hri_gap_mm=float(itf14_hri_gap_mm),
                    itf14_hri_position=itf14_hri_position,
                    code39_hri_gap_mm=float(code39_hri_gap_mm),
                    code39_hri_position=code39_hri_position,
                    code128_hri_gap_mm=float(code128_hri_gap_mm),
                    code128_hri_position=code128_hri_position,
                    ean5_hri_gap_mm=float(ean5_hri_gap_mm),
                    isbn13_show_title=isbn13_show_title,
                    pdf417_height=pdf417_height,
                    datamatrix_width=datamatrix_width,
                    datamatrix_height=datamatrix_height,
                    datamatrix_format=datamatrix_format,
                    datamatrix_hri_gap_mm=datamatrix_hri_gap_mm,
                                        datamatrix_hri_position=datamatrix_hri_position,
                    datamatrix_hri_align=datamatrix_hri_align,
                    datamatrix_hri_line_spacing=datamatrix_hri_line_spacing,
                    datamatrix_del_open=datamatrix_del_open,
                    datamatrix_del_close=datamatrix_del_close,
                    qr_del_open=qr_del_open,
                    qr_del_close=qr_del_close,
                    pdf417_del_open=pdf417_del_open,
                    pdf417_del_close=pdf417_del_close,
                    profile_name=profile_name,
                    auto_select=False,
                    barcode_id=num_id,


                    locked=pos_data.get("locked", False),
                )
                # Asegurar defaults en pos_data para PDF generation
            elif pos_type == "variable_text":
                vt_profile_name = pos_data.get("profile_name", "<Default>")
                vt_profile = (
                    self.variable_text_ui_manager._find_profile(vt_profile_name)
                    if hasattr(self, "variable_text_ui_manager") and vt_profile_name
                    else None
                )
                if vt_profile is not None:
                    font_family = vt_profile.font_family
                    font_style = vt_profile.font_style
                    font_size = vt_profile.font_size
                    color = vt_profile.text_color
                    color_tint = vt_profile.text_color_tint
                    color_space = vt_profile.text_color_space
                    # La Alineación es del PERFIL: el override por posición de
                    # proyectos v1 se ignora; se re-espeja en pos_data para que
                    # dropdown/export lean el valor vigente.
                    text_alignment = vt_profile.alignment
                    pos_data["text_alignment"] = text_alignment
                    font_path = getattr(vt_profile, "resolved_font_path", None)
                    metricas = getattr(vt_profile, "metricas", None)
                    value_source = vt_profile.value_source
                    excel_column = vt_profile.excel_column
                    restored_text = vt_profile.sample_text
                else:
                    restored_text = pos_data.get("sample_text", "")
                    value_source = pos_data.get("value_source", "sample")
                    excel_column = pos_data.get("excel_column", "")
                    font_family = pos_data.get("font_family", "Arial")
                    font_style = pos_data.get("font_style", "Regular")
                    font_size = pos_data.get("font_size", 12)
                    color = pos_data.get("text_color", "#000000")
                    color_tint = float(pos_data.get("text_color_tint", 100.0))
                    color_space = pos_data.get("text_color_space", "RGB")
                    text_alignment = pos_data.get("text_alignment", "izquierda")
                    font_path = pos_data.get("resolved_font_path")
                    metricas = pos_data.get("metricas")
                    value_source = pos_data.get("value_source", "sample")
                    excel_column = pos_data.get("excel_column", "")

                # Resolver marcadores `<@<col>@>` con la fila de la página actual
                # (mismo patrón que _update_all_numeradoras): con Excel cargado se
                # resuelven SIEMPRE (también con value_source "sample"), para que el
                # visor muestre los datos reales desde el primer render, no las etiquetas.
                if (
                    hasattr(self, "excel_manager")
                    and self.excel_manager
                    and self.excel_manager.is_loaded
                    and restored_text
                ):
                    try:
                        phys_page = self.current_page
                        phys_start = self.global_settings.get("start", 1)
                        phys_end = self.global_settings.get("end", 125)
                        phys_increment = self.global_settings.get("increment", 1)
                        phys_copies = self.global_settings.get("copies", 1)
                        reverse = self.global_settings.get("reverse", False)
                        phys_row = excel_row_index(
                            phys_start,
                            phys_end,
                            phys_increment,
                            phys_copies,
                            reverse,
                            phys_page,
                        )
                        restored_text = resolve_vt_text(
                            restored_text,
                            value_source=value_source,
                            excel_column=excel_column,
                            excel_manager=self.excel_manager,
                            row_index=phys_row,
                            text_case_filter=pos_data.get("text_case_filter", ""),
                        )
                    except Exception:
                        pass
                if vt_profile is not None:
                    pos_data["letter_spacing"] = vt_profile.letter_spacing
                    pos_data["line_spacing"] = vt_profile.line_spacing
                else:
                    pos_data.setdefault("letter_spacing", 0.0)
                    pos_data.setdefault("line_spacing", 1.0)
                self.interactive_viewer.add_variable_text(
                    x=pos_data.get("x", 10),
                    y=pos_data.get("y", 10),
                    text=restored_text,
                    font_family=font_family,
                    font_style=font_style,
                    font_size=font_size,
                    color=color,
                    color_tint=color_tint,
                    color_space=color_space,
                    alignment=pos_data.get("alignment", "izquierda"),
                    rotation=pos_data.get("rotation", "0°"),
                    auto_select=False,
                    variable_text_id=num_id,
                    font_path=font_path,
                    text_alignment=text_alignment,
                    metricas=metricas,
                    value_source=value_source,
                    excel_column=excel_column,
                    profile_name=pos_data.get("profile_name", ""),
                    locked=pos_data.get("locked", False),
                    line_spacing=pos_data.get("line_spacing", 1.0),
                    letter_spacing=pos_data.get("letter_spacing", 0.0),
                    anchor=pos_data.get("anchor"),
                )
            else:
                resolved_style_name = pos_data.get("text_style", "<Default>")
                if (
                    hasattr(self, "text_style_manager")
                    and resolved_style_name != "<Default>"
                ):
                    found = any(
                        p.name == resolved_style_name
                        for p in self.text_style_manager.profiles
                    )
                    if not found:
                        resolved_style_name = "<Default>"
                self.interactive_viewer.add_numeradora(
                    num_id=num_id,
                    x=pos_data.get("x", 10),
                    y=pos_data.get("y", 10),
                    alignment=pos_data.get("alignment", "center"),
                    text_style_name=resolved_style_name,
                    auto_select=False,
                    locked=pos_data.get("locked", False),
                )

                rotation = pos_data.get("rotation")
                if rotation:
                    self.interactive_viewer.set_rotation(num_id, rotation)

                number_str = self._calculate_number_for_numeradora(num_id)
                self.interactive_viewer.set_number(num_id, number_str, redraw=False)

        self.interactive_viewer._redraw_all(force=True)

        count_num = len(
            [
                p
                for p in current_positions.values()
                if p.get("type", "number") == "number"
            ]
        )
        count_bc = len(
            [p for p in current_positions.values() if p.get("type") == "barcode"]
        )
        count_vt = len(
            [p for p in current_positions.values() if p.get("type") == "variable_text"]
        )
        print(
            f"[VIEWER] Restauradas {count_num} numeradoras, {count_vt} textos variables y {count_bc} barcodes para {self.current_face}"
        )

    def _on_excel_cleared(self):
        """Actualiza pos_data y viewer tras eliminar/cambiar Excel."""
        real_face = self.current_face
        for face in ("CARA", "DORSO"):
            for pos_id, pos_data in list(self.positions[face].items()):
                ptype = pos_data.get("type", "number")
                profile_name = pos_data.get(
                    "profile_name", pos_data.get("text_style", "<Default>")
                )

                if ptype == "barcode":
                    for p in self.barcode_ui_manager.profile_manager.profiles:
                        if p.name == profile_name and p.value_source == "fixed":
                            pos_data["value_source"] = "fixed"
                            pos_data["excel_column"] = ""
                            if face == real_face:
                                self.interactive_viewer.set_barcode_value(
                                    pos_id, p.sample_value, redraw=False
                                )
                            if getattr(p, "symbology", "") == "pdf417":
                                from utils.barcode_module import (
                                    get_pdf417_min_dimensions,
                                )

                                min_w, min_h = get_pdf417_min_dimensions(
                                    [p.sample_value]
                                )
                                p.pdf417_size = min_w
                                p.pdf417_height = min_h
                                pos_data["pdf417_size"] = min_w
                                pos_data["pdf417_height"] = min_h
                                bd = self.interactive_viewer.barcodes.get(pos_id)
                                if bd:
                                    bd["data"]["pdf417_size"] = min_w
                                    bd["data"]["pdf417_height"] = min_h
                            break
                elif ptype == "variable_text":
                    for p in self.variable_text_ui_manager.profile_manager.profiles:
                        if p.name == profile_name and p.value_source == "sample":
                            pos_data["value_source"] = "sample"
                            pos_data["excel_column"] = ""
                            text = p.sample_text or ""
                            if face == real_face:
                                self.interactive_viewer.set_variable_text_value(
                                    pos_id, text, redraw=False
                                )
                            break
        self.interactive_viewer._redraw_all(force=True)
        self._mark_modified()

    def _recalculate_pdf417_heights(self):
        """Recalculate PDF417 min dimensions for all barcodes when Excel data reloads."""
        from utils.barcode_module import get_pdf417_min_dimensions

        for face in self.positions:
            for num_id, pos_data in self.positions[face].items():
                if (
                    pos_data.get("type") == "barcode"
                    and pos_data.get("symbology") == "pdf417"
                    and pos_data.get("value_source") == "excel"
                ):
                    col = pos_data.get("excel_column", "")
                    if col and self.excel_manager and self.excel_manager.is_loaded:
                        try:
                            vals = self.excel_manager.get_column_values(col)
                            if vals:
                                min_w, min_h = get_pdf417_min_dimensions(vals)
                                pos_data["pdf417_size"] = min_w
                                pos_data["pdf417_height"] = min_h
                        except Exception:
                            pass

    def _refresh_viewer(self):
        """Refresca el viewer con la imagen de fondo actual"""
        if not hasattr(self, "interactive_viewer") or self.interactive_viewer is None:
            return

        current_manager = self._get_current_background_image_manager()
        if current_manager.image_loaded:
            config = current_manager.get_image_config()
            self.interactive_viewer.set_background(config)
        else:
            # Sin imagen de fondo
            self.interactive_viewer.set_background(None)

    def _on_background_image_change(self):
        """
        Callback cuando cambia la imagen de fondo
        Actualiza el viewer y el estado del botón de ajustes
        """
        # Sincronizar con preferencias globales (como archivo físico solicitado)
        # IMPORTANTE: Guardar caché físico ANTES de refrescar el visor
        try:
            cache_dir = get_background_cache_dir()
            current_face = self.current_face  # CARA o DORSO
            manager = self._get_current_background_image_manager()
            cache_path = os.path.join(cache_dir, f"cache_bg_{current_face.lower()}.png")

            if manager.image_loaded:
                manager.save_preview_to_file(cache_path)
            else:
                # Si no hay imagen, asegurar que el archivo de caché física NO existe
                if os.path.exists(cache_path):
                    try:
                        os.unlink(cache_path)
                        print(f"[PREFERENCES] Caché física eliminada: {cache_path}")
                    except Exception as ex:
                        print(f"[PREFERENCES] No se pudo eliminar caché física: {ex}")

            # Obtener configs actuales
            cara_config = self.background_image_managers["CARA"].get_image_config()
            dorso_config = self.background_image_managers["DORSO"].get_image_config()

            # Limpiar base64 para que el JSON de preferencias sea ligero
            if "base64" in cara_config:
                del cara_config["base64"]
            if "base64" in dorso_config:
                del dorso_config["base64"]

            save_last_backgrounds(cara_config, dorso_config)
        except Exception as e:
            print(f"[PREFERENCES] Error al sincronizar fondos: {e}")

        # Actualizar el viewer (ahora encontrará el cache_path actualizado o None)
        self._refresh_viewer()

        # Actualizar el estado del botón de ajustes de imagen
        self._update_image_settings_button_state(do_update=True)

        # FASE 4: Marcar como modificado
        self._mark_modified()

    def _on_spot_colors_found(self, spots: list):
        """
        Callback llamado cuando un BackgroundImageManager extrae colores spot de un PDF.
        Acumula los spots y los pasa al ColorPickerDialog del TextStyleManager.
        """
        if not spots:
            return
        # Añadir solo spots nuevos (sin duplicar por nombre)
        existing_names = {s.get("name") for s in self.extracted_spot_colors}
        for s in spots:
            if s.get("name") not in existing_names:
                self.extracted_spot_colors.append(s)
                existing_names.add(s.get("name"))
        print(
            f"[SPOTS] Acumulados {len(self.extracted_spot_colors)} colores spot: "
            f"{[s['name'] for s in self.extracted_spot_colors]}"
        )
        # Propagar al TextStyleManager (maneja internamente si el picker está creado o no)
        try:
            self.text_style_manager.set_extracted_spots(self.extracted_spot_colors)
        except Exception as e:
            print(f"[SPOTS] No se pudo actualizar el picker de texto: {e}")

        # Propagar al BarcodeProfileManager
        if hasattr(self, "barcode_ui_manager") and self.barcode_ui_manager:
            try:
                self.barcode_ui_manager.profile_manager.set_extracted_spots(
                    self.extracted_spot_colors
                )
            except Exception as e:
                print(f"[SPOTS] No se pudo actualizar el picker de barcodes: {e}")

        # Propagar al VariableTextProfileManager
        if hasattr(self, "variable_text_ui_manager") and self.variable_text_ui_manager:
            try:
                self.variable_text_ui_manager.profile_manager.set_extracted_spots(
                    self.extracted_spot_colors
                )
            except Exception as e:
                print(f"[SPOTS] No se pudo actualizar el picker de texto variable: {e}")

    def _update_page_size_text(self):
        """
        Actualiza el texto de tamaño de página en la UI
        Muestra tamaño base (corte) y sangre por separado
        """
        # Convertir tamaño según la unidad actual y preparar etiquetas sin repetir la unidad
        width_converted = convert_from_mm(self.page_width_mm, self.current_unit)
        height_converted = convert_from_mm(self.page_height_mm, self.current_unit)

        # Formatos numéricos según unidad (sin sufijo de unidad)
        if self.current_unit == UNIT_PX:
            size_text = f"{width_converted:.0f} x {height_converted:.0f}"
        elif self.current_unit == UNIT_INCHES:
            size_text = f"{width_converted:.2f} x {height_converted:.2f}"
        elif self.current_unit == UNIT_PICAS:
            size_text = f"{width_converted:.1f} x {height_converted:.1f}"
        else:  # UNIT_MM
            size_text = f"{width_converted:.0f} x {height_converted:.0f}"

        unit_label = _unit_abbr(self.current_unit)

        # Añadir sangre si es mayor que 0
        if self.bleed_mm > 0:
            bleed_converted = convert_from_mm(self.bleed_mm, self.current_unit)

            # Calcular tamaño total (corte + sangre en ambos lados)
            total_width = convert_from_mm(
                self.page_width_mm + (self.bleed_mm * 2), self.current_unit
            )
            total_height = convert_from_mm(
                self.page_height_mm + (self.bleed_mm * 2), self.current_unit
            )

            # Formatos numéricos (sin unidad)
            if self.current_unit == UNIT_PX:
                bleed_text = f"{bleed_converted:.0f}"
                total_text = f"{total_width:.0f} x {total_height:.0f}"
            elif self.current_unit == UNIT_INCHES:
                bleed_text = f"{bleed_converted:.2f}"
                total_text = f"{total_width:.2f} x {total_height:.2f}"
            elif self.current_unit == UNIT_PICAS:
                bleed_text = f"{bleed_converted:.1f}"
                total_text = f"{total_width:.1f} x {total_height:.1f}"
            else:
                bleed_text = f"{bleed_converted:.0f}"
                total_text = f"{total_width:.0f} x {total_height:.0f}"

            self.page_size_text.value = (
                t("Tamaño de página: {0} + {1} Sangre = {2}").format(
                    size_text, bleed_text, total_text
                )
                + f" {unit_label}"
            )
        else:
            self.page_size_text.value = (
                t("Tamaño de página: {0}").format(size_text) + f" {unit_label}"
            )

        self.page_size_text.update()

    # ══════════════════════════════════════════════════════════════════════════════
    # AUXILIARES EXPORTACIÓN
    # ══════════════════════════════════════════════════════════════════════════════

    def _adjust_positions_for_export(self, positions: dict) -> dict:
        """
        Aplica las correcciones visuales (offsets) a las coordenadas para que el PDF
        coincida exactamente con el Viewer.

        El Viewer aplica un offset visual (Left Bearing + Corrección Manual) que no está
        en la coordenada 'x' base. El PDF generator espera coordenadas base, pero
        como no queremos ensuciar su lógica, pre-calculamos la posición final aquí.
        """
        # from metrics_analisys import FontMetricsCache
        # No usamos 'copy.deepcopy' porque puede fallar si existen referencias a objetos de contexto (Flet/Asyncio)
        # Hacemos una copia manual de 1 nivel que es segura y más rápida, ya que solo modificamos 'x'.

        # Usar el singleton de métricas (DEFAULT_FONT_METRICS) para obtener métricas correctamente
        from utils.metrics_analisys import DEFAULT_FONT_METRICS

        # Constante de conversión local
        PT_TO_MM = 25.4 / 72.0

        # Copia segura: iterar y copiar cada diccionario de posición individualmente
        adjusted_positions = {}
        if positions:
            for k, v in positions.items():
                if isinstance(v, dict):
                    adjusted_positions[k] = v.copy()
                else:
                    # Fallback por si acaso
                    adjusted_positions[k] = v

        print("[EXPORT] Ajustando posiciones para sincronización visual WYSIWYG...")

        for num_id, data in adjusted_positions.items():
            try:
                pos_type = data.get("type", "number")
                if pos_type == "barcode":
                    # Resolver campos de perfil desde el BarcodeProfile real
                    profile_name = data.get("profile_name", "<Default>")
                    profile = (
                        self.barcode_ui_manager._find_profile(profile_name)
                        if hasattr(self, "barcode_ui_manager") and profile_name
                        else None
                    )
                    if profile is not None:
                        data["color"] = profile.color
                        data["color_cmyk"] = (
                            list(profile.color_cmyk) if profile.color_cmyk else None
                        )
                        data["color_space"] = profile.color_space
                        data["color_name"] = profile.color_name
                        data["color_tint"] = profile.color_tint
                        data["text_color"] = profile.text_color
                        data["text_color_cmyk"] = (
                            list(profile.text_color_cmyk)
                            if profile.text_color_cmyk
                            else None
                        )
                        data["text_color_space"] = profile.text_color_space
                        data["text_color_name"] = profile.text_color_name
                        data["text_color_tint"] = profile.text_color_tint
                        data["bar_width"] = profile.bar_width
                        data["bar_height"] = profile.bar_height
                        if profile.symbology == "upca":
                            bw = profile.bar_width or 37.29
                            bh = profile.bar_height or 25.91
                            data["bar_width"] = max(29.83, bw)
                            data["bar_height"] = max(20.73, bh)
                        if profile.symbology == "upce":
                            bw = profile.bar_width or 22.11
                            bh = profile.bar_height or 25.91
                            data["bar_width"] = max(17.69, bw)
                            data["bar_height"] = max(20.73, bh)
                        data["symbology"] = profile.symbology
                        data["value_source"] = profile.value_source
                        data["mask"] = profile.mask
                        data["error_correction"] = profile.error_correction
                        data["barcode_font_family"] = profile.barcode_font_family
                        data["barcode_font_size"] = profile.barcode_font_size
                        data["itf14_quiet_zone_mm"] = profile.itf14_quiet_zone_mm
                        data["itf14_bearer_thickness_mm"] = (
                            profile.itf14_bearer_thickness_mm
                        )
                        data["itf14_bearer_sides"] = profile.itf14_bearer_sides
                        data["itf14_gtin_type"] = profile.itf14_gtin_type
                        data["itf14_printer_type"] = profile.itf14_printer_type
                        data["itf14_hri_gap_mm"] = profile.itf14_hri_gap_mm
                        data["itf14_hri_position"] = profile.itf14_hri_position
                        data["code39_hri_gap_mm"] = profile.code39_hri_gap_mm
                        data["code39_hri_position"] = profile.code39_hri_position
                        data["code128_hri_gap_mm"] = profile.code128_hri_gap_mm
                        data["ean5_hri_gap_mm"] = profile.ean5_hri_gap_mm
                        data["isbn13_show_title"] = profile.isbn13_show_title
                        data["pdf417_height"] = profile.pdf417_height
                        data["pdf417_size"] = profile.pdf417_size
                        data["datamatrix_width"] = profile.datamatrix_width
                        data["datamatrix_height"] = profile.datamatrix_height
                        data["datamatrix_format"] = profile.datamatrix_format
                        data["datamatrix_hri_gap_mm"] = profile.datamatrix_hri_gap_mm
                        data["datamatrix_hri_position"] = profile.datamatrix_hri_position
                        data["datamatrix_hri_align"] = getattr(profile, "datamatrix_hri_align", "bottom_center")
                        data["datamatrix_hri_line_spacing"] = getattr(profile, "datamatrix_hri_line_spacing", 1.0)
                        data["datamatrix_del_open"] = profile.datamatrix_del_open
                        data["datamatrix_del_close"] = (
                            profile.datamatrix_del_close
                            if profile.datamatrix_del_close is not None
                            else "|"
                        )
                        data["qr_hri_gap_mm"] = getattr(profile, "qr_hri_gap_mm", 2.0)
                        data["qr_hri_position"] = getattr(profile, "qr_hri_position", "below")
                        data["qr_hri_align"] = getattr(profile, "qr_hri_align", "bottom_center")
                        data["qr_hri_line_spacing"] = getattr(profile, "qr_hri_line_spacing", 1.0)
                        data["qr_del_open"] = getattr(profile, "qr_del_open", "") or ""
                        data["qr_del_close"] = getattr(profile, "qr_del_close", "|") or "|"
                        data["pdf417_hri_gap_mm"] = getattr(profile, "pdf417_hri_gap_mm", 2.0)
                        data["pdf417_hri_position"] = getattr(profile, "pdf417_hri_position", "below")
                        data["pdf417_hri_align"] = getattr(profile, "pdf417_hri_align", "bottom_center")
                        data["pdf417_hri_line_spacing"] = getattr(profile, "pdf417_hri_line_spacing", 1.0)
                        data["pdf417_del_open"] = getattr(profile, "pdf417_del_open", "") or ""
                        data["pdf417_del_close"] = getattr(profile, "pdf417_del_close", "|") or "|"
                        data["qr_del_close_newline"] = bool(getattr(profile, "qr_del_close_newline", False))
                        data["pdf417_del_close_newline"] = bool(getattr(profile, "pdf417_del_close_newline", False))
                        data["datamatrix_del_close_newline"] = bool(getattr(profile, "datamatrix_del_close_newline", False))
                        # Cara no restaurada (impresión directa tras abrir): el
                        # generador salta el código si barcode_value está vacío.
                        # Los caminos numbering/excel lo sobreescriben por página.
                        if not data.get("barcode_value"):
                            data["barcode_value"] = (
                                getattr(profile, "sample_value", "") or ""
                            )
                    else:
                        print(
                            f"  [Pos {num_id}] BARCODE - perfil '{profile_name}' no encontrado, usando pos_data"
                        )
                    continue
                if pos_type == "variable_text":
                    # Sin corrección legacy por 'alignment': el sistema de anclas (anchor +
                    # text_alignment + box_w tight de measure_vt_box) ya posiciona el texto
                    # pegado a la guía. Aplicar aquí un offset extra desplazaba el texto
                    # (p. ej. derecha) según el campo legacy 'alignment' por posición.
                    continue

                # Obtener datos de fuente para numeradora
                style_name = data.get("text_style", "<Default>")
                profile = self.text_style_manager.get_profile(style_name)
                font_size = profile.font_size
                font_family = profile.font_family
                font_style = profile.font_style

                font_path = getattr(profile, "resolved_font_path", None)
                if not font_path:
                    try:
                        from utils.pdf_generator import (
                            _find_system_font_file,
                        )

                        fpath, fidx = _find_system_font_file(
                            profile.font_family, profile.font_style
                        )
                        if fpath:
                            font_path = fpath
                    except Exception:
                        font_path = None

                print(f"    [Pos {num_id}] Resolved font_path: {font_path}")

                # Obtener métricas (usar singleton y pasar font_size)
                try:
                    metrics = DEFAULT_FONT_METRICS.get_metrics(font_path, font_size)
                except Exception as ex:
                    print(
                        f"    [Pos {num_id}] Warning: no se pudieron obtener métricas para '{font_path}' (size={font_size}): {ex}"
                    )
                    metrics = {"font_size": 12.0, "left_bearing": 0.0}

                ref_size = metrics.get("font_size", 12.0)
                lsb_pt = metrics.get("left_bearing", 0.0)
                real_bearing_ratio = lsb_pt / ref_size

                from utils.constants import (
                    PDF_VISUAL_CORRECTION_LEFT,
                    PDF_VISUAL_CORRECTION_CENTER,
                    PDF_VISUAL_CORRECTION_RIGHT,
                )

                alignment = data.get("alignment", "izquierda")

                if alignment == "izquierda":
                    final_ratio = (
                        max(real_bearing_ratio, 0.0) + PDF_VISUAL_CORRECTION_LEFT
                    )
                    offset_pt = font_size * final_ratio
                elif alignment == "centro":
                    final_ratio = (
                        max(real_bearing_ratio, 0.0) / 2.0
                    ) + PDF_VISUAL_CORRECTION_CENTER
                    offset_pt = font_size * final_ratio
                else:
                    final_ratio = PDF_VISUAL_CORRECTION_RIGHT
                    offset_pt = -(font_size * final_ratio)

                print(
                    f"    [Pos {num_id}] Alineación: {alignment}, Offset Final (pt): {offset_pt:.3f}"
                )

                rotation_value = data.get("rotation", 0)
                if isinstance(rotation_value, str):
                    rotation_value = int(rotation_value.replace("°", "").strip())

                rad = math.radians(rotation_value)
                original_x = data.get("x", 0.0)
                original_y = data.get("y", 0.0)

                data["x"] = original_x - (offset_pt * math.cos(rad) * PT_TO_MM)
                data["y"] = original_y - (offset_pt * math.sin(rad) * PT_TO_MM)

                print(
                    f"  [Pos {num_id}] Font: {font_family}, Size: {font_size}pt, Rot: {rotation_value}°"
                )
                print(f"    LSB (pt): {lsb_pt:.3f}, final_ratio={final_ratio:.6f}")
                print(f"    Offset: {offset_pt:.3f}pt -> {offset_pt * PT_TO_MM:.4f}mm")
                print(f"    Pos before: ({original_x:.4f}, {original_y:.4f})mm")
                print(f"    Pos after: ({data['x']:.4f}, {data['y']:.4f})mm")
                user_x_off = data.get("x_offset_mm", 0.0)
                if user_x_off:
                    print(
                        f"    User x_offset_mm present: {user_x_off:.4f}mm (note: applied later in render)"
                    )

            except Exception as e:
                print(f"  [Pos {num_id}] Error calculando offset: {e}")
                from utils.error_logger import log_error

                log_error(
                    f"_adjust_positions_for_export pos {num_id}: {e}", exc_info=True
                )

        return adjusted_positions

    # ══════════════════════════════════════════════════════════════════════════════
    # EXPORTACIÓN A PDF
    # ══════════════════════════════════════════════════════════════════════════════

    def _on_export_pdf(self, e):
        """Abre el diálogo de exportación a PDF"""
        print("[EXPORT] Abriendo diálogo de exportación a PDF...")

        # Rango del diálogo = NÚMEROS del proyecto (misma unidad que el
        # formulario principal: el generador emite números × copias).
        # No leer pages_field: puede estar stale si el usuario acaba de cambiar incremento
        try:
            gs = self.global_settings
            s = int(gs.get("start", 1))
            e_ = int(gs.get("end", 1))
            inc = int(gs.get("increment", 1)) or 1
            numeros = ((e_ - s) // inc) + 1 if e_ >= s else 1
            total_numbers = max(1, numeros)
        except Exception:
            try:
                total_numbers = max(1, int(self.pages_field.value))
            except (ValueError, AttributeError):
                total_numbers = 1000

        print(f"[EXPORT] Numeración del proyecto (derivado de global_settings): {total_numbers} números")

        # Crear y mostrar diálogo
        _cara_mgr = self.background_image_managers["CARA"]
        _dorso_mgr = self.background_image_managers["DORSO"]
        _has_cara_bg = bool(_cara_mgr.image_loaded and _cara_mgr.image_path)
        _has_dorso_bg = bool(
            self.double_sided_enabled
            and _dorso_mgr.image_loaded
            and _dorso_mgr.image_path
        )
        dialog = PDFExportDialog(
            self.page,
            on_export=self._execute_pdf_export,
            default_start=1,
            default_end=total_numbers,
            double_sided=self.double_sided_enabled,
            project_name=self.project_name,
            num_copies=self.global_settings.get("copies", 1),
            max_numbers=total_numbers,
            has_cara_background=_has_cara_bg,
            has_dorso_background=_has_dorso_bg,
        )
        dialog.show()

    def _on_preview_current_page(self, e):
        """Genera un PDF de la página actualmente vista en una ruta temporal fija y lo abre."""
        print(
            "[PREVIEW] Generando PDF de previsualización para la página",
            self.current_page,
        )

        # Preparar ruta temporal fija
        temp_dir = self._preview_temp_dir
        temp_path = self._preview_temp_path

        # Eliminar previo si existe (para garantizar sobreescritura limpia)
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except Exception:
            pass

        start_page = self.current_page
        end_page = self.current_page

        # Preparar backgrounds
        cara_background = None
        dorso_background = None
        cara_manager = self.background_image_managers["CARA"]
        if cara_manager.image_loaded:
            cara_background = cara_manager.get_image_config()

        if self.double_sided_enabled:
            dorso_manager = self.background_image_managers["DORSO"]
            if dorso_manager.image_loaded:
                dorso_background = dorso_manager.get_image_config()

        def worker_preview():
            try:
                # Pre-cargar y cachear fuentes usadas por los estilos disponibles
                try:
                    from utils.pdf_generator import preload_fonts

                    profiles = self.text_style_manager.get_profiles()
                    styles_to_preload = [
                        {"font_name": p.font_family, "font_style": p.font_style}
                        for p in profiles
                    ]
                    if styles_to_preload:
                        preload_fonts(styles_to_preload, page=None)
                        print(
                            f"[PRELOAD] Fuentes precargadas: {len(styles_to_preload)}"
                        )
                except Exception as e:
                    print(f"[PREVIEW] Warning: no se pudo precargar fuentes: {e}")

                # Ajustar posiciones para exportación (WYSIWYG)
                adjusted_cara = self._adjust_positions_for_export(
                    self.positions["CARA"]
                )
                adjusted_dorso = self._adjust_positions_for_export(
                    self.positions["DORSO"]
                )

                generar_pdf_numerado(
                    output_path=temp_path,
                    start_page=start_page,
                    end_page=end_page,
                    page_width_mm=self.page_width_mm,
                    page_height_mm=self.page_height_mm,
                    bleed_mm=self.bleed_mm,
                    double_sided=self.double_sided_enabled,
                    cara_settings={
                        **self.face_settings["CARA"],
                        **self.global_settings,
                    },
                    dorso_settings={
                        **self.face_settings["DORSO"],
                        **self.global_settings,
                    },
                    cara_positions=adjusted_cara,
                    dorso_positions=adjusted_dorso,
                    text_style_manager=self.text_style_manager,
                    cara_background=cara_background,
                    dorso_background=dorso_background,
                    progress_callback=None,
                )
                # Diagnóstico: extraer texto de cada página y loguear para verificar numeradoras
                try:
                    import fitz as _fitz

                    try:
                        _doc = _fitz.open(temp_path)
                        for i in range(len(_doc)):
                            ptext = _doc[i].get_text("text")
                            print(
                                f"[PREVIEW-DEBUG] Página {i+1} texto extraído:\n{ptext}\n---"
                            )
                        _doc.close()
                    except Exception as ex_tex:
                        print(
                            f"[PREVIEW-DEBUG] No se pudo extraer texto del PDF: {ex_tex}"
                        )
                except Exception:
                    pass

                # Abrir el PDF generado
                try:
                    import subprocess

                    sistema = platform.system()
                    if sistema == "Darwin":
                        subprocess.run(["open", temp_path])
                    elif sistema == "Windows":
                        os.startfile(temp_path)
                    else:
                        subprocess.run(["xdg-open", temp_path])
                except Exception as ex:
                    print(f"[PREVIEW] No se pudo abrir el PDF: {ex}")
            except Exception as ex:
                print(f"[PREVIEW] Error generando PDF de vista previa: {ex}")

        # Ejecutar en hilo para no bloquear UI
        t = threading.Thread(target=worker_preview, daemon=True)
        t.start()

    def _execute_pdf_export(self, export_config: dict):
        """
        Ejecuta la exportación PDF en un thread separado.
        Similar a impo_ui.abrir_dialogo_generar_pdf

        Args:
            export_config: Dict con start_page, end_page, output_path
        """
        print(f"[EXPORT] Iniciando exportación: {export_config}")

        # Extraer configuración
        start_page = export_config["start_page"]
        end_page = export_config["end_page"]
        output_path = export_config["output_path"]
        optimize_level = int(export_config.get("optimize_level", 1))
        generate_fiery = bool(export_config.get("generate_fiery", False))
        omit_background = bool(export_config.get("omit_background", False))
        create_master = bool(export_config.get("create_master", False))
        copies = max(
            1, int(export_config.get("copies", self.global_settings.get("copies", 1)))
        )

        # start/end YA son los números del proyecto (unidad = numeración,
        # igual que el formulario principal). El generador emite números ×
        # caras × copies en una sola fase: 1000 × 3 = 3000.
        logical_start_page = start_page
        logical_end_page = end_page

        # Niveles de optimización seleccionables desde el diálogo de impresión.
        # 0: sin optimizar, 1: fuentes optimizadas (recomendado),
        # 2: fuentes e imágenes optimizadas.
        save_opts_by_level = {
            0: dict(garbage=0, deflate=False, clean=False, use_objstms=0),
            1: dict(garbage=2, deflate=True, clean=False, use_objstms=1),
            2: dict(garbage=4, deflate=True, clean=False, use_objstms=1),
        }
        save_opts_final = save_opts_by_level.get(optimize_level, save_opts_by_level[1])
        enable_subset_fonts = optimize_level >= 1

        # Números pedidos × caras × copies = páginas físicas emitidas.
        # La fusión emite exacto: emitido = visible, sin recorte.
        num_pages = end_page - start_page + 1
        _faces = 2 if self.double_sided_enabled else 1
        total_pdf_pages = num_pages * _faces * copies

        # Denominador del progreso = emitido físico (igual que visible).
        total_emitted = total_pdf_pages

        # ═══════════════════════════════════════════════════════════════════
        # CREAR DIÁLOGO DE PROGRESO
        # ═══════════════════════════════════════════════════════════════════

        progress_bar = ft.ProgressBar(
            value=0,
            width=400,
            bgcolor=FONDO_TEXTFIELDS_COLOR,
            color=BOTONES_GENERICOS_OVERLAY_COLOR,
        )

        counter_label = ft.Text(
            t("Páginas generadas:"),
            size=13,
            color=TEXTO_COLOR_GENERICO,
            text_align=ft.TextAlign.CENTER,
            width=440,
        )
        counter_numbers = ft.Text(
            f"{'0'.rjust(len(str(total_emitted)))}/{total_emitted}",
            size=13,
            color=TEXTO_COLOR_GENERICO,
            text_align=ft.TextAlign.CENTER,
            width=440,
        )
        counter_block = ft.Container(
            width=440,
            content=ft.Column(
                [
                    ft.Row([counter_label], alignment=ft.MainAxisAlignment.CENTER),
                    ft.Row([counter_numbers], alignment=ft.MainAxisAlignment.CENTER),
                ],
                spacing=4,
                tight=True,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

        # Estado de cancelación
        cancelado = {"valor": False}

        def on_cancel_click(e):
            cancelado["valor"] = True
            print("[EXPORT] Cancelación solicitada por el usuario")

        cancel_button = ft.Button(
            t("Cancelar"),
            on_click=on_cancel_click,
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
        )

        progress_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Container(
                content=ft.Text(
                    t("Generando PDF"),
                    size=18,
                    weight=ft.FontWeight.BOLD,
                    color=TEXTO_COLOR_GENERICO,
                    text_align=ft.TextAlign.CENTER,
                ),
                alignment=ft.Alignment.CENTER,
            ),
            content=ft.Container(
                content=ft.Column(
                    [
                        counter_block,
                        ft.Container(height=12),
                        progress_bar,
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                width=480,
                height=170,
                padding=ft.Padding.only(left=20, right=20, top=18, bottom=18),
            ),
            actions=[cancel_button],
            actions_alignment=ft.MainAxisAlignment.CENTER,
            bgcolor=FONDO_ALERT_DIALOG,
        )

        # Mostrar diálogo de progreso
        # Mostrar diálogo de progreso usando overlay (más robusto)
        self.page.show_dialog(progress_dialog)

        # ═══════════════════════════════════════════════════════════════════
        # WORKER THREAD
        # ═══════════════════════════════════════════════════════════════════

        # Flet 1.0: el transporte es asíncrono y NO es thread-safe. Todo
        # pintado de UI debe ejecutarse en el event loop del page.
        loop = self.page.loop

        def _ui(fn):
            loop.call_soon_threadsafe(fn)

        def worker():
            try:
                final_phase_ui = {"active": False}
                # Coalescing: el worker puede disparar cientos de callbacks/s;
                # solo el último estado interesa y se pinta como mucho 1x/80ms.
                _latest = {"label": None, "num": None, "bar": 0, "show_bar": False}
                _paint = {"queued": False, "first": True}

                # Callback de progreso (se ejecuta en el worker). Los cálculos
                # quedan aquí; el pintado de controles se programa en el event
                # loop del page (_ui) porque el transporte Flet 1.0 no es
                # thread-safe (page.update() desde otro hilo no llega al cliente).
                def _apply_progress(label, num, bar, show_bar):
                    try:
                        if show_bar:
                            progress_bar.visible = True
                        counter_label.value = label
                        counter_numbers.value = num
                        progress_bar.value = bar
                        self.page.update(progress_bar, counter_label, counter_numbers)
                    except Exception as e:
                        print(f"[WARN] Error menor pintando progreso UI: {e}")

                def _paint_now():
                    # Limpiar la bandera ANTES de leer _latest: si el worker
                    # escribe entre medias encola otro paint y no se pierde.
                    _paint["queued"] = False
                    _paint["first"] = False
                    show_bar = _latest["show_bar"]
                    _latest["show_bar"] = False  # sticky: consumir al pintar
                    if _latest["label"] is None:
                        return
                    _apply_progress(_latest["label"], _latest["num"], _latest["bar"], show_bar)

                def _queue_paint():
                    if _paint["queued"]:
                        return
                    _paint["queued"] = True
                    if _paint["first"]:
                        loop.call_soon_threadsafe(_paint_now)
                    else:
                        loop.call_soon_threadsafe(lambda: loop.call_later(0.08, _paint_now))

                def _close_progress_dialog():
                    try:
                        progress_dialog.content = None
                        self.page.pop_dialog()
                    except Exception:
                        try:
                            progress_dialog.open = False
                        except Exception:
                            pass
                    try:
                        if progress_dialog in self.page.overlay:
                            self.page.overlay.remove(progress_dialog)
                    except Exception:
                        pass
                    try:
                        self.page.update()
                    except Exception:
                        pass

                def actualizar_progreso(current, total):
                    if cancelado["valor"]:
                        # No lanzar error inmediatamente aquí, dejar que el worker lo maneje
                        # o simplemente devoler control
                        raise InterruptedError(t("Generación cancelada por el usuario"))

                    try:
                        # Calcular valores en el worker
                        is_final_phase = total < 0
                        shown_total = abs(total)

                        if is_final_phase:
                            # Fase final (subset de lotes / unión / save): el
                            # diálogo NO se puede quedar congelado — label de
                            # fase + barra indeterminada animada. current>=0
                            # → contador real (0/15 lotes…, luego 2400/3000
                            # páginas); current<0 (-1/-2) → solo label+anim.
                            _latest["label"] = t("Optimizando PDF final:")
                            if current >= 0:
                                _latest["num"] = (
                                    f"{str(current).rjust(len(str(shown_total)))}/{shown_total}"
                                )
                            _latest["bar"] = None
                            _latest["show_bar"] = True
                            _queue_paint()
                            return

                        show_bar = final_phase_ui["active"]
                        if show_bar:
                            final_phase_ui["active"] = False

                        label = t("Páginas generadas:")
                        num = f"{str(current).rjust(len(str(shown_total)))}/{shown_total}"
                        bar = max(0, min(1, current / shown_total)) if shown_total else 0

                        # Actualizar estado compartido y encolar UN paint coalescido
                        _latest["label"] = label
                        _latest["num"] = num
                        _latest["bar"] = bar
                        if show_bar:
                            _latest["show_bar"] = True
                        _queue_paint()

                    except InterruptedError:
                        raise
                    except Exception as e:
                        # Ignorar errores de actualización de UI para no detener el proceso
                        print(f"[WARN] Error menor actualizando progreso UI: {e}")

                # Obtener configuración de background images
                cara_background = None
                dorso_background = None

                # Limpiar store interno de PyMuPDF para evitar arrastres de caché
                # tras cargar/eliminar fondos pesados en la misma sesión.
                try:
                    import fitz as _fitz

                    _fitz.TOOLS.store_shrink(100)
                except Exception:
                    pass

                def _get_valid_background_config(face_key, manager):
                    """Devuelve config de fondo solo si el estado es realmente válido."""
                    if not manager.image_loaded:
                        return None

                    cfg = manager.get_image_config() or {}
                    bg_path = cfg.get("image_path") or cfg.get("path")

                    # Si quedó estado inconsistente tras eliminar fondo, limpiarlo aquí.
                    if not bg_path or not os.path.exists(bg_path):
                        print(
                            f"[EXPORT][WARN] Fondo {face_key} inválido o inexistente, limpiando estado"
                        )
                        try:
                            manager.clear_image()
                        except Exception:
                            pass
                        return None

                    return cfg

                cara_manager = self.background_image_managers["CARA"]
                if omit_background:
                    cara_background = None
                    dorso_background = None
                else:
                    cara_background = _get_valid_background_config("CARA", cara_manager)

                    if self.double_sided_enabled:
                        dorso_manager = self.background_image_managers["DORSO"]
                        dorso_background = _get_valid_background_config(
                            "DORSO", dorso_manager
                        )

                print(f"[EXPORT] Background CARA: {bool(cara_background)}")
                print(f"[EXPORT] Background DORSO: {bool(dorso_background)}")

                # FUSIÓN: generar_pdf_numerado emite ×copies al crear cada
                # lógico → escribe el PDF final directo (no hay Phase 2).
                print(f"[EXPORT] Llamando a generar_pdf_numerado (copies={copies})...")

                # Ajustar posiciones para exportación (WYSIWYG)
                adjusted_cara = self._adjust_positions_for_export(
                    self.positions["CARA"]
                )
                adjusted_dorso = self._adjust_positions_for_export(
                    self.positions["DORSO"]
                )

                # Limpieza defensiva AL INICIAR (segura: aún no hay procesos
                # escribiendo). Al borrar el output previo, generar trata el
                # destino como "no existente" → un parcial suyo al cancelar
                # también se elimina (output_existed_before).
                try:
                    if os.path.exists(output_path):
                        os.remove(output_path)
                except Exception:
                    pass

                generar_pdf_numerado(
                    output_path=output_path,
                    start_page=logical_start_page,
                    end_page=logical_end_page,
                    page_width_mm=self.page_width_mm,
                    page_height_mm=self.page_height_mm,
                    bleed_mm=self.bleed_mm,
                    double_sided=self.double_sided_enabled,
                    cara_settings={
                        **self.face_settings["CARA"],
                        **self.global_settings,
                    },
                    dorso_settings={
                        **self.face_settings["DORSO"],
                        **self.global_settings,
                    },
                    cara_positions=adjusted_cara,
                    dorso_positions=adjusted_dorso,
                    text_style_manager=self.text_style_manager,
                    cara_background=cara_background,
                    dorso_background=dorso_background,
                    progress_callback=actualizar_progreso,
                    save_opts_final=save_opts_final,
                    use_copy_grouping=False,
                    enable_subset_fonts=enable_subset_fonts,
                    copies=copies,
                )

                if cancelado["valor"]:
                    raise InterruptedError(t("Generación cancelada por el usuario"))

                # Sin recorte: emitido = visible (números × caras × copies).
                visible_len = total_pdf_pages

                # Fiery: listas por copia sobre el físico emitido (= visible).
                # copies=1 → sin fiery (comportamiento previo).
                # logical_pages = páginas físicas por copia = lógicos × caras
                # (antes el return de merge_pdfs; ya no hay Phase 2).
                fiery_lists = {}
                if copies > 1:
                    logical_pages = (logical_end_page - logical_start_page + 1) * (
                        2 if self.double_sided_enabled else 1
                    )
                    if not self.double_sided_enabled:
                        fiery_lists = {
                            copia: [
                                p for p in (copia + j * copies for j in range(logical_pages))
                                if p <= visible_len
                            ]
                            for copia in range(1, copies + 1)
                        }
                    else:
                        fiery_lists = {copia: [] for copia in range(1, copies + 1)}
                        for b in range(logical_pages // 2):
                            for copia in range(1, copies + 1):
                                base = 2 * b * copies + 2 * (copia - 1)
                                for pg in (base + 1, base + 2):
                                    if pg <= visible_len:
                                        fiery_lists[copia].append(pg)

                    if generate_fiery and fiery_lists:
                        nombre_base = os.path.splitext(os.path.basename(output_path))[0]
                        ruta_fiery = os.path.join(
                            os.path.dirname(output_path),
                            f"{nombre_base}_Fiery.txt",
                        )
                        generar_archivo_fiery(fiery_lists, ruta_fiery)

                print(f"[EXPORT] PDF generado exitosamente")

                # ── Documento Maestro: PDF solo con imagen de fondo (1 pág/cara)
                if create_master and output_path:
                    try:
                        import fitz as _fitz_master
                        from utils.pdf_generator import add_background_to_page, set_pdf_boxes

                        master_path = os.path.splitext(output_path)[0] + "_Maestro.pdf"
                        print(f"[EXPORT] Generando documento maestro: {master_path}")

                        # Reconstruir configs de fondo (pueden haberse limpiado)
                        _cara_mgr = self.background_image_managers["CARA"]
                        _master_cara_bg = None
                        if _cara_mgr.image_loaded:
                            _cfg = _cara_mgr.get_image_config() or {}
                            if _cfg.get("image_path") and os.path.exists(_cfg["image_path"]):
                                _master_cara_bg = _cfg

                        _master_dorso_bg = None
                        if self.double_sided_enabled:
                            _dorso_mgr = self.background_image_managers["DORSO"]
                            if _dorso_mgr.image_loaded:
                                _cfg = _dorso_mgr.get_image_config() or {}
                                if _cfg.get("image_path") and os.path.exists(_cfg["image_path"]):
                                    _master_dorso_bg = _cfg

                        # Crear PDF con 1 o 2 páginas (tamaño físico CON sangre 216×106)
                        _master_doc = _fitz_master.open()
                        _page_w_pt = (self.page_width_mm + self.bleed_mm * 2) * 72 / 25.4
                        _page_h_pt = (self.page_height_mm + self.bleed_mm * 2) * 72 / 25.4

                        # Página CARA
                        _master_page = _master_doc.new_page(
                            width=_page_w_pt, height=_page_h_pt
                        )
                        set_pdf_boxes(
                            _master_page,
                            self.page_width_mm,
                            self.page_height_mm,
                            self.bleed_mm,
                        )
                        if _master_cara_bg:
                            add_background_to_page(
                                _master_page,
                                _master_cara_bg,
                                self.page_width_mm,
                                self.page_height_mm,
                                self.bleed_mm,
                            )

                        # Página DORSO (solo si doble cara)
                        if self.double_sided_enabled:
                            _dorso_page = _master_doc.new_page(
                                width=_page_w_pt, height=_page_h_pt
                            )
                            set_pdf_boxes(
                                _dorso_page,
                                self.page_width_mm,
                                self.page_height_mm,
                                self.bleed_mm,
                            )
                            if _master_dorso_bg:
                                add_background_to_page(
                                    _dorso_page,
                                    _master_dorso_bg,
                                    self.page_width_mm,
                                    self.page_height_mm,
                                    self.bleed_mm,
                                )

                        _master_doc.save(master_path, garbage=1, deflate=True)
                        _master_doc.close()
                        print(f"[EXPORT] Documento maestro generado: {master_path}")
                    except Exception as _master_err:
                        print(f"[EXPORT][WARN] Error generando documento maestro: {_master_err}")

                # Cerrar y limpiar diálogo de progreso
                _ui(_close_progress_dialog)

                # Mostrar diálogo de éxito
                def mostrar_dialogo_exito():
                    success_dialog = None
                    # num_pages = números; total_pdf_pages = físico emitido
                    mensaje_pages = t("{0} páginas").format(total_pdf_pages)
                    if self.double_sided_enabled:
                        mensaje_pages = t(
                            "{0} páginas a doble cara ({1} páginas en el PDF)"
                        ).format(num_pages, total_pdf_pages)

                    # Función para abrir el PDF
                    def abrir_pdf(e):
                        try:
                            import subprocess

                            if platform.system() == "Darwin":  # macOS
                                subprocess.run(["open", output_path])
                            elif platform.system() == "Windows":
                                os.startfile(output_path)
                            else:  # Linux
                                subprocess.run(["xdg-open", output_path])
                        except Exception as ex:
                            print(f"[ERROR] No se pudo abrir el PDF: {ex}")

                    def abrir_carpeta(e):
                        try:
                            import subprocess

                            # Obtener el directorio del archivo
                            directorio = os.path.dirname(os.path.abspath(output_path))

                            sistema = platform.system()
                            if sistema == "Darwin":  # macOS
                                subprocess.run(["open", directorio], check=True)
                            elif sistema == "Windows":
                                subprocess.Popen(
                                    f'explorer "{directorio}"',
                                    shell=True,
                                    stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL,
                                )
                            else:  # Linux y otros
                                subprocess.run(["xdg-open", directorio], check=True)
                        except Exception as ex:
                            print(f"[ERROR] No se pudo abrir la carpeta: {ex}")

                    success_dialog = ft.AlertDialog(
                        modal=True,
                        title=ft.Container(
                            content=ft.Text(
                                "\u2713 " + t("PDF Generado"),
                                size=18,
                                weight=ft.FontWeight.BOLD,
                                color=TEXTO_COLOR_GENERICO,
                                text_align=ft.TextAlign.CENTER,
                            ),
                            alignment=ft.Alignment.CENTER,
                        ),
                        content=ft.Container(
                            content=ft.Column(
                                [
                                    ft.Text(
                                        t("Se generaron {0}").format(mensaje_pages),
                                        size=15,
                                        color=TEXTO_COLOR_GENERICO,
                                        weight=ft.FontWeight.W_500,
                                        text_align=ft.TextAlign.CENTER,
                                    ),
                                    ft.Container(height=16),
                                    ft.Text(
                                        t("PDF generado en:"),
                                        size=16,
                                        color=TEXTO_COLOR_GENERICO,
                                        text_align=ft.TextAlign.CENTER,
                                    ),
                                    ft.Container(height=8),
                                    ft.Text(
                                        output_path,
                                        size=14,
                                        color=TEXTO_COLOR_GENERICO,
                                        selectable=True,
                                        text_align=ft.TextAlign.CENTER,
                                    ),
                                ],
                                spacing=5,
                                tight=True,
                                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            width=540,
                            padding=ft.Padding(10, 10, 10, 10),
                        ),
                        actions=[
                            ft.Button(
                                t("Abrir PDF"),
                                icon=ft.Icons.OPEN_IN_NEW,
                                on_click=abrir_pdf,
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
                                width=120,
                            ),
                            ft.Button(
                                t("Abrir carpeta"),
                                icon=ft.Icons.FOLDER_OPEN,
                                on_click=abrir_carpeta,
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
                                width=140,
                            ),
                            ft.Button(
                                t("Cerrar"),
                                on_click=lambda e: setattr(
                                    success_dialog, "open", False
                                )
                                or self.page.update(),
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
                                width=110,
                            ),
                        ],
                        actions_alignment=ft.MainAxisAlignment.CENTER,
                        bgcolor=FONDO_ALERT_DIALOG,
                    )

                    self.page.show_dialog(success_dialog)

                # Ejecutar directamente (no usar run_task) → sí, en el event loop del page
                _ui(mostrar_dialogo_exito)

            except InterruptedError as ie:
                # Cancelación. NO se borra nada aquí: no sabemos si el proceso
                # que escribía ha terminado (evita errores al eliminar). La
                # limpieza del output parcial se hace AL INICIAR la siguiente
                # exportación (pre-remove de output_path) y el propio
                # generar borra su parcial si output no existía antes.
                print(f"[EXPORT] Exportación cancelada: {ie}")

                # Cerrar y limpiar diálogo de progreso
                _ui(_close_progress_dialog)

                # Mostrar mensaje de cancelación (Diálogo informativo)
                cancelado_msg = str(ie) if str(ie) else t("Exportación cancelada")

                def mostrar_cancelacion():
                    final_msg = cancelado_msg

                    cancel_dialog = ft.AlertDialog(
                        modal=True,
                        title=ft.Container(
                            content=ft.Text(
                                t("Exportación cancelada"),
                                size=18,
                                weight=ft.FontWeight.BOLD,
                                color=TEXTO_COLOR_GENERICO,
                                text_align=ft.TextAlign.CENTER,
                            ),
                            alignment=ft.Alignment.CENTER,
                        ),
                        content=ft.Container(
                            content=ft.Column(
                                [
                                    ft.Text(
                                        t(
                                            "La generación ha sido detenida por el usuario."
                                        ),
                                        size=15,
                                        color=TEXTO_COLOR_GENERICO,
                                        weight=ft.FontWeight.W_500,
                                        text_align=ft.TextAlign.CENTER,
                                    ),
                                    ft.Container(height=8),
                                    ft.Text(
                                        t("Resultado: {0}").format(final_msg),
                                        size=14,
                                        color=TEXTO_COLOR_GENERICO,
                                        text_align=ft.TextAlign.CENTER,
                                    ),
                                    ft.Container(height=6),
                                    ft.Text(
                                        t("No se ha generado archivo final."),
                                        size=13,
                                        color=TEXTO_COLOR_GENERICO,
                                        weight=ft.FontWeight.W_500,
                                        text_align=ft.TextAlign.CENTER,
                                    ),
                                ],
                                spacing=5,
                                tight=True,
                                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            width=400,
                            padding=ft.Padding(10, 10, 10, 10),
                        ),
                        actions=[
                            ft.Button(
                                t("Cerrar"),
                                on_click=lambda e: setattr(cancel_dialog, "open", False)
                                or self.page.update(),
                                bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
                                style=ft.ButtonStyle(
                                    color={
                                        ft.ControlState.DEFAULT: BOTONES_GENERICOS_COLOR,
                                        "hovered": BOTONES_GENERICOS_HOVER_COLOR,
                                    },
                                    padding=ft.Padding(0, 0, 0, 0),
                                    shape=ft.RoundedRectangleBorder(radius=10),
                                ),
                                width=100,
                            ),
                        ],
                        actions_alignment=ft.MainAxisAlignment.CENTER,
                        bgcolor=FONDO_ALERT_DIALOG,
                    )

                    self.page.show_dialog(cancel_dialog)

                _ui(mostrar_cancelacion)

            except Exception as e:
                print(f"[ERROR] Error fatal en worker: {e}")
                import traceback

                traceback.print_exc()
                error_detail = str(e)

                # Cerrar y limpiar diálogo de progreso
                _ui(_close_progress_dialog)

                # Mostrar diálogo de error
                def mostrar_error():
                    error_dialog = ft.AlertDialog(
                        modal=True,
                        title=ft.Container(
                            content=ft.Text(
                                t("✗ Error"),
                                size=18,
                                weight=ft.FontWeight.BOLD,
                                color=ft.Colors.RED,
                                text_align=ft.TextAlign.CENTER,
                            ),
                            alignment=ft.Alignment.CENTER,
                        ),
                        content=ft.Container(
                            content=ft.Column(
                                [
                                    ft.Text(
                                        t("Error al generar el PDF:"),
                                        size=14,
                                        color=TEXTO_COLOR_GENERICO,
                                    ),
                                    ft.Container(height=5),
                                    ft.Text(
                                        error_detail,
                                        size=12,
                                        color=ft.Colors.RED_300,
                                    ),
                                ],
                                spacing=5,
                                tight=True,
                            ),
                            width=450,
                            padding=20,
                        ),
                        actions=[
                            ft.Button(
                                t("Cerrar"),
                                on_click=lambda e: setattr(error_dialog, "open", False)
                                or self.page.update(),
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
                            )
                        ],
                        actions_alignment=ft.MainAxisAlignment.END,
                        bgcolor=FONDO_ALERT_DIALOG,
                    )

                    self.page.show_dialog(error_dialog)

                # Ejecutar directamente → en el event loop del page
                _ui(mostrar_error)

        # Iniciar thread
        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

    def _execute_package_project(self, folder_path: str, include_fonts: bool = False):
        """Empaqueta el proyecto adjuntando imágenes (y opcionalmente fuentes) a la carpeta.

        include_fonts: si True, crea carpeta 'fonts/' con las fuentes usadas por el proyecto y
        escribe un archivo 'fonts/fonts.json' con mapeo family|style -> file + ttc_index.
        """
        import shutil

        print(f"[PACKAGE] Empaquetando proyecto en: {folder_path}")

        # Crear carpeta si no existe
        os.makedirs(folder_path, exist_ok=True)

        # Recordar ruta original del proyecto para poder moverla tras copiar
        original_project_path = (
            self.current_project_path
            if getattr(self, "current_project_path", None)
            else None
        )

        # 1. Guardar archivo .pnb solo si NO existe en destino, o si la fuente está más reciente
        pnb_filename = (
            os.path.basename(self.current_project_path)
            if self.current_project_path
            else "proyecto.pnb"
        )
        pnb_path = os.path.join(folder_path, pnb_filename)
        pnb_saved = False

        if not os.path.exists(pnb_path):
            # No existe: guardamos
            self._save_project_to_pnb(pnb_path)
            pnb_saved = True
            print(f"[PACKAGE] Archivo PNB guardado: {pnb_path}")
        else:
            # Existe: comparar fechas de modificación para decidir si sobrescribir
            try:
                src_mtime = os.path.getmtime(self.current_project_path)
                dst_mtime = os.path.getmtime(pnb_path)
                if src_mtime > dst_mtime:
                    # Fuente más reciente: sobrescribir destino
                    self._save_project_to_pnb(pnb_path)
                    pnb_saved = True
                    print(
                        f"[PACKAGE] Archivo PNB destino sobrescrito (fuente más reciente): {pnb_path}"
                    )
                else:
                    print(
                        f"[PACKAGE] Archivo PNB ya existe en destino y está actualizado, no se sobrescribe"
                    )
            except Exception as ex:
                # En caso de error comparando, evitamos sobrescribir y lo notificamos
                print(
                    f"[PACKAGE] Archivo PNB ya existe en destino, no se sobrescribe (error comparando fechas: {ex})"
                )

        # 2. Copiar imágenes de fondo (si existen)
        images_copied = []
        images_skipped = []

        for face in ["CARA", "DORSO"]:
            manager = self.background_image_managers[face]
            if manager.image_loaded and manager.image_path:
                src_path = manager.image_path
                if os.path.exists(src_path):
                    filename = os.path.basename(src_path)
                    dest_path = os.path.join(folder_path, filename)

                    # Verificar si la imagen ya existe
                    if os.path.exists(dest_path):
                        # Comparar fechas de modificación
                        src_mtime = os.path.getmtime(src_path)
                        dest_mtime = os.path.getmtime(dest_path)

                        if src_mtime > dest_mtime:
                            # Imagen origen es más nueva, copiar
                            shutil.copy2(src_path, dest_path)
                            images_copied.append(f"{filename} (actualizada)")
                            print(f"[PACKAGE] Imagen actualizada: {filename}")
                        else:
                            # Imagen destino es igual o más nueva, mantener
                            images_skipped.append(filename)
                            print(
                                f"[PACKAGE] Imagen {filename} ya está actualizada en destino"
                            )
                    else:
                        # La imagen no existe en destino, copiar
                        shutil.copy2(src_path, dest_path)
                        images_copied.append(filename)
                        print(f"[PACKAGE] Imagen copiada: {filename}")

                    # IMPORTANT: actualizar la ruta de la imagen en el manager para que el .pnb resultante
                    # apunte a la copia local dentro del paquete (ruta absoluta en carpeta destino)
                    try:
                        manager.image_path = dest_path
                        manager.image_loaded = True
                        print(
                            f"[PACKAGE DEBUG] Ruta de imagen actualizada en manager {face}: {dest_path}"
                        )
                    except Exception as e_upd:
                        print(
                            f"[PACKAGE DEBUG] No se pudo actualizar image_path en manager {face}: {e_upd}"
                        )

        # 3. Copiar archivo Excel/CSV si está cargado
        excel_copied = False
        excel_skipped = False
        if self.excel_manager.is_loaded and self.excel_manager.filepath:
            excel_src = self.excel_manager.filepath
            if os.path.exists(excel_src):
                excel_filename = os.path.basename(excel_src)
                excel_dest = os.path.join(folder_path, excel_filename)

                if os.path.exists(excel_dest):
                    src_mtime = os.path.getmtime(excel_src)
                    dest_mtime = os.path.getmtime(excel_dest)
                    if src_mtime > dest_mtime:
                        shutil.copy2(excel_src, excel_dest)
                        excel_copied = True
                        print(f"[PACKAGE] Excel actualizado: {excel_filename}")
                    else:
                        excel_skipped = True
                        print(f"[PACKAGE] Excel ya está actualizado en destino")
                else:
                    shutil.copy2(excel_src, excel_dest)
                    excel_copied = True
                    print(f"[PACKAGE] Excel copiado: {excel_filename}")

                # Actualizar ruta en manager para que el .pnb apunte a la copia local
                try:
                    self.excel_manager._filepath = excel_dest
                except Exception as e_upd:
                    print(
                        f"[PACKAGE DEBUG] No se pudo actualizar filepath en excel_manager: {e_upd}"
                    )

        # 4. Incluir tipos de letra si se solicitó
        fonts_copied = []
        fonts_missing = []
        if include_fonts:
            try:
                from utils import pdf_generator as pdfgen

                # Determinar target automáticamente según la plataforma (Mac/PC)
                if sys.platform == "darwin":
                    target_label = "mac"
                elif sys.platform.startswith("win") or os.name == "nt":
                    target_label = "pc"
                else:
                    target_label = "pc"

                fonts_dir = os.path.join(folder_path, f"fonts-{target_label}")
                os.makedirs(fonts_dir, exist_ok=True)

                # Comprobar si podemos escribir en la carpeta de fuentes (test rápido)
                try:
                    import tempfile as _tempfile

                    with _tempfile.NamedTemporaryFile(
                        dir=fonts_dir, delete=True
                    ) as _tf:
                        pass
                except Exception as _perm_err:
                    msg = f"Permiso denegado al crear archivos en: {fonts_dir} ({_perm_err})"
                    fonts_missing.append(msg)
                    print(f"[PACKAGE DEBUG] {msg}")
                    print(
                        f"[PACKAGE DEBUG] Sugerencia: verifica permisos de la carpeta destino o concede acceso a Desktop/Documentos a la app/Terminal en Preferencias del Sistema (macOS)"
                    )
                    # No intentar copiar fuentes si no podemos escribir en la carpeta
                    include_fonts = False

                # Registrar contenido previo de la carpeta de fuentes (para evitar interpretar archivos creados por ejecuciones previas)
                try:
                    existing_files = set(os.listdir(fonts_dir))
                except Exception:
                    existing_files = set()

                # Recolectar fuentes usadas en posiciones CARA y DORSO:
                #  - numeradoras: text_style / text_style_name (TextStyle)
                #  - texto variable: profile_name -> VariableTextProfile
                #  - barcode HRI no-OCR: barcode_font_family (las OCR van incluidas en la app)
                used_fonts = {}  # key=(family, style) -> label
                profiles = (
                    {p.name: p for p in self.text_style_manager.get_profiles()}
                    if self.text_style_manager
                    else {}
                )
                for face in ["CARA", "DORSO"]:
                    positions = self.positions.get(face, {})
                    for num_id, pos in positions.items():
                        pos_type = pos.get("type", "number")
                        if pos_type == "variable_text":
                            vt_pname = pos.get("profile_name") or "<Default>"
                            vt_profile = None
                            try:
                                vt_profile = (
                                    self.variable_text_ui_manager._find_profile(
                                        vt_pname
                                    )
                                    if self.variable_text_ui_manager
                                    else None
                                )
                            except Exception:
                                vt_profile = None
                            if vt_profile is not None:
                                used_fonts[
                                    (
                                        vt_profile.font_family,
                                        vt_profile.font_style,
                                    )
                                ] = vt_pname
                            else:
                                used_fonts[
                                    (
                                        pos.get("font_family", "Arial"),
                                        pos.get("font_style", "Regular"),
                                    )
                                ] = f"{vt_pname} (perfil no encontrado, usa datos de posición)"
                        elif pos_type == "barcode":
                            bf = (
                                (pos.get("barcode_font_family") or "OCR-B")
                                .strip()
                                .upper()
                            )
                            if bf not in ("OCR-A", "OCR-B", "OCR-B F", "OCR-B L"):
                                used_fonts[(bf, "Regular")] = f"HRI barcode ({bf})"
                        else:
                            ts = pos.get("text_style") or pos.get("text_style_name")
                            if ts:
                                profile = profiles.get(ts)
                                if not profile:
                                    print(
                                        f"[PACKAGE DEBUG] Perfil no encontrado para style_name={ts}"
                                    )
                                    fonts_missing.append(
                                        f"{ts} (perfil no encontrado)"
                                    )
                                    continue
                                used_fonts[
                                    (profile.font_family, profile.font_style)
                                ] = ts

                for (family, style), label in sorted(used_fonts.items()):
                    print(
                        f"[PACKAGE DEBUG] Intentando resolver fuente para '{label}': {family} / {style}"
                    )
                    fpath, fidx = pdfgen._find_system_font_file(family, style)
                    print(
                        f"[PACKAGE DEBUG] Resultado búsqueda: family={family}, style={style}, fpath={fpath!r}, fidx={fidx}"
                    )
                    if not fpath:
                        fonts_missing.append(f"{family} {style} -> no encontrado")
                        continue
                    try:
                        fname = os.path.basename(fpath)
                        dest = os.path.join(fonts_dir, fname)

                        was_present = os.path.exists(dest)

                        # Detailed pre-copy diagnostics
                        try:
                            dest_dir = os.path.dirname(dest)
                            dest_writable = os.access(dest_dir, os.W_OK)
                            src_stat = os.stat(fpath)
                            try:
                                dest_stat = os.stat(dest)
                            except Exception:
                                dest_stat = None
                            print(
                                f"[PACKAGE DEBUG] Pre-copy: dest_exists={os.path.exists(dest)}, dest_writable_dir={dest_writable}, src_uid={src_stat.st_uid}, src_gid={src_stat.st_gid}, src_size={src_stat.st_size}"
                            )
                            if dest_stat:
                                print(
                                    f"[PACKAGE DEBUG] Pre-copy: dest_uid={dest_stat.st_uid}, dest_gid={dest_stat.st_gid}, dest_size={dest_stat.st_size}"
                                )
                        except Exception as _diag:
                            print(
                                f"[PACKAGE DEBUG] Error diagnostic info pre-copy: {_diag}"
                            )

                        # Try copy preserving metadata, then copy, then manual stream copy as last resort
                        copy_method = None
                        last_exc = None
                        try:
                            shutil.copy2(fpath, dest)
                            copy_method = "copy2"
                        except Exception as e_copy2:
                            last_exc = e_copy2
                            # Mensaje conciso: copy2 puede fallar por metadata/permisos en macOS al preservar atributos
                            print(
                                f"[PACKAGE DEBUG] copy2 no permitido para {fname}, usando fallback copy() (metadata no preservada)"
                            )
                            try:
                                shutil.copy(fpath, dest)
                                copy_method = "copy"
                                print(
                                    f"[PACKAGE DEBUG] copy() OK para {fname} (metadata no preservada)"
                                )
                            except Exception as e_copy:
                                last_exc = e_copy
                                print(
                                    f"[PACKAGE DEBUG] copy() también falló para {fname}: {e_copy}"
                                )
                                # Intentar copia manual por streaming (evita metadata/atributos)
                                try:
                                    with open(fpath, "rb") as sf, open(
                                        dest, "wb"
                                    ) as df:
                                        import shutil as _sh

                                        _sh.copyfileobj(sf, df)
                                    copy_method = "manual"
                                    print(
                                        f"[PACKAGE DEBUG] copia manual OK para {fname}"
                                    )
                                except Exception as e_manual:
                                    last_exc = e_manual
                                    print(
                                        f"[PACKAGE DEBUG] copia manual falló para {fname}: {e_manual}"
                                    )

                        if copy_method:
                            if was_present:
                                fonts_copied.append(f"{fname} (actualizada)")
                                print(
                                    f"[PACKAGE DEBUG] Fuente actualizada: {fname} <- {fpath} (method={copy_method})"
                                )
                            else:
                                fonts_copied.append(fname)
                                print(
                                    f"[PACKAGE DEBUG] Fuente copiada: {fname} <- {fpath} (method={copy_method})"
                                )
                        else:
                            # Registrar error con máxima información
                            try:
                                import errno

                                is_perm = isinstance(last_exc, PermissionError) or (
                                    isinstance(last_exc, OSError)
                                    and getattr(last_exc, "errno", None)
                                    in (errno.EPERM, errno.EACCES, 1, 13)
                                )
                            except Exception:
                                is_perm = False
                            if is_perm:
                                msg = f"{family} {style} -> permiso denegado al escribir en: {dest} ({last_exc})"
                                fonts_missing.append(msg)
                                print(f"[PACKAGE DEBUG] {msg}")
                                print(
                                    f"[PACKAGE DEBUG] Sugerencia: verifica permisos de la carpeta destino o concede acceso a Desktop/Documentos a la app/Terminal (macOS)"
                                )
                            else:
                                fonts_missing.append(
                                    f"{family} {style} -> error copiar: {last_exc}"
                                )
                                print(
                                    f"[PACKAGE DEBUG] Error copiando fuente {family} {style}: {last_exc}"
                                )
                        # Solo copiamos la fuente al directorio de destino; no guardamos metadatos adicionales
                    except Exception as ef:
                        # Si la copia falla por permisos o cualquier otro error, registrar el error sin reclasificar
                        try:
                            import errno

                            is_perm = isinstance(ef, PermissionError) or (
                                isinstance(ef, OSError)
                                and getattr(ef, "errno", None)
                                in (errno.EPERM, errno.EACCES, 1, 13)
                            )
                        except Exception:
                            is_perm = False

                        if is_perm:
                            msg = f"{family} {style} -> permiso denegado al escribir en: {dest} ({ef})"
                            fonts_missing.append(msg)
                            print(f"[PACKAGE DEBUG] {msg}")
                            print(
                                f"[PACKAGE DEBUG] Sugerencia: verifica permisos de la carpeta destino o concede acceso a Desktop/Documentos a la app/Terminal (macOS)"
                            )
                        else:
                            fonts_missing.append(
                                f"{family} {style} -> error copiar: {ef}"
                            )
                            print(
                                f"[PACKAGE DEBUG] Error copiando fuente {family} {style}: {ef}"
                            )

                # Resumen detallado de lo recopilado para diagnóstico
                print(
                    f"[PACKAGE DEBUG] used_fonts={[(f, s) for (f, s), _ in used_fonts.items()]}"
                )
                try:
                    profiles_map = {
                        name: (
                            p.font_family,
                            p.font_style,
                            getattr(p, "resolved_font_path", None),
                        )
                        for name, p in profiles.items()
                    }
                except Exception:
                    profiles_map = {
                        name: ("<error>", "<error>", None) for name in profiles.keys()
                    }
                print(f"[PACKAGE DEBUG] profiles_map={profiles_map}")
                print(f"[PACKAGE DEBUG] fonts_copied={fonts_copied}")
                print(f"[PACKAGE DEBUG] fonts_missing={fonts_missing}")

            except Exception as egf:
                print(f"[PACKAGE][WARN] Error incluyendo tipos de letra: {egf}")

            # Si hemos guardado/creado el .pnb en la carpeta destino, reescribirlo ahora
            # para que incluya las rutas actualizadas de imágenes copiadas y adoptarlo como proyecto activo.
            if pnb_saved:
                try:
                    self._save_project_to_pnb(pnb_path)
                    # Actualizar ruta del proyecto para que la aplicación use el PNB dentro del paquete
                    self.current_project_path = pnb_path
                    self.project_name = os.path.basename(pnb_path)
                    self._saved_state_snapshot = self._create_state_snapshot()
                    self.project_modified = False
                    self._update_project_state_ui()
                    print(
                        f"[PACKAGE] Proyecto guardado en paquete y ahora activo: {pnb_path}"
                    )

                    # Intentar eliminar el archivo original si existía y es distinto del nuevo
                    try:
                        if original_project_path and os.path.abspath(
                            original_project_path
                        ) != os.path.abspath(pnb_path):
                            if os.path.exists(original_project_path):
                                os.remove(original_project_path)
                                print(
                                    f"[PACKAGE] Archivo original eliminado: {original_project_path}"
                                )
                            else:
                                print(
                                    f"[PACKAGE] Archivo original no existe (ya eliminado): {original_project_path}"
                                )
                    except Exception as e_del:
                        print(
                            f"[PACKAGE][WARN] No se pudo eliminar archivo original {original_project_path}: {e_del}"
                        )
                except Exception as e_rewrite:
                    print(
                        f"[PACKAGE][WARN] No se pudo reescribir PNB en destino: {e_rewrite}"
                    )

        # Preparar resumen como lista de líneas (evita usar '\\n' literales)
        summary_lines = []
        summary_lines.append(t("Archivos adjuntados correctamente:"))
        summary_lines.append("")
        summary_lines.append(t("Carpeta: {0}").format(folder_path))
        summary_lines.append("")

        if pnb_saved:
            summary_lines.append(t("Archivo guardado: {0}").format(pnb_filename))
        else:
            summary_lines.append(t("Archivo ya existía: {0}").format(pnb_filename))

        if images_copied:
            summary_lines.append(
                t("Imágenes copiadas/actualizadas: {0}").format(len(images_copied))
            )
            for img in images_copied:
                summary_lines.append(f"   • {img}")

        if images_skipped:
            summary_lines.append(
                t("Imágenes ya actualizadas: {0}").format(len(images_skipped))
            )
            for img in images_skipped:
                summary_lines.append(f"   • {img}")

        # Incluir resumen de fuentes si se solicitó
        if getattr(self, "_package_include_fonts", False):
            if fonts_copied:
                summary_lines.append(
                    t("Tipos de letra incluidos: {0}").format(len(fonts_copied))
                )
                for f in fonts_copied:
                    summary_lines.append(f"   • {f}")
            if fonts_missing:
                summary_lines.append(
                    t("Tipos de letra faltantes/error: {0}").format(len(fonts_missing))
                )
                for f in fonts_missing:
                    summary_lines.append(f"   • {f}")

        print(
            f"[PACKAGE] Empaquetado completo: {len(images_copied)} copiadas, {len(images_skipped)} ya actualizadas"
        )

        # Transformar summary_lines en controles y aplicar bold a los títulos
        summary_controls = []
        for line in summary_lines:
            s = line.strip()
            if not s:
                summary_controls.append(ft.Container(height=6))
                continue

            # Título principal: más grande y en negrita
            if s.startswith(t("Archivos adjuntados")):
                summary_controls.append(
                    ft.Text(
                        s,
                        size=17,
                        weight=ft.FontWeight.BOLD,
                        color=TEXTO_COLOR_GENERICO,
                        text_align=ft.TextAlign.CENTER,
                    )
                )
                summary_controls.append(ft.Container(height=8))
                continue

            # Carpeta: mostrar etiqueta en bold y ruta en caja seleccionable
            if s.startswith(t("Carpeta:")):
                try:
                    _, val = s.split(":", 1)
                    # Compact row: label bold + small selectable path (single line)
                    summary_controls.append(
                        ft.Row(
                            [
                                ft.Text(
                                    t("Carpeta:"),
                                    size=13,
                                    weight=ft.FontWeight.BOLD,
                                    color=TEXTO_COLOR_GENERICO,
                                ),
                                ft.Text(
                                    val.strip(),
                                    size=12,
                                    color=TEXTO_COLOR_GENERICO,
                                    selectable=True,
                                    expand=True,
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.START,
                            spacing=8,
                        )
                    )
                except Exception:
                    summary_controls.append(
                        ft.Text(
                            s,
                            size=13,
                            weight=ft.FontWeight.BOLD,
                            color=TEXTO_COLOR_GENERICO,
                        )
                    )
                continue

            # Archivo guardado / ya existía: etiqueta bold + ruta en caja seleccionable
            if s.startswith(t("Archivo guardado:")) or s.startswith(
                t("Archivo ya existía:")
            ):
                try:
                    label, val = s.split(":", 1)
                    # Compact row for file: label bold + small selectable path
                    summary_controls.append(
                        ft.Row(
                            [
                                ft.Text(
                                    f"{label}:",
                                    size=13,
                                    weight=ft.FontWeight.BOLD,
                                    color=TEXTO_COLOR_GENERICO,
                                ),
                                ft.Text(
                                    val.strip(),
                                    size=12,
                                    color=TEXTO_COLOR_GENERICO,
                                    selectable=True,
                                    expand=True,
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.START,
                            spacing=8,
                        )
                    )
                except Exception:
                    summary_controls.append(
                        ft.Text(
                            s,
                            size=13,
                            weight=ft.FontWeight.BOLD,
                            color=TEXTO_COLOR_GENERICO,
                        )
                    )
                continue

            # Imágenes / Tipos de letra: encabezados en bold
            if s.startswith(t("Imágenes")):
                summary_controls.append(
                    ft.Text(
                        t("Imágenes:"),
                        size=13,
                        weight=ft.FontWeight.BOLD,
                        color=TEXTO_COLOR_GENERICO,
                    )
                )
                # Si la línea incluye conteo (p.ej. 'Imágenes copiadas/actualizadas: N'), mostrarlo
                if ":" in s and not s.endswith(":"):
                    summary_controls.append(
                        ft.Text(s, size=13, color=TEXTO_COLOR_GENERICO)
                    )
                continue

            if s.startswith(t("Tipos de letra")):
                summary_controls.append(
                    ft.Text(
                        t("Tipos de letra:"),
                        size=13,
                        weight=ft.FontWeight.BOLD,
                        color=TEXTO_COLOR_GENERICO,
                    )
                )
                if ":" in s and not s.endswith(":"):
                    summary_controls.append(
                        ft.Text(s, size=13, color=TEXTO_COLOR_GENERICO)
                    )
                continue

            # List items (bullets)
            if (
                s.startswith("•")
                or s.startswith("-")
                or s.startswith("*")
                or s.startswith("•")
                or s.startswith("•")
                or s.startswith("•")
                or s.startswith("\u2022")
            ):
                summary_controls.append(ft.Text(s, size=13, color=TEXTO_COLOR_GENERICO))
                continue

            # Default: texto normal
            summary_controls.append(ft.Text(s, size=13, color=TEXTO_COLOR_GENERICO))

        # Si hubo errores/ausencias en fuentes, ajustar título/color del diálogo y loguear advertencia
        dialog_title_text = t("Archivos adjuntados")
        dialog_title_color = TEXTO_COLOR_GENERICO
        if fonts_missing:
            dialog_title_text = t("Archivos adjuntados (con advertencias)")
            dialog_title_color = ft.Colors.ORANGE
            print(
                f"[PACKAGE] Advertencias: {len(fonts_missing)} tipos de letra no copiados/errores"
            )

        # Mostrar diálogo de resultado
        success_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Container(
                content=ft.Text(
                    dialog_title_text,
                    size=21,
                    weight=ft.FontWeight.BOLD,
                    color=dialog_title_color,
                    text_align=ft.TextAlign.CENTER,
                ),
                alignment=ft.Alignment.CENTER,
            ),
            content=ft.Container(
                content=ft.Column(
                    controls=summary_controls,
                    spacing=6,
                    tight=True,
                ),
                width=450,
                padding=20,
            ),
            actions=[
                ft.Button(
                    t("Abrir carpeta"),
                    on_click=lambda e: self._open_folder(folder_path),
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
                    width=140,
                ),
                ft.Button(
                    t("Cerrar"),
                    on_click=lambda e: (
                        setattr(success_dialog, "open", False),
                        self.page.update(),
                    ),
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
                    width=110,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.CENTER,
            bgcolor=FONDO_ALERT_DIALOG,
        )

        self.page.show_dialog(success_dialog)

    def _open_folder(self, folder_path: str):
        """Abre una carpeta en el explorador del sistema"""
        try:
            import subprocess

            if platform.system() == "Darwin":  # macOS
                subprocess.run(["open", folder_path], check=True)
            elif platform.system() == "Windows":
                subprocess.Popen(
                    f'explorer "{folder_path}"',
                    shell=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:  # Linux
                subprocess.run(["xdg-open", folder_path], check=True)
        except Exception as ex:
            print(f"[ERROR] No se pudo abrir la carpeta: {ex}")

    def build(self) -> ft.Control:
        """Construye y retorna el control principal"""
        # Agregar FilePickers a los servicios de la página (Flet 1.0: FilePicker es Service)
        self.page.services.extend(
            [
                self.save_file_picker,
                self.load_file_picker,
                self.package_folder_picker,
                self.bg_missing_file_picker,
                self.excel_missing_file_picker,
            ]
        )

        # BLOQUEAR cierre nativo de la ventana
        self.page.window.prevent_close = True
        self.page.window.on_event = self._on_window_event
        print("[WINDOW] Cierre nativo bloqueado. Solo se puede salir con botón UI.")

        # Marcar UI como montada y actualizar estado visual ahora que los controles
        # han sido añadidos a la página (evita AssertionError al llamar update prematuramente)
        self._ui_mounted = True
        try:
            self._update_project_state_ui()
        except Exception as e:
            print(f"[INIT] _update_project_state_ui() during build failed: {e}")

        # Keyboard handler for PDF417 Enter/Tab validation
        self.page.on_keyboard_event = self._on_pdf417_page_keyboard
        self.page.on_click = self._on_pdf417_page_click

        # Active barcode profile reference
        self._active_barcode_profile = self._get_active_barcode_profile()

        return self.main_content
