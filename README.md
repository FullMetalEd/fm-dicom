# dicom-tag-editor

A robust Python GUI for editing DICOM tags. This tool allows you to view and modify metadata in DICOM files, making it useful for medical imaging professionals, researchers, and developers working with DICOM datasets.

## Features

- View DICOM file metadata in a user-friendly interface
- Edit, add, or remove DICOM tags
- Delete instances/series/studies/patients
- merge patients and all levels below
- Save changes back to DICOM files
- Cross-platform support (Linux, macOS, Windows)
- Nix/NixOS support for reproducible development and deployment

## Installation

### Windows

For Windows users, download the latest `.exe` (portable) release from the [GitHub Releases page](https://github.com/yourusername/dicom-tag-editor/releases).  
Simply run the `.exe` file—no installation is required.

> **Note:** In the future, a `.msi` installer may also be provided for easier installation.

### Using Nix (Recommended)

If you use [Nix](https://nixos.org/):

```sh
git clone https://github.com/yourusername/dicom-tag-editor.git
cd dicom-tag-editor
nix develop
```

This will drop you into a shell with all dependencies available.

### Manual Installation

1. Clone the repository:
    ```sh
    git clone https://github.com/yourusername/dicom-tag-editor.git
    cd dicom-tag-editor
    ```
2. Install Python (>=3.8) and pip if not already installed.
3. Install dependencies:
    ```sh
    pip install -r requirements.txt
    ```

## Running the Application

After installing dependencies, run:

```sh
python main.py
```

Or, if using the Nix development shell:

```sh
nix develop
python main.py
```

## Nix Development Environment

This project includes a `flake.nix` for reproducible development. To enter the development environment:

```sh
nix develop
```

This will provide you with Python, all required libraries, and any other tools needed for development.

## Adding to Your NixOS System Configuration

You can install `dicom-tag-editor` system-wide on NixOS so it is always available for all users. Here’s how:

1. **Add the repository as an input to your `flake.nix`:**

   Open your system's `flake.nix` (usually in `/etc/nixos/flake.nix` or your NixOS configuration repo) and add:

   ```nix
   inputs.dicom-tag-editor.url = "github:yourusername/dicom-tag-editor";
   ```

   Place this line in the `inputs` section, alongside other inputs like `nixpkgs`.

2. **Add the package to your system packages:**

   In your `flake.nix` or `configuration.nix`, add the package to `environment.systemPackages`. For example, in a `flake.nix`:

   ```nix
   outputs = { self, nixpkgs, ... }@inputs: {
     nixosConfigurations.your-hostname = nixpkgs.lib.nixosSystem {
       # ...existing code...
       configuration = {
         # ...existing code...
         environment.systemPackages = with pkgs; [
           inputs.dicom-tag-editor.packages.${system}.default
         ];
         # ...existing code...
       };
     };
   };
   ```

   Or in `configuration.nix` (if not using flakes):

   ```nix
   environment.systemPackages = with pkgs; [
     # ...other packages...
     dicom-tag-editor
   ];
   ```

   (You may need to overlay or package it if not using flakes.)

3. **Rebuild your system:**

   Apply your changes by running:

   ```sh
   sudo nixos-rebuild switch --flake /etc/nixos#your-hostname
   ```

   Replace `/etc/nixos` and `your-hostname` with your actual flake path and hostname if different.

After rebuilding, you can launch `dicom-tag-editor` from your terminal or application menu.

**Tip:** If you’re new to NixOS flakes, see the [NixOS flake documentation](https://nixos.wiki/wiki/Flakes) for more details.

## Contributing

Contributions are welcome! Please open issues or pull requests on GitHub.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

## Acknowledgements

- [pydicom](https://github.com/pydicom/pydicom) for DICOM file handling
- [PyQt5](https://riverbankcomputing.com/software/pyqt/intro) or [Tkinter] for GUI (depending on implementation)
