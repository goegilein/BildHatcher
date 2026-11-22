"""P9.1 / P10: pictograms, GUI_Files/icons/<meaning>.svg (see GUI_Files/icons/SOURCES.md).

The panel's icons are set in GUI_Files/BildHatcher.ui; this module serves the code-built parts (toolbar actions,
group strip, tool wheel, indicator). Coloured icons are used as they are; monochrome ones that use
`currentColor` (e.g. the text colour buttons) are drawn in `color`.
P11.3: every pictogram exists for the dark mode (GUI_Files/icons) and the bright mode (GUI_Files/icons/light);
icon() serves the current mode of theme.py (code that keeps icons re-sets them via theme.on_change).
"""
from functools import lru_cache

from PyQt6 import QtCore, QtGui
from PyQt6.QtSvg import QSvgRenderer

import theme

ICON_DIR = theme.ICON_DIR
INK = {"dark": "CBD5E1", "light": "37474F"}  # pictogram ink per mode (currentColor icons without a colour)
APP = None          # (default colour: the mode's ink)
ON_DARK = "FFFFFF"  # on the filled section buttons
_SIZES = (16, 24, 32, 48)


def ink():
    return INK[theme.MODE]


def icon(name, color=APP, checked_color=None):
    """QIcon of the pictogram `name` for the current mode, `currentColor` drawn in `color` (hex without #,
    default: the mode's ink), in `checked_color` while the button is checked (optional). Needs a QApplication."""
    return _icon(name, color or ink(), checked_color, theme.MODE)


@lru_cache(maxsize=None)
def _icon(name, color, checked_color, mode):
    source = theme.icon_file(name, mode).read_text(encoding="utf-8")
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


def toggle_icon(off_name, on_name):
    """QIcon showing `off_name` while unchecked and `on_name` while checked (e.g. grid / grid-hide)."""
    return _toggle_icon(off_name, on_name, theme.MODE)


@lru_cache(maxsize=None)
def _toggle_icon(off_name, on_name, mode):
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
