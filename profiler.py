import cProfile
import pstats
import io
import tkinter as tk
from tkinter import filedialog
import numpy as np
from PIL import Image
from NCDataGeneration import ImageHatcher  # Adjust the import based on your actual module and class names
import DataHandling

def setup_simulated_inputs(image_hatcher):
    # Simulate the necessary inputs and interactions
    # Example: Set attributes or call methods to provide the required inputs
    image_hatcher.hatch_pattern_vart = tk.StringVar(
            value="FixedMeander")
    image_hatcher.angle_var = tk.DoubleVar(value=45.0)
    image_hatcher.hatch_pattern_var = tk.StringVar(
            value="FixedMeander")
    # Add more setup as needed

def profile_hatch_meander():
    # Create an instance of the ImageHatcher class
    root = tk.Tk()
    image_canvas = tk.Canvas(root, width=400, height=400)  # Set fixed size
    export_frame = tk.LabelFrame(image_canvas, text="Build nc data")
    data_handler = DataHandling.DataHandler(image_canvas,export_frame)
    image_hatcher = ImageHatcher(root,data_handler,export_frame)

    # Set up the simulated inputs
    setup_simulated_inputs(image_hatcher)

    # Profile the hatch_meander method
    pr = cProfile.Profile()
    pr.enable()

    file_path = filedialog.askopenfilename()
    image_original = Image.open(file_path)
    image = Image.open(file_path)
    image_matrix = np.array(image)

    # Call the method you want to profile
    image_hatcher.hatch_meander(hatch_distance=0.00378,
                                step_size=0.378,
                                image_matrix=image_matrix,
                                pixel_per_mm=3.78,
                                color = np.array([0,5,1]),
                                hatch_mode="Flat",
                                cyl_rad=377.8,
                                progress_state=[1, 1],
                                cross_angle=90)
    
    pr.disable()
    
    # Create a string stream to capture the profiling results
    s = io.StringIO()
    sortby = 'cumulative'
    ps = pstats.Stats(pr, stream=s).sort_stats(sortby)
    ps.print_stats()
    
    # Print the profiling results
    print(s.getvalue())

if __name__ == "__main__":
    profile_hatch_meander()