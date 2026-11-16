from PyQt6 import QtWidgets

class AutomatedProcessor:
    def __init__(self, data_handler, hatcher, parser, gui):
        self.data_handler = data_handler
        self.hatcher = hatcher
        self.parser = parser
        self.gui = gui

        #load the GUI
        #DB Settings
        self.selected_laser_label = gui.selected_laser_label
        self.selected_material_label = gui.selected_material_label
        self.selected_material_type_label = gui.selected_material_type_label
        self.load_material_profile_button = gui.load_material_profile_button
        self.load_material_profile_button.clicked.connect(self.load_material_profile)
        self.profiles = data_handler.color_profiles
        self.profiles.callbacks.append(self.show_profile)
        self.show_profile(data_handler.color_profile)

        #Hatching and Parsing Settings
        self.automatic_gcode_file_button = gui.automatic_gcode_file_button
        self.automatic_gcode_file_button.clicked.connect(self.automatic_gcode_file)
        self.automatic_post_processing_comboBox = gui.automatic_post_processing_comboBox
        self.automatic_post_processing_comboBox.addItems(["None", "Maximize Lines", "Constant Drive", "Over Drive"])
        self.automatic_hatch_mode_comboBox = gui.automatic_hatch_mode_comboBox
        self.automatic_hatch_mode_comboBox.addItems(["Flat", "CylEquidistX", "CylEquidistRad"])
        self.automatic_cyl_rad_spinBox = gui.automatic_cyl_rad_spinBox


    def load_material_profile(self):
        self.profiles.choose()  # P8.5: sets the application-wide profile

    def show_profile(self, palette):
        ids = getattr(palette, "identifiers", None)
        for label, key in ((self.selected_laser_label, "laser"), (self.selected_material_label, "material"),
                           (self.selected_material_type_label, "material_type")):
            label.setText(f"<b> {ids[key]['name']} </b>" if ids else "-")
    
    def automatic_gcode_file(self):
        palette = self.profiles.require()
        if palette is None:
            QtWidgets.QMessageBox.warning(self.gui, "No Profile Selected", "Please select a material profile first.")
            return
        hatched = self.hatcher.create_hatching(
            mode="automatic",
            db_color_palette = palette,
            hatch_pattern = None,
            cyl_rad_mm = self.automatic_cyl_rad_spinBox.value(),
            hatch_mode = self.automatic_hatch_mode_comboBox.currentText(),
            stepsize_mm=  0.1)
        if not hatched:  # failed or cancelled: do not export stale hatch data
            return

        self.parser.automatic_jcode(
            db_color_palette = palette,
            offset = [0,0,0]
        )