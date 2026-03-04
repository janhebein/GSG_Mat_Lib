import os
import json
import re
import hashlib

DEFAULT_CACHE_DIR = os.path.join(os.path.expanduser("~"), ".houdini", "gsg_thumb_cache")
DEFAULT_CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".houdini_material_gallery.json")


def _read_gallery_config(config_path=DEFAULT_CONFIG_PATH):
    if not os.path.exists(config_path):
        return {}
    try:
        with open(config_path, "r") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def _resolve_cache_dir_from_config(config_path=DEFAULT_CONFIG_PATH):
    data = _read_gallery_config(config_path)
    configured = data.get("thumb_cache_dir")
    if configured:
        return os.path.normpath(configured)
    return DEFAULT_CACHE_DIR


def get_cache_dir():
    """Returns the central thumbnail cache directory. Creates it if needed."""
    cache_dir = _resolve_cache_dir_from_config()
    if not os.path.exists(cache_dir):
        os.makedirs(cache_dir, exist_ok=True)
    return cache_dir


def get_cached_thumb_path(original_path):
    """Returns the path where a cached thumbnail for this file would be stored."""
    # Create a unique filename from the full path to avoid collisions
    path_hash = hashlib.md5(os.path.normpath(original_path).encode()).hexdigest()[:12]
    basename = os.path.splitext(os.path.basename(original_path))[0]
    cache_filename = f"{basename}_{path_hash}.jpg"
    return os.path.join(get_cache_dir(), cache_filename)


def has_cached_thumbnail(original_path):
    """Check if a cached thumbnail exists for this file."""
    return os.path.exists(get_cached_thumb_path(original_path))


def ensure_cached_thumbnail(original_path, size=300, allow_houdini=True):
    """Create a JPG cache thumbnail when possible and return its path."""
    if not original_path:
        return None

    normalized_path = os.path.normpath(original_path)
    if not os.path.isfile(normalized_path):
        return None

    cached_path = get_cached_thumb_path(normalized_path)
    if os.path.exists(cached_path):
        return cached_path

    def _convert_with_pillow():
        try:
            from PIL import Image
        except Exception:
            return False

        try:
            with Image.open(normalized_path) as img:
                if img.mode != "RGB":
                    img = img.convert("RGB")
                img.thumbnail((size, size))
                img.save(cached_path, "JPEG", quality=85)
            return os.path.exists(cached_path)
        except Exception:
            return False

    def _convert_with_houdini():
        if not allow_houdini:
            return False
        try:
            import hou
        except Exception:
            return False

        try:
            src = normalized_path.replace("\\", "/")
            dst = cached_path.replace("\\", "/")
            hou.hscript('imgconvert -s {0} {0} "{1}" "{2}"'.format(int(size), src, dst))
            return os.path.exists(cached_path)
        except Exception:
            return False

    ext = os.path.splitext(normalized_path)[1].lower()
    heavy_formats = {".exr", ".hdr", ".hdri", ".tif", ".tiff", ".tga"}
    converters = (_convert_with_houdini, _convert_with_pillow) if ext in heavy_formats else (_convert_with_pillow, _convert_with_houdini)

    for converter in converters:
        if converter():
            return cached_path

    return None

TEXTURE_TYPES = {
    "albedo": ["albedo", "color", "basecolor", "diffuse", "base_color", "diff"],
    "roughness": ["roughness", "rough", "rgh"],
    "normal": ["normal", "nrm", "norm"],
    "displacement": ["displacement", "disp", "height"],
    "metallic": ["metallic", "metalness", "metal"],
    "ao": ["ao", "ambientocclusion", "ambient_occlusion"],
    "sheenopacity": ["sheenopacity", "sheen_opacity", "sheenroughness"],
    "opacity": ["opacity", "alpha"],
    "emissive": ["emissive", "emission"],
    "specular": ["specular", "spec", "refl"],
    "scatteringweight": ["scatteringweight", "scattering", "sssweight", "sss_weight", "transmission"],
    "sheencolor": ["sheencolor", "sheen_color"],
}

THUMBNAIL_IDENTIFIERS = ["thumb", "preview", "thumbnail", "sphere"]
VALID_EXTENSIONS = [".png", ".jpg", ".jpeg", ".exr", ".tif", ".tiff", ".tga"]
IGNORED_SIDECAREXTENSIONS = {".rat"}


def _is_ignored_sidecar_file(filename):
    filename_lower = filename.lower()
    ext = os.path.splitext(filename_lower)[1]
    return ext in IGNORED_SIDECAREXTENSIONS or ".rat." in filename_lower


def classify_texture_type(filename):
    """Returns the texture type string for a given filename, or 'unknown'."""
    name_lower = os.path.splitext(filename)[0].lower()
    for tex_type, identifiers in TEXTURE_TYPES.items():
        for identifier in identifiers:
            if identifier in name_lower:
                return tex_type
    return "unknown"


class Material:
    def __init__(self, path):
        self.path = os.path.normpath(path)
        self.name = os.path.basename(self.path)
        self.maps = {}
        self.texture_assets = []
        self.thumbnail = None
        
        self._scan_directory()

    def _scan_directory(self):
        """Scans the material directory to find texture maps and a thumbnail."""
        if not os.path.isdir(self.path):
            return

        for filename in os.listdir(self.path):
            filepath = os.path.join(self.path, filename)
            if not os.path.isfile(filepath):
                continue
            if _is_ignored_sidecar_file(filename):
                continue
             
            ext = os.path.splitext(filename)[1].lower()
            if ext not in VALID_EXTENSIONS:
                continue
                
            name_lower = os.path.splitext(filename)[0].lower()
            
            # Check if it's a thumbnail
            is_thumb = False
            for thumb_id in THUMBNAIL_IDENTIFIERS:
                if re.search(r'\b' + thumb_id + r'\b', name_lower) or thumb_id in name_lower:
                    self.thumbnail = filepath
                    is_thumb = True
                    break
            
            if is_thumb:
                continue
                
            # Classify texture map
            for tex_type, identifiers in TEXTURE_TYPES.items():
                assigned = False
                for identifier in identifiers:
                    if identifier in name_lower:
                        if tex_type not in self.maps:
                            self.maps[tex_type] = filepath
                        
                        # Create a TextureAsset for this individual map
                        asset = TextureAsset(filepath, is_file=True)
                        asset.texture_type = tex_type
                        self.texture_assets.append(asset)
                        assigned = True
                        break
                if assigned:
                    break
                    
    def represents_valid_material(self):
        """Returns True if this folder contains at least one valid texture map."""
        return len(self.maps) > 0

    def to_dict(self):
        return {
            "name": self.name,
            "path": self.path,
            "thumbnail": self.thumbnail,
            "maps": self.maps
        }

class MaterialLibraryManager:
    """Manages the registered root folders and loads their contents."""
    
    def __init__(self, config_path=None):
        self.config_path = config_path or DEFAULT_CONFIG_PATH
        self.root_folders = []
        self.thumb_cache_dir = None
        self.load_config()

    def load_config(self):
        data = _read_gallery_config(self.config_path)
        self.root_folders = data.get("root_folders", [])
        configured_cache_dir = data.get("thumb_cache_dir")
        self.thumb_cache_dir = os.path.normpath(configured_cache_dir) if configured_cache_dir else None

    def save_config(self):
        try:
            with open(self.config_path, "w") as f:
                json.dump(
                    {
                        "root_folders": self.root_folders,
                        "thumb_cache_dir": self.thumb_cache_dir,
                    },
                    f,
                    indent=4,
                )
        except Exception as e:
            print(f"Error saving config: {e}")

    def get_thumb_cache_dir(self):
        if self.thumb_cache_dir:
            return self.thumb_cache_dir
        return _resolve_cache_dir_from_config(self.config_path)

    def set_thumb_cache_dir(self, folder_path):
        if not folder_path:
            self.thumb_cache_dir = None
            self.save_config()
            return

        normalized = os.path.normpath(folder_path)
        if not os.path.exists(normalized):
            os.makedirs(normalized, exist_ok=True)
        if not os.path.isdir(normalized):
            raise ValueError("Thumbnail cache path must be a directory.")

        self.thumb_cache_dir = normalized
        self.save_config()

    def add_root_folder(self, folder_path):
        folder_path = os.path.normpath(folder_path)
        if folder_path not in self.root_folders and os.path.isdir(folder_path):
            self.root_folders.append(folder_path)
            self.save_config()

    def remove_root_folder(self, folder_path):
        folder_path = os.path.normpath(folder_path)
        if folder_path in self.root_folders:
            self.root_folders.remove(folder_path)
            self.save_config()

    def get_materials_in_folder(self, folder_path, recursive=False):
        """Scans a folder and returns (materials, subfolders, loose_files)."""
        materials = []
        subfolders = []
        loose_files = []
        
        if not os.path.isdir(folder_path):
            return materials, subfolders, loose_files

        for item in os.listdir(folder_path):
            item_path = os.path.join(folder_path, item)
            if os.path.isdir(item_path):
                mat = Material(item_path)
                if mat.represents_valid_material():
                    materials.append(mat)
                else:
                    subfolders.append(item_path)
                    if recursive:
                        rec_mats, rec_subs, rec_loose = self.get_materials_in_folder(item_path, recursive=True)
                        materials.extend(rec_mats)
                        loose_files.extend(rec_loose)
            elif os.path.isfile(item_path):
                if _is_ignored_sidecar_file(item):
                    continue
                ext = os.path.splitext(item)[1].lower()
                if ext in VALID_EXTENSIONS:
                    loose_files.append(item_path)
                    
        return materials, subfolders, loose_files

    def get_all_textures(self, folder_path, recursive=False):
        """Returns a flat list of all texture file paths in the folder."""
        textures = []
        
        if not os.path.isdir(folder_path):
            return textures

        for item in os.listdir(folder_path):
            item_path = os.path.join(folder_path, item)
            if os.path.isdir(item_path):
                if recursive:
                    textures.extend(self.get_all_textures(item_path, recursive=True))
            elif os.path.isfile(item_path):
                if _is_ignored_sidecar_file(item):
                    continue
                ext = os.path.splitext(item)[1].lower()
                if ext in VALID_EXTENSIONS:
                    textures.append(item_path)

        return textures

    def get_gsg_textures(self, library_root):
        """Scans the GSG textures/ subfolder. Each subfolder has a main texture + _preview.jpg."""
        textures_dir = os.path.join(library_root, "textures")
        results = []
        if not os.path.isdir(textures_dir):
            return results
        for item in sorted(os.listdir(textures_dir)):
            item_path = os.path.join(textures_dir, item)
            if os.path.isdir(item_path):
                asset = TextureAsset(item_path)
                if asset.texture_path:
                    results.append(asset)
        return results

    def get_gsg_hdris(self, library_root):
        """Scans the GSG hdris/ subfolder. Each subfolder has .exr/.hdr + _preview.jpg."""
        hdris_dir = os.path.join(library_root, "hdris")
        results = []
        if not os.path.isdir(hdris_dir):
            return results
        for item in sorted(os.listdir(hdris_dir)):
            item_path = os.path.join(hdris_dir, item)
            if os.path.isdir(item_path):
                asset = HDRIAsset(item_path)
                if asset.hdri_path:
                    results.append(asset)
        return results


HDRI_EXTENSIONS = [".exr", ".hdr", ".hdri"]


class TextureAsset:
    """Represents a single GSG texture (gobo/overlay/pattern)."""
    def __init__(self, path, is_file=False):
        self.path = os.path.normpath(path)
        self.name = os.path.basename(self.path)
        self.is_file = is_file
        self.texture_path = self.path if is_file else None
        self.thumbnail = None
        self.texture_type = None
        if not is_file:
            self._scan()

    def _scan(self):
        if not os.path.isdir(self.path):
            return
        for f in os.listdir(self.path):
            fp = os.path.join(self.path, f)
            if not os.path.isfile(fp):
                continue
            fl = f.lower()
            ext = os.path.splitext(fl)[1]
            if "_preview" in fl and ext in (".jpg", ".jpeg", ".png"):
                self.thumbnail = fp
            elif ext in VALID_EXTENSIONS and "_preview" not in fl and ext != ".gsga":
                if self.texture_path is None:
                    self.texture_path = fp

    def to_dict(self):
        return {
            "name": self.name,
            "path": self.path,
            "texture_path": self.texture_path,
            "thumbnail": self.thumbnail,
            "is_file": self.is_file,
            "texture_type": self.texture_type
        }


class HDRIAsset:
    """Represents a single GSG HDRI."""

    def __init__(self, path, is_file=False):
        self.path = os.path.normpath(path)
        self.name = os.path.basename(self.path)
        self.is_file = is_file
        self.hdri_path = self.path if is_file else None
        self.thumbnail = None
        if not is_file:
            self._scan()

    def _scan(self):
        if not os.path.isdir(self.path):
            return
        for f in os.listdir(self.path):
            fp = os.path.join(self.path, f)
            if not os.path.isfile(fp):
                continue
            if _is_ignored_sidecar_file(f):
                continue
            fl = f.lower()
            ext = os.path.splitext(fl)[1]
            if "_preview" in fl and ext in (".jpg", ".jpeg", ".png"):
                self.thumbnail = fp
            elif ext in HDRI_EXTENSIONS:
                # Prefer .exr over .hdr
                if self.hdri_path is None or ext == ".exr":
                    self.hdri_path = fp

    def to_dict(self):
        return {
            "name": self.name,
            "path": self.path,
            "hdri_path": self.hdri_path,
            "thumbnail": self.thumbnail,
            "is_file": self.is_file,
        }
