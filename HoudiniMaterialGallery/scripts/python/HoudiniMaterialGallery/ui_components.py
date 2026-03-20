from hutil.Qt import QtWidgets, QtCore, QtGui
import os
from .material_library import get_cached_thumb_path

_PIXMAP_CACHE = {}
_MAX_PIXMAP_CACHE_ITEMS = 256
_SAFE_DIRECT_PREVIEW_EXTENSIONS = {".jpg", ".jpeg", ".png"}
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


def _resolve_display_thumbnail_path(original_path):
    if not original_path:
        return None, False

    cached_path = get_cached_thumb_path(original_path)
    if os.path.exists(cached_path):
        return cached_path, True

    folder_path = os.path.dirname(original_path)
    file_name = os.path.basename(original_path)
    old_thumb = os.path.join(folder_path, ".thumbnails", file_name + ".jpg")
    if os.path.exists(old_thumb):
        return old_thumb, True

    ext = os.path.splitext(original_path)[1].lower()
    if ext in _SAFE_DIRECT_PREVIEW_EXTENSIONS:
        return original_path, False

    return None, False

class MaterialItem:
    """Wrapper for either a Material object or a Folder string for the List Model."""
    def __init__(self, data, is_folder=False):
        self.data = data
        self.is_folder = is_folder
        self.is_simple_file = False
        self.texture_type = None  # e.g. 'albedo', 'normal', etc.
        self.thumbnail_pixmap = None
        self.thumbnail_pixmap_size = None
        self.original_thumbnail_path = None
        self.thumbnail_source_path = None
        self.preview_popup_source_path = None
        
        # Caching pixmap
        self.is_cached = False
        if not self.is_folder and hasattr(self.data, 'thumbnail') and self.data.thumbnail:
            original_path = self.data.thumbnail
            self.original_thumbnail_path = original_path
            load_path, is_cached = _resolve_display_thumbnail_path(original_path)
            self.is_cached = is_cached

            if load_path and os.path.exists(load_path):
                self.thumbnail_source_path = load_path

            original_ext = os.path.splitext(original_path)[1].lower()
            if original_ext in (".jpg", ".jpeg", ".png") and os.path.exists(original_path):
                self.preview_popup_source_path = original_path
            else:
                self.preview_popup_source_path = self.thumbnail_source_path

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

    def get_thumbnail_pixmap(self, size):
        if not self.thumbnail_source_path:
            return None
        if self.thumbnail_pixmap is None or self.thumbnail_pixmap_size != size:
            self.thumbnail_pixmap = _load_scaled_pixmap(self.thumbnail_source_path, size)
            self.thumbnail_pixmap_size = size if self.thumbnail_pixmap is not None else None
        return self.thumbnail_pixmap


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
        self.preview_button_size = 22
        self.preview_button_margin = 6

    def sizeHint(self, option, index):
        return self.item_size

    def thumbnail_rect(self, item_rect):
        return QtCore.QRect(
            item_rect.left() + self.padding,
            item_rect.top() + self.padding,
            self.thumb_size,
            self.thumb_size,
        )

    def has_preview(self, item):
        return (
            item is not None
            and not item.is_folder
            and bool(getattr(item, "preview_popup_source_path", None))
        )

    def preview_button_rect(self, item_rect):
        thumb_rect = self.thumbnail_rect(item_rect)
        return QtCore.QRect(
            thumb_rect.left() + self.preview_button_margin,
            thumb_rect.top() + self.preview_button_margin,
            self.preview_button_size,
            self.preview_button_size,
        )

    def is_preview_button_hit(self, item_rect, item, pos):
        if not self.has_preview(item):
            return False
        return self.preview_button_rect(item_rect).contains(pos)

    def _draw_preview_button(self, painter, button_rect, is_hover):
        button_path = QtGui.QPainterPath()
        button_path.addRoundedRect(QtCore.QRectF(button_rect), 6, 6)

        fill_color = QtGui.QColor(14, 14, 14, 190 if is_hover else 155)
        border_color = QtGui.QColor(255, 255, 255, 120 if is_hover else 85)
        icon_color = QtGui.QColor(255, 255, 255, 230 if is_hover else 205)

        painter.fillPath(button_path, fill_color)
        painter.setPen(QtGui.QPen(border_color, 1))
        painter.drawPath(button_path)

        painter.setPen(QtGui.QPen(icon_color, 1.6, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap))
        inset = 6
        left = button_rect.left() + inset
        top = button_rect.top() + inset
        right = button_rect.right() - inset
        bottom = button_rect.bottom() - inset
        arm = 4

        painter.drawLine(left, top + arm, left, top)
        painter.drawLine(left, top, left + arm, top)

        painter.drawLine(right - arm, top, right, top)
        painter.drawLine(right, top, right, top + arm)

        painter.drawLine(left, bottom - arm, left, bottom)
        painter.drawLine(left, bottom, left + arm, bottom)

        painter.drawLine(right - arm, bottom, right, bottom)
        painter.drawLine(right, bottom - arm, right, bottom)

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
        thumb_rect = self.thumbnail_rect(rect)

        painter.setPen(QtCore.Qt.NoPen)
        clip_path = QtGui.QPainterPath()
        clip_path.addRoundedRect(QtCore.QRectF(thumb_rect), 6, 6)
        painter.setClipPath(clip_path)

        if item.is_folder:
            # Draw folder icon or generic folder image
            painter.fillRect(thumb_rect, QtGui.QColor("#404040"))
            painter.setPen(QtGui.QColor("#888888"))
            painter.drawText(thumb_rect, QtCore.Qt.AlignCenter, "FOLDER\n" + item.name)
        else:
            pixmap = item.get_thumbnail_pixmap(self.thumb_size)
            if pixmap and not pixmap.isNull():
            # Draw actual image centered and cropped based on aspect ratio
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

        if self.has_preview(item):
            self._draw_preview_button(
                painter,
                self.preview_button_rect(rect),
                bool(is_hover),
            )

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

