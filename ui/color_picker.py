"""
Color Picker personalizado con soporte RGB y CMYK
Extraído y adaptado de flet-contrib/color_picker
"""

import colorsys
import flet as ft
import sys
import os

# Añadir el directorio padre al path para importar color_design
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from color_design import (
    BORDE_TEXTFIELDS_COLOR,
    TEXTO_COLOR_GENERICO,
    FONDO_TEXTFIELDS_COLOR,
)

# Internacionalización dentro de PageNumber
from i18n import t

# ============================================================================
# FUNCIONES DE CONVERSIÓN
# ============================================================================


def rgb2hex(rgb):
    """Convierte RGB normalizado (0-1) a hex (#RRGGBB)"""
    return "#{:02x}{:02x}{:02x}".format(
        round(rgb[0] * 255.0), round(rgb[1] * 255.0), round(rgb[2] * 255.0)
    )


def hex2rgb(value):
    """Convierte hex (#RRGGBB) a RGB (0-255)"""
    value = value.lstrip("#")
    lv = len(value)
    return tuple(int(value[i : i + lv // 3], 16) for i in range(0, lv, lv // 3))


def hex2hsv(value):
    """Convierte hex (#RRGGBB) a HSV (0-1)"""
    rgb_color = hex2rgb(value)
    return colorsys.rgb_to_hsv(
        rgb_color[0] / 255, rgb_color[1] / 255, rgb_color[2] / 255
    )


def rgb_to_cmyk(r: int, g: int, b: int) -> tuple[float, float, float, float]:
    """
    Convierte RGB (0-255) a CMYK (0-100)

    Args:
        r, g, b: valores RGB en rango 0-255

    Returns:
        (c, m, y, k) cada valor en rango 0-100
    """
    # Normalizar RGB a 0-1
    r_norm = r / 255.0
    g_norm = g / 255.0
    b_norm = b / 255.0

    # Calcular K (negro)
    k = 1 - max(r_norm, g_norm, b_norm)

    # Calcular CMY
    if k < 1:
        c = (1 - r_norm - k) / (1 - k)
        m = (1 - g_norm - k) / (1 - k)
        y = (1 - b_norm - k) / (1 - k)
    else:
        # Cuando k=1 (negro puro RGB 0,0,0), CMY debe ser 0
        # RGB no puede representar CMYK con múltiples canales al 100%
        c = 0
        m = 0
        y = 0

    # Convertir a porcentaje (0-100)
    return c * 100, m * 100, y * 100, k * 100


def cmyk_to_rgb(c: float, m: float, y: float, k: float) -> tuple[int, int, int]:
    """
    Convierte CMYK (0-100) a RGB (0-255)
    Si hay valores CMYK no reproducibles en RGB (K=100 + cualquier CMY=100), retorna negro.

    Args:
        c, m, y, k: valores CMYK en rango 0-100

    Returns:
        (r, g, b) cada valor en rango 0-255
    """
    # Detectar valores no reproducibles en RGB: K=100 y algún canal CMY también al 100%
    if k >= 100 and (c >= 100 or m >= 100 or y >= 100):
        # No reproducible en RGB, retornar negro
        return 0, 0, 0

    # Normalizar CMYK a 0-1
    c_norm = c / 100.0
    m_norm = m / 100.0
    y_norm = y / 100.0
    k_norm = k / 100.0

    # Calcular RGB con fórmula estándar
    r = 255 * (1 - c_norm) * (1 - k_norm)
    g = 255 * (1 - m_norm) * (1 - k_norm)
    b = 255 * (1 - y_norm) * (1 - k_norm)

    return int(r), int(g), int(b)


# ============================================================================
# HUE SLIDER
# ============================================================================

SLIDER_WIDTH = 380
CIRCLE_SIZE = 16


class HueSlider(ft.GestureDetector):
    def __init__(self, on_change_hue, hue=1):
        super().__init__()
        self.__hue = hue
        self.__number_of_hues = 10
        self.content = ft.Stack(height=CIRCLE_SIZE, width=SLIDER_WIDTH)
        self.generate_slider()
        self.on_change_hue = on_change_hue
        self.on_pan_start = self.drag_start
        self.on_pan_update = self.drag_update

    @property
    def hue(self) -> float:
        return self.__hue

    @hue.setter
    def hue(self, value: float):
        if isinstance(value, float):
            self.__hue = value
            if value < 0 or value > 1:
                raise Exception("Hue value should be between 0 and 1")
        else:
            raise Exception("Hue value should be a float number")

    def _before_build_command(self):
        super()._before_build_command()
        self.thumb.left = self.__hue * self.track.width
        self.thumb.bgcolor = rgb2hex(colorsys.hsv_to_rgb(self.__hue, 1, 1))

    def __update_selected_hue(self, x):
        self.__hue = max(0, min((x - CIRCLE_SIZE / 2) / self.track.width, 1))
        self.thumb.left = self.__hue * self.track.width
        self.thumb.bgcolor = rgb2hex(colorsys.hsv_to_rgb(self.__hue, 1, 1))

    def update_selected_hue(self, x):
        self.__update_selected_hue(x)
        self.thumb.update()
        self.on_change_hue()

    def drag_start(self, e: ft.DragStartEvent):
        self.update_selected_hue(x=e.local_position.x)

    def drag_update(self, e: ft.DragUpdateEvent):
        self.update_selected_hue(x=e.local_position.x)

    def generate_gradient_colors(self):
        colors = []
        for i in range(0, self.__number_of_hues + 1):
            color = rgb2hex(colorsys.hsv_to_rgb(i / self.__number_of_hues, 1, 1))
            colors.append(color)
        return colors

    def generate_slider(self):
        self.track = ft.Container(
            gradient=ft.LinearGradient(
                begin=ft.Alignment.CENTER_LEFT,
                end=ft.Alignment.CENTER_RIGHT,
                colors=self.generate_gradient_colors(),
            ),
            width=SLIDER_WIDTH - CIRCLE_SIZE,
            height=CIRCLE_SIZE / 2,
            border_radius=5,
            top=CIRCLE_SIZE / 4,
            left=CIRCLE_SIZE / 2,
        )

        self.thumb = ft.Container(
            width=CIRCLE_SIZE,
            height=CIRCLE_SIZE,
            border_radius=CIRCLE_SIZE,
            border=ft.Border.all(width=2, color="white"),
        )

        self.content.controls.append(self.track)
        self.content.controls.append(self.thumb)


# ============================================================================
# COLOR PICKER
# ============================================================================

COLOR_MATRIX_WIDTH = 340
PICKER_CIRCLE_SIZE = 20


class ColorPicker(ft.Column):
    """
    Widget de selección de color con:
    - Matriz HSV interactiva
    - Slider de matiz
    - Campos Hex, RGB y CMYK
    """

    def __init__(self, color="#000000", width=460, color_space_dropdown=None):
        super().__init__()
        self.tight = True
        self.spacing = 0
        self.width = width
        self.__color = color
        self._skip_cmyk_update = (
            False  # Flag para no resetear CMYK cuando se edita manualmente
        )
        self._color_space = "RGB"  # Espacio de color actual
        self._color_space_dropdown = color_space_dropdown  # Dropdown externo
        self.on_color_change = (
            None  # Callback(hex_color) cuando el usuario cambia el color manualmente
        )
        self.hue_slider = HueSlider(
            on_change_hue=self.update_color_picker_on_hue_change,
            hue=hex2hsv(self.color)[0],
        )
        self.generate_color_map()
        self.generate_color_fields()

    @property
    def color(self):
        return self.__color

    @color.setter
    def color(self, value):
        self.__color = value

    def set_color_space(self, space: str):
        """Actualiza el espacio de color para el draggable"""
        self._color_space = space

    def before_update(self):
        super().before_update()
        self.hue_slider.hue = hex2hsv(self.color)[0]
        self.update_circle_position()
        self.update_color_map()
        self.update_color_field_values()

    def update_circle_position(self):
        hsv_color = hex2hsv(self.color)
        self.thumb.left = hsv_color[1] * self.color_map.width
        self.thumb.top = (1 - hsv_color[2]) * self.color_map.height

    def find_color(self, x, y):
        h = self.hue_slider.hue
        s = x / self.color_map.width
        v = (self.color_map.height - y) / self.color_map.height
        # Accion visual RGB: el CMYK se recalcula desde el color elegido
        self._skip_cmyk_update = False
        self.color = rgb2hex(colorsys.hsv_to_rgb(h, s, v))
        if self.on_color_change:
            try:
                self.on_color_change(self.__color)
            except Exception:
                pass

    def generate_color_fields(self):
        """Crea los campos de entrada para Hex, RGB y CMYK"""
        rgb = hex2rgb(self.color)
        cmyk = rgb_to_cmyk(*rgb)

        # Callbacks
        def on_hex_submit(e):
            try:
                # Validar formato hex
                color = e.control.value
                if not color.startswith("#"):
                    color = "#" + color
                if len(color) == 7:
                    # Accion RGB: el CMYK se recalcula desde el hex elegido
                    self._skip_cmyk_update = False
                    self.color = color
                    self.update()
            except:
                pass

        def on_rgb_submit(e):
            try:
                r = int(self.r.value)
                g = int(self.g.value)
                b = int(self.b.value)
                # Validar rango
                if 0 <= r <= 255 and 0 <= g <= 255 and 0 <= b <= 255:
                    rgb_norm = (r / 255, g / 255, b / 255)
                    # Accion RGB: el CMYK se recalcula desde el color elegido
                    self._skip_cmyk_update = False
                    self.color = rgb2hex(rgb_norm)
                    self.update()
            except:
                pass

        def on_cmyk_submit(e):
            try:
                c = float(self.cmyk_c.value)
                m = float(self.cmyk_m.value)
                y = float(self.cmyk_y.value)
                k = float(self.cmyk_k.value)
                # Validar rango
                if 0 <= c <= 100 and 0 <= m <= 100 and 0 <= y <= 100 and 0 <= k <= 100:
                    # Convertir CMYK a RGB unicamente para el preview visual
                    r, g, b = cmyk_to_rgb(c, m, y, k)
                    rgb_norm = (r / 255, g / 255, b / 255)
                    # CMYK y SPOT son los espacios de artes graficas: los campos
                    # mandan y no se recalculan desde el hex (solo el mapa/tono
                    # volveran a derivarlos).
                    self._skip_cmyk_update = True
                    self.color = rgb2hex(rgb_norm)
                    # Actualizar solo los campos RGB y Hex, no CMYK
                    self.hex.value = self.__color
                    self.r.value = str(r)
                    self.g.value = str(g)
                    self.b.value = str(b)
                    self.color_fields.controls[0].controls[0].bgcolor = self.color
                    self.thumb.bgcolor = self.color
                    self.update()
                    # Notificar al dialogo (nombre auto-generado, tinta SPOT)
                    if self.on_color_change:
                        try:
                            self.on_color_change(self.__color)
                        except Exception:
                            pass
            except:
                pass

        # Campos Hex
        self.hex = ft.TextField(
            value=self.__color,
            height=30,
            width=90,
            text_size=15,
            content_padding=ft.Padding(4, 0, 8, 0),
            filled=True,
            fill_color=FONDO_TEXTFIELDS_COLOR,
            text_style=ft.TextStyle(color=TEXTO_COLOR_GENERICO),
            on_submit=on_hex_submit,
            on_blur=on_hex_submit,border=ft.OutlineInputBorder(border_radius=4, side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)))

        # Campos RGB
        self.r = ft.TextField(
            label=t("R"),
            value=str(rgb[0]),
            height=30,
            width=55,
            text_size=15,
            content_padding=ft.Padding(4, 0, 8, 0),
            filled=True,
            fill_color=FONDO_TEXTFIELDS_COLOR,
            text_style=ft.TextStyle(color=TEXTO_COLOR_GENERICO),
            label_style=ft.TextStyle(size=13, color=TEXTO_COLOR_GENERICO),
            on_submit=on_rgb_submit,
            on_blur=on_rgb_submit,border=ft.OutlineInputBorder(border_radius=4, side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)))
        self.g = ft.TextField(
            label=t("G"),
            value=str(rgb[1]),
            height=30,
            width=55,
            text_size=15,
            content_padding=ft.Padding(4, 0, 8, 0),
            filled=True,
            fill_color=FONDO_TEXTFIELDS_COLOR,
            text_style=ft.TextStyle(color=TEXTO_COLOR_GENERICO),
            label_style=ft.TextStyle(size=13, color=TEXTO_COLOR_GENERICO),
            on_submit=on_rgb_submit,
            on_blur=on_rgb_submit,border=ft.OutlineInputBorder(border_radius=4, side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)))
        self.b = ft.TextField(
            label=t("B"),
            value=str(rgb[2]),
            height=30,
            width=55,
            text_size=15,
            content_padding=ft.Padding(4, 0, 8, 0),
            filled=True,
            fill_color=FONDO_TEXTFIELDS_COLOR,
            text_style=ft.TextStyle(color=TEXTO_COLOR_GENERICO),
            label_style=ft.TextStyle(size=13, color=TEXTO_COLOR_GENERICO),
            on_submit=on_rgb_submit,
            on_blur=on_rgb_submit,border=ft.OutlineInputBorder(border_radius=4, side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)))

        # Campos CMYK
        self.cmyk_c = ft.TextField(
            label=t("C"),
            value=f"{cmyk[0]:.0f}",
            height=30,
            width=55,
            text_size=15,
            content_padding=ft.Padding(4, 0, 8, 0),
            filled=True,
            fill_color=FONDO_TEXTFIELDS_COLOR,
            text_style=ft.TextStyle(color=TEXTO_COLOR_GENERICO),
            label_style=ft.TextStyle(size=13, color=TEXTO_COLOR_GENERICO),
            on_submit=on_cmyk_submit,
            on_blur=on_cmyk_submit,border=ft.OutlineInputBorder(border_radius=4, side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)))
        self.cmyk_m = ft.TextField(
            label=t("M"),
            value=f"{cmyk[1]:.0f}",
            height=30,
            width=55,
            text_size=15,
            content_padding=ft.Padding(4, 0, 8, 0),
            filled=True,
            fill_color=FONDO_TEXTFIELDS_COLOR,
            text_style=ft.TextStyle(color=TEXTO_COLOR_GENERICO),
            label_style=ft.TextStyle(size=13, color=TEXTO_COLOR_GENERICO),
            on_submit=on_cmyk_submit,
            on_blur=on_cmyk_submit,border=ft.OutlineInputBorder(border_radius=4, side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)))
        self.cmyk_y = ft.TextField(
            label=t("Y"),
            value=f"{cmyk[2]:.0f}",
            height=30,
            width=55,
            text_size=15,
            content_padding=ft.Padding(4, 0, 8, 0),
            filled=True,
            fill_color=FONDO_TEXTFIELDS_COLOR,
            text_style=ft.TextStyle(color=TEXTO_COLOR_GENERICO),
            label_style=ft.TextStyle(size=13, color=TEXTO_COLOR_GENERICO),
            on_submit=on_cmyk_submit,
            on_blur=on_cmyk_submit,border=ft.OutlineInputBorder(border_radius=4, side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)))
        self.cmyk_k = ft.TextField(
            label=t("K"),
            value=f"{cmyk[3]:.0f}",
            height=30,
            width=55,
            text_size=15,
            content_padding=ft.Padding(4, 0, 8, 0),
            filled=True,
            fill_color=FONDO_TEXTFIELDS_COLOR,
            text_style=ft.TextStyle(color=TEXTO_COLOR_GENERICO),
            label_style=ft.TextStyle(size=13, color=TEXTO_COLOR_GENERICO),
            on_submit=on_cmyk_submit,
            on_blur=on_cmyk_submit,border=ft.OutlineInputBorder(border_radius=4, side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)))

        # Layout: Preview + Hue slider + 3 filas de valores con títulos
        # Crear Draggable para el círculo preview
        self.preview_circle = ft.Container(
            width=60,
            height=60,
            border_radius=30,
            bgcolor=self.__color,
            border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
        )

        self.preview_draggable = ft.Draggable(
            content=self.preview_circle,
        )

        self.color_fields = ft.Column(
            spacing=6,
            controls=[
                # Preview + Hue Slider
                ft.Row(
                    alignment=ft.MainAxisAlignment.START,
                    spacing=16,
                    controls=[
                        self.preview_draggable,
                        self.hue_slider,
                    ],
                ),
                # Hint text + divider
                ft.Text(
                    t(
                        "Arrastra el círculo de vista previa a una muestra vacia para guardar el color."
                    ),
                    size=13,
                    color=TEXTO_COLOR_GENERICO,
                    italic=True,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Divider(height=1, color=BORDE_TEXTFIELDS_COLOR),
                # Hex
                ft.Row(
                    [
                        ft.Text(
                            t("Hex"), size=12, width=50, color=TEXTO_COLOR_GENERICO
                        ),
                        self.hex,
                    ],
                    spacing=8,
                ),
                # RGB
                ft.Row(
                    [
                        ft.Text(
                            t("RGB"), size=12, width=50, color=TEXTO_COLOR_GENERICO
                        ),
                        self.r,
                        self.g,
                        self.b,
                    ],
                    spacing=8,
                ),
                # CMYK
                ft.Row(
                    [
                        ft.Text(
                            t("CMYK"), size=12, width=50, color=TEXTO_COLOR_GENERICO
                        ),
                        self.cmyk_c,
                        self.cmyk_m,
                        self.cmyk_y,
                        self.cmyk_k,
                    ],
                    spacing=8,
                ),
            ],
        )

        # Agregar dropdown de espacio si fue proporcionado
        if self._color_space_dropdown:
            self.color_fields.controls.append(self._color_space_dropdown)

        self.controls.append(self.color_fields)

    def update_color_field_values(self):
        """Actualiza todos los campos cuando cambia el color"""
        rgb = hex2rgb(self.color)
        if self._skip_cmyk_update:
            try:
                # CMYK es la verdad (artes graficas): no recalcularlo desde el hex
                cmyk = (
                    float(self.cmyk_c.value),
                    float(self.cmyk_m.value),
                    float(self.cmyk_y.value),
                    float(self.cmyk_k.value),
                )
            except (ValueError, TypeError):
                # Campo cmyk vacio/incompleto -> derivar del hex como fallback
                cmyk = rgb_to_cmyk(*rgb)
        else:
            cmyk = rgb_to_cmyk(*rgb)

        # Preview circle
        self.preview_circle.bgcolor = self.color

        # Actualizar data del draggable con color actual
        import json

        self.preview_draggable.data = json.dumps(
            {"rgb": self.color, "cmyk": list(cmyk), "space": self._color_space}
        )

        # Hex
        self.hex.value = self.__color

        # RGB
        self.r.value = str(rgb[0])
        self.g.value = str(rgb[1])
        self.b.value = str(rgb[2])

        # CMYK - Solo actualizar si no se está editando manualmente
        if not self._skip_cmyk_update:
            self.cmyk_c.value = f"{cmyk[0]:.0f}"
            self.cmyk_m.value = f"{cmyk[1]:.0f}"
            self.cmyk_y.value = f"{cmyk[2]:.0f}"
            self.cmyk_k.value = f"{cmyk[3]:.0f}"

        # Thumb color
        self.thumb.bgcolor = self.color

    def generate_color_map(self):
        """Genera la matriz de selección de color HSV"""

        def __move_circle(x, y):
            self.thumb.top = max(
                0, min(y - PICKER_CIRCLE_SIZE / 2, self.color_map.height)
            )
            self.thumb.left = max(
                0, min(x - PICKER_CIRCLE_SIZE / 2, self.color_map.width)
            )
            self.find_color(x=self.thumb.left, y=self.thumb.top)
            self.update_color_field_values()

        def on_pan_update(e: ft.DragStartEvent):
            __move_circle(x=e.local_position.x, y=e.local_position.y)
            self.color_fields.update()
            self.thumb.update()

        self.color_map_container = ft.GestureDetector(
            content=ft.Stack(
                width=self.width,
                height=int(self.width * 3 / 5),
            ),
            on_pan_start=on_pan_update,
            on_pan_update=on_pan_update,
        )

        saturation_container = ft.Container(
            gradient=ft.LinearGradient(
                begin=ft.Alignment.CENTER_LEFT,
                end=ft.Alignment.CENTER_RIGHT,
                colors=[ft.Colors.WHITE, ft.Colors.RED],
            ),
            width=self.color_map_container.content.width - PICKER_CIRCLE_SIZE,
            height=self.color_map_container.content.height - PICKER_CIRCLE_SIZE,
            border_radius=5,
        )

        self.color_map = ft.ShaderMask(
            top=PICKER_CIRCLE_SIZE / 2,
            left=PICKER_CIRCLE_SIZE / 2,
            content=saturation_container,
            blend_mode=ft.BlendMode.MULTIPLY,
            shader=ft.LinearGradient(
                begin=ft.Alignment.TOP_CENTER,
                end=ft.Alignment.BOTTOM_CENTER,
                colors=[ft.Colors.WHITE, ft.Colors.BLACK],
            ),
            border_radius=5,
            width=saturation_container.width,
            height=saturation_container.height,
        )

        self.thumb = ft.Container(
            width=PICKER_CIRCLE_SIZE,
            height=PICKER_CIRCLE_SIZE,
            border_radius=PICKER_CIRCLE_SIZE,
            border=ft.Border.all(width=2, color="white"),
            bgcolor=ft.Colors.TRANSPARENT,
        )

        self.color_map_container.content.controls.append(self.color_map)
        self.color_map_container.content.controls.append(self.thumb)
        self.controls.append(self.color_map_container)

    def update_color_map(self):
        """Actualiza la matriz de color cuando cambia el matiz"""
        h = self.hue_slider.hue
        s = hex2hsv(self.color)[1]
        v = hex2hsv(self.color)[2]

        container_gradient_colors = [
            rgb2hex(colorsys.hsv_to_rgb(h, 0, 1)),
            rgb2hex(colorsys.hsv_to_rgb(h, 1, 1)),
        ]

        self.color_map.content.gradient.colors = container_gradient_colors
        self.color = rgb2hex(colorsys.hsv_to_rgb(h, s, v))

    def update_color_picker_on_hue_change(self):
        """Callback cuando cambia el slider de matiz"""
        # Accion visual RGB: el CMYK se recalcula desde el nuevo tono
        self._skip_cmyk_update = False
        self.update_color_map()
        self.update_color_field_values()
        self.color_fields.update()
        self.color_map_container.update()
        if self.on_color_change:
            try:
                self.on_color_change(self.__color)
            except Exception:
                pass
