"""Módulo de métricas tipográficas para PageNumber

Provee:
- FontMetricsCache: extrae y cachea métricas (usando PyMuPDF) por (font_path,font_size)
- TextAligner: utilidades para posicionar texto en Flet y PDF usando las métricas

Este módulo debe existir y ser importable por `PageNumber.ui.text_settings_dialog`
"""

_PRINT_DEBUG = False  # ← ACTIVADO para ver todos los prints de debug
if not _PRINT_DEBUG:

    def _no_print(*args, **kwargs):
        return None

    print = _no_print

from pathlib import Path
import os
import json

try:
    import fitz  # PyMuPDF
except Exception as e:
    fitz = None


class FontMetricsCache:
    """Cache de métricas de fuente.

    - Guarda en memoria durante la sesión y persiste en disco en `config/font_metrics/`.
    - Lanza errores claros si la fuente no existe o PyMuPDF no está disponible.
    """

    def __init__(self, cache_dir="config/font_metrics"):
        # Note: cache_dir is kept for compatibility but NOT used (all metrics stay in memory)
        self.cache_dir = Path(cache_dir)
        self.metrics = {}
        # cache en memoria para textos concretos: {(font_stem, size, text): metrics}
        self.text_metrics = {}

    def get_metrics(self, font_path: str, font_size: int, ttc_index: int = 0):
        key = f"{Path(font_path).stem}_{ttc_index}_{font_size}"
        print(
            f"[METRICS CACHE] get_metrics(font_path={font_path}, font_size={font_size}, ttc_index={ttc_index})"
        )
        print(f"  Key: {key}")
        if key in self.metrics:
            print(f"  ✓ Cache HIT - devolviendo métrica cacheada")
            cached = self.metrics[key]
            print(f"    cached['font_path']: {cached.get('font_path', 'N/A')}")
            print(
                f"    cached['baseline_to_top']: {cached.get('baseline_to_top', 'N/A')}"
            )
            return cached
        # Calculate and keep in memory only (no disk persistence)
        print(f"  ✗ Cache MISS - calculando nueva métrica...")
        data = self._calculate_metrics(font_path, font_size, ttc_index)
        print(f"  ✓ Métrica calculada, guardando en cache...")
        print(f"    data['font_path']: {data.get('font_path', 'N/A')}")
        print(f"    data['baseline_to_top']: {data.get('baseline_to_top', 'N/A')}")
        self.metrics[key] = data
        return data

    def _calculate_metrics(self, font_path: str, font_size: int, ttc_index: int = 0):
        if not fitz:
            raise RuntimeError(
                "PyMuPDF (fitz) no está disponible. Instala 'pymupdf' para habilitar extracción de métricas."
            )
        if not font_path or not Path(font_path).exists():
            raise FileNotFoundError(f"Archivo de fuente no encontrado: {font_path}")

        try:
            # PyMuPDF abre automáticamente la primera fuente en TTC/OTC
            font = fitz.Font(fontfile=font_path)
        except Exception as ex:
            raise RuntimeError(f"PyMuPDF no pudo abrir la fuente '{font_path}': {ex}")

        # IMPORTANTE: SIEMPRE EXTRAER A 12PT como referencia estándar
        # Las métricas se escalan proporcionalmente para otros tamaños usando ratio
        REFERENCE_FONT_SIZE = 12

        # Crear doc temporal con página grande
        test_text = "0"  # Solo medir el 0 para más precisión
        doc = fitz.open()
        page = doc.new_page(width=2000, height=2000)
        baseline_x, baseline_y = 100, 1000
        page.insert_text(
            (baseline_x, baseline_y),
            test_text,
            fontsize=REFERENCE_FONT_SIZE,
            fontfile=font_path,
        )
        text_data = page.get_text("dict")
        doc.close()

        bbox = None
        origin = None
        for block in text_data.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    if span.get("text") == test_text:
                        bbox = span.get("bbox")
                        origin = span.get("origin")
                        break
                if bbox:
                    break
            if bbox:
                break

        if bbox is None or origin is None:
            raise RuntimeError(
                "No se pudo extraer bbox/origin del texto de prueba; posible problema con PyMuPDF o la fuente."
            )

        # EXTRAER MÉTRICAS REALES DE LA FUENTE (Ascender/Descender)
        # Intentar obtener métricas robustas usando fontTools para coincidir con el renderizado del sistema (Flet/Skia)
        ascent_ratio = 0.8  # Fallback
        descent_ratio = -0.2  # Fallback

        try:
            from fontTools.ttLib import TTFont, TTCollection

            # Si es una colección TTC, cargar la cara específica
            if font_path.lower().endswith((".ttc", ".otc")):
                ttc = TTCollection(font_path)
                target_font = ttc[ttc_index]
            else:
                target_font = TTFont(font_path)

            upm = target_font["head"].unitsPerEm if "head" in target_font else 2048

            # Extraer métricas de diferentes tablas
            typo_asc = 0
            typo_desc = 0
            win_asc = 0
            win_desc = 0
            hhea_asc = 0
            hhea_desc = 0
            use_typo_metrics = False

            if "OS/2" in target_font:
                os2 = target_font["OS/2"]
                typo_asc = os2.sTypoAscender
                typo_desc = os2.sTypoDescender
                win_asc = os2.usWinAscent
                win_desc = os2.usWinDescent
                # Bit 7 de fsSelection: USE_TYPO_METRICS
                use_typo_metrics = bool(os2.fsSelection & 0x80)

            if "hhea" in target_font:
                hhea = target_font["hhea"]
                hhea_asc = hhea.ascent
                hhea_desc = hhea.descent

            # Selección de métricas para que coincidan con lo que Flutter/Skia
            # usa al calcular la posición del baseline dentro del widget.
            #
            # Regla universal (independiente de plataforma):
            #
            # 1. USE_TYPO_METRICS (bit 7 OS/2 fsSelection) activo → sTypoAscender/sTypoDescender.
            #    La fuente declara explícitamente que estos valores rigen el layout.
            #
            # 2. En cualquier otro caso → hhea.ascent / hhea.descent.
            #    Flutter (y los motores subyacentes: Core Text, DirectWrite, FreeType) usan hhea
            #    para calcular el line-box cuando USE_TYPO_METRICS no está activo.
            #    usWinAscent/usWinDescent se inflaron históricamente para evitar clipping en GDI
            #    antiguo de Windows y NO representan el baseline de layout real.
            #
            # No se usa max(win, hhea) porque infla el ascender en fuentes como Helvetica
            # donde win_asc >> hhea_asc, desplazando el texto varios milímetros.

            if use_typo_metrics:
                chosen_asc = typo_asc
                chosen_desc = typo_desc  # negativo
            else:
                # hhea es el estándar de layout real en todos los motores modernos
                chosen_asc = hhea_asc if hhea_asc != 0 else typo_asc
                chosen_desc = hhea_desc if hhea_desc != 0 else typo_desc  # negativo

            ascent_ratio = chosen_asc / upm
            descent_ratio = chosen_desc / upm

            print(f"  [fontTools] UPM: {upm}")
            print(
                f"  [fontTools] Win: {win_asc}/{win_desc}, Typo: {typo_asc}/{typo_desc}, Hhea: {hhea_asc}/{hhea_desc}"
            )
            print(f"  [fontTools] USE_TYPO_METRICS: {use_typo_metrics}")
            print(
                f"  [fontTools] Final Ratio: Ascent={ascent_ratio:.4f}, Descent={descent_ratio:.4f}"
            )

        except Exception as e:
            print(
                f"  [WARN] Error usando fontTools para métricas exactas: {e}. Usando PyMuPDF como fallback."
            )
            # Fallback a PyMuPDF (que suele devolver sTypo o hhea según el font_index)
            ascent_ratio = font.ascender
            descent_ratio = font.descender

        # Calcular valores en puntos para la referencia de 12pt
        # Nota: PyMuPDF descent suele ser negativo, lo convertimos a positivo para baseline_to_bottom
        baseline_to_top_font = ascent_ratio * REFERENCE_FONT_SIZE
        baseline_to_bottom_font = abs(descent_ratio * REFERENCE_FONT_SIZE)

        # También mantenemos la métrica del "0" para propósitos de centrado óptico si se prefiere
        x0, y0, x1, y1 = bbox
        origin_x, origin_y = origin

        baseline_to_top_digit = origin_y - y0
        baseline_to_bottom_digit = y1 - origin_y

        # --- CALCULO PRECISO DE LEFT BEARING VISUAL ---
        # PyMuPDF get_text("dict") a veces reporta bbox.x0 == origin.x incluso si hay bearing visual.
        # Renderizamos a un pixmap para medir la tinta real.
        try:
            # Zoom 4x para precisión (48pt efectivo si ref es 12pt)
            zoom = 4
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(
                matrix=mat,
                alpha=False,
                clip=fitz.Rect(
                    baseline_x - 10, baseline_y - 20, baseline_x + 50, baseline_y + 10
                ),
            )

            # El origen X en el pixmap (teniendo en cuenta el clip)
            # Clip x0 es baseline_x-10.
            # Pixmap coord x=0 corresponde a page coord x=baseline_x-10.
            # Origen del texto está en x=10 (relativo al pixmap).
            pix_origin_x_rel = 10 * zoom

            width = pix.width
            height = pix.height
            samples = pix.samples

            first_ink_x_rel = -1

            # Escanear columnas buscando tinta
            for x in range(width):
                has_ink = False
                for y in range(height):
                    offset = (y * width + x) * 3
                    if offset + 2 < len(samples) and samples[offset] < 255:  # Not white
                        has_ink = True
                        break
                if has_ink:
                    first_ink_x_rel = x
                    break

            if first_ink_x_rel != -1:
                # Distancia en píxeles del pixmap
                diff_px = first_ink_x_rel - pix_origin_x_rel
                # Convertir a puntos
                left_bearing = diff_px / zoom
            else:
                left_bearing = x0 - origin_x  # Fallback
        except Exception as e:
            # Error común de PyMuPDF con referencias nulas - usar fallback silenciosamente
            left_bearing = x0 - origin_x

        text_width = x1 - x0

        metrics = {
            "font_path": str(font_path),
            "font_size": REFERENCE_FONT_SIZE,  # SIEMPRE 12pt
            "baseline_to_top": baseline_to_top_font,  # Usar ascent real de fuente
            "baseline_to_bottom": baseline_to_bottom_font,  # Usar descent real de fuente
            "digit_0_to_top": baseline_to_top_digit,
            "digit_0_to_bottom": baseline_to_bottom_digit,
            "left_bearing": left_bearing,
            "width": text_width,
            "ascent_ratio": ascent_ratio if ascent_ratio else 0.8,
            "descent_ratio": (
                abs(descent_ratio) if descent_ratio else 0.2
            ),  # Ensure positive for height calc
            "method": "font_metrics_and_digit_0",
        }
        return metrics

    def measure_text(self, font_path: str, font_size: int, text: str):
        """Mide bbox/origin para `text` con la fuente y tamaño dados.

        Cachea resultados en memoria para evitar mediciones repetidas.
        Retorna un dict con las mismas claves que _calculate_metrics pero específicas para `text`.
        """
        key = (Path(font_path).stem, font_size, text)
        if key in self.text_metrics:
            return self.text_metrics[key]

        if not fitz:
            raise RuntimeError(
                "PyMuPDF (fitz) no está disponible. Instala 'pymupdf' para habilitar medición de texto."
            )

        doc = fitz.open()
        page = doc.new_page(width=400, height=220)
        baseline_x, baseline_y = 50, 120
        font_name = "F" + "".join(
            c for c in Path(font_path).stem if c.isalnum()
        )[:20] or "Fcustom"
        page.insert_text(
            (baseline_x, baseline_y),
            text,
            fontsize=font_size,
            fontfile=font_path,
            fontname=font_name,
        )
        text_data = page.get_text("dict")

        bbox = None
        origin = None
        for block in text_data.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    if span.get("text") == text:
                        bbox = span.get("bbox")
                        origin = span.get("origin")
                        break
                if bbox:
                    break
            if bbox:
                break

        doc.close()

        if bbox is None or origin is None:
            raise RuntimeError(
                f"No se pudo extraer bbox/origin para texto '{text}'; posible problema con PyMuPDF o la fuente."
            )

        x0, y0, x1, y1 = bbox
        origin_x, origin_y = origin

        baseline_to_top = origin_y - y0
        baseline_to_bottom = y1 - origin_y
        left_bearing = x0 - origin_x
        text_width = x1 - x0

        tm = {
            "font_path": str(font_path),
            "font_size": font_size,
            "baseline_to_top": baseline_to_top,
            "baseline_to_bottom": baseline_to_bottom,
            "left_bearing": left_bearing,
            "width": text_width,
            "method": "measured_text",
        }
        self.text_metrics[key] = tm
        return tm

        metrics = {
            "font_path": str(font_path),
            "font_size": font_size,
            "baseline_to_top": baseline_to_top,
            "baseline_to_bottom": baseline_to_bottom,
            "left_bearing": left_bearing,
            "width": text_width,
            "ascender": asc * font_size,
            "descender": -desc * font_size,
            "method": "measured",
        }
        return metrics


# Singleton de uso general dentro de la app
DEFAULT_FONT_METRICS = FontMetricsCache()


class TextAligner:
    def __init__(self, metrics_cache: FontMetricsCache):
        self.cache = metrics_cache

    def position_text_on_guides(
        self,
        text,
        font_path,
        font_size,
        guide_x,
        guide_y,
        offset_x=0,
        use_digits_only=True,
    ):
        metrics = self.cache.get_metrics(font_path, font_size)

        # Calcular ancho real del texto (preferir medición por PyMuPDF).
        # No confiar en el ancho guardado en cache para la cadena de prueba
        # porque en algunos entornos devuelve un valor invariantemente igual.
        try:
            f = fitz.Font(fontfile=font_path)
            text_width = f.text_length(text, fontsize=font_size)
        except Exception:
            # fallback: usar ancho cacheado si existe, sino aproximación
            text_width = (
                metrics.get("width")
                if metrics.get("width")
                else len(text) * font_size * 0.5
            )

        # Para la distancia desde baseline hasta la parte superior preferir el ascender
        # si está disponible (más consistente que bbox en algunos entornos).
        baseline_to_top = (
            metrics.get("ascender")
            if metrics.get("ascender")
            else metrics.get("baseline_to_top")
        )
        baseline_to_bottom = metrics.get("baseline_to_bottom")
        left_bearing = metrics.get("left_bearing", 0)

        # En Flet el `cv.Text` toma la coordenada Y como baseline, por tanto no restamos baseline_to_top.
        flet_top = guide_y - baseline_to_top
        flet_left = guide_x + offset_x + left_bearing

        if use_digits_only:
            flet_height = max(1, baseline_to_top)
        else:
            flet_height = baseline_to_top + baseline_to_bottom

        return {
            "left": flet_left,
            "top": flet_top,
            "width": text_width,
            "height": flet_height,
            "baseline_to_top": baseline_to_top,
            "metrics": metrics,
        }

    def insert_text_in_pdf(
        self, page, text, font_path, font_size, guide_x, guide_y, offset_x=0
    ):
        metrics = self.cache.get_metrics(font_path, font_size)
        pdf_x = guide_x + offset_x + metrics.get("left_bearing", 0)
        pdf_y = guide_y
        try:
            page.insert_text(
                (pdf_x, pdf_y), text, fontsize=font_size, fontfile=font_path
            )
        except Exception:
            page.insert_text((pdf_x, pdf_y), text, fontsize=font_size)


# =====================
# FUNCION CENTRAL DE CARGA DE METRICAS DE PERFILES
# =====================
def cargar_metricas_perfiles(
    perfiles, fuentes_sistema, font_metrics_cache, default_profile=None
):
    """
    Para cada perfil:
      - Si la fuente existe en fuentes_sistema, extrae la métrica y la añade como atributo 'metricas' al perfil.
      - Si no existe, cambia el perfil a default_profile y le asigna la métrica del default.
    Siempre lee y asigna la métrica al perfil <Default>.
    Prints claros y separados por secciones.
    Args:
        perfiles: lista de objetos perfil (deben tener font_family, font_style, font_size, name, id)
        fuentes_sistema: dict {family: [estilos]}
        font_metrics_cache: instancia de FontMetricsCache
        default_profile: perfil por defecto (si hay que hacer fallback)
    """


# =====================
# FUNCION CENTRAL DE CARGA DE METRICAS DE PERFILES
# =====================
def cargar_metricas_perfiles(
    perfiles, fuentes_sistema, font_metrics_cache, default_profile=None
):
    """
    Para cada perfil:
      - Si la fuente existe en fuentes_sistema, extrae la métrica y la añade como atributo 'metricas' al perfil.
      - Si no existe, cambia el perfil a default_profile y le asigna la métrica del default.
    Siempre lee y asigna la métrica al perfil <Default>.
    Prints claros y separados por secciones.
    Args:
        perfiles: lista de objetos perfil (deben tener font_family, font_style, font_size, name, id)
        fuentes_sistema: dict {family: [estilos]}
        font_metrics_cache: instancia de FontMetricsCache
        default_profile: perfil por defecto (si hay que hacer fallback)
    """
    print("\n==================== CARGANDO METRICAS DE PERFILES ====================")

    print("\n==================== CARGANDO METRICAS DE PERFILES ====================")
    print(f"Total perfiles a procesar: {len(perfiles)}")
    for i, perfil in enumerate(perfiles):
        print(
            f"  [{i}] {perfil.name} - {perfil.font_family} {perfil.font_style} {perfil.font_size}pt"
        )
    if not perfiles:
        print("[METRICAS] No hay perfiles para procesar")
        return

    # Primero aseguramos el perfil de fallback para métricas.
    # En trabajos guardados con solo post_data puede no existir <Default>.
    if default_profile is None:
        default_profile = next(
            (p for p in perfiles if getattr(p, "name", None) == "<Default>"), None
        )

    if default_profile is None:
        default_profile = perfiles[0]
        print(
            "[METRICAS] ⚠️ No existe perfil <Default>; se usa el primer perfil "
            f"'{getattr(default_profile, 'name', '?')}' como fallback"
        )
    try:
        default_path = getattr(default_profile, "resolved_font_path", None)
        default_ttc_index = getattr(default_profile, "resolved_font_index", 0)
        # Convertir objc.pyobjc_unicode a str si es necesario
        if default_path:
            default_path = str(default_path)
        print(
            f"[METRICAS] resolved_font_path para <Default>: {default_path} (ttc_index={default_ttc_index})"
        )
        if not default_path:
            # Si no hay resolved, intentar buscar por family/style (especialmente importante en Windows)
            print(
                f"[METRICAS] Buscando ruta de fuente para <Default>: {default_profile.font_family} {default_profile.font_style}"
            )
            try:
                from utils import font_index

                default_path, _ = font_index.find_font_file_for(
                    default_profile.font_family, default_profile.font_style
                )
                if default_path:
                    default_profile.resolved_font_path = default_path
                    print(
                        f"[METRICAS] Ruta resuelta dinámicamente para <Default>: {default_path}"
                    )
            except Exception as e:
                print(f"[METRICAS] Error al intentar resolver dinámicamente: {e}")

            if not default_path:
                raise RuntimeError(
                    "No se puede resolver la ruta de la fuente para <Default>"
                )

        default_metricas = font_metrics_cache.get_metrics(
            default_path, default_profile.font_size, default_ttc_index
        )
        default_profile.metricas = default_metricas
        print(
            f"[OK] Métrica cargada para <Default>: {default_profile.font_family} {default_profile.font_style} {default_profile.font_size}pt"
        )
    except Exception as ex:
        print(f"[ERROR] No se pudo cargar la métrica para <Default>: {ex}")
        default_profile.metricas = None

    for perfil in perfiles:
        # Saltar el default, ya está hecho
        if perfil is default_profile:
            continue
        fam = getattr(perfil, "font_family", None)
        estilo = getattr(perfil, "font_style", None)
        size = getattr(perfil, "font_size", None)
        # Comprobar si la familia y estilo existen
        # IMPORTANTE: NO modificar perfil.font_family/font_style permanentemente.
        # Solo intentar cargar métricas de la fuente resuelta, usar default como fallback temporal.
        try:
            font_path = getattr(perfil, "resolved_font_path", None)
            font_ttc_index = getattr(perfil, "resolved_font_index", 0)
            # Convertir objc.pyobjc_unicode a str si es necesario
            if font_path:
                font_path = str(font_path)
            if not font_path:
                # Si no hay ruta resuelta, usar métrica default sin modificar el perfil
                print(
                    f"[WARN] No hay ruta resuelta para perfil '{perfil.name}': {fam} {estilo}"
                )
                print(
                    f"[FALLBACK] Usando métrica de <Default> temporalmente (perfil NO modificado)"
                )
                perfil.metricas = default_profile.metricas
            else:
                # Cargar métrica de la fuente resuelta
                perfil.metricas = font_metrics_cache.get_metrics(
                    font_path, size, font_ttc_index
                )
                print(
                    f"[OK] Métrica cargada para perfil '{perfil.name}': {fam} {estilo} {size}pt"
                )
        except Exception as ex:
            print(
                f"[ERROR] Error cargando métrica para '{perfil.name}' ({fam} {estilo}): {ex}"
            )
            print(
                f"[FALLBACK] Usando métrica de <Default> temporalmente (perfil NO modificado)"
            )
            # Asignar métrica default como fallback TEMPORAL (no modificar font_family/font_style)
            perfil.metricas = default_profile.metricas
    print("\n==================== RESUMEN DE METRICAS ====================")
    for i, perfil in enumerate(perfiles):
        m = getattr(perfil, "metricas", None)
        print(f"\nPerfil {i}: {perfil.name}")
        print(f"  Font: {perfil.font_family} {perfil.font_style} {perfil.font_size}pt")
        print(f"  ID: {getattr(perfil, 'id', 'N/A')}")
        if m:
            print(f"  Status: ✓ métrica cargada")
            if isinstance(m, dict):
                print(f"    baseline_to_top: {m.get('baseline_to_top', 'N/A')}")
                print(f"    baseline_to_bottom: {m.get('baseline_to_bottom', 'N/A')}")
                print(f"    left_bearing: {m.get('left_bearing', 'N/A')}")
                print(f"    width: {m.get('width', 'N/A')}")
                print(f"    method: {m.get('method', 'N/A')}")
        else:
            print(f"  Status: ✗ SIN MÉTRICA")
    print("===========================================================\n")
