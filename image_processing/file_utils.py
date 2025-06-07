import os

def collect_image_paths(base_folder, extensions):
    image_paths = []
    for root, _, files in os.walk(base_folder):
        for file in files:
            if any(file.lower().endswith(ext) for ext in extensions):
                image_paths.append(os.path.join(root, file))
    return image_paths
