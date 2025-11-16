# Building CSV Converter Executable

This document explains how to build the CSV Converter application into a standalone Windows executable.

## Prerequisites

Make sure you have all dependencies installed in conda:

```bash
conda env create -f environment.yaml
conda activate csvtool
```

## Building the Executable

### Option 1: Using the Spec File (Recommended)

Simply run:

```bash
pyinstaller converter.spec
```

## Output

The executable will be created in the `dist/` folder:

- `dist/csv_converter.exe` - Your standalone executable

## File Structure

The build process bundles:

- All Python code (app.py, helpers.py, partijen.py)
- All dependencies (pandas, numpy, ttkbootstrap, etc.)
- Icon file: `assets/gewoonhout.ico`
- Data file: `assets/categories.csv`

## Build Artifacts

PyInstaller creates several folders:

- `build/` - Temporary build files (can be deleted)
- `dist/` - Contains the final executable
- `converter.spec` - Build configuration file

## Clean Build

To rebuild from scratch:

```bash
# Remove build artifacts
rmdir /s /q build dist
del converter.spec

# Rebuild
pyinstaller converter.spec
```

## Notes

- The executable will be approximately 50-100 MB due to pandas/numpy dependencies
- First launch may be slower as PyInstaller extracts files to a temp directory
- Antivirus software may flag PyInstaller executables - this is a false positive
- The icon (`assets/gewoonhout.ico`) will be embedded in the executable

## Troubleshooting

### Missing dependencies

If the executable fails to run, check for missing hidden imports. Add them to the `hiddenimports` list in `converter.spec`.

### File not found errors

Ensure all data files are listed in the `datas` section of `converter.spec`.

### Icon not showing

Verify the icon file exists at `assets/gewoonhout.ico` and is in .ico format.
