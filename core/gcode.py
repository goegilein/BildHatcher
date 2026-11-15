"""G-code / txt generation for process blocks. Pure functions, no Qt.

shortcut: header/footer/commands are Snapmaker Artisan specific, machine profiles come with P5.1.
"""
import datetime

from HelperClasses import ProcessBlock
from core.toolpath import MOVE_BURN, MOVE_RAPID, RAPID_SPEED

FEEDRATE_DEFAULT = 6000


def generate_gcode_header():
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
    gcode_commands.append("M2000 W1 P100 ; Artisan Setting to turn on Enclosure lights 100%")
    gcode_commands.append(f"G0 F{FEEDRATE_DEFAULT} ; set default feedrate for laser off moves")
    gcode_commands.append(f"G1 F{FEEDRATE_DEFAULT} ; set default feedrate for laser on moves")
    gcode_commands.append("")

    return gcode_commands


def generate_gcode_footer():
    gcode_commands=[]
    gcode_commands.append("; Footer")
    gcode_commands.append("M5 ; Turn off laser")
    gcode_commands.append("M9 ; Turn off Air assist")
    gcode_commands.append("M2000 W2 P0 ; Artisan Setting to turn off Enclosure fan (0%)")
    gcode_commands.append("M2000 L23 P1 ; Artisan 40W laser. 1 exits half power Moade")
    gcode_commands.append("; End of G-code")

    return gcode_commands


def generate_gcode(process_block:ProcessBlock=None, cluster_index=None):
    gcode_commands = []
    if process_block is None:
        print("Error: No ProcessBlock provided for G-code generation")
        return gcode_commands

    hatch_cluster_data = process_block.hatch_data.hatch_clusters[cluster_index].data #self.post_processor.process_data(process_block)

    gcode_commands.append("")
    gcode_commands.append("===;start of new Processblock===")

    #process block header
    gcode_commands.append(f"; Post Processing: {process_block.post_processing} | Laser Mode: {process_block.laser_mode} | Air Assist: {process_block.air_assist} | Power Mode: {process_block.power_mode} | Enclosure Fan: {process_block.enclosure_fan}%")
    gcode_commands.append(f"; Offset: X={process_block.offset[0]} Y={process_block.offset[1]} Z={process_block.offset[2]}")
    gcode_commands.append(f"; Number of color clusters: {len(hatch_cluster_data)}")
    gcode_commands.append(f"; Number of points: {sum(layer.point_count for layer in hatch_cluster_data)}")
    gcode_commands.append("")

    #set laser mode
    if process_block.laser_mode == "variable":
        gcode_commands.append("M4 P0 ; set Laser to variable Mode")
    elif process_block.laser_mode == "constant":
        gcode_commands.append("M3 P0 ; set laser to constant Mode")
    else:
        print("Error: Laser Mode not recognized")

    #set power mode
    if process_block.power_mode == "half":
        gcode_commands.append("M2000 L23 P0 ; Artisan 40W laser. 0 enters half power Mode (20W max)")
    elif process_block.power_mode == "full":
        gcode_commands.append("M2000 L23 P1 ; Artisan 40W laser. 1 exits half power Mode (40W max)")
    else:
        print("Error: Power Mode not recognized")

    #set enclosure fan and air assist
    gcode_commands.append(f"M2000 W2 P{process_block.enclosure_fan} ; Artisan Enclosure fan to {process_block.enclosure_fan}%")
    if process_block.air_assist == "on":
        gcode_commands.append("M8 ; Turn on Air assis")
        gcode_commands.append("G4 S1.0 ; Wait for 1.0 seconds to allow air assist to stabilize")
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

    for layer in hatch_cluster_data:
        pwr_P = layer.power
        pwr_S = pwr_P/100*255 if pwr_P is not None else None #pwr_S is in 8bit format (0-255)
        for line in layer.polylines:
            for x, y, z, move_type in line:
                speed = RAPID_SPEED if move_type == MOVE_RAPID else layer.speed
                feed = speed*60 #feed is in mm/min while speed is in mm/s



                if move_type != MOVE_BURN:
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


def generate_txt_code(process_block):
    txt_commands=[]
    for hatch_cluster in process_block.hatch_data.hatch_clusters:  # B06: was process_block.data
        for line in (p for layer in hatch_cluster.data for p in layer.polylines):
            for x, y, z, move in line:
                txt_commands.append(f"{x:.3f} {y:.3f} {z:.3f} {int(move != MOVE_BURN)}")
    return "\n".join(txt_commands)
