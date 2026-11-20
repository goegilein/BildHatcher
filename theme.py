"""The app's look: the "Atelier" style after piupulaser.de (GUI_Files/styles/atelier.qss).

Portable: copy this module, GUI_Files/styles, GUI_Files/fonts and the icons the stylesheet uses
(spin-up / spin-down / combo-down / check). The stylesheet is the source of the look; this module only

  * loads the fonts (Plus Jakarta Sans, Space Mono – SIL Open Font License),
  * registers the "icons:" search path used by url(icons:...) in the stylesheet,
  * applies the stylesheet to the whole application (dialogs included),
  * holds the palette for the few things drawn in code (tool wheel, indicators).

The stylesheet is also copied into the root of GUI_Files/BildHatcher.ui (tools/apply_style.py) so Qt Designer
shows the real look; a test keeps both identical. The previous look is kept in styles/legacy_burgundy.qss.
"""
from PyQt6 import QtCore, QtGui, QtWidgets

from PathManager import get_gui_file_path

STYLE = "atelier"
STYLE_DIR = get_gui_file_path("styles")
FONT_DIR = get_gui_file_path("fonts")
ICON_DIR = get_gui_file_path("icons")

# palette (names as in the web shop's Tailwind config)
BG = "#0B0E14"
SURFACE = "#131822"
SURFACE_HOVER = "#18202F"
GOLD = "#D0A76F"
GOLD_DARK = QtGui.QColor(208, 167, 111, 36)    # rgba(208, 167, 111, 0.14)
GOLD_40 = QtGui.QColor(208, 167, 111, 102)     # rgba(208, 167, 111, 0.40)
FROST = QtGui.QColor(255, 255, 255, 20)        # rgba(255, 255, 255, 0.08)
TEXT_HIGH = "#F1F5F9"
TEXT_MUTED = "#94A3B8"
TEXT_SLATE = "#64748B"
ON_GOLD = "#020617"
FONT_TEXT = "Plus Jakarta Sans"
FONT_MONO = "Space Mono"

QtCore.QDir.addSearchPath("icons", str(ICON_DIR))


def stylesheet(name=STYLE):
    return (STYLE_DIR / f"{name}.qss").read_text(encoding="utf-8")


_fonts_loaded = []


def load_fonts():
    """Register the bundled fonts (once). Returns the loaded families."""
    if not _fonts_loaded:
        for path in sorted(FONT_DIR.glob("*.ttf")):
            font_id = QtGui.QFontDatabase.addApplicationFont(str(path))
            if font_id >= 0:
                _fonts_loaded.extend(QtGui.QFontDatabase.applicationFontFamilies(font_id))
    return sorted(set(_fonts_loaded))


def apply(app=None, name=STYLE):
    """Fonts + stylesheet for the whole application."""
    app = app or QtWidgets.QApplication.instance()
    load_fonts()
    font = QtGui.QFont(FONT_TEXT)
    font.setPointSizeF(9)
    app.setFont(font)
    app.setStyleSheet(stylesheet(name))
    return app
