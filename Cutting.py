"""Cutting (Hatching group): draw single laser paths like in a small 2-D CAD tool and use them as toolpath.

Shapes: line, rectangle, ellipse, triangle, hexagon – outline only (no fill, no line width). Like the Text and
Geometries editor: a list of all cut overlays, select (also several, Shift), move, rotate, resize at the handles.
The selected overlay shows its size, rotation and centre (relative to the hatch centre, mm, y up) to edit.
"Fix position" locks the centre: the overlay can no longer be moved (resizing keeps the centre).
Buttons: use the selected overlays as the active hatch (toolpath, like contours / DXF imports), export them as DXF,
delete the selected / all overlays. Geometry and DXF writing: core/cut_shapes.py.
"""
import logging
import math

import numpy as np
from PyQt6 import QtCore, QtGui, QtWidgets, sip
from PyQt6.QtGui import QColor, QPainterPath, QPen

import icons
import theme
from core import cut_shapes
from core.toolpath import Layer, MOVE_BURN, MOVE_TRAVEL
from HelperClasses import HatchCluster, HatchData
from TextandGeometries import OverlayItem
from UndoRedo import TGAddOverlayAction, TGDeleteOverlayAction, TGTransformOverlayAction

log = logging.getLogger(__name__)

# shape, list / tooltip name, icon
SHAPE_BUTTONS = (("line", "Line", "geo-line"), ("rectangle", "Rectangle", "geo-rect"),
                 ("ellipse", "Ellipse", "geo-ellipse"), ("triangle", "Triangle", "geo-triangle"),
                 ("hexagon", "Hexagon", "geo-hexagon"))
CUT_COLOR = QColor(255, 0, 170)  # laser paths on the canvas: visible on any image
MIN_SIZE_PX = 1.0


class CutOverlay(OverlayItem):
    """One drawn laser path. Local frame: centred at (0, 0) (= pos, rotation origin), rect = (-w/2, -h/2, w, h)."""

    def __init__(self, shape_type, width, height, manager=None, mirrored=False, parent=None):
        super().__init__(QtCore.QRectF(-width / 2, -height / 2, width, height), parent)
        if shape_type not in cut_shapes.SHAPES:
            raise ValueError(f"Unsupported shape_type '{shape_type}'.")
        self.shape_type = shape_type
        self.mirrored = mirrored  # line from bottom left to top right
        self.fixed = False
        self._manager = manager
        self.setZValue(20)  # above the image and colour overlays

    def overlay_manager(self):
        return self._manager

    # --- geometry ---
    def size(self):
        return self._rect.width(), self._rect.height()

    def set_size(self, width, height):
        """Resize around the centre (the centre never moves)."""
        self.prepareGeometryChange()
        width, height = max(width, 0.0), max(height, 0.0)
        self._rect = QtCore.QRectF(-width / 2, -height / 2, width, height)
        self.update_transform_origin()
        self.update()

    def set_fixed(self, fixed):
        self.fixed = bool(fixed)
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable, not self.fixed)
        self.update()

    def local_outline(self, tolerance_px=0.5):
        w, h = self.size()
        return cut_shapes.outline(self.shape_type, w, h, self.mirrored, tolerance_px)

    def image_outline(self, tolerance_px=0.5):
        """Outline in image pixels (position and rotation applied)."""
        points = self.local_outline(tolerance_px)
        return np.array([[q.x(), q.y()] for q in (self.mapToParent(QtCore.QPointF(*p)) for p in points)])

    def outline_path(self):
        path = QPainterPath()
        points = self.local_outline(0.25)
        path.moveTo(*points[0])
        for p in points[1:]:
            path.lineTo(*p)
        return path

    # --- painting / picking ---
    def boundingRect(self):
        extra = self.HANDLE_RADIUS + 2
        return self._rect.adjusted(-extra, -extra - self.ROTATE_HANDLE_OFFSET, extra, extra)

    def shape(self):
        stroker = QtGui.QPainterPathStroker()
        stroker.setWidth(6)
        path = stroker.createStroke(self.outline_path())
        if self.shape_type in cut_shapes.CLOSED:
            path.addPath(self.outline_path())  # clicking inside selects as well
        if self.isSelected():
            for handle in self.handle_rects().values():
                path.addEllipse(handle)
        return path

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        pen = QPen(CUT_COLOR, 2)
        pen.setCosmetic(True)  # same width at every zoom level
        painter.setPen(pen)
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        painter.drawPath(self.outline_path())
        mark = QPen(CUT_COLOR, 1)
        mark.setCosmetic(True)
        painter.setPen(mark)
        s = 3.0
        painter.drawLine(QtCore.QPointF(-s, 0), QtCore.QPointF(s, 0))  # centre mark
        painter.drawLine(QtCore.QPointF(0, -s), QtCore.QPointF(0, s))
        if self.fixed:
            painter.drawEllipse(QtCore.QPointF(0, 0), s * 1.6, s * 1.6)
        if self.isSelected():
            self.paint_selection(painter)

    def paint_to_painter(self, painter):  # never imprinted into the image
        pass

    # --- interaction ---
    def do_resize(self, pos):
        """Corner handles: the opposite corner stays (fixed position: the centre stays, symmetric resize)."""
        start = self._start_rect
        if self.fixed:
            w, h = abs(pos.x()) * 2, abs(pos.y()) * 2
            new_rect = QtCore.QRectF(-w / 2, -h / 2, w, h)
        else:
            new_rect = QtCore.QRectF(start)
            delta = pos - self._mouse_down_pos
            corner = {"top_left": new_rect.topLeft, "top_right": new_rect.topRight,
                      "bottom_left": new_rect.bottomLeft, "bottom_right": new_rect.bottomRight}[self._active_handle]()
            setter = {"top_left": new_rect.setTopLeft, "top_right": new_rect.setTopRight,
                      "bottom_left": new_rect.setBottomLeft, "bottom_right": new_rect.setBottomRight}
            setter[self._active_handle](corner + delta)
            new_rect = new_rect.normalized()
        w, h = max(new_rect.width(), MIN_SIZE_PX), max(new_rect.height(), MIN_SIZE_PX)
        center = new_rect.center()
        self.prepareGeometryChange()
        # keep the local frame centred: move the item by the shift of the centre (rotation included)
        new_pos = self.mapToParent(center)
        self._rect = QtCore.QRectF(-w / 2, -h / 2, w, h)
        self._start_rect = QtCore.QRectF(self._rect)
        self._mouse_down_pos = self._mouse_down_pos - center
        self.update_transform_origin()
        self.setPos(new_pos)
        self.update()
        if self._manager:
            self._manager._update_ui_dimensions_only(self)

    def itemChange(self, change, value):
        result = super().itemChange(change, value)
        if change in (QtWidgets.QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged,
                      QtWidgets.QGraphicsItem.GraphicsItemChange.ItemRotationHasChanged) and self._manager:
            self._manager._update_ui_dimensions_only(self)
        return result


class CutStore:
    """The cut overlays in list order (store interface of the TG undo actions)."""

    def __init__(self, parent_item):
        self.parent_item = parent_item
        self.items: list[CutOverlay] = []
        self.active_item = None

    def add_item(self, item):
        if item not in self.items:
            self.items.append(item)
        if item.parentItem() is None:
            item.setParentItem(self.parent_item)
        self.active_item = item
        item.setSelected(True)

    def remove_item(self, item):
        if item in self.items:
            self.items.remove(item)
        if self.active_item is item:
            self.active_item = None
        if item.scene() is not None:
            item.scene().removeItem(item)
        item.setParentItem(None)

    def all_items(self):
        return list(self.items)


def _spinbox(name, minimum, maximum, suffix, decimals=2, step=1.0):  # 10 um, as the hatch precision
    spin = QtWidgets.QDoubleSpinBox(objectName=name)
    spin.setRange(minimum, maximum)
    spin.setDecimals(decimals)
    spin.setSingleStep(step)
    spin.setSuffix(suffix)
    spin.setKeyboardTracking(False)  # apply when the input is finished, not on every key
    spin.setSizePolicy(QtWidgets.QSizePolicy.Policy.Ignored, QtWidgets.QSizePolicy.Policy.Fixed)
    return spin


def _icon_button(name, tooltip, checkable=False):
    button = QtWidgets.QPushButton(objectName=name)
    button.setToolTip(tooltip)
    button.setProperty("styleClass", "IconButton")
    button.setFixedSize(34, 30)
    button.setIconSize(QtCore.QSize(20, 20))
    button.setCheckable(checkable)
    return button


def build_section(gui):
    """The Cutting section (outside / inside frame like the sections of the .ui); widgets become gui attributes."""
    frame = QtWidgets.QGroupBox(objectName="cutting_frame")
    frame.setProperty("styleClass", "outsideFrame")
    outer = QtWidgets.QVBoxLayout(frame)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)
    inside = QtWidgets.QGroupBox("Cutting", objectName="inside_cutting_frame")
    inside.setProperty("styleClass", "insideFrame")
    outer.addWidget(inside)
    grid = QtWidgets.QGridLayout(inside)
    grid.setHorizontalSpacing(4)
    grid.setVerticalSpacing(4)

    shapes = QtWidgets.QHBoxLayout()
    shapes.setSpacing(4)
    gui.cut_shape_buttons = {}
    for shape, label, _ in SHAPE_BUTTONS:
        button = _icon_button(f"cut_{shape}_button", f"Draw a {label.lower()} (drag on the image; Shift: "
                              f"{'45° steps' if shape == 'line' else 'regular shape'})", checkable=True)
        shapes.addWidget(button)
        gui.cut_shape_buttons[shape] = button
    shapes.addStretch(1)
    grid.addLayout(shapes, 0, 0, 1, 4)

    gui.cut_list_widget = QtWidgets.QListWidget(objectName="cut_list_widget")
    gui.cut_list_widget.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
    gui.cut_list_widget.setMaximumHeight(110)
    grid.addWidget(gui.cut_list_widget, 1, 0, 1, 4)

    gui.cut_width_spinbox = _spinbox("cut_width_spinbox", 0, 10000, " mm", step=0.5)
    gui.cut_height_spinbox = _spinbox("cut_height_spinbox", 0, 10000, " mm", step=0.5)
    gui.cut_x_spinbox = _spinbox("cut_x_spinbox", -10000, 10000, " mm", step=0.5)
    gui.cut_y_spinbox = _spinbox("cut_y_spinbox", -10000, 10000, " mm", step=0.5)
    gui.cut_rotation_spinbox = _spinbox("cut_rotation_spinbox", -360, 360, "°", decimals=2, step=1.0)
    gui.cut_rotation_spinbox.setWrapping(True)
    gui.cut_fix_checkbox = QtWidgets.QCheckBox("Fix position", objectName="cut_fix_checkbox")
    gui.cut_fix_checkbox.setToolTip("The selected overlays can no longer be moved")
    rows = (("Width", gui.cut_width_spinbox, "Height", gui.cut_height_spinbox),
            ("X", gui.cut_x_spinbox, "Y", gui.cut_y_spinbox),
            ("Rotation", gui.cut_rotation_spinbox, None, gui.cut_fix_checkbox))
    for row, (label_a, widget_a, label_b, widget_b) in enumerate(rows, start=2):
        grid.addWidget(QtWidgets.QLabel(label_a), row, 0)
        grid.addWidget(widget_a, row, 1)
        if label_b:
            grid.addWidget(QtWidgets.QLabel(label_b), row, 2)
            grid.addWidget(widget_b, row, 3)
        else:
            grid.addWidget(widget_b, row, 2, 1, 2)
    gui.cut_x_spinbox.setToolTip("Centre of the overlay relative to the hatch centre (mm, right)")
    gui.cut_y_spinbox.setToolTip("Centre of the overlay relative to the hatch centre (mm, up)")
    grid.setColumnStretch(1, 1)
    grid.setColumnStretch(3, 1)

    buttons = QtWidgets.QHBoxLayout()
    buttons.setSpacing(4)
    gui.cut_delete_button = _icon_button("cut_delete_button", "Delete the selected overlays")
    gui.cut_delete_all_button = _icon_button("cut_delete_all_button", "Delete all cut overlays")
    gui.cut_export_button = _icon_button("cut_export_button", "Export the selected overlays as .dxf")
    gui.cut_use_as_hatch_button = QtWidgets.QPushButton("Use as Hatch", objectName="cut_use_as_hatch_button")
    gui.cut_use_as_hatch_button.setToolTip("Use the selected lines as the active hatch (toolpath)")
    gui.cut_use_as_hatch_button.setProperty("styleClass", "PrimaryButton")
    gui.cut_use_as_hatch_button.setIconSize(QtCore.QSize(18, 18))
    gui.cut_use_as_hatch_button.setFixedHeight(30)
    for button in (gui.cut_delete_button, gui.cut_delete_all_button, gui.cut_export_button):
        buttons.addWidget(button)
    buttons.addStretch(1)
    buttons.addWidget(gui.cut_use_as_hatch_button)
    grid.addLayout(buttons, 5, 0, 1, 4)

    _set_icons(gui)
    theme.on_change(lambda: _set_icons(gui))  # P11.3: bright / dark mode
    gui.cutting_frame = frame
    gui.inside_cutting_frame = inside
    return frame


def _set_icons(gui):
    for shape, _, icon_name in SHAPE_BUTTONS:
        gui.cut_shape_buttons[shape].setIcon(icons.icon(icon_name))
    gui.cut_delete_button.setIcon(icons.icon("cut-delete"))
    gui.cut_delete_all_button.setIcon(icons.icon("cut-delete-all"))
    gui.cut_export_button.setIcon(icons.icon("cut-export"))
    gui.cut_use_as_hatch_button.setIcon(icons.icon("cut-to-hatch"))


class CuttingManager(QtCore.QObject):
    """Drawing, selection, editing and conversion of the cut overlays. A child of the section: its signal
    connections (e.g. to the scene, which outlives the window) end with the window."""

    def __init__(self, data_handler, gui, event_handler, hatcher):
        super().__init__(gui.cutting_frame)
        self.data_handler = data_handler
        self.gui = gui
        self.hatcher = hatcher  # NCDataGeneration.Hatcher: the active hatch is set through it
        self.undo_manager = getattr(data_handler, "undo_manager", None)
        self.store = CutStore(gui.image_item)
        self.draw_shape = None
        self.drag_item = None
        self.drag_start = None
        self._before_edit = None
        self._updating = False
        self.counter = {}

        for shape, button in gui.cut_shape_buttons.items():
            button.toggled.connect(lambda on, s=shape: self.set_draw_shape(s if on else None, from_button=True))
        gui.cut_list_widget.itemSelectionChanged.connect(self._on_list_selection)
        gui.image_scene.selectionChanged.connect(self._on_scene_selection)
        gui.cut_width_spinbox.valueChanged.connect(self._on_size_edited)
        gui.cut_height_spinbox.valueChanged.connect(self._on_size_edited)
        gui.cut_x_spinbox.valueChanged.connect(self._on_position_edited)
        gui.cut_y_spinbox.valueChanged.connect(self._on_position_edited)
        gui.cut_rotation_spinbox.valueChanged.connect(self._on_rotation_edited)
        gui.cut_fix_checkbox.clicked.connect(self._on_fix_toggled)
        gui.cut_delete_button.clicked.connect(self.delete_selected)
        gui.cut_delete_all_button.clicked.connect(self.delete_all)
        gui.cut_export_button.clicked.connect(lambda: self.export_selected_dxf())
        gui.cut_use_as_hatch_button.clicked.connect(self.use_selected_as_hatch)
        for spin in (gui.h_center_spinbox, gui.v_center_spinbox):  # the centre display follows the hatch centre
            spin.valueChanged.connect(self._on_hatch_center_changed)
        event_handler.add_canvas_event_filter(self._canvas_filter)  # while drawing, no other tool sees the mouse
        self._update_ui_from_selected()

    def _on_hatch_center_changed(self, *_):
        self._update_ui_from_selected()

    # --- coordinates ---
    @property
    def pixel_per_mm(self):
        return self.data_handler.pixel_per_mm

    def hatch_center(self):
        """Hatch centre in image pixels (default: image centre, as for hatching)."""
        center = self.data_handler.center_for_hatch
        if center is not None:
            return float(center[0]), float(center[1])
        image = self.data_handler.image_matrix
        if image is None:
            return 0.0, 0.0
        return (image.shape[1] - 1) / 2, (image.shape[0] - 1) / 2

    def center_mm(self, item):
        cx, cy = self.hatch_center()
        p = item.pos()
        return (p.x() - cx) / self.pixel_per_mm, (cy - p.y()) / self.pixel_per_mm

    # --- drawing ---
    def set_draw_shape(self, shape, from_button=False):
        self.draw_shape = shape
        for s, button in self.gui.cut_shape_buttons.items():
            if button.isChecked() != (s == shape):
                button.blockSignals(True)
                button.setChecked(s == shape)
                button.blockSignals(False)
        cursor = QtCore.Qt.CursorShape.CrossCursor if shape else QtCore.Qt.CursorShape.ArrowCursor
        self.gui.image_canvas.viewport().setCursor(cursor)

    def _canvas_filter(self, event):
        try:
            return self.on_canvas_event(event)
        except RuntimeError:  # the window was closed
            return None

    def on_canvas_event(self, event):
        if self.draw_shape is None or self.data_handler.image_matrix is None or not self.pixel_per_mm:
            return None
        kind = event.type()
        if kind == QtCore.QEvent.Type.MouseButtonPress and event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.start_drawing(self._image_point(event))
            return True
        if kind == QtCore.QEvent.Type.MouseMove and self.drag_item is not None:
            shift = bool(event.modifiers() & QtCore.Qt.KeyboardModifier.ShiftModifier)
            self.drag_drawing(self._image_point(event), shift)
            return True
        if kind == QtCore.QEvent.Type.MouseButtonRelease and event.button() == QtCore.Qt.MouseButton.LeftButton:
            if self.drag_item is not None:
                self.finish_drawing()
            return True
        return None

    def _image_point(self, event):
        scene_pos = self.gui.image_canvas.mapToScene(event.position().toPoint())
        return self.gui.image_item.mapFromScene(scene_pos)

    def start_drawing(self, point):
        self.gui.image_scene.clearSelection()
        self.drag_start = QtCore.QPointF(point)
        self.drag_item = CutOverlay(self.draw_shape, 0, 0, manager=self)
        self.drag_item.setPos(point)
        self.store.add_item(self.drag_item)
        self._update_overlay_list()

    def drag_drawing(self, point, regular=False):
        dx, dy = point.x() - self.drag_start.x(), point.y() - self.drag_start.y()
        shape = self.drag_item.shape_type
        if regular:
            if shape == "line":  # 45° steps
                angle = round(math.atan2(dy, dx) / (math.pi / 4)) * (math.pi / 4)
                length = math.hypot(dx, dy)
                dx, dy = length * math.cos(angle), length * math.sin(angle)
            else:
                ratio = math.sqrt(3) / 2 if shape in ("triangle", "hexagon") else 1.0  # equilateral / regular
                w = max(abs(dx), abs(dy) / ratio)
                dx, dy = math.copysign(w, dx or 1), math.copysign(w * ratio, dy or 1)
        self.drag_item.mirrored = dx * dy < 0
        self.drag_item.set_size(abs(dx), abs(dy))
        self.drag_item.setPos(self.drag_start + QtCore.QPointF(dx / 2, dy / 2))
        self._update_ui_dimensions_only(self.drag_item)

    def finish_drawing(self):
        item = self.drag_item
        self.drag_item = None
        w, h = item.size()
        if max(w, h) < MIN_SIZE_PX:  # a click without dragging: nothing drawn
            self.store.remove_item(item)
        elif self.undo_manager:
            self.undo_manager.push_action(TGAddOverlayAction(self, self.store, item, "Add Cut Overlay"))
        self.set_draw_shape(None)
        self._update_overlay_list()
        self._update_ui_from_selected()

    def add_overlay(self, shape, center_mm, width_mm, height_mm, rotation=0.0, mirrored=False):
        """Programmatic creation (tests, scripts): centre relative to the hatch centre (mm, y up)."""
        ppm = self.pixel_per_mm
        cx, cy = self.hatch_center()
        item = CutOverlay(shape, width_mm * ppm, height_mm * ppm, manager=self, mirrored=mirrored)
        item.setPos(cx + center_mm[0] * ppm, cy - center_mm[1] * ppm)
        item.setRotation(rotation)
        self.gui.image_scene.clearSelection()
        self.store.add_item(item)
        self._update_overlay_list()
        self._update_ui_from_selected()
        return item

    # --- selection / list ---
    def selected_items(self):
        return [item for item in self.store.items if item.isSelected()]

    def _sync_data_handler_lists(self):  # interface of the TG undo actions
        pass

    def _update_overlay_list(self):
        widget = self.gui.cut_list_widget
        widget.blockSignals(True)
        try:
            widget.clear()
            counts = {}
            for item in self.store.items:
                counts[item.shape_type] = counts.get(item.shape_type, 0) + 1
                name = f"{item.shape_type.upper()} #{counts[item.shape_type]}" + ("  (fixed)" if item.fixed else "")
                entry = QtWidgets.QListWidgetItem(name)
                entry.setData(QtCore.Qt.ItemDataRole.UserRole, item)
                widget.addItem(entry)
                entry.setSelected(item.isSelected())
        finally:
            widget.blockSignals(False)

    def _on_list_selection(self):
        if self._updating:
            return
        self._updating = True
        try:
            chosen = {id(entry.data(QtCore.Qt.ItemDataRole.UserRole)) for entry in self.gui.cut_list_widget.selectedItems()}
            for item in self.store.items:
                item.setSelected(id(item) in chosen)
            self._update_ui_from_selected()
        finally:
            self._updating = False

    def _on_scene_selection(self):
        if self._updating or sip.isdeleted(self.gui.cut_list_widget):  # window being destroyed
            return
        self._updating = True
        try:
            widget = self.gui.cut_list_widget
            widget.blockSignals(True)
            for row in range(widget.count()):
                entry = widget.item(row)
                entry.setSelected(entry.data(QtCore.Qt.ItemDataRole.UserRole).isSelected())
            widget.blockSignals(False)
            self._update_ui_from_selected()
        finally:
            self._updating = False

    # --- property fields ---
    def _fields(self):
        g = self.gui
        return (g.cut_width_spinbox, g.cut_height_spinbox, g.cut_x_spinbox, g.cut_y_spinbox, g.cut_rotation_spinbox)

    def _update_ui_dimensions_only(self, item):
        if self.store.active_item is item or self.drag_item is item:
            self._update_ui_from_selected(item)

    def _update_ui_from_selected(self, item=None):
        selected = self.selected_items()
        g = self.gui
        if item is None:
            item = selected[-1] if len(selected) == 1 else None
        self.store.active_item = item
        for spin in self._fields():
            spin.blockSignals(True)
        g.cut_fix_checkbox.blockSignals(True)
        try:
            single = item is not None and bool(self.pixel_per_mm)
            for spin in self._fields():
                spin.setEnabled(single)
            if single:
                ppm = self.pixel_per_mm
                w, h = item.size()
                x, y = self.center_mm(item)
                g.cut_width_spinbox.setValue(w / ppm)
                g.cut_height_spinbox.setValue(h / ppm)
                g.cut_x_spinbox.setValue(x)
                g.cut_y_spinbox.setValue(y)
                g.cut_rotation_spinbox.setValue(item.rotation())
                g.cut_x_spinbox.setEnabled(not item.fixed)
                g.cut_y_spinbox.setEnabled(not item.fixed)
            else:
                for spin in self._fields():
                    spin.setValue(0)
            g.cut_fix_checkbox.setEnabled(bool(selected))
            g.cut_fix_checkbox.setChecked(bool(selected) and all(i.fixed for i in selected))
            g.cut_delete_button.setEnabled(bool(selected))
            g.cut_export_button.setEnabled(bool(selected))
            g.cut_use_as_hatch_button.setEnabled(bool(selected))
            g.cut_delete_all_button.setEnabled(bool(self.store.items))
        finally:
            for spin in self._fields():
                spin.blockSignals(False)
            g.cut_fix_checkbox.blockSignals(False)

    def _get_item_state(self, item):
        return {"pos": QtCore.QPointF(item.pos()), "rect": QtCore.QRectF(item._rect), "rotation": item.rotation(),
                "fixed": item.fixed, "mirrored": item.mirrored}

    def _apply_item_state(self, item, state):
        item.prepareGeometryChange()
        item._rect = QtCore.QRectF(state["rect"])
        item.update_transform_origin()
        item.setPos(state["pos"])
        item.setRotation(state["rotation"])
        item.mirrored = state["mirrored"]
        item.set_fixed(state["fixed"])
        self._update_overlay_list()

    def _edit(self, description, change):
        """Apply `change(item)` to the active item with one undo step."""
        item = self.store.active_item
        if item is None:
            return
        before = self._get_item_state(item)
        change(item)
        after = self._get_item_state(item)
        if self.undo_manager and before != after:
            self.undo_manager.push_action(TGTransformOverlayAction(self, item, before, after, description))
        self._update_ui_from_selected()

    def _on_size_edited(self):
        ppm = self.pixel_per_mm
        w, h = self.gui.cut_width_spinbox.value() * ppm, self.gui.cut_height_spinbox.value() * ppm
        self._edit("Resize Cut Overlay", lambda item: item.set_size(w, h))

    def _on_position_edited(self):
        if self.store.active_item is None or self.store.active_item.fixed:
            return
        ppm = self.pixel_per_mm
        cx, cy = self.hatch_center()
        x, y = self.gui.cut_x_spinbox.value(), self.gui.cut_y_spinbox.value()
        self._edit("Move Cut Overlay", lambda item: item.setPos(cx + x * ppm, cy - y * ppm))

    def _on_rotation_edited(self):
        angle = self.gui.cut_rotation_spinbox.value()
        self._edit("Rotate Cut Overlay", lambda item: item.setRotation(angle))

    def _on_fix_toggled(self, fixed):
        for item in self.selected_items():
            before = self._get_item_state(item)
            item.set_fixed(fixed)
            if self.undo_manager:
                self.undo_manager.push_action(TGTransformOverlayAction(
                    self, item, before, self._get_item_state(item), "Fix Cut Overlay" if fixed else "Release Cut Overlay"))
        self._update_overlay_list()
        self._update_ui_from_selected()

    # --- delete ---
    def delete_selected(self):
        items = self.selected_items()
        if not items:
            return
        if self.undo_manager:
            self.undo_manager.push_action(TGDeleteOverlayAction(self, self.store, items, "Delete Cut Overlay"))
        for item in items:
            self.store.remove_item(item)
        self._update_overlay_list()
        self._update_ui_from_selected()

    def delete_all(self):
        if not self.store.items:
            return
        reply = QtWidgets.QMessageBox.question(self.gui, "Delete All Cut Overlays",
                                               "Are you sure you want to delete all cut overlays?",
                                               QtWidgets.QMessageBox.StandardButton.Yes |
                                               QtWidgets.QMessageBox.StandardButton.No)
        if reply != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        items = self.store.all_items()
        if self.undo_manager:
            self.undo_manager.push_action(TGDeleteOverlayAction(self, self.store, items, "Delete All Cut Overlays"))
        for item in items:
            self.store.remove_item(item)
        self._update_overlay_list()
        self._update_ui_from_selected()

    # --- output ---
    def toolpath_polylines(self, items):
        """One polyline (N, 4) in mm (x, y, z, move) per overlay, relative to the hatch centre."""
        ppm = self.pixel_per_mm
        center = self.hatch_center()
        polylines = []
        for item in items:
            xy = cut_shapes.to_mm(item.image_outline(cut_shapes.FLATTEN_TOLERANCE_MM * ppm), center, ppm)
            moves = np.full(len(xy), MOVE_BURN)
            moves[0] = MOVE_TRAVEL
            polylines.append(np.column_stack([xy, np.zeros(len(xy)), moves]))
        return polylines

    def use_selected_as_hatch(self):
        """The selected overlays become the active hatch (one black layer, like contours / DXF imports)."""
        items = self.selected_items()
        if not items:
            QtWidgets.QMessageBox.information(self.gui, "Use as Hatch", "Select the cut overlays to use first.")
            return None
        hatcher = self.hatcher
        hatcher.get_handler_data()
        cluster = HatchCluster([Layer((0, 0, 0), self.toolpath_polylines(items))], hatcher.image_matrix,
                               ref_position=[0, 0, 0, 0], cluster_center_for_hatch=hatcher.center_for_hatch,
                               cylinder_radius=0)
        hatcher.hatch_data = HatchData([cluster], "Cutting")
        hatcher.set_handler_data()
        return hatcher.hatch_data

    def dxf_entities(self, items):
        ppm = self.pixel_per_mm
        center = self.hatch_center()
        entities = []
        for item in items:
            if item.shape_type == "ellipse":
                w, h = item.size()
                c, ax, ay = cut_shapes.to_mm(
                    [[q.x(), q.y()] for q in (item.mapToParent(QtCore.QPointF(*p))
                                              for p in ((0, 0), (w / 2, 0), (0, h / 2)))], center, ppm)
                entities.append({"shape": "ellipse", "center": c, "axis_x": ax - c, "axis_y": ay - c})
            else:
                entities.append({"shape": item.shape_type,
                                 "points": cut_shapes.to_mm(item.image_outline(), center, ppm)})
        return entities

    def export_selected_dxf(self, path=None):
        items = self.selected_items()
        if not items:
            QtWidgets.QMessageBox.information(self.gui, "Export DXF", "Select the cut overlays to export first.")
            return None
        if path is None:
            path, _ = QtWidgets.QFileDialog.getSaveFileName(self.gui, "Export DXF", "", "DXF Files (*.dxf)")
            if not path:
                return None
            if not path.lower().endswith(".dxf"):
                path += ".dxf"
        cut_shapes.write_dxf(path, self.dxf_entities(items))
        log.info("%d cut overlays exported to %s", len(items), path)
        return path
