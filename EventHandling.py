from PyQt6 import QtWidgets, QtCore, QtGui

class EventHandler(QtCore.QObject):
    def __init__(self, gui):
        self.gui = gui
        super().__init__()

        #Install the event Filters
        self.gui.image_canvas.viewport().installEventFilter(self)
        self.gui.installEventFilter(self)

        self.canvas_event_callbacks = []
        self.global_event_callbacks = []
    
    def eventFilter(self, source, event):
        # Handle canvas viewport events
        if source == self.gui.image_canvas.viewport():
            for callback in self.canvas_event_callbacks:
                callback(event)
        # Handle global GUI events
        else:
            for callback in self.global_event_callbacks:
                callback(event)
        return super().eventFilter(source, event)
   
    
    def add_canvas_event_callback(self, callback):
        self.canvas_event_callbacks.append(callback)
    
    def add_global_event_callback(self, callback):
        self.global_event_callbacks.append(callback)