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
            makeWrapper
          ]);

          propagatedBuildInputs = with pkgs.python3Packages; [
            numpy
            (pydicom.overridePythonAttrs (oldAttrs: {
              # Patch the PIL features import bug in pydicom 3.0.1
              postPatch = (oldAttrs.postPatch or "") + ''
                # Fix missing PIL.features import in pillow.py decoder
                sed -i 's/^def is_available/from PIL import features\ndef is_available/' src/pydicom/pixels/decoders/pillow.py
              '';
            }))
            pyqt6
            pynetdicom
            pyyaml
            typer
            gdcm
            pillow
          ];

          # System dependencies for PyQt6
          buildInputs = with pkgs; [
            qt6.qtbase
            qt6.qtwayland
            kdePackages.qtwayland  # Newer Qt6 Wayland implementation
            qt6ct
            zenity
            xdg-desktop-portal
            xdg-desktop-portal-gtk
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

            # Wrap the binary to include runtime dependencies
            wrapProgram $out/bin/fm-dicom \
              --prefix PATH : ${pkgs.lib.makeBinPath [
                pkgs.zenity
                pkgs.qt6ct
                pkgs.xdg-desktop-portal
                pkgs.xdg-desktop-portal-gtk
              ]} \
              --prefix QT_PLUGIN_PATH : "${pkgs.qt6.qtbase}/lib/qt-6/plugins:${pkgs.qt6.qtwayland}/lib/qt-6/plugins:${pkgs.kdePackages.qtwayland}/lib/qt-6/plugins"
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
        devShells.default =
        let
          # Create a Python environment with all our dependencies including patched pydicom
          pythonWithPackages = pkgs.python3.withPackages (ps: [
            ps.numpy
            (ps.pydicom.overridePythonAttrs (oldAttrs: {
              # Fix missing PIL.features import in pillow.py decoder
              postPatch = (oldAttrs.postPatch or "") + ''
                sed -i 's/^def is_available/from PIL import features\ndef is_available/' src/pydicom/pixels/decoders/pillow.py
              '';
            }))
            ps.pyqt6
            ps.pynetdicom
            ps.gdcm
            ps.pillow
            ps.pyyaml
            ps.typer
          ]);
        in
        pkgs.mkShell {
          buildInputs = with pkgs; [
            pythonWithPackages
            uv
            gcc
            ninja
            meson
            pkg-config
            libyaml
            cmake
            # Qt6 system dependencies
            qt6.qtbase
            qt6.qtwayland
            kdePackages.qtwayland
            qt6ct
            zenity
            xdg-desktop-portal
            xdg-desktop-portal-gtk
          ];

          shellHook = ''
            # Force uv to use the Nix-provided Python environment
            export UV_PYTHON=${pythonWithPackages}/bin/python

            # Add the current directory to Python path so it can find fm_dicom
            export PYTHONPATH="$PWD:$PYTHONPATH"

            # Qt6 environment variables for better Wayland/Hyprland support
            export QT_QPA_PLATFORM_PLUGIN_PATH="${pkgs.qt6.qtbase}/lib/qt-6/plugins:${pkgs.qt6.qtwayland}/lib/qt-6/plugins"
            export QT_PLUGIN_PATH="${pkgs.qt6.qtbase}/lib/qt-6/plugins:${pkgs.qt6.qtwayland}/lib/qt-6/plugins"

            echo "✅ UV_PYTHON set to: $UV_PYTHON"
            echo "✅ Python version: $(python --version)"
            echo "✅ PYTHONPATH includes current directory"
            echo "✅ Qt6 plugins configured for Wayland/Hyprland"
            echo ""
            echo "Python development environment ready!"
            echo "Python: $(python --version)"
            echo ""
            echo "To run FM-Dicom, use:"
            echo "  python -m fm_dicom gui"
            echo ""
            echo "Available Python packages:"
            python -c "import sys; print('PyQt6:', end=' '); import PyQt6; print('✅'); print('pydicom:', end=' '); import pydicom; print('✅', pydicom.__version__); print('gdcm:', end=' '); import gdcm; print('✅')" 2>/dev/null || echo "Some packages may need to be imported after starting"
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