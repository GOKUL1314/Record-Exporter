# Record Exporter

A FastAPI web tool that lets you upload any Excel workbook (`.xlsx` or `.xls`), choose specific records, automatically fetch structured sections from each record's linked web page, and download individual records in **Excel (`.xlsx`)**, **CSV**, **JSON**, or **PDF**.

## Features

- **Dynamic Excel support**: Works with any number of columns, `.xlsx` and `.xls`, merged cells, blank headers (`Column N`), Excel dates (`DD-MM-YYYY`) and times (`HH:MM`), and duplicate rows.
- **Smart defaults**: Automatically selects the `"All Data"` sheet (if present) and auto-detects the link column while avoiding `"Source"` columns. Supports `"No link column"` to skip scraping.
- **Flexible record selection**: Supports `1,2,3`, `1-5`, `1,3-6`, and `all` (up to 200 records per request).
- **Flexible page section extraction**: Tries HTTP first, strips scripts/navigation/cookie banners, checks embedded JSON-LD / `__NEXT_DATA__`, and falls back to Playwright headless Chromium for JavaScript-rendered pages. Captures whatever sections each page contains without hardcoding section names.
- **Reliability & caching**: 15s timeout, 1 retry, max 5 concurrent requests, live streaming progress (`Fetching X of Y`), and per-session caching so exporting multiple formats does not re-fetch URLs.
- **Export rules**:
  - 1 selected record downloads directly as `{record_number}.{ext}` (e.g., `1.xlsx`).
  - 2 or more selected records download as `records_{ext}.zip` containing `1.{ext}`, `2.{ext}`, etc.
  - Formula-injection protection (`=`, `+`, `-`, `@` prefixed with `'`) in Excel and CSV exports.
  - Unicode-safe PDF output using bundled **DejaVu Sans** fonts (`app/assets/fonts/`).
- **Security**: Upload limit 10 MB, SSRF protection blocking localhost/private/internal IP ranges, HTML escaping in the UI, and automatic 1-hour upload cleanup.

## Setup

1. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Install the Playwright Chromium browser (one-time setup for JavaScript-rendered page fallback):
   ```bash
   playwright install chromium
   ```
   > Note: If Chromium is not installed, static HTTP and embedded JSON pages still work normally, and JS-only pages gracefully report `"Could not fetch: browser not installed"` instead of crashing.

## Running the App

```bash
python run.py
```

Then open http://localhost:8000 in your browser.

## Running Tests

```bash
python -m pytest -v
```

## Project Structure

```text
record-exporter/
  README.md
  requirements.txt
  run.py
  .gitignore
  app/
    __init__.py
    main.py
    config.py
    schemas.py
    assets/
      fonts/
        DejaVuSans.ttf
        DejaVuSans-Bold.ttf
    routes/
      upload.py
      records.py
      details.py
      download.py
    services/
      excel_reader.py
      record_selector.py
      page_scraper.py
      url_safety.py
      session_store.py
      zip_builder.py
      exporters/
        __init__.py
        base.py
        excel_exporter.py
        csv_exporter.py
        json_exporter.py
        pdf_exporter.py
  static/
    index.html
    css/style.css
    js/app.js
  tests/
    test_record_selector.py
    test_excel_reader.py
    test_page_scraper.py
    test_exporters.py
    sample/luma_sf_events.xlsx
  uploads/
```
