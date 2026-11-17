from PyQt6 import QtWidgets, QtCore, QtGui

class EventHandler(QtCore.QObject):
    def __init__(self, gui):
        self.gui = gui
        super().__init__()

        #Install the event Filters
        self.canvas_viewport = self.gui.image_canvas.viewport()
        self.canvas_viewport.installEventFilter(self)
        self.gui.installEventFilter(self)

        self.canvas_event_callbacks = []
        self.canvas_event_filters = []  # P9.11: checked first; if one consumes the event, the callbacks do not see it
        self.global_event_callbacks = []
    
    def eventFilter(self, source, event):
        # Handle canvas viewport events
        if source is self.canvas_viewport:  # B25: no call into a possibly deleted widget during teardown
            for event_filter in self.canvas_event_filters:
                if event_filter(event) is True:
                    return True
            consumed = False
            for callback in self.canvas_event_callbacks:
                if callback(event) is True:
                    consumed = True
            if consumed:
                return True
        # Handle global GUI events
        else:
            for callback in self.global_event_callbacks:
                callback(event)
        return super().eventFilter(source, event)
   
    
    def add_canvas_event_callback(self, callback):
        self.canvas_event_callbacks.append(callback)
    
    def add_canvas_event_filter(self, callback):
        """Like a canvas callback, but runs first and may hide the event from the others (return True)."""
        self.canvas_event_filters.append(callback)

    def add_global_event_callback(self, callback):
        self.global_event_callbacks.append(callback)