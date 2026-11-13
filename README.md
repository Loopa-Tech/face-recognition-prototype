# Face Indexer and Searcher

A tool for organizing and searching your photo collection by faces.

---

## 📦 Installation

### ✅ Prerequisites
- Python 3.8 or higher
- `pip` package manager

---

### 🔧 Setup Instructions

1. **Clone the repository or download the source code**  
   ```bash
   git clone https://github.com/Loopa-Tech/face-recognition-prototype.git
   cd face-recognition-prototype
   ```

2. **Create a virtual environment (recommended)**  
   ```bash
   python -m venv venv
   ```

3. **Activate the virtual environment**

   - **Windows:**
     ```bash
     venv\Scripts\activate
     ```

   - **macOS/Linux:**
     ```bash
     source venv/bin/activate
     ```

4. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

---

## 🚀 Running the Application

To launch the app:
```bash
python src/main.py
```

---

## 🧭 User Guide

### 🗂 Indexing Photos

1. Click **Index Faces** from the home page  
2. Use the **Browse & Select Folder** button to choose your image folder (you can choose the provided `photos` folder)
3. Configure options:
   - ✅ *Include RAW Files*: Enables support for `.nef`, `.arw`, `.dng`, `.cr2`, `.cr3`
   - ✅ *Show Photo Section*: Toggle image previews
4. Click image thumbnails to select/deselect them  
5. Click **Index Faces** to start

**The app will:**
- Convert RAW files (saved to `raw_converted/`)
- Detect and extract faces
- Save facial data to a database
- Display progress and statistics

---

### 🔍 Searching for Faces

1. Click **Search Faces** from the home page  
2. Select a face image (you can choose one in the provided `known_faces`)
3. Select a Face collection (saved in `./faces_indexed`)

**Results:**
- All photos containing people matching the selected face will be shown

---

## Alpicturia — application web

Le prototype de bureau ci-dessus est conservé. La nouvelle application web se trouve dans `web/` : espace festivalier mobile/PWA, portail photographe, administration, comptes/email, API et MCP, worker et déploiement Docker.

Consultez **[le guide de reprise et de démarrage](docs/ALPICTURIA-REPRISE.md)** pour les commandes, les fonctionnalités disponibles, les tests et les étapes encore nécessaires avant ouverture publique.
