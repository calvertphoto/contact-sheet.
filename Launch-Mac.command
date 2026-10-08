#!/bin/bash
set -e
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null 2>&1; then
  echo 'Install Python 3.12 or later from https://www.python.org/downloads/macos/ then run this again.'
  read -r -p 'Press Return to close.'
  exit 1
fi
if ! python3 -c 'import tkinter' >/dev/null 2>&1; then
  echo 'This Python lacks Tk. Install the Python.org macOS installer (includes Tk), then try again.'
  read -r -p 'Press Return to close.'
  exit 1
fi
if [ ! -d .venv ]; then python3 -m venv .venv; fi
if ! .venv/bin/python -c 'import PIL' >/dev/null 2>&1; then
  .venv/bin/python -m pip install -r requirements.txt
fi
.venv/bin/python app.py
