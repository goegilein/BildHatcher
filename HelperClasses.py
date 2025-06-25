import numpy as np
 
class ImgObj:
    def __init__(self, image_matrix, image_matrix_adjusted, image_matrix_original, pixel_per_mm, pixel_per_mm_original, image_scaling):
        self.image_matrix = image_matrix
        self.image_matrix_adjusted = image_matrix_adjusted
        self.image_matrix_original = image_matrix_original
        self.pixel_per_mm = pixel_per_mm
        self.pixel_per_mm_original = pixel_per_mm_original
        self.image_scaling = image_scaling
        
class Point:
    def __init__(self,x,y,z,move_type,r,g,b,speed=None,pwr=None):
        self._x = x
        self._y = y
        self._z = z
        self.move_type = move_type
        self.r=r
        self.g=g
        self.b=b
        self.speed = speed
        self.pwr = pwr
        self._pos = np.array([x,y,z])
    
    @property
    def pos(self):
        return self._pos
    
    @pos.setter
    def pos(self, new_value:np.ndarray) -> None:
        assert new_value.shape == (1, 3), f"Expected shape (1,3), got {new_value.shape}"
        self._pos = new_value
        self.x=new_value[0]
        self.y=new_value[1]
        self.z=new_value[2]

    @property
    def x(self):
        return self._x
    
    @x.setter
    def x(self, new_value):
        self._x = new_value
        self._pos = np.array([self._x, self._y, self._z])

    @property
    def y(self):
        return self._y
    
    @y.setter
    def y(self, new_value):
        self._y = new_value
        self._pos = np.array([self._x, self._y, self._z])

    @property
    def z(self):
        return self._z
    
    @z.setter
    def z(self, new_value):
        self._z = new_value
        self._pos = np.array([self._x, self._y, self._z])

    def copy_metadata(self):
        return self.move_type, self.r, self.g, self.b, self.speed, self.pwr
    
    def clone_with(self, x=None, y=None, z=None, move_type=None, speed=None, pwr=None):
        if x is None:
            x = self.x
        if y is None:
            y = self.y
        if z is None:
            z = self.z
        if move_type is None:
            move_type = self.move_type
        if speed is None:
            speed = self.speed
        if pwr is None:
            pwr = self.pwr

        return Point(
            x,
            y,
            z,
            move_type=move_type,
            r=self.r,
            g=self.g,
            b=self.b,
            speed=self.speed,
            pwr=self.pwr
        )
    
class ImgObj:
    def __init__(self, image_matrix, image_matrix_adjusted, image_matrix_original, pixel_per_mm, pixel_per_mm_original, image_scaling):
        self.image_matrix = image_matrix
        self.image_matrix_adjusted = image_matrix_adjusted
        self.image_matrix_original = image_matrix_original
        self.pixel_per_mm = pixel_per_mm
        self.pixel_per_mm_original = pixel_per_mm_original
        self.image_scaling = image_scaling
        self.mask_matrix = None

class HatchData:
    def __init__(self, data, type):
        self.data = data
        self.type = type

class HatchCluster:
    def __init__(self, hatch_lines, hatch_pattern, hatch_angle, hatch_distance, h_dist_min_max, hatch_mode, cyl_rad, hatch_precision):
        self.hatch_lines = hatch_lines
        self.hatch_pattern = hatch_pattern
        self.hatch_angle = hatch_angle
        self.hatch_distance = hatch_distance
        self.h_dist_min_max = h_dist_min_max
        self.hatch_mode = hatch_mode
        self.cyl_rad = cyl_rad
        self.hatch_precistion = hatch_precision
            
class ProcessBlock:
    def __init__(self, data, post_processing, laser_mode="constant",air_assit="on",enclosure_fan="on", offset = [0,0,0]):
        self.data = data
        self.post_processing = post_processing
        self.laser_mode = laser_mode
        self.air_assit = air_assit
        self.enclosure_fan = enclosure_fan
        self.offset = offset
        