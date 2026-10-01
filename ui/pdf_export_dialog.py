"""
Diálogo de exportación a PDF para PageNumber
Permite configurar rango de páginas y ruta de salida
"""

import flet as ft
from typing import Callable, Dict
import os
import sys
from i18n import t
from utils.preferences import get_last_file_dialog_path, set_last_file_dialog_path

# Silenciar prints de depuración en este módulo por defecto.
# Para activar, cambiar _PRINT_DEBUG = True durante desarrollo.
_PRINT_DEBUG = False
if not _PRINT_DEBUG:

    def _no_print(*args, **kwargs):
        return None

    print = _no_print


# Añadir el directorio padre al path para importar color_design
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from color_design import (
    FONDO_TEXTFIELDS_COLOR,
    BORDE_TEXTFIELDS_COLOR,
    BOTONES_GENERICOS_OVERLAY_COLOR,
    FONDO_ALERT_DIALOG,
    TEXTO_COLOR_GENERICO,
    TEXTOS_FASE_1_COLOR,
    BOTONES_GENERICOS_FONDO_COLOR,
    BOTONES_GENERICOS_COLOR,
    BOTONES_GENERICOS_HOVER_COLOR,
)


class PDFExportDialog:
    """Diálogo para configurar la exportación de PDF numerado"""

    # Nivel de optimización persistente entre instancias (0, 1 o 2)
    # NO USADO: la UI de optimización está comentada. Se exporta siempre "sin optimizar".
    # _last_optimize_level: int = 0

    # Persistencia del check "omitir imágenes de fondo" entre instancias
    _last_omit_background: bool = False

    def __init__(
        self,
        page: ft.Page,
        on_export: Callable[[Dict], None],
        default_start: int = 1,
        default_end: int = 1000,
        double_sided: bool = False,
        project_name: str = "numeracion",
        num_copies: int = 1,
        max_numbers: int = 0,
        has_cara_background: bool = False,
        has_dorso_background: bool = False,
    ):
        self.page = page
        self.on_export = on_export
        self.default_start = default_start
        self.default_end = default_end
        self.double_sided = double_sided
        self.project_name = project_name
        self.num_copies = max(1, int(num_copies or 1))
        # Último número del proyecto (0 = sin límite conocido)
        self.max_numbers = max(0, int(max_numbers or 0))
        self.has_cara_background = has_cara_background
        self.has_dorso_background = has_dorso_background

        # Variables de estado
        self.selected_path = None
        # Optimización fija: nivel 1 (fuentes, recomendado) — antes nivel 0 sin optimizar daba PDFs 20× con copias.
        self.optimize_level = 1
        # self.optimize_level = PDFExportDialog._last_optimize_level
        self.omit_background = PDFExportDialog._last_omit_background

        # Crear componentes
        self._create_components()

    def _create_components(self):
        """Crea los componentes del diálogo"""

        print("[DIALOG] Creando componentes del diálogo...")

        # ═══════════════════════════════════════════════════════════════════
        # CAMPOS DE RANGO
        # ═══════════════════════════════════════════════════════════════════

        self.field_start = ft.TextField(
            label=t("Desde página"),
            value=str(self.default_start),
            width=150,
            height=30,
            text_size=15,
            content_padding=ft.Padding(4, 0, 8, 0),
            filled=True,
            fill_color=FONDO_TEXTFIELDS_COLOR,
            text_style=ft.TextStyle(color=TEXTO_COLOR_GENERICO),
            label_style=ft.TextStyle(size=13, color=TEXTO_COLOR_GENERICO),
            keyboard_type=ft.KeyboardType.NUMBER,
            on_change=self._on_range_change,border=ft.OutlineInputBorder(border_radius=4, side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)))

        self.field_end = ft.TextField(
            label=t("Hasta página"),
            value=str(self.default_end),
            width=150,
            height=30,
            text_size=15,
            content_padding=ft.Padding(4, 0, 8, 0),
            filled=True,
            fill_color=FONDO_TEXTFIELDS_COLOR,
            text_style=ft.TextStyle(color=TEXTO_COLOR_GENERICO),
            label_style=ft.TextStyle(size=13, color=TEXTO_COLOR_GENERICO),
            keyboard_type=ft.KeyboardType.NUMBER,
            on_change=self._on_range_change,border=ft.OutlineInputBorder(border_radius=4, side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)))

        # Texto informativo
        self.info_text = ft.Text(
            "",
            size=14,
            color=TEXTO_COLOR_GENERICO,
            weight=ft.FontWeight.BOLD,
        )

        # Warning text (si hay error)
        self.warning_text = ft.Text(
            "",
            size=11,
            color=ft.Colors.RED_400,
            visible=False,
        )

        # Actualizar textos después de crear ambos componentes
        self._update_info_text()

        # Opción Fiery (solo visible cuando hay más de una copia configurada)
        self.fiery_checkbox = ft.Checkbox(
            label=t("Crear archivo Fiery  - Xerox"),
            value=False,
            visible=self.num_copies > 1,
            active_color=BORDE_TEXTFIELDS_COLOR,
            check_color=TEXTOS_FASE_1_COLOR,
            label_style=ft.TextStyle(
                size=13,
                color=TEXTOS_FASE_1_COLOR,
                weight=ft.FontWeight.BOLD,
            ),
            fill_color=FONDO_TEXTFIELDS_COLOR,
            border_side=ft.BorderSide(1, BORDE_TEXTFIELDS_COLOR),
            splash_radius=0,
        )

        # Check para omitir imágenes de fondo del PDF final
        _has_any_bg = self.has_cara_background or self.has_dorso_background
        self.omit_background_checkbox = ft.Checkbox(
            label=t("Omitir imágenes de fondo del PDF"),
            value=self.omit_background,
            active_color=BORDE_TEXTFIELDS_COLOR,
            check_color=TEXTOS_FASE_1_COLOR,
            label_style=ft.TextStyle(
                size=13,
                color=TEXTOS_FASE_1_COLOR,
                weight=ft.FontWeight.BOLD,
            ),
            fill_color=FONDO_TEXTFIELDS_COLOR,
            border_side=ft.BorderSide(1, BORDE_TEXTFIELDS_COLOR),
            splash_radius=0,
            on_change=self._on_omit_background_change,
            visible=_has_any_bg,
        )

        # Check para crear documento maestro (si hay imagen de fondo en cara o dorso)
        self.create_master_checkbox = ft.Checkbox(
            label=t("Crear Documento Maestro"),
            value=False,
            active_color=BORDE_TEXTFIELDS_COLOR,
            check_color=TEXTOS_FASE_1_COLOR,
            label_style=ft.TextStyle(
                size=13,
                color=TEXTOS_FASE_1_COLOR,
                weight=ft.FontWeight.BOLD,
            ),
            fill_color=FONDO_TEXTFIELDS_COLOR,
            border_side=ft.BorderSide(1, BORDE_TEXTFIELDS_COLOR),
            splash_radius=0,
            visible=_has_any_bg,
        )

        # ═══════════════════════════════════════════════════════════════════
        # SELECTOR DE OPTIMIZACIÓN  (NO USADO — comentado por petición del usuario)
        # El PDF se exporta siempre "sin optimizar" (self.optimize_level = 0).
        # Para reactivar, descomentar este bloque y el "Bloque optimización"
        # del contenido del diálogo.
        # ═══════════════════════════════════════════════════════════════════

        # _opt_labels = [
        #     t("PDF sin optimizar"),
        #     t("PDF con fuentes optimizadas"),
        #     t("PDF con fuentes e imágenes optimizadas"),
        # ]
        # _opt_descriptions = [
        #     t("Más rápido, tamaño de archivo grande"),
        #     t("Más lento, tamaño de archivo intermedio"),
        #     t("Bastante lento, tamaño de archivo mínimo"),
        # ]
        #
        # self.opt_desc_text = ft.Text(
        #     _opt_descriptions[self.optimize_level],
        #     size=12,
        #     color=TEXTO_COLOR_GENERICO,
        #     italic=False,
        #     width=380,
        #     max_lines=2,
        # )
        # self.opt_desc_container = ft.Container(
        #     content=self.opt_desc_text,
        #     height=34,
        # )
        #
        # def _on_opt_change(e):
        #     try:
        #         new_level = int(e.control.value)
        #     except (ValueError, TypeError):
        #         return
        #     self.optimize_level = new_level
        #     PDFExportDialog._last_optimize_level = new_level
        #     self.opt_desc_text.value = _opt_descriptions[new_level]
        #     self.page.update()
        #
        # self.opt_radio_group = ft.RadioGroup(
        #     value=str(self.optimize_level),
        #     on_change=_on_opt_change,
        #     content=ft.Column(
        #         [
        #             ft.Radio(
        #                 value="0",
        #                 label=_opt_labels[0],
        #                 label_style=ft.TextStyle(color=TEXTO_COLOR_GENERICO, size=13),
        #                 fill_color=BOTONES_GENERICOS_OVERLAY_COLOR,
        #             ),
        #             ft.Radio(
        #                 value="1",
        #                 label=_opt_labels[1],
        #                 label_style=ft.TextStyle(color=TEXTO_COLOR_GENERICO, size=13),
        #                 fill_color=BOTONES_GENERICOS_OVERLAY_COLOR,
        #             ),
        #             ft.Radio(
        #                 value="2",
        #                 label=_opt_labels[2],
        #                 label_style=ft.TextStyle(color=TEXTO_COLOR_GENERICO, size=13),
        #                 fill_color=BOTONES_GENERICOS_OVERLAY_COLOR,
        #             ),
        #         ],
        #         spacing=2,
        #         tight=True,
        #     ),
        # )

        # ═══════════════════════════════════════════════════════════════════
        # SELECTOR DE ARCHIVO (Y EJECUCIÓN)
        # ═══════════════════════════════════════════════════════════════════

        self.btn_select_path = ft.Button(
            t("Seleccionar Destino y Exportar"),
            on_click=self._on_select_path,
            width=240,
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

        # FilePicker
        self.file_picker = ft.FilePicker(on_result=self._on_file_picker_result)

        # ═══════════════════════════════════════════════════════════════════
        # BOTONES DE ACCIÓN
        # ═══════════════════════════════════════════════════════════════════

        self.btn_cancel = ft.Button(
            t("Cancelar"),
            on_click=self._on_cancel_click,
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

        # ═══════════════════════════════════════════════════════════════════
        # CONTENIDO DEL DIÁLOGO
        # ═══════════════════════════════════════════════════════════════════

        self.dialog = ft.AlertDialog(
            modal=True,
            title=ft.Container(
                content=ft.Text(
                    t("Exportar a PDF"),
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
                        # Bloque Rango
                        ft.Row(
                            [
                                ft.Column(
                                    [
                                        ft.Text(
                                            t("Rango de páginas"),
                                            size=13,
                                            weight=ft.FontWeight.BOLD,
                                            color=TEXTO_COLOR_GENERICO,
                                        ),
                                        ft.Row(
                                            [
                                                self.field_start,
                                                ft.Text(
                                                    t("a"),
                                                    size=13,
                                                    color=TEXTO_COLOR_GENERICO,
                                                ),
                                                self.field_end,
                                            ],
                                            spacing=10,
                                        ),
                                    ],
                                    horizontal_alignment=ft.CrossAxisAlignment.START,
                                    tight=True,
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.CENTER,
                        ),
                        # Info (centrada)
                        ft.Container(height=8),
                        self.info_text,
                        self.warning_text,
                        ft.Container(height=6),
                        ft.Row(
                            [self.fiery_checkbox, self.omit_background_checkbox, self.create_master_checkbox],
                            alignment=ft.MainAxisAlignment.CENTER,
                            spacing=24,
                        ),
                        # Separador
                        ft.Container(height=12),
                        ft.Divider(height=1, color=BORDE_TEXTFIELDS_COLOR),
                        ft.Container(height=8),
                        # Bloque optimización  (NO USADO — comentado por petición del usuario)
                        # ft.Row(
                        #     [
                        #         ft.Column(
                        #             [
                        #                 ft.Text(
                        #                     t("Optimización PDF"),
                        #                     size=13,
                        #                     weight=ft.FontWeight.BOLD,
                        #                     color=TEXTO_COLOR_GENERICO,
                        #                 ),
                        #                 ft.Container(height=4),
                        #                 self.opt_radio_group,
                        #                 ft.Container(height=4),
                        #                 self.opt_desc_container,
                        #             ],
                        #             horizontal_alignment=ft.CrossAxisAlignment.START,
                        #             tight=True,
                        #         ),
                        #     ],
                        #     alignment=ft.MainAxisAlignment.CENTER,
                        # ),
                        # Botón principal (centrado)
                        ft.Container(height=16),
                        self.btn_select_path,
                    ],
                    spacing=4,
                    tight=True,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                width=780,
                padding=20,
            ),
            actions=[self.btn_cancel],
            actions_alignment=ft.MainAxisAlignment.CENTER,
            bgcolor=FONDO_ALERT_DIALOG,
        )

        print("[DIALOG] Componentes creados correctamente")

    def _update_info_text(self):
        """Actualiza el texto informativo según el rango"""
        try:
            start = int(self.field_start.value)
            end = int(self.field_end.value)

            if start > end:
                self.warning_text.value = t(
                    "La página inicial no puede ser mayor que la final"
                )
                self.warning_text.visible = True
                self.info_text.value = ""
                return

            if start < 1:
                self.warning_text.value = t(
                    "La página inicial debe ser mayor o igual a 1"
                )
                self.warning_text.visible = True
                self.info_text.value = ""
                return

            self.warning_text.visible = False

            # El rango son NÚMEROS: el PDF emite números × copias (×2 si doble cara)
            num_pages = end - start + 1
            physical = num_pages * self.num_copies

            if self.double_sided:
                self.info_text.value = t(
                    "Se generarán {0} páginas a doble cara ({1} páginas en el PDF)"
                ).format(num_pages, physical * 2)
            else:
                self.info_text.value = t("Se generarán {0} páginas").format(physical)

        except ValueError:
            self.info_text.value = ""
            self.warning_text.visible = False

    def _on_range_change(self, e):
        """Callback cuando cambia el rango"""
        self._update_info_text()
        if self.dialog.open:
            try:
                # Solo los textos: un page.update() completo por tecla resetea el
                # buffer del TextField enfocado en Windows (se traga/reordena teclas)
                self.info_text.update()
                self.warning_text.update()
            except AssertionError:
                pass  # bug conocido de Flet con controles desmontados

    def _on_omit_background_change(self, e):
        """Callback cuando cambia el check de omitir imágenes de fondo"""
        self.omit_background = bool(e.control.value)
        PDFExportDialog._last_omit_background = self.omit_background

    async def _on_select_path(self, e):
        """Valida y abre el selector de archivo"""
        valid, error_msg = self._validate_inputs(check_path=False)
        if not valid:
            self._show_error(error_msg)
            return

        pdf_name = self.project_name
        if pdf_name.endswith(".pnb") or pdf_name.endswith(".json"):
            pdf_name = pdf_name.rsplit(".", 1)[0]

        saved_path = await self.file_picker.save_file(
            dialog_title=t("Guardar PDF como..."),
            file_name=f"{pdf_name}.pdf",
            allowed_extensions=["pdf"],
            initial_directory=get_last_file_dialog_path(),
        )
        self._on_file_picker_result(saved_path)

    def _on_file_picker_result(self, e):
        """Callback cuando se selecciona un archivo -> EJECUTA EXPORTACIÓN"""
        path = getattr(e, "path", e)
        if path:
            self.selected_path = path
            set_last_file_dialog_path(path)

            if not self.selected_path.lower().endswith(".pdf"):
                self.selected_path += ".pdf"

            self.dialog.open = False
            self.page.update()

            export_config = {
                "start_page": int(self.field_start.value),
                "end_page": int(self.field_end.value),
                "output_path": self.selected_path,
                "optimize_level": self.optimize_level,
                "copies": self.num_copies,
                "generate_fiery": (
                    self.fiery_checkbox.value if self.fiery_checkbox.visible else False
                ),
                "omit_background": self.omit_background_checkbox.value,
                "create_master": self.create_master_checkbox.value if self.create_master_checkbox.visible else False,
            }
            self.on_export(export_config)

    def _validate_inputs(self, check_path=True) -> tuple[bool, str]:
        """
        Valida los inputs del diálogo.
        Args:
            check_path: Si verificar que se haya seleccionado path (default True)
                        Para validación previa al picker, usar False.
        Returns:
            (valid, error_message)
        """
        try:
            start = int(self.field_start.value)
            end = int(self.field_end.value)
        except ValueError:
            return False, t("Los valores de página deben ser números enteros")

        if start < 1:
            return False, t("La página inicial debe ser mayor o igual a 1")

        if end < start:
            return False, t("La página final debe ser mayor o igual a la inicial")

        if self.max_numbers and end > self.max_numbers:
            return False, t("La página final supera el último número ({0})").format(
                self.max_numbers
            )

        if check_path and not self.selected_path:
            return False, t("Debe seleccionar una ubicación para guardar el PDF")

        return True, ""

    def _on_cancel_click(self, e):
        """Callback cuando se hace clic en Cancelar"""
        self.dialog.open = False
        self.page.update()

    def _show_error(self, message: str):
        """Muestra un mensaje de error"""
        self.warning_text.value = f"⚠️ {message}"
        self.warning_text.visible = True
        self.page.update()

    def show(self):
        """Muestra el diálogo"""
        try:
            print("[DIALOG] Mostrando diálogo de exportación...")

            if self.file_picker not in self.page.services:
                self.page.services.append(self.file_picker)

            self.page.show_dialog(self.dialog)
            print("[DIALOG] Diálogo mostrado correctamente")
        except Exception as e:
            print(f"[ERROR] Error mostrando diálogo: {e}")
            import traceback

            traceback.print_exc()
