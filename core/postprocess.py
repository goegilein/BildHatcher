import numpy as np
import copy

from HelperClasses import HatchData, ProcessBlock

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
                data_processed = self.set_drive_mode(data_offset, process_block.post_processing)
            
            hatch_cluster.data = data_processed

        return process_block

    def offset_data(self, data, offset):
        '''Offset the data by the given offset in x, y, and z direction.'''
        
        #return data if no offset is given
        if offset == [0, 0, 0]:
            return data
        
        data_offset = []
        for line_collection in data:
            hatch_lines_new = []
            for polyline in line_collection:
                polyline_new = []
                for point in polyline:
                    point_new = point.clone_with(x=point.pos[0] + offset[0], y=point.pos[1] + offset[1], z=point.pos[2] + offset[2])
                    polyline_new.append(point_new)
                hatch_lines_new.append(polyline_new)
            data_offset.append(hatch_lines_new)
        return data_offset

    def maximize_line_length(self, data):
        # self.get_handler_data()
        data_processed = []
        max_deviation = np.radians(1)
        for hatch_lines in data:
            hatch_lines_new=[]
            for polyline in hatch_lines:
                if len(polyline) < 3:
                    hatch_lines_new.append(polyline)
                    continue
                polyline_new=polyline[0:1]
                deviation_sum = 0  # B10: accumulated bend (pi = straight) since the last kept point
                for i in range(1,len(polyline)-1):
                    cos_angle=self.calculate_3d_angle(polyline[i-1].pos,polyline[i].pos,polyline[i+1].pos)
                    deviation_sum += np.pi - np.acos(cos_angle)
                    if deviation_sum > max_deviation:
                        polyline_new.append(polyline[i])
                        deviation_sum = 0
                polyline_new.append(polyline[-1])
                hatch_lines_new.append(polyline_new)
            data_processed.append(hatch_lines_new)

        return data_processed
    
    def set_drive_mode(self, data, mode):
        # self.get_handler_data()
        data_processed = []
        const_drive_len=1
        over_drive_len=0.2 #just default to this. 
        crit_cos_angle=np.cos(np.radians(170))
        angle_sum=np.pi #here we will track the accumulated polylines angle-difference to 180 degrees.
        for hatch_lines in data:
            if not hatch_lines:
                continue
            hatch_lines_new=[]
            #speed an power in one hatchline array should always be the same
            speed=hatch_lines[0][0].speed
            # const_drive_len=np.maximum(1, speed*0.04) #set constant drive length to 4% of speed/s in mm but at
            const_drive_len=np.maximum(0.1, 1.1*speed**2/(2*3000)) #assuming a constant acceleration/deceleration of 3000 mm/s^2 and using a 10% buffer
            #over_drive_len= (-0.075*speed**2+7.05*speed+37.5)/1000 #from a fit to measured data (10mm/s:100um, 20mm/s:150um, 30mm/s:180um, 40mm/2:200um)
            over_drive_len = 0.24484+(0.10634-0.24484)/(1+(speed/27.3937)**5.82549) #logistics fit to measured data of horz lines (31.01.2025) (10mm/s:110um, 20mm/s:120um, 30mm/s:200um, 40mm/2:220um, 50mm/s:250um, 60mm/s:230um, 70mm/s:240um, 100mm/s:260um)
            for polyline in hatch_lines:
                if len(polyline) < 2:  # B11: nothing to elongate
                    hatch_lines_new.append(polyline)
                    continue
                #always start with a constant drive motion
                A_new, A_pre, B_new, B_post = self.elongate_line(polyline[0].pos, polyline[1].pos, const_drive_len)
                polyline_new = [polyline[0].clone_with(x=A_pre[0], y=A_pre[1], z=A_pre[2],move_type=0, speed = 100), polyline[0]] #these are two G0 commands as first command from Hatcher is ALWAYS G0. we can maximize speed on first G0 command for efficiency
                point_prev = polyline[0]
                for i in range(1,len(polyline)-1):
                    point_now = polyline[i]
                    point_next = polyline[i+1]
                    cos_angle=self.calculate_3d_angle(point_prev.pos,point_now.pos,point_next.pos)
                    angle_sum+=np.acos(cos_angle)%np.pi
                    if np.cos(angle_sum) > np.cos(np.radians(179)) and cos_angle <= crit_cos_angle:
                        polyline_new.append(point_now)
                        angle_sum=np.pi

                    elif cos_angle > crit_cos_angle: # do a constant drive motion here so that decelaration is done in a G0 move
                        if mode == "Constant Drive":
                            A_new, A_pre, B_new1, B_post = self.elongate_line(point_prev.pos, point_now.pos, const_drive_len)
                            B_new2, B_pre, C_new, C_post = self.elongate_line(point_now.pos, point_next.pos, const_drive_len)
                            polyline_new.append(point_now)
                        elif mode == "Over Drive":
                            A_new, A_pre, B_new1, B_post = self.elongate_line(point_prev.pos, point_now.pos, const_drive_len, over_drive_len)
                            B_new2, B_pre, C_new, C_post = self.elongate_line(point_now.pos, point_next.pos, const_drive_len, over_drive_len)
                            polyline_new.append(point_now.clone_with(x=B_new1[0], y=B_new1[1], z=B_new1[2],move_type=1))
                        else:
                            print("Postprocessing Mode not recognized!")
                        polyline_new.append(point_now.clone_with(x=B_post[0], y=B_post[1], z=B_post[2],move_type=0))
                        polyline_new.append(point_now.clone_with(x=B_pre[0], y=B_pre[1], z=B_pre[2],move_type=0))
                        polyline_new.append(point_now.clone_with(move_type=0))
                    point_prev = point_now
                #finally also finish with a constant drive motion
                if mode == "Constant Drive":
                    A_new, A_pre, B_new, B_post = self.elongate_line(polyline[-2].pos, polyline[-1].pos, const_drive_len)
                    polyline_new.append(polyline[-1])
                    polyline_new.append(polyline[-1].clone_with(x=B_post[0], y=B_post[1], z=B_post[2],move_type=0))
                    
                elif mode== "Over Drive":
                    A_new, A_pre, B_new, B_post = self.elongate_line(polyline[-2].pos, polyline[-1].pos, const_drive_len, over_drive_len)
                    polyline_new.append(polyline[-1].clone_with(x=B_new[0], y=B_new[1], z=B_new[2],move_type=1))
                    polyline_new.append(polyline[-1].clone_with(x=B_post[0], y=B_post[1], z=B_post[2],move_type=0))
                hatch_lines_new.append(polyline_new)
            data_processed.append(hatch_lines_new)
        # self.hatch_data_processed = data_processed
        # self.set_handler_data()
        return data_processed


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


def apply_speed_and_power(hatch_data_in: HatchData, white_threshold, power_mode, speed_mode,
                          min_pwr=None, max_pwr=None, min_speed=None, max_speed=None,
                          pwr_struc_num=1, speed_struc_num=1, db_color_palette=None):
    """Return a deep copy of hatch_data with speed and power set on every point.
    power_mode / speed_mode: "constant (max. Val.)", "color-scaled", "test_structure" or "db_based"."""
    #work on a deepcopy of the raw data to avoid pointing issues
    hatch_data = copy.deepcopy(hatch_data_in)

    #data = HatchData(hatch_data, hatch_data.type)
    for hatch_cluster in hatch_data.hatch_clusters:
        for counter, line_collection in enumerate(hatch_cluster.data):
            if not line_collection:  # B09: colour without any hatch lines
                continue

            # Get first point for color of the entire cluster
            first_point = line_collection[0][0]
            color = [first_point.r, first_point.g, first_point.b]

            # Check for white threshold. If the color is too bright, remove the data
            if sum(color)/3>white_threshold:
                hatch_cluster.data[counter]=[] 
                continue


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
