"""Multiplatform font index helper for PageNumber

Wrapper module que delega a PageNumber.utils.font_index para las operaciones
principales y añade funcionalidad de normalización con gestor_fuentes.

Functions provided:
 - build_font_index() -> delegado a utils.font_index
 - get_normalized_fonts() -> usa gestor_fuentes para normalización
 - find_font_file_for() -> usa gestor_fuentes si disponible
 - validate_cached_fonts() -> delegado a utils.font_index

Usage examples:
    python -m font_index  # prints a short summary
    python -m font_index --normalized --search "Helvetica"
"""

from __future__ import annotations

_PRINT_DEBUG = False  # ← ACTIVADO para ver todos los prints de debug
if not _PRINT_DEBUG:

    def _no_print(*args, **kwargs):
        return None

    print = _no_print
import json
import os
import platform
from typing import Dict, List, Optional, Tuple
from .font_manager import get_default_font_family

# Importar implementaciones de utils (mismo directorio)
from . import font_index as utils_font_index

# Verbose debugging desactivado por defecto
VERBOSE = False  # os.environ.get("PAGEFONT_DEBUG", "0").lower() in ("1", "true")
_RUNTIME_FONT_EXTS = {".ttf", ".otf", ".ttc", ".otc"}


def _vprint(*args, **kwargs):
    if VERBOSE:
        print(*args, **kwargs)


def _is_runtime_supported_font_path(path: str | None) -> bool:
    """Retorna True si la ruta apunta a un formato usable por runtime/PyMuPDF."""
    if not path:
        return False
    ext = os.path.splitext(path)[1].lower()
    return ext in _RUNTIME_FONT_EXTS


# Importar gestor de fuentes mejorado (mismo directorio)
try:
    from . import font_manager

    obtener_gestor = font_manager.obtener_gestor
    inicializar_gestor = font_manager.inicializar_gestor
    GESTOR_DISPONIBLE = True
except ImportError:
    GESTOR_DISPONIBLE = False

PLATFORM = platform.system()

# Re-exportar funciones de utils para compatibilidad
enumerate_fonts_macos = utils_font_index.enumerate_fonts_macos
enumerate_fonts_windows = utils_font_index.enumerate_fonts_windows
enumerate_fonts_linux = utils_font_index.enumerate_fonts_linux


def build_font_index() -> Dict[str, List[Dict[str, str]]]:
    """Platform-agnostic front: returns family -> entries.

    On macOS this will use CoreText and thus should find activated-only fonts.
    """
    # Delegar a la implementación de utils que tiene la función CoreText correcta
    try:
        from . import font_index as utils_font_index

        return utils_font_index.build_font_index()
    except Exception as e:
        _vprint(
            f"[FONT_INDEX] Error usando utils.font_index: {e}, usando implementación local"
        )
        # Fallback a implementación local
        if PLATFORM == "Darwin":
            return enumerate_fonts_macos()
        elif PLATFORM == "Windows":
            return enumerate_fonts_windows()
        else:
            return enumerate_fonts_linux()


def inicializar_gestor_explicito():
    """
    Inicializa el gestor de fuentes de forma explícita al inicio de la app.

    Esto asegura que el caché de fuentes se cargue ANTES de que se intenten
    resolver fuentes de perfiles, evitando inicializaciones LAZY tardías.

    Orden correcto de startup:
    1. inicializar_gestor_explicito() ← PRIMERO
    2. Cargar perfiles de texto
    3. Resolver fuentes de perfiles
    4. ensure_preferences_fonts() para extraer TTCs
    """
    if not GESTOR_DISPONIBLE:
        _vprint("[FONT_INIT] Gestor de fuentes no disponible, saltando inicialización")
        return

    _vprint("[FONT_INIT] Inicializando gestor de fuentes de forma explícita...")
    gestor = obtener_gestor()

    # Si ya está inicializado, no hacer nada
    if gestor.fuentes:
        _vprint(
            f"[FONT_INIT] Gestor existente con {len(gestor.fuentes)} familias; sincronizando contra catálogo actual"
        )

    resultado = gestor.sincronizar_con_catalogo_sistema(skip_non_latin=True)
    _vprint(
        "[FONT_INIT] ✓ Gestor sincronizado con catálogo actual: "
        f"{resultado.get('familias', 0)} familias"
    )


def get_normalized_fonts() -> Dict[str, List[str]]:
    """
    Obtiene fuentes del sistema con estilos normalizados usando gestor_fuentes.

    Returns:
        Dict[familia, List[estilos_normalizados]]

    Si gestor_fuentes no está disponible, devuelve el índice básico.
    """
    if not GESTOR_DISPONIBLE:
        # Fallback: usar build_font_index sin normalización
        idx = build_font_index()
        resultado = {}
        for familia, entries in idx.items():
            # Extraer nombres únicos
            estilos = list(set(e.get("name", "Regular") for e in entries))
            resultado[familia] = sorted(estilos)
        return resultado

    # Usar gestor de fuentes para normalización
    gestor = obtener_gestor()

    # Si no está inicializado, cargarlo
    if not gestor.fuentes:
        idx = build_font_index()
        rutas = []
        for familia, entries in idx.items():
            for entry in entries:
                if entry.get("path") and entry["path"] not in rutas:
                    rutas.append(entry["path"])

        inicializar_gestor(rutas)

    # Retornar familias con estilos normalizados
    resultado = gestor.obtener_familias_con_info()

    return resultado


def find_font_file_for(family: str, style: str = "Regular") -> tuple:
    """
    Encuentra archivo de fuente para familia y estilo dados.
    Ahora usa gestor_fuentes si está disponible para mejor matching.

    Returns:
        (path_or_None, status)
        - path_or_None: ruta al archivo o None
        - status: 'installed' | 'activated-only' | 'missing'
    """
    if GESTOR_DISPONIBLE:
        gestor = obtener_gestor()

        # Asegurarse de que está inicializado
        if not gestor.fuentes:
            _vprint(
                f"[FIND_FONT] Inicializando gestor para búsqueda de {family}/{style}"
            )
            idx = build_font_index()
            rutas = []
            for fam, entries in idx.items():
                for entry in entries:
                    if entry.get("path") and entry["path"] not in rutas:
                        rutas.append(entry["path"])
            inicializar_gestor(rutas)
            _vprint(
                f"[FIND_FONT] Gestor inicializado con {len(gestor.fuentes)} familias"
            )

        # Buscar variante
        variante = gestor.buscar_por_estilo(family, style)

        if variante:
            path = variante["ruta"]
            _vprint(f"[FIND_FONT] ✓ Encontrado en gestor: {family}/{style} -> {path}")
            if path and os.path.exists(path) and _is_runtime_supported_font_path(path):
                return (path, "installed")
            elif path and not _is_runtime_supported_font_path(path):
                _vprint(
                    f"[FIND_FONT] Fuente encontrada pero formato no soportado por runtime: {path}"
                )
            else:
                return (path, "activated-only")
        else:
            _vprint(
                f"[FIND_FONT] ✗ No encontrado en gestor: {family}/{style}, usando fallback"
            )
            # Familia no encontrada, buscar en idx normal
            pass
    else:
        _vprint(
            f"[FIND_FONT] Gestor no disponible, usando método clásico para {family}/{style}"
        )

    # Fallback: usar búsqueda original
    idx = build_font_index()

    # Normalización y fallbacks multiplataforma
    families_to_try = [family]

    if PLATFORM == "Windows":
        default_family = get_default_font_family()
        if family.lower() == "helvetica":
            families_to_try.append("Arial")
        elif family.lower() == "times":
            families_to_try.append("Times New Roman")
        elif family.lower() == "courier":
            families_to_try.append("Courier New")

    entries = []
    for fam in families_to_try:
        # Búsqueda exacta
        if fam in idx:
            entries = idx[fam]
            break

        # Búsqueda case-insensitive
        fam_lower = fam.lower()
        matches = [v for k, v in idx.items() if k.lower() == fam_lower]
        if matches:
            entries = matches[0]
            break

        # Búsqueda por subcadena
        if len(fam) > 3:
            matches = [v for k, v in idx.items() if fam_lower in k.lower()]
            if matches:
                entries = matches[0]
                break

    if not entries:
        return (None, "missing")

    style_token = "".join(ch for ch in (style or "").lower() if ch.isalpha())

    # Preferir exact style match
    for e in entries:
        name = (e.get("name") or "").lower()
        fname = os.path.basename(e.get("path") or "").lower()
        if style_token and (style_token in name or style_token in fname):
            p = e.get("path")
            if p and os.path.exists(p) and _is_runtime_supported_font_path(p):
                return (p, "installed")
            else:
                return (p or None, "activated-only")

    # Fallback: devolver primera entrada con archivo real
    for e in entries:
        p = e.get("path")
        if p and os.path.exists(p) and _is_runtime_supported_font_path(p):
            return (p, "installed")

    # Último recurso: primera entrada como activated-only
    e0 = entries[0]
    return (e0.get("path") or None, "activated-only")


def validate_cached_fonts(
    cached_fonts: Dict[str, List[str]],
) -> Dict[str, Dict[str, str]]:
    """
    Valida fuentes en caché y retorna estado por estilo.
    Delegado a utils.font_index.

    Returns:
        { family: { style: status } }
        status in {'installed', 'activated-only', 'missing'}
    """
    return utils_font_index.validate_cached_fonts(cached_fonts)
    if args.normalized:
        # Mostrar fuentes con normalización
        _vprint("[MODO NORMALIZADO - usando gestor_fuentes]")
        idx = get_normalized_fonts()

        if args.search:
            q = args.search.lower()
            for fam, estilos in sorted(idx.items()):
                if q in fam.lower():
                    _vprint(f"\n{fam} -> {len(estilos)} estilos normalizados:")
                    for estilo in estilos:
                        _vprint(f"  - {estilo}")
        else:
            _vprint(f"Familias encontradas: {len(idx)}")
            for fam, estilos in sorted(list(idx.items())[:30]):
                _vprint(f"- {fam} ({len(estilos)} estilos)")

        if args.dump_json:
            with open(args.dump_json, "w", encoding="utf-8") as fh:
                json.dump(idx, fh, indent=2, ensure_ascii=False)
            _vprint("\nEscrito:", args.dump_json)
    else:
        # Modo original
        idx = build_font_index()

        if args.search:
            q = args.search.lower()
            for fam, entries in sorted(idx.items()):
                if q in fam.lower():
                    _vprint(f"{fam} -> {len(entries)} entries")
                    for e in entries[:10]:
                        _vprint("    ", e.get("name"), e.get("path"))
        else:
            _vprint(f"Platform: {PLATFORM}")
            _vprint(f"Families found: {len(idx)}")
            for fam, entries in sorted(idx.items())[:30]:
                _vprint(f"- {fam} ({len(entries)})")

        if args.dump_json:
            with open(args.dump_json, "w", encoding="utf-8") as fh:
                json.dump(idx, fh, indent=2, ensure_ascii=False)
            _vprint("Wrote:", args.dump_json)
