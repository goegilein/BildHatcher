import math
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtGui import QPainterPath, QPen, QBrush, QColor, QFont, QFontDatabase
from PyQt6.QtWidgets import QGraphicsItem


def select_color() -> QtGui.QColor:
    """Open a color picker dialog and return the selected color."""
    color = QtWidgets.QColorDialog.getColor(QtGui.QColor(0, 0, 0), None, "Select Color")
    return color if color.isValid() else QtGui.QColor(0, 0, 0)


class OverlayItem(QtWidgets.QGraphicsItem):
    """Base overlay item with drag, selection, resize and rotation support."""

    HANDLE_RADIUS = 10.0
    ROTATE_HANDLE_OFFSET = 20.0

    def __init__(self, rect: QtCore.QRectF = QtCore.QRectF(0, 0, 100, 100), parent=None):
        super().__init__(parent)
        self._rect = QtCore.QRectF(rect)
        self.fill_color = QColor(0, 0, 0, 0)
        self.outline_color = QColor(0, 0, 0)
        self.outline_width = 1.0
        self._active_handle = None
        self._mouse_down_pos = QtCore.QPointF()
        self._start_rect = QtCore.QRectF(self._rect)
        self._start_rotation = 0.0
        self.setFlags(
            QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
            QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
            QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)
        self.update_transform_origin()

    def update_transform_origin(self):
        self.setTransformOriginPoint(self._rect.center())

    def boundingRect(self) -> QtCore.QRectF:
        extra = self.HANDLE_RADIUS + self.outline_width
        rect = QtCore.QRectF(self._rect)
        rect.adjust(-extra, -extra - self.ROTATE_HANDLE_OFFSET, extra, extra)
        return rect

    def shape(self) -> QtGui.QPainterPath:
        path = QPainterPath()
        path.addRect(self._rect)
        return path

    def paint(self, painter: QtGui.QPainter, option, widget=None):
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        if self.fill_color.alpha() > 0:
            painter.fillRect(self._rect, QBrush(self.fill_color))

        pen = QPen(self.outline_color, self.outline_width)
        painter.setPen(pen)
        painter.drawRect(self._rect)

        if self.isSelected():
            self.paint_selection(painter)

    def paint_selection(self, painter: QtGui.QPainter):
        selection_pen = QPen(QColor(0, 120, 215), 1, QtCore.Qt.PenStyle.DashLine)
        painter.setPen(selection_pen)
        painter.drawRect(self._rect)
        for handle_rect in self.handle_rects().values():
            painter.setBrush(QBrush(QColor(255, 255, 255)))
            painter.setPen(QPen(QColor(0, 0, 0), 1))
            painter.drawEllipse(handle_rect)

    def handle_rects(self) -> dict[str, QtCore.QRectF]:
        s = self.HANDLE_RADIUS * 2
        rect = self._rect
        cx = rect.center().x()
        top_left = QtCore.QPointF(rect.left(), rect.top())
        top_right = QtCore.QPointF(rect.right(), rect.top())
        bottom_left = QtCore.QPointF(rect.left(), rect.bottom())
        bottom_right = QtCore.QPointF(rect.right(), rect.bottom())

        return {
            'top_left': QtCore.QRectF(top_left.x() - self.HANDLE_RADIUS, top_left.y() - self.HANDLE_RADIUS, s, s),
            'top_right': QtCore.QRectF(top_right.x() - self.HANDLE_RADIUS, top_right.y() - self.HANDLE_RADIUS, s, s),
            'bottom_left': QtCore.QRectF(bottom_left.x() - self.HANDLE_RADIUS, bottom_left.y() - self.HANDLE_RADIUS, s, s),
            'bottom_right': QtCore.QRectF(bottom_right.x() - self.HANDLE_RADIUS, bottom_right.y() - self.HANDLE_RADIUS, s, s),
            'rotate': QtCore.QRectF(cx - self.HANDLE_RADIUS, rect.top() - self.ROTATE_HANDLE_OFFSET - self.HANDLE_RADIUS, s, s)
        }

    def hoverMoveEvent(self, event: QtWidgets.QGraphicsSceneHoverEvent):
        if self.isSelected() and self.hit_test_handle(event.pos()):
            self.setCursor(QtCore.Qt.CursorShape.SizeAllCursor)
        else:
            self.setCursor(QtCore.Qt.CursorShape.OpenHandCursor)
        super().hoverMoveEvent(event)

    def hit_test_handle(self, pos: QtCore.QPointF) -> str | None:
        for name, rect in self.handle_rects().items():
            if rect.contains(pos):
                return name
        return None

    def mousePressEvent(self, event: QtWidgets.QGraphicsSceneMouseEvent):
        if self.isSelected():
            handle_name = self.hit_test_handle(event.pos())
            if handle_name:
                self._active_handle = handle_name
                self._mouse_down_pos = event.pos()
                self._start_rect = QtCore.QRectF(self._rect)
                self._start_rotation = self.rotation()
                event.accept()
                return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtWidgets.QGraphicsSceneMouseEvent):
        if self._active_handle == 'rotate':
            self.do_rotate(event.pos())
            event.accept()
            return

        if self._active_handle in {'top_left', 'top_right', 'bottom_left', 'bottom_right'}:
            self.do_resize(event.pos())
            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QtWidgets.QGraphicsSceneMouseEvent):
        self._active_handle = None
        super().mouseReleaseEvent(event)

    def do_rotate(self, pos: QtCore.QPointF):
        center = self._rect.center()
        delta_angle = math.degrees(math.atan2(pos.y() - center.y(), pos.x() - center.x()) -
                                   math.atan2(self._mouse_down_pos.y() - center.y(), self._mouse_down_pos.x() - center.x()))
        self.setRotation(self._start_rotation + delta_angle)

    def do_resize(self, pos: QtCore.QPointF):
        rect = QtCore.QRectF(self._start_rect)
        delta = pos - self._mouse_down_pos

        if self._active_handle == 'top_left':
            rect.setTopLeft(rect.topLeft() + delta)
        elif self._active_handle == 'top_right':
            rect.setTopRight(rect.topRight() + delta)
        elif self._active_handle == 'bottom_left':
            rect.setBottomLeft(rect.bottomLeft() + delta)
        elif self._active_handle == 'bottom_right':
            rect.setBottomRight(rect.bottomRight() + delta)

        if rect.width() < 10:
            rect.setWidth(10)
        if rect.height() < 10:
            rect.setHeight(10)

        self.prepareGeometryChange()
        self._rect = rect.normalized()
        self.update_transform_origin()
        self.update()

    def paint_to_painter(self, painter: QtGui.QPainter):
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        if self.fill_color.alpha() > 0:
            painter.fillRect(self._rect, QBrush(self.fill_color))
        pen = QPen(self.outline_color, self.outline_width)
        painter.setPen(pen)
        painter.drawRect(self._rect)

    def resize_by_pixels(self, width: float, height: float):
        rect = QtCore.QRectF(self._rect)
        rect.setWidth(max(width, 1.0))
        rect.setHeight(max(height, 1.0))
        self.prepareGeometryChange()
        self._rect = rect
        self.update_transform_origin()
        self.update()

    def resize_by_mm(self, width_mm: float, height_mm: float, pixel_per_mm: float):
        self.resize_by_pixels(width_mm * pixel_per_mm, height_mm * pixel_per_mm)

    def dimensions_in_mm(self, pixel_per_mm: float) -> tuple[float, float]:
        return self._rect.width() / pixel_per_mm, self._rect.height() / pixel_per_mm

    def set_fill_color(self, color: QtGui.QColor | tuple | list):
        self.fill_color = QColor(*color) if not isinstance(color, QColor) else color
        self.update()

    def set_outline_color(self, color: QtGui.QColor | tuple | list, width: float = 1.0):
        self.outline_color = QColor(*color) if not isinstance(color, QColor) else color
        self.outline_width = width
        self.update()


class TextFieldOverlay(OverlayItem):
    """A selectable text field overlay with formatting and outline support."""

    def __init__(
        self,
        rect: QtCore.QRectF = QtCore.QRectF(0, 0, 180, 90),
        text: str = "Text",
        font_family: str = "Arial",
        font_size: int = 24,
        bold: bool = False,
        italic: bool = False,
        underline: bool = False,
        strike_out: bool = False,
        text_color: QtGui.QColor | tuple | list = (0, 0, 0),
        outline_color: QtGui.QColor | tuple | list | None = None,
        outline_width: float = 0.0,
        parent=None,
    ):
        super().__init__(rect, parent)
        self.text = text
        self.font = QFont(font_family, font_size)
        self.font.setBold(bold)
        self.font.setItalic(italic)
        self.font.setUnderline(underline)
        self.font.setStrikeOut(strike_out)
        self.text_color = QColor(*text_color) if not isinstance(text_color, QColor) else text_color
        self.text_outline_color = QColor(*outline_color) if outline_color is not None and not isinstance(outline_color, QColor) else outline_color or QColor(0, 0, 0, 0)
        self.text_outline_width = outline_width

    def paint(self, painter: QtGui.QPainter, option, widget=None):
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        if self.fill_color.alpha() > 0:
            painter.fillRect(self._rect, QBrush(self.fill_color))

        if self.isSelected():
            self.paint_selection(painter)

        # Draw text
        if self.text:
            painter.setFont(self.font)
            text_rect = self._rect.adjusted(2, 2, -2, -2)
            if self.text_outline_width > 0 and self.text_outline_color.alpha() > 0:
                # Draw outline
                painter.setPen(QPen(self.text_outline_color, self.text_outline_width))
                painter.drawText(text_rect, QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignTop, self.text)
            # Draw fill
            painter.setPen(QPen(self.text_color, 0))
            painter.drawText(text_rect, QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignTop, self.text)

    def paint_to_painter(self, painter: QtGui.QPainter):
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        if self.fill_color.alpha() > 0:
            painter.fillRect(self._rect, QBrush(self.fill_color))
        # Draw text
        if self.text:
            painter.setFont(self.font)
            text_rect = self._rect.adjusted(2, 2, -2, -2)
            if self.text_outline_width > 0 and self.text_outline_color.alpha() > 0:
                # Draw outline
                painter.setPen(QPen(self.text_outline_color, self.text_outline_width))
                painter.drawText(text_rect, QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignTop, self.text)
            # Draw fill
            painter.setPen(QPen(self.text_color, 0))
            painter.drawText(text_rect, QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignTop, self.text)

    def text_path(self) -> QPainterPath:
        path = QPainterPath()
        if not self.text:
            return path

        painter_font_metrics = QtGui.QFontMetricsF(self.font)
        line_height = painter_font_metrics.lineSpacing()
        x = self._rect.left() + 2
        y = self._rect.top() + painter_font_metrics.ascent() + 2

        for line_index, line in enumerate(self.text.splitlines() or [""]):
            path.addText(x, y + line_index * line_height, self.font, line)

        return path

    def set_text(self, text: str):
        self.text = text
        self.update()

    def set_font_family(self, family: str):
        self.font.setFamily(family)
        self.update()

    def set_font_size(self, size: int):
        self.font.setPointSize(size)
        self.update()

    def set_text_style(self, bold: bool = False, italic: bool = False, underline: bool = False, strike_out: bool = False):
        self.font.setBold(bold)
        self.font.setItalic(italic)
        self.font.setUnderline(underline)
        self.font.setStrikeOut(strike_out)
        self.update()

    def set_text_color(self, color: QtGui.QColor | tuple | list):
        self.text_color = QColor(*color) if not isinstance(color, QColor) else color
        self.update()

    def set_text_outline(self, color: QtGui.QColor | tuple | list, width: float = 1.0):
        self.text_outline_color = QColor(*color) if not isinstance(color, QColor) else color
        self.text_outline_width = width
        self.update()

    @staticmethod
    def available_fonts() -> list[str]:
        return QFontDatabase.families()


class GeometryOverlay(OverlayItem):
    """A selectable geometry overlay with fill and outline options."""

    VALID_SHAPES = {'line', 'rectangle', 'triangle', 'ellipse'}

    def __init__(
        self,
        shape_type: str = 'rectangle',
        rect: QtCore.QRectF = QtCore.QRectF(0, 0, 120, 80),
        fill_color: QtGui.QColor | tuple | list = (0, 0, 0, 0),
        outline_color: QtGui.QColor | tuple | list = (0, 0, 0),
        outline_width: float = 1.0,
        parent=None,
    ):
        super().__init__(rect, parent)
        if shape_type not in self.VALID_SHAPES:
            raise ValueError(f"Unsupported shape_type '{shape_type}'. Choose one of {self.VALID_SHAPES}.")
        self.shape_type = shape_type
        self.fill_color = QColor(*fill_color) if not isinstance(fill_color, QColor) else fill_color
        self.outline_color = QColor(*outline_color) if not isinstance(outline_color, QColor) else outline_color
        self.outline_width = outline_width

    def shape_path(self) -> QPainterPath:
        path = QPainterPath()
        if self.shape_type == 'rectangle':
            path.addRect(self._rect)
        elif self.shape_type == 'ellipse':
            path.addEllipse(self._rect)
        elif self.shape_type == 'triangle':
            points = [
                QtCore.QPointF(self._rect.center().x(), self._rect.top()),
                QtCore.QPointF(self._rect.right(), self._rect.bottom()),
                QtCore.QPointF(self._rect.left(), self._rect.bottom()),
            ]
            polygon = QtGui.QPolygonF(points)
            path.addPolygon(polygon)
        elif self.shape_type == 'line':
            path.moveTo(self._rect.topLeft())
            path.lineTo(self._rect.bottomRight())
        return path

    def paint(self, painter: QtGui.QPainter, option, widget=None):
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        path = self.shape_path()
        if self.shape_type != 'line' and self.fill_color.alpha() > 0:
            painter.fillPath(path, QBrush(self.fill_color))

        pen = QPen(self.outline_color, self.outline_width)
        painter.setPen(pen)
        painter.drawPath(path)

        if self.isSelected():
            self.paint_selection(painter)

    def paint_to_painter(self, painter: QtGui.QPainter):
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        path = self.shape_path()
        if self.shape_type != 'line' and self.fill_color.alpha() > 0:
            painter.fillPath(path, QBrush(self.fill_color))
        pen = QPen(self.outline_color, self.outline_width)
        painter.setPen(pen)
        painter.drawPath(path)

    def set_shape_type(self, shape_type: str):
        if shape_type not in self.VALID_SHAPES:
            raise ValueError(f"Unsupported shape_type '{shape_type}'. Choose one of {self.VALID_SHAPES}.")
        self.shape_type = shape_type
        self.update()

    def set_fill_color(self, color: QtGui.QColor | tuple | list):
        self.fill_color = QColor(*color) if not isinstance(color, QColor) else color
        self.update()

    def set_outline_color(self, color: QtGui.QColor | tuple | list, width: float = 1.0):
        self.outline_color = QColor(*color) if not isinstance(color, QColor) else color
        self.outline_width = width
        self.update()


class OverlayStore:
    """Manages persistent text and geometry overlays for a given image item."""

    def __init__(self, parent_graphics_item: QtWidgets.QGraphicsItem | None = None):
        self.parent_graphics_item = parent_graphics_item
        self.text_items: list[TextFieldOverlay] = []
        self.geometry_items: list[GeometryOverlay] = []
        self.active_item: QtWidgets.QGraphicsItem | None = None

    def add_text_field(self, *args, **kwargs) -> TextFieldOverlay:
        text_item = TextFieldOverlay(*args, **kwargs)
        if self.parent_graphics_item is not None:
            text_item.setParentItem(self.parent_graphics_item)
        self.text_items.append(text_item)
        self.active_item = text_item
        text_item.setSelected(True)
        return text_item

    def add_geometry_item(self, *args, **kwargs) -> GeometryOverlay:
        geo_item = GeometryOverlay(*args, **kwargs)
        if self.parent_graphics_item is not None:
            geo_item.setParentItem(self.parent_graphics_item)
        self.geometry_items.append(geo_item)
        self.active_item = geo_item
        geo_item.setSelected(True)
        return geo_item

    def select_item(self, item: QtWidgets.QGraphicsItem | None):
        if self.active_item is not None:
            self.active_item.setSelected(False)
        self.active_item = item
        if item is not None:
            item.setSelected(True)

    def remove_item(self, item: QtWidgets.QGraphicsItem):
        if item in self.text_items:
            self.text_items.remove(item)
        if item in self.geometry_items:
            self.geometry_items.remove(item)
        if self.active_item is item:
            self.active_item = None
        if item.scene() is not None:
            item.scene().removeItem(item)

    def clear_all(self):
        for item in list(self.text_items) + list(self.geometry_items):
            if item.scene() is not None:
                item.scene().removeItem(item)
        self.text_items.clear()
        self.geometry_items.clear()
        self.active_item = None

    def all_items(self) -> list[QtWidgets.QGraphicsItem]:
        return list(self.text_items) + list(self.geometry_items)


class TextGeometryOverlayManager:
    """UI handler for creating and editing text/geometry overlays on the canvas."""

    # Drawing modes
    MODE_IDLE = 'idle'
    MODE_ADD_TEXT = 'add_text'
    MODE_ADD_GEOMETRY = 'add_geometry'

    def __init__(self, data_handler, overlay_store: OverlayStore, gui, event_handler):
        self.data_handler = data_handler
        self.overlay_store = overlay_store
        self.gui = gui
        self.event_handler = event_handler
        self.mode = self.MODE_IDLE
        self.current_geometry_type = 'rectangle'
        self.drag_start_pos = QtCore.QPointF()
        self.drag_item = None

        # add text button
        self.add_text_button = gui.add_text_button
        self.add_text_button.clicked.connect(lambda: self.set_add_text_mode(self.add_text_button.isChecked()))
        self.add_text_button.setCheckable(True)

        #add geometry button
        self.add_geometry_button = gui.add_geometry_button
        self.add_geometry_button.clicked.connect(lambda: self.set_add_geometry_mode(self.add_geometry_button.isChecked()))
        self.add_geometry_button.setCheckable(True)

        #geometry type combobox
        self.geometry_type_combobox = gui.geometry_type_combobox 
        self.geometry_type_combobox.addItems(["Line", "Rectangle", "Triangle", "Ellipse"])
        self.geometry_type_combobox.currentTextChanged.connect(lambda text: self.set_geometry_type(text.lower()))

        #font family combobox
        self.font_family_combobox = gui.font_family_combobox
        self.font_family_combobox.addItems(TextFieldOverlay.available_fonts())
        self.font_family_combobox.currentTextChanged.connect(self._on_font_family_changed)

        #font size spinbox
        self.font_size_spinbox = gui.font_size_spinbox
        self.font_size_spinbox.setRange(1, 1000)
        self.font_size_spinbox.setValue(24)
        self.font_size_spinbox.valueChanged.connect(self._on_font_size_changed)

        #text style checkboxes
        self.text_bold_checkbox = gui.text_bold_checkbox
        self.text_italic_checkbox = gui.text_italic_checkbox
        self.text_underline_checkbox = gui.text_underline_checkbox
        self.text_strike_checkbox = gui.text_strike_checkbox
        self.text_bold_checkbox.toggled.connect(self._on_text_style_changed)
        self.text_italic_checkbox.toggled.connect(self._on_text_style_changed)
        self.text_underline_checkbox.toggled.connect(self._on_text_style_changed)
        self.text_strike_checkbox.toggled.connect(self._on_text_style_changed)

        #color buttons and spinboxes
        self.text_color_button = gui.text_color_button
        self.text_color_button.clicked.connect(lambda: self.set_text_color(select_color()))

        #text outline color button and width
        self.text_outline_color_button = gui.text_outline_color_button
        self.text_outline_color_button.clicked.connect(lambda: self.set_text_outline_color(select_color()))

        #text outline width spinbox
        self.text_outline_width_spinbox = gui.text_outline_width_spinbox
        self.text_outline_width_spinbox.valueChanged.connect(self._on_text_outline_width_changed)

        #fill color button
        self.fill_color_button = gui.fill_color_button
        self.fill_color_button.clicked.connect(lambda: self.set_fill_color(select_color()))

        #outline color button
        self.outline_color_button = gui.outline_color_button
        self.outline_color_button.clicked.connect(lambda: self.set_outline_color(select_color()))

        #outline width spinbox
        self.outline_width_spinbox = gui.outline_width_spinbox 
        self.outline_width_spinbox.valueChanged.connect(self._on_outline_width_changed)

        #overlay list widget
        self.overlay_list_widget = gui.overlay_list_widget
        self.overlay_list_widget.itemSelectionChanged.connect(self._on_overlay_selected)

        #delete overlay button
        self.delete_overlay_button = gui.delete_overlay_button
        self.delete_overlay_button.clicked.connect(self.delete_active_overlay)

        #overlay dimension spinboxes
        self.width_mm_spinbox = gui.width_mm_spinbox
        self.height_mm_spinbox = gui.height_mm_spinbox 
        self.width_mm_spinbox.valueChanged.connect(lambda: self.set_overlay_dimensions_mm(self.width_mm_spinbox.value(), self.height_mm_spinbox.value()))
        self.height_mm_spinbox.valueChanged.connect(lambda: self.set_overlay_dimensions_mm(self.width_mm_spinbox.value(), self.height_mm_spinbox.value()))

        #text input lineedit
        self.text_input_lineedit = gui.text_input_lineedit
        self.text_input_lineedit.textChanged.connect(self._on_text_input_changed)



        # Current colors (defaults)
        self.current_text_color = QtGui.QColor(0, 0, 0)
        self.current_text_outline_color = QtGui.QColor(0, 0, 0, 0)
        self.current_fill_color = QtGui.QColor(0, 0, 0, 0)
        self.current_outline_color = QtGui.QColor(0, 0, 0)

        # Wire up event handler if available
        if event_handler:
            event_handler.add_canvas_event_callback(self.on_canvas_event)

    def on_canvas_event(self, event):
        """Handle canvas mouse events for drawing overlays."""
        if event.type() == QtCore.QEvent.Type.MouseButtonPress and event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.on_canvas_press(event)
        elif event.type() == QtCore.QEvent.Type.MouseMove and event.buttons() == QtCore.Qt.MouseButton.LeftButton:
            self.on_canvas_drag(event)
        elif event.type() == QtCore.QEvent.Type.MouseButtonRelease and event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.on_canvas_release(event)

    def on_canvas_press(self, event):
        """Start drawing a new overlay or select existing one."""
        if self.mode == self.MODE_IDLE:
            # Check if clicking on existing overlay
            items = self.gui.image_canvas.items(event.pos())
            for item in items:
                if item in self.overlay_store.all_items():
                    self.overlay_store.select_item(item)
                    self._update_ui_from_selected()
                    return

        if self.mode == self.MODE_ADD_TEXT:
            pos_canvas = event.pos()
            x_scene, y_scene = self.data_handler.canvas_to_scene_coords(pos_canvas.x(), pos_canvas.y())
            self.drag_start_pos_scene = QtCore.QPointF(x_scene, y_scene)
            self.drag_item = self.overlay_store.add_text_field(
                rect=QtCore.QRectF(0, 0, 1, 1),
                text=self.text_input_lineedit.text() if self.text_input_lineedit else "Text"
            )
            self.drag_item.setPos(self.drag_start_pos_scene)
            self._apply_text_formatting()
            self._update_overlay_list()

        elif self.mode == self.MODE_ADD_GEOMETRY:
            pos_canvas = event.pos()
            x_scene, y_scene = self.data_handler.canvas_to_scene_coords(pos_canvas.x(), pos_canvas.y())
            self.drag_start_pos_scene = QtCore.QPointF(x_scene, y_scene)
            self.drag_item = self.overlay_store.add_geometry_item(
                shape_type=self.current_geometry_type,
                rect=QtCore.QRectF(0, 0, 1, 1),
                fill_color=self.current_fill_color,
                outline_color=self.current_outline_color
            )
            self.drag_item.setPos(self.drag_start_pos_scene)
            self._update_overlay_list()

    def on_canvas_drag(self, event):
        """Resize the overlay being drawn."""
        if self.drag_item is None or self.mode == self.MODE_IDLE:
            return

        pos_canvas = event.pos()
        x_scene, y_scene = self.data_handler.canvas_to_scene_coords(pos_canvas.x(), pos_canvas.y())
        
        x_start = self.drag_start_pos_scene.x()
        y_start = self.drag_start_pos_scene.y()
        width = x_scene - x_start
        height = y_scene - y_start

        self.drag_item.prepareGeometryChange()
        self.drag_item._rect = QtCore.QRectF(0, 0, width, height)
        self.drag_item.update_transform_origin()
        self.drag_item.update()
        self.gui.image_canvas.update()

    def on_canvas_release(self, event):
        """Finish drawing the overlay and add it to data_handler."""
        if self.drag_item is None:
            return

        self.drag_item = None
        if self.mode in {self.MODE_ADD_TEXT, self.MODE_ADD_GEOMETRY}:
            if self.overlay_store.active_item:
                self.data_handler.text_overlays.extend([x for x in self.overlay_store.text_items if x not in self.data_handler.text_overlays])
                self.data_handler.geometry_overlays.extend([x for x in self.overlay_store.geometry_items if x not in self.data_handler.geometry_overlays])

    def _apply_text_formatting(self):
        """Apply current text formatting to the active text overlay."""
        if not isinstance(self.overlay_store.active_item, TextFieldOverlay):
            return

        item = self.overlay_store.active_item
        
        if self.font_size_spinbox:
            item.set_font_size(self.font_size_spinbox.value())
        if self.font_family_combobox:
            item.set_font_family(self.font_family_combobox.currentText())

        bold = self.text_bold_checkbox.isChecked() if self.text_bold_checkbox else False
        italic = self.text_italic_checkbox.isChecked() if self.text_italic_checkbox else False
        underline = self.text_underline_checkbox.isChecked() if self.text_underline_checkbox else False
        strike = self.text_strike_checkbox.isChecked() if self.text_strike_checkbox else False
        item.set_text_style(bold, italic, underline, strike)

        item.set_text_color(self.current_text_color)
        if self.current_text_outline_color.alpha() > 0:
            width = self.text_outline_width_spinbox.value() if self.text_outline_width_spinbox else 1.0
            item.set_text_outline(self.current_text_outline_color, width)

    def set_add_text_mode(self, enabled: bool):
        """Toggle text field drawing mode."""
        if enabled:
            self.mode = self.MODE_ADD_TEXT
            self.gui.image_canvas.viewport().setCursor(QtCore.Qt.CursorShape.CrossCursor)
        else:
            if self.mode == self.MODE_ADD_TEXT:
                self.mode = self.MODE_IDLE
                self.gui.image_canvas.viewport().setCursor(QtCore.Qt.CursorShape.ArrowCursor)

    def set_add_geometry_mode(self, enabled: bool):
        """Toggle geometry drawing mode."""
        if enabled:
            self.mode = self.MODE_ADD_GEOMETRY
            self.gui.image_canvas.viewport().setCursor(QtCore.Qt.CursorShape.CrossCursor)
        else:
            if self.mode == self.MODE_ADD_GEOMETRY:
                self.mode = self.MODE_IDLE
                self.gui.image_canvas.viewport().setCursor(QtCore.Qt.CursorShape.ArrowCursor)

    def set_geometry_type(self, geom_type: str):
        """Set the current geometry type to draw."""
        if geom_type in GeometryOverlay.VALID_SHAPES:
            self.current_geometry_type = geom_type
            if isinstance(self.overlay_store.active_item, GeometryOverlay):
                self.overlay_store.active_item.set_shape_type(geom_type)

    def set_text_color(self, color: QtGui.QColor):
        """Set the active text color."""
        self.current_text_color = color
        if isinstance(self.overlay_store.active_item, TextFieldOverlay):
            self.overlay_store.active_item.set_text_color(color)

    def set_text_outline_color(self, color: QtGui.QColor, width: float = 1.0):
        """Set the active text outline."""
        self.current_text_outline_color = color
        if isinstance(self.overlay_store.active_item, TextFieldOverlay):
            self.overlay_store.active_item.set_text_outline(color, width)

    def set_fill_color(self, color: QtGui.QColor):
        """Set the active fill color."""
        self.current_fill_color = color
        if isinstance(self.overlay_store.active_item, (GeometryOverlay, TextFieldOverlay)):
            self.overlay_store.active_item.set_fill_color(color)

    def set_outline_color(self, color: QtGui.QColor, width: float = 1.0):
        """Set the active outline color."""
        self.current_outline_color = color
        if isinstance(self.overlay_store.active_item, (GeometryOverlay, TextFieldOverlay)):
            self.overlay_store.active_item.set_outline_color(color, width)

    def set_overlay_dimensions_mm(self, width_mm: float, height_mm: float):
        """Resize active overlay by millimeters."""
        if self.overlay_store.active_item and self.data_handler.pixel_per_mm:
            self.overlay_store.active_item.resize_by_mm(width_mm, height_mm, self.data_handler.pixel_per_mm)
            self._update_ui_from_selected()

    def delete_active_overlay(self):
        """Remove the currently selected overlay."""
        if self.overlay_store.active_item:
            self.overlay_store.remove_item(self.overlay_store.active_item)
            self._update_overlay_list()

    def _update_overlay_list(self):
        """Refresh the overlay list widget display."""
        if not self.overlay_list_widget:
            return

        self.overlay_list_widget.clear()
        for i, item in enumerate(self.overlay_store.text_items):
            text = f"Text {i+1}: {item.text[:20]}"
            list_item = QtWidgets.QListWidgetItem(text)
            list_item.setData(QtCore.Qt.ItemDataRole.UserRole, item)
            self.overlay_list_widget.addItem(list_item)

        for i, item in enumerate(self.overlay_store.geometry_items):
            text = f"Geometry {i+1}: {item.shape_type}"
            list_item = QtWidgets.QListWidgetItem(text)
            list_item.setData(QtCore.Qt.ItemDataRole.UserRole, item)
            self.overlay_list_widget.addItem(list_item)

    def _on_font_size_changed(self):
        """Update font size of active text overlay."""
        if isinstance(self.overlay_store.active_item, TextFieldOverlay) and self.font_size_spinbox:
            self.overlay_store.active_item.set_font_size(self.font_size_spinbox.value())

    def _on_font_family_changed(self):
        """Update font family of active text overlay."""
        if isinstance(self.overlay_store.active_item, TextFieldOverlay) and self.font_family_combobox:
            self.overlay_store.active_item.set_font_family(self.font_family_combobox.currentText())

    def _on_text_style_changed(self):
        """Update text style (bold, italic, etc.) of active text overlay."""
        if isinstance(self.overlay_store.active_item, TextFieldOverlay):
            bold = self.text_bold_checkbox.isChecked() if self.text_bold_checkbox else False
            italic = self.text_italic_checkbox.isChecked() if self.text_italic_checkbox else False
            underline = self.text_underline_checkbox.isChecked() if self.text_underline_checkbox else False
            strike = self.text_strike_checkbox.isChecked() if self.text_strike_checkbox else False
            self.overlay_store.active_item.set_text_style(bold, italic, underline, strike)

    def _on_text_outline_width_changed(self):
        """Update text outline width of active text overlay."""
        if isinstance(self.overlay_store.active_item, TextFieldOverlay) and self.text_outline_width_spinbox:
            width = self.text_outline_width_spinbox.value()
            if width > 0 and self.current_text_outline_color.alpha() == 0:
                self.current_text_outline_color = QColor(0, 0, 0)  # default to black if transparent
            self.overlay_store.active_item.set_text_outline(self.current_text_outline_color, width)

    def _on_outline_width_changed(self):
        """Update outline width of active geometry overlay."""
        if isinstance(self.overlay_store.active_item, (GeometryOverlay, TextFieldOverlay)) and self.outline_width_spinbox:
            width = self.outline_width_spinbox.value()
            self.overlay_store.active_item.set_outline_color(self.current_outline_color, width)

    def _on_overlay_selected(self):
        """Handle overlay selection from list widget."""
        if not self.overlay_list_widget:
            return

        selected_items = self.overlay_list_widget.selectedItems()
        if selected_items:
            item = selected_items[0].data(QtCore.Qt.ItemDataRole.UserRole)
            self.overlay_store.select_item(item)
            self._update_ui_from_selected()

    def _on_text_input_changed(self):
        """Update text content of active text overlay."""
        if isinstance(self.overlay_store.active_item, TextFieldOverlay) and self.text_input_lineedit:
            self.overlay_store.active_item.set_text(self.text_input_lineedit.text())

    def _update_ui_from_selected(self):
        """Update UI controls to reflect active overlay properties."""
        item = self.overlay_store.active_item
        if not item:
            return

        if isinstance(item, TextFieldOverlay):
            if self.font_size_spinbox:
                self.font_size_spinbox.setValue(item.font.pointSize())
            if self.font_family_combobox:
                self.font_family_combobox.setCurrentText(item.font.family())
            if self.text_bold_checkbox:
                self.text_bold_checkbox.setChecked(item.font.bold())
            if self.text_italic_checkbox:
                self.text_italic_checkbox.setChecked(item.font.italic())
            if self.text_underline_checkbox:
                self.text_underline_checkbox.setChecked(item.font.underline())
            if self.text_strike_checkbox:
                self.text_strike_checkbox.setChecked(item.font.strikeOut())
            if self.text_input_lineedit:
                self.text_input_lineedit.setText(item.text)
            if self.outline_width_spinbox:
                self.outline_width_spinbox.setValue(item.outline_width)
            if self.text_outline_width_spinbox:
                self.text_outline_width_spinbox.setValue(item.text_outline_width)
            # Update current colors
            self.current_text_color = item.text_color
            self.current_text_outline_color = item.text_outline_color
            self.current_fill_color = item.fill_color
            self.current_outline_color = item.outline_color

        if isinstance(item, GeometryOverlay):
            if self.geometry_type_combobox:
                idx = self.geometry_type_combobox.findText(item.shape_type.capitalize())
                if idx >= 0:
                    self.geometry_type_combobox.setCurrentIndex(idx)
            if self.outline_width_spinbox:
                self.outline_width_spinbox.setValue(item.outline_width)
            # Update current colors
            self.current_fill_color = item.fill_color
            self.current_outline_color = item.outline_color

        if self.data_handler.pixel_per_mm:
            w_mm, h_mm = item.dimensions_in_mm(self.data_handler.pixel_per_mm)
            if self.width_mm_spinbox:
                self.width_mm_spinbox.setValue(w_mm)
            if self.height_mm_spinbox:
                self.height_mm_spinbox.setValue(h_mm)
