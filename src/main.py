#!/usr/bin/env python3
import tkinter as tk
from gui.app import FaceIndexerApp

def main():
    """Initialize and run the Face Indexer application."""
    root = tk.Tk()
    app = FaceIndexerApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()