"""Octane constants used by the material builder."""

OCTANE_NODE_TYPES = {
    "vopnet": "octane_vopnet",
    "vopnet_alt": "octane::octane_vopnet",
    "out_material": "octane::NT_OUT_MATERIAL",
    "standard_surface": "octane::NT_MAT_STANDARD_SURFACE",
    "displacement": "octane::NT_DISPLACEMENT",
    "transform_2d": "octane::NT_TRANSFORM_2D",
    "tex_image": "octane::NT_TEX_IMAGE",
    "tex_float_image": "octane::NT_TEX_FLOATIMAGE",
}

OCTANE_STANDARD_SURFACE_INPUTS = {
    "base_color": "baseColor",
    "diffuse_roughness": "diffuseRoughness",
    "roughness": "roughness",
    "metallic": "metallic",
    "normal": "normal",
    "displacement": "displacement",
    "ambient_occlusion": "ambientocclusion",
    "opacity": "opacity",
    "emission_color": "emissionColor",
    "specular": "specular",
    "transmission": "transmission",
    "sheen_color": "sheenColor",
    "sheen_roughness": "sheenRoughness",
}

OCTANE_TEXTURE_INPUTS = {
    "transform": "transform",
}

OCTANE_COLOR_SPACES = {
    "srgb": "NAMED_COLOR_SPACE_SRGB",
    "linear": "NAMED_COLOR_SPACE_OTHER",
}

OCTANE_DISPLACEMENT_PARMS = {
    "level_of_detail": ("levelOfDetail", "levelofdetail"),
    "mid_level": ("black_level", "midLevel", "mid_level"),
}
