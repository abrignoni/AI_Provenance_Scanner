# AI_Provenance_Scanner
Script that uses exiftool and c2pa to identify metadata tags that indicate AI generation

Usage:

# ==============================
# Python dependencies
# ==============================
c2pa==0.14.0             # C2PA Python library
ExifTool==0.5.4          # Python wrapper for ExifTool
python-magic==0.5.0      # Optional: MIME type detection (requires libmagic)

# ==============================
# External / system dependencies
# ==============================
# ExifTool (required by ExifToolHelper)
#   macOS: brew install exiftool
#   Linux: sudo apt install libimage-exiftool-perl
#   Windows: Download from https://exiftool.org/ and add exiftool.exe to PATH
#
# Optional: 'file' command / libmagic for improved MIME detection
#   macOS/Linux: usually pre-installed
#   Windows: use python-magic-bin: pip install python-magic-bin

# ==============================
# Notes on script arguments
# ==============================
# --flattened : Show the fully flattened C2PA manifest in the human-readable report
#               By default, flattened manifest is hidden to keep reports concise.
# --json      : Output all data in JSON format
# --c2pa-only : Skip IPTC extraction and only process C2PA data

OpenAI image output example with C2PA metadata.
<img width="1559" height="532" alt="Screenshot 2025-12-26 at 11 32 11 PM" src="https://github.com/user-attachments/assets/56a88b2c-87b6-4aa9-af60-0c23bd5570d7" />

Google AI image output example with IPTC metadata.
<img width="1565" height="551" alt="Screenshot 2025-12-26 at 11 33 09 PM" src="https://github.com/user-attachments/assets/310f36d5-0c62-4c07-a095-edc79a919871" />
