import pickle
import face_recognition
import sys

import face_recognition
def search_face(image_path, index_file="face_index.pkl", tolerance=0.6):
    with open(index_file, "rb") as f:
        known_faces = pickle.load(f)

    new_image = face_recognition.load_image_file(image_path)
    new_encodings = face_recognition.face_encodings(new_image)

    if not new_encodings:
        print("❌ No face found in the input image.")
        return []

    new_encoding = new_encodings[0]
    known_encodings = [face["encoding"] for face in known_faces]
    names = [face["name"] for face in known_faces]

    distances = face_recognition.face_distance(known_encodings, new_encoding)

    # Collect all matches within tolerance
    matched = []
    for name, distance in zip(names, distances):
        if distance <= tolerance:
            matched.append((name, distance))

    if matched:
        print("✅ Matches found:")
        for name, dist in sorted(matched, key=lambda x: x[1]):
            print(f" - {name} (distance: {dist:.4f})")
    else:
        print("❌ No match found under tolerance.")

    return matched

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python search_face.py <image_path>")
        sys.exit(1)

    image_path = sys.argv[1]

    # Import the updated search_face function from above or your module
    matches = search_face(image_path)

    if matches:
        import matches_gui
        matches_gui.show_matches_gui(image_path, matches)
    else:
        print("No matches to display.")