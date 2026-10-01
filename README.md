# PageNumber

PageNumber es un software para numerar y crear códigos de barras con dato variable y texto variable en páginas a una cara o a doble cara diseñado para usar con TalNumStack o su software de imposición, su salida es en PDF.

## Ejecutar

```bash
.venv/bin/python page_number_app.py      # macOS
# .venv\Scripts\python page_number_app.py  # Windows
```

Usar SIEMPRE el venv del root. Python 3.14. Interfaz con Flet 1.0.1.

## Dependencias

```bash
pip install -r requirements.txt            # Windows
pip install -r requirements-mac.txt        # macOS (adds pyobjc)
```

## Licencia

AGPL-3.0 — GNU Affero General Public License versión 3. Ver el fichero `LICENSE` para el texto completo.

> **Aviso sobre PyMuPDF**: este proyecto usa [PyMuPDF](https://pymupdf.readthedocs.io/), que se distribuye bajo AGPL-3.0 **o** licencia comercial de Artifex. Al distribuir PageNumber bajo AGPL-3.0 se cumple la opción libre: si prefieres usarlo en un producto cerrado, necesitas una licencia comercial de Artifex.
