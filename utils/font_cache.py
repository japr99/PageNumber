from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Any
import shutil
import time


_PRINT_DEBUG = False  # ← ACTIVADO para ver todos los prints de debug
if not _PRINT_DEBUG:
    def _no_print(*args, **kwargs):
        return None
    print = _no_print

try:
    from fontTools.ttLib import TTFont, TTCollection
    FONTTOOLS_AVAILABLE = False
except Exception:
    FONTTOOLS_AVAILABLE = False

def get_config_dir() -> Path:
    """Return the application config dir for storing caches.

    Tries to import the project's `preferences.get_config_dir`, falls back to
    a local `config/` directory.
    """
    try:
        from .preferences import get_config_dir as _gcd
        return _gcd() / "font_cache"
    except Exception:
        return Path("config") / "font_cache"


def ensure_dirs(base: Path) -> None:
    base.mkdir(parents=True, exist_ok=True)
    (base / "extracted").mkdir(parents=True, exist_ok=True)
    (base / "fonts_prefs").mkdir(parents=True, exist_ok=True)


def cache_path(base: Path) -> Path:
    return base / "font_index.json"


def load_cache(base: Path) -> Dict[str, Any]:
    p = cache_path(base)
    if not p.exists():
        return {}
    try:
        with open(p, 'r', encoding='utf-8') as fh:
            return json.load(fh)
    except Exception:
        return {}


def save_cache(base: Path, data: Dict[str, Any]) -> None:
    p = cache_path(base)
    tmp = p.with_suffix('.tmp')
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    tmp.replace(p)


def extracted_dir(base: Path) -> Path:
    return base / "extracted"


def prefs_dir(base: Path) -> Path:
    return base / "fonts_prefs"


def list_prefs_files(base: Path):
    d = prefs_dir(base)
    if not d.exists():
        return []
    return [p for p in d.iterdir() if p.is_file()]


def cleanup_prefs_cache(base: Path) -> Dict[str, Any]:
    """Validate extracted files kept in prefs_dir and clean stale cache entries.

    Instead of deleting extracted files, this function validates the `extracted_map`
    entries and removes cache references to missing files in `fonts_prefs/`.
    Returns the updated cache dict.
    """
    # Delegate to validate_extracted_map which performs normalization and marking of stale
    try:
        return validate_extracted_map(base)
    except Exception as e:
        print(f"[FONT_CACHE] Error validating prefs cache: {e}")
        return load_cache(base) or {}


def compute_checksum(path: Path) -> str | None:
    """Compute SHA256 checksum for a file or return None on error."""
    try:
        import hashlib
        h = hashlib.sha256()
        with open(path, 'rb') as fh:
            for chunk in iter(lambda: fh.read(8192), b''):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None


def validate_extracted_map(base: Path) -> Dict[str, Any]:
    """Load cache, validate `extracted_map` entries and attempt safe reconstitution.

    Performs these steps:
    - Detects corrupted JSON cache and backs it up
    - Ensures `fonts_prefs/` exists for re-extracted fonts
    - Validates each `extracted_map` entry: existence, non-zero size, checksum, and TT font validity
    - Attempts to re-extract from `original_path` when possible
    - Deletes corrupt and orphan files directly (no quarantine)
    - Persists an updated cache atomically and creates a backup before overwrite
    """
    cache_file = cache_path(base)
    raw_cache = {}
    try:
        raw_cache = load_cache(base) or {}
    except Exception:
        raw_cache = {}

    # If the file exists but load_cache returned empty and file non-empty, treat as corrupt
    try:
        if cache_file.exists() and cache_file.stat().st_size > 0 and not raw_cache:
            bk = cache_file.with_suffix('.corrupt.' + str(int(time.time())))
            shutil.copy2(cache_file, bk)
            print(f"[FONT_CACHE] WARNING: cache JSON parse failed — backed up to {bk}")
            raw_cache = {}
    except Exception:
        pass

    cache = dict(raw_cache)
    em = cache.get('extracted_map', {}) or {}
    updated = False

    pdir = prefs_dir(base)
    try:
        pdir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    new_em = {}
    reparaciones = 0
    corrupciones = 0

    for key, val in em.items():
        try:
            if isinstance(val, str):
                extracted_path = val
                orig_path, orig_idx = key.split('|', 1) if '|' in key else (None, None)
                entry = {
                    'extracted_path': extracted_path,
                    'original_path': orig_path,
                    'original_mtime': None,
                    'original_checksum': None,
                    'extracted_checksum': compute_checksum(Path(extracted_path)) if extracted_path else None,
                    'timestamp': None,
                    'stale': False,
                }
            elif isinstance(val, dict):
                entry = dict(val)
            else:
                continue

            orig = entry.get('original_path')
            extracted = entry.get('extracted_path')

            need_reextract = False
            if not extracted or not Path(extracted).exists():
                need_reextract = True
            else:
                p = Path(extracted)
                try:
                    if p.stat().st_size == 0:
                        need_reextract = True
                except Exception:
                    need_reextract = True

            if extracted and Path(extracted).exists():
                try:
                    checksum_now = compute_checksum(Path(extracted))
                    entry['extracted_checksum'] = checksum_now
                    if FONTTOOLS_AVAILABLE:
                        try:
                            TTFont(str(extracted))
                        except Exception:
                            need_reextract = True
                except Exception:
                    need_reextract = True

            reconst_path = None
            if need_reextract and orig and Path(orig).exists():
                try:
                    orig_path = Path(orig)
                    safe_fam = Path(entry.get('original_path') or '').stem.replace(' ', '')
                    ttc_index = 0
                    if '|' in key:
                        try:
                            ttc_index = int(key.split('|', 1)[1])
                        except Exception:
                            ttc_index = 0

                    out_name = f"{safe_fam}_idx{ttc_index}.ttf"
                    out_path = str(pdir / out_name)

                    if FONTTOOLS_AVAILABLE and orig_path.suffix.lower() in ('.ttc', '.otc'):
                        try:
                            ttc = TTCollection(str(orig_path))
                            font = ttc.fonts[ttc_index]
                            font.save(out_path)
                            ttc.close()
                        except Exception:
                            tt = TTFont(str(orig_path), fontNumber=ttc_index)
                            tt.save(out_path)
                            tt.close()
                    else:
                        shutil.copy2(str(orig_path), out_path)

                    ok = False
                    if Path(out_path).exists() and Path(out_path).stat().st_size > 0:
                        if FONTTOOLS_AVAILABLE:
                            try:
                                TTFont(out_path)
                                ok = True
                            except Exception:
                                ok = False
                        else:
                            ok = True

                    if ok:
                        reconst_path = out_path
                        reparaciones += 1
                        entry['extracted_path'] = reconst_path
                        entry['extracted_checksum'] = compute_checksum(Path(reconst_path))
                        entry['timestamp'] = time.time()
                        entry['stale'] = False
                        new_em[key] = entry
                        updated = True
                    else:
                        corrupciones += 1
                        entry['stale'] = True
                        # Eliminar archivo corrupto directamente
                        if extracted and Path(extracted).exists():
                            try:
                                Path(extracted).unlink()
                                print(f"[FONT_CACHE] Deleted corrupt file: {Path(extracted).name}")
                            except Exception:
                                pass
                except Exception:
                    entry['stale'] = True
                    corrupciones += 1
            else:
                if extracted and Path(extracted).exists():
                    new_em[key] = entry

        except Exception:
            continue

    # Eliminar archivos huérfanos directamente (no están en extracted_map)
    try:
        seen = {Path(v['extracted_path']).name for v in new_em.values() if v.get('extracted_path')}
        for f in list_prefs_files(base):
            if f.name not in seen:
                try:
                    f.unlink()
                    print(f"[FONT_CACHE] Deleted orphan file: {f.name}")
                except Exception:
                    pass
    except Exception:
        pass

    if updated:
        cache['extracted_map'] = new_em
        try:
            if cache_file.exists():
                bak = cache_file.with_suffix('.bak.' + str(int(time.time())))
                shutil.copy2(cache_file, bak)
                print(f"[FONT_CACHE] Backup of cache saved to {bak}")
        except Exception:
            pass

        try:
            save_cache(base, cache)
            print(f"[FONT_CACHE] Cache updated after validation: {len(new_em)} entries (repaired={reparaciones}, corrupt={corrupciones})")
        except Exception as e:
            print(f"[FONT_CACHE] Error saving updated cache: {e}")
    else:
        print(f"[FONT_CACHE] Validation complete: {len(new_em)} valid entries, reparaciones={reparaciones}, corrupciones={corrupciones}")

    cache['extracted_map'] = new_em
    return cache


def add_extracted_entry(base: Path, original_path: str, ttc_index: int, extracted_path: str) -> None:
    """Add or update an extracted_map entry and persist atomically.

    Entry format follows validate_extracted_map expectations.
    """
    try:
        cache = load_cache(base) or {}
        em = cache.get('extracted_map', {}) or {}
        key = f"{original_path}|{ttc_index}"
        entry = {
            'extracted_path': str(extracted_path),
            'original_path': str(original_path),
            'original_mtime': None,
            'original_checksum': None,
            'extracted_checksum': compute_checksum(Path(extracted_path)) if extracted_path and Path(extracted_path).exists() else None,
            'timestamp': time.time(),
            'stale': False,
        }
        em[key] = entry
        cache['extracted_map'] = em
        save_cache(base, cache)
        print(f"[FONT_CACHE] Added extracted_map entry: {key} -> {entry['extracted_path']}")
    except Exception as e:
        print(f"[FONT_CACHE] Error adding extracted entry: {e}")
