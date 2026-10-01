"""
guia_html_viewer.py
===================
Diálogo reutilizable de guías en HTML. Muestra la guía correspondiente en el
idioma activo de la app:
- Windows: Edge en modo app (sin WebView embebido).
- macOS: navegador del sistema (el WebView embebido quedaba detrás del
  AlertDialog al abrirse desde los diálogos de ajustes).

Uso:
    from ui.guia_html_viewer import abrir_guia, abrir_guia_barcode
    abrir_guia(page, "elementos/numeros")          # guia por ruta relativa
    abrir_guia_barcode(page, "ean13")              # guia por simbolo

El HTML es autocontenido (no necesita servidor HTTP).
"""

import glob
import os
import platform
import shutil
import sys
from pathlib import Path

import flet as ft


# Mapeo simbolo -> nombre de guia (carpeta codigos_de_barras)
SYMBOLOGY_GUIDE = {
    "qr": "qr",
    "pdf417": "pdf417",
    "datamatrix": "datamatrix",
    "datamatrix_gs1": "datamatrix",
    "datamatrix_dl": "datamatrix",
    "code128": "code128",
    "code39": "code39",
    "ean5": "ean",
    "ean8": "ean",
    "ean13": "ean",
    "upca": "upc",
    "upce": "upc",
    "isbn13": "isbn13",
    "itf14": "itf14",
}


def _get_guias_dir() -> str:
    """Directorio raíz de guías HTML (dev: PageNumber/guias_html; build: _MEIPASS/guias_html)."""
    try:
        base = sys._MEIPASS  # type: ignore[attr-defined]
    except AttributeError:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # PageNumber/
    return os.path.join(base, "guias_html")


def _get_guide_html(lang: str, guia_key: str) -> str:
    """Ruta al HTML de la guía dada, con fallback a español."""
    d = _get_guias_dir()
    lang_norm = str(lang or "es").strip().lower().replace("_", "-")
    lang_base = lang_norm.split("-")[0]

    guia_key = guia_key.strip("/").replace("\\", "/")
    for _lang_try in (lang_norm, lang_base):
        candidate = os.path.join(d, _lang_try, *guia_key.split("/")) + ".html"
        if os.path.isfile(candidate):
            return candidate

    # Fallback: es
    fallback_es = os.path.join(d, "es", *guia_key.split("/")) + ".html"
    if os.path.isfile(fallback_es):
        return fallback_es
    return ""


def abrir_guia_barcode(page: ft.Page, symbology: str):
    """Abre la guía del código de barras seleccionado (por id de simbología)."""
    guide = SYMBOLOGY_GUIDE.get(str(symbology or "").lower())
    if not guide:
        return
    abrir_guia(page, f"codigos_de_barras/{guide}")


def abrir_guia(page: ft.Page, guia_key: str):
    """Abre la guía indicada (ruta relativa tipo carpeta, ej: 'elementos/numeros')."""
    from i18n import get_lang, t

    _lang = get_lang() or "es"
    guide_html = _get_guide_html(_lang, guia_key)

    if not os.path.isfile(guide_html):
        dlg_error = ft.AlertDialog(
            title=ft.Text(t("Manual no disponible")),
            content=ft.Text(
                t("No se encontró el archivo de la guía:\n{0}").format(guide_html)
            ),
            actions=[
                ft.TextButton(t("Cerrar"), on_click=lambda e: page.pop_dialog())
            ],
        )
        page.show_dialog(dlg_error)
        return

    # Copiar con nombre único por mtime para evitar la caché de WKWebView/Edge.
    import shutil as _shutil_gu

    from utils.preferences import get_config_dir

    _mtime = int(os.path.getmtime(guide_html))
    _cache_dir = os.path.join(str(get_config_dir()), "guias_html")
    os.makedirs(_cache_dir, exist_ok=True)
    _slug = guia_key.replace("/", "_")
    _cached = os.path.join(_cache_dir, f"{_slug}_{_lang}_{_mtime}.html")
    if not os.path.isfile(_cached):
        for _old in glob.glob(os.path.join(_cache_dir, f"{_slug}_{_lang}_*.html")):
            try:
                os.remove(_old)
            except Exception:
                pass
        _shutil_gu.copy2(guide_html, _cached)
    url = Path(_cached).as_uri()

    # Windows: ft.WebView no está disponible -> Edge en modo app (con scroll nativo)
    if platform.system() == "Windows":
        import subprocess
        import webbrowser

        _edge_candidates = [
            os.path.expandvars(
                r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
            ),
            os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        ]
        _edge_exe = next((p for p in _edge_candidates if os.path.isfile(p)), None)
        if _edge_exe:
            subprocess.Popen(
                [_edge_exe, f"--app={url}", "--new-window", "--window-size=1100,800"]
            )
        else:
            webbrowser.open(url)
        return

    # macOS (y resto): navegador del sistema. El WebView embebido en overlay
    # quedaba DETRÁS del AlertDialog (capa de diálogos > overlay) al abrirse
    # desde los 3 diálogos de ajustes.
    import webbrowser

    webbrowser.open(url)
