# DICOM Tag Editor Project: Scope and Implementation Plan

## Project Overview
A simple GUI-based DICOM tag editor using Python and PyDICOM that allows users to load, view, edit, and distribute DICOM images with a focus on tag manipulation across different hierarchical levels.

## Technical Stack
- **Language**: Python 3.x
- **DICOM Library**: PyDICOM
- **GUI Framework**: PyQt6 (good cross-platform support and modern appearance)
- **Additional Libraries**: 
  - numpy (for image processing)
  - pynetdicom (for DICOM sending)

## Core Features
1. Load DICOM files (individual files, directories, and ZIP archives)
2. Hierarchical tag viewing and editing at:
   - Patient level
   - Study level
   - Series level
   - Instance (image) level
3. Tree-based navigation interface
4. Image thumbnails preview
5. Save edited DICOM files
6. DICOM networking (send to PACS/destinations)
7. Settings management for DICOM destinations

## Implementation Plan

### Phase 1: Project Setup & Basic DICOM Loading (Week 1)
- Set up project structure and environment
- Create basic PyQt application shell
- Implement DICOM loading functionality (single files)
- Implement basic tag display functionality
- Create basic file open/save dialogs

### Phase 2: Tree Navigation & Multi-Level Hierarchy (Week 2)
- Implement hierarchical data model for DICOM elements
- Create tree view for navigating through patient/study/series/instance levels
- Add ability to select items in tree and show corresponding tags
- Implement directory loading functionality
- Add ZIP file loading capability

### Phase 3: Tag Editing & Image Preview (Week 3)
- Implement tag editing functionality
- Add validation for tag edits
- Create image preview display for selected instances
- Implement thumbnail generation
- Add tag filtering/search capabilities

### Phase 4: Hierarchical Editing & Save Functionality (Week 4)
- Implement editing at different hierarchy levels
- Add propagation of changes (e.g., edit at study level affects all series)
- Implement save functionality for individual files
- Add batch save capability for edited files

### Phase 5: DICOM Networking & Settings (Week 5)
- Implement DICOM send functionality
- Create settings dialog for AE Title/destination configuration
- Add configuration storage
- Implement simple job queue for DICOM sending

### Phase 6: Testing, Refinement & Documentation (Week 6)
- Cross-platform testing (Linux/NixOS focus, Windows verification)
- Performance optimization
- User documentation creation
- Code cleanup and documentation

## Project Structure
```
dicom-tag-editor/
├── dicomtageditor/
│   ├── __init__.py
│   ├── main.py              # Application entry point
│   ├── app.py               # Main application window
│   ├── models/              # Data models
│   │   ├── __init__.py
│   │   ├── dicom_model.py   # Hierarchical DICOM data model
│   │   └── settings.py      # Settings storage
│   ├── views/               # UI views
│   │   ├── __init__.py
│   │   ├── main_window.py   # Main window layout
│   │   ├── tree_view.py     # DICOM hierarchy tree
│   │   ├── tag_editor.py    # Tag editing panel
│   │   ├── image_view.py    # Image preview panel
│   │   └── settings_dialog.py # Settings configuration
│   ├── controllers/         # Business logic
│   │   ├── __init__.py
│   │   ├── dicom_loader.py  # Loading functionality
│   │   ├── tag_controller.py # Tag editing logic
│   │   └── network.py       # DICOM networking
│   └── utils/               # Utility functions
│       ├── __init__.py
│       ├── dicom_utils.py   # DICOM helper functions
│       └── image_utils.py   # Image processing helpers
├── requirements.txt         # Dependencies
├── setup.py                 # Installation script
└── README.md                # Documentation
```

## Development Guidelines
1. Keep the codebase simple and maintainable
2. Use MVC pattern to separate concerns
3. Implement error handling for robust operation
4. Focus on Linux compatibility first, then ensure Windows support
5. Favor simplicity over complex features when possible
6. Document code as development progresses
