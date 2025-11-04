{
  description = "Python Dev Environment for Nixos fm_dicom";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
    nixgl.url = "github:guibou/nixGL";
  };

  outputs = { self, nixpkgs, flake-utils, nixgl }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        nixglPkg = nixgl.packages.${system}.nixGLIntel;

        # Define the installable package using Python 3.12 consistently
        fm_dicom = pkgs.python312Packages.buildPythonApplication {
          pname = "fm-dicom";
          version = "0.1.0";

          src = ./.;

          pyproject = true;

          nativeBuildInputs = with pkgs.python312Packages; [
            hatchling
          ] ++ (with pkgs; [
            qt6.wrapQtAppsHook
            copyDesktopItems
            makeWrapper
          ]);

          propagatedBuildInputs = with pkgs.python312Packages; [
            numpy
            pydicom
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
            qt6Packages.qt6ct
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
                pkgs.qt6Packages.qt6ct
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

        # Create nixGL-wrapped version for proper OpenGL support
        fm_dicom_wrapped = pkgs.writeShellScriptBin "fm-dicom" ''
          exec ${nixglPkg}/bin/nixGLIntel ${fm_dicom}/bin/fm-dicom "$@"
        '';
      in
      {
        # Make the package available
        packages = {
          default = fm_dicom_wrapped;  # Default to wrapped version with OpenGL support
          fm_dicom = fm_dicom_wrapped;
          fm_dicom_wrapped = fm_dicom_wrapped;
          fm_dicom_unwrapped = fm_dicom;  # Original package without nixGL wrapper
        };

        # Development shell
        devShells.default =
        let
          # Use Python 3.12 consistently to avoid version mismatches
          python = pkgs.python312;
          # Create a Python environment with all our dependencies
          pythonWithPackages = python.withPackages (ps: [
            ps.numpy
            ps.pydicom
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
            qt6Packages.qt6ct
            zenity
            xdg-desktop-portal
            xdg-desktop-portal-gtk
            # OpenGL dependencies for PyQt6
            libGL
            libGLU
            mesa
            # NixGL for OpenGL support
            nixglPkg
          ];

          shellHook = ''
            # Force uv to use the Nix-provided Python environment
            export UV_PYTHON=${pythonWithPackages}/bin/python

            # Add the current directory to Python path so it can find fm_dicom
            export PYTHONPATH="$PWD:$PYTHONPATH"

            # Qt6 environment variables for better Wayland/Hyprland support
            export QT_QPA_PLATFORM_PLUGIN_PATH="${pkgs.qt6.qtbase}/lib/qt-6/plugins:${pkgs.qt6.qtwayland}/lib/qt-6/plugins"
            export QT_PLUGIN_PATH="${pkgs.qt6.qtbase}/lib/qt-6/plugins:${pkgs.qt6.qtwayland}/lib/qt-6/plugins"

            # OpenGL library path for PyQt6
            export LD_LIBRARY_PATH="${pkgs.libGL}/lib:${pkgs.libGLU}/lib:${pkgs.mesa}/lib:${pkgs.mesa.drivers}/lib:$LD_LIBRARY_PATH"

            # Create convenience functions for running with OpenGL support
            function fm-dicom() {
              nixGLIntel uv run python -m fm_dicom "$@"
            }

            function fm-dicom-direct() {
              nixGLIntel python -m fm_dicom "$@"
            }

            echo "✅ UV_PYTHON set to: $UV_PYTHON"
            echo "✅ Python version: $(python --version)"
            echo "✅ PYTHONPATH includes current directory"
            echo "✅ Qt6 plugins configured for Wayland/Hyprland"
            echo "✅ OpenGL libraries configured with nixGL"
            echo ""
            echo "Python development environment ready!"
            echo "Python: $(python --version)"
            echo ""
            echo "To run FM-Dicom with OpenGL support:"
            echo "  fm-dicom gui                    # Using UV with nixGL wrapper"
            echo "  fm-dicom-direct gui             # Direct Python with nixGL wrapper"
            echo ""
            echo "Or manually:"
            echo "  nixGLIntel uv run python -m fm_dicom gui"
            echo "  nixGLIntel python -m fm_dicom gui"
            echo ""
            echo "Available Python packages:"
            python -c "import sys; print('PyQt6:', end=' '); import PyQt6; print('✅'); print('pydicom:', end=' '); import pydicom; print('✅', pydicom.__version__); print('gdcm:', end=' '); import gdcm; print('✅')" 2>/dev/null || echo "Some packages may need to be imported after starting"
          '';
        };

        # Make it available as an app you can run with nix run
        apps = {
          default = flake-utils.lib.mkApp {
            drv = fm_dicom_wrapped;
            name = "fm-dicom";
          };
          fm_dicom = flake-utils.lib.mkApp {
            drv = fm_dicom_wrapped;
            name = "fm-dicom";
          };
          # Unwrapped version (may not work with OpenGL)
          fm_dicom_unwrapped = flake-utils.lib.mkApp {
            drv = fm_dicom;
            name = "fm-dicom";
          };
        };
      });
}
