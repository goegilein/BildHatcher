import numpy as np
from HelperClasses import Point, HatchData

class Teststructures:
    def __init__(self, data_handler, gui):
        self.data_handler = data_handler
        self.gui = gui
        self.hatch_data = HatchData([], "")

        # Initialize GUI elements from the preloaded PyQt6 GUI
        self.test_structure_combobox = gui.test_structure_combobox
        self.create_test_button = gui.create_test_button
        self.structnum_pwr_spinbox = gui.structnum_pwr_spinbox
        self.structnum_speed_spinbox = gui.structnum_speed_spinbox
        self.struct_size_spinbox = gui.struct_size_spinbox
        self.struct_hDist_spinbox = gui.struct_hDist_spinbox

        # Initialize combobox values
        self.test_structure_combobox.addItems([
            "Simple Square Contour",
            "Polyline Square Contour",
            "Filled Squares Vert.",
            "Filled Squares Horz.",
            "Vert. Subfield Structure",
            "Horz. Subfield Structure",
            "Vert. Polyline Structure",
            "Horz. Polyline Structure"
        ])

        # Set default values for spinboxes
        self.structnum_pwr_spinbox.setValue(4)
        self.structnum_speed_spinbox.setValue(4)
        self.struct_size_spinbox.setValue(10.0)
        self.struct_hDist_spinbox.setValue(0.1)

        # Connect signals to methods
        self.test_structure_combobox.currentTextChanged.connect(self.update_test_structure)
        self.create_test_button.clicked.connect(self.create_test_structure)

        # Initialize the state of the UI based on the default selection
        self.update_test_structure()

    def update_test_structure(self, *args):
        selection = self.test_structure_combobox.currentText()
        if 'Square Contour' in selection:
            # Disable the spinboxes for power and speed
            self.structnum_pwr_spinbox.setEnabled(False)
            self.structnum_speed_spinbox.setEnabled(False)
        else:
            # Enable the spinboxes for power and speed
            self.structnum_pwr_spinbox.setEnabled(True)
            self.structnum_speed_spinbox.setEnabled(True)

        if 'Filled Squares' in selection:
            self.struct_size_spinbox.setEnabled(True)
            self.struct_hDist_spinbox.setEnabled(True)
        else:
            self.struct_size_spinbox.setEnabled(False)
            self.struct_hDist_spinbox.setEnabled(False)

    def create_test_structure(self):
        selection = self.test_structure_combobox.currentText()
        if selection == "Simple Square Contour":
            self.create_simple_square()
        elif selection == "Polyline Square Contour":
            self.create_polyline_square()
        elif "Subfield Structure" in selection:
            self.create_subfield_structure(selection=selection)
        elif selection == "Vert. Polyline Structure":
            self.create_polyline_structure_vert()
        elif selection == "Horz. Polyline Structure":
            self.create_polyline_structure_horz()
        elif "Filled Squares" in selection:
            self.create_filled_squares(selection)
        else:
            print("Error: Test pattern not supported!")

    def create_subfield_structure(self, selection, fieldSize=25, subfields=[5, 5]):
        fieldNum_row = self.structnum_pwr_spinbox.value()
        fieldNum_col = self.structnum_speed_spinbox.value()
        hDistances = np.linspace(5, 125, 25) / 1000
        subFieldWidth = fieldSize / subfields[1]  # includes 1mm space between subfields
        subFieldHeight = fieldSize / subfields[0]  # includes 1mm space between subfields
        if "Vert" in selection:
            nodeDist = subFieldHeight - 1  # make this smaller if needed
            numNodes = int((subFieldHeight - 1) / nodeDist)
        else:
            nodeDist = subFieldWidth - 1  # make this smaller if needed
            numNodes = int((subFieldWidth - 1) / nodeDist)
        hatched_test_structure = []
        line_dir = 1
        for row in range(fieldNum_row):
            for col in range(fieldNum_col):
                hatch_lines_poly = []
                for subfield_row in range(subfields[0]):
                    for subfield_col in range(subfields[1]):
                        current_subfield = subfield_row * subfields[0] + subfield_col
                        for line in range(int((subFieldWidth - 1) / hDistances[current_subfield])):
                            # Vert filling!
                            if "Vert" in selection:
                                x = col * (fieldSize + 2) + subfield_col * subFieldWidth + line * hDistances[current_subfield]
                                if line_dir == 1:
                                    y = -row * (fieldSize + 2) - subfield_row * subFieldHeight
                                else:
                                    y = -row * (fieldSize + 2) - (subfield_row + 1) * subFieldHeight + 1
                                polyline = [Point(x, y, 0, 0, 0, 0, 0)]
                                for node in range(1, int(numNodes) + 1):
                                    polyline.append(Point(x, y - line_dir * node * nodeDist, 0, 1, 0, 0, 0))
                                line_dir *= -1
                                hatch_lines_poly.append(polyline)

                            # Horz filling!
                            elif "Horz" in selection:
                                y = -row * (fieldSize + 2) - subfield_row * subFieldHeight - line * hDistances[current_subfield]
                                if line_dir == 1:
                                    x = col * (fieldSize + 2) + subfield_col * subFieldWidth
                                else:
                                    x = col * (fieldSize + 2) + (subfield_col + 1) * subFieldWidth - 1
                                polyline = [Point(x, y, 0, 0, 0, 0, 0)]
                                for node in range(1, int(numNodes) + 1):
                                    polyline.append(Point(x + line_dir * node * nodeDist, y, 0, 1, 0, 0, 0))
                                line_dir *= -1
                                hatch_lines_poly.append(polyline)
                            else:
                                print("Error: Unknown selection for subfield structure")
                hatched_test_structure.append(hatch_lines_poly)

        self.hatch_data.data = hatched_test_structure
        self.hatch_data.type = "Test: Subfield Structure"
        self.set_handler_data()

    def create_simple_square(self):
        size = 10
        polyline = [
            Point(0, 0, 0, 0, 0, 0, 0),
            Point(size, 0, 0, 1, 0, 0, 0),
            Point(size, -size, 0, 1, 0, 0, 0),
            Point(0, -size, 0, 1, 0, 0, 0),
            Point(0, 0, 0, 1, 0, 0, 0)
        ]
        self.hatch_data.data = [[polyline]]
        self.hatch_data.type = "Test: Simple Square Contour"
        self.set_handler_data()

    def create_polyline_square(self):
        size=10
        nodedist=2
        polyline=[Point(0,0,0,0,0,0,0)]
        for node in range(1,int(size/nodedist)+1):
            polyline.append(Point(node*nodedist,0,0,1,0,0,0))
        for node in range(1,int(size/nodedist)+1):
            polyline.append(Point(size,-node*nodedist,0,1,0,0,0))
        for node in range(1,int(size/nodedist)+1):
            polyline.append(Point(size-node*nodedist,-size,0,1,0,0,0))
        for node in range(1,int(size/nodedist)+1):
            polyline.append(Point(0,-size+node*nodedist,0,1,0,0,0))
        self.hatch_data.data=[[polyline]]
        self.hatch_data.type = "Test: Polyline Square Contour"
        self.set_handler_data()

    def create_polyline_structure_vert(self):
        # Get the number of rows and columns from the spinboxes
        lineNum_row=self.structnum_pwr_spinbox.value()
        lineNum_col=self.structnum_speed_spinbox.value()
        length = 10
        node_dist = 0.1
        space = 1
        x=0
        y=0
        hatched_test_structure=[]
        for row in range(lineNum_row):
            for col in range(lineNum_col):
                dir = col%2
                x=col*space
                y=-row*(length+2)-dir*length
                polyline=[]
                polyline.append(Point(x,y,0,0,0,0,0))
                for i in range(1,int(length/node_dist)+1):
                    polyline.append(Point(x,y-(1-2*dir)*i*node_dist,0,1,0,0,0))
                hatched_test_structure.append([polyline])
        self.hatch_data.data = hatched_test_structure
        self.hatch_data.type = "Test: Vert. Polyline Structure"
        self.set_handler_data()
    
    def create_polyline_structure_horz(self):
        # Get the number of rows and columns from the spinboxes
        lineNum_row=self.structnum_pwr_spinbox.value()
        lineNum_col=self.structnum_speed_spinbox.value()
        length = 10
        node_dist = 0.1
        space = 1
        x=0
        y=0
        hatched_test_structure=[]
        for row in range(lineNum_row):
            for col in range(lineNum_col):
                x=col*(length+2)
                y=-row*space
                polyline=[]
                polyline.append(Point(x,y,0,0,0,0,0))
                for i in range(1,int(length/node_dist)+1):
                    polyline.append(Point(x+i*node_dist,y,0,1,0,0,0))
                hatched_test_structure.append([polyline])
        self.hatch_data.data = hatched_test_structure
        self.hatch_data.type = "Test: Horz. Polyline Structure"
        self.set_handler_data()

    def create_filled_squares(self, selection):
        # Get the number of rows and columns from the spinboxes
        fieldNum_row=self.structnum_pwr_spinbox.value()
        fieldNum_col=self.structnum_speed_spinbox.value()
        square_size=self.struct_size_spinbox.value()
        h_dist=self.struct_hDist_spinbox.value()
        nodeDist=0.1 #default nodes to 100µm
        numNodes = int(square_size/nodeDist)
        hatched_test_structure=[]
        line_dir=1
        for row in range(fieldNum_row):
            for col in range(fieldNum_col):
                hatch_lines_poly=[]
                for line in range(int(square_size/h_dist)):
                    #Vert filling!
                    if "Vert" in selection:
                        x=col*(square_size+1)+line*h_dist
                        if line_dir==1:
                            y=-row*(square_size+1)
                        else:
                            y=-row*(square_size+1)-square_size
                        polyline=[Point(x,y,0,0,0,0,0)]
                        for node in range(1,int(numNodes)+1):
                            polyline.append(Point(x,y-line_dir*node*nodeDist,0,1,0,0,0))
                        line_dir*=-1
                        hatch_lines_poly.append(polyline)

                    #Horz filling!
                    elif "Horz" in selection:
                        y=-line*h_dist-row*(square_size+1)
                        if line_dir==1:
                            x=col*(square_size+1)
                        else:
                            x=col*(square_size+1)+square_size
                        polyline=[Point(x,y,0,0,0,0,0)]
                        for node in range(1,int(numNodes)+1):
                            polyline.append(Point(x+line_dir*node*nodeDist,y,0,1,0,0,0))
                        line_dir*=-1
                        hatch_lines_poly.append(polyline)
                    else:
                        print("Error: Unknown selection for subfield structure")
                hatched_test_structure.append(hatch_lines_poly)

        self.hatch_data.data = hatched_test_structure
        self.hatch_data.type = "Test: Filled Squares"
        self.set_handler_data()

    def set_handler_data(self):
        self.data_handler.hatch_data=self.hatch_data