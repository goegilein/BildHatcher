"""P8.6 / P8.7 / P9.3-P9.5 / P10: main window layout – toolbar ("hotbar") and the right-hand settings panel.

The sections, their pictograms, tooltips and sizes come from GUI_Files/BildHatcher.ui (edit them in Qt Designer);
this module only arranges them. Panel navigation has two levels: an outer strip with one (icon) button per group –
single select, clicking the active group closes the panel – and an inner strip with the subsections of the active
group (P10.6: single select as well – one section at a time; P12.10: a section can be pinned with the pin at its
top right – pinned sections stay visible whatever group is active). The open and pinned subsections of every group are remembered (Preferences "panel").
P10: the panel has one fixed width – the width of the Images section; every section is laid out to fit it.
"""
from PyQt6 import QtCore, QtWidgets

import icons
import ImageBar
import Preferences
import theme
import Tools

# group: (icon, [(strip label, tooltip / full name, section groupbox in the .ui)])
GROUPS = {
    "Image Editing": ("group-image-edit", [
        ("Adjust", "Image adjustments: colors, brightness, contrast, filter", "image_adjustment_frame"),
        ("Color", "Color image: paint, fill, contours, clean up", "image_color_frame"),
        ("Masks", "Mask drawing", "draw_mask_groupbox"),
        ("Text and Shapes", "Text and geometries", "tg_frame"),
    ]),
    "Hatching": ("group-hatching", [
        ("Hatch", "Image hatching and contours / outlines", "hatch_frame"),
        ("Cutting", "Cutting: draw single laser paths (lines, shapes) and use them as hatch", "cutting_frame"),
        ("Tests", "Test structures", "testStruc_frame"),
        ("Export", "Build NC data: process blocks and export", "export_frame"),
    ]),
    "Automation": ("group-automation", [("Automation", "Automatic J-code generation (uses the active color profile)",
                                         "laser_settings_frame")]),
}
# Images, Size and Center are drop-downs of the image tool bar row (ImageBar)
WIDTH_SOURCE = "images_frame"  # P10: every section gets the width of the Images section
DEFAULT_STATE = {"group": "Image Editing", "open": {"Image Editing": ["Adjust"], "Hatching": ["Hatch"],
                                                    "Automation": ["Automation"]}}
OLD_GROUPS = {"Image": "Image Editing", "Text": "Image Editing"}  # remembered states of older versions
OLD_SECTIONS = {"Text": "Text and Shapes"}


def _state():
    """The remembered panel state, cleaned: groups and sections that no longer exist are mapped or dropped."""
    state = Preferences.get("panel") or DEFAULT_STATE
    group = OLD_GROUPS.get(state.get("group"), state.get("group"))
    if group not in GROUPS:
        group = None if state.get("group") is None and "group" in state else DEFAULT_STATE["group"]
    labels = {group_name: [e[0] for e in entries] for group_name, (_, entries) in GROUPS.items()}
    open_sections = {}
    for old_group, sections in (state.get("open") or {}).items():
        new_group = OLD_GROUPS.get(old_group, old_group)
        if new_group in GROUPS and not open_sections.get(new_group):
            valid = [OLD_SECTIONS.get(label, label) for label in sections]
            open_sections[new_group] = [label for label in valid if label in labels[new_group]]
    for group_name in GROUPS:
        if group_name not in open_sections:
            open_sections[group_name] = list(DEFAULT_STATE["open"][group_name])
    every = {label for entries in labels.values() for label in entries}
    pinned = [OLD_SECTIONS.get(label, label) for label in state.get("pinned", [])]
    return {"group": group, "open": open_sections, "pinned": [label for label in pinned if label in every]}


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


def _take(widget):
    """Remove a widget from its current layout (it is re-added elsewhere)."""
    parent = widget.parentWidget()
    if parent is not None and parent.layout() is not None:
        parent.layout().removeWidget(widget)
    return widget


class SettingsPanel:
    """Two-level navigation (groups / subsections) over the stacked sections."""

    def __init__(self, gui, on_hidden=None):
        self.gui = gui
        self.on_hidden = on_hidden
        state = _state()
        self.open = {group: list(state["open"][group])[:1] for group in GROUPS}  # P10.6: one open section per group
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
                section = _take(getattr(gui, source))
                for inside in section.findChildren(QtWidgets.QGroupBox):
                    if inside.property("styleClass") == "insideFrame":
                        inside.show()
                section.setVisible(False)
                self.content_layout.addWidget(section)
                sub_button = _styled(VerticalButton(label), "SectionTab")  # Atelier style class
                sub_button.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Fixed)
                sub_button.setCheckable(True)
                sub_button.setToolTip(tooltip)
                sub_button.setChecked(label in self.open[group])
                sub_button.toggled.connect(lambda checked, g=group, l=label: self._toggle_section(g, l, checked))
                sub_button.hide()
                sub_layout.addWidget(sub_button)
                self.sections[label], self.section_buttons[label], self.group_of[label] = section, sub_button, group
        theme.on_change(lambda: [b.setIcon(icons.icon(GROUPS[g][0])) for g, b in self.group_buttons.items()])
        self.content_layout.addStretch(1)
        sub_layout.addStretch(1)
        # P10: one width for every section (and so for the panel): the Images section's (now the Images drop-down),
        # measured with the stylesheet applied; never narrower than a section needs (tests: Images is the widest)
        width_source = getattr(gui, WIDTH_SOURCE)
        width_source.ensurePolished()
        for section in self.sections.values():
            section.ensurePolished()
        self.width = max([width_source.sizeHint().width()] +
                         [section.minimumSizeHint().width() for section in self.sections.values()])
        for section in self.sections.values():
            section.setFixedWidth(self.width)
        self.scroll.setFixedWidth(self.width + self.scroll.verticalScrollBar().sizeHint().width() + 4)
        # P12.10: a pin at the top right of every section
        self.pinned = {label for label in state.get("pinned", []) if label in self.sections}
        self.pin_buttons = {}
        for label, section in self.sections.items():
            pin = _styled(QtWidgets.QToolButton(section, objectName=f"pin_button_{label}"), "PinButton")
            pin.setCheckable(True)
            pin.setChecked(label in self.pinned)
            pin.setIcon(icons.toggle_icon("pin", "pin-on"))
            pin.setIconSize(QtCore.QSize(18, 18))
            pin.setFixedSize(22, 22)
            pin.setToolTip("Pin: keep this section visible in every group")
            pin.move(self.width - 32, 4)
            pin.raise_()
            pin.toggled.connect(lambda on, l=label: self._toggle_pin(l, on))
            self.pin_buttons[label] = pin
        theme.on_change(lambda: [b.setIcon(icons.toggle_icon("pin", "pin-on")) for b in self.pin_buttons.values()])
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
        if shown:  # P10.6: single select – the other sections of the group close
            for other in self.open[group]:
                if other != label:
                    button = self.section_buttons[other]
                    button.blockSignals(True)
                    button.setChecked(False)
                    button.blockSignals(False)
            self.open[group] = [label]
        elif label in self.open[group]:
            self.open[group].remove(label)
        self._refresh()
        self._remember()

    def _toggle_pin(self, label, pinned):
        """Pinned: always visible. Unpinned: closes at once unless it is the open section of the active group."""
        if pinned:
            self.pinned.add(label)
        else:
            self.pinned.discard(label)
        self._refresh()
        self._remember()

    def _refresh(self):
        any_visible = False
        for label, section in self.sections.items():
            active = self.group_of[label] == self.group and label in self.open[self.group_of[label]]
            visible = active or label in self.pinned
            if section.isVisibleTo(self.widget) and not visible and self.on_hidden is not None:
                self.on_hidden(label)
            section.setVisible(visible)
            any_visible = any_visible or visible
        self.sub_strip.setVisible(self.group is not None)
        self.scroll.setVisible(any_visible)  # fixed width (P10); only the group strip when nothing is open

    def _remember(self):
        Preferences.put("panel", {"group": self.group, "open": self.open, "pinned": sorted(self.pinned)})


def build_panel(gui, on_hidden=None):
    return SettingsPanel(gui, on_hidden)


class _EnabledMirror(QtCore.QObject):
    """Keeps an action enabled exactly while its panel button is."""

    def __init__(self, action, button):
        super().__init__(button)
        self.action, self.button = action, button
        button.installEventFilter(self)
        action.setEnabled(button.isEnabled())

    def eventFilter(self, obj, event):
        if event.type() == QtCore.QEvent.Type.EnabledChange:
            self.action.setEnabled(self.button.isEnabled())
        return False


def mirror_button(action, button):
    """Toolbar action that does what `button` does and is enabled when it is."""
    action.triggered.connect(lambda: button.click() if button.isEnabled() else None)
    action._mirror = _EnabledMirror(action, button)
    return action


def build_toolbar(gui, c):
    """File / image / view actions, colour profile and machine in the toolbar."""
    bar = gui.toolBar
    bar.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonIconOnly)  # P9.2: pictograms, texts as tooltips
    bar.setIconSize(QtCore.QSize(22, 22))
    for action in (gui.actionLoad_Image, gui.actionSave_Image, gui.actionNew_Blank):  # icons from the .ui
        bar.addAction(action)
    c.tool_slot = bar.addSeparator()  # P9.10: the active-tool indicator goes before this separator

    # P10.6: imprint colours / overlays – the same as the buttons in the Color and Text sections
    for action, button in ((gui.actionImprint_Colors, gui.imprint_color_overlays_button),
                           (gui.actionImprint_Overlays, gui.imprint_selected_tg_overlays_button),
                           (gui.actionImprint_Masks, gui.imprint_mask_button)):  # P12.4: lifted masks
        mirror_button(action, button)
        bar.addAction(action)
        _styled(bar.widgetForAction(action), "ImprintAction")  # highlighted while something waits to be imprinted
    bar.addSeparator()

    # (the number of colours of the image: next to the Images button in the image tool bar row, ImageBar)

    # (P9.6: the image operations live in the Images section again)

    # view: zoom, reset, re-center, grid
    mover = c.image_sizer
    gui.zoom_slider.hide()  # the zoom field alone is enough in the toolbar (wheel / pinch zoom still work)
    gui.zoom_spinbox.setSuffix(" %")
    gui.zoom_spinbox.setToolTip("Zoom")
    zoom_action = bar.addAction(icons.icon("zoom-reset"), "Reset Zoom")  # reset first, then the zoom level
    zoom_action.triggered.connect(lambda: mover.reset_zoom())
    bar.addWidget(_take(gui.zoom_spinbox))
    center_action = bar.addAction(icons.icon("recenter"), "Re-Center Image")
    center_action.triggered.connect(lambda: mover.recenter_image())
    bar.addSeparator()  # the grid stands apart
    grid_action = bar.addAction(icons.toggle_icon("grid", "grid-hide"), "Grid")
    grid_action.setCheckable(True)
    grid_action.toggled.connect(lambda checked: mover.toggle_grid() if checked != mover.grid_on else None)
    gui.grid_distance_spinbox.setSuffix(" mm")
    gui.grid_distance_spinbox.setToolTip("Grid distance")
    bar.addWidget(_take(gui.grid_distance_spinbox))
    gui.image_scaler_frame.hide()
    bar.addSeparator()

    # application-wide profiles
    c.color_profiles.action.setIcon(icons.icon("color-profile"))
    bar.addAction(c.color_profiles.action)
    bar.widgetForAction(c.color_profiles.action).setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
    machine_label = QtWidgets.QLabel()
    machine_label.setPixmap(icons.icon("machine").pixmap(22, 22))
    machine_label.setToolTip("Machine profile")
    bar.addWidget(machine_label)
    gui.machine_profile_label.hide()
    bar.addWidget(_take(gui.machine_profile_combobox))

    def refresh_icons():  # P11.3: bright / dark mode switch
        zoom_action.setIcon(icons.icon("zoom-reset"))
        center_action.setIcon(icons.icon("recenter"))
        grid_action.setIcon(icons.toggle_icon("grid", "grid-hide"))
        c.color_profiles.action.setIcon(icons.icon("color-profile"))
        machine_label.setPixmap(icons.icon("machine").pixmap(22, 22))
    theme.on_change(refresh_icons)


def build_theme_switch(gui):
    """P11.3: Modes > Bright Mode switches the Atelier style between dark and bright (remembered)."""
    action = gui.actionBright_Mode
    action.setCheckable(True)
    action.setChecked(theme.MODE == "light")

    def switch(bright):
        mode = "light" if bright else "dark"
        if mode != theme.MODE:
            theme.set_mode(mode, gui)
            Preferences.put("theme", mode)
    action.toggled.connect(switch)
    return action


def build(gui, c):
    """Arrange toolbar and settings panel (call after main.create_components)."""
    build_toolbar(gui, c)
    c.image_bar = ImageBar.build(gui, c)  # second row: Images / Size / Center drop-downs (before the panel)
    # hiding the mask section switches off the mask tools (colour tools stay active: they have hotkeys, P9.10)
    reset_tools = lambda name: c.image_colorer.set_single_toggle_state('') if name == "Masks" else None
    panel = build_panel(gui, on_hidden=reset_tools)
    c.tools = Tools.ToolController(gui, c.image_colorer)  # P9.10: hotkeys D F R P C T + indicator
    c.single_tool = Tools.SingleActiveTool(gui, c)  # one canvas tool at a time: a new one ends the old one
    c.delete_key = Tools.DeleteHotkey(gui, c)  # Del: delete the selected overlays / mask
    c.tools.add_indicator(gui.toolBar, before=c.tool_slot)
    c.canvas_cursors = Tools.CanvasCursors(gui, c.image_colorer, c.event_handler)  # P11: tool cursors, pen outline
    c.tool_wheel = Tools.ToolWheel(c.tools, gui.image_canvas.viewport(), c.event_handler)  # P9.11
    tg = c.overlay_manager  # colour buttons: icons in the contrast colour of the current colour (P9.8)
    tg._style_color_button(gui.fill_color_button, tg.current_fill_color)
    tg._style_color_button(gui.outline_color_button, tg.current_outline_color)
    build_theme_switch(gui)
    theme.fit_dropdown_popups(gui)  # drop-down lists wider than the narrow combo boxes
    return panel
