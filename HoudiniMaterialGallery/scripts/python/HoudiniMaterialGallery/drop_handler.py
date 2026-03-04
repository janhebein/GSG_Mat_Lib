def _wrap_drop_script(payload_expression, builder_function_name):
    # Pass payload expression via the formatting so the string is properly quoted 
    # and safely passed to Houdini's Python interpreter
    return f"""
import hou
import traceback

try:
    from HoudiniMaterialGallery.octane_builder import {builder_function_name}

    pane = hou.ui.paneTabUnderCursor()
    if pane and pane.type() == hou.paneTabType.NetworkEditor:
        network_node = pane.pwd()
        
        try:
            pos = pane.cursorPosition()
        except Exception:
            try:
                pos = pane.visibleBounds().center()
            except Exception:
                pos = hou.Vector2(0, 0)

        # The payload expression contains the raw dictionary or string from `repr()`
        
        # We need to gracefully accept the raw repr string coming from Houdini's drop handler execution
        # using a simple hack where string payloads will be fully escaped but dict payloads evaluate directly.
        try:
             payload = {payload_expression}
             hou.ui.displayMessage("Parsed Payload as Dict! Type: " + str(type(payload)))
        except Exception as e1:
             # Houdini drop script string parsing throws errors resolving raw paths sometimes
             # so we fallback to a string injection format using raw string representation
             try:
                 payload_raw = r'''{payload_expression}'''
                 payload = payload_raw.strip("'").strip('"')
                 hou.ui.displayMessage("Parsed Payload as String! " + str(payload))
             except Exception as e2:
                 hou.ui.displayMessage("Both payload parsers failed! E1: " + str(e1) + " E2: " + str(e2))
             
        # Check if dropped onto a node
        dropped_node = None
        for child in network_node.children():
            # Rough bounds check for dropped node
            n_pos = child.position()
            n_size = child.size()
            
            MARGIN = 0.5
            if (pos[0] >= (n_pos[0] - MARGIN) and pos[0] <= (n_pos[0] + n_size[0] + MARGIN) and
                pos[1] >= (n_pos[1] - n_size[1] - MARGIN) and pos[1] <= (n_pos[1] + MARGIN)):
                dropped_node = child
                break
                
        # If payload is a texture path AND we dropped it ON an existing node
        if type(payload) is str and dropped_node:
            node_type = dropped_node.type().name()
            # If it's an image node type, populate its file parm directly
            if "IMAGE" in node_type or "image" in node_type.lower() or "file" in node_type.lower() or "tex" in node_type.lower():
                # Common Octane node parm names for textures
                for parm_name in ("File", "A_FILENAME", "filename", "textureFile"):
                    parm = dropped_node.parm(parm_name)
                    if parm is not None:
                        parm.set(payload)
                        print(f"Mapped {{payload}} -> {{dropped_node.name()}}")
                        break
            else:
                 # Otherwise let it create a new material structure as usual
                 {builder_function_name}(network_node, pos, payload)
        else:
            try:
                {builder_function_name}(network_node, pos, payload)
            except Exception as e:
                try:
                    sticky = network_node.createStickyNote()
                    sticky.setText("Failed to build material:\\n{{}}".format(str(e)))
                    sticky.setPosition(pos)
                    sticky.setSize(hou.Vector2(5, 2))
                except Exception:
                    pass
                print("Drop error:", e)
                traceback.print_exc()
                
    else:
        hou.ui.displayMessage("Drop Error: Not dropped into a Network Editor, or the cursor focus was lost!")
except Exception as e:
    try:
        hou.ui.displayMessage("Gallery Drop Error: {{}}".format(e))
    except Exception:
        pass
    traceback.print_exc()
"""
def generate_drop_script(material_dict):
    """
    Build script payload for dropping a full material item.
    """
    return _wrap_drop_script(repr(material_dict), "build_material")


def generate_texture_drop_script(texture_path):
    """
    Build script payload for dropping a single texture/thumbnail item.
    """
    return _wrap_drop_script(repr(texture_path), "build_material_from_texture_drop")
