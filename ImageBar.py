"""Second tool bar row (far left): Images, Size and Center of the active image.

Every entry is a button with the matching values as text beside it. A click opens the section as a drop-down under
the button; it stays open (also while working on the canvas) until the button is clicked again. Open drop-downs sit
side by side, they never cover each other.
  Images  - the image list and operations (was the Images section of the panel); text: image name, number of colours
  Size    - width / height / pixel size (the Size part of the old Size section); text: width x height in mm
  Center  - the hatch centre, X / Y editable (the Center part of the old Size section); text: X / Y in mm
"""
from PyQt6 import QtCore, QtWidgets

import icons
import theme

GAP = 6  # between drop-downs side by side, and below the tool bar


def _styled(widget, style_class):
    widget.setProperty("styleClass", style_class)
    return widget


def _take(widget):
    """Remove a widget from its current layout (it is re-added elsewhere)."""
    parent = widget.parentWidget()
    if parent is not None and parent.layout() is not None:
        parent.layout().removeWidget(widget)
    return widget


def card(title, content, name):
    """A section card (outsideFrame / insideFrame, like the panel sections) around `content` (a sub group box)."""
    outside = _styled(QtWidgets.QGroupBox(objectName=f"{name}_frame"), "outsideFrame")
    layout = QtWidgets.QVBoxLayout(outside)
    layout.setContentsMargins(0, 0, 0, 0)
    inside = _styled(QtWidgets.QGroupBox(title, objectName=f"inside_{name}_frame"), "insideFrame")
    inside_layout = QtWidgets.QVBoxLayout(inside)
    inside_layout.setContentsMargins(0, 0, 0, 0)
    _take(content)
    content.setTitle("")  # the card has the title
    content.setProperty("styleClass", "")
    content.setFlat(True)
    content.setStyleSheet("QGroupBox { border: none; margin: 0px; padding: 0px; }")
    inside_layout.addWidget(content)
    layout.addWidget(inside)
    return outside


class Dropdown(QtCore.QObject):
    """A section shown under its tool bar button while the button is checked."""

    def __init__(self, bar, button, section, name):
        super().__init__(button)
        self.bar, self.button, self.name = bar, button, name
        window = bar.window()
        self.holder = QtWidgets.QWidget(window, objectName=f"{name}_dropdown")
        layout = QtWidgets.QVBoxLayout(self.holder)
        layout.setContentsMargins(0, 0, 0, 0)
        self.section = _take(section)
        section.setParent(self.holder)
        for inside in section.findChildren(QtWidgets.QGroupBox):
            if inside.property("styleClass") == "insideFrame":
                inside.show()
        section.show()
        layout.addWidget(section)
        self.holder.hide()
        button.toggled.connect(self.set_open)

    def is_open(self):
        return self.button.isChecked()

    def set_open(self, shown):
        if self.button.isChecked() != shown:
            self.button.setChecked(shown)  # comes back here through toggled
            return
        self.holder.setVisible(shown)
        if shown:
            self.holder.raise_()
        self.bar.layout_dropdowns()

    def anchor(self):
        """Top left position under the button, in window coordinates; below the canvas tabs (Image / Hatch view),
        so they stay reachable while drop-downs are open."""
        window = self.holder.parentWidget()
        point = self.button.mapTo(window, QtCore.QPoint(0, self.button.height() + GAP))
        tabs = getattr(window, "visualization_tabWidget", None)
        if tabs is not None and tabs.isVisible():
            bar = tabs.tabBar()
            point.setY(max(point.y(), bar.mapTo(window, QtCore.QPoint(0, bar.height())).y() + 2))
        return point


class ImageBar(QtWidgets.QToolBar):
    """The tool bar row with the Images / Size / Center buttons and their values."""

    def __init__(self, gui, c):
        super().__init__("Image", gui)
        self.setObjectName("image_toolBar")
        self.gui, self.c = gui, c
        self.setMovable(True)  # the grip on the left, as the main tool bar
        self.setFloatable(False)
        self.setAllowedAreas(QtCore.Qt.ToolBarArea.TopToolBarArea | QtCore.Qt.ToolBarArea.BottomToolBarArea)
        self.setIconSize(QtCore.QSize(22, 22))
        self.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonIconOnly)
        gui.addToolBarBreak(QtCore.Qt.ToolBarArea.TopToolBarArea)
        gui.addToolBar(QtCore.Qt.ToolBarArea.TopToolBarArea, self)
        gui.image_toolBar = self
        self.dropdowns = []

        # Images: name and number of colours of the active image
        self.images_button = self._button("images", "group-image", "Images: list, add / remove, split / combine, "
                                          "rotate, crop, upscale (click again to close)")
        gui.toolbar_image_name_label = self._label("toolbar_image_name_label", "ToolbarName", "Active image")
        gui.toolbar_colors_label = self._label("toolbar_colors_label", "ToolbarInfo", "Number of colors in the image")
        self.addSeparator()
        # Size: width x height in mm
        self.size_button = self._button("size", "image-size", "Image size (click again to close)")
        gui.toolbar_size_label = self._label("toolbar_size_label", "ToolbarInfo", "Width x height of the image")
        self.addSeparator()
        # Center: hatch centre X / Y in mm
        self.center_button = self._button("center", "image-center", "Hatch center: show, set, type in "
                                          "(click again to close)")
        gui.toolbar_center_label = self._label("toolbar_center_label", "ToolbarInfo",
                                               "Hatch center X / Y (mm from the top left corner of the image)")

        self.images = Dropdown(self, self.images_button, gui.images_frame, "images")
        gui.size_dropdown_frame = card("Size", gui.image_dimension_frame, "size_dropdown")
        self.size = Dropdown(self, self.size_button, gui.size_dropdown_frame, "size")
        gui.center_dropdown_frame = card("Center", gui.groupBox_2, "center_dropdown")
        self.center = Dropdown(self, self.center_button, gui.center_dropdown_frame, "center")
        self.dropdowns = [self.images, self.size, self.center]
        gui.size_frame.hide()  # its two parts now live in the Size and Center drop-downs
        # one width for the drop-downs: the Images section's (as the panel)
        gui.images_frame.ensurePolished()
        width = gui.images_frame.sizeHint().width()
        for dropdown in self.dropdowns:
            dropdown.section.setFixedWidth(max(width, dropdown.section.minimumSizeHint().width()))

        self._relayout = QtCore.QTimer(self, singleShot=True, interval=0)  # (owned: never fires after closing)
        self._relayout.timeout.connect(self.layout_dropdowns)
        gui.installEventFilter(self)  # keep the drop-downs under their buttons
        dh = c.data_handler
        dh.add_image_changed_callback(self.refresh)
        dh.add_image_resized_callback(self.refresh)
        dh.image_shape_changed_callback_list.append(self.refresh)
        c.image_sizer.center_changed.connect(self.refresh_center)
        gui.images_ListWidget.itemChanged.connect(lambda *_: self.refresh_name())
        theme.on_change(self._set_icons)
        self.refresh()

    def _button(self, name, icon_name, tooltip):
        button = QtWidgets.QToolButton(self, objectName=f"toolbar_{name}_button")
        button.setCheckable(True)
        button.setIcon(icons.icon(icon_name))
        button.setIconSize(QtCore.QSize(22, 22))
        button.setToolTip(tooltip)
        button.setProperty("iconName", icon_name)
        self.addWidget(button)
        return button

    def _label(self, name, style_class, tooltip):
        label = _styled(QtWidgets.QLabel(objectName=name), style_class)
        label.setToolTip(tooltip)
        self.addWidget(label)
        return label

    def _set_icons(self):
        for button in (self.images_button, self.size_button, self.center_button):
            button.setIcon(icons.icon(button.property("iconName")))

    # --- values ---
    def refresh(self):
        self.refresh_name()
        self.refresh_size()
        self.refresh_center()

    def refresh_name(self):
        item = self.c.image_controller.active_image_item
        has_image = self.c.data_handler.image_matrix is not None and item is not None
        self.gui.toolbar_image_name_label.setText(item.text() if has_image else "No image")
        if not has_image:
            self.gui.toolbar_colors_label.setText("0 colors")

    def refresh_size(self):
        dh = self.c.data_handler
        if dh.image_matrix is None or not dh.pixel_per_mm:
            self.gui.toolbar_size_label.setText("– x – mm")
            return
        h, w = dh.image_matrix.shape[:2]
        self.gui.toolbar_size_label.setText(f"{w / dh.pixel_per_mm:.2f} x {h / dh.pixel_per_mm:.2f} mm")

    def refresh_center(self):
        center = self.c.image_sizer.image_center_mm()
        text = "X – / Y – mm" if center is None else f"X {center[0]:.2f} / Y {center[1]:.2f} mm"
        self.gui.toolbar_center_label.setText(text)

    # --- drop-downs ---
    def layout_dropdowns(self):
        """Open drop-downs under their buttons, side by side from left to right (never on top of each other)."""
        window = self.gui
        x_min = 0
        for dropdown in self.dropdowns:
            if not dropdown.holder.isVisible():
                continue
            holder = dropdown.holder
            holder.adjustSize()
            anchor = dropdown.anchor()
            x = max(anchor.x(), x_min)
            x = max(0, min(x, window.width() - holder.width()))
            if self.gui.toolBarArea(self) == QtCore.Qt.ToolBarArea.BottomToolBarArea:  # open upwards
                top = dropdown.button.mapTo(window, QtCore.QPoint(0, 0)).y() - GAP
                height = min(holder.sizeHint().height(), max(top, 80))
                holder.setGeometry(x, top - height, holder.width(), height)
            else:
                height = min(holder.sizeHint().height(), max(window.height() - anchor.y() - GAP, 80))
                holder.setGeometry(x, anchor.y(), holder.width(), height)
            x_min = x + holder.width() + GAP

    def eventFilter(self, obj, event):
        if obj is self.gui and event.type() in (QtCore.QEvent.Type.Resize, QtCore.QEvent.Type.Show,
                                                QtCore.QEvent.Type.LayoutRequest):
            self._relayout.start()
        return False

    def moveEvent(self, event):  # the bar was moved (grip): the drop-downs follow
        super().moveEvent(event)
        self._relayout.start()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._relayout.start()


def build(gui, c):
    return ImageBar(gui, c)
