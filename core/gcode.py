"""G-code / txt generation for process blocks. Pure functions, no Qt.
All machine specific commands come from the block's MachineProfile (core/machine.py).
"""
import datetime

from HelperClasses import ProcessBlock
from core.toolpath import MOVE_BURN, MOVE_RAPID
import logging

log = logging.getLogger(__name__)


def generate_gcode_header(machine):
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
    gcode_commands.extend(line.format(feedrate=machine.feedrate) for line in machine.header)
    gcode_commands.append("")

    return gcode_commands


def generate_gcode_footer(machine):
    gcode_commands=[]
    gcode_commands.append("; Footer")
    gcode_commands.extend(machine.footer)
    gcode_commands.append("; End of G-code")

    return gcode_commands


def generate_gcode(process_block:ProcessBlock=None, cluster_index=None):
    gcode_commands = []
    if process_block is None:
        log.error("Error: No ProcessBlock provided for G-code generation")
        return gcode_commands

    hatch_cluster_data = process_block.hatch_data.hatch_clusters[cluster_index].data
    machine = process_block.machine

    gcode_commands.append("")
    gcode_commands.append("===;start of new Processblock===")

    #process block header
    gcode_commands.append(f"; Post Processing: {process_block.post_processing} | Laser Mode: {process_block.laser_mode} | Air Assist: {process_block.air_assist} | Power Mode: {process_block.power_mode} | Enclosure Fan: {process_block.enclosure_fan}%")
    gcode_commands.append(f"; Offset: X={process_block.offset[0]} Y={process_block.offset[1]} Z={process_block.offset[2]}")
    gcode_commands.append(f"; Number of color clusters: {len(hatch_cluster_data)}")
    gcode_commands.append(f"; Number of points: {sum(layer.point_count for layer in hatch_cluster_data)}")
    gcode_commands.append("")

    #laser mode, power mode, enclosure fan, air assist
    gcode_commands.extend(machine.option_lines("laser_modes", process_block.laser_mode))
    gcode_commands.extend(machine.option_lines("power_modes", process_block.power_mode))
    gcode_commands.extend(line.format(fan=process_block.enclosure_fan) for line in machine.enclosure_fan)
    gcode_commands.extend(machine.option_lines("air_assist", process_block.air_assist))

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
                speed = machine.rapid_speed if move_type == MOVE_RAPID else layer.speed
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
                    if pwr_S != pwr_prev or prev_gcode_command=="G0": gcode_command += machine.burn_power.format(power=pwr_P, s=pwr_S)
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
