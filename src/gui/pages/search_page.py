import os
import pickle
import threading
import tkinter as tk
from tkinter import filedialog, ttk
from tkinter import messagebox
from PIL import Image, ImageTk
import time

from search_matches import search_matches

from ..base_page import BasePage

class SearchPage(BasePage):
    """Search page for finding faces in indexed photos with image previews."""

    def _setup_ui(self):
        # Navigation bar
        self._create_navigation_bar()

        # Main container
        self.content_frame = ttk.Frame(self.frame, padding=20)
        self.content_frame.pack(fill="both", expand=True)

        # Title
        ttk.Label(self.content_frame,
                  text="Search Faces",
                  font=('Arial', 18, 'bold')).pack(pady=(0, 20))

        # Controls
        controls_frame = ttk.Frame(self.content_frame)
        controls_frame.pack(fill="x", pady=(0, 10))

        self.face_path_var = tk.StringVar(value="No image selected")
        face_btn = ttk.Button(controls_frame,
                              text="Select Face Image",
                              command=self.select_face_image)
        face_btn.grid(row=0, column=0, padx=5)

        self.face_preview_label = ttk.Label(controls_frame)
        self.face_preview_label.grid(row=0, column=2, padx=5)

        ttk.Label(controls_frame,
                  textvariable=self.face_path_var,
                  wraplength=300).grid(row=0, column=1, sticky="w")

        self.pkl_path_var = tk.StringVar(value="No collection selected")
        pkl_btn = ttk.Button(controls_frame,
                             text="Select Face Collection (.pkl)",
                             command=self.select_pkl_file)
        pkl_btn.grid(row=1, column=0, padx=5, pady=5)

        self.pkl_info_label = ttk.Label(controls_frame)
        self.pkl_info_label.grid(row=1, column=2, padx=5)

        ttk.Label(controls_frame,
                  textvariable=self.pkl_path_var,
                  wraplength=300).grid(row=1, column=1, sticky="w")

        # Search button
        self.search_btn = ttk.Button(self.content_frame,
                                     text="Search",
                                     command=self.run_search_thread,
                                     state="disabled")
        self.search_btn.pack(pady=(0, 10))

        # Progress bar
        self.progress = ttk.Progressbar(self.content_frame, orient="horizontal", mode="indeterminate")
        self.progress.pack(fill="x", pady=(0, 10))
        self.progress.pack_forget()

        # Results
        results_container = ttk.LabelFrame(self.content_frame, text="Matches", padding=10)
        results_container.pack(fill="both", expand=True)
        self.results_canvas = tk.Canvas(results_container, bg="#ffffff")
        self.results_canvas.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(results_container, orient="vertical", command=self.results_canvas.yview)
        scrollbar.pack(side="right", fill="y")
        self.results_canvas.configure(yscrollcommand=scrollbar.set)
        self.results_inner = ttk.Frame(self.results_canvas)
        self.results_canvas.create_window((0,0), window=self.results_inner, anchor="nw")
        self.results_inner.bind("<Configure>", lambda e: self.results_canvas.configure(scrollregion=self.results_canvas.bbox("all")))

        # State
        self.selected_face = None
        self.selected_pkl = None
        self.match_images = []  # Keep references to PhotoImage objects

    def select_face_image(self):
        path = filedialog.askopenfilename(
            title="Select face image",
            filetypes=[("Image files", "*.jpg *.jpeg *.png *.bmp *.webp"), ("All files", "*")]
        )
        if path:
            self.selected_face = path
            self.face_path_var.set(os.path.basename(path))
            self._update_face_preview(path)
            self._update_search_button_state()

    def _update_face_preview(self, image_path):
        try:
            img = Image.open(image_path)
            img.thumbnail((200, 100))
            self.face_preview_image = ImageTk.PhotoImage(img)
            self.face_preview_label.config(image=self.face_preview_image)
        except Exception:
            self.face_preview_label.config(image="")

    def select_pkl_file(self):
        path = filedialog.askopenfilename(
            title="Select face collection",
            filetypes=[("Pickle files", "*.pkl"), ("All files", "*")]
        )
        if path:
            self.selected_pkl = path
            self.pkl_path_var.set(os.path.basename(path))
            self._update_pkl_info(path)
            self._update_search_button_state()

    def _update_pkl_info(self, pkl_path):
        try:
            with open(pkl_path, 'rb') as f:
                faces = pickle.load(f)
            self.pkl_info_label.config(text=f"{len(faces)} faces")
        except Exception:
            self.pkl_info_label.config(text="Error")

    def _update_search_button_state(self):
        self.search_btn.config(state="normal" if self.selected_face and self.selected_pkl else "disabled")

    def run_search_thread(self):
        for w in self.results_inner.winfo_children():
            w.destroy()
        self.match_images.clear()
        self.progress.pack(fill="x", pady=(0,10))
        self.progress.start(10)
        self.search_btn.config(state="disabled")
        threading.Thread(target=self._search_task, daemon=True).start()

    def _search_task(self):
        start_time = time.time()
        try:
            matches = search_matches(self.selected_face, self.selected_pkl)
        except Exception as e:
            matches = []
            self.app.root.after(0, lambda: messagebox.showerror("Search Error", str(e)))
        end_time = time.time()
        duration = end_time - start_time
        self.app.root.after(0, lambda: self._show_matches(matches, duration))

    def _show_matches(self, matches, duration=0):
        self.progress.stop()
        self.progress.pack_forget()
        self.search_btn.config(state="normal")

        try:
            with open(self.selected_pkl, 'rb') as f:
                face_entries = pickle.load(f)
            entry_map = {f["name"]: f for f in face_entries}
        except:
            entry_map = {}

        ttk.Label(self.results_inner,
                text=f"Search completed in {duration:.2f} seconds",
                font=('Arial', 10, 'italic')).pack(pady=(0, 10))

        if not matches:
            ttk.Label(self.results_inner, text="No matches found.", font=('Arial', 12)).pack(pady=10)
            return

        for name, distance in sorted(matches, key=lambda x: x[1]):
            entry = entry_map.get(name)
            frame = ttk.Frame(self.results_inner, padding=5)
            frame.pack(fill="x", pady=5)

            if entry:
                try:
                    img = Image.open(entry['image_path'])
                    top, right, bottom, left = entry.get('location', (0,0,0,0))
                    face_crop = img.crop((left, top, right, bottom))
                    face_crop.thumbnail((80,80))
                    face_img = ImageTk.PhotoImage(face_crop)
                    self.match_images.append(face_img)
                    ttk.Label(frame, image=face_img).pack(side="left", padx=5)

                    orig_img = img.copy()
                    orig_img.thumbnail((100,100))
                    orig_img_tk = ImageTk.PhotoImage(orig_img)
                    self.match_images.append(orig_img_tk)
                    ttk.Label(frame, image=orig_img_tk).pack(side="left", padx=5)
                except Exception:
                    pass

            info_frame = ttk.Frame(frame)
            info_frame.pack(side="left", fill="x", expand=True)
            ttk.Label(info_frame, text=name, font=('Arial', 10, 'bold')).pack(anchor="w")
            ttk.Label(info_frame, text=f"Confidence: {distance:.4f}", font=('Arial', 9)).pack(anchor="w")
