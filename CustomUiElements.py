from PyQt6 import QtWidgets, QtCore, QtGui

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
