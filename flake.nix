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
          
          # Qt wrapping is handled by wrapQtAppsHook
          
          meta = with pkgs.lib; {
            description = "A basic wrapper for pydicom commands. Lets you edit dicom tags, merge patients and then export/dicom send the changes";
            license = licenses.mit; # Change to appropriate license
            maintainers = [ ];
          };
        };
      in
      {
        # Make the package available
        packages = {
          default = dicomtageditor;
          dicomtageditor = dicomtageditor;
        };
        
        # Development shell (your existing setup)
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