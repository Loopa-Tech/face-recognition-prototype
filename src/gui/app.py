"""
Main Application Controller
Handles navigation between different pages/views
"""

import tkinter as tk
from tkinter import ttk
from .pages.home_page import HomePage
from .pages.index_page import IndexPage
from .pages.search_page import SearchPage
from .styles import configure_styles

class FaceIndexerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Face Indexer and Searcher")
        self.root.geometry("960x800")
        
        # Configure styles
        configure_styles()
        
        # Create main container
        self.main_frame = ttk.Frame(self.root)
        self.main_frame.pack(fill="both", expand=True)
        
        # Initialize pages
        self.pages = {}
        self.current_page = None
        
        # Create pages
        self._create_pages()
        
        # Show home page initially
        self.show_page("home")
    
    def _create_pages(self):
        """Create all application pages."""
        self.pages["home"] = HomePage(self.main_frame, self)
        self.pages["index"] = IndexPage(self.main_frame, self)
        self.pages["search"] = SearchPage(self.main_frame, self)
    
    def show_page(self, page_name):
        """Show the specified page and hide others."""
        # Hide current page
        if self.current_page:
            self.pages[self.current_page].hide()
        
        # Show new page
        if page_name in self.pages:
            self.pages[page_name].show()
            self.current_page = page_name
        else:
            raise ValueError(f"Unknown page: {page_name}")
    
    def navigate_to_home(self):
        """Navigate to home page."""
        self.show_page("home")
    
    def navigate_to_index(self):
        """Navigate to index page."""
        self.show_page("index")
    
    def navigate_to_search(self):
        """Navigate to search page."""
        self.show_page("search")