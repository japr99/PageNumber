"""
Gestor unificado de fuentes para Flet y PyMuPDF
Lee del registro del sistema, agrupa familias y prepara para ambos frameworks
Normaliza nombres de estilos y proporciona metadata completa
"""

_PRINT_DEBUG = False  # ← ACTIVADO para ver todos los prints de debug
if not _PRINT_DEBUG:

    def _no_print(*args, **kwargs):
        return None

    print = _no_print

import warnings

# Suprimir advertencias comunes de fontTools que no afectan la funcionalidad
warnings.filterwarnings("ignore", message=".*extra bytes in post.stringData.*")
warnings.filterwarnings("ignore", category=UserWarning, module="fontTools.*")

from fontTools.ttLib import TTFont, TTCollection
from collections import defaultdict
from typing import Dict, List, Optional, Tuple
import platform
import os
import json
import re
import hashlib
from pathlib import Path
from datetime import datetime

# Importaciones opcionales para evitar dependencias circulares
try:
    import flet as ft

    FLET_DISPONIBLE = True
except ImportError:
    FLET_DISPONIBLE = False
    ft = None

try:
    import fitz

    FITZ_DISPONIBLE = True
except ImportError:
    FITZ_DISPONIBLE = False
    fitz = None


class GestorFuentesCompleto:
    """
    Gestor unificado de fuentes para Flet y PyMuPDF
    Lee del registro del sistema, agrupa familias y prepara para ambos frameworks
    """

    # Nombre de carpeta de caché (se ubicará dentro del directorio de preferencias)
    CACHE_DIR_NAME = "font_cache"
    CACHE_FILE = "font_index.json"

    def __init__(self):
        self.fuentes: Dict[str, List[dict]] = defaultdict(
            list
        )  # {familia: [variantes]}
        self.mapeo_codigos = self._crear_mapeo_codigos()
        self.timestamp_carga = None
        self.platform = platform.system()
        self.extracted_map: Dict[str, str] = {}
        self._raw_font_family_count: int = 0

        # Resolver directorio de preferencias y ubicar caché allí
        # Usar el helper centralizado para directorios de caché
        try:
            from .font_cache import get_config_dir as _gcd, ensure_dirs

            self.CACHE_DIR = _gcd()
            ensure_dirs(self.CACHE_DIR)
        except Exception:
            # Fallback al directorio de trabajo si algo falla
            self.CACHE_DIR = Path("config") / self.CACHE_DIR_NAME
            self.CACHE_DIR.mkdir(parents=True, exist_ok=True)

        # Política opcional: permitir filtrar fuentes que no contienen glifos Latin
        # Esto puede activarse al llamar a `cargar_fuentes_desde_rutas(skip_non_latin=True)`
        self.skip_non_latin_default = False
        # Umbral mínimo de glifos Latin para considerar una fuente 'latin'
        self.min_latin_glyphs = 3
        # Proporción mínima de glifos Latin en cmap cuando OS/2 indica cobertura
        # (ej: 0.02 = 2%)
        self.min_latin_ratio = 0.02

    def _crear_mapeo_codigos(self) -> Dict[str, str]:
        """Diccionario de códigos abreviados a nombres completos"""
        return {
            # Pesos - ORDEN ALFABÉTICO para mejor lookup
            "B": "Bold",
            "BI": "Bold Italic",
            "Bd": "Bold",
            "BdIt": "Bold Italic",
            "Blk": "Black",
            "BlkIt": "Black Italic",
            "Bk": "Book",
            "BkIt": "Book Italic",
            "Bold": "Bold",
            "BoldIt": "Bold Italic",
            "Book": "Book",
            "DmBd": "Semibold",
            "ExBd": "Extra Bold",
            "ExBdIt": "Extra Bold Italic",
            "ExLt": "Extra Light",
            "ExLtIt": "Extra Light Italic",
            "Hairline": "Hairline",
            "Heavy": "Heavy",
            "HLt": "Hairline",
            "Hv": "Heavy",
            "HvIt": "Heavy Italic",
            "It": "Italic",
            "Italic": "Italic",
            "Light": "Light",
            "Lt": "Light",
            "LtIt": "Light Italic",
            "Md": "Medium",
            "MdIt": "Medium Italic",
            "Med": "Medium",
            "Medium": "Medium",
            "Obl": "Oblique",
            "Oblique": "Oblique",
            "Reg": "Regular",
            "Regular": "Regular",
            "Rg": "Regular",
            "RgIt": "Italic",
            "RegIt": "Italic",
            "Roman": "Regular",
            "SemiBd": "Semibold",
            "SemiBdIt": "Semibold Italic",
            "Semibold": "Semibold",
            "SmBd": "Semibold",
            "SmBdIt": "Semibold Italic",
            "Th": "Thin",
            "Thin": "Thin",
            "ThIt": "Thin Italic",
            "UBlk": "Ultra Black",
            "UltraBlk": "Ultra Black",
            "UltraLt": "Ultra Light",
            "ULt": "Ultra Light",
            "ULtIt": "Ultra Light Italic",
            "XBd": "Extra Bold",
            "XLt": "Extra Light",
            # Anchos
            "Cn": "Condensed",
            "Cond": "Condensed",
            "Condensed": "Condensed",
            "Ex": "Extended",
            "ExCn": "Extra Condensed",
            "Ext": "Extended",
            "Extd": "Extended",
            "Extended": "Extended",
            "Nar": "Narrow",
            "Narrow": "Narrow",
            "SemiCn": "Semi Condensed",
            "SmCn": "Semi Condensed",
            "UCn": "Ultra Condensed",
            "UltCn": "Ultra Condensed",
            "Wd": "Wide",
            "Wide": "Wide",
            "XCn": "Extra Condensed",
            # Combinaciones peso + ancho
            "CnBlk": "Condensed Black",
            "CnBd": "Condensed Bold",
            "CnBdIt": "Condensed Bold Italic",
            "CnIt": "Condensed Italic",
            "CnLt": "Condensed Light",
            "CnLtIt": "Condensed Light Italic",
            "CnMd": "Condensed Medium",
            "CnReg": "Condensed Regular",
            "CnRg": "Condensed Regular",
            # Abreviaturas Helvetica Neue específicas
            "Bd Cn": "Bold Condensed",
            "Bd Cn O": "Bold Condensed Oblique",
            "Bd Ex": "Bold Extended",
            "Bd Ex O": "Bold Extended Oblique",
            "Bd Ou": "Bold Outline",
            "Blk Cn": "Black Condensed",
            "Blk Cn O": "Black Condensed Oblique",
            "Blk Ex": "Black Extended",
            "Blk Ex O": "Black Extended Oblique",
            "Cn O": "Condensed Oblique",
            "Ex O": "Extended Oblique",
            "Hv Cn": "Heavy Condensed",
            "Hv Cn O": "Heavy Condensed Oblique",
            "Hv Ex": "Heavy Extended",
            "Hv Ex O": "Heavy Extended Oblique",
            "Lt Cn": "Light Condensed",
            "Lt Cn O": "Light Condensed Oblique",
            "Lt Ex": "Light Extended",
            "Lt Ex O": "Light Extended Oblique",
            "Md Cn": "Medium Condensed",
            "Md Cn O": "Medium Condensed Oblique",
            "Md Ex": "Medium Extended",
            "Md Ex O": "Medium Extended Oblique",
            "Th Cn": "Thin Condensed",
            "Th Cn O": "Thin Condensed Oblique",
            "Th Ex": "Thin Extended",
            "Th Ex O": "Thin Extended Oblique",
            "Ult Lt": "Ultra Light",
            "Ult Lt Cn": "Ultra Light Condensed",
            "Ult Lt Cn O": "Ultra Light Condensed Oblique",
            "Ult Lt Ex": "Ultra Light Extended",
            "Ult Lt Ex O": "Ultra Light Extended Oblique",
            "Ult Lt It": "Ultra Light Italic",
            "Xblk Cn": "Extra Black Condensed",
            "Xblk Cn O": "Extra Black Condensed Oblique",
        }

    def normalizar_codigo(self, codigo: str) -> str:
        """Convierte código abreviado a nombre completo"""
        if not codigo:
            return "Regular"

        # Buscar match exacto primero
        if codigo in self.mapeo_codigos:
            return self.mapeo_codigos[codigo]

        # Intentar con espacios en lugar de guiones
        codigo_espacios = codigo.replace("-", " ")
        if codigo_espacios in self.mapeo_codigos:
            return self.mapeo_codigos[codigo_espacios]

        # Devolver el código original si no hay match
        return codigo

    @staticmethod
    def _panose_to_weight(panose_weight: int) -> int:
        """Convierte PANOSE bWeight (byte 2) a usWeightClass numérico.

        PANOSE bWeight values:
        2 = Very Light (100-200)
        3 = Light (250-300)
        4 = Thin (300-350)
        5 = Book/Regular (400)
        6 = Medium (500-550)
        7 = Semibold (600)
        8 = Bold (700)
        9 = Heavy (800-850)
        10 = Black (900)
        11 = Extra Black (950)
        """
        weight_map = {
            2: 150,  # Very Light
            3: 300,  # Light
            4: 325,  # Thin
            5: 400,  # Book/Regular
            6: 500,  # Medium
            7: 600,  # Semibold
            8: 700,  # Bold
            9: 850,  # Heavy
            10: 900,  # Black
            11: 950,  # Extra Black
        }
        return weight_map.get(panose_weight, 400)

    @staticmethod
    def _validate_italic_majority(
        fs_selection_italic: bool,
        panose_italic: bool,
        post_angle_italic: bool,
        mac_style_italic: bool,
    ) -> bool:
        """Valida italic usando voto mayoritario de múltiples fuentes.

        Returns True si 2 o más fuentes indican italic.
        """
        votes = [
            fs_selection_italic,
            panose_italic,
            post_angle_italic,
            mac_style_italic,
        ]
        return sum(votes) >= 2

    def extraer_metadata_fuente(self, ruta: str) -> Optional[dict]:
        """
        Extrae toda la metadata de una fuente usando FontTools
        Retorna dict con info para Flet y PyMuPDF
        """
        try:
            # Manejar colecciones TTC/OTF
            is_collection = ruta.lower().endswith((".ttc", ".otc"))

            if is_collection:
                # Para colecciones, necesitamos procesar cada fuente
                return self._extraer_metadata_coleccion(ruta)
            else:
                return self._extraer_metadata_simple(ruta)

        except Exception as e:
            print(f"[GESTOR_FUENTES] Error procesando {ruta}: {e}")
            return None

    def _extraer_metadata_simple(self, ruta: str, ttc_index: int = 0) -> Optional[dict]:
        """Extrae metadata de una fuente simple (TTF/OTF) o un miembro de colección

        Filtra fuentes bitmap (no soportadas por PyMuPDF).
        """
        try:
            font = TTFont(ruta, fontNumber=ttc_index)

            # FILTRO: Detectar y rechazar fuentes bitmap (sin tablas glyf/CFF)
            # Estas fuentes no son soportadas por PyMuPDF/FreeType para métricas
            tiene_outlines = "glyf" in font or "CFF " in font or "CFF2" in font
            if not tiene_outlines:
                font.close()
                print(
                    f"[GESTOR_FUENTES] ⊗ Fuente bitmap ignorada (no soportada): {ruta}[{ttc_index}]"
                )
                return None

            # Inicializar valores
            familia = None
            subfamilia = None
            subfamilia_tipografica = None
            peso = 400
            italic = False
            ancho = 5  # Normal

            # Tabla name - Nombres EN INGLÉS
            name_table = font["name"]

            # Función auxiliar para obtener nombres en inglés
            def obtener_nombre_ingles(name_id):
                """
                Obtiene nombre priorizando inglés
                Prioridad:
                1. Windows Inglés US (platformID=3, langID=0x0409)
                2. Mac Inglés (platformID=1, langID=0)
                3. Windows Inglés UK (platformID=3, langID=0x0809)
                4. Cualquier plataforma no-CJK
                """
                candidatos = {}

                for record in name_table.names:
                    if record.nameID != name_id:
                        continue

                    try:
                        texto = record.toUnicode()
                    except (UnicodeDecodeError, UnicodeEncodeError, LookupError):
                        # Saltar registros con codificación problemática
                        continue

                    # Prioridad 1: Windows Inglés US
                    if record.platformID == 3 and record.langID == 0x0409:
                        return texto
                    # Prioridad 2: Mac Inglés
                    elif record.platformID == 1 and record.langID == 0:
                        candidatos["mac_en"] = texto
                    # Prioridad 3: Windows Inglés UK
                    elif record.platformID == 3 and record.langID == 0x0809:
                        candidatos["win_en_uk"] = texto
                    # Evitar CJK (Chino/Japonés/Coreano)
                    elif record.langID not in [0x0404, 0x0804, 0x0411, 0x0412]:
                        if "fallback" not in candidatos:
                            candidatos["fallback"] = texto

                return (
                    candidatos.get("mac_en")
                    or candidatos.get("win_en_uk")
                    or candidatos.get("fallback")
                )

            # Obtener nombres en inglés
            familia = obtener_nombre_ingles(16) or obtener_nombre_ingles(1)
            subfamilia_tipografica = obtener_nombre_ingles(17)
            subfamilia = obtener_nombre_ingles(2)

            # Filtrar fuentes de interfaz ocultas que comienzan con .
            # Solo si NO estamos siendo llamados desde _extraer_metadata_coleccion
            # (que ya hace el filtrado basado en CoreText en macOS)
            if familia and familia.startswith("."):
                # Verificar si no es una fuente registrada en CoreText
                import platform

                if platform.system() == "Darwin":
                    # En macOS, las fuentes con . generalmente son de interfaz y están ocultas
                    # Pero algunas SÍ están en CoreText, así que solo las filtramos si no están
                    # El filtrado real lo hace _extraer_metadata_coleccion consultando CoreText
                    pass
                else:
                    # En otros OS, filtrar fuentes que empiezan con .
                    font.close()
                    return None

            # Tabla OS/2 - Metadata técnica con validación PANOSE
            panose_data = None
            usWeightClass = 400
            usWidthClass = 5
            fs_selection_italic = False

            if "OS/2" in font:
                os2 = font["OS/2"]
                usWeightClass = os2.usWeightClass
                usWidthClass = os2.usWidthClass
                fs_selection_italic = bool(os2.fsSelection & 1)

                # Leer PANOSE (10 bytes)
                try:
                    panose = os2.panose
                    panose_data = {
                        "family_type": panose.bFamilyType,
                        "serif_style": panose.bSerifStyle,
                        "weight": panose.bWeight,
                        "proportion": panose.bProportion,
                        "contrast": panose.bContrast,
                        "stroke_variation": panose.bStrokeVariation,
                        "arm_style": panose.bArmStyle,
                        "letterform": panose.bLetterForm,
                        "midline": panose.bMidline,
                        "x_height": panose.bXHeight,
                        "raw": [
                            panose.bFamilyType,
                            panose.bSerifStyle,
                            panose.bWeight,
                            panose.bProportion,
                            panose.bContrast,
                            panose.bStrokeVariation,
                            panose.bArmStyle,
                            panose.bLetterForm,
                            panose.bMidline,
                            panose.bXHeight,
                        ],
                    }
                except Exception:
                    panose_data = None

            # Validación cruzada de peso con PANOSE
            if panose_data and panose_data["weight"] > 0:
                panose_weight = self._panose_to_weight(panose_data["weight"])
                # Si difieren más de 100 unidades, PANOSE es más confiable
                if abs(panose_weight - usWeightClass) > 100:
                    peso = panose_weight
                else:
                    peso = usWeightClass
            else:
                peso = usWeightClass

            # Validación cruzada de ancho con PANOSE
            # PANOSE bProportion 6,7 = Condensed; 5,9 = Extended
            ancho_final = usWidthClass
            ancho_category = "normal"  # 'condensed', 'extended', 'normal'

            if panose_data and panose_data["proportion"] in [6, 7]:  # Condensed
                ancho_category = "condensed"
                if usWidthClass > 3:  # Si OS/2 dice Normal pero PANOSE dice Condensed
                    ancho_final = 3
            elif panose_data and panose_data["proportion"] in [5, 9]:  # Extended
                ancho_category = "extended"
                if usWidthClass < 7:
                    ancho_final = 7
            else:
                # Usar usWidthClass sin modificar
                if usWidthClass <= 3:
                    ancho_category = "condensed"
                elif usWidthClass >= 7:
                    ancho_category = "extended"

            ancho = ancho_final

            # Tabla post - Ángulo itálica
            post_angle_italic = False
            if "post" in font:
                try:
                    angulo_italic = font["post"].italicAngle
                    post_angle_italic = angulo_italic != 0
                except Exception:
                    post_angle_italic = False

            # Tabla head - macStyle italic bit
            mac_style_italic = False
            if "head" in font:
                try:
                    mac_style_italic = bool(font["head"].macStyle & 2)
                except Exception:
                    mac_style_italic = False

            # PANOSE letterform (byte 7): 9 = italic/oblique, 2 = normal/upright
            panose_italic = False
            if panose_data and panose_data["letterform"] == 9:
                panose_italic = True

            # Voto mayoritario para italic
            italic = self._validate_italic_majority(
                fs_selection_italic, panose_italic, post_angle_italic, mac_style_italic
            )

            # Normalizar subfamilia
            subfamilia_final = subfamilia_tipografica or subfamilia or "Regular"

            # LIMPIEZA: eliminar prefijos "Condensed"/"Extended" de subfamilia cuando
            # ya están incluidos en familia_logica para evitar duplicación
            subfamilia_limpia = subfamilia_final
            if ancho_category == "condensed":
                # Eliminar "Condensed" del inicio de la subfamilia
                subfamilia_limpia = re.sub(
                    r"^Condensed\s*", "", subfamilia_final, flags=re.IGNORECASE
                ).strip()
                if not subfamilia_limpia:  # Si quedó vacío, usar Regular
                    subfamilia_limpia = "Regular"
            elif ancho_category == "extended":
                # Eliminar "Extended" del inicio de la subfamilia
                subfamilia_limpia = re.sub(
                    r"^Extended\s*", "", subfamilia_final, flags=re.IGNORECASE
                ).strip()
                if not subfamilia_limpia:
                    subfamilia_limpia = "Regular"

            subfamilia_normalizada = self.normalizar_codigo(subfamilia_limpia)

            # Generar nombre para PyMuPDF
            nombre_fitz = self._generar_nombre_fitz(familia, peso, italic, ancho)

            # Mapear peso a Flet
            peso_flet = self._peso_a_flet(peso)

            font.close()

            # Determinar familia lógica (separar Condensed/Extended)
            familia_logica = familia
            if ancho_category == "condensed":
                # Evitar duplicar "Condensed" si ya está en el nombre
                if "condensed" not in familia.lower():
                    familia_logica = f"{familia} Condensed"
            elif ancho_category == "extended":
                if "extended" not in familia.lower():
                    familia_logica = f"{familia} Extended"

            return {
                # Info general
                "familia": familia,
                "familia_logica": familia_logica,  # Nueva: para separar Condensed/Extended
                "subfamilia_original": subfamilia_final,
                "subfamilia": subfamilia_normalizada,
                "ruta": ruta,
                "ttc_index": ttc_index,
                "peso": peso,
                "italic": italic,
                "ancho": ancho,
                "ancho_category": ancho_category,  # 'normal', 'condensed', 'extended'
                "panose": panose_data,  # Metadata PANOSE completa
                # Para Flet
                "flet": {"font_family": familia, "weight": peso_flet, "italic": italic},
                # Para PyMuPDF
                "fitz": {"fontname": nombre_fitz, "fontfile": ruta},
            }

        except Exception as e:
            print(
                f"[GESTOR_FUENTES] Error procesando fuente simple {ruta}[{ttc_index}]: {e}"
            )
            return None

    def _extraer_metadata_coleccion(self, ruta: str) -> Optional[List[dict]]:
        """Extrae metadata de todas las fuentes en una colección TTC/OTC

        En macOS, solo extrae las fuentes que CoreText registra.
        En Windows/Linux, extrae todas las fuentes del TTC.
        """
        try:
            # Usar TTCollection para obtener el número correcto de fuentes
            ttc = TTCollection(ruta)
            num_fonts = len(ttc.fonts)
            ttc.close()

            resultados = []

            # Procesar cada fuente del TTC
            for i in range(num_fonts):
                info = self._extraer_metadata_simple(ruta, ttc_index=i)
                if not info:
                    continue

                familia = info["familia"]

                # Filtrar fuentes de interfaz ocultas (empiezan con .)
                if familia.startswith("."):
                    continue

                # En macOS, filtrar versiones legacy que no usa CoreText
                # Estas son versiones de compatibilidad incluidas en los TTC pero no registradas
                import platform

                if platform.system() == "Darwin":
                    # Patrones de fuentes legacy de macOS (Pro/ProN son versiones antiguas)
                    # macOS moderno usa versiones sin estos sufijos
                    legacy_patterns = [
                        ("Hiragino Kaku Gothic Pro", "Hiragino Sans"),  # Pro -> Sans
                        (
                            "Hiragino Mincho Pro",
                            "Hiragino Mincho ProN",
                        ),  # Pro -> ProN (en este caso ProN es la moderna)
                    ]

                    is_legacy = False
                    for legacy_name, modern_name in legacy_patterns:
                        if familia == legacy_name:
                            # Es una versión legacy, verificar si ya tenemos la moderna
                            if any(r["familia"] == modern_name for r in resultados):
                                # Ya tenemos la versión moderna, omitir legacy
                                is_legacy = True
                                break
                            # Si no hemos encontrado la moderna aún, marcar para verificar después
                            # Por ahora incluirla

                    if is_legacy:
                        continue

                resultados.append(info)

            # En macOS, hacer segunda pasada para eliminar legacy si encontramos la moderna
            import platform

            if platform.system() == "Darwin" and resultados:
                legacy_map = {
                    "Hiragino Kaku Gothic Pro": "Hiragino Sans",
                    "Hiragino Kaku Gothic ProN": "Hiragino Sans",
                    "Hiragino Kaku Gothic Std": "Hiragino Sans",
                    "Hiragino Kaku Gothic StdN": "Hiragino Sans",
                    "Hiragino Mincho Pro": "Hiragino Mincho ProN",
                    "Hiragino Maru Gothic Pro": "Hiragino Maru Gothic ProN",
                }

                # Construir set de familias modernas encontradas
                familias_modernas = {r["familia"] for r in resultados}

                # Filtrar legacy si existe la moderna
                resultados_finales = []
                for r in resultados:
                    familia = r["familia"]
                    if familia in legacy_map:
                        # Es legacy, verificar si existe la moderna
                        moderna = legacy_map[familia]
                        if moderna in familias_modernas:
                            # Omitir legacy
                            continue
                    resultados_finales.append(r)

                return resultados_finales if resultados_finales else None

            return resultados if resultados else None

        except Exception as e:
            # Si falla TTCollection, intentar como fuente simple
            return (
                [self._extraer_metadata_simple(ruta, 0)]
                if self._extraer_metadata_simple(ruta, 0)
                else None
            )

    def _peso_a_flet(self, peso: int):
        """Convierte peso numérico a formato Flet"""
        if not FLET_DISPONIBLE:
            # Retornar el peso como entero si flet no está disponible
            return peso

        mapeo = {
            100: ft.FontWeight.W_100,
            200: ft.FontWeight.W_200,
            300: ft.FontWeight.W_300,
            400: ft.FontWeight.W_400,
            500: ft.FontWeight.W_500,
            600: ft.FontWeight.W_600,
            700: ft.FontWeight.W_700,
            800: ft.FontWeight.W_800,
            900: ft.FontWeight.W_900,
        }

        # Redondear al múltiplo de 100 más cercano
        peso_redondeado = round(peso / 100) * 100
        peso_redondeado = max(100, min(900, peso_redondeado))

        return mapeo.get(peso_redondeado, ft.FontWeight.W_400)

    def _file_has_latin(self, ruta: str) -> bool:
        """
        FUNCIÓN DESACTIVADA - Siempre retorna True

        Razón: Con la implementación de validación PANOSE, ya no es necesario filtrar
        fuentes por script/idioma. El sistema PANOSE funciona correctamente con fuentes
        de cualquier script (Latin, CJK, árabe, cirílico, etc.).

        Filtrar fuentes no latinas era una optimización prematura que:
        1. Excluía fuentes válidas que el usuario podría necesitar
        2. Requería dependencias opcionales (langdetect) que no siempre están instaladas
        3. Añadía complejidad innecesaria ahora que PANOSE valida metadata correctamente

        El parámetro skip_non_latin se mantiene por compatibilidad pero no tiene efecto.

        CÓDIGO ORIGINAL COMENTADO ABAJO (conservado por referencia):
        """
        return True

        # ============================================================================
        # CÓDIGO DESACTIVADO - NO SE EJECUTA
        # ============================================================================
        # """
        # Comprueba si la fuente (o alguno de los miembros en un TTC) contiene mapas
        # de glifos para bloques Latin. Retorna True si detecta any código Latin.
        # """
        # try:
        #     from fontTools.ttLib import TTFont, TTCollection
        # except Exception:
        #     # Si fontTools no está disponible, no filtrar
        #     return True
        #
        # # Bits de ulUnicodeRange que indican cobertura Latin (OpenType)
        # LATIN_BITS = {0, 1, 2, 3, 57}
        #
        # def _os2_has_latin(tt) -> bool:
        #     try:
        #         if 'OS/2' not in tt:
        #             return False
        #         os2 = tt['OS/2']
        #         # Combinar los 4 campos ulUnicodeRange en un entero único
        #         r1 = getattr(os2, 'ulUnicodeRange1', 0) or 0
        #         r2 = getattr(os2, 'ulUnicodeRange2', 0) or 0
        #         r3 = getattr(os2, 'ulUnicodeRange3', 0) or 0
        #         r4 = getattr(os2, 'ulUnicodeRange4', 0) or 0
        #         mask = (r1 & 0xFFFFFFFF) | ((r2 & 0xFFFFFFFF) << 32) | ((r3 & 0xFFFFFFFF) << 64) | ((r4 & 0xFFFFFFFF) << 96)
        #         for b in LATIN_BITS:
        #             if mask & (1 << b):
        #                 return True
        #         return False
        #     except Exception:
        #         return False
        #
        # # Reusar la heurística por cmap como fallback (existente)
        # def _cmap_has_latin(tt):
        #     LATIN_RANGES = [
        #         (0x0000, 0x007F),   # Basic Latin
        #         (0x0080, 0x00FF),   # Latin-1 Supplement
        #         (0x0100, 0x017F),   # Latin Extended-A
        #         (0x0180, 0x024F),   # Latin Extended-B
        #         (0x1E00, 0x1EFF),   # Latin Extended Additional
        #     ]
        #
        #     try:
        #         cmap = tt.getBestCmap() or {}
        #     except Exception:
        #         try:
        #             tables = tt['cmap'].tables
        #             cmap_map = {}
        #             for t in tables:
        #                 if hasattr(t, 'cmap') and isinstance(t.cmap, dict):
        #                     cmap_map.update(t.cmap)
        #             cmap = cmap_map
        #         except Exception:
        #             cmap = {}
        #     if not cmap:
        #         return False
        #
        #     latin_letter_count = 0
        #     for codepoint in cmap.keys():
        #         if 0x0041 <= codepoint <= 0x005A or 0x0061 <= codepoint <= 0x007A:
        #             latin_letter_count += 1
        #         else:
        #             for a, b in LATIN_RANGES:
        #                 if a <= codepoint <= b:
        #                     try:
        #                         ch = chr(codepoint)
        #                         import unicodedata
        #                         if unicodedata.category(ch).startswith('L'):
        #                             latin_letter_count += 1
        #                             break
        #                     except Exception:
        #                         continue
        #
        #     if latin_letter_count >= getattr(self, 'min_latin_glyphs', 3):
        #         return True
        #
        #     # Fallback por heurística de nombre (langdetect opcional - DEPENDENCIA ELIMINADA)
        #     try:
        #         name_table = tt.get('name') if hasattr(tt, 'get') else None
        #         names = []
        #         if name_table is not None:
        #             for record in getattr(name_table, 'names', []):
        #                 try:
        #                     txt = record.toUnicode()
        #                 except Exception:
        #                     try:
        #                         txt = record.string.decode('utf-8', 'replace')
        #                     except Exception:
        #                         txt = ''
        #                 if txt:
        #                     names.append(txt)
        #         nm = ' '.join(names)
        #         if nm and len(nm) > 2:
        #             try:
        #                 from langdetect import detect  # ← Dependencia opcional ELIMINADA
        #                 lang = detect(nm)
        #                 LATIN_LANGS = {
        #                     'en','es','pt','fr','it','de','nl','sv','no','da','fi','is','tr','ro','hu','pl','cs','sk','sl','hr','bs','sr','lv','lt','et'
        #                 }
        #                 return lang in LATIN_LANGS
        #             except Exception:
        #                 pass
        #     except Exception:
        #         pass
        #
        #     return False
        #
        # def _count_latin_in_cmap(tt):
        #     try:
        #         cmap = tt.getBestCmap() or {}
        #     except Exception:
        #         try:
        #             tables = tt['cmap'].tables
        #             cmap_map = {}
        #             for t in tables:
        #                 if hasattr(t, 'cmap') and isinstance(t.cmap, dict):
        #                    cmap_map.update(t.cmap)
        #             cmap = cmap_map
        #         except Exception:
        #             cmap = {}
        #     total = len(cmap) if cmap else 0
        #     latin_count = 0
        #     if cmap:
        #         for codepoint in cmap.keys():
        #             if 0x0041 <= codepoint <= 0x005A or 0x0061 <= codepoint <= 0x007A:
        #                 latin_count += 1
        #             else:
        #                 for a, b in [(0x0000,0x007F),(0x0080,0x00FF),(0x0100,0x017F),(0x0180,0x024F),(0x1E00,0x1EFF)]:
        #                     if a <= codepoint <= b:
        #                         try:
        #                             import unicodedata
        #                             if unicodedata.category(chr(codepoint)).startswith('L'):
        #                                 latin_count += 1
        #                                 break
        #                         except Exception:
        #                             continue
        #     return latin_count, total
        #
        # path = str(ruta)
        # try:
        #     if path.lower().endswith(('.ttc', '.otc')):
        #         ttc = TTCollection(path, recalcBBoxes=False)
        #         try:
        #             for f in ttc.fonts:
        #                 # Si OS/2 indica Latin, comprobar proporción y conteo en cmap
        #                 if _os2_has_latin(f):
        #                     latin_count, total = _count_latin_in_cmap(f)
        #                     ratio = (latin_count / total) if total else 0.0
        #                     if latin_count >= getattr(self, 'min_latin_glyphs', 3) and ratio >= getattr(self, 'min_latin_ratio', 0.02):
        #                         return True
        #                     # Si no cumple proporción, no aceptamos solo por OS/2
        #                 # Como fallback, usar cmap heurística antigua
        #                 if _cmap_has_latin(f):
        #                     return True
        #             return False
        #         finally:
        #             try:
        #                 ttc.close()
        #             except Exception:
        #                 pass
        #     else:
        #         tt = TTFont(path, recalcBBoxes=False)
        #         try:
        #             if _os2_has_latin(tt):
        #                 latin_count, total = _count_latin_in_cmap(tt)
        #                 ratio = (latin_count / total) if total else 0.0
        #                 if latin_count >= getattr(self, 'min_latin_glyphs', 3) and ratio >= getattr(self, 'min_latin_ratio', 0.02):
        #                     return True
        #             return _cmap_has_latin(tt)
        #         finally:
        #             try:
        #                 tt.close()
        #             except Exception:
        #                 pass
        # except Exception:
        #     # En caso de error al leer la fuente, no filtrar por seguridad
        #     return True

    def _generar_nombre_fitz(
        self, familia: str, peso: int, italic: bool, ancho: int
    ) -> str:
        """Genera nombre único para PyMuPDF

        En macOS: usa formato con guiones (ej: TrebuchetMS-Bold-Italic)
        En Windows: usa formato con espacios (ej: Trebuchet MS Bold Italic)
        """
        import platform

        # SECCIÓN WINDOWS: usar nombres con espacios
        if platform.system() == "Windows":
            partes = [familia]  # Mantener espacios en el nombre de familia

            # Agregar ancho si no es normal
            if ancho <= 3:
                partes.append("Condensed")
            elif ancho >= 7:
                partes.append("Extended")

            # Agregar peso
            if peso <= 200:
                partes.append("Thin")
            elif peso <= 300:
                partes.append("Light")
            elif peso == 500:
                partes.append("Medium")
            elif peso == 600:
                partes.append("Semibold")
            elif peso >= 800:
                partes.append("Black")
            elif peso >= 700:
                partes.append("Bold")

            # Agregar italic
            if italic:
                partes.append("Italic")

            return " ".join(partes)

        # SECCIÓN MACOS: usar formato con guiones (código original)
        partes = [familia.replace(" ", "")]

        # Agregar ancho si no es normal
        if ancho <= 3:
            partes.append("Condensed")
        elif ancho >= 7:
            partes.append("Extended")

        # Agregar peso
        if peso <= 200:
            partes.append("Thin")
        elif peso <= 300:
            partes.append("Light")
        elif peso == 500:
            partes.append("Medium")
        elif peso == 600:
            partes.append("Semibold")
        elif peso >= 800:
            partes.append("Black")
        elif peso >= 700:
            partes.append("Bold")

        # Agregar italic
        if italic:
            partes.append("Italic")

        return "-".join(partes)

    def _generar_hash_rutas(self, rutas: List[str]) -> str:
        """Genera un hash de las rutas y timestamps para detectar cambios"""
        # Ordenar rutas para consistencia
        rutas_ordenadas = sorted(set(rutas))

        # Crear string con ruta:mtime para cada archivo
        info_rutas = []
        for ruta in rutas_ordenadas:
            try:
                if os.path.exists(ruta):
                    mtime = os.path.getmtime(ruta)
                    info_rutas.append(f"{ruta}:{mtime}")
            except Exception:
                continue

        # Hash del conjunto completo
        data = "\n".join(info_rutas).encode("utf-8")
        return hashlib.md5(data).hexdigest()

    def comparar_con_cache(self, cache_data: dict) -> dict:
        """Compara catálogo actual del sistema con cache para detectar cambios.

        Returns:
            Dict con claves 'nuevas', 'eliminadas', 'modificadas' conteniendo familias afectadas.
        """
        resultado = {"nuevas": [], "eliminadas": [], "modificadas": []}

        try:
            cache_familias = set(cache_data.get("fuentes", {}).keys())
            sistema_familias = set(self.fuentes.keys())

            # Familias nuevas
            resultado["nuevas"] = sorted(sistema_familias - cache_familias)

            # Familias eliminadas
            resultado["eliminadas"] = sorted(cache_familias - sistema_familias)

            # Familias modificadas (cambio en variantes)
            for familia in sistema_familias & cache_familias:
                sistema_variantes = self.obtener_variantes(familia)
                cache_variantes = cache_data.get("fuentes", {}).get(familia, [])

                # Comparar número y pesos de variantes
                sistema_pesos = sorted(
                    set((v["peso"], v["italic"]) for v in sistema_variantes)
                )
                cache_pesos = sorted(
                    set(
                        (v.get("peso", 400), v.get("italic", False))
                        for v in cache_variantes
                    )
                )

                if sistema_pesos != cache_pesos:
                    resultado["modificadas"].append(familia)

            return resultado
        except Exception as e:
            print(f"[GESTOR_FUENTES] Error comparando cache: {e}")
            return resultado

    def limpiar_huerfanos_extracted_map(self) -> int:
        """Limpia entradas huérfanas en extracted_map basándose en familias actuales.

        ELIMINA archivos físicos .ttf huérfanos de la carpeta extracted/.

        Retorna número de entradas eliminadas.
        """
        try:
            from . import font_cache
            import os
            from pathlib import Path

            # Construir set de rutas|índices válidos en el catálogo actual
            validos = set()
            for familia, peso_data in self.fuentes.items():
                for peso, italic_variants in peso_data.items():
                    for italic, variante in italic_variants.items():
                        ruta = variante.get("ruta")
                        idx = variante.get("ttc_index", 0)
                        if ruta:
                            key = f"{ruta}|{idx}"
                            validos.add(key)

            # Filtrar extracted_map y eliminar archivos físicos
            huerfanos = 0
            archivos_eliminados = 0
            bytes_liberados = 0
            nuevos_entries = {}

            for key, entry in self.extracted_map.items():
                if key in validos:
                    nuevos_entries[key] = entry
                else:
                    huerfanos += 1
                    # Eliminar archivo físico si existe
                    extracted_path = entry.get("extracted_path")
                    if extracted_path and os.path.exists(extracted_path):
                        try:
                            file_size = os.path.getsize(extracted_path)
                            os.remove(extracted_path)
                            archivos_eliminados += 1
                            bytes_liberados += file_size
                            print(
                                f"[CLEANUP] 🗑️  Eliminado: {Path(extracted_path).name} ({file_size / 1024:.1f} KB)"
                            )
                        except Exception as e:
                            print(
                                f"[CLEANUP] ⚠️  Error eliminando {extracted_path}: {e}"
                            )
                    else:
                        print(f"[CLEANUP] Huérfano (sin archivo físico): {key}")

            if huerfanos > 0:
                self.extracted_map = nuevos_entries
                # Guardar cache actualizada
                try:
                    self._guardar_cache([])
                    print(
                        f"[CLEANUP] ✓ Limpiados {huerfanos} huérfanos de extracted_map"
                    )
                    if archivos_eliminados > 0:
                        print(
                            f"[CLEANUP] ✓ {archivos_eliminados} archivos eliminados ({bytes_liberados / 1024:.1f} KB liberados)"
                        )
                except Exception as e:
                    print(f"[CLEANUP] ⚠️  Error guardando cache: {e}")

            return huerfanos
        except Exception as e:
            print(f"[CLEANUP] Error limpiando huérfanos: {e}")
            return 0

    def limpiar_carpetas_basura(self) -> dict:
        """Limpia archivos de respaldo antiguos (.bak, .corrupt) en font_cache.

        Ya NO se usan carpetas orphans/ o corrupt/ - los archivos se eliminan directamente.
        Esta función solo limpia backups antiguos del cache JSON.

        Retorna dict con estadísticas: {'archivos': int, 'bytes': int}
        """
        stats = {"archivos": 0, "bytes": 0}

        try:
            from . import font_cache
            from pathlib import Path
            from datetime import datetime, timedelta

            base_dir = font_cache.get_config_dir()  # Ya incluye /font_cache

            # Limpiar backups antiguos (más de 7 días)
            backup_extensions = [".bak.*", ".corrupt.*"]
            cutoff_time = (datetime.now() - timedelta(days=7)).timestamp()

            for pattern in backup_extensions:
                for backup in base_dir.glob(f"**/*{pattern}"):
                    if backup.is_file():
                        try:
                            if backup.stat().st_mtime < cutoff_time:
                                tamaño = backup.stat().st_size
                                backup.unlink()
                                stats["archivos"] += 1
                                stats["bytes"] += tamaño
                                print(f"[CLEANUP] Deleted old backup: {backup.name}")
                        except Exception as e:
                            print(f"[CLEANUP] Error deleting backup {backup.name}: {e}")

            return stats
        except Exception as e:
            print(f"[CLEANUP] Error limpiando backups: {e}")
            return stats

    def _guardar_cache(self, rutas: List[str]):
        """Guarda el índice de fuentes en caché"""
        try:
            from . import font_cache

            # Convertir estructura jerárquica a formato serializable
            # Y serializar objetos no-JSON (FontWeight)
            fuentes_serializables = {}
            # Intentar recuperar mapa previo de extracciones para marcar extracted_path
            try:
                prev_cache = font_cache.load_cache(self.CACHE_DIR) or {}
                extracted_map = prev_cache.get("extracted_map", {})
            except Exception:
                extracted_map = {}

            # Convertir de jerárquico a lista plana para serialización
            for familia, peso_data in self.fuentes.items():
                fuentes_serializables[familia] = []
                for peso, italic_variants in sorted(peso_data.items()):
                    for italic, variante in sorted(italic_variants.items()):
                        v_copy = dict(variante)
                        # Normalizar peso flet si es objeto
                        if "flet" in v_copy and "weight" in v_copy["flet"]:
                            weight_obj = v_copy["flet"]["weight"]
                            if hasattr(weight_obj, "value"):
                                v_copy["flet"]["weight"] = weight_obj.value

                        # Flags para extracción / compatibilidad con Flet
                        ruta = v_copy.get("ruta") or ""
                        ext = ruta.lower()
                        v_copy["requires_extraction"] = ext.endswith((".ttc", ".otc"))
                        v_copy["flet_compatible"] = ext.endswith((".ttf", ".otf")) and (
                            ruta and os.path.exists(ruta)
                        )

                        # If previously extracted mapping exists, attach it
                        key = f"{ruta}|{v_copy.get('ttc_index', '')}"
                        if key in extracted_map:
                            v_copy["extracted_path"] = extracted_map[key]

                        fuentes_serializables[familia].append(v_copy)

            cache_data = {
                "hash_rutas": self._generar_hash_rutas(rutas),
                "timestamp": datetime.now().isoformat(),
                "platform": self.platform,
                "num_familias": len(self.fuentes),
                "fuentes": fuentes_serializables,
                "extracted_map": self.extracted_map,
            }

            # Guardar de forma atómica usando font_cache helper
            font_cache.save_cache(self.CACHE_DIR, cache_data)
            print(f"[CACHE] ✓ Guardado índice de {len(self.fuentes)} familias")

        except Exception as e:
            print(f"[CACHE] Advertencia: No se pudo guardar caché: {e}")

    def _cargar_desde_cache(self) -> Optional[dict]:
        """Intenta cargar y validar la estructura básica del caché.

        Retorna el dict de caché si es válido (aunque las rutas hayan cambiado),
        o None si el archivo está corrupto o es de otra plataforma.
        """
        try:
            from . import font_cache

            # Validate extracted_map and normalize cache before using
            cache_data = font_cache.validate_extracted_map(self.CACHE_DIR)
            if not cache_data:
                return None

            # Verificar plataforma
            if cache_data.get("platform") != self.platform:
                print("[CACHE] Plataforma diferente, ignorando caché...")
                return None

            return cache_data

        except Exception as e:
            print(f"[CACHE] Error leyendo caché: {e}")
            return None

    def cargar_fuentes_desde_rutas(
        self,
        rutas_fuentes: List[str],
        usar_cache: bool = True,
        skip_non_latin: bool = False,
    ):
        """
        Procesa las fuentes de manera incremental usando caché.

        Args:
            rutas_fuentes: Lista de rutas de archivos de fuente del registro
            usar_cache: Si True, intenta usar caché en disco (por defecto True)
        """
        import time
        from datetime import datetime

        self.timestamp_carga = time.time()

        print(f"[GESTOR_FUENTES] Iniciando carga de {len(rutas_fuentes)} archivos...")

        # 1. Cargar caché previo
        cache_data = None
        if usar_cache:
            cache_data = self._cargar_desde_cache()

        # Preparar estructuras
        fuentes_temp = defaultdict(list)
        rutas_procesadas = set()  # Para evitar duplicados en la entrada

        # Mapa inverso de caché para búsqueda rápida: ruta -> [variantes]
        cache_por_ruta = defaultdict(list)
        cache_timestamp = 0
        extracted_map = {}

        if cache_data:
            # Recuperar timestamp del caché para validación
            try:
                ts_str = cache_data.get("timestamp")
                if ts_str:
                    cache_timestamp = datetime.fromisoformat(ts_str).timestamp()
            except Exception:
                cache_timestamp = 0

            # Recuperar extracted_map
            extracted_map = cache_data.get("extracted_map", {}) or {}
            self.extracted_map = extracted_map

            # Indexar caché por ruta
            fuentes_cargadas = cache_data.get("fuentes", {})
            for familia, variantes in fuentes_cargadas.items():
                for variante in variantes:
                    r = variante.get("ruta")
                    if r:
                        cache_por_ruta[r].append(variante)

        # 2. Procesar rutas (Incremental)
        reusados = 0
        nuevos = 0
        errores = 0

        for ruta in rutas_fuentes:
            if ruta in rutas_procesadas:
                continue
            rutas_procesadas.add(ruta)

            # Opción: omitir fuentes que no contienen Latin
            if skip_non_latin:
                try:
                    if not self._file_has_latin(ruta):
                        continue
                except Exception:
                    pass

            # Lógica Incremental:
            # Si la ruta está en caché y el archivo no se ha modificado DESPUÉS del caché
            # reutilizamos la info.
            reusar = False
            if ruta in cache_por_ruta:
                try:
                    if os.path.exists(ruta):
                        mtime = os.path.getmtime(ruta)
                        # Margen de 1s por precisión de timestamps
                        if mtime < (cache_timestamp - 1.0):
                            reusar = True
                except Exception:
                    pass

            if reusar:
                # REUSAR DEL CACHÉ
                variantes = cache_por_ruta[ruta]
                for v in variantes:
                    # Restaurar Weight object si es necesario (para Flet)
                    if "flet" in v and "weight" in v["flet"]:
                        w_val = v["flet"]["weight"]
                        if FLET_DISPONIBLE and isinstance(w_val, str):
                            v["flet"]["weight"] = self._peso_a_flet(v.get("peso", 400))

                    fam = v.get("familia_logica")
                    if fam and not fam.startswith("."):
                        fuentes_temp[fam].append(v)
                reusados += 1
            else:
                # PROCESAR NUEVO / MODIFICADO
                info = self.extraer_metadata_fuente(ruta)
                if info:
                    nuevos += 1
                    if isinstance(info, list):
                        for variante in info:
                            if variante and variante.get("familia_logica"):
                                fam = variante["familia_logica"]
                                if not fam.startswith("."):
                                    fuentes_temp[fam].append(variante)
                    elif isinstance(info, dict):
                        if info.get("familia_logica"):
                            fam = info["familia_logica"]
                            if not fam.startswith("."):
                                fuentes_temp[fam].append(info)

        print(
            f"[GESTOR_FUENTES] Resultado carga: {reusados} reusados, {nuevos} procesados/nuevos"
        )

        # 3. Convertir estructura plana a jerárquica
        # Antes se indexaba solo por (peso, italic) y se perdían variantes
        # distintas con la misma dupla (ej: Roman y Fractions).
        self.fuentes = {}
        for familia_logica, variantes_lista in fuentes_temp.items():
            self.fuentes[familia_logica] = {}
            for variante in variantes_lista:
                try:
                    peso = int(variante.get("peso", 400))
                except Exception:
                    peso = 400
                italic = bool(variante.get("italic", False))

                if peso not in self.fuentes[familia_logica]:
                    self.fuentes[familia_logica][peso] = {}

                if italic not in self.fuentes[familia_logica][peso]:
                    variante_ok = dict(variante)
                    variante_ok["peso"] = peso
                    self.fuentes[familia_logica][peso][italic] = variante_ok
                    continue

                # Si es exactamente la misma fuente (misma ruta + mismo índice TTC), ignorar duplicado.
                existente = self.fuentes[familia_logica][peso][italic]
                misma_fuente = (existente.get("ruta") == variante.get("ruta")) and (
                    int(existente.get("ttc_index", 0))
                    == int(variante.get("ttc_index", 0))
                )
                if misma_fuente:
                    continue

                # Colisión real: buscar siguiente peso libre para ese mismo italic.
                peso_colision = peso
                while True:
                    peso_colision += 1
                    if peso_colision not in self.fuentes[familia_logica]:
                        self.fuentes[familia_logica][peso_colision] = {}
                    if italic not in self.fuentes[familia_logica][peso_colision]:
                        variante_col = dict(variante)
                        variante_col["peso"] = peso_colision
                        self.fuentes[familia_logica][peso_colision][
                            italic
                        ] = variante_col
                        print(
                            "[GESTOR_FUENTES] Colisión resuelta en "
                            f"{familia_logica}: peso={peso} italic={italic} "
                            f"-> peso_alterno={peso_colision} "
                            f"({variante_col.get('subfamilia', 'Regular')})"
                        )
                        break

        print(f"[GESTOR_FUENTES] Total familias disponibles: {len(self.fuentes)}")

        cambios_cache = {
            "nuevas": [],
            "eliminadas": [],
            "modificadas": [],
        }
        if cache_data:
            try:
                cambios_cache = self.comparar_con_cache(cache_data)
            except Exception as e:
                print(
                    f"[GESTOR_FUENTES] Advertencia comparando catálogo actualizado con caché: {e}"
                )

        # 4. Limpieza y Guardado
        # Limpiar huérfanos en extracted_map (si ya no están en self.fuentes)
        try:
            huerfanos = self.limpiar_huerfanos_extracted_map()
            if huerfanos > 0:
                print(f"[GESTOR_FUENTES] ✓ Limpiados {huerfanos} registros huérfanos")
        except Exception as e:
            print(f"[GESTOR_FUENTES] Advertencia al limpiar huérfanos: {e}")

        cache_desactualizado = any(cambios_cache.values())
        if cache_desactualizado:
            print(
                "[GESTOR_FUENTES] Detectados cambios frente a la caché: "
                f"nuevas={len(cambios_cache['nuevas'])}, "
                f"eliminadas={len(cambios_cache['eliminadas'])}, "
                f"modificadas={len(cambios_cache['modificadas'])}"
            )

        # Guardar en caché actualizado
        if usar_cache and (nuevos > 0 or not cache_data or cache_desactualizado):
            self._guardar_cache(rutas_fuentes)
        elif usar_cache:
            print("[GESTOR_FUENTES] Caché al día, no se requiere guardar.")

        self._system_family_count = len(self.fuentes)
        return dict(self.fuentes)

    def sincronizar_con_catalogo_sistema(self, skip_non_latin: bool = True) -> dict:
        """Reconstruye el catálogo desde el sistema y lo sincroniza con la caché.

        Esta ruta siempre parte del índice actual del sistema (CoreText en macOS,
        registro en Windows, etc.) y luego deja que `cargar_fuentes_desde_rutas`
        reutilice la caché solo para los archivos que sigan vigentes.
        """
        try:
            from . import font_index as utils_font_index

            idx = utils_font_index.build_font_index()
            if self.platform == "Windows":
                self._raw_font_family_count = self._count_windows_font_files()
            else:
                self._raw_font_family_count = len(idx)
            rutas = []
            vistas = set()
            for entries in idx.values():
                if not isinstance(entries, list):
                    continue
                for entry in entries:
                    ruta = entry.get("path") if isinstance(entry, dict) else None
                    if ruta and ruta not in vistas:
                        rutas.append(ruta)
                        vistas.add(ruta)

            cache_prev = self._cargar_desde_cache() or {}
            self.cargar_fuentes_desde_rutas(
                rutas,
                usar_cache=True,
                skip_non_latin=skip_non_latin,
            )

            cambios = (
                self.comparar_con_cache(cache_prev)
                if cache_prev
                else {
                    "nuevas": sorted(self.fuentes.keys()),
                    "eliminadas": [],
                    "modificadas": [],
                }
            )

            print(
                "[GESTOR_FUENTES] Sincronización catálogo sistema completada: "
                f"rutas={len(rutas)}, familias={len(self.fuentes)}, "
                f"nuevas={len(cambios['nuevas'])}, "
                f"eliminadas={len(cambios['eliminadas'])}, "
                f"modificadas={len(cambios['modificadas'])}"
            )

            return {
                "rutas": rutas,
                "familias": len(self.fuentes),
                "cambios": cambios,
            }
        except Exception as e:
            print(f"[GESTOR_FUENTES] Error sincronizando catálogo del sistema: {e}")
            return {
                "rutas": [],
                "familias": len(self.fuentes),
                "cambios": {
                    "nuevas": [],
                    "eliminadas": [],
                    "modificadas": [],
                },
            }

    def _count_windows_font_files(self) -> int:
        """Cuenta archivos de fuentes registrados en Windows registry (rápido, sin parsear)."""
        import winreg

        count = 0
        for hive, subkey in [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Fonts"),
        ]:
            try:
                with winreg.OpenKey(hive, subkey) as key:
                    i = 0
                    while True:
                        try:
                            winreg.EnumValue(key, i)
                            count += 1
                            i += 1
                        except OSError:
                            break
            except OSError:
                pass
        return count

    def check_font_system_changed(self) -> bool:
        """Escaneo rápido: compara count de fuentes del sistema vs el conocido.
        En Windows usa el registry (rápido, sin parsear archivos).
        En macOS/Linux usa build_font_index() (CoreText/fc-list)."""
        try:
            if self.platform == "Windows":
                return self._count_windows_font_files() != getattr(
                    self, "_raw_font_family_count", -1
                )
            from . import font_index as utils_font_index

            idx = utils_font_index.build_font_index()
            return len(idx) != getattr(self, "_raw_font_family_count", -1)
        except Exception:
            return True

    def ensure_preferences_fonts(self):
        """Garantiza que las fuentes referenciadas en las preferencias estén extraídas
        en `fonts_prefs/` y actualiza las entradas de preferencias con `resolved_font_path`.
        """
        try:
            from . import font_cache
            from . import preferences

            prefs = preferences.load_preferences()
            profiles = prefs.get("text_style_profiles", [])
            if not profiles:
                return

            prefs_dir = font_cache.prefs_dir(self.CACHE_DIR)

            changed = False
            for perfil in profiles:
                fam = perfil.get("font_family")
                estilo = perfil.get("font_style")
                # Intentar encontrar variante en gestor
                # Primero buscar en familia_logica (puede ser "X Condensed" si el perfil guardado así lo indica)
                variante = None

                # Buscar en familia directa
                if fam in self.fuentes:
                    variante = self.buscar_por_estilo(fam, estilo)

                # Si no se encuentra, buscar case-insensitive en todas las familias
                if not variante:
                    for f in self.fuentes:
                        if f.lower() == (fam or "").lower():
                            variante = self.buscar_por_estilo(f, estilo)
                            break

                if not variante:
                    continue

                ruta = variante.get("ruta")
                ttc_index = variante.get("ttc_index", 0)

                key = f"{ruta}|{ttc_index}"
                out_path = None

                # Si ya hay extracted_path en variante o en extracted_map, usarlo
                if variante.get("extracted_path"):
                    out_path = variante.get("extracted_path")
                elif key in self.extracted_map:
                    entry = self.extracted_map.get(key)
                    if isinstance(entry, dict):
                        out_path = entry.get("extracted_path")
                    else:
                        out_path = entry

                # Si requiere extracción y no tenemos salida, generar en prefs_dir
                ext = (ruta or "").lower()
                requires = ext.endswith((".ttc", ".otc"))
                if requires and not out_path:
                    out = self.generar_instancia_estatica(
                        ruta,
                        ttc_index,
                        str(prefs_dir),
                        variante.get("familia") or fam,
                        variante.get("peso", 400),
                        variante.get("italic", False),
                    )
                    if out:
                        out_path = out
                        changed = True

                # Si tenemos out_path, actualizar perfil
                if out_path:
                    perfil["resolved_font_path"] = out_path
                    perfil["resolved_font_index"] = 0
                    changed = True

            if changed:
                try:
                    preferences.save_text_style_profiles(profiles)
                    # guardar cache actualizada
                    self._guardar_cache([])
                except Exception:
                    pass

        except Exception as e:
            print(f"[GESTOR_FUENTES] Error al asegurar fuentes de preferencias: {e}")

    def generar_instancia_estatica(
        self,
        ruta: str,
        ttc_index: int,
        dest_dir: str,
        familia: str,
        peso: int,
        italic: bool,
    ) -> Optional[str]:
        """Extrae un miembro TTC/OTC a TTF en `dest_dir` y actualiza extracted_map.

        Retorna la ruta al archivo extraído o None en error.
        """
        try:
            out_dir = Path(dest_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            # Nombre de salida
            safe_fam = familia.replace(" ", "")
            out_name = f"{safe_fam}_idx{ttc_index}_w{peso}{'_i' if italic else ''}.ttf"
            out_path = str(out_dir / out_name)

            # Usar extractor centralizado para colecciones TTC/OTC
            if ruta.lower().endswith((".ttc", ".otc")):
                try:
                    from . import font_ttc

                    ok = font_ttc.extract_subfont_to_file(ruta, ttc_index, out_path)
                    if not ok:
                        return None
                except Exception:
                    return None
            else:
                # No es colección: copiar archivo
                from shutil import copyfile

                copyfile(ruta, out_path)

            # Registrar en mapa con metadatos y persistir cache
            key = f"{ruta}|{ttc_index}"
            try:
                original_mtime = (
                    Path(ruta).stat().st_mtime if Path(ruta).exists() else None
                )
            except Exception:
                original_mtime = None
            try:
                import hashlib

                def _checksum(p):
                    h = hashlib.sha256()
                    with open(p, "rb") as fh:
                        for chunk in iter(lambda: fh.read(8192), b""):
                            h.update(chunk)
                    return h.hexdigest()

                original_checksum = _checksum(ruta) if Path(ruta).exists() else None
                extracted_checksum = _checksum(out_path)
            except Exception:
                original_checksum = None
                extracted_checksum = None

            entry = {
                "extracted_path": out_path,
                "original_path": ruta,
                "original_mtime": original_mtime,
                "original_checksum": original_checksum,
                "extracted_checksum": extracted_checksum,
                "timestamp": datetime.now().isoformat(),
                "stale": False,
            }

            self.extracted_map[key] = entry
            # Forzar guardado de cache para actualizar extracted_map
            try:
                self._guardar_cache(
                    rutas_fuentes if (rutas_fuentes := []) is not None else []
                )
            except Exception:
                # Fallback guardar simple
                try:
                    self._guardar_cache([])
                except Exception:
                    pass
            return out_path
        except Exception as e:
            print(f"[GESTOR_FUENTES] Error extrayendo instancia estática: {e}")
            return None

    def extraer_ttc_individual(self, font_path: str, ttc_index: int) -> Optional[Path]:
        """Extrae un miembro TTC a TTF individual para uso en Flet.

        Args:
            font_path: Ruta al archivo TTC/OTC
            ttc_index: Índice del miembro dentro del TTC

        Returns:
            Path al archivo extraído o None si falla
        """
        try:
            # Verificar si ya existe en extracted_map
            key = f"{font_path}|{ttc_index}"
            if key in self.extracted_map:
                entry = self.extracted_map[key]
                extracted_path = Path(entry.get("extracted_path", ""))
                if extracted_path.exists():
                    # Checksum del TTC ACTUAL vs el guardado: si la fuente en esta
                    # ruta cambió de contenido (mismo nombre, archivo distinto),
                    # re-extraer en vez de devolver la extracción antigua.
                    from . import font_cache

                    cur = font_cache.compute_checksum(Path(font_path))
                    old = entry.get("original_checksum")
                    if cur and old and cur == old:
                        return extracted_path
                    # checksum distinto o ausente → caer al re-extraído (sobrescribe entry)

            # No existe en caché, extraer
            # Primero obtener metadata para generar nombre apropiado
            metadata = self._extraer_metadata_simple(font_path, ttc_index)
            if not metadata:
                return None

            familia = metadata.get("familia", "Unknown")
            peso = metadata.get("peso", 400)
            italic = metadata.get("italic", False)

            # Directorio de destino
            dest_dir = str(self.CACHE_DIR / "extracted")

            # Llamar al método principal
            out_path_str = self.generar_instancia_estatica(
                font_path, ttc_index, dest_dir, familia, peso, italic
            )

            if out_path_str:
                return Path(out_path_str)
            return None

        except Exception as e:
            import logging

            logging.error(
                f"[GESTOR_FUENTES] Error en extraer_ttc_individual({font_path}, {ttc_index}): {e}",
                exc_info=True,
            )
            return None

    def obtener_familias(self) -> List[str]:
        """Retorna lista de nombres de familias disponibles ordenadas alfabéticamente (case-insensitive)"""
        return sorted(self.fuentes.keys(), key=str.lower)

    def generar_alias_flet(self, familia: str, peso: int, italic: bool) -> str:
        """Genera nombre de alias Flet único para un estilo específico.

        Formato: FamiliaBase-EstiloPeso
        Ejemplos:
            - AmericanTypewriter-Light
            - AmericanTypewriter-Bold
            - AmericanTypewriterCondensed-Light
        """
        # Limpiar nombre de familia
        familia_safe = familia.replace(" ", "")

        # Determinar sufijo de peso
        peso_map = {
            100: "Thin",
            200: "UltraLight",
            300: "Light",
            400: "Regular",
            500: "Medium",
            600: "Semibold",
            700: "Bold",
            800: "ExtraBold",
            900: "Black",
        }
        # Redondear peso al múltiplo de 100 más cercano
        peso_redondeado = round(peso / 100) * 100
        peso_redondeado = max(100, min(900, peso_redondeado))
        peso_nombre = peso_map.get(peso_redondeado, "Regular")

        # Construir alias
        if italic:
            if peso_nombre == "Regular":
                return f"{familia_safe}-Italic"
            else:
                return f"{familia_safe}-{peso_nombre}Italic"
        else:
            return f"{familia_safe}-{peso_nombre}"

    def obtener_mapeo_flet_fonts(
        self, solo_extraidos: bool = False, auto_extract: bool = True
    ) -> Dict[str, str]:
        """Genera mapeo completo {alias_flet: ruta_archivo} para page.fonts.

        Args:
            solo_extraidos: Si True, solo incluye fuentes TTC ya extraídas (ignora TTCs no procesados).
                           Si False, incluye todas las fuentes disponibles.
            auto_extract: Si True, extrae automáticamente fuentes TTC que aún no han sido procesadas.
                         Si False, solo incluye fuentes ya extraídas previamente.

        Returns:
            Diccionario listo para asignar a page.fonts
        """
        mapeo = {}

        # Determinar directorio de extracción
        try:
            from . import font_cache

            extract_dir = font_cache.extract_dir(self.CACHE_DIR)
        except Exception:
            extract_dir = self.CACHE_DIR / "extracted"
            extract_dir.mkdir(parents=True, exist_ok=True)

        for familia, peso_data in self.fuentes.items():
            for peso, italic_variants in peso_data.items():
                for italic, variante in italic_variants.items():
                    ruta = variante.get("ruta")
                    ttc_index = variante.get("ttc_index", 0)

                    # Determinar ruta final
                    ruta_final = None

                    # Si es TTC, buscar en extracted_map o extraer
                    if ruta and ruta.lower().endswith((".ttc", ".otc")):
                        key = f"{ruta}|{ttc_index}"

                        # Verificar si ya está extraído
                        if key in self.extracted_map:
                            entry = self.extracted_map.get(key)
                            if isinstance(entry, dict):
                                ruta_final = entry.get("extracted_path")
                            else:
                                ruta_final = entry

                        # Si no está extraído y auto_extract está activado, extraer ahora
                        if not ruta_final and auto_extract:
                            ruta_final = self.generar_instancia_estatica(
                                ruta,
                                ttc_index,
                                str(extract_dir),
                                variante.get("familia", familia),
                                peso,
                                italic,
                            )

                        # Si solo_extraidos y no está extraído, omitir
                        if solo_extraidos and not ruta_final:
                            continue
                    else:
                        # TTF/OTF directo
                        ruta_final = ruta

                    if ruta_final and os.path.exists(ruta_final):
                        alias = self.generar_alias_flet(familia, peso, italic)
                        mapeo[alias] = ruta_final

        return mapeo

    def obtener_variantes(self, familia: str) -> List[dict]:
        """Retorna todas las variantes de una familia (compatibilidad con estructura anterior)"""
        if familia not in self.fuentes:
            return []

        # Convertir estructura jerárquica a lista plana
        variantes = []
        for peso, italic_variants in sorted(self.fuentes[familia].items()):
            for italic, info in sorted(italic_variants.items()):
                variantes.append(info)
        return variantes

    def obtener_estilos(self, familia: str) -> List[str]:
        """Retorna lista de nombres de estilos disponibles para una familia"""
        variantes = self.obtener_variantes(familia)
        return [v["subfamilia"] for v in variantes]

    def limpiar_cache(self):
        """Elimina el archivo de caché para forzar recarga completa"""
        try:
            cache_path = self.CACHE_DIR / self.CACHE_FILE
            if cache_path.exists():
                cache_path.unlink()
                print("[CACHE] ✓ Caché eliminada")
            else:
                print("[CACHE] No hay caché para eliminar")
        except Exception as e:
            print(f"[CACHE] Error eliminando caché: {e}")

    def buscar_variante(
        self, familia: str, peso: int = 400, italic: bool = False
    ) -> Optional[dict]:
        """
        Busca la variante más cercana a los parámetros dados

        Returns:
            Dict con info de la fuente, o None si no existe la familia
        """
        if familia not in self.fuentes:
            return None

        familia_data = self.fuentes[familia]

        if not familia_data:
            return None

        # Buscar match exacto de peso+italic
        if peso in familia_data and italic in familia_data[peso]:
            return familia_data[peso][italic]

        # Buscar peso exacto con italic diferente
        if peso in familia_data:
            # Preferir mismo peso aunque italic difiera
            if False in familia_data[peso]:
                return familia_data[peso][False]
            if True in familia_data[peso]:
                return familia_data[peso][True]

        # Buscar peso más cercano
        pesos_disponibles = sorted(familia_data.keys())
        peso_cercano = min(pesos_disponibles, key=lambda p: abs(p - peso))

        # Preferir italic correcto en el peso cercano
        if italic in familia_data[peso_cercano]:
            return familia_data[peso_cercano][italic]

        # Retornar cualquier variante del peso cercano
        italic_variants = familia_data[peso_cercano]
        return next(iter(italic_variants.values()))

    def buscar_por_estilo(self, familia: str, estilo: str) -> Optional[dict]:
        """
        Busca una variante por familia y nombre de estilo

        Args:
            familia: Nombre de la familia de fuente
            estilo: Nombre del estilo (ej: "Bold", "Regular", "Light Italic")

        Returns:
            Dict con info de la fuente, o None si no se encuentra
        """
        if familia not in self.fuentes:
            return None

        # Buscar en todas las variantes
        for peso_data in self.fuentes[familia].values():
            for variante in peso_data.values():
                # Match exacto
                if variante.get("subfamilia") == estilo:
                    return variante

        # Buscar match case-insensitive
        estilo_lower = estilo.lower()
        for peso_data in self.fuentes[familia].values():
            for variante in peso_data.values():
                if variante.get("subfamilia", "").lower() == estilo_lower:
                    return variante

        # No encontrado
        return None

    def para_flet(
        self, familia: str, peso: int = 400, italic: bool = False
    ) -> Optional[dict]:
        """
        Obtiene parámetros para usar en Flet

        Returns:
            Dict con font_family, weight, italic o None
        """
        variante = self.buscar_variante(familia, peso, italic)
        return variante["flet"] if variante else None

    def para_pymupdf(
        self, familia: str, peso: int = 400, italic: bool = False
    ) -> Optional[dict]:
        """
        Obtiene parámetros para usar en PyMuPDF

        Returns:
            Dict con fontname, fontfile o None
        """
        variante = self.buscar_variante(familia, peso, italic)
        return variante["fitz"] if variante else None

    def necesita_recarga(self) -> bool:
        """
        Verifica si han pasado X segundos desde última carga
        Para evitar recargas innecesarias.

        Nota: CoreText sync ya detecta cambios reales en el sistema,
        este timeout es solo una capa adicional de seguridad.
        """
        if not self.timestamp_carga:
            return True

        import time

        segundos_desde_carga = time.time() - self.timestamp_carga
        return (
            segundos_desde_carga > 300
        )  # 5 minutos (CoreText sync ya detecta cambios)

    def recargar(self, rutas_fuentes: List[str]):
        """Recarga fuentes de forma segura"""
        print("[GESTOR_FUENTES] Recargando fuentes del sistema...")
        self.fuentes.clear()  # Limpiar cache
        self.cargar_fuentes_desde_rutas(rutas_fuentes)
        print(f"[GESTOR_FUENTES] Recarga completa: {len(self.fuentes)} familias")

    def resumen(self):
        """Imprime resumen de fuentes cargadas"""
        print(f"\n{'='*60}")
        print(f"FUENTES CARGADAS: {len(self.fuentes)} familias lógicas")
        print(f"Plataforma: {self.platform}")
        print(f"{'='*60}\n")

        for familia in sorted(self.fuentes.keys()):
            variantes = self.obtener_variantes(familia)
            print(f"{familia}: {len(variantes)} variantes")
            for v in variantes[:10]:  # Limitar a 10 para no saturar
                panose_info = ""
                if v.get("panose"):
                    pw = v["panose"].get("weight", 0)
                    panose_info = f" [PANOSE w:{pw}]"
                print(
                    f"  - {v['subfamilia']:30} (peso: {v['peso']}, italic: {v['italic']}, ancho: {v.get('ancho_category', 'normal')}){panose_info}"
                )
            if len(variantes) > 10:
                print(f"  ... y {len(variantes) - 10} más")
            print()

    def obtener_familias_con_info(self) -> Dict[str, List[str]]:
        """
        Retorna diccionario {familia: [estilos]} con toda la info
        Compatible con el formato usado por font_index
        """
        resultado = {}
        for familia, peso_data in self.fuentes.items():
            resultado[familia] = []
            for peso, italic_variants in sorted(peso_data.items()):
                for italic, variante in sorted(italic_variants.items()):
                    resultado[familia].append(variante.get("subfamilia", "Regular"))
        return resultado


# ============================================================================
# FUNCIONES DE UTILIDAD PARA INTEGRACIÓN
# ============================================================================

# Instancia global (singleton)
_gestor_global: Optional[GestorFuentesCompleto] = None


def obtener_gestor() -> GestorFuentesCompleto:
    """
    Obtiene la instancia global del gestor de fuentes.
    Si no está inicializado, lo carga automáticamente.
    """
    global _gestor_global
    if _gestor_global is None:
        _gestor_global = GestorFuentesCompleto()

        # Auto-cargar fuentes del sistema si no está cargado
        if not _gestor_global.fuentes:
            try:
                # Antes de cargar, limpiar caché persistente de prefs si existen extracciones
                from . import font_cache

                prefs_files = font_cache.list_prefs_files(_gestor_global.CACHE_DIR)
                if prefs_files:
                    print(
                        "[GESTOR_FUENTES] Detectadas fuentes extraídas en prefs: validando integridad (no se borrará font_cache persistente)..."
                    )
                    result = font_cache.cleanup_prefs_cache(_gestor_global.CACHE_DIR)
                    # Mostrar resumen no destructivo
                    try:
                        em = (
                            result.get("extracted_map", {})
                            if isinstance(result, dict)
                            else {}
                        )
                        print(
                            f"[GESTOR_FUENTES] font_cache preservado. Entradas validadas en extracted_map: {len(em)}"
                        )
                    except Exception:
                        print(
                            "[GESTOR_FUENTES] font_cache preservado (no se pudo leer resumen)"
                        )

                import utils.font_index as utils_font_index

                import utils.font_index as utils_font_index

                # Obtener el índice de fuentes
                font_index = utils_font_index.build_font_index()

                # Extraer rutas únicas del font_index
                rutas_set = set()
                for familia, entries in font_index.items():
                    if isinstance(entries, list):
                        for entry in entries:
                            if isinstance(entry, dict) and entry.get("path"):
                                rutas_set.add(entry["path"])

                rutas = list(rutas_set)

                # Cargar fuentes
                # Al arrancar, omitir fuentes que no provean glifos Latin para ahorrar trabajo
                try:
                    _gestor_global.cargar_fuentes_desde_rutas(
                        rutas, skip_non_latin=True
                    )
                except TypeError:
                    # Compatibilidad: si la firma antigua no acepta skip_non_latin
                    _gestor_global.cargar_fuentes_desde_rutas(rutas)
                # Después de cargar, asegurar que las fuentes referenciadas en preferencias
                # estén extraídas y registradas en prefs
                try:
                    _gestor_global.ensure_preferences_fonts()
                except Exception:
                    pass

            except Exception as e:
                print(
                    f"[GESTOR_FUENTES] Advertencia: No se pudieron cargar fuentes del sistema: {e}"
                )

    return _gestor_global


def get_default_font_family() -> str:
    """Retorna la familia de fuente por defecto según la plataforma"""
    import platform

    if platform.system() == "Windows":
        return "Arial"
    return "Helvetica"


def inicializar_gestor(rutas_fuentes: List[str], forzar: bool = False):
    """
    Inicializa el gestor global con las rutas de fuentes

    Args:
        rutas_fuentes: Lista de rutas de archivos de fuentes
        forzar: Si True, recarga aunque ya esté inicializado
    """
    gestor = obtener_gestor()

    if forzar or not gestor.fuentes:
        gestor.cargar_fuentes_desde_rutas(rutas_fuentes)

    return gestor


if __name__ == "__main__":
    """Prueba del gestor de fuentes"""
    import sys

    # Cargar fuentes del sistema usando font_index
    try:
        from . import font_index_wrapper as font_index

        print("Obteniendo rutas de fuentes del sistema...")

        if platform.system() == "Darwin":
            # macOS
            idx = font_index.enumerate_fonts_macos()
            rutas = []
            for familia, entries in idx.items():
                for entry in entries:
                    if entry.get("path"):
                        rutas.append(entry["path"])
        elif platform.system() == "Windows":
            rutas = font_index.iter_windows_font_files()
        else:
            idx = font_index.enumerate_fonts_linux()
            rutas = []
            for familia, entries in idx.items():
                for entry in entries:
                    if entry.get("path"):
                        rutas.append(entry["path"])

        # Eliminar duplicados
        rutas = list(set(rutas))

        print(f"Encontradas {len(rutas)} rutas únicas de fuentes")

        # Crear gestor y cargar
        gestor = GestorFuentesCompleto()
        gestor.cargar_fuentes_desde_rutas(rutas)

        # Mostrar resumen
        gestor.resumen()

        # Probar búsqueda de Helvetica Neue
        print("\n" + "=" * 60)
        print("PRUEBA: Helvetica Neue")
        print("=" * 60)
        if "Helvetica Neue" in gestor.fuentes:
            variantes = gestor.obtener_variantes("Helvetica Neue")
            print(f"Encontradas {len(variantes)} variantes:")
            for v in variantes:
                print(f"  {v['subfamilia']:30} | Orig: {v['subfamilia_original']}")

    except ImportError as e:
        print(f"Error: No se pudo importar font_index: {e}")
        print("Ejecuta desde el directorio raíz: python -m gestor_fuentes")
