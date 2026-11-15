from PyQt6 import QtWidgets
from PyQt6.QtWidgets import QFileDialog, QProgressDialog 
from PyQt6.QtCore import QObject, QThread, QEventLoop, pyqtSignal
import logging
import numpy as np
from collections import defaultdict
import random
import dataclasses
from HelperClasses import HatchData, HatchCluster
from core.toolpath import Layer, polyline, X, Y, MOVE, MOVE_TRAVEL, MOVE_BURN
import ezdxf

log = logging.getLogger(__name__)


def _to_layer(color, line_collection):
    """One hatched colour: list of row lists -> Layer with polyline arrays."""
    return Layer((int(color[0]), int(color[1]), int(color[2])), [polyline(rows) for rows in line_collection])

'''
This module contains the Hatcher class, which is responsible for generating hatching patterns based on the input image and user settings. 
It includes methods for creating different hatch patterns, calculating clusters for hatching, and managing the hatching process in a separate thread to keep the GUI responsive.

DATA-ARCHITECTURE (see core/toolpath.py):
- HatchData: a list of HatchClusters and a type description.
- HatchCluster: one part of the image (cylindrical hatching may split the image). `data` is a list of Layers,
  plus the input image matrix of the cluster, its reference position and the cylinder radius.
- Layer: all polylines of one colour, with colour, speed and power of that colour.
- Polyline: float ndarray (N, 4) with rows (x, y, z, move) in mm; move is MOVE_TRAVEL / MOVE_BURN / MOVE_RAPID.
'''

class Hatcher(QObject):  # QObject so worker signals are delivered on the GUI thread
    def __init__(self, data_handler, gui):
        super().__init__()
        self.data_handler = data_handler
        self.gui = gui
        self.hatch_data = HatchData([], "")
        self.clusters = None
        self.image_matrix = None
        self.pixel_per_mm = None
        self.hatching_cancelled = False
        self._last_progress = 0
        self.center_for_hatch = None  # Center of the image for Hatching

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

    def calculate_clusters(self, hatch_mode, workpiece_radius):
        hatch_data= HatchData([], "")
        image_matrix = self.image_matrix #np.flipud(self.image_matrix)

        if hatch_mode in ["CylEquidistX", "CylEquidistRad"]:

            # Check if the image ist too large for cylindrical hatching (Laser Distance has to be maintained). Dive then.
            image_width_px = image_matrix.shape[1]
            image_with_mm = image_width_px / self.pixel_per_mm
            z_dist = 17 # Distance from in mm laser to workpiece for 1064nm lasers
            radius_mm = workpiece_radius
            
            #calculate the maximum angle allowed to maintain laser distance
            max_angle_allowed = np.acos(np.clip((radius_mm - z_dist)/radius_mm, -1, 1)) * 2 * (180/np.pi)  # in degrees; B26: clip for radius < z_dist

            #calculate the angle that the image would cover on the cylinder
            max_angle_image=image_with_mm/(2*np.pi*radius_mm)*360
            if max_angle_image>360:
                return None
            
            #get the center of the image_matrix for hatching
            if self.center_for_hatch is None:
                self.center_for_hatch = [(image_matrix.shape[1]-1)/2,
                                (image_matrix.shape[0]-1)/2]
            
            if max_angle_image>max_angle_allowed:
                clusters_needed = int(np.ceil(max_angle_image/max_angle_allowed))
                cluster_width_px = int(np.ceil(image_width_px/clusters_needed))
                for i in range(clusters_needed):
                    start_x = i * cluster_width_px
                    end_x = min((i + 1) * cluster_width_px, image_width_px)
                    cluster_matrix = image_matrix[:, start_x:end_x]
                    cluster_mid_x_rel_to_image_center = ((start_x + end_x) / 2 - self.center_for_hatch[0]) / self.pixel_per_mm
                    angle_for_cluster_mid = (cluster_mid_x_rel_to_image_center/(2*radius_mm*np.pi) * 360) #*-1 #invert angle for correct rotation direction
                    ref_position = [0, 0, 0, angle_for_cluster_mid]  # x, y, z, rotation
                    cluster_center_for_hatch = [(cluster_matrix.shape[1]-1)/2, self.center_for_hatch[1], 0]
                    hatch_data.hatch_clusters.append(HatchCluster(None, cluster_matrix, ref_position,cluster_center_for_hatch, radius_mm))
                return hatch_data
        else:
            radius_mm = 0  # Not used for non-cylindrical hatching

        #if not cylindrical hatching or image fits within laser distance, return single cluster
        hatch_data.hatch_clusters.append(HatchCluster(None, image_matrix, ref_position=[0,0,0,0], cluster_center_for_hatch=self.center_for_hatch, cylinder_radius=radius_mm))

        return hatch_data

    def get_sorted_unique_colors(self, image_matrix):
        """
        Extracts all unique RGB colors from the image and sorts them by the sum of the RGB values in descending order.

        Args:
            image_matrix (numpy.ndarray): The image matrix with shape (height, width, 3).

        Returns:
            list: A list of unique RGB colors sorted by the sum of the RGB values in descending order.
        """
        # # Reshape the image matrix to a 2D array where each row is an RGB color
        # reshaped_image = image_matrix.reshape(-1, 3)
        
        # # Get unique colors
        # unique_colors = np.unique(reshaped_image, axis=0)
        
        # # Sort unique colors by the sum of the RGB values in descending order
        # sorted_colors = sorted(unique_colors, key=lambda color: np.sum(color), reverse=True)
        
        # # Convert sorted colors to a list of tuples
        # sorted_colors_list = [tuple(color) for color in sorted_colors]
        # Reshape and convert rows to tuples

        #new implementation for speed
        reshaped = image_matrix.reshape(-1, 3)
        
        # Use a set to get unique colors (very fast)
        unique_colors_set = set(map(tuple, reshaped))
        
        # Convert to list and sort by sum of RGB values
        sorted_colors_list = sorted(unique_colors_set, key=lambda color: int(color[0]) + int(color[1]) + int(color[2]), reverse=True)  # B23: int() avoids uint8 overflow
    
        return sorted_colors_list
    
    def collect_hatch_settings(self, mode="manual", **overrides):
        """Read all hatch parameters from the GUI. Must run on the GUI thread."""
        settings = dict(
            mode=mode,
            db_color_palette=None,
            hatch_pattern=self.hatch_pattern_combobox.currentText(),
            hatch_angle=self.hatch_angle_spinbox.value(),
            hatch_dist_mode="Fixed" if mode == "automatic" else self.hatch_dist_mode_combobox.currentText(),
            hatch_dist_min=self.hatch_dist_min_spinbox.value(),
            hatch_dist_max=self.hatch_dist_max_spinbox.value(),
            cyl_rad_mm=self.cyl_rad_spinbox.value(),
            hatch_mode=self.hatch_mode_combobox.currentText(),
            stepsize_mm=self.hatch_precision_spinbox.value(),
            white_threshold=self.white_threshold_hatching_spinbox.value(),
        )
        settings.update(overrides)
        return settings

    def create_hatching(self, mode="manual", **overrides):
        """Start hatching in a worker thread. In automatic mode this blocks until the worker is done
        and returns True if a result was produced."""
        settings = self.collect_hatch_settings(mode, **overrides)

        self.progress_dialog = QProgressDialog("Hatching in progress...", "Cancel", 0, 100, self.gui)
        self.progress_dialog.setWindowTitle("Creating Hatch Pattern")
        self.progress_dialog.setModal(True)

        self.hatching_cancelled = False
        self._last_progress = 0
        self._hatch_result = None
        self._hatch_error = None
        self.hatch_progress_label.setText("Hatch Progress: Hatching...")

        self.worker = HatchingWorker(self, settings)
        self.worker.progress.connect(self.progress_dialog.setValue)
        # single completion slot (QThread.finished is always emitted, also on error/cancel) -> deterministic order
        self.worker.finished.connect(self._on_worker_done)
        self.progress_dialog.canceled.connect(self.cancel_hatching)

        self._worker_done = False
        self._wait_loop = QEventLoop() if mode == "automatic" else None
        self.worker.start()
        self.progress_dialog.show()
        if self._wait_loop is not None:
            if not self._worker_done:
                self._wait_loop.exec()
            self._wait_loop = None
            return self._hatch_result is not None
        return None

    def create_hatching_worker(self, mode="manual", db_color_palette=None, hatch_pattern=None, hatch_angle=None,
                               hatch_dist_mode="Fixed", hatch_dist_min=None, hatch_dist_max=None, cyl_rad_mm=None,
                               hatch_mode=None, stepsize_mm=None, white_threshold=None):
        """Runs in the worker thread: must not touch any widget."""
        try:
            self.get_handler_data()
            self._report_progress(0)

            #check if hatching was cancelled
            if self.hatching_cancelled:
                return None

            #divde the image into clusters to hatch and store in appropriate output format already. then loop over all clusters
            hatch_data = self.calculate_clusters(hatch_mode, cyl_rad_mm)
            if hatch_data is None:
                self._hatch_error = "The image is too wide to be wrapped around the cylinder (more than 360 degrees)."
                return None

            for idx, hatch_cluster in enumerate(hatch_data.hatch_clusters):
                cluster_progress = (idx+1)/len(hatch_data.hatch_clusters)*100
                #first get the colors of the cluster
                color_list = self.get_sorted_unique_colors(hatch_cluster.input_matrix)
                hatch_cluster.data = self.hatch_cluster(
                    cluster_matrix = hatch_cluster.input_matrix,
                    cluster_center_for_hatch = hatch_cluster.cluster_center_for_hatch,
                    mode=mode,
                    color_list=color_list,
                    hatch_pattern=hatch_pattern,
                    hatch_angle=hatch_angle,
                    hatch_dist_mode=hatch_dist_mode,
                    hatch_dist_min=hatch_dist_min,
                    hatch_dist_max=hatch_dist_max,
                    cyl_rad_mm=cyl_rad_mm,
                    hatch_mode=hatch_mode,
                    stepsize_mm=stepsize_mm,
                    white_threshold=white_threshold,
                    db_color_palette=db_color_palette,
                    cluster_progress = cluster_progress
                )
                if hatch_cluster.data == 0 or hatch_cluster.data is None:
                    return None

            if mode == "automatic":
                hatch_data.type = "Image: database profile"
            else:
                hatch_data.type = f"Image: {hatch_pattern} with {hatch_dist_mode} Lines"

            #check if hatching was cancelled
            if self.hatching_cancelled:
                return None
            if hatch_mode in ["CylEquidistX", "CylEquidistRad"]:
                for hatch_cluster in hatch_data.hatch_clusters:
                    hatch_cluster.data = self.make_hatch_cylindrical(hatch_cluster.data, cyl_rad_mm)
                hatch_data.type += f" and {hatch_mode}"
            return hatch_data

        except Exception as e:
            log.exception("Error hatching clusters")
            self._hatch_error = str(e)
            return None

    def _report_progress(self, value):
        """Emit progress (0-100) only when it increased, to keep signal traffic low."""
        value = int(value)
        if value > self._last_progress and not self.hatching_cancelled:
            self._last_progress = value
            self.worker.progress.emit(value)

    def hatching_finished(self, result):
        self._hatch_result = result
        if result:
            self.hatch_data = result
            self.set_handler_data()
            self.hatch_progress_label.setText("Hatch State: Finished!")

    def _on_worker_done(self):
        self._worker_done = True
        self.progress_dialog.canceled.disconnect(self.cancel_hatching)  # close() emits canceled
        self.progress_dialog.close()
        if not self.hatching_cancelled:
            self.hatching_finished(self.worker.result)
            if self.worker.result is None:
                self.hatch_progress_label.setText("Hatch State: Failed")
                QtWidgets.QMessageBox.warning(self.gui, "Hatching failed", self._hatch_error or "Hatching produced no result.")
        if self._wait_loop is not None:
            self._wait_loop.quit()

    def cancel_hatching(self):
        if not hasattr(self, 'worker'):
            return
        self.hatching_cancelled = True
        # keep QThread.finished connected: it closes the dialog and ends the automatic-mode wait loop
        self.worker.progress.disconnect()
        self.worker.wait()
        self.hatch_progress_label.setText("Hatch State: Cancelled")

    def hatch_cluster(self, cluster_matrix, cluster_center_for_hatch, mode="manual", color_list=None, hatch_pattern="RandomMeander", hatch_angle=90, hatch_dist_mode="ColorRanged", hatch_dist_min=300, hatch_dist_max=700, cyl_rad_mm = 100, hatch_mode = "Flat", stepsize_mm = 0.1, white_threshold=255, db_color_palette=None, cluster_progress=0):
        hatched_cluster = []
        color_cluster_counter = 0
        cyl_rad = cyl_rad_mm * self.pixel_per_mm
        #cluster = np.flipud(self.image_matrix)
        
        # if self.center_for_hatch is None:
        #     self.center_for_hatch = [(input_matrix.shape[1]-1)/2,
        #                     (input_matrix.shape[0]-1)/2]

        for color in color_list:
            #check if hatching was cancelled
            if self.hatching_cancelled:
                return None
            
            # Ensure the sum of RGB values is within a safe range
            color = np.array(color, dtype=np.int64)

            if sum(color)/3 > white_threshold:
                # Skip colors that are too bright (white), and update the progress bar
                color_cluster_counter += 1
                self._report_progress(np.ceil(color_cluster_counter / len(color_list) * cluster_progress))
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
                    hatch_distance = (hatch_dist_min + sum(color) / 765 * (hatch_dist_max - hatch_dist_min))/1000
                elif hatch_dist_mode == "Fixed":
                    hatch_distance = hatch_dist_min/1000
                else:
                    print("Hatch Distance Mode not recognized")
                    continue

            step_size = stepsize_mm * self.pixel_per_mm  # Step size in pixels
            hatch_distance = hatch_distance * self.pixel_per_mm  # Hatch distance in pixels

            progress_state = [color_cluster_counter, len(color_list), cluster_progress]

            if hatch_pattern in ["RandomMeander", "FixedMeander"]:
                line_collection = self.hatch_meander(
                    hatch_pattern, hatch_distance, hatch_angle, step_size, cluster_matrix, cluster_center_for_hatch, color, hatch_mode, cyl_rad, progress_state
                )
                if line_collection == 0:
                    return 0
                else:
                    hatched_cluster.append(_to_layer(color, line_collection))
            elif hatch_pattern == "CrossedMeander":
                line_collection1 = self.hatch_meander(
                    hatch_pattern, hatch_distance, hatch_angle, step_size, cluster_matrix, cluster_center_for_hatch, color, hatch_mode, cyl_rad, progress_state, cross_angle=0
                )
                line_collection2 = self.hatch_meander(
                    hatch_pattern, hatch_distance, hatch_angle, step_size, cluster_matrix, cluster_center_for_hatch, color, hatch_mode, cyl_rad, progress_state, cross_angle=90
                )
                if line_collection1 == 0:
                    return 0
                else:
                    hatched_cluster.append(_to_layer(color, line_collection1))
                    hatched_cluster.append(_to_layer(color, line_collection2))
            elif hatch_pattern == "Circular":
                line_collection = self.hatch_circular(
                    hatch_distance, step_size, cluster_matrix, cluster_center_for_hatch, color, hatch_mode, cyl_rad, progress_state
                )
                if line_collection == 0:
                    return 0
                else:
                    hatched_cluster.append(_to_layer(color, line_collection))
            elif hatch_pattern == "Spiral":
                line_collection = self.hatch_spiral(
                    hatch_distance, step_size, cluster_matrix, cluster_center_for_hatch, color, hatch_mode, cyl_rad, progress_state
                )
                if line_collection == 0:
                    return 0
                else:
                    hatched_cluster.append(_to_layer(color, line_collection))
            elif hatch_pattern == "Radial":
                line_collection = self.hatch_radial(
                    hatch_distance, step_size, cluster_matrix, cluster_center_for_hatch, color, hatch_mode, cyl_rad, progress_state
                )
                if line_collection == 0:
                    return 0
                else:
                    hatched_cluster.append(_to_layer(color, line_collection))
            else:
                print("Unknown hatch method")
            color_cluster_counter += 1
            
            #check if hatching was cancelled
            if self.hatching_cancelled:
                return None
            

            # Update progress bar
            self._report_progress(np.ceil(color_cluster_counter / len(color_list) * cluster_progress))
        return hatched_cluster

    def hatch_meander(self, hatch_pattern, hatch_distance, hatch_angle, step_size, image_matrix, center, color, hatch_mode, cyl_rad, progress_state, cross_angle=None):
        line_collection_poly=[]
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

        # center = self.center_for_hatch
        #center = [(max_x+min_x)/2, (max_y+min_y)/2] #depreciated: no defined globally

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
            point_outside=False  # B04: must be reset before the cylinder check below may set it
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
                        x1=((x+prev_x)/2-center[0])/self.pixel_per_mm
                        y1=((y+prev_y)/2-center[1])/self.pixel_per_mm
                        z1=0
                        polyline.append([x1, y1, z1, 1])
                        polyline_cache.append(polyline)
                        polyline=[]
                    point_outside=False
                    current_pixel_color=np.array([-1,-1,-1])
                else:
                    current_pixel_color=image_matrix[y_round, x_round]

                #check if the current pixel is the same color as the hatch color
                if current_pixel_color[0]==color[0] and current_pixel_color[1]==color[1] and current_pixel_color[2]==color[2]: #MUCH faster than np.array_equal
                    
                    if polyline:
                        # polyline.append([x1, y1, z1, 1])
                        pass
                    else:
                        x1=(x-center[0])/self.pixel_per_mm
                        y1=(y-center[1])/self.pixel_per_mm
                        z1=0
                        polyline.append([x1, y1, z1, 0])
                else:
                    if polyline:
                        x1=((x+prev_x)/2-center[0])/self.pixel_per_mm
                        y1=((y+prev_y)/2-center[1])/self.pixel_per_mm
                        z1=0
                        polyline.append([x1, y1, z1, 1])
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
                        x1=((x+prev_x)/2-center[0])/self.pixel_per_mm
                        y1=((y+prev_y)/2-center[1])/self.pixel_per_mm
                        z1=0
                        polyline.append([x1, y1, z1, 1])
                        polyline_cache.append(polyline)
                        polyline=[]
            #append polyines here in correct order for meandering
            if hatch_line_dir==1:
                for poly_line in polyline_cache:
                    line_collection_poly.append(poly_line)
            else:
                for poly_line in reversed(polyline_cache):
                    poly_line[0][MOVE]=MOVE_BURN
                    poly_line[-1][MOVE]=MOVE_TRAVEL
                    line_collection_poly.append(list(reversed(poly_line)))

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
            current_state = np.ceil((progress_state[0]+line_count/max_lines)/progress_state[1]*progress_state[2])
            self._report_progress(current_state)
        return line_collection_poly
        
    def hatch_circular(self, hatch_distance, step_size, image_matrix, center, color, hatch_mode, cyl_rad, progress_state):
        line_collection_poly=[]
        # Maximum Radius of one circle defined by the cluster diagonal, plus extra space for one hatch line
        max_rad = np.ceil(
            np.sqrt((image_matrix.shape[0]/2)**2+(image_matrix.shape[1]/2)**2))+np.ceil(hatch_distance)

        # center = self.center_for_hatch
        # center = [(image_matrix.shape[1]-1)/2,
        #           (image_matrix.shape[0]-1)/2]

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
                            line_collection_poly.append(polyline)
                        polyline = []
                    point_outside=False
                    current_pixel_color=np.array([-1,-1,-1])
                else:
                    current_pixel_color=image_matrix[y_round, x_round]

                #check if current pixel is the color we want to hatch
                if current_pixel_color[0]==color[0] and current_pixel_color[1]==color[1] and current_pixel_color[2]==color[2]: #MUCH faster than np.array_equal
                    x1 = (x-center[0])/self.pixel_per_mm
                    y1 = (y-center[1])/self.pixel_per_mm
                    z1 = 0
                    if polyline:
                        polyline.append([x1, y1, z1, 1])
                    else:
                        polyline.append([x1, y1, z1, 0])
                else:
                    if polyline:
                        if len(polyline) > 1:
                            line_collection_poly.append(polyline)
                        polyline = []

                angle += angle_res
            if polyline:  # if we have a last line add it
                if len(polyline) > 1:
                        line_collection_poly.append(polyline)
                polyline = []
            hatch_rad += hatch_distance
            #update progress bar
            current_state = np.ceil((progress_state[0]+hatch_rad/max_rad)/progress_state[1]*progress_state[2])
            self._report_progress(current_state)
        return line_collection_poly
            
    def hatch_spiral(self, hatch_distance, step_size, image_matrix, center, color, hatch_mode, cyl_rad, progress_state):
        line_collection_poly=[]
        # Maximum Radius of one circle defined by the cluster diagonal
        max_rad = np.ceil(
            np.sqrt((image_matrix.shape[0]/2)**2+(image_matrix.shape[1]/2)**2))+np.ceil(hatch_distance)

        # center = self.center_for_hatch
        # center = [(image_matrix.shape[1]-1)/2,
        #           (image_matrix.shape[0]-1)/2]

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
                            line_collection_poly.append(polyline)
                        polyline = []
                    point_outside=False
                    current_pixel_color=np.array([-1,-1,-1])
                else:
                    current_pixel_color=image_matrix[y_round, x_round]

                #check if current pixel is the color we want to hatch        
                if current_pixel_color[0]==color[0] and current_pixel_color[1]==color[1] and current_pixel_color[2]==color[2]: #MUCH faster than np.array_equal
                    x1 = (x-center[0])/self.pixel_per_mm
                    y1 = (y-center[1])/self.pixel_per_mm
                    z1 = 0
                    if polyline:
                        polyline.append([x1, y1, z1, 1])
                    else:
                        polyline.append([x1, y1, z1, 0])

                else:
                    if polyline:
                        if len(polyline) > 1:
                            line_collection_poly.append(polyline)
                        polyline = []
                angle += angle_res
            if polyline:  # if we have a last line add it
                if len(polyline) > 1:
                        line_collection_poly.append(polyline)
                polyline = []
            hatch_rad_avg += hatch_distance
            #update progress bar
            current_state = np.ceil((progress_state[0]+hatch_rad_avg/max_rad)/progress_state[1]*progress_state[2])
            self._report_progress(current_state)
        return line_collection_poly
            
    def hatch_radial(self, hatch_distance, step_size, image_matrix, center, color, hatch_mode, cyl_rad,progress_state):
        line_collection_poly=[]
        hatch_line_dir=1
        # We have to pad the array, since start points of hatchlines might lay outside the image
        # Maximum Radius of one circle defined by the cluster diagonal
        max_rad = np.ceil(
            np.sqrt((image_matrix.shape[0]/2)**2+(image_matrix.shape[1]/2)**2))+np.ceil(hatch_distance)
        
        # center = self.center_for_hatch
        # center = [(image_matrix.shape[1]-1)/2,
        #           (image_matrix.shape[0]-1)/2]

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
            point_outside=False  # B04: must be reset before the cylinder check below may set it
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
                        x1=((x+prev_x)/2-center[0])/self.pixel_per_mm
                        y1=((y+prev_y)/2-center[1])/self.pixel_per_mm
                        z1=0
                        polyline.append([x1, y1, z1, 1])
                        polyline_cache.append(polyline)
                        polyline=[]
                    point_outside=False
                    current_pixel_color=np.array([-1,-1,-1])
                else:
                    current_pixel_color=image_matrix[y_round, x_round]
                
                #check if current pixel is the color we want to hatch
                if current_pixel_color[0]==color[0] and current_pixel_color[1]==color[1] and current_pixel_color[2]==color[2]: #MUCH faster than np.array_equal
                    x1=(x-center[0])/self.pixel_per_mm
                    y1=(y-center[1])/self.pixel_per_mm
                    z1=0
                    if polyline:
                        pass
                        # polyline.append([x1, y1, z1, 1])
                    else:
                        polyline.append([x1, y1, z1, 0])
                else:
                    if polyline:
                        x1=((x+prev_x)/2-center[0])/self.pixel_per_mm
                        y1=((y+prev_y)/2-center[1])/self.pixel_per_mm
                        z1=0
                        polyline.append([x1, y1, z1, 1])
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
                    x1=((x+prev_x)/2-center[0])/self.pixel_per_mm
                    y1=((y+prev_y)/2-center[1])/self.pixel_per_mm
                    z1=0
                    polyline.append([x1, y1, z1, 1])
                    polyline_cache.append(polyline)
                    polyline=[]

            #append polyines here in correct order for meandering
            if hatch_line_dir==1:
                for poly_line in polyline_cache:
                    line_collection_poly.append(poly_line)
            else:
                for poly_line in reversed(polyline_cache):
                    poly_line[0][MOVE]=MOVE_BURN
                    poly_line[-1][MOVE]=MOVE_TRAVEL
                    line_collection_poly.append(list(reversed(poly_line)))

            ray_count+=1
            hatch_line_dir*=-1

            #update progress bar
            current_state = np.ceil((progress_state[0]+ray_count/len(angles))/progress_state[1]*progress_state[2])
            self._report_progress(current_state)
            #print("finished radial ray " + str(ray_count) + " / " + str(len(angles)))
        return line_collection_poly
            
            
    def make_hatch_cylindrical(self, layers, cyl_rad_mm=100):
        """Wrap flat layers around a cylinder of radius cyl_rad_mm (x becomes the arc length)."""
        radius = cyl_rad_mm
        layers_cylindrical = []
        for layer in layers:
            #check if hatching was cancelled
            if self.hatching_cancelled:
                return None

            polylines_cyl = []
            for line in layer.polylines:
                if len(line) == 2:  # a single straight line: subdivide in 100 um steps along x before bending
                    num_nodes = int(np.ceil(max(np.abs(line[0, X] - line[1, X]) * 10, 2)))
                    line = np.column_stack([
                        np.linspace(line[0, X], line[1, X], num_nodes),
                        np.linspace(line[0, Y], line[1, Y], num_nodes),
                        np.zeros(num_nodes),
                        np.where(np.arange(num_nodes) == 0, line[0, MOVE], line[1, MOVE]),
                    ])
                elif len(line) < 2:
                    log.warning("Single hatch point encountered. This should not happen. Skipping it.")
                    continue
                angle = line[:, X] / radius
                polylines_cyl.append(np.column_stack([
                    radius * np.sin(angle), line[:, Y], radius * np.cos(angle) - radius, line[:, MOVE]]))
            layers_cylindrical.append(dataclasses.replace(layer, polylines=polylines_cyl))
        return layers_cylindrical
    
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
        height = self.image_matrix.shape[0]
        center = self.center_for_hatch
        polylines = []
        for contour in self.contours_list:
            if type(contour[0])==int: #single point detected. skip it
                continue
            pixels = np.asarray(contour + contour[:1], dtype=np.float64)  # always close contours
            moves = np.full(len(pixels), MOVE_BURN)
            moves[0] = MOVE_TRAVEL
            polylines.append(np.column_stack([
                (pixels[:, 0] - center[0]) / self.pixel_per_mm,
                ((height - pixels[:, 1] - 1) - center[1]) / self.pixel_per_mm,
                np.zeros(len(pixels)),
                moves,
            ]))
        cluster = HatchCluster([Layer((0, 0, 0), polylines)], self.image_matrix, ref_position=[0,0,0,0], cluster_center_for_hatch=self.center_for_hatch, cylinder_radius=0)
        self.hatch_data = HatchData([cluster], "Contours")
        self.set_handler_data()
    
    def contour_from_dxf(self):
        """
        Reads a DXF file and gathers lines, polylines, circles, arcs, etc.
        Approximates arcs & circles into polylines.
        Then shifts everything so the top-left corner of the bounding box is (0,0).
        Stores the result in self.hatch_data as one Layer of polylines.
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
            if end_angle <= start_angle:  # DXF arcs run counter-clockwise and may cross 0 degrees
                end_angle += 360
            segments = max(2, int(np.ceil((end_angle - start_angle) / 360 * 100)))  # B01: angles are degrees, range() needs int
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
        line_collection = []
        for poly in polylines_shifted:
            line_collection.append([(px, py, 0, MOVE_TRAVEL if i == 0 else MOVE_BURN) for i, (px, py) in enumerate(poly)])

        cluster_data = [_to_layer((0, 0, 0), line_collection)]
        self.hatch_data = HatchData([HatchCluster(cluster_data, None, ref_position=[0,0,0,0], cluster_center_for_hatch=None, cylinder_radius=0)], "DXF_Imported")
        self.set_handler_data()

 

    def set_handler_data(self):
        self.data_handler.hatch_data = self.hatch_data

    def get_handler_data(self):
        self.image_matrix = np.flipud(self.data_handler.image_matrix) #account for the fact that image coordinates are flipped in y direction compared to canvas coordinates
        self.pixel_per_mm = self.data_handler.pixel_per_mm
        self.center_for_hatch = [self.data_handler.center_for_hatch[0], self.data_handler.image_matrix.shape[0] - self.data_handler.center_for_hatch[1]]
        self.contours_list = self.data_handler.contours_list


class HatchingWorker(QThread):
    """Runs the hatching; the result is read in Hatcher._on_worker_done (connected to QThread.finished)."""
    progress = pyqtSignal(int)

    def __init__(self, hatcher, settings: dict):
        super().__init__()
        self.hatcher = hatcher
        self.settings = settings
        self.result = None

    def run(self):
        self.result = self.hatcher.create_hatching_worker(**self.settings)
