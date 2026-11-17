"""P9.10: the colour tools from anywhere – hotkeys and the active-tool indicator in the toolbar.

Every entry does exactly what its button in the Color section does (the button is clicked), so the panel
section does not have to be visible. Hotkeys are single letters; they are ignored while a text or number
field has the keyboard focus (typing a text overlay must not switch tools).
"""
from PyQt6 import QtCore, QtGui, QtWidgets

import icons

# key, label, icon, object name of the Color-section button
TOOLS = (
    ("D", "Draw", "brush", "toggle_draw_button"),
    ("F", "Fill", "bucket-droplet", "flood_fill_button"),
    ("R", "Replace", "replace", "replace_color_button"),
    ("P", "Pick from image", "color-picker", "pick_color_from_image_button"),
    ("C", "More colors", "palette", "select_color_color_button"),
    ("T", "Transparent", "droplet-off", "transparent_color_button"),
)
TOOL_ICONS = {"Draw": "brush", "Fill": "bucket-droplet", "Replace": "replace", "Pick": "color-picker",
              "Mask": "mask", "": "click"}
_TYPING_WIDGETS = (QtWidgets.QLineEdit, QtWidgets.QAbstractSpinBox, QtWidgets.QTextEdit, QtWidgets.QPlainTextEdit)


def typing_focus():
    """True while a text / number field has the keyboard focus."""
    widget = QtWidgets.QApplication.focusWidget()
    if isinstance(widget, QtWidgets.QComboBox):
        return widget.isEditable()
    return isinstance(widget, _TYPING_WIDGETS)


class ToolController:
    """Hotkeys for TOOLS and the indicator of the active tool and colour (toolbar)."""

    def __init__(self, gui, colorer):
        self.gui = gui
        self.colorer = colorer
        self.shortcuts = {}
        for key, label, icon_name, button_name in TOOLS:
            shortcut = QtGui.QShortcut(QtGui.QKeySequence(key), gui)
            shortcut.setContext(QtCore.Qt.ShortcutContext.WindowShortcut)  # main window only, not in dialogs
            shortcut.activated.connect(lambda name=button_name: self.trigger(name))
            self.shortcuts[key] = shortcut
            button = self.button(button_name)
            base = button.toolTip() or label
            if f"({key})" not in base:
                button.setToolTip(f"{base} ({key})")
        self.indicator = None

    def button(self, name):
        found = getattr(self.gui, name, None) or self.gui.findChild(QtWidgets.QAbstractButton, name)
        if found is None:
            raise LookupError(name)
        return found

    def trigger(self, button_name, from_key=True):
        """Do what the button does (also while its section is hidden)."""
        if from_key and typing_focus():
            return False
        button = self.button(button_name)
        if not button.isEnabled():
            return False
        button.click()
        return True

    # --- toolbar indicator ---
    def add_indicator(self, toolbar, before=None):
        self.indicator = QtWidgets.QLabel(objectName="active_tool_indicator")  # (a tool button gets the toolbar's icon size)
        self.indicator.setContentsMargins(4, 0, 4, 0)
        if before is not None:
            toolbar.insertWidget(before, self.indicator)
        else:
            toolbar.addWidget(self.indicator)
        self.colorer.state_callbacks.append(self.update_indicator)
        self.update_indicator()
        return self.indicator

    def update_indicator(self):
        if self.indicator is None:
            return
        tool = self.colorer.active_tool
        rgba = self.colorer.active_color
        size = 24
        ratio = self.indicator.devicePixelRatioF()
        pixmap = QtGui.QPixmap(int(size * 2 * ratio), int(size * ratio))
        pixmap.setDevicePixelRatio(ratio)
        pixmap.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(pixmap)
        painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawPixmap(QtCore.QRect(0, 0, size, size), icons.icon(TOOL_ICONS.get(tool, "click")).pixmap(48, 48))
        swatch = QtCore.QRect(size + 4, 4, size - 8, size - 8)
        if rgba[3] == 0:  # transparent: checkerboard
            painter.fillRect(swatch, QtGui.QColor("white"))
            half = swatch.width() // 2
            painter.fillRect(swatch.x(), swatch.y(), half, half, QtGui.QColor("#BBBBBB"))
            painter.fillRect(swatch.x() + half, swatch.y() + half, swatch.width() - half, swatch.height() - half,
                             QtGui.QColor("#BBBBBB"))
        else:
            painter.fillRect(swatch, QtGui.QColor(*rgba[:3]))
        painter.setPen(QtGui.QColor("#" + icons.APP))
        painter.drawRect(swatch)
        painter.end()
        self.indicator.setPixmap(pixmap)
        keys = ", ".join(f"{key} {label.lower()}" for key, label, *_ in TOOLS)
        colour = "transparent" if rgba[3] == 0 else f"R{rgba[0]} G{rgba[1]} B{rgba[2]}"
        self.indicator.setToolTip(f"Active tool: {tool or 'none'} · color: {colour}\nHotkeys: {keys}")
