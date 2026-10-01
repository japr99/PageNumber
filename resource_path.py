"""Utility to resolve resource paths compatible with PyInstaller bundles"""

import sys
import os


def get_resource_path(relative_path):
    """Obtiene la ruta absoluta del recurso, compatible con PyInstaller"""
    base_path = getattr(sys, "_MEIPASS", None)
    if not base_path:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)
