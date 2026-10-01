"""
Integracion de textos variables en MainScreen.
Mantiene la logica de UI de textos variables separada de main_screen.py.
"""

from __future__ import annotations

from typing import Callable, List, Optional

from ui.variable_text_settings_dialog import (
    VariableTextProfile,
    VariableTextProfileManager,
)


class VariableTextUIManager:
    """Gestiona la UI de textos variables en MainScreen.

    Se encarga de:
    - Crear/editar posiciones de texto variable
    - Abrir el dialogo de configuracion (VariableTextProfileManager)
    - Sincronizar con el InteractiveViewer
    """

    def __init__(
        self,
        page,
        viewer,
        excel_manager=None,
    ):
        self.page = page
        self.viewer = viewer
        self.excel_manager = excel_manager

        # Profile manager
        self.profile_manager = VariableTextProfileManager(
            page=page,
            viewer_callback=viewer,
            excel_manager=excel_manager,
            on_profile_changed=self._on_profile_changed,
            on_row_change=self._on_row_change,
        )

        # Callbacks
        self.on_project_modified: Optional[Callable] = None
        self.on_vt_profile_changed: Optional[Callable] = None
        self.on_row_change: Optional[Callable] = None
        self._active_vt_id: Optional[int] = None

    def _on_row_change(self, row_number: int):
        """Reenvía el sync fila→página del diálogo al main."""
        if self.on_row_change:
            try:
                self.on_row_change(row_number)
            except Exception:
                pass

    def _on_profile_changed(self, profile):
        """Callback cuando un perfil cambia en el manager desde el diálogo."""
        if self.on_vt_profile_changed:
            self.on_vt_profile_changed(profile, self._active_vt_id)

    def _find_profile(self, name: str) -> Optional[VariableTextProfile]:
        """Busca un perfil por nombre en el manager."""
        for p in self.profile_manager.get_profiles():
            if p.name == name:
                return p
        return None

    def add_variable_text_position(
        self,
        x: float,
        y: float,
        profile_name: str = "<Default>",
        rotation: str = "0°",
        alignment: str = "izquierda",
        auto_select: bool = True,
        variable_text_id: Optional[int] = None,
        text: Optional[str] = None,
    ) -> int:
        """Anade un texto variable en el viewer y devuelve su ID."""
        profile = self._find_profile(profile_name)
        if profile is None:
            profiles = self.profile_manager.get_profiles()
            profile = profiles[0] if profiles else VariableTextProfile.create_default()

        vt_id = self.viewer.add_variable_text(
            x=x,
            y=y,
            text=text if text is not None else profile.sample_text,
            font_family=profile.font_family,
            font_style=profile.font_style,
            font_size=profile.font_size,
            color=profile.text_color,
            alignment=alignment,
            rotation=rotation,
            auto_select=auto_select,
            variable_text_id=variable_text_id,
            profile_name=profile_name,
            font_path=getattr(profile, "resolved_font_path", None),
            text_alignment=getattr(profile, "alignment", "izquierda"),
            metricas=getattr(profile, "metricas", None),
            value_source=getattr(profile, "value_source", "sample"),
            excel_column=getattr(profile, "excel_column", ""),
            line_spacing=getattr(profile, "line_spacing", 0.0),
            letter_spacing=getattr(profile, "letter_spacing", 0.0),
            anchor=getattr(profile, "anchor", None),
        )

        return vt_id

    def open_variable_text_dialog(
        self,
        profile_name: Optional[str] = None,
        position_data: Optional[dict] = None,
        target_vt_id: Optional[int] = None,
        initial_row: Optional[int] = None,
    ):
        """Abre el dialogo de configuracion de texto variable."""
        self._active_vt_id = target_vt_id

        # Sincronizar columnas Excel antes de abrir
        if self.excel_manager and self.excel_manager.is_loaded:
            self.profile_manager.set_excel_columns(self.excel_manager.columns)

        # Si se pide un perfil especifico, seleccionarlo
        if profile_name:
            profiles = self.profile_manager.get_profiles()
            for i, p in enumerate(profiles):
                if p.name == profile_name:
                    self.profile_manager.selected_profile_index = i
                    self.profile_manager.current_profile = p.copy()
                    break

        self.profile_manager.set_initial_row(initial_row)
        self.profile_manager.open()
