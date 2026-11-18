from PyQt6 import QtWidgets
from PyQt6.QtWidgets import QFileDialog, QProgressDialog 
from PyQt6.QtCore import QObject, QThread, QEventLoop, pyqtSignal
import logging
import numpy as np
from collections import defaultdict
import random
import dataclasses
from HelperClasses import HatchData, HatchCluster
from core import hatching
from core.toolpath import Layer, polyline, X, Y, MOVE, MOVE_TRAVEL, MOVE_BURN
import ezdxf
from ezdxf import path as dxf_path

log = logging.getLogger(__name__)


DXF_TOLERANCE = 0.01  # mm, max. deviation of the flattened curves


def dxf_polylines(modelspace, tolerance=DXF_TOLERANCE):
    """2-D vertex arrays of all path-like entities of a DXF modelspace (closed shapes end at their start point)."""
    polylines = []
    for entity in modelspace:
        try:
            p = dxf_path.make_path(entity)
        except (TypeError, ValueError):
            continue  # entity type without a path representation
        for sub in p.sub_paths():
            vertices = np.array([(v.x, v.y) for v in sub.flattening(tolerance)])
            if len(vertices) >= 2:
                polylines.append(vertices)
    return polylines


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

        # P4.4: random seed for RandomMeander / Circular (0 = new random pattern every time; widget in the .ui, P10)
        self.random_seed_spinbox = gui.random_seed_spinbox

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
            z_dist = self.data_handler.machine_profile.cylinder_laser_distance  # mm the surface may leave the focus
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
            random_seed=self.random_seed_spinbox.value(),
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
        self.hatch_progress_label.setText("Hatching...")

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
                               hatch_mode=None, stepsize_mm=None, random_seed=0):
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
                #first get the colors of the cluster (as label image, transparent = -1)
                labels, color_list = hatching.label_colors(hatch_cluster.input_matrix)
                hatch_cluster.data = self.hatch_cluster(
                    labels = labels,
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
                    db_color_palette=db_color_palette,
                    cluster_progress = cluster_progress,
                    rng = random.Random(random_seed) if random_seed else random
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
            self.hatch_progress_label.setText("Finished")

    def _on_worker_done(self):
        self._worker_done = True
        self.progress_dialog.canceled.disconnect(self.cancel_hatching)  # close() emits canceled
        self.progress_dialog.close()
        if not self.hatching_cancelled:
            self.hatching_finished(self.worker.result)
            if self.worker.result is None:
                self.hatch_progress_label.setText("Failed")
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
        self.hatch_progress_label.setText("Cancelled")

    def hatch_cluster(self, labels, cluster_center_for_hatch, mode="manual", color_list=None, hatch_pattern="RandomMeander", hatch_angle=90, hatch_dist_mode="ColorRanged", hatch_dist_min=300, hatch_dist_max=700, cyl_rad_mm = 100, hatch_mode = "Flat", stepsize_mm = 0.1, db_color_palette=None, cluster_progress=0, rng=random):
        """Hatch every colour of one cluster. labels: label image from hatching.label_colors, color_list: its colours."""
        hatched_cluster = []
        cyl_rad = cyl_rad_mm * self.pixel_per_mm
        center = cluster_center_for_hatch
        step_size = stepsize_mm * self.pixel_per_mm  # Step size in pixels

        for color_index, color in enumerate(color_list):
            #check if hatching was cancelled
            if self.hatching_cancelled:
                return None

            #if mode is automatic, get hatch settings from best fit color of database color palette
            if mode == "automatic":
                bestfit_color = db_color_palette.find_paramset_by_color(np.array(color, dtype=np.int64))
                hatch_distance = bestfit_color['hatch_distance']/1000
                hatch_pattern = bestfit_color['hatch_pattern']
                hatch_angle = bestfit_color['hatch_angle']
            elif hatch_dist_mode == "ColorRanged":
                hatch_distance = (hatch_dist_min + sum(color) / 765 * (hatch_dist_max - hatch_dist_min))/1000
            elif hatch_dist_mode == "Fixed":
                hatch_distance = hatch_dist_min/1000
            else:
                log.warning("Hatch distance mode %r not recognized", hatch_dist_mode)
                continue
            hatch_distance = hatch_distance * self.pixel_per_mm  # Hatch distance in pixels

            def progress(fraction, done=color_index):
                self._report_progress(np.ceil((done + fraction) / len(color_list) * cluster_progress))
                return self.hatching_cancelled

            args = (labels, color_index, center, self.pixel_per_mm)
            kwargs = dict(hatch_mode=hatch_mode, cyl_rad=cyl_rad, progress=progress)
            if hatch_pattern == "FixedMeander":
                line_collections = [hatching.meander(*args, hatch_angle, hatch_distance, step_size, **kwargs)]
            elif hatch_pattern == "RandomMeander":
                theta = np.floor(rng.uniform(0, 180))  # one random angle per colour
                line_collections = [hatching.meander(*args, theta, hatch_distance, step_size, **kwargs)]
            elif hatch_pattern == "CrossedMeander":
                line_collections = [hatching.meander(*args, hatch_angle + cross, hatch_distance, step_size, **kwargs) for cross in (0, 90)]
            elif hatch_pattern == "Circular":
                line_collections = [hatching.circular(*args, hatch_distance, step_size, rng=rng, **kwargs)]
            elif hatch_pattern == "Spiral":
                line_collections = [hatching.spiral(*args, hatch_distance, step_size, **kwargs)]
            elif hatch_pattern == "Radial":
                line_collections = [hatching.radial(*args, hatch_distance, step_size, **kwargs)]
            else:
                log.warning("Unknown hatch pattern %r", hatch_pattern)
                continue
            if any(lines is None for lines in line_collections):  # cancelled
                return None
            hatched_cluster.extend(_to_layer(color, lines) for lines in line_collections)

            # Update progress bar
            self._report_progress(np.ceil((color_index + 1) / len(color_list) * cluster_progress))
        return hatched_cluster

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
            log.error("Error: contour source not supported.")
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
        """Import the outlines of a DXF file as one layer of polylines, shifted so the lower left corner is (0, 0).
        P6.8: every entity ezdxf can turn into a path (lines, (LW)polylines incl. bulges, circles, arcs, ellipses,
        splines, ...) is flattened with DXF_TOLERANCE; other entities (text, blocks, ...) are skipped."""
        file_path, _ = QFileDialog.getOpenFileName(self.gui, "Import DXF", "", "DXF Files (*.dxf);;All Files (*)")
        if not file_path:
            return
        polylines = dxf_polylines(ezdxf.readfile(file_path).modelspace())
        if not polylines:
            QtWidgets.QMessageBox.warning(self.gui, "Import DXF", "No supported geometry found in the DXF file.")
            return
        offset = np.min(np.concatenate(polylines), axis=0)
        line_collection = [[(px, py, 0, MOVE_TRAVEL if i == 0 else MOVE_BURN) for i, (px, py) in enumerate(poly - offset)]
                           for poly in polylines]
        cluster_data = [_to_layer((0, 0, 0), line_collection)]
        self.hatch_data = HatchData([HatchCluster(cluster_data, None, ref_position=[0,0,0,0], cluster_center_for_hatch=None, cylinder_radius=0)], "DXF_Imported")
        self.set_handler_data()

 

    def set_handler_data(self):
        self.data_handler.hatch_data = self.hatch_data

    def get_handler_data(self):
        rgba = np.flipud(self.data_handler.image_matrix) #account for the fact that image coordinates are flipped in y direction compared to canvas coordinates
        # int16 RGB with -1 for transparent pixels: matches no colour, so the background is never hatched
        self.image_matrix = rgba[..., :3].astype(np.int16)
        self.image_matrix[rgba[..., 3] == 0] = -1
        self.pixel_per_mm = self.data_handler.pixel_per_mm
        # B28: rows are flipped as r -> H-1-r (flipud above), the center must use the same mapping (was H-r: 1 px y offset)
        self.center_for_hatch = [self.data_handler.center_for_hatch[0], self.data_handler.image_matrix.shape[0] - 1 - self.data_handler.center_for_hatch[1]]
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
