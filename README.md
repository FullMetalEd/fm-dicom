# FM-DICOM Tag Editor

![FM-DICOM Logo](fm_dicom/fm-dicom.png)

A robust, cross-platform Python GUI for viewing, editing, and managing DICOM metadata. Built with **PyQt6** and **pydicom**, it offers advanced features like anonymization, validation, duplication, and PACS integration.

## Features

*   **Metadata Editor**: View, edit, add, or remove DICOM tags seamlessly.
*   **File Management**: Load single files, directories, DICOMDIRs, or ZIP archives.
*   **Bulk Operations**: Delete or modify instances, series, studies, or patients.
*   **Anonymization**: Template-based anonymization (Clinical, Research) with custom template support.
*   **Validation**: Validate DICOM tags against standard definitions to identify errors.
*   **Analysis**: Analyze image resolutions, file sizes, and loading performance.
*   **PACS Integration**: Built-in C-STORE client to send data to PACS nodes. Supports automatic JPEG2000 conversion.
*   **Duplication**: Intelligent DICOM duplication with configurable UID regeneration (Patient/Study/Series level).
*   **Visuals**: Basic image viewer with support for standard and compressed transfer syntaxes.
*   **Modern UI**: Aurora-themed interface with Dark, Light, and Catppuccin Macchiato modes.

## Installation

### Windows
Download the latest portable `.exe` from the [Releases Page](https://github.com/FullMetalEd/fm-dicom/releases). No installation required.

### Linux (Nix / NixOS)

**Try it without installing:**
```bash
nix run github:FullMetalEd/fm-dicom
```

**Install via Flakes:**
Add to your `flake.nix`:
```nix
inputs.fm-dicom.url = "github:fullmetaled/fm-dicom";
# ... inside your modules list:
environment.systemPackages = [ inputs.fm-dicom.packages."${system}".default ];
```

### Development Setup (Cross-Platform)

We recommend using [uv](https://github.com/astral-sh/uv) or [Nix](https://nixos.org/) for development.

**Using uv:**
```bash
uv sync
uv run -m fm_dicom.main
```

**Using Nix:**
```bash
nix develop
nix run
```

## Configuration

FM-DICOM uses a `config.yml` file for persistent settings.
*   **Linux**: `~/.config/fm-dicom/config.yml`
*   **Windows**: `%APPDATA%/fm-dicom/config.yml`
*   **macOS**: `~/Library/Application Support/fm-dicom/config.yml`

**Example Configuration:**
```yaml
log_level: "INFO"
theme: "dark"  # Options: dark, light, catppuccin
ae_title: "FM-DICOM"
destinations:
  - label: "Primary PACS"
    ae_title: "ORTHANC"
    host: "192.168.1.100"
    port: 4242
favorite_tags:
  - "PatientName"
  - "StudyDate"
```

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for details on setting up your environment, running tests, and our coding standards.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

## Acknowledgements

*   [pydicom](https://github.com/pydicom/pydicom) - DICOM file handling
*   [pynetdicom](https://github.com/pydicom/pynetdicom) - DICOM network operations
*   [PyQt6](https://pypi.org/project/PyQt6/) - GUI Framework
