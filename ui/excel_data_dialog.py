"""
Dialogo de carga y gestion de datos externos (Excel/CSV).
Muestra un ListView con los datos cargados, campos de prefijo/sufijo,
y validacion de filas vs paginas del proyecto.
Todas las notificaciones se muestran como popups dentro del dialogo principal.
"""

from __future__ import annotations

import gc
import os
import sys
from typing import Callable, Optional

import flet as ft
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from color_design import (
    TEXTO_COLOR_GENERICO,
    FONDO_TEXTFIELDS_COLOR,
    BORDE_TEXTFIELDS_COLOR,
    FONDO_SECCIONES,
    FONDO_ALERT_DIALOG,
    SUCCESS_COLOR,
    ERROR_COLOR,
    BOTONES_GENERICOS_COLOR,
    BOTONES_GENERICOS_HOVER_COLOR,
    BOTONES_GENERICOS_OVERLAY_COLOR,
    BOTONES_GENERICOS_FONDO_COLOR,
    FONDO_BLOQUE_RESUMEN_COLOR,
    TEXTOS_FASE_1_COLOR,
)
from i18n import t
from utils.excel_manager import ExcelManager
from utils.preferences import get_last_file_dialog_path, set_last_file_dialog_path


class ExcelDataDialog:
    # ponytail: limit preview to 200 rows — no need to render 5000+ Flet widgets
    _MAX_PREVIEW = 200
    """Dialogo para cargar y gestionar archivos de datos externos.

    Permite:
    - Cargar archivos Excel/CSV
    - Ver previsualizacion completa en ListView
    - Configurar prefijo y sufijo
    - Validar filas vs paginas del proyecto
    - Confirmar o cancelar la carga
    """

    def __init__(
        self,
        page: ft.Page,
        excel_manager: ExcelManager,
        get_global_settings_fn: Callable[[], dict],
        on_data_loaded: Optional[Callable] = None,
        on_modified: Optional[Callable] = None,
        on_excel_cleared: Optional[Callable] = None,
        barcode_profile_manager=None,
        vt_profile_manager=None,
    ):
        self.page = page
        self.excel_manager = excel_manager
        self.get_global_settings = get_global_settings_fn
        self.on_data_loaded = on_data_loaded
        self.on_modified = on_modified
        self.on_excel_cleared = on_excel_cleared
        self.barcode_profile_manager = barcode_profile_manager
        self.vt_profile_manager = vt_profile_manager

        self.dialog: Optional[ft.AlertDialog] = None
        self.dialog_root_stack: Optional[ft.Stack] = None
        self._filepath_field: Optional[ft.Text] = None
        self._page_count_text: Optional[ft.Text] = None
        self._row_count_text: Optional[ft.Text] = None
        self._data_container: Optional[ft.Container] = None
        self._btn_accept: Optional[ft.Button] = None
        self._btn_remove: Optional[ft.Button] = None

        # Preview: local copy of Excel data for UI display only
        self._preview = {
            "filepath": None,
            "columns": [],
            "row_count": 0,
            "rows_data": [],
        }
        # Batch: pending operations, applied only on Accept
        self._batch = {
            "excel_action": None,  # None, "load", "remove"
            "excel_path": None,
        }

        # Crear FilePicker UNA VEZ y reutilizarlo (no acumular en overlay)
        self._file_picker = ft.FilePicker(on_result=self._on_file_picked)
        self.page.services.append(self._file_picker)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_total_pages(self) -> int:
        gs = self.get_global_settings()
        start = int(gs.get("start", 1))
        end = int(gs.get("end", 1))
        increment = int(gs.get("increment", 1))
        copies = int(gs.get("copies", 1))
        if increment == 0:
            increment = 1
        total_numbers = ((end - start) // increment) + 1
        return total_numbers * copies

    def _show_popup(self, title: str, message: str, btn_label: str = None):
        """Muestra un popup centrado con shadow sobre el dialogo."""
        if btn_label is None:
            btn_label = t("Aceptar")

        def on_close(e):
            self._remove_last_popup()

        _btn_style = ft.ButtonStyle(
            color={ft.ControlState.DEFAULT: BOTONES_GENERICOS_COLOR, "hovered": BOTONES_GENERICOS_HOVER_COLOR},
            overlay_color=BOTONES_GENERICOS_OVERLAY_COLOR,
            padding=ft.Padding(0, 0, 0, 0),
            shape=ft.RoundedRectangleBorder(radius=10),
        )

        popup_content = ft.Container(
            content=ft.Column(
                [
                    ft.Text(title, weight=ft.FontWeight.BOLD, size=18, color=TEXTO_COLOR_GENERICO),
                    ft.Container(height=10),
                    ft.Text(message, size=13, color=TEXTO_COLOR_GENERICO),
                    ft.Container(height=15),
                    ft.Row(
                        [ft.Button(btn_label, on_click=on_close, width=110, bgcolor=BOTONES_GENERICOS_FONDO_COLOR, style=_btn_style)],
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),
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

    def _show_confirm(self, title: str, message: str, on_accept, on_cancel=None, on_cancel_label: str = None, accept_label: str = None):
        """Muestra un popup de confirmacion centrado con shadow."""
        if on_cancel_label is None:
            on_cancel_label = t("Cancelar")
        if accept_label is None:
            accept_label = t("Aceptar")

        def on_cancel_click(e):
            self._remove_last_popup()
            if on_cancel:
                on_cancel()

        def on_accept_click(e):
            self._remove_last_popup()
            on_accept()

        _btn_style = ft.ButtonStyle(
            color={ft.ControlState.DEFAULT: BOTONES_GENERICOS_COLOR, "hovered": BOTONES_GENERICOS_HOVER_COLOR},
            overlay_color=BOTONES_GENERICOS_OVERLAY_COLOR,
            padding=ft.Padding(0, 0, 0, 0),
            shape=ft.RoundedRectangleBorder(radius=10),
        )

        popup_content = ft.Container(
            content=ft.Column(
                [
                    ft.Text(title, weight=ft.FontWeight.BOLD, size=18, color=TEXTO_COLOR_GENERICO),
                    ft.Container(height=10),
                    ft.Text(message, size=13, color=TEXTO_COLOR_GENERICO),
                    ft.Container(height=15),
                    ft.Row(
                        [
                            ft.Button(on_cancel_label, on_click=on_cancel_click, width=110, bgcolor=BOTONES_GENERICOS_FONDO_COLOR, style=_btn_style),
                            ft.Button(accept_label, on_click=on_accept_click, width=110, bgcolor=BOTONES_GENERICOS_FONDO_COLOR, style=_btn_style),
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                        spacing=15,
                    ),
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

    # ------------------------------------------------------------------
    # File loading
    # ------------------------------------------------------------------

    def _on_file_picked(self, e):
        files = getattr(e, "files", e) or []
        if files:
            filepath = files[0].path
            set_last_file_dialog_path(filepath)
            if self._preview["filepath"]:
                if filepath == self._preview["filepath"]:
                    return
                old_name = os.path.basename(self._preview["filepath"])
                new_name = os.path.basename(filepath)
                self._confirm_replace_file(old_name, new_name, filepath)
            else:
                self._try_load_file(filepath)

    async def _pick_file(self, e):
        files = await self._file_picker.pick_files(
            allow_multiple=False,
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["xlsx", "xls", "csv"],
            initial_directory=get_last_file_dialog_path(),
        )
        self._on_file_picked(files)

    def _confirm_replace_file(self, old_name: str, new_name: str, filepath: str):
        msg = t("Ya hay un archivo cargado: '{0}'.\nSe reemplazara por: '{1}'.\n\n").format(old_name, new_name)
        msg += t("¿Desea continuar?")

        def on_accept():
            self._batch["excel_action"] = "load"
            self._batch["excel_path"] = filepath
            self._load_file_preview(filepath)

        self._show_confirm(t("Reemplazar archivo"), msg, on_accept=on_accept)

    def _on_remove_excel(self, e):
        self._clear_preview()
        self._btn_accept.disabled = False
        self._batch["excel_action"] = "remove"
        self.page.update()

    def _load_file_preview(self, filepath: str):
        """Load file into preview (local DataFrame), set batch. Doesn't touch singleton."""
        ok, msg, df = self._read_file_local(filepath)
        if not ok:
            self._show_popup(t("Error al cargar archivo"), msg)
            return

        rows = len(df)
        total_pages = self._get_total_pages()

        cols = [str(c) for c in df.columns.tolist()]
        rows_data = df.fillna("").astype(str).values.tolist()

        if rows < total_pages:
            self._confirm_fewer_rows(filepath, rows, total_pages, cols, rows_data)
            return

        if rows > total_pages:
            extra = rows - total_pages
            self._confirm_extra_rows(filepath, rows, total_pages, extra, cols, rows_data)
            return

        self._apply_preview(filepath, cols, rows, rows_data)
        self._refresh_ui()
        self.page.update()

    def _apply_preview(self, filepath, cols, rows, rows_data):
        self._preview["filepath"] = filepath
        self._preview["columns"] = cols
        self._preview["row_count"] = rows
        self._preview["rows_data"] = rows_data
        self._batch["excel_action"] = "load"
        self._batch["excel_path"] = filepath

    def _read_file_local(self, filepath: str) -> tuple:
        """Read file into a local DataFrame without touching the singleton."""
        ext = os.path.splitext(filepath)[1].lower()
        try:
            if ext in (".xlsx", ".xls"):
                df = pd.read_excel(filepath, sheet_name=0, dtype=str, engine="calamine")
            elif ext == ".csv":
                df = pd.read_csv(filepath, dtype=str)
            else:
                return False, t("Formato no soportado"), None
        except Exception as ex:
            return False, str(ex), None
        if df.empty:
            return False, t("El archivo esta vacio"), None
        df = df.fillna("")
        df.columns = df.columns.astype(str)
        return True, "", df

    def _try_load_file(self, filepath: str):
        """Entry point for first file load (no replace). Delegates to preview load."""
        self._load_file_preview(filepath)

    def _confirm_fewer_rows(self, filepath: str, rows: int, total_pages: int, cols: list, rows_data: list):
        """Dialogo informativo cuando el archivo tiene menos filas que paginas."""
        missing = total_pages - rows

        def on_accept():
            self._apply_preview(filepath, cols, rows, rows_data)
            self._refresh_ui()
            self.page.update()

        self._show_confirm(
            t("Menos filas que paginas"),
            t("El archivo tiene {0} filas pero hay {1} paginas.\nLas {2} paginas sin datos no tendran texto variable.\n\n¿Desea continuar?").format(rows, total_pages, missing),
            on_accept=on_accept,
        )

    def _confirm_extra_rows(self, filepath: str, rows: int, total_pages: int, extra: int, cols: list, rows_data: list):
        def on_accept():
            self._apply_preview(filepath, cols, rows, rows_data)
            self._refresh_ui()
            self.page.update()

        self._show_confirm(
            t("Mas filas que paginas"),
            t("El archivo tiene {0} filas pero solo hay {1} paginas.\nSe perderan las {2} filas restantes.\n\n¿Desea continuar?").format(rows, total_pages, extra),
            on_accept=on_accept,
        )

    def _refresh_ui(self):
        p = self._preview
        filename = os.path.basename(p["filepath"]) if p["filepath"] else ""

        self._filepath_field.value = f"{filename} \u2705"
        total_pages = self._get_total_pages()
        rows = p["row_count"]
        if rows > total_pages:
            unused = rows - total_pages
            self._row_count_text.value = t("Filas: {0} ({1} usadas, {2} sin usar)").format(rows, total_pages, unused)
            self._row_count_text.color = TEXTOS_FASE_1_COLOR
        else:
            self._row_count_text.value = t("Filas: {0}").format(rows)
            self._row_count_text.color = TEXTO_COLOR_GENERICO
        self._page_count_text.value = t("Paginas actuales: {0}").format(total_pages)
        self._btn_accept.disabled = False
        self._populate_listview()

    def _snapshot_singleton_to_preview(self):
        """Copy singleton state into preview on dialog open."""
        em = self.excel_manager
        if em.is_loaded:
            rows_data = em._df.head(self._MAX_PREVIEW).fillna("").astype(str).values.tolist()
            self._preview = {
                "filepath": em.filepath,
                "columns": list(em.columns),
                "row_count": em.row_count,
                "rows_data": rows_data,
            }
        else:
            self._preview = {
                "filepath": None,
                "columns": [],
                "row_count": 0,
                "rows_data": [],
            }

    def _clear_preview(self):
        """Clear preview and reset UI (no singleton interaction)."""
        self._preview = {
            "filepath": None,
            "columns": [],
            "row_count": 0,
            "rows_data": [],
        }
        self._batch["excel_action"] = None
        self._batch["excel_path"] = None
        self._filepath_field.value = t("Ningun archivo cargado")
        self._row_count_text.value = ""
        self._btn_accept.disabled = True
        self._data_container.content = ft.Container(
            content=ft.Text(t("Cargue un archivo para previsualizar los datos"), size=12, color=TEXTOS_FASE_1_COLOR, italic=True),
            alignment=ft.Alignment.CENTER,
        )
        if self._btn_remove:
            self._btn_remove.visible = False
        self.page.update()

    def _reset_ui_after_clear(self):
        """Reset dialog UI after removing excel data."""
        self._clear_preview()

    def _populate_listview(self):
        p = self._preview
        if not p["filepath"]:
            return

        cols = p["columns"]
        rows_data = p["rows_data"]
        total_rows = p["row_count"]

        # ponytail: limit preview to 200 rows — no need to render 5000+ Flet widgets
        shown = rows_data[:self._MAX_PREVIEW]

        # Calcular ancho natural por columna basado en contenido real
        natural_widths: list[int] = []
        for j, col in enumerate(cols):
            max_len = len(col)
            for row in shown:
                if j < len(row):
                    max_len = max(max_len, len(row[j]))
            # ~7.5px/char + 20px padding, min 60, max 400
            natural_widths.append(min(max(int(max_len * 7.5 + 20), 60), 400))

        total_natural = 40 + sum(natural_widths)

        sep = ft.BorderSide(1, BORDE_TEXTFIELDS_COLOR)

        def _cell(text: str, j: int, pad: ft.Padding, is_header: bool, is_last: bool):
            return ft.Container(
                content=ft.Text(
                    text, size=12 if is_header else 11,
                    weight=ft.FontWeight.BOLD if is_header else ft.FontWeight.NORMAL,
                    color=TEXTOS_FASE_1_COLOR if is_header else TEXTO_COLOR_GENERICO,
                    no_wrap=True,
                ),
                padding=pad,
                border=ft.Border.only(right=sep) if not is_last else None,
                width=natural_widths[j],
            )

        # Header row
        header_row = ft.Container(
            content=ft.Row(
                spacing=0,
                controls=[
                    ft.Container(
                        content=ft.Text("#", size=12, weight=ft.FontWeight.BOLD, color=TEXTOS_FASE_1_COLOR),
                        width=40, padding=ft.Padding(4, 2, 4, 2), border=ft.Border.only(right=sep),
                    ),
                    *[_cell(col, j, ft.Padding(4, 2, 4, 2), True, j == len(cols) - 1)
                      for j, col in enumerate(cols)],
                ],
            ),
            bgcolor=FONDO_SECCIONES,
        )

        # Data rows (limited to _MAX_PREVIEW)
        row_controls = []
        for i, vals in enumerate(shown):
            real_idx = i  # 0-based index in the shown slice
            row_color = None if real_idx % 2 == 0 else ft.Colors.with_opacity(0.03, TEXTO_COLOR_GENERICO)
            row_controls.append(
                ft.Container(
                    content=ft.Row(
                        spacing=0,
                        controls=[
                            ft.Container(
                                content=ft.Text(str(real_idx + 1), size=11, color=TEXTOS_FASE_1_COLOR),
                                width=40, padding=ft.Padding(4, 1, 4, 1), border=ft.Border.only(right=sep),
                            ),
                            *[_cell(val, j, ft.Padding(4, 1, 4, 1), False, j == len(cols) - 1)
                              for j, val in enumerate(vals)],
                        ],
                    ),
                    bgcolor=row_color,
                )
            )

        all_controls = [header_row, *row_controls]

        total_w = 40 + sum(natural_widths)
        for c in all_controls:
            c.width = total_w
        scroll_container = ft.Container(
            content=ft.Row(
                scroll=ft.ScrollMode.AUTO,
                expand=True,
                controls=[ft.Column(
                    controls=all_controls,
                    scroll=ft.ScrollMode.AUTO,
                    width=total_w,
                )],
            ),
            border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
            border_radius=4,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            expand=True,
        )

        self._data_container.content = scroll_container

        # ponytail: store info for title row footer
        if hasattr(self, "_preview_info_text"):
            if total_rows > self._MAX_PREVIEW:
                self._preview_info_text.value = t("Mostrando {0} de {1} filas").format(self._MAX_PREVIEW, total_rows)
                self._preview_info_text.visible = True
            else:
                self._preview_info_text.visible = False

    # ------------------------------------------------------------------
    # Open dialog
    # ------------------------------------------------------------------

    def open(self):
        total_pages = self._get_total_pages()

        # Reset batch for fresh dialog session
        self._batch = {
            "excel_action": None,
            "excel_path": None,
        }

        # Initialize preview from singleton if already loaded
        self._snapshot_singleton_to_preview()

        info_text = ft.Text(
            t("Recuerda: configura Inicio y Fin antes para que coincida con las filas del archivo."),
            size=12, color=TEXTOS_FASE_1_COLOR, italic=True,
        )

        self._page_count_text = ft.Text(
            t("Paginas actuales: {0}").format(total_pages),
            size=12, color=TEXTO_COLOR_GENERICO,
        )

        self._btn_load = ft.Button(
            t("Cargar archivo Excel / CSV"),
            icon=ft.Icons.UPLOAD_FILE,
            on_click=self._pick_file,
            bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
            style=ft.ButtonStyle(
                color={ft.ControlState.DEFAULT: BOTONES_GENERICOS_COLOR, "hovered": BOTONES_GENERICOS_HOVER_COLOR},
                overlay_color=BOTONES_GENERICOS_OVERLAY_COLOR,
                padding=ft.Padding(12, 0, 12, 0),
                shape=ft.RoundedRectangleBorder(radius=10),
            ),
        )

        self._filepath_field = ft.Text(
            t("Ningun archivo cargado"),
            size=12, color=TEXTO_COLOR_GENERICO, italic=True,
        )

        self._row_count_text = ft.Text("", size=12, color=TEXTO_COLOR_GENERICO)

        self._preview_info_text = ft.Text(
            "", size=11, color=TEXTOS_FASE_1_COLOR, visible=False,
        )

        self._data_container = ft.Container(
            content=ft.Container(
                content=ft.Text(t("Cargue un archivo para previsualizar los datos"), size=12, color=TEXTOS_FASE_1_COLOR, italic=True),
                alignment=ft.Alignment.CENTER,
            ),
            padding=8,
            border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
            border_radius=4,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            expand=True,
        )

        self._btn_accept = ft.Button(
            t("Aceptar"), on_click=self._on_accept, width=110,
            bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
            style=ft.ButtonStyle(
                color={ft.ControlState.DEFAULT: BOTONES_GENERICOS_COLOR, "hovered": BOTONES_GENERICOS_HOVER_COLOR},
                overlay_color=BOTONES_GENERICOS_OVERLAY_COLOR,
                padding=ft.Padding(0, 0, 0, 0),
                shape=ft.RoundedRectangleBorder(radius=10),
            ),
            disabled=True,
        )

        self._btn_remove = ft.Button(
            t("Eliminar"),
            icon=ft.Icons.DELETE,
            on_click=self._on_remove_excel,
            bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
            style=ft.ButtonStyle(
                color={ft.ControlState.DEFAULT: BOTONES_GENERICOS_COLOR, "hovered": BOTONES_GENERICOS_HOVER_COLOR},
                overlay_color=BOTONES_GENERICOS_OVERLAY_COLOR,
                padding=ft.Padding(10, 0, 10, 0),
                shape=ft.RoundedRectangleBorder(radius=10),
            ),
        )
        self._btn_remove.visible = bool(self._preview["filepath"])

        if self._preview["filepath"]:
            p = self._preview
            filename = os.path.basename(p["filepath"])
            self._filepath_field.value = f"{filename} \u2705"
            total_pages = self._get_total_pages()
            rows = p["row_count"]
            if rows > total_pages:
                unused = rows - total_pages
                self._row_count_text.value = t("Filas: {0} ({1} usadas, {2} sin usar)").format(rows, total_pages, unused)
                self._row_count_text.color = TEXTOS_FASE_1_COLOR
            else:
                self._row_count_text.value = t("Filas: {0}").format(rows)
                self._row_count_text.color = TEXTO_COLOR_GENERICO
            self._populate_listview()
            self._btn_accept.disabled = False

        base_content = ft.Container(
            content=ft.Column(
                [
                    ft.Container(
                        content=ft.Column(
                            [info_text, ft.Divider(height=1, color=BORDE_TEXTFIELDS_COLOR),
                             ft.Row(controls=[self._page_count_text, ft.Container(expand=True), self._btn_load], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                             ft.Row(controls=[self._filepath_field, ft.Container(width=20), self._row_count_text, self._btn_remove], vertical_alignment=ft.CrossAxisAlignment.CENTER)],
                            spacing=8,
                        ),
                        bgcolor=FONDO_SECCIONES, border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR), border_radius=4, padding=ft.Padding.all(12),
                    ),
                    ft.Container(height=8),
                    ft.Container(
                        content=ft.Column(
                            [ft.Row(
                                [
                                    ft.Text(t("Previsualizacion de datos"), size=13, weight=ft.FontWeight.BOLD, color=TEXTOS_FASE_1_COLOR),
                                    ft.Container(expand=True),
                                    self._preview_info_text,
                                ],
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                             self._data_container],
                            spacing=6,
                        ),
                        bgcolor=FONDO_SECCIONES, border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR), border_radius=4, padding=ft.Padding.all(12), expand=True,
                    ),
                ],
                spacing=6, expand=True,
            ),
            width=1250, height=700,
        )

        self.dialog_root_stack = ft.Stack(
            controls=[base_content],
            width=1250,
            height=700,
        )

        dialog_content = self.dialog_root_stack

        def on_cancel(e):
            # Cancel: just close, singleton never touched
            self._cleanup_dialog()
            self.page.pop_dialog()

        self.dialog = ft.AlertDialog(
            modal=True,
            inset_padding=0,
            title_padding=ft.Padding(10, 20, 10, 8),
            title=ft.Container(
                content=ft.Text(t("Configurar Datos Externos"), size=18, weight=ft.FontWeight.BOLD, color=TEXTO_COLOR_GENERICO, text_align=ft.TextAlign.CENTER),
                alignment=ft.Alignment.CENTER,
            ),
            content=dialog_content,
            actions=[
                ft.Button(t("Cancelar"), on_click=on_cancel, width=110,
                    bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
                    style=ft.ButtonStyle(color={ft.ControlState.DEFAULT: BOTONES_GENERICOS_COLOR, "hovered": BOTONES_GENERICOS_HOVER_COLOR}, overlay_color=BOTONES_GENERICOS_OVERLAY_COLOR, padding=ft.Padding(0, 0, 0, 0), shape=ft.RoundedRectangleBorder(radius=10))),
                self._btn_accept,
            ],
            actions_alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            bgcolor=FONDO_BLOQUE_RESUMEN_COLOR,
            content_padding=ft.Padding(20, 10, 20, 10),
            actions_padding=ft.Padding(24, 0, 24, 15),
        )

        self.page.show_dialog(self.dialog)

    def _cleanup_dialog(self):
        """Limpia controles del diálogo y libera memoria."""
        if self._data_container:
            self._data_container.content = None
        if self.dialog:
            self.dialog.content = None
        self.page.update()
        gc.collect()

    def _on_accept(self, e):
        action = self._batch["excel_action"]
        if action == "load":
            ok, msg = self.excel_manager.load(self._batch["excel_path"])
            if not ok:
                self._show_popup(t("Error"), msg)
                return
            if self.on_excel_cleared:
                self.on_excel_cleared()
        elif action == "remove":
            self.excel_manager.clear()
            if self.on_excel_cleared:
                self.on_excel_cleared()

        columns = self._preview["columns"] if self._preview["filepath"] else []
        if self.vt_profile_manager:
            self.vt_profile_manager.set_excel_columns(columns)
        if action != "remove" and self.on_data_loaded:
            self.on_data_loaded()
        if self.on_modified:
            self.on_modified()
        self._cleanup_dialog()
        self.page.pop_dialog()
