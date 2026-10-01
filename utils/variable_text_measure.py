"""Medición y resolución de la caja de texto variable (tight a la tinta).

Compartido por el diálogo (preview), el viewer (render + ancla) y el PDF
(posicionamiento). La caja NO tiene tamaño fijo: su ancho y alto son el bbox
de la tinta real del texto (retornos de carro + cuerpo + interlineado), sin
el em-box de la fuente.

Marcadores soportados en el texto:
- `<@<columna>@>` → valor de la columna Excel en la fila correspondiente.

Los retornos de carro son reales (Enter del teclado), nunca un marcador.
"""

from __future__ import annotations

import os
import re

try:
    import fitz
except ImportError:
    fitz = None

_MARKER_COL = re.compile(r"<@<([^>]+)>@>")

# Mapa de ancla (9) → fracción (fx, fy) del punto de la CAJA que coincide con la guía.
# La guía es el punto fijo; el ancla dice qué punto de la caja descansa sobre ella:
#   fx: 0 = guía en el borde izquierdo (caja a la derecha), 1 = borde derecho.
#   fy: 0 = guía en el tope (caja cuelga DEBAJO de la guía), 1 = guía en la base
#       (caja descansa SOBRE la guía). 0.5 = centrado en ese eje.
ANCHOR_UV = {
    "superior_izquierda": (0.0, 1.0),
    "superior_centro": (0.5, 1.0),
    "superior_derecha": (1.0, 1.0),
    "centro_izquierda": (0.0, 0.5),
    "centro_centro": (0.5, 0.5),
    "centro_derecha": (1.0, 0.5),
    "inferior_izquierda": (0.0, 0.0),
    "inferior_centro": (0.5, 0.0),
    "inferior_derecha": (1.0, 0.0),
}

DEFAULT_ANCHOR = "superior_izquierda"


def anchor_uv(anchor):
    """Fracción (fx, fy) del ancla; fallback a superior izquierda."""
    return ANCHOR_UV.get(anchor, ANCHOR_UV[DEFAULT_ANCHOR])


def vertical_anchor_offset(fy, box, font_path, font_size_pt):
    """Offset vertical (pt) desde el TOP de la caja hasta el punto que coincide con la guía.

    El texto descansa sobre las LETRAS NORMALES, no sobre caracteres que cuelgan
    o sobresalen (`@`, `j`, acentos): el ancla usa la baseline / métricas de
    diseño constantes, nunca el borde de la tinta.
        fy=1 (superior): baseline de la última línea.
        fy=0 (inferior): tope de la tinta (caja cuelga pegada a la guía).
        fy=0.5 (centro): centro de la caja tight (incluye cuelgue, como el usuario).
    """
    if not box.get("baselines"):
        return fy * box.get("box_h", 0.0)
    if fy >= 1.0:
        return box["baselines"][-1]
    if fy <= 0.0:
        return 0.0
    return fy * box.get("box_h", 0.0)


def resolve_vt_text(
    sample_text: str,
    value_source: str = "sample",
    excel_column: str = "",
    excel_manager=None,
    row_index: int = 0,
    text_case_filter: str = "",
) -> str:
    """Resuelve los marcadores `<@<columna>@>` al texto final.

    Los marcadores se sustituyen siempre que haya un excel cargado con la
    columna (independiente de value_source): el preview debe mostrar el valor
    real. Si la columna no existe o no hay excel, se deja literal en modo
    "sample" y vacío en modo "excel". Los retornos de carro ya vienen reales
    (`\n`) del editor.
    """
    text = sample_text or ""

    if excel_manager is not None:
        def _replace_col(m):
            col = m.group(1).strip()
            if not col:
                return m.group(0) if value_source != "excel" else ""
            try:
                if not excel_manager.is_loaded:
                    return m.group(0) if value_source != "excel" else ""
                value = excel_manager.get_value_at(col, row_index)
                if value is not None:
                    return value
                return m.group(0) if value_source != "excel" else ""
            except Exception:
                return m.group(0) if value_source != "excel" else ""

        text = _MARKER_COL.sub(_replace_col, text)

    if text_case_filter and (value_source == "excel" or excel_manager is not None):
        from ui.variable_text_settings_dialog import VariableTextProfile

        text = VariableTextProfile.apply_text_case_filter(text, text_case_filter)
    return text


def extract_used_columns(sample_text):
    """Columnas usadas por los marcadores `<@<col>@>` del texto (ordenadas)."""
    return [m for m in _MARKER_COL.findall(sample_text or "")]


def _measure_resolved_width(text, font_path, font_size_pt):
    """Ancho real (pt) de la línea más ancha de la tinta, sin renderizar pixmap.

    fitz.text_length es rápido (miles de filas en <1s) y respeta el ancho real de
    cada glifo: 'más caracteres no quiere decir que sea más larga' (una 'W' pesa
    más que una 'l').
    """
    if not text:
        return 0.0
    try:
        if font_path and os.path.exists(font_path):
            f = fitz.Font(fontfile=font_path)
        else:
            f = fitz.Font(fontname="helv")
        return max(
            (f.text_length(ln, fontsize=font_size_pt) for ln in text.split("\n")),
            default=0.0,
        )
    except Exception:
        return max(len(ln) for ln in text.split("\n")) * font_size_pt * 0.6


def find_extreme_row(row_count, build_value_fn, font_path, font_size_pt, want_max=True):
    """Fila (0-based) cuyo valor resuelto ocupa más/menos ancho de tinta.

    build_value_fn(row_index) → str (texto ya resuelto de la fila). Escaneo
    lineal con fitz.text_length; apto para miles de filas.
    """
    best_row = 0
    best_width = None
    for i in range(row_count):
        try:
            w = _measure_resolved_width(build_value_fn(i), font_path, font_size_pt)
        except Exception:
            w = 0.0
        if best_width is None or (w > best_width if want_max else w < best_width):
            best_width = w
            best_row = i
    return best_row


def _font_asc_desc(font_path, font_size_pt):
    """Métricas de DISEÑO de la fuente (asc/desc en pt), constantes por fuente.

    El interlineado se define sobre estas métricas (no sobre la tinta de cada
    fila): acentos/mayúsculas/descendentes no deben mover la caja ni el espaciado.
    """
    asc = font_size_pt * 0.8
    desc = font_size_pt * 0.2
    if fitz:
        try:
            if font_path and os.path.exists(font_path):
                f = fitz.Font(fontfile=font_path)
            else:
                f = fitz.Font(fontname="helv")
            asc = font_size_pt * f.ascender
            desc = font_size_pt * (-f.descender if f.descender < 0 else f.descender)
        except Exception:
            pass
    return asc, desc


def _measure_line_fallback(line, font_path, font_size_pt):
    """Aproximación sin métricas extraídas: ancho por text_length, asc/desc de la fuente."""
    asc, desc = _font_asc_desc(font_path, font_size_pt)
    width = len(line) * font_size_pt * 0.6
    if fitz:
        try:
            if font_path and os.path.exists(font_path):
                f = fitz.Font(fontfile=font_path)
            else:
                f = fitz.Font(fontname="helv")
            width = f.text_length(line, fontsize=font_size_pt)
        except Exception:
            pass
    return {
        "width": width,
        "baseline_to_top": asc,
        "baseline_to_bottom": desc,
        "left_bearing": 0.0,
    }


def _measure_line_tight(line, font_path, font_size_pt):
    """Tinta real de una línea: scan del render de PyMuPDF.

    PyMuPDF reporta el bbox de línea completo (asc/desc de la FUENTE, igual para
    todas las líneas). El scan rasteriza el clip y da la tinta real: ancho,
    left_bearing y la vertical tal y como se imprime. El interlineado lo fija el
    grid de baselines en measure_vt_box (paso line_spacing), NO esta tinta.
    """
    if not line:
        return {
            "width": 0.0,
            "baseline_to_top": 0.0,
            "baseline_to_bottom": 0.0,
            "left_bearing": 0.0,
        }
    if not fitz:
        return _measure_line_fallback(line, font_path, font_size_pt)
    try:
        fs = max(1, int(round(font_size_pt)))
        page_w = max(400, int(fs * (len(line) + 1) * 1.4) + 200)
        doc = fitz.open()
        page = doc.new_page(width=page_w, height=400)
        bx, by = 100.0, 200.0
        # Registrar la fuente igual que el PDF (_ensure_font_cached): insert_font(fontbuffer)
        # + insert_text(fontname=...). insert_text(fontfile=...) renderiza fuentes con métricas
        # raras (p. ej. Herculanum) más estrechas que el dibujo real del PDF → box_w corto.
        if font_path and os.path.exists(font_path):
            with open(font_path, "rb") as _fh:
                page.insert_font(fontname="vtm", fontbuffer=_fh.read())
            page.insert_text((bx, by), line, fontsize=fs, fontname="vtm")
        else:
            page.insert_text((bx, by), line, fontsize=fs)

        # Caja aproximada (font-wide) para acotar el clip del scan.
        bbox = origin = None
        for block in page.get_text("dict").get("blocks", []):
            if block.get("type") != 0:
                continue
            for l in block.get("lines", []):
                for s in l.get("spans", []):
                    if s.get("text") == line:
                        bbox = s.get("bbox")
                        origin = s.get("origin")
                        break
                if bbox:
                    break
            if bbox:
                break
        if bbox is None or origin is None:
            doc.close()
            return _measure_line_fallback(line, font_path, font_size_pt)

        zoom = 4
        clip = fitz.Rect(bbox)
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False, clip=clip)
        samples = pix.samples
        w, h = pix.width, pix.height
        min_x = 10**9
        min_y = 10**9
        max_x = -1
        max_y = -1
        for y in range(h):
            row = y * w * 3
            for x in range(w):
                if samples[row + x * 3] < 255:
                    if x < min_x:
                        min_x = x
                    if x > max_x:
                        max_x = x
                    if y < min_y:
                        min_y = y
                    if y > max_y:
                        max_y = y
        doc.close()
        if max_x < 0:
            return _measure_line_fallback(line, font_path, font_size_pt)

        ox = (origin[0] - clip.x0) * zoom
        oy = (origin[1] - clip.y0) * zoom
        return {
            "width": (max_x - min_x) / zoom,
            # Tinta real vertical de la línea. El interlineado de la caja NO
            # depende de esto: lo fija el grid de baselines en measure_vt_box.
            "baseline_to_top": (oy - min_y) / zoom,
            "baseline_to_bottom": (max_y - oy) / zoom,
            "left_bearing": (min_x - ox) / zoom,
        }
    except Exception:
        return _measure_line_fallback(line, font_path, font_size_pt)


def measure_vt_box(
    lines,
    font_path,
    font_size_pt,
    line_spacing: float = 0.0,
    letter_spacing: float = 0.0,
):
    """bbox tight de una caja de texto multilínea.

    lines: iterable de str (una por línea, ya resueltas sin marcadores).
    font_path: ruta .ttf/.otf de la fuente (para métricas reales por glifo).
    letter_spacing: interletraje en pt entre caracteres (n-1 huecos por línea).

    Returns dict:
        lines        : [ {width, spaced_width, baseline_to_top, baseline_to_bottom, left_bearing} ]
        box_w        : ancho tight en pt (unión de la tinta de todas las líneas + interletraje)
        box_h        : alto tight en pt (de la tinta superior a la inferior)
        baselines    : y del baseline de cada línea desde el top de la caja (pt)
        line_heights : avance de cada línea = line_spacing pt (leading total estilo InDesign; 0 = varias líneas en la misma baseline)
        left_offset  : desplazamiento del borde izquierdo de la tinta respecto al origen (pt)
    """
    lines = [ln or "" for ln in lines]
    if not lines:
        return {
            "lines": [],
            "box_w": 0.0,
            "box_h": 0.0,
            "baselines": [],
            "line_heights": [],
            "left_offset": 0.0,
        }

    ls = float(letter_spacing or 0.0)
    line_data = []
    for ln in lines:
        if not ln:
            line_data.append(
                {
                    "width": 0.0,
                    "spaced_width": 0.0,
                    "baseline_to_top": 0.0,
                    "baseline_to_bottom": 0.0,
                    "left_bearing": 0.0,
                }
            )
            continue
        try:
            d = _measure_line_tight(ln, font_path, font_size_pt)
        except Exception:
            d = _measure_line_fallback(ln, font_path, font_size_pt)
        d["spaced_width"] = max(0.0, d["width"] + ls * (len(ln) - 1))
        line_data.append(d)

    asc_reals = [d["baseline_to_top"] for d in line_data]
    desc_reals = [d["baseline_to_bottom"] for d in line_data]

    # left_offset: el borde izquierdo de la tinta es el min de los left_bearing.
    # (sin clamp: si todos los left_bearing > 0 el box_w sería pen→tinta-más-ancha e
    # incluiría el aire de la izquierda; el ancla del PDF resta left_bearing al pen,
    # así que box_w debe ser el span de tinta real).
    left_offset = min((d["left_bearing"] for d in line_data), default=0.0)

    # box_w: unión horizontal de la tinta = max(right_ink) - min(left_bearing).
    # right_ink usa el ancho ESPACIADO (tinta + n-1 huecos de interletraje): el
    # render per-char avanza text_length(ch)+spacing, así el ancla/alineación
    # cuadra con el dibujo.
    right_ink = [d["left_bearing"] + d["spaced_width"] for d in line_data]
    box_w = max(right_ink) - left_offset if line_data else 0.0

    # baselines: cada línea se posiciona por su baseline. line_spacing = interlineado
    # en pt = avance TOTAL de línea (leading estilo InDesign, p. ej. 1.2×cuerpo).
    # Con 0 todas las líneas caen en la misma baseline.
    # ponytail: sin floor — un mínimo de 1.2×(asc+desc) ≈ 1.5×cuerpo congelaba el
    # visor y el PDF por debajo del AUTO (1.2×cuerpo). El anti-apilado va en los
    # llamadores del PDF (dato ausente → default), no en la medida compartida.
    line_heights = [max(float(line_spacing), 0.0) for _ in asc_reals]
    raw_baselines = []
    acc = asc_reals[0] if asc_reals else 0.0
    raw_baselines.append(acc)
    for h in line_heights[:-1]:
        acc += h
        raw_baselines.append(acc)

    # box_h: tinta superior → inferior de la UNIÓN de todas las líneas (no solo la
    # primera): una línea con ascendentes más altos sube la caja, una con más
    # descendentes la baja. Caja tight real, sin recorte.
    ink_tops = [b - d["baseline_to_top"] for b, d in zip(raw_baselines, line_data)]
    ink_bottoms = [b + d["baseline_to_bottom"] for b, d in zip(raw_baselines, line_data)]
    box_top = min(ink_tops) if ink_tops else 0.0
    box_bottom = max(ink_bottoms) if ink_bottoms else 0.0
    baselines = [b - box_top for b in raw_baselines]
    box_h = box_bottom - box_top

    return {
        "lines": line_data,
        "box_w": box_w,
        "box_h": box_h,
        "baselines": baselines,
        "line_heights": line_heights,
        "left_offset": left_offset,
    }


def _vt_hex_to_rgb(color):
    """'#RRGGBB' / '#AARRGGBB' / tupla → (r, g, b)."""
    if isinstance(color, (tuple, list)):
        return tuple(int(c) for c in color[:3])
    if not isinstance(color, str):
        return (0, 0, 0)
    c = color.lstrip("#")
    try:
        if len(c) == 6:
            return tuple(int(c[i : i + 2], 16) for i in (0, 2, 4))
        if len(c) == 8:
            return tuple(int(c[i : i + 2], 16) for i in (2, 4, 6))
    except ValueError:
        pass
    return (0, 0, 0)


def render_vt_image_b64(
    lines,
    font_path,
    font_size_pt,
    line_spacing_pt=0.0,
    letter_spacing_pt=0.0,
    text_alignment="izquierda",
    text_color=(0, 0, 0),
    supersample=4,
):
    """Render PIL de una caja de texto variable → (b64, box_w_pt, box_h_pt, baselines_pt).

    La imagen es la TINTA real (getmask) dibujada con anchor='lt', por lo que
    coincide pixel a pixel con el bbox tight de la caja de `measure_vt_box`.
    El blanco se hace transparente (la página del visor ya es blanca). La
    rotación NO se incluye: la aplica el contenedor del visor, igual que el PDF
    rota alrededor de la guía. Devuelve la caja en pt (independiente de la
    escala del visor), lista para anclar como el PDF. baselines_pt es el grid
    de baselines (desde el top de la caja) que usa el ancla vertical.
    letter_spacing_pt: interletraje en pt; si es != 0 el texto se dibuja
    carácter a carácter (avance text_length(ch)+spacing, se pierde el kerning,
    misma regla que las numeradoras). Con 0 = dibujo nativo con kerning.
    """
    lines = [ln or "" for ln in lines]

    def _fallback_box():
        b = measure_vt_box(
            lines,
            font_path,
            font_size_pt,
            line_spacing=line_spacing_pt,
            letter_spacing=letter_spacing_pt,
        )
        return b["box_w"], b["box_h"], list(b["baselines"])

    try:
        import base64
        import io
        import math

        from PIL import Image, ImageDraw, ImageFont
    except Exception:
        w, h, bl = _fallback_box()
        return "", w, h, bl

    if not font_path or not os.path.exists(font_path) or not lines:
        w, h, bl = _fallback_box()
        return "", w, h, bl

    ppp = max(1, int(supersample))
    font_px = max(1, int(round(font_size_pt * ppp)))
    font = ImageFont.truetype(font_path, font_px)

    # Ink real de cada línea relativo al origen 'lt' (getmask == draw anchor='lt').
    # ponytail: FreeType lanza `division by zero` para Helvetica con px < 8 (cualquier texto);
    # en ese caso devolvemos la caja medida (PyMuPDF) sin imagen en vez de crashear.
    try:
        masks = []
        for ln in lines:
            mb = font.getmask(ln).getbbox()
            masks.append(mb if mb is not None else (0, 0, 0, 0))
    except OSError:
        w, h, bl = _fallback_box()
        return "", w, h, bl
    union_left = min((m[0] for m in masks), default=0)
    union_right = max((m[2] for m in masks), default=0)
    box_w_px = max(1, int(math.ceil(union_right - union_left)))

    # Baselines de la caja (pt, equidistantes a line_spacing) desde measure_vt_box:
    # el mismo grid que usa el PDF. El render ancla cada línea por SU BASELINE
    # (anchor 'ls'), no por el top de la tinta: un acento/descendente alarga la
    # tinta dentro de su propio aire pero NUNCA mueve la línea del grid.
    box = measure_vt_box(
        lines,
        font_path,
        font_size_pt,
        line_spacing=line_spacing_pt,
        letter_spacing=letter_spacing_pt,
    )
    baselines_px = [b * ppp for b in box["baselines"]]
    box_h_px = max(1, int(math.ceil(box["box_h"] * ppp)))

    # Posición de cada línea y canvas que nunca recorte (derecha/centro con
    # left_bearing divergente pueden asomarse; izq siempre == measure_vt_box).
    # Con interletraje cada carácter se dibuja en su propio pen: el avance por
    # carácter (getlength + spacing) extiende la tinta, así que el canvas usa el
    # máximo de (extensión por avance, tinta real del mask).
    ls_px = float(letter_spacing_pt or 0.0) * ppp
    line_layout = []
    canvas_left = 0
    canvas_right = box_w_px
    for i, ln in enumerate(lines):
        if not ln:
            continue
        w_i = masks[i][2] - masks[i][0]
        if ls_px:
            # Con interletraje se dibuja per-char (avance getlength+spacing): la
            # alineación y el canvas usan ESE avance, no la tinta del mask sin
            # espaciar. Con ls negativo + derecha, mask+align_off inflaba la imagen
            # con aire a la derecha y separaba el texto de la guía.
            ref_w = sum(font.getlength(ch) for ch in ln) + ls_px * (len(ln) - 1)
        else:
            ref_w = w_i
        if text_alignment == "derecha":
            align_off = box_w_px - ref_w
        elif text_alignment == "centro":
            align_off = (box_w_px - ref_w) // 2
        else:
            align_off = 0
        ink_left = masks[i][0] - union_left + align_off
        lx = ink_left - masks[i][0]
        anchors = []
        pen = lx
        for ch in ln:
            anchors.append(pen)
            pen += font.getlength(ch) + ls_px
        if ls_px and anchors:
            line_left = anchors[0] + font.getbbox(ln[0])[0]
            line_right = anchors[-1] + font.getbbox(ln[-1])[2]
        else:
            line_left = lx
            line_right = masks[i][2] - union_left + align_off
        canvas_left = min(canvas_left, line_left)
        canvas_right = max(canvas_right, line_right)
        line_layout.append((ln, anchors, baselines_px[i]))
    box_w_px = max(1, int(math.ceil(canvas_right - canvas_left)))

    img = Image.new("RGB", (box_w_px, box_h_px), "white")
    draw = ImageDraw.Draw(img)
    fill = _vt_hex_to_rgb(text_color)
    if ls_px:
        for ln, anchors, ly in line_layout:
            for ch, ax in zip(ln, anchors):
                draw.text((ax - canvas_left, ly), ch, fill=fill, font=font, anchor="ls")
    else:
        # ls == 0 → dibujo nativo de la línea entera (con kerning), igual que antes.
        for ln, anchors, ly in line_layout:
            draw.text((anchors[0] - canvas_left, ly), ln, fill=fill, font=font, anchor="ls")

    # Blanco → transparente (la página del visor ya es blanca).
    img = img.convert("RGBA")
    img.putdata(
        [
            (p[0], p[1], p[2], 0)
            if p[0] > 240 and p[1] > 240 and p[2] > 240
            else p
            for p in img.getdata()
        ]
    )
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return (
        base64.b64encode(buf.getvalue()).decode(),
        box_w_px / ppp,
        box_h_px / ppp,
        box["baselines"],
    )


def measure_text_advance_with_spacing(font_obj, text, font_size_pt, letter_spacing=0.0):
    """Ancho (pt) de `text` añadiendo letter_spacing ENTRE caracteres (n-1 huecos).

    Sirve de medición compartida para numeradoras y texto variable: el render
    per-char (insert_text por carácter) avanza `text_length(ch) + spacing` y
    esta función suma lo mismo, para que la métrica cuadre con el dibujo.
    `letter_spacing <= 0` → avance nativo sin huecos extra.
    """
    if not text:
        return 0.0
    try:
        total = sum(font_obj.text_length(ch, fontsize=font_size_pt) for ch in text)
    except Exception:
        total = len(text) * font_size_pt * 0.6
    if letter_spacing and len(text) > 1:
        total += letter_spacing * (len(text) - 1)
    return total


if __name__ == "__main__":
    # Self-check de find_extreme_row: la fila más ancha NO es la de más caracteres.
    vals = ["l", "WWWWWWWWWW", "WW", "WWWWWWWW"]
    longest = find_extreme_row(
        len(vals), lambda i: vals[i], "", 12.0, want_max=True
    )
    shortest = find_extreme_row(
        len(vals), lambda i: vals[i], "", 12.0, want_max=False
    )
    assert longest == 1, longest
    assert shortest == 0, shortest
    # Fila con varias líneas: cuenta la línea más ancha.
    multi = ["a", "b\nWWWWWWWWWW", "c"]
    assert find_extreme_row(len(multi), lambda i: multi[i], "", 12.0, want_max=True) == 1

    # measure_text_advance_with_spacing: n-1 huecos, monótono con el spacing.
    font = fitz.Font(fontname="helv") if fitz else None
    base_ab = measure_text_advance_with_spacing(font, "AB", 12.0, 0.0)
    spaced_ab = measure_text_advance_with_spacing(font, "AB", 12.0, 5.0)
    assert base_ab > 0.0 and base_ab + 5.0 == spaced_ab, (base_ab, spaced_ab)
    single_a = measure_text_advance_with_spacing(font, "A", 12.0, 0.0)
    assert measure_text_advance_with_spacing(font, "A", 12.0, 5.0) == single_a, "1 char sin huecos"
    assert measure_text_advance_with_spacing(font, "", 12.0, 5.0) == 0.0, "texto vacío"

    # measure_vt_box con interletraje: box_w crece n-1 huecos por línea y
    # spaced_width == width + ls*(n-1) (tinta intacta en width).
    _helv = "/System/Library/Fonts/Helvetica.ttc"
    if os.path.exists(_helv):
        b0 = measure_vt_box(["AB", "C"], _helv, 12.0)
        b5 = measure_vt_box(["AB", "C"], _helv, 12.0, letter_spacing=5.0)
        assert b5["box_w"] >= b0["box_w"] + 5.0, (b0["box_w"], b5["box_w"])
        assert b5["lines"][0]["spaced_width"] == b5["lines"][0]["width"] + 5.0
        assert b5["lines"][1]["spaced_width"] == b5["lines"][1]["width"], "1 char sin huecos"
        assert b0["box_h"] == b5["box_h"], "el interletraje NO toca la altura"
    print("variable_text_measure: self-check OK")
