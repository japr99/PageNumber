"""Diálogo compartido para informar el cierre y la limpieza temporal."""

import flet as ft

from color_design import FONDO_ALERT_DIALOG, TEXTO_COLOR_GENERICO


def cerrar_dialogos_abiertos(page):
    """Cierra los diálogos abiertos antes de mostrar el aviso final."""
    try:
        for control in reversed(list(getattr(page, "overlay", []) or [])):
            if hasattr(control, "open"):
                try:
                    control.open = False
                except Exception:
                    pass
        page.update()
    except Exception:
        pass


def crear_dialogo_cierre(page, t):
    """Construye el diálogo final de cierre con el estilo común de la app."""
    return ft.AlertDialog(
        modal=True,
        title=ft.Container(
            content=ft.Text(
                t("Limpiando temporales y cerrando la app"),
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
                        t("Se están limpiando los archivos temporales."),
                        size=14,
                        weight=ft.FontWeight.BOLD,
                        color=TEXTO_COLOR_GENERICO,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    ft.Container(height=10),
                    ft.Text(
                        t("La aplicación se cerrará en unos segundos."),
                        size=13,
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
        actions=[],
        actions_alignment=ft.MainAxisAlignment.CENTER,
        bgcolor=FONDO_ALERT_DIALOG,
    )


def mostrar_dialogo_cierre(page, t):
    """Oculta modales previos y muestra el aviso final de cierre."""
    cerrar_dialogos_abiertos(page)
    dialogo = crear_dialogo_cierre(page, t)
    try:
        page.overlay.append(dialogo)
    except Exception:
        pass
    dialogo.open = True
    try:
        page.update()
    except Exception:
        pass
    return dialogo
