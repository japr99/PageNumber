"""
Archivo de conveniencia para el subpaquete PageNumber.
Se limita a reexportar el motor de i18n definido en el módulo raíz `lang`.
De esta manera cualquier módulo dentro de PageNumber puede hacer:

    from i18n import t, set_language

"""


# importar el módulo raíz `lang` (evitar copiar la variable LANG para que su
# valor refleje cambios en tiempo de ejecución). Reexportamos `t` y
# `set_language` y proporcionamos `get_lang()` para obtener el valor actual.
try:
    # Cuando se importa desde el paquete PageNumber
    import lang as _lang
except Exception:
    # Cuando se ejecuta como script directamente
    import lang as _lang

# Reexportar funciones útiles
t = _lang.t
set_language = _lang.set_language
I18N = _lang.I18N
get_language_options = _lang.get_language_options

def get_lang():
    """Devuelve el código de idioma actualmente seleccionado."""
    return _lang.LANG
