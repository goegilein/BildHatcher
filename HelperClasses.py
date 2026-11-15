import numpy as np
from typing import List
        
class HatchCluster:
    """One hatch cluster: `data` is a list of core.toolpath.Layer (one per colour)."""
    def __init__(self, data: list, input_matrix: np.ndarray, ref_position: np.ndarray, cluster_center_for_hatch: np.ndarray, cylinder_radius: float, additional_code: str = ""):
        self.data=data
        self.input_matrix = input_matrix
        self.ref_position=ref_position
        self.cluster_center_for_hatch = cluster_center_for_hatch
        self.cylinder_radius = cylinder_radius
        self.additional_code=additional_code

# class ClusterMetaData:
#     def __init__(self, hatch_pattern: str = None, hatch_distance_mode: str = None, hatch_distance: list = None, hatch_angle: float = None, hatch_mode: str = None, hatch_precision: float = None, hatch_cylinder_radius: float = None):
#         self.hatch_pattern = hatch_pattern
#         self.hatch_distance_mode = hatch_distance_mode
#         self.hatch_distance = hatch_distance
#         self.hatch_angle = hatch_angle
#         self.hatch_mode = hatch_mode
#         self.hatch_precision = hatch_precision
#         self.hatch_cylinder_radius = hatch_cylinder_radius

class HatchData:
    def __init__(self, hatch_clusters: List[HatchCluster], type: str):
        self.hatch_clusters = hatch_clusters
        self.type = type

            
class ProcessBlock:
    def __init__(self, hatch_data:HatchData, iterations = 1, post_processing="None", laser_mode="constant",air_assist="off",enclosure_fan=100, power_mode="half" , offset = [0,0,0]):
        self.hatch_data = hatch_data
        self.iterations = iterations
        self.post_processing = post_processing
        self.laser_mode = laser_mode
        self.air_assist = air_assist
        self.enclosure_fan = enclosure_fan
        self.power_mode = power_mode
        self.offset = offset

class DBColorPalette:
    def __init__(self, color_palette, settings=None):
        self.color_palette = color_palette
        if settings:
            self.post_processing = settings.get('post_processing', 'None')
            self.laser_mode = settings.get('laser_mode', 'constant')
            self.enclosure_fan = settings.get('enclosure_fan', 0)
            self.air_assist = settings.get('air_assist', 'off')
            self.power_mode = settings.get('power_mode', 'half')
        else:
            self.post_processing = 'None'
            self.laser_mode = 'constant'
            self.enclosure_fan = 100
            self.air_assist = 'off'
            self.power_mode = 'half'

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
    
class ObservableList(list):
    """
    A list subclass that notifies observers whenever the list is modified.
    Supports append, extend, insert, remove, pop, clear, and item assignment.
    """
    def __init__(self, *args, on_change=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.on_change = on_change

    def append(self, item):
        super().append(item)
        if self.on_change:
            self.on_change()

    def extend(self, iterable):
        super().extend(iterable)
        if self.on_change:
            self.on_change()

    def insert(self, index, item):
        super().insert(index, item)
        if self.on_change:
            self.on_change()

    def remove(self, item):
        super().remove(item)
        if self.on_change:
            self.on_change()

    def pop(self, index=-1):
        result = super().pop(index)
        if self.on_change:
            self.on_change()
        return result

    def clear(self):
        super().clear()
        if self.on_change:
            self.on_change()

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        if self.on_change:
            self.on_change()

    def __delitem__(self, key):
        super().__delitem__(key)
        if self.on_change:
            self.on_change()

    def __iadd__(self, other):
        result = super().__iadd__(other)
        if self.on_change:
            self.on_change()
        return result

    def __imul__(self, other):
        result = super().__imul__(other)
        if self.on_change:
            self.on_change()
        return result

    def sort(self, *args, **kwargs):
        super().sort(*args, **kwargs)
        if self.on_change:
            self.on_change()

    def reverse(self):
        super().reverse()
        if self.on_change:
            self.on_change()