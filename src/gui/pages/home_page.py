"""
Home page with navigation buttons
"""

import tkinter as tk
from tkinter import ttk
from ..base_page import BasePage

class HomePage(BasePage):
    """Home page with main navigation options."""
    
    def _setup_ui(self):
        """Setup the home page UI."""
        # Main container with padding
        main_container = ttk.Frame(self.frame, style="Home.TFrame", padding=50)
        main_container.pack(fill="both", expand=True)
        
        # Center content vertically and horizontally
        content_frame = ttk.Frame(main_container, style="Home.TFrame")
        content_frame.place(relx=0.5, rely=0.5, anchor="center")
        
        # Title
        title_label = ttk.Label(content_frame, 
                               text="Face Indexer and Searcher", 
                               style="HomeTitle.TLabel")
        title_label.pack(pady=(0, 10))
        
        # Subtitle
        subtitle_label = ttk.Label(content_frame, 
                                  text="Organize and search your photo collection by faces", 
                                  style="HomeSubtitle.TLabel")
        subtitle_label.pack(pady=(0, 40))
        
        # Button container
        button_frame = ttk.Frame(content_frame, style="Home.TFrame")
        button_frame.pack()
        
        # Index Faces button
        index_button = ttk.Button(button_frame,
                                 text="Index Faces",
                                 command=self.app.navigate_to_index,
                                 style="HomeButton.TButton",
                                 width=20)
        index_button.pack(pady=10)
        
        # Search button
        search_button = ttk.Button(button_frame,
                                  text="Search Faces",
                                  command=self.app.navigate_to_search,
                                  style="HomeButton.TButton",
                                  width=20)
        search_button.pack(pady=10)
        
        # Add some descriptive text
        description_frame = ttk.Frame(content_frame, style="Home.TFrame")
        description_frame.pack(pady=(30, 0))
        
        index_desc = ttk.Label(description_frame,
                              text="• Index Faces: Scan your photos and create a searchable face database",
                              style="HomeSubtitle.TLabel")
        index_desc.pack(anchor="w", pady=2)
        
        search_desc = ttk.Label(description_frame,
                               text="• Search Faces: Find photos containing specific people",
                               style="HomeSubtitle.TLabel")
        search_desc.pack(anchor="w", pady=2)