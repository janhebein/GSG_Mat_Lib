import os
import re

from .material_library import (
    Material,
    TEXTURE_TYPES,
    THUMBNAIL_IDENTIFIERS,
    VALID_EXTENSIONS,
    classify_texture_type,
)
from .octane_mappings import (
    OCTANE_COLOR_SPACES,
    OCTANE_DISPLACEMENT_PARMS,
    OCTANE_NODE_TYPES,
    OCTANE_STANDARD_SURFACE_INPUTS,
    OCTANE_TEXTURE_INPUTS,
)

MATERIAL_CONTEXT_CATEGORIES = {"Mat", "Vop", "Shop", "Vopnet"}

MAP_TYPES_TO_INPUTS = {
    "albedo": (OCTANE_STANDARD_SURFACE_INPUTS["base_color"], OCTANE_NODE_TYPES["tex_image"], True),
    "specularroughness": (OCTANE_STANDARD_SURFACE_INPUTS["roughness"], OCTANE_NODE_TYPES["tex_float_image"], False),
    "diffuseroughness": (OCTANE_STANDARD_SURFACE_INPUTS["diffuse_roughness"], OCTANE_NODE_TYPES["tex_float_image"], False),
    "roughness": (OCTANE_STANDARD_SURFACE_INPUTS["roughness"], OCTANE_NODE_TYPES["tex_float_image"], False),
    "metallic": (OCTANE_STANDARD_SURFACE_INPUTS["metallic"], OCTANE_NODE_TYPES["tex_float_image"], False),
    "normal": (OCTANE_STANDARD_SURFACE_INPUTS["normal"], OCTANE_NODE_TYPES["tex_image"], False),
    "displacement": (OCTANE_STANDARD_SURFACE_INPUTS["displacement"], OCTANE_NODE_TYPES["tex_float_image"], False),
    "ao": (OCTANE_STANDARD_SURFACE_INPUTS["ambient_occlusion"], OCTANE_NODE_TYPES["tex_float_image"], False),
    "opacity": (OCTANE_STANDARD_SURFACE_INPUTS["opacity"], OCTANE_NODE_TYPES["tex_float_image"], False),
    "emissive": (OCTANE_STANDARD_SURFACE_INPUTS["emission_color"], OCTANE_NODE_TYPES["tex_image"], True),
    "specular": (OCTANE_STANDARD_SURFACE_INPUTS["specular"], OCTANE_NODE_TYPES["tex_float_image"], False),
    "scatteringweight": (OCTANE_STANDARD_SURFACE_INPUTS["transmission"], OCTANE_NODE_TYPES["tex_float_image"], False),
    "sheencolor": (OCTANE_STANDARD_SURFACE_INPUTS["sheen_color"], OCTANE_NODE_TYPES["tex_image"], True),
    "sheenopacity": (OCTANE_STANDARD_SURFACE_INPUTS["sheen_roughness"], OCTANE_NODE_TYPES["tex_float_image"], False),
}

GSG_STANDARD_SURFACE_PARM_ALIASES = {
    "base_color": ("baseColor", "base_color"),
    "coat": ("coating", "coat", "coatWeight", "coatingWeight"),
    "coat_color": ("coatingColor", "coatColor", "coat_color"),
    "coat_IOR": ("coatingIor", "coatIOR", "coatIor", "coat_ior"),
    "coat_roughness": ("coatingRoughness", "coatRoughness", "coat_roughness"),
    "dielectric_priority": ("dielectricPriority", "dielectric_priority"),
    "diffuse_roughness": ("diffuseRoughness", "diffuse_roughness"),
    "internal_reflections": ("internalReflections", "internal_reflections"),
    "sheen": ("sheen",),
    "sheen_color": ("sheenColor", "sheen_color"),
    "sheen_roughness": ("sheenRoughness", "sheen_roughness"),
    "specular": ("specular",),
    "specular_IOR": ("ior", "specularIOR", "specularIor", "specular_ior"),
    "specular_anisotropy": ("specularAnisotropy", "specular_anisotropy", "anisotropy"),
    "specular_roughness": ("roughness", "specularRoughness", "specular_roughness"),
    "specular_color": ("specularColor", "specular_color"),
    "specular_rotation": ("specularRotation", "specular_rotation", "anisotropyRotation"),
    "subsurface": ("subsurface",),
    "subsurface_color": ("subsurfaceColor", "subsurface_color"),
    "subsurface_radius": ("subsurfaceRadius", "subsurface_radius"),
    "subsurface_scale": ("subsurfaceScale", "subsurface_scale"),
    "subsurface_type": ("subsurfaceType", "subsurface_type"),
    "thin_walled": ("thinWall", "thinWalled", "thin_walled"),
    "transmission": ("transmission",),
    "transmission_color": ("transmissionColor", "transmission_color"),
    "transmission_depth": ("transmissionDepth", "transmission_depth"),
    "transmission_scatter": ("transmissionScatter", "transmission_scatter", "scatterColor", "subsurfaceColor"),
    "caustics": ("caustics",),
}

GSG_NORMAL_MAP_PARM_ALIASES = {
    "strength": ("power", "strength", "normalStrength", "normal_strength"),
}


def _safe_status(message):
    import hou

    try:
        hou.ui.setStatusMessage(message)
    except Exception:
        pass


def _is_material_context(parent_node):
    try:
        category_name = parent_node.childTypeCategory().name()
    except Exception:
        return False
    return category_name in MATERIAL_CONTEXT_CATEGORIES


def _first_existing_parm(node, parm_names):
    for parm_name in parm_names:
        parm = node.parm(parm_name)
        if parm is not None:
            return parm
    return None


def _connect_input_by_name(target_node, input_name, source_node):
    for index, connection_name in enumerate(target_node.inputNames()):
        if connection_name == input_name:
            target_node.setInput(index, source_node, 0)
            return True
    return False


def _set_texture_file_parm(texture_node, texture_path):
    file_parm = _first_existing_parm(texture_node, ("File", "A_FILENAME", "filename", "textureFile"))
    if file_parm is not None:
        file_parm.set(texture_path)


def _set_linear_gamma(texture_node):
    gamma_parm = texture_node.parm("gamma")
    if gamma_parm is not None:
        gamma_parm.set(1.0)


def _set_texture_color_space(texture_node, use_srgb):
    color_space_parms = ("colorSpace", "colorspace", "color_space")
    target_space = OCTANE_COLOR_SPACES["srgb"] if use_srgb else OCTANE_COLOR_SPACES["linear"]
    if _set_first_parm_value(texture_node, color_space_parms, target_space):
        return

    fallback_space = "sRGB" if use_srgb else "Other"
    if _set_first_parm_value(texture_node, color_space_parms, fallback_space):
        return

    if not use_srgb:
        _set_linear_gamma(texture_node)


def _set_first_parm_value(node, parm_names, value):
    parm = _first_existing_parm(node, parm_names)
    if parm is None:
        return False

    try:
        parm.set(value)
        return True
    except TypeError:
        pass
    except Exception:
        return False

    try:
        parm.set(str(value))
        return True
    except TypeError:
        pass
    except Exception:
        return False

    value_str = str(value)
    try:
        menu_items = parm.menuItems() or ()
    except Exception:
        menu_items = ()

    if menu_items:
        for menu_item in menu_items:
            if menu_item == value_str or value_str in menu_item:
                try:
                    parm.set(menu_item)
                    return True
                except Exception:
                    continue

        try:
            menu_labels = parm.menuLabels() or ()
        except Exception:
            menu_labels = ()

        for index, label in enumerate(menu_labels):
            if value_str in str(label) and index < len(menu_items):
                try:
                    parm.set(menu_items[index])
                    return True
                except Exception:
                    continue

    return False


def _set_rgb_like_value(node, parm_names, value):
    try:
        if isinstance(value, dict):
            rgb = (
                float(value.get("r", 0.0)),
                float(value.get("g", 0.0)),
                float(value.get("b", 0.0)),
            )
        elif isinstance(value, (tuple, list)) and len(value) >= 3:
            rgb = (float(value[0]), float(value[1]), float(value[2]))
        else:
            return False
    except Exception:
        return False

    for parm_name in parm_names:
        try:
            parm_tuple = node.parmTuple(parm_name)
            if parm_tuple is not None and len(parm_tuple) >= 3:
                parm_tuple.set(rgb[: len(parm_tuple)])
                return True
        except Exception:
            pass

        for suffixes in (("r", "g", "b"), ("R", "G", "B"), ("_r", "_g", "_b")):
            channels = [node.parm("{0}{1}".format(parm_name, suffix)) for suffix in suffixes]
            if all(channel is not None for channel in channels):
                try:
                    channels[0].set(rgb[0])
                    channels[1].set(rgb[1])
                    channels[2].set(rgb[2])
                    return True
                except Exception:
                    continue
    return False


def _set_uniform_rgb_like_value(node, parm_names, scalar_value):
    try:
        v = float(scalar_value)
    except Exception:
        return False

    rgb = {"r": v, "g": v, "b": v}
    return _set_rgb_like_value(node, parm_names, rgb)


def _apply_standard_surface_metadata(standard_surface_node, metadata):
    if not isinstance(metadata, dict):
        return

    rgb_like_metadata_keys = {
        "base_color",
        "subsurface_radius",
        "subsurface_color",
        "sheen_color",
        "specular_color",
        "transmission_color",
        "transmission_scatter",
    }

    for metadata_key, value in metadata.items():
        parm_names = GSG_STANDARD_SURFACE_PARM_ALIASES.get(metadata_key)
        if not parm_names:
            continue

        if _set_rgb_like_value(standard_surface_node, parm_names, value):
            continue
        if metadata_key in rgb_like_metadata_keys and _set_uniform_rgb_like_value(
            standard_surface_node, parm_names, value
        ):
            continue

        if isinstance(value, bool):
            value = int(value)
        _set_first_parm_value(standard_surface_node, parm_names, value)


def _apply_normal_map_metadata(normal_texture_node, metadata):
    if normal_texture_node is None or not isinstance(metadata, dict):
        return

    for metadata_key, value in metadata.items():
        parm_names = GSG_NORMAL_MAP_PARM_ALIASES.get(metadata_key)
        if not parm_names:
            continue
        _set_first_parm_value(normal_texture_node, parm_names, value)


def _apply_gsg_metadata(standard_surface_node, map_nodes, metadata):
    if not isinstance(metadata, dict):
        return

    params = metadata.get("params")
    if not isinstance(params, dict):
        return

    _apply_standard_surface_metadata(standard_surface_node, params.get("standard_surface", {}))
    _apply_normal_map_metadata(map_nodes.get("normal"), params.get("normal_map", {}))


def _enforce_required_defaults(standard_surface_node, displacement_node):
    # Keep base weight consistent regardless of source metadata.
    _set_first_parm_value(standard_surface_node, ("base", "baseWeight", "base_weight"), 1.0)

    if displacement_node is not None:
        _set_first_parm_value(displacement_node, OCTANE_DISPLACEMENT_PARMS["level_of_detail"], 4096)


def _create_2d_transform_node(vopnet):
    import hou

    for node_type in (OCTANE_NODE_TYPES["transform_2d"], "NT_TRANSFORM_2D", "octane_transform_2d"):
        try:
            return vopnet.createNode(node_type, "2D_transformation1")
        except hou.OperationFailed:
            continue
    return None


def _snapshot_sibling_positions(parent_node):
    snapshot = {}
    try:
        for child in parent_node.children():
            snapshot[child.path()] = child.position()
    except Exception:
        pass
    return snapshot


def _restore_sibling_positions(parent_node, snapshot, excluded_nodes=()):
    excluded_paths = set()
    for node in excluded_nodes or ():
        if node is None:
            continue
        try:
            excluded_paths.add(node.path())
        except Exception:
            continue

    for child in parent_node.children():
        try:
            child_path = child.path()
            if child_path in excluded_paths:
                continue
            old_pos = snapshot.get(child_path)
            if old_pos is not None:
                child.setPosition(old_pos)
        except Exception:
            continue


def _build_material_data_from_texture(texture_path):
    normalized_path = os.path.normpath(texture_path)
    if not os.path.isfile(normalized_path):
        raise ValueError("Dropped texture path does not exist.")

    folder_path = os.path.dirname(normalized_path)
    dropped_filename = os.path.basename(normalized_path)
    dropped_stem = os.path.splitext(dropped_filename)[0]

    def to_tokens(name):
        return [token for token in re.split(r"[^a-z0-9]+", name.lower()) if token]

    def infer_base_name(stem):
        tokens = to_tokens(stem)
        if not tokens:
            return stem.lower()

        all_suffixes = []
        for identifiers in TEXTURE_TYPES.values():
            all_suffixes.extend(identifiers)
        all_suffixes.extend(THUMBNAIL_IDENTIFIERS)
        normalized_suffixes = {suffix.lower() for suffix in all_suffixes}

        if tokens[-1] in normalized_suffixes and len(tokens) > 1:
            tokens = tokens[:-1]
        return "_".join(tokens)

    dropped_base = infer_base_name(dropped_stem)
    inferred_maps = {}
    try:
        for sibling in os.listdir(folder_path):
            sibling_path = os.path.join(folder_path, sibling)
            if not os.path.isfile(sibling_path):
                continue
            if os.path.splitext(sibling)[1].lower() not in VALID_EXTENSIONS:
                continue

            sibling_type = classify_texture_type(sibling)
            if sibling_type == "unknown":
                continue

            sibling_base = infer_base_name(os.path.splitext(sibling)[0])
            if sibling_base != dropped_base:
                continue

            if sibling_type not in inferred_maps:
                inferred_maps[sibling_type] = sibling_path
    except Exception:
        inferred_maps = {}

    if inferred_maps:
        return {
            "name": os.path.basename(folder_path) or dropped_stem,
            "path": folder_path,
            "thumbnail": normalized_path,
            "maps": inferred_maps,
        }

    folder_material = Material(folder_path)
    if folder_material.represents_valid_material():
        data = folder_material.to_dict()
        if not data.get("name"):
            data["name"] = os.path.splitext(os.path.basename(normalized_path))[0]
        return data

    texture_type = classify_texture_type(dropped_filename)
    if texture_type == "unknown":
        texture_type = "albedo"

    base_name = dropped_stem
    return {
        "name": base_name,
        "path": folder_path,
        "thumbnail": normalized_path,
        "maps": {texture_type: normalized_path},
    }


def build_material_from_texture_drop(parent_node, position, texture_path):
    import hou
    import os
    sibling_positions = _snapshot_sibling_positions(parent_node)
    
    # If dropped inside a material builder, just create an image node!
    try:
        node_type = parent_node.type().name()
        if "vopnet" in node_type.lower() or "materialbuilder" in node_type.lower() or parent_node.type().category().name() == "Vop":
            try:
                texture_node = parent_node.createNode(OCTANE_NODE_TYPES["tex_image"], "Image")
            except hou.OperationFailed:
                try:
                    texture_node = parent_node.createNode("octane_image", "Image")
                except hou.OperationFailed:
                    # Generic fallback if not Octane
                    texture_node = parent_node.createNode("texture", "Image")
                    
            texture_node.setPosition(position)
            
            # Set the filename
            for parm_name in ("File", "A_FILENAME", "filename", "textureFile", "file"):
                parm = texture_node.parm(parm_name)
                if parm is not None:
                    parm.set(texture_path)
                    break
                    
            nice_name = os.path.splitext(os.path.basename(texture_path))[0]
            # Replace invalid chars with underscore
            nice_name = "".join([c if c.isalnum() else "_" for c in nice_name])
            try: texture_node.setName(nice_name, unique_name=True)
            except: pass
            _restore_sibling_positions(parent_node, sibling_positions, excluded_nodes=(texture_node,))
            return texture_node
    except Exception as e:
        print("Failed to create standalone image node:", e)
        _restore_sibling_positions(parent_node, sibling_positions)
        
    material_data = _build_material_data_from_texture(texture_path)
    build_material(parent_node, position, material_data)


def build_material(parent_node, position, material_data):
    """
    Build an Octane material builder from material data in a material network context.
    """
    import hou

    if not _is_material_context(parent_node):
        hou.ui.displayMessage("Please drop into a Material Network (/mat or materiallibrary).")
        return None

    material_name = material_data.get("name", "New_Material")
    material_name = hou.text.alphaNumeric(material_name) or "New_Material"
    maps = material_data.get("maps", {})
    metadata = material_data.get("metadata", {})
    sibling_positions = _snapshot_sibling_positions(parent_node)
    vopnet = None

    try:
        try:
            vopnet = parent_node.createNode(OCTANE_NODE_TYPES["vopnet"], node_name=material_name)
        except hou.OperationFailed as exc:
            try:
                # Maybe the internal name is different in this Houdini/Octane version
                # Let's try the other common Octane vopnet name
                vopnet = parent_node.createNode(OCTANE_NODE_TYPES["vopnet_alt"], node_name=material_name)
            except hou.OperationFailed as exc2:
                hou.ui.displayMessage(
                    "Failed to create octane_vopnet. Make sure Octane is installed and /mat is active.\n\n{0}\n{1}".format(exc, exc2)
                )
                return None

        vopnet.setPosition(position)

        for child in list(vopnet.children()):
            child.destroy()

        try:
            out_node = vopnet.createNode(OCTANE_NODE_TYPES["out_material"], "octane_material1")
        except hou.OperationFailed:
            out_node = vopnet.createNode("octane_material", "octane_material1")
            
        out_node.setPosition(hou.Vector2(3, 0))

        try:
            standard_surface = vopnet.createNode(OCTANE_NODE_TYPES["standard_surface"], "Standard_Surface")
        except hou.OperationFailed:
            standard_surface = vopnet.createNode("octane_standard_surface", "Standard_Surface")
            
        standard_surface.setPosition(hou.Vector2(0, 0))
        out_node.setInput(0, standard_surface, 0)

        displacement_node = None
        if maps.get("displacement"):
            try:
                displacement_node = vopnet.createNode(OCTANE_NODE_TYPES["displacement"], "Displacement1")
            except hou.OperationFailed:
                displacement_node = vopnet.createNode("octane_displacement", "Displacement1")
                 
            displacement_node.setPosition(hou.Vector2(1.5, -4))
            _connect_input_by_name(standard_surface, OCTANE_STANDARD_SURFACE_INPUTS["displacement"], displacement_node)
            _set_first_parm_value(displacement_node, OCTANE_DISPLACEMENT_PARMS["level_of_detail"], 4096)
            _set_first_parm_value(displacement_node, OCTANE_DISPLACEMENT_PARMS["mid_level"], 0.5)

        y_offset = 4.0
        x_offset = -4.0
        transform_2d_node = _create_2d_transform_node(vopnet) if maps else None
        map_nodes = {}
        if transform_2d_node is not None:
            transform_2d_node.setPosition(hou.Vector2(x_offset - 2.5, 0))

        for map_key, texture_path in maps.items():
            map_config = MAP_TYPES_TO_INPUTS.get(map_key)
            nice_name = map_key.capitalize()

            if not map_config:
                # Unknown texture - create node but don't connect
                try:
                    texture_node = vopnet.createNode(OCTANE_NODE_TYPES["tex_image"], nice_name)
                except hou.OperationFailed:
                    texture_node = vopnet.createNode("octane_image", nice_name)
                
                try: texture_node.setName(nice_name, unique_name=True)
                except: pass
                 
                _set_texture_file_parm(texture_node, texture_path)
                if transform_2d_node is not None:
                    _connect_input_by_name(texture_node, OCTANE_TEXTURE_INPUTS["transform"], transform_2d_node)
                texture_node.setPosition(hou.Vector2(x_offset, y_offset))
                map_nodes[map_key] = texture_node
                y_offset -= 2.5
                continue

            target_input_name, node_type, use_srgb = map_config
            
            # Format nice name for specific recognized types
            nice_name = target_input_name[:1].upper() + target_input_name[1:]
            if nice_name == "BaseColor": nice_name = "Base_Color"
            elif map_key == "diffuseroughness": nice_name = "Diffuse_Roughness"
            elif map_key == "specularroughness": nice_name = "Specular_Roughness"
            elif nice_name == "DiffuseRoughness": nice_name = "Diffuse_Roughness"
            elif nice_name == "Transmission": nice_name = "Scattering_Weight"
            elif nice_name == "SheenColor": nice_name = "Sheen_Color"
            elif nice_name == "SheenRoughness": nice_name = "Sheen_Roughness"
            
            try:
                texture_node = vopnet.createNode(node_type, nice_name)
            except hou.OperationFailed:
                # Fallback if `octane::NT_TEX_IMAGE` or `octane::NT_TEX_FLOATIMAGE` fail
                fallback_type = "octane_image" if "IMAGE" in node_type else "octane_floatimage"
                texture_node = vopnet.createNode(fallback_type, nice_name)
                
            try: texture_node.setName(nice_name, unique_name=True)
            except: pass
                 
            _set_texture_file_parm(texture_node, texture_path)
            _set_texture_color_space(texture_node, use_srgb)
            if transform_2d_node is not None:
                _connect_input_by_name(texture_node, OCTANE_TEXTURE_INPUTS["transform"], transform_2d_node)

            texture_node.setPosition(hou.Vector2(x_offset, y_offset))
            map_nodes[map_key] = texture_node
            y_offset -= 2.5

            if map_key == "displacement" and displacement_node is not None:
                displacement_node.setInput(0, texture_node, 0)
                continue

            _connect_input_by_name(standard_surface, target_input_name, texture_node)

        _apply_gsg_metadata(standard_surface, map_nodes, metadata)
        _enforce_required_defaults(standard_surface, displacement_node)

        vopnet.layoutChildren()
        vopnet.setSelected(True, clear_all_selected=True)
        _safe_status("Created Octane Material: {0}".format(material_name))
        return vopnet
    finally:
        _restore_sibling_positions(parent_node, sibling_positions, excluded_nodes=(vopnet,))
