import sys
import math
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QPushButton, QHBoxLayout, QGraphicsView, 
                             QGraphicsScene, QGraphicsPixmapItem, QGraphicsPathItem,
                             QLabel, QSlider, QMessageBox)
from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import (QImage, QPixmap, QPainter, QPen, QColor, 
                         QPainterPath, QBrush, QKeySequence, QShortcut)
import collections
import numpy as np

class PixelEditorView(QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        
        # Rendering Hints for Pixel Art Style
        self.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        
        # Navigation
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setBackgroundBrush(QBrush(QColor(40, 40, 40)))

        # Drawing Tools
        self.is_drawing_mode = False
        self.is_currently_drawing = False
        self.pen_size = 1
        
        self.pixel_pen = QPen(QColor("red"), self.pen_size)
        self.pixel_pen.setCosmetic(False)
        self.pixel_pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        self.pixel_pen.setCapStyle(Qt.PenCapStyle.SquareCap) 

        # Layers
        self.background_item = None
        self.current_path = None
        self.temp_path_item = None

        # --- UNDO SYSTEM ---
        # Stack for Vector Items (Lightweight)
        self.active_vector_items = [] 
        # Stack for Pixel Snapshots (Heavyweight - limit this!)
        self.pixel_history = [] 
        self.MAX_PIXEL_HISTORY = 10 # Limit memory usage

    def load_image(self, width=100, height=100):
        self.scene.clear()
        self.active_vector_items.clear()
        self.pixel_history.clear()
        
        # Create Dummy High-Res Image
        img = QImage(width, height, QImage.Format.Format_RGB32)
        img.fill(Qt.GlobalColor.white)
        
        # Draw grid pattern
        painter = QPainter(img)
        painter.setPen(QColor(230, 230, 230))
        for i in range(0, width, 10): painter.drawLine(i, 0, i, height)
        for i in range(0, height, 10): painter.drawLine(0, i, width, i)
        painter.end()
        
        pixmap = QPixmap.fromImage(img)
        self.background_item = self.scene.addPixmap(pixmap)
        self.background_item.setZValue(0)
        
        self.fitInView(self.scene.itemsBoundingRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def set_pen_size(self, size):
        self.pen_size = size
        self.pixel_pen.setWidth(size)

    def snap_to_pixel_grid(self, position: QPointF):
        x = math.floor(position.x()) + 0.5
        y = math.floor(position.y()) + 0.5
        return QPointF(x, y)

    # --- INPUT EVENTS ---

    def mousePressEvent(self, event):
        if self.is_drawing_mode and event.button() == Qt.MouseButton.LeftButton:
            self.is_currently_drawing = True
            
            scene_pos = self.mapToScene(event.pos())
            snapped_pos = self.snap_to_pixel_grid(scene_pos)
            
            self.current_path = QPainterPath(snapped_pos)
            
            self.temp_path_item = QGraphicsPathItem(self.current_path)
            self.temp_path_item.setPen(self.pixel_pen)
            self.temp_path_item.setZValue(10)
            
            self.scene.addItem(self.temp_path_item)
            
            # Add to vector stack for Undo
            self.active_vector_items.append(self.temp_path_item)
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.is_currently_drawing and self.temp_path_item:
            scene_pos = self.mapToScene(event.pos())
            snapped_pos = self.snap_to_pixel_grid(scene_pos)
            
            if self.current_path.currentPosition() != snapped_pos:
                self.current_path.lineTo(snapped_pos)
                self.temp_path_item.setPath(self.current_path)
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.is_currently_drawing and event.button() == Qt.MouseButton.LeftButton:
            self.is_currently_drawing = False
        super().mouseReleaseEvent(event)

    def undo(self):
        """ Handles both Vector Undo and Pixel Undo transparently. """
        
        # Priority 1: Undo active vector drawings (not yet imprinted)
        if self.active_vector_items:
            # Remove last drawn stroke
            last_item = self.active_vector_items.pop()
            self.scene.removeItem(last_item)
            print("Undid vector stroke.")
            return

        # Priority 2: Undo Imprint (Revert pixel changes)
        if self.pixel_history:
            # Restore last saved pixmap
            previous_pixmap = self.pixel_history.pop()
            self.background_item.setPixmap(previous_pixmap)
            print("Undid imprint (restored pixels).")
        else:
            print("Nothing to undo.")
    
    # Hilfsmethode: Konvertiert QImage zu Numpy (für Analyse)
    def _get_image_matrix(self):
        """ Returns the current base image as a (H, W, 4) Numpy Array (RGBA). """
        if not self.background_item: return None
        
        ptr = self.background_item.pixmap().toImage()
        ptr = ptr.convertToFormat(QImage.Format.Format_RGBA8888)
        
        width = ptr.width()
        height = ptr.height()
        
        # Pointer Zugriff für Speed
        ptr.bits().setsize(height * width * 4)
        arr = np.frombuffer(ptr.bits(), np.uint8).reshape((height, width, 4))
        return arr.copy() # Copy, damit wir das Original nicht versehentlich ändern

    # Hilfsmethode: Erstellt ein transparentes Overlay Item aus einer Maske
    def _create_overlay_from_mask(self, mask_boolean, color: QColor):
        """
        Efficiently converts a boolean mask (H, W) into a QGraphicsPixmapItem overlay.
        """
        h, w = mask_boolean.shape
        
        # 1. Leeres RGBA Array erstellen (Standard: 0,0,0,0 = Transparent)
        rgba_overlay = np.zeros((h, w, 4), dtype=np.uint8)
        
        # 2. Farbe setzen (r, g, b, a)
        r, g, b, a = color.red(), color.green(), color.blue(), 255
        
        # 3. Nur dort Pixel setzen, wo die Maske True ist
        # Numpy Broadcasting ist hier extrem schnell (auch bei 4K/8K)
        rgba_overlay[mask_boolean] = [b, g, r, a] # Achtung: QImage erwartet oft BGR order je nach Format
        
        # 4. In QImage wandeln
        # Format_ARGB32 oder Format_RGBA8888 beachten. Hier nehmen wir RGBA8888
        overlay_img = QImage(rgba_overlay.data, w, h, QImage.Format.Format_RGBA8888)
        
        # 5. QGraphicsItem erstellen
        pixmap_item = QGraphicsPixmapItem(QPixmap.fromImage(overlay_img))
        pixmap_item.setZValue(10) # Über dem Hintergrund
        return pixmap_item

    # ==========================================
    # ANGEPASSTE METHODEN
    # ==========================================

    def fill_color_patch(self, event_pos, new_color: QColor):
        """
        Flood-fill angepasst für Overlay-Logik.
        event_pos: QPointF (Scene Coordinates)
        """
        # 1. Daten abholen
        image_matrix = self._get_image_matrix() # Das ist RGBA
        if image_matrix is None: return

        h, w = image_matrix.shape[:2]
        x = int(event_pos.x())
        y = int(event_pos.y())

        # Bounds Check
        if not (0 <= x < w and 0 <= y < h): return

        # Farben vergleichen (Vergleich muss im gleichen Farbraum sein)
        # Wir nehmen an image_matrix ist RGBA
        target_color = image_matrix[y, x].copy() 
        fill_color_arr = np.array([new_color.blue(), new_color.green(), new_color.red(), 255], dtype=np.uint8)
        
        # Abbruch wenn Farbe gleich (Toleranz könnte hier eingebaut werden)
        if np.array_equal(target_color, fill_color_arr): return

        # 2. BFS Algorithmus (Numpy optimiert ist schwer für Floodfill, daher Queue)
        # Für extrem große Bilder: skimage.segmentation.flood_fill wäre schneller, 
        # aber hier bleiben wir bei reinem Python/Numpy Standard.
        
        mask = np.zeros((h, w), dtype=bool)
        queue = collections.deque([(y, x)])
        visited = set([(y, x)])
        
        # Helper für Farbevergleich (wir vergleichen nur RGB, ignorieren Alpha für Logik)
        target_rgb = target_color[:3]
        
        while queue:
            cy, cx = queue.popleft()
            mask[cy, cx] = True
            
            # Nachbarn checken
            for dy, dx in [(-1,0), (1,0), (0,-1), (0,1)]:
                ny, nx = cy + dy, cx + dx
                if 0 <= ny < h and 0 <= nx < w:
                    if (ny, nx) not in visited:
                        # Pixel Farbe prüfen
                        if np.array_equal(image_matrix[ny, nx][:3], target_rgb):
                            visited.add((ny, nx))
                            queue.append((ny, nx))

        # 3. Overlay erstellen & zum Stack hinzufügen
        if np.any(mask):
            overlay_item = self._create_overlay_from_mask(mask, new_color)
            self.scene.addItem(overlay_item)
            self.active_vector_items.append(overlay_item) # Kommt auf den Undo Stack

    def replace_color(self, event_pos, new_color: QColor):
        """
        Ersetzt Farbe global oder basierend auf Logik.
        """
        image_matrix = self._get_image_matrix()
        if image_matrix is None: return

        x = int(event_pos.x())
        y = int(event_pos.y())
        h, w = image_matrix.shape[:2]

        if not (0 <= x < w and 0 <= y < h): return

        # Ziel-Farbe identifizieren (RGB)
        target_color_rgb = image_matrix[y, x][:3]
        
        # Maske erstellen: Wo sind die Pixel gleich der Ziel-Farbe?
        # np.all checkt über die letzte Achse (Color Channels)
        # Wir vergleichen nur die ersten 3 Kanäle (RGB), ignorieren Alpha
        mask = np.all(image_matrix[:, :, :3] == target_color_rgb, axis=2)

        # Optional: Hier deine "DataHandler" Masken-Logik einfügen, 
        # um 'mask' weiter einzuschränken (z.B. mask = mask & area_mask)
        
        # Overlay erstellen
        if np.any(mask):
            overlay_item = self._create_overlay_from_mask(mask, new_color)
            self.scene.addItem(overlay_item)
            self.active_vector_items.append(overlay_item)

    def recolor_entire_image(self, new_image_matrix_rgb):
        """
        Für 'recolor_color_from_db'.
        Erwartet, dass die DB-Logik bereits gelaufen ist und ein neues Bild (Matrix) liefert.
        """
        h, w = new_image_matrix_rgb.shape[:2]
        
        # Konvertierung zu QImage
        # Annahme: new_image_matrix ist uint8 RGB oder RGBA
        if new_image_matrix_rgb.shape[2] == 3:
            fmt = QImage.Format.Format_RGB888
        else:
            fmt = QImage.Format.Format_RGBA8888
            
        img = QImage(new_image_matrix_rgb.data, w, h, fmt)
        img = img.copy() # Wichtig data copy
        
        # Das ist kein transparentes Overlay, sondern ein komplett neues Bild
        # Wir legen es trotzdem einfach drüber.
        pixmap_item = QGraphicsPixmapItem(QPixmap.fromImage(img))
        pixmap_item.setZValue(10)
        
        self.scene.addItem(pixmap_item)
        self.active_vector_items.append(pixmap_item)

    # ==========================================
    # UPDATE IMPRINT LOGIC
    # ==========================================
    
    def imprint(self):
        """ 
        Updated Imprint: Handles both Vector Paths AND Pixmap Overlays 
        """
        if not self.active_vector_items: return

        # 1. Snapshot for Undo
        current_pixmap = self.background_item.pixmap()
        self.pixel_history.append(current_pixmap.copy())
        if len(self.pixel_history) > self.MAX_PIXEL_HISTORY:
            self.pixel_history.pop(0)

        # 2. Painter auf das Basis-Bild
        painter = QPainter(current_pixmap)
        # Wichtig: CompositionMode SourceOver ist Standard, mischt Transparenz korrekt
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        
        for item in self.active_vector_items:
            # Unterscheidung des Typs
            if isinstance(item, QGraphicsPathItem):
                # Zeichne Vektor
                painter.setPen(item.pen())
                painter.drawPath(item.path())
            
            elif isinstance(item, QGraphicsPixmapItem):
                # Zeichne Overlay-Bild (Floodfill / Replace Color Ergebnisse)
                # offset() ist wichtig, falls wir später bounding-box items nutzen
                pos = item.offset() 
                painter.drawPixmap(int(pos.x()), int(pos.y()), item.pixmap())
            
            # Item aus Szene entfernen
            self.scene.removeItem(item)
            
        painter.end()

        # 3. Update und Cleanup
        self.background_item.setPixmap(current_pixmap)
        self.active_vector_items.clear()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Pixel-Perfect Editor with UNDO")
        self.resize(1000, 800)

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)

        # Controls
        controls = QHBoxLayout()
        
        self.btn_mode = QPushButton("Draw Mode: OFF")
        self.btn_mode.setCheckable(True)
        self.btn_mode.clicked.connect(self.toggle_mode)

        # self.btn_fill_batch = QPushButton("Fill Batch")
        # self.btn_fill_batch.clicked.connect(lambda: self.editor.imprint())
        
        self.btn_imprint = QPushButton("Imprint (Commit)")
        self.btn_imprint.clicked.connect(lambda: self.editor.imprint())
        self.btn_imprint.setStyleSheet("font-weight: bold; color: darkred;")

        self.btn_undo = QPushButton("Undo (Ctrl+Z)")
        self.btn_undo.clicked.connect(lambda: self.editor.undo())

        controls.addWidget(self.btn_mode)
        controls.addWidget(self.btn_imprint)
        controls.addWidget(self.btn_undo)
        controls.addStretch()

        # Editor
        self.editor = PixelEditorView()
        # Loading a 2000x2000 image to show performance
        self.editor.load_image(200, 200) 

        layout.addLayout(controls)
        layout.addWidget(self.editor)

        # Keyboard Shortcut for Undo
        self.shortcut_undo = QShortcut(QKeySequence("Ctrl+Z"), self)
        self.shortcut_undo.activated.connect(self.editor.undo)

    def toggle_mode(self, checked):
        self.editor.is_drawing_mode = checked
        if checked:
            self.btn_mode.setText("Draw Mode: ON")
            self.editor.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.editor.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.btn_mode.setText("Draw Mode: OFF")
            self.editor.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            self.editor.setCursor(Qt.CursorShape.ArrowCursor)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())