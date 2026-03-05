# GSG Mat Lib

Simple Houdini Python Panel for browsing and dropping **materials**, **textures**, and **HDRIs** into a material network.

![GSG Mat Lib UI](docs/ui.png)

## Includes
- Materials view
- Textures view
- HDRIs view
- Drag and drop materials into supported networks
- Drag and drop textures/HDRIs directly onto compatible file parameters
- Reads `.gsgm` material metadata and applies supported values to the Octane shader on import/drop
- Right-click `Copy File Path` / `Copy Material Path`
- Preview thumbnail caching
- On-demand thumbnail cache generation for heavy image formats
- More reliable drag release handling when dropping outside panel bounds
- Improved material detail thumbnails (per-map preview correctness)
- Metadata-only materials (for example glass entries with preview + `.gsgm`) are supported
- Octane material builder adds a shared `2D Transform` node and connects it to texture image nodes
- Octane texture displacement defaults: `Level of detail` = `4096x4096`, `Mid level` = `0.5`

## Install (quick)
1. Copy this `HoudiniMaterialGallery` folder to your machine.
2. Edit `HoudiniMaterialGallery.json` and set:
   - `HMG_LOCATION` to your local `HoudiniMaterialGallery` folder path.
3. Put `HoudiniMaterialGallery.json` into your Houdini `packages` folder.
4. Restart Houdini.
5. Open the Python Panel: `GSG Mat Lib`.

## Notes
- Supported library tabs: `Materials`, `Textures`, `HDRIs`.
- Supports **Greyscale Gorilla** materials, textures, and HDRIs.
