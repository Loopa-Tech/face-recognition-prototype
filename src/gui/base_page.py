"""
Base page class for all application pages
"""

import tkinter as tk
from tkinter import ttk

class BasePage:
    """Base class for all application pages."""
    
    def __init__(self, parent, app):
        self.parent = parent
        self.app = app
        self.frame = None
        self._create_page()
    
    def _create_page(self):
        """Create the page frame. Override in subclasses."""
        self.frame = ttk.Frame(self.parent)
        self._setup_ui()
    
    def _setup_ui(self):
        """Setup the user interface. Override in subclasses."""
        pass
    
    def show(self):
        """Show the page."""
        if self.frame:
            self.frame.pack(fill="both", expand=True)
    
    def hide(self):
        """Hide the page."""
        if self.frame:
            self.frame.pack_forget()
    
    def _create_navigation_bar(self):
        """Create a navigation bar with back to home button."""
        nav_frame = ttk.Frame(self.frame, style="Nav.TFrame")
        nav_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Button(nav_frame, 
                  text="← Home", 
                  command=self.app.navigate_to_home,
                  style="NavButton.TButton").pack(side="left", padx=10, pady=5)
        
        return nav_frame