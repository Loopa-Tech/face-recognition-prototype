import pickle
import face_recognition
import tkinter as tk
from PIL import Image, ImageTk, ImageDraw

def show_matches_gui(query_image_path, matches, index_file="face_index.pkl"):
    import os

    with open(index_file, "rb") as f:
        known_faces = pickle.load(f)

    root = tk.Tk()
    root.title("Face Search Results")
    root.geometry("700x800")

    # --- QUERY FACE DISPLAY ---
    query_img = face_recognition.load_image_file(query_image_path)
    query_locations = face_recognition.face_locations(query_img)
    if not query_locations:
        print("No face found in query image for display.")
        return
    top, right, bottom, left = query_locations[0]
    face_crop = query_img[top:bottom, left:right]
    pil_face = Image.fromarray(face_crop).resize((150, 150))
    query_photo = ImageTk.PhotoImage(pil_face)

    header = tk.Label(root, text="Query Face", font=("Arial", 16, "bold"))
    header.pack(pady=(10, 2))
    tk.Label(root, image=query_photo).pack()
    tk.Label(root, text="Matches Found:", font=("Arial", 14)).pack(pady=(12, 6))

    # --- SCROLLABLE FRAME ---
    container = tk.Frame(root)
    canvas = tk.Canvas(container, height=650)
    scrollbar = tk.Scrollbar(container, orient="vertical", command=canvas.yview)
    scrollable_frame = tk.Frame(canvas)

    scrollable_frame.bind(
        "<Configure>",
        lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
    )

    canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)

    container.pack(fill="both", expand=True)
    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    # --- DISPLAY EACH MATCH ---
    for name, dist in sorted(matches, key=lambda x: x[1]):
        match_data = next((f for f in known_faces if f["name"] == name), None)
        if not match_data:
            continue

        img_path = match_data["image_path"]
        location = match_data["location"]

        try:
            full_img = Image.open(img_path).convert("RGB")
        except FileNotFoundError:
            print(f"Image file not found: {img_path}")
            continue

        draw = ImageDraw.Draw(full_img)
        top, right, bottom, left = location
        draw.rectangle([left, top, right, bottom], outline="green", width=4)

        display_width = 500
        display_height = int(display_width * full_img.height / full_img.width)
        full_img_resized = full_img.resize((display_width, display_height))
        img_tk = ImageTk.PhotoImage(full_img_resized)

        # Frame for each result
        frame = tk.Frame(scrollable_frame, pady=10)
        frame.pack()

        img_label = tk.Label(frame, image=img_tk)
        img_label.image = img_tk
        img_label.pack()

        # Confidence label
        label = tk.Label(
            frame,
            text=f"Name: {name}\nDistance: {dist:.4f}",
            font=("Arial", 11),
            justify="center",
            padx=10,
            pady=4
        )
        label.pack()

    root.mainloop()
