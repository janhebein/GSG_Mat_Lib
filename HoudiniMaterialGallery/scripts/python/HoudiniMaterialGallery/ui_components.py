from hutil.Qt import QtWidgets, QtCore, QtGui
import os
from .material_library import get_cached_thumb_path, ensure_cached_thumbnail

_PIXMAP_CACHE = {}
_MAX_PIXMAP_CACHE_ITEMS = 256
_HEAVY_THUMB_EXTENSIONS = {".exr", ".hdr", ".hdri", ".tif", ".tiff", ".tga"}


def _load_scaled_pixmap(path, size):
    norm_path = os.path.normpath(path)
    try:
        mtime = os.path.getmtime(norm_path)
    except OSError:
        return None

    key = (norm_path, mtime, size)
    if key in _PIXMAP_CACHE:
        return _PIXMAP_CACHE[key]

    reader = QtGui.QImageReader(norm_path)
    source_size = reader.size()
    if source_size.isValid():
        source_size.scale(size, size, QtCore.Qt.KeepAspectRatio)
        reader.setScaledSize(source_size)
    image = reader.read()
    if image.isNull():
        pixmap = QtGui.QPixmap(norm_path)
    else:
        pixmap = QtGui.QPixmap.fromImage(image)

    if pixmap.isNull():
        return None

    pixmap = pixmap.scaled(size, size, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
    _PIXMAP_CACHE[key] = pixmap
    if len(_PIXMAP_CACHE) > _MAX_PIXMAP_CACHE_ITEMS:
        _PIXMAP_CACHE.clear()
    return pixmap

class MaterialItem:
    """Wrapper for either a Material object or a Folder string for the List Model."""
    def __init__(self, data, is_folder=False):
        self.data = data
        self.is_folder = is_folder
        self.is_simple_file = False
        self.texture_type = None  # e.g. 'albedo', 'normal', etc.
        self.thumbnail_pixmap = None
        
        # Caching pixmap
        self.is_cached = False
        if not self.is_folder and hasattr(self.data, 'thumbnail') and self.data.thumbnail:
            original_path = self.data.thumbnail
            cached_path = get_cached_thumb_path(original_path)
            
            if os.path.exists(cached_path):
                load_path = cached_path
                self.is_cached = True
            else:
                # Fallback: also check old .thumbnails subfolder for backwards compat
                folder_path = os.path.dirname(original_path)
                file_name = os.path.basename(original_path)
                old_thumb = os.path.join(folder_path, '.thumbnails', file_name + '.jpg')
                if os.path.exists(old_thumb):
                    load_path = old_thumb
                    self.is_cached = True
                else:
                    ext = os.path.splitext(original_path)[1].lower()
                    if ext in _HEAVY_THUMB_EXTENSIONS:
                        generated_thumb = ensure_cached_thumbnail(original_path)
                        if generated_thumb and os.path.exists(generated_thumb):
                            load_path = generated_thumb
                            self.is_cached = True
                        else:
                            load_path = None
                    else:
                        load_path = original_path
            
            if load_path and os.path.exists(load_path):
                self.thumbnail_pixmap = _load_scaled_pixmap(load_path, 160)

    @property
    def name(self):
        if self.is_folder:
            return os.path.basename(self.data)
        return self.data.name

    @property
    def path(self):
        if self.is_folder:
            return self.data
        return self.data.path


class MaterialListModel(QtCore.QAbstractListModel):
    def __init__(self, items=None, parent=None):
        super().__init__(parent)
        self.items = items or []

    def rowCount(self, parent=QtCore.QModelIndex()):
        return len(self.items)

    def data(self, index, role=QtCore.Qt.DisplayRole):
        if not index.isValid():
            return None

        item = self.items[index.row()]

        if role == QtCore.Qt.DisplayRole:
            return item.name
        elif role == QtCore.Qt.UserRole:
            return item
        return None

    def flags(self, index):
        default_flags = super().flags(index)
        if index.isValid():
            return default_flags | QtCore.Qt.ItemIsDragEnabled
        return default_flags

    def update_items(self, new_items):
        self.beginResetModel()
        self.items = new_items
        self.endResetModel()


class MaterialDelegate(QtWidgets.QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.item_size = QtCore.QSize(180, 220)
        self.thumb_size = 160
        self.padding = 10
        self.radius = 8

    def sizeHint(self, option, index):
        return self.item_size

    def paint(self, painter, option, index):
        item = index.data(QtCore.Qt.UserRole)
        if not item:
            return

        painter.save()
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)

        rect = option.rect

        # Colors based on state
        bg_color = QtGui.QColor("#2a2a2a")
        hover_bg = QtGui.QColor("#3a3a3a")
        selected_bg = QtGui.QColor("#4a90e2")
        text_color = QtGui.QColor("#e0e0e0")

        # Draw Background
        is_selected = option.state & QtWidgets.QStyle.State_Selected
        is_hover = option.state & QtWidgets.QStyle.State_MouseOver

        path = QtGui.QPainterPath()
        path.addRoundedRect(QtCore.QRectF(rect.adjusted(2, 2, -2, -2)), self.radius, self.radius)

        if is_selected:
            painter.fillPath(path, selected_bg)
        elif is_hover:
            painter.fillPath(path, hover_bg)
        else:
            painter.fillPath(path, bg_color)

        # Draw Thumbnail
        thumb_rect = QtCore.QRect(
            rect.left() + self.padding,
            rect.top() + self.padding,
            self.thumb_size,
            self.thumb_size
        )

        painter.setPen(QtCore.Qt.NoPen)
        clip_path = QtGui.QPainterPath()
        clip_path.addRoundedRect(QtCore.QRectF(thumb_rect), 6, 6)
        painter.setClipPath(clip_path)

        if item.is_folder:
            # Draw folder icon or generic folder image
            painter.fillRect(thumb_rect, QtGui.QColor("#404040"))
            painter.setPen(QtGui.QColor("#888888"))
            painter.drawText(thumb_rect, QtCore.Qt.AlignCenter, "FOLDER\n" + item.name)
        elif item.thumbnail_pixmap and not item.thumbnail_pixmap.isNull():
            # Draw actual image centered and cropped based on aspect ratio
            pixmap = item.thumbnail_pixmap
            # scaled pixmap is already ready to draw
            pw = pixmap.width()
            ph = pixmap.height()
            
            x_offset = int((self.thumb_size - pw) / 2)
            y_offset = int((self.thumb_size - ph) / 2)
            
            painter.drawPixmap(thumb_rect.left() + x_offset, thumb_rect.top() + y_offset, pixmap)
        else:
            # No thumbnail
            painter.fillRect(thumb_rect, QtGui.QColor("#333333"))
            painter.setPen(QtGui.QColor("#666666"))
            painter.drawText(thumb_rect, QtCore.Qt.AlignCenter, "NO PREVIEW")

        # Uncached indicator (small orange dot in top-right)
        if not item.is_folder and not getattr(item, 'is_cached', True):
            indicator_size = 10
            ix = thumb_rect.right() - indicator_size - 4
            iy = thumb_rect.top() + 4
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(QtGui.QColor("#ff8800"))
            painter.drawEllipse(ix, iy, indicator_size, indicator_size)

        # Discard clip path
        painter.setClipRect(rect)

        # Draw Type Badge
        badge_text = None
        badge_color = QtGui.QColor("#4a90e2")
        if item.is_folder:
            pass  # No badge for folders
        elif item.is_simple_file and item.texture_type:
            badge_text = item.texture_type.upper()
            badge_colors = {
                "albedo": "#e27d4a", "roughness": "#7a7a7a", "normal": "#6a6aee",
                "displacement": "#aa5599", "metallic": "#c0c0c0", "ao": "#555555",
                "opacity": "#44aa88", "emissive": "#e2d44a",
                "specular": "#e2e2e2", "scatteringweight": "#55aa55",
                "sheencolor": "#aa5555", "sheenopacity": "#aaa"
            }
            badge_color = QtGui.QColor(badge_colors.get(item.texture_type, "#4a90e2"))
        elif not item.is_simple_file and not item.is_folder:
            map_count = len(getattr(item.data, 'maps', {}))
            if map_count > 0:
                badge_text = f"PBR · {map_count}"
                badge_color = QtGui.QColor("#4a90e2")

        if badge_text:
            badge_font = painter.font()
            badge_font.setPointSize(7)
            badge_font.setBold(True)
            painter.setFont(badge_font)
            badge_metrics = QtGui.QFontMetrics(badge_font)
            badge_w = badge_metrics.horizontalAdvance(badge_text) + 10
            badge_h = 18
            badge_rect = QtCore.QRect(
                thumb_rect.left() + 4,
                thumb_rect.bottom() - badge_h - 4,
                badge_w, badge_h
            )
            badge_path = QtGui.QPainterPath()
            badge_path.addRoundedRect(QtCore.QRectF(badge_rect), 4, 4)
            badge_color.setAlpha(200)
            painter.fillPath(badge_path, badge_color)
            painter.setPen(QtGui.QColor("#ffffff"))
            painter.drawText(badge_rect, QtCore.Qt.AlignCenter, badge_text)

        # Draw Text
        text_rect = QtCore.QRect(
            rect.left() + self.padding,
            rect.top() + self.thumb_size + self.padding + 5,
            self.thumb_size,
            rect.height() - self.thumb_size - self.padding * 2 - 5
        )

        font = painter.font()
        font.setPointSize(9)
        if is_selected:
            font.setBold(True)
        painter.setFont(font)
        painter.setPen(text_color)
        
        # Elide text if it's too long
        metrics = QtGui.QFontMetrics(font)
        elided_text = metrics.elidedText(item.name, QtCore.Qt.ElideRight, text_rect.width())
        painter.drawText(text_rect, QtCore.Qt.AlignHCenter | QtCore.Qt.AlignTop, elided_text)

        painter.restore()

