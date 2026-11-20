"""P9.10 / P9.11: the colour tools from anywhere – hotkeys, active-tool indicator, tool wheel.

Every entry does exactly what its button in the Color section does (the button is clicked), so the panel
section does not have to be visible. Hotkeys are single letters; they are ignored while a text or number
field has the keyboard focus (typing a text overlay must not switch tools).
"""
import math

from PyQt6 import QtCore, QtGui, QtWidgets

import icons
import theme

# key, label, icon, object name of the Color-section button
TOOLS = (
    ("D", "Draw", "draw", "toggle_draw_button"),
    ("F", "Fill", "fill", "flood_fill_button"),
    ("R", "Replace", "replace", "replace_color_button"),
    ("P", "Pick from image", "pick", "pick_color_from_image_button"),
    ("C", "More colors", "more-colors", "select_color_color_button"),
    ("T", "Transparent", "transparent", "transparent_color_button"),
)
TOOL_ICONS = {"Draw": "draw", "Fill": "fill", "Replace": "replace", "Pick": "pick", "Mask": "mask-rect",
              "": "tool-none"}
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
        painter.drawPixmap(QtCore.QRect(0, 0, size, size), icons.icon(TOOL_ICONS.get(tool, "tool-none")).pixmap(48, 48))
        swatch = QtCore.QRect(size + 4, 4, size - 8, size - 8)
        if rgba[3] == 0:  # transparent: checkerboard
            painter.fillRect(swatch, QtGui.QColor("white"))
            half = swatch.width() // 2
            painter.fillRect(swatch.x(), swatch.y(), half, half, QtGui.QColor("#BBBBBB"))
            painter.fillRect(swatch.x() + half, swatch.y() + half, swatch.width() - half, swatch.height() - half,
                             QtGui.QColor("#BBBBBB"))
        else:
            painter.fillRect(swatch, QtGui.QColor(*rgba[:3]))
        painter.setPen(QtGui.QColor(theme.TEXT_MUTED))
        painter.drawRect(swatch)
        painter.end()
        self.indicator.setPixmap(pixmap)
        keys = ", ".join(f"{key} {label.lower()}" for key, label, *_ in TOOLS)
        colour = "transparent" if rgba[3] == 0 else f"R{rgba[0]} G{rgba[1]} B{rgba[2]}"
        self.indicator.setToolTip(f"Active tool: {tool or 'none'} · color: {colour}\nHotkeys: {keys}")


# P11: canvas cursors – (cursor picture in GUI_Files/icons, hot spot = the pixel the tip points at)
CURSORS = {"Draw": ("cursor-draw", (1, 30)), "Fill": ("cursor-fill", (5, 26)),
           "Replace": ("cursor-replace", (1, 1)), "Pick": ("cursor-pick", (1, 30))}
CURSOR_SIZE = 32
TRANSPARENT_PAINT = "E0E0E0"  # paint colour shown for the transparent "colour"


def pen_footprint(x, y, width):
    """Image pixels a pen stroke of `width` covers around pixel (x, y): (left, top, size).

    The pen draws through pixel centres with square caps and no antialiasing; that covers a width x width square
    starting (width - 1) // 2 pixels left of / above the pixel (measured, see tests)."""
    width = max(int(width), 1)
    offset = (width - 1) // 2
    return x - offset, y - offset, width


def make_cursor(name, hot, paint_hex="000000", ratio=1.0):
    """QCursor from GUI_Files/icons/<name>.svg (currentColor = paint), with a white halo so it shows on any image."""
    from PyQt6.QtSvg import QSvgRenderer
    source = (icons.ICON_DIR / f"{name}.svg").read_text(encoding="utf-8").replace("currentColor", f"#{paint_hex}")
    renderer = QSvgRenderer(QtCore.QByteArray(source.encode("utf-8")))
    side = int(round(CURSOR_SIZE * ratio))

    def blank():
        pixmap = QtGui.QPixmap(side, side)
        pixmap.fill(QtCore.Qt.GlobalColor.transparent)
        return pixmap
    shape = blank()
    painter = QtGui.QPainter(shape)
    renderer.render(painter, QtCore.QRectF(0, 0, side, side))
    painter.end()
    halo = shape.copy()
    painter = QtGui.QPainter(halo)
    painter.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(halo.rect(), QtGui.QColor("white"))
    painter.end()
    result = blank()
    painter = QtGui.QPainter(result)
    step = max(1, int(round(ratio)))
    for dx in (-step, 0, step):
        for dy in (-step, 0, step):
            if dx or dy:
                painter.drawPixmap(dx, dy, halo)
    painter.drawPixmap(0, 0, shape)
    painter.end()
    result.setDevicePixelRatio(ratio)
    return QtGui.QCursor(result, hot[0], hot[1])


class CanvasCursors:
    """P11: the mouse over the image shows the active colour tool (draw / fill / replace / pick) with its tip
    exactly on the pixel that gets used; drawing also shows the outline of the pixels the pen will cover
    (an outline in image pixels, so it scales with the zoom)."""

    def __init__(self, gui, colorer, event_handler):
        self.gui = gui
        self.colorer = colorer
        self.viewport = gui.image_canvas.viewport()
        self.tool = None
        self.footprint = None   # (outer white, inner dark) outline items, children of the image item
        self.last_pos = None
        colorer.state_callbacks.append(self.update)
        gui.pen_width_spinbox.valueChanged.connect(lambda *_: self.move_footprint(self.last_pos))
        event_handler.add_canvas_event_filter(self.on_canvas_event)
        self.update()

    # --- cursor ---
    def paint_hex(self):
        rgba = self.colorer.active_color
        return TRANSPARENT_PAINT if rgba[3] == 0 else "{:02X}{:02X}{:02X}".format(*rgba[:3])

    def update(self):
        tool = self.colorer.active_tool
        if tool in CURSORS:
            name, hot = CURSORS[tool]
            self.viewport.setCursor(make_cursor(name, hot, self.paint_hex(), self.viewport.devicePixelRatioF()))
        elif self.tool in CURSORS:  # tool switched off: back to the arrow (masks set their own cursor)
            if tool == "":
                self.viewport.setCursor(QtCore.Qt.CursorShape.ArrowCursor)
        self.tool = tool
        self.move_footprint(self.last_pos)

    # --- pen outline ---
    def _footprint_items(self):
        alive = self.footprint is not None
        if alive:
            try:
                alive = self.footprint[0].scene() is not None and self.footprint[0].parentItem() is self.gui.image_item
            except RuntimeError:  # deleted with the scene
                alive = False
        if not alive:
            items = []
            for color, width in (("white", 3), ("#263238", 1)):
                item = QtWidgets.QGraphicsPathItem(self.gui.image_item)
                pen = QtGui.QPen(QtGui.QColor(color), width)
                pen.setCosmetic(True)  # always thin on screen; the outlined square itself is in image pixels
                pen.setJoinStyle(QtCore.Qt.PenJoinStyle.MiterJoin)
                item.setPen(pen)
                item.setZValue(1000)
                item.setAcceptedMouseButtons(QtCore.Qt.MouseButton.NoButton)
                items.append(item)
            self.footprint = tuple(items)
        return self.footprint

    def move_footprint(self, viewport_pos):
        """Outline the pixels the pen covers under `viewport_pos` (None: hide)."""
        show = viewport_pos is not None and self.tool == "Draw" and self.gui.image_item.pixmap() is not None \
            and not self.gui.image_item.pixmap().isNull()
        if not show:
            if self.footprint is not None:
                try:
                    for item in self.footprint:
                        item.hide()
                except RuntimeError:
                    self.footprint = None
            return
        scene_pos = self.gui.image_canvas.mapToScene(viewport_pos)
        pos = self.gui.image_item.mapFromScene(scene_pos)
        left, top, size = pen_footprint(math.floor(pos.x()), math.floor(pos.y()), self.gui.pen_width_spinbox.value())
        path = QtGui.QPainterPath()
        path.addRect(QtCore.QRectF(left, top, size, size))
        for item in self._footprint_items():
            item.setPath(path)
            item.show()

    def on_canvas_event(self, event):
        kind = event.type()
        if kind in (QtCore.QEvent.Type.MouseMove, QtCore.QEvent.Type.MouseButtonPress):
            self.last_pos = event.position().toPoint()
            self.move_footprint(self.last_pos)
        elif kind == QtCore.QEvent.Type.Leave:
            self.last_pos = None
            self.move_footprint(None)
        return False


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
        gold = QtGui.QColor(theme.GOLD)  # Atelier look: dark surface, gold accents
        c = self.centre
        outer = QtCore.QRectF(c.x() - self.RADIUS, c.y() - self.RADIUS, 2 * self.RADIUS, 2 * self.RADIUS)
        painter.setPen(QtGui.QPen(theme.GOLD_40, 1.5))
        surface = QtGui.QColor(theme.SURFACE)
        surface.setAlpha(240)
        painter.setBrush(surface)
        painter.drawEllipse(outer)
        step = 360 / len(TOOLS)
        if self.highlight is not None:  # highlighted sector (Qt angles: 0 = 3 o'clock, counter-clockwise)
            start = 90 - (self.highlight * step) - step / 2
            path = QtGui.QPainterPath(c)
            path.arcTo(outer, start, step)
            path.closeSubpath()
            painter.setPen(QtGui.QPen(gold, 1.5))
            painter.setBrush(QtGui.QColor(208, 167, 111, 60))
            painter.drawPath(path)
        painter.setPen(QtGui.QPen(theme.FROST, 1))
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
            pix = icons.icon(icon_name).pixmap(48, 48)
            painter.drawPixmap(QtCore.QRectF(p.x() - 12, p.y() - 18, 24, 24), pix, QtCore.QRectF(pix.rect()))
            painter.setPen(gold if on else QtGui.QColor(theme.TEXT_HIGH))
            painter.drawText(QtCore.QRectF(p.x() - 45, p.y() + 6, 90, 16), QtCore.Qt.AlignmentFlag.AlignCenter,
                             f"{label.split()[0]} ({key})")
        inner = QtCore.QRectF(c.x() - self.INNER, c.y() - self.INNER, 2 * self.INNER, 2 * self.INNER)
        painter.setPen(QtGui.QPen(theme.GOLD_40, 1.5))
        painter.setBrush(QtGui.QColor(theme.BG))
        painter.drawEllipse(inner)
        x = icons.icon("close").pixmap(48, 48)
        painter.drawPixmap(QtCore.QRectF(c.x() - 10, c.y() - 10, 20, 20), x, QtCore.QRectF(x.rect()))
        painter.end()
