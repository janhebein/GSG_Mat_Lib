from hutil.Qt import QtWidgets, QtCore, QtGui
import os
import traceback
from .material_library import (
    Material,
    MaterialLibraryManager,
    classify_texture_type,
    ensure_cached_thumbnail,
    get_cache_dir,
    get_cached_thumb_path,
)
from .ui_components import MaterialItem, MaterialListModel, MaterialDelegate

class MaterialListView(QtWidgets.QListView):
    """Custom list view that implements drag-to-network-editor by tracking
    mouse press/release and directly calling the Octane builder when the
    mouse is released over a Houdini Network Editor pane."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(False)  # We handle our own drag
        self._dragging_item = None
        self._drag_start_pos = None
        self._drag_watchdog = QtCore.QTimer(self)
        self._drag_watchdog.setInterval(120)
        self._drag_watchdog.timeout.connect(self._on_drag_watchdog_tick)

    def _clear_drag_state(self):
        self._dragging_item = None
        self._drag_start_pos = None
        if self._drag_watchdog.isActive():
            self._drag_watchdog.stop()
        self.setCursor(QtCore.Qt.ArrowCursor)

    def _start_drag_watchdog(self):
        if not self._drag_watchdog.isActive():
            self._drag_watchdog.start()

    def _on_drag_watchdog_tick(self):
        if self._dragging_item is None:
            if self._drag_watchdog.isActive():
                self._drag_watchdog.stop()
            return

        # Handle release globally even when the list view itself didn't receive
        # the mouse release event (common when dragging outside panel bounds).
        if not (QtWidgets.QApplication.mouseButtons() & QtCore.Qt.LeftButton):
            item = self._dragging_item
            self._clear_drag_state()
            if item is not None:
                self._handle_item_drop(item)
    
    def mousePressEvent(self, event):
        # Reset any stale drag state before starting a new interaction.
        if self._dragging_item is not None:
            self._clear_drag_state()
        if event.button() == QtCore.Qt.LeftButton:
            self._drag_start_pos = event.pos()
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        if self._dragging_item is not None and not (event.buttons() & QtCore.Qt.LeftButton):
            self._clear_drag_state()
            super().mouseMoveEvent(event)
            return

        if (self._drag_start_pos is not None and
            event.buttons() & QtCore.Qt.LeftButton):
            distance = (event.pos() - self._drag_start_pos).manhattanLength()
            if distance >= QtWidgets.QApplication.startDragDistance():
                index = self.indexAt(self._drag_start_pos)
                if index.isValid():
                    try:
                        item = self.model().mapToSource(index).data(QtCore.Qt.UserRole)
                    except Exception:
                        item = index.data(QtCore.Qt.UserRole)
                    
                    if item and not item.is_folder:
                        self._dragging_item = item
                        self.setCursor(QtCore.Qt.ClosedHandCursor)
                        self._start_drag_watchdog()
                        return  # Consume the event, we're in drag mode
        super().mouseMoveEvent(event)

    @staticmethod
    def _defer_drop_action(callback):
        def _safe_call():
            try:
                callback()
            except Exception as exc:
                print("[MaterialGallery] Deferred drop action failed:", exc)
                traceback.print_exc()

        try:
            import hdefereval
            hdefereval.executeDeferred(_safe_call)
        except Exception:
            QtCore.QTimer.singleShot(0, _safe_call)
    
    @staticmethod
    def _pane_tab_under_cursor(hou_module):
        pane = hou_module.ui.paneTabUnderCursor()
        if pane is not None:
            return pane

        pane_container = hou_module.ui.paneUnderCursor()
        if pane_container is not None:
            current_tab = getattr(pane_container, "currentTab", None)
            if callable(current_tab):
                try:
                    return current_tab()
                except Exception:
                    return None
        return None

    def mouseReleaseEvent(self, event):
        if self._dragging_item is not None and event.button() == QtCore.Qt.LeftButton:
            item = self._dragging_item
            self._clear_drag_state()
            self._handle_item_drop(item)
            return
        
        self._drag_start_pos = None
        super().mouseReleaseEvent(event)

    def _handle_item_drop(self, item):
        try:
            if hasattr(item, "is_simple_file") and item.is_simple_file:
                if self._set_text_on_widget_under_cursor(item.path, excluded_root=self.window()):
                    return

            import hou
            pane = self._pane_tab_under_cursor(hou)
            handled = False

            if pane and pane.type() == hou.paneTabType.NetworkEditor:
                network_node = pane.pwd()
                try:
                    pos = pane.cursorPosition()
                except Exception:
                    try:
                        pos = pane.visibleBounds().center()
                    except Exception:
                        pos = hou.Vector2(0, 0)

                if hasattr(item, 'is_simple_file') and item.is_simple_file:
                    # For textures: check if dropped ON a node
                    dropped_node = self._find_node_at_pos(network_node, pos)
                    if dropped_node:
                        # Try to set any file-type parameter on the node
                        if self._set_file_parm_on_node(dropped_node, item.path, getattr(item, "texture_type", None)):
                            handled = True
                        else:
                            # No file parm found, create an image node
                            from .octane_builder import build_material_from_texture_drop
                            self._defer_drop_action(
                                lambda: build_material_from_texture_drop(network_node, pos, item.path)
                            )
                            handled = True
                    else:
                        selected_nodes = hou.selectedNodes()
                        if selected_nodes:
                            handled = self._set_file_parm_on_node(
                                selected_nodes[0],
                                item.path,
                                getattr(item, "texture_type", None),
                            )
                        if not handled:
                            # Dropped on empty space, create node
                            from .octane_builder import build_material_from_texture_drop
                            self._defer_drop_action(
                                lambda: build_material_from_texture_drop(network_node, pos, item.path)
                            )
                            handled = True
                else:
                    from .octane_builder import build_material
                    material_data = item.data.to_dict()
                    self._defer_drop_action(
                        lambda: build_material(network_node, pos, material_data)
                    )
                    handled = True

            if hasattr(item, "is_simple_file") and item.is_simple_file and not handled:
                handled = self._set_file_parm_in_parameter_pane(
                    pane,
                    item.path,
                    getattr(item, "texture_type", None),
                )

            if hasattr(item, "is_simple_file") and item.is_simple_file and not handled:
                selected_nodes = hou.selectedNodes()
                if selected_nodes:
                    self._set_file_parm_on_node(
                        selected_nodes[0],
                        item.path,
                        getattr(item, "texture_type", None),
                    )
        except Exception as e:
            print("[MaterialGallery] Drop error:", e)
            traceback.print_exc()

    def focusOutEvent(self, event):
        if self._dragging_item is not None:
            self._clear_drag_state()
        super().focusOutEvent(event)

    def hideEvent(self, event):
        if self._dragging_item is not None:
            self._clear_drag_state()
        super().hideEvent(event)

    @staticmethod
    def _find_node_at_pos(parent_node, pos):
        """Find a node at the given network position."""
        import hou
        MARGIN = 0.5
        for child in parent_node.children():
            n_pos = child.position()
            n_size = child.size()
            if (pos[0] >= (n_pos[0] - MARGIN) and pos[0] <= (n_pos[0] + n_size[0] + MARGIN) and
                pos[1] >= (n_pos[1] - n_size[1] - MARGIN) and pos[1] <= (n_pos[1] + MARGIN)):
                return child
        return None

    @staticmethod
    def _infer_texture_type_from_path(filepath, default_type="unknown"):
        extension = os.path.splitext(filepath or "")[1].lower()
        if extension in (".hdr", ".hdri"):
            return "hdri"

        inferred_type = classify_texture_type(os.path.basename(filepath or ""))
        if inferred_type == "unknown":
            if extension == ".exr":
                # EXR files from the HDRI tab should be treated as environment maps.
                return default_type
            return default_type
        return inferred_type

    @staticmethod
    def _is_file_reference_parm(parm):
        try:
            import hou
            template = parm.parmTemplate()
            if template.type() != hou.parmTemplateType.String:
                return False
            if template.stringType() == hou.stringParmType.FileReference:
                return True

            tags = template.tags() or {}
            tag_keys = " ".join(tags.keys()).lower()
            tag_vals = " ".join(str(v) for v in tags.values()).lower()
            if "filechooser" in tag_keys or "filechooser" in tag_vals:
                return True
            if "chooser_mode" in tag_keys and "read" in tag_vals:
                return True
            return False
        except Exception:
            return False

    @classmethod
    def _set_file_parm_on_node(cls, node, filepath, texture_type=None, preferred_parms=None):
        """Try to set a file-type parameter on the node. Returns True if successful."""
        # Common file parameter names across Houdini nodes
        file_parm_names = ("File", "A_FILENAME", "filename", "textureFile", "file", 
                           "fileName", "tex0", "map", "texture", "image", "path",
                           "env_map", "vm_background", "environment_map", "hdri_map",
                           "gobo", "gobo_map", "cookie", "cookie_map", "projection_map",
                           "light_texture", "ar_light_color_texture", "A_FILENAME")
        for parm_name in file_parm_names:
            parm = node.parm(parm_name)
            if parm is not None:
                try:
                    parm.set(filepath)
                    return True
                except Exception:
                    pass

        if preferred_parms:
            for parm in preferred_parms:
                if parm is None:
                    continue
                try:
                    candidate_parms = parm.parms() if hasattr(parm, "parms") else [parm]
                except Exception:
                    candidate_parms = [parm]

                for candidate in candidate_parms:
                    if candidate is None:
                        continue
                    if cls._is_file_reference_parm(candidate):
                        try:
                            candidate.set(filepath)
                            return True
                        except Exception:
                            continue

        # Fallback: search all string parms that are file references.
        for parm in node.parms():
            if cls._is_file_reference_parm(parm):
                try:
                    parm.set(filepath)
                    return True
                except Exception:
                    continue
        return False

    @staticmethod
    def _set_text_on_widget_under_cursor(filepath, excluded_root=None):
        widget = QtWidgets.QApplication.widgetAt(QtGui.QCursor.pos())
        if widget is None:
            return False
        if excluded_root is not None:
            try:
                if widget is excluded_root or excluded_root.isAncestorOf(widget):
                    return False
            except Exception:
                pass
        visited = set()

        while widget is not None and id(widget) not in visited:
            visited.add(id(widget))
            if isinstance(widget, QtWidgets.QLineEdit):
                try:
                    widget.setText(filepath)
                    widget.returnPressed.emit()
                    widget.editingFinished.emit()
                    return True
                except Exception:
                    pass
            elif isinstance(widget, QtWidgets.QComboBox) and widget.isEditable():
                try:
                    widget.setEditText(filepath)
                    return True
                except Exception:
                    pass
            widget = widget.parentWidget()
        return False

    @classmethod
    def _set_file_parm_in_parameter_pane(cls, pane, filepath, texture_type=None):
        try:
            if cls._set_text_on_widget_under_cursor(filepath):
                return True
        except Exception:
            pass

        try:
            import hou
            parm_pane_types = {
                getattr(hou.paneTabType, "Parm", None),
                getattr(hou.paneTabType, "Parameters", None),
                getattr(hou.paneTabType, "ParameterEditor", None),
            }
            parm_pane_types.discard(None)
            if not pane or pane.type() not in parm_pane_types:
                return False

            node = None
            current_node_method = getattr(pane, "currentNode", None)
            if callable(current_node_method):
                node = current_node_method()
            if node is None:
                selected_nodes = hou.selectedNodes()
                if selected_nodes:
                    node = selected_nodes[0]
            if node is None:
                return False

            preferred_parms = []
            visible_parms_method = getattr(pane, "visibleParms", None)
            if callable(visible_parms_method):
                try:
                    preferred_parms = list(visible_parms_method() or [])
                except Exception:
                    preferred_parms = []

            return cls._set_file_parm_on_node(node, filepath, texture_type, preferred_parms)
        except Exception:
            return False

class ThumbnailCacheWorker(QtCore.QThread):
    progress = QtCore.Signal(int, int, str)
    finished_stats = QtCore.Signal(int, int, int, bool)

    def __init__(self, library_path, parent=None):
        super().__init__(parent)
        self.library_path = library_path
        self._cancel_requested = False

    def cancel(self):
        self._cancel_requested = True

    def run(self):
        to_process = []
        success = 0
        failed = 0

        for root, dirs, files in os.walk(self.library_path):
            if self._cancel_requested:
                break
            if ".thumbnails" in dirs:
                dirs.remove(".thumbnails")
            if not any(f.lower().endswith((".png", ".jpg", ".jpeg", ".exr", ".hdr", ".hdri", ".tif", ".tiff", ".tga")) for f in files):
                continue

            mat = Material(root)
            if not mat.thumbnail or not os.path.exists(mat.thumbnail):
                continue

            if os.path.exists(get_cached_thumb_path(mat.thumbnail)):
                continue

            to_process.append(mat.thumbnail)

        total = len(to_process)
        for idx, preview_path in enumerate(to_process, 1):
            if self._cancel_requested:
                break
            if ensure_cached_thumbnail(preview_path, size=300, allow_houdini=False):
                success += 1
            else:
                failed += 1
            self.progress.emit(idx, total, os.path.basename(preview_path))

        self.finished_stats.emit(success, failed, total, self._cancel_requested)

class MaterialGalleryWindow(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.WindowMinMaxButtonsHint | QtCore.Qt.WindowCloseButtonHint)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, False)
        
        self.setWindowTitle("GSG Mat Lib")
        self.resize(1000, 700)
        
        self.library_manager = MaterialLibraryManager()
        self.current_library = None
        self.current_folder = None
        self.in_material_view = False
        self.material_overview_folder = None
        self.view_mode = "materials"  # "materials" or "textures"
        self._thumb_worker = None
        self._thumb_progress = None
        
        self.setup_ui()
        self.load_root_folders()

    def setup_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)

        # --- Top Header Area ---
        header_layout = QtWidgets.QHBoxLayout()
        
        # Gear Settings Button
        self.btn_settings = QtWidgets.QPushButton()
        self.btn_settings.setObjectName("btn_settings")
        self.btn_settings.setFixedSize(36, 30)
        self.btn_settings.setToolTip("Library Settings")
        try:
            import hou
            self.btn_settings.setIcon(hou.qt.Icon("BUTTONS_gear", 22, 22))
            self.btn_settings.setIconSize(QtCore.QSize(22, 22))
        except Exception:
            self.btn_settings.setText("*")
        self.btn_settings.clicked.connect(self.show_settings_menu)
        header_layout.addWidget(self.btn_settings)
        
        # Asset Type Dropdown
        self.type_combo = QtWidgets.QComboBox()
        self.type_combo.addItems(["Materials", "Textures", "HDRIs"])
        self.type_combo.setFixedHeight(30)
        self.type_combo.setMinimumWidth(140)
        self.type_combo.currentIndexChanged.connect(self.on_type_changed)
        header_layout.addWidget(self.type_combo)
        
        # Search Bar
        self.search_bar = QtWidgets.QLineEdit()
        self.search_bar.setPlaceholderText("Search...")
        self.search_bar.setFixedHeight(30)
        self.search_bar.textChanged.connect(self.on_search_changed)
        header_layout.addWidget(self.search_bar)

        self.btn_refresh = QtWidgets.QPushButton()
        self.btn_refresh.setObjectName("btn_refresh")
        self.btn_refresh.setFixedSize(30, 30)
        self.btn_refresh.setToolTip("Refresh Gallery")
        self.btn_refresh.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_BrowserReload))
        self.btn_refresh.setIconSize(QtCore.QSize(14, 14))
        self.btn_refresh.clicked.connect(self.on_refresh_clicked)
        header_layout.addWidget(self.btn_refresh)
        
        header_layout.addStretch()
        
        # Import Button
        self.btn_import = QtWidgets.QPushButton("Import ▶")
        self.btn_import.setObjectName("btn_import")
        self.btn_import.setFixedHeight(30)
        self.btn_import.setFixedWidth(100)
        self.btn_import.setToolTip("Import selected material into the current Network Editor")
        self.btn_import.clicked.connect(self.import_selected_material)
        header_layout.addWidget(self.btn_import)

        main_layout.addLayout(header_layout)

        # --- Sub Header Area (Navigation) ---
        nav_layout = QtWidgets.QHBoxLayout()
        
        self.btn_back = QtWidgets.QPushButton("← Back")
        self.btn_back.setVisible(False)
        self.btn_back.clicked.connect(self.navigate_back)
        
        self.breadcrumb_label = QtWidgets.QLabel("")
        self.breadcrumb_label.setObjectName("breadcrumb")
        
        nav_layout.addWidget(self.btn_back)
        nav_layout.addWidget(self.breadcrumb_label)
        nav_layout.addStretch()
        

        
        nav_layout.addSpacing(10)
        
        main_layout.addLayout(nav_layout)

        # --- Main Gallery View ---
        self.list_view = MaterialListView()
        self.list_view.setViewMode(QtWidgets.QListView.IconMode)
        self.list_view.setResizeMode(QtWidgets.QListView.Adjust)
        self.list_view.setSpacing(10)
        self.list_view.setUniformItemSizes(True)
        self.list_view.setMovement(QtWidgets.QListView.Static)
        self.list_view.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.list_view.setDragEnabled(False)
        self.list_view.setDragDropMode(QtWidgets.QAbstractItemView.NoDragDrop)
        
        # Context Menu
        self.list_view.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.list_view.customContextMenuRequested.connect(self.show_context_menu)
        
        self.delegate = MaterialDelegate(self.list_view)
        self.list_view.setItemDelegate(self.delegate)
        
        self.model = MaterialListModel([], self)
        
        # Proxy Model for Search Filtering
        self.proxy_model = QtCore.QSortFilterProxyModel(self)
        self.proxy_model.setSourceModel(self.model)
        self.proxy_model.setFilterCaseSensitivity(QtCore.Qt.CaseInsensitive)
        self.proxy_model.setFilterRole(QtCore.Qt.DisplayRole)
        
        self.list_view.setModel(self.proxy_model)
        
        self.list_view.doubleClicked.connect(self.on_item_double_clicked)
        
        main_layout.addWidget(self.list_view)
        
        self.load_stylesheet()

    def load_stylesheet(self):
        qss_path = os.path.join(os.path.dirname(__file__), "style.qss")
        if os.path.exists(qss_path):
            with open(qss_path, "r", encoding="utf-8") as f:
                stylesheet = f.read()

            arrow_path = os.path.join(os.path.dirname(__file__), "arrow_down.png")
            if os.path.exists(arrow_path):
                arrow_path = arrow_path.replace("\\", "/")
                stylesheet = stylesheet.replace("__COMBO_ARROW_ICON__", arrow_path)
            else:
                stylesheet = stylesheet.replace('image: url("__COMBO_ARROW_ICON__");', "image: none;")

            self.setStyleSheet(stylesheet)

    def load_root_folders(self):
        if self.library_manager.root_folders:
            self.current_library = self.library_manager.root_folders[0]
            self.current_folder = os.path.join(self.current_library, "materials")
            self.in_material_view = False
            self.refresh_view()
        else:
            self.model.update_items([])
            self.breadcrumb_label.setText("No library selected. Click Settings to set path.")

    def show_settings_menu(self):
        menu = QtWidgets.QMenu(self)
        
        set_path_action = menu.addAction("Set Library Path...")
        set_path_action.triggered.connect(self.add_root_folder)

        menu.addSeparator()
        cache_dir_label = menu.addAction("Preview Cache: " + self.library_manager.get_thumb_cache_dir())
        cache_dir_label.setEnabled(False)
        edit_cache_path_action = menu.addAction("Set Preview Cache Path...")
        edit_cache_path_action.triggered.connect(self.edit_thumbnail_cache_path)
        
        if self.current_library:
            menu.addSeparator()
            path_label = menu.addAction("Path: " + str(self.current_library))
            path_label.setEnabled(False)
            
            edit_path_action = menu.addAction("Edit Path...")
            edit_path_action.triggered.connect(self.edit_library_path)
            
            menu.addSeparator()
            cache_action = menu.addAction("Cache Preview Thumbnails")
            cache_action.setToolTip("Compresses ONLY preview images into small JPGs")
            cache_action.triggered.connect(self.generate_thumbnails)
        
        menu.exec(self.btn_settings.mapToGlobal(QtCore.QPoint(0, self.btn_settings.height())))

    def edit_library_path(self):
        from hutil.Qt import QtWidgets
        text, ok = QtWidgets.QInputDialog.getText(self, "Edit Library Path", "GSG Library Root:", text=self.current_library or "")
        if ok and text.strip():
            new_path = text.strip()
            if os.path.exists(new_path) and os.path.isdir(new_path):
                self.library_manager.root_folders = [new_path]
                self.library_manager.save_config()
                self.load_root_folders()
            else:
                import hou
                hou.ui.displayMessage("Invalid directory path.")

    def edit_thumbnail_cache_path(self):
        current_cache_dir = self.library_manager.get_thumb_cache_dir()
        text, ok = QtWidgets.QInputDialog.getText(
            self,
            "Preview Cache Path",
            "Preview cache directory (leave empty for default):",
            text=current_cache_dir or "",
        )
        if not ok:
            return

        try:
            new_path = text.strip()
            if not new_path:
                self.library_manager.set_thumb_cache_dir(None)
            else:
                self.library_manager.set_thumb_cache_dir(new_path)
        except Exception as e:
            try:
                import hou
                hou.ui.displayMessage("Invalid cache path:\n{0}".format(e))
            except Exception:
                print("[MaterialGallery] Invalid cache path:", e)

    def on_type_changed(self, index):
        self.in_material_view = False
        self.material_overview_folder = None
        self.current_folder = None
        self.search_bar.clear()
        self.refresh_view()

    def get_current_asset_type(self):
        return self.type_combo.currentText()  # "Materials", "Textures", or "HDRIs"

    def on_refresh_clicked(self):
        self.refresh_view()

    def _materials_root_folder(self):
        if not self.current_library:
            return None
        return os.path.normpath(os.path.join(self.current_library, "materials"))

    def _can_navigate_back(self):
        if self.in_material_view:
            return True

        if self.get_current_asset_type() != "Materials" or not self.current_folder:
            return False

        root_folder = self._materials_root_folder()
        if not root_folder:
            return False

        return os.path.normpath(self.current_folder) != os.path.normpath(root_folder)

    def _materials_breadcrumb_text(self):
        root_folder = self._materials_root_folder()
        if not root_folder or not self.current_folder:
            return "Materials"

        current = os.path.normpath(self.current_folder)
        root = os.path.normpath(root_folder)
        if current == root:
            return "Materials"

        try:
            relative = os.path.relpath(current, root)
        except Exception:
            return "Materials"

        if relative in (".", ""):
            return "Materials"
        return "Materials > " + relative.replace("\\", " > ")

    def refresh_view(self):
        if not self.current_library:
            return
            
        asset_type = self.get_current_asset_type()
        
        if self.in_material_view:
            self.breadcrumb_label.setText("Materials > " + os.path.basename(self.current_folder or "Material"))
            self.populate_material_maps()
        else:
            if asset_type == "Materials":
                default_materials_folder = os.path.join(self.current_library, "materials")
                if (
                    not self.current_folder
                    or not os.path.isdir(self.current_folder)
                    or os.path.normpath(self.current_folder) == os.path.normpath(self.current_library)
                ):
                    self.current_folder = default_materials_folder
                self.breadcrumb_label.setText(self._materials_breadcrumb_text())
                self.populate_materials(self.current_folder)
            elif asset_type == "Textures":
                self.breadcrumb_label.setText("Textures")
                self.current_folder = os.path.join(self.current_library, "textures")
                self.populate_textures()
            elif asset_type == "HDRIs":
                self.breadcrumb_label.setText("HDRIs")
                self.current_folder = os.path.join(self.current_library, "hdris")
                self.populate_hdris()

        self.btn_back.setVisible(self._can_navigate_back())

    def populate_materials(self, folder_path=None):
        mat_dir = os.path.normpath(folder_path or os.path.join(self.current_library, "materials"))
        self.current_folder = mat_dir
        if not os.path.isdir(mat_dir):
            self.model.update_items([])
            return
            
        materials, subfolders, loose_files = self.library_manager.get_materials_in_folder(mat_dir, recursive=False)
        
        items = []
        for m in materials:
            items.append(MaterialItem(m, is_folder=False))
            
        for sf in subfolders:
            items.insert(0, MaterialItem(sf, is_folder=True))

        for lf in loose_files:
            dd = type('DummyData', (), {'path': lf, 'name': os.path.basename(lf), 'thumbnail': lf})()
            m_item = MaterialItem(dd, is_folder=False)
            m_item.is_simple_file = True
            m_item.texture_type = MaterialListView._infer_texture_type_from_path(lf, default_type="texture")
            items.append(m_item)
                 
        self.model.update_items(items)

    def populate_textures(self):
        textures = self.library_manager.get_gsg_textures(self.current_library)
        items = []
        for tex in textures:
            inferred_type = MaterialListView._infer_texture_type_from_path(tex.texture_path, default_type="texture")
            # Use the preview as thumbnail, texture_path for drag/drop
            dd = type('DummyData', (), {
                'path': tex.texture_path, 
                'name': tex.name, 
                'thumbnail': tex.thumbnail or tex.texture_path
            })()
            m_item = MaterialItem(dd, is_folder=False)
            m_item.is_simple_file = True
            m_item.texture_type = inferred_type
            items.append(m_item)
        self.model.update_items(items)

    def populate_hdris(self):
        hdris = self.library_manager.get_gsg_hdris(self.current_library)
        items = []
        for hdri in hdris:
            dd = type('DummyData', (), {
                'path': hdri.hdri_path,
                'name': hdri.name,
                'thumbnail': hdri.thumbnail or hdri.hdri_path
            })()
            m_item = MaterialItem(dd, is_folder=False)
            m_item.is_simple_file = True
            m_item.texture_type = "hdri"
            items.append(m_item)
        self.model.update_items(items)

    def populate_material_maps(self):
        """When dived into a material, show its textures as items."""
        mat = Material(self.current_folder)
        items = []
        for asset in mat.texture_assets:
            dd = type('DummyData', (), {
                'path': asset.texture_path, 
                'name': asset.name, 
                'thumbnail': asset.texture_path or mat.thumbnail
            })()
            m_item = MaterialItem(dd, is_folder=False)
            m_item.is_simple_file = True
            m_item.texture_type = asset.texture_type
            items.append(m_item)
                
        self.model.update_items(items)

    def on_item_double_clicked(self, index):
        item = index.data(QtCore.Qt.UserRole)
        if hasattr(item, 'is_simple_file') and item.is_simple_file:
            self.apply_texture_to_selected_node(item.path)
            return
            
        if item.is_folder:
            if self.get_current_asset_type() == "Materials" and not self.in_material_view:
                self.current_folder = item.path
                self.search_bar.clear()
                self.refresh_view()
                return

            # Fallback behavior for non-material folder items.
            self.current_library = item.path
            self.refresh_view()
        else:
            # It's a Material, dive into it
            self.material_overview_folder = self.current_folder
            self.in_material_view = True
            self.current_folder = item.path
            self.search_bar.clear() # Clear search when diving in
            self.refresh_view()
            
    def on_search_changed(self, text):
        self.proxy_model.setFilterFixedString(text)

    def show_context_menu(self, pos):
        index = self.list_view.indexAt(pos)
        if not index.isValid():
            return

        item = self.proxy_model.mapToSource(index).data(QtCore.Qt.UserRole)
        if not item:
            return

        menu = QtWidgets.QMenu(self)
        
        open_action = menu.addAction("Open in Explorer")
        open_action.triggered.connect(lambda: self.open_in_explorer(item.path))
        
        if getattr(item, "is_simple_file", False):
            copy_label = "Copy File Path"
        elif item.is_folder:
            copy_label = "Copy Folder Path"
        else:
            copy_label = "Copy Material Path"

        copy_action = menu.addAction(copy_label)
        copy_action.triggered.connect(lambda: QtWidgets.QApplication.clipboard().setText(item.path))
        
        if not item.is_folder:
            menu.addSeparator()
            import_action = menu.addAction("Import Material to Network")
            import_action.triggered.connect(self.import_selected_material)

        menu.exec(self.list_view.mapToGlobal(pos))

    def open_in_explorer(self, path):
        import platform
        import subprocess
        
        path = os.path.normpath(path)
        if platform.system() == "Windows":
            if os.path.isdir(path):
                subprocess.Popen(f'explorer "{path}"')
            else:
                subprocess.Popen(f'explorer /select,"{path}"')
        elif platform.system() == "Darwin":
            if os.path.isdir(path):
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["open", "-R", path])
        else:
            if os.path.isdir(path):
                subprocess.Popen(["xdg-open", path])
            else:
                subprocess.Popen(["xdg-open", os.path.dirname(path)])

    def navigate_back(self):
        if self.in_material_view:
            overview_folder = self.material_overview_folder or os.path.join(self.current_library, "materials")
            if not os.path.isdir(overview_folder):
                overview_folder = os.path.join(self.current_library, "materials")

            self.in_material_view = False
            self.material_overview_folder = None
            self.current_folder = overview_folder
        elif self.get_current_asset_type() == "Materials":
            root_folder = self._materials_root_folder()
            if root_folder and self.current_folder:
                current = os.path.normpath(self.current_folder)
                root = os.path.normpath(root_folder)
                if current != root:
                    parent = os.path.normpath(os.path.dirname(current))
                    try:
                        if os.path.commonpath([root, parent]) != root:
                            parent = root
                    except Exception:
                        parent = root
                    self.current_folder = parent

        self.search_bar.clear()
        self.refresh_view()

    def add_root_folder(self):
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Select Root Material Folder")
        if folder:
            self.library_manager.add_root_folder(folder)
            self.load_root_folders()
            
    def remove_current_library(self):
        if self.current_library:
            self.library_manager.remove_root_folder(self.current_library)
            self.load_root_folders()

    def generate_thumbnails(self):
        if not self.current_library:
             import hou
             hou.ui.displayMessage("Please add a library first.")
             return

        cache_dir = self.library_manager.get_thumb_cache_dir() or get_cache_dir()

        import hou
        if hou.ui.displayMessage(
            "This will scan your Library and create small 300px JPG copies of ONLY the material preview images in:\n\n"
            + cache_dir
            + "\n\nYour original textures are NOT touched. Already cached previews will be skipped.\n\nContinue?",
            buttons=("Yes", "Cancel"),
        ) != 0:
            return

        if self._thumb_worker is not None and self._thumb_worker.isRunning():
            hou.ui.displayMessage("Thumbnail generation is already running.")
            return

        self._thumb_progress = QtWidgets.QProgressDialog(
            "Scanning library previews...",
            "Cancel",
            0,
            100,
            self,
        )
        self._thumb_progress.setWindowTitle("Caching Preview Thumbnails")
        self._thumb_progress.setWindowModality(QtCore.Qt.WindowModal)
        self._thumb_progress.setMinimumDuration(0)
        self._thumb_progress.setValue(0)
        self._thumb_progress.show()

        self._thumb_worker = ThumbnailCacheWorker(self.current_library, self)
        self._thumb_worker.progress.connect(self._on_thumbnail_progress)
        self._thumb_worker.finished_stats.connect(self._on_thumbnail_finished)
        self._thumb_progress.canceled.connect(self._thumb_worker.cancel)
        self._thumb_worker.start()

    def _on_thumbnail_progress(self, current, total, file_name):
        progress_dialog = self._thumb_progress
        if progress_dialog is None:
            return
        try:
            if total <= 0:
                progress_dialog.setRange(0, 0)
                progress_dialog.setLabelText("Scanning library previews...")
                return

            progress_dialog.setRange(0, total)
            progress_dialog.setValue(current)
            progress_dialog.setLabelText(
                "Caching preview thumbnails...\n{0}/{1} - {2}".format(current, total, file_name)
            )
        except Exception:
            return

    def _on_thumbnail_finished(self, success, failed, total, canceled):
        progress_dialog = self._thumb_progress
        self._thumb_progress = None
        worker = self._thumb_worker
        self._thumb_worker = None

        if progress_dialog is not None:
            try:
                if total > 0:
                    progress_dialog.setRange(0, total)
                    progress_dialog.setValue(total)
                progress_dialog.hide()
                progress_dialog.close()
                progress_dialog.deleteLater()
            except Exception:
                pass

        if worker is not None:
            try:
                worker.progress.disconnect(self._on_thumbnail_progress)
            except Exception:
                pass
            try:
                worker.finished_stats.disconnect(self._on_thumbnail_finished)
            except Exception:
                pass
            try:
                worker.deleteLater()
            except Exception:
                pass

        try:
            import hou
            QtWidgets.QApplication.processEvents()
            if canceled:
                msg = "Thumbnail generation canceled.\n\nProcessed: {0}/{1}\nSuccess: {2}\nFailed: {3}".format(
                    success + failed, total, success, failed
                )
            elif total == 0:
                msg = "All previews are already cached.\n\nCache path:\n{0}".format(
                    self.library_manager.get_thumb_cache_dir()
                )
            else:
                msg = "Thumbnail generation finished.\n\nCached: {0}\nFailed: {1}\nTotal: {2}\n\nCache path:\n{3}".format(
                    success,
                    failed,
                    total,
                    self.library_manager.get_thumb_cache_dir(),
                )
            hou.ui.displayMessage(msg)
        except Exception:
            pass

    def import_selected_material(self):
        """Import the selected material into the current Houdini network editor.
        This follows the same pattern as the legacy importAssetCommand()."""
        try:
            import hou
        except ImportError:
            print("[MaterialGallery] Not running inside Houdini.")
            return

        indexes = self.list_view.selectedIndexes()
        if not indexes:
            hou.ui.displayMessage("No material selected. Please select a material first.")
            return

        source_index = self.proxy_model.mapToSource(indexes[0])
        item = source_index.data(QtCore.Qt.UserRole)
        if not item or item.is_folder:
            return

        # Get current network editor context (same as the legacy getNetworkEditor flow)
        network_editor = None
        for pane in hou.ui.paneTabs():
            if isinstance(pane, hou.NetworkEditor) and pane.isCurrentTab():
                network_editor = pane
                break
        if not network_editor:
            for pane in hou.ui.paneTabs():
                if isinstance(pane, hou.NetworkEditor):
                    network_editor = pane
                    break

        if not network_editor:
            hou.ui.displayMessage("No Network Editor found.")
            return

        ctx = network_editor.pwd()
        try:
            drop_pos = network_editor.cursorPosition()
        except:
            drop_pos = hou.Vector2(0, 0)

        if getattr(item, 'is_simple_file', False):
            # If a node is selected, try applying the texture to its parameter
            if len(hou.selectedNodes()) > 0:
                self.apply_texture_to_selected_node(item.path)
                return
                
            try:
                from HoudiniMaterialGallery.octane_builder import build_material_from_texture_drop
                build_material_from_texture_drop(ctx, drop_pos, item.path)
            except Exception as e:
                hou.ui.displayMessage(f"Failed to build material from texture: {e}")
            return

        # It's a full material - build it
        material_data = item.data.to_dict()
        try:
            from HoudiniMaterialGallery.octane_builder import build_material
            build_material(ctx, drop_pos, material_data)
        except Exception as e:
            # Fallback: create a sticky note with the error
            try:
                sticky = ctx.createStickyNote()
                sticky.setText(f"Material: {material_data.get('name')}\nError: {str(e)}")
                sticky.setPosition(drop_pos)
                sticky.setSize(hou.Vector2(4, 2))
                print(f"[MaterialGallery] Import error: {e}")
                traceback.print_exc()
            except Exception as e2:
                hou.ui.displayMessage(f"Failed to import: {e}\n\nFallback also failed: {e2}")

    def apply_texture_to_selected_node(self, texture_path):
        import hou
        try:
            selected_nodes = hou.selectedNodes()
            if not selected_nodes:
                return
            node = selected_nodes[0]
            inferred_type = MaterialListView._infer_texture_type_from_path(texture_path, default_type="texture")
            MaterialListView._set_file_parm_on_node(node, texture_path, inferred_type)
        except Exception as e:
            print("Failed to apply texture to node:", e)

def launch():
    import sys
    app = QtWidgets.QApplication.instance()
    if not app:
        app = QtWidgets.QApplication(sys.argv)
        
    window = MaterialGalleryWindow()
    window.show()
    
    # If not running inside Houdini, we need to exec the app
    if not hasattr(sys, 'houdini_is_running'):
        app.exec_()
    return window

if __name__ == "__main__":
    launch()

