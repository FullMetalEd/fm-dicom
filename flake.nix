{
  description = "Python Dev Environment for Nixos fm_dteditor";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};

        # Define the installable package
        dicomtageditor = pkgs.python3Packages.buildPythonApplication {
          pname = "dicomtageditor";
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
          ];

          # System dependencies for PyQt6
          buildInputs = with pkgs; [
            qt6.qtbase
            qt6.qtwayland
          ];

          # Desktop entry configuration
          desktopItems = [
            (pkgs.makeDesktopItem {
              name = "dicomtageditor";
              desktopName = "DICOM Tag Editor";
              comment = "Edit DICOM tags, merge patients and export/send changes";
              exec = "dicomtageditor %F";
              icon = "dicomtageditor";
              categories = [ "Graphics" "MedicalSoftware" "Utility" ];
              mimeTypes = [ "application/dicom" ];
              keywords = [ "DICOM" "Medical" "Imaging" "Tags" "Editor" ];
              startupNotify = true;
              terminal = false;
            })
          ];

          # Install icon if you have one
          postInstall = ''
            # Create icons directories
            mkdir -p $out/share/icons/hicolor/48x48/apps
            mkdir -p $out/share/icons/hicolor/scalable/apps
            
            # If you have an icon file, copy it here
            # For now, we'll create a placeholder or you can add your own icon
            # cp ${./icons/dicomtageditor.png} $out/share/icons/hicolor/48x48/apps/dicomtageditor.png
            # cp ${./icons/dicomtageditor.svg} $out/share/icons/hicolor/scalable/apps/dicomtageditor.svg
            
            # Alternative: Use a system icon as fallback
            ln -sf ${pkgs.gnome.adwaita-icon-theme}/share/icons/Adwaita/48x48/mimetypes/text-x-generic.png \
              $out/share/icons/hicolor/48x48/apps/dicomtageditor.png
          '';

          meta = with pkgs.lib; {
            description = "A basic wrapper for pydicom commands. Lets you edit dicom tags, merge patients and then export/dicom send the changes";
            license = licenses.mit;
            maintainers = [ ];
            mainProgram = "dicomtageditor";
          };
        };
      in
      {
        # Make the package available
        packages = {
          default = dicomtageditor;
          dicomtageditor = dicomtageditor;
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
            drv = dicomtageditor;
            name = "dicomtageditor";
          };
          dicomtageditor = flake-utils.lib.mkApp {
            drv = dicomtageditor;
            name = "dicomtageditor";
          };
        };
      });
}