"""
Aplicación principal de PageNumber
"""

import flet as ft
import sys
import os

# el path se ajustará antes de importar módulos PageNumber
try:
    import certifi
    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
except Exception:
    # Si certifi no está instalado, continuar sin alterar el en torno
    pass

# Silenciar prints de depuración en este módulo por defecto.
# Para activar, cambiar _PRINT_DEBUG = True durante desarrollo.
_PRINT_DEBUG = False  # ← ACTIVADO para ver todos los prints de debug
if not _PRINT_DEBUG:
    def _no_print(*args, **kwargs): 
        return None
    print = _no_print

# Añadir el directorio padre al path PRIMERO
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# internacionalización (usar el reexport de PageNumber)
from resource_path import get_resource_path
from i18n import t

# Configurar logger de errores DESPUÉS de configurar el path
try:
    from utils.error_logger import setup_error_logger, install_exception_handler
    setup_error_logger()
    install_exception_handler()
    print("[LOGGER] Logger de errores iniciado correctamente")
except Exception as e:
    # Si falla el logger, continuar sin él
    print(f"[LOGGER ERROR] No se pudo iniciar el logger: {e}")
    import traceback
    traceback.print_exc()


from color_design import (
    FONDO_APP,
    TEXTO_COLOR_GENERICO,
    tema_flet,
    definir_constantes_color,
    actualizar_colores,
)

# MainScreen import deferred until after loading preferences/language


async def main(page: ft.Page):
    """Función principal de la aplicación"""
    
    # Limpiar caché de fondos de la sesión anterior (solicitado por usuario)
    try:
        from utils.preferences import delete_background_cache, reset_last_backgrounds
        delete_background_cache()
        reset_last_backgrounds() # También resetear configuración para empezar limpio
    except Exception as e:
        print(f"[INIT] Error limpiando caché de fondos: {e}")

    # Cargar idioma guardado en preferencias (si existe) y aplicarlo antes de construir UI
    try:
        from utils.preferences import get_preference
        from i18n import set_language, get_lang
        lang_pref = get_preference('language', None)
        print(f"[LANG] Preferencia leída: {lang_pref!r}")
        if lang_pref:
            try:
                set_language(lang_pref)
                print(f"[LANG] set_language('{lang_pref}') OK → get_lang()={get_lang()!r}")
            except Exception as exc:
                print(f"[LANG] Error en set_language: {exc}")
        else:
            print(f"[LANG] No había preferencia de idioma guardada")
    except Exception as exc:
        import traceback
        print(f"[LANG] Error cargando preferencia: {exc}")
        traceback.print_exc()

    # Importar M,las traducciones
    # aplicadas se reflejen correctamente en todos los textos importados.
    try:
        from ui.main_screen import MainScreen
    except Exception:
        raise

    # Configurar página
    page.title = t("PageNumber - Sin título")
    page.padding = 0
    
    # Configurar icono de la ventana (especialmente para Windows)
    try:
        # Intentar cargar desde la nueva carpeta assets
        _icon_path = get_resource_path(os.path.join("assets", "icon.ico"))
        if not os.path.exists(_icon_path):
            # Fallback a la ubicación anterior por si acaso
            _icon_path = get_resource_path("PageNumber_icon.ico")
            
        if os.path.exists(_icon_path):
            page.window.icon = _icon_path
            print(f"[INIT] Icono configurado desde: {_icon_path}")
    except Exception as e:
        print(f"[INIT] Error configurando icono: {e}")
    
    # Aplicar tema
    actualizar_colores()
    page.theme_mode = tema_flet
    page.theme, page.dark_theme = definir_constantes_color()
    page.bgcolor = FONDO_APP
    print(f"[DBG] theme_mode={page.theme_mode} bgcolor={page.bgcolor}")
    print(f"[DBG] theme.co_scheme.T={page.theme.color_scheme.tertiary if page.theme else None}")
    print(f"[DBG] theme.co_scheme.OS={page.theme.color_scheme.on_surface if page.theme else None}")
    print(f"[DBG] theme.co_scheme.S={page.theme.color_scheme.surface if page.theme else None}")
    
    # Configurar tamaño de ventana (compatible con TalNumStack)
    page.window.width = 1470
    page.window.height = 860
    page.window.min_width = 1470
    page.window.min_height = 860
    page.run_task(page.window.center)  # Centrar ventana (async en Flet 1.0)

    # Mostrar vista de carga antes de inicializar fuentes (bloquea interacción)
    loading_view = ft.Container(
        content=ft.Column(
            [
                ft.ProgressRing(width=80, height=80, stroke_width=6),
                ft.Text(t("Cargando tipos de letra..."), color=TEXTO_COLOR_GENERICO, size=20),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=24,
        ),
        alignment=ft.Alignment.CENTER,
        expand=True,
        bgcolor=FONDO_APP,
    )
    page.add(loading_view)
    page.update()

    # Ceder el event loop para que el cliente renderice la vista de carga
    # (main() es async en Flet 1.0: sin await, el spinner nunca se pinta)
    import asyncio
    await asyncio.sleep(0.1)

    # Crear pantalla principal (bloquea mientras escanea fuentes)
    main_screen = MainScreen(page)

    # Registrar en `page.fonts` los TTF extraídos presentes en la caché
    try:
        from utils import font_cache
        from pathlib import Path

        base = font_cache.get_config_dir()
        cache = font_cache.load_cache(base) or {}
        em = cache.get('extracted_map', {}) or {}
        if page.fonts is None:
            page.fonts = {}
        fonts_map = page.fonts

        for key, entry in em.items():
            try:
                orig = entry.get('original_path') or ''
                idx = key.split('|', 1)[1] if '|' in key else '0'
                safe = Path(orig).stem.replace(' ', '') or f"font{idx}"
                alias = f"{safe}__{idx}"
                extracted = entry.get('extracted_path')
                if extracted and alias not in fonts_map:
                    try:
                        fonts_map[alias] = extracted
                    except Exception:
                        pass
            except Exception:
                continue
    except Exception:
        pass
    
    # Registrar fuentes OCR para EAN-13
    try:
        from utils.preferences import get_config_dir as _get_config_dir
        import shutil
        
        ean13_dir = _get_config_dir() / "ean13_fonts"
        ean13_dir.mkdir(parents=True, exist_ok=True)
        if page.fonts is None:
            page.fonts = {}
        for label, fname in [
            ("OCR-A", "OCRA.ttf"),
            ("OCR-B", "OCRB.ttf"),
            ("OCR-B F", "OCRBF.ttf"),
            ("OCR-B L", "OCRBL.ttf"),
        ]:
            try:
                _src = get_resource_path(f"ocr-0.3.1/{fname}")
                _dst = ean13_dir / fname
                if not _dst.exists() and os.path.exists(_src):
                    shutil.copy2(_src, _dst)
                if _dst.exists() and label not in page.fonts:
                    page.fonts[label] = str(_dst)
            except Exception:
                continue
    except Exception:
        pass
    
    # Registrar callback de resize (Flet 1.0: page.on_resize con PageResizeEvent)
    page.on_resize = main_screen.on_page_resize
    
    # Quitar vista de carga y agregar UI real
    page.controls.clear()
    page.add(main_screen.build())
    
    # Actualizar texto de tamaño de página después de añadir a la página
    main_screen._update_page_size_text()

    page.update()


def _heal_flet_client_cache() -> bool:
    """Garantiza que el cliente cacheado se llama PageNumber (nunca Flet).

    flet_desktop.ensure_client_cached solo comprueba que exista la CARPETA
    (~/.flet/client/flet-desktop-*) y la devuelve tal cual. Si esa carpeta la
    pobló una sesión dev (cliente vanilla "Flet.app" bajado de GitHub), la
    .app empaquetada la reutiliza y NUNCA extrae el tar branded
    (PageNumber.app, com.japr.pagenumber) que lleva dentro → el Dock enseña
    "Flet". Aquí se valida por NOMBRE del bundle (sin hash, el hash del tar
    cambia con cada rebuild) y se repara:
      - empaquetada: se borra la caché contaminada → se re-extrae del tar
        embebido (flet pack ya lo deja branded y firmado).
      - dev: no hay tar branded → se renombra el bundle, se parchea el plist
        y se re-firma ad-hoc (mismo gesto de flet pack al ensamblar).
    Devuelve True SOLO si en este arranque hubo que instalar/extraer/renombrar
    el cliente (y por tanto hay que aplicar el icono); False si el cliente ya
    existía y era correcto → _brand_and_set_client_icon no tocará nada.
    """
    try:
        import builtins
        import shutil
        import subprocess
        import plistlib
        import time

        from flet_desktop import ensure_client_cached, find_macos_app_bundle

        cache_dir = ensure_client_cached()
        bundle = find_macos_app_bundle(cache_dir)
        instalado = False

        if bundle is None:
            builtins.print(f"[FLET] Caché hueca sin cliente, regenerando: {cache_dir}")
            shutil.rmtree(cache_dir, ignore_errors=True)
            cache_dir = ensure_client_cached()
            bundle = find_macos_app_bundle(cache_dir)
            instalado = True

        if bundle is not None and bundle.name != "PageNumber.app":
            if getattr(sys, "frozen", False):
                builtins.print(
                    f"[FLET] Cliente {bundle.name} no es de la app, re-extrayendo del tar: {cache_dir}"
                )
                shutil.rmtree(cache_dir, ignore_errors=True)
                cache_dir = ensure_client_cached()
                bundle = find_macos_app_bundle(cache_dir)
                instalado = True
            elif bundle is not None:
                renombrado = bundle.parent / "PageNumber.app"
                bundle.rename(renombrado)
                bundle = renombrado
                plist_path = bundle / "Contents" / "Info.plist"
                with open(plist_path, "rb") as f:
                    pl = plistlib.load(f)
                pl["CFBundleName"] = "PageNumber"
                pl["CFBundleDisplayName"] = "PageNumber"
                pl["CFBundleIdentifier"] = "com.japr.pagenumber"
                with open(plist_path, "wb") as f:
                    plistlib.dump(pl, f)
                subprocess.run(
                    ["codesign", "--force", "--deep", "-s", "-", str(bundle)],
                    check=False,
                )
                builtins.print(f"[FLET] Cliente renombrado a {bundle.name} (dev)")
                instalado = True

        # Correcto pero acabado de extraer/descargar en ESTE arranque
        # (primera vez en ~/.flet vacío): cuenta como instalado → icono.
        if not instalado and bundle is not None:
            try:
                if time.time() - bundle.stat().st_birthtime < 120:
                    instalado = True
            except OSError:
                pass
        return instalado
    except Exception as e:
        import builtins

        builtins.print(f"[FLET] Aviso saneando caché del cliente: {e}")
        return False


def _brand_and_set_client_icon(instalado: bool = False) -> None:
    """Aplica el icono de PageNumber al cliente Flet instalado (solo darwin).

    No vale parchear un .icns suelto (falló en el pasado: el icono de la app
    Flutter vive en Assets.car): se usa NSWorkspace.setIcon, el mismo gesto
    que "Get Info > arrastrar icono", la única vía que macOS acepta. Solo
    toca el bundle si _heal_flet_client_cache devolvió instalado=True (este
    arranque instaló/extrajo/renombró el cliente); si el cliente ya existía
    y era correcto NO se hace nada (ni icono, ni marcador, ni print). El
    marcador `.icon-applied` (fijo y legible, sin hash) evita repetirlo
    dentro de la misma instalación. La carpeta del cliente lleva la versión
    de Flet en el nombre → al subir la versión se instala de cero y el icono
    se re-aplica. Nunca revienta la app si algo falla.
    """
    try:
        import builtins
        import shutil
        import time

        from flet_desktop import ensure_client_cached, find_macos_app_bundle

        cache_dir = ensure_client_cached()
        bundle = find_macos_app_bundle(cache_dir)

        if bundle is None:
            builtins.print("[FLET] cliente sin bundle, icono no aplicado")
        elif not instalado:
            pass  # cliente correcto y ya existente → no se toca nada
        else:
            try:
                from AppKit import NSImage, NSWorkspace
            except Exception as e:
                builtins.print(f"[FLET] sin AppKit ({e}), icono no aplicado")
            else:
                icns = get_resource_path("PageNumber_icon.icns")
                # Marcador de nombre FIJO (legible): solo se escribe si en este
                # arranque se instaló el cliente y aún no se le puso el icono.
                # Si algún día cambia el icono real, borrar .icon-applied y se
                # re-aplicará una vez.
                marca = cache_dir / ".icon-applied"
                for old in cache_dir.glob(".icon-*"):
                    if old.name != marca.name:
                        old.unlink()
                if not marca.exists():
                    img = NSImage.alloc().initWithContentsOfFile_(icns)
                    if img is not None:
                        NSWorkspace.sharedWorkspace().setIcon_forFile_options_(
                            img, str(bundle), 0
                        )
                        marca.touch()
                        builtins.print(f"[FLET] icono PageNumber aplicado: {bundle}")

        root = cache_dir.parent
        keep = cache_dir.name
        for entry in root.glob("flet-desktop-full-*_pagenumber"):
            if entry.name == keep or not entry.is_dir():
                continue
            lu = entry / ".last-used"
            try:
                age = time.time() - lu.stat().st_mtime if lu.exists() else None
            except OSError:
                age = None
            # no borrar si otra instancia la usó hoy
            if age is None or age > 86400:
                shutil.rmtree(entry, ignore_errors=True)
                builtins.print(f"[FLET] caché cliente vieja borrada: {entry.name}")
    except Exception as e:
        import builtins

        builtins.print(f"[FLET] Aviso branding del cliente: {e}")


if __name__ == "__main__":
    # Obligatorio: ProcessPoolExecutor (subset de lotes) en la .app
    # empaquetada — sin esto el hijo de multiprocessing relanza la GUI.
    import multiprocessing

    multiprocessing.freeze_support()
    if sys.platform == "darwin":
        _brand_and_set_client_icon(_heal_flet_client_cache())
    try:
        ft.run(main)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[FT_APP_ERROR] {e}")