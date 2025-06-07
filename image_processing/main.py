from file_utils import collect_image_paths
from raw_converter import convert_all_raw_images
from face_indexer import index_faces
from visualize_indexed_faces import visualize_indexed_faces
import argparse

def main():
    parser = argparse.ArgumentParser(description="Process and index faces in images")
    parser.add_argument("--index", action="store_true", help="Index faces in images")
    parser.add_argument("--visualize", action="store_true", help="Visualize indexed faces")
    parser.add_argument("--output-dir", type=str, default="visualized_faces", help="Output directory for visualized images")
    parser.add_argument("--index-file", type=str, default="face_index.pkl", help="Path to face index file")
    parser.add_argument("--limit", type=int, default=None, help="Limit the number of images to process")
    
    args = parser.parse_args()
    
    # If no arguments provided, run both index and visualize
    if not (args.index or args.visualize):
        args.index = True
        args.visualize = True
    
    raw_extensions = ['.nef', '.arw', '.dng'] # TODO: why not working with '.cr2'?
    image_extensions = ['.jpg', '.jpeg', '.png']
    
    if args.index:
        image_paths = collect_image_paths('photos/jpg-png', image_extensions)
        
        # raw_image_paths = collect_image_paths('photos/raw', raw_extensions)
        # convert_all_raw_images(raw_image_paths)
        # image_paths += collect_image_paths('photos/raw_converted', image_extensions)
        
        if args.limit:
            image_paths = image_paths[:args.limit]
            
        print(f"Found {len(image_paths)} image files.")
        
        index_faces(image_paths, index_file=args.index_file, save_faces_preview=True)
    
    if args.visualize:
        visualize_indexed_faces(index_file=args.index_file, output_dir=args.output_dir)
        
if __name__ == "__main__":
    main()
