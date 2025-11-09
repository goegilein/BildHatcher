import numpy as np
from typing import List
        
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

class HatchCluster:
    def __init__(self, data, input_matrix, ref_position, additional_code=""):
        self.data=data
        self.input_matrix = input_matrix
        self.ref_position=ref_position
        self.additional_code=additional_code

class HatchData:
    def __init__(self, hatch_clusters: List[HatchCluster], type: str):
        self.hatch_clusters = hatch_clusters
        self.type = type
            
class ProcessBlock:
    def __init__(self, hatch_data:HatchData, iterations = 1, post_processing="None", laser_mode="constant",air_assist="off",enclosure_fan=100 , offset = [0,0,0]):
        self.hatch_data = hatch_data
        self.iterations = iterations
        self.post_processing = post_processing
        self.laser_mode = laser_mode
        self.air_assist = air_assist
        self.enclosure_fan = enclosure_fan
        self.offset = offset

class DBColorPalette:
    def __init__(self, color_palette, settings=None):
        self.color_palette = color_palette
        if settings:
            self.post_processing = settings.get('post_processing', 'None')
            self.laser_mode = settings.get('laser_mode', 'constant')
            self.enclosure_fan = settings.get('enclosure_fan', 0)
            self.air_assist = settings.get('air_assist', 'off')
        else:
            self.post_processing = 'None'
            self.laser_mode = 'variable'
            self.enclosure_fan = 100
            self.air_assist = 'off'

    def find_paramset_by_color(self, color):

        if self.color_palette is None:
            raise ValueError("No database values provided for automated hatch distance.")

        min_rgb_diff = 3*255**2  # Maximum possible RGB difference
        bestfit_color = None
        for color_param in self.color_palette:
            param_rgb = np.array([int(x) for x in color_param['color_rgb'].split(',')], dtype=np.int64)
            if np.sum((param_rgb - color)**2) < min_rgb_diff:
                min_rgb_diff = np.sum((param_rgb - color)**2)
                bestfit_color = color_param

        if bestfit_color is None:   
            raise ValueError(f"No hatch distance value found for color {color}.")
        return bestfit_color
    
    def get_color_list(self):
        if self.color_palette is None:
            raise ValueError("No database values provided for automated hatch distance.")
        return [np.array([int(x) for x in color_param['color_rgb'].split(',')], dtype=np.int64) for color_param in self.color_palette]