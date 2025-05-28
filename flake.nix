{
  description = "Python Dev Environment for Nixos fm_dicom";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};

        # Define the installable package
        fm_dicom = pkgs.python3Packages.buildPythonApplication {
          pname = "fm-dicom";
          version = "0.1.0";

          src = ./.;

          pyproject = true;

          nativeBuildInputs = with pkgs.python3Packages; [
            hatchling
          ] ++ (with pkgs; [
            qt6.wrapQtAppsHook
            copyDesktopItems
          ]);

          propagatedBuildInputs = with pkgs.python3Packages; [
            numpy
            pydicom
            pyqt6
            pynetdicom
            pyyaml
            typer
          ];

          # System dependencies for PyQt6
          buildInputs = with pkgs; [
            qt6.qtbase
            qt6.qtwayland
          ];

          # Desktop entry configuration
          desktopItems = [
            (pkgs.makeDesktopItem {
              name = "fm-dicom";
              desktopName = "FM DICOM Tag Editor";
              comment = "Edit DICOM tags, merge patients and export/send changes";
              exec = "fm-dicom %F";
              icon = "fm-dicom";
              categories = [ "Graphics" "MedicalSoftware" "Utility" ];
              mimeTypes = [ "application/dicom" ];
              keywords = [ "DICOM" "Medical" "Imaging" "Tags" "Editor" ];
              startupNotify = true;
              terminal = false;
            })
          ];

          postInstall = ''
            # Create icons directories
            mkdir -p $out/share/icons/hicolor/48x48/apps
            cp ${./fm_dicom/fm-dicom.png} $out/share/icons/hicolor/48x48/apps/fm-dicom.png
          '';

          meta = with pkgs.lib; {
            description = "A basic wrapper for pydicom commands. Lets you edit DICOM tags, merge patients and then export/send the changes";
            license = licenses.mit;
            maintainers = [ ];
            mainProgram = "fm-dicom";
          };
        };
      in
      {
        # Make the package available
        packages = {
          default = fm_dicom;
          fm_dicom = fm_dicom;
        };

        # Development shell
        devShells.default = pkgs.mkShell {
          buildInputs = with pkgs; [
            python314
            uv
            gcc
            python3Packages.numpy
            python3Packages.pydicom
            python3Packages.pyqt6
            python3Packages.pynetdicom
          ];

          shellHook = ''
            rm -rf .venv
            uv venv .venv
            source .venv/bin/activate
            export PIP_REQUIRE_VIRTUALENV=true
            export PIP_USE_UV=1
            uv pip install -e .[dev]
          '';
        };

        # Make it available as an app you can run with nix run
        apps = {
          default = flake-utils.lib.mkApp {
            drv = fm_dicom;
            name = "fm-dicom";
          };
          fm_dicom = flake-utils.lib.mkApp {
            drv = fm_dicom;
            name = "fm-dicom";
          };
        };
      });
}