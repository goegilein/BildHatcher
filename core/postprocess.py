import copy
import dataclasses

import numpy as np

from HelperClasses import HatchData, ProcessBlock
from core.toolpath import polyline, MOVE_TRAVEL, MOVE_BURN, MOVE_RAPID
import logging

log = logging.getLogger(__name__)

MAXIMIZE_LINES_TOLERANCE = 0.01  # mm. shortcut: fixed, far below the laser spot size; make it a setting if needed


def simplify_indices(points, tolerance):
    """Ramer-Douglas-Peucker: indices of the points to keep so no removed point is further than tolerance from the line."""
    n = len(points)
    keep = np.zeros(n, dtype=bool)
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        s, e = stack.pop()
        if e - s < 2:
            continue
        a, b = points[s], points[e]
        ab = b - a
        rel = points[s + 1:e] - a
        length = np.linalg.norm(ab)
        dist = np.linalg.norm(np.cross(rel, ab), axis=1) / length if length > 0 else np.linalg.norm(rel, axis=1)
        i = int(np.argmax(dist))
        if dist[i] > tolerance:
            keep[s + 1 + i] = True
            stack.append((s, s + 1 + i))
            stack.append((s + 1 + i, e))
    return np.flatnonzero(keep)


class PostProcessor:
    def __init__(self):
        pass

    def process_block(self,process_block:ProcessBlock):
        for hatch_cluster in process_block.hatch_data.hatch_clusters:
            data = hatch_cluster.data
            data_offset = self.offset_data(data, process_block.offset)

            if process_block.post_processing == "None":
                data_processed = data_offset
            elif process_block.post_processing == "Maximize Lines":
                data_processed = self.maximize_line_length(data_offset)
            elif process_block.post_processing == "Constant Drive" or process_block.post_processing == "Over Drive":
                machine = process_block.machine
                data_processed = self.set_drive_mode(data_offset, process_block.post_processing,
                                                     machine.acceleration, machine.over_drive_fit)
            
            hatch_cluster.data = data_processed

        return process_block

    def offset_data(self, data, offset):
        '''Offset the data by the given offset in x, y, and z direction.'''
        
        #return data if no offset is given
        if offset == [0, 0, 0]:
            return data
        
        shift = np.array([offset[0], offset[1], offset[2], 0.0])
        return [dataclasses.replace(layer, polylines=[line + shift for line in layer.polylines]) for layer in data]

    def maximize_line_length(self, data, tolerance=MAXIMIZE_LINES_TOLERANCE):
        """Remove polyline points that deviate less than `tolerance` (mm) from a straight line (Ramer-Douglas-Peucker)."""
        return [dataclasses.replace(layer, polylines=[line[simplify_indices(line[:, :3], tolerance)] for line in layer.polylines])
                for layer in data]
    
    def set_drive_mode(self, data, mode, acceleration=3000, over_drive_fit=(0.24484, 0.10634, 27.3937, 5.82549)):
        """Constant Drive: accelerate/decelerate outside the burn (lead-in/lead-out travel moves of const_drive_len).
        Over Drive: additionally extend each burn by the measured over-drive length.
        Corners sharper than 10 degrees get a lead-out/lead-in as well; exactly collinear points are dropped."""
        if mode not in ("Constant Drive", "Over Drive"):
            raise ValueError(f"Postprocessing mode {mode!r} not recognized")
        over = mode == "Over Drive"
        crit_cos_angle = np.cos(np.radians(170))
        data_processed = []
        for layer in data:
            if not layer.polylines:
                continue
            speed = layer.speed
            # constant acceleration/deceleration of `acceleration` mm/s^2 plus a 10 % buffer
            const_drive_len = np.maximum(0.1, 1.1 * speed**2 / (2 * acceleration))
            # logistic fit to measured over-drive of horizontal lines (31.01.2025): 10 mm/s: 110 um ... 100 mm/s: 260 um
            a, b, c, n = over_drive_fit
            over_drive_len = a + (b - a) / (1 + (speed / c)**n) if over else 0
            hatch_lines_new = []
            for line in layer.polylines:
                if len(line) < 2:  # B11: nothing to elongate
                    hatch_lines_new.append(line)
                    continue
                pos = line[:, :3]
                _, A_pre, _, _ = self.elongate_line(pos[0], pos[1], const_drive_len)
                # first command from the hatcher is ALWAYS a travel move: approach the lead-in point at rapid speed
                parts = [polyline([(*A_pre, MOVE_RAPID)]), line[:1]]

                interior = np.arange(1, len(line) - 1)
                cos_angle = self.vertex_cosines(pos)
                corner = cos_angle > crit_cos_angle
                collinear = cos_angle <= -1 + 1e-12
                last = 0
                for i in interior[corner]:  # usually none: straight runs are copied as array slices
                    run = np.arange(last + 1, i)
                    parts.append(line[run[~collinear[run - 1]]])
                    # lead-out/lead-in around the corner so that deceleration happens in travel moves
                    _, _, B_new1, B_post = self.elongate_line(pos[i - 1], pos[i], const_drive_len, over_drive_len)
                    _, B_pre, _, _ = self.elongate_line(pos[i], pos[i + 1], const_drive_len, over_drive_len)
                    parts.append(polyline([(*B_new1, MOVE_BURN) if over else line[i],
                                           (*B_post, MOVE_TRAVEL), (*B_pre, MOVE_TRAVEL), (*pos[i], MOVE_TRAVEL)]))
                    last = i
                run = np.arange(last + 1, len(line) - 1)
                parts.append(line[run[~collinear[run - 1]]])

                #finally also finish with a constant drive motion
                _, _, B_new, B_post = self.elongate_line(pos[-2], pos[-1], const_drive_len, over_drive_len)
                parts.append(polyline([(*B_new, MOVE_BURN) if over else line[-1], (*B_post, MOVE_TRAVEL)]))
                hatch_lines_new.append(np.concatenate(parts))
            data_processed.append(dataclasses.replace(layer, polylines=hatch_lines_new))
        return data_processed

    @staticmethod
    def vertex_cosines(pos):
        """cos of the angle at every interior vertex (-1 = straight); duplicate points count as straight (B11)."""
        BA, BC = pos[:-2] - pos[1:-1], pos[2:] - pos[1:-1]
        norm = np.linalg.norm(BA, axis=1) * np.linalg.norm(BC, axis=1)
        with np.errstate(invalid="ignore", divide="ignore"):
            cos = np.where(norm > 0, np.einsum("ij,ij->i", BA, BC) / norm, -1.0)
        return np.clip(cos, -1.0, 1.0)


    def calculate_3d_angle(self, A, B, C):
        """
        Calculate the 3D angle between three points A, B, and C, where B is the vertex.

        Args:
            A (np.ndarray): Coordinates of point A [x, y, z].
            B (np.ndarray): Coordinates of point B [x, y, z].
            C (np.ndarray): Coordinates of point C [x, y, z].

        Returns:
            float: The angle in degrees between the vectors BA and BC.
        """
        # # Convert points to numpy arrays
        # A = np.array(A)
        # B = np.array(B)
        # C = np.array(C)

        # Calculate vectors BA and BC
        BA = A - B
        BC = C - B

        # Calculate the dot product and magnitudes of the vectors
        dot_product = np.dot(BA, BC)
        magnitude_BA = np.linalg.norm(BA)
        magnitude_BC = np.linalg.norm(BC)
        if magnitude_BA == 0 or magnitude_BC == 0:  # B11: duplicate point -> treat as straight
            return -1.0

        # Calculate the cosine of the angle
        cos_angle = dot_product / (magnitude_BA * magnitude_BC)

        # Ensure the cosine value is within the valid range [-1, 1]
        cos_angle = np.clip(cos_angle, -1.0, 1.0)

        # Calculate the angle in radians and then convert to degrees
        # angle_radians = np.arccos(cos_angle)
        # angle_degrees = np.degrees(angle_radians)

        return cos_angle
    
    def elongate_line(self, A, B, const_drive_len, over_drive_len=0):
        """
        Elongate a line defined by points A and B in 3D space by const+over drive length in both directions and return 2 additional nodes.
        over_drive_len shits the input points. const_drive_len creates new points based on shifted points

        Parameters:
        A (np.ndarray): The start point of the line [x, y, z].
        B (np.ndarray): The end point of the line [x, y, z].
        over_drive_len: length by which the old points will be shifted in both directions for laser on moves
        const_drive_len (float): The length by which to elongate the line in both directions for laser off moves.


        Returns:
        A_pre (np.ndarray): The new start point of the elongated line for the laser off move.
        A_new (np.ndarray): The new Point A which can be used for a laser on move
        B_post (np.ndarray): The new end point of the elongated line for the laser off move.
        B_mew (np.ndarray): The new Point B whcih can be used for a lser on move
        """
        # # Convert points to numpy arrays for vector operations
        # A = np.array(A)
        # B = np.array(B)

        # Calculate the direction vector from A to B
        direction_vector = B - A
        length = np.linalg.norm(direction_vector)
        if length == 0:  # B11: zero-length segment has no direction -> no elongation
            return A, A, B, B

        # Normalize the direction vector to get the unit vector
        unit_vector = direction_vector / length

        # Calculate the elongation vectors for both const and over drive
        elong_v_const_drive = unit_vector * const_drive_len
        elong_v_over_drive = unit_vector * over_drive_len


        # Calculate the new points A_pre and B_post
        
        A_new = A - elong_v_over_drive
        B_new = B + elong_v_over_drive
        A_pre = A_new - elong_v_const_drive
        B_post = B_new + elong_v_const_drive

        return A_new, A_pre, B_new, B_post


def apply_speed_and_power(hatch_data_in: HatchData, power_mode, speed_mode,
                          min_pwr=None, max_pwr=None, min_speed=None, max_speed=None,
                          pwr_struc_num=1, speed_struc_num=1, db_color_palette=None):
    """Return a deep copy of hatch_data with speed and power set on every layer.
    power_mode / speed_mode: "constant (max. Val.)", "color-scaled", "test_structure" or "db_based"."""
    #work on a deepcopy of the raw data to avoid pointing issues
    hatch_data = copy.deepcopy(hatch_data_in)

    #data = HatchData(hatch_data, hatch_data.type)
    for hatch_cluster in hatch_data.hatch_clusters:
        for counter, layer in enumerate(hatch_cluster.data):
            if not layer.polylines:  # B09: colour without any hatch lines
                continue
            color = list(layer.color)


            #power settings
            if power_mode=="constant (max. Val.)":
                pwr = max_pwr
            elif power_mode=="color-scaled":
                pwr=int(max_pwr-(max_pwr-min_pwr)*sum(color)/765)
            elif power_mode=="test_structure":
                if pwr_struc_num>1:
                    pwr=int(min_pwr+(max_pwr-min_pwr)*np.floor(counter/speed_struc_num)/(pwr_struc_num-1))
                else:
                    pwr=max_pwr
            elif power_mode=="db_based":
                bestfit_color = db_color_palette.find_paramset_by_color(color)
                pwr = bestfit_color['laser_power']
            else:
                log.error("error: PowerMode not recognized")
            #speed/feedrate settings
            if speed_mode=="constant (max. Val.)":
                speed = max_speed
            elif speed_mode=="color-scaled":
                speed=int(min_speed+(max_speed-min_speed)*sum(color)/765)
            elif speed_mode=="test_structure":
                if speed_struc_num>1:
                    speed=int((min_speed+(max_speed-min_speed)*(counter%speed_struc_num/(speed_struc_num-1))))
                else:    
                    speed=max_speed
            elif speed_mode=="db_based":
                bestfit_color = db_color_palette.find_paramset_by_color(color)
                speed = bestfit_color['speed']
            else:
                log.error("error: SpeedMode not recognized")
            layer.speed = speed
            layer.power = pwr

    return hatch_data
