"""
Search page for finding faces (placeholder for now)
"""

import tkinter as tk
from tkinter import ttk
from ..base_page import BasePage

class SearchPage(BasePage):
    """Search page for finding faces in indexed photos."""
    
    def _setup_ui(self):
        """Setup the search page UI."""
        # Navigation bar
        self._create_navigation_bar()
        
        # Main content container
        content_frame = ttk.Frame(self.frame, padding=20)
        content_frame.pack(fill="both", expand=True)
        
        # Page title
        title_label = ttk.Label(content_frame, 
                               text="Search Faces", 
                               font=('Arial', 18, 'bold'))
        title_label.pack(pady=(0, 20))
        
        # Placeholder content
        placeholder_frame = ttk.Frame(content_frame)
        placeholder_frame.pack(fill="both", expand=True)
        
        # Center the placeholder text
        placeholder_container = ttk.Frame(placeholder_frame)
        placeholder_container.place(relx=0.5, rely=0.5, anchor="center")
        
        placeholder_label = ttk.Label(placeholder_container,
                                     text="Search functionality coming soon...",
                                     font=('Arial', 14),
                                     foreground="#7f8c8d")
        placeholder_label.pack()
        
        description_label = ttk.Label(placeholder_container,
                                     text="This page will allow you to search for specific faces\nin your indexed photo collection.",
                                     font=('Arial', 10),
                                     foreground="#95a5a6",
                                     justify="center")
        description_label.pack(pady=(10, 0))