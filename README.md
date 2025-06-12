# FM-Dicom Tag Editor


**2.0 UPDATE**

A robust Python GUI for editing DICOM tags. This tool allows you to view and modify metadata in DICOM files, making it useful for medical imaging professionals, researchers, and developers working with DICOM datasets.

I am not a programmer, I do understand alot of the concepts but AI has certainly helped make this possible for me.
If there is something you think I should add  or maybe something you think needs modifying please let me know.

![FM-DICOM Logo](fm_dicom/fm-dicom.png)

## Features

- View DICOM file metadata
- Load DICOM dir/zip files/ just plain dcm files in a folder.
- Edit, add, or remove DICOM tags
- Delete instances/series/studies/patients
- Merge patients/studies/series
- Anonomize imaging based on template (reaserch, clinical, etc), create your own tempaltes.
- DICOM tag validations, potentially find errors in existing imaging that you have.
- DICOM file analyzing, determine your picture resolutions, file sizes etc.
- DICOM performance testing, get a list of slow to load instances, file sizes.
- Save all of the above reports to csv for further manipulation if needed. 
- DICOM send instances/series/studies or patients to another PACS device.
- Save changes back to DICOM files/zip/dicomdir & zip file.
- Basic Image viewer
- Support for JPEG2000, and if dicom sending to a pacs that doesn't support that format then it will be converted automatically and resent.
- Cross-platform support (Linux, Windows)
- Nix/NixOS support for reproducible development and deployment

## Installation

### Windows

For Windows users, download the latest `.exe` (portable) release from the [GitHub Releases page](https://github.com/yourusername/dicom-tag-editor/releases).  
Simply run the `.exe` file. No installation is required.


### Nix test it without installing it!

```bash
    nix run github:FullMetalEd/fm-dicom
```

### Adding to Your NixOS System Configuration via FLAKES!!

You can install `fm-dicom` system-wide on NixOS so it is always available for all users. Here’s how:

1. **Add the repository as an input to your `flake.nix`:**

   Open your system's `flake.nix` (usually in `/etc/nixos/flake.nix` or your NixOS configuration repo) and add the dicom-tag-editor github repo to your inputs section (it should looks something like below):

   ```nix
   inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-25.05";
    nixpkgs-unstable.url = "github:nixos/nixpkgs/nixpkgs-unstable";
    zen-browser.url = "github:0xc000022070/zen-browser-flake";
    fm-dicom.url = "github:fullmetaled/fm-dicom";
};
   ```

2. **Add the package to your system packages:**

   In your `flake.nix` under 'nixosConfigurations' in the 'modules' list add the package to `environment.systemPackages`. For example:

   ```nix
   modules = [
            # List of the config files this profile needs.
            ./configuration.nix
            (
              {nixpkgs, ...}:
                {
                  environment.systemPackages = [
                    zen-browser.packages."${systemSettings.system}".default
                    fm-dicom.packages."${systemSettings.system}".default
                  ];
                }
            )
          ];
   ```


3. **Rebuild your system:**

   Apply your changes by running:

   ```sh
   sudo nixos-rebuild switch --flake /etc/nixos#your-hostname
   ```

   Replace `/etc/nixos` and `your-hostname` with your actual flake path and hostname.

After rebuilding, you can launch `fm-dicom` from your terminal or application menu.

## Nix Development Environment

This project includes a `flake.nix` for reproducible development. To enter the development environment, clone the repo to your system and in the top directory run this:

```sh
nix develop
```

This will provide you with UV, Python, all required libraries, and any other tools needed for development.

You can run the project with:

**NIX**
```bash
nix run #fm_dicom
```

**UV**
```bash
uv sync && uv run -m fm-dicom.main 
```
Optionally you can pass the path to a ```.dcm``` or ```.zip``` file:
```bash
uv sync && uv run -m fm-dicom.main ~/Downloads/exported_study.zip
```


## Configuration file:

fm-dicom requires a config.yml file for setting persistent settings you may want. Please find below an example config. If you have issues with the config not being read properly please look at the logs, on Windows; in your user's ```appdata``` folder, on linux: ```~.local/share/fm-dicom```.

```yaml
log_path: "~/.local/share/fm-dicom/fm-dicom.log"
log_level: "INFO"
show_image_preview: true
file_picker_native: true
window_size: [1500, 1000]
theme: "dark"
language: "en"
default_export_dir: ~/Downloads/fm-dicom/exports
default_import_dir: ~/Downloads/fm-dicom/imports
ae_title: "FM-DICOM"
destinations:
  - label: "Our Primary PACS"
    ae_title: "DICOMPACS"
    host: "192.168.0.12"
    port: 11112
```


## Contributing

Contributions are welcome! Please open issues or pull requests on GitHub.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.


## Acknowledgements

- [pydicom](https://github.com/pydicom/pydicom) for DICOM file handling
- [PyQt6](https://riverbankcomputing.com/software/pyqt/intro) or [Tkinter] for GUI (depending on implementation)
- nump
- pyyaml
- pynetdicom


## Docker Image

**Docker** is not a viable option for this application since there is a GUI. If you really want to dockerize it, you can there is guides out there to allow you to remote  into the container and access the UI. But I would advise again that since this is also interacting dynamically with your file system. Unless you really want to limit the folders it can access to a bind mount.
