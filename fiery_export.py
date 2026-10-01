from datetime import datetime
from lang import t


# Silenciar prints de depuración en este módulo por defecto.
# Para activar, cambiar _PRINT_DEBUG = True durante desarrollo.
_PRINT_DEBUG = False
if not _PRINT_DEBUG:

    def _no_print(*args, **kwargs):
        return None

    print = _no_print


def generar_listas_fiery(ordenamiento_pdf):
    """
    Genera listas de páginas agrupadas por número de copia para configuración en Fiery.

    Args:
        ordenamiento_pdf (dict): Diccionario de ordenamiento PDF

    Returns:
        dict: Diccionario con listas por copia {1: [páginas], 2: [páginas], ...}
    """
    if not ordenamiento_pdf:
        # print("[DEBUG] generar_listas_fiery: ordenamiento_pdf está vacío")
        return {}

    # print(f"[DEBUG] generar_listas_fiery: procesando {len(ordenamiento_pdf)} elementos")

    # Agrupar páginas por numero_copia
    listas_fiery = {}

    for pagina, datos in ordenamiento_pdf.items():
        # Saltar metadata
        if pagina == "_metadata":
            # print(f"[DEBUG] generar_listas_fiery: saltando metadata")
            continue

        if not isinstance(datos, dict) or "numero_copia" not in datos:
            # print(f"[DEBUG] generar_listas_fiery: elemento inválido en página {pagina}: {datos}")
            continue

        numero_copia = datos["numero_copia"]
        # print(f"[DEBUG] generar_listas_fiery: página {pagina} -> copia {numero_copia}")

        if numero_copia not in listas_fiery:
            listas_fiery[numero_copia] = []

        listas_fiery[numero_copia].append(pagina)

    # Ordenar las páginas dentro de cada lista
    for copia in listas_fiery:
        listas_fiery[copia].sort()
        # print(f"[DEBUG] generar_listas_fiery: copia {copia} tiene {len(listas_fiery[copia])} páginas")

    return listas_fiery


def generar_archivo_fiery(listas_fiery, nombre_archivo):
    """
    Genera un archivo de texto con las listas de páginas para Fiery.

    Args:
        listas_fiery (dict): Diccionario con listas por copia
        nombre_archivo (str): Ruta del archivo a crear
    """
    try:
        with open(nombre_archivo, "w", encoding="utf-8") as file:
            # Escribir encabezado (con clave i18n)
            fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            file.write(t("Archivo Fiery - Generado el {0}").format(fecha) + "\n")
            file.write(t("Total de copias: {0}").format(len(listas_fiery)) + "\n\n")

            for copia, paginas in sorted(listas_fiery.items()):
                paginas_str = ",".join(map(str, paginas))
                file.write(
                    t("Copia {0} ({1} páginas)").format(copia, len(paginas)) + "\n"
                )
                file.write(paginas_str + "\n\n\n")

        # print(f"[SUCCESS] Archivo Fiery creado: {nombre_archivo}")
        return True
    except Exception as e:
        # print(f"[ERROR] No se pudo crear el archivo Fiery: {e}")
        return False


def generar_archivo_xerox_manual(listas_fiery, nombre_archivo):
    """
    Genera un archivo específico para copiar manualmente al Fiery/Xerox.
    Formato: Copia X: seguido de salto de línea y luego los números separados por comas.

    Args:
        listas_fiery (dict): Diccionario con listas por copia
        nombre_archivo (str): Ruta del archivo a crear

    Returns:
        bool: True si se creó exitosamente, False en caso contrario
    """
    try:
        # print(f"[DEBUG] Iniciando generación archivo Xerox manual: {nombre_archivo}")
        # print(f"[DEBUG] Listas recibidas: {len(listas_fiery)} copias")

        with open(nombre_archivo, "w", encoding="utf-8") as file:
            for copia, paginas in sorted(listas_fiery.items()):
                paginas_str = ",".join(map(str, paginas))
                # print(f"[DEBUG] Escribiendo Copia {copia}: {len(paginas)} páginas")
                file.write(t("Copia {0}:").format(copia) + "\n\n")
                file.write(paginas_str + "\n\n\n")

        # print(f"[SUCCESS] Archivo Xerox manual creado: {nombre_archivo}")
        return True
    except Exception as e:
        # print(f"[ERROR] No se pudo crear el archivo Xerox manual: {e}")
        return False


def mostrar_preview_fiery(listas_fiery):
    """
    Muestra un preview de cómo se verá el archivo de Fiery.
    """
    # print("\n=== PREVIEW ARCHIVO FIERY ===")
    for copia, paginas in sorted(listas_fiery.items()):
        paginas_str = ",".join(map(str, paginas))
        # print(f"Copia {copia}: {paginas_str}")
        # print()
    # print("=== FIN PREVIEW ===\n")


def generar_listas_xerox_para_pliegos(
    ordenamiento_pliegos, num_copias, modo_doble_cara=False
):
    """
    Genera listas de PLIEGOS agrupados por número de copia para máquinas Xerox/Fiery.

    En imposición, los pliegos se duplican por copias. Esta función agrupa los números
    de pliego del PDF final por cajón de papel (copia).

    Args:
        ordenamiento_pliegos (dict): Diccionario de pliegos con estructura:
            {pliego_num: {'datos': [...], 'numero_copia': N, 'doble_cara': 'cara/dorso'}}
        num_copias (int): Número total de copias a generar
        modo_doble_cara (bool): Si True, agrupa pares cara+dorso como unidad

    Returns:
        dict: Diccionario con listas de números de pliego por copia
        {1: [1,3,5,7], 2: [2,4,6,8], 3: [9,11,13], ...}

    Ejemplo UNA CARA (2 copias, 4 pliegos):
        - Pliego 1 copia 1 -> PDF página 1 -> Copia 1: [1]
        - Pliego 1 copia 2 -> PDF página 2 -> Copia 2: [2]
        - Pliego 2 copia 1 -> PDF página 3 -> Copia 1: [3]
        - Pliego 2 copia 2 -> PDF página 4 -> Copia 2: [4]
        Resultado: {1: [1,3,5,7], 2: [2,4,6,8]}

    Ejemplo DOBLE CARA (2 copias, 2 pares cara+dorso):
        - Par 1 (cara+dorso) copia 1 -> PDF páginas 1-2 -> Copia 1: [1,2]
        - Par 1 (cara+dorso) copia 2 -> PDF páginas 3-4 -> Copia 2: [3,4]
        - Par 2 (cara+dorso) copia 1 -> PDF páginas 5-6 -> Copia 1: [5,6]
        Resultado: {1: [1,2,5,6], 2: [3,4,7,8]}
    """
    if not ordenamiento_pliegos or num_copias <= 1:
        print("[DEBUG] generar_listas_xerox_para_pliegos: sin copias o dict vacío")
        return {}

    # Filtrar solo pliegos (claves numéricas), excluir metadata
    pliegos_ordenados = sorted(
        [k for k in ordenamiento_pliegos.keys() if isinstance(k, int)]
    )

    if not pliegos_ordenados:
        print(
            "[DEBUG] generar_listas_xerox_para_pliegos: no hay pliegos en ordenamiento"
        )
        return {}

    print(
        f"[DEBUG XEROX PLIEGOS] Total pliegos en ordenamiento: {len(pliegos_ordenados)}"
    )
    print(
        f"[DEBUG XEROX PLIEGOS] Copias: {num_copias}, Modo doble cara: {modo_doble_cara}"
    )

    listas_xerox = {}
    for i in range(1, num_copias + 1):
        listas_xerox[i] = []

    # Contador de página en el PDF final (secuencial 1, 2, 3, ...)
    pagina_pdf_actual = 1

    # Procesar pliegos
    idx = 0
    while idx < len(pliegos_ordenados):
        # Determinar cuántos pliegos forman un grupo
        grupo_pliegos = [pliegos_ordenados[idx]]

        # Si es doble cara y el siguiente es DORSO, agruparlos
        if modo_doble_cara and idx + 1 < len(pliegos_ordenados):
            siguiente_key = pliegos_ordenados[idx + 1]
            pliego_data = ordenamiento_pliegos.get(siguiente_key, {})
            if pliego_data.get("doble_cara", "cara").lower() == "dorso":
                grupo_pliegos.append(siguiente_key)
                idx += 2
            else:
                idx += 1
        else:
            idx += 1

        # Duplicar este grupo por cada copia
        for copia in range(1, num_copias + 1):
            # Agregar números de página del PDF para cada pliego del grupo
            for pliego_key in grupo_pliegos:
                listas_xerox[copia].append(pagina_pdf_actual)
                pagina_pdf_actual += 1

    # Log resultados
    for copia, paginas in sorted(listas_xerox.items()):
        print(
            f"[DEBUG XEROX PLIEGOS] Copia {copia}: {len(paginas)} páginas PDF -> {paginas[:5]}{'...' if len(paginas) > 5 else ''}"
        )

    return listas_xerox


def generar_archivo_xerox_para_pliegos(
    listas_xerox, nombre_archivo, modo_doble_cara=False
):
    """
    Genera archivo Xerox manual para PLIEGOS (imposición).
    Formato: Copia X: seguido de números de página del PDF separados por comas.

    Args:
        listas_xerox (dict): Diccionario con listas por copia {1: [1,3,5], 2: [2,4,6]}
        nombre_archivo (str): Ruta del archivo a crear
        modo_doble_cara (bool): Si True indica que es doble cara, False para una cara

    Returns:
        bool: True si se creó exitosamente, False en caso contrario
    """
    try:
        print(f"[DEBUG XEROX] Generando archivo para pliegos: {nombre_archivo}")
        print(f"[DEBUG XEROX] Total cajones (copias): {len(listas_xerox)}")
        print(f"[DEBUG XEROX] Modo: {'DOBLE CARA' if modo_doble_cara else 'UNA CARA'}")

        with open(nombre_archivo, "w", encoding="utf-8") as file:
            fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            file.write(t("Archivo Fiery - Generado el {0}").format(fecha) + "\n")
            modo_str = t("DOBLE CARA") if modo_doble_cara else t("UNA CARA")
            file.write(t("Modo: {0}").format(modo_str) + "\n")
            file.write(t("Cajones de papel: {0}").format(len(listas_xerox)) + "\n")
            file.write(
                t(
                    "Aplicar cada grupo de copias a su papel correspondiente en su cajón."
                )
                + "\n\n"
            )

            for copia, paginas_pdf in sorted(listas_xerox.items()):
                paginas_str = ",".join(map(str, paginas_pdf))
                file.write(t("Copia {0}:").format(copia) + "\n\n")
                file.write(paginas_str + "\n\n\n")

        print(f"[SUCCESS] Archivo Xerox para pliegos creado: {nombre_archivo}")
        return True
    except Exception as e:
        print(f"[ERROR] No se pudo crear archivo Xerox para pliegos: {e}")
        return False
