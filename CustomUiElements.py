from PyQt6 import QtWidgets, QtCore, QtGui


class WheelBlocker(QtCore.QObject):
    """App-wide event filter: the mouse wheel never changes spin boxes, drop-downs or sliders.
    The wheel event goes to the parent widget instead, so a scrollable panel under the cursor still scrolls."""
    BLOCKED = (QtWidgets.QAbstractSpinBox, QtWidgets.QComboBox, QtWidgets.QSlider, QtWidgets.QDial)

    def eventFilter(self, obj, event):
        if event.type() == QtCore.QEvent.Type.Wheel and isinstance(obj, self.BLOCKED):
            parent = obj.parentWidget()
            if parent is not None:
                QtCore.QCoreApplication.sendEvent(parent, event)
            return True
        return False

    @classmethod
    def install(cls, app):
        app._wheel_blocker = cls(app)  # keep a reference for the app lifetime
        app.installEventFilter(app._wheel_blocker)
        return app._wheel_blocker

class ListRename:
    """Right click on a list entry -> "Rename". `on_renamed(item, name)` stores the new name where the list's
    entries come from (lists rebuilt from their data must keep it there); default: the entry's text.
    A plain Python helper kept by the list widget (no QObject of its own: an extra QObject child with Python
    callbacks made the interpreter crash now and then when it shut down)."""

    def __init__(self, list_widget, on_renamed=None, current_name=None):
        self.list_widget = list_widget
        self.on_renamed = on_renamed or (lambda item, name: item.setText(name))
        self.current_name = current_name or (lambda item: item.text())
        list_widget.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        list_widget.customContextMenuRequested.connect(self.show_menu)

    def show_menu(self, pos):
        item = self.list_widget.itemAt(pos)
        if item is None:
            return
        menu = QtWidgets.QMenu(self.list_widget.window())  # not a child of the (see-through) section card
        rename = menu.addAction("Rename")
        if menu.exec(self.list_widget.viewport().mapToGlobal(pos)) is rename:
            self.ask(item)

    def ask(self, item):
        name, ok = QtWidgets.QInputDialog.getText(self.list_widget.window(), "Rename", "Name:", text=self.current_name(item))
        if ok:
            self.rename(item, name)

    def rename(self, item, name):
        name = name.strip()
        if name:
            self.on_renamed(item, name)
        return bool(name)


def enable_rename(list_widget, on_renamed=None, current_name=None):
    """Right click -> Rename for the entries of `list_widget` (see ListRename)."""
    list_widget._rename = ListRename(list_widget, on_renamed, current_name)
    return list_widget._rename


class NoScrollGraphicsView(QtWidgets.QGraphicsView):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.checkerboard_item = None  # QGraphicsPixmapItem whose transparent pixels show a checkerboard
        self._checker_brush = None

    def wheelEvent(self, event):
        # Ignore wheel events to prevent scrolling
        event.ignore()

    def drawBackground(self, painter, rect):
        super().drawBackground(painter, rect)
        item = self.checkerboard_item
        if item is None or item.pixmap().isNull():
            return
        if self._checker_brush is None:
            tile = QtGui.QPixmap(16, 16)
            tile.fill(QtGui.QColor(255, 255, 255))
            tile_painter = QtGui.QPainter(tile)
            tile_painter.fillRect(0, 0, 8, 8, QtGui.QColor(204, 204, 204))
            tile_painter.fillRect(8, 8, 8, 8, QtGui.QColor(204, 204, 204))
            tile_painter.end()
            self._checker_brush = QtGui.QBrush(tile)
        # in screen pixels, so the squares keep their size at every zoom level and pixel size
        area = self.mapFromScene(item.sceneBoundingRect()).boundingRect()
        painter.save()
        painter.resetTransform()
        painter.setBrushOrigin(area.topLeft())  # pattern moves with the image when panning
        painter.fillRect(area, self._checker_brush)
        painter.restore()
