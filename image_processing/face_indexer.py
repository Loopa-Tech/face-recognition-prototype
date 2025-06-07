import face_recognition
import pickle
from tqdm import tqdm
import os
from PIL import Image  # For saving cropped faces

def index_faces(
    image_paths,
    index_file="face_index.pkl",
    max_faces_per_image=4,
    save_faces_preview=False,
    preview_dir="indexedPreview"
):
    encoded_faces = []

    if save_faces_preview:
        os.makedirs(preview_dir, exist_ok=True)

    for image_path in tqdm(image_paths, desc="Indexing faces", unit="img"):
        filename = os.path.basename(image_path)
        name_prefix = os.path.splitext(filename)[0]

        image = face_recognition.load_image_file(image_path)
        encodings = face_recognition.face_encodings(image)
        face_locations = face_recognition.face_locations(image) 

        if not encodings:
            print(f"[Warning] No face found in {filename}")
            continue

        for i, encoding in enumerate(encodings[:max_faces_per_image]):
            encoded_faces.append({
                "name": f"{name_prefix}_{i}",
                "encoding": encoding,
                "image_path": image_path,
                "location": face_locations[i]  # (top, right, bottom, left)
            })

            if save_faces_preview:
                # Crop face from the original image using face_locations
                top, right, bottom, left = face_locations[i]
                face_image = image[top:bottom, left:right]
                pil_img = Image.fromarray(face_image)

                # Save with a clear filename
                save_path = os.path.join(preview_dir, f"{name_prefix}_{i}.jpg")
                pil_img.save(save_path)

    with open(index_file, "wb") as f:
        pickle.dump(encoded_faces, f)

    print(f"\n✅ Done! {len(encoded_faces)} face(s) saved to '{index_file}'.")
    if save_faces_preview:
        print(f"✅ Cropped face previews saved to folder '{preview_dir}'.")
