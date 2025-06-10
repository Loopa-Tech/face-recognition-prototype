import argparse
import os
from utils.file_utils import collect_image_paths
from raw_converter import convert_all_raw_images
from face_indexer import index_faces

def main():
    parser = argparse.ArgumentParser(description="Process and index faces in images")
    parser.add_argument("--index", action="store_true", help="Index faces in images")
    parser.add_argument("--convert", action="store_true", help="Convert RAW to JPG")
    parser.add_argument("--folder", type=str, default="photos", help="Base photo folder")
    parser.add_argument("--index-file", type=str, default="face_index.pkl", help="Output index file")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of images")

    args = parser.parse_args()
    raw_ext = ['.nef', '.arw', '.dng']
    img_ext = ['.jpg', '.jpeg', '.png']

    if args.convert:
        raw_paths = collect_image_paths(os.path.join(args.folder, 'raw'), raw_ext)
        convert_all_raw_images(raw_paths)

    if args.index:
        img_paths = collect_image_paths(os.path.join(args.folder, 'jpg-png'), img_ext)
        if args.limit:
            img_paths = img_paths[:args.limit]
        index_faces(img_paths, index_file=args.index_file, save_faces_preview=False)

if __name__ == "__main__":
    main()
