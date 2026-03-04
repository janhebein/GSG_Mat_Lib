# GSG Mat Lib

Simple Houdini Python Panel for browsing and dropping **materials**, **textures**, and **HDRIs** into a material network.

![GSG Mat Lib UI](docs/ui.png)

## Includes
- Materials view
- Textures view
- HDRIs view
- Drag and drop materials
- Drag and drop textures/HDRIs to node file parameters
- Right-click `Copy File Path` / `Copy Material Path`
- Preview thumbnail caching
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
- Supported library tabs right now: `Materials`, `Textures`, `HDRIs`.
- Supports only **Greyscale Gorilla** materials, textures, and HDRIs.
- Huge thanks to [oakztream](https://github.com/oakztream) for helping and contributing, especially with mapping data and insights that improved the Octane node mapping.
