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
        self._moving_items = False
        self._drag_start_parent_pos = QtCore.QPointF()
        self._drag_start_item_positions = {}
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
        # Support Shift-clicking to toggle/add selection without clearing others
        if event.modifiers() & QtCore.Qt.KeyboardModifier.ShiftModifier:
            self.setSelected(not self.isSelected())
            event.accept()
            return

        if self.isSelected():
            handle_name = self.hit_test_handle(event.pos())
            if handle_name:
                self._active_handle = handle_name
                self._mouse_down_pos = event.pos()
                self._start_rect = QtCore.QRectF(self._rect)
                self._start_rotation = self.rotation()
                event.accept()
                return
            else:
                # Body click on an already selected item!
                # We start moving all selected items manually to prevent QGraphicsScene from clearing the selection.
                self._moving_items = True
                if self.parentItem() is not None:
                    self._drag_start_parent_pos = self.parentItem().mapFromScene(event.scenePos())
                else:
                    self._drag_start_parent_pos = event.scenePos()
                
                self._drag_start_item_positions = {}
                if self.scene() is not None:
                    selected = self.scene().selectedItems()
                    for item in selected:
                        if isinstance(item, OverlayItem):
                            self._drag_start_item_positions[item] = item.pos()
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

        if getattr(self, '_moving_items', False):
            if self.parentItem() is not None:
                current_parent_pos = self.parentItem().mapFromScene(event.scenePos())
            else:
                current_parent_pos = event.scenePos()
            delta = current_parent_pos - self._drag_start_parent_pos
            for item, start_pos in self._drag_start_item_positions.items():
                item.setPos(start_pos + delta)
            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QtWidgets.QGraphicsSceneMouseEvent):
        self._active_handle = None
        self._moving_items = False
        self._drag_start_item_positions = {}
        super().mouseReleaseEvent(event)

        # Trigger a full UI update on release to ensure everything is perfectly synced
        scene = self.scene()
        if scene and hasattr(scene, 'tg_manager') and scene.tg_manager:
            scene.tg_manager._update_ui_from_selected()

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

        # Update the UI spinboxes in real time while dragging
        scene = self.scene()
        if scene and hasattr(scene, 'tg_manager') and scene.tg_manager:
            scene.tg_manager._update_ui_dimensions_only(self)

    def paint_to_painter(self, painter: QtGui.QPainter):
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, False)
        fill_color = QColor(self.fill_color)
        if fill_color.alpha() > 0:
            fill_color.setAlpha(255)
            painter.fillRect(self._rect, QBrush(fill_color))
        outline_color = QColor(self.outline_color)
        if outline_color.alpha() > 0:
            outline_color.setAlpha(255)
        pen = QPen(outline_color, self.outline_width)
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
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, False)
        painter.setRenderHint(QtGui.QPainter.RenderHint.TextAntialiasing, False)
        fill_color = QColor(self.fill_color)
        if fill_color.alpha() > 0:
            fill_color.setAlpha(255)
            painter.fillRect(self._rect, QBrush(fill_color))
        # Draw text
        if self.text:
            font = QFont(self.font)
            font.setStyleStrategy(QFont.StyleStrategy.NoAntialias)
            painter.setFont(font)
            text_rect = self._rect.adjusted(2, 2, -2, -2)
            text_outline_color = QColor(self.text_outline_color)
            if text_outline_color.alpha() > 0:
                text_outline_color.setAlpha(255)
            if self.text_outline_width > 0 and text_outline_color.alpha() > 0:
                # Draw outline
                painter.setPen(QPen(text_outline_color, self.text_outline_width))
                painter.drawText(text_rect, QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignTop, self.text)
            # Draw fill
            text_color = QColor(self.text_color)
            if text_color.alpha() > 0:
                text_color.setAlpha(255)
            painter.setPen(QPen(text_color, 0))
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

    def set_text_style(self, bold: bool | None = None, italic: bool | None = None, underline: bool | None = None, strike_out: bool | None = None):
        if bold is not None:
            self.font.setBold(bold)
        if italic is not None:
            self.font.setItalic(italic)
        if underline is not None:
            self.font.setUnderline(underline)
        if strike_out is not None:
            self.font.setStrikeOut(strike_out)
        self.update()

    def set_text_color(self, color: QtGui.QColor | tuple | list):
        self.text_color = QColor(*color) if not isinstance(color, QColor) else color
        self.update()

    def set_text_outline(self, color: QtGui.QColor | tuple | list, width: float = 1.0):
        self.text_outline_color = QColor(*color) if not isinstance(color, QColor) else color
        self.text_outline_width = width
        self.update()

    def set_fill_color(self, color: QtGui.QColor | tuple | list):
        # Polymorphically treat fill_color as text character color
        self.text_color = QColor(*color) if not isinstance(color, QColor) else color
        self.update()

    def set_outline_color(self, color: QtGui.QColor | tuple | list, width: float = 1.0):
        # Polymorphically treat outline_color as text characters outline color
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
            path.closeSubpath()
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
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, False)
        path = self.shape_path()
        fill_color = QColor(self.fill_color)
        if self.shape_type != 'line' and fill_color.alpha() > 0:
            fill_color.setAlpha(255)
            painter.fillPath(path, QBrush(fill_color))
        outline_color = QColor(self.outline_color)
        if outline_color.alpha() > 0:
            outline_color.setAlpha(255)
        pen = QPen(outline_color, self.outline_width)
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
        self.current_geometry_type = 'line'
        self.drag_start_pos = QtCore.QPointF()
        self.drag_item = None

        # Register this manager on the scene so overlays can easily communicate with it
        if hasattr(gui, "image_scene") and gui.image_scene:
            gui.image_scene.tg_manager = self

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
        if self.text_bold_checkbox is not None:
            self.text_bold_checkbox.toggled.connect(self._on_bold_toggled)
        if self.text_italic_checkbox is not None:
            self.text_italic_checkbox.toggled.connect(self._on_italic_toggled)
        if self.text_underline_checkbox is not None:
            self.text_underline_checkbox.toggled.connect(self._on_underline_toggled)
        if self.text_strike_checkbox is not None:
            self.text_strike_checkbox.toggled.connect(self._on_strike_toggled)

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
        self.tg_overlay_list_widget = gui.tg_overlay_list_widget
        self.tg_overlay_list_widget.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tg_overlay_list_widget.itemSelectionChanged.connect(self._on_overlay_selected)

        #delete overlay button
        self.delete_tg_overlay_button = gui.delete_tg_overlay_button
        self.delete_tg_overlay_button.clicked.connect(self.delete_active_overlay)

        #delete all overlays button
        self.delete_all_tg_overlays_button = gui.delete_all_tg_overlays_button
        self.delete_all_tg_overlays_button.clicked.connect(self.delete_all_overlays)

        # imprint selected tg overlays button
        self.imprint_selected_tg_overlays_button = gui.imprint_selected_tg_overlays_button
        self.imprint_selected_tg_overlays_button.clicked.connect(self.imprint_selected_overlays)

        # Wire up scene selection changed signal
        self._updating_selection = False
        if hasattr(gui, "image_scene"):
            gui.image_scene.selectionChanged.connect(self._on_scene_selection_changed)

        #overlay dimension spinboxes
        self.width_mm_spinbox = gui.width_mm_spinbox
        self.height_mm_spinbox = gui.height_mm_spinbox 
        self.width_mm_spinbox.valueChanged.connect(lambda: self.set_overlay_dimensions_mm(self.width_mm_spinbox.value(), self.height_mm_spinbox.value()))
        self.height_mm_spinbox.valueChanged.connect(lambda: self.set_overlay_dimensions_mm(self.width_mm_spinbox.value(), self.height_mm_spinbox.value()))

        #text input lineedit
        self.text_input_lineedit = gui.text_input_lineedit
        if self.text_input_lineedit:
            self.text_input_lineedit.textChanged.connect(self._on_text_input_changed)



        # Current colors (defaults)
        # self.current_text_color = QtGui.QColor(0, 0, 0)
        # self.current_text_outline_color = QtGui.QColor(0, 0, 0, 0)
        self.current_fill_color = QtGui.QColor(0, 0, 0, 0)
        self.current_outline_color = QtGui.QColor(0, 0, 0)

        # Initialize button styles
        self._style_color_button(self.fill_color_button, self.current_fill_color)
        self._style_color_button(self.outline_color_button, self.current_outline_color)

        # Wire up event handler if available
        if event_handler:
            event_handler.add_canvas_event_callback(self.on_canvas_event)

        # Initialize UI properties panel state
        self._disable_and_reset_properties()

    def on_canvas_event(self, event):
        """Handle canvas mouse events for drawing overlays."""
        if event.type() == QtCore.QEvent.Type.MouseButtonPress and event.button() == QtCore.Qt.MouseButton.LeftButton:
            if self.mode in {self.MODE_ADD_TEXT, self.MODE_ADD_GEOMETRY}:
                self.on_canvas_press(event)
                return True
            else:
                if self.on_canvas_press(event) is True:
                    return True
        elif event.type() == QtCore.QEvent.Type.MouseMove and event.buttons() == QtCore.Qt.MouseButton.LeftButton:
            if self.mode in {self.MODE_ADD_TEXT, self.MODE_ADD_GEOMETRY}:
                self.on_canvas_drag(event)
                return True
        elif event.type() == QtCore.QEvent.Type.MouseButtonRelease and event.button() == QtCore.Qt.MouseButton.LeftButton:
            if self.mode in {self.MODE_ADD_TEXT, self.MODE_ADD_GEOMETRY}:
                self.on_canvas_release(event)
                return True

    def on_canvas_press(self, event):
        """Start drawing a new overlay or select existing one."""
        if self.mode == self.MODE_IDLE:
            # Check if clicking on existing overlay
            items = self.gui.image_canvas.items(event.pos())
            for item in items:
                if item in self.overlay_store.all_items():
                    if event.modifiers() & QtCore.Qt.KeyboardModifier.ShiftModifier:
                        # Toggle selection on Shift-click
                        item.setSelected(not item.isSelected())
                        # Active item is the last selected overlay in the scene
                        selected = self.gui.image_scene.selectedItems()
                        self.overlay_store.active_item = selected[-1] if selected else None
                        self._update_ui_from_selected()
                        event.accept()
                        return True
                    else:
                        if item.isSelected():
                            return
                        self.overlay_store.select_item(item)
                        self._update_ui_from_selected()
                        return
            # If we click on empty canvas, clear selection in the scene
            if not (event.modifiers() & QtCore.Qt.KeyboardModifier.ShiftModifier) and hasattr(self.gui, "image_scene"):
                self.gui.image_scene.clearSelection()

        if self.mode == self.MODE_ADD_TEXT:
            if hasattr(self.gui, "image_scene"):
                self.gui.image_scene.clearSelection()
            pos_canvas = event.pos()
            x_scene, y_scene = self.data_handler.canvas_to_scene_coords(pos_canvas.x(), pos_canvas.y())
            self.drag_start_pos_scene = QtCore.QPointF(x_scene, y_scene)
            self.drag_item = self.overlay_store.add_text_field(
                rect=QtCore.QRectF(0, 0, 1, 1),
                text=self.text_input_lineedit.text() if self.text_input_lineedit else "Text",
                text_color=self.current_fill_color,
                outline_color=self.current_outline_color,
                outline_width=self.outline_width_spinbox.value() if self.outline_width_spinbox else 0.0
            )
            self.drag_item.setPos(self.drag_start_pos_scene)
            self._apply_text_formatting()
            self._update_overlay_list()

        elif self.mode == self.MODE_ADD_GEOMETRY:
            if hasattr(self.gui, "image_scene"):
                self.gui.image_scene.clearSelection()
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
        # Normalize the rectangle to handle negative dimensions (dragging up/left)
        rect = QtCore.QRectF(0, 0, width, height).normalized()
        self.drag_item._rect = rect
        self.drag_item.update_transform_origin()
        self.drag_item.update()
        self.gui.image_canvas.update()

        # Update the UI spinboxes in real time while drawing
        if self.data_handler.pixel_per_mm:
            w_mm, h_mm = self.drag_item.dimensions_in_mm(self.data_handler.pixel_per_mm)
            self._block_property_signals(True)
            try:
                if self.width_mm_spinbox:
                    self.width_mm_spinbox.setValue(w_mm)
                if self.height_mm_spinbox:
                    self.height_mm_spinbox.setValue(h_mm)
            finally:
                self._block_property_signals(False)

        event.accept()  # Consume the event to prevent ItemIsMovable from handling it

    def on_canvas_release(self, event):
        """Finish drawing the overlay and add it to data_handler."""
        if self.drag_item is None:
            return

        self.drag_item = None
        if self.mode in {self.MODE_ADD_TEXT, self.MODE_ADD_GEOMETRY}:
            if self.overlay_store.active_item:
                self.data_handler.text_overlays.extend([x for x in self.overlay_store.text_items if x not in self.data_handler.text_overlays])
                self.data_handler.geometry_overlays.extend([x for x in self.overlay_store.geometry_items if x not in self.data_handler.geometry_overlays])

            # Reset mode and buttons
            self.mode = self.MODE_IDLE
            self.gui.image_canvas.viewport().setCursor(QtCore.Qt.CursorShape.ArrowCursor)
            
            if self.add_text_button:
                self.add_text_button.setChecked(False)
            if self.add_geometry_button:
                self.add_geometry_button.setChecked(False)

            self._update_ui_from_selected()

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

        # Apply formatting using unified color and outline properties
        item.set_fill_color(self.current_fill_color)
        width = self.outline_width_spinbox.value() if self.outline_width_spinbox else 1.0
        item.set_outline_color(self.current_outline_color, width)

    def set_add_text_mode(self, enabled: bool):
        """Toggle text field drawing mode."""
        if enabled:
            self.mode = self.MODE_ADD_TEXT
            self.gui.image_canvas.viewport().setCursor(QtCore.Qt.CursorShape.CrossCursor)
            if self.add_geometry_button and self.add_geometry_button.isChecked():
                self.add_geometry_button.setChecked(False)
                self.set_add_geometry_mode(False)
        else:
            if self.mode == self.MODE_ADD_TEXT:
                self.mode = self.MODE_IDLE
                self.gui.image_canvas.viewport().setCursor(QtCore.Qt.CursorShape.ArrowCursor)

    def set_add_geometry_mode(self, enabled: bool):
        """Toggle geometry drawing mode."""
        if enabled:
            self.mode = self.MODE_ADD_GEOMETRY
            self.gui.image_canvas.viewport().setCursor(QtCore.Qt.CursorShape.CrossCursor)
            if self.add_text_button and self.add_text_button.isChecked():
                self.add_text_button.setChecked(False)
                self.set_add_text_mode(False)
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

    # def set_text_color(self, color: QtGui.QColor):
    #     """Set the active text color (for backwards compatibility/fallbacks)."""
    #     self.current_text_color = color
    #     selected_items = self.gui.image_scene.selectedItems() if hasattr(self.gui, "image_scene") else []
    #     overlays_to_color = [item for item in selected_items if item in self.overlay_store.all_items()]
    #     if not overlays_to_color and self.overlay_store.active_item:
    #         overlays_to_color = [self.overlay_store.active_item]
    #     for item in overlays_to_color:
    #         if isinstance(item, TextFieldOverlay):
    #             item.set_text_color(color)

    # def set_text_outline_color(self, color: QtGui.QColor, width: float = 1.0):
    #     """Set the active text outline color (for backwards compatibility/fallbacks)."""
    #     self.current_text_outline_color = color
    #     selected_items = self.gui.image_scene.selectedItems() if hasattr(self.gui, "image_scene") else []
    #     overlays_to_color = [item for item in selected_items if item in self.overlay_store.all_items()]
    #     if not overlays_to_color and self.overlay_store.active_item:
    #         overlays_to_color = [self.overlay_store.active_item]
    #     for item in overlays_to_color:
    #         if isinstance(item, TextFieldOverlay):
    #             item.set_text_outline(color, width)

    def set_fill_color(self, color: QtGui.QColor):
        """Set the active fill color for all selected overlays."""
        self.current_fill_color = color
        selected_items = self.gui.image_scene.selectedItems() if hasattr(self.gui, "image_scene") else []
        overlays_to_color = [item for item in selected_items if item in self.overlay_store.all_items()]
        if not overlays_to_color and self.overlay_store.active_item:
            overlays_to_color = [self.overlay_store.active_item]
        for item in overlays_to_color:
            item.set_fill_color(color)
        self._style_color_button(self.fill_color_button, color)
        if hasattr(self.gui, "image_scene"):
            self.gui.image_scene.update()

    def set_outline_color(self, color: QtGui.QColor, width: float = 1.0):
        """Set the active outline color for all selected overlays."""
        self.current_outline_color = color
        selected_items = self.gui.image_scene.selectedItems() if hasattr(self.gui, "image_scene") else []
        overlays_to_color = [item for item in selected_items if item in self.overlay_store.all_items()]
        if not overlays_to_color and self.overlay_store.active_item:
            overlays_to_color = [self.overlay_store.active_item]
        for item in overlays_to_color:
            item.set_outline_color(color, width)
        self._style_color_button(self.outline_color_button, color)
        if hasattr(self.gui, "image_scene"):
            self.gui.image_scene.update()

    def set_overlay_dimensions_mm(self, width_mm: float, height_mm: float):
        """Resize active overlay by millimeters."""
        if self.overlay_store.active_item and self.data_handler.pixel_per_mm:
            self.overlay_store.active_item.resize_by_mm(width_mm, height_mm, self.data_handler.pixel_per_mm)
            self._update_ui_from_selected()

    def delete_active_overlay(self):
        """Remove all currently selected overlays."""
        if not hasattr(self.gui, "image_scene"):
            return

        # Retrieve all currently selected overlays from the scene
        selected_items = self.gui.image_scene.selectedItems()
        overlays_to_delete = [item for item in selected_items if item in self.overlay_store.all_items()]
        
        # If nothing is selected in the scene, check the list widget selection as fallback
        if not overlays_to_delete and self.tg_overlay_list_widget is not None:
            for list_item in self.tg_overlay_list_widget.selectedItems():
                overlay_item = list_item.data(QtCore.Qt.ItemDataRole.UserRole)
                if overlay_item and overlay_item not in overlays_to_delete:
                    overlays_to_delete.append(overlay_item)
                    
        if overlays_to_delete:
            for item in overlays_to_delete:
                self.overlay_store.remove_item(item)
                
            # Also remove them from data_handler lists
            self.data_handler.text_overlays[:] = [x for x in self.data_handler.text_overlays if x in self.overlay_store.text_items]
            self.data_handler.geometry_overlays[:] = [x for x in self.data_handler.geometry_overlays if x in self.overlay_store.geometry_items]
            
            self._update_overlay_list()

    def delete_all_overlays(self):
        """Remove all overlays in the project."""
        reply = QtWidgets.QMessageBox.question(
            self.gui, "Delete All Overlays",
            "Are you sure you want to delete all text and geometry overlays?",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No
        )
        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            self.overlay_store.clear_all()
            
            # Clear from data_handler lists as well
            self.data_handler.text_overlays.clear()
            self.data_handler.geometry_overlays.clear()
            
            self._update_overlay_list()

    def imprint_selected_overlays(self):
        """Bakes only the currently selected text and geometry overlays into the background image."""
        if not hasattr(self.gui, "image_scene") or not self.gui.image_item:
            return

        import numpy as np

        # 1. Retrieve selected overlays
        selected_items = self.gui.image_scene.selectedItems()
        overlays_to_imprint = [item for item in selected_items if item in self.overlay_store.all_items()]

        if not overlays_to_imprint:
            QtWidgets.QMessageBox.information(
                self.gui, "Imprint Overlays",
                "No overlays are currently selected to imprint."
            )
            return

        # 2. Get copy of current background image pixmap
        current_pixmap = self.gui.image_item.pixmap()
        if current_pixmap.isNull():
            return
            
        result_pixmap = current_pixmap.copy()

        # 3. Create painter on the copy to draw the overlays on it
        painter = QtGui.QPainter(result_pixmap)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, False)

        for item in overlays_to_imprint:
            if hasattr(item, 'paint_to_painter'):
                painter.save()
                painter.translate(item.pos())
                painter.setTransform(item.transform(), True)
                item.paint_to_painter(painter)
                painter.restore()
            else:
                try:
                    painter.save()
                    painter.translate(item.pos())
                    painter.setTransform(item.transform(), True)
                    if hasattr(item, 'paint'):
                        item.paint(painter, None, None)
                    painter.restore()
                except Exception:
                    pass

        painter.end()

        # 4. Remove imprinted overlays from scene and overlay store
        for item in overlays_to_imprint:
            self.overlay_store.remove_item(item)

        # Clear them from data_handler lists
        self.data_handler.text_overlays[:] = [x for x in self.data_handler.text_overlays if x in self.overlay_store.text_items]
        self.data_handler.geometry_overlays[:] = [x for x in self.data_handler.geometry_overlays if x in self.overlay_store.geometry_items]

        # Refresh overlay list display and clear properties panel selection
        self._update_overlay_list()
        self._update_ui_from_selected()

        # 5. QPixmap -> QImage -> Numpy Array conversion to update the logical matrix
        image = result_pixmap.toImage()
        if image.format() != QtGui.QImage.Format.Format_RGBA8888:
            image = image.convertToFormat(QtGui.QImage.Format.Format_RGBA8888)

        width = image.width()
        height = image.height()

        ptr = image.bits()
        ptr.setsize(height * width * 4)

        # copy buffer so python owns the data
        arr = np.frombuffer(ptr, np.uint8).reshape((height, width, 4)).copy()
        
        # Drop alpha as we work in RGB only
        self.data_handler.image_matrix = arr[:,:,:3]

        # Update the active list item's ImgObj in gui if one exists
        images_list_widget = getattr(self.gui, "images_ListWidget", None)
        if images_list_widget is not None and images_list_widget.currentItem() is not None:
            active_item = images_list_widget.currentItem()
            img_obj = active_item.data(QtCore.Qt.ItemDataRole.UserRole)
            if img_obj is not None:
                img_obj.image_matrix = self.data_handler.image_matrix.copy()
                active_item.setData(QtCore.Qt.ItemDataRole.UserRole, img_obj)

    def _update_overlay_list(self):
        """Refresh the overlay list widget display."""
        if self.tg_overlay_list_widget is None:
            return

        # Temporarily block signals to avoid triggering selection updates during list population
        self.tg_overlay_list_widget.blockSignals(True)
        try:
            self.tg_overlay_list_widget.clear()
            
            text_count = 0
            geom_counts = {}
            
            # Retrieve all currently selected items in the scene to preserve selection
            selected_in_scene = []
            if hasattr(self.gui, "image_scene"):
                selected_in_scene = self.gui.image_scene.selectedItems()
            
            for item in self.overlay_store.text_items:
                text_count += 1
                name = f"textbox #{text_count}"
                list_item = QtWidgets.QListWidgetItem(name)
                list_item.setData(QtCore.Qt.ItemDataRole.UserRole, item)
                self.tg_overlay_list_widget.addItem(list_item)
                if item in selected_in_scene:
                    list_item.setSelected(True)

            for item in self.overlay_store.geometry_items:
                shape = item.shape_type.upper()  # e.g., RECTANGLE, ELLIPSE, LINE, TRIANGLE
                geom_counts[shape] = geom_counts.get(shape, 0) + 1
                name = f"{shape} #{geom_counts[shape]}"
                list_item = QtWidgets.QListWidgetItem(name)
                list_item.setData(QtCore.Qt.ItemDataRole.UserRole, item)
                self.tg_overlay_list_widget.addItem(list_item)
                if item in selected_in_scene:
                    list_item.setSelected(True)
        finally:
            self.tg_overlay_list_widget.blockSignals(False)

    def _on_font_size_changed(self):
        """Update font size of all selected text overlays."""
        if not self.font_size_spinbox:
            return
        size = self.font_size_spinbox.value()
        selected_items = self.gui.image_scene.selectedItems() if hasattr(self.gui, "image_scene") else []
        text_items = [item for item in selected_items if isinstance(item, TextFieldOverlay)]
        if not text_items and isinstance(self.overlay_store.active_item, TextFieldOverlay):
            text_items = [self.overlay_store.active_item]
        for item in text_items:
            item.set_font_size(size)
        if hasattr(self.gui, "image_scene"):
            self.gui.image_scene.update()

    def _on_font_family_changed(self):
        """Update font family of all selected text overlays."""
        if not self.font_family_combobox:
            return
        family = self.font_family_combobox.currentText()
        selected_items = self.gui.image_scene.selectedItems() if hasattr(self.gui, "image_scene") else []
        text_items = [item for item in selected_items if isinstance(item, TextFieldOverlay)]
        if not text_items and isinstance(self.overlay_store.active_item, TextFieldOverlay):
            text_items = [self.overlay_store.active_item]
        for item in text_items:
            item.set_font_family(family)
        if hasattr(self.gui, "image_scene"):
            self.gui.image_scene.update()

    def _on_bold_toggled(self, checked: bool):
        """Update bold style of all selected text overlays independently."""
        self._apply_single_style(bold=checked)

    def _on_italic_toggled(self, checked: bool):
        """Update italic style of all selected text overlays independently."""
        self._apply_single_style(italic=checked)

    def _on_underline_toggled(self, checked: bool):
        """Update underline style of all selected text overlays independently."""
        self._apply_single_style(underline=checked)

    def _on_strike_toggled(self, checked: bool):
        """Update strike_out style of all selected text overlays independently."""
        self._apply_single_style(strike_out=checked)

    def _apply_single_style(self, bold=None, italic=None, underline=None, strike_out=None):
        """Apply a single font style to selected text overlays without altering other styles."""
        selected_items = self.gui.image_scene.selectedItems() if hasattr(self.gui, "image_scene") else []
        text_items = [item for item in selected_items if isinstance(item, TextFieldOverlay)]
        if not text_items and isinstance(self.overlay_store.active_item, TextFieldOverlay):
            text_items = [self.overlay_store.active_item]
        for item in text_items:
            item.set_text_style(bold=bold, italic=italic, underline=underline, strike_out=strike_out)
        if hasattr(self.gui, "image_scene"):
            self.gui.image_scene.update()

    # def _on_text_outline_width_changed(self):
    #     """Update text outline width of active/selected text overlays (deprecated/fallback)."""
    #     if not self.text_outline_width_spinbox:
    #         return
    #     width = self.text_outline_width_spinbox.value()
    #     selected_items = self.gui.image_scene.selectedItems() if hasattr(self.gui, "image_scene") else []
    #     overlays_to_update = [item for item in selected_items if item in self.overlay_store.all_items()]
    #     if not overlays_to_update and self.overlay_store.active_item:
    #         overlays_to_update = [self.overlay_store.active_item]
    #     for item in overlays_to_update:
    #         if isinstance(item, TextFieldOverlay):
    #             color = item.text_outline_color
    #             if width > 0 and color.alpha() == 0:
    #                 color = QColor(0, 0, 0)
    #             item.set_text_outline(color, width)
    #     if hasattr(self.gui, "image_scene"):
    #         self.gui.image_scene.update()

    def _on_outline_width_changed(self):
        """Update outline width of all selected overlays."""
        if not self.outline_width_spinbox:
            return
        width = self.outline_width_spinbox.value()
        selected_items = self.gui.image_scene.selectedItems() if hasattr(self.gui, "image_scene") else []
        overlays_to_update = [item for item in selected_items if item in self.overlay_store.all_items()]
        if not overlays_to_update and self.overlay_store.active_item:
            overlays_to_update = [self.overlay_store.active_item]
        for item in overlays_to_update:
            color = item.text_outline_color if isinstance(item, TextFieldOverlay) else item.outline_color
            item.set_outline_color(color, width)
        if hasattr(self.gui, "image_scene"):
            self.gui.image_scene.update()

    def _on_overlay_selected(self):
        """Handle overlay selection from list widget (List -> Canvas)."""
        if self.tg_overlay_list_widget is None or self._updating_selection or not hasattr(self.gui, "image_scene"):
            return

        self._updating_selection = True
        try:
            self.gui.image_scene.clearSelection()
            selected_items = self.tg_overlay_list_widget.selectedItems()
            active_item = None
            for list_item in selected_items:
                overlay_item = list_item.data(QtCore.Qt.ItemDataRole.UserRole)
                if overlay_item:
                    overlay_item.setSelected(True)
                    active_item = overlay_item
            
            self.overlay_store.active_item = active_item
            self._update_ui_from_selected()
                
            # Force canvas viewport and scene redraw to reflect selection instantly
            self.gui.image_scene.update()
            if hasattr(self.gui, "image_canvas") and self.gui.image_canvas.viewport():
                self.gui.image_canvas.viewport().update()
        finally:
            self._updating_selection = False

    def _on_scene_selection_changed(self):
        """Handle overlay selection from scene (Canvas -> List)."""
        if self.tg_overlay_list_widget is None or self._updating_selection or not hasattr(self.gui, "image_scene"):
            return

        self._updating_selection = True
        try:
            self.tg_overlay_list_widget.clearSelection()
            selected_in_scene = self.gui.image_scene.selectedItems()
            
            # Select matching list items
            for i in range(self.tg_overlay_list_widget.count()):
                list_item = self.tg_overlay_list_widget.item(i)
                overlay_item = list_item.data(QtCore.Qt.ItemDataRole.UserRole)
                if overlay_item in selected_in_scene:
                    list_item.setSelected(True)
                    
            # Set properties panel focus to the primary selected item
            overlays_selected = [x for x in self.overlay_store.all_items() if x.isSelected()]
            if overlays_selected:
                self.overlay_store.active_item = overlays_selected[-1]
            else:
                self.overlay_store.active_item = None
            self._update_ui_from_selected()
        finally:
            self._updating_selection = False

    def _on_text_input_changed(self):
        """Update text content of active text overlay."""
        if isinstance(self.overlay_store.active_item, TextFieldOverlay) and self.text_input_lineedit:
            self.overlay_store.active_item.set_text(self.text_input_lineedit.text())

    def _update_ui_dimensions_only(self, item):
        """Update only the width and height spinboxes in real-time without refreshing other inputs."""
        if not self.width_mm_spinbox and not self.height_mm_spinbox:
            return
        if not self.data_handler.pixel_per_mm:
            return

        selected_items = self.gui.image_scene.selectedItems() if hasattr(self.gui, "image_scene") else []
        selected_overlays = [x for x in selected_items if x in self.overlay_store.all_items()]

        # Only update if this is the single selected item
        if len(selected_overlays) == 1 and selected_overlays[0] is item:
            w_mm, h_mm = item.dimensions_in_mm(self.data_handler.pixel_per_mm)
            self._block_property_signals(True)
            try:
                if self.width_mm_spinbox:
                    self.width_mm_spinbox.setValue(w_mm)
                if self.height_mm_spinbox:
                    self.height_mm_spinbox.setValue(h_mm)
            finally:
                self._block_property_signals(False)

    def _update_ui_from_selected(self):
        """Update UI controls to reflect active overlay properties and selection state."""
        selected_items = self.gui.image_scene.selectedItems() if hasattr(self.gui, "image_scene") else []
        selected_overlays = [item for item in selected_items if item in self.overlay_store.all_items()]

        if not selected_overlays:
            self._disable_and_reset_properties()
            return

        # Determine selection characteristics
        has_text = any(isinstance(x, TextFieldOverlay) for x in selected_overlays)
        
        # Block signals during enablement and value updates to prevent recursion
        self._block_property_signals(True)
        try:
            # Enable general controls
            if self.outline_width_spinbox:
                self.outline_width_spinbox.setEnabled(True)
                
            # Width and height are only enabled if exactly one overlay is selected
            if len(selected_overlays) == 1:
                if self.width_mm_spinbox:
                    self.width_mm_spinbox.setEnabled(True)
                if self.height_mm_spinbox:
                    self.height_mm_spinbox.setEnabled(True)
            else:
                if self.width_mm_spinbox:
                    self.width_mm_spinbox.setEnabled(False)
                    self.width_mm_spinbox.setValue(0.0)
                if self.height_mm_spinbox:
                    self.height_mm_spinbox.setEnabled(False)
                    self.height_mm_spinbox.setValue(0.0)

            # Enable/Disable text-specific controls
            if has_text:
                if self.font_family_combobox:
                    self.font_family_combobox.setEnabled(True)
                if self.font_size_spinbox:
                    self.font_size_spinbox.setEnabled(True)
                for cb in [self.text_bold_checkbox, self.text_italic_checkbox, 
                           self.text_underline_checkbox, self.text_strike_checkbox]:
                    if cb:
                        cb.setEnabled(True)
                if self.text_input_lineedit:
                    self.text_input_lineedit.setEnabled(len(selected_overlays) <= 1 )
                    if len(selected_overlays) > 1:
                        self.text_input_lineedit.setText("")
            else:
                # Only geometries selected -> disable and reset text controls
                if self.font_family_combobox:
                    self.font_family_combobox.setEnabled(False)
                    self.font_family_combobox.setCurrentIndex(0)
                if self.font_size_spinbox:
                    self.font_size_spinbox.setEnabled(False)
                    self.font_size_spinbox.setValue(24)
                for cb in [self.text_bold_checkbox, self.text_italic_checkbox, 
                           self.text_underline_checkbox, self.text_strike_checkbox]:
                    if cb:
                        cb.setEnabled(False)
                        cb.setChecked(False)
                if self.text_input_lineedit:
                    self.text_input_lineedit.setEnabled(False)
                    self.text_input_lineedit.setText("")

            # Enable/Disable geometry type control
            if self.geometry_type_combobox:
                # if len(selected_overlays) == 1 and isinstance(selected_overlays[0], GeometryOverlay):
                self.geometry_type_combobox.setEnabled(len(selected_overlays) <= 1 )
                # elif len(selected_overlays) == 0:
                #     self.geometry_type_combobox.setEnabled(True)
                if len(selected_overlays) > 1:
                    self.geometry_type_combobox.setEnabled(False)
                    self.geometry_type_combobox.setCurrentIndex(0)

            # Populate values from the active item
            item = self.overlay_store.active_item
            if item:
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
                    if self.text_input_lineedit and len(selected_overlays) <= 1:
                        self.text_input_lineedit.setText(item.text)
                    if self.outline_width_spinbox:
                        self.outline_width_spinbox.setValue(item.text_outline_width)
                    
                    self.current_fill_color = item.text_color
                    self.current_outline_color = item.text_outline_color
                    # self.current_text_color = item.text_color
                    # self.current_text_outline_color = item.text_outline_color

                if isinstance(item, GeometryOverlay):
                    if self.geometry_type_combobox:
                        idx = self.geometry_type_combobox.findText(item.shape_type.capitalize())
                        if idx >= 0:
                            self.geometry_type_combobox.setCurrentIndex(idx)
                    if self.outline_width_spinbox:
                        self.outline_width_spinbox.setValue(item.outline_width)
                    self.current_fill_color = item.fill_color
                    self.current_outline_color = item.outline_color

                # Update the button styling
                self._style_color_button(self.fill_color_button, self.current_fill_color)
                self._style_color_button(self.outline_color_button, self.current_outline_color)

                # Only populate width and height if a single item is selected
                if len(selected_overlays) == 1 and self.data_handler.pixel_per_mm:
                    w_mm, h_mm = item.dimensions_in_mm(self.data_handler.pixel_per_mm)
                    if self.width_mm_spinbox:
                        self.width_mm_spinbox.setValue(w_mm)
                    if self.height_mm_spinbox:
                        self.height_mm_spinbox.setValue(h_mm)
        finally:
            self._block_property_signals(False)

    def _disable_and_reset_properties(self):
        """Disable all properties widgets and reset to standard defaults when selection is empty."""
        self._block_property_signals(True)
        try:
            # Font family
            if self.font_family_combobox:
                self.font_family_combobox.setEnabled(False)
                self.font_family_combobox.setCurrentIndex(0)
            # Font size
            if self.font_size_spinbox:
                self.font_size_spinbox.setEnabled(False)
                self.font_size_spinbox.setValue(24)
            # Checkboxes
            for cb in [self.text_bold_checkbox, self.text_italic_checkbox, 
                       self.text_underline_checkbox, self.text_strike_checkbox]:
                if cb:
                    cb.setEnabled(False)
                    cb.setChecked(False)
            # Text input
            if self.text_input_lineedit:
                self.text_input_lineedit.setEnabled(True)
            # Geometry type
            if self.geometry_type_combobox:
                self.geometry_type_combobox.setEnabled(True)
            # Outline width
            if self.outline_width_spinbox:
                self.outline_width_spinbox.setEnabled(False)
                self.outline_width_spinbox.setValue(1.0)
            # Geometry width and height
            if self.width_mm_spinbox:
                self.width_mm_spinbox.setEnabled(False)
                self.width_mm_spinbox.setValue(0.0)
            if self.height_mm_spinbox:
                self.height_mm_spinbox.setEnabled(False)
                self.height_mm_spinbox.setValue(0.0)
            # Reset color buttons
            # self._style_color_button(self.fill_color_button, QColor(0, 0, 0, 0))
            # self._style_color_button(self.outline_color_button, QColor(0, 0, 0, 0))
        finally:
            self._block_property_signals(False)

    def _block_property_signals(self, block: bool):
        """Block or unblock layout properties controls' signals to prevent feedback recursion."""
        widgets = [
            self.font_family_combobox, self.font_size_spinbox,
            self.text_bold_checkbox, self.text_italic_checkbox,
            self.text_underline_checkbox, self.text_strike_checkbox,
            self.text_input_lineedit, self.outline_width_spinbox,
            self.width_mm_spinbox, self.height_mm_spinbox,
            self.geometry_type_combobox
        ]
        for w in widgets:
            if w is not None:
                w.blockSignals(block)

    def _style_color_button(self, button, color: QtGui.QColor):
        """Update a color button's background to the chosen color, with a high-contrast complementary text color."""
        if button is None:
            return

        if color is None or color.alpha() == 0:
            # Default styling for transparent / no color
            button.setStyleSheet(
                "QPushButton {"
                "  background-color: #f0f0f0;"
                "  color: #333333;"
                "  border: 1px solid #cccccc;"
                "  font-weight: bold;"
                "  border-radius: 4px;"
                "  padding: 4px;"
                "}"
                "QPushButton:hover {"
                "  background-color: #e4e4e4;"
                "}"
            )
            return

        r, g, b = color.red(), color.green(), color.blue()
        cr, cg, cb = 255 - r, 255 - g, 255 - b
        
        # Calculate YIQ luminance of background
        luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255.0
        
        # If the background is a mid-tone, the complementary color will also be a mid-tone
        # and therefore lack contrast. In those cases, force pure black or white text.
        if 0.35 <= luminance <= 0.65:
            text_color = "rgb(255, 255, 255)" if luminance <= 0.5 else "rgb(0, 0, 0)"
        else:
            text_color = f"rgb({cr}, {cg}, {cb})"

        # Subtle dark border
        border_r = max(0, r - 30)
        border_g = max(0, g - 30)
        border_b = max(0, b - 30)
        
        button.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: rgba({r}, {g}, {b}, {color.alpha()});"
            f"  color: {text_color};"
            f"  border: 1px solid rgb({border_r}, {border_g}, {border_b});"
            f"  font-weight: bold;"
            f"  border-radius: 4px;"
            f"  padding: 4px;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background-color: rgba({min(255, r+20)}, {min(255, g+20)}, {min(255, b+20)}, {color.alpha()});"
            f"}}"
        )
