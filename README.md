# nasa-image-explorer

Pybites Community Challenge: Build a NASA Image Explorer app using NASA Open APIs.

Search NASA's public [image library](https://images-api.nasa.gov) from a NiceGUI
front end served by FastAPI. No API key required.

## Layout

| File | Purpose |
| --- | --- |
| `app.py` | FastAPI app, `/api/search` JSON endpoint, NiceGUI mount |
| `nasa_api.py` | Async NASA Images API client |
| `ui.py` | NiceGUI search page and image gallery |
| `tests/` | Tests for the API client and the JSON endpoint |

## Setup

```bash
uv venv
uv pip install -r requirements.txt
pre-commit install
```

## Run

```bash
.venv/bin/python app.py
```

Then open <http://127.0.0.1:8000>. The same search is available as JSON at
`/api/search?q=mars&limit=10`, and the OpenAPI docs at `/docs`.

## Test

```bash
.venv/bin/python -m pytest
```
