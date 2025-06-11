import rawpy
import imageio
import os
from tqdm import tqdm

def convert_raw_to_jpeg(raw_path, jpeg_path):
    try:
        with rawpy.imread(raw_path) as raw:
            rgb = raw.postprocess()
            imageio.imwrite(jpeg_path, rgb)
        return jpeg_path
    except Exception as e:
        print(f"Failed to convert {raw_path}: {e}")
        return None

def convert_all_raw_images(raw_image_paths, raw_base=None, output_base='tmp_raw_converted'):
    converted_paths = []
    for raw_path in tqdm(raw_image_paths, desc="Converting RAW images", unit="img"):
        if raw_base is None:
            # Use the parent directory of the first image as the base
            raw_base = os.path.dirname(os.path.dirname(raw_path))
        
        rel_path = os.path.relpath(raw_path, raw_base)
        rel_path_jpg = os.path.splitext(rel_path)[0] + '.jpg'
        jpeg_path = os.path.join(output_base, rel_path_jpg)
        os.makedirs(os.path.dirname(jpeg_path), exist_ok=True)
        converted_path = convert_raw_to_jpeg(raw_path, jpeg_path)
        if converted_path:
            converted_paths.append(converted_path)
    
    return converted_paths
