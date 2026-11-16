import json
import logging
from PyQt6 import QtWidgets, QtGui, QtCore
from core import machine
from PyQt6.QtWidgets import QFileDialog
from Database.database_main import DatabaseNavigatorWidget,NavigatorMode

log = logging.getLogger(__name__)

# config key -> widget attribute name on the gui
IMAGE_SETTINGS = {
    'color_count': 'color_count_spinbox',
    'quantize_method': 'quantize_method_combobox',
    'sharpness': 'sharpness_slider',
    'brightness': 'brightness_slider',
    'contrast': 'contrast_slider',
    'pen_width': 'pen_width_spinbox',
    'contour_thickness': 'contour_thickness_spinbox',
    'contour_space': 'contour_space_spinbox',
}
HATCHING_SETTINGS = {
    'machine_profile': 'machine_profile_combobox',  # first, so the mode options below exist when loading
    'hatch_pattern': 'hatch_pattern_combobox',
    'hatch_angle': 'hatch_angle_spinbox',
    'hatch_dist_mode': 'hatch_dist_mode_combobox',
    'hatch_dist_min': 'hatch_dist_min_spinbox',
    'hatch_dist_max': 'hatch_dist_max_spinbox',
    'hatch_mode': 'hatch_mode_combobox',
    'cyl_rad': 'cyl_rad_spinbox',
    'hatch_precision': 'hatch_precision_spinbox',
    'random_seed': 'random_seed_spinbox',
    'contour_source': 'contour_source_combobox',
    'laser_mode': 'laser_mode_combobox',
    'max_power': 'max_power_spinbox',
    'min_power': 'min_power_spinbox',
    'max_speed': 'max_speed_spinbox',
    'min_speed': 'min_speed_spinbox',
    'offset_x': 'offset_x_spinbox',
    'offset_y': 'offset_y_spinbox',
    'offset_z': 'offset_z_spinbox',
    'export_format': 'export_format_combobox',
    'post_processing': 'post_processing_combobox',
    'power_format': 'power_format_combobox',
    'power_mode': 'power_mode_combobox',
    'speed_format': 'speed_format_combobox',
    'iterations': 'iterations_spinbox',
    'air_assist': 'air_assist_combobox',
}
ALL_SETTINGS = {**IMAGE_SETTINGS, **HATCHING_SETTINGS}


class Settings:
    def __init__(self, gui):
        self.gui = gui

        # Create File Menu
        self.menubar = gui.menubar
        self.actionLoad_Config = gui.actionLoad_Config
        self.actionLoad_Config.triggered.connect(self.load_config)
        self.actionSave_Config = gui.actionSave_Config
        self.actionSave_Config.triggered.connect(self.save_config)
        self.actionOpenColorDatabase = gui.actionOpenColorDatabase
        self.actionOpenColorDatabase.triggered.connect(self.open_color_database)
        self.action_open_profiles = QtGui.QAction("Open Machine Profiles Folder", gui)
        self.action_open_profiles.triggered.connect(
            lambda: QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(machine.USER_DIR))))
        for menu in gui.menubar.findChildren(QtWidgets.QMenu):
            if self.actionOpenColorDatabase in menu.actions():
                menu.addAction(self.action_open_profiles)
                break

    def load_config(self):
        options = QFileDialog.Option.DontUseNativeDialog
        file_path, _ = QFileDialog.getOpenFileName(self.gui, "Load Configuration", "", "JSON Files (*.json)", options=options)
        if file_path:
            with open(file_path, 'r') as f:
                self.apply_settings(json.load(f))
            QtWidgets.QMessageBox.information(self.gui, "Config Loaded", "Successfully loaded config")

    def apply_settings(self, settings):
        """Apply the settings present in the dict; unknown keys are ignored."""
        for key, value in settings.items():
            if key not in ALL_SETTINGS:
                continue
            widget = getattr(self.gui, ALL_SETTINGS[key])
            try:
                if isinstance(widget, QtWidgets.QComboBox):
                    if isinstance(value, int):  # configs before 2.0 stored the index
                        widget.setCurrentIndex(value)
                    elif widget.findText(value) >= 0:
                        widget.setCurrentText(value)
                    else:
                        log.warning("Setting %s: unknown option %r", key, value)
                else:
                    widget.setValue(value)
            except Exception as e:
                log.warning("Error applying setting %s: %s", key, e)

    def collect_settings(self, keys):
        settings = {}
        for key, widget_name in keys.items():
            widget = getattr(self.gui, widget_name)
            # B19: comboboxes are stored by text, indices break when the item list changes
            settings[key] = widget.currentText() if isinstance(widget, QtWidgets.QComboBox) else widget.value()
        return settings

    def save_config(self):
        """P8.1: one file with all settings (old _imageconfig / _hatchingconfig files still load)."""
        options = QFileDialog.Option.DontUseNativeDialog
        file_path, _ = QFileDialog.getSaveFileName(self.gui, "Save Config", "", "JSON Files (*.json)", options=options)
        if file_path:
            if not file_path.lower().endswith('.json'):
                file_path += '.json'
            with open(file_path, 'w') as f:
                json.dump(self.collect_settings(ALL_SETTINGS), f, indent=4)

    def open_color_database(self):
        self.editor_window = QtWidgets.QMainWindow()
        navigator = DatabaseNavigatorWidget(mode=NavigatorMode.FULL_EDIT)
        self.editor_window.setWindowTitle("Database Manager")
        self.editor_window.setCentralWidget(navigator)
        self.editor_window.setGeometry(150, 150, 600, 850)
        self.editor_window.show()
