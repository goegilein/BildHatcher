"""P9.1: pictograms (Tabler Icons, GUI_Files/icons), recoloured to the app colours.

icon("brush")                  -> burgundy outline icon (for light backgrounds: toolbar, menus)
icon("brush", ON_DARK)         -> white icon (for the filled burgundy buttons of the sections)
"""
from functools import lru_cache

from PyQt6 import QtCore, QtGui
from PyQt6.QtSvg import QSvgRenderer

from PathManager import get_gui_file_path

ICON_DIR = get_gui_file_path("icons")
APP = "7A0020"      # app burgundy (light backgrounds)
ON_DARK = "FFFFFF"  # on the filled section buttons
_SIZES = (16, 24, 32, 48)


@lru_cache(maxsize=None)
def icon(name, color=APP):
    """QIcon of GUI_Files/icons/<name>.svg drawn in `color` (hex without #). Needs a QApplication."""
    svg = (ICON_DIR / f"{name}.svg").read_text(encoding="utf-8").replace("currentColor", f"#{color}")
    renderer = QSvgRenderer(QtCore.QByteArray(svg.encode("utf-8")))
    result = QtGui.QIcon()
    for size in _SIZES:
        pixmap = QtGui.QPixmap(size, size)
        pixmap.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        result.addPixmap(pixmap)
    return result


def set_icon(widget, name, tooltip=None, color=APP, keep_text=False, size=20):
    """Give a button / action an icon; its former text becomes the tooltip (unless given) and is removed."""
    text = widget.text() if hasattr(widget, "text") else ""
    widget.setIcon(icon(name, color))
    widget.setToolTip(tooltip or text.strip())
    if not keep_text and hasattr(widget, "setText") and not isinstance(widget, QtGui.QAction):
        widget.setText("")
    if hasattr(widget, "setIconSize"):
        widget.setIconSize(QtCore.QSize(size, size))
    return widget
