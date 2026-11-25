import asyncio
import pytest

from app.schemas import PageDetails
from app.services import page_scraper
from app.services.page_scraper import extract_page_details, fetch_page_details
from app.services.url_safety import UnsafeURLError, validate_url


def test_url_safety_blocks_private_and_non_http():
    for bad in [
        "http://localhost:8000",
        "http://127.0.0.1/admin",
        "http://169.254.169.254/latest/meta-data",
        "http://10.0.0.1/internal",
        "http://192.168.1.10",
        "file:///etc/passwd",
        "javascript:alert(1)",
    ]:
        with pytest.raises(UnsafeURLError):
            validate_url(bad, resolve_dns=False)

    assert validate_url("https://luma.com/32d8mqid", resolve_dns=False) == "https://luma.com/32d8mqid"


def test_extract_page_details_flexible_sections_and_strips_noise():
    html = """
    <html>
      <head><title>Demo Event · Luma</title></head>
      <body>
        <nav><a href="/">Home</a><a href="/explore">Explore</a></nav>
        <div class="cookie-banner">Accept cookies</div>
        <main>
          <h1>Demo Event</h1>
          <div class="content-card">
            <div class="card-title"><div class="title-label">About Event</div></div>
            <div class="content">
              <p>Welcome to the demo.</p>
              <h1>&#8203; The Challenge</h1>
              <p>Build something useful.</p>
              <h1>&#8203; Prizes</h1>
              <ul><li>First prize: $1000</li><li>Second prize: Swag</li></ul>
            </div>
          </div>
          <div class="content-card">
            <div class="card-title"><div class="title-label">Location</div></div>
            <div class="content">
              <p>San Francisco, CA</p>
            </div>
          </div>
        </main>
        <footer>Copyright 2026</footer>
      </body>
    </html>
    """
    details = extract_page_details(html, "https://luma.com/demo")
    assert details.title == "Demo Event · Luma"
    headings = [s.heading for s in details.sections]
    assert headings == ["About Event", "The Challenge", "Prizes", "Location"]
    assert "Accept cookies" not in details.sections[0].content
    assert "- First prize: $1000\n- Second prize: Swag" in details.sections[2].content
    assert details.sections[3].content == "San Francisco, CA"


def test_extract_page_details_uses_json_ld_fallback():
    html = """
    <html>
      <head>
        <title>JS Page</title>
        <script type="application/ld+json">
          {
            "@context": "https://schema.org",
            "@type": "Event",
            "name": "AI Meetup",
            "description": "An evening of demos and lightning talks in downtown SF.",
            "location": {"@type": "Place", "name": "SF Hub"}
          }
        </script>
      </head>
      <body><div id="__next"></div></body>
    </html>
    """
    details = extract_page_details(html, "https://example.com/event")
    assert [s.heading for s in details.sections] == ["Description", "Location"]
    assert "lightning talks" in details.sections[0].content
    assert "SF Hub" in details.sections[1].content


def test_fetch_page_details_reports_browser_not_installed(monkeypatch):
    async def fake_httpx(url: str):
        return url, "<html><body><div id='root'></div><noscript>Enable JavaScript</noscript></body></html>"

    async def fake_pw(url: str):
        raise RuntimeError("browser not installed")

    monkeypatch.setattr(page_scraper, "validate_url", lambda u, resolve_dns=True: u)
    monkeypatch.setattr(page_scraper, "_fetch_html_httpx", fake_httpx)
    monkeypatch.setattr(page_scraper, "_fetch_html_playwright", fake_pw)

    result: PageDetails = asyncio.run(fetch_page_details("https://example.com/spa"))
    assert result.fetch_status == "Could not fetch: browser not installed"
    assert result.sections == []


def test_fetch_page_details_blocks_ssrf_without_network():
    result = asyncio.run(fetch_page_details("http://127.0.0.1:9000/secret"))
    assert result.fetch_status.startswith("Could not fetch:")
