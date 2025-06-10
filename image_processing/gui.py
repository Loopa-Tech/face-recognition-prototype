import os
import threading
import tkinter as tk
from tkinter import filedialog, ttk
from PIL import Image, ImageTk, ImageOps # Import ImageOps for borders
import numpy as np
from face_indexer import index_faces
from raw_converter import convert_all_raw_images
from utils.file_utils import collect_image_paths

# Define common RAW and standard image extensions
RAW_EXTENSIONS = ['.nef', '.arw', '.dng', '.cr2', '.cr3']
IMG_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.webp']

class FaceIndexerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Face Indexer")

        # Tkinter variables to hold application state
        self.folder_path = tk.StringVar(value="") # No default folder
        self.use_raw_var = tk.BooleanVar(value=False) # Controls whether RAW files are included
        self.show_preview_var = tk.BooleanVar(value=False) # Default not showing the photo section

        # Sets to keep track of selected image paths and image references
        self.selected_images = set() # Stores paths of currently selected images
        self.image_thumbnails = {} # Stores PhotoImage objects for main thumbnails, keyed by path
        self.thumbnail_items = {} # Stores references to the thumbnail frame widgets, keyed by path
        self.face_images = [] # For displaying extracted face previews (from index_faces)

        # Set up the graphical user interface
        self.setup_ui()

        # Initial call to toggle the photo section based on default state
        self.toggle_photo_section()

    def setup_ui(self):
        # Main container frame for padding and overall layout
        main_frame = ttk.Frame(self.root, padding=15)
        main_frame.grid(row=0, column=0, sticky="nsew")
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        # Control Frame for folder selection, options, and main buttons
        control_frame = ttk.LabelFrame(main_frame, text="Folder and Options", padding=10)
        control_frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=10)
        control_frame.grid_columnconfigure(1, weight=1) # Allow entry field to expand

        # Folder path display and entry
        ttk.Label(control_frame, text="Current Folder:").grid(row=0, column=0, sticky="w", pady=2)
        ttk.Entry(control_frame, textvariable=self.folder_path, width=80, state="readonly").grid(row=0, column=1, sticky="ew", padx=5) # Made readonly
        ttk.Button(control_frame, text="Browse & Select Folder", command=self.select_folder_with_dialog).grid(row=0, column=2, padx=5)

        # Checkbox for including RAW files in scans
        ttk.Checkbutton(control_frame, text="Include RAW Files", variable=self.use_raw_var, command=self.scan_folder_for_images).grid(row=1, column=0, sticky="w", pady=5)
        # Checkbox for toggling the visibility of the photo section
        ttk.Checkbutton(control_frame, text="Show Photo Section", variable=self.show_preview_var, command=self.toggle_photo_section).grid(row=1, column=1, sticky="w", pady=5)

        # Main "Index Faces" button
        self.index_btn = ttk.Button(control_frame, text="Index Faces", command=self.run_index_thread)
        self.index_btn.grid(row=1, column=2, pady=10, sticky="ew")

        # Progress bar for indexing operations
        self.progress = ttk.Progressbar(main_frame, orient="horizontal", length=600, mode="determinate")
        self.progress.grid(row=1, column=0, columnspan=2, pady=10, sticky="ew")

        # Image Previews Area - structured for scrollability
        # This frame will be hidden/shown
        self.preview_frame = ttk.LabelFrame(main_frame, text="Image Previews (Click to Select/Deselect)", padding=10)
        # We initially grid it, but toggle_photo_section will manage its visibility
        self.preview_frame.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=10)
        self.preview_frame.grid_rowconfigure(0, weight=1)
        self.preview_frame.grid_columnconfigure(0, weight=1)

        # Canvas with Scrollbar for the main image thumbnails
        self.canvas_scroll_frame = ttk.Frame(self.preview_frame)
        self.canvas_scroll_frame.grid(row=0, column=0, sticky="nsew")
        self.canvas_scroll_frame.grid_rowconfigure(0, weight=1)
        self.canvas_scroll_frame.grid_columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(self.canvas_scroll_frame, bg="#e0e0e0", highlightbackground="#cccccc", highlightthickness=1)
        self.canvas.grid(row=0, column=0, sticky="nsew")

        # Vertical scrollbar for the canvas
        self.scrollbar_y = ttk.Scrollbar(self.canvas_scroll_frame, orient="vertical", command=self.canvas.yview)
        self.scrollbar_y.grid(row=0, column=1, sticky="ns")
        self.canvas.config(yscrollcommand=self.scrollbar_y.set)

        # Bind canvas configure event to update scroll region
        self.canvas.bind('<Configure>', self._on_canvas_configure)

        # Inner frame to hold image thumbnails, placed inside the canvas
        self.inner_canvas_frame = ttk.Frame(self.canvas)
        # Create a window on the canvas to place the inner frame
        self.canvas_window_id = self.canvas.create_window((0, 0), window=self.inner_canvas_frame, anchor="nw")
        # Bind inner frame configure event to update scroll region when content changes
        self.inner_canvas_frame.bind("<Configure>", self._on_inner_frame_configure)


    def _on_canvas_configure(self, event):
        """Updates the canvas scroll region when the canvas itself is resized."""
        # Ensure the inner frame's width matches the canvas width to prevent horizontal scrolling
        self.canvas.itemconfig(self.canvas_window_id, width=event.width)
        self.canvas.config(scrollregion=self.canvas.bbox("all"))

    def _on_inner_frame_configure(self, event):
        """Updates the canvas scroll region when the content (inner frame) changes size."""
        self.canvas.config(scrollregion=self.canvas.bbox("all"))

    def select_folder_with_dialog(self):
        """Opens a file dialog to select a folder and then triggers an image scan."""
        folder = filedialog.askdirectory(initialdir=self.folder_path.get() if self.folder_path.get() else os.getcwd())
        if folder:
            self.folder_path.set(folder)
            self.scan_folder_for_images()

    def scan_folder_for_images(self):
        """Scans the currently set folder path for images based on selected extensions."""
        folder = self.folder_path.get()
        if not folder or not os.path.isdir(folder):
            print(f"Error: Folder '{folder}' does not exist or is inaccessible.")
            # Clear existing previews if folder is invalid
            self.clear_previews()
            return

        all_extensions = IMG_EXTENSIONS[:] # Start with standard image extensions
        if self.use_raw_var.get():
            all_extensions.extend(RAW_EXTENSIONS) # Add RAW extensions if selected

        img_paths = collect_image_paths(folder, all_extensions)

        print(f"Found {len(img_paths)} image(s) in '{folder}' with extensions: {', '.join(all_extensions)}")
        self.display_previews(img_paths)

    def clear_previews(self):
        """Clears all displayed thumbnails and resets selection."""
        for widget in self.inner_canvas_frame.winfo_children():
            widget.destroy()
        self.image_thumbnails.clear()
        self.thumbnail_items.clear()
        self.selected_images = set()
        self.canvas.config(scrollregion=self.canvas.bbox("all")) # Update scroll region after clearing

    def display_previews(self, img_paths):
        """
        Clears existing thumbnails and displays new ones for the given image paths.
        All found images are initially selected.
        """
        self.clear_previews() # Clear previous before displaying new

        # Ensure the photo section is visible when new images are displayed
        self.show_preview_var.set(True)
        self.toggle_photo_section()

        col_count = 6 # Number of columns for thumbnail grid
        thumbnail_size = 100 # Size of the longest side of the thumbnail
        padding_x = 10
        padding_y = 15
        current_row = 0
        current_col = 0

        for path in img_paths:
            try:
                # Load image and create thumbnail, then add border for selection indication
                image = Image.open(path)
                image.thumbnail((thumbnail_size, thumbnail_size))

                img_tk = ImageTk.PhotoImage(image)
                self.image_thumbnails[path] = img_tk # Store PhotoImage to prevent garbage collection

                # Create a frame for each thumbnail to hold image and text label
                thumb_container = ttk.Frame(self.inner_canvas_frame, relief="solid", borderwidth=1, style="Thumbnail.TFrame")
                
                # Label to display the image
                img_label = ttk.Label(thumb_container, image=img_tk, cursor="hand2")
                img_label.pack(pady=5, padx=5)

                # Label to display the filename
                file_name_label = ttk.Label(thumb_container, text=os.path.basename(path), wraplength=thumbnail_size + 20, anchor="center")
                file_name_label.pack(pady=2)

                # Place the thumbnail container in the grid
                thumb_container.grid(row=current_row, column=current_col, padx=padding_x, pady=padding_y, sticky="nsew")
                
                # Store reference to the container for selection styling
                self.thumbnail_items[path] = thumb_container

                # Bind click events to both the container frame and the image label
                thumb_container.bind('<Button-1>', lambda e, p=path: self.toggle_selection(p))
                img_label.bind('<Button-1>', lambda e, p=path: self.toggle_selection(p))

                # Move to the next grid position
                current_col += 1
                if current_col >= col_count:
                    current_col = 0
                    current_row += 1

                # Select all newly displayed images by default
                self.selected_images.add(path)

            except Exception as e:
                print(f"Error loading {path}: {e}")
        
        # Update scroll region and canvas window width after all images are placed
        self.root.update_idletasks() # Ensure all widgets are rendered before calculating bounding box
        self.canvas.config(scrollregion=self.canvas.bbox("all")) # Update the scrollable area
        # Adjust the width of the window holding the inner frame to match canvas width
        self.canvas.itemconfig(self.canvas_window_id, width=self.canvas.winfo_width())

        self.update_thumbnail_borders() # Apply initial selection borders

    def toggle_selection(self, path):
        """Adds or removes an image path from the selected_images set."""
        if path in self.selected_images:
            self.selected_images.remove(path)
        else:
            self.selected_images.add(path)
        self.update_thumbnail_borders() # Update visual feedback for selection

    def update_thumbnail_borders(self):
        """Updates the visual border style of thumbnails based on their selection state."""
        for path, frame_widget in self.thumbnail_items.items():
            if path in self.selected_images:
                frame_widget.config(borderwidth=3, relief="solid") # Thicker border for selected
                frame_widget.configure(style="Selected.TFrame") # Apply selected style
            else:
                frame_widget.config(borderwidth=1, relief="solid") # Thinner border for deselected
                frame_widget.configure(style="Thumbnail.TFrame") # Apply default thumbnail style


    def get_selected_images(self):
        """Returns a list of currently selected image paths."""
        return list(self.selected_images)

    def run_index_thread(self):
        """Starts the face indexing process in a separate thread."""
        image_paths = self.get_selected_images()
        if not image_paths:
            print("No images selected for indexing.")
            return

        # Disable the index button to prevent multiple simultaneous runs
        self.index_btn.config(state="disabled")
        self.progress["value"] = 0 # Reset progress bar

        # Start the indexing task in a new thread to keep the UI responsive
        threading.Thread(target=self.index_faces_task, args=(image_paths,), daemon=True).start()

    def index_faces_task(self, image_paths):
        """
        The main task for indexing faces, potentially including RAW conversion.
        Runs in a separate thread.
        """
        total = len(image_paths)
        if not total:
            self.root.after(0, lambda: self.index_btn.config(state="normal")) # Re-enable button if no images
            return

        self.root.after(0, lambda: self.update_progress(0, total)) # Initialize progress bar

        def on_progress(current, total):
            """Callback for updating progress from the index_faces function."""
            self.root.after(0, lambda: self.update_progress(current, total))

        def preview_callback(image_np, name):
            """Callback for displaying individual face previews from index_faces."""
            self.root.after(0, lambda: self.display_face_preview(image_np, name))

        try:
            processed_image_paths = image_paths
            # Check if RAW conversion is needed for selected images
            if self.use_raw_var.get():
                raw_paths_to_convert = [p for p in image_paths if os.path.splitext(p)[1].lower() in RAW_EXTENSIONS]
                if raw_paths_to_convert:
                    self.root.after(0, lambda: print("Converting RAW images (this may take a moment)..."))
                    # Call the raw converter. Assumes convert_all_raw_images returns paths to converted files.
                    converted_paths = convert_all_raw_images(raw_paths_to_convert)
                    
                    # Replace original raw paths with their converted counterparts for indexing
                    processed_image_paths = [p for p in image_paths if p not in raw_paths_to_convert] + converted_paths
            
            # Call the main face indexing function
            index_faces(processed_image_paths, progress_callback=on_progress, preview_callback=preview_callback)
            self.root.after(0, lambda: print("Indexing complete."))
        except Exception as e:
            self.root.after(0, lambda: print(f"Error during indexing: {e}"))
        finally:
            self.root.after(0, lambda: self.index_btn.config(state="normal")) # Re-enable button

    def update_progress(self, current, total):
        """Updates the progress bar."""
        self.progress["maximum"] = total
        self.progress["value"] = current
        # self.root.update_idletasks() # Generally avoid in fast loops to prevent UI freezing

    def display_face_preview(self, image_np, name):
        """
        Displays a small preview of an extracted face.
        Note: This currently draws on the main canvas at an arbitrary offset.
        For a more robust solution, a dedicated area for face previews might be better.
        """
        pil_img = Image.fromarray(image_np)
        pil_img.thumbnail((100, 100))
        img = ImageTk.PhotoImage(pil_img)
        self.face_images.append(img)  # Keep reference to prevent garbage collection

        # Calculate position for face preview (simple layout to avoid immediate overlap)
        # This will wrap images based on canvas width, below the main image previews.
        x_offset = (len(self.face_images) - 1) % 6 * 110 # 6 images per row, 110px spacing
        y_offset = (len(self.face_images) - 1) // 6 * 130 # 130px row height for faces
        
        # Place the face preview and its name on the main canvas
        # The 420 is an arbitrary y-offset to place these below the main image previews.
        self.canvas.create_image(x_offset + 10, y_offset + 420, image=img, anchor="nw")
        self.canvas.create_text(x_offset + 60, y_offset + 530, text=name, anchor="n", font=("Arial", 8))
        self.canvas.config(scrollregion=self.canvas.bbox("all")) # Update scroll region to include new faces

    def toggle_photo_section(self):
        """Hides or shows the main image preview frame based on the checkbox state."""
        if self.show_preview_var.get():
            self.preview_frame.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=10)
            self.root.grid_rowconfigure(2, weight=1) # Give weight when visible
        else:
            self.preview_frame.grid_forget()
            self.root.grid_rowconfigure(2, weight=0) # Remove weight when hidden


def run_gui():
    """Initializes the Tkinter root window and runs the application."""
    root = tk.Tk()
    
    # Configure ttk styles for a modern look
    style = ttk.Style()
    style.theme_use('clam') # Use 'clam' theme for better aesthetics

    # General Frame styles
    style.configure("TFrame", background="#f0f0f0")

    # Styles for image thumbnail containers in the main window
    style.configure("Thumbnail.TFrame",
                    background="#f0f0f0",
                    borderwidth=1,
                    relief="solid",
                    highlightbackground="#cccccc",
                    highlightcolor="#cccccc")
    style.map("Thumbnail.TFrame",
              background=[('active', '#e6e6e6'), ('!disabled', '#f0f0f0')]) # Hover effect

    # Style for SELECTED image thumbnail containers
    style.configure("Selected.TFrame",
                    background="#d0e0ff", # Light blue background
                    borderwidth=3,        # Thicker border
                    relief="solid",
                    highlightbackground="#007bff", # Blue highlight
                    highlightcolor="#007bff")
    style.map("Selected.TFrame",
              background=[('active', '#c0d0ef'), ('!disabled', '#d0e0ff')]) # Hover effect for selected

    # Style for preview image containers in the separate preview window (no longer used, but kept for consistency if re-added)
    style.configure("Preview.TFrame",
                    background="#ffffff",
                    borderwidth=1,
                    relief="solid",
                    highlightbackground="#e0e0e0",
                    highlightcolor="#e0e0e0")

    # Label styles
    style.configure("TLabel", background="#f0f0f0", foreground="#333333")

    # Button styles
    style.configure("TButton",
                    padding=(10, 5), # Horizontal and vertical padding
                    relief="flat",
                    background="#007bff", # Blue background
                    foreground="white", # White text
                    font=('Arial', 10, 'bold')) # Bold font
    style.map("TButton",
              background=[('active', '#0056b3')], # Darker blue on hover/click
              foreground=[('active', 'white')])

    # Checkbutton styles
    style.configure("TCheckbutton", background="#f0f0f0", foreground="#333333", font=('Arial', 9))

    # Entry field style
    style.configure("TEntry", fieldbackground="white", foreground="#333333", borderwidth=1, relief="solid")

    # Progress bar style
    style.configure("TProgressbar",
                    background="#007bff", # Blue progress color
                    troughcolor="#e0e0e0", # Light grey trough
                    borderwidth=0,
                    relief="flat")


    app = FaceIndexerApp(root)
    root.mainloop()

if __name__ == "__main__":
    run_gui()