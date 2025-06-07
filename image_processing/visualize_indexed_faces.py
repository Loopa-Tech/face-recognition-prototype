import os
import pickle
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import face_recognition

def visualize_indexed_faces(index_file="face_index.pkl", output_dir="visualized_faces"):
    """
    Create visualizations of the original images with bounding boxes around indexed faces.
    
    Args:
        index_file (str): Path to the face index pickle file
        output_dir (str): Directory to save the visualized images
    """
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # Load the face index
    try:
        with open(index_file, "rb") as f:
            encoded_faces = pickle.load(f)
    except FileNotFoundError:
        print(f"Error: Face index file '{index_file}' not found.")
        return
        
    # Group faces by image_path
    images_dict = {}
    for face in encoded_faces:
        image_path = face["image_path"]
        if image_path not in images_dict:
            images_dict[image_path] = []
        images_dict[image_path].append(face)
    
    print(f"Processing {len(images_dict)} images...")
    
    # Process each image
    for image_path, faces in images_dict.items():
        if not os.path.exists(image_path):
            print(f"Warning: Image file {image_path} not found, skipping.")
            continue
            
        # Load the image
        image = cv2.imread(image_path)
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)  # Convert from BGR to RGB
        pil_image = Image.fromarray(image)
        draw = ImageDraw.Draw(pil_image)
        
        # Set up font for labels
        try:
            font = ImageFont.truetype("arial.ttf", 20)
        except IOError:
            font = ImageFont.load_default()
            
        # Draw bounding box and label for each face
        for face in faces:
            top, right, bottom, left = face["location"]
            face_name = face["name"]
            
            # Draw a box around the face
            draw.rectangle(((left, top), (right, bottom)), outline=(0, 255, 0), width=3)
            
            # Draw label
            text_width, text_height = draw.textsize(face_name, font=font) if hasattr(draw, "textsize") else (100, 20)
            draw.rectangle(((left, bottom - text_height - 10), (left + text_width + 10, bottom)), fill=(0, 255, 0))
            draw.text((left + 5, bottom - text_height - 5), face_name, font=font, fill=(0, 0, 0))
        
        # Save the output image
        filename = os.path.basename(image_path)
        output_path = os.path.join(output_dir, f"visualized_{filename}")
        pil_image.save(output_path)
        
    print(f"✅ Done! Visualized images saved to '{output_dir}'.")

if __name__ == "__main__":
    # You can change these parameters as needed
    visualize_indexed_faces(index_file="face_index.pkl", output_dir="visualized_faces")