"""
scholar.py: Google Scholar scraping via Playwright Python API.

Agent calls this script via bash:
  python -m agents.search_agent.scholar "quantum computing optimization" --max 10
  python -m agents.search_agent.scholar "attention mechanism" --download-dir /tmp/pdfs

Outputs JSON list of {title, url, snippet, citation_count, pdf_url} to stdout.
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.parse
import urllib.request
import shutil
from pathlib import Path


def search_scholar(query: str, max_results: int = 10) -> list[dict]:
    """
    Search Google Scholar and return paper metadata.

    Uses Playwright with Chromium. Adds human-like delays to avoid blocking.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.stderr.write(
            "playwright not installed. Run: pip install playwright && playwright install chromium\n"
        )
        return []

    encoded_query = urllib.parse.quote(query)
    url = f"https://scholar.google.com/scholar?q={encoded_query}&hl=en&as_sdt=0%2C5"
    results: list[dict] = []

    import os
    ws_endpoint = os.environ.get("PLAYWRIGHT_WS_ENDPOINT")

    with sync_playwright() as p:
        if ws_endpoint:
            try:
                browser = p.chromium.connect(ws_endpoint)
            except Exception as e:
                sys.stderr.write(f"[warning] Cannot connect to PLAYWRIGHT_WS_ENDPOINT ({e}), falling back to local launch\n")
                browser = p.chromium.launch(headless=True)
        else:
            browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
        )
        page = context.new_page()

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(2)

            try:
                page.click('button:has-text("Accept all")', timeout=3000)
                time.sleep(1)
            except Exception:
                pass

            for article in page.query_selector_all(".gs_r.gs_or.gs_scl")[:max_results]:
                try:
                    title_el = article.query_selector(".gs_rt a")
                    title    = title_el.inner_text() if title_el else ""
                    href     = title_el.get_attribute("href") if title_el else ""

                    snippet_el = article.query_selector(".gs_rs")
                    snippet    = snippet_el.inner_text() if snippet_el else ""

                    cite_el    = article.query_selector(".gs_fl a")
                    cite_count = ""
                    if cite_el:
                        text = cite_el.inner_text()
                        if "Cited by" in text:
                            cite_count = text.replace("Cited by", "").strip()

                    pdf_el  = article.query_selector(".gs_or_ggsm a")
                    pdf_url = pdf_el.get_attribute("href") if pdf_el else ""

                    if title:
                        results.append({
                            "title": title,
                            "url": href or "",
                            "snippet": snippet,
                            "citation_count": cite_count,
                            "pdf_url": pdf_url or "",
                        })
                except Exception as e:
                    sys.stderr.write(f"[warning] Failed to parse article: {e}\n")

        except Exception as e:
            sys.stderr.write(f"[error] Scholar scraping failed: {e}\n")
        finally:
            browser.close()

    return results


def download_pdf(url: str, output_path: str) -> str:
    """Download a PDF to output_path. Returns path on success, error string on failure."""
    dest = Path(output_path)
    dest.parent.mkdir(parents=True, exist_ok=True)

    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
            },
        )
        with urllib.request.urlopen(req, timeout=60) as resp, open(dest, "wb") as out:
            shutil.copyfileobj(resp, out)
        return str(dest)
    except Exception as e:
        return f"[error] Download failed: {e}"


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Search Google Scholar via Playwright")
    parser.add_argument("query", help="Search query")
    parser.add_argument("--max", type=int, default=10, dest="max_results",
                        help="Maximum results (default: 10)")
    parser.add_argument("--download-dir", default="",
                        help="Download PDFs into this directory")
    args = parser.parse_args()

    results = search_scholar(args.query, args.max_results)

    if args.download_dir:
        for r in results:
            if r.get("pdf_url"):
                safe_name = re.sub(r"[^\w\-_]", "_", r["title"])[:60]
                dest = Path(args.download_dir) / f"{safe_name}.pdf"
                r["downloaded_pdf"] = download_pdf(r["pdf_url"], str(dest))

    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
