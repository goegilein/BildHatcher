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
import Tools

# group: (icon, [(strip label, tooltip / full name, section groupbox name or builder key)])
GROUPS = {
    "Image": ("photo", [
        ("Images", "Images: list, add / remove, split / combine", "@images"),
        ("Size", "Image size and hatch center", "@size"),
        ("Adjust", "Image adjustments: brightness, contrast, colors", "image_adjustment_frame"),
        ("Color", "Color image: paint, fill, contours, clean up", "@color"),
        ("Masks", "Mask drawing", "draw_mask_groupbox"),
    ]),
    "Text": ("typography", [("Text", "Text and geometries", "@text")]),
    "Hatching": ("texture", [
        ("Hatch", "Image hatching and contours / outlines", "hatch_frame"),
        ("Tests", "Test structures", "testStruc_frame"),
        ("Export", "Build NC data: process blocks and export", "export_frame"),
    ]),
    "Automation": ("robot", [("Automation", "Automatic J-code generation (uses the active color profile)", "laser_settings_frame")]),
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


# P9.6: pictograms of the Images section (filled buttons: white icons); the texts become tooltips
IMAGE_BUTTONS = (
    ("add_image_button", "photo-plus", "Add image"),
    ("remove_image_button", "photo-minus", "Remove image"),
    ("keep_changes_button", "photo-check", "Set as original: the current image becomes the restore point"),
    ("split_color_button", "arrows-split-2", "Split into color channels"),
    ("combine_image_button", "layers-union", "Combine selected images (darkest color wins)"),
    ("combine_monochrome_button", "contrast", "Combine selected images monochrome (one average color)"),
    ("rot_image_90_button", "rotate-clockwise", "Rotate 90° clockwise"),
    ("mirror_image_horizontal_button", "flip-vertical", "Mirror horizontally (left / right)"),
    ("mirror_image_vertical_button", "flip-horizontal", "Mirror vertically (top / bottom)"),
    ("crop_background_button", "crop", "Crop transparent background"),
    ("cut_to_mask_button", "scissors", "Cut to the active mask"),
    ("upscale_button", "sparkles", "Upscale 2x (AI)"),
    ("upscale_preserving_button", "arrows-maximize", "Upscale 2x, keep the colors"),
    ("bright_transparent_button", "sun-off", "Make bright colors transparent..."),
)


# P9.7: Color section. Tools keep a short text and share one size; the rest are icon buttons
COLOR_BUTTONS = (
    ("select_color_color_button", "palette", "More colors..."),
    ("pick_color_from_image_button", "color-picker", "Pick a color from the image"),
    ("pick_color_from_db_button", "database", "Pick a color of the active color profile"),
    ("recolor_from_database_button", "color-swatch", "Recolor with the colors of the active color profile"),
    ("clean_up_image_colors_button", "wand", "Clean up colors (merge similar colors, remove stray pixels)"),
    ("imprint_color_overlays_button", "stack-push", "Imprint the colored overlays into the image"),
    ("undo_color_button", "arrow-back-up", "Undo the last color step"),
    ("restore_uncolored_image_button", "restore", "Restore the uncolored image"),
)
COLOR_TOOLS = (
    ("toggle_draw_button", "brush", "Draw with the active color"),
    ("flood_fill_button", "bucket-droplet", "Fill an area with the active color"),
    ("replace_color_button", "replace", "Replace a color everywhere with the active color"),
    ("draw_contour_button", "vector", "Show / hide the contours of the image"),
)


def _iconify(gui, table, color=icons.ON_DARK, size=20, box=(34, 30), keep_text=False):
    for name, icon_name, tooltip in table:
        button = getattr(gui, name)
        tip = button.toolTip() if name == "recolor_from_database_button" and button.toolTip() else tooltip
        icons.set_icon(button, icon_name, tooltip=tip, color=color, size=size, keep_text=keep_text,
                       checked_color=icons.APP)
        button.setProperty("iconName", icon_name)  # e.g. colour buttons recolour their icon
        button.setMinimumSize(0, 0)
        button.setFixedSize(*box)


def _color_section(gui):
    _iconify(gui, COLOR_BUTTONS)
    _iconify(gui, COLOR_TOOLS, size=18, box=(92, 30), keep_text=True)
    options = gui.fill_options_widget  # the fill-mode options must not resize the section
    options.setFixedHeight(30)
    options.setSizePolicy(QtWidgets.QSizePolicy.Policy.Ignored, QtWidgets.QSizePolicy.Policy.Fixed)
    options.setStyleSheet("#fill_options_widget { background: transparent; }")
    gui.fill_options_grid_layout.setContentsMargins(0, 0, 0, 0)
    return _take(gui.image_color_frame)


# P9.8: Text section – icon buttons, B / I / U / S toggles and pictogram labels
TEXT_BUTTONS = (
    ("add_text_button", "text-plus", "Add a text field (click into the image)"),
    ("add_geometry_button", "square-plus", "Add a geometry (drag in the image)"),
    ("text_bold_checkbox", "bold", "Bold"),
    ("text_italic_checkbox", "italic", "Italic"),
    ("text_underline_checkbox", "underline", "Underline"),
    ("text_strike_checkbox", "strikethrough", "Strike out"),
    ("fill_color_button", "paint", "Fill / text color"),
    ("outline_color_button", "border-outer", "Outline color"),
    ("delete_tg_overlay_button", "trash", "Delete the selected overlays"),
    ("delete_all_tg_overlays_button", "trash-x", "Delete all overlays"),
    ("imprint_selected_tg_overlays_button", "stack-push", "Imprint the selected overlays into the image"),
)
TEXT_LABELS = (
    ("label_25", "typography", "Font family"),
    ("label_26", "text-size", "Font size"),
    ("label_30", "line-height", "Outline width"),
    ("label_28", "arrow-autofit-width", "Width (mm)"),
    ("label_29", "arrow-autofit-height", "Height (mm)"),
)


# P9.9: remaining sections. Mask tools as icon buttons; action buttons keep their text and get an icon
MASK_BUTTONS = (
    ("rectangle_mask_button", "square", "Rectangle mask"),
    ("ellipse_mask_button", "circle", "Ellipse mask"),
    ("polygon_mask_button", "polygon", "Polygon mask"),
    ("edit_mask_button", "pencil", "Edit the selected mask"),
    ("move_masked_area_button", "arrows-move", "Move the masked area"),
    ("unselect_mask_button", "deselect", "Unselect the mask"),
    ("delete_mask_button", "trash", "Delete the selected mask"),
    ("delete_all_masks_button", "trash-x", "Delete all masks"),
    ("save_mask_button", "device-floppy", "Save the selected mask area as an image"),
)
CENTER_BUTTONS = (
    ("show_image_center_button", "target", "Show the hatch center"),
    ("set_image_center_button", "crosshair", "Select the hatch center in the image"),
    ("reset_image_center_button", "focus-centered", "Reset the hatch center"),
)
ACTION_BUTTONS = (
    ("restore_original_color_button", "restore"), ("invert_color_button", "contrast"),
    ("convolute_image_button", "adjustments"), ("reset_image_size_button", "dimensions"),
    ("hatch_image_button", "texture"),
    ("create_contours_button", "vector"), ("create_test_button", "test-pipe"),
    ("add_process_block_button", "square-plus"), ("remove_process_block_button", "trash"),
    ("export_button", "file-export"), ("load_material_profile_button", "database"),
    ("automatic_gcode_file_button", "robot"),
)


def _iconify_remaining(gui):
    _iconify(gui, MASK_BUTTONS)
    _iconify(gui, CENTER_BUTTONS)
    for name, icon_name in ACTION_BUTTONS:
        button = getattr(gui, name)
        tooltip = button.toolTip() or button.text().strip()
        icons.set_icon(button, icon_name, tooltip=tooltip, color=icons.ON_DARK, keep_text=True, size=18,
                       checked_color=icons.APP)
        button.setProperty("iconName", icon_name)
    gui.masks_list_widget.setMaximumHeight(120)


def _icon_labels(gui, table, size=20):
    for name, icon_name, tooltip in table:
        label = getattr(gui, name)
        label.setPixmap(icons.icon(icon_name).pixmap(size, size))
        label.setToolTip(tooltip)
        label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)


def _text_section(gui):
    _iconify(gui, TEXT_BUTTONS)
    _icon_labels(gui, TEXT_LABELS)
    combo = gui.geometry_type_combobox
    for i, icon_name in enumerate(("line", "square", "triangle", "oval")):  # Line, Rectangle, Triangle, Ellipse
        if i < combo.count():
            combo.setItemIcon(i, icons.icon(icon_name))
    combo.setToolTip("Geometry type")
    gui.tg_overlay_list_widget.setMaximumHeight(140)
    return _take(gui.tg_frame)


def _images_section(gui):
    _iconify(gui, IMAGE_BUTTONS)
    gui.images_ListWidget.setMaximumHeight(160)
    return _take(gui.images_frame)


def _size_section(gui):
    return _new_section("Size && Center", _take(gui.image_dimension_frame), _take(gui.groupBox_2))


class SettingsPanel:
    """Two-level navigation (groups / subsections) over the stacked sections."""

    def __init__(self, gui, on_hidden=None):
        self.gui = gui
        self.on_hidden = on_hidden
        builders = {"@images": _images_section, "@size": _size_section, "@color": _color_section, "@text": _text_section}
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
                sub_button.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Fixed)
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

        fixed, maximum, preferred = (QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Maximum,
                                     QtWidgets.QSizePolicy.Policy.Preferred)
        for strip in (self.sub_strip, group_strip):  # the strips never take the free space (P9.4)
            strip.setSizePolicy(fixed, preferred)
        self.widget.setSizePolicy(maximum, preferred)  # the canvas gets the rest
        panel_layout.addWidget(self.scroll)
        panel_layout.addWidget(self.sub_strip)
        panel_layout.addWidget(group_strip)
        central = gui.centralwidget.layout()
        central.replaceWidget(gui.control_tabWidget, self.widget)
        central.setStretch(0, 1)  # the free width goes to the canvas, not to the panel (P9.4)
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
    c.tool_slot = bar.addSeparator()  # P9.10: the active-tool indicator goes before this separator

    # (P9.6: the image operations live in the Images section again)

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
    _iconify_remaining(gui)
    panel = build_panel(gui, on_hidden=reset_tools)
    c.tools = Tools.ToolController(gui, c.image_colorer)  # P9.10: hotkeys D F R P C T + indicator
    c.tools.add_indicator(gui.toolBar, before=c.tool_slot)
    c.tool_wheel = Tools.ToolWheel(c.tools, gui.image_canvas.viewport(), c.event_handler)  # P9.11
    tg = c.overlay_manager  # colour buttons: icons in the contrast colour of the current colour (P9.8)
    tg._style_color_button(gui.fill_color_button, tg.current_fill_color)
    tg._style_color_button(gui.outline_color_button, tg.current_outline_color)
    return panel
