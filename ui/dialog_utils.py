"""Utilidades compartidas para diálogos de PageNumber."""

import flet as ft


def reopen_dialog(page, dialog) -> None:
    """Sincroniza `dialog` en la pila de Flet 1.0.

    - Si ya está open en la pila → solo `_dialogs.update()` (fuerza redibujo;
      Flutter no redibuja el padre solo al cerrar el picker de encima).
    - Si quedó basura (en la pila con open=False) → la retira antes de show_dialog.
    - RuntimeErrors se tragan (show_dialog lanza "Dialog is already opened").
    """
    if dialog is None or page is None:
        return
    try:
        stack = page._dialogs.controls
    except Exception:
        stack = None
    if stack is not None and dialog in stack:
        if dialog.open:
            # Ya en pila y open: Flet no re-renderiza solo — forzar sync
            # (bajo el picker Flutter lo puede tener oculto hasta un update).
            try:
                page._dialogs.update()
            except Exception:
                try:
                    page.update()
                except Exception:
                    pass
            return
        try:
            stack.remove(dialog)
        except Exception:
            pass
    try:
        page.show_dialog(dialog)
    except RuntimeError:
        pass


def purge_stale_dialog(page, dialog) -> None:
    """Retira de la pila una instancia vieja con open=False (pendiente de dismiss)."""
    if dialog is None or page is None:
        return
    try:
        stack = page._dialogs.controls
        if dialog in stack and not dialog.open:
            stack.remove(dialog)
    except Exception:
        pass
from color_design import (
    TEXTO_COLOR_GENERICO,
    FONDO_ALERT_DIALOG,
    BORDE_TEXTFIELDS_COLOR,
    BOTONES_GENERICOS_COLOR,
    BOTONES_GENERICOS_HOVER_COLOR,
    BOTONES_GENERICOS_OVERLAY_COLOR,
    BOTONES_GENERICOS_FONDO_COLOR,
)
from i18n import t


def show_rename_profile_dialog(
    root_stack: ft.Stack,
    current_name: str,
    existing_names: list,
    on_rename_success: callable,
    title: str = None,
):
    """Muestra un popup para renombrar un perfil.

    Args:
        root_stack: ft.Stack donde se añade el popup overlay.
        current_name: Nombre actual del perfil.
        existing_names: Lista de todos los nombres de perfil existentes.
        on_rename_success: Callback con la firma on_rename_success(new_name).
        title: Título del popup (opcional, default "Renombrar Perfil").
    """
    _title = title or t("Renombrar Perfil")

    name_field = ft.TextField(
        value=current_name,
        label=t("Nombre del perfil"),
        width=300,
        autofocus=True,
    )

    error_text = ft.Text(
        value="",
        size=12,
        color=TEXTO_COLOR_GENERICO,
        height=20,
        text_align=ft.TextAlign.CENTER,
    )

    def on_save(e):
        new_name = name_field.value.strip()
        if not new_name:
            error_text.value = t("El nombre no puede estar vacío")
            error_text.update()
            return
        if new_name in existing_names and new_name != current_name:
            error_text.value = t("Ya existe un perfil con ese nombre")
            error_text.update()
            return
        on_rename_success(new_name)
        if popup_container in root_stack.controls:
            root_stack.controls.remove(popup_container)
        root_stack.update()

    def on_cancel(e):
        if popup_container in root_stack.controls:
            root_stack.controls.remove(popup_container)
        root_stack.update()

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
                        _title,
                        weight=ft.FontWeight.BOLD,
                        size=18,
                        color=TEXTO_COLOR_GENERICO,
                    ),
                    alignment=ft.Alignment.CENTER,
                ),
                ft.Container(height=10),
                name_field,
                error_text,
                ft.Container(height=15),
                ft.Row(
                    [
                        ft.Button(
                            t("Cancelar"),
                            on_click=on_cancel,
                            width=110,
                            bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
                            style=_btn_style,
                        ),
                        ft.Button(
                            t("Guardar"),
                            on_click=on_save,
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

    root_stack.controls.append(popup_container)
    root_stack.update()
    name_field.focus()
