"""
Application styling configuration
"""

from tkinter import ttk

def configure_styles():
    """Configure ttk styles for a modern look."""
    style = ttk.Style()
    style.theme_use('clam')

    # General Frame styles
    style.configure("TFrame", background="#f0f0f0")

    # Home page specific styles
    style.configure("Home.TFrame", background="#f8f9fa")
    style.configure("HomeTitle.TLabel", 
                    background="#f8f9fa", 
                    foreground="#2c3e50", 
                    font=('Arial', 24, 'bold'))
    style.configure("HomeSubtitle.TLabel", 
                    background="#f8f9fa", 
                    foreground="#7f8c8d", 
                    font=('Arial', 12))

    # Navigation styles
    style.configure("Nav.TFrame", background="#34495e", relief="flat")
    style.configure("NavButton.TButton",
                    padding=(15, 8),
                    relief="flat",
                    background="#3498db",
                    foreground="white",
                    font=('Arial', 10, 'bold'))
    style.map("NavButton.TButton",
              background=[('active', '#2980b9'), ('pressed', '#21618c')])

    # Home page button styles
    style.configure("HomeButton.TButton",
                    padding=(20, 15),
                    relief="flat",
                    background="#3498db",
                    foreground="white",
                    font=('Arial', 14, 'bold'))
    style.map("HomeButton.TButton",
              background=[('active', '#2980b9'), ('pressed', '#21618c')])

    # Styles for image thumbnail containers
    style.configure("Thumbnail.TFrame",
                    background="#f0f0f0",
                    borderwidth=1,
                    relief="solid",
                    highlightbackground="#cccccc",
                    highlightcolor="#cccccc")
    style.map("Thumbnail.TFrame",
              background=[('active', '#e6e6e6'), ('!disabled', '#f0f0f0')])

    # Style for SELECTED image thumbnail containers
    style.configure("Selected.TFrame",
                    background="#d0e0ff",
                    borderwidth=3,
                    relief="solid",
                    highlightbackground="#007bff",
                    highlightcolor="#007bff")
    style.map("Selected.TFrame",
              background=[('active', '#c0d0ef'), ('!disabled', '#d0e0ff')])

    # Style for indexed face containers
    style.configure("IndexedFace.TFrame",
                    background="#ffffff",
                    borderwidth=1,
                    relief="solid",
                    highlightbackground="#dddddd",
                    highlightcolor="#dddddd")

    # Label styles
    style.configure("TLabel", background="#f0f0f0", foreground="#333333")

    # Button styles
    style.configure("TButton",
                    padding=(10, 5),
                    relief="flat",
                    background="#007bff",
                    foreground="white",
                    font=('Arial', 10, 'bold'))
    style.map("TButton",
              background=[('active', '#0056b3')])

    # Checkbutton styles
    style.configure("TCheckbutton", background="#f0f0f0", foreground="#333333", font=('Arial', 9))

    # Entry field style
    style.configure("TEntry", fieldbackground="white", foreground="#333333", borderwidth=1, relief="solid")

    # Progress bar style
    style.configure("TProgressbar",
                    background="#007bff",
                    troughcolor="#e0e0e0",
                    borderwidth=0,
                    relief="flat")