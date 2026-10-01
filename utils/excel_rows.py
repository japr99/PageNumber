def excel_row_index(start, end, increment, copies, reverse, phys_page, use_copy_grouping=True):
    """Índice de fila Excel (1-based) para una página lógica, aplicando 'Invertir orden'.

    Con reverse=True, la página 1 usa la última fila del rango y la última página
    la primera (misma fórmula que _calculate_number_for_numeradora / _calculate_number_for_page).
    """
    index_en_ciclo = (phys_page - 1) // copies if use_copy_grouping else (phys_page - 1)
    if reverse:
        index_en_ciclo = ((end - start) // increment) - index_en_ciclo
    return start + index_en_ciclo * increment - 1