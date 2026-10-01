"""Font index and cache validation helpers for PageNumber (utils).

Functions:
 - enumerate_fonts_macos()
 - enumerate_fonts_windows()
 - enumerate_fonts_linux()
 - build_font_index()
 - validate_cached_fonts(cached_fonts: dict) -> dict

validate_cached_fonts returns a mapping:
  { family: { style: status } }
where status is one of: 'installed', 'activated-only', 'missing'

Designed for PR1: use CoreText on macOS to detect activated fonts and
help mark cached entries as installed/activated-only/missing.
"""

from __future__ import annotations

import os
import platform
import subprocess
import hashlib
from collections import defaultdict
from typing import Dict, List

PLATFORM = platform.system()

_PRINT_DEBUG = False  # ← ACTIVADO para ver todos los prints de debug
if not _PRINT_DEBUG:

    def _no_print(*args, **kwargs):
        return None

    print = _no_print

try:
    import CoreText as CT  # type: ignore
except Exception:
    CT = None  # type: ignore

try:
    import winreg  # type: ignore
except Exception:
    winreg = None  # type: ignore

try:
    from fontTools.ttLib import TTFont  # type: ignore
except Exception:
    TTFont = None  # type: ignore


# Cache en memoria del indice para evitar releer CoreText completo en cada apertura.
_cached_index: Dict[str, List[Dict[str, str]]] | None = None
_cached_signature_macos: str | None = None
_RUNTIME_FONT_EXTS = {".ttf", ".otf", ".ttc", ".otc"}


def _is_runtime_supported_font_path(path: str | None) -> bool:
    """True si la ruta apunta a un formato que puede abrir el runtime PDF.

    Solo .ttf/.otf/.ttc/.otc son soportados por PyMuPDF/fitz.
    Archivos sin extensión, Type 1 (.pfb/.pfa), .bdf, .pcf, .scr, etc.
    quedan fuera: el sistema los puede mostrar pero la app no los usa.
    """
    if not path:
        return False
    return os.path.splitext(path)[1].lower() in _RUNTIME_FONT_EXTS


def _compute_macos_registry_signature() -> str | None:
    """Retorna una firma ligera del estado de fuentes del sistema en macOS.

    Usa listas CoreText de bajo costo (familias + PostScript names) y no recorre
    descriptores completos con URLs/rutas.
    """
    if CT is None:
        return None

    def _digest(values) -> tuple[int, str]:
        items = sorted(str(v) for v in (values or []) if v is not None)
        if not items:
            return (0, "empty")
        payload = "\n".join(items).encode("utf-8", errors="ignore")
        return (len(items), hashlib.sha1(payload).hexdigest())

    try:
        fam = CT.CTFontManagerCopyAvailableFontFamilyNames()
        ps = CT.CTFontManagerCopyAvailablePostScriptNames()
        fam_count, fam_hash = _digest(fam)
        ps_count, ps_hash = _digest(ps)
        return f"fam:{fam_count}:{fam_hash}|ps:{ps_count}:{ps_hash}"
    except Exception:
        return None


def enumerate_fonts_macos() -> Dict[str, List[Dict[str, str]]]:
    """Enumerate fonts using CoreText collection APIs (robust across PyObjC versions).

    Uses CTFontCollectionCreateFromAvailableFonts + CTFontCollectionCreateMatchingFontDescriptors
    because some PyObjC builds do not export the legacy CTFontManagerCopyAvailableFontDescriptors
    symbol. This approach returns descriptors that include kCTFontURLAttribute when available.
    """
    if CT is None:
        raise RuntimeError("PyObjC CoreText not available on this system")

    index: Dict[str, List[Dict[str, str]]] = defaultdict(list)

    try:
        coll = CT.CTFontCollectionCreateFromAvailableFonts(None)
        descriptors = CT.CTFontCollectionCreateMatchingFontDescriptors(coll)
    except Exception as ex:
        # Fall back to empty index on error
        raise RuntimeError(f"CoreText collection enumeration failed: {ex}")

    if not descriptors:
        print("CoreText returned no descriptors")
        return {}

    for desc in descriptors:
        try:
            url = CT.CTFontDescriptorCopyAttribute(desc, CT.kCTFontURLAttribute)
            fam = CT.CTFontDescriptorCopyAttribute(desc, CT.kCTFontFamilyNameAttribute)
            name = CT.CTFontDescriptorCopyAttribute(desc, CT.kCTFontNameAttribute)
        except Exception:
            continue

        if fam is None:
            continue
        fams = str(fam)
        name_s = str(name) if name is not None else ""
        path = None
        if url is not None:
            try:
                path = url.path()
            except Exception:
                path = str(url)

        # Descartar fuentes no usables por el runtime (Type 1, sin extensión, etc.)
        if not _is_runtime_supported_font_path(path):
            print(
                "macOS font SKIP (no runtime):", fams, "->", name_s, path or "(no-path)"
            )
            continue

        index[fams].append({"name": name_s, "path": path or ""})
        print("macOS font:", fams, "->", name_s, path or "(no-path)")

    return dict(index)


def iter_windows_font_files() -> List[str]:
    if winreg is None:
        raise RuntimeError("winreg not available (not Windows)")

    # Se agregan raíces para buscar también fuentes de usuario
    # (HKEY_CURRENT_USER) que es donde se instalan muchas fuentes modernas.
    roots = [
        (
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts",
        ),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Fonts"),
        (
            winreg.HKEY_CURRENT_USER,
            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts",
        ),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Fonts"),
    ]
    paths = set()
    for root_hkey, root_path in roots:
        try:
            key = winreg.OpenKey(root_hkey, root_path)
        except OSError:
            continue
        i = 0
        while True:
            try:
                name, value, _ = winreg.EnumValue(key, i)
            except OSError:
                break
            i += 1
            if not value:
                continue
            val = value
            if not os.path.isabs(val):
                # Si no es ruta absoluta, buscar en C:\Windows\Fonts (Sistema)
                # o en %LOCALAPPDATA%\Microsoft\Windows\Fonts (Usuario)
                windir = os.environ.get("WINDIR", r"C:\Windows")
                path_sys = os.path.join(windir, "Fonts", val)

                local_app_data = os.environ.get("LOCALAPPDATA", "")
                path_user = os.path.join(
                    local_app_data, "Microsoft", "Windows", "Fonts", val
                )

                if os.path.exists(path_sys):
                    paths.add(os.path.normpath(path_sys))
                elif os.path.exists(path_user):
                    paths.add(os.path.normpath(path_user))
            else:
                path = val
                if os.path.exists(path):
                    paths.add(os.path.normpath(path))
    return sorted(paths)


def enumerate_fonts_windows() -> Dict[str, List[Dict[str, str]]]:
    files = iter_windows_font_files()
    # Filtrar ya en la lista: solo formatos usables por runtime
    files = [f for f in files if _is_runtime_supported_font_path(f)]
    index: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for f in files:
        name = os.path.basename(f)
        fam = name
        if TTFont is not None:
            try:
                # Check if it's a collection (.ttc/.otc)
                is_collection = f.lower().endswith((".ttc", ".otc"))

                if is_collection:
                    # For TTC/OTC collections, enumerate each font inside
                    font_num = 0
                    while True:
                        try:
                            tt = TTFont(f, lazy=True, fontNumber=font_num)
                            name_table = tt["name"]
                            fam = None
                            full = None
                            for record in name_table.names:
                                if record.nameID == 1 and fam is None:
                                    try:
                                        fam = record.toUnicode()
                                    except Exception:
                                        fam = str(record.string)
                                if record.nameID == 4 and full is None:
                                    try:
                                        full = record.toUnicode()
                                    except Exception:
                                        full = str(record.string)
                            if fam is None:
                                fam = os.path.basename(f)
                            full = full or os.path.basename(f)
                            tt.close()
                            index.setdefault(str(fam), []).append(
                                {"name": str(full), "path": f}
                            )
                            print("windows TTC member:", fam, "->", full, f)
                            font_num += 1
                        except Exception as e:
                            # No more fonts in this collection or error reading
                            break
                else:
                    # Single font file
                    tt = TTFont(f, lazy=True)
                    name_table = tt["name"]
                    fam = None
                    full = None
                    for record in name_table.names:
                        if record.nameID == 1 and fam is None:
                            try:
                                fam = record.toUnicode()
                            except Exception:
                                fam = str(record.string)
                        if record.nameID == 4 and full is None:
                            try:
                                full = record.toUnicode()
                            except Exception:
                                full = str(record.string)
                    if fam is None:
                        fam = os.path.basename(f)
                    full = full or os.path.basename(f)
                    tt.close()
                    index.setdefault(str(fam), []).append(
                        {"name": str(full), "path": f}
                    )
                    print("windows font:", fam, "->", full, f)
            except Exception:
                fam = os.path.basename(f)
                index.setdefault(str(fam), []).append({"name": str(name), "path": f})
        else:
            index.setdefault(str(fam), []).append({"name": str(name), "path": f})
    print("Windows enumeration complete. Families:", len(index))
    return dict(index)


def enumerate_fonts_linux() -> Dict[str, List[Dict[str, str]]]:
    try:
        out = subprocess.check_output(
            ["fc-list", ":", "file", "family"], text=True, stderr=subprocess.DEVNULL
        )
    except Exception as exc:
        raise RuntimeError("fc-list not available or failed: %s" % exc)

    index: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for line in out.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        path, rest = line.split(":", 1)
        if not _is_runtime_supported_font_path(path):
            continue
        family = rest.strip().split(",")[0].strip() if rest else os.path.basename(path)
        index.setdefault(family, []).append({"name": family, "path": path})
        print("linux font:", family, path)
    return dict(index)


def build_font_index(force: bool = False) -> Dict[str, List[Dict[str, str]]]:
    """Construye el indice de fuentes del sistema.

    En macOS usa cache en memoria y una firma ligera del estado del sistema para
    evitar releer descriptores completos en cada llamada.
    """
    global _cached_index, _cached_signature_macos

    if PLATFORM == "Darwin" and not force and _cached_index is not None:
        sig = _compute_macos_registry_signature()
        if sig is not None and sig == _cached_signature_macos:
            print("Building font index: usando cache en memoria (macOS)")
            return _cached_index

    print("Building font index for platform:", PLATFORM)
    if PLATFORM == "Darwin":
        result = enumerate_fonts_macos()
        _cached_index = result
        _cached_signature_macos = _compute_macos_registry_signature()
        return result
    elif PLATFORM == "Windows":
        return enumerate_fonts_windows()
    else:
        return enumerate_fonts_linux()


def validate_cached_fonts(
    cached_fonts: Dict[str, List[str]],
) -> Dict[str, Dict[str, str]]:
    """Validate cached fonts and return per-style status.

    Returns: { family: { style: status } }
    status in {'installed', 'activated-only', 'missing'}
    """
    # Intentar usar gestor_fuentes para validación basada en rutas de archivo
    try:
        from . import font_manager

        gestor = font_manager.obtener_gestor()

        if gestor and gestor.fuentes:
            # Construir índice inverso: ruta de archivo -> lista de nombres/estilos del sistema
            try:
                idx = build_font_index()
            except Exception:
                idx = {}

            print("Validating cached fonts against system index and gestor_fuentes")
            # Crear mapeo: archivo normalizado -> lista de entries del sistema
            file_to_system_entries: Dict[str, List[Dict[str, str]]] = defaultdict(list)
            for family, entries in idx.items():
                for e in entries:
                    path = e.get("path")
                    if path:
                        # Normalizar ruta para comparación robusta
                        normalized_path = (
                            os.path.normpath(os.path.realpath(path))
                            if os.path.exists(path)
                            else os.path.normpath(path)
                        )
                        file_to_system_entries[normalized_path].append(e)

            # Validar cada familia/estilo usando rutas de archivo
            result: Dict[str, Dict[str, str]] = {}
            for family, styles in cached_fonts.items():
                print("Checking family:", family, "styles:", styles)
                fam_status = {}

                # Buscar variantes de esta familia en el caché de gestor_fuentes con estructura jerárquica
                # gestor.fuentes = {familia: {peso: {italic: dict}}}
                pesos_dict = gestor.fuentes.get(family, {})

                for style in styles:
                    matched = False
                    style_norm = "".join(
                        ch for ch in (style or "").lower() if ch.isalnum()
                    )

                    def _style_match(candidate: str | None) -> bool:
                        cand = "".join(
                            ch for ch in (candidate or "").lower() if ch.isalnum()
                        )
                        if not cand or not style_norm:
                            return False
                        return (
                            cand == style_norm
                            or cand in style_norm
                            or style_norm in cand
                        )

                    # Iterar sobre la estructura jerárquica: peso -> italic -> datos
                    for peso_key, italic_dict in pesos_dict.items():
                        if not isinstance(italic_dict, dict):
                            continue
                        for italic_key, variante in italic_dict.items():
                            if not isinstance(variante, dict):
                                continue
                            # Verificar si esta variante corresponde al estilo buscado
                            if (
                                _style_match(variante.get("subfamilia"))
                                or _style_match(variante.get("nombre"))
                                or _style_match(variante.get("name"))
                            ):
                                # Encontrada en caché, verificar si el archivo existe en el sistema
                                ruta_cache = variante.get("ruta")
                                if ruta_cache:
                                    # Normalizar ruta del caché
                                    ruta_normalizada = (
                                        os.path.normpath(os.path.realpath(ruta_cache))
                                        if os.path.exists(ruta_cache)
                                        else os.path.normpath(ruta_cache)
                                    )

                                    # Verificar si este archivo está en el índice del sistema
                                    if ruta_normalizada in file_to_system_entries:
                                        # Archivo encontrado en sistema
                                        if _is_runtime_supported_font_path(ruta_cache):
                                            fam_status[style] = "installed"
                                        else:
                                            fam_status[style] = "activated-only"
                                        matched = True
                                        break
                                    else:
                                        # El path no coincide con el índice CoreText (puede ser
                                        # diferencia de caché vs. ruta actual), pero si el archivo
                                        # existe en disco se considera instalado igualmente.
                                        if _is_runtime_supported_font_path(ruta_cache):
                                            print(
                                                f"  -> style '{style}' ({family}): path no en CoreText index pero archivo existe: {ruta_cache}"
                                            )
                                            fam_status[style] = "installed"
                                            matched = True
                                            break
                        if matched:
                            break

                    if not matched:
                        # Fallback robusto: si existe la familia en idx, no marcar missing por
                        # diferencias de naming de estilo (Times-Roman vs Times Roman, etc.).
                        fam_entries = idx.get(family, [])
                        if fam_entries:
                            any_path_exists = any(
                                _is_runtime_supported_font_path(e.get("path"))
                                for e in fam_entries
                            )
                            fam_status[style] = (
                                "installed" if any_path_exists else "activated-only"
                            )
                        else:
                            fam_status[style] = "missing"
                            print("  -> style not matched:", family, style)

                result[family] = fam_status

            return result

    except Exception as e:
        # Si falla gestor_fuentes, usar método original
        print(
            f"[FONT_VALIDATE] Gestor no disponible, usando método de validación básico: {e}"
        )
        pass

    # Método de validación original (fallback)
    try:
        idx = build_font_index()
    except Exception:
        idx = {}
    result: Dict[str, Dict[str, str]] = {}

    for family, styles in cached_fonts.items():
        fam_entries = idx.get(family, [])
        fam_status = {}
        if not fam_entries:
            # Family not found at all
            for s in styles:
                fam_status[s] = "missing"
            result[family] = fam_status
            continue

        # If we have entries for family, check whether any entry has an existing file path
        any_path_exists = any(
            _is_runtime_supported_font_path(e.get("path")) for e in fam_entries
        )
        for s in styles:
            # Try best-effort match: look for style token in entry name or filename
            matched = False
            style_token = "".join(ch for ch in (s or "").lower() if ch.isalpha())

            # En macOS, si la familia existe con archivos válidos, considerar todos los estilos como instalados
            # a menos que se pueda hacer una validación más específica
            if PLATFORM == "Darwin" and any_path_exists:
                # Intentar match específico primero
                for e in fam_entries:
                    name = (e.get("name") or "").lower()
                    fname = os.path.basename(e.get("path") or "").lower()
                    # Buscar el token completo o partes del estilo
                    if style_token and (
                        style_token in name
                        or style_token in fname
                        or s.lower() in name
                        or s.lower() in fname
                    ):
                        if _is_runtime_supported_font_path(e.get("path")):
                            fam_status[s] = "installed"
                        else:
                            fam_status[s] = "activated-only"
                        matched = True
                        break

                # Si no hubo match específico pero la familia tiene archivos válidos, asumir instalado
                if not matched:
                    fam_status[s] = "installed"
                    matched = True
            else:
                # Windows/Linux: validación más estricta
                for e in fam_entries:
                    name = (e.get("name") or "").lower()
                    fname = os.path.basename(e.get("path") or "").lower()
                    if style_token and (style_token in name or style_token in fname):
                        if _is_runtime_supported_font_path(e.get("path")):
                            fam_status[s] = "installed"
                        else:
                            fam_status[s] = "activated-only"
                        matched = True
                        break

            if not matched:
                # No exact match for style; if any path exists for family consider installed
                fam_status[s] = "installed" if any_path_exists else "activated-only"
        result[family] = fam_status

    return result


def find_font_file_for(family: str, style: str = "Regular") -> tuple:
    """Find best matching font file for a given family and style using the built index.

    Returns: (path_or_None, status)
      - path_or_None: str path to font file if available (may be .ttf/.otf/.ttc) or None
      - status: 'installed' | 'activated-only' | 'missing'
    """
    try:
        idx = build_font_index()
    except Exception:
        idx = {}

    # 0) NORMALIZACION Y FALLBACKS MULTIPLATAFORMA
    families_to_try = [family]

    # En Windows, si piden Helvetica (default de la app), buscar Arial como fallback
    if PLATFORM == "Windows":
        if family.lower() == "helvetica":
            families_to_try.append("Arial")
        elif family.lower() == "times":
            families_to_try.append("Times New Roman")
        elif family.lower() == "courier":
            families_to_try.append("Courier New")

    entries = []
    found_family = None
    for fam in families_to_try:
        # Búsqueda exacta
        if fam in idx:
            entries = idx[fam]
            found_family = fam
            break

        # Búsqueda case-insensitive
        fam_lower = fam.lower()
        matches = [v for k, v in idx.items() if k.lower() == fam_lower]
        if matches:
            entries = matches[0]
            found_family = next(k for k in idx.keys() if k.lower() == fam_lower)
            break

        # Búsqueda por subcadena (solo si la familia tiene cierta longitud)
        if len(fam) > 3:
            matches = [v for k, v in idx.items() if fam_lower in k.lower()]
            if matches:
                entries = matches[0]
                found_family = next(k for k in idx.keys() if fam_lower in k.lower())
                break

    if not entries:
        return (None, "missing")

    style_token = "".join(ch for ch in (style or "").lower() if ch.isalpha())

    # 1) Preferir exact style match in entry name or filename
    for e in entries:
        name = (e.get("name") or "").lower()
        fname = os.path.basename(e.get("path") or "").lower()
        if style_token and (style_token in name or style_token in fname):
            p = e.get("path")
            if p and os.path.exists(p):
                return (p, "installed")
            else:
                return (p or None, "activated-only")

    # 2) Fallback: if any entry has a real file path, return it
    for e in entries:
        p = e.get("path")
        if p and os.path.exists(p):
            return (p, "installed")

    # 3) Otherwise return first entry as activated-only
    e0 = entries[0]
    return (e0.get("path") or None, "activated-only")

    # 1) prefer exact style match in entry name or filename
    for e in entries:
        name = (e.get("name") or "").lower()
        fname = os.path.basename(e.get("path") or "").lower()
        if style_token and (style_token in name or style_token in fname):
            p = e.get("path")
            if p and os.path.exists(p):
                return (p, "installed")
            else:
                return (p or None, "activated-only")

    # 2) fallback: if any entry has a real file path, return it
    for e in entries:
        p = e.get("path")
        if p and os.path.exists(p):
            return (p, "installed")

    # 3) otherwise return first entry as activated-only
    e0 = entries[0]
    return (e0.get("path") or None, "activated-only")


def assign_font_file(family: str, style: str, src_path: str) -> str:
    """Register a user-selected font file path for immediate use without copying.

    Formerly this function copied the file into Application Support. Per decision
    we do NOT copy by default: the app will *register* and use the selected
    path directly (so the system path is respected and no duplicate files are created).

    Returns the validated src_path.
    """
    # Validate presence and extension
    if not os.path.exists(src_path):
        raise RuntimeError(f"Font file not found: {src_path}")
    ext = os.path.splitext(src_path)[1].lower()
    if ext not in (".ttf", ".otf", ".ttc"):
        raise RuntimeError(f"Unsupported font extension: {ext}")

    # Do not copy; return original path for registration
    return src_path


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument("--dump", help="Write index JSON to file")
    parser.add_argument("--search", help="Search family substring")
    args = parser.parse_args()

    idx = build_font_index()
    if args.search:
        for fam, items in sorted(idx.items()):
            if args.search.lower() in fam.lower():
                print(f"{fam} -> {len(items)}")
                for it in items[:10]:
                    print("    ", it.get("name"), it.get("path"))
    elif args.dump:
        with open(args.dump, "w", encoding="utf-8") as fh:
            json.dump(idx, fh, indent=2, ensure_ascii=False)
        print("Wrote:", args.dump)
    else:
        print(f"Platform: {PLATFORM}")
        print(f"Families: {len(idx)}")
        for fam in sorted(list(idx.keys())[:50]):
            print("-", fam)
