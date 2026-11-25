# Project Notes — Record Exporter

## 1. Installed Packages and Libraries

### Python Runtime & Dependencies (`requirements.txt`)
All Python packages currently installed in this environment (Python 3.11.9):

| Package | Installed Version | Purpose in Record Exporter |
| :--- | :--- | :--- |
| `fastapi` | `0.165.0` | Backend web framework and REST/streaming API routes |
| `uvicorn` | `0.54.0` | ASGI web server started by `run.py` |
| `python-multipart` | `0.0.34` | Handles `.xlsx`/`.xls` multipart file uploads |
| `openpyxl` | `3.1.5` | Reads `.xlsx` workbooks and writes exported `.xlsx` files |
| `xlrd` | `2.0.2` | Reads legacy `.xls` workbooks |
| `httpx` | `0.28.1` | Async HTTP client for fetching linked web pages |
| `beautifulsoup4` | `4.15.0` | Parses HTML and extracts page title & dynamic sections |
| `lxml` | `6.1.3` | Fast HTML/XML parser backend for BeautifulSoup |
| `playwright` | `1.65.2` | Headless browser fallback for JavaScript-rendered pages |
| `reportlab` | `5.0.1` | Generates Unicode-safe `.pdf` exports |
| `pytest` | `9.2.0` | Runs the unit test suite (`tests/`) |

> Note: `fastapi` (`0.165.0`) and `xlrd` (`2.0.2`) were installed specifically during setup; the other dependencies were already available in the Python environment.

### Bundled Assets & Standard Library
- **Bundled Fonts (`app/assets/fonts/`)**: `DejaVuSans.ttf` and `DejaVuSans-Bold.ttf` are included in the repository so PDF exports render Unicode characters properly on Windows.
- **Python Standard Library**: `csv`, `json`, `zipfile`, `asyncio`, `ipaddress`, `socket`, `uuid`, `pathlib`, `re`, `datetime`.
- **Frontend**: Plain HTML, CSS, and JavaScript (`static/index.html`, `static/css/style.css`, `static/js/app.js`) — no Node.js or frontend build tools are required.

---

## 2. What to Install Before Running

1. **Python 3.11+** (verified with Python `3.11.9`).
2. **Install Python dependencies** from the project root (`record-exporter`):
   ```bash
   pip install -r requirements.txt
   ```
3. **Install Playwright Chromium browser (one-time setup)** so JavaScript-rendered event pages can be scraped when static HTTP HTML is empty:
   ```bash
   playwright install chromium
   ```
   > If you skip this step, static HTML and embedded JSON pages still work, and JS-only pages will safely report `"Could not fetch: browser not installed"` instead of crashing.

---

## 3. How to Run the Project

1. Open a terminal in the project folder (`record-exporter`).
2. Start the server:
   ```bash
   python run.py
   ```
3. Open your browser and go to:
   ```text
   http://localhost:8000
   ```
4. Upload an `.xlsx` or `.xls` file (up to 10 MB), pick the sheet and link column, enter record numbers (e.g., `1,2`, `1-5`, or `all`), click **Show records**, and download as **Excel**, **CSV**, **JSON**, or **PDF**.

### Running the Tests
```bash
python -m pytest -v
```
