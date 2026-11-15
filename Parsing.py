from PyQt6 import QtWidgets, QtCore
from PyQt6.QtWidgets import QFileDialog
import numpy as np
import datetime
from HelperClasses import ProcessBlock, HatchData, HatchCluster
from core import gcode, machine
from core.postprocess import PostProcessor, apply_speed_and_power
import copy
import logging

log = logging.getLogger(__name__)

class Parser:
    def __init__(self, data_handler, gui):
        self.data_handler = data_handler
        self.post_processor = PostProcessor()
        self.gui = gui
        self.hatch_data = HatchData(None, None)

        # Initialize GUI elements from the preloaded PyQt6 GUI
        self.post_processing_combobox = gui.post_processing_combobox
        self.laser_mode_combobox = gui.laser_mode_combobox
        self.min_power_spinbox = gui.min_power_spinbox
        self.max_power_spinbox = gui.max_power_spinbox
        self.power_format_combobox = gui.power_format_combobox
        self.min_speed_spinbox = gui.min_speed_spinbox
        self.max_speed_spinbox = gui.max_speed_spinbox
        self.speed_format_combobox = gui.speed_format_combobox
        self.offset_x_spinbox = gui.offset_x_spinbox
        self.offset_y_spinbox = gui.offset_y_spinbox
        self.offset_z_spinbox = gui.offset_z_spinbox
        self.iterations_spinbox = gui.iterations_spinbox
        self.export_format_combobox = gui.export_format_combobox
        self.export_button = gui.export_button
        self.add_process_block_button = gui.add_process_block_button
        self.remove_process_block_button = gui.remove_process_block_button
        self.process_listWidget = gui.process_listWidget
        self.air_assist_combobox = gui.air_assist_combobox
        self.power_mode_combobox = gui.power_mode_combobox

        # Set default values for spinboxes and comboboxes
        self.post_processing_combobox.addItems(["None", "Maximize Lines", "Constant Drive", "Over Drive"])
        self.power_format_combobox.addItems(["constant (max. Val.)", "color-scaled", "test_structure"])
        self.speed_format_combobox.addItems(["constant (max. Val.)", "color-scaled", "test_structure"])
        self.export_format_combobox.addItems([".jcode", ".gcode", ".txt"])

        # P5.1: machine profile selection (in the cells of the former white threshold); fills the mode drop-downs
        gui.machine_profile_label = QtWidgets.QLabel("Machine")
        gui.machine_profile_combobox = QtWidgets.QComboBox()
        gui.machine_profile_combobox.setToolTip("Machine profile (JSON files in " + str(machine.USER_DIR) + ")")
        gui.gridLayout_15.addWidget(gui.machine_profile_label, 0, 1)
        gui.gridLayout_15.addWidget(gui.machine_profile_combobox, 1, 1)
        self.machine_profile_combobox = gui.machine_profile_combobox
        self.machine_profile_combobox.currentTextChanged.connect(self.set_machine_profile)
        self.reload_machine_profiles()

        self.min_power_spinbox.setValue(0)
        self.max_power_spinbox.setValue(100)
        self.min_speed_spinbox.setValue(0)
        self.max_speed_spinbox.setValue(80)
        self.offset_x_spinbox.setValue(0)
        self.offset_y_spinbox.setValue(0)
        self.offset_z_spinbox.setValue(0)
        self.iterations_spinbox.setValue(1)

        # Connect signals to methods
        self.export_button.clicked.connect(self.export_data)
        self.add_process_block_button.clicked.connect(lambda: self.add_process_block(self.iterations_spinbox.value()))
        self.remove_process_block_button.clicked.connect(self.remove_selected_process_block)

    def format_gcode_for_jcode(self, process_block, cluster_index):
        header = gcode.generate_gcode_header(process_block.machine)
        footer = gcode.generate_gcode_footer(process_block.machine)
        full_gcode = header
        full_gcode += gcode.generate_gcode(process_block, cluster_index)
        full_gcode += footer
        return "\n".join(full_gcode)

    def export_gcode_for_jcode(self, path, process_block:ProcessBlock, cluster_index):
        # Open a save file dialog
        savepath = path
        if savepath:
            with open(savepath, 'w') as file:
                file.write(self.format_gcode_for_jcode(process_block, cluster_index))
    
    def save_jcode(self, block_list = None):
        if block_list is None:
            block_list = []
            for block_idx in range(self.process_listWidget.count()):
                list_item = self.process_listWidget.item(block_idx)  # Get the item at the given index
                process_block = list_item.data(QtCore.Qt.ItemDataRole.UserRole)  # Retrieve the stored ProcessBlock object
                block_list.append(process_block)
            
        if not block_list:
            QtWidgets.QMessageBox.critical(self.gui, "Error", "No Process Blocks available to save.")
            return

        savepath, _ = QFileDialog.getSaveFileName(
            caption="Save J-code File",
            filter="J-code files (*.jcode);;All files (*.*)",
            directory="",
        )
        if not savepath:
            return
        # B07: cluster files are derived from the base name; without the extension they would overwrite the main file
        base_path = savepath[:-len('.jcode')] if savepath.lower().endswith('.jcode') else savepath
        savepath = base_path + '.jcode'
        with open(savepath, 'w') as file:
            file.write('; This file was created by BildHatcher\n')
            current_datetime = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            file.write(f'; Created: {current_datetime}\n')

        #first loop over all process blocks
        for block_idx, process_block in enumerate(block_list):
        
            #loop over all iterations
            for block_iter in range(process_block.iterations):
                #loop over all hatch clusters. write to jcode and create separate gcode files for every cluster
                hatch_clusters = process_block.hatch_data.hatch_clusters
                for cluster_index, hatch_cluster in enumerate(hatch_clusters):
                    cluster_pos = hatch_cluster.ref_position
                    cluster_filename = f'{base_path}_block-{block_idx+1}_cluster-{cluster_index+1}.nc'
                    with open(savepath, 'a') as file:
                        file.write(f"\nJ0 X{cluster_pos[0]} Y{cluster_pos[1]} Z{cluster_pos[2]} R{cluster_pos[3]}")
                        file.write(f"\nJ1 {cluster_filename}")
                    
                    if block_iter > 0:
                        #in this case the gcode for this cluster was already created.
                        continue

                    #create gcode for every cluster here
                    self.export_gcode_for_jcode(cluster_filename, process_block, cluster_index)
    
    def save_gcode(self, block_list = None):

        #frist get all blocks so we can make a sanity check
        if block_list is None:
            block_list = []
            for block_idx in range(self.process_listWidget.count()):
                list_item = self.process_listWidget.item(block_idx)  # Get the item at the given index
                process_block = list_item.data(QtCore.Qt.ItemDataRole.UserRole)  # Retrieve the stored ProcessBlock object
                block_list.append(process_block)
        
        if not block_list:
            QtWidgets.QMessageBox.critical(self.gui, "Error", "No Process Blocks available to save.")
            return

        #santiy check if all clusters of all blocks use the wp as ref position
        ref_position = [0,0,0,0]

        for block_idx, process_block in enumerate(block_list):
            for cluster_index, hatch_cluster in enumerate(process_block.hatch_data.hatch_clusters):
                if not hatch_cluster.ref_position == ref_position:
                    QtWidgets.QMessageBox.critical(self.gui, "Error", f"Cluster {cluster_index+1} of Process Block {block_idx+1} has a non-zero reference position. \nCannot save as single G-code file. Use .jcode instead.")
                    return

        # Open a save file dialog
        savepath, _ = QFileDialog.getSaveFileName(
            #parent=self.gui,
            caption="Save G-code File",
            filter="G-code files (*.gcode);;All files (*.*)",
            directory="",
            #selectedFilter="*.gcode"
        )
        if not savepath:
            return

        #setup gcode
        header = gcode.generate_gcode_header(block_list[0].machine)
        footer = gcode.generate_gcode_footer(block_list[0].machine)
        full_gcode = header 
        #now loop over all process blocks and clusters and pack everything into a single gcode file
        for block_idx, process_block in enumerate(block_list):
        
            #loop over all iterations
            for block_iter in range(process_block.iterations):
                #loop over all hatch clusters. write to jcode and create separate gcode files for every cluster
                hatch_clusters = process_block.hatch_data.hatch_clusters
                for cluster_index, hatch_cluster in enumerate(hatch_clusters):

                    
                    full_gcode += gcode.generate_gcode(process_block, cluster_index)
        
        full_gcode += footer
        formated_gcode = "\n".join(full_gcode)

        with open(savepath, 'w') as file:
            file.write(formated_gcode)

    
    def automatic_jcode(self, db_color_palette, offset = [0,0,0]):
        post_processing = db_color_palette.post_processing
        laser_mode = db_color_palette.laser_mode
        enclosure_fan = db_color_palette.enclosure_fan
        air_assist = db_color_palette.air_assist
        power_mode = db_color_palette.power_mode

        self.get_handler_data()

        hatch_data = apply_speed_and_power(
            self.hatch_data, power_mode="db_based", speed_mode="db_based",
            db_color_palette=db_color_palette)
        
        process_block = self.post_processor.process_block(ProcessBlock(
            hatch_data,
            iterations=1,
            post_processing=post_processing,
            laser_mode=laser_mode,
            air_assist=air_assist,
            enclosure_fan=enclosure_fan,
            power_mode=power_mode,
            offset=offset,
            machine=self.data_handler.machine_profile)
        )

        self.save_jcode(block_list=[process_block])

    def reload_machine_profiles(self):
        """(Re)read the profile files; keeps the current selection if it still exists."""
        current = self.machine_profile_combobox.currentText() or self.data_handler.machine_profile.name
        self.profiles = machine.load_profiles()
        if not self.profiles:  # no readable file at all: fall back to the bundled default
            self.profiles = {self.data_handler.machine_profile.name: self.data_handler.machine_profile}
        self.machine_profile_combobox.blockSignals(True)
        self.machine_profile_combobox.clear()
        self.machine_profile_combobox.addItems(list(self.profiles))
        self.machine_profile_combobox.blockSignals(False)
        index = self.machine_profile_combobox.findText(current)
        self.machine_profile_combobox.setCurrentIndex(max(index, 0))
        self.set_machine_profile(self.machine_profile_combobox.currentText())

    def set_machine_profile(self, name):
        profile = self.profiles.get(name)
        if profile is None:
            return
        self.data_handler.machine_profile = profile
        for combobox, options in ((self.laser_mode_combobox, profile.laser_modes),
                                  (self.power_mode_combobox, profile.power_modes),
                                  (self.air_assist_combobox, profile.air_assist)):
            current = combobox.currentText()
            combobox.clear()
            combobox.addItems(list(options))
            if combobox.findText(current) >= 0:
                combobox.setCurrentText(current)

    def add_process_block(self,iterations=1):
        '''Creates a process block from the active hatch data and puts it into the processListWidget'''
        post_processing = self.post_processing_combobox.currentText()
        laser_mode = self.laser_mode_combobox.currentText()
        air_assist = self.air_assist_combobox.currentText()
        power_mode = self.power_mode_combobox.currentText()
        offset = [
            self.offset_x_spinbox.value(),
            self.offset_y_spinbox.value(),
            self.offset_z_spinbox.value()
        ]

        self.get_handler_data()

        hatch_data = apply_speed_and_power(
            self.hatch_data,
            power_mode=self.power_format_combobox.currentText(),
            speed_mode=self.speed_format_combobox.currentText(),
            min_pwr=self.min_power_spinbox.value(), max_pwr=self.max_power_spinbox.value(),
            min_speed=self.min_speed_spinbox.value(), max_speed=self.max_speed_spinbox.value(),
            pwr_struc_num=self.gui.structnum_pwr_spinbox.value(),
            speed_struc_num=self.gui.structnum_speed_spinbox.value())
        process_block = self.post_processor.process_block(ProcessBlock(
            hatch_data, iterations, post_processing, laser_mode, air_assist=air_assist, power_mode=power_mode,
            offset=offset, machine=self.data_handler.machine_profile))
        list_item = QtWidgets.QListWidgetItem(f"{iterations}x {self.hatch_data.type}")
        list_item.setData(QtCore.Qt.ItemDataRole.UserRole, process_block)  # Store the process block in the item's data
        self.process_listWidget.addItem(list_item)


    def remove_selected_process_block(self):
        '''Removes the selected process block from the QListWidget'''
        selected_items = self.process_listWidget.selectedItems()
        if not selected_items:
            return  # No item selected

        for item in selected_items:
            self.process_listWidget.takeItem(self.process_listWidget.row(item))  # Remove the selected item
            
    def save_txt(self):
        folder = QFileDialog.getExistingDirectory(caption="Select Folder")
        if not folder:
            return
        
        idx_code=[]
        for index in range(self.process_listWidget.count()):
            list_item = self.process_listWidget.item(index)  # Get the item at the given index
            process_block = list_item.data(QtCore.Qt.ItemDataRole.UserRole)  # Retrieve the stored ProcessBlock object

            block_path=folder + "/"+ 'temp' + f"_block-{index+1}.txt"
            txt_commands=gcode.generate_txt_code(process_block)
            with open(block_path, 'w') as file:
                file.write(txt_commands)
            
            idx_code.append(f"0 0 0 " + "temp" + f"_block-{index+1}.txt"+ f" {index+1}")  # B06: same name as the file written above
        #save the idx_code to file here
        idx_path=folder + "/"+ "temp" + "_INDEX.txt"
        idx_code="\n".join(idx_code)
        with open(idx_path, 'w') as file:
                file.write(idx_code)
    
    def export_data(self):
        format = self.export_format_combobox.currentText()
        if format == ".jcode":
            self.save_jcode()
        elif format == ".gcode":
            self.save_gcode()
        elif format == ".txt":
            self.save_txt()
        log.info("finished exporting")
    def get_handler_data(self):
        self.hatch_data = self.data_handler.hatch_data



