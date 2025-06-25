from PyQt6 import QtWidgets
from Database.database_main import DatabaseNavigatorWidget,NavigatorMode

class AutomatedProcessor:
    def __init__(self, data_handler, hatcher, parser, gui):
        self.data_handler = data_handler
        self.hatcher = hatcher
        self.parser = parser
        self.gui = gui

        self.color_palettes = None

        #load the GUI
        self.selected_laser_label = gui.selected_laser_label
        self.selected_material_label = gui.selected_material_label
        self.selected_material_type_label = gui.selected_material_type_label
        self.load_material_profile_button = gui.load_material_profile_button
        self.load_material_profile_button.clicked.connect(self.load_material_profile)
        self.automatic_gcode_file_button = gui.automatic_gcode_file_button
        self.automatic_gcode_file_button.clicked.connect(self.automatic_gcode_file)


    def load_material_profile(self):

        def on_profile_received(data):
            if data is not None:
                ids = data['identifiers']
                self.color_palettes = data['parameters']
                self.selected_laser_label.setText(f"<b> {ids['laser']['name']} </b>")
                self.selected_material_label.setText(f"<b> {ids['material']['name']} </b>")
                self.selected_material_type_label.setText(f"<b> {ids['material_type']['name']} </b>")


        dialog = QtWidgets.QDialog()
        dialog.setWindowTitle("Select Profile")
        layout = QtWidgets.QVBoxLayout(dialog)
        navigator=DatabaseNavigatorWidget(NavigatorMode.SELECT_PROFILE,parent=dialog)
        navigator.selection_button_box.rejected.connect(dialog.reject)
        navigator.profileSelected.connect(on_profile_received)
        layout.addWidget(navigator)
        dialog.exec()
    
    def automatic_gcode_file(self):
        self.hatcher.create_hatching(mode="automatic", database_params=self.color_palettes)