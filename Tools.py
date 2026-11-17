"""P9.10 / P9.11: the colour tools from anywhere – hotkeys, active-tool indicator, tool wheel.

Every entry does exactly what its button in the Color section does (the button is clicked), so the panel
section does not have to be visible. Hotkeys are single letters; they are ignored while a text or number
field has the keyboard focus (typing a text overlay must not switch tools).
"""
import math

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


class ToolWheel(QtWidgets.QWidget):
    """P9.11: radial menu of TOOLS over the canvas.

    Hold the right mouse button over the image: the wheel opens around the pointer, moving highlights a tool,
    releasing selects it (releasing in the centre cancels). A short right click opens it to stay: then move
    and click to select, click in the centre / press Esc to close.
    """

    RADIUS = 104
    INNER = 30
    CLICK_MS = 350

    def __init__(self, controller, viewport, event_handler):
        super().__init__(viewport)
        self.controller = controller
        self.viewport = viewport
        self.setObjectName("tool_wheel")
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)  # the viewport keeps the mouse
        size = 2 * self.RADIUS + 8
        self.resize(size, size)
        self.hide()
        self.highlight = None
        self.sticky = False  # opened by a short click
        self.opened = QtCore.QElapsedTimer()
        event_handler.add_canvas_event_filter(self.on_canvas_event)

    # --- geometry ---
    @property
    def centre(self):
        return QtCore.QPointF(self.width() / 2, self.height() / 2)

    def sector_at(self, pos_in_viewport):
        """Index of the tool under a viewport position, None in the centre or outside."""
        vec = QtCore.QPointF(pos_in_viewport) - QtCore.QPointF(self.pos()) - self.centre
        dist = (vec.x() ** 2 + vec.y() ** 2) ** 0.5
        if dist < self.INNER or dist > self.RADIUS + 40:
            return None
        angle = (math.degrees(math.atan2(vec.y(), vec.x())) + 90) % 360  # 0 = up, clockwise
        step = 360 / len(TOOLS)
        return int(((angle + step / 2) % 360) // step)

    def open_at(self, pos):
        half = self.width() // 2
        x = min(max(int(pos.x()) - half, 0), max(self.viewport.width() - self.width(), 0))
        y = min(max(int(pos.y()) - half, 0), max(self.viewport.height() - self.height(), 0))
        self.move(x, y)
        self.highlight = None
        self.sticky = False
        self.opened.start()
        self.show()
        self.raise_()

    def close_wheel(self, select):
        index = self.highlight if select else None
        self.hide()
        self.highlight = None
        self.sticky = False
        if index is not None:
            self.controller.trigger(TOOLS[index][3], from_key=False)
        return index

    # --- events (from the canvas viewport) ---
    def on_canvas_event(self, event):
        kind = event.type()
        Type, Button = QtCore.QEvent.Type, QtCore.Qt.MouseButton
        if kind == Type.ContextMenu:
            return True
        if not self.isVisible():
            if kind == Type.MouseButtonPress and event.button() == Button.RightButton:
                self.open_at(event.position())
                return True
            return False
        if kind == Type.MouseMove:
            index = self.sector_at(event.position())
            if index != self.highlight:
                self.highlight = index
                self.update()
            return True
        if kind == Type.MouseButtonRelease and event.button() == Button.RightButton and not self.sticky:
            self.highlight = self.sector_at(event.position())
            if self.highlight is None and self.opened.elapsed() < self.CLICK_MS:
                self.sticky = True  # short click: keep it open
                return True
            self.close_wheel(select=True)
            return True
        if kind == Type.MouseButtonPress and self.sticky:
            self.highlight = self.sector_at(event.position())
            self.close_wheel(select=True)
            return True
        if kind == Type.KeyPress and event.key() == QtCore.Qt.Key.Key_Escape:
            self.close_wheel(select=False)
            return True
        return kind in (Type.MouseButtonRelease, Type.MouseButtonDblClick)

    # --- painting ---
    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        app = QtGui.QColor("#" + icons.APP)
        c = self.centre
        outer = QtCore.QRectF(c.x() - self.RADIUS, c.y() - self.RADIUS, 2 * self.RADIUS, 2 * self.RADIUS)
        painter.setPen(QtGui.QPen(app, 1.5))
        painter.setBrush(QtGui.QColor(255, 255, 255, 235))
        painter.drawEllipse(outer)
        step = 360 / len(TOOLS)
        if self.highlight is not None:  # highlighted sector (Qt angles: 0 = 3 o'clock, counter-clockwise)
            start = 90 - (self.highlight * step) - step / 2
            path = QtGui.QPainterPath(c)
            path.arcTo(outer, start, step)
            path.closeSubpath()
            painter.setBrush(app)
            painter.drawPath(path)
        painter.setPen(QtGui.QPen(QtGui.QColor(app.red(), app.green(), app.blue(), 90), 1))
        for i in range(len(TOOLS)):  # sector borders
            a = math.radians(i * step - step / 2 - 90)
            painter.drawLine(QtCore.QPointF(c.x() + self.INNER * math.cos(a), c.y() + self.INNER * math.sin(a)),
                             QtCore.QPointF(c.x() + self.RADIUS * math.cos(a), c.y() + self.RADIUS * math.sin(a)))
        font = painter.font()
        font.setPointSizeF(max(font.pointSizeF() * 0.8, 7))
        painter.setFont(font)
        for i, (key, label, icon_name, _) in enumerate(TOOLS):
            a = math.radians(i * step - 90)
            r = (self.RADIUS + self.INNER) / 2 + 4
            p = QtCore.QPointF(c.x() + r * math.cos(a), c.y() + r * math.sin(a))
            on = i == self.highlight
            pix = icons.icon(icon_name, icons.ON_DARK if on else icons.APP).pixmap(48, 48)
            painter.drawPixmap(QtCore.QRectF(p.x() - 12, p.y() - 18, 24, 24), pix, QtCore.QRectF(pix.rect()))
            painter.setPen(QtGui.QColor("white") if on else app)
            painter.drawText(QtCore.QRectF(p.x() - 45, p.y() + 6, 90, 16), QtCore.Qt.AlignmentFlag.AlignCenter,
                             f"{label.split()[0]} ({key})")
        inner = QtCore.QRectF(c.x() - self.INNER, c.y() - self.INNER, 2 * self.INNER, 2 * self.INNER)
        painter.setPen(QtGui.QPen(app, 1.5))
        painter.setBrush(QtGui.QColor(245, 245, 245))
        painter.drawEllipse(inner)
        x = icons.icon("x").pixmap(48, 48)
        painter.drawPixmap(QtCore.QRectF(c.x() - 10, c.y() - 10, 20, 20), x, QtCore.QRectF(x.rect()))
        painter.end()
