"""P8.6 / P8.7: main window layout – toolbar ("hotbar") and the right-hand settings panel.

The section contents still come from GUI_Files/BildHatcher.ui (editable in Qt Designer); this module only
arranges them: every section becomes a toggle button in a vertical strip at the right edge, the opened sections
are stacked next to it (scrollable), and with all sections closed the panel shrinks to the strip.
Widgets keep their object names, so the controllers find them as before.
"""
from PyQt6 import QtCore, QtGui, QtWidgets

# (strip label, tooltip / full name, section groupbox name or builder key); None = group separator
SECTIONS = [
    ("Images", "Images: list, add / remove / keep changes, split / combine", "@images"),
    ("Size", "Image size and hatch center", "@size"),
    ("Adjust", "Image adjustments: brightness, contrast, colors", "image_adjustment_frame"),
    ("Color", "Color image: paint, fill, contours, clean up", "image_color_frame"),
    ("Masks", "Mask drawing", "draw_mask_groupbox"),
    None,
    ("Text", "Text and geometries", "tg_frame"),
    None,
    ("Hatch", "Image hatching", "hatch_frame"),
    ("Contours", "Contours / outlines", "contour_frame"),
    ("Tests", "Test structures", "testStruc_frame"),
    ("Export", "Build NC data: process blocks and export", "export_frame"),
    None,
    ("Laser", "Laser settings (color profile)", "laser_settings_frame"),
    ("J-Code", "Automatic J-code generation", "jcode_settings_frame"),
]
OPEN_AT_START = ("Images", "Hatch")


class VerticalButton(QtWidgets.QPushButton):
    """Checkable push button with its text rotated by 90 degrees (reads bottom to top)."""

    def sizeHint(self):
        size = super().sizeHint()
        return QtCore.QSize(size.height(), size.width() + 8)

    def minimumSizeHint(self):
        return self.sizeHint()

    def paintEvent(self, event):
        painter = QtWidgets.QStylePainter(self)
        option = QtWidgets.QStyleOptionButton()
        self.initStyleOption(option)
        text, option.text = option.text, ""
        painter.drawControl(QtWidgets.QStyle.ControlElement.CE_PushButton, option)  # background in the button's style
        painter.translate(0, self.height())
        painter.rotate(-90)
        option.text = text
        option.rect = QtCore.QRect(0, 0, self.height(), self.width())
        painter.drawControl(QtWidgets.QStyle.ControlElement.CE_PushButtonLabel, option)  # text colour from the stylesheet


def _styled(widget, style_class):
    widget.setProperty("styleClass", style_class)
    return widget


def _new_section(title, *contents):
    """A section in the look of the Designer sections (outsideFrame / MenuButton header / insideFrame)."""
    section = _styled(QtWidgets.QGroupBox(), "outsideFrame")
    layout = QtWidgets.QVBoxLayout(section)
    layout.addWidget(_styled(QtWidgets.QPushButton(title), "MenuButton"))
    inside = _styled(QtWidgets.QGroupBox(), "insideFrame")
    inside_layout = QtWidgets.QVBoxLayout(inside)
    for widget in contents:
        inside_layout.addWidget(widget)
    layout.addWidget(inside)
    return section


def _take(widget):
    """Remove a widget from its current layout (it is re-added elsewhere)."""
    parent = widget.parentWidget()
    if parent is not None and parent.layout() is not None:
        parent.layout().removeWidget(widget)
    return widget


def _images_section(gui):
    box = _styled(QtWidgets.QGroupBox("Images"), "verticalSubFrame")
    grid = QtWidgets.QGridLayout(box)
    grid.addWidget(_take(gui.images_ListWidget), 0, 0, 1, 2)
    gui.images_ListWidget.setMaximumHeight(160)
    for i, name in enumerate(["add_image_button", "remove_image_button", "keep_changes_button",
                              "split_color_button", "combine_image_button", "monochrome_check"]):
        grid.addWidget(_take(getattr(gui, name)), 1 + i // 2, i % 2)
    gui.image_lister_frame.hide()  # what is left there moved to the toolbar
    return _new_section("Images", box)


def _size_section(gui):
    return _new_section("Size & Center", _take(gui.image_dimension_frame), _take(gui.groupBox_2))


def _header_of(section):
    return next(b for b in section.findChildren(QtWidgets.QPushButton) if b.property("styleClass") == "MenuButton")


def build_panel(gui, on_close=None):
    """Replace the control tab widget by the strip + stacked sections. Returns {strip label: toggle button}."""
    builders = {"@images": _images_section, "@size": _size_section}
    panel = QtWidgets.QWidget(objectName="settings_panel")
    panel_layout = QtWidgets.QHBoxLayout(panel)
    panel_layout.setContentsMargins(0, 0, 0, 0)
    panel_layout.setSpacing(2)

    content = QtWidgets.QWidget(objectName="settings_panel_content")
    content_layout = QtWidgets.QVBoxLayout(content)
    content_layout.setContentsMargins(0, 0, 0, 0)
    scroll = QtWidgets.QScrollArea(objectName="settings_panel_scroll")
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setWidget(content)

    strip = QtWidgets.QWidget(objectName="settings_panel_strip")
    strip_layout = QtWidgets.QVBoxLayout(strip)
    strip_layout.setContentsMargins(0, 0, 0, 0)
    strip_layout.setSpacing(2)

    buttons = {}
    width = 0
    for entry in SECTIONS:
        if entry is None:
            line = QtWidgets.QFrame()
            line.setFrameShape(QtWidgets.QFrame.Shape.HLine)
            strip_layout.addWidget(line)
            continue
        label, tooltip, source = entry
        section = builders[source](gui) if source in builders else _take(getattr(gui, source))
        for inside in section.findChildren(QtWidgets.QGroupBox):
            if inside.property("styleClass") == "insideFrame" and inside.parentWidget() is section:
                inside.show()  # the header no longer collapses the content: the strip opens/closes sections
        header = _header_of(section)
        header.setCheckable(False)
        header.setToolTip("Close section")
        content_layout.addWidget(section)
        width = max(width, section.minimumSizeHint().width())

        button = VerticalButton(label)
        button.setCheckable(True)
        button.setToolTip(tooltip)
        button.toggled.connect(section.setVisible)
        header.clicked.connect(lambda checked=False, b=button: b.setChecked(False))
        if on_close is not None:
            button.toggled.connect(lambda checked, name=label: None if checked else on_close(name))
        strip_layout.addWidget(button)
        buttons[label] = button
        section.setVisible(False)
    content_layout.addStretch(1)
    strip_layout.addStretch(1)

    scroll.setFixedWidth(width + scroll.verticalScrollBar().sizeHint().width() + 4)

    def update_collapsed(*_):  # with every section closed only the strip stays
        scroll.setVisible(any(b.isChecked() for b in buttons.values()))
    for button in buttons.values():
        button.toggled.connect(update_collapsed)

    panel_layout.addWidget(scroll)
    panel_layout.addWidget(strip)
    central = gui.centralwidget.layout()
    central.replaceWidget(gui.control_tabWidget, panel)
    gui.control_tabWidget.hide()
    gui.settings_panel = panel
    for label in OPEN_AT_START:
        buttons[label].setChecked(True)
    update_collapsed()
    gui.Image_controls_frame.hide()  # its contents now live in the panel and the toolbar
    return buttons


def build_toolbar(gui, c):
    """File / image / view actions, colour profile and machine in the toolbar."""
    bar = gui.toolBar
    bar.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextOnly)
    for action in (gui.actionLoad_Image, gui.actionSave_Image, gui.actionNew_Blank):
        bar.addAction(action)
    bar.addSeparator()

    # image operations as a drop-down "Image" menu
    ctrl = c.image_controller
    menu = QtWidgets.QMenu("Image", gui)
    for text, slot in (("Rotate 90°", ctrl.rot_image_90_clockwise),
                       ("Mirror Horizontal", ctrl.mirror_image_horizontal),
                       ("Mirror Vertical", ctrl.mirror_image_vertical),
                       ("Crop Background", ctrl.crop_background),
                       ("Cut to Mask", ctrl.cut_to_mask),
                       ("Upscale 2x (AI)", lambda: ctrl.upscale_active_image()),
                       ("Upscale 2x (keep colors)", lambda: ctrl.upscale_active_image(preserve_palette=True))):
        menu.addAction(text).triggered.connect(lambda checked=False, f=slot: f())
    menu.addSeparator()
    menu.addAction(ctrl.action_bright_to_transparent)
    menu.addAction(ctrl.action_white_is_background)
    image_button = QtWidgets.QToolButton()
    image_button.setText("Image")
    image_button.setMenu(menu)
    image_button.setPopupMode(QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup)
    bar.addWidget(image_button)
    bar.addSeparator()

    # view: zoom, reset, re-center, grid
    mover = c.image_sizer
    gui.zoom_slider.hide()  # the zoom field alone is enough in the toolbar (wheel / pinch zoom still work)
    bar.addWidget(QtWidgets.QLabel(" Zoom "))
    gui.zoom_spinbox.setSuffix(" %")
    bar.addWidget(_take(gui.zoom_spinbox))
    bar.addAction("Reset Zoom").triggered.connect(lambda: mover.reset_zoom())
    bar.addAction("Re-center").triggered.connect(lambda: mover.recenter_image())
    grid_action = bar.addAction("Grid")
    grid_action.setCheckable(True)
    grid_action.toggled.connect(lambda checked: mover.toggle_grid() if checked != mover.grid_on else None)
    gui.grid_distance_spinbox.setSuffix(" mm")
    gui.grid_distance_spinbox.setToolTip("Grid distance")
    bar.addWidget(_take(gui.grid_distance_spinbox))
    gui.image_scaler_frame.hide()
    bar.addSeparator()

    # application-wide profiles
    bar.addAction(c.color_profiles.action)
    bar.addWidget(QtWidgets.QLabel(" Machine "))
    gui.machine_profile_label.hide()
    bar.addWidget(_take(gui.machine_profile_combobox))


def build(gui, c):
    """Arrange toolbar and settings panel (call after main.create_components)."""
    build_toolbar(gui, c)
    # leaving the colour / mask sections switches off their canvas tools (was: switching the tab)
    reset_tools = lambda name: c.image_colorer.set_single_toggle_state('') if name in ("Color", "Masks") else None
    return build_panel(gui, on_close=reset_tools)
