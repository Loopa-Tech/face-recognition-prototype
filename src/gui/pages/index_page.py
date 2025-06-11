"""
Face indexing page - main functionality from original app
"""

import os
import threading
import tkinter as tk
from tkinter import filedialog, ttk
from PIL import Image, ImageTk
import time
from ..base_page import BasePage

# Import your existing modules - adjust paths as needed
from face_indexer import index_faces
from raw_converter import convert_all_raw_images
from utils.file_utils import collect_image_paths

# Define common RAW and standard image extensions
RAW_EXTENSIONS = ['.nef', '.arw', '.dng', '.cr2', '.cr3']
IMG_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.webp']

class IndexPage(BasePage):
    """Face indexing page with all the original functionality."""
    
    def _setup_ui(self):
        """Setup the indexing page UI."""
        # Navigation bar
        self._create_navigation_bar()
        
        # Main container frame for padding and overall layout
        main_frame = ttk.Frame(self.frame, padding=15)
        main_frame.pack(fill="both", expand=True)
        
        # Initialize state variables
        self._init_variables()
        
        # Setup UI components
        self._setup_controls(main_frame)
        self._setup_preview_section(main_frame)
        self._setup_progress_section(main_frame)
        self._setup_statistics_section(main_frame)
        self._setup_indexed_faces_section(main_frame)
        
        # Configure grid weights
        main_frame.grid_rowconfigure(1, weight=1)  # Photo section
        main_frame.grid_rowconfigure(5, weight=1)  # Indexed faces section
        
        # Initial state
        self.toggle_photo_section()
        self.toggle_indexed_faces_section()
    
    def _init_variables(self):
        """Initialize tkinter variables and state."""
        self.folder_path = tk.StringVar(value="")
        self.use_raw_var = tk.BooleanVar(value=False)
        self.show_preview_var = tk.BooleanVar(value=False)
        self.show_indexed_faces_var = tk.BooleanVar(value=False)
        
        # Sets to keep track of selected image paths and image references
        self.selected_images = set()
        self.image_thumbnails = {}
        self.thumbnail_items = {}
        self.indexed_faces_data = []
        self.indexed_face_images = []
        
        # Timing and statistics
        self.start_time = None
        self.processing_times = []
        self.total_faces_found = 0
        self.images_processed = 0
    
    def _setup_controls(self, parent):
        """Setup control frame with folder selection and options."""
        control_frame = ttk.LabelFrame(parent, text="Folder and Options", padding=10)
        control_frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=10)
        control_frame.grid_columnconfigure(1, weight=1)
        
        # Folder path display and entry
        ttk.Label(control_frame, text="Current Folder:").grid(row=0, column=0, sticky="w", pady=2)
        ttk.Entry(control_frame, textvariable=self.folder_path, width=80, state="readonly").grid(row=0, column=1, sticky="ew", padx=5)
        ttk.Button(control_frame, text="Browse & Select Folder", command=self.select_folder_with_dialog).grid(row=0, column=2, padx=5)
        
        # Checkboxes
        ttk.Checkbutton(control_frame, text="Include RAW Files", variable=self.use_raw_var, command=self.scan_folder_for_images).grid(row=1, column=0, sticky="w", pady=5)
        ttk.Checkbutton(control_frame, text="Show Photo Section", variable=self.show_preview_var, command=self.toggle_photo_section).grid(row=1, column=1, sticky="w", pady=5)
        
        # Main "Index Faces" button
        self.index_btn = ttk.Button(control_frame, text="Index Faces", command=self.run_index_thread)
        self.index_btn.grid(row=1, column=2, pady=10, sticky="ew")
    
    def _setup_preview_section(self, parent):
        """Setup image preview section."""
        self.preview_frame = ttk.LabelFrame(parent, text="Image Previews (Click to Select/Deselect)", padding=10)
        self.preview_frame.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=10)
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
        self.canvas_window_id = self.canvas.create_window((0, 0), window=self.inner_canvas_frame, anchor="nw")
        self.inner_canvas_frame.bind("<Configure>", self._on_inner_frame_configure)
    
    def _setup_progress_section(self, parent):
        """Setup progress bar and timing info."""
        progress_frame = ttk.Frame(parent)
        progress_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=10)
        progress_frame.grid_columnconfigure(0, weight=1)
        
        self.progress = ttk.Progressbar(progress_frame, orient="horizontal", length=600, mode="determinate")
        self.progress.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        
        # Timing information label
        self.timing_label = ttk.Label(progress_frame, text="Ready", font=('Arial', 9))
        self.timing_label.grid(row=0, column=1, sticky="e")
    
    def _setup_statistics_section(self, parent):
        """Setup statistics display."""
        self.stats_frame = ttk.LabelFrame(parent, text="Statistics", padding=10)
        self.stats_frame.grid(row=3, column=0, columnspan=2, sticky="ew", pady=10)
        
        self.stats_label = ttk.Label(self.stats_frame, text="No processing completed yet", font=('Arial', 9))
        self.stats_label.pack(anchor="w")
    
    def _setup_indexed_faces_section(self, parent):
        """Setup indexed faces display section."""
        # Control for indexed faces section
        indexed_faces_control_frame = ttk.Frame(parent)
        indexed_faces_control_frame.grid(row=4, column=0, columnspan=2, sticky="ew", pady=5)
        
        ttk.Checkbutton(indexed_faces_control_frame, text="Show Indexed Faces", 
                       variable=self.show_indexed_faces_var, 
                       command=self.toggle_indexed_faces_section).pack(anchor="w")
        
        # Indexed Faces Display Area
        self.indexed_faces_frame = ttk.LabelFrame(parent, text="Indexed Faces", padding=10)
        self.indexed_faces_frame.grid(row=5, column=0, columnspan=2, sticky="nsew", pady=10)
        self.indexed_faces_frame.grid_rowconfigure(0, weight=1)
        self.indexed_faces_frame.grid_columnconfigure(0, weight=1)
        
        # Canvas with Scrollbar for indexed faces
        self.indexed_canvas_scroll_frame = ttk.Frame(self.indexed_faces_frame)
        self.indexed_canvas_scroll_frame.grid(row=0, column=0, sticky="nsew")
        self.indexed_canvas_scroll_frame.grid_rowconfigure(0, weight=1)
        self.indexed_canvas_scroll_frame.grid_columnconfigure(0, weight=1)
        
        self.indexed_canvas = tk.Canvas(self.indexed_canvas_scroll_frame, bg="#f5f5f5", 
                                       highlightbackground="#cccccc", highlightthickness=1)
        self.indexed_canvas.grid(row=0, column=0, sticky="nsew")
        
        # Vertical scrollbar for indexed faces canvas
        self.indexed_scrollbar_y = ttk.Scrollbar(self.indexed_canvas_scroll_frame, orient="vertical", 
                                                command=self.indexed_canvas.yview)
        self.indexed_scrollbar_y.grid(row=0, column=1, sticky="ns")
        self.indexed_canvas.config(yscrollcommand=self.indexed_scrollbar_y.set)
        
        # Bind canvas configure event
        self.indexed_canvas.bind('<Configure>', self._on_indexed_canvas_configure)
        
        # Inner frame for indexed faces
        self.indexed_inner_frame = ttk.Frame(self.indexed_canvas)
        self.indexed_canvas_window_id = self.indexed_canvas.create_window((0, 0), window=self.indexed_inner_frame, anchor="nw")
        self.indexed_inner_frame.bind("<Configure>", self._on_indexed_inner_frame_configure)
    
    # Canvas event handlers
    def _on_canvas_configure(self, event):
        """Updates the canvas scroll region when the canvas itself is resized."""
        self.canvas.itemconfig(self.canvas_window_id, width=event.width)
        self.canvas.config(scrollregion=self.canvas.bbox("all"))
    
    def _on_inner_frame_configure(self, event):
        """Updates the canvas scroll region when the content (inner frame) changes size."""
        self.canvas.config(scrollregion=self.canvas.bbox("all"))
    
    def _on_indexed_canvas_configure(self, event):
        """Updates the indexed faces canvas scroll region when resized."""
        self.indexed_canvas.itemconfig(self.indexed_canvas_window_id, width=event.width)
        self.indexed_canvas.config(scrollregion=self.indexed_canvas.bbox("all"))
    
    def _on_indexed_inner_frame_configure(self, event):
        """Updates the indexed faces canvas scroll region when content changes."""
        self.indexed_canvas.config(scrollregion=self.indexed_canvas.bbox("all"))
    
    # Folder and image handling methods
    def select_folder_with_dialog(self):
        """Opens a file dialog to select a folder and then triggers an image scan."""
        folder = filedialog.askdirectory()
        if folder:
            self.folder_path.set(folder)
            self.scan_folder_for_images()
    
    def scan_folder_for_images(self):
        """Scans the currently set folder path for images based on selected extensions."""
        folder = self.folder_path.get()
        if not folder or not os.path.isdir(folder):
            print(f"Error: Folder '{folder}' does not exist or is inaccessible.")
            self.clear_previews()
            return
        
        all_extensions = IMG_EXTENSIONS[:]
        if self.use_raw_var.get():
            all_extensions.extend(RAW_EXTENSIONS)
        
        img_paths = collect_image_paths(folder, all_extensions)
        
        print(f"Found {len(img_paths)} image(s) in '{folder}' with extensions: {', '.join(all_extensions)}")
        self.display_previews(img_paths)
    
    # Preview handling methods
    def clear_previews(self):
        """Clears all displayed thumbnails and resets selection."""
        for widget in self.inner_canvas_frame.winfo_children():
            widget.destroy()
        self.image_thumbnails.clear()
        self.thumbnail_items.clear()
        self.selected_images = set()
        self.canvas.config(scrollregion=self.canvas.bbox("all"))
    
    def display_previews(self, img_paths):
        """Clears existing thumbnails and displays new ones for the given image paths."""
        self.clear_previews()
        
        # Ensure the photo section is visible when new images are displayed
        self.show_preview_var.set(True)
        self.toggle_photo_section()
        
        col_count = 6
        thumbnail_size = 100
        padding_x = 10
        padding_y = 15
        current_row = 0
        current_col = 0
        
        for path in img_paths:
            try:
                image = Image.open(path)
                image.thumbnail((thumbnail_size, thumbnail_size))
                
                img_tk = ImageTk.PhotoImage(image)
                self.image_thumbnails[path] = img_tk
                
                thumb_container = ttk.Frame(self.inner_canvas_frame, relief="solid", borderwidth=1, style="Thumbnail.TFrame")
                
                img_label = ttk.Label(thumb_container, image=img_tk, cursor="hand2")
                img_label.pack(pady=5, padx=5)
                
                file_name_label = ttk.Label(thumb_container, text=os.path.basename(path), wraplength=thumbnail_size + 20, anchor="center")
                file_name_label.pack(pady=2)
                
                thumb_container.grid(row=current_row, column=current_col, padx=padding_x, pady=padding_y, sticky="nsew")
                
                self.thumbnail_items[path] = thumb_container
                
                thumb_container.bind('<Button-1>', lambda e, p=path: self.toggle_selection(p))
                img_label.bind('<Button-1>', lambda e, p=path: self.toggle_selection(p))
                
                current_col += 1
                if current_col >= col_count:
                    current_col = 0
                    current_row += 1
                
                self.selected_images.add(path)
                
            except Exception as e:
                print(f"Error loading {path}: {e}")
        
        self.app.root.update_idletasks()
        self.canvas.config(scrollregion=self.canvas.bbox("all"))
        self.canvas.itemconfig(self.canvas_window_id, width=self.canvas.winfo_width())
        
        self.update_thumbnail_borders()
    
    def toggle_selection(self, path):
        """Adds or removes an image path from the selected_images set."""
        if path in self.selected_images:
            self.selected_images.remove(path)
        else:
            self.selected_images.add(path)
        self.update_thumbnail_borders()
    
    def update_thumbnail_borders(self):
        """Updates the visual border style of thumbnails based on their selection state."""
        for path, frame_widget in self.thumbnail_items.items():
            if path in self.selected_images:
                frame_widget.config(borderwidth=3, relief="solid")
                frame_widget.configure(style="Selected.TFrame")
            else:
                frame_widget.config(borderwidth=1, relief="solid")
                frame_widget.configure(style="Thumbnail.TFrame")
    
    def get_selected_images(self):
        """Returns a list of currently selected image paths."""
        return list(self.selected_images)
    
    # Face indexing methods
    def run_index_thread(self):
        """Starts the face indexing process in a separate thread."""
        image_paths = self.get_selected_images()
        if not image_paths:
            print("No images selected for indexing.")
            return
        
        # Clear previous indexed faces data
        self.clear_indexed_faces()
        
        # Reset statistics
        self.total_faces_found = 0
        self.images_processed = 0
        self.processing_times = []
        
        self.index_btn.config(state="disabled")
        self.progress["value"] = 0
        
        threading.Thread(target=self.index_faces_task, args=(image_paths,), daemon=True).start()
    
    def index_faces_task(self, image_paths):
        """The main task for indexing faces, potentially including RAW conversion."""
        total = len(image_paths)
        if not total:
            self.app.root.after(0, lambda: self.index_btn.config(state="normal"))
            return
        
        self.start_time = time.time()
        self.app.root.after(0, lambda: self.update_progress(0, total))
        self.app.root.after(0, lambda: self.update_timing_display(0, total))
        
        def on_progress(current, total):
            """Callback for updating progress from the index_faces function."""
            self.images_processed = current
            elapsed = time.time() - self.start_time
            self.processing_times.append(elapsed / current if current > 0 else 0)
            self.app.root.after(0, lambda: self.update_progress(current, total))
            self.app.root.after(0, lambda: self.update_timing_display(current, total))
        
        def preview_callback(face_img_np, original_img_path, confidence, face_name):
            """Callback for displaying individual face previews from index_faces."""
            self.total_faces_found += 1
            self.app.root.after(0, lambda: self.add_indexed_face(face_img_np, original_img_path, confidence, face_name))
        
        try:
            processed_image_paths = image_paths
            if self.use_raw_var.get():
                raw_paths_to_convert = [p for p in image_paths if os.path.splitext(p)[1].lower() in RAW_EXTENSIONS]
                if raw_paths_to_convert:
                    self.app.root.after(0, lambda: print("Converting RAW images (this may take a moment)..."))
                    converted_paths = convert_all_raw_images(raw_paths_to_convert)
                    processed_image_paths = [p for p in image_paths if p not in raw_paths_to_convert] + converted_paths
            
            # Call the main face indexing function
            index_faces(processed_image_paths, progress_callback=on_progress, preview_callback=preview_callback)
            
            # Update final statistics
            self.app.root.after(0, self.update_final_statistics)
            self.app.root.after(0, lambda: print("Indexing complete."))
            
            # Show indexed faces section if faces were found
            if self.total_faces_found > 0:
                self.app.root.after(0, lambda: self.show_indexed_faces_var.set(True))
                self.app.root.after(0, self.toggle_indexed_faces_section)
                
        except Exception as e:
            error_msg = f"Error during indexing: {e}"
            self.app.root.after(0, lambda: print(error_msg))
        finally:
            self.app.root.after(0, lambda: self.index_btn.config(state="normal"))
    
    # Progress and statistics methods
    def update_progress(self, current, total):
        """Updates the progress bar."""
        self.progress["maximum"] = total
        self.progress["value"] = current
    
    def update_timing_display(self, current, total):
        """Updates the timing information display."""
        if current == 0:
            self.timing_label.config(text="Starting...")
            return
            
        elapsed = time.time() - self.start_time
        avg_time_per_image = elapsed / current if current > 0 else 0
        remaining_images = total - current
        estimated_remaining = remaining_images * avg_time_per_image
        
        elapsed_str = f"{elapsed:.1f}s"
        avg_str = f"{avg_time_per_image:.1f}s/img"
        remaining_str = f"~{estimated_remaining:.1f}s left"
        
        self.timing_label.config(text=f"Elapsed: {elapsed_str} | Avg: {avg_str} | {remaining_str}")
    
    def update_final_statistics(self):
        """Updates the final statistics display after processing is complete."""
        if not self.processing_times:
            return
            
        total_time = time.time() - self.start_time
        avg_time_per_image = total_time / self.images_processed if self.images_processed > 0 else 0
        
        stats_text = (f"Processing completed in {total_time:.1f} seconds\n"
                     f"Images processed: {self.images_processed}\n"
                     f"Total faces found: {self.total_faces_found}\n"
                     f"Average time per image: {avg_time_per_image:.2f} seconds\n"
                     f"Average faces per image: {self.total_faces_found / self.images_processed:.1f}" 
                     if self.images_processed > 0 else "0")
        
        self.stats_label.config(text=stats_text)
        self.timing_label.config(text=f"Completed in {total_time:.1f}s")
    
    # Indexed faces methods
    def clear_indexed_faces(self):
        """Clears all indexed faces from display."""
        for widget in self.indexed_inner_frame.winfo_children():
            widget.destroy()
        self.indexed_faces_data.clear()
        self.indexed_face_images.clear()
        self.indexed_canvas.config(scrollregion=self.indexed_canvas.bbox("all"))
    
    def add_indexed_face(self, face_img_np, original_img_path, confidence, face_name):
        """Adds a new indexed face to the display."""
        try:
            # Convert numpy array to PIL Image for face
            face_pil = Image.fromarray(face_img_np)
            face_pil.thumbnail((100, 100))
            face_tk = ImageTk.PhotoImage(face_pil)
            
            # Load and thumbnail the original image
            original_pil = Image.open(original_img_path)
            original_pil.thumbnail((150, 150))
            original_tk = ImageTk.PhotoImage(original_pil)
            
            # Store references to prevent garbage collection
            self.indexed_face_images.extend([face_tk, original_tk])
            
            # Create container for this face entry
            face_entry = ttk.Frame(self.indexed_inner_frame, padding=10, style="IndexedFace.TFrame")
            face_entry.pack(fill="x", padx=10, pady=5)
            
            # Left side - Face image
            left_frame = ttk.Frame(face_entry)
            left_frame.pack(side="left", padx=(0, 20))
            
            face_label = ttk.Label(left_frame, image=face_tk)
            face_label.pack()
            
            face_name_label = ttk.Label(left_frame, text=face_name, font=('Arial', 9, 'bold'))
            face_name_label.pack(pady=(5, 0))
            
            confidence_label = ttk.Label(left_frame, text=f"Confidence: {confidence:.2f}", 
                                       font=('Arial', 8), foreground="#666666")
            confidence_label.pack()
            
            # Right side - Original image
            right_frame = ttk.Frame(face_entry)
            right_frame.pack(side="left")
            
            original_label = ttk.Label(right_frame, image=original_tk)
            original_label.pack()
            
            source_label = ttk.Label(right_frame, text=f"Source: {os.path.basename(original_img_path)}", 
                                   font=('Arial', 8), foreground="#666666")
            source_label.pack(pady=(5, 0))
            
            # Update scroll region
            self.app.root.update_idletasks()
            self.indexed_canvas.config(scrollregion=self.indexed_canvas.bbox("all"))
            
        except Exception as e:
            print(f"Error adding indexed face: {e}")
    
    # Section toggle methods
    def toggle_photo_section(self):
        """Hides or shows the main image preview frame based on the checkbox state."""
        if self.show_preview_var.get():
            self.preview_frame.grid()
        else:
            self.preview_frame.grid_remove()
    
    def toggle_indexed_faces_section(self):
        """Hides or shows the indexed faces frame based on the checkbox state."""
        if self.show_indexed_faces_var.get():
            self.indexed_faces_frame.grid()
        else:
            self.indexed_faces_frame.grid_remove()