"""
Gestor de datos Excel compartido para toda la aplicación.
Carga única con pandas, acceso por columnas.
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional, Tuple

import pandas as pd


class ExcelManager:
    """Singleton que gestiona la carga y acceso a datos Excel.

    Solo una hoja (la primera) se carga. El archivo se mantiene
    en memoria para acceso rápido.
    """

    _instance: Optional[ExcelManager] = None
    _initialized: bool = False

    def __new__(cls) -> ExcelManager:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        self._df: Optional[pd.DataFrame] = None
        self._filepath: Optional[str] = None
        self._columns: List[str] = []

    @property
    def is_loaded(self) -> bool:
        return self._df is not None

    @property
    def filepath(self) -> Optional[str]:
        return self._filepath

    @property
    def columns(self) -> List[str]:
        return list(self._columns)

    @property
    def row_count(self) -> int:
        if self._df is None:
            return 0
        return len(self._df)

    def load(self, filepath: str) -> Tuple[bool, str]:
        """Load an Excel file. Returns (success, message)."""
        if not os.path.isfile(filepath):
            return False, f"Archivo no encontrado: {filepath}"

        _, ext = os.path.splitext(filepath)
        ext = ext.lower()

        try:
            if ext in (".xls", ".xlsx"):
                self._df = pd.read_excel(filepath, sheet_name=0, dtype=str, engine="calamine")
            elif ext == ".csv":
                self._df = pd.read_csv(filepath, dtype=str)
            else:
                return False, f"Formato no soportado: {ext} (use .xlsx, .xls o .csv)"

            if self._df is None or self._df.empty:
                return False, "El archivo está vacío"

            self._filepath = filepath
            self._columns = list(self._df.columns)
            return True, f"Cargadas {self.row_count} filas, {len(self._columns)} columnas"

        except Exception as e:
            self._df = None
            self._filepath = None
            self._columns = []
            return False, f"Error al leer archivo: {e}"

    def get_column_values(self, column: str) -> List[str]:
        """Get all values from a column as strings."""
        if self._df is None:
            return []
        if column not in self._df.columns:
            return []
        return self._df[column].dropna().astype(str).tolist()

    def get_value_at(self, column: str, index: int) -> Optional[str]:
        """Get value at a specific row index."""
        if self._df is None or column not in self._df.columns:
            return None
        if index < 0 or index >= len(self._df):
            return None
        val = self._df[column].iloc[index]
        if pd.isna(val):
            return None
        return str(val)

    def columns_preview(self, max_rows: int = 5) -> Dict[str, List[str]]:
        """Get preview of first rows for each column."""
        if self._df is None:
            return {}
        preview: Dict[str, List[str]] = {}
        for col in self._columns:
            vals = self._df[col].dropna().astype(str).tolist()
            preview[col] = vals[:max_rows]
        return preview

    def clear(self) -> None:
        """Unload the current file."""
        self._df = None
        self._filepath = None
        self._columns = []

    def total_pages_for_current_project(
        self, global_settings: dict
    ) -> int:
        """Calculate total pages from global settings for comparison."""
        start = int(global_settings.get("start", 1))
        end = int(global_settings.get("end", 1))
        increment = int(global_settings.get("increment", 1))
        copies = int(global_settings.get("copies", 1))
        if increment == 0:
            return 0
        total_numbers = ((end - start) // increment) + 1
        return total_numbers * copies
