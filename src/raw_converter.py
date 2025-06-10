import rawpy
import imageio
import os
from tqdm import tqdm

def convert_raw_to_jpeg(raw_path, jpeg_path):
    try:
        with rawpy.imread(raw_path) as raw:
            rgb = raw.postprocess()
            imageio.imwrite(jpeg_path, rgb)
    except Exception as e:
        print(f"Failed to convert {raw_path}: {e}")

def convert_all_raw_images(raw_image_paths, raw_base='photos/raw', output_base='photos/raw_converted'):
    for raw_path in tqdm(raw_image_paths, desc="Converting RAW images", unit="img"):
        rel_path = os.path.relpath(raw_path, raw_base)
        rel_path_jpg = os.path.splitext(rel_path)[0] + '.jpg'
        jpeg_path = os.path.join(output_base, rel_path_jpg)
        os.makedirs(os.path.dirname(jpeg_path), exist_ok=True)
        convert_raw_to_jpeg(raw_path, jpeg_path)
