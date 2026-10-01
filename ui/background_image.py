"""
Módulo para gestionar la imagen de fondo y su diálogo de posicionamiento.
Maneja la configuración, carga y procesamiento de imágenes de fondo.
"""

import flet as ft
import os
import fitz
import sys
import base64

# Silenciar prints de depuración en este módulo por defecto.
# Para activar, cambiar _PRINT_DEBUG = True durante desarrollo.
_PRINT_DEBUG = False
if not _PRINT_DEBUG:

    def _no_print(*args, **kwargs):
        return None

    print = _no_print


# Añadir el directorio raíz al path
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
from color_design import (
    BOTONES_GENERICOS_COLOR,
    BOTONES_GENERICOS_HOVER_COLOR,
    BOTONES_GENERICOS_OVERLAY_COLOR,
    BOTONES_GENERICOS_FONDO_COLOR,
    FONDO_ALERT_DIALOG,
    FONDO_TEXTFIELDS_COLOR,
    BORDE_TEXTFIELDS_COLOR,
    TEXTOS_FASE_1_COLOR,
    TEXTO_COLOR_GENERICO,
    DROPDOWN_TEXT_STYLE_COLOR,
    DROPDOWN_TRAILING_ICON_COLOR,
    DROPDOWN_FONDO_MENU_COLOR,
)

# Internacionalización
from i18n import t
from utils.constants import normalize_decimal_input, convert_from_mm, get_unit_inches, get_unit_picas

# Constantes de unidades - importadas desde constants.py para consistencia y traducción correcta
from utils.constants import (
    UNIT_MM,
    UNIT_PX,
    UNIT_INCHES,
    UNIT_PICAS,
    get_unit_inches,
    get_unit_picas,
)
from utils.constants import convert_to_mm, convert_from_mm
from utils.preferences import get_last_file_dialog_path, set_last_file_dialog_path

# Lista de unidades como tuplas (clave_interna, etiqueta_mostrada)
# Esto asegura que el dropdown mantenga la clave interna en `data`
UNITS = [
    (UNIT_MM, "mm"),
    # Para etiquetas traducibles use la clave interna como marcador.
    # La resolución de la etiqueta se hace en tiempo de ejecución via
    # `_get_unit_label` para respetar el idioma activo.
    (UNIT_INCHES, UNIT_INCHES),
    (UNIT_PICAS, UNIT_PICAS),
]


def _translated_unit_label(unit_key: str) -> str:
    """Devuelve la etiqueta traducida para la unidad.

    Si la función de i18n no ha traducido (devuelve la misma clave interna),
    proporcionamos un fallback en inglés (p. ej. 'inches'). Esto evita que
    aparezcan letras en español cuando la UI está en inglés y falta la
    traducción para esa clave.
    """
    try:
        if unit_key == UNIT_INCHES:
            lbl = get_unit_inches()
            if str(lbl).strip().lower() == str(UNIT_INCHES).lower():
                return "inches"
            return str(lbl)
        if unit_key == UNIT_PICAS:
            lbl = get_unit_picas()
            if str(lbl).strip().lower() == str(UNIT_PICAS).lower():
                return "picas"
            return str(lbl)
    except Exception:
        pass
    return str(unit_key)


def _unit_abbr(unit_key: str) -> str:
    """Abreviatura fija (no traducible) para una clave de unidad."""
    return {
        UNIT_MM: "mm",
        UNIT_PX: "px",
        UNIT_INCHES: "in",
        UNIT_PICAS: "pc",
    }.get(unit_key, str(unit_key))


class PDFPageSelector:
    """
    Diálogo para seleccionar una página de un archivo PDF con previsualización
    e información de las cajas (MediaBox, CropBox, BleedBox).
    """

    def __init__(self, page: ft.Page, pdf_path: str, on_selected, unit_getter=None):
        self.page = page
        self.pdf_path = pdf_path
        self.on_selected = on_selected
        # Optional getter function returning current unit (internal key)
        self.unit_getter = unit_getter

        self.doc = fitz.open(pdf_path)
        self.total_pages = len(self.doc)
        self.current_page_idx = 0

        # Componentes de la UI - Previsualización más grande
        self.preview_image = ft.Image(
            src="",
            width=600,
            height=500,
            fit=ft.BoxFit.CONTAIN,
            border_radius=4,
        )

        self.page_number_field = ft.TextField(
            value="1",
            width=60,
            height=32,
            text_size=14,
            content_padding=ft.Padding(5, 0, 5, 0),
            text_align=ft.TextAlign.CENTER,
            on_submit=self._on_page_field_submit,
            bgcolor=FONDO_TEXTFIELDS_COLOR,
            color=TEXTOS_FASE_1_COLOR,border=ft.OutlineInputBorder(side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)))

        self.boxes_info = ft.Column(spacing=6)

        # Construir el diálogo con layout horizontal
        self.dialog = ft.AlertDialog(
            modal=True,
            title=ft.Container(
                content=ft.Text(
                    t("Seleccionar página del PDF"),
                    size=20,
                    weight=ft.FontWeight.BOLD,
                    color=TEXTO_COLOR_GENERICO,
                    text_align=ft.TextAlign.CENTER,
                ),
                alignment=ft.Alignment.CENTER,
            ),
            content=ft.Container(
                content=ft.Row(
                    [
                        # Columna izquierda: Previsualización
                        ft.Container(
                            content=ft.Column(
                                [
                                    ft.Container(
                                        content=self.preview_image,
                                        bgcolor=FONDO_TEXTFIELDS_COLOR,
                                        border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
                                        border_radius=6,
                                        padding=10,
                                        alignment=ft.Alignment.CENTER,
                                    ),
                                    ft.Container(height=8),
                                    # Navegación - simplificada
                                    ft.Row(
                                        [
                                            ft.IconButton(
                                                icon=ft.Icons.NAVIGATE_BEFORE,
                                                on_click=self._prev_page,
                                                icon_color=TEXTOS_FASE_1_COLOR,
                                                icon_size=24,
                                            ),
                                            self.page_number_field,
                                            ft.Text(
                                                t("de {0}").format(self.total_pages),
                                                size=14,
                                                color=TEXTO_COLOR_GENERICO,
                                            ),
                                            ft.IconButton(
                                                icon=ft.Icons.NAVIGATE_NEXT,
                                                on_click=self._next_page,
                                                icon_color=TEXTOS_FASE_1_COLOR,
                                                icon_size=24,
                                            ),
                                        ],
                                        alignment=ft.MainAxisAlignment.CENTER,
                                        spacing=8,
                                        tight=True,
                                    ),
                                ],
                                spacing=0,
                                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                tight=True,
                            ),
                            width=680,
                        ),
                        # Columna derecha: Información de cajas
                        ft.Container(
                            content=ft.Column(
                                [
                                    ft.Text(
                                        t("Dimensiones"),
                                        size=16,
                                        weight=ft.FontWeight.BOLD,
                                        color=TEXTO_COLOR_GENERICO,
                                    ),
                                    ft.Container(height=8),
                                    self.boxes_info,
                                ],
                                spacing=0,
                                tight=True,
                            ),
                            width=180,
                            padding=ft.Padding.only(
                                left=15, top=10, right=10, bottom=10
                            ),
                        ),
                    ],
                    spacing=15,
                    vertical_alignment=ft.CrossAxisAlignment.START,
                    tight=True,
                ),
                width=840,
            ),
            actions=[
                self._create_button(t("Cancelar"), self._on_cancel),
                self._create_button(t("Seleccionar"), self._on_accept),
            ],
            actions_alignment=ft.MainAxisAlignment.CENTER,
            bgcolor=FONDO_ALERT_DIALOG,
            content_padding=ft.Padding(20, 10, 20, 10),
            actions_padding=ft.Padding(0, 0, 0, 20),
        )

        # Cargar primera página
        self._update_page()

    def _create_button(self, label: str, on_click) -> ft.Button:
        """Crea un botón con estilo consistente"""
        return ft.Button(
            content=label,
            width=110,
            height=32,
            on_click=on_click,
            bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
            style=ft.ButtonStyle(
                color={
                    ft.ControlState.DEFAULT: BOTONES_GENERICOS_COLOR,
                    "hovered": BOTONES_GENERICOS_HOVER_COLOR,
                },
                overlay_color=BOTONES_GENERICOS_OVERLAY_COLOR,
                padding=ft.Padding(0, 0, 0, 0),
                shape=ft.RoundedRectangleBorder(radius=6),
            ),
        )

    def show(self):
        """Muestra el diálogo"""
        self.page.show_dialog(self.dialog)

    def _update_page(self):
        """Actualiza la previsualización y la información de la página actual"""
        if self.current_page_idx < 0:
            self.current_page_idx = 0
        if self.current_page_idx >= self.total_pages:
            self.current_page_idx = self.total_pages - 1

        self.page_number_field.value = str(self.current_page_idx + 1)

        # Generar preview de alta resolución (zoom de 2.0 para mayor calidad)
        page = self.doc.load_page(self.current_page_idx)
        pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0))
        img_bytes = pix.tobytes("png")
        self.preview_image.src = base64.b64encode(img_bytes).decode("utf-8")

        # Actualizar información de cajas
        self._update_boxes_text(page)

        if self.dialog.open:
            self.page.update()

    def _update_boxes_text(self, page):
        """Lee las cajas del PDF y actualiza el texto en mm"""
        self.boxes_info.controls.clear()

        # fitz da las medidas en puntos (1/72 pulgada). Convertir a mm.
        # 1 pt = 25.4 / 72 mm
        pt_to_mm = 25.4 / 72.0

        # Leer cajas usando leer_cajas_pdf de pdf_manipulator o directamente de fitz
        # Para mayor velocidad aquí usamos directamente el objeto 'page' de fitz que ya tenemos
        rects = {
            "MediaBox": page.rect,
            "CropBox": page.cropbox,
            "BleedBox": page.bleedbox,
            "TrimBox": page.trimbox,
        }

        # If a unit_getter is provided, convert values from mm to the displayed unit
        cur_unit = None
        try:
            if self.unit_getter:
                cur_unit = self.unit_getter()
        except Exception:
            cur_unit = None

        for name, rect in rects.items():
            w_mm = rect.width * pt_to_mm
            h_mm = rect.height * pt_to_mm

            if cur_unit:
                # Convert mm to desired unit for display
                try:
                    w_disp = convert_from_mm(w_mm, cur_unit)
                    h_disp = convert_from_mm(h_mm, cur_unit)
                    # Choose unit label
                    if cur_unit == UNIT_PX:
                        label = f"{w_disp:.1f} × {h_disp:.1f} px"
                    elif cur_unit == UNIT_INCHES:
                        label = f"{w_disp:.2f} × {h_disp:.2f} {_unit_abbr(UNIT_INCHES)}"
                    elif cur_unit == UNIT_PICAS:
                        label = f"{w_disp:.2f} × {h_disp:.2f} {_unit_abbr(UNIT_PICAS)}"
                    else:
                        label = f"{w_disp:.1f} × {h_disp:.1f} mm"
                except Exception:
                    label = f"{w_mm:.1f} × {h_mm:.1f} mm"
            else:
                label = f"{w_mm:.1f} × {h_mm:.1f} mm"

            self.boxes_info.controls.append(
                ft.Column(
                    [
                        ft.Text(
                            name,
                            size=13,
                            weight=ft.FontWeight.BOLD,
                            color=TEXTO_COLOR_GENERICO,
                        ),
                        ft.Text(label, size=12, color=TEXTOS_FASE_1_COLOR),
                    ],
                    spacing=2,
                    tight=True,
                )
            )

    def _prev_page(self, e):
        if self.current_page_idx > 0:
            self.current_page_idx -= 1
            self._update_page()

    def _next_page(self, e):
        if self.current_page_idx < self.total_pages - 1:
            self.current_page_idx += 1
            self._update_page()

    def _on_page_field_submit(self, e):
        try:
            val = int(self.page_number_field.value)
            if 1 <= val <= self.total_pages:
                self.current_page_idx = val - 1
                self._update_page()
            else:
                self.page_number_field.value = str(self.current_page_idx + 1)
                self.page.update()
        except ValueError:
            self.page_number_field.value = str(self.current_page_idx + 1)
            self.page.update()

    def _on_cancel(self, e):
        self.dialog.open = False
        self.doc.close()
        self.page.update()

    def _on_accept(self, e):
        if getattr(self, "_accepting", False):
            return
        self._accepting = True

        self.dialog.open = False
        # Leer cajas finales para pasar al callback
        try:
            page = self.doc.load_page(self.current_page_idx)
            pt_to_mm = 25.4 / 72.0
            boxes = {
                "mediabox": (
                    page.rect.x0 * pt_to_mm,
                    page.rect.y0 * pt_to_mm,
                    page.rect.x1 * pt_to_mm,
                    page.rect.y1 * pt_to_mm,
                ),
                "cropbox": (
                    page.cropbox.x0 * pt_to_mm,
                    page.cropbox.y0 * pt_to_mm,
                    page.cropbox.x1 * pt_to_mm,
                    page.cropbox.y1 * pt_to_mm,
                ),
                "bleedbox": (
                    page.bleedbox.x0 * pt_to_mm,
                    page.bleedbox.y0 * pt_to_mm,
                    page.bleedbox.x1 * pt_to_mm,
                    page.bleedbox.y1 * pt_to_mm,
                ),
                "trimbox": (
                    page.trimbox.x0 * pt_to_mm,
                    page.trimbox.y0 * pt_to_mm,
                    page.trimbox.x1 * pt_to_mm,
                    page.trimbox.y1 * pt_to_mm,
                ),
            }
            self.doc.close()
            self.page.update()

            if self.on_selected:
                self.on_selected(self.current_page_idx, boxes)
        finally:
            self._accepting = False


class BackgroundImageManager:
    """
    Gestiona la imagen de fondo y su configuración.
    """

    def __init__(self, page: ft.Page, on_change=None, on_spot_colors_found=None):
        def_unit_getter = None
        # backward-compatible signature: allow passing unit_getter via kwargs in future
        # (we'll accept it if provided in on_change by the caller setting attribute after init)
        self.page = page
        self.on_change = on_change
        # Callback llamado con lista de dicts de colores spot cuando se carga un PDF.
        # Firma: on_spot_colors_found(spots: list[dict])
        self.on_spot_colors_found = on_spot_colors_found

        # Estado de la imagen
        self.image_path = None
        self.image_loaded = False

        # Configuración de posicionamiento
        self.align_to = "physical"  # "printable" o "physical"
        self.alignment_position = (
            "center"  # center, top_left, top_center, top_right, etc.
        )
        self.offset_horizontal = 0.0  # en mm
        self.offset_vertical = 0.0  # en mm
        self.offset_unit = UNIT_MM

        # Configuración de repetición (Tile)
        self.tile_enabled = False
        self.auto_fit = False
        self.tiles_across = 1
        self.tiles_down = 1

        # Configuración de rotación
        self.rotation = 0  # 0, 90, 180, 270

        # Configuración de tamaño personalizado
        self.use_custom_size = False
        self.custom_width = 210.0  # en mm
        self.custom_height = 297.0  # en mm
        self.custom_size_unit = UNIT_MM
        self.scale_percentage = 100.0
        self.base_width = 210.0
        self.base_height = 297.0

        # Atributos adicionales para el nuevo flujo (PDF/Imágenes)
        self.source_type = None  # "pdf" o "image"
        self.pdf_page_num = 0
        self.pdf_boxes = {}
        self.current_metadata = {}
        self.image_base64 = (
            None  # Caché base64 para el visor (temporal en preferencias)
        )
        self.pdf_temp_path = None  # PDF temporal con la página extraída y optimizada

        # Dimensiones de la página de la App (para cálculos de auto-fit)
        self.app_page_width = 210.0
        self.app_page_height = 297.0

        # Grid de alineación - posiciones activas
        self.alignment_buttons = {}

        # Inicializar FilePicker
        self.file_picker = ft.FilePicker(on_result=self._on_file_selected)
        self.page.services.append(self.file_picker)

        # Referencia a la ventana de ajustes abierta
        self.adjustment_window = None
        # Optional getter to read the global unit from MainScreen
        self.unit_getter = None

    def set_unit_getter(self, getter):
        """Establece una función que devuelve la unidad actual (clave interna)."""
        self.unit_getter = getter

    def _normalize_unit(self, unit_key: str) -> str:
        """Normaliza una posible clave de unidad (localizada o en inglés) a la clave interna esperada.

        Acepta valores como 'inches', 'pulgadas', la etiqueta traducida o la constante interna
        y devuelve una de las constantes: UNIT_MM, UNIT_PX, UNIT_INCHES, UNIT_PICAS.
        """
        if not unit_key:
            return UNIT_MM

        key = str(unit_key).strip().lower()
        # Match exact internal constants
        for const in (UNIT_MM, UNIT_PX, UNIT_INCHES, UNIT_PICAS):
            if key == str(const).lower():
                return const

        # Common English aliases
        if key in ("inch", "inches", "inchs"):
            return UNIT_INCHES
        if key in ("px", "pixel", "pixels"):
            return UNIT_PX
        if key in ("mm", "millimeter", "millimeters", "milimetro", "milimetros"):
            return UNIT_MM
        if key in ("pica", "picas"):
            return UNIT_PICAS

        # If matches translated label from get_unit_inches/get_unit_picas
        try:
            if key == str(get_unit_inches()).lower():
                return UNIT_INCHES
            if key == str(get_unit_picas()).lower():
                return UNIT_PICAS
        except Exception:
            pass

        # Fallback to mm
        return UNIT_MM

    def _get_unit_label(self, unit_key: str) -> str:
        """Devuelve la abreviatura fija para una clave de unidad."""
        return _unit_abbr(unit_key)

    def _create_generic_button(
        self, label: str, on_click, width: int = 110
    ) -> ft.Button:
        """Crea un botón con estilo genérico consistente"""
        return ft.Button(
            content=label,
            width=width,
            height=32,
            on_click=on_click,
            bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
            style=ft.ButtonStyle(
                color={
                    ft.ControlState.DEFAULT: BOTONES_GENERICOS_COLOR,
                    "hovered": BOTONES_GENERICOS_HOVER_COLOR,
                },
                overlay_color=BOTONES_GENERICOS_OVERLAY_COLOR,
                padding=ft.Padding(0, 0, 0, 0),
                shape=ft.RoundedRectangleBorder(radius=6),
            ),
        )

    def _create_textfield(
        self,
        value: str,
        width: int = 140,
        text_size: int = 14,
        on_change=None,
        disabled: bool = False,
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
            text_style=ft.TextStyle(color=TEXTO_COLOR_GENERICO),
            on_change=on_change,
            disabled=disabled,border=ft.OutlineInputBorder(border_radius=3, side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)))

    def _create_dropdown_compact(
        self,
        options: list,
        value: str,
        width: int = 140,
        text_size: int = 14,
        on_change=None,
    ) -> ft.Container:
        """Crea un dropdown compacto simulado usando PopupMenuButton"""
        # Encontrar el texto a mostrar basándose en el valor inicial (puede ser tupla o string)
        display_text = str(value)
        for opt in options:
            if isinstance(opt, tuple) and opt[0] == value:
                display_text = str(opt[1])
                break
            elif not isinstance(opt, tuple) and opt == value:
                break

        texto_valor = ft.Text(
            display_text,
            size=text_size,
            color=DROPDOWN_TEXT_STYLE_COLOR,
            no_wrap=True,
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
                    texto_valor,
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
                        items=items,
                    ),
                ],
            ),
        )

    def open_positioning_dialog(self):
        """Abre el diálogo de posicionamiento de imagen de fondo"""
        # Cerrar ventana previa si existe para evitar duplicados
        if self.adjustment_window and self.adjustment_window in self.page.overlay:
            try:
                self.adjustment_window.content = None
                self.page.overlay.remove(self.adjustment_window)
            except Exception:
                pass

        print("[DIALOG] Abriendo diálogo de posicionamiento de imagen")

        # Grid 3x3 de alineación (similar a marcas de texto en impo_ui)
        alignment_buttons = {}
        active_alignment = [self.alignment_position]

        def create_alignment_button(position, icon):
            """Crea un botón de alineación con icono"""
            is_active = position == active_alignment[0]
            btn = ft.Button(
                content=ft.Icon(icon, size=20),
                width=60,
                height=60,
                bgcolor=(
                    BOTONES_GENERICOS_FONDO_COLOR
                    if is_active
                    else FONDO_TEXTFIELDS_COLOR
                ),
                style=ft.ButtonStyle(
                    color={
                        ft.ControlState.DEFAULT: (
                            BOTONES_GENERICOS_COLOR
                            if is_active
                            else TEXTOS_FASE_1_COLOR
                        ),
                    },
                    shape=ft.RoundedRectangleBorder(radius=6),
                ),
                data=position,
                on_click=lambda e: select_alignment(e.control.data),
            )
            alignment_buttons[position] = btn
            return btn

        def select_alignment(position):
            """Selecciona una posición de alineación"""
            # Desactivar todos
            for key, btn in alignment_buttons.items():
                btn.bgcolor = FONDO_TEXTFIELDS_COLOR
                btn.style.color = {ft.ControlState.DEFAULT: TEXTOS_FASE_1_COLOR}
                btn.update()
            # Activar el seleccionado
            alignment_buttons[position].bgcolor = BOTONES_GENERICOS_FONDO_COLOR
            alignment_buttons[position].style.color = {ft.ControlState.DEFAULT: BOTONES_GENERICOS_COLOR}
            alignment_buttons[position].update()
            active_alignment[0] = position

            # Resetear offsets al cambiar alineamiento
            offset_h_field.value = "0.0"
            offset_v_field.value = "0.0"
            offset_h_field.update()
            offset_v_field.update()

            _trigger_update()

        def _trigger_update(e=None):
            """Aplica los cambios al estado y notifica al visor en tiempo real"""
            try:
                if e is not None and hasattr(e, "control"):
                    normalize_decimal_input(e)
                self.alignment_position = active_alignment[0]
                # Note: determine unit first, then convertir valores introducidos a mm
                if offset_unit_dropdown is not None:
                    chosen_unit = (
                        offset_unit_dropdown.content.controls[0].data
                        if offset_unit_dropdown.content.controls[0].data is not None
                        else offset_unit_dropdown.content.controls[0].value
                    )
                elif self.unit_getter:
                    chosen_unit = self.unit_getter()
                else:
                    chosen_unit = self.offset_unit

                try:
                    val_h = float(offset_h_field.value or 0)
                except Exception:
                    val_h = 0.0
                try:
                    val_v = float(offset_v_field.value or 0)
                except Exception:
                    val_v = 0.0

                self.offset_horizontal = convert_to_mm(val_h, chosen_unit)
                self.offset_vertical = convert_to_mm(val_v, chosen_unit)
                print(
                    f"[DEBUG BG] _trigger_update: chosen_unit={chosen_unit}, entered H={val_h}, V={val_v} -> mm H={self.offset_horizontal}, V={self.offset_vertical}"
                )
                self.offset_unit = chosen_unit

                # Lógica de exclusión mutua: Auto-fit vs Tamaño Personalizado
                control = e.control if hasattr(e, "control") else None

                if control == auto_fit_checkbox:
                    if auto_fit_checkbox.value:
                        custom_size_checkbox.value = False
                        custom_size_checkbox.update()

                        # Sincronizar campos: Calcular valores que daría el auto-fit
                        # Relación de aspecto del fondo original
                        if self.base_width > 0 and self.base_height > 0:
                            # Ajustar dimensiones base según rotación actual
                            print(f"[DEBUG AUTO-FIT] Rotación actual: {self.rotation}°")
                            if self.rotation in [90, 270]:
                                eff_base_w = self.base_height
                                eff_base_h = self.base_width
                                print(
                                    f"[DEBUG AUTO-FIT] Usando dimensiones rotadas: {eff_base_w}x{eff_base_h}mm"
                                )
                            else:
                                eff_base_w = self.base_width
                                eff_base_h = self.base_height
                                print(
                                    f"[DEBUG AUTO-FIT] Usando dimensiones originales: {eff_base_w}x{eff_base_h}mm"
                                )

                            ratio_w = self.app_page_width / eff_base_w
                            ratio_h = self.app_page_height / eff_base_h
                            auto_scale = min(ratio_w, ratio_h)

                            print(
                                f"[DEBUG AUTO-FIT] App Page: {self.app_page_width}x{self.app_page_height}mm"
                            )
                            print(
                                f"[DEBUG AUTO-FIT] Base Image: {self.base_width}x{self.base_height}mm"
                            )
                            print(
                                f"[DEBUG AUTO-FIT] Ratios: w={ratio_w:.4f}, h={ratio_h:.4f} -> Scale: {auto_scale:.4f} ({auto_scale*100:.1f}%)"
                            )

                            # Actualizar valores reales
                            self.custom_width = round(self.base_width * auto_scale, 2)
                            self.custom_height = round(self.base_height * auto_scale, 2)
                            self.scale_percentage = round(auto_scale * 100, 0)

                            # Actualizar campos visualmente
                            custom_width_field.value = f"{self.custom_width:.2f}"
                            custom_height_field.value = f"{self.custom_height:.2f}"
                            scale_field.value = f"{self.scale_percentage:.0f}%"

                            custom_width_field.update()
                            custom_height_field.update()
                            scale_field.update()
                    else:
                        # Cuando se desactiva Auto-Fit, resetear a 100%
                        print("[DEBUG AUTO-FIT] Desactivado -> Reset a 100%")
                        self.scale_percentage = 100.0
                        self.custom_width = self.base_width
                        self.custom_height = self.base_height

                        # Actualizar campos visualmente
                        scale_field.value = "100%"
                        custom_width_field.value = f"{self.base_width:.2f}"
                        custom_height_field.value = f"{self.base_height:.2f}"

                        scale_field.update()
                        custom_width_field.update()
                        custom_height_field.update()

                elif control == custom_size_checkbox and custom_size_checkbox.value:
                    auto_fit_checkbox.value = False
                    auto_fit_checkbox.update()

                self.auto_fit = auto_fit_checkbox.value

                rotation_str = rotation_dropdown.content.controls[0].value
                self.rotation = int(rotation_str.replace("°", ""))

                self.use_custom_size = custom_size_checkbox.value

                # SIEMPRE actualizar estado disabled de campos según checkboxes
                custom_width_field.disabled = not self.use_custom_size
                custom_height_field.disabled = not self.use_custom_size
                scale_field.disabled = (
                    not self.use_custom_size
                )  # Habilitado solo cuando checkbox activo

                custom_width_field.update()
                custom_height_field.update()
                scale_field.update()
                scale_field.update()

                # Lógica de sincronización Escala <-> Tamaño Personalizado
                try:
                    new_scale_pct = float(scale_field.value.replace("%", "") or 100)
                    new_w = float(custom_width_field.value or 0)
                    new_h = float(custom_height_field.value or 0)

                    if self.use_custom_size:
                        # 1. Si cambió la escala, actualizar W/H basado en la base
                        if new_scale_pct != self.scale_percentage:
                            new_scale = new_scale_pct / 100.0
                            w_val = f"{self.base_width * new_scale:.1f}"
                            h_val = f"{self.base_height * new_scale:.1f}"
                            if custom_width_field.value != w_val:
                                custom_width_field.value = w_val
                                custom_width_field.update()
                            if custom_height_field.value != h_val:
                                custom_height_field.value = h_val
                                custom_height_field.update()

                        # 2. Si cambió el Ancho manualmente, actualizar Escala
                        elif new_w != self.custom_width and self.base_width > 0:
                            new_scale_pct = (new_w / self.base_width) * 100
                            scale_field.value = f"{new_scale_pct:.0f}%"
                            scale_field.update()

                        # 3. Si cambió el Alto manualmente, actualizar Escala
                        elif new_h != self.custom_height and self.base_height > 0:
                            new_scale_pct = (new_h / self.base_height) * 100
                            scale_field.value = f"{new_scale_pct:.0f}%"
                            scale_field.update()
                except:
                    pass

                # Convertir tamaño personalizado a mm según unidad seleccionada
                try:
                    w_val = float(custom_width_field.value or 0)
                except Exception:
                    w_val = 0.0
                try:
                    h_val = float(custom_height_field.value or 0)
                except Exception:
                    h_val = 0.0

                if custom_size_unit_dropdown is not None:
                    chosen_cs_unit = (
                        custom_size_unit_dropdown.content.controls[0].data
                        if custom_size_unit_dropdown.content.controls[0].data
                        is not None
                        else custom_size_unit_dropdown.content.controls[0].value
                    )
                elif self.unit_getter:
                    chosen_cs_unit = self.unit_getter()
                else:
                    chosen_cs_unit = self.custom_size_unit

                self.custom_width = convert_to_mm(w_val, chosen_cs_unit)
                self.custom_height = convert_to_mm(h_val, chosen_cs_unit)
                self.custom_size_unit = chosen_cs_unit

                scale_val = scale_field.value.replace("%", "")
                self.scale_percentage = float(scale_val or 100)

                if self.on_change:
                    print("[DEBUG BG] calling on_change() from _trigger_update")
                    self.on_change()
            except Exception:
                import traceback

                print("[DEBUG BG] Exception in _trigger_update:")
                traceback.print_exc()
                pass

        # Grid 3x3 completo
        alignment_grid = ft.Column(
            [
                ft.Row(
                    [
                        create_alignment_button("top_left", ft.Icons.NORTH_WEST),
                        create_alignment_button("top_center", ft.Icons.NORTH),
                        create_alignment_button("top_right", ft.Icons.NORTH_EAST),
                    ],
                    spacing=5,
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
                ft.Row(
                    [
                        create_alignment_button("middle_left", ft.Icons.WEST),
                        create_alignment_button("center", ft.Icons.FILTER_CENTER_FOCUS),
                        create_alignment_button("middle_right", ft.Icons.EAST),
                    ],
                    spacing=5,
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
                ft.Row(
                    [
                        create_alignment_button("bottom_left", ft.Icons.SOUTH_WEST),
                        create_alignment_button("bottom_center", ft.Icons.SOUTH),
                        create_alignment_button("bottom_right", ft.Icons.SOUTH_EAST),
                    ],
                    spacing=5,
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
            ],
            spacing=5,
        )

        # Campos de offset
        offset_h_field = self._create_textfield(
            f"{self.offset_horizontal:.2f}", width=100, on_change=_trigger_update
        )

        offset_v_field = self._create_textfield(
            f"{self.offset_vertical:.2f}", width=100, on_change=_trigger_update
        )

        # Si tenemos un getter global de unidad, mostramos solo la etiqueta
        if self.unit_getter:
            offset_unit_display = ft.Text(
                self._get_unit_label(self.unit_getter()),
                size=14,
                color=TEXTOS_FASE_1_COLOR,
            )
            offset_unit_dropdown = None
        else:
            offset_unit_dropdown = self._create_dropdown_compact(
                UNITS, self.offset_unit, width=100, on_change=_trigger_update
            )

        # Checkbox "Ajustar imagen a tamaño de página"
        auto_fit_checkbox = ft.Checkbox(
            label=t("Ajustar imagen a tamaño de página"),
            value=self.auto_fit,
            active_color=BORDE_TEXTFIELDS_COLOR,
            check_color=TEXTOS_FASE_1_COLOR,
            label_style=ft.TextStyle(size=14, color=TEXTOS_FASE_1_COLOR),
            fill_color=BOTONES_GENERICOS_FONDO_COLOR,
            on_change=_trigger_update,
        )

        # Callback específico para rotación que resetea offsets
        def on_rotation_change(e):
            # Resetear offsets al cambiar rotación
            offset_h_field.value = "0.0"
            offset_v_field.value = "0.0"
            offset_h_field.update()
            offset_v_field.update()
            _trigger_update(e)

        # Dropdown de rotación
        rotation_dropdown = self._create_dropdown_compact(
            ["0°", "90°", "180°", "270°"],
            f"{self.rotation}°",
            width=120,
            on_change=on_rotation_change,
        )

        # Checkbox "Usar tamaño personalizado de imagen"
        custom_size_checkbox = ft.Checkbox(
            label=t("Usar tamaño personalizado de imagen"),
            value=self.use_custom_size,
            active_color=BORDE_TEXTFIELDS_COLOR,
            check_color=TEXTOS_FASE_1_COLOR,
            label_style=ft.TextStyle(size=14, color=TEXTOS_FASE_1_COLOR),
            fill_color=BOTONES_GENERICOS_FONDO_COLOR,
            on_change=_trigger_update,
        )

        # Campos de tamaño personalizado
        custom_width_field = self._create_textfield(
            f"{self.custom_width:.1f}", width=100, on_change=_trigger_update
        )
        custom_width_field.disabled = not self.use_custom_size

        custom_height_field = self._create_textfield(
            f"{self.custom_height:.1f}", width=100, on_change=_trigger_update
        )
        custom_height_field.disabled = not self.use_custom_size

        # Si usamos el getter global de unidad, mostrar los campos convertidos (unidad mostrada)
        if self.unit_getter:
            try:
                cur_unit = self.unit_getter()
                print(f"[DEBUG BG] unit_getter present -> cur_unit={cur_unit}")
                # Convertir offsets de mm a la unidad mostrada
                off_h = convert_from_mm(self.offset_horizontal, cur_unit)
                off_v = convert_from_mm(self.offset_vertical, cur_unit)
                print(
                    f"[DEBUG BG] offsets mm -> displayed: {self.offset_horizontal}->{off_h}, {self.offset_vertical}->{off_v}"
                )
                if cur_unit == UNIT_PX:
                    offset_h_field.value = f"{off_h:.1f}"
                    offset_v_field.value = f"{off_v:.1f}"
                else:
                    offset_h_field.value = f"{off_h:.4f}"
                    offset_v_field.value = f"{off_v:.4f}"

                # Convertir tamaño personalizado
                w_conv = convert_from_mm(self.custom_width, cur_unit)
                h_conv = convert_from_mm(self.custom_height, cur_unit)
                if cur_unit == UNIT_PX:
                    custom_width_field.value = f"{w_conv:.1f}"
                    custom_height_field.value = f"{h_conv:.1f}"
                else:
                    custom_width_field.value = f"{w_conv:.4f}"
                    custom_height_field.value = f"{h_conv:.4f}"

                # No llamar a .update() aquí: actualizaré los controles después
                # de añadir el panel al overlay (ver más abajo) para evitar
                # AssertionError si aún no están adjuntos a la página.
            except Exception:
                import traceback

                print(f"[DEBUG BG] Exception converting displayed values:")
                traceback.print_exc()
                pass

        if self.unit_getter:
            custom_size_unit_display = ft.Text(
                self._get_unit_label(self.unit_getter()),
                size=14,
                color=TEXTOS_FASE_1_COLOR,
            )
            custom_size_unit_dropdown = None
        else:
            custom_size_unit_dropdown = self._create_dropdown_compact(
                UNITS, self.custom_size_unit, width=100, on_change=_trigger_update
            )

        scale_field = self._create_textfield(
            f"{self.scale_percentage:.0f}%",
            width=100,
            on_change=_trigger_update,
            disabled=not self.use_custom_size,  # Habilitado solo cuando checkbox está activo
        )

        # Botones
        def on_save(e):
            """Guardar configuración"""
            try:
                # Guardar valores (convertir desde la unidad mostrada a mm)
                self.alignment_position = active_alignment[0]
                # determinar unidad usada para offsets
                if offset_unit_dropdown is not None:
                    save_unit = (
                        offset_unit_dropdown.content.controls[0].data
                        if offset_unit_dropdown.content.controls[0].data is not None
                        else offset_unit_dropdown.content.controls[0].value
                    )
                elif self.unit_getter:
                    save_unit = self.unit_getter()
                else:
                    save_unit = self.offset_unit

                try:
                    off_h_val = float(offset_h_field.value or 0)
                except Exception:
                    off_h_val = 0.0
                try:
                    off_v_val = float(offset_v_field.value or 0)
                except Exception:
                    off_v_val = 0.0

                self.offset_horizontal = convert_to_mm(off_h_val, save_unit)
                self.offset_vertical = convert_to_mm(off_v_val, save_unit)
                print(
                    f"[DEBUG BG] on_save: save_unit={save_unit}, off_h_val={off_h_val}, off_v_val={off_v_val} -> mm H={self.offset_horizontal}, V={self.offset_vertical}"
                )
                self.offset_unit = save_unit

                self.auto_fit = auto_fit_checkbox.value

                rotation_str = rotation_dropdown.content.controls[0].value
                self.rotation = int(rotation_str.replace("°", ""))

                self.use_custom_size = custom_size_checkbox.value
                # determinar unidad usada para tamaño personalizado
                if custom_size_unit_dropdown is not None:
                    cs_unit = (
                        custom_size_unit_dropdown.content.controls[0].data
                        if custom_size_unit_dropdown.content.controls[0].data
                        is not None
                        else custom_size_unit_dropdown.content.controls[0].value
                    )
                elif self.unit_getter:
                    cs_unit = self.unit_getter()
                else:
                    cs_unit = self.custom_size_unit

                try:
                    w_in = float(custom_width_field.value or 0)
                except Exception:
                    w_in = 0.0
                try:
                    h_in = float(custom_height_field.value or 0)
                except Exception:
                    h_in = 0.0

                self.custom_width = convert_to_mm(w_in, cs_unit)
                self.custom_height = convert_to_mm(h_in, cs_unit)
                print(
                    f"[DEBUG BG] on_save: custom size {w_in}x{h_in} {cs_unit} -> mm {self.custom_width}x{self.custom_height}"
                )
                self.custom_size_unit = cs_unit

                print(f"[IMAGE] Configuración guardada:")
                print(f"  Posición: {self.alignment_position}")
                print(
                    f"  Offset: {self.offset_horizontal}, {self.offset_vertical} {self.offset_unit}"
                )
                print(f"  Ajustar a página: {self.auto_fit}")
                print(f"  Rotación: {self.rotation}°")
                print(f"  Tamaño personalizado: {self.use_custom_size}")

                # Cerrar diálogo flotante
                close_floating(None)

            except ValueError as ex:
                print(f"[ERROR] Valores inválidos: {ex}")

        def on_cancel(e):
            """Cancelar sin guardar"""
            close_floating(e)

        # Contenido del diálogo - diseño en dos columnas
        # Abreviatura de unidad para labels de desplazamiento y tamaño
        try:
            _disp_abbr = _unit_abbr(self.unit_getter() if self.unit_getter else UNIT_MM)
        except Exception:
            _disp_abbr = "mm"
        dialog_content = ft.Row(
            [
                # Columna izquierda: Posicionamiento
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Text(
                                t("Posicionamiento"),
                                size=18,
                                weight=ft.FontWeight.BOLD,
                                color=TEXTO_COLOR_GENERICO,
                            ),
                            ft.Container(height=5),
                            # Grid de alineación
                            alignment_grid,
                            ft.Container(height=10),
                            # Offset de posicionamiento
                            ft.Text(
                                t("Desplazamiento:"),
                                size=14,
                                color=TEXTO_COLOR_GENERICO,
                            ),
                            ft.Row(
                                [
                                    ft.Text(
                                        "H:",
                                        size=14,
                                        width=25,
                                        color=TEXTO_COLOR_GENERICO,
                                    ),
                                    offset_h_field,
                                    ft.Text(
                                        _disp_abbr,
                                        size=12,
                                        color=TEXTO_COLOR_GENERICO,
                                    ),
                                ]
                            ),
                            ft.Row(
                                [
                                    ft.Text(
                                        "V:",
                                        size=14,
                                        width=25,
                                        color=TEXTO_COLOR_GENERICO,
                                    ),
                                    offset_v_field,
                                    ft.Text(
                                        _disp_abbr,
                                        size=12,
                                        color=TEXTO_COLOR_GENERICO,
                                    ),
                                ]
                            ),
                        ],
                        spacing=8,
                        tight=True,
                    ),
                    width=310,
                    height=520,
                    padding=15,
                    border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
                    border_radius=6,
                ),
                # Columna derecha: Otras opciones
                ft.Container(
                    content=ft.Column(
                        [
                            # Ajustar imagen
                            ft.Text(
                                t("Ajuste"),
                                size=18,
                                weight=ft.FontWeight.BOLD,
                                color=TEXTO_COLOR_GENERICO,
                            ),
                            ft.Container(height=5),
                            ft.Container(
                                content=auto_fit_checkbox,
                                padding=ft.Padding(-10, 0, 0, 0),
                            ),
                            ft.Divider(height=1),
                            # Rotar imagen
                            ft.Text(
                                t("Rotación"),
                                size=18,
                                weight=ft.FontWeight.BOLD,
                                color=TEXTO_COLOR_GENERICO,
                            ),
                            ft.Container(height=5),
                            rotation_dropdown,
                            ft.Divider(height=1),
                            # Tamaño personalizado
                            ft.Text(
                                t("Tamaño personalizado"),
                                size=18,
                                weight=ft.FontWeight.BOLD,
                                color=TEXTO_COLOR_GENERICO,
                            ),
                            ft.Container(height=5),
                            ft.Container(
                                content=custom_size_checkbox,
                                padding=ft.Padding(-10, 0, 0, 0),
                            ),
                            ft.Row(
                                [
                                    ft.Text(
                                        f"{t('Ancho:')}",
                                        size=14,
                                        width=65,
                                        color=TEXTO_COLOR_GENERICO,
                                    ),
                                    custom_width_field,
                                    ft.Text(
                                        _disp_abbr,
                                        size=12,
                                        color=TEXTO_COLOR_GENERICO,
                                    ),
                                ]
                            ),
                            ft.Row(
                                [
                                    ft.Text(
                                        f"{t('Alto:')}",
                                        size=14,
                                        width=65,
                                        color=TEXTO_COLOR_GENERICO,
                                    ),
                                    custom_height_field,
                                    ft.Text(
                                        _disp_abbr,
                                        size=12,
                                        color=TEXTO_COLOR_GENERICO,
                                    ),
                                ]
                            ),
                            ft.Row(
                                [
                                    ft.Text(
                                        t("Escala:"),
                                        size=14,
                                        width=65,
                                        color=TEXTO_COLOR_GENERICO,
                                    ),
                                    scale_field,
                                ]
                            ),
                        ],
                        spacing=8,
                        tight=True,
                    ),
                    width=310,
                    height=520,
                    padding=15,
                    border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
                    border_radius=6,
                ),
            ],
            spacing=15,
            vertical_alignment=ft.CrossAxisAlignment.START,
            alignment=ft.MainAxisAlignment.CENTER,
        )

        # Variables para arrastrar la ventana - calcular posición centrada
        dialog_width = 700
        dialog_height = 650  # altura aproximada del diálogo (ajustada)
        win_x = max(0, (self.page.width - dialog_width) / 2)
        win_y = max(0, (self.page.height - dialog_height) / 2)

        def on_drag(e: ft.DragUpdateEvent):
            dx = e.local_delta.x if e.local_delta else 0
            dy = e.local_delta.y if e.local_delta else 0
            # Límites horizontales (basados en el ancho fijo de 700)
            new_left = floating_window.left + dx
            max_left = max(0, self.page.width - 700)
            floating_window.left = max(0, min(new_left, max_left))

            # Límites verticales (asegurar que la barra de título siempre sea accesible)
            new_top = floating_window.top + dy
            max_top = max(0, self.page.height - 50)
            floating_window.top = max(0, min(new_top, max_top))

            floating_window.update()

        # Función para cerrar el panel flotante
        def close_floating(e):
            if floating_window in self.page.overlay:
                floating_window.content = None
                self.page.overlay.remove(floating_window)
            self.adjustment_window = None
            self.page.update()

        # Preparar barra de metadatos
        info_items = []
        md = self.current_metadata
        if md:
            tipo = md.get("tipo", "N/A")
            info_items.append(
                ft.Text(
                    f"{t('Formato:')} {tipo}",
                    size=12,
                    color=TEXTO_COLOR_GENERICO,
                    weight=ft.FontWeight.BOLD,
                )
            )

            if tipo == "PDF":
                info_items.append(
                    ft.Text(
                        f"{t('Pág:')} {md.get('página')}",
                        size=12,
                        color=TEXTO_COLOR_GENERICO,
                    )
                )
                mb = md.get("mediabox")
                tb = md.get("trimbox")
                # Mostrar dimensiones en la unidad global si está disponible
                cur_unit = None
                try:
                    if self.unit_getter:
                        cur_unit = self.unit_getter()
                except Exception:
                    cur_unit = None

                if mb:
                    w_mm = mb[2] - mb[0]
                    h_mm = mb[3] - mb[1]
                    if cur_unit:
                        try:
                            w_disp = convert_from_mm(w_mm, cur_unit)
                            h_disp = convert_from_mm(h_mm, cur_unit)
                            if cur_unit == UNIT_PX:
                                label = f"MediaBox: {w_disp:.1f}x{h_disp:.1f} px"
                            elif cur_unit == UNIT_INCHES:
                                label = f"MediaBox: {w_disp:.2f}x{h_disp:.2f} {_unit_abbr(UNIT_INCHES)}"
                            elif cur_unit == UNIT_PICAS:
                                label = f"MediaBox: {w_disp:.2f}x{h_disp:.2f} {_unit_abbr(UNIT_PICAS)}"
                            else:
                                label = f"MediaBox: {w_disp:.1f}x{h_disp:.1f} mm"
                        except Exception:
                            label = f"MediaBox: {w_mm:.1f}x{h_mm:.1f} mm"
                    else:
                        label = f"MediaBox: {w_mm:.1f}x{h_mm:.1f} mm"
                    info_items.append(
                        ft.Text(label, size=11, color=TEXTO_COLOR_GENERICO)
                    )

                if tb:
                    w_mm = tb[2] - tb[0]
                    h_mm = tb[3] - tb[1]
                    if cur_unit:
                        try:
                            w_disp = convert_from_mm(w_mm, cur_unit)
                            h_disp = convert_from_mm(h_mm, cur_unit)
                            if cur_unit == UNIT_PX:
                                label = f"TrimBox: {w_disp:.1f}x{h_disp:.1f} px"
                            elif cur_unit == UNIT_INCHES:
                                label = f"TrimBox: {w_disp:.2f}x{h_disp:.2f} {_unit_abbr(UNIT_INCHES)}"
                            elif cur_unit == UNIT_PICAS:
                                label = f"TrimBox: {w_disp:.2f}x{h_disp:.2f} {_unit_abbr(UNIT_PICAS)}"
                            else:
                                label = f"TrimBox: {w_disp:.1f}x{h_disp:.1f} mm"
                        except Exception:
                            label = f"TrimBox: {w_mm:.1f}x{h_mm:.1f} mm"
                    else:
                        label = f"TrimBox: {w_mm:.1f}x{h_mm:.1f} mm"
                    info_items.append(
                        ft.Text(
                            label,
                            size=11,
                            color=TEXTO_COLOR_GENERICO,
                            weight=ft.FontWeight.BOLD,
                        )
                    )
            else:
                info_items.append(
                    ft.Text(
                        f"PX: {md.get('dimensiones_px')}",
                        size=11,
                        color=TEXTO_COLOR_GENERICO,
                    )
                )
                # Mostrar tamaño convertido a la unidad actual (si existe) y etiqueta localizada
                try:
                    # Preferir dimensiones almacenadas en el manager cuando existan
                    w_mm = getattr(self, "base_width", None) or 0.0
                    h_mm = getattr(self, "base_height", None) or 0.0

                    if cur_unit:
                        try:
                            w_disp = convert_from_mm(w_mm, cur_unit)
                            h_disp = convert_from_mm(h_mm, cur_unit)
                            if cur_unit == UNIT_PX:
                                size_label = f"{w_disp:.1f} x {h_disp:.1f} px"
                            elif cur_unit == UNIT_INCHES:
                                size_label = f"{w_disp:.2f} x {h_disp:.2f} {_unit_abbr(UNIT_INCHES)}"
                            elif cur_unit == UNIT_PICAS:
                                size_label = f"{w_disp:.2f} x {h_disp:.2f} {_unit_abbr(UNIT_PICAS)}"
                            else:
                                # mm por defecto
                                size_label = (
                                    f"{w_disp:.1f} x {h_disp:.1f} {_unit_abbr(UNIT_MM)}"
                                )
                        except Exception:
                            size_label = (
                                md.get("tamaño_mm") or f"{w_mm:.1f} x {h_mm:.1f} mm"
                            )
                    else:
                        # Sin unidad global: mostrar en mm (fallback)
                        size_label = (
                            md.get("tamaño_mm") or f"{w_mm:.1f} x {h_mm:.1f} mm"
                        )

                    info_items.append(
                        ft.Text(size_label, size=11, color=TEXTO_COLOR_GENERICO)
                    )
                except Exception:
                    info_items.append(
                        ft.Text(
                            md.get("tamaño_mm") or "--",
                            size=11,
                            color=TEXTO_COLOR_GENERICO,
                        )
                    )
                info_items.append(
                    ft.Text(
                        f"DPI: {md.get('resolución')}",
                        size=11,
                        color=TEXTO_COLOR_GENERICO,
                    )
                )

        # Si no hay items, usar un contenedor expandible para que la barra ocupe todo el ancho
        row_contents = info_items if info_items else [ft.Container(expand=True)]
        metadata_bar = ft.Container(
            content=ft.Row(
                row_contents,
                spacing=15,
                alignment=ft.MainAxisAlignment.START,
                scroll=ft.ScrollMode.ADAPTIVE,
            ),
            padding=ft.Padding(15, 5, 15, 5),
            bgcolor=ft.Colors.with_opacity(0.05, TEXTO_COLOR_GENERICO),
            border=ft.Border.only(
                bottom=ft.BorderSide(1, BORDE_TEXTFIELDS_COLOR)
            ),
            width=700,
        )

        # Crear el panel flotante
        floating_window = ft.Container(
            content=ft.Column(
                [
                    # Barra de título / área de arrastre
                    ft.GestureDetector(
                        content=ft.Container(
                            content=ft.Row(
                                [
                                    ft.Icon(
                                        ft.Icons.DRAG_INDICATOR,
                                        size=20,
                                        color=TEXTO_COLOR_GENERICO,
                                    ),
                                    ft.Text(
                                        t("Ajustes de página o imagen."),
                                        size=16,
                                        weight=ft.FontWeight.BOLD,
                                        color=TEXTO_COLOR_GENERICO,
                                    ),
                                    ft.IconButton(
                                        icon=ft.Icons.CLOSE,
                                        icon_size=18,
                                        icon_color=TEXTO_COLOR_GENERICO,
                                        on_click=close_floating,
                                    ),
                                ],
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            ),
                            bgcolor=ft.Colors.with_opacity(0.1, TEXTO_COLOR_GENERICO),
                            padding=ft.Padding(15, 8, 8, 8),
                            border_radius=ft.BorderRadius.only(
                                top_left=10, top_right=10
                            ),
                        ),
                        on_pan_update=on_drag,
                    ),
                    # Barra de metadatos
                    metadata_bar,
                    # Contenido (los controles)
                    ft.Container(
                        content=ft.Column(
                            [
                                dialog_content,
                                ft.Divider(height=1),
                                ft.Container(
                                    content=self._create_generic_button(
                                        t("Finalizar Ajustes"),
                                        close_floating,
                                        width=160,
                                    ),
                                    alignment=ft.Alignment.CENTER,
                                    padding=ft.Padding(0, 5, 0, 0),
                                ),
                            ],
                            spacing=10,
                            tight=True,
                        ),
                        padding=ft.Padding(15, 10, 15, 20),
                    ),
                ],
                spacing=0,
                tight=True,
            ),
            width=700,
            bgcolor=FONDO_ALERT_DIALOG,
            border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
            border_radius=10,
            left=win_x,
            top=win_y,
            shadow=ft.BoxShadow(
                blur_radius=15, spread_radius=1, color=ft.Colors.BLACK_45
            ),
            animate_position=100,  # Suavidad al mover
        )

        # Mostrar en el overlay
        self.adjustment_window = floating_window
        self.page.overlay.append(floating_window)
        self.page.update()

        # Ahora que el panel está añadido al overlay, forzar actualización
        # de los campos cuyo .value fue modificado durante la construcción
        try:
            offset_h_field.update()
        except Exception:
            pass
        try:
            offset_v_field.update()
        except Exception:
            pass
        try:
            custom_width_field.update()
        except Exception:
            pass
        try:
            custom_height_field.update()
        except Exception:
            pass

    def load_image(self, image_path: str):
        """
        Carga una imagen de fondo desde una ruta.
        TODO: Implementar la carga real de la imagen
        """
        self.image_path = image_path
        self.image_loaded = True
        print(f"[IMAGE] Imagen cargada: {image_path}")

    def clear_image(self):
        """Limpia la imagen de fondo actual"""
        # Borrar PDF temporal si existe
        if self.pdf_temp_path and os.path.exists(self.pdf_temp_path):
            try:
                os.remove(self.pdf_temp_path)
                print(f"[IMAGE] PDF temporal eliminado: {self.pdf_temp_path}")
            except Exception as e:
                print(f"[IMAGE] Error eliminando PDF temporal: {e}")
        self.image_path = None
        self.image_base64 = None
        self.source_type = None
        self.image_loaded = False
        self.pdf_page_num = 0
        self.pdf_boxes = {}
        self.pdf_temp_path = None
        self.cache_path = None
        self.current_metadata = {}

        # Liberar caché interna de PyMuPDF para evitar arrastre de memoria
        # tras haber trabajado con fondos pesados en la misma sesión.
        try:
            fitz.TOOLS.store_shrink(100)
            print("[IMAGE] Caché PyMuPDF liberada tras limpiar fondo")
        except Exception as e:
            print(f"[IMAGE] No se pudo liberar caché PyMuPDF: {e}")

        print("[IMAGE] Imagen limpiada")

    def set_app_page_size(self, width: float, height: float):
        """Actualiza las dimensiones de la página de la aplicación para cálculos de ajuste"""
        self.app_page_width = width
        self.app_page_height = height
        print(f"[IMAGE] Página App actualizada como referencia: {width}x{height}mm")

    def get_image_config(self) -> dict:
        """Retorna la configuración actual como diccionario para el visor y guardado"""
        return {
            "image_path": self.image_path,  # Cambiado de "path" a "image_path" para PDF generator
            "path": self.image_path,  # Mantener para compatibilidad con guardado de proyectos
            "type": self.source_type
            or (
                "pdf"
                if self.image_path and self.image_path.lower().endswith(".pdf")
                else "image"
            ),
            "page": self.pdf_page_num,
            "boxes": self.pdf_boxes,
            "align_to": self.align_to,
            "alignment_position": self.alignment_position,  # Para PDF generator
            "alignment": self.alignment_position,  # Para guardado de proyectos
            "offset_horizontal": self.offset_horizontal,  # Para PDF generator
            "offset_x": self.offset_horizontal,  # Para guardado de proyectos
            "offset_vertical": self.offset_vertical,  # Para PDF generator
            "offset_y": self.offset_vertical,  # Para guardado de proyectos
            "offset_unit": self.offset_unit,
            "scale": self.scale_percentage,
            "rotation": self.rotation,
            "auto_fit": self.auto_fit,
            "use_custom_size": self.use_custom_size,
            "custom_width": self.custom_width,
            "custom_height": self.custom_height,
        }

    def load_config(self, config: dict):
        """Carga configuración desde un diccionario (al cargar proyecto)"""
        self.image_path = config.get("path") or config.get("image_path")
        self.source_type = config.get("type")
        self.pdf_page_num = config.get("page", 0)
        self.pdf_boxes = config.get("boxes", {})
        self.align_to = config.get("align_to", "physical")
        self.alignment_position = config.get(
            "alignment", "center"
        )  # Coincidir con get_image_config
        self.offset_horizontal = config.get(
            "offset_x", 0.0
        )  # Coincidir con get_image_config
        self.offset_vertical = config.get(
            "offset_y", 0.0
        )  # Coincidir con get_image_config
        self.offset_unit = config.get("offset_unit", UNIT_MM)
        self.auto_fit = config.get("auto_fit", False)
        self.rotation = config.get("rotation", 0)
        self.cache_path = config.get("cache_path")
        self.use_custom_size = config.get("use_custom_size", False)
        self.custom_width = config.get("custom_width", 210.0)
        self.custom_height = config.get("custom_height", 297.0)
        self.custom_size_unit = config.get("custom_size_unit", UNIT_MM)
        self.scale_percentage = config.get(
            "scale", 100.0
        )  # Coincidir con get_image_config

        if self.image_path:
            original_exists = os.path.exists(self.image_path)

            if original_exists:
                self.image_loaded = True

                # Si el fondo es PDF, extraer página y colores spot
                is_pdf_source = self.source_type == "pdf" or (
                    isinstance(self.image_path, str)
                    and self.image_path.lower().endswith(".pdf")
                )
                if is_pdf_source and original_exists:
                    self._extract_pdf_page_to_temp(self.image_path, self.pdf_page_num)
                    try:
                        from utils.spot_color_extractor import (
                            extract_spot_colors_from_page,
                        )
                        spots = extract_spot_colors_from_page(self.image_path, self.pdf_page_num)
                        if spots and self.on_spot_colors_found:
                            self.on_spot_colors_found(spots)
                    except Exception as e:
                        print(f"[IMAGE] Error extrayendo spots en load_config: {e}")
            else:
                print(
                    f"[IMAGE] Archivo no encontrado ({self.image_path}), ignorando fondo"
                )
                self.image_path = None
                self.image_loaded = False

        print(f"[IMAGE] Configuración cargada")

    async def open_file_picker(self):
        """Abre el diálogo de selección de archivos para el fondo"""
        print("[IMAGE] Abriendo FilePicker")
        files = await self.file_picker.pick_files(
            allow_multiple=False,
            allowed_extensions=["pdf", "png", "jpg", "jpeg", "bmp"],
            dialog_title=t("Seleccionar fondo (PDF o Imagen)"),
            initial_directory=get_last_file_dialog_path(),
        )
        if files:
            self._on_file_selected(files)
        else:
            self._on_file_selected([])

    def _on_file_selected(self, files: list):
        """Maneja el resultado de la selección de archivo"""
        if not files or len(files) == 0:
            print("[IMAGE] Carga cancelada")
            return

        file_path = files[0].path
        set_last_file_dialog_path(file_path)
        filename = os.path.basename(file_path)
        ext = os.path.splitext(file_path.lower())[1]

        print(f"[IMAGE] Archivo seleccionado: {filename} ({ext})")

        self.image_path = file_path

        if ext == ".pdf":
            self.source_type = "pdf"
            self._handle_pdf_selection(file_path)
        else:
            self.source_type = "image"
            self._handle_image_selection(file_path)

    def _handle_pdf_selection(self, path):
        """Inicia el flujo para selección de página PDF"""
        print(f"[IMAGE] Iniciando flujo PDF para {path}")
        selector = PDFPageSelector(
            self.page,
            path,
            on_selected=self._on_pdf_page_selected,
            unit_getter=self.unit_getter,
        )
        selector.show()

    def _on_pdf_page_selected(self, page_idx, boxes):
        """Maneja la página seleccionada y abre el diálogo de ajuste"""
        self.pdf_page_num = page_idx
        self.pdf_boxes = boxes

        # Pre-cargar dimensiones personalizadas desde el PDF (TrimBox > CropBox > MediaBox)
        tb = boxes.get("trimbox")
        cb = boxes.get("cropbox")
        mb = boxes.get("mediabox")

        # Jerarquía de referencia para tamaño (TrimBox es el producto final)
        ref = (
            tb
            if tb and (tb[2] - tb[0] > 0)
            else (cb if cb and (cb[2] - cb[0] > 0) else mb)
        )

        if ref and len(ref) == 4:
            self.base_width = round(ref[2] - ref[0], 2)
            self.base_height = round(ref[3] - ref[1], 2)
            self.custom_width = self.base_width
            self.custom_height = self.base_height
            print(
                f"[IMAGE] Dimensiones base/custom pre-cargadas (ref: {'Trim' if ref==tb else ('Crop' if ref==cb else 'Media')}): {self.custom_width}x{self.custom_height}mm"
            )

        # Guardar metadatos para mostrar en el diálogo
        self.current_metadata = {
            "tipo": "PDF",
            "página": page_idx + 1,
            "mediabox": boxes.get("mediabox"),
            "trimbox": boxes.get("trimbox"),
            "bleedbox": boxes.get("bleedbox"),
            "cropbox": boxes.get("cropbox"),
        }

        self.image_loaded = True  # Consideramos cargado al seleccionar página
        print(f"[IMAGE] Página {page_idx + 1} seleccionada. Boxes: {boxes}")

        # Extraer la página seleccionada a un PDF temporal optimizado
        self._extract_pdf_page_to_temp(self.image_path, page_idx)

        # Extraer colores spot del PDF
        try:
            from utils.spot_color_extractor import (
                extract_spot_colors_from_page,
            )

            spots = extract_spot_colors_from_page(self.image_path, page_idx)
            if spots and self.on_spot_colors_found:
                self.on_spot_colors_found(spots)
        except Exception as _e_spot:
            print(f"[IMAGE] No se pudieron extraer spots: {_e_spot}")

        # Generar base64 para el visor (el "temporal" en preferencias)
        self._generate_base64()

        # Notificar cambio inicial al visor (para que cargue la imagen)
        if self.on_change:
            self.on_change()

        # Abrir diálogo de posicionamiento existente
        self.open_positioning_dialog()

    def _extract_pdf_page_to_temp(self, pdf_path: str, page_idx: int):
        """Extrae la página seleccionada a un PDF temporal optimizado en background_cache."""
        try:
            from utils.preferences import get_background_cache_dir

            cache_dir = get_background_cache_dir()
            # Nombre único por manager para evitar colisiones CARA/DORSO aunque
            # usen el mismo PDF y la misma página.
            import uuid

            key = uuid.uuid4().hex[:12]
            temp_path = os.path.join(str(cache_dir), f"bg_pdf_temp_{key}.pdf")

            src = fitz.open(pdf_path)
            out = fitz.open()
            out.insert_pdf(src, from_page=page_idx, to_page=page_idx)
            src.close()
            out.save(temp_path, garbage=4, deflate=False, clean=True, use_objstms=1)
            out.close()

            # Borrar temp anterior si era distinto
            if self.pdf_temp_path and self.pdf_temp_path != temp_path:
                try:
                    if os.path.exists(self.pdf_temp_path):
                        os.remove(self.pdf_temp_path)
                except Exception:
                    pass

            self.pdf_temp_path = temp_path
            print(f"[IMAGE] PDF temporal extraído y optimizado: {temp_path}")
        except Exception as e:
            print(f"[IMAGE] Error extrayendo PDF temporal: {e}")
            self.pdf_temp_path = None

    def _handle_image_selection(self, path):
        """Inicia el flujo para ajuste de imagen directa"""
        print(f"[IMAGE] Iniciando flujo Imagen para {path}")

        # Pre-cargar dimensiones de la imagen (usando fitz para detectar tamaño)
        try:
            import fitz

            doc = fitz.open(path)
            if len(doc) > 0:
                page = doc[0]
                pt_to_mm = 25.4 / 72.0
                self.base_width = round(page.rect.width * pt_to_mm, 2)
                self.base_height = round(page.rect.height * pt_to_mm, 2)
                self.custom_width = self.base_width
                self.custom_height = self.base_height

                # Intentar obtener resolución real si es posible
                # En fitz.open(imagen), page.rect son los píxeles a 72 DPI
                px_w = int(page.rect.width)
                px_h = int(page.rect.height)

                self.current_metadata = {
                    "tipo": os.path.splitext(path)[1].upper().replace(".", ""),
                    "dimensiones_px": f"{px_w} x {px_h} px",
                    "tamaño_mm": f"{self.base_width:.1f} x {self.base_height:.1f} mm",
                    "resolución": "72 DPI (aprox)",
                }
                print(f"[IMAGE] Metadatos imagen: {self.current_metadata}")
            doc.close()
        except Exception as ex:
            print(f"[IMAGE] No se pudo obtener dimensiones de imagen: {ex}")

        self.image_loaded = True

        # Generar base64 para el visor (el "temporal" en preferencias)
        self._generate_base64()

        # Notificar cambio inicial al visor
        if self.on_change:
            self.on_change()
        self.open_positioning_dialog()

    def _generate_base64(self):
        """Genera la representación base64 del fondo para el visor"""
        if not self.image_path:
            self.image_base64 = None
            return

        try:
            print(f"[IMAGE] Generando base64 temporal para el visor: {self.image_path}")
            doc = fitz.open(self.image_path)

            if self.source_type == "pdf":
                page = doc.load_page(self.pdf_page_num)
                # Usar zoom 2x para buena calidad en el visor
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                img_bytes = pix.tobytes("png")
            else:
                # Imagen normal
                page = doc.load_page(0)
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                img_bytes = pix.tobytes("png")

            self.image_base64 = base64.b64encode(img_bytes).decode("utf-8")
            doc.close()
            print(
                f"[IMAGE] Base64 generado exitosamente ({len(self.image_base64)} bytes)"
            )
        except Exception as e:
            print(f"[IMAGE] Error generando base64: {e}")
            self.image_base64 = None

    def save_preview_to_file(self, file_path: str):
        """Genera y guarda la previsualización actual a un archivo físico"""
        if not self.image_loaded or not self.image_path:
            return False

        try:
            import fitz
            import os

            # Asegurar directorio
            os.makedirs(os.path.dirname(file_path), exist_ok=True)

            doc = fitz.open(self.image_path)

            if self.source_type == "pdf":
                page = doc.load_page(self.pdf_page_num)
                pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0))
                pix.save(file_path)
            else:
                page = doc.load_page(0)
                pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0))
                pix.save(file_path)

            doc.close()
            self.cache_path = file_path
            print(f"[IMAGE] Previsualización física guardada: {file_path}")
            return True
        except Exception as e:
            print(f"[IMAGE] Error guardando previsualización física: {e}")
            return False
