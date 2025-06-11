from datetime import datetime
import face_recognition
import pickle
import os
from PIL import Image
from tqdm import tqdm
import numpy as np

def index_faces(image_paths, index_file=None, max_faces_per_image=4, progress_callback=None, preview_callback=None):
    encoded_faces = []
    for idx, image_path in enumerate(tqdm(image_paths, desc="Indexing faces", unit="img")):
        filename = os.path.basename(image_path)
        name_prefix = os.path.splitext(filename)[0]

        try:
            image = face_recognition.load_image_file(image_path)
            face_locations = face_recognition.face_locations(image)
            encodings = face_recognition.face_encodings(image, face_locations)

            if not encodings:
                print(f"[Warning] No face found in {filename}, (face_locations: {face_locations})")
                if progress_callback:
                    progress_callback(idx + 1, len(image_paths))
                if preview_callback:
                    preview_callback(None, image_path, "NO FACES FOUND")
                continue

            for i, encoding in enumerate(encodings[:max_faces_per_image]):
                encoded_faces.append({
                    "name": f"{name_prefix}_{i}",
                    "encoding": encoding,
                    "image_path": image_path,
                    "location": face_locations[i]
                })

                if preview_callback:
                    top, right, bottom, left = face_locations[i]
                    face_image = image[top:bottom, left:right]
                    face_image_np = np.array(face_image)
    
                    preview_callback(face_image_np, image_path, f"{name_prefix}_{i}")
                        
        except Exception as e:
            print(f"Error processing {filename}: {e}")

        # Update progress
        if progress_callback:
            progress_callback(idx + 1, len(image_paths))
    # Generate default index file name if not provided

    if index_file is None: # TODO remove this part and just dont save if it 
        output_dir = os.path.join(os.getcwd(), "faces_indexed")
        os.makedirs(output_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y-%m-%d--%Hh-%Mm-%Ss")
        file_name = f"{len(encoded_faces)}-faces-{timestamp}.pkl"
        index_file = os.path.join(output_dir, file_name)

    # Save the index
    with open(index_file, "wb") as f:
        pickle.dump(encoded_faces, f)

    print(f"\n✅ Done! {len(encoded_faces)} face(s) saved to '{index_file}'.")