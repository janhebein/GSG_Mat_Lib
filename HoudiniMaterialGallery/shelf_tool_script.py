import sys
import importlib
import hou

# 1. Unload all HoudiniMaterialGallery modules from memory
prefix = "HoudiniMaterialGallery"
modules_to_remove = [name for name in sys.modules if name == prefix or name.startswith(prefix + ".")]

for name in modules_to_remove:
    del sys.modules[name]

# 2. Re-import the fresh package
from HoudiniMaterialGallery import ui_main

# 3. Safely close any existing UI instance
if hasattr(hou.session, 'houdini_material_gallery_ui'):
    try:
        hou.session.houdini_material_gallery_ui.close()
        hou.session.houdini_material_gallery_ui.deleteLater()
    except Exception:
        pass

# 4. Create and show the new window
hou.session.houdini_material_gallery_ui = ui_main.MaterialGalleryWindow(hou.qt.mainWindow())
hou.session.houdini_material_gallery_ui.show()


