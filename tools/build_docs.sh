#!/bin/sh
# Build the User Guide: version from pyproject.toml, XeLaTeX (latexmk) into docs/build/,
# then copy the PDF into the package (src/daftarche/data/user_guide.pdf). Needs a TeX
# installation with XeLaTeX (MacTeX has it).
set -e
cd "$(dirname "$0")/.."
version=$(sed -n 's/^version = "\(.*\)"/\1/p' pyproject.toml)
printf '\\newcommand{\\AppVersion}{%s}\n' "$version" > docs/version.tex
cd docs
latexmk -xelatex -interaction=nonstopmode -halt-on-error -outdir=build user_guide.tex
cd ..
cp docs/build/user_guide.pdf src/daftarche/data/user_guide.pdf
echo "User Guide $version -> src/daftarche/data/user_guide.pdf"
