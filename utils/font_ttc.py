"""
Utilities to inspect TTC/OTC files: determine index for a requested style
and extract a subfont to bytes or to a file. Centralized so callers
use a single authoritative implementation.
"""
from typing import Optional
import unicodedata
import io

_PRINT_DEBUG = False  # ← ACTIVADO para ver todos los prints de debug
if not _PRINT_DEBUG:
    def _no_print(*args, **kwargs):
        return None
    print = _no_print

def _unicode_tokens(s: str):
    if not s:
        return []
    tokens = []
    cur = []
    for ch in s:
        cat = unicodedata.category(ch)
        if cat.startswith('L') or cat.startswith('N'):
            cur.append(ch)
        else:
            if cur:
                tokens.append(''.join(cur).lower())
                cur = []
    if cur:
        tokens.append(''.join(cur).lower())
    return tokens


_style_weight_map = {
    'thin': 100,
    'ultralight': 200,
    'light': 300,
    'regular': 400,
    'book': 400,
    'medium': 500,
    'semibold': 600,
    'demibold': 600,
    'bold': 700,
    'black': 900,
}


def _target_weight(style: str) -> Optional[int]:
    s = (style or '').lower()
    for k in _style_weight_map:
        if k in s:
            return _style_weight_map[k]
    return None


def _panose_to_weight(panose_weight: int) -> int:
    """Convierte PANOSE bWeight (byte 2) a usWeightClass numérico."""
    weight_map = {
        2: 150, 3: 300, 4: 325, 5: 400, 6: 500,
        7: 600, 8: 700, 9: 850, 10: 900, 11: 950,
    }
    return weight_map.get(panose_weight, 400)


def _get_font_weight_with_panose(font) -> Optional[int]:
    """Obtiene el peso validado con PANOSE si está disponible."""
    try:
        os2 = font.get('OS/2', None)
        if not os2:
            return None
        
        usWeightClass = getattr(os2, 'usWeightClass', None)
        
        # Intentar leer PANOSE
        try:
            panose = os2.panose
            panose_weight_byte = panose.bWeight
            if panose_weight_byte > 0:
                panose_weight = _panose_to_weight(panose_weight_byte)
                # Si PANOSE y usWeightClass difieren mucho, PANOSE es más confiable
                if usWeightClass and abs(panose_weight - usWeightClass) > 100:
                    return panose_weight
        except Exception:
            pass
        
        return usWeightClass
    except Exception:
        return None


def determine_ttc_index(ttc_path: str, font_style: str) -> int:
    """Determine the member index inside a TTC/OTC for the requested style.

    Returns 0 on fallback or error.
    """
    try:
        from fontTools.ttLib import TTCollection
        print(f"[TTC util] Determinando índice para estilo '{font_style}' en {ttc_path}")
        desired_weight = _target_weight(font_style)
        ttc = TTCollection(ttc_path)

        candidates = []  # (index, match_type, weight)
        for i, font in enumerate(ttc):
            try:
                name_table = font.get('name')
                # score name records: prefer platformID==3 lang==0x409, then platformID==3, then platformID==1
                best_full = None
                best_full_score = 0
                best_sub = None
                best_sub_score = 0
                for record in name_table.names:
                    try:
                        txt = record.toUnicode()
                    except Exception:
                        try:
                            txt = record.string.decode('utf-8', 'replace')
                        except Exception:
                            txt = ''
                    score = 0
                    if record.platformID == 3 and record.langID == 0x409:
                        score = 3
                    elif record.platformID == 3:
                        score = 2
                    elif record.platformID == 1:
                        score = 1
                    if record.nameID == 4 and score > best_full_score:
                        best_full_score = score
                        best_full = txt
                    if record.nameID == 2 and score > best_sub_score:
                        best_sub_score = score
                        best_sub = txt
                full = best_full or None
                sub = best_sub or None
                full_tokens = set(_unicode_tokens(full))
                sub_tokens = set(_unicode_tokens(sub))
                combined = full_tokens | sub_tokens

                # Obtener peso validado con PANOSE
                weight_validated = _get_font_weight_with_panose(font)

                print(f"[TTC util] Índice {i}: '{full}' (estilo: '{sub}') weight={weight_validated or 'n/a'}")

                req_tokens = set(_unicode_tokens(font_style))
                if req_tokens and req_tokens.issubset(sub_tokens):
                    candidates.append((i, 'exact_sub', weight_validated))
                    continue
                if req_tokens and req_tokens.issubset(full_tokens):
                    candidates.append((i, 'exact_full', weight_validated))
                    continue
                if req_tokens and req_tokens.issubset(combined):
                    candidates.append((i, 'combined', weight_validated))
                    continue
            except Exception:
                continue

        if candidates:
            # Primero dar preferencia absoluta a coincidencias por token (más fiables cuando están presentes)
            for pref in ('exact_sub', 'exact_full', 'combined'):
                for c in candidates:
                    if c[1] == pref:
                        print(f"[TTC util] ✓ Seleccionado índice {c[0]} por coincidencia {pref}")
                        return c[0]

            # Si no hubo coincidencias por token, usar heurística por peso si existe desired_weight
            if desired_weight is not None:
                # Ignorar miembros sin usWeightClass (None) para no tratarlos como 0
                weighted = [(i, w) for (i, _m, w) in candidates if w is not None]
                if weighted:
                    best = min(weighted, key=lambda c: abs(c[1] - desired_weight))
                    print(f"[TTC util] ✓ Seleccionado índice {best[0]} por cercanía de peso (desired={desired_weight})")
                    return best[0]
                # Si ninguno tiene weight metadata, caerá al fallback abajo
        
        # Si no hubo candidatos por token matching, intentar fallback por peso puro
        # (útil para fuentes con nombres en scripts no-latinos)
        if not candidates and desired_weight is not None:
            print(f"[TTC util] Sin matches por token, intentando fallback por peso (desired={desired_weight})")
            weight_candidates = []
            for i, font in enumerate(ttc):
                try:
                    weight = _get_font_weight_with_panose(font)
                    if weight is not None:
                        weight_candidates.append((i, weight))
                except Exception:
                    continue
            
            if weight_candidates:
                best = min(weight_candidates, key=lambda c: abs(c[1] - desired_weight))
                print(f"[TTC util] ✓ Seleccionado índice {best[0]} por peso (weight={best[1]}, diff={abs(best[1]-desired_weight)})")
                return best[0]

        # Fallback: try to detect Regular
        req_tokens = set(_unicode_tokens(font_style))
        if ''.join(req_tokens) == 'regular' or (not req_tokens and font_style.lower().strip() == 'regular'):
            for i, font in enumerate(ttc):
                try:
                    name_table = font.get('name')
                    full = None
                    sub = None
                    for record in name_table.names:
                        try:
                            txt = record.toUnicode()
                        except Exception:
                            txt = ''
                        if record.nameID == 4 and full is None:
                            full = txt
                        if record.nameID == 2 and sub is None:
                            sub = txt
                    fnorm = (full or '').lower().replace(' ', '').replace('-', '')
                    snorm = (sub or '').lower().replace(' ', '').replace('-', '')
                    has_modifier = any(mod in fnorm for mod in ['bold', 'italic', 'oblique', 'light', 'medium', 'thin', 'black', 'heavy', 'condensed', 'ultra'])
                    if not has_modifier or snorm in ['regular', 'normal', 'roman']:
                        print(f"[TTC util] ✓ Índice {i} parece ser Regular (sin modificadores)")
                        return i
                except Exception:
                    continue

        print(f"[TTC util] No se encontró estilo '{font_style}', usando índice 0")
        return 0
    except ImportError:
        print("[TTC util] fontTools no está instalado; fallback índice 0")
        return 0
    except Exception as e:
        print(f"[TTC util] Error determinando índice TTC: {e}")
        return 0


def extract_subfont_to_file(ttc_path: str, font_index: int, out_path: str) -> bool:
    """Extracts the member at `font_index` from `ttc_path` and writes it to `out_path`.

    Returns True on success.
    """
    try:
        from fontTools.ttLib import TTCollection, TTFont
        if ttc_path.lower().endswith(('.ttc', '.otc')):
            try:
                ttc = TTCollection(ttc_path)
                if font_index >= len(ttc):
                    print(f"[TTC util] Índice {font_index} fuera de rango (max {len(ttc)-1}); usar 0")
                    font_index = 0
                font = ttc[font_index]
                font.save(out_path)
                ttc.close()
                return True
            except Exception:
                # fallback: try TTFont with fontNumber
                tt = TTFont(ttc_path, fontNumber=font_index)
                tt.save(out_path)
                tt.close()
                return True
        else:
            # not a collection: just copy
            from shutil import copyfile
            copyfile(ttc_path, out_path)
            return True
    except ImportError:
        print("[TTC util] fontTools no está instalado; no se puede extraer")
        return False
    except Exception as e:
        print(f"[TTC util] Error extrayendo subfuente: {e}")
        return False


def extract_subfont_bytes(ttc_path: str, font_index: int) -> Optional[bytes]:
    """Return extracted subfont as bytes, or None on error."""
    try:
        from fontTools.ttLib import TTCollection, TTFont
        import io
        if ttc_path.lower().endswith(('.ttc', '.otc')):
            try:
                ttc = TTCollection(ttc_path)
                if font_index >= len(ttc):
                    font_index = 0
                font = ttc[font_index]
                buf = io.BytesIO()
                font.save(buf)
                ttc.close()
                return buf.getvalue()
            except Exception:
                tt = TTFont(ttc_path, fontNumber=font_index)
                buf = io.BytesIO()
                tt.save(buf)
                tt.close()
                return buf.getvalue()
        else:
            with open(ttc_path, 'rb') as fh:
                return fh.read()
    except Exception as e:
        print(f"[TTC util] Error extrayendo bytes de subfuente: {e}")
        return None
