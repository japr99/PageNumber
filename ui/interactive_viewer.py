"""
Visor interactivo de PageNumber
Basado en VARIOS/mover_numeros.py
"""

import flet as ft


def _safe_page(ctrl):
    """Devuelve ctrl.page o None si no está montado (Flet 1.0: .page lanza RuntimeError)."""
    try:
        return ctrl.page
    except Exception:
        return None


import flet.canvas as cv
import sys
import os
import platform
import base64
import math
import io
import builtins
import fitz  # PyMuPDF para calcular ancho de texto
import threading
import traceback

# Añadir el directorio padre al path para importar color_design
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from color_design import (
    BORDE_TEXTFIELDS_COLOR,
    ERROR_COLOR,
    FONDO_TEXTFIELDS_COLOR,
    TEXTO_COLOR_GENERICO,
)

from utils.constants import (
    MIN_ZOOM,
    MAX_ZOOM,
    DEFAULT_ZOOM,
    DEFAULT_PAGE_WIDTH_PIXELS,
    DEFAULT_PAGE_HEIGHT_PIXELS,
    PAGE_SIZES,
    mm_to_screen_pixels,
    screen_pixels_to_mm,
    ENABLE_RULERS,
    RULER_UNITS,
    UNIT_MM,
    RIGHT_ANCHOR_VISUAL_COMP_PT,
    VISUAL_CORRECTION_LEFT,
    VISUAL_CORRECTION_CENTER,
)
from i18n import t
from utils.preferences import get_rendering_tuning_settings
from utils.barcode_module import (
    get_barcode_rects,
    get_module_count,
    get_qr_module_count,
    encode_ean13,
    validate_ean13,
    get_ean13_module_count,
    EAN13_GUARD_MODULES,
    get_ean13_font_descender_ratio,
    get_ean13_font_ascender_ratio,
    encode_ean8,
    validate_ean8,
    encode_ean5,
    validate_ean5,
    get_ean8_module_count,
    get_ean5_module_count,
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
    validate_gtin13,
    encode_itf14,
    get_itf14_module_count,
    ITF14_TOTAL_MODULES,
    gtin13_to_gtin14,
    calc_itf14_dimensions,
    format_itf14_hri,
    get_pdf417_image_b64,
    get_pdf417_total_size,
    get_qr_image_b64,
    get_datamatrix_image_b64,
    validate_datamatrix,
    _is_datamatrix_family,
    get_digit_advance_em,
    ean_hri_layout,
)
from utils.variable_text_measure import (
    DEFAULT_ANCHOR,
    render_vt_image_b64,
    resolve_vt_text,
    anchor_uv,
    vertical_anchor_offset,
)

# Silenciar prints de depuración en este módulo por defecto.
# Para activar, cambiar _PRINT_DEBUG = True durante desarrollo.
_PRINT_DEBUG = False  # Debug desactivado
if not _PRINT_DEBUG:

    def _no_print(*args, **kwargs):
        return None

    print = _no_print

# Colores para líneas guía y punto de control
COLOR_ACTIVO = ERROR_COLOR  # Color intenso para numeradora activa (rojo)
COLOR_INACTIVO = ft.Colors.BLUE_200  # Color tenue para numeradoras inactivas
COLOR_LOCKED = ft.Colors.GREY_400  # Color para elementos bloqueados

# Conversión de unidades: puntos (pt) a milímetros (mm)
FONT_PT_TO_MM = 0.3528  # 25.4mm/inch ÷ 72pt/inch

# Constantes de render Windows (no configurables por el usuario)
WINDOWS_TEXT_WIDTH_PADDING_RATIO = 0.20
WINDOWS_TEXT_WIDTH_PADDING_MIN_PX = 2.0


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


def _apply_thousands_separator(number_str: str, separator_type: str) -> str:
    """Legacy wrapper for simple separator application without mask"""
    return _inject_thousands_separator(number_str, separator_type)


def _apply_mask(
    number: int,
    mask: str,
    separator_type: str = "normal",
    placeholder: str = "0",
    digit_placeholder: int = 0,
) -> str:
    """
    Aplica máscara simplificada (placeholder '0') y luego inyecta separadores.

    Nota: Los parámetros placeholder y digit_placeholder se mantienen por compatibilidad
    con llamadas antiguas pero NO SE USAN en la nueva lógica simplificada.
    """
    str_number = str(number)

    if not mask:
        # Sin máscara, solo aplicar separador estándar
        return _apply_thousands_separator(str_number, separator_type)

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
        # print(f"[VIEWER_MASK] Num: {number} -> Val: {val}, Final: '{final_result}'")
    except (ValueError, TypeError):
        final_result = full_result

    # print(f"[VIEWER_MASK] Mask: '{mask}', Num: {number}, Final: '{final_result}'")

    return final_result


def _align_to_anchor(alignment):
    """Migración legacy alignment (3) → anchor (9): fila superior.
    Decisión del usuario: el default al añadir un VT es superior izquierda."""
    _map = {
        "izquierda": "superior_izquierda",
        "centro": "superior_centro",
        "derecha": "superior_derecha",
    }
    return _map.get(alignment, DEFAULT_ANCHOR)


def _rotate_point_cw(x, y, W, H, rot):
    """Re-mapea un punto (x, y) del frame original (mm, y-down, origen top-left) al
    frame de la imagen pre-rotada en sentido horario (PIL rotate(-rot, expand=True)).
    Misma matemática que el PDF (rotación alrededor del punto de anclaje).
    Compartido por render y post-data de todos los barcodes imagen (QR/PDF417/DM)."""
    if rot == 90:
        return (H - y, x)
    if rot == 180:
        return (W - x, H - y)
    if rot == 270:
        return (y, W - x)
    return (x, y)


def _rotate_dims_cw(W, H, rot):
    """Dimensiones visuales de una imagen tras pre-rotarla en sentido horario."""
    if rot in (90, 270):
        return (H, W)
    return (W, H)


def _datamatrix_guide_mm(
    canvas_w_mm, canvas_h_mm, code_h_mm, alignment, hri_position, code_w_mm=None
):
    """Punto de la GUÍA dentro del canvas sin rotar (mm desde top-left).

    El ancla horizontal es el BORDE DEL CÓDIGO (tamaño fijo), no el lienzo:
    el lienzo crece con el texto HRI variable y anclarlo hacía bailar el
    código alrededor de la guía. x_code dentro del lienzo = mismo cálculo que
    _compose_hri_canvas (below/above: código centrado; left/right: código a un
    lado). El vertical sigue al código: fondo del código (below/above) o
    centro vertical del código (left/right)."""
    if code_w_mm is None:
        code_w_mm = canvas_w_mm  # compat: sin código conocido → ancla al lienzo
    if hri_position in ("left", "right"):
        gy = (canvas_h_mm + code_h_mm) / 2.0
    else:
        gy = code_h_mm if hri_position == "below" else canvas_h_mm
    if hri_position == "left":
        x_code = canvas_w_mm - code_w_mm
    elif hri_position == "right":
        x_code = 0.0
    else:
        x_code = (canvas_w_mm - code_w_mm) / 2.0
    if alignment == "centro":
        gx = x_code + code_w_mm / 2.0
    elif alignment == "derecha":
        gx = x_code + code_w_mm
    else:
        gx = x_code
    return (gx, gy)


class InteractiveViewer:
    """Visor interactivo con drag & drop para numeradoras"""

    def __init__(
        self,
        page: ft.Page,
        viewer_width=800,
        viewer_height=600,
        on_zoom_change=None,
        on_position_update=None,
        on_select=None,
        page_size_name="A4",
        text_style_manager=None,
    ):
        self.page = page
        self._load_runtime_tuning_settings()
        self.on_zoom_change_callback = on_zoom_change
        self.on_position_update_callback = (
            on_position_update  # Callback para actualizar posición en main_screen
        )
        self.on_select_callback = (
            on_select  # Callback para notificar selección al main_screen
        )

        # Gestor de estilos de texto
        self.text_style_manager = text_style_manager
        self.barcode_profile_manager = None
        self.vt_profile_manager = None

        # Mostrar/ocultar las guías (líneas vertical/horizontal). El punto de control
        # (círculo) permanece siempre visible independientemente de este flag.
        self.show_guides = True
        # Snap magnético: al arrastrar un elemento, si está dentro del umbral (px) del
        # centro de otro elemento, la posición se alinea automáticamente.
        self.magnetic_snap_active = True
        self.magnetic_snap_threshold = 5.0  # píxeles en pantalla
        # Mostrar línea de verificación (baseline) — por defecto OFF para evitar
        # las líneas azules que aparecen en Windows pero no en mac.
        self.show_verification_line = False

        # Diccionario para almacenar numeradoras dinámicamente
        # Formato: {id: {container, text, guide_h, guide_v, data}}
        self.numeradoras = {}
        self.next_id = 1
        self.selected_id = None

        # Diccionario para almacenar barcodes
        # Formato: {id: {data: {x, y, value, symbology, bar_width, bar_height, rotation, alignment}}}
        self.barcodes = {}
        self.next_barcode_id = 1
        self.selected_barcode_id = None

        # Diccionario para almacenar textos variables
        self.variable_texts = {}
        self.next_variable_text_id = 1
        self.selected_variable_text_id = None
        self._vt_img_cache = {}

        # Doble clic
        self.last_click_time = 0
        self.last_clicked_id = None
        self.double_click_threshold = 0.3  # 300ms
        self.on_double_click_callback = None  # Callback para doble clic numeradoras
        self.on_barcode_double_click_callback = (
            None  # Callback para doble clic barcodes
        )
        self.on_variable_text_double_click_callback = (
            None  # Callback para doble clic textos variables
        )

        # Fondo
        self.background_config = None
        self.background_image_src = None

        # Tamaño de página (convertir de mm a píxeles de pantalla para visualización)
        self.page_size_name = page_size_name
        self.bleed_mm = 0.0  # Sangre (bleed) inicial
        if page_size_name in PAGE_SIZES:
            width_mm, height_mm = PAGE_SIZES[page_size_name]
            self.page_width_mm = width_mm
            self.page_height_mm = height_mm
            self.canvas_width = mm_to_screen_pixels(width_mm)
            self.canvas_height = mm_to_screen_pixels(height_mm)
        else:
            # Fallback a valores por defecto (A4)
            # Los tamaños personalizados se aplicarán después con set_page_size
            width_mm, height_mm = PAGE_SIZES["A4"]
            self.page_width_mm = width_mm
            self.page_height_mm = height_mm
            self.canvas_width = DEFAULT_PAGE_WIDTH_PIXELS
            self.canvas_height = DEFAULT_PAGE_HEIGHT_PIXELS

        print(
            f"[VIEWER] Tamaño de página: {page_size_name} = {width_mm}x{height_mm} mm = {self.canvas_width:.1f}x{self.canvas_height:.1f} px"
        )

        # Dimensiones del visor
        self.viewer_width = viewer_width
        self.viewer_height = viewer_height

        # Calcular zoom inicial automático (como impo_ui.py)
        self.initial_scale = self._calculate_initial_scale()
        print(
            f"[VIEWER] Zoom inicial calculado: {self.initial_scale:.3f} (viewer: {viewer_width}x{viewer_height}px)"
        )

        # Inicializar unidad de las reglas (antes de crear las reglas)
        self.ruler_unit = UNIT_MM
        # Timestamp para limitar la frecuencia de actualizaciones pesadas del canvas
        # (evita overflooding durante drag/pan que puede producir race conditions)
        self._last_canvas_update_ts = 0.0
        # Lock para serializar redibujos y mutaciones de canvas_shapes entre
        # handlers de Flet (se ejecutan en thread pool).
        self._redraw_lock = threading.Lock()
        # Flag para evitar redraw_all innecesario en gesture_end tras simple click
        self._gesture_moved = False
        # Throttling de logs por contexto para evitar flood durante drag (~60 FPS)
        self._last_update_error_log_ts = {}

        # Guías de posición (inyectadas por main_screen).
        self.position_guides = None
        # Cara cuyas guías se dibujan/interactúan (CARA/DORSO).
        # Property viva: cuando main inyecta `_get_guides_face_fn` (mismo patrón que
        # `get_current_face_fn` de los managers de numeradora), la cara se consulta
        # SIEMPRE en vivo → sync automático al cambiar CARA/DORSO. Sin callback → CARA.
        self._guides_face = "CARA"  # Fallback si no inyectan callback
        self._get_guides_face_fn = None  # Inyectado por main_screen (sync vivo CARA/DORSO)
        # Guía actualmente arrastrada/seleccionada (id) + su cara.
        self._dragging_guide_id = None
        self._dragging_guide_face = None
        # Guía nueva creada desde una regla (id) + regla de origen ("H"/"V").
        self._new_guide_id = None
        self._new_guide_from = None
        # Colores de guía (cargados desde preferencias en _load_runtime_tuning_settings).
        self.guide_color = "#757575"
        self.guide_color_selected = "#E91E63"
        # Grosor de línea de las guías en px CONSTANTE (el zoom NO amplía el ancho,
        # igual que las líneas guía de las posiciones actuales).
        self.guide_stroke_width = 1.0

        # Crear componentes
        self._create_components()

        # Crear reglas (si están habilitadas)
        if ENABLE_RULERS:
            self._create_rulers()

    @property
    def guides_face(self):
        """Cara cuyas guías de posición se dibujan/interactúan (CARA/DORSO).

        Patrón igual al de los managers de numeradora: main inyecta un callback
        vivo (`_get_guides_face_fn`) apuntando a `self.current_face` de main, así
        las guías SIEMPRE siguen a la cara activa sin sync manual por sitio.
        Sin callback inyectado → valor por defecto `_guides_face` (CARA).
        """
        fn = self._get_guides_face_fn
        if fn is not None:
            try:
                return fn()
            except Exception:
                pass
        return self._guides_face

    @guides_face.setter
    def guides_face(self, value):
        self._guides_face = value

    def _load_runtime_tuning_settings(self):
        """Carga los ajustes de calibración del visor desde preferencias."""
        settings = get_rendering_tuning_settings()
        self.fine_adjust_step_mm = float(settings.get("fine_adjust_step_mm", 0.1))
        # padding ratio y min px son constantes globales de módulo
        self.windows_text_width_padding_ratio = WINDOWS_TEXT_WIDTH_PADDING_RATIO
        self.windows_text_width_padding_min_px = WINDOWS_TEXT_WIDTH_PADDING_MIN_PX
        # Cargar umbral de snap desde preferencias
        from utils.preferences import get_preference

        self.magnetic_snap_threshold = float(
            get_preference("magnetic_snap_threshold", 5.0)
        )
        self.guide_color = str(get_preference("guide_color", "#757575"))
        self.guide_color_selected = str(
            get_preference("guide_color_selected", "#E91E63")
        )

    def reload_runtime_tuning_settings(self):
        """Recarga calibración desde preferencias y refresca la vista."""
        self._load_runtime_tuning_settings()
        self._redraw_all(force=True)

    def _create_rulers(self):
        """Crea las reglas horizontales y verticales (reserva esquina para control)"""
        self.ruler_horizontal_shapes = []
        self.ruler_vertical_shapes = []

        # Tamaño de la intersección (esquina)
        self.corner_size = 25

        # Canvas para regla horizontal (superior)
        self.ruler_horizontal_canvas = cv.Canvas(
            self.ruler_horizontal_shapes,
            width=self.viewer_width,
            height=self.corner_size,
        )

        # Canvas para regla vertical (izquierda) — altura reducida por corner_size
        self.ruler_vertical_canvas = cv.Canvas(
            self.ruler_vertical_shapes,
            width=self.corner_size,
            height=max(0, self.viewer_height - self.corner_size),
        )

        # Contenedores para las reglas (ahora con gestos: arrastrar desde una
        # regla crea una guía de posición nueva, patrón InDesign)
        self.ruler_horizontal_container = ft.Container(
            content=ft.GestureDetector(
                content=self.ruler_horizontal_canvas,
                on_pan_start=lambda e: self._on_ruler_pan_start(e, "H"),
                on_pan_update=lambda e: self._on_ruler_pan_update(e, "H"),
                on_pan_end=lambda e: self._on_ruler_pan_end(e, "H"),
                drag_interval=16,
            ),
            width=self.viewer_width,
            height=self.corner_size,
            bgcolor=ft.Colors.GREY_200,
            border=ft.Border.all(1, ft.Colors.GREY_400),
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
        )

        self.ruler_vertical_container = ft.Container(
            content=ft.GestureDetector(
                content=self.ruler_vertical_canvas,
                on_pan_start=lambda e: self._on_ruler_pan_start(e, "V"),
                on_pan_update=lambda e: self._on_ruler_pan_update(e, "V"),
                on_pan_end=lambda e: self._on_ruler_pan_end(e, "V"),
                drag_interval=16,
            ),
            width=self.corner_size,
            height=max(0, self.viewer_height - self.corner_size),
            bgcolor=ft.Colors.GREY_200,
            border=ft.Border.all(1, ft.Colors.GREY_400),
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
        )

        # Espacio vacío en la esquina superior izquierda (sin interactividad por ahora)
        self.corner_space = ft.Container(
            width=self.corner_size,
            height=self.corner_size,
            bgcolor=ft.Colors.GREY_300,
        )

    def _get_page_margins(self):
        """Retorna los márgenes entre el viewer y la página"""
        if ENABLE_RULERS:
            margin_left = self.corner_size + 20  # Esquina + margen visual
            margin_top = self.corner_size + 40  # Esquina + margen visual mayor
        else:
            margin_left = 20
            margin_top = 20
        return margin_left, margin_top

    def _transform_viewer_to_page_coords(self, x_viewer, y_viewer):
        """
        Transforma coordenadas del viewer (px) a coordenadas de página (mm)
        Inverso de _transform_page_to_viewer_coords

        IMPORTANTE: Resta la sangre del offset para que los valores guardados
        sean sin sangre (para los textfields), aunque visualmente se vean desplazados.
        """
        # Calcular donde empieza la página en el canvas ampliado
        page_start_x = (
            self.big_canvas_width - self.canvas_width * self.current_scale
        ) / 2 + self.offset_x
        page_start_y = (
            self.big_canvas_height - self.canvas_height * self.current_scale
        ) / 2 + self.offset_y

        # Restar el inicio de la página
        x_scaled = x_viewer - page_start_x
        y_scaled = y_viewer - page_start_y

        # Revertir zoom
        x_px = x_scaled / self.current_scale
        y_px = y_scaled / self.current_scale

        # RESTAR SANGRE para obtener coordenadas sin sangre
        # Esto garantiza que los valores guardados y mostrados en textfields
        # sean las coordenadas respecto al área de corte (sin sangre)
        bleed_px = mm_to_screen_pixels(self.bleed_mm)
        x_px -= bleed_px
        y_px -= bleed_px

        # Convertir píxeles a mm
        x_mm = screen_pixels_to_mm(x_px)
        y_mm = screen_pixels_to_mm(y_px)

        return x_mm, y_mm

    def _transform_page_to_viewer_coords(self, x_mm, y_mm):
        """
        Transforma coordenadas de página (mm) a coordenadas del viewer (px)
        considerando zoom, centrado y pan

        IMPORTANTE: Suma la sangre al offset visual para que las numeradoras
        se vean en la posición correcta sobre las reglas (que están a tamaño de corte).
        Los textfields mantienen el valor sin sangre, pero visualmente se suma la sangre.
        """
        # Convertir mm a píxeles de canvas
        x_px = mm_to_screen_pixels(x_mm)
        y_px = mm_to_screen_pixels(y_mm)

        # SUMAR SANGRE al offset de las numeradoras
        # Esto hace que visualmente se vean desplazadas según la sangre,
        # pero los valores en los textfields siguen siendo sin sangre
        bleed_px = mm_to_screen_pixels(self.bleed_mm)
        x_px += bleed_px
        y_px += bleed_px

        # Aplicar zoom
        x_scaled = x_px * self.current_scale
        y_scaled = y_px * self.current_scale

        # Calcular donde empieza la página en el canvas ampliado
        page_start_x = (
            self.big_canvas_width - self.canvas_width * self.current_scale
        ) / 2 + self.offset_x
        page_start_y = (
            self.big_canvas_height - self.canvas_height * self.current_scale
        ) / 2 + self.offset_y

        # Posición final en el viewer
        x_final = page_start_x + x_scaled
        y_final = page_start_y + y_scaled

        return x_final, y_final

    def _calculate_initial_scale(self):
        """
        Calcula el zoom inicial para que el canvas quepa en el viewer
        IMPORTANTE: Márgenes individuales para cada lado (reglas + margen visual)

        Returns:
            float: Escala inicial calculada
        """
        # Márgenes individuales según si hay reglas
        if ENABLE_RULERS:
            margin_left = 25 + 20  # Regla vertical + margen visual
            margin_right = 20  # Solo margen visual
            margin_top = 25 + 40  # Regla horizontal + margen visual mayor
            margin_bottom = 5  # Margen mínimo inferior
        else:
            margin_left = 20
            margin_right = 20
            margin_top = 20
            margin_bottom = 20

        # Restar márgenes del viewer
        viewer_effective_w = self.viewer_width - margin_left - margin_right
        viewer_effective_h = self.viewer_height - margin_top - margin_bottom

        # Calcular zoom para ambas dimensiones
        scale_width = viewer_effective_w / self.canvas_width
        scale_height = viewer_effective_h / self.canvas_height

        # Usar el MENOR para que quepa completamente (como impo_ui.py)
        zoom = min(scale_width, scale_height)

        print(f"[AUTO-ZOOM] Canvas: {self.canvas_width:.1f}x{self.canvas_height:.1f}px")
        print(f"[AUTO-ZOOM] Viewer: {self.viewer_width:.1f}x{self.viewer_height:.1f}px")
        print(
            f"[AUTO-ZOOM] Márgenes: L={margin_left} R={margin_right} T={margin_top} B={margin_bottom}"
        )
        print(
            f"[AUTO-ZOOM] Viewer efectivo: {viewer_effective_w:.1f}x{viewer_effective_h:.1f}px"
        )
        print(
            f"[AUTO-ZOOM] scale_width: {scale_width:.3f}, scale_height: {scale_height:.3f}"
        )
        print(f"[AUTO-ZOOM] zoom = min(scale_width, scale_height) = {zoom:.3f}")

        return zoom

    def _create_components(self):
        """Crea todos los componentes del visor - ARQUITECTURA MANUAL (sin InteractiveViewer)"""

        # Variables de drag
        self.dragging_element = False
        self.dragging_element_id = None
        self.dragging_barcode = False
        self.dragging_qr = False
        self.dragging_variable_text = False
        self.dragging_control = None
        self.panning = False
        self._drag_stack_failed = (
            False  # Si page.update(self.stack) falla, dejar de mover containers
        )
        # No bloquear drag por un fallo único de update tras pan.
        self._drag_canvas_fail_streak = 0
        # Offsets previos para calcular delta de pan en _redraw_canvas_only
        self._prev_offset_x: float = 0.0
        self._prev_offset_y: float = 0.0

        # Zoom manual (reemplaza InteractiveViewer.scale)
        # Aplicar zoom inicial del usuario (DEFAULT_ZOOM = 0.96 para 4% de margen)
        self.current_scale = self.initial_scale * DEFAULT_ZOOM
        self.min_scale = max(0.1, self.initial_scale * 0.5)
        self.max_scale = self.initial_scale * MAX_ZOOM

        # Canvas ampliado para permitir pan (viewer * 2.5)
        self.big_canvas_width = int(self.viewer_width * 2.5)
        self.big_canvas_height = int(self.viewer_height * 2.5)

        # Offset global para pan (centrado inicialmente)
        # Si hay reglas, compensar el ancho de la regla vertical (25px) para centrar correctamente
        effective_viewer_width = self.viewer_width - (25 if ENABLE_RULERS else 0)
        self.offset_x = -(self.big_canvas_width - effective_viewer_width) / 2
        self.offset_y = -(self.big_canvas_height - self.viewer_height) / 2

        # Guardar posición inicial para reset
        self.initial_offset_x = self.offset_x
        self.initial_offset_y = self.offset_y

        # Límites del pan (boundary)
        self.max_offset_x = 0
        self.min_offset_x = -(self.big_canvas_width - self.viewer_width)
        self.max_offset_y = 0
        self.min_offset_y = -(self.big_canvas_height - self.viewer_height)

        print(f"[CANVAS] Página: {self.canvas_width}x{self.canvas_height}px")
        print(f"[CANVAS] Viewer: {self.viewer_width}x{self.viewer_height}px")
        print(
            f"[CANVAS] Canvas ampliado: {self.big_canvas_width}x{self.big_canvas_height}px"
        )
        print(f"[CANVAS] Offset inicial: x={self.offset_x:.1f}, y={self.offset_y:.1f}")
        print(
            f"[CANVAS] Límites: x=[{self.min_offset_x:.1f}, {self.max_offset_x:.1f}], y=[{self.min_offset_y:.1f}, {self.max_offset_y:.1f}]"
        )
        print(
            f"[ZOOM] Inicial: {self.current_scale:.3f}, Min: {self.min_scale:.3f}, Max: {self.max_scale:.3f}"
        )

        # Control para la imagen de fondo (Capa intermedia)
        self.background_image_control = ft.Image(
            src=None,
            visible=False,
            gapless_playback=True,
        )

        # Capa de fondo blanco con recorte (clipping) - Estilo impo_ui
        self.white_page_control = ft.Container(
            bgcolor=ft.Colors.WHITE,
            visible=True,
            border=ft.Border.all(1, ft.Colors.BLACK_12),
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            content=ft.Stack([self.background_image_control]),
        )

        # Canvas para dibujar TODO (página + numeradoras + líneas)
        self.canvas_shapes = []

        # Stack para Containers de texto (se actualiza dinámicamente sin afectar Canvas)
        self.text_stack = ft.Stack(
            controls=[],
            width=self.big_canvas_width,
            height=self.big_canvas_height,
            clip_behavior=ft.ClipBehavior.NONE,  # No recortar texto fuera de límites
        )

        self.canvas = cv.Canvas(
            self.canvas_shapes,
            width=self.big_canvas_width,
            height=self.big_canvas_height,
        )

        # Stack principal
        self.stack = ft.Stack(
            controls=[
                self.white_page_control,
                self.canvas,
                self.text_stack,  # Agregado: Stack para Containers de texto (sin afectar Canvas/zoom)
            ],
            width=self.big_canvas_width,
            height=self.big_canvas_height,
        )

        # GestureDetector que maneja AMBOS: pan y drag de elementos
        gesture = ft.GestureDetector(
            content=self.stack,
            on_pan_start=self._on_gesture_start,
            on_pan_update=self._on_gesture_update,
            on_pan_end=self._on_gesture_end,
            drag_interval=16,  # Limitar a ~60 FPS para mejor rendimiento
        )

        # Contenedor con clip para el viewer
        self.zoom_container = ft.Container(
            content=gesture,
            width=self.viewer_width,
            height=self.viewer_height,
            border=ft.Border.all(1, ft.Colors.GREY_400),
            border_radius=8,
            bgcolor=ft.Colors.GREY_100,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
        )

        # Panel de ajuste fino (fijo en UI, independiente del zoom/pan)
        arrow_size = 28

        def _fine_adjust_button(icon, tooltip_text, axis, direction):
            return ft.Container(
                width=arrow_size,
                height=arrow_size,
                border_radius=4,
                alignment=ft.Alignment.CENTER,
                ink=True,
                on_click=lambda e: self._nudge_selected(
                    self.fine_adjust_step_mm * direction if axis == "x" else 0.0,
                    self.fine_adjust_step_mm * direction if axis == "y" else 0.0,
                ),
                tooltip=tooltip_text,
                content=ft.Icon(
                    icon,
                    size=16,
                    color=TEXTO_COLOR_GENERICO,
                ),
            )

        self.fine_adjust_panel = ft.Container(
            visible=False,
            padding=ft.Padding.all(8),
            bgcolor=FONDO_TEXTFIELDS_COLOR,
            border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
            border_radius=8,
            content=ft.Column(
                [
                    ft.Text(
                        t("Ajuste fino"),
                        size=11,
                        weight=ft.FontWeight.BOLD,
                        color=TEXTO_COLOR_GENERICO,
                    ),
                    ft.Row(
                        [
                            ft.Container(width=arrow_size, height=arrow_size),
                            _fine_adjust_button(
                                ft.Icons.KEYBOARD_ARROW_UP,
                                t("Subir"),
                                "y",
                                -1.0,
                            ),
                            ft.Container(width=arrow_size, height=arrow_size),
                        ],
                        spacing=2,
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),
                    ft.Row(
                        [
                            _fine_adjust_button(
                                ft.Icons.KEYBOARD_ARROW_LEFT,
                                t("Izquierda"),
                                "x",
                                -1.0,
                            ),
                            ft.Container(width=arrow_size, height=arrow_size),
                            _fine_adjust_button(
                                ft.Icons.KEYBOARD_ARROW_RIGHT,
                                t("Derecha"),
                                "x",
                                1.0,
                            ),
                        ],
                        spacing=2,
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),
                    ft.Row(
                        [
                            ft.Container(width=arrow_size, height=arrow_size),
                            _fine_adjust_button(
                                ft.Icons.KEYBOARD_ARROW_DOWN,
                                t("Bajar"),
                                "y",
                                1.0,
                            ),
                            ft.Container(width=arrow_size, height=arrow_size),
                        ],
                        spacing=2,
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),
                ],
                spacing=4,
                tight=True,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

    def _update_fine_adjust_visibility(self):
        """Muestra/oculta el panel de ajuste fino según selección actual."""
        should_show = (
            self.selected_id is not None
            or self.selected_barcode_id is not None
            or self.selected_variable_text_id is not None
        )
        if not hasattr(self, "fine_adjust_panel"):
            return
        if self.fine_adjust_panel.visible != should_show:
            self.fine_adjust_panel.visible = should_show
            try:
                if getattr(self, "page", None) and getattr(
                    self.fine_adjust_panel, "page", None
                ):
                    self.page.update(self.fine_adjust_panel)
            except Exception:
                traceback.print_exc()

    def _nudge_selected(self, dx_mm: float, dy_mm: float):
        """Aplica un ajuste fino a la numeradora o barcode seleccionado."""
        if self.selected_id is not None:
            num_data = self.numeradoras.get(self.selected_id)
            if not num_data or num_data["data"].get("locked", False):
                return
            num_data["data"]["x"] += dx_mm
            num_data["data"]["y"] += dy_mm
            if self.on_position_update_callback:
                self.on_position_update_callback(
                    self.selected_id,
                    num_data["data"]["x"],
                    num_data["data"]["y"],
                )
            self._redraw_all(force=True)
        elif self.selected_barcode_id is not None:
            bc_data = self.barcodes.get(self.selected_barcode_id)
            if not bc_data or bc_data["data"].get("locked", False):
                return
            bc_data["data"]["x"] += dx_mm
            bc_data["data"]["y"] += dy_mm
            if self.on_position_update_callback:
                self.on_position_update_callback(
                    self.selected_barcode_id,
                    bc_data["data"]["x"],
                    bc_data["data"]["y"],
                )
            self._redraw_all(force=True)
        elif self.selected_variable_text_id is not None:
            vt_data = self.variable_texts.get(self.selected_variable_text_id)
            if not vt_data or vt_data["data"].get("locked", False):
                return
            vt_data["data"]["x"] += dx_mm
            vt_data["data"]["y"] += dy_mm
            if self.on_position_update_callback:
                self.on_position_update_callback(
                    self.selected_variable_text_id,
                    vt_data["data"]["x"],
                    vt_data["data"]["y"],
                )
            self._redraw_all(force=True)

    def _update_canvas_limits(self):
        """
        Recalcula los límites del canvas ampliado basándose en el zoom actual.
        Esto permite que el usuario pueda hacer pan de toda la página incluso con zoom alto.
        """
        # Calcular el tamaño de la página escalada
        scaled_page_width = self.canvas_width * self.current_scale
        scaled_page_height = self.canvas_height * self.current_scale

        # El canvas ampliado debe ser lo suficientemente grande para:
        # 1. Contener la página escalada
        # 2. Más márgenes para poder mover la página
        # Usamos un margen del 50% del viewer en cada lado
        margin_buffer = 0.5  # 50% de margen extra

        min_canvas_width = scaled_page_width + (self.viewer_width * margin_buffer * 2)
        min_canvas_height = scaled_page_height + (
            self.viewer_height * margin_buffer * 2
        )

        # Asegurar que el canvas sea al menos 2.5x el viewer (mínimo original)
        self.big_canvas_width = max(int(self.viewer_width * 2.5), int(min_canvas_width))
        self.big_canvas_height = max(
            int(self.viewer_height * 2.5), int(min_canvas_height)
        )

        # Recalcular límites del pan
        self.max_offset_x = 0
        self.min_offset_x = -(self.big_canvas_width - self.viewer_width)
        self.max_offset_y = 0
        self.min_offset_y = -(self.big_canvas_height - self.viewer_height)

        # Ajustar offset actual para que esté dentro de los nuevos límites
        self.offset_x = max(self.min_offset_x, min(self.max_offset_x, self.offset_x))
        self.offset_y = max(self.min_offset_y, min(self.max_offset_y, self.offset_y))

        # Actualizar el tamaño del canvas
        self.canvas.width = self.big_canvas_width
        self.canvas.height = self.big_canvas_height

        print(f"[CANVAS UPDATE] Zoom: {self.current_scale:.3f}")
        print(
            f"[CANVAS UPDATE] Página escalada: {scaled_page_width:.0f}x{scaled_page_height:.0f}px"
        )
        print(
            f"[CANVAS UPDATE] Canvas ampliado: {self.big_canvas_width}x{self.big_canvas_height}px"
        )
        print(
            f"[CANVAS UPDATE] Nuevos límites: x=[{self.min_offset_x:.1f}, {self.max_offset_x:.1f}], y=[{self.min_offset_y:.1f}, {self.max_offset_y:.1f}]"
        )

    def _update_canvas(self):
        """Actualiza el visor de forma segura

        Evitar llamadas directas a `control.update()` que en ocasiones lanzan
        `AssertionError` cuando el control está en un estado inconsistente
        (p. ej. tiene `page` pero aún no tiene `__uid`). Preferir
        `self.page.update(control)` y comprobar internamente `_Control__uid`.
        """
        updated_any = False

        # Rebuild necesita refrescar ambas capas: página blanca + canvas (guías/shapes)
        if self._safe_page_update(
            getattr(self, "white_page_control", None), "_update_canvas:white_page"
        ):
            updated_any = True

        if self._safe_page_update(
            getattr(self, "canvas", None), "_update_canvas:canvas"
        ):
            updated_any = True

        if updated_any:
            return True

        # Último fallback cuando ninguna capa está lista todavía
        return self._safe_page_update(
            getattr(self, "zoom_container", None),
            "_update_canvas:fallback zoom_container",
        )

    def _is_control_mounted(self, ctrl):
        """Comprueba si un control está montado en Flet (page accesible).

        En Flet 1.0 `ctrl.page` lanza RuntimeError si no está montado,
        así que esa es la señal (sin privados como el antiguo `_Control__uid`).
        """
        if ctrl is None:
            return False
        try:
            return ctrl.page is not None
        except Exception:
            return False

    def _has_unmounted_children(self, ctrl):
        """Detecta hijos directos sin page para evitar updates parciales inseguros."""
        children = getattr(ctrl, "controls", None) or []
        for child in children:
            if child is None:
                continue
            try:
                if child.page is None:
                    return True
            except Exception:
                return True
        return False

    def _log_update_exception(self, context):
        """Emite contexto del error por stderr sin traceback (error Flet inocuo)."""
        import time

        now = time.monotonic()
        last_ts = self._last_update_error_log_ts.get(context, 0.0)
        if (now - last_ts) < 0.5:
            return
        self._last_update_error_log_ts[context] = now

        try:
            sys.stderr.write(
                f"[VIEWER_UPDATE] {context} — ignorado (error Flet inocuo: update en control no montado)\n"
            )
        except Exception:
            pass

    def _safe_page_update(self, ctrl, context, require_children_mounted=False):
        """Actualiza un control si está listo, evitando asserts por uid transitorio."""
        if not self._is_control_mounted(ctrl):
            return False
        if require_children_mounted and self._has_unmounted_children(ctrl):
            return False
        try:
            self.page.update(ctrl)
            return True
        except Exception:
            self._log_update_exception(context)
            return False

    def _on_gesture_start(self, e):
        """Maneja inicio de interacción: detecta si se hace clic en círculo o se inicia pan"""
        self._gesture_moved = False
        self._gesture_finished = False
        import time

        self.dragging_control = None

        # Convertir coordenadas del viewer a coordenadas de página (mm)
        x_mm, y_mm = self._transform_viewer_to_page_coords(
            e.local_position.x, e.local_position.y
        )

        # Elementos primero: las guías van debajo en capas, así que un
        # elemento encima siempre gana el clic (las guías se cogen en
        # el tramo libre). El hit-test de guías está en la rama else.
        # Buscar si hay una numeradora, barcode o texto variable en esta posición
        # Los ítems bloqueados se saltan automáticamente (skip_locked=True)
        num_id = self._get_clicked_numeradora(x_mm, y_mm, skip_locked=True)
        barcode_id = (
            self._get_clicked_barcode(x_mm, y_mm, skip_locked=True)
            if num_id is None
            else None
        )
        variable_text_id = (
            self._get_clicked_variable_text(x_mm, y_mm, skip_locked=True)
            if (num_id is None and barcode_id is None)
            else None
        )

        if num_id is not None:
            # Detectar doble clic
            current_time = time.time()
            is_double_click = False

            if (
                self.last_clicked_id == num_id
                and current_time - self.last_click_time < self.double_click_threshold
            ):
                is_double_click = True
                self.last_click_time = 0
                self.last_clicked_id = None
            else:
                self.last_click_time = current_time
                self.last_clicked_id = num_id

            if is_double_click:
                if self.on_double_click_callback:
                    self.on_double_click_callback(num_id)
            else:
                self.dragging_element = True
                self.dragging_element_id = num_id
                self._drag_stack_failed = False
                self._drag_canvas_fail_streak = 0
                self._select_numeradora(num_id)
        elif barcode_id is not None:
            # Detectar doble clic en barcode
            current_time = time.time()
            is_double_click = False
            if (
                self.last_clicked_id == barcode_id
                and current_time - self.last_click_time < self.double_click_threshold
            ):
                is_double_click = True
                self.last_click_time = 0
                self.last_clicked_id = None
            else:
                self.last_click_time = current_time
                self.last_clicked_id = barcode_id

            if is_double_click:
                if self.on_barcode_double_click_callback:
                    try:
                        self.on_barcode_double_click_callback(barcode_id)
                    except AssertionError:
                        pass
            else:
                self._drag_stack_failed = False
                self._drag_canvas_fail_streak = 0
                bd = self.barcodes[barcode_id]["data"]
                s = bd.get("symbology", "")
                self.dragging_qr = s in (
                    "qr",
                    "ean13",
                    "ean8",
                    "ean5",
                    "isbn13",
                    "upca",
                    "upce",
                    "itf14",
                )
                self._select_barcode(barcode_id)
                self.dragging_element = True
                self.dragging_element_id = barcode_id
                self.dragging_barcode = True
        elif variable_text_id is not None:
            # Detectar doble clic en texto variable
            current_time = time.time()
            is_double_click = False
            if (
                self.last_clicked_id == variable_text_id
                and current_time - self.last_click_time < self.double_click_threshold
            ):
                is_double_click = True
                self.last_click_time = 0
                self.last_clicked_id = None
            else:
                self.last_click_time = current_time
                self.last_clicked_id = variable_text_id

            if is_double_click:
                if self.on_variable_text_double_click_callback:
                    self.on_variable_text_double_click_callback(variable_text_id)
            else:
                self.dragging_element = True
                self.dragging_element_id = variable_text_id
                self.dragging_variable_text = True
                self._drag_stack_failed = False
                self._drag_canvas_fail_streak = 0
                self._select_variable_text(variable_text_id)
        else:
            # Guías de posición DESPUÉS que elementos: si no hay elemento
            # bajo el cursor se intenta coger guía (sin deseleccionar ni pan).
            if self._try_hold_guide(x_mm, y_mm):
                return
            # Clic en el fondo: deseleccionar todo
            if self.selected_id is not None:
                self._deselect_numeradora()
            elif self.selected_barcode_id is not None:
                _old_bc = self.selected_barcode_id
                self.selected_barcode_id = None
                self._update_fine_adjust_visibility()
                self._update_selection_visual(_old_bc, "barcode", selected=False)
                if self.on_select_callback:
                    self.on_select_callback(None)
            elif self.selected_variable_text_id is not None:
                _old_vt = self.selected_variable_text_id
                self.selected_variable_text_id = None
                self._update_fine_adjust_visibility()
                self._update_selection_visual(_old_vt, "variable_text", selected=False)
                if self.on_select_callback:
                    self.on_select_callback(None)
            self.panning = True

    def _try_hold_guide(self, x_mm, y_mm):
        """Intenta "coger" una guía de posición en el punto dado.

        Tolerancia en px constante→mm (8px / zoom). Devuelve True si el clic
        queda consumido por una guía (arrastrable o bloqueada).
        """
        pg = self.position_guides
        if not pg or not pg.show:
            return False
        face = getattr(self, "guides_face", "CARA")
        scale = self.current_scale if self.current_scale > 0 else 1.0
        tolerance_mm = screen_pixels_to_mm(8 / scale)
        guide = pg.hit_test(face, x_mm, y_mm, tolerance_mm)
        if guide is None:
            return False
        if guide["locked"] or pg.locked:
            return True  # bloqueada: consumir el clic, no arrastrar ni pan
        self._dragging_guide_id = guide["id"]
        self._dragging_guide_face = face
        self._gesture_moved = False
        # Feedback inmediato al pulsar (un clic sin arrastre no redibuja
        # por sí solo). Al soltar vuelve a oscuro (dragging=None).
        self._redraw_canvas_only()
        return True

    def _drag_guide(self, e):
        """Mueve una guía de posición existente con el cursor (clamp a página)."""
        pg = self.position_guides
        gid = self._dragging_guide_id
        if not pg or gid is None:
            return
        face = getattr(self, "_dragging_guide_face", "CARA")
        guide = pg.guide_at(face, gid)
        if not guide or guide["locked"] or pg.locked:
            self._dragging_guide_id = None
            return
        x_mm, y_mm = self._transform_viewer_to_page_coords(
            e.local_position.x, e.local_position.y
        )
        if guide["orientation"] == "V":
            coord = max(0.0, min(x_mm, self.page_width_mm))
        else:
            coord = max(0.0, min(y_mm, self.page_height_mm))
        self._dragging_guide_coord_vivo_mm = coord
        pg.move_guide(face, guide["id"], coord)
        self._gesture_moved = True
        self._redraw_canvas_only()

    def _finish_guide_drag(self, e):
        """Cierra el drag de guía: si se soltó sobre su regla de origen se
        borra (patrón InDesign); si no, se mantiene."""
        pg = self.position_guides
        face = getattr(self, "_dragging_guide_face", "CARA")
        gid = self._dragging_guide_id
        if pg is not None and gid is not None:
            guide = pg.guide_at(face, gid)
            _cs = getattr(self, "corner_size", 0)
            if guide is not None:
                coord_vivo_mm = getattr(self, "_dragging_guide_coord_vivo_mm", None)
                over_ruler = coord_vivo_mm is not None and coord_vivo_mm <= (
                    _cs / self.current_scale
                )
                if over_ruler:
                    pg.delete_guide(face, gid)
        self._dragging_guide_id = None
        self._dragging_guide_face = None
        self._redraw_all(force=True)

    def _on_gesture_update(self, e):
        """Actualiza durante drag de elemento o pan global"""
        if getattr(self, "_gesture_finished", False):
            return
        delta_x = e.local_delta.x if e.local_delta else 0
        delta_y = e.local_delta.y if e.local_delta else 0
        # Drag de una guía de posición existente (no de una nueva de regla)
        if self._dragging_guide_id is not None and not self._new_guide_id:
            self._drag_guide(e)
            return
        if self.dragging_element and self.dragging_element_id is not None:
            # Drag de elemento individual
            # Encontrar el elemento en la estructura de datos
            is_barcode = getattr(self, "dragging_barcode", False)
            is_variable_text = getattr(self, "dragging_variable_text", False)
            num_data = self.numeradoras.get(self.dragging_element_id)
            barcode_data = (
                self.barcodes.get(self.dragging_element_id) if is_barcode else None
            )
            variable_text_data = (
                self.variable_texts.get(self.dragging_element_id)
                if is_variable_text
                else None
            )
            element_data = (
                variable_text_data
                if is_variable_text
                else (barcode_data if is_barcode else num_data)
            )

            if not element_data:
                return

            self._gesture_moved = True
            # Calcular cambio en posición (para actualizar modelo de datos)
            # e.local_delta.x/y están en píxeles de pantalla
            # Para el modelo (mm), necesitamos des-escalar
            delta_px = delta_x / self.current_scale
            delta_py = delta_y / self.current_scale

            delta_mm_x = screen_pixels_to_mm(delta_px)
            delta_mm_y = screen_pixels_to_mm(delta_py)

            # Snap magnético: ajustar deltas si hay otro elemento cerca
            delta_mm_x, delta_mm_y = self._apply_magnetic_snap(
                element_data["data"]["x"],
                element_data["data"]["y"],
                delta_mm_x,
                delta_mm_y,
                element_data,
            )

            # Sincronizar delta_x/y con el snap para que los controles visuales
            # (target_control, guías, control_point) se muevan alineados.
            delta_x = delta_mm_x * self.current_scale
            delta_y = delta_mm_y * self.current_scale

            # Actualizar datos (en milímetros de página)
            element_data["data"]["x"] += delta_mm_x
            element_data["data"]["y"] += delta_mm_y

            # Notificar callback (para numeradoras y barcodes)
            if self.on_position_update_callback:
                try:
                    self.on_position_update_callback(
                        self.dragging_element_id,
                        element_data["data"]["x"],
                        element_data["data"]["y"],
                    )
                except Exception:
                    self._log_update_exception("drag:on_position_update_callback")

            # Mover contenedor del elemento en text_stack (in-place, sin reconstruir)
            # Solo si el stack update NO ha fallado antes (evita acumulación de error)
            _dx_sp = delta_x
            _dy_sp = delta_y
            if not getattr(self, "_drag_stack_failed", False):
                if is_barcode:
                    _bc = self.barcodes.get(self.dragging_element_id)
                    if _bc:
                        _ctrl = None
                        for _c in (
                            _bc.get("qr_container"),
                            _bc.get("pdf417_container"),
                            _bc.get("datamatrix_container"),
                            _bc.get("ean13_container"),
                            _bc.get("ean8_container"),
                            _bc.get("ean5_container"),
                            _bc.get("isbn13_container"),
                            _bc.get("upca_container"),
                            _bc.get("upce_container"),
                            _bc.get("itf14_container"),
                            _bc.get("code39_container"),
                            _bc.get("code128_container"),
                        ):
                            if _c and _c in self.text_stack.controls:
                                _ctrl = _c
                                break
                        if _ctrl:
                            _ctrl.left = (_ctrl.left or 0) + _dx_sp
                            _ctrl.top = (_ctrl.top or 0) + _dy_sp
                            self.dragging_control = _ctrl
                        elif _bc:
                            _dm_tag = f"datamatrix_{self.dragging_element_id}"
                            for _c in self.text_stack.controls:
                                if str(getattr(_c, "data", "")) == _dm_tag:
                                    _c.left = (_c.left or 0) + _dx_sp
                                    _c.top = (_c.top or 0) + _dy_sp
                                    self.dragging_control = _c
                                    _bc["datamatrix_container"] = _c
                                    break
                elif num_data is not None:
                    for _c in self.text_stack.controls:
                        if str(getattr(_c, "data", "")) == str(
                            self.dragging_element_id
                        ):
                            _c.left = (_c.left or 0) + _dx_sp
                            _c.top = (_c.top or 0) + _dy_sp
                            self.dragging_control = _c
                            break
                elif is_variable_text:
                    for _c in self.text_stack.controls:
                        if str(getattr(_c, "data", "")) == str(
                            self.dragging_element_id
                        ):
                            _c.left = (_c.left or 0) + _dx_sp
                            _c.top = (_c.top or 0) + _dy_sp
                            self.dragging_control = _c
                            break
            else:
                # Recovery: snap container to correct position via full redraw
                self._drag_stack_failed = False
                self._drag_canvas_fail_streak = 0
                self._redraw_all(force=True)
                return

            self._redraw_canvas_only()

        elif self.panning:
            self._gesture_moved = True
            # Pan con límites
            new_offset_x = self.offset_x + delta_x
            new_offset_y = self.offset_y + delta_y

            # Aplicar clamp a los límites
            self.offset_x = max(self.min_offset_x, min(self.max_offset_x, new_offset_x))
            self.offset_y = max(self.min_offset_y, min(self.max_offset_y, new_offset_y))

            # Redibujar solo si hay movimiento real (sin reglas para mejor rendimiento durante pan)
            if delta_x != 0 or delta_y != 0:
                self._redraw_canvas_only()

    def _on_gesture_end(self, e):
        """Finaliza drag o pan"""
        # Fin de drag de guía existente (commit o borrado si se suelta en la regla)
        if self._dragging_guide_id is not None and not self._new_guide_id:
            self._finish_guide_drag(e)
            return
        _had_movement = self._gesture_moved
        self.dragging_element = False
        self.dragging_element_id = None
        self.dragging_barcode = False
        self.dragging_qr = False
        self.dragging_variable_text = False
        self.dragging_control = None
        self.panning = False
        self._drag_stack_failed = False
        self._drag_canvas_fail_streak = 0
        self._gesture_moved = False
        if _had_movement:
            # Corta frames de drag aún en vuelo (thread pool de Flet) para que el
            # rebuild completo no compita con updates viejos (estela de guías).
            self._gesture_finished = True
            # Rebuild completo al soltar: auto-corrige cualquier desync residual
            # de text_stack tras zoom + pan rápido (regresión del 318 que solo redibujaba reglas)
            self._redraw_all(force=True)

    def _remove_barcode_stack_containers(self, barcode_id):
        bc = self.barcodes.get(barcode_id)
        if not bc:
            return
        for _key in ("qr_container", "pdf417_container", "datamatrix_container",
                     "ean13_container", "ean8_container", "ean5_container",
                     "isbn13_container", "upca_container", "upce_container",
                     "code39_container", "itf14_container", "code128_container"):
            _cont = bc.get(_key)
            if _cont and _cont in self.text_stack.controls:
                self.text_stack.controls.remove(_cont)

    def _redraw_canvas_only(self, force=False, only_barcode_ids=None):
        """Serializa redibujos entre threads del pool de Flet (evita frames fuera de orden)."""
        with self._redraw_lock:
            self._redraw_canvas_only_locked(
                force=force, only_barcode_ids=only_barcode_ids
            )

    def _redraw_canvas_only_locked(self, force=False, only_barcode_ids=None):
        """Redibuja solo el canvas (página + numeradoras) sin las reglas - más rápido durante drag/pan
        only_barcode_ids: lista de IDs de barcode a regenerar (None = todos).
        """
        import time

        # Rate limiter temprano: evitar trabajo desperdiciado si no vamos a enviar UI update
        if not force:
            now = time.time()
            MIN_UPDATE_INTERVAL = 0.02  # ~50 FPS
            if (now - self._last_canvas_update_ts) < MIN_UPDATE_INTERVAL:
                return
            self._last_canvas_update_ts = now

        # Guardar shapes de barcodes NO target (solo si hay only_barcode_ids)
        _saved_shapes = []
        if only_barcode_ids is not None:
            for _bid, _bc in self.barcodes.items():
                if _bid in only_barcode_ids:
                    continue
                _cp = _bc.get("control_point_shape")
                if _cp is not None:
                    _saved_shapes.append(_cp)
                for _gk in ("guide_v_control", "guide_h_control"):
                    _g = _bc.get(_gk)
                    if _g is not None:
                        _saved_shapes.append(_g)

        self.canvas_shapes = []

        # Guías de posición: PRIMERAS de la lista (debajo de todo, encima de
        # la página). Así nunca tapan ni bloquean la selección de elementos.
        self._draw_position_guides()

        # Estrategia de text_stack:
        # - force=True        → reconstruir (fin de gesto, zoom, primer draw)
        # - dragging_element  → NO reconstruir (se mueve in-place en _on_gesture_update)
        # - panning           → NO reconstruir (pan-shift in-place después)
        # - only_barcode_ids  → NO reconstruir (preservar containers de otros barcodes)
        # - otro caso         → reconstruir (cambio de perfil, selección, etc.)
        _do_text_rebuild = (force or (not self.panning and not self.dragging_element
            and self._dragging_guide_id is None and not self._new_guide_id)) and only_barcode_ids is None
        if _do_text_rebuild:
            # Re-crear el Stack evita reciclar controles con estado uid transitorio
            # cuando hay muchos ítems y rebuilds frecuentes.
            self.text_stack = ft.Stack(
                controls=[],
                width=self.big_canvas_width,
                height=self.big_canvas_height,
                clip_behavior=ft.ClipBehavior.NONE,
            )
            self.dragging_control = None
            if getattr(self, "stack", None):
                if len(self.stack.controls) >= 3:
                    self.stack.controls[2] = self.text_stack
                else:
                    self.stack.controls.append(self.text_stack)

        # 1. Posicionar base blanca de la página (Capa inferior del Stack)
        page_x = (
            self.big_canvas_width - self.canvas_width * self.current_scale
        ) / 2 + self.offset_x
        page_y = (
            self.big_canvas_height - self.canvas_height * self.current_scale
        ) / 2 + self.offset_y

        self.white_page_control.left = page_x
        self.white_page_control.top = page_y
        self.white_page_control.width = self.canvas_width * self.current_scale
        self.white_page_control.height = self.canvas_height * self.current_scale

        # Ya no dibujamos el Rect blanco en el canvas para no tapar el fondo

        # 1.1. Actualizar imagen de fondo si existe y es visible
        import sys

        # print(f"[VIEWER] Checkeando fondo: config={self.background_config is not None}, src={self.background_image_src is not None}")
        if sys.stdout is not None:
            sys.stdout.flush()
        if self.background_config and self.background_image_src:
            boxes = self.background_config.get("boxes", {})
            mb = boxes.get("mediabox")  # (x0, y0, x1, y1) en mm
            tb = boxes.get("trimbox")  # (x0, y0, x1, y1) en mm

            # Pixels per mm at current scale
            # mm_to_screen_pixels(1.0) es la escala base (DPI)
            px_per_mm = mm_to_screen_pixels(1.0)

            # Dimensiones NETAS (Trim) del papel de la app en px escalados
            app_trim_w_px = self.page_width_mm * px_per_mm * self.current_scale
            app_trim_h_px = self.page_height_mm * px_per_mm * self.current_scale
            app_bleed_px = self.bleed_mm * px_per_mm * self.current_scale

            # PDF Boxes from configuration
            boxes = self.background_config.get("boxes", {})
            tb = boxes.get("trimbox")
            cb = boxes.get("cropbox")
            mb = boxes.get("mediabox")

            # hierarchy: TrimBox > CropBox > MediaBox
            ref_box = (
                tb
                if tb and (tb[2] - tb[0] > 0)
                else (cb if cb and (cb[2] - cb[0] > 0) else mb)
            )

            if ref_box and len(ref_box) == 4:
                # ORIGINAL dimensions from file
                orig_ref_w = ref_box[2] - ref_box[0]
                orig_ref_h = ref_box[3] - ref_box[1]

                # User sizing intent
                if self.background_config.get("use_custom_size"):
                    # Custom size mode: user defines the target mm directly
                    # Scale is derived from target / original
                    custom_w = self.background_config.get("custom_width", 210.0)
                    user_scale = custom_w / orig_ref_w if orig_ref_w > 0 else 1.0
                    base_scale = 1.0
                elif self.background_config.get("auto_fit"):
                    # Auto-fit mode: scale to fit page, NO usar porcentaje
                    # Considerar rotación para calcular el ajuste correcto
                    rotation = int(self.background_config.get("rotation", 0))

                    if rotation in [90, 270]:
                        # Si está rotado, la anchura visual es la altura original y viceversa
                        eff_w = orig_ref_h
                        eff_h = orig_ref_w
                    else:
                        eff_w = orig_ref_w
                        eff_h = orig_ref_h

                    ratio_w = self.page_width_mm / eff_w if eff_w > 0 else 1.0
                    ratio_h = self.page_height_mm / eff_h if eff_h > 0 else 1.0
                    base_scale = min(ratio_w, ratio_h)
                    user_scale = (
                        1.0  # NO aplicar porcentaje cuando auto_fit está activo
                    )
                else:
                    # Manual mode: usar porcentaje de escala
                    user_scale = self.background_config.get("scale", 100) / 100.0
                    base_scale = 1.0

                final_scale = base_scale * user_scale

                # rw, rh = reference box size in screen pixels
                # ALWAYS scale from original dimensions
                rw = orig_ref_w * final_scale * px_per_mm * self.current_scale
                rh = orig_ref_h * final_scale * px_per_mm * self.current_scale

                # Size of the whole PDF (the drawn container) in screen pixels
                # We use the most inclusive box available to show everything
                container_box = mb if mb else (cb if cb else ref_box)
                media_w_mm = container_box[2] - container_box[0]
                media_h_mm = container_box[3] - container_box[1]

                # Offset of reference inside the drawn container (en mm)
                ref_off_x_mm = ref_box[0] - container_box[0]
                ref_off_y_mm = ref_box[1] - container_box[1]

                img_w = media_w_mm * final_scale * px_per_mm * self.current_scale
                img_h = media_h_mm * final_scale * px_per_mm * self.current_scale

                img_ref_off_x = (
                    ref_off_x_mm * final_scale * px_per_mm * self.current_scale
                )
                img_ref_off_y = (
                    ref_off_y_mm * final_scale * px_per_mm * self.current_scale
                )
            else:
                # Fallback for raster images
                img_w_mm = self.background_config.get(
                    "custom_width", self.page_width_mm
                )
                img_h_mm = self.background_config.get(
                    "custom_height", self.page_height_mm
                )

                if self.background_config.get("use_custom_size"):
                    # Use absolute dimensions as target
                    final_scale = 1.0
                elif self.background_config.get("auto_fit"):
                    # Auto-fit mode
                    rotation = int(self.background_config.get("rotation", 0))
                    if rotation in [90, 270]:
                        eff_w = img_h_mm
                        eff_h = img_w_mm
                    else:
                        eff_w = img_w_mm
                        eff_h = img_h_mm

                    ratio_w = self.page_width_mm / eff_w if eff_w > 0 else 1.0
                    ratio_h = self.page_height_mm / eff_h if eff_h > 0 else 1.0
                    final_scale = min(ratio_w, ratio_h)
                else:
                    # Manual mode: usar porcentaje de escala
                    user_scale = self.background_config.get("scale", 100) / 100.0
                    final_scale = user_scale

                img_w = img_w_mm * final_scale * px_per_mm * self.current_scale
                img_h = img_h_mm * final_scale * px_per_mm * self.current_scale
                rw, rh = img_w, img_h
                img_ref_off_x = 0
                img_ref_off_y = 0

            # Alignment (Applied to the Reference Box inside App's Trim Area)
            align = self.background_config.get("alignment", "center")
            rotation = self.background_config.get("rotation", 0)

            # Para alineamientos de borde, necesitamos dimensiones visuales (rotadas)
            # Para centro puro, usamos dimensiones originales (Flet rota desde el centro)
            is_pure_center = align in ["center", "middle"]

            if is_pure_center:
                # Centro: usar dimensiones originales (rotación se hace desde el centro)
                visual_w = rw
                visual_h = rh
            else:
                # Bordes: usar dimensiones visuales después de rotar
                if rotation in [90, 270]:
                    visual_w = rh
                    visual_h = rw
                else:
                    visual_w = rw
                    visual_h = rh

            rel_x = 0
            rel_y = 0

            # Calcular alineamiento
            if "center" in align or "middle" in align:
                rel_x = (app_trim_w_px - visual_w) / 2
                rel_y = (app_trim_h_px - visual_h) / 2

            # Refine per axis
            if "top" in align:
                rel_y = 0
            if "bottom" in align:
                rel_y = app_trim_h_px - visual_h
            if "left" in align:
                rel_x = 0
            if "right" in align:
                rel_x = app_trim_w_px - visual_w

            # Manual Offset (mm -> px escalados)
            off_x_mm = self.background_config.get("offset_x", 0)
            off_y_mm = self.background_config.get("offset_y", 0)
            off_x_px = mm_to_screen_pixels(off_x_mm) * self.current_scale
            off_y_px = mm_to_screen_pixels(off_y_mm) * self.current_scale

            # Para rotaciones, los offsets de referencia interna necesitan transformarse
            # Por ahora, cuando hay rotación NO aplicamos offsets internos del PDF
            if rotation in [90, 270]:
                # TODO: Calcular transformación correcta de offsets para rotación
                rotated_ref_off_x = 0
                rotated_ref_off_y = 0
            else:
                rotated_ref_off_x = img_ref_off_x
                rotated_ref_off_y = img_ref_off_y

            # Debug print
            print(f"\n[VIEWER BG] Configuración:")
            print(f"  Alineamiento: {align}")
            print(f"  Rotación: {rotation}°")
            print(f"  is_pure_center: {is_pure_center}")
            print(f"  Offset (mm): H={off_x_mm}, V={off_y_mm}")
            print(f"  Offset (px): H={off_x_px:.1f}, V={off_y_px:.1f}")
            print(f"  Dimensiones imagen: {img_w:.1f}x{img_h:.1f}px")
            print(f"  Dimensiones referencia originales: {rw:.1f}x{rh:.1f}px")
            print(f"  Dimensiones visuales (después de rotar): {visual_w:.1f}x{visual_h:.1f}px")
            print(f"  Area trim app: {app_trim_w_px:.1f}x{app_trim_h_px:.1f}px")
            print(f"  Posición relativa calculada: rel_x={rel_x:.1f}, rel_y={rel_y:.1f}")
            print(f"  app_bleed_px: {app_bleed_px:.1f}")
            print(f"  img_ref_off originales: x={img_ref_off_x:.1f}, y={img_ref_off_y:.1f}")
            print(f"  img_ref_off rotados: x={rotated_ref_off_x:.1f}, y={rotated_ref_off_y:.1f}")

            # Final position (Relative to white_page_control's top-left)
            # app_bleed_px points to the App's TrimBox top-left

            # Cuando hay rotación, Flet rota alrededor del centro del control
            # Necesitamos ajustar left/top para compensar
            if rotation in [90, 270]:
                # Calcular centro visual deseado
                visual_center_x = (
                    app_bleed_px + rel_x + off_x_px + visual_w / 2 - rotated_ref_off_x
                )
                visual_center_y = (
                    app_bleed_px + rel_y + off_y_px + visual_h / 2 - rotated_ref_off_y
                )

                # Convertir a left/top del control original (sin rotar)
                final_left = visual_center_x - img_w / 2
                final_top = visual_center_y - img_h / 2
            else:
                # Sin rotación, posición directa
                final_left = app_bleed_px + rel_x + off_x_px - rotated_ref_off_x
                final_top = app_bleed_px + rel_y + off_y_px - rotated_ref_off_y

            # print(f"  Posición final: left={final_left:.1f}, top={final_top:.1f}\n")

            self.background_image_control.visible = True
            self.background_image_control.left = final_left
            self.background_image_control.top = final_top
            self.background_image_control.width = img_w
            self.background_image_control.height = img_h
            self.background_image_control.rotate = ft.Rotate(
                angle=math.radians(rotation)
            )

            # Force FILL because we manually calculate dimensions
            self.background_image_control.fit = ft.BoxFit.FILL

            # Ensure internal stack covers the whole area (including app bleed)
            self.white_page_control.content.width = self.white_page_control.width
            self.white_page_control.content.height = self.white_page_control.height
        else:
            self.background_image_control.visible = False

        self.canvas_shapes.append(
            cv.Rect(
                page_x,
                page_y,
                self.canvas_width * self.current_scale,
                self.canvas_height * self.current_scale,
                paint=ft.Paint(
                    color=BORDE_TEXTFIELDS_COLOR,
                    stroke_width=1,
                    style=ft.PaintingStyle.STROKE,
                ),
            )
        )

        # 1.5. Dibujar líneas de sangre si hay sangre > 0
        if self.bleed_mm > 0:
            bleed_px = mm_to_screen_pixels(self.bleed_mm) * self.current_scale

            # Rectángulo interior (área de página sin sangre)
            inner_x = page_x + bleed_px
            inner_y = page_y + bleed_px
            inner_width = self.canvas_width * self.current_scale - (bleed_px * 2)
            inner_height = self.canvas_height * self.current_scale - (bleed_px * 2)

            self.canvas_shapes.append(
                cv.Rect(
                    inner_x,
                    inner_y,
                    inner_width,
                    inner_height,
                    paint=ft.Paint(
                        color=ft.Colors.RED_300,
                        stroke_width=1,
                        style=ft.PaintingStyle.STROKE,
                    ),
                )
            )

        # 2. Dibujar numeradoras y líneas
        line_width = 0.0
        # Aumentado +4px para que el punto de control sea más visible
        circle_radius = 6.0

        # Función de ayuda (definida fuera del loop para estar disponible incluso sin numeradoras)
        def _viewer_tinted_color(base_hex, tint_pct, color_space):
            if color_space != "SPOT" or tint_pct >= 99.9:
                return base_hex
            try:
                val = str(base_hex).lstrip("#")
                if len(val) == 6:
                    r0, g0, b0 = tuple(int(val[i : i + 2], 16) for i in (0, 2, 4))
                    t = max(0.0, min(100.0, float(tint_pct))) / 100.0
                    r = max(0, min(255, int(round(255 + (r0 - 255) * t))))
                    g = max(0, min(255, int(round(255 + (g0 - 255) * t))))
                    b = max(0, min(255, int(round(255 + (b0 - 255) * t))))
                    return f"#{r:02x}{g:02x}{b:02x}"
            except Exception:
                pass
            return base_hex

        for num_id, num_data in self.numeradoras.items():
            x_mm = num_data["data"]["x"]
            y_mm = num_data["data"]["y"]
            number = num_data["data"]["number"]
            alignment = num_data["data"]["alignment"]
            rotation_str = num_data["data"].get("rotation", "0°")

            # Convertir rotación de string a grados y radianes
            rotation_degrees = int(rotation_str.replace("°", ""))
            rotation_radians = (
                rotation_degrees * 3.14159265359 / 180.0
                if rotation_degrees != 0
                else None
            )

            # Transformar a coordenadas de viewer
            x_viewer, y_viewer = self._transform_page_to_viewer_coords(x_mm, y_mm)

            # Determinar color según selección y bloqueo
            is_selected = num_id == self.selected_id
            is_locked = num_data["data"].get("locked", False)
            color = (
                COLOR_LOCKED
                if is_locked
                else (COLOR_ACTIVO if is_selected else COLOR_INACTIVO)
            )

            # Líneas guía (solo si show_guides=True). El círculo de control se dibuja siempre.
            # Guardamos referencia a las shapes para poder moverlas en el drag & drop
            # Inicializar referencias en None
            self.numeradoras[num_id]["guide_v_control"] = None
            self.numeradoras[num_id]["guide_h_control"] = None
            self.numeradoras[num_id]["verification_line_control"] = None

            if self.show_guides:
                # Línea vertical (desde arriba hasta abajo del viewer)
                guide_v_shape = cv.Line(
                    x_viewer,
                    0,
                    x_viewer,
                    self.viewer_height,
                    paint=ft.Paint(stroke_width=line_width, color=color),
                )
                self.canvas_shapes.append(guide_v_shape)
                self.numeradoras[num_id]["guide_v_control"] = guide_v_shape

                # Línea horizontal (desde izquierda hasta derecha del viewer)
                guide_h_shape = cv.Line(
                    0,
                    y_viewer,
                    self.viewer_width,
                    y_viewer,
                    paint=ft.Paint(stroke_width=line_width, color=color),
                )
                self.canvas_shapes.append(guide_h_shape)
                self.numeradoras[num_id]["guide_h_control"] = guide_h_shape

            # Círculo de control
            control_point_shape = cv.Circle(
                x_viewer,
                y_viewer,
                circle_radius,
                paint=ft.Paint(color=color, style=ft.PaintingStyle.FILL),
            )
            self.canvas_shapes.append(control_point_shape)
            self.numeradoras[num_id]["control_point_shape"] = control_point_shape

            # Saltar reconstrucción de controles Flet de texto si no hace falta.
            # Durante barcode-drag y pan los controles ya existen con uid válido.
            if not _do_text_rebuild:
                continue

            # Texto - Obtener estilo de texto (sin resolver fuente en cada redibujado)
            text_style_name = num_data["data"].get("text_style_name", "<Default>")
            text_style = None
            if self.text_style_manager:
                # Acceso ligero a perfiles (no búsqueda de archivos aquí)
                for profile in self.text_style_manager.profiles:
                    if profile.name == text_style_name:
                        text_style = profile
                        print(
                            f"\n[VIEWER] Numeradora {num_id}: Usando perfil '{text_style_name}'"
                        )
                        print(f"  Font: {profile.font_family} {profile.font_style}")
                        print(
                            f"  resolved_font_path: {getattr(profile, 'resolved_font_path', 'N/A')}"
                        )
                        print(f"  Has metricas: {hasattr(profile, 'metricas')}")
                        if hasattr(profile, "metricas") and profile.metricas:
                            print(
                                f"  metricas['font_path']: {profile.metricas.get('font_path', 'N/A')}"
                            )
                        break

            # Si no se encuentra el estilo, usar valores por defecto
            if text_style is None:
                base_font_size = 14.0
                font_family = "Helvetica"
                number_color = ft.Colors.BLACK
                prefix_color = ft.Colors.BLACK
                suffix_color = ft.Colors.BLACK
                font_weight = ft.FontWeight.NORMAL
                font_italic = False
                letter_spacing = 0.0
                prefix_suffix_spacing = 0.0
                prefix = ""
                suffix = ""
                mask = ""
                mask_placeholder = "*"
                digit_placeholder = 0
            else:
                base_font_size = float(text_style.font_size)
                # Preferir alias registrado en Flet (si existe) — evita usar TTC index directamente
                resolved_alias = getattr(text_style, "resolved_flet_alias", None)
                print(f"[VIEWER_FONT] resolved_flet_alias: {resolved_alias}")
                print(f"[VIEWER_FONT] font_family (fallback): {text_style.font_family}")
                font_family = (
                    resolved_alias if resolved_alias else text_style.font_family
                )
                print(f"[VIEWER_FONT] font_family usado en ft.Text: {font_family}")

                # Verificar si está registrado en page.fonts
                if (
                    _safe_page(self) is not None
                    and self.page
                    and hasattr(self.page, "fonts")
                    and self.page.fonts
                ):
                    is_registered = font_family in self.page.fonts
                    print(
                        f"[VIEWER_FONT] ¿Está '{font_family}' en page.fonts? {is_registered}"
                    )
                    if is_registered:
                        print(
                            f"[VIEWER_FONT] Ruta registrada: {self.page.fonts[font_family]}"
                        )
                else:
                    print(f"[VIEWER_FONT] page.fonts no está disponible")

                # Obtener los tres colores con su espacio de color independiente
                num_color_space = getattr(
                    text_style,
                    "number_color_space",
                    getattr(text_style, "color_space", "RGB"),
                )
                pref_color_space = getattr(
                    text_style,
                    "prefix_color_space",
                    getattr(text_style, "color_space", "RGB"),
                )
                suf_color_space = getattr(
                    text_style,
                    "suffix_color_space",
                    getattr(text_style, "color_space", "RGB"),
                )

                base_num_color = (
                    text_style.number_color
                    if hasattr(text_style, "number_color")
                    else text_style.color
                )
                num_tint = float(getattr(text_style, "number_color_tint", 100.0))
                number_color = _viewer_tinted_color(
                    base_num_color, num_tint, num_color_space
                )

                base_pref_color = (
                    text_style.prefix_color
                    if hasattr(text_style, "prefix_color")
                    else base_num_color
                )
                pref_tint = float(getattr(text_style, "prefix_color_tint", 100.0))
                prefix_color = _viewer_tinted_color(
                    base_pref_color, pref_tint, pref_color_space
                )

                base_suf_color = (
                    text_style.suffix_color
                    if hasattr(text_style, "suffix_color")
                    else base_num_color
                )
                suf_tint = float(getattr(text_style, "suffix_color_tint", 100.0))
                suffix_color = _viewer_tinted_color(
                    base_suf_color, suf_tint, suf_color_space
                )

                letter_spacing = (
                    float(text_style.letter_spacing)
                    if hasattr(text_style, "letter_spacing")
                    else 0.0
                )
                prefix_suffix_spacing = (
                    float(text_style.prefix_suffix_spacing)
                    if hasattr(text_style, "prefix_suffix_spacing")
                    else 0.0
                )
                prefix = text_style.prefix
                suffix = text_style.suffix
                mask = text_style.mask if hasattr(text_style, "mask") else ""
                mask_placeholder = (
                    text_style.mask_placeholder
                    if hasattr(text_style, "mask_placeholder")
                    else "*"
                )
                digit_placeholder = (
                    int(text_style.digit_placeholder)
                    if hasattr(text_style, "digit_placeholder")
                    else 0
                )

                # Mapear estilo a weight e italic
                style_lower = text_style.font_style.lower()

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
                    font_weight = weight_map.get(w_number, ft.FontWeight.NORMAL)
                # Si no es W#, usar detección por palabras clave
                elif "black" in style_lower:
                    font_weight = ft.FontWeight.W_900
                elif "bold" in style_lower:
                    font_weight = ft.FontWeight.BOLD
                elif "semibold" in style_lower or "medium" in style_lower:
                    font_weight = ft.FontWeight.W_600
                elif "light" in style_lower:
                    font_weight = ft.FontWeight.W_300
                elif "thin" in style_lower or "ultralight" in style_lower:
                    font_weight = ft.FontWeight.W_100
                else:
                    font_weight = ft.FontWeight.NORMAL

                font_italic = "italic" in style_lower or "oblique" in style_lower

                # If no resolved_flet_alias is present but we have a resolved font path
                # (or can locate the variant in the global gestor), attempt to extract the
                # TTC member to a temp file and register an alias in `page.fonts` so Flet
                # uses the exact file (avoids relying only on family+weight heuristics).
                try:
                    if getattr(text_style, "resolved_flet_alias", None) is None:
                        # Prefer resolved path from profile (prefs) when available
                        ruta = getattr(text_style, "resolved_font_path", None)
                        idx = getattr(text_style, "resolved_font_index", 0) or 0
                        if not ruta:
                            # Fallback: ask gestor for variant by family/style
                            try:
                                from utils import font_manager

                                gestor = font_manager.obtener_gestor()
                                fam = getattr(text_style, "font_family", None)
                                if fam:
                                    variante = gestor.buscar_por_estilo(
                                        fam, getattr(text_style, "font_style", "")
                                    )
                                    if variante:
                                        ruta = variante.get("ruta")
                                        idx = variante.get("ttc_index", 0) or 0
                            except Exception:
                                ruta = None

                        if ruta:
                            try:
                                from utils import font_ttc, font_cache
                                from pathlib import Path

                                cache_dir = font_cache.get_config_dir()
                                extracted_dir = font_cache.extracted_dir(cache_dir)
                                Path(extracted_dir).mkdir(parents=True, exist_ok=True)
                                safe_name = (
                                    getattr(text_style, "font_family", "font") or "font"
                                ).replace(" ", "")
                                out_name = f"{safe_name}__{idx}.ttf"
                                out_path = str(Path(extracted_dir) / out_name)
                                ok = font_ttc.extract_subfont_to_file(
                                    ruta, int(idx), out_path
                                )
                                if (
                                    ok
                                    and _safe_page(self) is not None
                                    and self.page is not None
                                ):
                                    alias = f"{safe_name}__{idx}"
                                    try:
                                        if alias not in getattr(self.page, "fonts", {}):
                                            self.page.fonts[alias] = out_path
                                    except Exception:
                                        pass
                                    text_style.resolved_flet_alias = alias
                                    font_family = alias  # ← Actualizar variable local para ESTE redraw
                                    # Persist extracted mapping so we don't re-parse the TTC next time
                                    try:
                                        cache_dir = font_cache.get_config_dir()
                                        font_cache.add_extracted_entry(
                                            cache_dir, ruta, int(idx), out_path
                                        )
                                    except Exception:
                                        pass
                            except Exception:
                                pass

                                # DEBUG: imprimir información sobre la fuente resuelta y el alias extraído
                                try:
                                    try:
                                        alias = getattr(
                                            text_style, "resolved_flet_alias", None
                                        )
                                    except Exception:
                                        alias = None
                                    effective_font = alias if alias else font_family
                                    debug_parts = [
                                        f"[VIEWER_FONT] style={text_style_name}",
                                        f"effective_font={effective_font}",
                                        f"alias={alias}",
                                    ]

                                    # Ver ruta registrada en page.fonts si hay alias
                                    try:
                                        if (
                                            alias
                                            and _safe_page(self) is not None
                                            and self.page is not None
                                        ):
                                            page_fonts = (
                                                getattr(self.page, "fonts", {}) or {}
                                            )
                                            path = page_fonts.get(alias)
                                            debug_parts.append(
                                                f"page_fonts_path={path}"
                                            )
                                    except Exception:
                                        pass

                                    # Intentar leer la entrada del cache font_index.json para este original|index
                                    try:
                                        from utils import font_cache
                                        from pathlib import Path

                                        base = font_cache.get_config_dir()
                                        cache = font_cache.load_cache(base) or {}
                                        em = cache.get("extracted_map", {}) or {}

                                        orig_path_val = getattr(
                                            text_style, "resolved_font_path", None
                                        )
                                        if not orig_path_val and "ruta" in locals():
                                            orig_path_val = ruta
                                        idx_val = None
                                        try:
                                            idx_val = int(
                                                getattr(
                                                    text_style,
                                                    "resolved_font_index",
                                                    None,
                                                )
                                                or (idx if "idx" in locals() else 0)
                                            )
                                        except Exception:
                                            idx_val = 0

                                        if orig_path_val:
                                            key = f"{orig_path_val}|{idx_val}"
                                            entry = em.get(key)
                                            debug_parts.append(f"cache_key={key}")
                                            if entry:
                                                debug_parts.append(
                                                    f"cache_extracted={entry.get('extracted_path')}"
                                                )
                                                try:
                                                    chk = font_cache.compute_checksum(
                                                        Path(
                                                            entry.get("extracted_path")
                                                        )
                                                    )
                                                    debug_parts.append(
                                                        f"cache_checksum={chk}"
                                                    )
                                                except Exception:
                                                    pass
                                    except Exception:
                                        pass

                                    print(" ".join([p for p in debug_parts if p]))
                                except Exception:
                                    pass
                except Exception:
                    pass

            # Obtener configuración de separador de millares
            thousands_separator = (
                text_style.thousands_separator
                if hasattr(text_style, "thousands_separator")
                else "normal"
            )
            # print(f"[VIEWER_DEBUG] Style: {text_style_name}, Sep Type: '{thousands_separator}', Num: {number}, Mask: '{mask}'")

            # Aplicar máscara y formato completo
            formatted_number = _apply_mask(
                number,
                mask,
                thousands_separator,
                placeholder=mask_placeholder,  # Legacy param, ignored
                digit_placeholder=digit_placeholder,  # Legacy param, ignored
            )

            # Aplicar prefijo y sufijo
            display_text = f"{prefix}{formatted_number}{suffix}"
            # print(f"[VIEWER_DRAW] Numeradora {num_id}: number='{number}', prefix='{prefix}', suffix='{suffix}', display_text='{display_text}'")

            # ═══════════════════════════════════════════════════════════════════════════
            # CONVERSIÓN DE TAMAÑO DE FUENTE: PDF (PyMuPDF) → VIEWER (cv.Text)
            # ═══════════════════════════════════════════════════════════════════════════
            # PyMuPDF usa puntos PostScript (72 DPI) en page.insert_text(fontsize=...)
            # cv.Text de Flet NO escala automáticamente con el canvas zoom
            #
            # Fórmula final verificada:
            #   adjusted_font_size = font_size_pt × 0.3528 × current_scale
            #
            # Donde:
            #   - font_size_pt: Tamaño en puntos del perfil de texto (ej: 40pt)
            #   - 0.3528: Factor de conversión pt→mm (25.4mm/inch ÷ 72pt/inch) [constante global FONT_PT_TO_MM]
            #   - current_scale: Zoom del canvas (ej: 3.909 para ajustar al viewer)
            #
            # Ejemplo: 40pt × 0.3528 × 3.909 = 55.16pt en cv.Text
            #
            # Nota: Esta conversión garantiza que el texto del viewer coincida
            #       visualmente con el PDF generado, y escale correctamente con zoom.
            # ═══════════════════════════════════════════════════════════════════════════
            adjusted_font_size = base_font_size * FONT_PT_TO_MM * self.current_scale
            # print(f"[VIEWER_DRAW] Font size: {base_font_size}pt × {FONT_PT_TO_MM} × zoom({self.current_scale:.3f}) = {adjusted_font_size:.2f}pt")

            text_x_mm = self._calculate_text_x_position(
                x_mm, alignment, display_text, base_font_size
            )
            text_x_viewer, text_y_viewer = self._transform_page_to_viewer_coords(
                text_x_mm, y_mm
            )

            # Ajuste de baseline según rotación:
            # PASO 3: Usar métricas de fuente en lugar del factor fijo 0.20
            # Con height=1.0, el EM-square es uniforme para todas las fuentes
            # Flet usa bottom_* (fondo del EM-square)
            # PyMuPDF usa baseline (línea donde se apoyan las letras)

            # Calcular baseline_offset usando las métricas (en lugar del factor 0.20)
            metrics = getattr(text_style, "metricas", None) if text_style else None
            print(f"[VIEWER] Has metrics: {metrics is not None}")
            if metrics:
                print(f"  baseline_to_top: {metrics.get('baseline_to_top', 'N/A')}")
                print(f"  font_path en metrics: {metrics.get('font_path', 'N/A')}")
            if metrics and isinstance(metrics, dict) and base_font_size > 0:
                # Obtener baseline_to_top en puntos (métrica extraída SIEMPRE a 12pt de referencia)
                baseline_to_top_pt = metrics.get("baseline_to_top", 0)
                baseline_to_bottom_pt = metrics.get("baseline_to_bottom", 0)
                left_bearing_pt = metrics.get("left_bearing", 0)

                # Las métricas están en pt, extraídas a 12pt SIEMPRE
                # Ratio = baseline_to_top_pt / 12 (tamaño de extracción, NO el font_size del perfil)
                REFERENCE_EXTRACTION_SIZE = 12
                baseline_ratio = baseline_to_top_pt / REFERENCE_EXTRACTION_SIZE
                baseline_bottom_ratio = (
                    baseline_to_bottom_pt / REFERENCE_EXTRACTION_SIZE
                )
                left_bearing_ratio = left_bearing_pt / REFERENCE_EXTRACTION_SIZE

                # Calcular ratios base para posicionamiento preciso
                ascent_ratio = metrics.get("ascent_ratio", baseline_ratio)
                descent_ratio = metrics.get("descent_ratio", baseline_bottom_ratio)

                # --- CALCULO DE ALTURA SEGURA Y OFFSET ---
                # Flet centra el texto verticalmente en el 'line_height'.
                # Calculamos una altura que cubra toda la métrica + un margen de seguridad (10%).
                metric_height_ratio = ascent_ratio + descent_ratio
                target_height_ratio = (
                    metric_height_ratio * 1.1
                )  # 10% extra para seguridad

                # Calcular el padding superior que Flet añadirá al centrar
                # top_padding = (Height - ContentHeight) / 2
                top_padding_ratio = (target_height_ratio - metric_height_ratio) / 2.0

                # El offset total desde el top del contenedor hasta el baseline es:
                # PaddingSuperior + Ascender
                total_baseline_ratio = top_padding_ratio + ascent_ratio

                # Calcular left_bearing_offset (desplazamiento horizontal inicial)
                # ratio real de la fuente
                real_bearing_ratio = max(left_bearing_ratio, 0.0)

                # Calculamos el ajuste final según el alineamiento
                if alignment == "izquierda":
                    # Izquierda: Compensamos el bearing real + el ajuste manual
                    # (Ambos empujan el texto a la izquierda para que la tinta toque la guía)
                    final_ratio = real_bearing_ratio + VISUAL_CORRECTION_LEFT
                    bearing_adj = adjusted_font_size * final_ratio
                elif alignment == "centro":
                    # Centro: Compensamos la mitad del bearing para mantener equilibrio
                    final_ratio = (real_bearing_ratio / 2.0) + VISUAL_CORRECTION_CENTER
                    bearing_adj = adjusted_font_size * final_ratio
                else:  # derecha
                    # Derecha: el anclaje ya se calcula con right_anchor_width.
                    # Aplicar bearing aquí desplaza el contenedor respecto a la guía.
                    final_ratio = 0.0
                    bearing_adj = 0.0

                # Guardamos para usar en los offsets de rotación
                left_bearing_offset = bearing_adj

                # Aplicar al tamaño en píxeles
                baseline_offset = adjusted_font_size * total_baseline_ratio

                # Aplicar ajuste visual de baseline por rotación (fracción del font_size)
                from utils.constants import (
                    VISUAL_BASELINE_ADJUST_0,
                    VISUAL_BASELINE_ADJUST_90,
                    VISUAL_BASELINE_ADJUST_180,
                    VISUAL_BASELINE_ADJUST_270,
                )

                if rotation_degrees == 0:
                    baseline_offset += adjusted_font_size * VISUAL_BASELINE_ADJUST_0
                elif rotation_degrees == 90:
                    baseline_offset += adjusted_font_size * VISUAL_BASELINE_ADJUST_90
                elif rotation_degrees == 180:
                    baseline_offset += adjusted_font_size * VISUAL_BASELINE_ADJUST_180
                elif rotation_degrees == 270:
                    baseline_offset += adjusted_font_size * VISUAL_BASELINE_ADJUST_270

                # print(f"[METRICS_CALC] Font: {font_family}")
                # print(f"  Ascent: {ascent_ratio:.4f}, Descent: {descent_ratio:.4f}, Total: {metric_height_ratio:.4f}")
                # print(f"  Ajuste Horizontal (en font_ratio): {final_ratio:.4f} (Alignment: {alignment})")
                # print(f"  Target Height: {target_height_ratio:.4f} (×1.1)")
                # print(f"  Top Padding: {top_padding_ratio:.4f}")
                # print(f"  Baseline Ratio: {total_baseline_ratio:.4f}")
                # print(f"  Offset: {baseline_offset:.2f}px (Size: {adjusted_font_size:.2f}px)")

            else:
                # Fallback: asumir fuente estándar (Ascent 0.8, Descent 0.2)
                print(
                    f"[VIEWER] ⚠️ USANDO FALLBACK - Sin métricas para {text_style_name}"
                )
                ascent_ratio = 0.8
                descent_ratio = 0.2
                metric_height_ratio = 1.0
                target_height_ratio = 1.1
                top_padding_ratio = (1.1 - 1.0) / 2.0
                total_baseline_ratio = top_padding_ratio + ascent_ratio

                baseline_offset = adjusted_font_size * total_baseline_ratio
                left_bearing_offset = 0

            # PASO FINAL: Determinar el ajuste horizontal (bearing_adj) basado en el alineamiento.
            # Este ajuste se usará luego en las fórmulas de rotación (offset_x/y).
            bearing_adj = left_bearing_offset

            if rotation_degrees == 0:
                # 0°: texto horizontal normal
                # offset_y = -baseline_offset: el baseline toca la línea guía
                # offset_x = -bearing_adj: el inicio/final visual coincide con la guía
                offset_x = -bearing_adj
                offset_y = -baseline_offset
            elif rotation_degrees == 90:
                # 90°: texto vertical (rotado a la derecha)
                offset_x = baseline_offset
                offset_y = -bearing_adj
            elif rotation_degrees == 180:
                # 180°: texto horizontal invertido
                offset_x = bearing_adj
                offset_y = baseline_offset
            elif rotation_degrees == 270:
                # 270°: texto vertical (rotado a la izquierda)
                offset_x = -baseline_offset
                offset_y = bearing_adj
            else:
                # Sin rotación conocida, no ajustar
                offset_x = 0
                offset_y = 0

            # Construir TextSpans POR CARÁCTER para texto con múltiples colores.
            # OJO: Flutter aplica letterSpacing DESPUÉS de cada carácter (incluido
            # el último de cada span y el último del texto). Con un span por
            # segmento se generarían huecos no deseados en los límites
            # prefijo→número, número→sufijo y tras el último carácter, separando
            # el bloque y descuadrando el ancho respecto a real_text_width.
            # Con un span por carácter solo se aplica letter_spacing cuando el
            # siguiente carácter pertenece al MISMO segmento (n-1 huecos por
            # segmento, ninguno en los límites), igual que la medición.
            number_start = len(prefix)
            number_end = number_start + len(formatted_number)
            ls_scaled = letter_spacing * FONT_PT_TO_MM * self.current_scale
            text_spans = []
            for _i, _ch in enumerate(display_text):
                if _i < number_start:
                    _char_color = prefix_color
                elif _i < number_end:
                    _char_color = number_color
                else:
                    _char_color = suffix_color
                # letter_spacing SOLO si hay un carácter siguiente en el mismo
                # segmento; en los límites prefijo→número y número→sufijo va
                # prefix_suffix_spacing (misma semántica que el PDF)
                pss_scaled = prefix_suffix_spacing * FONT_PT_TO_MM * self.current_scale
                _char_ls = 0.0
                if _i < len(display_text) - 1:
                    if _i == number_start - 1 or _i == number_end - 1:
                        if prefix_suffix_spacing != 0:
                            _char_ls = pss_scaled
                        elif letter_spacing != 0:
                            _char_ls = ls_scaled
                    elif letter_spacing != 0:
                        _char_ls = ls_scaled
                text_spans.append(
                    ft.TextSpan(
                        _ch,
                        ft.TextStyle(
                            size=adjusted_font_size,
                            color=_char_color,
                            font_family=font_family,
                            weight=font_weight,
                            italic=font_italic,
                            letter_spacing=_char_ls,
                            height=target_height_ratio,
                        ),
                    )
                )

            # DEBUG: Imprimir información de posicionamiento ANTES de dibujar
            # Guardar para debug posterior
            self._last_offset_debug = {
                "num_id": num_id,
                "x_viewer": x_viewer,
                "y_viewer": y_viewer,
                "text_x_viewer": text_x_viewer,
                "text_y_viewer": text_y_viewer,
                "baseline_offset": baseline_offset,
                "offset_x": offset_x,
                "offset_y": offset_y,
                "rotation": rotation_degrees,
                "adjusted_font_size": adjusted_font_size,
                "font_family": font_family,
                "y_final": text_y_viewer + offset_y,
                "y_difference": (text_y_viewer + offset_y) - y_viewer,
            }
            # print(f"[OFFSET_DEBUG] num_id={num_id} | guia_y={y_viewer:.1f}px | texto_y_final={(text_y_viewer + offset_y):.1f}px | diferencia={(text_y_viewer + offset_y) - y_viewer:.1f}px | offset_y={offset_y:.1f}px | font_size={adjusted_font_size:.1f}pt")

            # Calcular ancho del texto usando PyMuPDF por carácter.
            # Esto evita errores ópticos cuando cambia el último glifo (ej: Y vs M).
            font = None
            try:
                # Intentar usar el archivo de fuente real si está resuelto
                font_path = getattr(text_style, "resolved_font_path", None)
                if font_path and os.path.exists(font_path):
                    font = fitz.Font(fontfile=font_path)
                else:
                    # Fallback a nombre de familia (fitz intentará resolverlo o usará fuentes estándar)
                    font = fitz.Font(fontname=font_family)

                number_start = len(prefix)
                number_end = number_start + len(formatted_number)

                text_width_pt = 0.0
                for i, ch in enumerate(display_text):
                    text_width_pt += float(
                        font.text_length(ch, fontsize=base_font_size)
                    )
                    # Intra-segmento (n-1 huecos): letter_spacing. En los límites
                    # prefijo→número y número→sufijo: prefix_suffix_spacing.
                    # Misma semántica que _build_pdf_segments en el PDF.
                    if i < len(display_text) - 1:
                        if prefix_suffix_spacing != 0 and (
                            i == number_start - 1 or i == number_end - 1
                        ):
                            text_width_pt += prefix_suffix_spacing
                        elif letter_spacing != 0:
                            text_width_pt += letter_spacing

                real_text_width = text_width_pt * FONT_PT_TO_MM * self.current_scale
            except Exception:
                # Fallback: aproximar por número de caracteres
                real_text_width = (
                    len(display_text) * adjusted_font_size * 0.6
                )  # Fallback razonable

            right_anchor_width = real_text_width
            if alignment == "derecha":
                try:
                    font_path_for_measure = getattr(
                        text_style, "resolved_font_path", None
                    )
                    if not font_path_for_measure and hasattr(text_style, "metricas"):
                        metricas = getattr(text_style, "metricas", {}) or {}
                        font_path_for_measure = metricas.get("font_path")

                    if font_path_for_measure and os.path.exists(font_path_for_measure):
                        from utils.metrics_analisys import (
                            DEFAULT_FONT_METRICS,
                        )

                        number_start = len(prefix)
                        number_end = number_start + len(formatted_number)
                        pen_pt = 0.0
                        max_right_pt = 0.0

                        for i, ch in enumerate(display_text):
                            char_metrics = DEFAULT_FONT_METRICS.measure_text(
                                str(font_path_for_measure), base_font_size, ch
                            )
                            char_left_pt = float(char_metrics.get("left_bearing", 0.0))
                            char_ink_width_pt = float(char_metrics.get("width", 0.0))
                            char_right_pt = pen_pt + char_left_pt + char_ink_width_pt
                            if char_right_pt > max_right_pt:
                                max_right_pt = char_right_pt

                            if font is not None:
                                adv_pt = float(
                                    font.text_length(ch, fontsize=base_font_size)
                                )
                            else:
                                adv_pt = char_ink_width_pt
                            pen_pt += adv_pt
                            if i < len(display_text) - 1:
                                if prefix_suffix_spacing != 0 and (
                                    i == number_start - 1 or i == number_end - 1
                                ):
                                    pen_pt += prefix_suffix_spacing
                                elif letter_spacing != 0:
                                    pen_pt += letter_spacing

                        right_ink_pt = max_right_pt
                        ink_width_pt = max_right_pt

                        right_anchor_width = (
                            right_ink_pt * FONT_PT_TO_MM * self.current_scale
                        )
                except Exception:
                    right_anchor_width = real_text_width

            if alignment == "derecha" and RIGHT_ANCHOR_VISUAL_COMP_PT != 0:
                right_anchor_visual_comp_mm = (
                    RIGHT_ANCHOR_VISUAL_COMP_PT * FONT_PT_TO_MM * self.current_scale
                )
                right_anchor_width = max(
                    0.0, right_anchor_width - right_anchor_visual_comp_mm
                )

            # AÑADIR MARGEN DE SEGURIDAD AL ANCHO para el Container (10% es suficiente)
            container_width = real_text_width * 1.1
            if alignment == "derecha":
                # Derecha: usar ancho de anclaje completo para evitar recorte de
                # prefijos/sufijos cuando hay diferencias de bearing en el primer glifo.
                container_width = right_anchor_width

            # Windows: Flet puede pintar ligeramente más ancho que la medida de PyMuPDF.
            # Reservar un pequeño margen extra evita que el último dígito quede cortado.
            if platform.system() == "Windows":
                windows_text_padding = max(
                    adjusted_font_size * self.windows_text_width_padding_ratio,
                    self.windows_text_width_padding_min_px,
                )
                container_width += windows_text_padding

            # POSICIONAMIENTO PRECISO (Lógica WYSIWYG sincronizada con PDF)

            # 1. Alineamiento: Calcular desplazamiento a lo largo de la línea base
            align_shift = 0
            if alignment == "centro":
                # Centro: anclar por el ancho del CONTENEDOR (mismo patrón que VT):
                # el contenedor es real_text_width*1.1 (+pad Windows) y TextAlign.CENTER
                # centra dentro; si se ancla por real_text_width a secas, el sobrante
                # del 1.1 empuja el texto un 5% a la derecha de la guía.
                align_shift = -container_width / 2
            elif alignment == "derecha":
                align_shift = -right_anchor_width

            # 2. Rotación: Calcular vectores de dirección (Flet usa grados horaria)
            # 0°=derecha, 90°=abajo, 180°=izquierda, 270°=arriba
            rad = math.radians(rotation_degrees)
            disp_x = math.cos(rad)
            disp_y = math.sin(rad)

            # 3. Aplicar desplazamiento de alineación según los vectores de rotación
            shift_x = align_shift * disp_x
            shift_y = align_shift * disp_y

            # 4. Posición base (top-left del contenedor antes de rotar)
            # Container Top = Guide Y - Baseline Offset (ajustado por rotación después)
            # Nota: offset_x y offset_y ya contienen el ajuste de baseline/bearing según 0,90,180,270
            final_left = text_x_viewer + offset_x + shift_x
            final_top = text_y_viewer + offset_y + shift_y

            debug_container_bg = None
            debug_container_border = None

            text_control = ft.Text(
                value="",  # valor vacío, usamos spans
                spans=text_spans,
                size=adjusted_font_size,
                width=container_width,
                no_wrap=True,
                height=target_height_ratio,
                weight=font_weight,
                italic=font_italic,
                color=number_color,
                overflow=ft.TextOverflow.VISIBLE,
                text_align=(
                    ft.TextAlign.RIGHT
                    if alignment == "derecha"
                    else ft.TextAlign.CENTER
                    if alignment == "centro"
                    else ft.TextAlign.LEFT
                ),
            )

            # Contenedor con rotación aplicada
            # Mantener sin clipping para no recortar sufijos por diferencias mínimas de métricas.
            container_clip = ft.ClipBehavior.NONE

            text_stack_item = ft.Container(
                content=text_control,
                data=num_id,  # IMPORTANTISIMO para optimización de drag & drop
                left=final_left,
                top=final_top,
                padding=0,
                margin=0,
                width=container_width,
                height=adjusted_font_size * target_height_ratio,
                bgcolor=debug_container_bg,
                border=debug_container_border,
                clip_behavior=container_clip,
                # APLICAR ROTACIÓN (coincide con el sistema de grados de la UI)
                rotate=ft.Rotate(angle=rad, alignment=ft.Alignment.TOP_LEFT),
            )

            # Línea AZUL DE VERIFICACIÓN (Baseline)
            # Solo dibujamos para 0° para no saturar, o calculamos el vector...
            # (Lo simplificamos para que siempre sea útil si el usuario lo necesita)
            if rotation_degrees == 0 and self.show_verification_line:
                calculated_baseline_y = final_top + baseline_offset
                verif_line_shape = cv.Line(
                    final_left - 5,
                    calculated_baseline_y,
                    final_left + real_text_width + 5,
                    calculated_baseline_y,
                    paint=ft.Paint(
                        stroke_width=1,
                        color=ft.Colors.with_opacity(0.3, ft.Colors.BLUE),
                        style=ft.PaintingStyle.STROKE,
                    ),
                )
                self.canvas_shapes.append(verif_line_shape)
                self.numeradoras[num_id]["verification_line_control"] = verif_line_shape

            self.text_stack.controls.append(text_stack_item)

        # 2b. Sync bc_data from profile before render (like numeradoras read from text_style_profile)
        # Solo cuando hay rebuild de text_stack o redraw dirigido de barcode(s)
        if self.barcode_profile_manager and (_do_text_rebuild or only_barcode_ids is not None):
            _profiles = self.barcode_profile_manager.get_profiles()
            for _bc in self.barcodes.values():
                _bd = _bc["data"]
                _pn = _bd.get("profile_name")
                if _pn:
                    for _p in _profiles:
                        if _p.name == _pn:
                            _bd["symbology"] = _p.symbology
                            if _is_datamatrix_family(_p.symbology):
                                _bd["bar_width"] = _p.datamatrix_width
                                _bd["bar_height"] = _p.datamatrix_height
                            else:
                                if _p.bar_width is not None:
                                    _bd["bar_width"] = _p.bar_width
                                if _p.bar_height is not None:
                                    _bd["bar_height"] = _p.bar_height
                            _bd["color"] = _p.color
                            _bd["color_cmyk"] = list(_p.color_cmyk) if _p.color_cmyk else None
                            _bd["color_space"] = _p.color_space
                            _bd["color_name"] = _p.color_name
                            _bd["color_tint"] = _p.color_tint
                            _bd["text_color"] = _p.text_color
                            _bd["text_color_cmyk"] = list(_p.text_color_cmyk) if _p.text_color_cmyk else None
                            _bd["text_color_space"] = _p.text_color_space
                            _bd["text_color_name"] = _p.text_color_name
                            _bd["text_color_tint"] = _p.text_color_tint
                            _bd["value_source"] = _p.value_source
                            _bd["mask"] = _p.mask
                            _bd["error_correction"] = _p.error_correction
                            _bd["barcode_font_family"] = _p.barcode_font_family
                            _bd["barcode_font_size"] = _p.barcode_font_size
                            _bd["itf14_quiet_zone_mm"] = _p.itf14_quiet_zone_mm
                            _bd["itf14_bearer_thickness_mm"] = _p.itf14_bearer_thickness_mm
                            _bd["itf14_bearer_sides"] = _p.itf14_bearer_sides
                            _bd["itf14_gtin_type"] = _p.itf14_gtin_type
                            _bd["itf14_printer_type"] = _p.itf14_printer_type
                            _bd["itf14_hri_gap_mm"] = _p.itf14_hri_gap_mm
                            _bd["itf14_hri_position"] = _p.itf14_hri_position
                            _bd["code39_hri_gap_mm"] = _p.code39_hri_gap_mm
                            _bd["code39_hri_position"] = _p.code39_hri_position
                            _bd["code128_hri_gap_mm"] = _p.code128_hri_gap_mm
                            _bd["code128_hri_position"] = _p.code128_hri_position
                            _bd["ean5_hri_gap_mm"] = _p.ean5_hri_gap_mm
                            _bd["datamatrix_width"] = _p.datamatrix_width
                            _bd["datamatrix_height"] = _p.datamatrix_height
                            _bd["datamatrix_format"] = _p.datamatrix_format
                            _bd["datamatrix_hri_gap_mm"] = _p.datamatrix_hri_gap_mm
                            _bd["datamatrix_hri_position"] = _p.datamatrix_hri_position
                            _bd["datamatrix_hri_align"] = getattr(_p, "datamatrix_hri_align", "bottom_center")
                            _bd["datamatrix_hri_line_spacing"] = getattr(_p, "datamatrix_hri_line_spacing", 1.0)
                            _bd["datamatrix_del_open"] = _p.datamatrix_del_open
                            _bd["datamatrix_del_close"] = (
                                _p.datamatrix_del_close
                                if _p.datamatrix_del_close is not None
                                else "|"
                            )
                            _bd["datamatrix_del_close_newline"] = bool(
                                getattr(_p, "datamatrix_del_close_newline", False)
                            )
                            _bd["isbn13_show_title"] = _p.isbn13_show_title
                            _bd["pdf417_height"] = _p.pdf417_height
                            _bd["pdf417_hri_gap_mm"] = getattr(_p, "pdf417_hri_gap_mm", 2.0)
                            _bd["pdf417_hri_position"] = getattr(_p, "pdf417_hri_position", "below")
                            _bd["pdf417_hri_align"] = getattr(_p, "pdf417_hri_align", "bottom_center")
                            _bd["pdf417_hri_line_spacing"] = getattr(_p, "pdf417_hri_line_spacing", 1.0)
                            _bd["pdf417_del_open"] = getattr(_p, "pdf417_del_open", "") or ""
                            _bd["pdf417_del_close"] = getattr(_p, "pdf417_del_close", "|") or "|"
                            _bd["pdf417_del_close_newline"] = bool(
                                getattr(_p, "pdf417_del_close_newline", False)
                            )
                            _bd["qr_hri_gap_mm"] = getattr(_p, "qr_hri_gap_mm", 2.0)
                            _bd["qr_hri_position"] = getattr(_p, "qr_hri_position", "below")
                            _bd["qr_hri_align"] = getattr(_p, "qr_hri_align", "bottom_center")
                            _bd["qr_hri_line_spacing"] = getattr(_p, "qr_hri_line_spacing", 1.0)
                            _bd["qr_del_open"] = getattr(_p, "qr_del_open", "") or ""
                            _bd["qr_del_close"] = getattr(_p, "qr_del_close", "|") or "|"
                            _bd["qr_del_close_newline"] = bool(
                                getattr(_p, "qr_del_close_newline", False)
                            )
                            break
        # 2c. Dibujar barcodes
        if only_barcode_ids is not None:
            for _bid in only_barcode_ids:
                self._remove_barcode_stack_containers(_bid)
        for barcode_id, barcode_data in self.barcodes.items():
            if only_barcode_ids is not None and barcode_id not in only_barcode_ids:
                continue
            bd = barcode_data["data"]
            x_mm = bd["x"]
            y_mm = bd["y"]
            value = bd.get("value", "")
            total_bar_width = float(bd.get("bar_width", 80.0))
            bar_height = float(bd.get("bar_height", 30.0))
            rotation_str = bd.get("rotation", "0°")
            try:
                rotation_degrees = int(str(rotation_str).replace("°", ""))
            except (ValueError, AttributeError):
                rotation_degrees = 0
            bar_color = bd.get("color", "#000000")
            hri_text_color = bd.get("text_color", "#000000")
            symbology = bd.get("symbology", "code128")
            is_qr = symbology == "qr"
            is_pdf417 = symbology == "pdf417"
            is_ean13 = symbology == "ean13"
            is_ean8 = symbology == "ean8"
            is_ean5 = symbology == "ean5"
            is_isbn13 = symbology == "isbn13"
            is_upca = symbology == "upca"
            is_upce = symbology == "upce"
            is_itf14 = symbology == "itf14"
            is_code39 = symbology == "code39"
            is_datamatrix = _is_datamatrix_family(symbology)

            if not value:
                continue

            try:
                if is_qr:
                    n_modules = get_qr_module_count(value)
                    module_size = total_bar_width / n_modules
                    total_content_size = n_modules * module_size
                elif is_pdf417:
                    pdf417_h_target = bd.get("pdf417_height")
                    pdf417_w, _ = get_pdf417_total_size(
                        value,
                        total_bar_width,
                        target_height_mm=pdf417_h_target if pdf417_h_target else None,
                    )
                    total_content_size = pdf417_w
                elif is_ean13:
                    total_content_size = total_bar_width
                elif is_ean8:
                    total_content_size = total_bar_width
                elif is_ean5:
                    total_content_size = total_bar_width
                elif is_isbn13:
                    total_content_size = total_bar_width
                elif is_upca:
                    total_content_size = total_bar_width
                elif is_upce:
                    total_content_size = total_bar_width
                elif is_code39:
                    total_content_size = total_bar_width
                elif is_itf14:
                    printer_type = bd.get("itf14_printer_type", "flexografia")
                    dims = calc_itf14_dimensions(
                        total_bar_width, printer_type, float(bd.get("bar_height", 0))
                    )
                    itf14_qz = dims["quiet_zone_mm"]
                    itf14_bw = dims["bearer_thickness_mm"]
                    bar_height = dims["bar_height"]
                    total_content_size = total_bar_width + 2 * itf14_qz + itf14_bw
                elif is_datamatrix:
                    dm_w = float(bd.get("datamatrix_width", 20.0))
                    dm_h = float(bd.get("datamatrix_height", 20.0))
                    total_content_size = dm_w
                else:
                    total_modules = get_module_count(value)
                    module_width = total_bar_width / total_modules
                    rects = get_barcode_rects(
                        value, module_width=module_width, bar_height=bar_height
                    )
                    total_content_size = total_bar_width
            except Exception:
                continue

            # Transform to viewer coords
            x_viewer, y_viewer_rel = self._transform_page_to_viewer_coords(x_mm, y_mm)
            if is_qr:
                # Sin pre-ajuste de y_viewer: el bloque QR se posiciona por ancla sobre
                # y_viewer_rel en su bloque de render (patrón DataMatrix).
                pass
            elif is_pdf417:
                y_viewer = (
                    y_viewer_rel - (pdf417_h_target * self.current_scale)
                    if pdf417_h_target
                    else y_viewer_rel
                )
            elif is_datamatrix:
                # Sin pre-ajuste de y_viewer: el bloque DM se posiciona por ancla sobre
                # y_viewer_rel en su bloque de render (evita la doble resta con la ancla gy).
                pass
            else:
                y_viewer = y_viewer_rel - (bar_height * self.current_scale)

            is_selected = barcode_id == self.selected_barcode_id
            is_locked = bd.get("locked", False)
            guide_color = (
                COLOR_LOCKED
                if is_locked
                else (COLOR_ACTIVO if is_selected else COLOR_INACTIVO)
            )

            # Position based on alignment
            total_px = total_content_size * self.current_scale
            alignment = bd.get("alignment", "izquierda")
            if alignment == "centro":
                x_start = x_viewer - total_px / 2
            elif alignment == "derecha":
                x_start = x_viewer - total_px
            else:
                x_start = x_viewer

            # Control point circle at reference position
            circle_radius = 6.0
            control_shape = cv.Circle(
                x_viewer,
                y_viewer_rel,
                circle_radius,
                paint=ft.Paint(color=guide_color, style=ft.PaintingStyle.FILL),
            )
            self.canvas_shapes.append(control_shape)
            barcode_data["control_point_shape"] = control_shape

            # Draw content (QR as image, EAN-13 as Container, Code128 as vector rects)
            scale = self.current_scale
            if is_qr:
                # ═══ QR — render as PNG (canvas con HRI, patrón DataMatrix) ═══
                qr_size_mm = total_content_size
                cache_key = "qr_base64"
                if cache_key not in barcode_data:
                    b64, cw, chh, code_h = get_qr_image_b64(
                        value,
                        size_mm=qr_size_mm,
                        font_family=bd.get("barcode_font_family", "OCR-B"),
                        font_size=float(bd.get("barcode_font_size", 9.0)),
                        hri_gap_mm=float(bd.get("qr_hri_gap_mm", 2.0)),
                        hri_position=bd.get("qr_hri_position", "below"),
                        fill_color=bar_color,
                        text_color=hri_text_color,
                        hri_align=bd.get("qr_hri_align", "bottom_center"),
                        hri_line_spacing=float(bd.get("qr_hri_line_spacing", 1.0) or 1.0),
                        del_open=bd.get("qr_del_open", "") or "",
                        del_close=bd.get("qr_del_close", "|") or "|",
                        close_as_newline=bool(bd.get("qr_del_close_newline", False)),
                    )
                    if b64:
                        barcode_data[cache_key] = b64
                        barcode_data["qr_canvas_w_mm"] = cw
                        barcode_data["qr_canvas_h_mm"] = chh
                        barcode_data["qr_code_h_mm"] = code_h
                else:
                    b64 = barcode_data.get(cache_key)
                    cw = barcode_data.get("qr_canvas_w_mm", qr_size_mm)
                    chh = barcode_data.get("qr_canvas_h_mm", qr_size_mm)
                    code_h = barcode_data.get("qr_code_h_mm", qr_size_mm)
                if b64:
                    # Imagen pre-rotada (sin ft.Rotate, patrón DM): la guía se calcula
                    # en el canvas original y se re-mapea al frame rotado.
                    b64_rot = self._prerotated_b64(
                        barcode_data, "qr_base64", b64, rotation_degrees
                    )
                    _gx_mm, _gy_mm = _datamatrix_guide_mm(
                        cw, chh, code_h,
                        alignment, bd.get("qr_hri_position", "below"),
                        code_w_mm=qr_size_mm,
                    )
                    _rot_gx_mm, _rot_gy_mm = _rotate_point_cw(
                        _gx_mm, _gy_mm, cw, chh, rotation_degrees
                    )
                    _vis_w_mm, _vis_h_mm = _rotate_dims_cw(cw, chh, rotation_degrees)
                    qr_px_w = _vis_w_mm * scale
                    qr_px_h = _vis_h_mm * scale
                    qr_left = x_viewer - _rot_gx_mm * scale
                    qr_top = y_viewer_rel - _rot_gy_mm * scale

                    qr_container = barcode_data.get("qr_container")
                    if qr_container and qr_container in self.text_stack.controls:
                        if _do_text_rebuild:
                            qr_container.left = qr_left
                            qr_container.top = qr_top
                            qr_container.width = qr_px_w
                            qr_container.height = qr_px_h
                            qr_container.rotate = None
                        img_ctrl = qr_container.content
                        if _do_text_rebuild:
                            img_ctrl.width = qr_px_w
                            img_ctrl.height = qr_px_h
                        if force or img_ctrl.src != b64_rot:
                            img_ctrl.src = b64_rot
                    else:
                        qr_container = ft.Container(
                            content=ft.Image(
                                src=b64_rot,
                                width=qr_px_w,
                                height=qr_px_h,
                                fit=ft.BoxFit.FILL,
                                gapless_playback=True,
                            ),
                            data=f"qr_{barcode_id}",
                            left=qr_left,
                            top=qr_top,
                            width=qr_px_w,
                            height=qr_px_h,
                        )
                        self.text_stack.controls.append(qr_container)
                        barcode_data["qr_container"] = qr_container
            elif is_pdf417:
                # ═══ PDF417 — render as PNG (canvas con HRI, patrón DataMatrix) ═══
                pdf417_h_target = bd.get("pdf417_height")
                pdf417_w_mm, _ = get_pdf417_total_size(
                    value,
                    total_bar_width,
                    target_height_mm=pdf417_h_target if pdf417_h_target else None,
                )
                pdf417_h_mm = pdf417_h_target if pdf417_h_target else pdf417_w_mm

                cache_key = "pdf417_base64"
                if cache_key not in barcode_data:
                    b64, cw, chh, code_h = self._generate_pdf417_base64(
                        value, bar_color, total_bar_width,
                        target_height=pdf417_h_target,
                        font_family=bd.get("barcode_font_family", "OCR-B"),
                        font_size=float(bd.get("barcode_font_size", 9.0)),
                        hri_gap_mm=float(bd.get("pdf417_hri_gap_mm", 2.0)),
                        hri_position=bd.get("pdf417_hri_position", "below"),
                        text_color=hri_text_color,
                        hri_align=bd.get("pdf417_hri_align", "bottom_center"),
                        hri_line_spacing=float(bd.get("pdf417_hri_line_spacing", 1.0) or 1.0),
                        del_open=bd.get("pdf417_del_open", "") or "",
                        del_close=bd.get("pdf417_del_close", "|") or "|",
                        close_as_newline=bool(bd.get("pdf417_del_close_newline", False)),
                    )
                    if b64:
                        barcode_data[cache_key] = b64
                        barcode_data["pdf417_canvas_w_mm"] = cw
                        barcode_data["pdf417_canvas_h_mm"] = chh
                        barcode_data["pdf417_code_h_mm"] = code_h
                else:
                    b64 = barcode_data.get(cache_key)
                    cw = barcode_data.get("pdf417_canvas_w_mm", pdf417_w_mm)
                    chh = barcode_data.get("pdf417_canvas_h_mm", pdf417_h_mm)
                    code_h = barcode_data.get("pdf417_code_h_mm", pdf417_h_mm)
                if b64:
                    b64_rot = self._prerotated_b64(
                        barcode_data, "pdf417_base64", b64, rotation_degrees
                    )
                    # Ancla = punto de la GUÍA sobre el BORDE DEL CÓDIGO (tamaño
                    # fijo; el lienzo crece con el texto): x por alineación, y =
                    # fondo del código. Se re-mapea al frame rotado y el contenedor
                    # se posiciona sin ft.Rotate.
                    _gx_mm, _gy_mm = _datamatrix_guide_mm(
                        cw, chh, code_h,
                        alignment, bd.get("pdf417_hri_position", "below"),
                        code_w_mm=pdf417_w_mm,
                    )
                    _rot_ax_mm, _rot_ay_mm = _rotate_point_cw(
                        _gx_mm, _gy_mm, cw, chh, rotation_degrees
                    )
                    _vis_w_mm, _vis_h_mm = _rotate_dims_cw(cw, chh, rotation_degrees)
                    _pdf417_px_w = _vis_w_mm * scale
                    _pdf417_px_h = _vis_h_mm * scale
                    _pdf417_left = x_viewer - _rot_ax_mm * scale
                    _pdf417_top = y_viewer_rel - _rot_ay_mm * scale

                    pdf417_container = barcode_data.get("pdf417_container")
                    if (
                        pdf417_container
                        and pdf417_container in self.text_stack.controls
                    ):
                        if _do_text_rebuild:
                            pdf417_container.left = _pdf417_left
                            pdf417_container.top = _pdf417_top
                            pdf417_container.width = _pdf417_px_w
                            pdf417_container.height = _pdf417_px_h
                            pdf417_container.rotate = None
                        img_ctrl = pdf417_container.content
                        if _do_text_rebuild:
                            img_ctrl.width = _pdf417_px_w
                            img_ctrl.height = _pdf417_px_h
                        if force or img_ctrl.src != b64_rot:
                            img_ctrl.src = b64_rot
                    else:
                        pdf417_container = ft.Container(
                            content=ft.Image(
                                src=b64_rot,
                                width=_pdf417_px_w,
                                height=_pdf417_px_h,
                                fit=ft.BoxFit.FILL,
                                gapless_playback=True,
                            ),
                            data=f"pdf417_{barcode_id}",
                            left=_pdf417_left,
                            top=_pdf417_top,
                            width=_pdf417_px_w,
                            height=_pdf417_px_h,
                        )
                        self.text_stack.controls.append(pdf417_container)
                        barcode_data["pdf417_container"] = pdf417_container
            elif is_datamatrix:
                dm_w_mm = float(bd.get("datamatrix_width", 20.0))
                dm_h_mm = float(bd.get("datamatrix_height", 20.0))

                cache_key = "datamatrix_base64"
                if cache_key not in barcode_data:
                    result = get_datamatrix_image_b64(
                        value,
                        width_mm=dm_w_mm,
                        height_mm=dm_h_mm,
                        font_family=bd.get("barcode_font_family", "OCR-B"),
                        font_size=float(bd.get("barcode_font_size", 9.0)),
                        hri_gap_mm=float(bd.get("datamatrix_hri_gap_mm", 2.0)),
                        hri_position=bd.get("datamatrix_hri_position", "below"),
                        fill_color=bar_color,
                        text_color=bd.get("text_color", "#000000"),
                        formato=bd.get("datamatrix_format", ""),
                        del_open=bd.get("datamatrix_del_open", ""),
                        del_close=bd.get("datamatrix_del_close", "|"),
                        hri_align=bd.get("datamatrix_hri_align", "bottom_center"),
                        hri_line_spacing=float(bd.get("datamatrix_hri_line_spacing", 1.0) or 1.0),
                        close_as_newline=bool(bd.get("datamatrix_del_close_newline", False)),
                        symbology=symbology,
                    )
                    b64, canvas_w_mm, canvas_h_mm, code_h_mm = result
                    if b64:
                        barcode_data[cache_key] = b64
                        barcode_data["dm_canvas_w_mm"] = canvas_w_mm
                        barcode_data["dm_canvas_h_mm"] = canvas_h_mm
                        barcode_data["dm_code_h_mm"] = code_h_mm
                else:
                    b64 = barcode_data.get(cache_key)
                    canvas_w_mm = barcode_data.get("dm_canvas_w_mm", dm_w_mm)
                    canvas_h_mm = barcode_data.get("dm_canvas_h_mm", dm_h_mm)
                    code_h_mm = barcode_data.get("dm_code_h_mm", dm_h_mm)

                if b64:
                    # Imagen pre-rotada (sin ft.Rotate, patrón QR): la guía se calcula
                    # en el canvas original y se re-mapea al frame rotado (misma
                    # matemática que el PDF). El contenedor se posiciona con su ancla.
                    b64_rot = self._prerotated_b64(
                        barcode_data, "datamatrix_base64", b64, rotation_degrees
                    )
                    _gx_mm, _gy_mm = _datamatrix_guide_mm(
                        canvas_w_mm, canvas_h_mm, code_h_mm,
                        alignment, bd.get("datamatrix_hri_position", "below"),
                        code_w_mm=dm_w_mm,
                    )
                    _rot_gx_mm, _rot_gy_mm = _rotate_point_cw(
                        _gx_mm, _gy_mm, canvas_w_mm, canvas_h_mm, rotation_degrees
                    )
                    _vis_w_mm, _vis_h_mm = _rotate_dims_cw(
                        canvas_w_mm, canvas_h_mm, rotation_degrees
                    )
                    dm_px_w = _vis_w_mm * scale
                    dm_px_h = _vis_h_mm * scale
                    dm_left = x_viewer - _rot_gx_mm * scale
                    dm_top = y_viewer_rel - _rot_gy_mm * scale

                    dm_container = barcode_data.get("datamatrix_container")
                    if dm_container and dm_container in self.text_stack.controls:
                        if _do_text_rebuild:
                            dm_container.left = dm_left
                            dm_container.top = dm_top
                            dm_container.width = dm_px_w
                            dm_container.height = dm_px_h
                            dm_container.rotate = None
                        img_ctrl = dm_container.content
                        if _do_text_rebuild:
                            img_ctrl.width = dm_px_w
                            img_ctrl.height = dm_px_h
                        if force or img_ctrl.src != b64_rot:
                            img_ctrl.src = b64_rot
                    else:
                        dm_container = ft.Container(
                            content=ft.Image(
                                src=b64_rot,
                                width=dm_px_w,
                                height=dm_px_h,
                                fit=ft.BoxFit.FILL,
                                gapless_playback=True,
                            ),
                            data=f"datamatrix_{barcode_id}",
                            left=dm_left,
                            top=dm_top,
                            width=dm_px_w,
                            height=dm_px_h,
                        )
                        self.text_stack.controls.append(dm_container)
                        barcode_data["datamatrix_container"] = dm_container
            elif is_ean13:
                # ═══ EAN-13 — Canvas in pixels (test script convention) ═══
                # All canvas coordinates in dp (logical pixels) at current scale,
                # matching test_ean13_rotation.py which works in pixels.
                ds_pt = float(bd.get("barcode_font_size", 13.0))
                ds_mm = ds_pt * FONT_PT_TO_MM
                font_family = bd.get("barcode_font_family", "OCR-B")
                module_width_mm = total_bar_width / get_ean13_module_count()
                elements, c_eff_mm, bar_offset_mm, cw_mm, ds_eff_mm = ean_hri_layout(
                    "ean13", "0" * 13, module_width_mm, ds_mm, font_family
                )
                guard_ext_mm = max(1.5, ds_eff_mm * (0.25 + get_ean13_font_ascender_ratio(font_family)))
                ch_mm = guard_ext_mm + bar_height

                s = scale
                cw_px = cw_mm * s
                ch_px = ch_mm * s

                valid, err_msg = validate_ean13(value)
                if not valid:
                    error_shapes = [
                        cv.Text(
                            2,
                            ch_px - 2,
                            f"EAN-13: {err_msg}",
                            style=ft.TextStyle(size=12, color=ERROR_COLOR),
                        ),
                    ]
                    content_canvas = cv.Canvas(error_shapes, width=cw_px, height=ch_px)
                else:
                    pattern, fullcode = encode_ean13(value)
                    elements, c_eff_mm, bar_offset_mm, cw_mm, ds_eff_mm = ean_hri_layout(
                        "ean13", fullcode, module_width_mm, ds_mm, font_family
                    )
                    module_width_px = module_width_mm * s
                    guard_ext_px = guard_ext_mm * s
                    ds_px = ds_eff_mm * s
                    c_eff_px = c_eff_mm * s
                    bar_offset_px = bar_offset_mm * s

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
                        rh_px = bar_height * s + (guard_ext_px if is_guard else 0)
                        bx_px = bar_offset_px + x_px
                        by_px = 0
                        shapes.append(
                            cv.Rect(
                                bx_px,
                                by_px,
                                w_px,
                                rh_px,
                                paint=ft.Paint(
                                    color=bar_color, style=ft.PaintingStyle.FILL
                                ),
                            )
                        )
                        x_px += w_px
                        i = j

                    positions = [(digit, cx_mm * s) for digit, cx_mm in elements]

                    ts = ft.TextStyle(size=ds_px, color=hri_text_color)
                    if font_family:
                        ts.font_family = font_family
                    for i, (digit_char, cx_px) in enumerate(positions):
                        dx_px = cx_px - c_eff_px / 2
                        shapes.append(
                            cv.Text(
                                dx_px,
                                ch_px
                                + ds_px * get_ean13_font_descender_ratio(font_family),
                                digit_char,
                                style=ts,
                                alignment=ft.Alignment.BOTTOM_LEFT,
                            )
                        )

                    content_canvas = cv.Canvas(shapes, width=cw_px, height=ch_px)

                ean13_y_viewer = y_viewer_rel - ch_px

                if alignment == "centro":
                    ean13_left = x_viewer - cw_px / 2
                    rot_align = ft.Alignment(0, 1)
                elif alignment == "derecha":
                    ean13_left = x_viewer - cw_px
                    rot_align = ft.Alignment(1, 1)
                else:
                    ean13_left = x_viewer
                    rot_align = ft.Alignment(-1, 1)

                rad = math.radians(rotation_degrees)

                ean13_container = barcode_data.get("ean13_container")
                if ean13_container and ean13_container in self.text_stack.controls:
                    if _do_text_rebuild:
                        ean13_container.left = ean13_left
                        ean13_container.top = ean13_y_viewer
                        ean13_container.width = None
                        ean13_container.height = None
                        ean13_container.rotate = (
                            ft.Rotate(angle=rad, alignment=rot_align)
                            if rotation_degrees != 0
                            else None
                        )
                        ean13_container.content = content_canvas
                else:
                    ean13_container = ft.Container(
                        content=content_canvas,
                        data=f"ean13_{barcode_id}",
                        left=ean13_left,
                        top=ean13_y_viewer,
                        rotate=(
                            ft.Rotate(angle=rad, alignment=rot_align)
                            if rotation_degrees != 0
                            else None
                        ),
                    )
                    self.text_stack.controls.append(ean13_container)
                    barcode_data["ean13_container"] = ean13_container
            elif is_isbn13:
                # ═══ ISBN-13 — EAN-13 bars + smaller "ISBN" text above ═══
                ds_pt = float(bd.get("barcode_font_size", 13.0))
                ds_mm = ds_pt * FONT_PT_TO_MM
                font_family = bd.get("barcode_font_family", "OCR-B")
                show_title = bd.get("isbn13_show_title", "Sí") == "Sí"

                module_width_mm = total_bar_width / get_ean13_module_count()
                elements, c_eff_mm, bar_offset_mm, cw_mm, ds_eff_mm = ean_hri_layout(
                    "isbn13", "0" * 13, module_width_mm, ds_mm, font_family
                )
                # Label y hueco siguen al cuerpo CRUDO (no al ds_eff capado por las barras),
                # sin suelo: debe bajar y subir con el cuerpo
                isbn_ds_pt = max(1.0, ds_pt - ISBN_SIZE_OFFSET)
                isbn_ds_mm = isbn_ds_pt * FONT_PT_TO_MM
                isbn_gap_mm = ds_pt * FONT_PT_TO_MM * 0.25
                guard_ext_mm = max(1.5, ds_eff_mm * (0.25 + get_ean13_font_ascender_ratio(font_family)))
                _isbn_line_ratio = get_ean13_font_ascender_ratio(
                    font_family
                ) + get_ean13_font_descender_ratio(font_family)
                _isbn_label_h_mm = isbn_ds_mm * _isbn_line_ratio
                if show_title:
                    ch_mm = _isbn_label_h_mm + isbn_gap_mm + guard_ext_mm + bar_height
                else:
                    ch_mm = guard_ext_mm + bar_height

                s = scale
                cw_px = cw_mm * s
                ch_px = ch_mm * s

                valid, err_msg = validate_isbn13(value)
                if not valid:
                    error_shapes = [
                        cv.Text(
                            2,
                            ch_px - 2,
                            f"ISBN-13: {err_msg}",
                            style=ft.TextStyle(size=12, color=ERROR_COLOR),
                        ),
                    ]
                    content_canvas = cv.Canvas(error_shapes, width=cw_px, height=ch_px)
                else:
                    pattern, fullcode = encode_ean13(value)
                    elements, c_eff_mm, bar_offset_mm, cw_mm, ds_eff_mm = ean_hri_layout(
                        "isbn13", fullcode, module_width_mm, ds_mm, font_family
                    )
                    module_width_px = module_width_mm * s
                    guard_ext_px = guard_ext_mm * s
                    ds_px = ds_eff_mm * s
                    isbn_ds_px = isbn_ds_mm * s
                    isbn_gap_px = isbn_gap_mm * s
                    _isbn_label_h_px = _isbn_label_h_mm * s
                    c_eff_px = c_eff_mm * s
                    bar_offset_px = bar_offset_mm * s
                    bars_top_px = (_isbn_label_h_px + isbn_gap_px) if show_title else 0

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
                        rh_px = bar_height * s + (guard_ext_px if is_guard else 0)
                        bx_px = bar_offset_px + x_px
                        shapes.append(
                            cv.Rect(
                                bx_px,
                                bars_top_px,
                                w_px,
                                rh_px,
                                paint=ft.Paint(
                                    color=bar_color, style=ft.PaintingStyle.FILL
                                ),
                            )
                        )
                        x_px += w_px
                        i = j

                    positions = [(digit, cx_mm * s) for digit, cx_mm in elements]

                    if show_title:
                        # ISBN text above bars (compact, centered)
                        isbn_label = _format_isbn13(fullcode)
                        isbn_ts = ft.TextStyle(
                            size=isbn_ds_px,
                            color=bar_color,
                            font_family=font_family or None,
                        )
                        isbn_cx = bar_offset_px + total_bar_width * s / 2
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
                    ts = ft.TextStyle(size=ds_px, color=hri_text_color)
                    if font_family:
                        ts.font_family = font_family
                    for i, (digit_char, cx_px) in enumerate(positions):
                        dx_px = cx_px - c_eff_px / 2
                        shapes.append(
                            cv.Text(
                                dx_px,
                                ch_px
                                + ds_px * get_ean13_font_descender_ratio(font_family),
                                digit_char,
                                style=ts,
                                alignment=ft.Alignment.BOTTOM_LEFT,
                            )
                        )

                    content_canvas = cv.Canvas(shapes, width=cw_px, height=ch_px)

                isbn13_y_viewer = y_viewer_rel - ch_px

                if alignment == "centro":
                    isbn13_left = x_viewer - cw_px / 2
                    rot_align = ft.Alignment(0, 1)
                elif alignment == "derecha":
                    isbn13_left = x_viewer - cw_px
                    rot_align = ft.Alignment(1, 1)
                else:
                    isbn13_left = x_viewer
                    rot_align = ft.Alignment(-1, 1)

                rad = math.radians(rotation_degrees)

                isbn13_container = barcode_data.get("isbn13_container")
                if isbn13_container and isbn13_container in self.text_stack.controls:
                    if _do_text_rebuild:
                        isbn13_container.left = isbn13_left
                        isbn13_container.top = isbn13_y_viewer
                        isbn13_container.width = None
                        isbn13_container.height = None
                        isbn13_container.rotate = (
                            ft.Rotate(angle=rad, alignment=rot_align)
                            if rotation_degrees != 0
                            else None
                        )
                        isbn13_container.content = content_canvas
                else:
                    isbn13_container = ft.Container(
                        content=content_canvas,
                        data=f"isbn13_{barcode_id}",
                        left=isbn13_left,
                        top=isbn13_y_viewer,
                        rotate=(
                            ft.Rotate(angle=rad, alignment=rot_align)
                            if rotation_degrees != 0
                            else None
                        ),
                    )
                    self.text_stack.controls.append(isbn13_container)
                    barcode_data["isbn13_container"] = isbn13_container
            elif is_upca:
                # ═══ UPC-A — EAN-13 bars + 1+5+5+1 digit layout ═══
                ds_pt = float(bd.get("barcode_font_size", 13.0))
                ds_mm = ds_pt * FONT_PT_TO_MM
                font_family = bd.get("barcode_font_family", "OCR-B")
                module_width_mm = total_bar_width / get_ean13_module_count()
                elements, c_eff_mm, bar_offset_mm, cw_mm, ds_eff_mm = ean_hri_layout(
                    "upca", "0" * 12, module_width_mm, ds_mm, font_family
                )
                guard_ext_mm = max(1.5, ds_eff_mm * (0.25 + get_ean13_font_ascender_ratio(font_family)))
                ch_mm = guard_ext_mm + bar_height

                s = scale
                cw_px = cw_mm * s
                ch_px = ch_mm * s

                valid, err_msg = validate_upca(value)
                if not valid:
                    error_shapes = [
                        cv.Text(
                            2,
                            ch_px - 2,
                            f"UPC-A: {err_msg}",
                            style=ft.TextStyle(size=12, color=ERROR_COLOR),
                        ),
                    ]
                    content_canvas = cv.Canvas(error_shapes, width=cw_px, height=ch_px)
                else:
                    pattern, fullcode = encode_upca(value)
                    elements, c_eff_mm, bar_offset_mm, cw_mm, ds_eff_mm = ean_hri_layout(
                        "upca", fullcode, module_width_mm, ds_mm, font_family
                    )
                    module_width_px = module_width_mm * s
                    guard_ext_px = guard_ext_mm * s
                    ds_px = ds_eff_mm * s
                    c_eff_px = c_eff_mm * s
                    bar_offset_px = bar_offset_mm * s

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
                        rh_px = bar_height * s + (guard_ext_px if is_guard else 0)
                        bx_px = bar_offset_px + x_px
                        by_px = 0
                        shapes.append(
                            cv.Rect(
                                bx_px,
                                by_px,
                                w_px,
                                rh_px,
                                paint=ft.Paint(
                                    color=bar_color, style=ft.PaintingStyle.FILL
                                ),
                            )
                        )
                        x_px += w_px
                        i = j

                    positions = [(digit, cx_mm * s) for digit, cx_mm in elements]

                    ts = ft.TextStyle(size=ds_px, color=hri_text_color)
                    if font_family:
                        ts.font_family = font_family
                    for i, (digit_char, cx_px) in enumerate(positions):
                        dx_px = cx_px - c_eff_px / 2
                        shapes.append(
                            cv.Text(
                                dx_px,
                                ch_px
                                + ds_px * get_ean13_font_descender_ratio(font_family),
                                digit_char,
                                style=ts,
                                alignment=ft.Alignment.BOTTOM_LEFT,
                            )
                        )

                    content_canvas = cv.Canvas(shapes, width=cw_px, height=ch_px)

                upca_y_viewer = y_viewer_rel - ch_px

                if alignment == "centro":
                    upca_left = x_viewer - cw_px / 2
                    rot_align = ft.Alignment(0, 1)
                elif alignment == "derecha":
                    upca_left = x_viewer - cw_px
                    rot_align = ft.Alignment(1, 1)
                else:
                    upca_left = x_viewer
                    rot_align = ft.Alignment(-1, 1)

                rad = math.radians(rotation_degrees)

                upca_container = barcode_data.get("upca_container")
                if upca_container and upca_container in self.text_stack.controls:
                    if _do_text_rebuild:
                        upca_container.left = upca_left
                        upca_container.top = upca_y_viewer
                        upca_container.width = None
                        upca_container.height = None
                        upca_container.rotate = (
                            ft.Rotate(angle=rad, alignment=rot_align)
                            if rotation_degrees != 0
                            else None
                        )
                        upca_container.content = content_canvas
                else:
                    upca_container = ft.Container(
                        content=content_canvas,
                        data=f"upca_{barcode_id}",
                        left=upca_left,
                        top=upca_y_viewer,
                        rotate=(
                            ft.Rotate(angle=rad, alignment=rot_align)
                            if rotation_degrees != 0
                            else None
                        ),
                    )
                    self.text_stack.controls.append(upca_container)
                    barcode_data["upca_container"] = upca_container
            elif is_upce:
                # ═══ UPC-E — EAN-13 bars (expanded via zero-suppression), no center guard, 6 digits ═══
                ds_pt = float(bd.get("barcode_font_size", 13.0))
                ds_mm = ds_pt * FONT_PT_TO_MM
                font_family = bd.get("barcode_font_family", "OCR-B")
                module_width_mm = total_bar_width / get_upce_module_count()
                elements, c_eff_mm, bar_offset_mm, cw_mm, ds_eff_mm = ean_hri_layout(
                    "upce", value.zfill(6), module_width_mm, ds_mm, font_family
                )
                guard_ext_mm = max(1.5, ds_eff_mm * (0.25 + get_ean13_font_ascender_ratio(font_family)))
                ch_mm = guard_ext_mm + bar_height

                s = scale
                cw_px = cw_mm * s
                ch_px = ch_mm * s

                valid, err_msg = validate_upce(value)
                if not valid:
                    error_shapes = [
                        cv.Text(
                            2,
                            ch_px - 2,
                            f"UPC-E: {err_msg}",
                            style=ft.TextStyle(size=12, color=ERROR_COLOR),
                        ),
                    ]
                    content_canvas = cv.Canvas(error_shapes, width=cw_px, height=ch_px)
                else:
                    pattern, _ = encode_upce(value)
                    elements, c_eff_mm, bar_offset_mm, cw_mm, ds_eff_mm = ean_hri_layout(
                        "upce", value.zfill(6), module_width_mm, ds_mm, font_family
                    )
                    module_width_px = module_width_mm * s
                    guard_ext_px = guard_ext_mm * s
                    ds_px = ds_eff_mm * s
                    c_eff_px = c_eff_mm * s
                    bar_offset_px = bar_offset_mm * s

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
                        rh_px = bar_height * s + (guard_ext_px if is_guard else 0)
                        bx_px = bar_offset_px + x_px
                        by_px = 0
                        shapes.append(
                            cv.Rect(
                                bx_px,
                                by_px,
                                w_px,
                                rh_px,
                                paint=ft.Paint(
                                    color=bar_color, style=ft.PaintingStyle.FILL
                                ),
                            )
                        )
                        x_px += w_px
                        i = j

                    ts = ft.TextStyle(size=ds_px, color=hri_text_color)
                    if font_family:
                        ts.font_family = font_family

                    for digit_char, cx_mm in elements:
                        dx_px = cx_mm * s - c_eff_px / 2
                        shapes.append(
                            cv.Text(
                                dx_px,
                                ch_px
                                + ds_px * get_ean13_font_descender_ratio(font_family),
                                digit_char,
                                style=ts,
                                alignment=ft.Alignment.BOTTOM_LEFT,
                            )
                        )

                    content_canvas = cv.Canvas(shapes, width=cw_px, height=ch_px)

                upce_y_viewer = y_viewer_rel - ch_px

                if alignment == "centro":
                    upce_left = x_viewer - cw_px / 2
                    rot_align = ft.Alignment(0, 1)
                elif alignment == "derecha":
                    upce_left = x_viewer - cw_px
                    rot_align = ft.Alignment(1, 1)
                else:
                    upce_left = x_viewer
                    rot_align = ft.Alignment(-1, 1)

                rad = math.radians(rotation_degrees)

                upce_container = barcode_data.get("upce_container")
                if upce_container and upce_container in self.text_stack.controls:
                    if _do_text_rebuild:
                        upce_container.left = upce_left
                        upce_container.top = upce_y_viewer
                        upce_container.width = None
                        upce_container.height = None
                        upce_container.rotate = (
                            ft.Rotate(angle=rad, alignment=rot_align)
                            if rotation_degrees != 0
                            else None
                        )
                        upce_container.content = content_canvas
                else:
                    upce_container = ft.Container(
                        content=content_canvas,
                        data=f"upce_{barcode_id}",
                        left=upce_left,
                        top=upce_y_viewer,
                        rotate=(
                            ft.Rotate(angle=rad, alignment=rot_align)
                            if rotation_degrees != 0
                            else None
                        ),
                    )
                    self.text_stack.controls.append(upce_container)
                    barcode_data["upce_container"] = upce_container
            elif is_ean8:
                # ═══ EAN-8 — all digits encoded in bars, no outside digit ═══
                ds_pt = float(bd.get("barcode_font_size", 13.0))
                ds_mm = ds_pt * FONT_PT_TO_MM
                font_family = bd.get("barcode_font_family", "OCR-B")
                module_width_mm = total_bar_width / get_ean8_module_count()
                elements, c_eff_mm, bar_offset_mm, cw_mm, ds_eff_mm = ean_hri_layout(
                    "ean8", "0" * 8, module_width_mm, ds_mm, font_family
                )
                guard_ext_mm = max(1.5, ds_eff_mm * (0.25 + get_ean13_font_ascender_ratio(font_family)))
                ch_mm = guard_ext_mm + bar_height

                s = scale
                cw_px = cw_mm * s
                ch_px = ch_mm * s

                valid, err_msg = validate_ean8(value)
                if not valid:
                    error_shapes = [
                        cv.Text(
                            2,
                            ch_px - 2,
                            f"EAN-8: {err_msg}",
                            style=ft.TextStyle(size=12, color=ERROR_COLOR),
                        ),
                    ]
                    content_canvas = cv.Canvas(error_shapes, width=cw_px, height=ch_px)
                else:
                    pattern, fullcode = encode_ean8(value)
                    elements, c_eff_mm, bar_offset_mm, cw_mm, ds_eff_mm = ean_hri_layout(
                        "ean8", fullcode, module_width_mm, ds_mm, font_family
                    )
                    module_width_px = module_width_mm * s
                    guard_ext_px = guard_ext_mm * s
                    ds_px = ds_eff_mm * s
                    c_eff_px = c_eff_mm * s

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
                        rh_px = bar_height * s + (guard_ext_px if is_guard else 0)
                        bx_px = x_px
                        by_px = 0
                        shapes.append(
                            cv.Rect(
                                bx_px,
                                by_px,
                                w_px,
                                rh_px,
                                paint=ft.Paint(
                                    color=bar_color, style=ft.PaintingStyle.FILL
                                ),
                            )
                        )
                        x_px += w_px
                        i = j

                    positions = [(digit, cx_mm * s) for digit, cx_mm in elements]

                    ts = ft.TextStyle(size=ds_px, color=hri_text_color)
                    if font_family:
                        ts.font_family = font_family
                    for i, (digit_char, cx_px) in enumerate(positions):
                        dx_px = cx_px - c_eff_px / 2
                        shapes.append(
                            cv.Text(
                                dx_px,
                                ch_px
                                + ds_px * get_ean13_font_descender_ratio(font_family),
                                digit_char,
                                style=ts,
                                alignment=ft.Alignment.BOTTOM_LEFT,
                            )
                        )

                    content_canvas = cv.Canvas(shapes, width=cw_px, height=ch_px)

                ean8_y_viewer = y_viewer_rel - ch_px

                if alignment == "centro":
                    ean8_left = x_viewer - cw_px / 2
                    rot_align = ft.Alignment(0, 1)
                elif alignment == "derecha":
                    ean8_left = x_viewer - cw_px
                    rot_align = ft.Alignment(1, 1)
                else:
                    ean8_left = x_viewer
                    rot_align = ft.Alignment(-1, 1)

                rad = math.radians(rotation_degrees)

                ean8_container = barcode_data.get("ean8_container")
                if ean8_container and ean8_container in self.text_stack.controls:
                    if _do_text_rebuild:
                        ean8_container.left = ean8_left
                        ean8_container.top = ean8_y_viewer
                        ean8_container.width = None
                        ean8_container.height = None
                        ean8_container.rotate = (
                            ft.Rotate(angle=rad, alignment=rot_align)
                            if rotation_degrees != 0
                            else None
                        )
                        ean8_container.content = content_canvas
                else:
                    ean8_container = ft.Container(
                        content=content_canvas,
                        data=f"ean8_{barcode_id}",
                        left=ean8_left,
                        top=ean8_y_viewer,
                        rotate=(
                            ft.Rotate(angle=rad, alignment=rot_align)
                            if rotation_degrees != 0
                            else None
                        ),
                    )
                    self.text_stack.controls.append(ean8_container)
                    barcode_data["ean8_container"] = ean8_container
            elif is_ean5:
                # ═══ EAN-5 — digits ABOVE bars, no guard extensions ═══
                ds_pt = float(bd.get("barcode_font_size", 13.0))
                ds_mm = ds_pt * FONT_PT_TO_MM
                gap_mm = float(bd.get("ean5_hri_gap_mm", 2.0))
                font_family = bd.get("barcode_font_family", "OCR-B")
                from utils.barcode_module import (
                    resolve_font_path,
                    get_font_text_metrics,
                )

                _asc, _desc_neg, _total = get_font_text_metrics(
                    resolve_font_path(font_family)
                )
                char_w_mm = ds_mm * get_digit_advance_em(font_family)

                module_width_mm = total_bar_width / get_ean5_module_count()
                cw_mm = 47 * module_width_mm
                ch_mm = _asc * ds_mm + gap_mm + bar_height

                s = scale
                cw_px = cw_mm * s
                ch_px = ch_mm * s

                valid, err_msg = validate_ean5(value)
                if not valid:
                    error_shapes = [
                        cv.Text(
                            2,
                            ch_px - 2,
                            f"EAN-5: {err_msg}",
                            style=ft.TextStyle(size=12, color=ERROR_COLOR),
                        ),
                    ]
                    content_canvas = cv.Canvas(error_shapes, width=cw_px, height=ch_px)
                else:
                    pattern, fullcode = encode_ean5(value)
                    module_width_px = module_width_mm * s
                    ds_px = ds_mm * s
                    char_w_px = char_w_mm * s
                    baseline_px = _asc * ds_px
                    bar_top_px = baseline_px + gap_mm * s

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
                                bar_height * s,
                                paint=ft.Paint(
                                    color=bar_color, style=ft.PaintingStyle.FILL
                                ),
                            )
                        )
                        x_px += w_px
                        i = j

                    positions = []
                    for idx in range(5):
                        cm = (idx + 0.5) * (47 / 5.0)
                        positions.append((fullcode[idx], cm * module_width_px))

                    ts = ft.TextStyle(size=ds_px, color=hri_text_color)
                    if font_family:
                        ts.font_family = font_family
                    if ds_px > 0:
                        for digit_char, cx_px in positions:
                            dx_px = cx_px - char_w_px / 2
                            shapes.append(
                                cv.Text(
                                    dx_px,
                                    0,
                                    digit_char,
                                    style=ts,
                                    alignment=ft.Alignment.TOP_LEFT,
                                )
                            )

                    content_canvas = cv.Canvas(shapes, width=cw_px, height=ch_px)

                ean5_y_viewer = y_viewer_rel - ch_px

                if alignment == "centro":
                    ean5_left = x_viewer - cw_px / 2
                    rot_align = ft.Alignment(0, 1)
                elif alignment == "derecha":
                    ean5_left = x_viewer - cw_px
                    rot_align = ft.Alignment(1, 1)
                else:
                    ean5_left = x_viewer
                    rot_align = ft.Alignment(-1, 1)

                rad = math.radians(rotation_degrees)

                ean5_container = barcode_data.get("ean5_container")
                if ean5_container and ean5_container in self.text_stack.controls:
                    if _do_text_rebuild:
                        ean5_container.left = ean5_left
                        ean5_container.top = ean5_y_viewer
                        ean5_container.width = None
                        ean5_container.height = None
                        ean5_container.rotate = (
                            ft.Rotate(angle=rad, alignment=rot_align)
                            if rotation_degrees != 0
                            else None
                        )
                        ean5_container.content = content_canvas
                else:
                    ean5_container = ft.Container(
                        content=content_canvas,
                        data=f"ean5_{barcode_id}",
                        left=ean5_left,
                        top=ean5_y_viewer,
                        rotate=(
                            ft.Rotate(angle=rad, alignment=rot_align)
                            if rotation_degrees != 0
                            else None
                        ),
                    )
                    self.text_stack.controls.append(ean5_container)
                    barcode_data["ean5_container"] = ean5_container
            elif is_code39:
                # ═══ Code 39 — bars via _pattern_to_rects + HRI text below ═══
                from utils.barcode_module import (
                    encode_code39,
                    _pattern_to_rects,
                    resolve_font_path,
                    get_font_cap_height_ratio,
                    measure_text,
                )

                try:
                    pattern, fullcode = encode_code39(value)
                except Exception:
                    pattern, fullcode = "", value
                if not pattern:
                    continue

                module_width_mm = total_bar_width / len(pattern)

                rects = _pattern_to_rects(pattern, module_width_mm, bar_height)

                ds_pt = float(bd.get("barcode_font_size", 13.0))
                ds_mm = ds_pt * FONT_PT_TO_MM
                code39_gap_mm = float(bd.get("code39_hri_gap_mm", 2.0))
                code39_position = bd.get("code39_hri_position", "below")
                font_family = bd.get("barcode_font_family", "OCR-B")

                s = scale
                cw_px = total_bar_width * s
                ds_px = ds_mm * s

                if code39_position == "below":
                    _cap = get_font_cap_height_ratio(resolve_font_path(font_family))
                    _desc_abs = get_ean13_font_descender_ratio(font_family)
                    ch_mm = bar_height + code39_gap_mm + _cap * ds_mm
                    ch_px = ch_mm * s

                    shapes = []
                    for rx, ry, rw, rh in rects:
                        shapes.append(
                            cv.Rect(
                                rx * s,
                                ry * s,
                                rw * s,
                                rh * s,
                                paint=ft.Paint(
                                    color=bar_color, style=ft.PaintingStyle.FILL
                                ),
                            )
                        )

                    hri_w_px = measure_text(
                        fullcode, resolve_font_path(font_family), ds_px
                    )
                    hri_start_x = cw_px / 2 - hri_w_px / 2
                    ts = ft.TextStyle(size=ds_px, color=hri_text_color)
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

                    _asc, _, _ = get_font_text_metrics(resolve_font_path(font_family))
                    ch_mm = _asc * ds_mm + code39_gap_mm + bar_height
                    ch_px = ch_mm * s
                    bar_top_px = _asc * ds_px + code39_gap_mm * s

                    shapes = []
                    for rx, ry, rw, rh in rects:
                        shapes.append(
                            cv.Rect(
                                rx * s,
                                bar_top_px,
                                rw * s,
                                rh * s,
                                paint=ft.Paint(
                                    color=bar_color, style=ft.PaintingStyle.FILL
                                ),
                            )
                        )

                    hri_w_px = measure_text(
                        fullcode, resolve_font_path(font_family), ds_px
                    )
                    hri_start_x = cw_px / 2 - hri_w_px / 2
                    ts = ft.TextStyle(size=ds_px, color=hri_text_color)
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

                content_widget = cv.Canvas(shapes, width=cw_px, height=ch_px)
                code39_y_viewer = y_viewer_rel - ch_px

                if alignment == "centro":
                    code39_left = x_viewer - cw_px / 2
                    rot_align = ft.Alignment(0, 1)
                elif alignment == "derecha":
                    code39_left = x_viewer - cw_px
                    rot_align = ft.Alignment(1, 1)
                else:
                    code39_left = x_viewer
                    rot_align = ft.Alignment(-1, 1)

                rad = math.radians(rotation_degrees)
                code39_container = barcode_data.get("code39_container")
                if code39_container and code39_container in self.text_stack.controls:
                    if _do_text_rebuild:
                        code39_container.left = code39_left
                        code39_container.top = code39_y_viewer
                        code39_container.width = None
                        code39_container.height = None
                        code39_container.rotate = (
                            ft.Rotate(angle=rad, alignment=rot_align)
                            if rotation_degrees != 0
                            else None
                        )
                        code39_container.content = content_widget
                else:
                    code39_container = ft.Container(
                        content=content_widget,
                        data=f"code39_{barcode_id}",
                        left=code39_left,
                        top=code39_y_viewer,
                        rotate=(
                            ft.Rotate(angle=rad, alignment=rot_align)
                            if rotation_degrees != 0
                            else None
                        ),
                    )
                    self.text_stack.controls.append(code39_container)
                    barcode_data["code39_container"] = code39_container

            elif is_itf14:
                # ═══ ITF-14 — bars at top, bearer bar, digits below, baseline on guide ═══
                ds_pt = float(bd.get("barcode_font_size", 13.0))
                ds_mm = ds_pt * FONT_PT_TO_MM
                itf14_hri_gap_mm = float(bd.get("itf14_hri_gap_mm", 0.0))
                itf14_hri_position = bd.get("itf14_hri_position", "below")
                font_family = bd.get("barcode_font_family", "OCR-B")
                from utils.barcode_module import (
                    resolve_font_path,
                    get_font_cap_height_ratio,
                )

                _cap = get_font_cap_height_ratio(resolve_font_path(font_family))
                _desc_abs = get_ean13_font_descender_ratio(font_family)

                # Resolver según tipo GTIN
                raw_value = value
                gtin_type = bd.get("itf14_gtin_type", "gtin14")
                skip_itf14 = False
                itf14_error = ""
                if gtin_type == "gtin13":
                    gtin13_valid, gtin13_msg = validate_gtin13(raw_value)
                    if not gtin13_valid:
                        skip_itf14 = True
                        itf14_error = gtin13_msg
                    else:
                        raw_value = gtin13_to_gtin14(raw_value)
                else:
                    if len(raw_value) != 14:
                        skip_itf14 = True
                        itf14_error = "Debe tener 14 digitos"
                    else:
                        gtin14_valid, gtin14_msg = validate_itf14(raw_value)
                        if not gtin14_valid:
                            skip_itf14 = True
                            itf14_error = gtin14_msg

                printer_type = bd.get("itf14_printer_type", "flexografia")
                dims = calc_itf14_dimensions(
                    total_bar_width, printer_type, float(bd.get("bar_height", 0))
                )
                itf14_quiet_zone_mm = dims["quiet_zone_mm"]
                itf14_bearer_w_mm = dims["bearer_thickness_mm"]
                itf14_bearer_sides = dims["bearer_sides"]
                bar_height = dims["bar_height"]
                cw_mm = dims["bar_content_width"]
                module_width_mm = cw_mm / get_itf14_module_count()

                if itf14_hri_position == "above":
                    from utils.barcode_module import get_font_text_metrics

                    _asc, _, _ = get_font_text_metrics(resolve_font_path(font_family))
                    ch_mm = _asc * ds_mm + itf14_hri_gap_mm + bar_height
                else:
                    ch_mm = bar_height + itf14_hri_gap_mm + _cap * ds_mm
                if itf14_bearer_sides == "2":
                    ch_mm -= itf14_bearer_w_mm / 2

                s = scale
                cw_px = cw_mm * s
                ch_px = ch_mm * s
                quiet_zone_px = itf14_quiet_zone_mm * s
                bearer_w_px = itf14_bearer_w_mm * s
                half_bearer_px = bearer_w_px / 2
                total_vis_px = cw_px + 2 * quiet_zone_px + bearer_w_px
                bars_start_x = half_bearer_px + quiet_zone_px
                ds_px = ds_mm * s
                y_off_px = 0.0
                if itf14_hri_position == "above":
                    from utils.barcode_module import get_font_text_metrics

                    _asc, _, _ = get_font_text_metrics(resolve_font_path(font_family))
                    y_off_px = _asc * ds_px + itf14_hri_gap_mm * s

                if skip_itf14:
                    error_shapes = [
                        cv.Text(
                            2,
                            ch_px - 2,
                            f"ITF-14: {itf14_error}",
                            style=ft.TextStyle(size=12, color=ERROR_COLOR),
                        ),
                    ]
                    content_widget = cv.Canvas(error_shapes, width=cw_px, height=ch_px)
                    total_vis_px = cw_px
                else:
                    pattern, fullcode = encode_itf14(raw_value)
                    module_width_px = module_width_mm * s

                    shapes = []

                    if itf14_bearer_sides == "4":
                        shapes.append(
                            cv.Rect(
                                half_bearer_px,
                                half_bearer_px + y_off_px,
                                cw_px + 2 * quiet_zone_px,
                                bar_height * s - bearer_w_px,
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
                                paint=ft.Paint(
                                    color=bar_color, style=ft.PaintingStyle.FILL
                                ),
                            )
                        )
                        shapes.append(
                            cv.Rect(
                                0,
                                bar_height * s
                                - half_bearer_px
                                - bearer_w_px
                                + y_off_px,
                                total_vis_px,
                                bearer_w_px,
                                paint=ft.Paint(
                                    color=bar_color, style=ft.PaintingStyle.FILL
                                ),
                            )
                        )

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
                        shapes.append(
                            cv.Rect(
                                x_px,
                                half_bearer_px + y_off_px,
                                w_px,
                                bar_height * s - bearer_w_px,
                                paint=ft.Paint(
                                    color=bar_color, style=ft.PaintingStyle.FILL
                                ),
                            )
                        )
                        x_px += w_px
                        i = j

                    from utils.barcode_module import measure_text

                    hri = format_itf14_hri(fullcode)
                    hri_w_px = measure_text(hri, resolve_font_path(font_family), ds_px)
                    hri_start_x = total_vis_px / 2 - hri_w_px / 2
                    ts = ft.TextStyle(size=ds_px, color=hri_text_color)
                    if font_family:
                        ts.font_family = font_family
                    if itf14_hri_position == "above":
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
                    content_widget = cv.Canvas(shapes, width=total_vis_px, height=ch_px)

                # Column validation errors display
                col_errors = bd.get("itf14_column_errors", [])
                if col_errors:
                    err_count = len(col_errors)
                    err_lines = [f"Columna: {err_count} fila(s) invalida(s)"]
                    for row_idx, msg in col_errors[:3]:
                        err_lines.append(f"  Fila {row_idx + 1}: {msg}")
                    if err_count > 3:
                        err_lines.append(f"  ... y {err_count - 3} mas")
                    err_text = "\n".join(err_lines)
                    err_shapes = [
                        cv.Text(
                            4,
                            4,
                            err_text,
                            style=ft.TextStyle(size=11, color=ERROR_COLOR),
                        ),
                    ]
                    err_h = (len(err_lines) + 1) * 14
                    err_canvas = cv.Canvas(err_shapes, width=total_vis_px, height=err_h)
                    content_widget = ft.Column(
                        controls=[content_widget, err_canvas],
                        spacing=2,
                    )

                itf14_y_viewer = y_viewer_rel - ch_px

                if alignment == "centro":
                    itf14_left = x_viewer - total_vis_px / 2
                    rot_align = ft.Alignment(0, 1)
                elif alignment == "derecha":
                    itf14_left = x_viewer - total_vis_px
                    rot_align = ft.Alignment(1, 1)
                else:
                    itf14_left = x_viewer
                    rot_align = ft.Alignment(-1, 1)

                rad = math.radians(rotation_degrees)

                itf14_container = barcode_data.get("itf14_container")
                if itf14_container and itf14_container in self.text_stack.controls:
                    if _do_text_rebuild:
                        itf14_container.left = itf14_left
                        itf14_container.top = itf14_y_viewer
                        itf14_container.width = None
                        itf14_container.height = None
                        itf14_container.rotate = (
                            ft.Rotate(angle=rad, alignment=rot_align)
                            if rotation_degrees != 0
                            else None
                        )
                        itf14_container.content = content_widget
                else:
                    itf14_container = ft.Container(
                        content=content_widget,
                        data=f"itf14_{barcode_id}",
                        left=itf14_left,
                        top=itf14_y_viewer,
                        rotate=(
                            ft.Rotate(angle=rad, alignment=rot_align)
                            if rotation_degrees != 0
                            else None
                        ),
                    )
                    self.text_stack.controls.append(itf14_container)
                    barcode_data["itf14_container"] = itf14_container
            else:
                # ═══ Code128 — bars + HRI text on canvas ═══
                ds_pt = float(bd.get("barcode_font_size", 13.0))
                ds_mm = ds_pt * FONT_PT_TO_MM
                code128_gap_mm = float(bd.get("code128_hri_gap_mm", 2.0))
                code128_position = bd.get("code128_hri_position", "below")
                font_family = bd.get("barcode_font_family", "OCR-B")
                s = scale
                ds_px = ds_mm * s
                cw_px = total_bar_width * s

                if code128_position == "below":
                    from utils.barcode_module import (
                        resolve_font_path,
                        get_font_cap_height_ratio,
                        measure_text,
                    )

                    _cap = get_font_cap_height_ratio(resolve_font_path(font_family))
                    _desc_abs = get_ean13_font_descender_ratio(font_family)
                    ch_mm = bar_height + code128_gap_mm + _cap * ds_mm
                    ch_px = ch_mm * s

                    code128_shapes = []
                    for rx, ry, rw, rh in rects:
                        code128_shapes.append(
                            cv.Rect(
                                rx * s,
                                ry * s,
                                rw * s,
                                rh * s,
                                paint=ft.Paint(
                                    color=bar_color, style=ft.PaintingStyle.FILL
                                ),
                            )
                        )

                    hri_w_px = measure_text(
                        value, resolve_font_path(font_family), ds_px
                    )
                    hri_start_x = cw_px / 2 - hri_w_px / 2
                    ts = ft.TextStyle(size=ds_px, color=hri_text_color)
                    if font_family:
                        ts.font_family = font_family
                    if ds_px > 0:
                        code128_shapes.append(
                            cv.Text(
                                hri_start_x,
                                ch_px + _desc_abs * ds_px,
                                value,
                                style=ts,
                                alignment=ft.Alignment.BOTTOM_LEFT,
                            )
                        )
                else:
                    from utils.barcode_module import (
                        resolve_font_path,
                        get_font_text_metrics,
                        measure_text,
                    )

                    _asc, _, _ = get_font_text_metrics(resolve_font_path(font_family))
                    ch_mm = _asc * ds_mm + code128_gap_mm + bar_height
                    ch_px = ch_mm * s
                    bar_top_px = _asc * ds_px + code128_gap_mm * s

                    code128_shapes = []
                    for rx, ry, rw, rh in rects:
                        code128_shapes.append(
                            cv.Rect(
                                rx * s,
                                bar_top_px,
                                rw * s,
                                rh * s,
                                paint=ft.Paint(
                                    color=bar_color, style=ft.PaintingStyle.FILL
                                ),
                            )
                        )

                    hri_w_px = measure_text(
                        value, resolve_font_path(font_family), ds_px
                    )
                    hri_start_x = cw_px / 2 - hri_w_px / 2
                    ts = ft.TextStyle(size=ds_px, color=hri_text_color)
                    if font_family:
                        ts.font_family = font_family
                    if ds_px > 0:
                        code128_shapes.append(
                            cv.Text(
                                hri_start_x,
                                0,
                                value,
                                style=ts,
                                alignment=ft.Alignment.TOP_LEFT,
                            )
                        )

                code128_canvas = cv.Canvas(code128_shapes, width=cw_px, height=ch_px)

                if alignment == "centro":
                    code128_left = x_viewer - cw_px / 2
                    rot_align = ft.Alignment(0, 1)
                elif alignment == "derecha":
                    code128_left = x_viewer - cw_px
                    rot_align = ft.Alignment(1, 1)
                else:
                    code128_left = x_viewer
                    rot_align = ft.Alignment(-1, 1)

                code128_y_viewer = y_viewer_rel - ch_px
                rad = math.radians(rotation_degrees)

                code128_container = barcode_data.get("code128_container")
                if code128_container and code128_container in self.text_stack.controls:
                    if _do_text_rebuild:
                        code128_container.left = code128_left
                        code128_container.top = code128_y_viewer
                        code128_container.width = None
                        code128_container.height = None
                        code128_container.rotate = (
                            ft.Rotate(angle=rad, alignment=rot_align)
                            if rotation_degrees != 0
                            else None
                        )
                        code128_container.content = code128_canvas
                else:
                    code128_container = ft.Container(
                        content=code128_canvas,
                        data=f"code128_{barcode_id}",
                        left=code128_left,
                        top=code128_y_viewer,
                        rotate=(
                            ft.Rotate(angle=rad, alignment=rot_align)
                            if rotation_degrees != 0
                            else None
                        ),
                    )
                    self.text_stack.controls.append(code128_container)
                    barcode_data["code128_container"] = code128_container

            # Guides if enabled (en posición de referencia x_mm, no en la primera barra)
            if self.show_guides:
                guide_v = cv.Line(
                    x_viewer,
                    0,
                    x_viewer,
                    self.viewer_height,
                    paint=ft.Paint(stroke_width=0, color=guide_color),
                )
                self.canvas_shapes.append(guide_v)
                barcode_data["guide_v_control"] = guide_v
                guide_h = cv.Line(
                    0,
                    y_viewer_rel,
                    self.viewer_width,
                    y_viewer_rel,
                    paint=ft.Paint(stroke_width=0, color=guide_color),
                )
                self.canvas_shapes.append(guide_h)
                barcode_data["guide_h_control"] = guide_h

        # 2c. Sync vt_data from profile before render (like barcodes at 2b)
        if self.vt_profile_manager and _do_text_rebuild:
            _vt_profiles = self.vt_profile_manager.get_profiles()
            for _vt in self.variable_texts.values():
                _vd = _vt["data"]
                _pn = _vd.get("profile_name")
                if _pn:
                    for _p in _vt_profiles:
                        if _p.name == _pn:
                            _vd["font_size"] = _p.font_size
                            _vd["font_family"] = _p.font_family
                            _vd["font_style"] = _p.font_style
                            _vd["color"] = _p.text_color
                            _vd["color_tint"] = _p.text_color_tint
                            _vd["color_space"] = _p.text_color_space
                            _vd["line_spacing"] = getattr(_p, "line_spacing", 1.0)
                            _vd["letter_spacing"] = getattr(_p, "letter_spacing", 0.0)
                            _vd["resolved_font_path"] = getattr(_p, "resolved_font_path", None)
                            _vd["resolved_font_index"] = getattr(_p, "resolved_font_index", 0)
                            _vd["metricas"] = getattr(_p, "metricas", None)
                            _vd["value_source"] = _p.value_source
                            _vd["excel_column"] = getattr(_p, "excel_column", "")
                            break
        # 2d. Dibujar textos variables
        for vt_id, vt_data in self.variable_texts.items():
            vt_d = vt_data["data"]
            x_mm = vt_d["x"]
            y_mm = vt_d["y"]
            rotation_str = vt_d.get("rotation", "0°")
            rotation_degrees = int(rotation_str.replace("°", ""))
            text_alignment = vt_d.get("text_alignment", "izquierda")
            x_viewer, y_viewer = self._transform_page_to_viewer_coords(x_mm, y_mm)

            is_selected = (
                self.selected_variable_text_id == vt_id
                and self.selected_id is None
                and self.selected_barcode_id is None
            )
            is_locked = vt_d.get("locked", False)
            guide_color = (
                COLOR_LOCKED
                if is_locked
                else (COLOR_ACTIVO if is_selected else COLOR_INACTIVO)
            )

            # Inicializar referencias de shapes (para in-place drag)
            self.variable_texts[vt_id]["guide_v_control"] = None
            self.variable_texts[vt_id]["guide_h_control"] = None
            self.variable_texts[vt_id]["control_point_shape"] = None

            # Círculo de control (FILL como numeradoras)
            control_point_shape = cv.Circle(
                x=x_viewer,
                y=y_viewer,
                radius=6,
                paint=ft.Paint(color=guide_color, style=ft.PaintingStyle.FILL),
            )
            self.canvas_shapes.append(control_point_shape)
            self.variable_texts[vt_id]["control_point_shape"] = control_point_shape

            # Guías (solo si show_guides)
            if self.show_guides:
                guide_v = cv.Line(
                    x_viewer,
                    0,
                    x_viewer,
                    self.viewer_height,
                    paint=ft.Paint(stroke_width=0, color=guide_color),
                )
                self.canvas_shapes.append(guide_v)
                self.variable_texts[vt_id]["guide_v_control"] = guide_v
                guide_h = cv.Line(
                    0,
                    y_viewer,
                    self.viewer_width,
                    y_viewer,
                    paint=ft.Paint(stroke_width=0, color=guide_color),
                )
                self.canvas_shapes.append(guide_h)
                self.variable_texts[vt_id]["guide_h_control"] = guide_h

            # Texto
            if _do_text_rebuild:
                pfx = vt_d.get("prefix", "")
                sfx = vt_d.get("suffix", "")
                txt = vt_d.get("text", "")
                display_text = f"{pfx}{txt}{sfx}"
                font_size = vt_d.get("font_size", 12)
                _color = vt_d.get("color", "#000000")
                _color_tint = float(vt_d.get("color_tint", 100.0))
                _color_space = vt_d.get("color_space", "RGB")
                text_color = _viewer_tinted_color(_color, _color_tint, _color_space)
                ps_color = text_color
                font_family = vt_d.get("font_family", "Arial")
                font_style = vt_d.get("font_style", "Regular")
                letter_spacing = float(vt_d.get("letter_spacing", 0.0))
                metricas = vt_d.get("metricas")
                resolved_font_path = vt_d.get("resolved_font_path")
                # Interlineado en pt (perfil); medida de caja usa multiplicador.
                line_spacing_pt = float(vt_d.get("line_spacing", 0.0))
                anchor = vt_d.get("anchor", DEFAULT_ANCHOR)
                text_alignment = vt_d.get("text_alignment", "izquierda")

                # Caja tight multilínea (pt) + render PIL de la tinta real.
                # La imagen (getmask, anchor 'lt') coincide pixel a pixel con el
                # bbox tight: sin aire de em-box, sin desbordes ni recortes.
                lines = (display_text or "").split("\n")
                px = FONT_PT_TO_MM * self.current_scale
                cache_key = (
                    vt_id,
                    display_text,
                    resolved_font_path or "",
                    float(font_size),
                    float(line_spacing_pt),
                    float(letter_spacing),
                    text_alignment,
                    text_color,
                )
                cached = self._vt_img_cache.get(cache_key)
                if cached is None:
                    b64, w_pt, h_pt, baselines_pt = render_vt_image_b64(
                        lines,
                        resolved_font_path or "",
                        float(font_size),
                        line_spacing_pt=float(line_spacing_pt),
                        letter_spacing_pt=float(letter_spacing),
                        text_alignment=text_alignment,
                        text_color=text_color,
                    )
                    cached = (b64, w_pt, h_pt, baselines_pt)
                    self._vt_img_cache[cache_key] = cached
                b64, w_pt, h_pt, baselines_pt = cached
                box_w = w_pt * px
                box_h = h_pt * px
                # El container se ancla con las DOS componentes de la POSICIÓN
                # (anchor 9, post_data): la caja se coloca vs la guía en X e Y.
                # La Alineación (perfil) solo alinea líneas DENTRO de la caja.
                fx, fy = anchor_uv(anchor)
                final_left = x_viewer - fx * box_w
                _v_off = vertical_anchor_offset(
                    fy,
                    {"baselines": baselines_pt, "box_h": h_pt},
                    resolved_font_path or "",
                    float(font_size),
                )
                final_top = y_viewer - _v_off * px

                container = ft.Container(
                    content=ft.Image(
                        src=b64,
                        width=box_w,
                        height=box_h,
                        fit=ft.BoxFit.FILL,
                        gapless_playback=True,
                    ),
                    data=vt_id,
                    left=final_left,
                    top=final_top,
                    padding=0,
                    margin=0,
                    width=box_w,
                    height=box_h,
                    clip_behavior=ft.ClipBehavior.NONE,
                    rotate=ft.Rotate(
                        angle=math.radians(rotation_degrees),
                        # Pivot en el punto de la caja que coincide con la guía:
                        # (fx horizontal, offset vertical real). Alignment espera -1..1.
                        alignment=ft.Alignment(
                            fx * 2 - 1,
                            (_v_off / h_pt) * 2 - 1 if h_pt else -1,
                        ),
                    ),
                )
                self.text_stack.controls.append(container)

        # Pan-shift: aplicar delta de desplazamiento in-place sobre controles existentes.
        # Solo se ejecuta cuando no se reconstruyeron (panning=True).
        if self.panning:
            _dx = self.offset_x - self._prev_offset_x
            _dy = self.offset_y - self._prev_offset_y
            if _dx != 0.0 or _dy != 0.0:
                for _ctrl in self.text_stack.controls:
                    _ctrl.left = (_ctrl.left or 0.0) + _dx
                    _ctrl.top = (_ctrl.top or 0.0) + _dy
        self._prev_offset_x = self.offset_x
        self._prev_offset_y = self.offset_y

        # Restaurar shapes de barcodes NO target (control points y guías)
        if _saved_shapes:
            self.canvas_shapes.extend(_saved_shapes)

        # Sincronizar canvas.shapes con nuestra lista
        self.canvas.shapes = self.canvas_shapes
        if _do_text_rebuild:
            # Actualizar capas base (white_page + canvas).
            self._update_canvas()
            # Actualizar zoom_container para montar el nuevo text_stack.
            # El text_stack acaba de ser creado (línea 1261) y aún no tiene __uid,
            # por lo que _safe_page_update(text_stack) fallaría silenciosamente.
            # Actualizando el padre (zoom_container) Flet serializa todo el subárbol
            # incluyendo el text_stack nuevo con sus controles.
            self._safe_page_update(
                getattr(self, "zoom_container", None),
                "rebuild:update(zoom_container)",
            )
        elif self.dragging_element and self.dragging_element_id is not None:
            # Element drag: evitar update del stack completo para no tocar subárboles inestables
            _ok_canvas = self._safe_page_update(
                getattr(self, "canvas", None), "drag:update(canvas)"
            )
            _ok_text = False
            if self.dragging_control is not None:
                _ok_text = self._safe_page_update(
                    self.dragging_control,
                    "drag:update(active_control)",
                )
            else:
                _ok_text = self._safe_page_update(
                    getattr(self, "text_stack", None),
                    "drag:update(text_stack)",
                )

            # Solo bloquear movimiento in-place tras varios fallos seguidos de canvas.
            if _ok_canvas:
                self._drag_canvas_fail_streak = 0
            else:
                self._drag_canvas_fail_streak += 1
            self._drag_stack_failed = self._drag_canvas_fail_streak >= 3

            if not _ok_canvas:
                # Último fallback para no romper visualmente el drag
                self._safe_page_update(
                    getattr(self, "zoom_container", None),
                    "drag:fallback update(zoom_container)",
                )
        else:
            # Panning: update granular para evitar asserts del stack completo
            _ok_white = self._safe_page_update(
                getattr(self, "white_page_control", None),
                "pan:update(white_page)",
            )
            _ok_canvas = self._safe_page_update(
                getattr(self, "canvas", None), "pan:update(canvas)"
            )
            _ok_text = self._safe_page_update(
                getattr(self, "text_stack", None),
                "pan:update(text_stack)",
            )
            if not (_ok_white or _ok_canvas or _ok_text):
                self._safe_page_update(
                    getattr(self, "zoom_container", None),
                    "pan:fallback update(zoom_container)",
                )
            elif not _ok_text and (_ok_white or _ok_canvas):
                # text_stack falló (uid transitorio tras rebuild del zoom) pero el resto
                # se movió: forzar resync del subtree completo para no desincronizar contenedores
                self._safe_page_update(
                    getattr(self, "zoom_container", None),
                    "pan:resync text_stack",
                )

    def _redraw_all(self, force=False, only_barcode_ids=None):
        """Redibuja página, numeradoras, líneas Y reglas - llamar al finalizar drag/pan
        only_barcode_ids: lista de IDs de barcode a regenerar (None = todos).
        """
        self._redraw_canvas_only(force=force, only_barcode_ids=only_barcode_ids)

        if ENABLE_RULERS:
            self._redraw_rulers()

    # ------------------------------------------------------------------
    # Guías de posición: dibujo
    # ------------------------------------------------------------------
    def _draw_position_guides(self):
        """Dibuja las guías de la cara activa como líneas a página completa.

        Grosor CONSTANTE en px (el zoom escala longitud, NO el ancho).
        La guía arrastrada se dibuja con `guide_color_selected`.
        """
        pg = self.position_guides
        if not pg or not pg.show:
            return
        face = getattr(self, "guides_face", "CARA")
        for g in pg.get_guides(face):
            is_dragged = g["id"] == self._dragging_guide_id
            paint = ft.Paint(
                stroke_width=self.guide_stroke_width,
                color=self.guide_color_selected if is_dragged else self.guide_color,
            )
            if g["orientation"] == "V":
                x_viewer, _ = self._transform_page_to_viewer_coords(
                    g["position_mm"], 0
                )
                # La guía cruza TODO el viewer (de regla superior a inferior) para
                # que se vea hasta dónde arrastrarla y soltarla sobre las reglas.
                self.canvas_shapes.append(
                    cv.Line(
                        x_viewer,
                        0,
                        x_viewer,
                        self.viewer_height,
                        paint=paint,
                    )
                )
            else:
                _, y_viewer = self._transform_page_to_viewer_coords(
                    0, g["position_mm"]
                )
                self.canvas_shapes.append(
                    cv.Line(
                        0,
                        y_viewer,
                        self.viewer_width,
                        y_viewer,
                        paint=paint,
                    )
                )

    # ------------------------------------------------------------------
    # Guías de posición: creación desde las reglas (patrón InDesign)
    # ------------------------------------------------------------------
    def _on_ruler_pan_start(self, e, from_ruler):
        """Inicia drag de una guía NUEVA desde una regla.
        Con guías desactivadas (show=False) no se crea nada."""
        pg = self.position_guides
        if not pg or not pg.show:
            return
        face = getattr(self, "guides_face", "CARA")
        # Guía CENTRADA + orientada por regla (patrón InDesign):
        # regla SUPERIOR (H) → guía HORIZONTAL en height/2  (línea horizontal);
        # regla IZQUIERDA (V) → guía VERTICAL   en width/2  (línea vertical).
        if from_ruler == "H":
            coord = self.page_height_mm / 2
            orient = "H"
        else:
            coord = self.page_width_mm / 2
            orient = "V"
        guide = pg.create_from_ruler(
            face, orient, coord, self.page_width_mm, self.page_height_mm
        )
        self._new_guide_id = guide["id"]
        self._new_guide_coord_vivo_mm = coord
        self._new_guide_from = from_ruler
        self._new_guide_ever_left = False
        self._dragging_guide_id = guide["id"]
        self._dragging_guide_face = face
        self._redraw_all(force=True)

    def _on_ruler_pan_update(self, e, from_ruler):
        pg = self.position_guides
        if not pg or self._new_guide_id is None:
            return
        face = getattr(self, "_dragging_guide_face", "CARA")
        x_viewer = e.local_position.x + self.corner_size
        y_viewer = e.local_position.y + self.corner_size
        x_mm, y_mm = self._transform_viewer_to_page_coords(x_viewer, y_viewer)
        # Guía HORIZONTAL (de regla superior) se posiciona en Y; guía
        # VERTICAL (de regla izquierda) se posiciona en X.
        coord = y_mm if from_ruler == "H" else x_mm
        limit_mm = self.page_height_mm if from_ruler == "H" else self.page_width_mm
        coord = max(0.0, min(coord, limit_mm))
        # coord>0 ⇒ el cursor cruzó a la página (fuera de la franja de regla):
        # distingue un clic/arrastre-restringido a la regla de un drag real.
        if coord > 0:
            self._new_guide_ever_left = True
        if self._new_guide_ever_left:
            # Solo tras cruzar a la página se sigue al cursor; mientras la
            # punta siga en la regla, la guía se mantiene centrada (clic).
            self._new_guide_coord_vivo_mm = coord
            pg.move_guide(face, self._new_guide_id, coord)
        self._redraw_canvas_only()

    def _on_ruler_pan_end(self, e, from_ruler):
        pg = self.position_guides
        if not pg or self._new_guide_id is None:
            return
        face = getattr(self, "_dragging_guide_face", "CARA")
        # Soltar sobre la regla de origen → se borra (patrón InDesign).
        # Nota: DragEndEvent de Flet 0.28 NO expone local_x/local_y; se usa la
        # coordenada viva que dejó el último pan_update.
        coord_vivo_mm = getattr(self, "_new_guide_coord_vivo_mm", None)
        over_ruler = (
            coord_vivo_mm is not None
            and getattr(self, "_new_guide_ever_left", False)
            and coord_vivo_mm <= (self.corner_size / self.current_scale)
        )
        if over_ruler:
            pg.delete_guide(face, self._new_guide_id)
        self._new_guide_id = None
        self._new_guide_from = None
        self._dragging_guide_id = None
        self._dragging_guide_face = None
        self._redraw_all(force=True)

    def _redraw_rulers(self):
        """Redibuja las reglas con el zoom actual"""
        if not ENABLE_RULERS:
            return

        current_scale = self.current_scale

        # Usar offset global (ya no viene de InteractiveViewer)
        offset_x = self.offset_x
        offset_y = self.offset_y

        # Obtener configuración de la unidad actual
        unit_config = RULER_UNITS.get(self.ruler_unit, RULER_UNITS[UNIT_MM])
        to_mm = unit_config["to_mm"]
        major_tick = unit_config["major_tick"]
        minor_tick = unit_config["minor_tick"]
        tiny_tick = unit_config["tiny_tick"]
        label_divisor = unit_config["label_divisor"]

        # Limpiar shapes anteriores
        self.ruler_horizontal_shapes.clear()
        self.ruler_vertical_shapes.clear()

        # REGLA HORIZONTAL (superior)
        # Usar el tamaño de página REAL (sin sangre)
        max_units_h = self.page_width_mm / to_mm

        # Calcular donde empieza la página en el canvas ampliado (coordenadas del viewer)
        page_start_x = (
            self.big_canvas_width - self.canvas_width * current_scale
        ) / 2 + offset_x

        # Ajustar el origen para que empiece después de la sangre
        bleed_offset_px = mm_to_screen_pixels(self.bleed_mm) * current_scale
        page_start_x += bleed_offset_px

        # Dibujar marcas
        unit = 0
        while unit <= max_units_h:
            # Posición en mm en la página
            x_mm = unit * to_mm
            # Convertir mm a píxeles de canvas
            x_px_canvas = mm_to_screen_pixels(x_mm)
            # Aplicar escala
            x_scaled = x_px_canvas * current_scale

            # Posición en el viewer (ajustada por corner_size para el canvas de la regla)
            x_viewer = page_start_x + x_scaled - self.corner_size

            # Solo dibujar si está visible en el viewer
            if 0 <= x_viewer <= self.viewer_width:
                # Determinar tipo de marca
                if abs(unit % major_tick) < 0.001:  # Marca mayor
                    line_height = 15
                    # Línea de la marca
                    line_y_start = self.corner_size - line_height
                    self.ruler_horizontal_shapes.append(
                        cv.Line(
                            x_viewer,
                            line_y_start,
                            x_viewer,
                            25,
                            paint=ft.Paint(stroke_width=1, color=ft.Colors.GREY_700),
                        )
                    )
                    # Mostrar número cada label_divisor, justo arriba de la línea
                    if abs(unit % label_divisor) < 0.001:
                        # Número centrado horizontalmente sobre la línea, con bottom en line_y_start
                        self.ruler_horizontal_shapes.append(
                            cv.Text(
                                x_viewer,
                                line_y_start - 2,
                                f"{int(unit)}",
                                ft.TextStyle(size=8, color=ft.Colors.BLACK),
                                alignment=ft.Alignment.BOTTOM_CENTER,
                            )
                        )
                elif abs(unit % minor_tick) < 0.001:  # Marca media
                    line_height = 10
                    self.ruler_horizontal_shapes.append(
                        cv.Line(
                            x_viewer,
                            self.corner_size - line_height,
                            x_viewer,
                            self.corner_size,
                            paint=ft.Paint(stroke_width=1, color=ft.Colors.GREY_700),
                        )
                    )
                else:  # Marca menor
                    line_height = 5
                    self.ruler_horizontal_shapes.append(
                        cv.Line(
                            x_viewer,
                            self.corner_size - line_height,
                            x_viewer,
                            self.corner_size,
                            paint=ft.Paint(stroke_width=1, color=ft.Colors.GREY_700),
                        )
                    )

            unit += tiny_tick

        # REGLA VERTICAL (izquierda)
        # Usar el tamaño de página REAL (sin sangre)
        max_units_v = self.page_height_mm / to_mm

        # Calcular donde empieza la página en el canvas ampliado (coordenadas del viewer)
        page_start_y = (
            self.big_canvas_height - self.canvas_height * current_scale
        ) / 2 + offset_y

        # Ajustar el origen para que empiece después de la sangre
        bleed_offset_px = mm_to_screen_pixels(self.bleed_mm) * current_scale
        page_start_y += bleed_offset_px

        # Dibujar marcas
        unit = 0
        while unit <= max_units_v:
            # Posición en mm en la página
            y_mm = unit * to_mm
            # Convertir mm a píxeles de canvas
            y_px_canvas = mm_to_screen_pixels(y_mm)
            # Aplicar escala
            y_scaled = y_px_canvas * current_scale

            # Posición en el viewer (ajustada por corner_size para el canvas de la regla)
            y_viewer = page_start_y + y_scaled - self.corner_size

            # Solo dibujar si está visible en el viewer
            if 0 <= y_viewer <= self.viewer_height:
                # Determinar tipo de marca
                if abs(unit % major_tick) < 0.001:  # Marca mayor
                    line_width = 15
                    # Línea de la marca
                    line_x_start = self.corner_size - line_width
                    self.ruler_vertical_shapes.append(
                        cv.Line(
                            line_x_start,
                            y_viewer,
                            self.corner_size,
                            y_viewer,
                            paint=ft.Paint(stroke_width=1, color=ft.Colors.GREY_700),
                        )
                    )
                    # Mostrar número cada label_divisor (rotado 90°), a la izquierda de la línea
                    if abs(unit % label_divisor) < 0.001:
                        # Número rotado 90°, centrado verticalmente a la izquierda de la línea
                        # Con rotación 90°, bottom_center hace que el número quede a la izquierda
                        self.ruler_vertical_shapes.append(
                            cv.Text(
                                line_x_start - 2,
                                y_viewer,
                                f"{int(unit)}",
                                ft.TextStyle(size=8, color=ft.Colors.BLACK),
                                alignment=ft.Alignment.CENTER_RIGHT,
                                rotate=90 * 3.14159 / 180,
                            )
                        )
                elif abs(unit % minor_tick) < 0.001:  # Marca media
                    line_width = 10
                    self.ruler_vertical_shapes.append(
                        cv.Line(
                            self.corner_size - line_width,
                            y_viewer,
                            self.corner_size,
                            y_viewer,
                            paint=ft.Paint(stroke_width=1, color=ft.Colors.GREY_700),
                        )
                    )
                else:  # Marca menor
                    line_width = 5
                    self.ruler_vertical_shapes.append(
                        cv.Line(
                            25 - line_width,
                            y_viewer,
                            25,
                            y_viewer,
                            paint=ft.Paint(stroke_width=1, color=ft.Colors.GREY_700),
                        )
                    )

            unit += tiny_tick

        # Actualizar canvas de las reglas
        self.ruler_horizontal_canvas.shapes = self.ruler_horizontal_shapes
        self.ruler_vertical_canvas.shapes = self.ruler_vertical_shapes

        # Solo llamar a update() si los canvases ya están en la página
        # (esto evita errores durante la inicialización)
        try:
            if _safe_page(self.ruler_horizontal_canvas) is not None:
                self.ruler_horizontal_canvas.update()
                self.ruler_vertical_canvas.update()
        except (AssertionError, AttributeError):
            # Los canvases aún no están agregados a la página, se renderizarán automáticamente
            # print("Rulers not ready for update yet")
            pass
        except Exception:
            print("_redraw_rulers Error:")
            traceback.print_exc()

    def set_ruler_unit(self, unit):
        """Cambia la unidad de medida de las reglas"""
        if not ENABLE_RULERS:
            return

        if unit in RULER_UNITS:
            self.ruler_unit = unit
            self._redraw_rulers()

    def add_numeradora(
        self,
        x=None,
        y=None,
        number="",
        alignment="izquierda",
        text_style_name="<Default>",
        auto_select=True,
        num_id=None,
        locked=False,
    ):
        """
        Agrega una nueva numeradora al visor usando Canvas

        Args:
            x: Posición X de referencia (línea vertical)
            y: Posición Y de referencia (parte superior del texto)
            number: Texto del número a mostrar
            alignment: Alineación del texto ("izquierda", "centro", "derecha")
            text_style_name: Nombre del estilo de texto a aplicar
            auto_select: Si es True, selecciona automáticamente la numeradora
            num_id: ID específico para la numeradora (si None, se genera automáticamente)
        """
        # Usar ID específico o generar uno nuevo
        if num_id is None:
            num_id = self.next_id
            self.next_id += 1
        else:
            # Si se proporciona un ID, asegurarse de que next_id sea mayor
            if num_id >= self.next_id:
                self.next_id = num_id + 1

        # Posición por defecto (centro del canvas)
        if x is None:
            x = self.canvas_width / 2
        if y is None:
            y = self.canvas_height / 2

        # NO VALIDAR límites - permitir numeradoras fuera de la página (como programas de diseño)

        # Posición de la línea horizontal
        # Debe estar en la misma Y que la BASE del texto (baseline)
        line_h_y = y

        # Calcular posición del texto según alineación
        text_x = self._calculate_text_x_position(x, alignment, number, 14)

        print(
            f"[VIEWER] Creando numeradora: x={x}, y={y}, text_x={text_x}, alignment={alignment}"
        )

        # Guardar en diccionario (solo datos, las shapes se dibujan en el overlay)
        self.numeradoras[num_id] = {
            "data": {
                "x": x,
                "y": y,
                "number": number,
                "alignment": alignment,
                "text_style_name": text_style_name,  # Guardar el nombre del estilo
                "locked": locked,
            }
        }

        # Redibujar todo con todas las numeradoras
        self._redraw_all(force=True)

        # Seleccionar automaticamente la nueva numeradora (solo si auto_select=True)
        if auto_select:
            self._select_numeradora(num_id)

        return num_id

    def _get_canvas_alignment(self, alignment):
        """
        Convierte alineación de texto a alignment de Canvas
        Usa bottom_* porque el texto se alinea por su base

        Args:
            alignment: "izquierda", "centro", "derecha"

        Returns:
            ft.alignment para Canvas
        """
        if alignment == "izquierda":
            return ft.Alignment.BOTTOM_LEFT
        elif alignment == "centro":
            return ft.Alignment.BOTTOM_CENTER
        elif alignment == "derecha":
            return ft.Alignment.BOTTOM_RIGHT
        else:
            return ft.Alignment.BOTTOM_LEFT

    def _calculate_text_x_position(self, ref_x, alignment, text, font_size):
        """
        Retorna la posición X de referencia. El ajuste por alineación se realiza
        en el método _redraw_canvas_only para considerar la rotación.
        """
        return ref_x

    def _select_numeradora(self, num_id):
        """Selecciona una numeradora cambiando los colores de guías y punto de control"""
        _old_bc = self.selected_barcode_id
        _old_num = self.selected_id
        _old_vt = self.selected_variable_text_id
        self.selected_id = num_id
        self.selected_barcode_id = None
        self.selected_variable_text_id = None

        self._update_fine_adjust_visibility()

        if _old_bc is not None:
            self._update_selection_visual(_old_bc, "barcode", False)
        if _old_num is not None and _old_num != num_id:
            self._update_selection_visual(_old_num, "number", False)
        if _old_vt is not None:
            self._update_selection_visual(_old_vt, "variable_text", False)
        self._update_selection_visual(num_id, "number", True)

        if self.on_select_callback:
            self.on_select_callback(num_id)

    def _deselect_numeradora(self):
        """
        Deselecciona la numeradora activa
        Notifica al main_screen mediante callback con None
        """
        if self.selected_id is None:
            return  # No hay nada seleccionado

        print(f"[VIEWER] Deseleccionando numeradora {self.selected_id}")

        # Limpiar selección
        _old_id = self.selected_id
        self.selected_id = None

        self._update_fine_adjust_visibility()

        if _old_id is not None:
            self._update_selection_visual(_old_id, "number", selected=False)

        if self.on_select_callback:
            self.on_select_callback(None)

        print("[VIEWER] Numeradora deseleccionada")

    def set_show_guides(self, visible: bool):
        """Mostrar u ocultar las líneas guía (vertical/horizontal)."""
        self.show_guides = bool(visible)
        self._redraw_all()

    def _apply_magnetic_snap(
        self, current_x, current_y, delta_mm_x, delta_mm_y, element_data
    ):
        """Ajusta deltas para que el elemento snapée al centro de otros cercanos."""
        if not self.magnetic_snap_active:
            return delta_mm_x, delta_mm_y

        proposed_x = current_x + delta_mm_x
        proposed_y = current_y + delta_mm_y

        scale = self.current_scale if self.current_scale > 0 else 1.0
        threshold_mm = screen_pixels_to_mm(self.magnetic_snap_threshold / scale)

        # Recoger todos los centros de otros elementos (excluyendo el que se arrastra).
        # Hay DOS listas: las guías solo entran en su eje (vertical→X,
        # horizontal→Y) para que una guía nunca clave el otro eje.
        from itertools import chain

        cand_x = []
        cand_y = []
        for edata in chain(
            self.numeradoras.values(),
            self.barcodes.values(),
            self.variable_texts.values(),
        ):
            if edata is element_data:
                continue
            try:
                ex = edata["data"]["x"]
                ey = edata["data"]["y"]
                cand_x.append((ex, ey))
                cand_y.append((ex, ey))
            except Exception:
                pass

        # Guías de posición: cada una SOLO en su eje. El snap efectivo exige
        # botón magnético AND guías activas (show): ocultar desactiva el snap
        # pero no toca la memoria del botón; al reactivar vuelve según el botón.
        if self.position_guides and self.position_guides.snap_active and self.position_guides.show:
            _face = getattr(self, "guides_face", "CARA")
            _gc = self.position_guides.magnetic_candidates(_face)
            try:
                _ex = element_data["data"]["x"]
                _ey = element_data["data"]["y"]
            except Exception:
                _ex, _ey = current_x, current_y
            for _xv in _gc["x_mm"]:
                cand_x.append((_xv, _ey))
            for _yv in _gc["y_mm"]:
                cand_y.append((_ex, _yv))

        if not cand_x and not cand_y:
            return delta_mm_x, delta_mm_y

        # Snap X: snap a la X más cercana si está dentro del umbral
        best_dx = None
        best_x_dist = None
        for ex, ey in cand_x:
            diff = abs(proposed_x - ex)
            if diff < threshold_mm:
                if best_dx is None or diff < best_x_dist:
                    best_dx = ex - current_x
                    best_x_dist = diff

        # Snap Y: snap a la Y más cercana si está dentro del umbral
        best_dy = None
        best_y_dist = None
        for ex, ey in cand_y:
            diff = abs(proposed_y - ey)
            if diff < threshold_mm:
                if best_dy is None or diff < best_y_dist:
                    best_dy = ey - current_y
                    best_y_dist = diff

        # Imán con fuerza, SOLO en el eje que se mueve: moviendo arriba/abajo
        # solo imanta la guía horizontal (eje Y); moviendo izq/der solo la
        # vertical (eje X). `delta==0` en un eje → ese eje ni suena.
        # En su eje: atrae al acercarse, clava al llegar justo (best==0),
        # y solo suelta si se arrastra en dirección opuesta.
        if best_dx is not None and delta_mm_x != 0 and best_dx * delta_mm_x >= 0:
            delta_mm_x = best_dx
        if best_dy is not None and delta_mm_y != 0 and best_dy * delta_mm_y >= 0:
            delta_mm_y = best_dy

        return delta_mm_x, delta_mm_y

    def set_alignment(self, num_id, alignment):
        """
        Cambia la alineación de una numeradora

        Args:
            num_id: ID de la numeradora
            alignment: "izquierda", "centro", "derecha"
        """
        if num_id not in self.numeradoras:
            return

        num_data = self.numeradoras[num_id]
        num_data["data"]["alignment"] = alignment
        print(f"[VIEWER] set_alignment({num_id}): alignment = {alignment}")
        print(f"  Data completo: {num_data['data']}")

        # Redibujar todo
        self._redraw_all()

    def set_rotation(self, num_id, rotation_str):
        """
        Cambia la rotación de una numeradora.
        Solo actualiza el dato y redibuja.

        Args:
            num_id: ID de la numeradora
            rotation_str: String con rotación ("0°", "90°", "180°", "270°")
        """
        if num_id not in self.numeradoras:
            return

        num_data = self.numeradoras[num_id]
        num_data["data"]["rotation"] = rotation_str
        print(f"[VIEWER] set_rotation({num_id}): rotation = {rotation_str}")
        print(f"  Data completo: {num_data['data']}")

        # Redibujar todo para aplicar la rotación
        self._redraw_all()

    def set_number(self, num_id, number_str, redraw=True):
        """
        Cambia el número mostrado por una numeradora

        Args:
            num_id: ID de la numeradora
            number_str: String con el número a mostrar (ej: "0001", "101")
            redraw: Si es True, redibuja inmediatamente forzando el redibujado
        """
        if num_id not in self.numeradoras:
            return

        num_data = self.numeradoras[num_id]
        num_data["data"]["number"] = number_str

        # Redibujar todo para mostrar el nuevo número
        if redraw:
            self._redraw_all(force=True)

    def update_numeradora_position(self, num_id, new_x, new_y):
        """
        Actualiza la posición de una numeradora programáticamente
        (cuando el usuario cambia los textfields de posición)

        Args:
            num_id: ID de la numeradora
            new_x: Nueva coordenada X en píxeles
            new_y: Nueva coordenada Y en píxeles
        """
        if num_id not in self.numeradoras:
            return

        num_data = self.numeradoras[num_id]

        # NO aplicar límites - permitir posiciones fuera del canvas

        # Actualizar datos
        num_data["data"]["x"] = new_x
        num_data["data"]["y"] = new_y

        # Redibujar todo (incluye líneas, círculos, texto y reglas)
        self._redraw_all()

    def update_variable_text_position(self, vt_id, new_x, new_y):
        """Actualiza la posición de un texto variable desde los textfields."""
        if vt_id not in self.variable_texts:
            return
        self.variable_texts[vt_id]["data"]["x"] = new_x
        self.variable_texts[vt_id]["data"]["y"] = new_y
        self._redraw_all()

    def set_variable_text_rotation(self, vt_id, rotation_str):
        """Cambia la rotación de un texto variable desde el dropdown."""
        if vt_id not in self.variable_texts:
            return
        self.variable_texts[vt_id]["data"]["rotation"] = rotation_str
        self._redraw_all()

    def set_variable_text_alignment(self, vt_id, alignment):
        """Cambia la posición (ancla 9) de un texto variable desde el dropdown."""
        if vt_id not in self.variable_texts:
            return
        self.variable_texts[vt_id]["data"]["anchor"] = alignment
        self._redraw_all()

    def update_barcode_post_data_visual(self, barcode_id, x_mm=None, y_mm=None, rotation=None, alignment=None):
        """Actualiza la posición/rotación/alineación de un barcode in-place
        sin regenerar bitmaps (QR, pdf417, datamatrix, etc.).

        Solo mueve el punto de control, las guías y el contenedor del text_stack.
        Llamar desde los handlers de post_data en main_screen en lugar de _redraw_all.
        """
        if barcode_id not in self.barcodes:
            return
        bd = self.barcodes[barcode_id]["data"]

        old_x_mm = bd.get("x", 0)
        old_y_mm = bd.get("y", 0)

        if x_mm is not None:
            bd["x"] = x_mm
        if y_mm is not None:
            bd["y"] = y_mm
        if rotation is not None:
            bd["rotation"] = rotation
        if alignment is not None:
            bd["alignment"] = alignment

        # Barcodes imagen (QR/PDF417/DM) se renderizan con la imagen pre-rotada: un
        # cambio de rotación necesita bitmap + dimensiones nuevos → redraw dirigido
        # (los b64 prerotados ya están en cache; no se regenera el código).
        if (
            rotation is not None
            and bd.get("symbology") in ("datamatrix", "qr", "pdf417")
            and barcode_id in self.barcodes
        ):
            self._redraw_all(force=True, only_barcode_ids=[barcode_id])
            return

        cur_x_mm = bd["x"]
        cur_y_mm = bd["y"]
        cur_rotation = bd.get("rotation", "0°")
        cur_alignment = bd.get("alignment", "izquierda")

        new_x_viewer, new_y_viewer = self._transform_page_to_viewer_coords(
            cur_x_mm, cur_y_mm
        )

        # Control point
        cp = self.barcodes[barcode_id].get("control_point_shape")
        if cp is not None:
            cp.x = new_x_viewer
            cp.y = new_y_viewer

        # Guide lines
        gv = self.barcodes[barcode_id].get("guide_v_control")
        if gv is not None:
            gv.x1 = new_x_viewer
            gv.x2 = new_x_viewer
        gh = self.barcodes[barcode_id].get("guide_h_control")
        if gh is not None:
            gh.y1 = new_y_viewer
            gh.y2 = new_y_viewer

        self.canvas.shapes = self.canvas_shapes

        # Container en text_stack
        _bc = self.barcodes.get(barcode_id)
        _ctrl = None
        if _bc:
            for _ckey in (
                "qr_container", "pdf417_container", "datamatrix_container",
                "ean13_container", "ean8_container", "ean5_container",
                "isbn13_container", "upca_container", "upce_container",
                "itf14_container", "code39_container", "code128_container",
            ):
                _c = _bc.get(_ckey)
                if _c and _c in self.text_stack.controls:
                    _ctrl = _c
                    break
            if not _ctrl:
                _dm_tag = f"datamatrix_{barcode_id}"
                for _c in self.text_stack.controls:
                    if str(getattr(_c, "data", "")) == _dm_tag:
                        _ctrl = _c
                        _bc["datamatrix_container"] = _c
                        break

        if _ctrl:
            _is_img = bd.get("symbology") in ("datamatrix", "qr", "pdf417")
            if _is_img:
                # Imagen pre-rotada (sin ft.Rotate): posicionar el ancla —punto de la
                # guía en el frame original, re-mapeado al frame rotado— sobre la guía.
                # El frame se lee del contenedor VIVO (ancho/alto real renderizado) en
                # vez de la caché mm: la caché queda stale tras seleccionar/reabrir y
                # hacía que el ancla se calculara contra un frame equivocado.
                try:
                    _rot_deg = int(str(cur_rotation).replace("°", ""))
                except (ValueError, AttributeError):
                    _rot_deg = 0
                _scale = self.current_scale
                if _is_datamatrix_family(bd.get("symbology")):
                    _code_w = float(bd.get("datamatrix_width", 20.0))
                    _code_h = _bc.get("dm_code_h_mm") or float(
                        bd.get("datamatrix_height", _code_w)
                    )
                    _hri_pos = bd.get("datamatrix_hri_position", "below")
                elif bd.get("symbology") == "qr":
                    _code_w = float(bd.get("bar_width", 80.0))
                    _code_h = _bc.get("qr_code_h_mm") or _code_w
                    _hri_pos = bd.get("qr_hri_position", "below")
                else:
                    _code_w = float(bd.get("bar_width", 80.0))
                    _pdf_h = bd.get("pdf417_height")
                    # Mismo ancho que el render (get_pdf417_total_size): con
                    # pdf417_height el ancho real puede diferir de bar_width.
                    _code_w, _code_h_natural = get_pdf417_total_size(
                        bd.get("value", ""), _code_w,
                        target_height_mm=_pdf_h if _pdf_h else None,
                    )
                    _code_h = float(_pdf_h) if _pdf_h else _code_h_natural
                    _code_h = _bc.get("pdf417_code_h_mm") or _code_h
                    _hri_pos = bd.get("pdf417_hri_position", "below")
                _cw_px = _ctrl.width or 0.0
                _ch_px = _ctrl.height or 0.0
                if not _cw_px and _ctrl.content:
                    _cw_px = getattr(_ctrl.content, "width", None) or 0.0
                    _ch_px = getattr(_ctrl.content, "height", None) or 0.0
                if _cw_px and _ch_px:
                    _frame_w, _frame_h = _rotate_dims_cw(
                        _cw_px / _scale, _ch_px / _scale, _rot_deg
                    )
                else:
                    _frame_w = _bc.get("dm_canvas_w_mm") or _code_w
                    _frame_h = _bc.get("dm_canvas_h_mm") or _code_h
                _ax_mm, _ay_mm = _datamatrix_guide_mm(
                    _frame_w, _frame_h, _code_h,
                    cur_alignment, _hri_pos,
                    code_w_mm=_code_w,
                )
                if _frame_w and _frame_h:
                    _rpx_mm, _rpy_mm = _rotate_point_cw(
                        _ax_mm, _ay_mm, _frame_w, _frame_h, _rot_deg
                    )
                    _ctrl.left = new_x_viewer - _rpx_mm * _scale
                    _ctrl.top = new_y_viewer - _rpy_mm * _scale
                    _ctrl.rotate = None
            else:
                old_x_viewer, old_y_viewer = self._transform_page_to_viewer_coords(
                    old_x_mm, old_y_mm
                )
                _new_x_viewer = new_x_viewer
                cw_px = 0.0
                if _ctrl.content and hasattr(_ctrl.content, "width"):
                    cw_px = _ctrl.content.width or 0.0
                if alignment is not None:
                    if cw_px:
                        if alignment == "centro":
                            _ctrl.left = _new_x_viewer - cw_px / 2
                        elif alignment == "derecha":
                            _ctrl.left = _new_x_viewer - cw_px
                        else:
                            _ctrl.left = _new_x_viewer
                    if y_mm is not None:
                        _ctrl.top = (_ctrl.top or 0) + (new_y_viewer - old_y_viewer)
                elif x_mm is not None or y_mm is not None:
                    _ctrl.left = (_ctrl.left or 0) + (new_x_viewer - old_x_viewer)
                    _ctrl.top = (_ctrl.top or 0) + (new_y_viewer - old_y_viewer)

                # Pivot de rotación recalculado en CADA llamada desde la alineación
                # actual (solo barcodes vectoriales: el contenido no se pre-rota).
                try:
                    _rot_deg = int(str(cur_rotation).replace("°", ""))
                except (ValueError, AttributeError):
                    _rot_deg = 0
                if _rot_deg != 0:
                    rad = math.radians(_rot_deg)
                    if cur_alignment == "centro":
                        _px = 0.0
                    elif cur_alignment == "derecha":
                        _px = 1.0
                    else:
                        _px = -1.0
                    _ctrl.rotate = ft.Rotate(
                        angle=rad, alignment=ft.Alignment(_px, 1.0)
                    )
                else:
                    _ctrl.rotate = None

        self._safe_page_update(
            getattr(self, "canvas", None), "post_data:canvas"
        )
        if _ctrl:
            self._safe_page_update(_ctrl, "post_data:ctrl")
        else:
            self._safe_page_update(
                getattr(self, "text_stack", None), "post_data:text_stack"
            )

    def _get_text_alignment_for_rotation(self, alignment, rotation_degrees):
        """
        Calcula el alignment del texto basado en la alineación y rotación.
        Rotación tipo reloj: 0°=3h, 90°=6h, 180°=9h, 270°=12h

        Para IZQUIERDA:
        - 0° (3h): top_left
        - 90° (6h): top_left
        - 180° (9h): top_right
        - 270° (12h): bottom_right

        Args:
            alignment: "izquierda", "centro", "derecha"
            rotation_degrees: 0, 90, 180, 270

        Returns:
            ft.alignment para cv.Text
        """
        # IZQUIERDA
        if alignment == "izquierda":
            if rotation_degrees == 90:
                return ft.Alignment.BOTTOM_LEFT
            elif rotation_degrees == 180:
                return ft.Alignment.BOTTOM_LEFT
            elif rotation_degrees == 270:
                return ft.Alignment.BOTTOM_LEFT
            else:  # 0°
                return ft.Alignment.BOTTOM_LEFT

        # CENTRO
        elif alignment == "centro":
            if rotation_degrees == 90:
                return ft.Alignment.BOTTOM_CENTER
            elif rotation_degrees == 180:
                return ft.Alignment.BOTTOM_CENTER
            elif rotation_degrees == 270:
                return ft.Alignment.BOTTOM_CENTER
            else:  # 0°
                return ft.Alignment.BOTTOM_CENTER

        # DERECHA
        elif alignment == "derecha":
            if rotation_degrees == 90:
                return ft.Alignment.BOTTOM_RIGHT
            elif rotation_degrees == 180:
                return ft.Alignment.BOTTOM_RIGHT
            elif rotation_degrees == 270:
                return ft.Alignment.BOTTOM_RIGHT
            else:  # 0°
                return ft.Alignment.BOTTOM_RIGHT

        # Default
        return ft.Alignment.BOTTOM_LEFT

    def set_page_size(self, page_size_name):
        """
        Cambia el tamaño de la página del canvas

        Args:
            page_size_name: Nombre del tamaño ("A4", "Letter", etc.)
        """
        if page_size_name not in PAGE_SIZES:
            print(f"[ERROR] Tamaño de página '{page_size_name}' no encontrado")
            return

        # Actualizar tamaño
        self.page_size_name = page_size_name
        width_mm, height_mm = PAGE_SIZES[page_size_name]
        self.page_width_mm = width_mm
        self.page_height_mm = height_mm
        new_width = mm_to_screen_pixels(width_mm)
        new_height = mm_to_screen_pixels(height_mm)

        print(
            f"[VIEWER] Cambiando tamaño de página a {page_size_name}: {width_mm}x{height_mm} mm = {new_width:.1f}x{new_height:.1f} px"
        )

        # Actualizar canvas
        self.canvas_width = new_width
        self.canvas_height = new_height
        self.canvas.width = new_width
        self.canvas.height = new_height

        # Actualizar líneas guía de todas las numeradoras
        for num_id, num_data in self.numeradoras.items():
            # Línea vertical (ajustar altura)
            num_data["guide_v"].y2 = new_height
            # Línea horizontal (ajustar ancho)
            num_data["guide_h"].x2 = new_width

        self._update_canvas()

    def update_numeradora_style(self, num_id: int, style_name: str):
        """
        Actualiza el estilo de texto de una numeradora

        Args:
            num_id: ID de la numeradora
            style_name: Nombre del nuevo estilo de texto
        """
        print(
            f"[VIEWER_UPDATE_STYLE] ===== INICIO ===== num_id={num_id}, style_name={style_name}"
        )
        print(
            f"[VIEWER_UPDATE_STYLE] Numeradoras disponibles: {list(self.numeradoras.keys())}"
        )

        if num_id not in self.numeradoras:
            print(f"[VIEWER_UPDATE_STYLE] ¡ERROR! Numeradora {num_id} no encontrada")
            return

        print(
            f"[VIEWER_UPDATE_STYLE] ANTES: text_style_name = {self.numeradoras[num_id]['data'].get('text_style_name')}"
        )
        self.numeradoras[num_id]["data"]["text_style_name"] = style_name
        print(
            f"[VIEWER_UPDATE_STYLE] DESPUÉS: text_style_name = {self.numeradoras[num_id]['data'].get('text_style_name')}"
        )
        print(
            f"[VIEWER_UPDATE_STYLE] Numeradora {num_id} actualizada con estilo '{style_name}'"
        )
        print(f"[VIEWER_UPDATE_STYLE] ===== Llamando _redraw_all =====")

        # Redibujar para aplicar el nuevo estilo
        self._redraw_all()

    def remove_numeradora(self, num_id):
        """Elimina una numeradora del visor"""
        if num_id not in self.numeradoras:
            return

        # Si era la selección actual, limpiar
        if self.selected_id == num_id:
            self.selected_id = None
            self._update_fine_adjust_visibility()

        # Eliminar del diccionario
        del self.numeradoras[num_id]

        # Redibujar todo (los shapes se generan dinámicamente)
        self._redraw_all(force=True)

    def get_numeradora_data(self, num_id):
        """
        Obtiene todos los datos de una numeradora

        Args:
            num_id: ID de la numeradora

        Returns:
            Diccionario con los datos de la numeradora o None si no existe
        """
        if num_id not in self.numeradoras:
            return None

        return self.numeradoras[num_id]["data"].copy()

    def add_barcode(
        self,
        x=None,
        y=None,
        value="",
        symbology="code128",
        bar_width=80.0,
        bar_height=30.0,
        rotation="0°",
        alignment="izquierda",
        color="#000000",
        color_cmyk=None,
        color_space="RGB",
        color_name="",
        color_tint=100.0,
        text_color="#000000",
        text_color_cmyk=None,
        text_color_space="RGB",
        text_color_name="",
        text_color_tint=100.0,
        value_source="fixed",
        mask="",
        error_correction="M",
        barcode_font_family="OCR-B",
        barcode_font_size=13.0,
        itf14_quiet_zone_mm=10.16,
        itf14_bearer_thickness_mm=4.8,
        itf14_bearer_sides="4",
        itf14_gtin_type="gtin14",
        itf14_indicator="1",
        itf14_printer_type="flexografia",
        itf14_hri_gap_mm=2.0,
        itf14_hri_position="below",
        code39_hri_gap_mm=2.0,
        code39_hri_position="below",
        code128_hri_gap_mm=2.0,
        code128_hri_position="below",
        ean5_hri_gap_mm=2.0,
        isbn13_show_title="Sí",
        pdf417_height=None,
        datamatrix_width=20.0,
        datamatrix_height=20.0,
        datamatrix_format="",
        datamatrix_hri_gap_mm=2.0,
        datamatrix_hri_position="below",
        datamatrix_hri_align="bottom_center",
        datamatrix_hri_line_spacing=1.0,
        datamatrix_del_open="",
        datamatrix_del_close="",
        datamatrix_del_close_newline: bool = False,
        qr_hri_gap_mm=2.0,
        qr_hri_position="below",
        qr_hri_align="bottom_center",
        qr_hri_line_spacing=1.0,
        qr_del_open="",
        qr_del_close="|",
        qr_del_close_newline: bool = False,
        pdf417_hri_gap_mm=2.0,
        pdf417_hri_position="below",
        pdf417_hri_align="bottom_center",
        pdf417_hri_line_spacing=1.0,
        pdf417_del_open="",
        pdf417_del_close="|",
        pdf417_del_close_newline: bool = False,
        profile_name="",
        auto_select=True,
        barcode_id=None,
        locked=False,
    ):
        """Añade un barcode al viewer."""
        if barcode_id is None:
            barcode_id = self.next_barcode_id
            self.next_barcode_id += 1
        else:
            if barcode_id >= self.next_barcode_id:
                self.next_barcode_id = barcode_id + 1

        if x is None:
            x = self.canvas_width / 2
        if y is None:
            y = self.canvas_height / 2

        if color_cmyk is None:
            from ui.color_picker import hex2rgb, rgb_to_cmyk

            r, g, b = hex2rgb(color)
            color_cmyk = rgb_to_cmyk(r, g, b)

        if text_color_cmyk is None:
            from ui.color_picker import hex2rgb as _hex2rgb, rgb_to_cmyk as _rgb_to_cmyk

            r, g, b = _hex2rgb(text_color)
            text_color_cmyk = _rgb_to_cmyk(r, g, b)

        self.barcodes[barcode_id] = {
            "data": {
                "x": x,
                "y": y,
                "value": value,
                "symbology": symbology,
                "bar_width": bar_width,
                "bar_height": bar_height,
                "rotation": rotation,
                "alignment": alignment,
                "color": color,
                "color_cmyk": color_cmyk,
                "color_space": color_space,
                "color_name": color_name,
                "color_tint": color_tint,
                "text_color": text_color,
                "text_color_cmyk": text_color_cmyk,
                "text_color_space": text_color_space,
                "text_color_name": text_color_name,
                "text_color_tint": text_color_tint,
                "value_source": value_source,
                "mask": mask,
                "error_correction": error_correction,
                "barcode_font_family": barcode_font_family,
                "barcode_font_size": barcode_font_size,
                "itf14_quiet_zone_mm": itf14_quiet_zone_mm,
                "itf14_bearer_thickness_mm": itf14_bearer_thickness_mm,
                "itf14_bearer_sides": itf14_bearer_sides,
                "itf14_gtin_type": itf14_gtin_type,
                "itf14_indicator": itf14_indicator,
                "itf14_printer_type": itf14_printer_type,
                "itf14_hri_gap_mm": itf14_hri_gap_mm,
                "itf14_hri_position": itf14_hri_position,
                "code39_hri_gap_mm": code39_hri_gap_mm,
                "code39_hri_position": code39_hri_position,
                "code128_hri_gap_mm": code128_hri_gap_mm,
                "code128_hri_position": code128_hri_position,
                "ean5_hri_gap_mm": ean5_hri_gap_mm,
                "isbn13_show_title": isbn13_show_title,
                "pdf417_height": pdf417_height,
                "datamatrix_width": datamatrix_width,
                "datamatrix_height": datamatrix_height,
                "datamatrix_format": datamatrix_format,
                "datamatrix_hri_gap_mm": datamatrix_hri_gap_mm,
                "datamatrix_hri_position": datamatrix_hri_position,
                "datamatrix_hri_align": datamatrix_hri_align,
                "datamatrix_hri_line_spacing": datamatrix_hri_line_spacing,
                "datamatrix_del_open": datamatrix_del_open,
                "datamatrix_del_close": datamatrix_del_close,
                "datamatrix_del_close_newline": datamatrix_del_close_newline,
                "qr_hri_gap_mm": qr_hri_gap_mm,
                "qr_hri_position": qr_hri_position,
                "qr_hri_align": qr_hri_align,
                "qr_hri_line_spacing": qr_hri_line_spacing,
                "qr_del_open": qr_del_open,
                "qr_del_close": qr_del_close,
                "qr_del_close_newline": qr_del_close_newline,
                "pdf417_hri_gap_mm": pdf417_hri_gap_mm,
                "pdf417_hri_position": pdf417_hri_position,
                "pdf417_hri_align": pdf417_hri_align,
                "pdf417_hri_line_spacing": pdf417_hri_line_spacing,
                "pdf417_del_open": pdf417_del_open,
                "pdf417_del_close": pdf417_del_close,
                "pdf417_del_close_newline": pdf417_del_close_newline,
                "profile_name": profile_name,
                "locked": locked,
            }
        }

        self._redraw_all(force=True)
        if auto_select:
            self._select_barcode(barcode_id)
        return barcode_id

    def remove_barcode(self, barcode_id):
        if barcode_id not in self.barcodes:
            return
        barcode_data = self.barcodes[barcode_id]
        # Remove container via stored reference
        qr_container = barcode_data.get("qr_container")
        if qr_container and qr_container in self.text_stack.controls:
            self.text_stack.controls.remove(qr_container)
        ean13_container = barcode_data.get("ean13_container")
        if ean13_container and ean13_container in self.text_stack.controls:
            self.text_stack.controls.remove(ean13_container)
        ean8_container = barcode_data.get("ean8_container")
        if ean8_container and ean8_container in self.text_stack.controls:
            self.text_stack.controls.remove(ean8_container)
        ean5_container = barcode_data.get("ean5_container")
        if ean5_container and ean5_container in self.text_stack.controls:
            self.text_stack.controls.remove(ean5_container)
        isbn13_container = barcode_data.get("isbn13_container")
        if isbn13_container and isbn13_container in self.text_stack.controls:
            self.text_stack.controls.remove(isbn13_container)
        upca_container = barcode_data.get("upca_container")
        if upca_container and upca_container in self.text_stack.controls:
            self.text_stack.controls.remove(upca_container)
        upce_container = barcode_data.get("upce_container")
        if upce_container and upce_container in self.text_stack.controls:
            self.text_stack.controls.remove(upce_container)
        itf14_container = barcode_data.get("itf14_container")
        if itf14_container and itf14_container in self.text_stack.controls:
            self.text_stack.controls.remove(itf14_container)
        code39_container = barcode_data.get("code39_container")
        if code39_container and code39_container in self.text_stack.controls:
            self.text_stack.controls.remove(code39_container)
        pdf417_container = barcode_data.get("pdf417_container")
        if pdf417_container and pdf417_container in self.text_stack.controls:
            self.text_stack.controls.remove(pdf417_container)
        if (
            not qr_container
            and not ean13_container
            and not ean8_container
            and not ean5_container
            and not isbn13_container
            and not upca_container
            and not upce_container
            and not itf14_container
            and not code39_container
            and not pdf417_container
        ):
            # Fallback: buscar por data (numeradora containers)
            for i in range(len(self.text_stack.controls) - 1, -1, -1):
                ctrl = self.text_stack.controls[i]
                if str(getattr(ctrl, "data", "")) == str(barcode_id):
                    self.text_stack.controls.pop(i)
                    break
        del self.barcodes[barcode_id]
        if self.selected_barcode_id == barcode_id:
            self.selected_barcode_id = None
        self._redraw_all(force=True)

    def set_barcode_value(self, barcode_id, value, redraw=True):
        """Cambia el valor mostrado por un barcode."""
        if barcode_id not in self.barcodes:
            return
        data = self.barcodes[barcode_id]["data"]
        if data.get("value") != value:
            data["value"] = value
            self.invalidate_barcode_render_cache(barcode_id)
        if redraw:
            self._redraw_all(force=True)

    def get_barcode_data(self, barcode_id):
        if barcode_id not in self.barcodes:
            return None
        return self.barcodes[barcode_id]["data"]

    def get_barcode_ids_by_profile(self, profile_name):
        return [bid for bid, bc in self.barcodes.items()
                if bc["data"].get("profile_name") == profile_name]

    def invalidate_datamatrix_cache(self, barcode_id):
        entry = self.barcodes.get(barcode_id)
        if entry:
            entry.pop("datamatrix_base64", None)
            entry.pop("dm_canvas_w_mm", None)
            entry.pop("dm_canvas_h_mm", None)
            entry.pop("dm_code_h_mm", None)
            for _k in list(entry):
                if _k.startswith("datamatrix_base64_"):
                    del entry[_k]

    def invalidate_barcode_render_cache(self, barcode_id):
        entry = self.barcodes.get(barcode_id)
        if not entry:
            return
        entry.pop("datamatrix_base64", None)
        entry.pop("dm_canvas_w_mm", None)
        entry.pop("dm_canvas_h_mm", None)
        entry.pop("dm_code_h_mm", None)
        entry.pop("qr_base64", None)
        entry.pop("qr_canvas_w_mm", None)
        entry.pop("qr_canvas_h_mm", None)
        entry.pop("qr_code_h_mm", None)
        entry.pop("pdf417_base64", None)
        entry.pop("pdf417_canvas_w_mm", None)
        entry.pop("pdf417_canvas_h_mm", None)
        entry.pop("pdf417_code_h_mm", None)
        for _k in list(entry):
            if _k.startswith("datamatrix_base64_") or _k.startswith(
                "pdf417_base64_"
            ) or _k.startswith("qr_base64_"):
                del entry[_k]

    def _compute_text_render_data(
        self,
        x_viewer,
        y_viewer,
        alignment,
        rotation_degrees,
        display_text,
        prefix,
        suffix,
        font_size_pt,
        font_family,
        font_weight,
        font_italic,
        main_color,
        prefix_color,
        suffix_color,
        letter_spacing=0.0,
        prefix_suffix_spacing=0.0,
        text_style_metrics=None,
        resolved_font_path=None,
        line_spacing=1.0,
    ):
        """Calcula posicionamiento y spans para un texto segmentado (numeradora o variable text).
        Utiliza la misma logica de posicionamiento preciso que las numeradoras (baseline, bearing,
        right-anchor, ajustes de rotacion, Windows).
        Devuelve un dict con las claves necesarias para construir el ft.Container final.
        """
        adjusted_font_size = font_size_pt * FONT_PT_TO_MM * self.current_scale

        metrics = text_style_metrics
        if metrics and isinstance(metrics, dict) and font_size_pt > 0:
            baseline_to_top_pt = metrics.get("baseline_to_top", 0)
            baseline_to_bottom_pt = metrics.get("baseline_to_bottom", 0)
            left_bearing_pt = metrics.get("left_bearing", 0)

            REFERENCE_EXTRACTION_SIZE = 12
            baseline_ratio = baseline_to_top_pt / REFERENCE_EXTRACTION_SIZE
            baseline_bottom_ratio = baseline_to_bottom_pt / REFERENCE_EXTRACTION_SIZE
            left_bearing_ratio = left_bearing_pt / REFERENCE_EXTRACTION_SIZE

            ascent_ratio = metrics.get("ascent_ratio", baseline_ratio)
            descent_ratio = metrics.get("descent_ratio", baseline_bottom_ratio)

            metric_height_ratio = ascent_ratio + descent_ratio
            target_height_ratio = metric_height_ratio
            top_padding_ratio = (target_height_ratio - metric_height_ratio) / 2.0
            total_baseline_ratio = top_padding_ratio + ascent_ratio

            real_bearing_ratio = max(left_bearing_ratio, 0.0)

            if alignment == "izquierda":
                # VT: para texto libre, la correccion fija global puede sobrecompensar
                # y hacer que el primer glifo invada la guia. Usamos solo bearing real.
                final_ratio = real_bearing_ratio
                bearing_adj = adjusted_font_size * final_ratio
            elif alignment == "centro":
                final_ratio = (real_bearing_ratio / 2.0) + VISUAL_CORRECTION_CENTER
                bearing_adj = adjusted_font_size * final_ratio
            else:
                final_ratio = 0.0
                bearing_adj = 0.0

            left_bearing_offset = bearing_adj
            baseline_offset = adjusted_font_size * total_baseline_ratio

            from utils.constants import (
                VISUAL_BASELINE_ADJUST_0,
                VISUAL_BASELINE_ADJUST_90,
                VISUAL_BASELINE_ADJUST_180,
                VISUAL_BASELINE_ADJUST_270,
            )

            if rotation_degrees == 0:
                baseline_offset += adjusted_font_size * VISUAL_BASELINE_ADJUST_0
            elif rotation_degrees == 90:
                baseline_offset += adjusted_font_size * VISUAL_BASELINE_ADJUST_90
            elif rotation_degrees == 180:
                baseline_offset += adjusted_font_size * VISUAL_BASELINE_ADJUST_180
            elif rotation_degrees == 270:
                baseline_offset += adjusted_font_size * VISUAL_BASELINE_ADJUST_270

        else:
            ascent_ratio = 0.8
            descent_ratio = 0.2
            metric_height_ratio = 1.0
            target_height_ratio = 1.0
            top_padding_ratio = 0.0
            total_baseline_ratio = top_padding_ratio + ascent_ratio
            baseline_offset = adjusted_font_size * total_baseline_ratio
            left_bearing_offset = 0
            bearing_adj = 0

        bearing_adj = left_bearing_offset

        if rotation_degrees == 0:
            offset_x = -bearing_adj
            offset_y = -baseline_offset
        elif rotation_degrees == 90:
            offset_x = baseline_offset
            offset_y = -bearing_adj
        elif rotation_degrees == 180:
            offset_x = bearing_adj
            offset_y = baseline_offset
        elif rotation_degrees == 270:
            offset_x = -baseline_offset
            offset_y = bearing_adj
        else:
            offset_x = 0
            offset_y = 0

        # Interlineado: 0 = tintas tocándose (leading real neutro). Suma en unidades de cuerpo.
        # El baseline se mantiene intacto (solo cambia el avance entre líneas).
        _ls = max(float(line_spacing or 0.0), 0.0)
        target_height_ratio += _ls

        text_spans = []
        if prefix:
            text_spans.append(
                ft.TextSpan(
                    prefix,
                    ft.TextStyle(
                        size=adjusted_font_size,
                        color=prefix_color,
                        font_family=font_family,
                        weight=font_weight,
                        italic=font_italic,
                        height=target_height_ratio,
                    ),
                )
            )

        text_spans.append(
            ft.TextSpan(
                (
                    display_text[len(prefix) : len(display_text) - len(suffix)]
                    if (prefix or suffix)
                    else display_text
                ),
                ft.TextStyle(
                    size=adjusted_font_size,
                    color=main_color,
                    font_family=font_family,
                    weight=font_weight,
                    italic=font_italic,
                    letter_spacing=letter_spacing,
                    height=target_height_ratio,
                ),
            )
        )

        if suffix:
            text_spans.append(
                ft.TextSpan(
                    suffix,
                    ft.TextStyle(
                        size=adjusted_font_size,
                        color=suffix_color,
                        font_family=font_family,
                        weight=font_weight,
                        italic=font_italic,
                        height=target_height_ratio,
                    ),
                )
            )

        text_width_pt = 0.0
        font = None
        try:
            if resolved_font_path and os.path.exists(resolved_font_path):
                font = fitz.Font(fontfile=resolved_font_path)
            else:
                font = fitz.Font(fontname=font_family)
        except Exception:
            font = None

        if font:
            number_start = len(prefix)
            number_end = number_start + len(display_text) - len(prefix) - len(suffix)
            char_index = 0
            for i, ch in enumerate(display_text):
                text_width_pt += float(font.text_length(ch, fontsize=font_size_pt))
                if letter_spacing != 0 and number_start <= i < (number_end - 1):
                    text_width_pt += letter_spacing
        else:
            # Fallback: ajustar multiplicador según peso e italic para mejor aproximación
            _weight_val = getattr(font_weight, "value", 400)
            if isinstance(_weight_val, str):
                _wt = _weight_val.lower().replace("w", "")
                _weight_val = {"normal": 400, "bold": 700}.get(
                    _wt, int(_wt) if _wt.isdigit() else 400
                )
            _fallback_mult = {
                100: 0.45,
                200: 0.50,
                300: 0.55,
                400: 0.60,
                500: 0.65,
                600: 0.68,
                700: 0.72,
                800: 0.76,
                900: 0.80,
            }.get(_weight_val, 0.60)
            if font_italic:
                _fallback_mult *= 1.03
            text_width_pt = len(display_text) * font_size_pt * _fallback_mult

        real_text_width = text_width_pt * FONT_PT_TO_MM * self.current_scale

        right_anchor_width = real_text_width
        if alignment == "derecha":
            try:
                fp = resolved_font_path
                if fp and os.path.exists(fp):
                    from utils.metrics_analisys import DEFAULT_FONT_METRICS

                    number_start = len(prefix)
                    number_end = (
                        number_start + len(display_text) - len(prefix) - len(suffix)
                    )
                    pen = 0.0
                    max_right = 0.0
                    for i, ch in enumerate(display_text):
                        cm = DEFAULT_FONT_METRICS.measure_text(
                            str(fp), font_size_pt, ch
                        )
                        cl = float(cm.get("left_bearing", 0.0))
                        cw = float(cm.get("width", 0.0))
                        cr = pen + cl + cw
                        if cr > max_right:
                            max_right = cr
                        if font:
                            adv = float(font.text_length(ch, fontsize=font_size_pt))
                        else:
                            adv = cw
                        pen += adv
                        if letter_spacing != 0 and number_start <= i < (number_end - 1):
                            pen += letter_spacing
                    right_ink = max_right
                    right_anchor_width = right_ink * FONT_PT_TO_MM * self.current_scale
            except Exception:
                right_anchor_width = real_text_width

        if alignment == "derecha" and RIGHT_ANCHOR_VISUAL_COMP_PT != 0:
            comp = RIGHT_ANCHOR_VISUAL_COMP_PT * FONT_PT_TO_MM * self.current_scale
            right_anchor_width = max(0.0, right_anchor_width - comp)

        container_width = real_text_width * 1.1
        if alignment == "derecha":
            container_width = right_anchor_width

        if platform.system() == "Windows":
            pad = max(
                adjusted_font_size * WINDOWS_TEXT_WIDTH_PADDING_RATIO,
                WINDOWS_TEXT_WIDTH_PADDING_MIN_PX,
            )
            container_width += pad

        align_shift = 0
        if alignment == "centro":
            # Centro VT: anclar por el ancho efectivo del contenedor.
            align_shift = -container_width / 2
        elif alignment == "derecha":
            # Derecha VT: con TextAlign.RIGHT el final visual del texto coincide con
            # el borde derecho del contenedor, asi que el anclaje debe usar ese ancho.
            align_shift = -container_width

        rad = math.radians(rotation_degrees)
        disp_x = math.cos(rad)
        disp_y = math.sin(rad)
        shift_x = align_shift * disp_x
        shift_y = align_shift * disp_y

        final_left = x_viewer + offset_x + shift_x
        final_top = y_viewer + offset_y + shift_y

        return {
            "text_spans": text_spans,
            "final_left": final_left,
            "final_top": final_top,
            "container_width": container_width,
            "container_height": adjusted_font_size * target_height_ratio,
            "adjusted_font_size": adjusted_font_size,
            "baseline_offset": baseline_offset,
            "bearing_adj": bearing_adj,
            "real_text_width": real_text_width,
            "rad": rad,
            "target_height_ratio": target_height_ratio,
            "font_weight": font_weight,
            "font_italic": font_italic,
            "main_color": main_color,
            "offset_x": offset_x,
            "offset_y": offset_y,
        }

    def add_variable_text(
        self,
        x=None,
        y=None,
        text="",
        font_family="Arial",
        font_style="Regular",
        font_size=12.0,
        color="#000000",
        prefix="",
        suffix="",
        alignment="izquierda",
        rotation="0°",
        auto_select=True,
        variable_text_id=None,
        profile_name="",
        font_path=None,
        text_alignment="izquierda",
        letter_spacing=0.0,
        prefix_suffix_spacing=0.0,
        metricas=None,
        value_source="sample",
        excel_column="",
        color_tint=100.0,
        color_space="RGB",
        locked=False,
        line_spacing=1.0,
        anchor=None,
    ):
        """Añade un texto variable al viewer.
        alignment: posicion del bloque respecto a la guia (legacy, se migra a anchor)
        text_alignment: alineacion del texto DENTRO de la caja (del perfil)
        anchor: posicion (9 anclas) de la caja respecto a la guia (nuevo)
        """
        if variable_text_id is None:
            variable_text_id = self.next_variable_text_id
            self.next_variable_text_id += 1
        else:
            if variable_text_id >= self.next_variable_text_id:
                self.next_variable_text_id = variable_text_id + 1

        if x is None:
            x = self.canvas_width / 2
        if y is None:
            y = self.canvas_height / 2

        # Migración legacy alignment (3) → anchor (9): fila central.
        if anchor is None:
            anchor = _align_to_anchor(alignment)

        self.variable_texts[variable_text_id] = {
            "data": {
                "x": x,
                "y": y,
                "text": text,
                "font_family": font_family,
                "font_style": font_style,
                "font_size": font_size,
                "color": color,
                "color_tint": color_tint,
                "color_space": color_space,
                "prefix": prefix,
                "suffix": suffix,
                "alignment": alignment,
                "anchor": anchor,
                "rotation": rotation,
                "profile_name": profile_name,
                "resolved_font_path": font_path,
                "text_alignment": text_alignment,
                "letter_spacing": letter_spacing,
                "prefix_suffix_spacing": prefix_suffix_spacing,
                "metricas": metricas,
                "value_source": value_source,
                "excel_column": excel_column,
                "locked": locked,
                "line_spacing": line_spacing,
            }
        }

        self._redraw_all(force=True)
        if auto_select:
            self._select_variable_text(variable_text_id)
        return variable_text_id

    def remove_variable_text(self, variable_text_id):
        if variable_text_id not in self.variable_texts:
            return
        del self.variable_texts[variable_text_id]
        if self.selected_variable_text_id == variable_text_id:
            self.selected_variable_text_id = None
        # Remover el container del text_stack directamente
        for i in range(len(self.text_stack.controls) - 1, -1, -1):
            ctrl = self.text_stack.controls[i]
            if getattr(ctrl, "data", None) == variable_text_id:
                self.text_stack.controls.pop(i)
                break
        self._redraw_all(force=True)

    def get_variable_text_data(self, variable_text_id):
        if variable_text_id not in self.variable_texts:
            return None
        return self.variable_texts[variable_text_id]["data"]

    def set_item_locked(self, item_id, locked):
        """Establece el estado bloqueado/desbloqueado de cualquier tipo de elemento."""
        if item_id in self.numeradoras:
            self.numeradoras[item_id]["data"]["locked"] = locked
        elif item_id in self.barcodes:
            self.barcodes[item_id]["data"]["locked"] = locked
        elif item_id in self.variable_texts:
            self.variable_texts[item_id]["data"]["locked"] = locked
        else:
            return
        self._redraw_all(force=True)

    def set_variable_text_value(self, variable_text_id, value, redraw=True):
        """Cambia el texto mostrado por un texto variable."""
        if variable_text_id not in self.variable_texts:
            return
        self.variable_texts[variable_text_id]["data"]["text"] = value
        if redraw:
            self._redraw_all(force=True)

    def _select_variable_text(self, variable_text_id):
        _old_bc = self.selected_barcode_id
        _old_num = self.selected_id
        _old_vt = self.selected_variable_text_id
        self.selected_variable_text_id = variable_text_id
        self.selected_id = None
        self.selected_barcode_id = None
        self._update_fine_adjust_visibility()
        if _old_bc is not None:
            self._update_selection_visual(_old_bc, "barcode", False)
        if _old_num is not None:
            self._update_selection_visual(_old_num, "number", False)
        if _old_vt is not None and _old_vt != variable_text_id:
            self._update_selection_visual(_old_vt, "variable_text", False)
        self._update_selection_visual(variable_text_id, "variable_text", True)
        if self.on_select_callback:
            self.on_select_callback(variable_text_id)

    def _update_selection_visual(self, element_id, element_type, selected):
        """Cambia color del punto de control y guías de UN elemento (barcode/numeradora/VT)
        sin regenerar bitmaps."""
        with self._redraw_lock:
            if element_type == "barcode":
                container = self.barcodes
            elif element_type == "number":
                container = self.numeradoras
            elif element_type == "variable_text":
                container = self.variable_texts
            else:
                return
            el = container.get(element_id)
            if el is None:
                return
            is_locked = el["data"].get("locked", False)
            color = COLOR_LOCKED if is_locked else (COLOR_ACTIVO if selected else COLOR_INACTIVO)
            cp = el.get("control_point_shape")
            if cp is not None:
                cp.paint = ft.Paint(color=color, style=ft.PaintingStyle.FILL)
            for gk in ("guide_v_control", "guide_h_control"):
                g = el.get(gk)
                if g is not None:
                    g.paint = ft.Paint(stroke_width=0, color=color)
            self.canvas.shapes = self.canvas_shapes
            self._safe_page_update(getattr(self, "canvas", None), "sel_vis")

    def _select_barcode(self, barcode_id):
        _old_bc = self.selected_barcode_id
        _old_num = self.selected_id
        _old_vt = self.selected_variable_text_id
        self.selected_barcode_id = barcode_id
        self.selected_id = None
        self.selected_variable_text_id = None
        self._update_fine_adjust_visibility()
        if _old_bc is not None and _old_bc != barcode_id:
            self._update_selection_visual(_old_bc, "barcode", False)
        if _old_num is not None:
            self._update_selection_visual(_old_num, "number", False)
        if _old_vt is not None:
            self._update_selection_visual(_old_vt, "variable_text", False)
        self._update_selection_visual(barcode_id, "barcode", True)
        if self.on_select_callback:
            try:
                self.on_select_callback(barcode_id)
            except AssertionError:
                pass

    def _prerotated_b64(self, barcode_data, base_key, b64, rot):
        """Pre-rota una imagen b64 y la cachea bajo f'{base_key}_{rot}' (patrón QR).
        Con rot == 0 devuelve b64 sin tocar (no crea entrada de cache)."""
        if rot in (0, None):
            return b64
        key = f"{base_key}_{rot}"
        if key not in barcode_data:
            from PIL import Image

            img = Image.open(io.BytesIO(base64.b64decode(b64)))
            img = img.rotate(-rot, expand=True)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            barcode_data[key] = base64.b64encode(buf.getvalue()).decode()
        return barcode_data[key]

    def _generate_pdf417_base64(
        self,
        value: str,
        fill_color: str,
        bar_width: float,
        target_height: float = None,
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
    ) -> tuple:
        """Generate PDF417 barcode as base64 PNG with optional HRI text (unrotated).

        Returns (b64, canvas_w_mm, canvas_h_mm, code_h_mm) or (None, w, h, h) on error.
        """
        try:
            from pdf417gen import render_image as pdf417_render
            from utils.barcode_module import (
                _pdf417_encode_safe,
                _pdf417_barcode_size,
                _build_hri_canvas,
                _format_hri_lines,
            )

            encode_value = (
                value.replace(del_close, "\n")
                if close_as_newline and del_close and value
                else value
            )
            codes, _ = _pdf417_encode_safe(encode_value, columns=6)
            barcode_w_mod, _ = _pdf417_barcode_size(codes)
            PX_PER_MM = 300.0 / 25.4
            module_width = bar_width / barcode_w_mod if barcode_w_mod > 0 else 0.3
            scale = max(3, int(round(module_width * PX_PER_MM)))
            img = pdf417_render(
                codes,
                scale=scale,
                ratio=3,
                padding=0,
                fg_color=fill_color,
                bg_color="#FFFFFF",
            )
            # Redimensionar a mm EXACTOS (patrón DataMatrix): ancho = bar_width, alto = target_height
            target_w_px = int(round(bar_width * PX_PER_MM))
            if target_height is not None and target_height > 0:
                target_h_px = int(round(target_height * PX_PER_MM))
            else:
                target_h_px = int(round(img.height * target_w_px / img.width))
            if (target_w_px, target_h_px) != img.size:
                img = img.resize((target_w_px, target_h_px), 0)
            code_h_mm = target_h_px / PX_PER_MM
            img = img.convert("RGB")
            hri_lines = _format_hri_lines(
                value, font_family, font_size, bar_width, del_open, del_close, "pdf417"
            )
            return _build_hri_canvas(
                img, hri_lines, bar_width, code_h_mm, font_family, font_size,
                hri_gap_mm, hri_position, hri_align, hri_line_spacing, text_color,
            )
        except Exception:
            return None, bar_width, bar_width, bar_width

    def set_zoom(self, zoom_value):
        """
        Establece el nivel de zoom MULTIPLICATIVO del usuario (1.0-5.0x)
        El zoom final = zoom_automático × zoom_usuario

        Args:
            zoom_value: Factor de zoom multiplicativo (1.0-5.0)
        """
        old_scale = self.current_scale

        # Factor de zoom del usuario (1.0 a 5.0)
        user_zoom_factor = max(MIN_ZOOM, min(MAX_ZOOM, float(zoom_value)))

        # Calcular zoom final = zoom_auto × zoom_usuario
        zoom_final = self.initial_scale * user_zoom_factor

        # Aplicar límites
        zoom_final = max(self.min_scale, min(self.max_scale, zoom_final))

        # Fast-path eliminado: set_zoom_live puede dejar current_scale al valor final
        # sin haber reconstruido text_stack (rate limiter de 20ms), así que aquí
        # siempre se recalcula offset + _redraw_all() para renderizar a escala final.
        print(f"[ZOOM MANUAL] Botón +/- presionado")
        print(f"[ZOOM MANUAL]   - Zoom usuario: {user_zoom_factor:.3f}x")
        print(f"[ZOOM MANUAL]   - Zoom automático: {self.initial_scale:.3f}")
        print(f"[ZOOM MANUAL]   - Zoom final: {zoom_final:.3f}")
        print(f"[ZOOM MANUAL]   - Scale anterior: {old_scale:.3f}")

        # Mantener en la vista el mismo punto central del viewer al cambiar el zoom
        try:
            center_vx = self.viewer_width / 2.0
            center_vy = self.viewer_height / 2.0
            # Coordenadas en mm del punto central antes del cambio
            center_mm_x, center_mm_y = self._transform_viewer_to_page_coords(
                center_vx, center_vy
            )
        except Exception:
            center_mm_x, center_mm_y = None, None

        # Aplicar zoom
        self.current_scale = zoom_final

        # Recalcular límites del canvas ampliado basándose en la página escalada
        self._update_canvas_limits()

        # Si pudimos obtener el punto central antes, ajustar offsets para que el mismo
        # punto en mm permanezca centrado tras el cambio de zoom (evita recentrar)
        if center_mm_x is not None:
            try:
                # Convertir el punto central en mm a px sin escala
                px_x = mm_to_screen_pixels(center_mm_x)
                px_y = mm_to_screen_pixels(center_mm_y)

                # Calcular page_start (parte izquierda/arriba de la página escalada)
                page_start_x = (
                    self.big_canvas_width - self.canvas_width * self.current_scale
                ) / 2
                page_start_y = (
                    self.big_canvas_height - self.canvas_height * self.current_scale
                ) / 2

                # Nuevo offset para que el punto px_x * current_scale quede en center_vx
                desired_offset_x = center_vx - (
                    page_start_x + px_x * self.current_scale
                )
                desired_offset_y = center_vy - (
                    page_start_y + px_y * self.current_scale
                )

                # Aplicar clamp a límites
                self.offset_x = max(
                    self.min_offset_x, min(self.max_offset_x, desired_offset_x)
                )
                self.offset_y = max(
                    self.min_offset_y, min(self.max_offset_y, desired_offset_y)
                )
            except Exception:
                pass

        # Redibujar todo con el nuevo zoom
        self._redraw_all()

        # Notificar cambio de zoom si hay callback
        if self.on_zoom_change_callback:
            zoom_percent = int(self.current_scale * 100)
            self.on_zoom_change_callback(zoom_percent)

        print(
            f"[ZOOM MANUAL]   - Scale actual (después de aplicar): {self.current_scale:.3f}"
        )

    def set_zoom_live(self, zoom_value):
        """
        Aplicar un cambio de zoom ligero para previsualización en vivo.
        No realiza el recalculo completo de límites del canvas para mantener la
        interacción fluida durante el arrastre del slider.
        """
        # Factor de zoom del usuario (1.0 a 5.0)
        user_zoom_factor = max(MIN_ZOOM, min(MAX_ZOOM, float(zoom_value)))

        # Calcular zoom final = zoom_auto × zoom_usuario
        zoom_final = self.initial_scale * user_zoom_factor

        # Aplicar límites
        zoom_final = max(self.min_scale, min(self.max_scale, zoom_final))

        # Aplicar zoom ligero (sin recalculos pesados)
        self.current_scale = zoom_final

        # Redibujar solo la parte rápida (canvas y texto) para mantener FPS
        try:
            self._redraw_canvas_only()
        except Exception:
            # Fallback seguro a redibujado completo si ocurre algo inesperado
            try:
                self._redraw_all()
            except Exception:
                pass

    def reset_view(self):
        """Resetea la vista al centro inicial y zoom original"""
        self.current_scale = self.initial_scale * DEFAULT_ZOOM

        # Recalcular límites del canvas con la nueva escala
        self._update_canvas_limits()

        # Centrar la página escalada en el viewer
        # Calcular el tamaño de la página escalada
        scaled_page_width = self.canvas_width * self.current_scale
        scaled_page_height = self.canvas_height * self.current_scale

        # Centrar horizontalmente
        if scaled_page_width < self.viewer_width:
            # Si la página escalada es menor que el viewer, centrar
            self.offset_x = -(self.big_canvas_width - self.viewer_width) / 2
        else:
            # Si es más grande, empezar desde el borde izquierdo
            self.offset_x = -(self.big_canvas_width - self.viewer_width) / 2

        # Centrar verticalmente
        if scaled_page_height < self.viewer_height:
            # Si la página escalada es menor que el viewer, centrar
            self.offset_y = -(self.big_canvas_height - self.viewer_height) / 2
        else:
            # Si es más grande, empezar desde el borde superior
            self.offset_y = -(self.big_canvas_height - self.viewer_height) / 2

        # Asegurar que los offsets están dentro de los límites
        self.offset_x = max(self.min_offset_x, min(self.max_offset_x, self.offset_x))
        self.offset_y = max(self.min_offset_y, min(self.max_offset_y, self.offset_y))

        print(f"[RESET VIEW] Zoom vuelto a: {self.current_scale:.3f}")
        print(
            f"[RESET VIEW] Página escalada: {scaled_page_width:.0f}x{scaled_page_height:.0f}px"
        )
        print(
            f"[RESET VIEW] Canvas ampliado: {self.big_canvas_width}x{self.big_canvas_height}px"
        )
        print(
            f"[RESET VIEW] Offset centrado: x={self.offset_x:.1f}, y={self.offset_y:.1f}"
        )

        self._redraw_all()

    def set_viewer_size(self, width, height):
        """
        Actualiza las dimensiones del VIEWER (espacio de UI) y recalcula el zoom
        También actualiza las reglas si están habilitadas

        Args:
            width: Ancho del VIEWER en píxeles (espacio de UI disponible)
            height: Alto del VIEWER en píxeles (espacio de UI disponible)
        """
        old_width = self.viewer_width
        old_height = self.viewer_height

        self.viewer_width = width
        self.viewer_height = height

        # Solo recalcular si realmente cambió
        if old_width != width or old_height != height:
            # Recalcular canvas ampliado
            self.big_canvas_width = int(self.viewer_width * 2.5)
            self.big_canvas_height = int(self.viewer_height * 2.5)

            # Recalcular límites del pan
            self.max_offset_x = 0
            self.min_offset_x = -(self.big_canvas_width - self.viewer_width)
            self.max_offset_y = 0
            self.min_offset_y = -(self.big_canvas_height - self.viewer_height)

            # Resetear offset al centro
            self.offset_x = -(self.big_canvas_width - self.viewer_width) / 2
            self.offset_y = -(self.big_canvas_height - self.viewer_height) / 2
            self.initial_offset_x = self.offset_x
            self.initial_offset_y = self.offset_y

            # Actualizar dimensiones del zoom_container
            self.zoom_container.width = width
            self.zoom_container.height = height

            # Actualizar dimensiones del canvas y stack
            self.canvas.width = self.big_canvas_width
            self.canvas.height = self.big_canvas_height
            self.stack.width = self.big_canvas_width
            self.stack.height = self.big_canvas_height

            # Actualizar dimensiones de las reglas si están habilitadas
            if ENABLE_RULERS:
                self.ruler_horizontal_canvas.width = width
                self.ruler_horizontal_container.width = width
                # Ajustar la altura de la regla vertical restando la esquina
                vert_h = max(0, height - self.corner_size)
                self.ruler_vertical_canvas.height = vert_h
                self.ruler_vertical_container.height = vert_h

            # Recalcular zoom inicial para que el canvas quepa en el nuevo espacio
            new_scale = self._calculate_initial_scale()
            self.initial_scale = new_scale
            self.current_scale = new_scale * DEFAULT_ZOOM

            # Recalcular límites de zoom
            self.min_scale = max(0.1, self.initial_scale * 0.5)
            self.max_scale = self.initial_scale * MAX_ZOOM

            print(f"[RESIZE] Nuevo tamaño de viewer: {width}x{height}px")
            print(
                f"[RESIZE] Canvas ampliado: {self.big_canvas_width}x{self.big_canvas_height}px"
            )
            print(f"[RESIZE] Zoom inicial: {self.current_scale:.3f}")

            # Redibujar todo
            self._redraw_all()

            # Forzar actualización visual
            if _safe_page(self) is not None:
                self.page.update()

    def set_page_size(self, width_mm, height_mm, bleed_mm=0.0):
        """
        Cambia el tamaño de la página (incluyendo sangre)

        Args:
            width_mm: Ancho total en mm (página + sangre*2)
            height_mm: Alto total en mm (página + sangre*2)
            bleed_mm: Sangre en mm
        """
        self.page_width_mm = width_mm - (bleed_mm * 2)  # Tamaño neto de página
        self.page_height_mm = height_mm - (bleed_mm * 2)
        self.bleed_mm = bleed_mm

        # Actualizar canvas width/height (en píxeles, tamaño total con sangre)
        self.canvas_width = mm_to_screen_pixels(width_mm)
        self.canvas_height = mm_to_screen_pixels(height_mm)

        # Recalcular zoom inicial y límites
        self.initial_scale = self._calculate_initial_scale()

        # Aplicar el nuevo zoom inicial
        self.current_scale = self.initial_scale * DEFAULT_ZOOM
        self.min_scale = max(0.1, self.initial_scale * 0.5)
        self.max_scale = self.initial_scale * MAX_ZOOM

        # Recentrar el canvas (compensar regla vertical si está habilitada)
        effective_viewer_width = self.viewer_width - (25 if ENABLE_RULERS else 0)
        self.offset_x = -(self.big_canvas_width - effective_viewer_width) / 2
        self.offset_y = -(self.big_canvas_height - self.viewer_height) / 2

        self._update_canvas_limits()

        # Redibujar todo
        self._redraw_all()
        self._update_canvas()

        print(
            f"[VIEWER] Tamaño actualizado: {width_mm}x{height_mm} mm (página: {self.page_width_mm}x{self.page_height_mm} + sangre: {bleed_mm})"
        )
        print(
            f"[VIEWER] Zoom recalculado: initial={self.initial_scale:.3f}, current={self.current_scale:.3f}"
        )

    def _get_clicked_numeradora(self, x, y, skip_locked=True):
        """
        Detecta si se hizo clic en un círculo de control

        Args:
            x, y: Coordenadas del clic EN MILÍMETROS (ya transformadas de viewer a página)
            skip_locked: Si True, salta ítems bloqueados (sigue buscando)

        Returns:
            ID de la numeradora si se hizo clic en su círculo, None si no
        """
        # Radio del círculo de control (tolerancia ajustada al zoom)
        tolerance_px = 8
        tolerance_mm = tolerance_px / self.current_scale

        print(
            f"[HIT TEST] Click en ({x:.2f}, {y:.2f}) mm, tolerancia={tolerance_mm:.2f} mm"
        )

        for num_id, num_data in self.numeradoras.items():
            circle_x = num_data["data"]["x"]
            circle_y = num_data["data"]["y"]  # en la baseline

            # Calcular distancia (en mm)
            distance = ((x - circle_x) ** 2 + (y - circle_y) ** 2) ** 0.5

            print(
                f"  Num {num_id}: círculo en ({circle_x:.2f}, {circle_y:.2f}), distancia={distance:.2f} mm"
            )

            if distance <= tolerance_mm:
                if skip_locked and num_data["data"].get("locked", False):
                    print(f"  → SKIP (bloqueado) {num_id}")
                    continue
                print(f"  → ¡HIT! Seleccionado {num_id}")
                return num_id

        print(f"  → MISS, ninguna numeradora encontrada")
        return None

    def _get_clicked_barcode(self, x, y, skip_locked=True):
        """Detecta si se hizo clic en un barcode (solo punto de control)"""
        tolerance_px = 8
        tolerance_mm = tolerance_px / self.current_scale

        for barcode_id, barcode_data in self.barcodes.items():
            bd = barcode_data["data"]
            if not bd.get("value", ""):
                continue
            circle_x = bd["x"]
            circle_y = bd["y"]

            # Check reference point (circle)
            distance = ((x - circle_x) ** 2 + (y - circle_y) ** 2) ** 0.5
            if distance <= tolerance_mm:
                if skip_locked and bd.get("locked", False):
                    continue
                return barcode_id

        return None

    def _get_clicked_variable_text(self, x, y, skip_locked=True):
        """Detecta si se hizo clic en un texto variable (en el punto de control)"""
        tolerance_px = 8
        tolerance_mm = tolerance_px / self.current_scale

        for vt_id, vt_data in self.variable_texts.items():
            vd = vt_data["data"]
            circle_x = vd["x"]
            circle_y = vd["y"]
            distance = ((x - circle_x) ** 2 + (y - circle_y) ** 2) ** 0.5
            if distance <= tolerance_mm:
                if skip_locked and vd.get("locked", False):
                    continue
                return vt_id
        return None

    def _get_canvas_coordinates(self, global_x, global_y):
        """
        Convierte coordenadas globales a coordenadas del canvas considerando zoom y pan

        Args:
            global_x, global_y: Coordenadas globales del evento

        Returns:
            (x, y): Coordenadas en el canvas
        """
        # Por ahora, asumimos que las coordenadas ya están ajustadas
        # En una implementación completa habría que considerar el zoom y pan del InteractiveViewer
        return global_x, global_y

    def build(self) -> ft.Control:
        """Retorna el control del visor con reglas (si están habilitadas)"""
        fine_adjust_margin = 8
        if ENABLE_RULERS:
            # Dibujar las reglas por primera vez
            self._redraw_all()

            # Stack con todas las capas
            stack_with_rulers = ft.Stack(
                [
                    # Viewer en el fondo
                    self.zoom_container,
                    # Espacio vacío en la esquina
                    ft.Container(
                        content=self.corner_space,
                        top=0,
                        left=0,
                    ),
                    # Regla horizontal desplazada a la derecha por corner_size
                    ft.Container(
                        content=self.ruler_horizontal_container,
                        top=0,
                        left=self.corner_size,
                    ),
                    # Regla vertical desplazada hacia abajo por corner_size
                    ft.Container(
                        content=self.ruler_vertical_container,
                        top=self.corner_size,
                        left=0,
                    ),
                    # Panel de ajuste fino (fijo en esquina, no afecta zoom)
                    ft.Container(
                        content=self.fine_adjust_panel,
                        top=self.corner_size + fine_adjust_margin,
                        right=fine_adjust_margin,
                    ),
                ],
                expand=True,
            )

            return stack_with_rulers
        else:
            # Sin reglas, devolver stack para incluir panel fijo de ajuste fino
            self._redraw_all()
            stack_without_rulers = ft.Stack(
                [
                    self.zoom_container,
                    ft.Container(
                        content=self.fine_adjust_panel,
                        top=fine_adjust_margin,
                        right=fine_adjust_margin,
                    ),
                ],
                expand=True,
            )
            return stack_without_rulers

    def set_background(self, config):
        """Establece la configuración del fondo y genera la imagen base64 si es necesario"""
        print(">>> VIEWER set_background INICIO <<<")

        old_path = (
            self.background_config.get("path") if self.background_config else None
        )
        new_path = config.get("path") if config else None
        old_page = (
            self.background_config.get("page") if self.background_config else None
        )
        new_page = config.get("page") if config else None

        self.background_config = config

        if config:
            # PRIORIDAD 1: Archivo físico de caché (Nuevo) - Leemos a base64 por compatibilidad Flet
            cache_path = config.get("cache_path")
            if cache_path and os.path.exists(cache_path):
                print(f"[VIEWER] Cargando desde caché física: {cache_path}")
                try:
                    with open(cache_path, "rb") as f:
                        self.background_image_src = base64.b64encode(f.read()).decode(
                            "utf-8"
                        )
                    self.background_image_control.src = self.background_image_src
                    self.background_image_control.visible = True
                    self._redraw_all(force=True)
                    return
                except Exception as e:
                    print(f"[VIEWER] Error leyendo caché física: {e}")

            # PRIORIDAD 2: Usar base64 si ya viene en la configuración (Caché en proyectos .pnb)
            if config.get("base64"):
                self.background_image_src = config.get("base64")
                self.background_image_control.src = self.background_image_src
                self.background_image_control.visible = True
                print(
                    f"[VIEWER] Usando base64 cacheado de la configuración (len: {len(self.background_image_src)})"
                )
                self._redraw_all(force=True)
                return

        # PRIORIDAD 3: Solo si no hay caché, cargar del disco si el path o página cambian
        if new_path != old_path or new_page != old_page:
            if config and new_path:
                path = new_path
                print(f"[VIEWER] Cargando fondo: {path} (tipo: {config.get('type')})")
                if config.get("type") == "pdf":
                    # Generar imagen de la página PDF
                    try:
                        import fitz

                        doc = fitz.open(path)
                        page = doc.load_page(config.get("page", 0))
                        # Usar un zoom moderado
                        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                        img_bytes = pix.tobytes("png")
                        base64_data = base64.b64encode(img_bytes).decode("utf-8")
                        # Usar raw base64 para src
                        self.background_image_src = base64_data
                        print(
                            f"[VIEWER] PDF convertido a base64 (len: {len(self.background_image_src)})"
                        )
                        doc.close()
                    except Exception as e:
                        # if sys.stderr is not None:
                        #     sys.stderr.write(
                        #         f"[VIEWER] Error cargando PDF de fondo: {e}\n"
                        #     )
                        self.background_image_src = None
                else:
                    # Imagen raster
                    try:
                        with open(path, "rb") as f:
                            base64_data = base64.b64encode(f.read()).decode("utf-8")
                            self.background_image_src = base64_data
                            print(
                                f"[VIEWER] Imagen cargada a base64 (len: {len(self.background_image_src)})"
                            )
                    except Exception as e:
                        # if sys.stderr is not None:
                        #     sys.stderr.write(
                        #         f"[VIEWER] Error cargando imagen de fondo: {e}\n"
                        #     )
                        self.background_image_src = None
            else:
                if config:
                    print("[VIEWER] Path de fondo vacío")
                else:
                    print("[VIEWER] Limpiando imagen de fondo (config None)")
                self.background_image_src = None

            # Asignar al control de imagen (usar src para base64 puro)
            self.background_image_control.src = self.background_image_src

            # Forzar visibilidad si hay imagen
            if self.background_image_src:
                self.background_image_control.visible = True
            else:
                self.background_image_control.visible = False

        # SIEMPRE redibujar para actualizar posición/rotación/escala (FUERA del if)
        # print(f"[VIEWER] Llamando _redraw_all() - config existe: {self.background_config is not None}")
        self._redraw_all(force=True)
