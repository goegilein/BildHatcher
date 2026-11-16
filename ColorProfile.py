"""P8.5: one active colour-database profile (laser + material + material type) for the whole application.

It is chosen once (toolbar / Laser Settings) and used by DB recolouring, automatic hatching and the database
colour pickers. The choice is remembered in USER_DIR/preferences.json and restored from the database on startup.
"""
import json
import logging

from PyQt6 import QtGui, QtWidgets

from Database.database_main import DatabaseManager, DatabaseNavigatorWidget, NavigatorMode
from HelperClasses import DBColorPalette
from PathManager import USER_DIR

log = logging.getLogger(__name__)

PREFERENCES_FILE = USER_DIR / "preferences.json"


def palette_from_payload(payload):
    """DBColorPalette from the payload of DatabaseNavigatorWidget.profileSelected."""
    palette = DBColorPalette(payload["parameters"], payload["settings"])
    palette.identifiers = payload["identifiers"]
    return palette


def profile_name(palette):
    if palette is None or not getattr(palette, "identifiers", None):
        return "none"
    ids = palette.identifiers
    return f"{ids['laser']['name']} / {ids['material']['name']} / {ids['material_type']['name']}"


def load_profile(laser_id, material_id, type_id):
    """Build the profile payload from database ids (same content as the navigator's selection), or None."""
    db = DatabaseManager()
    try:
        laser = next((row for row in db.get_lasers() if row["id"] == laser_id), None)
        material = next((row for row in db.get_all_materials() if row["id"] == material_id), None)
        mtype = next((row for row in db.get_material_types_for_material(material_id) if row["id"] == type_id), None)
        if laser is None or material is None or mtype is None:
            return None
        palette_id = db.get_or_create_palette(laser_id, type_id)
        return {
            "identifiers": {"laser": {"id": laser_id, "name": laser["name"]},
                            "material": {"id": material_id, "name": material["name"]},
                            "material_type": {"id": type_id, "name": mtype["name"]}},
            "settings": {key: mtype[key] for key in ("post_processing", "laser_mode", "enclosure_fan", "air_assist", "power_mode")},
            "parameters": [dict(p) for p in db.get_parameters(palette_id)],
        }
    finally:
        db.close()


def choose_profile_dialog(parent):
    """Let the user pick a profile in the database navigator. Returns a DBColorPalette or None."""
    chosen = {}
    dialog = QtWidgets.QDialog(parent)
    dialog.setWindowTitle("Select Color Profile")
    layout = QtWidgets.QVBoxLayout(dialog)
    navigator = DatabaseNavigatorWidget(NavigatorMode.SELECT_PROFILE, parent=dialog)
    navigator.selection_button_box.rejected.connect(dialog.reject)
    navigator.profileSelected.connect(lambda payload: chosen.update(payload=payload))
    layout.addWidget(navigator)
    dialog.exec()
    return palette_from_payload(chosen["payload"]) if chosen else None


def pick_color_dialog(parent, palette, title="Select Color"):
    """Choose one colour of the active profile (buttons). Returns [r, g, b] or None."""
    chosen = {}
    dialog = QtWidgets.QDialog(parent)
    dialog.setWindowTitle(f"{title} – {profile_name(palette)}")
    grid = QtWidgets.QGridLayout(dialog)
    for i, param in enumerate(palette.color_palette):
        rgb = [int(v) for v in param["color_rgb"].split(",")]
        button = QtWidgets.QPushButton(param["color_name"])
        light = (0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]) > 128
        button.setStyleSheet(f"background-color: rgb({rgb[0]}, {rgb[1]}, {rgb[2]}); color: {'black' if light else 'white'};")
        button.clicked.connect(lambda checked, c=rgb: (chosen.update(rgb=c), dialog.accept()))
        grid.addWidget(button, i // 4, i % 4)
    if not palette.color_palette:
        grid.addWidget(QtWidgets.QLabel("The active profile has no colors."), 0, 0)
    dialog.exec()
    return chosen.get("rgb")


class ColorProfileController:
    """Owns the active profile (data_handler.color_profile) and its toolbar action."""

    def __init__(self, data_handler, gui):
        self.data_handler = data_handler
        self.gui = gui
        self.callbacks = []  # called after the active profile changed
        self.action = QtGui.QAction("Color Profile: none", gui)
        self.action.setToolTip("Laser / material / material type of the color database used for recoloring, "
                               "DB colors and automatic hatching")
        self.action.triggered.connect(self.choose)
        self.data_handler.color_profile = None
        self.restore()

    def choose(self):
        palette = choose_profile_dialog(self.gui)
        if palette is not None:
            self.set_profile(palette)
        return palette

    def require(self):
        """The active profile; asks for one if none is set (None if the user cancels)."""
        return self.data_handler.color_profile or self.choose()

    def set_profile(self, palette, remember=True):
        self.data_handler.color_profile = palette
        self.action.setText(f"Color Profile: {profile_name(palette)}")
        if remember:
            self._save_preference(palette)
        for callback in self.callbacks:
            callback(palette)

    def restore(self):
        try:
            ids = json.loads(PREFERENCES_FILE.read_text(encoding="utf-8")).get("color_profile")
        except (OSError, ValueError):
            return
        if not ids:
            return
        try:
            payload = load_profile(ids["laser_id"], ids["material_id"], ids["type_id"])
        except Exception:
            log.exception("Could not restore the color profile %s", ids)
            return
        if payload is not None:
            self.set_profile(palette_from_payload(payload), remember=False)

    @staticmethod
    def _save_preference(palette):
        try:
            prefs = json.loads(PREFERENCES_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            prefs = {}
        ids = palette.identifiers
        prefs["color_profile"] = {"laser_id": ids["laser"]["id"], "material_id": ids["material"]["id"],
                                  "type_id": ids["material_type"]["id"]}
        try:
            PREFERENCES_FILE.parent.mkdir(parents=True, exist_ok=True)
            PREFERENCES_FILE.write_text(json.dumps(prefs, indent=2), encoding="utf-8")
        except OSError as e:
            log.warning("Could not save preferences: %s", e)
