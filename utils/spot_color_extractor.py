"""
Módulo para extraer colores spot (Separation/DeviceN) de páginas PDF.
Utiliza PyMuPDF (fitz) para navegar los recursos de página y decodificar
los espacios de color Separation que indican tintas planas (Pantone, etc.).
"""

import fitz
import re
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# Utilidades de decodificación PDF
# ─────────────────────────────────────────────────────────────────────────────

# Silenciar prints de depuración en este módulo por defecto.
# Para activar, cambiar _PRINT_DEBUG = True durante desarrollo.
_PRINT_DEBUG = False
if not _PRINT_DEBUG:

    def _no_print(*args, **kwargs):
        return None

    print = _no_print
    
def _decode_pdf_name(name: str) -> str:
    """
    Decodifica un nombre PDF.
    Los nombres PDF codifican caracteres especiales como #XX (hex).
    Ejemplo: 'PANTONE#20485#20C' → 'PANTONE 485 C'
    """

    def replace_hex(m):
        return chr(int(m.group(1), 16))

    return re.sub(r"#([0-9A-Fa-f]{2})", replace_hex, name)


def _lab_to_rgb(l: float, a: float, b: float) -> tuple[int, int, int]:
    """Convierte de espacio Lab (D50) a RGB sRGB."""
    y = (l + 16) / 116
    x = a / 500 + y
    z = y - b / 200

    def f_inv(t):
        return t**3 if t**3 > 0.008856 else (t - 16 / 116) / 7.787

    # Illuminant D50 (común en PDF Lab profiles)
    X = f_inv(x) * 0.9642
    Y = f_inv(y) * 1.0000
    Z = f_inv(z) * 0.8249

    r =  3.1338561 * X - 1.6168667 * Y - 0.4906146 * Z
    g = -0.9787684 * X + 1.9161415 * Y + 0.0334540 * Z
    b_chan =  0.0719453 * X - 0.2289914 * Y + 1.4052427 * Z

    def gamma(v):
        v = max(0.0, min(1.0, v))
        return int(round((12.92 * v if v <= 0.0031308 else 1.055 * (v ** (1 / 2.4)) - 0.055) * 255))

    return gamma(r), gamma(g), gamma(b_chan)


def _parse_array_floats(text: str) -> list[float]:
    """Extrae todos los floats de un string que representa un array PDF como '[0 0.5 1 0]'"""
    return [
        float(v) for v in re.findall(r"[-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?", text)
    ]


def _extract_c1_from_function(func_str: str, n_components: int) -> Optional[list]:
    """
    Extrae los valores C1 (tint=1, tinta a pleno) de la cadena de un objeto función PDF.

    Soporta:
      - FunctionType 2 con /C1 [v0 v1 ...]  (exponencial, la más común)
      - FunctionType 0 con /Range [...]       (sampled function — usa la mitad derecha del rango)
    """
    # FunctionType 2 — explícito: /C1 [c m y k]
    c1_match = re.search(r"/C1\s*\[([^\]]*)\]", func_str)
    if c1_match:
        vals = _parse_array_floats(c1_match.group(1))
        if len(vals) >= n_components:
            return vals[:n_components]

    # FunctionType 0 — Range puede darnos los límites máximos del output
    # La Range es [min0 max0 min1 max1 ...] → max de cada canal en tint=1
    range_match = re.search(r"/Range\s*\[([^\]]*)\]", func_str)
    if range_match:
        vals = _parse_array_floats(range_match.group(1))
        if len(vals) >= n_components * 2:
            # Tomar los valores "max" de cada componente
            return [vals[i * 2 + 1] for i in range(n_components)]

    return None


def _parse_separation_object(
    obj_str: str, doc: "fitz.Document" = None
) -> Optional[dict]:
    """
    Intenta parsear un objeto PDF de tipo Separation.
    Formato esperado en el string de objeto:
        [ /Separation /NombreColor /AlternateCS <<función>> ]
      o con la función referenciada:
        [ /Separation /NombreColor /DeviceCMYK 42 0 R ]

    Args:
        obj_str:  String del objeto xref que contiene el Separation.
        doc:      Documento fitz abierto, para seguir referencias a funciones externas.

    Retorna dict con:
        {
            'name': str,           # nombre decodificado de la tinta
            'alternate': str,      # 'CMYK' | 'RGB' | 'Gray' | 'Unknown'
            'cmyk': tuple | None,  # (C, M, Y, K) en 0-100 si alternate=CMYK
            'rgb': str | None,     # '#RRGGBB' si alternate=RGB
        }
    o None si no se puede parsear.
    """
    # Buscar primero el nombre del color (segundo elemento del array)
    m = re.search(r"/Separation\s+/([^\s/\[\]<>(){}]+)", obj_str)
    if not m:
        return None

    raw_name = m.group(1)
    color_name = _decode_pdf_name(raw_name)

    # Ignorar "None" y "All" que son nombres reservados PDF
    if color_name.lower() in ("none", "all"):
        return None

    # Detectar espacio de color alternativo
    alternate = "Unknown"
    cmyk = None
    rgb_hex = None

    resolved_cs_str = obj_str
    if doc is not None:
        # Buscar posibles referencias a espacios de color como "22 0 R"
        for ref_m in re.finditer(r"(\d+)\s+0\s+R", obj_str):
            try:
                ref_obj = doc.xref_object(int(ref_m.group(1)), compressed=False)
                if ref_obj and ("/" in ref_obj or "[" in ref_obj):
                    resolved_cs_str += " " + ref_obj
            except Exception:
                continue

    def _resolve_function_str(obj_str: str, n_comp: int) -> str:
        """
        Devuelve el string con los datos de la función de tinta.
        Primero intenta inline (<<...>>); si no, sigue la referencia 'N 0 R'.
        """
        # ¿Hay función inline entre << >> ?
        if "/C1" in obj_str or "/Range" in obj_str or "/FunctionType" in obj_str:
            return obj_str
        # Buscar referencia externa: último "N 0 R" antes del fin del array
        if doc is not None:
            ref_match = re.search(r"(\d+)\s+0\s+R", obj_str)
            if ref_match:
                ref_xref = int(ref_match.group(1))
                try:
                    ref_str = doc.xref_object(ref_xref, compressed=False)
                    if ref_str:
                        return ref_str
                    # Puede ser un stream (FunctionType 4 o 0)
                    raw = doc.xref_stream(ref_xref)
                    if raw:
                        return raw.decode("latin-1", errors="replace")
                except Exception:
                    pass
        return obj_str

    if "/DeviceCMYK" in resolved_cs_str:
        alternate = "CMYK"
        func_str = _resolve_function_str(obj_str, 4)
        vals = _extract_c1_from_function(func_str, 4)
        if vals and len(vals) >= 4:
            cmyk = (
                round(vals[0] * 100, 1),
                round(vals[1] * 100, 1),
                round(vals[2] * 100, 1),
                round(vals[3] * 100, 1),
            )
        if cmyk is None:
            cmyk = (0.0, 0.0, 0.0, 100.0)  # fallback negro

    elif "/DeviceRGB" in resolved_cs_str:
        alternate = "RGB"
        func_str = _resolve_function_str(obj_str, 3)
        vals = _extract_c1_from_function(func_str, 3)
        if vals and len(vals) >= 3:
            r = int(vals[0] * 255)
            g = int(vals[1] * 255)
            b = int(vals[2] * 255)
            rgb_hex = "#{:02x}{:02x}{:02x}".format(r, g, b)
            try:
                from ui.color_picker import rgb_to_cmyk

                cmyk = rgb_to_cmyk(r, g, b)
            except Exception:
                pass

    elif "/DeviceGray" in resolved_cs_str:
        alternate = "Gray"
        func_str = _resolve_function_str(obj_str, 1)
        vals = _extract_c1_from_function(func_str, 1)
        if vals:
            k = round((1 - vals[0]) * 100, 1)
            cmyk = (0.0, 0.0, 0.0, k)

    elif "/Lab" in resolved_cs_str:
        alternate = "Lab"
        func_str = _resolve_function_str(obj_str, 3)
        vals = _extract_c1_from_function(func_str, 3)
        if vals and len(vals) >= 3:
            r, g, b = _lab_to_rgb(vals[0], vals[1], vals[2])
            rgb_hex = "#{:02x}{:02x}{:02x}".format(r, g, b)
            try:
                from ui.color_picker import rgb_to_cmyk

                cmyk = rgb_to_cmyk(r, g, b)
            except Exception:
                pass

    # Generar hex RGB desde CMYK si no se tiene
    if cmyk is not None and rgb_hex is None:
        try:
            from ui.color_picker import cmyk_to_rgb

            r, g, b = cmyk_to_rgb(*cmyk)
            rgb_hex = "#{:02x}{:02x}{:02x}".format(r, g, b)
        except Exception:
            rgb_hex = "#000000"

    return {
        "name": color_name,
        "alternate": alternate,
        "cmyk": cmyk if cmyk is not None else (0.0, 0.0, 0.0, 100.0),
        "rgb": rgb_hex or "#000000",
    }


def _parse_devicen_object(obj_str: str) -> list[dict]:
    """
    Intenta parsear un objeto PDF de tipo DeviceN.
    Formato: [ /DeviceN [name1 name2 ...] /AlternateCS <<función>> ]

    Retorna lista de dicts (uno por nombre de tinta encontrado).
    Para DeviceN, extraer los nombres individuales.
    Los valores CMYK no se pueden separar fácilmente por tinta en DeviceN,
    así que se devuelven sin valores de color específicos.
    """
    m = re.search(r"/DeviceN\s*\[([^\]]*)\]", obj_str)
    if not m:
        return []

    names_raw = m.group(1)
    # Obtener nombres del array (cada /Nombre)
    results = []
    for raw_name in re.findall(r"/([^\s/\[\]<>(){}]+)", names_raw):
        color_name = _decode_pdf_name(raw_name)
        if color_name.lower() in (
            "none",
            "all",
            "cyan",
            "magenta",
            "yellow",
            "black",
            "red",
            "green",
            "blue",
        ):
            continue  # Ignorar canales de proceso en DeviceN mixto
        results.append(
            {
                "name": color_name,
                "alternate": "DeviceN",
                "cmyk": (0.0, 0.0, 0.0, 100.0),  # fallback
                "rgb": "#000000",
            }
        )
    return results


# ─────────────────────────────────────────────────────────────────────────────
# Función pública principal
# ─────────────────────────────────────────────────────────────────────────────


def extract_spot_colors(pdf_path: str, page_indices: list = None) -> list[dict]:
    """
    Extrae los colores spot (Separation/DeviceN) de las páginas indicadas de un PDF.

    Args:
        pdf_path:      Ruta absoluta al archivo PDF.
        page_indices:  Lista de índices de página (0-based). None = todas las páginas.

    Returns:
        Lista de dicts únicos (sin duplicados por nombre) con:
            - 'name' (str)   : nombre del color plano (p.ej. "PANTONE 485 C")
            - 'alternate' (str): 'CMYK' | 'RGB' | 'DeviceN' | 'Unknown'
            - 'cmyk' (tuple) : (C, M, Y, K) en 0-100 (valores alternativos)
            - 'rgb' (str)    : hex '#RRGGBB' aproximado del color

    Nota:
        Los valores CMYK son los del colorspace alternativo del PDF. El RIP
        puede ignorarlos si tiene la librería Pantone instalada y usará su
        propia definición del color.
    """
    result = []
    seen_names = set()

    try:
        doc = fitz.open(pdf_path)

        if page_indices is None:
            page_indices = list(range(len(doc)))

        # Recopilar todos los xrefs de objetos referenciados por las páginas indicadas
        # Estrategia: escanear todos los xrefs del documento (rápido en PDFs típicos)
        # y filtrar los que contienen /Separation o /DeviceN
        n_xrefs = doc.xref_length()

        for xref in range(1, n_xrefs):
            try:
                obj_str = doc.xref_object(xref, compressed=False)
                if not obj_str:
                    continue

                if "/Separation" in obj_str:
                    spot = _parse_separation_object(obj_str, doc=doc)
                    if spot and spot["name"] not in seen_names:
                        seen_names.add(spot["name"])
                        result.append(spot)

                elif "/DeviceN" in obj_str:
                    spots = _parse_devicen_object(obj_str)
                    for spot in spots:
                        if spot["name"] not in seen_names:
                            seen_names.add(spot["name"])
                            result.append(spot)

            except Exception:
                continue

        doc.close()

    except Exception as e:
        print(f"[SPOT_EXTRACTOR] Error al extraer colores spot de '{pdf_path}': {e}")

    # Ordenar por nombre para presentación consistente
    result.sort(key=lambda x: x["name"])

    for s in result:
        cmyk = s.get("cmyk")
        cmyk_str = (
            f"C={cmyk[0]:.0f} M={cmyk[1]:.0f} Y={cmyk[2]:.0f} K={cmyk[3]:.0f}"
            if cmyk
            else "sin valores"
        )
        print(
            f"[SPOT_EXTRACTOR]   · {s['name']}  ({s['alternate']})  CMYK: {cmyk_str}  RGB: {s.get('rgb','?')}"
        )
    print(f"[SPOT_EXTRACTOR] '{pdf_path}': {len(result)} color(es) spot encontrado(s)")

    return result


def extract_spot_colors_from_page(pdf_path: str, page_idx: int) -> list[dict]:
    """Wrapper para extraer spots de una sola página."""
    return extract_spot_colors(pdf_path, page_indices=[page_idx])
