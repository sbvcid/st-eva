"""
End-to-End Real Browser Smoke Tests using Playwright.
Verifies real Chromium execution against live FastAPI static serving and background jobs:
- Desktop: AAPL analysis end-to-end, TSM contract refusal (1st class UX), invalid ticker
- Mobile viewports (375px, 390px, 430px): layout sanity, no horizontal overflow, buttons/cards visible
"""

import time
import threading
import socket
import tempfile
import unittest
import uvicorn
from playwright.sync_api import sync_playwright

from web.app import create_app


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class TestBrowserSmoke(unittest.TestCase):
    server_thread = None
    server = None
    port = None
    base_url = None
    archive_dir = None
    _archive_tmp = None

    @classmethod
    def setUpClass(cls):
        cls.port = find_free_port()
        cls.base_url = f"http://127.0.0.1:{cls.port}"

        # These tests run real analyses for real tickers. The archive directory
        # is redirected to a temporary directory so a test run never writes into
        # the operator's own archives under `data/archives`.
        cls._archive_tmp = tempfile.TemporaryDirectory(prefix="steva-browser-smoke-")
        cls.archive_dir = cls._archive_tmp.name

        app = create_app(archives_dir=cls.archive_dir)
        config = uvicorn.Config(app, host="127.0.0.1", port=cls.port, log_level="warning")
        cls.server = uvicorn.Server(config)

        cls.server_thread = threading.Thread(target=cls.server.run, daemon=True)
        cls.server_thread.start()

        # Wait for server to start
        for _ in range(50):
            try:
                with socket.create_connection(("127.0.0.1", cls.port), timeout=0.1):
                    break
            except (ConnectionRefusedError, OSError):
                time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        if cls.server:
            cls.server.should_exit = True
        if cls.server_thread:
            cls.server_thread.join(timeout=2.0)
        if cls._archive_tmp is not None:
            cls._archive_tmp.cleanup()

    def test_desktop_aapl_full_flow(self):
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(locale="en-US", viewport={"width": 1280, "height": 800})
            page = context.new_page()
            page.goto(self.base_url)

            # Check title and elements
            self.assertIn("ST-EVA", page.title())
            page.wait_for_selector("text=Reverse-engineer market expectations")

            # Click AAPL quick example
            aapl_button = page.locator("button:has-text('AAPL')")
            aapl_button.click()

            # Wait for verdict and result cards (timeout up to 90s for live EDGAR/market data fetch)
            try:
                page.wait_for_selector("text=Analysis Verdict", timeout=90000)
            except Exception:
                print("Page content at timeout:\n", page.locator("body").inner_text())
                raise
            page.wait_for_selector("text=AAPL", timeout=10000)
            page.wait_for_selector("text=Market Price", timeout=5000)
            page.wait_for_selector("text=Admission Status:", timeout=5000)

            # Evidence accordion test
            evidence_btn = page.locator("button:has-text('Evidence & Regulatory Provenance')")
            evidence_btn.click()
            page.wait_for_selector("text=Source Attributions", timeout=5000)

            # Replay section
            page.wait_for_selector("text=Point-in-Time Replay Verification", timeout=5000)

            context.close()
            browser.close()

    def test_desktop_tsm_refusal_is_not_error(self):
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(locale="en-US", viewport={"width": 1280, "height": 800})
            page = context.new_page()
            page.goto(self.base_url)

            tsm_button = page.locator("button:has-text('TSM')")
            tsm_button.click()

            page.wait_for_selector("text=Analysis Verdict", timeout=60000)
            page.wait_for_selector("text=Admission Status: REFUSED", timeout=10000)

            # Verify no generic error banner
            self.assertEqual(page.locator("text=Analysis Request Error").count(), 0)

            # Verify refusal reason explanation is rendered
            self.assertGreater(page.locator("text=This issuer was legitimately withheld").count(), 0)

            context.close()
            browser.close()

    def test_invalid_ticker_handling(self):
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(locale="en-US", viewport={"width": 1280, "height": 800})
            page = context.new_page()
            page.goto(self.base_url)

            input_box = page.locator("input[placeholder*='Enter ticker']")
            input_box.fill("INVALID;;;TICKER")

            analyze_btn = page.locator("button:has-text('Analyze')")
            analyze_btn.click()

            # Expect 400 Bad Request message rendered cleanly in error box without white-screen crash
            page.wait_for_selector("text=Analysis Request Error", timeout=5000)
            page.wait_for_selector("text=Invalid ticker format", timeout=5000)

            context.close()
            browser.close()

    def test_browser_bilingual_switch(self):
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 800})
            page.goto(self.base_url)

            # Ensure header language switcher is present
            page.wait_for_selector("button:has-text('中文')")
            page.wait_for_selector("button:has-text('EN')")

            # Click 中文
            page.locator("button:has-text('中文')").click()
            page.wait_for_selector("text=反推市場定價預期")
            page.wait_for_selector("button:has-text('開始分析')")
            page.wait_for_selector("text=目前針對美國 SEC 申報企業最佳化")

            # Click EN
            page.locator("button:has-text('EN')").click()
            page.wait_for_selector("text=Reverse-engineer market expectations")
            page.wait_for_selector("button:has-text('Analyze')")

            browser.close()

    def test_mobile_viewports_sanity(self):
        viewports = [
            {"width": 375, "height": 667, "name": "iPhone SE / 375px"},
            {"width": 390, "height": 844, "name": "iPhone 13-15 / 390px"},
            {"width": 430, "height": 932, "name": "iPhone 15 Pro Max / 430px"},
        ]

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            for vp in viewports:
                context = browser.new_context(locale="en-US", viewport={"width": vp["width"], "height": vp["height"]})
                page = context.new_page()
                page.goto(self.base_url)

                page.wait_for_selector("input")
                page.wait_for_selector("button:has-text('Analyze')")

                # Verify no horizontal scroll / overflow
                scroll_width = page.evaluate("() => document.documentElement.scrollWidth")
                client_width = page.evaluate("() => document.documentElement.clientWidth")
                self.assertLessEqual(
                    scroll_width,
                    client_width + 1,
                    f"Horizontal overflow detected on viewport {vp['name']}: scrollWidth={scroll_width}, clientWidth={client_width}",
                )

                # Test typing and clicking MSFT regression fixture
                msft_btn = page.locator("button:has-text('MSFT')")
                msft_btn.click()

                # The analysis itself takes about three seconds against a cold
                # archive. Thirty seconds was enough when this suite reused a
                # pre-seeded archive under `data/archives`; now that it runs
                # against a fresh temporary directory every time, the first
                # request also pays for registry seeding, and a loaded machine
                # running the whole suite alongside it can exceed the old
                # budget. The wait is for a real completion condition, so a
                # longer budget costs nothing when the page is ready.
                page.wait_for_selector("text=Analysis Verdict", timeout=90000)

                # Verify cards are within viewport width
                card_box = page.locator("text=Microsoft Corporation").bounding_box()
                self.assertIsNotNone(card_box)
                self.assertLess(card_box["x"] + card_box["width"], vp["width"] + 5)

                page.close()

            browser.close()

    def test_pwa_metadata_and_service_worker(self):
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()
            page.goto(self.base_url)

            # Check PWA manifest link
            manifest_href = page.evaluate("() => document.querySelector('link[rel=\"manifest\"]')?.getAttribute('href')")
            self.assertEqual(manifest_href, "/manifest.webmanifest")

            # Check Apple Touch Icon
            apple_icon = page.evaluate("() => document.querySelector('link[rel=\"apple-touch-icon\"]')?.getAttribute('href')")
            self.assertEqual(apple_icon, "/icons/icon-192.png")

            # Check theme-color meta
            theme_color = page.evaluate("() => document.querySelector('meta[name=\"theme-color\"]')?.getAttribute('content')")
            self.assertEqual(theme_color, "#2563eb")

            # Wait for Service Worker registration
            sw_ready = page.evaluate("""async () => {
                if (!('serviceWorker' in navigator)) return false;
                try {
                    const reg = await navigator.serviceWorker.ready;
                    return reg && (reg.active !== null || reg.installing !== null || reg.waiting !== null);
                } catch (e) {
                    return false;
                }
            }""")
            self.assertTrue(sw_ready, "Service worker should register and reach ready state")

            context.close()
            browser.close()

    def test_offline_banner_and_offline_guard(self):
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(locale="en-US")
            page = context.new_page()
            page.goto(self.base_url)

            # Wait for initial load
            page.wait_for_selector("text=ST-EVA")

            # Simulate network offline
            context.set_offline(True)
            page.evaluate("() => window.dispatchEvent(new Event('offline'))")

            # Verify offline banner is displayed
            page.wait_for_selector("text=Offline Mode", timeout=5000)
            self.assertGreater(page.locator("text=Live financial valuation requires an active network connection").count(), 0)

            # Attempt analysis while offline
            input_box = page.locator("input[placeholder*='Enter ticker']")
            input_box.fill("AAPL")
            analyze_btn = page.locator("button:has-text('Analyze')")
            analyze_btn.click()

            # Verify offline guard message
            page.wait_for_selector("text=Offline: Live SEC ingestion and financial admission require network connectivity", timeout=5000)

            # Restore network
            context.set_offline(False)
            page.evaluate("() => window.dispatchEvent(new Event('online'))")

            # Verify offline banner disappears
            self.assertEqual(page.locator("text=Offline Mode").count(), 0)

            context.close()
            browser.close()


if __name__ == "__main__":
    unittest.main()
