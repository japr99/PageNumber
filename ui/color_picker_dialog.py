"""
Color picker dialog con soporte RGB, CMYK y SPOT (tinta plana).
Incluye muestras guardadas con drag & drop, selector de espacio de color,
y slider de tinta para colores SPOT.

Extraído de text_settings_dialog.py para uso compartido entre texto y barcode.
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import flet as ft

def _safe_page(ctrl):
    """Devuelve ctrl.page o None si no está montado (Flet 1.0: .page lanza RuntimeError)."""
    try:
        return ctrl.page
    except Exception:
        return None

from typing import Callable, Optional, Tuple

from color_design import (
    TEXTO_COLOR_GENERICO,
    FONDO_TEXTFIELDS_COLOR,
    BORDE_TEXTFIELDS_COLOR,
    FONDO_ALERT_DIALOG,
    DROPDOWN_FONDO_MENU_COLOR,
    DROPDOWN_TEXT_STYLE_COLOR,
    DROPDOWN_TRAILING_ICON_COLOR,
    BOTONES_GENERICOS_COLOR,
    BOTONES_GENERICOS_TEXTO_COLOR,
    BOTONES_GENERICOS_HOVER_COLOR,
    BOTONES_GENERICOS_OVERLAY_COLOR,
    BOTONES_GENERICOS_FONDO_COLOR,
)
from .color_picker import ColorPicker
from i18n import t


class ColorPickerDialog:
    """
    Dialogo para seleccionar color.
    Espacios de color: RGB | CMYK | SPOT (tinta plana / Separation)

    - Campo de nombre editable para todos los espacios.
    - Dropdown de colores spot extraidos de los PDFs cargados.
    - 16 muestras guardadas en preferencias, con scroll, mostrando nombre y valores.
    - Drag & drop para guardar muestras.
    """

    # Numero total de casillas de muestras
    SWATCH_COUNT = 99
    SWATCHES_PER_ROW = 3

    def __init__(
        self,
        page: ft.Page,
        on_color_selected: Callable[[str, tuple], None],
        parent_dialog=None,
        on_dismissed=None,
    ):
        self.page = page
        self.on_color_selected = on_color_selected
        self._parent_dialog = (
            parent_dialog  # referencia (ya no se usa para ocultar/mostrar)
        )
        self._on_dismissed = (
            on_dismissed  # callback para reabrir el dialogo padre al cerrar
        )
        self.current_color_space = "RGB"
        self._extracted_spots: list = []  # colores spot extraidos de los PDFs cargados
        self._spot_tint: float = 100.0  # porcentaje de tinta plana (0-100)
        self._tint_base_color: str = "#000000"  # color base sin tinte (RGB hex)
        self._tint_base_cmyk: tuple = (
            0,
            0,
            0,
            100,
        )  # CMYK base al 100% para Separation PDF

        # -- Muestras -----------------------------------------------------------
        from utils.preferences import get_color_swatches

        self.color_swatches = get_color_swatches()  # 16 slots
        # Asegurar longitud
        while len(self.color_swatches) < self.SWATCH_COUNT:
            self.color_swatches.append(None)

        # Referencias Draggable -> indice de swatch (para drag & drop entre muestras).
        # En Flet 1.0 DragTargetEvent trae `src` resuelto por uid (misma instancia),
        # así que se compara por identidad (is) contra esta lista.
        self._swatch_draggable_refs: list = []

        # -- Campo de nombre del color -------------------------------------------
        self.color_name_field = ft.TextField(
            label=t("Nombre del color"),
            height=36,
            text_size=13,
            content_padding=ft.Padding(8, 0, 8, 0),
            filled=True,
            fill_color=FONDO_TEXTFIELDS_COLOR,
            text_style=ft.TextStyle(color=TEXTO_COLOR_GENERICO),
            label_style=ft.TextStyle(size=11, color=TEXTO_COLOR_GENERICO),
            expand=True,border=ft.OutlineInputBorder(border_radius=4, side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)))

        # -- Dropdown de spots extraidos (visible solo cuando hay spots) ---------
        self._spots_label = ft.Text(
            t("Colores del PDF"),
            size=11,
            width=90,
            color=TEXTO_COLOR_GENERICO,
        )
        self._spots_menu_text = ft.Text(
            "\u2014",
            size=12,
            color=DROPDOWN_TEXT_STYLE_COLOR,
            no_wrap=True,
        )
        self._spots_popup = ft.PopupMenuButton(
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
            items=[],  # se rellenan con set_extracted_spots()
        )
        self._spots_row = ft.Row(
            [
                self._spots_label,
                ft.Container(
                    width=270,
                    height=30,
                    padding=ft.Padding(8, 0, 2, 0),
                    border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
                    border_radius=3,
                    bgcolor=FONDO_TEXTFIELDS_COLOR,
                    content=ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=0,
                        controls=[
                            self._spots_menu_text,
                            self._spots_popup,
                        ],
                    ),
                ),
            ],
            spacing=8,
            visible=False,
        )

        # -- Dropdown espacio de color -------------------------------------------
        self.color_space_text = ft.Text(
            "RGB",
            size=12,
            color=DROPDOWN_TEXT_STYLE_COLOR,
            no_wrap=True,
        )

        def on_color_space_change(text_value: str):
            self.current_color_space = text_value
            self.color_space_text.value = text_value
            self.color_picker.set_color_space(text_value)
            # Mostrar/ocultar fila de spots segun si hay spots y espacio SPOT
            self._spots_row.visible = bool(self._extracted_spots)
            # Mostrar fila de tinta solo cuando el espacio es SPOT
            self._tint_row.visible = text_value == "SPOT"
            # Actualizar nombre automatico si esta vacio o fue auto-generado
            current_name = self.color_name_field.value.strip()
            is_auto_name = (
                not current_name
                or current_name.startswith("RGB ")
                or current_name.startswith("CMYK ")
                or current_name.startswith("SPOT ")
            )
            if is_auto_name:
                self._auto_fill_name_from_values()
            self._update_swatches_display()
            self.color_space_text.update()
            self._spots_row.update()
            self._tint_row.update()

        def on_space_item_click(e):
            on_color_space_change(e.control.content)

        self.color_space_dropdown = ft.Row(
            [
                ft.Text(t("Espacio"), size=12, width=50, color=TEXTO_COLOR_GENERICO),
                ft.Container(
                    width=110,
                    height=30,
                    padding=ft.Padding(8, 0, 2, 0),
                    border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
                    border_radius=3,
                    bgcolor=FONDO_TEXTFIELDS_COLOR,
                    content=ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=0,
                        controls=[
                            self.color_space_text,
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
                                        content="RGB", on_click=on_space_item_click
                                    ),
                                    ft.PopupMenuItem(
                                        content="CMYK", on_click=on_space_item_click
                                    ),
                                    ft.PopupMenuItem(
                                        content="SPOT", on_click=on_space_item_click
                                    ),
                                ],
                            ),
                        ],
                    ),
                ),
            ],
            spacing=8,
        )

        # -- Slider de tinta % (solo visible para SPOT) -------------------------
        self._tint_label = ft.Text(
            "100%",
            size=12,
            width=38,
            text_align=ft.TextAlign.RIGHT,
            color=TEXTO_COLOR_GENERICO,
        )

        def _on_tint_slider_change(e):
            tint = float(e.control.value)
            self._spot_tint = tint
            self._tint_label.value = f"{tint:.0f}%"
            # Calcular color tintado: mezcla lineal color_base -> blanco
            # formula: canal_tintado = 255 + (canal_base - 255) * tint / 100
            try:
                from .color_picker import hex2rgb, hex2hsv

                r0, g0, b0 = hex2rgb(self._tint_base_color)
                t = tint / 100.0
                r = max(0, min(255, int(round(255 + (r0 - 255) * t))))
                g = max(0, min(255, int(round(255 + (g0 - 255) * t))))
                b = max(0, min(255, int(round(255 + (b0 - 255) * t))))
                tinted_hex = f"#{r:02x}{g:02x}{b:02x}"
                # Asignar al picker el color tintado
                self.color_picker.color = tinted_hex
                # Forzar skip_cmyk_update=False para que CMYK se recalcule
                self.color_picker._skip_cmyk_update = False
                # Actualizar todos los campos de texto (rgb, hex, cmyk, preview_circle, thumb)
                self.color_picker.update_color_field_values()
                self.color_picker.color_fields.update()
                # Actualizar posicion del thumb en el mapa de color
                self.color_picker.update_circle_position()
                self.color_picker.thumb.update()
                # Actualizar posicion del hue slider
                self.color_picker.hue_slider.hue = hex2hsv(tinted_hex)[0]
                self.color_picker.hue_slider.update()
            except Exception as ex:
                import traceback

                print(f"[TINT_SLIDER] Error calculando color: {ex}")
                traceback.print_exc()
            self._tint_label.update()

        self._tint_slider = ft.Slider(
            min=0,
            max=100,
            value=100,
            divisions=100,
            label="{value}%",
            expand=True,
            on_change=_on_tint_slider_change,
            active_color=BOTONES_GENERICOS_COLOR,
            inactive_color=BORDE_TEXTFIELDS_COLOR,
            thumb_color=BOTONES_GENERICOS_COLOR,
        )

        self._tint_row = ft.Row(
            [
                ft.Text(t("Tinta"), size=12, width=42, color=TEXTO_COLOR_GENERICO),
                ft.Text("0%", size=10, color=TEXTO_COLOR_GENERICO),
                self._tint_slider,
                self._tint_label,
            ],
            spacing=6,
            visible=False,  # solo aparece cuando se selecciona SPOT
        )

        # -- ColorPicker principal -----------------------------------------------
        self.color_picker = ColorPicker(
            color="#000000",
            width=580,
            color_space_dropdown=self.color_space_dropdown,
        )

        def _on_picker_manual_color_change(new_hex: str):
            """Se dispara cuando el usuario cambia el color (mapa HSV, tono o
            entrada CMYK manual). Actualiza _tint_base_color/_tint_base_cmyk
            para que el slider de tinta use el color elegido como base."""
            self._tint_base_color = new_hex
            try:
                self._tint_base_cmyk = tuple(self._current_cmyk())
            except Exception:
                pass

            # Actualizar nombre auto-generado si aplica
            current_name = self.color_name_field.value.strip()
            if (
                not current_name
                or current_name.startswith("RGB ")
                or current_name.startswith("CMYK ")
                or current_name.startswith("SPOT ")
            ):
                try:
                    self._auto_fill_name_from_values()
                except Exception:
                    pass

        self.color_picker.on_color_change = _on_picker_manual_color_change

        # -- Callbacks Accept / Cancel -------------------------------------------
        def on_accept(e):
            # Recopilar datos ANTES de cambiar estado de dialogos
            callback = self.on_color_selected
            color_data = None
            if callback:
                if self.current_color_space == "SPOT":
                    rgb_color = self._tint_base_color
                    cmyk = self._tint_base_cmyk
                else:
                    rgb_color = self.color_picker.color
                    try:
                        cmyk = (
                            float(self.color_picker.cmyk_c.value),
                            float(self.color_picker.cmyk_m.value),
                            float(self.color_picker.cmyk_y.value),
                            float(self.color_picker.cmyk_k.value),
                        )
                    except Exception:
                        from .color_picker import hex2rgb, rgb_to_cmyk

                        r, g, b = hex2rgb(rgb_color)
                        cmyk = rgb_to_cmyk(r, g, b)

                color_name = self.color_name_field.value.strip()
                if not color_name:
                    color_name = self._generate_default_name(rgb_color, cmyk)
                tint = self._spot_tint
                color_data = (
                    rgb_color,
                    cmyk,
                    self.current_color_space,
                    color_name,
                    tint,
                )

            # Cerrar SOLO el picker (el padre sigue abierto debajo)
            self.page.pop_dialog()
            # Forzar re-render del stack para que el padre reaparezca YA
            # (si no, Flutter tarda en redibujarlo hasta el próximo update)
            try:
                self.page._dialogs.update()
            except Exception:
                try:
                    self.page.update()
                except Exception:
                    pass

            # Llamar callback con datos de color
            if callback and color_data:
                callback(*color_data)

            # Padre ya open: _reopen solo fuerza update de nuevo (barato)
            self._schedule_reopen()

        def on_cancel(e):
            self.page.pop_dialog()
            try:
                self.page._dialogs.update()
            except Exception:
                try:
                    self.page.update()
                except Exception:
                    pass
            self._schedule_reopen()

        # -- Botones -------------------------------------------------------------
        _btn_style = ft.ButtonStyle(
            color={
                ft.ControlState.DEFAULT: BOTONES_GENERICOS_COLOR,
                "hovered": BOTONES_GENERICOS_HOVER_COLOR,
            },
            overlay_color=BOTONES_GENERICOS_OVERLAY_COLOR,
            padding=ft.Padding(0, 0, 0, 0),
            shape=ft.RoundedRectangleBorder(radius=10),
        )
        _buttons_row = ft.Row(
            [
                ft.Button(
                    t("Cancelar"),
                    on_click=on_cancel,
                    width=110,
                    bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
                    style=_btn_style,
                ),
                ft.Button(
                    t("Aceptar"),
                    on_click=on_accept,
                    width=110,
                    bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
                    style=_btn_style,
                ),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=10,
        )

        # -- Columna izquierda: picker + nombre + spots --------------------------
        _left_col = ft.Column(
            [
                ft.Text(
                    t("Selector de color"),
                    weight=ft.FontWeight.BOLD,
                    size=16,
                    color=TEXTO_COLOR_GENERICO,
                ),
                ft.Divider(height=1, color=BORDE_TEXTFIELDS_COLOR),
                self.color_picker,
                ft.Divider(height=1, color=BORDE_TEXTFIELDS_COLOR),
                ft.Row(
                    [
                        ft.Text(
                            t("Nombre"), size=12, width=90, color=TEXTO_COLOR_GENERICO
                        ),
                        self.color_name_field,
                    ],
                    spacing=8,
                ),
                self._tint_row,
                self._spots_row,
            ],
            spacing=8,
            tight=True,
            width=580,
        )

        # -- Columna derecha: muestras guardadas ---------------------------------
        self._swatches_scroll_container = ft.Container(
            content=ft.Column(controls=[], scroll=ft.ScrollMode.AUTO),
            expand=True,
        )
        _right_col = ft.Column(
            [
                ft.Text(
                    t("Muestras guardadas"),
                    size=16,
                    weight=ft.FontWeight.BOLD,
                    color=TEXTO_COLOR_GENERICO,
                ),
                ft.Divider(height=1, color=BORDE_TEXTFIELDS_COLOR),
                self._swatches_scroll_container,
                _buttons_row,
            ],
            spacing=8,
            expand=True,
        )

        # -- Layout 2 columnas ---------------------------------------------------
        _main_row = ft.Row(
            [
                _left_col,
                ft.VerticalDivider(width=1, color=BORDE_TEXTFIELDS_COLOR),
                ft.Container(content=_right_col, expand=True),
            ],
            spacing=16,
            expand=True,
            vertical_alignment=ft.CrossAxisAlignment.STRETCH,
        )

        # -- BottomSheet ---------------------------------------------------------
        self.dialog = ft.AlertDialog(
            modal=False,  # No modal para evitar doble scrim al apilarse sobre el dialogo padre
            title=None,
            content=ft.Container(
                content=_main_row,
                width=1230,
                height=800,
                padding=ft.Padding(12, 10, 12, 10),
                bgcolor=FONDO_ALERT_DIALOG,
                border_radius=8,
                clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            ),
            content_padding=ft.Padding(0, 0, 0, 0),
            actions_padding=ft.Padding(0, 0, 0, 0),
            actions=[],
            actions_alignment=ft.MainAxisAlignment.CENTER,
            bgcolor=FONDO_ALERT_DIALOG,
            shape=ft.RoundedRectangleBorder(radius=8),
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            inset_padding=ft.Padding(0, 0, 0, 0),
        )
        # Alias de compatibilidad
        self.bottom_sheet = self.dialog

    # -- Helpers -----------------------------------------------------------------

    def _generate_default_name(self, rgb_hex: str, cmyk: tuple) -> str:
        """Genera un nombre automatico basado en el espacio de color actual."""
        if self.current_color_space == "RGB":
            try:
                from .color_picker import hex2rgb

                r, g, b = hex2rgb(rgb_hex)
                return f"RGB {r},{g},{b}"
            except Exception:
                return rgb_hex
        elif self.current_color_space == "CMYK":
            return f"CMYK {cmyk[0]:.0f},{cmyk[1]:.0f},{cmyk[2]:.0f},{cmyk[3]:.0f}"
        else:  # SPOT
            return f"SPOT {cmyk[0]:.0f},{cmyk[1]:.0f},{cmyk[2]:.0f},{cmyk[3]:.0f}"

    def _auto_fill_name_from_values(self):
        """Rellena el nombre automaticamente segun el espacio de color actual."""
        try:
            rgb_hex = self.color_picker.color
            cmyk = tuple(self._current_cmyk())
            name = self._generate_default_name(rgb_hex, cmyk)
            self.color_name_field.value = name
            if hasattr(self.color_name_field, "update"):
                try:
                    self.color_name_field.update()
                except Exception:
                    pass
        except Exception:
            pass

    def _current_cmyk(self) -> tuple:
        """CMYK canonico (los campos del picker mandan en CMYK/SPOT).

        Si _skip_cmyk_update esta activo, los campos guardan el CMYK tecleado o
        cargado (artes graficas: no se recalculan desde un hex de 8 bits). Si no,
        se deriva del hex actual (el usuario eligio el color por una accion RGB).
        """
        if getattr(self.color_picker, "_skip_cmyk_update", False):
            try:
                return (
                    float(self.color_picker.cmyk_c.value),
                    float(self.color_picker.cmyk_m.value),
                    float(self.color_picker.cmyk_y.value),
                    float(self.color_picker.cmyk_k.value),
                )
            except (ValueError, TypeError):
                pass
        from .color_picker import hex2rgb, rgb_to_cmyk

        r, g, b = hex2rgb(self.color_picker.color)
        return rgb_to_cmyk(r, g, b)

    def set_extracted_spots(self, spots: list):
        """
        Actualiza la lista de colores spot extraidos de los PDFs cargados.
        Llamado desde main_screen cuando se carga un PDF.

        Args:
            spots: lista de dicts {'name', 'alternate', 'cmyk', 'rgb'}
        """
        self._extracted_spots = spots or []

        # Reconstruir items del popup
        items = []
        for spot in self._extracted_spots:
            name = spot.get("name", "?")
            cmyk = spot.get("cmyk")
            if cmyk is None:
                cmyk = (0, 0, 0, 100)

            def make_handler(s=spot):
                def handler(e):
                    rgb = s.get("rgb", "#000000")
                    # -- Base color y CMYK ---------------------------------------
                    self._tint_base_color = rgb
                    try:
                        bc, bm, by, bk = s.get("cmyk") or (0, 0, 0, 100)
                        self._tint_base_cmyk = (
                            float(bc),
                            float(bm),
                            float(by),
                            float(bk),
                        )
                    except Exception:
                        bc, bm, by, bk = 0, 0, 0, 100
                        self._tint_base_cmyk = (0, 0, 0, 100)
                    # -- Espacio de color: forzar SPOT ---------------------------
                    self.current_color_space = "SPOT"
                    self.color_space_text.value = "SPOT"
                    self.color_picker.set_color_space("SPOT")
                    # -- Aplicar color al picker y actualizar todos los campos ----
                    self.color_picker.color = rgb
                    # Los campos CMYK muestran el cmyk base del spot (verdad)
                    try:
                        self.color_picker.cmyk_c.value = f"{bc:.0f}"
                        self.color_picker.cmyk_m.value = f"{bm:.0f}"
                        self.color_picker.cmyk_y.value = f"{by:.0f}"
                        self.color_picker.cmyk_k.value = f"{bk:.0f}"
                    except Exception:
                        pass
                    self.color_picker._skip_cmyk_update = True
                    self.color_picker.update_color_field_values()
                    self.color_picker.color_fields.update()
                    self.color_picker.update_circle_position()
                    self.color_picker.thumb.update()
                    # -- Slider de tinta: resetear a 100% -------------------------
                    self._spot_tint = 100.0
                    self._tint_slider.value = 100
                    self._tint_label.value = "100%"
                    self._tint_row.visible = True
                    # -- Nombre ---------------------------------------------------
                    self.color_name_field.value = s.get("name", "")
                    self._spots_menu_text.value = s.get("name", "")
                    self.page.update()

                return handler

            items.append(
                ft.PopupMenuItem(
                    content=f"{name}  ({cmyk[0]:.0f},{cmyk[1]:.0f},{cmyk[2]:.0f},{cmyk[3]:.0f})",
                    on_click=make_handler(),
                )
            )

        self._spots_popup.items = items
        self._spots_row.visible = bool(self._extracted_spots)
        # Refrescar UI si el dialogo ya esta montado en la pagina
        try:
            self._spots_row.update()
        except Exception:
            pass

    # -- Swatches -----------------------------------------------------------------

    def _swatch_text_color(self, bg_hex: str) -> str:
        """Devuelve blanco u oscuro segun luminosidad del fondo."""
        try:
            r = int(bg_hex[1:3], 16)
            g = int(bg_hex[3:5], 16)
            b = int(bg_hex[5:7], 16)
            lum = 0.299 * r + 0.587 * g + 0.114 * b
            return "#FFFFFF" if lum < 128 else "#000000"
        except Exception:
            return "#FFFFFF"

    def _create_swatch_container(self, index: int):
        """Crea un container de muestra de color con drag & drop."""
        swatch_data = (
            self.color_swatches[index] if index < len(self.color_swatches) else None
        )

        if swatch_data:
            bg_color = swatch_data.get("rgb", "#888888")
            text_color = self._swatch_text_color(bg_color)
            name = swatch_data.get("name", "") or swatch_data.get("color_name", "")
            space = swatch_data.get("space", "RGB")
            cmyk = swatch_data.get("cmyk", (0, 0, 0, 100))

            # Prefijo de tinta para SPOT
            tint = swatch_data.get("tint", 100)
            tint_pct = f" {tint:.0f}% -" if space == "SPOT" else ""

            # Linea superior: nombre (si existe) o valores
            if name:
                top_text = name
                # Linea inferior: valores segun espacio guardado
                if space == "RGB":
                    try:
                        from .color_picker import hex2rgb

                        r, g, b = hex2rgb(bg_color)
                        bottom_text = f"RGB {r},{g},{b}"
                    except Exception:
                        bottom_text = bg_color
                elif space == "SPOT":
                    bottom_text = f"SPOT{tint_pct} {cmyk[0]:.0f},{cmyk[1]:.0f},{cmyk[2]:.0f},{cmyk[3]:.0f}"
                else:
                    bottom_text = (
                        f"CMYK {cmyk[0]:.0f},{cmyk[1]:.0f},{cmyk[2]:.0f},{cmyk[3]:.0f}"
                    )
            else:
                # Sin nombre: mostrar valores segun espacio visualizado actualmente
                if space == "RGB":
                    try:
                        from .color_picker import hex2rgb

                        r, g, b = hex2rgb(bg_color)
                        top_text = f"RGB {r},{g},{b}"
                    except Exception:
                        top_text = bg_color
                elif space == "SPOT":
                    top_text = f"SPOT{tint_pct} {cmyk[0]:.0f},{cmyk[1]:.0f},{cmyk[2]:.0f},{cmyk[3]:.0f}"
                else:
                    top_text = (
                        f"CMYK {cmyk[0]:.0f},{cmyk[1]:.0f},{cmyk[2]:.0f},{cmyk[3]:.0f}"
                    )
                bottom_text = ""
            border_color = BORDE_TEXTFIELDS_COLOR
        else:
            bg_color = FONDO_TEXTFIELDS_COLOR
            text_color = TEXTO_COLOR_GENERICO
            top_text = ""
            bottom_text = ""
            border_color = BORDE_TEXTFIELDS_COLOR
            name = ""

        # -- Callbacks -----------------------------------------------------------

        def on_drag_accept(e: ft.DragTargetEvent, _idx=index):
            """Al soltar algo sobre esta muestra.
            - Si viene de otra muestra: intercambiar posiciones.
            - Si viene del preview circle: guardar color actual.
            """
            try:
                # Detectar si es un drag entre muestras buscando la instancia
                # origen por identidad (e.src se resuelve por src_id a la misma
                # instancia Draggable de _create_swatch_container).
                src_idx = None
                for _drag_ref, _drag_idx in self._swatch_draggable_refs:
                    if _drag_ref is e.src:
                        src_idx = _drag_idx
                        break
                if src_idx is not None:
                    if src_idx == _idx:
                        return  # Soltar sobre si mismo, no hacer nada
                    # Intercambiar posiciones
                    self.color_swatches[src_idx], self.color_swatches[_idx] = (
                        self.color_swatches[_idx],
                        self.color_swatches[src_idx],
                    )
                    from utils.preferences import save_color_swatches

                    save_color_swatches(self.color_swatches)
                    self._update_swatches_display()
                    return

                # Viene del preview circle: guardar color actual
                from .color_picker import hex2rgb, rgb_to_cmyk

                rgb_color = self.color_picker.color
                try:
                    cmyk_color = (
                        float(self.color_picker.cmyk_c.value),
                        float(self.color_picker.cmyk_m.value),
                        float(self.color_picker.cmyk_y.value),
                        float(self.color_picker.cmyk_k.value),
                    )
                except Exception:
                    r2, g2, b2 = hex2rgb(rgb_color)
                    cmyk_color = rgb_to_cmyk(r2, g2, b2)

                # Siempre guardar los valores actuales del picker (ya tintados si SPOT)
                saved_rgb = rgb_color
                saved_cmyk = cmyk_color

                current_name = self.color_name_field.value.strip()
                # Si el nombre fue auto-generado con otro espacio, regenerar
                _auto_prefixes = ("RGB ", "CMYK ", "SPOT ")
                if not current_name or any(
                    current_name.startswith(p) for p in _auto_prefixes
                ):
                    current_name = self._generate_default_name(saved_rgb, saved_cmyk)

                # Comprobar si ya existe una muestra identica
                for existing in self.color_swatches:
                    if existing is None:
                        continue
                    if existing.get("space", "") != self.current_color_space:
                        continue
                    if existing.get("name", "") != current_name:
                        continue
                    # Comparar CMYK redondeado (evita diferencias de decimales)
                    ex_cmyk = existing.get("cmyk", (0, 0, 0, 0))
                    try:
                        same_cmyk = all(
                            round(float(a)) == round(float(b))
                            for a, b in zip(ex_cmyk, saved_cmyk)
                        )
                    except Exception:
                        same_cmyk = False
                    if same_cmyk:
                        # Ya existe, no guardar duplicado
                        return

                self.color_swatches[_idx] = {
                    "rgb": saved_rgb,
                    "cmyk": saved_cmyk,
                    "space": self.current_color_space,
                    "name": current_name,
                    "tint": self._spot_tint,
                }
                from utils.preferences import save_color_swatches

                save_color_swatches(self.color_swatches)
                self._update_swatches_display()
            except Exception as ex:
                print(f"[SWATCH] Error drag-accept idx={_idx}: {ex}")

        def on_swatch_click(e, _idx=index):
            """Clic: cargar el color de la muestra al picker."""
            sd = self.color_swatches[_idx] if _idx < len(self.color_swatches) else None
            if sd:
                rgb = sd.get("rgb", "#000000")
                space = sd.get("space", "RGB")
                tint = float(sd.get("tint", 100.0))

                # -- Color base y CMYK base ---------------------------------------
                self._tint_base_color = rgb
                try:
                    c2, m2, y2, k2 = sd.get("cmyk", (0, 0, 0, 100))
                    self._tint_base_cmyk = (float(c2), float(m2), float(y2), float(k2))
                except Exception:
                    self._tint_base_cmyk = (0, 0, 0, 100)
                    c2, m2, y2, k2 = 0, 0, 0, 100

                # -- Calcular color a mostrar en el picker (base o tintado) -------
                from .color_picker import hex2rgb, hex2hsv

                if space == "SPOT" and tint < 99.9:
                    r0, g0, b0 = hex2rgb(rgb)
                    t = tint / 100.0
                    pr = max(0, min(255, int(round(255 + (r0 - 255) * t))))
                    pg = max(0, min(255, int(round(255 + (g0 - 255) * t))))
                    pb = max(0, min(255, int(round(255 + (b0 - 255) * t))))
                    display_color = f"#{pr:02x}{pg:02x}{pb:02x}"
                else:
                    display_color = rgb

                # -- Espacio de color (ANTES de actualizar campos para que
                #    color_fields.update() renderice el dropdown correcto) ---------
                self.current_color_space = space
                self.color_space_text.value = space
                self.color_picker.set_color_space(space)

                # Los campos CMYK muestran el cmyk guardado de la muestra (verdad,
                # no se recalculan desde el hex)
                try:
                    self.color_picker.cmyk_c.value = f"{c2:.0f}"
                    self.color_picker.cmyk_m.value = f"{m2:.0f}"
                    self.color_picker.cmyk_y.value = f"{y2:.0f}"
                    self.color_picker.cmyk_k.value = f"{k2:.0f}"
                except Exception:
                    pass
                self.color_picker._skip_cmyk_update = space in ("CMYK", "SPOT")

                # Asignar color al picker y actualizar todos sus campos
                self.color_picker.color = display_color
                self.color_picker.update_color_field_values()
                self.color_picker.color_fields.update()
                self.color_picker.update_circle_position()
                self.color_picker.thumb.update()

                # -- Nombre -------------------------------------------------------
                self.color_name_field.value = sd.get("name", "") or sd.get(
                    "color_name", ""
                )

                # -- Tinta --------------------------------------------------------
                self._spot_tint = tint
                self._tint_slider.value = tint
                self._tint_label.value = f"{tint:.0f}%"
                self._tint_row.visible = space == "SPOT"
                self._spots_row.visible = (space == "SPOT") and bool(
                    self._extracted_spots
                )

                try:
                    self.color_space_text.update()
                    self._tint_row.update()
                    self._spots_row.update()
                except AssertionError:
                    pass

                self.page.update()

        def on_delete_click(e, _idx=index):
            self.color_swatches[_idx] = None
            from utils.preferences import save_color_swatches

            save_color_swatches(self.color_swatches)
            self._update_swatches_display()

        # -- Contenido visual -----------------------------------------------------
        if swatch_data:
            inner = ft.Stack(
                controls=[
                    ft.Container(
                        content=ft.Column(
                            [
                                ft.Text(
                                    top_text,
                                    size=10,
                                    color=text_color,
                                    text_align=ft.TextAlign.CENTER,
                                    weight=ft.FontWeight.BOLD,
                                    overflow=ft.TextOverflow.ELLIPSIS,
                                    max_lines=1,
                                ),
                                (
                                    ft.Text(
                                        bottom_text,
                                        size=9,
                                        color=text_color,
                                        text_align=ft.TextAlign.CENTER,
                                        max_lines=1,
                                        overflow=ft.TextOverflow.ELLIPSIS,
                                    )
                                    if bottom_text
                                    else ft.Container(height=0)
                                ),
                            ],
                            spacing=2,
                            alignment=ft.MainAxisAlignment.CENTER,
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        expand=True,
                        height=44,
                        bgcolor=bg_color,
                        border=ft.Border.all(1, border_color),
                        border_radius=4,
                        alignment=ft.Alignment.CENTER,
                        padding=ft.Padding(4, 4, 4, 4),
                    ),
                    ft.Container(
                        content=ft.IconButton(
                            icon=ft.Icons.CLOSE,
                            icon_size=13,
                            icon_color=text_color,
                            on_click=on_delete_click,
                            tooltip=t("Eliminar muestra"),
                            padding=0,
                            width=18,
                            height=18,
                        ),
                        top=2,
                        right=2,
                    ),
                ],
                expand=True,
                height=44,
            )
            # Envolver en Draggable para reordenar entre muestras
            draggable_inner = ft.Draggable(
                content=ft.GestureDetector(content=inner, on_tap=on_swatch_click),
                content_feedback=ft.Container(
                    width=100,
                    height=50,
                    bgcolor=bg_color,
                    border_radius=4,
                    opacity=0.7,
                    border=ft.Border.all(2, BOTONES_GENERICOS_COLOR),
                    content=ft.Text(
                        top_text,
                        size=9,
                        color=text_color,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    alignment=ft.Alignment.CENTER,
                ),
            )
            # Registrar referencia Draggable -> indice de swatch
            self._swatch_draggable_refs.append((draggable_inner, index))
        else:
            inner = ft.Container(
                expand=True,
                height=44,
                bgcolor=bg_color,
                border=ft.Border.all(1, border_color),
                border_radius=4,
            )
            draggable_inner = ft.GestureDetector(content=inner, on_tap=on_swatch_click)

        return ft.Container(
            content=ft.DragTarget(
                content=draggable_inner,
                on_accept=on_drag_accept,
            ),
            expand=True,
        )

    def _update_swatches_display(self):
        """Regenera todas las casillas de muestra y actualiza el contenedor."""
        # Limpiar referencias de draggables al regenerar
        self._swatch_draggable_refs = []
        # Asegurar que la lista tenga suficientes slots
        while len(self.color_swatches) < self.SWATCH_COUNT:
            self.color_swatches.append(None)
        n_rows = (
            self.SWATCH_COUNT + self.SWATCHES_PER_ROW - 1
        ) // self.SWATCHES_PER_ROW
        rows = []
        for row_idx in range(n_rows):
            row_swatches = []
            for col_idx in range(self.SWATCHES_PER_ROW):
                abs_idx = row_idx * self.SWATCHES_PER_ROW + col_idx
                if abs_idx < self.SWATCH_COUNT:
                    row_swatches.append(self._create_swatch_container(abs_idx))
            rows.append(ft.Row(spacing=4, controls=row_swatches, expand=True))
        self.swatches_grid = ft.Container(
            content=ft.Column(spacing=4, controls=rows),
            padding=ft.Padding(0, 0, 14, 0),
        )
        # Actualizar el contenedor de scroll
        if hasattr(self, "_swatches_scroll_container"):
            self._swatches_scroll_container.content.controls = [self.swatches_grid]
        if _safe_page(self):
            try:
                self.page.update()
            except Exception:
                pass

    def _build_swatches_grid(self):
        """Construye el grid inicial y lo inyecta en el contenedor de scroll."""
        self._update_swatches_display()

    # -- API publica -------------------------------------------------------------

    def _schedule_reopen(self) -> None:
        """Padre ya está open debajo: solo sync del stack (sin sleep, sin show_dialog)."""
        if not self._on_dismissed:
            return
        try:
            self._on_dismissed()
        except Exception as ex:
            print(f"[COLOR_PICKER] Error reabriendo diálogo padre: {ex}")

    def open(
        self,
        rgb_color: str = "#000000",
        cmyk_color: tuple = None,
        color_space: str = "RGB",
        color_name: str = "",
        tint: float = 100.0,
    ):
        """Abre el BottomSheet inicializando el picker con los valores dados."""
        if cmyk_color is None:
            from .color_picker import hex2rgb, rgb_to_cmyk

            r, g, b = hex2rgb(rgb_color)
            cmyk_color = rgb_to_cmyk(r, g, b)

        self.color_picker.color = rgb_color
        self.color_picker.set_color_space(color_space)
        self.current_color_space = color_space
        self.color_space_text.value = color_space

        # Rellenar CMYK en los campos del picker para que sean correctos desde el inicio.
        # CMYK y SPOT son los espacios de artes graficas: los campos mandan y no se
        # recalculan desde el hex (solo una accion visual del mapa/tono lo hara).
        try:
            self.color_picker.cmyk_c.value = f"{cmyk_color[0]:.0f}"
            self.color_picker.cmyk_m.value = f"{cmyk_color[1]:.0f}"
            self.color_picker.cmyk_y.value = f"{cmyk_color[2]:.0f}"
            self.color_picker.cmyk_k.value = f"{cmyk_color[3]:.0f}"
            self.color_picker._skip_cmyk_update = color_space in ("CMYK", "SPOT")
        except Exception:
            pass

        # Nombre del color
        self.color_name_field.value = color_name
        # Resetear seleccion anterior del dropdown de spots
        self._spots_menu_text.value = "\u2014"

        # Tinta
        self._spot_tint = max(0.0, min(100.0, float(tint)))
        self._tint_base_color = rgb_color  # guardar base sin tinte (RGB hex)
        # Guardar CMYK base al 100% para PDF Separation
        try:
            self._tint_base_cmyk = (
                float(cmyk_color[0]),
                float(cmyk_color[1]),
                float(cmyk_color[2]),
                float(cmyk_color[3]),
            )
        except Exception:
            self._tint_base_cmyk = (0, 0, 0, 100)
        self._tint_slider.value = self._spot_tint
        self._tint_label.value = f"{self._spot_tint:.0f}%"
        self._tint_row.visible = color_space == "SPOT"
        # Si hay tinte activo para SPOT, inicializar picker con el color tintado
        if color_space == "SPOT" and self._spot_tint < 99.9:
            try:
                from .color_picker import hex2rgb, hex2hsv

                r0, g0, b0 = hex2rgb(rgb_color)
                t = self._spot_tint / 100.0
                r = max(0, min(255, int(round(255 + (r0 - 255) * t))))
                g = max(0, min(255, int(round(255 + (g0 - 255) * t))))
                b = max(0, min(255, int(round(255 + (b0 - 255) * t))))
                tinted_hex = f"#{r:02x}{g:02x}{b:02x}"
                self.color_picker.color = tinted_hex
                self.color_picker._skip_cmyk_update = False
                self.color_picker.update_color_field_values()
            except Exception:
                pass

        # Mostrar fila de spots si hay
        self._spots_row.visible = bool(self._extracted_spots)

        # Recargar muestras desde preferencias (pueden haber cambiado)
        from utils.preferences import get_color_swatches

        self.color_swatches = get_color_swatches()
        while len(self.color_swatches) < self.SWATCH_COUNT:
            self.color_swatches.append(None)

        self._update_swatches_display()

        # Abrir encima del padre (el padre sigue abierto debajo)
        from ui.dialog_utils import purge_stale_dialog

        purge_stale_dialog(self.page, self.dialog)
        self.page.show_dialog(self.dialog)
