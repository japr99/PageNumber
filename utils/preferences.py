"""
Sistema de preferencias para PageNumber
Guarda configuración del usuario de forma persistente

Formato y comportamiento (IMPORTANTE):
- Versión de formato: 1  -> variable `CURRENT_PREFERENCES_VERSION`.
- Archivo: `preferences.json` en el directorio devuelto por `get_config_dir()`.
- Migración: si al cargar las preferencias la versión del archivo difiere de
  `CURRENT_PREFERENCES_VERSION`, se aplica `_migrate_preferences()` para:
    * conservar claves compatibles (con verificación básica de tipo),
    * rellenar con valores por defecto las claves nuevas,
    * eliminar claves incompatibles o desconocidas.
- Borrado: usar `delete_preferences()` para eliminar el archivo de preferencias
  (herramienta de depuración; la app puede cerrarse tras borrar).
- NOTA: cuando se incremente `CURRENT_PREFERENCES_VERSION`, actualizar
  `_migrate_preferences()` para definir la lógica de actualización necesaria.
"""

import os
import json
from pathlib import Path
import uuid
from .font_manager import get_default_font_family

# Verbose print helper: intentar reutilizar el definido en el wrapper de fuentes,
# si no está disponible, definir un no-op para evitar NameError al arrancar.

_PRINT_DEBUG = False  # ← ACTIVADO para ver todos los prints de debug
if not _PRINT_DEBUG:

    def _no_print(*args, **kwargs):
        return None

    print = _no_print


try:
    from .font_index_wrapper import _vprint  # type: ignore
except Exception:

    def _vprint(*args, **kwargs):
        return None


# Directorio de configuración del usuario
def get_config_dir():
    """Obtiene el directorio de configuración según el sistema operativo"""
    home = Path.home()

    if os.name == "nt":  # Windows
        config_dir = home / "AppData" / "Local" / "PageNumber"
    elif os.name == "posix":
        if "darwin" in os.sys.platform:  # macOS
            config_dir = home / "Library" / "Application Support" / "PageNumber"
        else:  # Linux
            config_dir = home / ".config" / "PageNumber"
    else:
        config_dir = home / ".pagenumber"

    # Crear directorio si no existe
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def get_background_cache_dir():
    """Obtiene el directorio donde se guardarán los archivos temporales de fondo"""
    cache_dir = get_config_dir() / "background_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


# Archivo de preferencias
PREFERENCES_FILE = get_config_dir() / "preferences.json"

# Archivo de caché de fuentes (legacy). Por decisión del equipo eliminamos
# esta caché persistente y la removemos al arrancar para evitar residuos
# y comportamientos inconsistentes entre plataformas.
FONT_CACHE_FILE = get_config_dir() / "font_cache.json"
try:
    if FONT_CACHE_FILE.exists():
        try:
            FONT_CACHE_FILE.unlink()
            _vprint(f"[PREFERENCES] Removed legacy font cache: {FONT_CACHE_FILE}")
        except Exception as e:
            _vprint(
                f"[PREFERENCES] Failed to remove legacy font cache {FONT_CACHE_FILE}: {e}"
            )
except Exception:
    # Silencioso en entornos donde el FS esté restringido
    pass

# Versión de formato de preferencias (incrementar cuando cambie la estructura)
CURRENT_PREFERENCES_VERSION = 2

# Generador de perfil de texto por defecto (serializable a JSON)
import uuid


def _default_text_profile_dict():
    """Devuelve un dict serializable que representa el perfil <Default>.
    Evitamos importar TextStyle para no crear dependencias circulares.
    """
    return {
        "id": str(uuid.uuid4()),
        "name": "<Default>",
        "font_family": get_default_font_family(),
        "font_style": "Regular",
        "font_size": 12.0,
        "color_space": "RGB",
        "number_color_space": "RGB",
        "prefix_color_space": "RGB",
        "suffix_color_space": "RGB",
        "number_color": "#000000",
        "prefix_color": "#000000",
        "suffix_color": "#000000",
        "number_color_cmyk": [0.0, 0.0, 0.0, 100.0],
        "prefix_color_cmyk": [0.0, 0.0, 0.0, 100.0],
        "suffix_color_cmyk": [0.0, 0.0, 0.0, 100.0],
        "letter_spacing": 0.0,
        "prefix_suffix_spacing": 0.0,
        "prefix": "",
        "suffix": "",
        "mask": "0000",
        "mask_placeholder": "0",
        "digit_placeholder": 0,
        "thousands_separator": "normal",
        "color": "#000000",
    }


def _default_barcode_profile_dict():
    """Devuelve un dict serializable para el perfil de barcode por defecto."""
    return {
        "id": str(uuid.uuid4()),
        "name": "<Default>",
        "symbology": "code128",
        "value_source": "fixed",
        "sample_value": "123ABC",
        "excel_column": "",
        "bar_width": 80.0,
        "bar_height": 30.0,
        "mask": "",
        "color": "#000000",
        "color_cmyk": [0.0, 0.0, 0.0, 100.0],
        "color_space": "RGB",
        "color_name": "",
        "color_tint": 100.0,
        "error_correction": "M",
        "barcode_font_family": "OCR-B",
        "barcode_font_size": 13.0,
        "isbn13_show_title": "Sí",
    }


def _default_variable_text_profile_dict():
    """Devuelve un dict serializable para el perfil de texto variable por defecto."""
    return {
        "id": str(uuid.uuid4()),
        "name": "<Default>",
        "font_family": get_default_font_family(),
        "font_style": "Regular",
        "font_size": 12.0,
        "text_color": "#000000",
        "text_color_cmyk": [0.0, 0.0, 0.0, 100.0],
        "text_color_space": "RGB",
        "text_color_name": "",
        "text_color_tint": 100.0,
        "prefix": "",
        "suffix": "",
        "value_source": "sample",
        "sample_text": "Texto de muestra",
        "excel_column": "",
        "anchor": "superior_izquierda",
        "letter_spacing": 0.0,
    }


# Preferencias por defecto
DEFAULT_PREFERENCES = {
    "preferences_version": CURRENT_PREFERENCES_VERSION,
    "custom_page_sizes": {},  # {name: (width_mm, height_mm)}
    "last_page_size": "A4",
    "last_unit": "mm",
    "default_position_offset_x": 20.0,  # Offset X inicial para nuevas numeradoras (mm)
    "default_position_offset_y": 20.0,  # Offset Y inicial para nuevas numeradoras (mm)
    "default_alignment": "izquierda",  # Alineación inicial de nuevas numeradoras
    "default_rotation": "0°",  # Rotación inicial de nuevas numeradoras
    # Ajustes de calibración del visor (persistentes por máquina)
    "fine_adjust_step_mm": 0.1,
    "windows_text_width_padding_ratio": 0.20,
    "windows_text_width_padding_min_px": 2.0,
    # Inicializar con un perfil <Default> listo para usar al abrir la app
    "text_style_profiles": [
        _default_text_profile_dict()
    ],  # Perfiles de texto globales (se usa para nuevos proyectos)
    "barcode_profiles": [
        _default_barcode_profile_dict()
    ],  # Perfiles de barcode globales (se usa para nuevos proyectos)
    "variable_text_profiles": [
        _default_variable_text_profile_dict()
    ],  # Perfiles de texto variable globales (se usa para nuevos proyectos)
    "last_background_cara": {},  # Último fondo usado en CARA (incluye base64)
    "last_background_dorso": {},  # Último fondo usado en DORSO (incluye base64)
    "magnetic_snap_threshold": 5.0,  # Distancia en píxeles para snap magnético a guías
    "guide_color": "#757575",  # Color normal de las guías de posición (mm sobre página)
    "guide_color_selected": "#E91E63",  # Color de guía seleccionada/arrastrada
}


def _migrate_preferences(old_prefs: dict, old_version: int, new_version: int) -> dict:
    """Migración simple de preferencias:
    - Conserva las keys que existen en DEFAULT_PREFERENCES si son del tipo esperado
    - Rellena con defaults las keys nuevas
    - Elimina keys desconocidas para evitar incompatibilidades
    """
    new_prefs = {}
    for key, default_value in DEFAULT_PREFERENCES.items():
        if key == "preferences_version":
            continue
        if key in old_prefs:
            val = old_prefs[key]
            # comprobación de tipo básica
            try:
                if isinstance(default_value, dict):
                    ok = isinstance(val, dict)
                elif isinstance(default_value, list):
                    ok = isinstance(val, list)
                elif isinstance(default_value, float):
                    ok = isinstance(val, (int, float))
                else:
                    ok = isinstance(val, type(default_value))
            except Exception:
                ok = False

            if ok:
                # normalizar floats
                if isinstance(default_value, float) and isinstance(val, (int, float)):
                    new_prefs[key] = float(val)
                else:
                    new_prefs[key] = val
            else:
                new_prefs[key] = default_value
        else:
            new_prefs[key] = default_value

    # Si la migración deja la lista de perfiles vacía, asegurar que haya un perfil <Default>
    try:
        if not new_prefs.get("text_style_profiles"):
            new_prefs["text_style_profiles"] = [_default_text_profile_dict()]
            print(
                "[PREFERENCES] No había perfiles de texto tras migración: añadido perfil <Default>"
            )
    except Exception:
        pass

    try:
        if not new_prefs.get("barcode_profiles"):
            new_prefs["barcode_profiles"] = [_default_barcode_profile_dict()]
            print(
                "[PREFERENCES] No había perfiles de barcode tras migración: añadido perfil <Default>"
            )
    except Exception:
        pass

    new_prefs["preferences_version"] = new_version
    return new_prefs


def load_preferences():
    """Carga las preferencias desde el archivo JSON con soporte de migración"""
    try:
        if PREFERENCES_FILE.exists():
            with open(PREFERENCES_FILE, "r", encoding="utf-8") as f:
                prefs = json.load(f)

            file_version = prefs.get("preferences_version", 0)
            if file_version != CURRENT_PREFERENCES_VERSION:
                _vprint(
                    f"[PREFERENCES] Versión detectada {file_version} -> migrando a {CURRENT_PREFERENCES_VERSION}"
                )
                prefs = _migrate_preferences(
                    prefs, file_version, CURRENT_PREFERENCES_VERSION
                )
                # Guardar el resultado de la migración
                save_preferences(prefs)
                return prefs

            # Versión correcta: fusionar (los valores en el archivo prevalecen)
            merged = {**DEFAULT_PREFERENCES, **prefs}
            should_persist_merged = False

            # Si faltan claves esperadas en el archivo, persistir merged para
            # dejar el JSON completo desde el primer arranque.
            for key in DEFAULT_PREFERENCES.keys():
                if key not in prefs:
                    should_persist_merged = True
                    break

            # Migración 'Helvetica' -> 'Arial' en Windows para compatibilidad interactiva
            if os.name == "nt":
                profiles = merged.get("text_style_profiles", [])
                changed = False
                for p in profiles:
                    if p.get("font_family") == "Helvetica":
                        p["font_family"] = "Arial"
                        changed = True
                if changed:
                    _vprint(
                        "[PREFERENCES] Migradas fuentes Helvetica -> Arial en Windows"
                    )
                    should_persist_merged = True
                    try:
                        save_preferences(merged)
                    except Exception:
                        pass

            # Si la lista de perfiles está vacía o no existe, añadir perfil <Default> y persistir
            if not merged.get("text_style_profiles"):
                merged["text_style_profiles"] = [_default_text_profile_dict()]
                should_persist_merged = True
                try:
                    save_preferences(merged)
                    print(
                        "[PREFERENCES] Añadido perfil <Default> a preferences existentes (lista vacía)."
                    )
                except Exception as e:
                    print(
                        f"[PREFERENCES] Error guardando preferencias tras añadir <Default>: {e}"
                    )

            if should_persist_merged:
                try:
                    save_preferences(merged)
                except Exception:
                    pass
            return merged
        else:
            # No existe: crear archivo de preferencias con los defaults y devolverlos.
            from copy import deepcopy

            prefs = deepcopy(DEFAULT_PREFERENCES)
            try:
                # Guardar en disco para que futuras ejecuciones vean el archivo
                save_preferences(prefs)
                print(
                    f"[PREFERENCES] Archivo de preferencias no encontrado. Se han creado los defaults en: {PREFERENCES_FILE}"
                )
            except Exception as ex:
                print(
                    f"[PREFERENCES] Error al crear archivo de preferencias por defecto: {ex}"
                )
            return prefs
    except Exception as ex:
        print(f"[PREFERENCES] Error al cargar preferencias: {ex}")
        return DEFAULT_PREFERENCES.copy()


def save_preferences(preferences):
    """Guarda las preferencias en el archivo JSON"""
    try:
        with open(PREFERENCES_FILE, "w", encoding="utf-8") as f:
            json.dump(preferences, f, indent=2, ensure_ascii=False)
        _vprint(f"[PREFERENCES] Guardadas en: {PREFERENCES_FILE}")
        return True
    except Exception as ex:
        print(f"[PREFERENCES] Error al guardar preferencias: {ex}")
        return False


def get_custom_page_sizes():
    """Obtiene los tamaños de página personalizados"""
    prefs = load_preferences()
    # Convertir de dict con listas a dict con tuplas
    custom_sizes = {}
    for name, size in prefs.get("custom_page_sizes", {}).items():
        if isinstance(size, list) and len(size) == 2:
            custom_sizes[name] = (float(size[0]), float(size[1]))
        elif isinstance(size, tuple) and len(size) == 2:
            custom_sizes[name] = (float(size[0]), float(size[1]))
    return custom_sizes


def save_custom_page_sizes(custom_sizes):
    """Guarda los tamaños de página personalizados"""
    prefs = load_preferences()
    # Convertir tuplas a listas para JSON
    prefs["custom_page_sizes"] = {
        name: [width, height] for name, (width, height) in custom_sizes.items()
    }
    return save_preferences(prefs)


def get_last_settings():
    """Obtiene los últimos ajustes usados"""
    prefs = load_preferences()
    unit = prefs.get("last_unit", "mm")
    if unit == "px":
        unit = "mm"
    return {
        "page_size": prefs.get("last_page_size", "A4"),
        "bleed_mm": prefs.get("last_bleed_mm", 0.0),
        "unit": unit,
    }


def save_last_settings(page_size, bleed_mm, unit):
    """Guarda los últimos ajustes usados"""
    prefs = load_preferences()
    prefs["last_page_size"] = page_size
    prefs["last_bleed_mm"] = bleed_mm
    prefs["last_unit"] = unit
    return save_preferences(prefs)


def get_default_position_settings():
    """Obtiene la configuración por defecto para nuevas numeradoras"""
    prefs = load_preferences()
    return {
        "offset_x": prefs.get("default_position_offset_x", 20.0),
        "offset_y": prefs.get("default_position_offset_y", 20.0),
        "alignment": prefs.get("default_alignment", "izquierda"),
        "rotation": prefs.get("default_rotation", "0°"),
    }


def save_default_position_settings(offset_x, offset_y, alignment, rotation):
    """Guarda la configuración por defecto para nuevas numeradoras"""
    prefs = load_preferences()
    prefs["default_position_offset_x"] = offset_x
    prefs["default_position_offset_y"] = offset_y
    prefs["default_alignment"] = alignment
    prefs["default_rotation"] = rotation
    return save_preferences(prefs)


def get_rendering_tuning_settings():
    """Obtiene la calibración de renderizado del visor."""
    prefs = load_preferences()

    def _to_float(value, default_value):
        try:
            if isinstance(value, str):
                value = value.strip().replace(",", ".")
            return float(value)
        except (TypeError, ValueError):
            return float(default_value)

    fine_adjust_step_mm = _to_float(prefs.get("fine_adjust_step_mm", 0.1), 0.1)
    windows_text_width_padding_ratio = _to_float(
        prefs.get("windows_text_width_padding_ratio", 0.20), 0.20
    )
    windows_text_width_padding_min_px = _to_float(
        prefs.get("windows_text_width_padding_min_px", 2.0), 2.0
    )

    # Autorreparar valores corruptos/no numéricos y persistirlos para
    # que siguientes arranques lean valores válidos desde disco.
    repaired = (
        prefs.get("fine_adjust_step_mm") != fine_adjust_step_mm
        or prefs.get("windows_text_width_padding_ratio")
        != windows_text_width_padding_ratio
        or prefs.get("windows_text_width_padding_min_px")
        != windows_text_width_padding_min_px
    )
    if repaired:
        prefs["fine_adjust_step_mm"] = fine_adjust_step_mm
        prefs["windows_text_width_padding_ratio"] = windows_text_width_padding_ratio
        prefs["windows_text_width_padding_min_px"] = windows_text_width_padding_min_px
        try:
            save_preferences(prefs)
        except Exception:
            pass

    return {
        "fine_adjust_step_mm": fine_adjust_step_mm,
        "windows_text_width_padding_ratio": windows_text_width_padding_ratio,
        "windows_text_width_padding_min_px": windows_text_width_padding_min_px,
    }


def save_rendering_tuning_settings(
    fine_adjust_step_mm,
    windows_text_width_padding_ratio,
    windows_text_width_padding_min_px,
):
    """Guarda la calibración de renderizado del visor."""

    def _to_float(value, default_value):
        try:
            if isinstance(value, str):
                value = value.strip().replace(",", ".")
            return float(value)
        except (TypeError, ValueError):
            return float(default_value)

    prefs = load_preferences()
    prefs["fine_adjust_step_mm"] = _to_float(fine_adjust_step_mm, 0.1)
    prefs["windows_text_width_padding_ratio"] = _to_float(
        windows_text_width_padding_ratio, 0.20
    )
    prefs["windows_text_width_padding_min_px"] = _to_float(
        windows_text_width_padding_min_px, 2.0
    )
    return save_preferences(prefs)


def get_startup_settings():
    """Obtiene la configuración de inicio de la aplicación (sin sangre, que es parte del proyecto)"""
    prefs = load_preferences()
    unit = prefs.get("last_unit", "mm")
    if unit == "px":
        unit = "mm"
    return {
        "page_size": prefs.get("last_page_size", "A4"),
        "unit": unit,
    }


def save_startup_settings(page_size, unit):
    """Guarda la configuración de inicio (sin sangre, que es parte del proyecto)"""
    prefs = load_preferences()
    prefs["last_page_size"] = page_size
    prefs["last_unit"] = unit
    return save_preferences(prefs)


def get_text_style_profiles():
    """Obtiene los perfiles de texto guardados en preferencias globales"""
    prefs = load_preferences()
    return prefs.get("text_style_profiles", [])


def save_text_style_profiles(profiles_data):
    """
    Guarda los perfiles de texto en preferencias globales

    Args:
        profiles_data: Lista de diccionarios con los datos de cada perfil
    """
    prefs = load_preferences()
    prefs["text_style_profiles"] = profiles_data
    return save_preferences(prefs)


def get_barcode_profiles():
    """Obtiene los perfiles de código de barras guardados en preferencias globales"""
    prefs = load_preferences()
    return prefs.get("barcode_profiles", [])


def save_barcode_profiles(profiles_data):
    """
    Guarda los perfiles de código de barras en preferencias globales

    Args:
        profiles_data: Lista de diccionarios con los datos de cada perfil
    """
    prefs = load_preferences()
    prefs["barcode_profiles"] = profiles_data
    return save_preferences(prefs)


def get_variable_text_profiles():
    """Obtiene los perfiles de texto variable guardados en preferencias globales"""
    prefs = load_preferences()
    return prefs.get("variable_text_profiles", [])


def save_variable_text_profiles(profiles_data):
    """
    Guarda los perfiles de texto variable en preferencias globales

    Args:
        profiles_data: Lista de diccionarios con los datos de cada perfil
    """
    prefs = load_preferences()
    prefs["variable_text_profiles"] = profiles_data
    return save_preferences(prefs)


def get_preference(key, default=None):
    """Obtiene una preferencia específica"""
    prefs = load_preferences()
    return prefs.get(key, default)


def save_preference(key, value):
    """Guarda una preferencia específica"""
    prefs = load_preferences()
    prefs[key] = value
    return save_preferences(prefs)


def get_last_backgrounds():
    """Obtiene los últimos fondos usados (CARA y DORSO)"""
    prefs = load_preferences()
    return {
        "CARA": prefs.get("last_background_cara", {}),
        "DORSO": prefs.get("last_background_dorso", {}),
    }


def save_last_backgrounds(cara_config, dorso_config):
    """Guarda los últimos fondos usados"""
    prefs = load_preferences()
    prefs["last_background_cara"] = cara_config
    prefs["last_background_dorso"] = dorso_config
    return save_preferences(prefs)


# ============================================================================
# COLOR SWATCHES
# ============================================================================


def save_color_swatches(swatches):
    """
    Guarda las muestras de color en preferencias.

    Args:
        swatches: Lista de 8 elementos, cada uno es dict con {rgb, cmyk, space} o None
    """
    return save_preference("color_swatches", swatches)


def get_color_swatches():
    """
    Obtiene las muestras de color guardadas.

    Returns:
        Lista de 8 elementos (dict o None)
    """
    swatches = get_preference("color_swatches", None)
    if swatches is None:
        # Inicializar con 27 slots vacíos
        swatches = [None] * 27
        save_color_swatches(swatches)
    elif len(swatches) < 27:
        # Ampliar lista antigua a 27
        swatches = swatches + [None] * (27 - len(swatches))
        save_color_swatches(swatches)
    return swatches


def delete_preferences():
    """Elimina el archivo de preferencias y caches/dirs legacy.

    Buscamos en varias ubicaciones conocidas para ayudar en depuración.
    Devuelve True si la operación fue exitosa (o no había nada que borrar),
    False si hubo errores.
    """
    import shutil
    from pathlib import Path

    print("[PREFERENCES] delete_preferences() called")

    config_dir = get_config_dir()

    candidates = [
        PREFERENCES_FILE,
        FONT_CACHE_FILE,
        # Nota: no borrar `config_dir / 'font_cache'` aquí. Usar funciones granulares
        # `delete_font_cache_general()` y `delete_font_cache_prefs()` desde la UI.
        # config_dir / 'font_cache',  # nueva ubicación de caché de fuentes
        config_dir / "font_metrics",
        config_dir / "fonts",
        Path.cwd() / "config" / "preferences.json",
        Path(os.path.dirname(os.path.abspath(__file__))).parent.parent
        / "config"
        / "preferences.json",
    ]

    removed = []
    errors = []

    for p in candidates:
        try:
            if p.exists():
                if p.is_dir():
                    shutil.rmtree(p)
                    removed.append(str(p))
                    print(f"[PREFERENCES] Removed directory: {p}")
                else:
                    p.unlink()
                    removed.append(str(p))
                    print(f"[PREFERENCES] Removed file: {p}")
            else:
                print(f"[PREFERENCES] Not present: {p}")
        except Exception as ex:
            errors.append((str(p), str(ex)))
            print(f"[PREFERENCES] Error removing {p}: {ex}")

    # Intentar limpiar el directorio de configuración si quedó vacío
    try:
        if (
            config_dir.exists()
            and config_dir.is_dir()
            and not any(config_dir.iterdir())
        ):
            try:
                config_dir.rmdir()
                removed.append(str(config_dir))
                print(f"[PREFERENCES] Removed empty config dir: {config_dir}")
            except Exception as ex:
                print(
                    f"[PREFERENCES] Could not remove config dir (non-empty or protected): {ex}"
                )
    except Exception:
        pass

    if errors:
        print(f"[PREFERENCES] Errors occurred while deleting preferences: {errors}")
        return False

    if not removed:
        print("[PREFERENCES] No preferences or legacy files found to remove.")
    else:
        print(f"[PREFERENCES] Removed items: {removed}")

    return True


def delete_font_cache_general():
    """Elimina el caché temporal de fuentes (extracted/ y font_index.json),
    PRESERVANDO fonts_prefs/ que es usado por perfiles guardados.
    Devuelve True si se eliminó o no existía, False si hubo error.
    """
    import shutil

    success = True
    try:
        config_dir = get_config_dir()
        font_cache_dir = config_dir / "font_cache"

        # Eliminar extracted/
        extracted_dir = font_cache_dir / "extracted"
        if extracted_dir.exists() and extracted_dir.is_dir():
            shutil.rmtree(extracted_dir)
            print(f"[PREFERENCES] ✓ Removed extracted fonts: {extracted_dir}")
        else:
            print(f"[PREFERENCES] No extracted fonts to remove")

        # Eliminar font_index.json
        index_file = font_cache_dir / "font_index.json"
        if index_file.exists() and index_file.is_file():
            index_file.unlink()
            print(f"[PREFERENCES] ✓ Removed font index: {index_file}")
        else:
            print(f"[PREFERENCES] No font index to remove")

        # PRESERVAR fonts_prefs/ (contiene fuentes de perfiles guardados)
        fonts_prefs_dir = font_cache_dir / "fonts_prefs"
        if fonts_prefs_dir.exists():
            print(
                f"[PREFERENCES] ℹ️ Preserving fonts_prefs (used by saved profiles): {fonts_prefs_dir}"
            )

        return True
    except Exception as ex:
        print(f"[PREFERENCES] ⚠️ Error removing font cache: {ex}")
        return False


def delete_font_cache_prefs():
    """⚠️ Elimina el subdirectorio `fonts_prefs` dentro de `font_cache`.
    ADVERTENCIA: Esto romperá los perfiles guardados que usen fuentes extraídas.
    Solo usar si también se van a eliminar las preferencias completas.
    Devuelve True si se eliminó o no existía, False si hubo error.
    """
    import shutil

    try:
        config_dir = get_config_dir()
        target = config_dir / "font_cache" / "fonts_prefs"
        if target.exists() and target.is_dir():
            shutil.rmtree(target)
            print(
                f"[PREFERENCES] ⚠️ Removed fonts_prefs dir (saved profiles may break): {target}"
            )
        else:
            print(f"[PREFERENCES] fonts_prefs not present: {target}")
        return True
    except Exception as ex:
        print(f"[PREFERENCES] Error removing fonts_prefs {target}: {ex}")
        return False


def delete_main_preferences():
    """Elimina la carpeta completa de configuración de PageNumber
    (~/Library/Application Support/PageNumber en macOS) con TODAS sus
    preferencias, cachés y fuentes guardadas.
    ⚠️ ADVERTENCIA: Esto resetea TODOS los perfiles de texto, colores y configuración guardada.
    Devuelve True si se eliminó o no existía, False si hubo error.
    """
    import shutil

    config_dir = get_config_dir()
    try:
        if config_dir.exists():
            shutil.rmtree(config_dir)
            print(f"[PREFERENCES] ⚠️ Removed PageNumber config dir: {config_dir}")
        else:
            print(f"[PREFERENCES] PageNumber config dir not present: {config_dir}")
        return True
    except Exception as ex:
        print(f"[PREFERENCES] Error removing PageNumber config dir {config_dir}: {ex}")
        return False


def delete_background_cache():
    """Elimina los archivos del caché de fondos"""
    import shutil

    try:
        cache_dir = get_background_cache_dir()
        if cache_dir.exists():
            shutil.rmtree(cache_dir)
            cache_dir.mkdir()
            _vprint(f"[PREFERENCES] Background cache cleared: {cache_dir}")
        return True
    except Exception as e:
        print(f"[PREFERENCES] Error clearing background cache: {e}")
        return False


def reset_last_backgrounds():
    """Resetea la configuración de fondos en las preferencias globales"""
    try:
        prefs = load_preferences()
        if "last_background_cara" in prefs:
            del prefs["last_background_cara"]
        if "last_background_dorso" in prefs:
            del prefs["last_background_dorso"]
        save_preferences(prefs)
        _vprint("[PREFERENCES] Last backgrounds reset to clean state")
        return True
    except Exception as e:
        print(f"[PREFERENCES] Error resetting backgrounds: {e}")
        return False


def get_last_file_dialog_path():
    """Último directorio usado por cualquier file picker (imagen, Excel, proyecto, etc.)"""
    return get_preference("last_file_dialog_path", os.path.expanduser("~/Documents"))


def set_last_file_dialog_path(filepath):
    """Guarda el directorio del archivo seleccionado como último path de file picker."""
    if filepath:
        save_preference("last_file_dialog_path", os.path.dirname(os.path.abspath(filepath)))
