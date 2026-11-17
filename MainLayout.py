"""P8.6 / P8.7 / P9.3-P9.5: main window layout – toolbar ("hotbar") and the right-hand settings panel.

The section contents come from GUI_Files/BildHatcher.ui (editable in Qt Designer); this module only arranges them.
Panel navigation has two levels: an outer strip with one (icon) button per group – single select, clicking the
active group closes the panel – and an inner strip with the subsections of the active group (multi select).
The open subsections of every group are remembered (also across restarts, Preferences "panel").
Sections keep their natural size (nothing is stretched); the panel is as wide as the widest visible section.
Widgets keep their object names, so the controllers find them as before.
"""
from PyQt6 import QtCore, QtGui, QtWidgets

import icons
import Preferences

# group: (icon, [(strip label, tooltip / full name, section groupbox name or builder key)])
GROUPS = {
    "Image": ("photo", [
        ("Images", "Images: list, add / remove, split / combine", "@images"),
        ("Size", "Image size and hatch center", "@size"),
        ("Adjust", "Image adjustments: brightness, contrast, colors", "image_adjustment_frame"),
        ("Color", "Color image: paint, fill, contours, clean up", "image_color_frame"),
        ("Masks", "Mask drawing", "draw_mask_groupbox"),
    ]),
    "Text": ("typography", [("Text", "Text and geometries", "tg_frame")]),
    "Hatching": ("texture", [
        ("Hatch", "Image hatching and contours / outlines", "hatch_frame"),
        ("Tests", "Test structures", "testStruc_frame"),
        ("Export", "Build NC data: process blocks and export", "export_frame"),
    ]),
    "Automation": ("robot", [("Automation", "Laser settings and automatic J-code generation", "laser_settings_frame")]),
}
DEFAULT_STATE = {"group": "Image", "open": {"Image": ["Images"], "Text": ["Text"], "Hatching": ["Hatch"],
                                            "Automation": ["Automation"]}}


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
    """A section in the look of the Designer sections (outsideFrame with a titled insideFrame)."""
    section = _styled(QtWidgets.QGroupBox(), "outsideFrame")
    layout = QtWidgets.QVBoxLayout(section)
    inside = _styled(QtWidgets.QGroupBox(title), "insideFrame")
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
    box = QtWidgets.QWidget()
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


class SettingsPanel:
    """Two-level navigation (groups / subsections) over the stacked sections."""

    def __init__(self, gui, on_hidden=None):
        self.gui = gui
        self.on_hidden = on_hidden
        builders = {"@images": _images_section, "@size": _size_section}
        state = Preferences.get("panel") or DEFAULT_STATE
        self.open = {group: list(state.get("open", {}).get(group, DEFAULT_STATE["open"][group])) for group in GROUPS}
        self.group = None

        self.widget = QtWidgets.QWidget(objectName="settings_panel")
        panel_layout = QtWidgets.QHBoxLayout(self.widget)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(2)

        content = QtWidgets.QWidget(objectName="settings_panel_content")
        self.content_layout = QtWidgets.QVBoxLayout(content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll = QtWidgets.QScrollArea(objectName="settings_panel_scroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setWidget(content)

        self.sub_strip = QtWidgets.QWidget(objectName="settings_panel_sections")
        sub_layout = QtWidgets.QVBoxLayout(self.sub_strip)
        sub_layout.setContentsMargins(0, 0, 0, 0)
        sub_layout.setSpacing(2)
        group_strip = QtWidgets.QWidget(objectName="settings_panel_groups")
        group_layout = QtWidgets.QVBoxLayout(group_strip)
        group_layout.setContentsMargins(0, 0, 0, 0)
        group_layout.setSpacing(2)

        self.group_buttons, self.section_buttons, self.sections, self.group_of = {}, {}, {}, {}
        for group, (icon_name, entries) in GROUPS.items():
            button = _styled(QtWidgets.QToolButton(objectName=f"group_button_{group}"), "PanelGroup")
            button.setCheckable(True)
            button.setIcon(icons.icon(icon_name))
            button.setIconSize(QtCore.QSize(24, 24))
            button.setToolTip(group)
            button.clicked.connect(lambda checked, g=group: self.select_group(g if checked else None))
            group_layout.addWidget(button)
            self.group_buttons[group] = button
            for label, tooltip, source in entries:
                section = builders[source](gui) if source in builders else _take(getattr(gui, source))
                for inside in section.findChildren(QtWidgets.QGroupBox):
                    if inside.property("styleClass") == "insideFrame":
                        inside.show()
                section.setVisible(False)
                self.content_layout.addWidget(section, 0, QtCore.Qt.AlignmentFlag.AlignLeft)  # natural width (P9.4)
                sub_button = VerticalButton(label)
                sub_button.setCheckable(True)
                sub_button.setToolTip(tooltip)
                sub_button.setChecked(label in self.open[group])
                sub_button.toggled.connect(lambda checked, g=group, l=label: self._toggle_section(g, l, checked))
                sub_button.hide()
                sub_layout.addWidget(sub_button)
                self.sections[label], self.section_buttons[label], self.group_of[label] = section, sub_button, group
        self.content_layout.addStretch(1)
        sub_layout.addStretch(1)
        group_layout.addStretch(1)

        panel_layout.addWidget(self.scroll)
        panel_layout.addWidget(self.sub_strip)
        panel_layout.addWidget(group_strip)
        gui.centralwidget.layout().replaceWidget(gui.control_tabWidget, self.widget)
        gui.control_tabWidget.hide()
        gui.Image_controls_frame.hide()  # its contents now live in the panel
        gui.settings_panel = self.widget
        self.select_group(state.get("group"), remember=False)

    def select_group(self, group, remember=True):
        """Show the subsections of `group` (None: close the panel to the group strip)."""
        self.group = group
        for name, button in self.group_buttons.items():
            button.setChecked(name == group)
        for label, button in self.section_buttons.items():
            button.setVisible(self.group_of[label] == group)
        self._refresh()
        if remember:
            self._remember()

    def _toggle_section(self, group, label, shown):
        if shown and label not in self.open[group]:
            self.open[group].append(label)
        elif not shown and label in self.open[group]:
            self.open[group].remove(label)
        self._refresh()
        self._remember()

    def _refresh(self):
        width = 0
        for label, section in self.sections.items():
            visible = self.group_of[label] == self.group and label in self.open[self.group_of[label]]
            if section.isVisibleTo(self.widget) and not visible and self.on_hidden is not None:
                self.on_hidden(label)
            section.setVisible(visible)
            if visible:
                width = max(width, section.sizeHint().width())
        self.sub_strip.setVisible(self.group is not None)
        self.scroll.setVisible(width > 0)
        self.scroll.setFixedWidth(width + self.scroll.verticalScrollBar().sizeHint().width() + 4)

    def _remember(self):
        Preferences.put("panel", {"group": self.group, "open": self.open})


def build_panel(gui, on_hidden=None):
    return SettingsPanel(gui, on_hidden)


def build_toolbar(gui, c):
    """File / image / view actions, colour profile and machine in the toolbar."""
    bar = gui.toolBar
    bar.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonIconOnly)  # P9.2: pictograms, texts as tooltips
    bar.setIconSize(QtCore.QSize(22, 22))
    for action, name in ((gui.actionLoad_Image, "folder-open"), (gui.actionSave_Image, "device-floppy"),
                         (gui.actionNew_Blank, "file-plus")):
        icons.set_icon(action, name)
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
    image_button = QtWidgets.QToolButton()
    image_button.setText("Image")
    icons.set_icon(image_button, "photo", tooltip="Image operations")
    image_button.setMenu(menu)
    image_button.setPopupMode(QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup)
    bar.addWidget(image_button)
    bar.addSeparator()

    # view: zoom, reset, re-center, grid
    mover = c.image_sizer
    gui.zoom_slider.hide()  # the zoom field alone is enough in the toolbar (wheel / pinch zoom still work)
    gui.zoom_spinbox.setSuffix(" %")
    gui.zoom_spinbox.setToolTip("Zoom")
    bar.addWidget(_take(gui.zoom_spinbox))
    bar.addAction(icons.icon("zoom-reset"), "Reset Zoom").triggered.connect(lambda: mover.reset_zoom())
    bar.addAction(icons.icon("focus-centered"), "Re-center").triggered.connect(lambda: mover.recenter_image())
    grid_action = bar.addAction(icons.icon("grid-4x4"), "Grid")
    grid_action.setCheckable(True)
    grid_action.toggled.connect(lambda checked: mover.toggle_grid() if checked != mover.grid_on else None)
    gui.grid_distance_spinbox.setSuffix(" mm")
    gui.grid_distance_spinbox.setToolTip("Grid distance")
    bar.addWidget(_take(gui.grid_distance_spinbox))
    gui.image_scaler_frame.hide()
    bar.addSeparator()

    # application-wide profiles
    c.color_profiles.action.setIcon(icons.icon("database"))
    bar.addAction(c.color_profiles.action)
    bar.widgetForAction(c.color_profiles.action).setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
    machine_label = QtWidgets.QLabel()
    machine_label.setPixmap(icons.icon("device-desktop-cog").pixmap(22, 22))
    machine_label.setToolTip("Machine profile")
    bar.addWidget(machine_label)
    gui.machine_profile_label.hide()
    bar.addWidget(_take(gui.machine_profile_combobox))


def build(gui, c):
    """Arrange toolbar and settings panel (call after main.create_components)."""
    build_toolbar(gui, c)
    # hiding the mask section switches off the mask tools (colour tools stay active: they have hotkeys, P9.10)
    reset_tools = lambda name: c.image_colorer.set_single_toggle_state('') if name == "Masks" else None
    return build_panel(gui, on_hidden=reset_tools)
