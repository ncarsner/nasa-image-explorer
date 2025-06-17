from fastapi import FastAPI
from nicegui import ui
from ui import render_main_page
import httpx
from nasa_api import search_images

# Project Structure
"""
nasa-image-explorer/
│
├── app.py                  # Main FastAPI + NiceGUI app entrypoint
├── nasa_api.py             # NASA Open API client (no API key needed)
├── ui.py                   # NiceGUI UI components and layout
├── requirements.txt        # Python dependencies
├── .pre-commit-config.yaml # Pre-commit hooks config
├── README.md               # Project overview and instructions
└── tests/
    └── test_nasa_api.py    # Basic tests for NASA API client
"""

app = FastAPI()

# TODO: Mount NiceGUI to FastAPI
# TODO: Add root endpoint to render_main_page

if __name__ == "__main__":
    ...
    # TODO: Run NiceGUI app
    # ui.run(app, title='NASA Image Explorer')


# Next Steps:
# 1. Implement NASA API client in nasa_api.py
# 2. Build UI in ui.py using NiceGUI
# 3. Wire up FastAPI and NiceGUI in app.py
# 4. Add pre-commit hooks and write tests
