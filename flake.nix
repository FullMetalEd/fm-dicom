{
  description = "Python Dev Environment for Nixos";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
      in
      {
        devShells.default = pkgs.mkShell {
          buildInputs = with pkgs; [
            python3
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

            uv pip install -e .
          '';
        };
      });
}
