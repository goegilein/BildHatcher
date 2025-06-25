import json
from PyQt6 import QtWidgets
from PyQt6.QtWidgets import QFileDialog
from Database.database_main import DatabaseNavigatorWidget,NavigatorMode

class Settings:
    def __init__(self, gui):
        self.gui = gui

        # Create File Menu
        self.menubar = gui.menubar
        self.actionLoad_Config = gui.actionLoad_Config
        self.actionLoad_Config.triggered.connect(self.load_config)
        self.actionSave_ImageConfig = gui.actionSave_ImageConfig
        self.actionSave_ImageConfig.triggered.connect(self.save_image_config)
        self.actionSave_HatchingConfig = gui.actionSave_HatchingConfig
        self.actionSave_HatchingConfig.triggered.connect(self.save_hatching_config)
        self.actionOpenColorDatabase = gui.actionOpenColorDatabase
        self.actionOpenColorDatabase.triggered.connect(self.open_color_database)

    def load_config(self):
        options = QFileDialog.Option.DontUseNativeDialog
        file_path, _ = QFileDialog.getOpenFileName(self.gui, "Load Configuration", "", "JSON Files (*.json)", options=options)
        if file_path:
            with open(file_path, 'r') as f:
                settings = json.load(f)
            # Only apply the settings present in the loaded config
            for key, value in settings.items():
                try:
                    if key == 'color_count':
                        self.gui.color_count_spinbox.setValue(value)
                    elif key == 'quantize_method':
                        self.gui.quantize_method_combobox.setCurrentIndex(value)
                    elif key == 'sharpness':
                        self.gui.sharpness_slider.setValue(value)
                    elif key == 'brightness':
                        self.gui.brightness_slider.setValue(value)
                    elif key == 'contrast':
                        self.gui.contrast_slider.setValue(value)
                    elif key == 'pen_width':
                        self.gui.pen_width_spinbox.setValue(value)
                    elif key == 'contour_thickness':
                        self.gui.contour_thickness_spinbox.setValue(value)
                    elif key == 'contour_space':
                        self.gui.contour_space_spinbox.setValue(value)
                    elif key == 'hatch_pattern':
                        self.gui.hatch_pattern_combobox.setCurrentIndex(value)
                    elif key == 'hatch_angle':
                        self.gui.hatch_angle_spinbox.setValue(value)
                    elif key == 'hatch_dist_mode':
                        self.gui.hatch_dist_mode_combobox.setCurrentIndex(value)
                    elif key == 'hatch_dist_min':
                        self.gui.hatch_dist_min_spinbox.setValue(value)
                    elif key == 'hatch_dist_max':
                        self.gui.hatch_dist_max_spinbox.setValue(value)
                    elif key == 'hatch_mode':
                        self.gui.hatch_mode_combobox.setCurrentIndex(value)
                    elif key == 'cyl_rad':
                        self.gui.cyl_rad_spinbox.setValue(value)
                    elif key == 'hatch_precision':
                        self.gui.hatch_precision_spinbox.setValue(value)
                    elif key == 'contour_source':
                        self.gui.contour_source_combobox.setCurrentIndex(value)
                    elif key == 'laser_mode':
                        self.gui.laser_mode_combobox.setCurrentIndex(value)
                    elif key == 'white_threshold_parsing':
                        self.gui.white_threshold_parsing_spinbox.setValue(value)
                    elif key == 'max_power':
                        self.gui.max_power_spinbox.setValue(value)
                    elif key == 'min_power':
                        self.gui.min_power_spinbox.setValue(value)
                    elif key == 'max_speed':
                        self.gui.max_speed_spinbox.setValue(value)
                    elif key == 'min_speed':
                        self.gui.min_speed_spinbox.setValue(value)
                    elif key == 'offset_x':
                        self.gui.offset_x_spinbox.setValue(value)
                    elif key == 'offset_y':
                        self.gui.offset_y_spinbox.setValue(value)
                    elif key == 'offset_z':
                        self.gui.offset_z_spinbox.setValue(value)
                    elif key == 'export_format':
                        self.gui.export_format_combobox.setCurrentIndex(value)
                    elif key == 'post_processing':
                        self.gui.post_processing_combobox.setCurrentIndex(value)
                    elif key == 'power_format':
                        self.gui.power_format_combobox.setCurrentIndex(value)
                    elif key == 'speed_format':
                        self.gui.speed_format_combobox.setCurrentIndex(value)
                    elif key == 'iterations':
                        self.gui.iterations_spinbox.setValue(value)
                except Exception as e:
                    print(f"Error applying setting {key}: {e}")
            QtWidgets.QMessageBox.information(self.gui, "Konfig Loaded", "Successfully loaded Konfig")

    def save_image_config(self):
        settings = self._collect_image_settings()
        options = QFileDialog.Option.DontUseNativeDialog
        file_path, _ = QFileDialog.getSaveFileName(self.gui, "Save Image Settings", "", "JSON Files (*.json)", options=options)
        if file_path:
            if not file_path.lower().endswith('_imageconfig.json'):
                if file_path.lower().endswith('.json'):
                    file_path = file_path[:-5] + '_imageconfig.json'
                else:
                    file_path += '_imageconfig.json'
            with open(file_path, 'w') as f:
                json.dump(settings, f, indent=4)

    def save_hatching_config(self):
        settings = self._collect_hatching_settings()
        options = QFileDialog.Option.DontUseNativeDialog
        file_path, _ = QFileDialog.getSaveFileName(self.gui, "Save Hatching Settings", "", "JSON Files (*.json)", options=options)
        if file_path:
            if not file_path.lower().endswith('_hatchingconfig.json'):
                if file_path.lower().endswith('.json'):
                    file_path = file_path[:-5] + '_hatchingconfig.json'
                else:
                    file_path += '_hatchingconfig.json'
            with open(file_path, 'w') as f:
                json.dump(settings, f, indent=4)

    def _collect_image_settings(self):
        gui = self.gui
        settings = {}
        try:
            settings['color_count'] = gui.color_count_spinbox.value()
            settings['quantize_method'] = gui.quantize_method_combobox.currentIndex()
            settings['sharpness'] = gui.sharpness_slider.value()
            settings['brightness'] = gui.brightness_slider.value()
            settings['contrast'] = gui.contrast_slider.value()
            settings['pen_width'] = gui.pen_width_spinbox.value()
            settings['contour_thickness'] = gui.contour_thickness_spinbox.value()
            settings['contour_space'] = gui.contour_space_spinbox.value()
            # Add more image adjustment tab settings as needed
        except Exception as e:
            print(f"Error collecting image settings: {e}")
        return settings

    def _collect_hatching_settings(self):
        gui = self.gui
        settings = {}
        try:
            settings['hatch_pattern'] = gui.hatch_pattern_combobox.currentIndex()
            settings['hatch_angle'] = gui.hatch_angle_spinbox.value()
            settings['hatch_dist_mode'] = gui.hatch_dist_mode_combobox.currentIndex()
            settings['hatch_dist_min'] = gui.hatch_dist_min_spinbox.value()
            settings['hatch_dist_max'] = gui.hatch_dist_max_spinbox.value()
            settings['hatch_mode'] = gui.hatch_mode_combobox.currentIndex()
            settings['cyl_rad'] = gui.cyl_rad_spinbox.value()
            settings['hatch_precision'] = gui.hatch_precision_spinbox.value()
            settings['contour_source'] = gui.contour_source_combobox.currentIndex()
            settings['laser_mode'] = gui.laser_mode_combobox.currentIndex()
            settings['white_threshold_parsing'] = gui.white_threshold_parsing_spinbox.value()
            settings['max_power'] = gui.max_power_spinbox.value()
            settings['min_power'] = gui.min_power_spinbox.value()
            settings['max_speed'] = gui.max_speed_spinbox.value()
            settings['min_speed'] = gui.min_speed_spinbox.value()
            settings['offset_x'] = gui.offset_x_spinbox.value()
            settings['offset_y'] = gui.offset_y_spinbox.value()
            settings['offset_z'] = gui.offset_z_spinbox.value()
            settings['export_format'] = gui.export_format_combobox.currentIndex()
            settings['post_processing'] = gui.post_processing_combobox.currentIndex()
            settings['power_format'] = gui.power_format_combobox.currentIndex()
            settings['speed_format'] = gui.speed_format_combobox.currentIndex()
            settings['iterations'] = gui.iterations_spinbox.value()
            # Add more hatching tab settings as needed
        except Exception as e:
            print(f"Error collecting hatching settings: {e}")
        return settings
    
    def open_color_database(self):
        self.editor_window = QtWidgets.QMainWindow()
        navigator = DatabaseNavigatorWidget(mode=NavigatorMode.FULL_EDIT)
        self.editor_window.setWindowTitle("Database Manager")
        self.editor_window.setCentralWidget(navigator)
        self.editor_window.setGeometry(150, 150, 600, 850)
        self.editor_window.show()

