"""P9.1 / P10: pictograms, GUI_Files/icons/<meaning>.svg (see GUI_Files/icons/SOURCES.md).

The panel's icons are set in GUI_Files/BildHatcher.ui; this module serves the code-built parts (toolbar actions,
group strip, tool wheel, indicator). Coloured icons are used as they are; monochrome ones that use
`currentColor` (e.g. the text colour buttons) are drawn in `color`.
"""
from functools import lru_cache

from PyQt6 import QtCore, QtGui
from PyQt6.QtSvg import QSvgRenderer

from PathManager import get_gui_file_path

ICON_DIR = get_gui_file_path("icons")
APP = "7A0020"      # app burgundy (light backgrounds)
ON_DARK = "FFFFFF"  # on the filled section buttons
_SIZES = (16, 24, 32, 48)
QtCore.QDir.addSearchPath("icons", str(ICON_DIR))  # stylesheet images: url(icons:spin-up.svg)


@lru_cache(maxsize=None)
def icon(name, color=APP, checked_color=None):
    """QIcon of GUI_Files/icons/<name>.svg drawn in `color` (hex without #), in `checked_color` while the
    button is checked (optional). Needs a QApplication."""
    source = (ICON_DIR / f"{name}.svg").read_text(encoding="utf-8")
    result = QtGui.QIcon()
    states = [(color, QtGui.QIcon.State.Off)]
    if checked_color:
        states.append((checked_color, QtGui.QIcon.State.On))
    for hex_color, state in states:
        renderer = QSvgRenderer(QtCore.QByteArray(source.replace("currentColor", f"#{hex_color}").encode("utf-8")))
        for size in _SIZES:
            pixmap = QtGui.QPixmap(size, size)
            pixmap.fill(QtCore.Qt.GlobalColor.transparent)
            painter = QtGui.QPainter(pixmap)
            renderer.render(painter)
            painter.end()
            result.addPixmap(pixmap, QtGui.QIcon.Mode.Normal, state)
    return result


@lru_cache(maxsize=None)
def toggle_icon(off_name, on_name):
    """QIcon showing `off_name` while unchecked and `on_name` while checked (e.g. grid / grid-hide)."""
    result = QtGui.QIcon()
    for name, state in ((off_name, QtGui.QIcon.State.Off), (on_name, QtGui.QIcon.State.On)):
        for size in _SIZES:
            result.addPixmap(icon(name).pixmap(size, size), QtGui.QIcon.Mode.Normal, state)
    return result


def set_icon(widget, name, tooltip=None, color=APP, keep_text=False, size=20, checked_color=None):
    """Give a button / action an icon; its former text becomes the tooltip (unless given) and is removed."""
    text = widget.text() if hasattr(widget, "text") else ""
    widget.setIcon(icon(name, color, checked_color))
    widget.setToolTip(tooltip or text.strip())
    if not keep_text and hasattr(widget, "setText") and not isinstance(widget, QtGui.QAction):
        widget.setText("")
    if hasattr(widget, "setIconSize"):
        widget.setIconSize(QtCore.QSize(size, size))
    return widget
