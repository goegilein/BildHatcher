"""The app's look: the "Atelier" style after piupulaser.de, dark or bright (GUI_Files/styles/atelier.qss).

Portable: copy this module, GUI_Files/styles, GUI_Files/fonts and the four images the stylesheet uses
(icons/spin-up, spin-down, combo-down, check). The stylesheet is the source of the look – a template whose
@tokens are defined by the two palettes in its header; this module only

  * renders it for a mode ("dark" = the web shop's look, "light" = bright mode) and applies it app-wide,
  * loads the fonts (Plus Jakarta Sans, Space Mono – SIL Open Font License),
  * registers the "icons:" search path used by url(icons:...) in the stylesheet,
  * switches modes at run time: pictograms set in the .ui are reloaded from the mode's icon folder
    (GUI_Files/icons = dark, GUI_Files/icons/light = bright) and code that builds its own icons or
    colours is told via on_change(),
  * gives the palette to the few things drawn in code (tool wheel, indicators): color(name).

The dark rendering is also copied into the root of GUI_Files/BildHatcher.ui (tools/apply_style.py) so Qt
Designer shows the real look; a test keeps both identical. The previous look: styles/legacy_burgundy.qss.
"""
import re

from PyQt6 import QtCore, QtGui, QtWidgets

from PathManager import get_gui_file_path

STYLE = "atelier"
MODES = ("dark", "light")
STYLE_DIR = get_gui_file_path("styles")
FONT_DIR = get_gui_file_path("fonts")
ICON_DIR = get_gui_file_path("icons")
UI_FILE = get_gui_file_path("BildHatcher.ui")
FONT_TEXT = "Plus Jakarta Sans"
FONT_MONO = "Space Mono"

MODE = "dark"
_callbacks = []

QtCore.QDir.addSearchPath("icons", str(ICON_DIR))


# --- stylesheet ---
def template(name=STYLE):
    return (STYLE_DIR / f"{name}.qss").read_text(encoding="utf-8")


def palettes(name=STYLE):
    """{mode: {token: value}} from the @palette blocks in the stylesheet's header."""
    result = {}
    for mode, body in re.findall(r"@palette\s+(\w+)\s*\n(.*?)@end", template(name), flags=re.S):
        values = {}
        for row in body.splitlines():
            parts = row.split(None, 1)
            if len(parts) == 2:
                token, rest = parts
                value = re.match(r"(rgba?\([^)]*\)|#[0-9A-Fa-f]{3,8})", rest.strip())
                if value:
                    values[token] = value.group(1)
        result[mode] = values
    return result


def render(mode=None, name=STYLE):
    """The stylesheet with the palette of `mode` filled in."""
    palette = palettes(name)[mode or MODE]
    return re.sub(r"@([A-Za-z]+)\b", lambda m: palette.get(m.group(1), m.group(0)), template(name))


def stylesheet(mode=None, name=STYLE):  # (name kept for callers)
    return render(mode, name)


def color(token, mode=None):
    """QColor of a palette token, e.g. color("accent")."""
    value = palettes()[mode or MODE][token]
    rgba = re.match(r"rgba?\(([^)]*)\)", value)
    if rgba:
        parts = [p.strip() for p in rgba.group(1).split(",")]
        r, g, b = (int(p) for p in parts[:3])
        a = float(parts[3]) if len(parts) > 3 else 1.0
        return QtGui.QColor(r, g, b, int(round(a * 255)))
    return QtGui.QColor(value)


# --- fonts ---
_fonts_loaded = []


def load_fonts():
    """Register the bundled fonts (once). Returns the loaded families."""
    if not _fonts_loaded:
        for path in sorted(FONT_DIR.glob("*.ttf")):
            font_id = QtGui.QFontDatabase.addApplicationFont(str(path))
            if font_id >= 0:
                _fonts_loaded.extend(QtGui.QFontDatabase.applicationFontFamilies(font_id))
    return sorted(set(_fonts_loaded))


# --- icons per mode ---
def icon_dir(mode=None):
    return ICON_DIR if (mode or MODE) == "dark" else ICON_DIR / "light"


def icon_file(name, mode=None):
    """Path of pictogram `name` (without .svg) for the mode."""
    return icon_dir(mode) / f"{name}.svg"


_ui_icons = None


def ui_icons():
    """[(object name, "icon" | "pixmap", off file name, on file name)] of the pictograms set in the .ui."""
    global _ui_icons
    if _ui_icons is None:
        from xml.etree import ElementTree  # standard library: the app itself needs no lxml
        root = ElementTree.parse(str(UI_FILE)).getroot()
        found = []
        for element in (e for e in root.iter() if e.tag in ("widget", "action")):
            for prop in element.findall("property"):
                if prop.get("name") == "icon" and prop.find("iconset") is not None:
                    iconset = prop.find("iconset")
                    off, on = iconset.findtext("normaloff"), iconset.findtext("normalon")
                    if off:
                        found.append((element.get("name"), "icon", off.strip(), (on or off).strip()))
                elif prop.get("name") == "pixmap" and prop.findtext("pixmap"):
                    found.append((element.get("name"), "pixmap", prop.findtext("pixmap").strip(), None))
        _ui_icons = found
    return _ui_icons


def refresh_ui_icons(window):
    """Reload the .ui's pictograms from the current mode's folder (widgets with an "iconName" property are
    coloured by their own code and left alone)."""
    def path(ui_path):
        return str(icon_dir() / ui_path.split("/")[-1])
    for name, kind, off, on in ui_icons():
        obj = window.findChild(QtCore.QObject, name)
        if obj is None or obj.property("iconName"):
            continue
        if kind == "icon":
            icon = QtGui.QIcon()
            icon.addFile(path(off), QtCore.QSize(), QtGui.QIcon.Mode.Normal, QtGui.QIcon.State.Off)
            icon.addFile(path(on), QtCore.QSize(), QtGui.QIcon.Mode.Normal, QtGui.QIcon.State.On)
            obj.setIcon(icon)
        elif isinstance(obj, QtWidgets.QLabel):
            obj.setPixmap(QtGui.QPixmap(path(off)))


# --- applying ---
def on_change(callback):
    """Call `callback()` after every mode switch (code-built icons / colours)."""
    _callbacks.append(callback)
    return callback


def apply(app=None, mode=None):
    """Fonts + stylesheet for the whole application."""
    global MODE
    MODE = mode if mode in MODES else MODE
    app = app or QtWidgets.QApplication.instance()
    load_fonts()
    font = QtGui.QFont(FONT_TEXT)
    font.setPointSizeF(9)
    app.setFont(font)
    app.setStyleSheet(render(MODE))
    return app


def set_mode(mode, window=None):
    """Switch dark / light at run time."""
    if mode not in MODES:
        raise ValueError(mode)
    apply(mode=mode)
    if window is not None:
        refresh_ui_icons(window)
    for callback in list(_callbacks):
        try:
            callback()
        except RuntimeError:  # a widget of a closed window
            _callbacks.remove(callback)
