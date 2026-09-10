# nasa-image-explorer

[![CI](https://github.com/ncarsner/nasa-image-explorer/actions/workflows/ci.yml/badge.svg)](https://github.com/ncarsner/nasa-image-explorer/actions/workflows/ci.yml)

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
| `.github/workflows/ci.yml` | Lint and test workflow |

## Setup

Requires Python 3.10 or newer.

```bash
uv venv
uv pip install -r requirements.txt
pre-commit install
```

## Run

```bash
.venv/bin/python app.py
```

Then open <http://127.0.0.1:8000>. Results are paged, 24 at a time, with
prev/next controls under the gallery. Clicking a result opens the largest
rendition NASA publishes for it, along with its date, photographer, center and
full description. The same search is available as JSON at
`/api/search?q=mars&page=2&limit=10`, and the OpenAPI docs at `/docs`.

The API serves at most 10,000 results for a query, so deep paging stops there
even when a search reports far more hits.

## Test

```bash
.venv/bin/python -m pytest
```

GitHub Actions runs `pre-commit run --all-files` and the test suite on Python
3.10 through 3.14 for every push to `main` and every pull request.
