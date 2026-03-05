import os
import sys
import hashlib
try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

lib_dir = sys.argv[1]
cache_dir = os.path.join(os.path.expanduser("~"), ".houdini", "gsg_thumb_cache")
if not os.path.exists(cache_dir):
    os.makedirs(cache_dir, exist_ok=True)

print("=" * 50)
print("GSG Thumbnail Cache Generator")
print("Cache dir:", cache_dir)
print("Scanning library...")

from HoudiniMaterialGallery.material_library import Material

# First pass: count total items to process
to_process = []
for root, dirs, files in os.walk(lib_dir):
    if '.thumbnails' in dirs:
         dirs.remove('.thumbnails')
    if any(f.lower().endswith(('.png', '.jpg', '.jpeg', '.exr', '.tif', '.tiff', '.tga')) for f in files):
        mat = Material(root)
        if mat.thumbnail and os.path.exists(mat.thumbnail):
             orig_path = mat.thumbnail
             path_hash = hashlib.md5(os.path.normpath(orig_path).encode()).hexdigest()[:12]
             basename = os.path.splitext(os.path.basename(orig_path))[0]
             fast_path = os.path.join(cache_dir, f"{basename}_{path_hash}.jpg")
             if not os.path.exists(fast_path):
                  to_process.append((orig_path, fast_path))

total = len(to_process)
if total == 0:
    print("All previews already cached! Nothing to do.")
    sys.exit(0)

print(f"Found {total} uncached previews. Starting...")
print("=" * 50)

success = 0
failed = 0
for i, (orig_path, fast_path) in enumerate(to_process, 1):
    pct = int(i / total * 100)
    bar = '#' * (pct // 5) + '-' * (20 - pct // 5)
    print(f"[{bar}] {i}/{total} ({pct}%) - {os.path.basename(orig_path)}")
    try:
        if HAS_PIL:
            try:
                img = Image.open(orig_path)
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                img.thumbnail((300, 300))
                img.save(fast_path, 'JPEG', quality=85)
                success += 1
                continue
            except:
                pass
        import hou
        hou.hscript(f'imgconvert -s 300 300 "{orig_path}" "{fast_path}"')
        success += 1
    except Exception as e:
        failed += 1
        print(f"  FAILED: {e}")

print("=" * 50)
print(f"DONE! Cached: {success} | Failed: {failed} | Total: {total}")
print("Reload the GSG Gallery to see updated thumbnails.")
print("=" * 50)