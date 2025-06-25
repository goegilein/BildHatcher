import sys
import os
import sqlite3
from enum import Enum
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QInputDialog, QMessageBox,
    QPushButton, QColorDialog, QDialog, QVBoxLayout, QLabel, QLineEdit,
    QDialogButtonBox, QSpinBox, QComboBox, QDoubleSpinBox
)
from PyQt6.QtCore import Qt, pyqtSignal

# --- MODIFIED: Adjust import path for subfolder structure ---
# This assumes that from your main project folder, you would run the app,
# and Python can find the "Database" folder. You might need to adjust your PYTHONPATH
# or use relative imports if you structure it as a package.
# For now, we assume the UI file is accessible.
try:
    # This will work when you run the app from your main project folder.
    from Database.DatabaseNavigator_ui import Ui_DatabaseNavigatorWidget
except ImportError:
    # This will work when you run database_main.py directly for testing.
    from DatabaseNavigator_ui import Ui_DatabaseNavigatorWidget


# --- Enum for modes (unchanged) ---
class NavigatorMode(Enum):
    FULL_EDIT = 0
    SELECT_COLOR = 1
    SELECT_PROFILE = 2

# --- ConfirmDeleteDialog (unchanged) ---
class ConfirmDeleteDialog(QDialog):
    def __init__(self, item_name, item_type_str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Confirm Deletion")
        self.item_name=item_name; layout=QVBoxLayout(self)
        message=QLabel(f"This action is permanent and will delete all associated data.<br>To confirm deletion of the {item_type_str} named: <br><br><b>{item_name}</b><br><br>Please type the full name below and click OK.")
        message.setWordWrap(True); message.setTextFormat(Qt.TextFormat.RichText); layout.addWidget(message)
        self.confirmation_input=QLineEdit(self); layout.addWidget(self.confirmation_input)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel); buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addWidget(buttons)
    def get_confirmed(self): return self.confirmation_input.text()==self.item_name

# =============================================================================
#  DATABASE MANAGER CLASS (MODIFIED)
# =============================================================================
class DatabaseManager:
    # --- MODIFIED: The __init__ method now builds a robust path ---
    def __init__(self, db_subfolder="Database", db_filename="laser_database.db"):
        """
        Initializes the DatabaseManager.
        Constructs a path to the database file in a subfolder relative
        to this script's location, ensuring it's always found.
        """
        # Get the absolute path to the directory where this script is located
        script_dir = os.path.dirname(os.path.realpath(__file__))
        
        # Define the path to the database subfolder
        db_folder_path = os.path.join(script_dir, db_subfolder)
        
        # Create the subfolder if it doesn't exist
        os.makedirs(db_folder_path, exist_ok=True)
        
        # Define the full path to the database file
        self.db_file = os.path.join(db_folder_path, db_filename)
        
        db_exists=os.path.exists(self.db_file)
        self.conn=sqlite3.connect(self.db_file)
        self.conn.row_factory=sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.cursor=self.conn.cursor()
        if not db_exists:
            self.create_schema()

    def create_schema(self):
        # ... (schema creation is unchanged) ...
        with self.conn:
            self.cursor.execute("CREATE TABLE IF NOT EXISTS lasers (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE)")
            self.cursor.execute("CREATE TABLE IF NOT EXISTS materials (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE)")
            self.cursor.execute("CREATE TABLE IF NOT EXISTS material_types (id INTEGER PRIMARY KEY, material_id INTEGER NOT NULL, name TEXT NOT NULL, FOREIGN KEY (material_id) REFERENCES materials (id) ON DELETE CASCADE, UNIQUE (material_id, name))")
            self.cursor.execute("CREATE TABLE IF NOT EXISTS color_palettes (id INTEGER PRIMARY KEY, laser_id INTEGER NOT NULL, material_type_id INTEGER NOT NULL, FOREIGN KEY (laser_id) REFERENCES lasers (id) ON DELETE CASCADE, FOREIGN KEY (material_type_id) REFERENCES material_types (id) ON DELETE CASCADE, UNIQUE (laser_id, material_type_id))")
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS parameters (
                    id INTEGER PRIMARY KEY, palette_id INTEGER NOT NULL, color_name TEXT NOT NULL, 
                    color_rgb TEXT NOT NULL, hatch_distance REAL NOT NULL, hatch_pattern TEXT NOT NULL,
                    hatch_angle INTEGER NOT NULL, laser_power REAL NOT NULL, speed REAL NOT NULL,
                    FOREIGN KEY (palette_id) REFERENCES color_palettes (id) ON DELETE CASCADE,
                    UNIQUE (palette_id, color_name)
                );""")
        print(f"Database schema created/verified in {self.db_file}")

    def add_parameter(self,p_id,name,rgb,hatch_dist,hatch_pattern,hatch_angle,power,speed):
        try:
            with self.conn:
                self.cursor.execute("""INSERT INTO parameters(palette_id, color_name, color_rgb, hatch_distance, hatch_pattern, hatch_angle, laser_power, speed) VALUES (?,?,?,?,?,?,?,?)""", (p_id,name,rgb,hatch_dist,hatch_pattern,hatch_angle,power,speed))
                return self.cursor.lastrowid
        except sqlite3.IntegrityError:return None

    def update_parameter(self,p_id,name,rgb,hatch_dist,hatch_pattern,hatch_angle,power,speed):
        with self.conn:
            self.cursor.execute("""UPDATE parameters SET color_name=?, color_rgb=?, hatch_distance=?, hatch_pattern=?, hatch_angle=?, laser_power=?, speed=? WHERE id=?""", (name,rgb,hatch_dist,hatch_pattern,hatch_angle,power,speed,p_id))
            return self.cursor.rowcount>0
            
    # ... other database methods are unchanged ...
    def add_laser(self, name):
        try:
            with self.conn:self.cursor.execute("INSERT INTO lasers(name) VALUES (?)",(name,));return self.cursor.lastrowid
        except sqlite3.IntegrityError:return None
    def get_lasers(self): self.cursor.execute("SELECT * FROM lasers ORDER BY name");return self.cursor.fetchall()
    def update_laser(self, id, name): 
        with self.conn:self.cursor.execute("UPDATE lasers SET name=? WHERE id=?",(name,id));return self.cursor.rowcount>0
    def delete_laser(self, id): 
        with self.conn:self.cursor.execute("DELETE FROM lasers WHERE id=?",(id,));return self.cursor.rowcount>0
    def add_material(self, name):
        try:
            with self.conn:self.cursor.execute("INSERT INTO materials(name) VALUES (?)",(name,));return self.cursor.lastrowid
        except sqlite3.IntegrityError:return None
    def get_all_materials(self): self.cursor.execute("SELECT * FROM materials ORDER BY name");return self.cursor.fetchall()
    def update_material(self, id, name): 
        with self.conn:self.cursor.execute("UPDATE materials SET name=? WHERE id=?",(name,id));return self.cursor.rowcount>0
    def delete_material(self, id): 
        with self.conn:self.cursor.execute("DELETE FROM materials WHERE id=?",(id,));return self.cursor.rowcount>0
    def add_material_type(self, mat_id, name):
        try:
            with self.conn:self.cursor.execute("INSERT INTO material_types(material_id, name) VALUES (?,?)",(mat_id,name));return self.cursor.lastrowid
        except sqlite3.IntegrityError:return None
    def get_material_types_for_material(self, mat_id): self.cursor.execute("SELECT * FROM material_types WHERE material_id=? ORDER BY name",(mat_id,));return self.cursor.fetchall()
    def update_material_type(self, id, name): 
        with self.conn:self.cursor.execute("UPDATE material_types SET name=? WHERE id=?",(name,id));return self.cursor.rowcount>0
    def delete_material_type(self, id): 
        with self.conn:self.cursor.execute("DELETE FROM material_types WHERE id=?",(id,));return self.cursor.rowcount>0
    def get_or_create_palette(self, laser_id, type_id):
        with self.conn:
            self.cursor.execute("SELECT id FROM color_palettes WHERE laser_id=? AND material_type_id=?",(laser_id,type_id));res=self.cursor.fetchone()
            if res:return res['id']
            else:self.cursor.execute("INSERT INTO color_palettes(laser_id,material_type_id) VALUES (?,?)",(laser_id,type_id));return self.cursor.lastrowid
    def get_parameters(self, palette_id): self.cursor.execute("SELECT * FROM parameters WHERE palette_id=? ORDER BY color_name",(palette_id,));return self.cursor.fetchall()
    def delete_parameter(self, p_id): 
        with self.conn:self.cursor.execute("DELETE FROM parameters WHERE id=?",(p_id,));return self.cursor.rowcount>0
    def close(self): self.conn.close()

# =============================================================================
#  DATABASE NAVIGATOR WIDGET (Unchanged Logic)
# =============================================================================
class DatabaseNavigatorWidget(QWidget, Ui_DatabaseNavigatorWidget):
    colorSelected = pyqtSignal(dict)
    profileSelected = pyqtSignal(dict)
    
    def __init__(self, mode=NavigatorMode.FULL_EDIT, parent=None):
        super().__init__(parent)
        self.setupUi(self)
        
        self.db_manager = DatabaseManager()
        self.current_palette_id = None
        self.selected_param_id = None
        self.mode = mode
        
        self.hatch_patterns = ["FixedMeander", "RandomMeander", "CrossedMeander", "Circular", "Spiral", "Radial"]
        self.hatch_pattern_combo.addItems(self.hatch_patterns)
        
        self._connect_signals()
        self.set_mode(self.mode) 
        self._populate_lasers()
        self._update_ui_state()
    
    def _clear_color_palette(self):
        while self.color_grid_layout.count():
            item = self.color_grid_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _populate_lasers(self):
        current_id = self.laser_combo.currentData()
        self.laser_combo.blockSignals(True)
        self.laser_combo.clear()
        self.laser_combo.addItem("-None-", None)
        for laser in self.db_manager.get_lasers():
            self.laser_combo.addItem(laser['name'], userData=laser['id'])
        idx = self.laser_combo.findData(current_id)
        self.laser_combo.setCurrentIndex(idx if idx != -1 else 0)
        self.laser_combo.blockSignals(False)
        self._populate_materials()

    def _populate_materials(self):
        current_id = self.material_combo.currentData()
        self.material_combo.blockSignals(True)
        self.material_combo.clear()
        self.material_combo.addItem("-None-", None)
        for material in self.db_manager.get_all_materials():
            self.material_combo.addItem(material['name'], userData=material['id'])
        idx = self.material_combo.findData(current_id)
        self.material_combo.setCurrentIndex(idx if idx != -1 else 0)
        self.material_combo.blockSignals(False)
        self._populate_types()

    def _populate_types(self):
        current_id = self.type_combo.currentData()
        self.type_combo.blockSignals(True)
        self.type_combo.clear()
        self.type_combo.addItem("-None-", None)
        material_id = self.material_combo.currentData()
        if material_id is not None:
            for t in self.db_manager.get_material_types_for_material(material_id):
                self.type_combo.addItem(t['name'], userData=t['id'])
        idx = self.type_combo.findData(current_id)
        self.type_combo.setCurrentIndex(idx if idx != -1 else 0)
        self.type_combo.blockSignals(False)
        self._on_profile_selected()

    def _on_color_selected(self):
        for i in range(self.color_grid_layout.count()):
            w=self.color_grid_layout.itemAt(i).widget()
            if w is not self.sender(): w.setChecked(False)
        
        param_data=self.sender().property("param_data")
        if param_data:
            self.selected_param_id=param_data['id']
            if self.mode == NavigatorMode.FULL_EDIT:
                self.color_name_edit.setText(param_data['color_name'])
                self.color_rgb_label.setText(param_data['color_rgb'])
                self.color_rgb_btn.setStyleSheet(f"background-color:rgb({param_data['color_rgb']});")
                self.hatch_dist_spinbox.setValue(param_data['hatch_distance'])
                self.laser_power_spinbox.setValue(param_data['laser_power'])
                self.speed_spinbox.setValue(param_data['speed'])
                self.hatch_pattern_combo.setCurrentText(param_data['hatch_pattern'])
                self.hatch_angle_spinbox.setValue(param_data['hatch_angle'])
        self._update_ui_state()
        
    def _clear_parameter_details(self):
        self.selected_param_id = None
        self.color_name_edit.clear()
        self.color_rgb_label.clear()
        self.hatch_dist_spinbox.setValue(0.0)
        self.laser_power_spinbox.setValue(0.0)
        self.speed_spinbox.setValue(0.0)
        self.hatch_pattern_combo.setCurrentIndex(0)
        self.hatch_angle_spinbox.setValue(0)
        self.color_rgb_btn.setStyleSheet(""); self._update_ui_state()

    def _save_parameters(self):
        if not self.selected_param_id: return
        try:
            name=self.color_name_edit.text()
            rgb=self.color_rgb_label.text()
            hatch_dist = self.hatch_dist_spinbox.value()
            power = self.laser_power_spinbox.value()
            speed = self.speed_spinbox.value()
            hatch_pattern=self.hatch_pattern_combo.currentText()
            hatch_angle=self.hatch_angle_spinbox.value()
            self.db_manager.update_parameter(self.selected_param_id,name,rgb,hatch_dist,hatch_pattern,hatch_angle,power,speed)
            QMessageBox.information(self,"Success","Parameters updated.")
            self._populate_color_palette()
        except sqlite3.IntegrityError:QMessageBox.warning(self,"Update Failed","A color with this NAME already exists.")
        
    def _add_color(self):
        if not self.current_palette_id:return
        name,ok=QInputDialog.getText(self,"Add New Color","Enter name:")
        if ok and name:
            result = self.db_manager.add_parameter(self.current_palette_id,name,"255,255,255",0.5, "FixedMeander", 0, 50,500)
            if result is None: QMessageBox.warning(self,"Add Failed",f"Name '{name}' already exists.")
            else: self._populate_color_palette()

    def _get_complementary_color(self, rgb_list):
        r, g, b = rgb_list; luminance = (0.299*r + 0.587*g + 0.114*b) / 255
        return "black" if luminance > 0.5 else "white"
    
    def _populate_color_palette(self):
        self._clear_color_palette()
        if self.current_palette_id is None: return
        for param in self.db_manager.get_parameters(self.current_palette_id):
            color_btn=QPushButton(param['color_name']); color_btn.setCheckable(True)
            rgb=[int(c) for c in param['color_rgb'].split(',')]; bg=f"rgb({rgb[0]},{rgb[1]},{rgb[2]})"; txt=self._get_complementary_color(rgb)
            color_btn.setStyleSheet(f"background-color:{bg};color:{txt};"); color_btn.setProperty("param_data",param); color_btn.clicked.connect(self._on_color_selected)
            self.color_grid_layout.addWidget(color_btn, self.color_grid_layout.count() // 4, self.color_grid_layout.count() % 4)

    def set_mode(self, mode):
        self.mode = mode
        is_full_edit = (self.mode == NavigatorMode.FULL_EDIT)
        for btn in [self.add_laser_btn, self.edit_laser_btn, self.remove_laser_btn, self.add_material_btn, self.edit_material_btn, self.remove_material_btn, self.add_type_btn, self.edit_type_btn, self.remove_type_btn, self.add_color_btn, self.remove_color_btn]: btn.setVisible(is_full_edit)
        self.editor_group.setVisible(is_full_edit); self.save_params_btn.setVisible(is_full_edit); self.selection_button_box.setVisible(not is_full_edit)
        if self.mode == NavigatorMode.SELECT_COLOR: self.setWindowTitle("Select a Color")
        elif self.mode == NavigatorMode.SELECT_PROFILE: self.setWindowTitle("Select a Material Profile")
        else: self.setWindowTitle("Database Manager")

    def _connect_signals(self):
        self.laser_combo.currentIndexChanged.connect(self._populate_materials)
        self.material_combo.currentIndexChanged.connect(self._populate_types)
        self.type_combo.currentIndexChanged.connect(self._on_profile_selected)
        self.add_laser_btn.clicked.connect(self._add_laser)
        self.edit_laser_btn.clicked.connect(self._edit_laser)
        self.remove_laser_btn.clicked.connect(self._remove_laser)
        self.add_material_btn.clicked.connect(self._add_material)
        self.edit_material_btn.clicked.connect(self._edit_material)
        self.remove_material_btn.clicked.connect(self._remove_material)
        self.add_type_btn.clicked.connect(self._add_type)
        self.edit_type_btn.clicked.connect(self._edit_type)
        self.remove_type_btn.clicked.connect(self._remove_type)
        self.add_color_btn.clicked.connect(self._add_color)
        self.remove_color_btn.clicked.connect(self._remove_color)
        self.color_rgb_btn.clicked.connect(self._pick_color)
        self.save_params_btn.clicked.connect(self._save_parameters)
        self.selection_button_box.accepted.connect(self._on_selection_confirmed)

    def _on_selection_confirmed(self):
        if self.mode == NavigatorMode.SELECT_COLOR:
            if self.selected_param_id is not None:
                params = self.db_manager.get_parameters(self.current_palette_id)
                selected_data = next((p for p in params if p['id'] == self.selected_param_id), None)
                if selected_data: self.colorSelected.emit(dict(selected_data))
            else: QMessageBox.warning(self, "No Selection", "Please select a color."); return 
        elif self.mode == NavigatorMode.SELECT_PROFILE:
            if self.current_palette_id is not None:
                profile_identifiers = {'laser': {'id': self.laser_combo.currentData(), 'name': self.laser_combo.currentText()},'material': {'id': self.material_combo.currentData(), 'name': self.material_combo.currentText()},'material_type': {'id': self.type_combo.currentData(), 'name': self.type_combo.currentText()}}
                parameters_list = [dict(p) for p in self.db_manager.get_parameters(self.current_palette_id)]
                payload = {"identifiers": profile_identifiers, "parameters": parameters_list}
                self.profileSelected.emit(payload)
            else: QMessageBox.warning(self, "No Selection", "Please select a complete profile."); return 
        if isinstance(self.parent(), QDialog): self.parent().accept()
    
    def _on_profile_selected(self):
        laser_id,type_id=self.laser_combo.currentData(),self.type_combo.currentData()
        if laser_id is not None and type_id is not None: self.current_palette_id=self.db_manager.get_or_create_palette(laser_id,type_id)
        else: self.current_palette_id=None
        self._populate_color_palette();self._clear_parameter_details();self._update_ui_state()

    def _update_ui_state(self):
        self.edit_laser_btn.setEnabled(self.laser_combo.currentData() is not None);self.remove_laser_btn.setEnabled(self.laser_combo.currentData()is not None);self.edit_material_btn.setEnabled(self.material_combo.currentData()is not None);self.remove_material_btn.setEnabled(self.material_combo.currentData()is not None);self.add_type_btn.setEnabled(self.material_combo.currentData()is not None);self.edit_type_btn.setEnabled(self.type_combo.currentData()is not None);self.remove_type_btn.setEnabled(self.type_combo.currentData()is not None);self.add_color_btn.setEnabled(self.current_palette_id is not None);self.remove_color_btn.setEnabled(self.selected_param_id is not None);param_selected=self.selected_param_id is not None
        self.color_name_edit.setEnabled(param_selected);self.color_rgb_btn.setEnabled(param_selected);self.hatch_pattern_combo.setEnabled(param_selected);self.hatch_angle_spinbox.setEnabled(param_selected);self.save_params_btn.setEnabled(param_selected)
        self.hatch_dist_spinbox.setEnabled(param_selected);self.laser_power_spinbox.setEnabled(param_selected);self.speed_spinbox.setEnabled(param_selected)

    def _remove_laser(self):
        id,name=self.laser_combo.currentData(),self.laser_combo.currentText()
        if id and(d:=ConfirmDeleteDialog(name,"laser",self)).exec()and d.get_confirmed(): self.db_manager.delete_laser(id);self._populate_lasers()
    def _remove_material(self):
        mat_id,name=self.material_combo.currentData(),self.material_combo.currentText()
        if mat_id and(d:=ConfirmDeleteDialog(name,"material",self)).exec()and d.get_confirmed(): self.db_manager.delete_material(mat_id);self._populate_materials()
    def _remove_type(self):
        type_id,name=self.type_combo.currentData(),self.type_combo.currentText()
        if type_id and(d:=ConfirmDeleteDialog(name,"material type",self)).exec()and d.get_confirmed(): self.db_manager.delete_material_type(type_id);self._populate_types()
    def _add_laser(self):
        name, ok = QInputDialog.getText(self, "Add Laser", "Enter new laser name:")
        if ok and name: self.db_manager.add_laser(name); self._populate_lasers()
    def _edit_laser(self):
        laser_id, current_name = self.laser_combo.currentData(), self.laser_combo.currentText()
        if not laser_id: return
        name, ok = QInputDialog.getText(self, "Edit Laser", "New name:", text=current_name)
        if ok and name: self.db_manager.update_laser(laser_id, name); self._populate_lasers()
    def _add_material(self):
        name, ok = QInputDialog.getText(self, "Add Material", "Enter new material name:")
        if ok and name: self.db_manager.add_material(name); self._populate_materials()
    def _edit_material(self):
        mat_id, current_name = self.material_combo.currentData(), self.material_combo.currentText()
        if not mat_id: return
        name, ok = QInputDialog.getText(self, "Edit Material", "New name:", text=current_name)
        if ok and name: self.db_manager.update_material(mat_id, name); self._populate_materials()
    def _add_type(self):
        mat_id = self.material_combo.currentData()
        if not mat_id: return
        name, ok = QInputDialog.getText(self, "Add Type", "Enter new type name:")
        if ok and name: self.db_manager.add_material_type(mat_id, name); self._populate_types()
    def _edit_type(self):
        type_id, current_name = self.type_combo.currentData(), self.type_combo.currentText()
        if not type_id: return
        name, ok = QInputDialog.getText(self, "Edit Type", "New name:", text=current_name)
        if ok and name: self.db_manager.update_material_type(type_id, name); self._populate_types()
    def _remove_color(self):
        if self.selected_param_id:
            reply = QMessageBox.question(self,"Remove Color","Are you sure?")
            if reply == QMessageBox.StandardButton.Yes: self.db_manager.delete_parameter(self.selected_param_id); self._clear_parameter_details(); self._populate_color_palette()
    def _pick_color(self):
        color=QColorDialog.getColor()
        if color.isValid(): rgb=f"{color.red()},{color.green()},{color.blue()}"; self.color_rgb_label.setText(rgb); self.color_rgb_btn.setStyleSheet(f"background-color:{color.name()};")

# =============================================================================
#  APPLICATION LAUNCHER
# =============================================================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__();self.setWindowTitle("Main Application");self.setGeometry(100,100,400,200)
        central=QWidget();self.setCentralWidget(central);layout=QVBoxLayout(central)
        self.manage_db_btn=QPushButton("Manage Database");self.get_color_btn=QPushButton("Select a Color");self.get_profile_btn=QPushButton("Load Profile")
        self.results_label=QLabel("Selection results appear here.");self.results_label.setWordWrap(True)
        [layout.addWidget(w) for w in[self.manage_db_btn,self.get_color_btn,self.get_profile_btn,self.results_label]]
        self.manage_db_btn.clicked.connect(self.open_full_editor);self.get_color_btn.clicked.connect(self.open_color_selector);self.get_profile_btn.clicked.connect(self.open_profile_selector)
    
    def open_full_editor(self):
        self.editor_window=QMainWindow();nav=DatabaseNavigatorWidget(mode=NavigatorMode.FULL_EDIT)
        self.editor_window.setWindowTitle("Database Manager");self.editor_window.setCentralWidget(nav);self.editor_window.setGeometry(150,150,600,850);self.editor_window.show()
    
    def open_color_selector(self):
        d=QDialog(self);d.setWindowTitle("Select Color");l=QVBoxLayout(d);nav=DatabaseNavigatorWidget(NavigatorMode.SELECT_COLOR,d)
        nav.selection_button_box.rejected.connect(d.reject);nav.colorSelected.connect(self.on_color_received);l.addWidget(nav);d.exec()
    
    def open_profile_selector(self):
        d=QDialog(self);d.setWindowTitle("Select Profile");l=QVBoxLayout(d);nav=DatabaseNavigatorWidget(NavigatorMode.SELECT_PROFILE,d)
        nav.selection_button_box.rejected.connect(d.reject);nav.profileSelected.connect(self.on_profile_received);l.addWidget(nav);d.exec()
    
    def on_color_received(self,data):
        print("Color:",data)
        self.results_label.setText(f"<b>Color:</b> {data['color_name']}")
    
    def on_profile_received(self,data):
        print("Profile Data:", data)
        ids = data['identifiers']
        params = data['parameters']
        self.results_label.setText(f"<b>Profile Loaded:</b><br>"
                                   f"Laser: {ids['laser']['name']}<br>"
                                   f"Material: {ids['material']['name']} - {ids['material_type']['name']}<br>"
                                   f"Contains {len(params)} color parameters.")

if __name__ == '__main__':
    # --- MODIFIED: Ensure demo DB is created in the right place ---
    db_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "Database", "laser_database.db")
    if not os.path.exists(db_path):
        print("Creating a dummy database for demonstration...")
        db = DatabaseManager(db_subfolder="Database", db_filename="laser_database.db")
        l_id=db.add_laser("CO2");m_id=db.add_material("Wood");t_id=db.add_material_type(m_id,"Plywood")
        p_id=db.get_or_create_palette(l_id,t_id);db.add_parameter(p_id,"Engrave","0,0,0",0.2,"FixedMeander",0,80,500);db.close()
    
    app=QApplication(sys.argv);window=MainWindow();window.show();sys.exit(app.exec())
