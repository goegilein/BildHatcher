from PyQt6 import QtWidgets, QtCore
from PyQt6.QtWidgets import QFileDialog
import numpy as np
import datetime
from HelperClasses import ProcessBlock, HatchData, HatchCluster
import PostProcessing
import copy

class Parser:
    def __init__(self, data_handler, gui):
        self.data_handler = data_handler
        self.post_processor = PostProcessing.PostProcessor()
        self.gui = gui
        self.hatch_data = HatchData(None, None)
        self.laser_mode = ""
        self.feedrate_default = 6000

        # Initialize GUI elements from the preloaded PyQt6 GUI
        self.post_processing_combobox = gui.post_processing_combobox
        self.white_threshold_parsing_spinbox = gui.white_threshold_parsing_spinbox
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

        # Set default values for spinboxes and comboboxes
        self.post_processing_combobox.addItems(["None", "Maximize Lines", "Constant Drive", "Over Drive"])
        self.laser_mode_combobox.addItems([ "constant","variable"])
        self.power_format_combobox.addItems(["constant (max. Val.)", "color-scaled", "test_structure"])
        self.speed_format_combobox.addItems(["constant (max. Val.)", "color-scaled", "test_structure"])
        self.export_format_combobox.addItems([".jcode", ".txt"])

        self.white_threshold_parsing_spinbox.setValue(255)
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

    def generate_gcode_header(self):
        gcode_commands=[]
        # Get the current date and time
        current_datetime = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Initialize G-code with header
        gcode_commands.append("; Header")
        gcode_commands.append("; G-code generated from line_collection")
        gcode_commands.append(f"; Created: {current_datetime}")
        gcode_commands.append("")
        gcode_commands.append("; Presets")
        gcode_commands.append("")
        gcode_commands.append("G90 ; Use absolute coordinates")
        gcode_commands.append("G21 ; Set units to millimeters")
        #gcode_commands.append("M4 P0 ; set Laser to variable Mode")#TO BE TESTED. This is Skywriting equivalent
        #gcode_commands.append("M3 P0 ; set laser to constant Mode")#TO BE TESTED
        # if air_assist == "on":
        #     gcode_commands.append("M8 ; Turn on Air assis")
        # else:
        #     gcode_commands.append("M9 ; Turn off Air assis")
        gcode_commands.append("M2000 W1 P100 ; Artisan Setting to turn on Enclosure lights 100%")
        # gcode_commands.append(f"M2000 W2 P{enclosure_fan} ; Artisan Setting to turn on Enclosure fan (100%)")
        gcode_commands.append("M2000 L23 P0 ; Artisan 40W laser. 0 enters half power Mode") #TO BE TESTED! should be better for marking
        gcode_commands.append("")
        gcode_commands.append(f"G0 F{self.feedrate_default} ; set default feedrate for laser off moves")
        gcode_commands.append(f"G1 F{self.feedrate_default} ; set default feedrate for laser on moves")
        gcode_commands.append("")

        return gcode_commands

    def generate_gcode_footer(self):
        gcode_commands=[]
        gcode_commands.append("; Footer")
        gcode_commands.append("M5 ; Turn off laser")
        gcode_commands.append("M9 ; Turn off Air assist")
        gcode_commands.append("M2000 W2 P0 ; Artisan Setting to turn off Enclosure fan (0%)")
        gcode_commands.append("M2000 L23 P1 ; Artisan 40W laser. 1 exits half power Moade")
        gcode_commands.append("; End of G-code")

        return gcode_commands

    def generate_gcode(self,process_block:ProcessBlock=None, cluster_index=None):
        gcode_commands = []
        if process_block is None:
            print("Error: No ProcessBlock provided for G-code generation")
            return gcode_commands
        
        gcode_commands.append("")
        gcode_commands.append(";start of new Processblock")
        gcode_commands.append("")
        #set laser mode
        if process_block.laser_mode == "variable":
            gcode_commands.append("M4 P0 ; set Laser to variable Mode")
        elif process_block.laser_mode == "constant":
            gcode_commands.append("M3 P0 ; set laser to constant Mode")
        else:
            print("Error: Laser Mode not recognized")
        #set enclosure fan and air assist
        gcode_commands.append(f"M2000 W2 P{process_block.enclosure_fan} ; Artisan Setting to turn on Enclosure fan (100%)")
        if process_block.air_assist == "on":
            gcode_commands.append("M8 ; Turn on Air assis")
        else:
            gcode_commands.append("M9 ; Turn off Air assis")

        gcode_commands.append("")
        gcode_commands.append(";start of Pattern")
        gcode_commands.append("")

        x_prev=None
        y_prev=None
        z_prev=None
        pwr_prev=[]
        feedG1_prev=0
        feedG0_prev=0
        prev_gcode_command=""

        hatch_cluster_data = process_block.hatch_data.hatch_clusters[cluster_index].data #self.post_processor.process_data(process_block)

        #process block header
        gcode_commands.append(f"; Process Block: {process_block.post_processing} | Laser Mode: {process_block.laser_mode} | Air Assist: {process_block.air_assist} | Enclosure Fan: {process_block.enclosure_fan}%")
        gcode_commands.append(f"; Offset: X={process_block.offset[0]} Y={process_block.offset[1]} Z={process_block.offset[2]}")
        gcode_commands.append(f"; Number of color clusters: {len(hatch_cluster_data)}")
        gcode_commands.append(f"; Number of points: {sum(len(polyline) for cluster in hatch_cluster_data for polyline in cluster)}")
        gcode_commands.append("")

        for counter, line_collection in enumerate(hatch_cluster_data):
            for polyline in line_collection:
                for point in polyline:

                    move_type = point.move_type
                    x = point.x
                    y = point.y
                    z = point.z
                    feed = point.speed*60 #feed is in mm/min while speed is in mm/s
                    pwr_P = point.pwr
                    pwr_S = pwr_P/100*255 #pwr_S is in 8bit format (0-255)

                    

                    if move_type == 0:
                        # Rapid move (G0)
                        # if not prev_gcode_command=="G0":
                        #     gcode_commands.append("M05")
                        gcode_command="G0"
                        if x != x_prev: gcode_command += f" X{x:.3f}"
                        if y != y_prev: gcode_command += f" Y{y:.3f}"
                        if z != z_prev: gcode_command += f" Z{z:.3f}"
                        if feed != feedG0_prev or prev_gcode_command=="G1": gcode_command += f" F{feed}"
                        #gcode_command += f" F{feed}"
                        
                        
                        gcode_commands.append(gcode_command)

                        #update previous values
                        pwr_prev=0
                        feedG0_prev=feed
                        prev_gcode_command="G0"
                    else:
                        # Linear move with processing (G1)
                        # if not prev_gcode_command=="G1":
                        #     gcode_commands.append(f"M03 P{pwr_P} S{pwr_S}")

                        gcode_command="G1"
                        if x != x_prev: gcode_command += f" X{x:.3f}"
                        if y != y_prev: gcode_command += f" Y{y:.3f}"
                        if z != z_prev: gcode_command += f" Z{z:.3f}"
                        if pwr_S != pwr_prev or prev_gcode_command=="G0": gcode_command += f" P{pwr_P} S{pwr_S}" #P input is a NECESSITY for Artisan's Marlin!
                        if feed != feedG1_prev or prev_gcode_command=="G0": gcode_command += f" F{feed}"
                        #gcode_command += f" F{feed}"

                        gcode_commands.append(gcode_command)

                        #update previous values
                        feedG1_prev=feed
                        pwr_prev=pwr_S
                        prev_gcode_command="G1"
                    # Update previous values that are identical for both move types
                    x_prev=x
                    y_prev=y
                    z_prev=z
                    

            gcode_commands.append("")  # Add empty line between clusters    
        gcode_commands.append("; End of Pattern")
        gcode_commands.append("")
        return(gcode_commands)

    def format_gcode(self, process_block, cluster_index):
        header = self.generate_gcode_header()
        footer = self.generate_gcode_footer()
        full_gcode = header 
        full_gcode += self.generate_gcode(process_block, cluster_index)
        full_gcode += footer
        return "\n".join(full_gcode)

    def export_gcode(self, path, process_block:ProcessBlock, cluster_index):
        # Open a save file dialog
        savepath = path
        if savepath:
            with open(savepath, 'w') as file:
                file.write(self.format_gcode(process_block, cluster_index))
    
    def save_jcode(self):
        # we will export jcode main file here
        # Open a save file dialog
        savepath, _ = QFileDialog.getSaveFileName(
            #parent=self.gui,
            caption="Save J-code File",
            filter="J-code files (*.jcode);;All files (*.*)",
            directory="",
        )
        with open(savepath, 'w') as file:
            file.write(';This file was created by BildHatcher\n')
            current_datetime = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            file.write(f'; Created: {current_datetime}\n')

        #first loop over all process blocks
        for block_idx in range(self.process_listWidget.count()):
            list_item = self.process_listWidget.item(block_idx)  # Get the item at the given index
            process_block = list_item.data(QtCore.Qt.ItemDataRole.UserRole)  # Retrieve the stored ProcessBlock object

            #loop over all iterations
            for block_iter in range(process_block.iterations):
                #loop over all hatch clusters. write to jcode and create separate gcode files for every cluster
                hatch_clusters = process_block.hatch_data.hatch_clusters
                for cluster_index, hatch_cluster in enumerate(hatch_clusters):
                    cluster_pos = hatch_cluster.ref_position
                    cluster_filename = savepath.replace('.jcode', f'_block-{block_idx+1}_cluster-{cluster_index+1}.nc')
                    with open(savepath, 'a') as file:
                        file.write(f"\nJ0 X{cluster_pos[0]} Y{cluster_pos[1]} Z{cluster_pos[2]} R{cluster_pos[3]}")
                        file.write(f"\nJ1 {cluster_filename}")
                    
                    if block_iter > 0:
                        continue

                    #create gcode for every cluster here
                    self.export_gcode(cluster_filename, process_block, cluster_index)

    
    def automatic_gcode(self, db_color_palette, white_threshold=255, offset = [0,0,0]):
        # Open a save file dialog
        savepath, _ = QFileDialog.getSaveFileName(
            #parent=self.gui,
            caption="Save G-code File",
            filter="G-code files (*.nc);;All files (*.*)",
            directory="",
            #selectedFilter="*.nc"
        )
        if not savepath:
            return

        post_processing = db_color_palette.post_processing
        laser_mode = db_color_palette.laser_mode
        enclosure_fan = db_color_palette.enclosure_fan
        air_assist = db_color_palette.air_assist

        self.get_handler_data()

        hatch_data = self.set_speed_and_pwr(
            hatch_data_in=self.hatch_data.hatch_clusters,
            white_threshold=white_threshold, 
            mode="automatic", 
            db_color_palette=db_color_palette)
        
        process_block = ProcessBlock(
            hatch_data,
            post_processing=post_processing,
            laser_mode=laser_mode,
            air_assist=air_assist,
            enclosure_fan=enclosure_fan,
            offset=offset)

        with open(savepath, 'w') as file:
                file.write(self.format_gcode(process_block=process_block))

    def add_process_block(self,iterations=1):
        '''Creates a process block from the active hatch data and puts it into the processListWidget'''
        post_processing = self.post_processing_combobox.currentText()
        laser_mode = self.laser_mode_combobox.currentText()
        offset = [
            self.offset_x_spinbox.value(),
            self.offset_y_spinbox.value(),
            self.offset_z_spinbox.value()
        ]

        self.get_handler_data()

        hatch_data = self.set_speed_and_pwr(self.hatch_data, 
                                            white_threshold=self.white_threshold_parsing_spinbox.value(), 
                                            mode="manual")
        #process_block = ProcessBlock(hatch_data, post_processing, laser_mode, offset=offset)
        process_block = self.post_processor.process_block(ProcessBlock(hatch_data, iterations, post_processing, laser_mode, offset=offset))
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
            txt_commands=self.generate_txt_code(process_block)
            with open(block_path, 'w') as file:
                file.write(txt_commands)
            
            idx_code.append(f"0 0 0 " + "temp" + f"_cluster-{index+1}.txt"+ f" {index+1}")
        #save the idx_code to file here
        idx_path=folder + "/"+ "temp" + "_INDEX.txt"
        idx_code="\n".join(idx_code)
        with open(idx_path, 'w') as file:
                file.write(idx_code)
    
    def generate_txt_code(self,process_block):
        txt_commands=[]
        for cluster in process_block.data:
            for polyline in cluster:
                for point in polyline:
                    txt_commands.append(f"{point.x:.3f} {point.y:.3f} {point.z:.3f} {np.abs(point.move_type-1)}")
        return "\n".join(txt_commands)
    
    def export_data(self):
        format = self.export_format_combobox.currentText()
        if format == ".jcode":
            self.save_jcode()
        elif format == ".txt":
            self.save_txt()
        print("finished exporting")

    def set_speed_and_pwr(self,hatch_data_in:HatchData, white_threshold, mode ="manual", db_color_palette=None):
        #work on a deepcopy of the raw data to avoid pointing issues
        hatch_data = copy.deepcopy(hatch_data_in)

        #data = HatchData(hatch_data, hatch_data.type)
        for hatch_cluster in hatch_data.hatch_clusters:
            for counter, line_collection in enumerate(hatch_cluster.data):

                # Get first point for color of the entire cluster
                first_point = line_collection[0][0]
                color = [first_point.r, first_point.g, first_point.b]

                # Check for white threshold. If the color is too bright, remove the data
                if sum(color)/3>white_threshold:
                    hatch_cluster.data[counter]=[] 
                    continue
                
                if mode == "manual":
                    # Get Power limits
                    min_pwr = self.min_power_spinbox.value()
                    max_pwr = self.max_power_spinbox.value()
                    power_mode = self.power_format_combobox.currentText()
                    pwr_struc_num = self.gui.structnum_pwr_spinbox.value()

                    # Get Speed limits
                    min_speed = self.min_speed_spinbox.value()
                    max_speed = self.max_speed_spinbox.value()
                    speed_mode = self.speed_format_combobox.currentText()
                    speed_struc_num = self.gui.structnum_speed_spinbox.value()
                elif mode == "automatic":
                    power_mode = "db_based"
                    speed_mode = "db_based"

                #power settings
                if power_mode=="constant (max. Val.)":
                    pwr = max_pwr
                elif power_mode=="color-scaled":
                    pwr=int(max_pwr-(max_pwr-min_pwr)*sum([first_point.r,first_point.g,first_point.b])/765)
                elif power_mode=="test_structure":
                    if pwr_struc_num>1:
                        pwr=int(min_pwr+(max_pwr-min_pwr)*np.floor(counter/speed_struc_num)/(pwr_struc_num-1))
                    else:
                        pwr=max_pwr
                elif power_mode=="db_based":
                    bestfit_color = db_color_palette.find_paramset_by_color(color)
                    pwr = bestfit_color['laser_power']
                else:
                    print("error: PowerMode not recognized")

                #speed/feedrate settings
                if speed_mode=="constant (max. Val.)":
                    speed = max_speed
                elif speed_mode=="color-scaled":
                    speed=int(min_speed+(max_speed-min_speed)*sum([first_point.r,first_point.g,first_point.b])/765)
                elif speed_mode=="test_structure":
                    if speed_struc_num>1:
                        speed=int((min_speed+(max_speed-min_speed)*(counter%speed_struc_num/(speed_struc_num-1))))
                    else:    
                        speed=max_speed
                elif speed_mode=="db_based":
                    bestfit_color = db_color_palette.find_paramset_by_color(color)
                    speed = bestfit_color['speed']
                else:
                    print("error: SpeedMode not recognized")

                #set data in every point
                for polyline in line_collection:
                    for point in polyline:
                        point.speed=speed
                        point.pwr=pwr
        
        return hatch_data

    def get_handler_data(self):
        self.hatch_data = self.data_handler.hatch_data



