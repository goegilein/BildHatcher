from PyQt6 import QtWidgets
from PyQt6.QtWidgets import QFileDialog, QProgressDialog 
from PyQt6.QtCore import QThread, pyqtSignal
import numpy as np
from collections import defaultdict
import random
from HelperClasses import Point, HatchData
import ezdxf

class Hatcher:
    def __init__(self, data_handler, gui):
        self.data_handler = data_handler
        self.gui = gui
        self.hatch_data = HatchData([], "")
        self.clusters = None
        self.image_matrix = None
        self.pixel_per_mm = None
        self.hatching_cancelled = False

        # Initialize GUI elements from the preloaded PyQt6 GUI
        self.hatch_pattern_combobox = gui.hatch_pattern_combobox
        self.hatch_angle_spinbox = gui.hatch_angle_spinbox
        self.hatch_dist_mode_combobox = gui.hatch_dist_mode_combobox
        self.hatch_dist_min_spinbox = gui.hatch_dist_min_spinbox
        self.hatch_dist_max_spinbox = gui.hatch_dist_max_spinbox
        self.hatch_mode_combobox = gui.hatch_mode_combobox
        self.cyl_rad_spinbox = gui.cyl_rad_spinbox
        self.hatch_image_button = gui.hatch_image_button
        self.hatch_precision_spinbox = gui.hatch_precision_spinbox
        self.hatch_progress_bar = gui.hatch_progress_bar
        self.hatch_progress_label = gui.hatch_progress_label
        self.create_contours_button = gui.create_contours_button
        self.contour_source_combobox = gui.contour_source_combobox
        self.white_threshold_hatching_spinbox = gui.white_threshold_hatching_spinbox

        # Initialize combobox values
        self.hatch_pattern_combobox.addItems(["FixedMeander", "RandomMeander", "CrossedMeander", "Circular", "Spiral", "Radial"])
        self.hatch_dist_mode_combobox.addItems(["ColorRanged", "Fixed"])
        self.hatch_mode_combobox.addItems(["Flat", "CylEquidistX", "CylEquidistRad"])
        self.contour_source_combobox.addItems(["Image", ".dxf File"])

        # Set default values for spinboxes
        self.hatch_angle_spinbox.setValue(45.0)
        self.hatch_dist_min_spinbox.setValue(300)
        self.hatch_dist_max_spinbox.setValue(700)
        self.cyl_rad_spinbox.setValue(100)
        self.hatch_precision_spinbox.setValue(0.1)

        # Connect signals to methods
        self.hatch_pattern_combobox.currentTextChanged.connect(self.update_angle_entry_state)
        self.hatch_dist_mode_combobox.currentTextChanged.connect(self.update_hatch_dist_mode_state)
        self.hatch_mode_combobox.currentTextChanged.connect(self.update_hatch_mode_state)
        self.hatch_image_button.clicked.connect(lambda: self.create_hatching(mode = "manual"))
        self.create_contours_button.clicked.connect(self.create_contours)

        # Initialize the state of the UI based on default selections
        self.update_angle_entry_state()
        self.update_hatch_dist_mode_state()
        self.update_hatch_mode_state()

    def update_angle_entry_state(self, *args):
        # Enable hatch angle spinbox only for FixedMeander or CrossedMeander patterns
        text = self.hatch_pattern_combobox.currentText()
        if text in ["FixedMeander", "CrossedMeander"]:
            self.hatch_angle_spinbox.setEnabled(True)
        else:
            self.hatch_angle_spinbox.setEnabled(False)

    def update_hatch_dist_mode_state(self, *args):
        # Enable/disable the maximum hatch distance spinbox based on the selected mode
        text = self.hatch_dist_mode_combobox.currentText()
        if text == "Fixed":
            self.hatch_dist_max_spinbox.setEnabled(False)
        else:
            self.hatch_dist_max_spinbox.setEnabled(True)

    def update_hatch_mode_state(self, *args):
        # Enable/disable the cylinder radius spinbox based on the selected hatch mode
        text = self.hatch_mode_combobox.currentText()
        if text == "Flat":
            self.cyl_rad_spinbox.setEnabled(False)
        else:
            self.cyl_rad_spinbox.setEnabled(True)

    def find_clusters(self):
        self.get_handler_data()
        height, width, _ = self.image_matrix.shape
        self.clusters = defaultdict(
            lambda: np.zeros((height, width), dtype=np.uint8))

        for i in range(height):
            for j in range(width):
                color = tuple(self.image_matrix[i, j])
                # Invert the y-axis to match the image display
                self.clusters[color][height-i-1, j] = 1

    def get_sorted_unique_colors(self, image_matrix):
        """
        Extracts all unique RGB colors from the image and sorts them by the sum of the RGB values in descending order.

        Args:
            image_matrix (numpy.ndarray): The image matrix with shape (height, width, 3).

        Returns:
            list: A list of unique RGB colors sorted by the sum of the RGB values in descending order.
        """
        # Reshape the image matrix to a 2D array where each row is an RGB color
        reshaped_image = image_matrix.reshape(-1, 3)
        
        # Get unique colors
        unique_colors = np.unique(reshaped_image, axis=0)
        
        # Sort unique colors by the sum of the RGB values in descending order
        sorted_colors = sorted(unique_colors, key=lambda color: np.sum(color), reverse=True)
        
        # Convert sorted colors to a list of tuples
        sorted_colors_list = [tuple(color) for color in sorted_colors]
        
        return sorted_colors_list
    
    def create_hatching(self, mode="manual", db_color_palette=None, hatch_pattern=None,
                       hatch_angle=None, cyl_rad_mm=None, hatch_mode=None,
                       stepsize_mm=None, white_threshold=None):
        
        # Create progress dialog
        self.progress_dialog = QProgressDialog("Hatching in progress...", "Cancel", 0, 100, self.gui)
        self.progress_dialog.setWindowTitle("Creating Hatch Pattern")
        self.progress_dialog.setModal(True)
        
        # Create and setup worker
        self.worker = HatchingWorker(
            self, mode, db_color_palette, hatch_pattern,
            hatch_angle, cyl_rad_mm, hatch_mode,
            stepsize_mm, white_threshold
        )
        
        # Connect signals
        self.worker.progress.connect(self.progress_dialog.setValue)
        self.worker.finished.connect(self.hatching_finished)
        self.progress_dialog.canceled.connect(self.cancel_hatching)
        
        # Start worker
        self.hatching_cancelled = False
        self.worker.start()
        self.progress_dialog.show()

    def create_hatching_worker(self, 
                        mode="manual",
                        db_color_palette=None,
                        hatch_pattern=None,
                        hatch_angle=None,
                        cyl_rad_mm=None,
                        hatch_mode=None,
                        stepsize_mm=None,
                        white_threshold=None):
        hatch_data= HatchData([], "")

        if mode == "manual":
            hatch_dist_mode = self.hatch_dist_mode_combobox.currentText()
            hatch_pattern = self.hatch_pattern_combobox.currentText()
            hatch_angle = self.hatch_angle_spinbox.value()  # Get hatch angle from spinbox
            cyl_rad_mm = self.cyl_rad_spinbox.value()  # Get cylinder radius from spinbox
            hatch_mode = self.hatch_mode_combobox.currentText()  # Get hatch mode from combobox
            stepsize_mm = self.hatch_precision_spinbox.value()
            white_threshold = self.white_threshold_hatching_spinbox.value()
        else:
            hatch_dist_mode = "Fixed"  # Default for automatic mode
        try:
            self.get_handler_data()
            # Reset progress bar
            self.worker.progress.emit(int(0))
            self.hatch_progress_label.setText("Hatch Progress: Hatching...")
            color_list = self.get_sorted_unique_colors(self.image_matrix)
            #check if hatching was cancelled
            if self.hatching_cancelled:
                return None
            hatch_data.data = self.hatch_clusters(
                mode=mode,
                color_list=color_list,
                hatch_pattern=hatch_pattern,
                hatch_angle=hatch_angle,
                hatch_dist_mode=hatch_dist_mode,
                cyl_rad_mm=cyl_rad_mm,
                hatch_mode=hatch_mode,
                stepsize_mm=stepsize_mm,
                white_threshold=white_threshold,
                db_color_palette=db_color_palette
            )
            if hatch_data.data == 0 or hatch_data.data is None:
                return None
            else:
                hatch_data.type = f"Image: {self.hatch_pattern_combobox.currentText()} with {self.hatch_dist_mode_combobox.currentText()} Lines"
            
            #check if hatching was cancelled
            if self.hatching_cancelled:
                return None
            if hatch_mode in ["CylEquidistX", "CylEquidistRad"]:
                hatch_data.data = self.make_hatch_cylindrical(hatch_data.data, cyl_rad_mm)
                addstring = f" and {self.hatch_mode_combobox.currentText()}"
                hatch_data.type += addstring
            return hatch_data
            #self.hatch_progress_label.setText("Hatch Progress: Finished!")
            #self.set_handler_data()
        except Exception as e:
            print(f"Error hatching clusters: {e}")

    def hatching_finished(self, result):
        if result:
            self.hatch_data = result
            self.set_handler_data()
            #self.hatch_progress_label.setText("Hatch Progress: Finished!")
        #self.progress_dialog.close()
    
    def cancel_hatching(self):
        if hasattr(self, 'worker'):
            self.hatching_cancelled = True

            # Disconnect all signals
            self.worker.progress.disconnect()
            self.worker.finished.disconnect()
            self.progress_dialog.canceled.disconnect()

            self.worker.cancel()
            
            # Close and delete the dialog
            self.progress_dialog.close()
            self.progress_dialog.deleteLater()
            
            # Remove references
            delattr(self, 'worker')
            delattr(self, 'progress_dialog')

    def hatch_clusters(self, mode="manual", color_list=None, hatch_pattern="RandomMeander", hatch_angle=90, hatch_dist_mode="ColorRanged", cyl_rad_mm = 100, hatch_mode = "Flat", stepsize_mm = 0.1, white_threshold=255, db_color_palette=None):
        hatched_clusters = []
        cluster_counter = 0
        cyl_rad = cyl_rad_mm * self.pixel_per_mm
        image_matrix = np.flipud(self.image_matrix)

        for color in color_list:
            #check if hatching was cancelled
            if self.hatching_cancelled:
                return None
            
            # Ensure the sum of RGB values is within a safe range
            color = np.array(color, dtype=np.int64)

            if sum(color)/3 > white_threshold:
                # Skip colors that are too bright (white), and update the progress bar
                cluster_counter += 1
                self.worker.progress.emit(int(np.ceil(cluster_counter / len(color_list) * 100)))
                QtWidgets.QApplication.processEvents()  # Update the UI
                continue

            #if mode is automatic, get hatch settings from best fit color of database color palette   
            if mode == "automatic":
                bestfit_color = db_color_palette.find_paramset_by_color(color)
                hatch_distance = bestfit_color['hatch_distance']/1000
                hatch_pattern = bestfit_color['hatch_pattern']
                hatch_angle = bestfit_color['hatch_angle']
            else:    
                if hatch_dist_mode == "ColorRanged":
                    # Define Hatch Dist depending on chosen Hatch_Mode
                    h_min = self.hatch_dist_min_spinbox.value()  # Get minimum hatch distance
                    h_max = self.hatch_dist_max_spinbox.value()  # Get maximum hatch distance
                    hatch_distance = (h_min + sum(color) / 765 * (h_max - h_min))/1000
                elif hatch_dist_mode == "Fixed":
                    hatch_distance = self.hatch_dist_min_spinbox.value()/1000
                else:
                    print("Hatch Distance Mode not recognized")
                    continue

            step_size = stepsize_mm * self.pixel_per_mm  # Step size in pixels
            hatch_distance = hatch_distance * self.pixel_per_mm  # Hatch distance in pixels

            progress_state = [cluster_counter, len(color_list)]

            if hatch_pattern in ["RandomMeander", "FixedMeander"]:
                hatch_lines = self.hatch_meander(
                    hatch_pattern, hatch_distance, hatch_angle, step_size, image_matrix, self.pixel_per_mm, color, hatch_mode, cyl_rad, progress_state
                )
                if hatch_lines == 0:
                    return 0
                else:
                    hatched_clusters.append(hatch_lines)
            elif hatch_pattern == "CrossedMeander":
                hatch_lines1 = self.hatch_meander(
                    hatch_pattern, hatch_distance, hatch_angle, step_size, image_matrix, self.pixel_per_mm, color, hatch_mode, cyl_rad, progress_state, cross_angle=0
                )
                hatch_lines2 = self.hatch_meander(
                    hatch_pattern, hatch_distance, hatch_angle, step_size, image_matrix, self.pixel_per_mm, color, hatch_mode, cyl_rad, progress_state, cross_angle=90
                )
                if hatch_lines1 == 0:
                    return 0
                else:
                    hatched_clusters.append(hatch_lines1)
                    hatched_clusters.append(hatch_lines2)
            elif hatch_pattern == "Circular":
                hatch_lines = self.hatch_circular(
                    hatch_distance, step_size, image_matrix, self.pixel_per_mm, color, hatch_mode, cyl_rad, progress_state
                )
                if hatch_lines == 0:
                    return 0
                else:
                    hatched_clusters.append(hatch_lines)
            elif hatch_pattern == "Spiral":
                hatch_lines = self.hatch_spiral(
                    hatch_distance, step_size, image_matrix, self.pixel_per_mm, color, hatch_mode, cyl_rad, progress_state
                )
                if hatch_lines == 0:
                    return 0
                else:
                    hatched_clusters.append(hatch_lines)
            elif hatch_pattern == "Radial":
                hatch_lines = self.hatch_radial(
                    hatch_distance, step_size, image_matrix, self.pixel_per_mm, color, hatch_mode, cyl_rad, progress_state
                )
                if hatch_lines == 0:
                    return 0
                else:
                    hatched_clusters.append(hatch_lines)
            else:
                print("Unknown hatch method")
            cluster_counter += 1
            
            #check if hatching was cancelled
            if self.hatching_cancelled:
                return None

            # Update progress bar
            self.worker.progress.emit(int(np.ceil(cluster_counter / len(color_list) * 100)))
            QtWidgets.QApplication.processEvents()  # Update the UI
        return hatched_clusters

    def hatch_meander(self, hatch_pattern, hatch_distance, hatch_angle, step_size, image_matrix, pixel_per_mm, color, hatch_mode, cyl_rad, progress_state,cross_angle=None):
        hatch_lines_poly=[]
        hatch_line_dir=1
        hatch_x_finished=False
        hatch_y_finished=False
        
        # Choose slice angle based on user input
        theta = 0  # Default angle is 0 degrees
        if hatch_pattern == "FixedMeander":
            theta = hatch_angle  # Get hatch angle from spinbox
        elif hatch_pattern == "RandomMeander":
            # Randomly choose theta between 0 and 179 degrees
            theta = np.floor(random.uniform(0, 180))
        elif hatch_pattern == "CrossedMeander":
            theta = hatch_angle + cross_angle
        theta = np.mod(theta, 180)  # Ensure theta is between 0 and 179 degrees
        theta_rad = np.radians(theta)  # Convert theta to radians
        cos_theta = np.cos(theta_rad)
        sin_theta = np.sin(theta_rad)

        #calculate step size in x and y direction. catch special cases of 0 an d 90 degrees
        if theta == 0:
            max_lines=image_matrix.shape[0]/hatch_distance
            step_start_y=hatch_distance
            step_start_x=1
            hatch_x_finished = True
        elif theta == 90:
            max_lines=image_matrix.shape[1]/hatch_distance
            step_start_x=hatch_distance
            step_start_y=1
            hatch_y_finished=True
        else:
            step_start_y = np.abs(hatch_distance/cos_theta)
            step_start_x = np.abs(hatch_distance/sin_theta)
            max_lines=image_matrix.shape[0]/step_start_y+image_matrix.shape[1]/step_start_x

        # Determine the bounding box of the cluster.
        min_y = -np.ceil(step_start_y)
        max_y = image_matrix.shape[0]+np.ceil(step_start_y)
        min_x = -np.ceil(step_start_x)
        max_x = image_matrix.shape[1]+np.ceil(step_start_x)

        center = [(max_x+min_x)/2, (max_y+min_y)/2]

        # Determine the starting point of the hatch lines.
        if cos_theta >= 0:
            hatch_start_x = max_x
            hatch_start_y = min_y
            incline = -1
        else:
            hatch_start_x = min_x
            hatch_start_y = min_y
            incline = 1

        # Generate hatch lines within the bounding box
        line_count = 0
        hatching_done = False
        #loop over hatchlines. will set hatching done when both x and y linestarts are outsinde the bounding box
        while not hatching_done:
            #check if hatching was cancelled
            if self.hatching_cancelled:
                return None
            
            prev_x = None
            prev_y = None
            x_target = hatch_start_x
            if hatch_mode == "CylEquidistX":
                if np.abs(x_target-center[0])>cyl_rad:
                    point_outside=True
                    x=0 #just a dummy
                else:
                    x=np.asin((x_target-center[0])/cyl_rad)*(cyl_rad)+center[0]
            else:
                x=x_target
            y = hatch_start_y
            polyline = []
            polyline_cache=[]
            point_outside=False
            #loop over one hatchline until it is outside the bounding box. this is looped over A LOT. Limit ALL function calls as much as possible
            current_pixel_color=np.array([-1,-1,-1]) #use non existend color when the point is outside the image
            while ((x >= min_x or incline==1) and (x <= max_x or incline==-1) and y >= min_y):
                #use a special rounding for x and y for efficiency. we know that they can never be negative (else it will be caught anyway)
                if int(y)==int(y-0.5):
                    y_round=int(y+1)
                else:
                    y_round=int(y)
                if int(x)==int(x-0.5):
                    x_round=int(x+1)
                else:
                    x_round=int(x)
                    
                #check if the current point is outside the image
                if point_outside or y_round>=image_matrix.shape[0] or y_round<0 or x_round>= image_matrix.shape[1] or x_round<0:
                    if polyline:
                        x1=((x+prev_x)/2-center[0])/pixel_per_mm
                        y1=((y+prev_y)/2-center[1])/pixel_per_mm
                        z1=0
                        polyline.append(Point(x1, y1, z1, 1, color[0], color[1], color[2]))
                        polyline_cache.append(polyline)
                        polyline=[]
                    point_outside=False
                    current_pixel_color=np.array([-1,-1,-1])
                else:
                    current_pixel_color=image_matrix[y_round, x_round]

                #check if the current pixel is the same color as the hatch color
                if current_pixel_color[0]==color[0] and current_pixel_color[1]==color[1] and current_pixel_color[2]==color[2]: #MUCH faster than np.array_equal
                    
                    if polyline:
                        # polyline.append(Point(x1, y1, z1, 1, color[0], color[1], color[2]))
                        pass
                    else:
                        x1=(x-center[0])/pixel_per_mm
                        y1=(y-center[1])/pixel_per_mm
                        z1=0
                        polyline.append(Point(x1, y1, z1, 0, color[0], color[1], color[2]))
                else:
                    if polyline:
                        x1=((x+prev_x)/2-center[0])/pixel_per_mm
                        y1=((y+prev_y)/2-center[1])/pixel_per_mm
                        z1=0
                        polyline.append(Point(x1, y1, z1, 1, color[0], color[1], color[2]))
                        polyline_cache.append(polyline)
                        polyline=[]
                        
                #increase the x/y step and keep track of last position
                x_target -= cos_theta * step_size
                if hatch_mode == "CylEquidistX":
                    if np.abs(x_target-center[0])>cyl_rad:
                        point_outside=True
                    else:
                        prev_x=x
                        x=np.asin((x_target-center[0])/cyl_rad)*(cyl_rad)+center[0]
                else:
                    prev_x=x
                    x=x_target
                prev_y = y
                y -= sin_theta * step_size

            #finally append the last line if there is one
            if polyline:
                        x1=((x+prev_x)/2-center[0])/pixel_per_mm
                        y1=((y+prev_y)/2-center[1])/pixel_per_mm
                        z1=0
                        polyline.append(Point(x1, y1, z1, 1, color[0], color[1], color[2]))
                        polyline_cache.append(polyline)
                        polyline=[]
            #append polyines here in correct order for meandering
            if hatch_line_dir==1:
                for poly_line in polyline_cache:
                    hatch_lines_poly.append(poly_line)
            else:
                for poly_line in reversed(polyline_cache):
                    poly_line[0].move_type=1
                    poly_line[-1].move_type=0
                    hatch_lines_poly.append(list(reversed(poly_line)))

            hatch_line_dir*=-1

            # move to next line. First move along y, then along x
            if not hatch_y_finished:
                hatch_start_y += step_start_y 
                if hatch_start_y >= max_y:
                    hatch_y_finished = True #check if we are at the end of the bounding box in y-direction
            elif not hatch_x_finished:
                if hatch_y_finished and not hatch_start_y>=max_y:
                    hatch_start_y=max_y+1 # this is just for 90deg case. y hast to be set manually
                hatch_start_x += incline*step_start_x
                if (hatch_start_x <= min_x or incline==1) and (hatch_start_x >= max_x or incline==-1): #check if we are at the end of the bounding box in x-direction
                    hatch_x_finished = True
            else:
                hatching_done = True

            #update progress bar
            line_count+=1
            current_state = np.ceil((progress_state[0]+line_count/max_lines)/progress_state[1]*100)
            if current_state > self.hatch_progress_bar.value()+1 and not self.hatching_cancelled:
                self.worker.progress.emit(int(current_state))
                pass
        return hatch_lines_poly
        
    def hatch_circular(self, hatch_distance, step_size, image_matrix, pixel_per_mm, color, hatch_mode, cyl_rad, progress_state):
        hatch_lines_poly=[]
        # Maximum Radius of one circle defined by the cluster diagonal, plus extra space for one hatch line
        max_rad = np.ceil(
            np.sqrt((image_matrix.shape[0]/2)**2+(image_matrix.shape[1]/2)**2))+np.ceil(hatch_distance)

        center = [(image_matrix.shape[1]-1)/2,
                  (image_matrix.shape[0]-1)/2]

        point_outside=False
        hatch_rad = hatch_distance/10 #just the start radius is smaller

        #loop over circles. will stop when the circle is outside the image
        while hatch_rad <= max_rad:
            #check if hatching was cancelled
            if self.hatching_cancelled:
                return None
            
            angle_res = step_size/hatch_rad
            if angle_res > 2*np.pi/36:
                angle_res = 2*np.pi/36
            # Randomly choose theta between 0 and 19 degrees
            start_angle = np.deg2rad(np.floor(random.uniform(0, 20)))
            polyline = []
            current_pixel_color=np.array([-1,-1,-1]) #use non existend color when the point is outside the image

            #loop over single circle. points are known so use a foor loop. The inside is called A LOT. Use as few function calls as possible
            for angle in np.linspace(start_angle, start_angle+2*np.pi, int(np.ceil(2*np.pi/angle_res))):
                x = center[0]+hatch_rad*np.cos(angle)
                if hatch_mode == "CylEquidistX":
                    if np.abs(x-center[0])>cyl_rad:
                        point_outside=True
                    else:
                        x=np.asin((x-center[0])/cyl_rad)*(cyl_rad)+center[0]
                y = center[1]+hatch_rad*np.sin(angle)

                #use a special rounding for x and y for efficiency. we know that they can never be negative (else it will be caught anyway)
                if int(y)==int(y-0.5):
                    y_round=int(y+1)
                else:
                    y_round=int(y)
                if int(x)==int(x-0.5):
                    x_round=int(x+1)
                else:
                    x_round=int(x)

                #check if current pixel is outside the image
                if point_outside or y_round>=image_matrix.shape[0] or y_round<0 or x_round>= image_matrix.shape[1] or x_round<0:
                    if polyline:
                        if len(polyline) > 1:
                            hatch_lines_poly.append(polyline)
                        polyline = []
                    point_outside=False
                    current_pixel_color=np.array([-1,-1,-1])
                else:
                    current_pixel_color=image_matrix[y_round, x_round]

                #check if current pixel is the color we want to hatch
                if current_pixel_color[0]==color[0] and current_pixel_color[1]==color[1] and current_pixel_color[2]==color[2]: #MUCH faster than np.array_equal
                    x1 = (x-center[0])/pixel_per_mm
                    y1 = (y-center[1])/pixel_per_mm
                    z1 = 0
                    if polyline:
                        polyline.append(Point(x1, y1, z1, 1, color[0], color[1], color[2]))
                    else:
                        polyline.append(Point(x1, y1, z1, 0, color[0], color[1], color[2]))
                else:
                    if polyline:
                        if len(polyline) > 1:
                            hatch_lines_poly.append(polyline)
                        polyline = []

                angle += angle_res
            if polyline:  # if we have a last line add it
                if len(polyline) > 1:
                        hatch_lines_poly.append(polyline)
                polyline = []
            hatch_rad += hatch_distance
            #update progress bar
            current_state = np.ceil((progress_state[0]+hatch_rad/max_rad)/progress_state[1]*100)
            if current_state > self.hatch_progress_bar.value()+1 and not self.hatching_cancelled:
                self.worker.progress.emit(int(current_state))
        return hatch_lines_poly
            
    def hatch_spiral(self, hatch_distance, step_size, image_matrix, pixel_per_mm,color, hatch_mode, cyl_rad, progress_state):
        hatch_lines_poly=[]
        # Maximum Radius of one circle defined by the cluster diagonal
        max_rad = np.ceil(
            np.sqrt((image_matrix.shape[0]/2)**2+(image_matrix.shape[1]/2)**2))+np.ceil(hatch_distance)


        center = [(image_matrix.shape[1]-1)/2,
                  (image_matrix.shape[0]-1)/2]

        x = center[0]
        y = center[1]
        hatch_rad_avg=hatch_distance/2
        point_outside=False

        #loop over spiral. will stop when the spiral is outside the image
        while hatch_rad_avg+hatch_distance/2 <= max_rad:
            #check if hatching was cancelled
            if self.hatching_cancelled:
                return None
            
            angle_res = step_size/hatch_rad_avg
            if angle_res > 2*np.pi/36:
                angle_res = 2*np.pi/36
            polyline = []
            angles = np.linspace(0, 2*np.pi, int(np.ceil(2*np.pi/angle_res)))
            hatch_radii = np.linspace(hatch_rad_avg-hatch_distance/2, hatch_rad_avg+hatch_distance/2, int(np.ceil(2*np.pi/angle_res))) 
            current_pixel_color=np.array([-1,-1,-1]) #use non existend color when the point is outside the image

            #loop over single circle of the spiral. points are known so use a foor loop. The inside is called A LOT. Use as few function calls as possible
            for angle, hatch_rad in zip(angles, hatch_radii):
                x = center[0]+hatch_rad*np.cos(angle)
                if hatch_mode == "CylEquidistX":
                    if np.abs(x-center[0])>cyl_rad:
                        point_outside=True
                    else:
                        x=np.asin((x-center[0])/cyl_rad)*(cyl_rad)+center[0]
                y = center[1]+hatch_rad*np.sin(angle)

                #use a special rounding for x and y for efficiency. we know that they can never be negative (else it will be caught anyway)
                if int(y)==int(y-0.5):
                    y_round=int(y+1)
                else:
                    y_round=int(y)
                if int(x)==int(x-0.5):
                    x_round=int(x+1)
                else:
                    x_round=int(x)

                #check if current pixel is outside the image
                if point_outside or y_round>=image_matrix.shape[0] or y_round<0 or x_round>= image_matrix.shape[1] or x_round<0:
                    if polyline:
                        if len(polyline) > 1:
                            hatch_lines_poly.append(polyline)
                        polyline = []
                    point_outside=False
                    current_pixel_color=np.array([-1,-1,-1])
                else:
                    current_pixel_color=image_matrix[y_round, x_round]

                #check if current pixel is the color we want to hatch        
                if current_pixel_color[0]==color[0] and current_pixel_color[1]==color[1] and current_pixel_color[2]==color[2]: #MUCH faster than np.array_equal
                    x1 = (x-center[0])/pixel_per_mm
                    y1 = (y-center[1])/pixel_per_mm
                    z1 = 0
                    if polyline:
                        polyline.append(Point(x1, y1, z1, 1, color[0], color[1], color[2]))
                    else:
                        polyline.append(Point(x1, y1, z1, 0, color[0], color[1], color[2]))

                else:
                    if polyline:
                        if len(polyline) > 1:
                            hatch_lines_poly.append(polyline)
                        polyline = []
                angle += angle_res
            if polyline:  # if we have a last line add it
                if len(polyline) > 1:
                        hatch_lines_poly.append(polyline)
                polyline = []
            hatch_rad_avg += hatch_distance
            #update progress bar
            current_state = np.ceil((progress_state[0]+hatch_rad_avg/max_rad)/progress_state[1]*100)
            if current_state > self.hatch_progress_bar.value()+1 and not self.hatching_cancelled:
                self.worker.progress.emit(int(current_state))
        return hatch_lines_poly
            
    def hatch_radial(self, hatch_distance, step_size, image_matrix, pixel_per_mm, color, hatch_mode, cyl_rad,progress_state):
        hatch_lines_poly=[]
        hatch_line_dir=1
        # We have to pad the array, since start points of hatchlines might lay outside the image
        # Maximum Radius of one circle defined by the cluster diagonal
        max_rad = np.ceil(
            np.sqrt((image_matrix.shape[0]/2)**2+(image_matrix.shape[1]/2)**2))+np.ceil(hatch_distance)

        center = [(image_matrix.shape[1]-1)/2,
                  (image_matrix.shape[0]-1)/2]

        hatch_start_x = center[0]
        hatch_start_y = center[1]
        angle_res=np.atan(hatch_distance/max_rad)*2
        angles = np.linspace(0, 2*np.pi, int(np.ceil(2*np.pi/angle_res)))
        
        ray_count=0
        
        #loop over radial rays. ray number is known so use a for loop
        for angle in angles:
            #check if hatching was cancelled
            if self.hatching_cancelled:
                return None
            
            sin_angle=np.sin(angle)
            cos_angle=np.cos(angle)
            x_target = hatch_start_x
            prev_x=None
            prev_y=None
            if hatch_mode == "CylEquidistX":
                if np.abs(x_target-center[0])>cyl_rad:
                    point_outside=True
                    x=0 # just a dummy
                else:
                    x=np.asin((x_target-center[0])/cyl_rad)*(cyl_rad)+center[0]
            else:
                x=x_target
            y = hatch_start_y

            polyline = []
            polyline_cache=[]
            point_outside=False
            current_pixel_color=np.array([-1,-1,-1]) #use non existend color when the point is outside the image

            #loop over single ray. stop when the ray is outside the image. This is looped over A LOT. Limit ALL function calls as much as possible
            while np.sqrt((x_target-center[0])**2+(y-center[1])**2) <= max_rad:
                #use a special rounding for x and y for efficiency. we know that they can never be negative (else it will be caught anyway)
                if int(y)==int(y-0.5):
                    y_round=int(y+1)
                else:
                    y_round=int(y)
                if int(x)==int(x-0.5):
                    x_round=int(x+1)
                else:
                    x_round=int(x)

                #check if current pixel is outside the image
                if point_outside or y_round>=image_matrix.shape[0] or y_round<0 or x_round>= image_matrix.shape[1] or x_round<0:
                    if polyline:
                        x1=((x+prev_x)/2-center[0])/pixel_per_mm
                        y1=((y+prev_y)/2-center[1])/pixel_per_mm
                        z1=0
                        polyline.append(Point(x1, y1, z1, 1, color[0], color[1], color[2]))
                        polyline_cache.append(polyline)
                        polyline=[]
                    point_outside=False
                    current_pixel_color=np.array([-1,-1,-1])
                else:
                    current_pixel_color=image_matrix[y_round, x_round]
                
                #check if current pixel is the color we want to hatch
                if current_pixel_color[0]==color[0] and current_pixel_color[1]==color[1] and current_pixel_color[2]==color[2]: #MUCH faster than np.array_equal
                    x1=(x-center[0])/pixel_per_mm
                    y1=(y-center[1])/pixel_per_mm
                    z1=0
                    if polyline:
                        pass
                        # polyline.append(Point(x1, y1, z1, 1, color[0], color[1], color[2]))
                    else:
                        polyline.append(Point(x1, y1, z1, 0, color[0], color[1], color[2]))
                else:
                    if polyline:
                        x1=((x+prev_x)/2-center[0])/pixel_per_mm
                        y1=((y+prev_y)/2-center[1])/pixel_per_mm
                        z1=0
                        polyline.append(Point(x1, y1, z1, 1, color[0], color[1], color[2]))
                        polyline_cache.append(polyline)
                        polyline=[]
                x_target += cos_angle * step_size
                if hatch_mode == "CylEquidistX":
                    if np.abs(x_target-center[0])>cyl_rad:
                        point_outside=True
                    else:
                        prev_x=x
                        x=np.asin((x_target-center[0])/cyl_rad)*(cyl_rad)+center[0]
                else:
                    prev_x=x
                    x=x_target
                prev_y=y
                y += sin_angle * step_size
            
            #finally append line if there is an open one
            if polyline:
                    x1=((x+prev_x)/2-center[0])/pixel_per_mm
                    y1=((y+prev_y)/2-center[1])/pixel_per_mm
                    z1=0
                    polyline.append(Point(x1, y1, z1, 1, color[0], color[1], color[2]))
                    polyline_cache.append(polyline)
                    polyline=[]

            #append polyines here in correct order for meandering
            if hatch_line_dir==1:
                for poly_line in polyline_cache:
                    hatch_lines_poly.append(poly_line)
            else:
                for poly_line in reversed(polyline_cache):
                    poly_line[0].move_type=1
                    poly_line[-1].move_type=0
                    hatch_lines_poly.append(list(reversed(poly_line)))

            ray_count+=1
            hatch_line_dir*=-1

            #update progress bar
            current_state = np.ceil((progress_state[0]+ray_count/len(angles))/progress_state[1]*100)
            if current_state > self.hatch_progress_bar.value()+1 and not self.hatching_cancelled:
                self.worker.progress.emit(int(current_state))
            #print("finished radial ray " + str(ray_count) + " / " + str(len(angles)))
        return hatch_lines_poly
            
            
    def make_hatch_cylindrical(self, hatched_clusters,cyl_rad_mm=100):
        hatched_clusters_cylindrical = []
        radius = cyl_rad_mm
        for hatch_lines in hatched_clusters:
            #check if hatching was cancelled
            if self.hatching_cancelled:
                return None
            
            hatch_lines_cylindrical = []
            for polyline in hatch_lines:
                polyline_cyl = []
                if len(polyline) > 2:  # we have an actual polyline

                    for point in polyline:
                        x = point.x
                        y = point.y
                        z = point.z
                        m=point.move_type
                        r=point.r
                        g=point.g
                        b=point.b
                        angle = x/radius
                        x_cyl = radius*np.sin(angle)
                        z_cyl = radius*np.cos(angle)-radius
                        y_cyl = y

                        polyline_cyl.append(Point(x_cyl, y_cyl, z_cyl, m, r, g, b))
                elif len(polyline)==2:  # we have a single line of one color
                    point1, point2 = polyline
                    len_x = np.abs(point1.x-point2.x)*10 #100µm steps in x direction
                    if len_x<2:
                        len_x=2
                    nodes_x = np.linspace(point1.x, point2.x, int(np.ceil(len_x)))
                    nodes_y = np.linspace(point1.y, point2.y, int(np.ceil(len_x)))

                    for i in range(len(nodes_x)):
                        angle = nodes_x[i]/radius
                        x_cyl = radius*np.sin(angle)
                        z_cyl = radius*np.cos(angle)-radius
                        y_cyl = nodes_y[i]
                        if i == 0:
                            polyline_cyl.append(Point(x_cyl, y_cyl, z_cyl, point1.move_type, point1.r, point1.g, point1.b))
                        else:
                            polyline_cyl.append(Point(x_cyl, y_cyl, z_cyl, point2.move_type, point2.r, point2.g, point2.b))
                        
                else:
                    print("Single Hatch-Point encountered. This should not happen. Skipping it.")
                hatch_lines_cylindrical.append(polyline_cyl)
            hatched_clusters_cylindrical.append(hatch_lines_cylindrical)
        return hatched_clusters_cylindrical
    
    def create_contours(self):
        source = self.contour_source_combobox.currentText()
        if source == "Image":
            self.contour_from_image()
        elif source == ".dxf File":
            self.contour_from_dxf()
        else:
            print("Error: contour source not supported.")

    def contour_from_image(self):
        self.get_handler_data()
        self.hatch_data.data=[]
        polyline_cluster=[]
        height, width, _ = self.image_matrix.shape
        center = [(width)/2, (height)/2]
        for polyline in self.contours_list:
            polyline_new=[]
            if type(polyline[0])==int: #single point detected. skip it
                continue
            for i, point in enumerate(polyline):
                x=(point[0]-center[0])/self.pixel_per_mm
                y=((height-point[1]-1)-center[1])/self.pixel_per_mm
                z=0
                if i==0:
                    m=0
                else: 
                    m=1
                r=0
                g=0
                b=0
                polyline_new.append(Point(x,y,z,m,r,g,b))
            #always close contours, by appending first point as last.
            last_point=polyline[0]
            x=(last_point[0]-center[0])/self.pixel_per_mm
            y=((height-last_point[1]-1)-center[1])/self.pixel_per_mm
            z=0
            polyline_new.append(Point(x,y,z,1,0,0,0))
            polyline_cluster.append(polyline_new)
        self.hatch_data.data.append(polyline_cluster)
        self.hatch_data.type = "Contours"
        self.set_handler_data()
    
    def contour_from_dxf(self):
        """
        Reads a DXF file and gathers lines, polylines, circles, arcs, etc.
        Approximates arcs & circles into polylines.
        Then shifts everything so the top-left corner of the bounding box is (0,0).
        Stores the result in self.hatch_data as a list of polylines (each a list of Point).
        """
        file_path, _ = QFileDialog.getOpenFileName()
        if not file_path:
            return

        doc = ezdxf.readfile(file_path)
        msp = doc.modelspace()

        polylines_raw = []
        all_points = []

        #need functions to convert circles and arcs
        def approximate_circle(center, radius, segments=36):
            """Return a list of (x, y) points approximating the entire circle."""
            cx, cy = center
            points = []
            for i in range(segments):
                angle = 2.0 * np.pi * i / segments
                x = cx + radius * np.cos(angle)
                y = cy + radius * np.sin(angle)
                points.append((x, y))
            # Close the circle
            points.append(points[0])
            return points

        def approximate_arc(center, radius, start_angle, end_angle, segments=36):
            """Return a list of (x, y) points approximating an arc from start_angle to end_angle."""
            cx, cy = center
            points = []
            sweep = end_angle - start_angle
            for i in range(segments + 1):
                frac = i / segments
                angle = np.radians(start_angle + sweep * frac)
                x = cx + radius * np.cos(angle)
                y = cy + radius * np.sin(angle)
                points.append((x, y))
            return points

        # Collect LINE entities (each is 2 points)
        for entity in msp.query("LINE"):
            start = entity.dxf.start
            end = entity.dxf.end
            line_poly = [(start.x, start.y), (end.x, end.y)]
            polylines_raw.append(line_poly)
            all_points.extend(line_poly)

        # Collect LWPOLYLINE entities
        for entity in msp.query("LWPOLYLINE"):
            coords = [(x, y) for x, y, *rest in entity.lwpoints]
            polylines_raw.append(coords)
            all_points.extend(coords)
        
        # Collect regular POLYLINE entities (2D)
        for entity in msp.query("POLYLINE"):
            # Some polyline entities can have vertices
            coords = []
            for vertex in entity.vertices:
                coords.append((vertex.dxf.location.x, vertex.dxf.location.y))
            if coords:
                polylines_raw.append(coords)
                all_points.extend(coords)

        # Collect CIRCLE entities, approximate them
        for entity in msp.query("CIRCLE"):
            center = (entity.dxf.center.x, entity.dxf.center.y)
            radius = entity.dxf.radius
            circle_approx = approximate_circle(center, radius, segments=100)
            polylines_raw.append(circle_approx)
            all_points.extend(circle_approx)

        # Collect ARC entities, approximate them
        for entity in msp.query("ARC"):
            center = (entity.dxf.center.x, entity.dxf.center.y)
            radius = entity.dxf.radius
            start_angle = entity.dxf.start_angle
            end_angle = entity.dxf.end_angle
            segments=abs(start_angle-end_angle)/2/np.pi*100
            arc_approx = approximate_arc(center, radius, start_angle, end_angle, segments=segments)
            polylines_raw.append(arc_approx)
            all_points.extend(arc_approx)

        if not all_points:
            print("Error: No geometry found in the DXF.")
            return
        
        # Compute bounding box & shift so top-left => (0,0)
        min_x = min(pt[0] for pt in all_points)
        min_y = min(pt[1] for pt in all_points)
        
        # Shift polylines
        polylines_shifted = []
        for poly in polylines_raw:
            shifted_poly = []
            for i, (px, py) in enumerate(poly):
                # Shift to make top-left corner at (0,0)
                sx = px - min_x
                sy = py - min_y
                shifted_poly.append((sx, sy))
            polylines_shifted.append(shifted_poly)

        # Convert to hatch_data format: list of polylines, each a list of Points
        # move_type: 0 for the first point, 1 for subsequent points
        hatch_data = []
        for poly in polylines_shifted:
            point_list = []
            for i, (px, py) in enumerate(poly):
                move = 0 if i == 0 else 1
                point_list.append(Point(px, py, 0, move, r=0, g=0, b=0))
            hatch_data.append(point_list)

        self.hatch_data.data = [hatch_data]  # store as a list of lists of polylines
        self.hatch_data.type = "DXF_Imported"
        self.set_handler_data()

 

    def set_handler_data(self):
        self.data_handler.hatch_data = self.hatch_data

    def get_handler_data(self):
        self.image_matrix = self.data_handler.image_matrix
        self.pixel_per_mm = self.data_handler.pixel_per_mm
        self.contours_list = self.data_handler.contours_list


class HatchingWorker(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal(object)
    
    def __init__(self, hatcher, mode, db_color_palette=None, hatch_pattern=None, 
                 hatch_angle=None, cyl_rad_mm=None, hatch_mode=None, 
                 stepsize_mm=None, white_threshold=None):
        super().__init__()
        self.hatcher = hatcher
        self.mode = mode
        self.db_color_palette = db_color_palette
        self.hatch_pattern = hatch_pattern
        self.hatch_angle = hatch_angle
        self.cyl_rad_mm = cyl_rad_mm
        self.hatch_mode = hatch_mode
        self.stepsize_mm = stepsize_mm
        self.white_threshold = white_threshold
        self.cancelled = False
        
    def run(self):
        try:
            result = self.hatcher.create_hatching_worker(
                self.mode, self.db_color_palette, self.hatch_pattern,
                self.hatch_angle, self.cyl_rad_mm, self.hatch_mode,
                self.stepsize_mm, self.white_threshold
            )
            if not self.cancelled:
                self.finished.emit(result)
        except Exception as e:
            print(f"Error in worker thread: {e}")
            
    def cancel(self):
        self.cancelled = True
        self.quit()  # Use quit() instead of terminate()
        self.wait()  # Wait for the thread to finish



