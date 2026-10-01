"""Guías de posición estilo InDesign (PageNumber).

Modelo + lógica pura del feature, SIN importar Flet. Así el módulo es
directamente testeable sin arrancar la app y el viewer sigue siendo el único
sitio que sabe transformar mm→px y dibujar.

Responsabilidades (división de trabajo con `interactive_viewer`):

  - ESTE módulo:        datos por cara (independientes CARA/DORSO), hit-test
                        punto-cerca-de-línea, candidatos de snap magnético,
                        flags genéricos (visible/fijado/snap), serialización.
  - interactive_viewer: dibuja las líneas (sabe mm→px y colores), la creación
                        arrastrando desde las reglas, y el drag de guías
                        dentro de su pipeline de gestos ya existente.

Las guías se comportan como las posiciones del main: misma idea de dibujo y
arrastre, PERO sin círculo ni item (no hay número/texto asociado) y en un
array independiente por cara.

Estructura de cada guía (lista por cara; nunca se mezclan caras):

    {
      "id": int,
      "orientation": "V" | "H",
      "position_mm": float,     # V → X mm ; H → Y mm (coordenada sin sangre)
      "locked": bool,           # inamovible (bloqueo global de la cara)
    }

  - "V" = guía VERTICAL   (se crea arrastrando desde la REGLA HORIZONTAL;
                           se dibuja como línea vertical; pos = X en mm)
  - "H" = guía HORIZONTAL (se crea desde la REGLA VERTICAL; se dibuja
                           horizontal; pos = Y en mm)

Flags genéricos (afectan a AMBAS caras — "genérico" como en preferencias):
  - show:        guías visibles (toggle booleano, default True → visibles)
  - lock:        guías fijadas (inamovibles al arrastrar)
  - snap_active: snap magnético activo (usa el MISMO umbral que el snap de
                 posiciones, `magnetic_snap_threshold`, ya existente en prefs)

Persistencia por cara vía `serialize(face)` / `load_face(face, raw)`,
retrocompatible (archivos antiguos sin "guides" cargan vacíos, sin subir la
versión del proyecto).
"""

from __future__ import annotations

from typing import Dict, List, Optional


class PositionGuides:
    """Guías de posición independientes por cara (CARA/DORSO).

    Contiene la lista de guías de cada una de las 2 caras y los 3 flags
    genéricos. No conoce el viewer: entrega posiciones en mm y deja el dibujo
    y las transformaciones al viewer mediante el patrón de "contacto mínimo".
    """

    def __init__(self) -> None:
        # Guías por cara. Cada guía: dict con la estructura documentada arriba.
        self._guides: Dict[str, List[dict]] = {"CARA": [], "DORSO": []}

        # Flags genéricos (ambas caras).
        self.show = True          # visibles (default True → se ven al abrir)
        self.locked = False       # fijadas (inamovibles al arrastrar)
        self.snap_active = True   # snap magnético a guías

        # Contadores por cara para ids estables.
        self._next_id: Dict[str, int] = {"CARA": 1, "DORSO": 1}

    # ------------------------------------------------------------------
    # Configuración / acceso
    # ------------------------------------------------------------------
    def set_guides(self, face: str, guides: List[dict]) -> None:
        """Sustituye la lista de guías de una cara (carga defensiva)."""
        face = "CARA" if face == "CARA" else "DORSO"
        clean = []
        for g in guides or []:
            if not isinstance(g, dict):
                continue
            try:
                clean.append(
                    {
                        "id": int(g.get("id", self._next_id[face])),
                        "orientation": "H" if g.get("orientation", "V") == "H" else "V",
                        "position_mm": max(0.0, float(g.get("position_mm", 0.0))),
                        "locked": bool(g.get("locked", False)),
                    }
                )
            except (TypeError, ValueError):
                continue
        # Recalcular el siguiente id libre
        self._next_id[face] = max([g["id"] for g in clean], default=0) + 1
        self._guides[face] = clean

    def get_guides(self, face: str) -> List[dict]:
        face = "CARA" if face == "CARA" else "DORSO"
        return self._guides[face]

    def face_has_guides(self, face: str) -> bool:
        return len(self.get_guides(face)) > 0

    def total_count(self) -> int:
        return len(self._guides["CARA"]) + len(self._guides["DORSO"])

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    def add_guide(self, face: str, orientation: str, position_mm: float) -> dict:
        """Añade una guía a la cara. No valida rango (el viewer clampa al drag)."""
        face = "CARA" if face == "CARA" else "DORSO"
        guide = {
            "id": self._next_id[face],
            "orientation": "H" if orientation == "H" else "V",
            "position_mm": max(0.0, float(position_mm)),
            "locked": False,
        }
        self._next_id[face] += 1
        self._guides[face].append(guide)
        return guide

    def delete_guide(self, face: str, guide_id: int) -> bool:
        face = "CARA" if face == "CARA" else "DORSO"
        before = len(self._guides[face])
        self._guides[face] = [g for g in self._guides[face] if g["id"] != guide_id]
        return len(self._guides[face]) != before

    def set_guide_locked(self, face: str, guide_id: int, locked: bool) -> bool:
        face = "CARA" if face == "CARA" else "DORSO"
        for g in self._guides[face]:
            if g["id"] == guide_id:
                g["locked"] = bool(locked)
                return True
        return False

    def guide_at(self, face: str, guide_id: int) -> Optional[dict]:
        face = "CARA" if face == "CARA" else "DORSO"
        for g in self._guides[face]:
            if g["id"] == guide_id:
                return g
        return None

    def move_guide(self, face: str, guide_id: int, position_mm: float) -> bool:
        """Mueve una guía (drag del viewer). `position_mm` ya viene clampado.
        Respeta el lock genérico y el de la propia guía."""
        face = "CARA" if face == "CARA" else "DORSO"
        for g in self._guides[face]:
            if g["id"] == guide_id:
                if g["locked"] or self.locked:
                    return False
                g["position_mm"] = float(position_mm)
                return True
        return False

    # ------------------------------------------------------------------
    # Hit-test: busca la guía más cercana a (x_mm, y_mm) dentro de tolerance_mm
    # ------------------------------------------------------------------
    def hit_test(
        self, face: str, x_mm: float, y_mm: float, tolerance_mm: float
    ) -> Optional[dict]:
        """Devuelve la guía más cercana (o None) si el punto está a
        `tolerance_mm` de su línea. Patrón distancia punto-a-línea."""
        if not self.show:
            return None
        face = "CARA" if face == "CARA" else "DORSO"
        best: Optional[dict] = None
        best_dist = tolerance_mm
        for g in self._guides[face]:
            pos = g["position_mm"]
            if g["orientation"] == "V":
                dist = abs(pos - x_mm)
            else:
                dist = abs(pos - y_mm)
            if dist <= best_dist:
                best_dist = dist
                best = g
        return best

    # ------------------------------------------------------------------
    # Snap magnético: candidatos de líneas para el snap de elementos
    # ------------------------------------------------------------------
    def magnetic_candidates(self, face: str) -> Dict[str, List[float]]:
        """Devuelve {"x_mm": [...], "y_mm": [...]} con las posiciones de las
        guías de la cara. El viewer gatea el snap por `snap_active AND show`
        (ocultas/desactivadas no imantan; el botón magnético es la memoria)."""
        face = "CARA" if face == "CARA" else "DORSO"
        xs, ys = [], []
        for g in self._guides[face]:
            if g["orientation"] == "V":
                xs.append(g["position_mm"])
            else:
                ys.append(g["position_mm"])
        return {"x_mm": xs, "y_mm": ys}

    # ------------------------------------------------------------------
    # Creación desde la regla (drag del detector de regla, patrón InDesign)
    # ------------------------------------------------------------------
    def create_from_ruler(
        self, face: str, orientation: str, position_mm: float,
        page_width_mm: float, page_height_mm: float,
    ) -> dict:
        """Crea una guía nueva "fantasma" en `position_mm` (cursor sobre la
        página). `orientation` es la de la REGLA de origen:
          - desde la regla HORIZONTAL → guía VERTICAL ("V", posición = X)
          - desde la regla VERTICAL   → guía HORIZONTAL ("H", posición = Y)
        El clamp a la página se hace aquí para que una guía arrastrada muy
        lejos del borde quede siempre dentro de la página."""
        face = "CARA" if face == "CARA" else "DORSO"
        orient = "H" if orientation == "H" else "V"
        limit_mm = page_height_mm if orient == "H" else page_width_mm
        pos = max(0.0, min(float(position_mm), limit_mm))
        return self.add_guide(face, orient, pos)

    # ------------------------------------------------------------------
    # Serialización (por cara, retrocompatible)
    # ------------------------------------------------------------------
    def serialize(self, face: str) -> List[dict]:
        face = "CARA" if face == "CARA" else "DORSO"
        return [dict(g) for g in self._guides[face]]

    def clear(self, face: str) -> None:
        face = "CARA" if face == "CARA" else "DORSO"
        self._guides[face] = []

    def load_face(self, face: str, raw_guides) -> None:
        """Carga las guías de una cara desde datos del archivo (delega en
        `set_guides`, que es defensivo)."""
        self.set_guides(face, raw_guides if isinstance(raw_guides, list) else [])

    # ------------------------------------------------------------------
    # Flags genéricos (afectan a AMBAS caras — "genérico")
    # ------------------------------------------------------------------
    def set_show(self, visible: bool):
        """Muestra/oculta las guías de AMBAS caras (limpiar el lienzo)."""
        self.show = bool(visible)

    def set_snap_all(self, snap: bool):
        """Activa/desactiva el snap magnético a guías en AMBAS caras.
        Es la memoria del botón magnético; el snap efectivo además exige
        guías activas (`show`) — lo gatea el viewer."""
        self.snap_active = bool(snap)

    def set_locked_all(self, locked: bool):
        """Fija (bloquea) las guías de AMBAS caras: no se pueden arrastrar
        ni eliminar. Genérico como pediste. NO toca el snap."""
        self.locked = bool(locked)


if __name__ == "__main__":
    pg = PositionGuides()

    # CRUD + ids por cara
    v = pg.add_guide("CARA", "V", 10.0)
    h = pg.add_guide("CARA", "H", 20.0)
    pg.add_guide("DORSO", "V", 5.0)
    assert v["id"] == 1 and h["id"] == 2, "ids secuenciales por cara"
    assert v["orientation"] == "V" and h["orientation"] == "H"
    assert len(pg.get_guides("CARA")) == 2
    assert len(pg.get_guides("DORSO")) == 1

    # hit-test (punto-a-línea, tolerancia)
    hit = pg.hit_test("CARA", 10.5, 100, 1.0)
    assert hit is not None and hit["id"] == v["id"]
    assert pg.hit_test("CARA", 50, 50, 1.0) is None
    assert pg.hit_test("DORSO", 5.5, 0, 1.0) is not None

    # inválidos no rompen: huecos y solo dicts
    pg.set_guides("CARA", [{"id": 9, "orientation": "H", "position_mm": 1}])
    assert len(pg.get_guides("CARA")) == 1
    assert pg.get_guides("CARA")[0]["id"] == 9

    # compatible con cargas viejas (retrocompat)
    pg.load_face("DORSO", [{"id": 3, "orientation": "bad", "position_mm": "7.5"}])
    assert pg.get_guides("DORSO")[0]["orientation"] == "V"
    assert pg.get_guides("DORSO")[0]["position_mm"] == 7.5

    # move respeta lock (propio y genérico)
    mv = pg.add_guide("CARA", "V", 30.0)
    assert pg.move_guide("CARA", mv["id"], 40.0)
    assert pg.get_guides("CARA")[-1]["position_mm"] == 40.0
    pg.set_guide_locked("CARA", mv["id"], True)
    assert not pg.move_guide("CARA", mv["id"], 50.0)
    pg.set_locked_all(True)
    pg2 = PositionGuides()
    pg2.set_locked_all(True)
    assert pg2.locked and not hasattr(pg2, "snap_locked")
    pg2.set_locked_all(False)

    # create_from_ruler con clamps
    cr = pg.create_from_ruler("CARA", "H", -5.0, 210.0, 297.0)
    assert cr["position_mm"] == 0.0
    cr2 = pg.create_from_ruler("CARA", "H", 900.0, 210.0, 297.0)
    assert cr2["position_mm"] == 297.0

    # magnetic_candidates respetan show y orientación
    pg3 = PositionGuides()
    gv = pg3.add_guide("CARA", "V", 15.0)
    gh_ = pg3.add_guide("CARA", "H", 25.0)
    cand = pg3.magnetic_candidates("CARA")
    assert cand == {"x_mm": [15.0], "y_mm": [25.0]}
    pg3.set_show(False)
    assert pg3.magnetic_candidates("CARA") == {"x_mm": [], "y_mm": []}
    assert pg3.hit_test("CARA", gv["position_mm"], 0, 1.0) is None
    pg3.set_show(True)
    assert pg3.hit_test("CARA", gv["position_mm"], 0, 1.0) is not None
    assert pg3.hit_test("CARA", 100, gh_["position_mm"], 1.0) is not None

    # serialización round-trip
    pg4 = PositionGuides()
    pg4.add_guide("CARA", "V", 3.0)
    pg4.add_guide("CARA", "H", 4.0)
    data = pg4.serialize("CARA")
    assert data == [
        {"id": 1, "orientation": "V", "position_mm": 3.0, "locked": False},
        {"id": 2, "orientation": "H", "position_mm": 4.0, "locked": False},
    ]
    pg5 = PositionGuides()
    pg5.load_face("CARA", data)
    assert pg5.serialize("CARA") == data

    print("position_guides: asserts OK")