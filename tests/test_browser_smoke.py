"""
End-to-End Real Browser Smoke Tests using Playwright.
Verifies real Chromium execution against live FastAPI static serving and background jobs:
- Desktop: AAPL analysis end-to-end, TSM contract refusal (1st class UX), invalid ticker
- Mobile viewports (375px, 390px, 430px): layout sanity, no horizontal overflow, buttons/cards visible
- Live mode selection: the browser request carries mode=live and the selected
  assumptions, and the drawer renders that request's result rather than a
  previous one (stubbed route contract; no market data is baked into it)
"""

import json
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

    def test_research_surface_reads_the_research_api_end_to_end(self):
        """
        The research surface against the real research API.

        The research path is served by the same application, on its own
        route, with no route interception: what the browser reads here is
        what a user would read. A research metric is not chosen for the
        user, the refused dates carry their reasons, the calculation runs,
        and the result says it is not a valuation reference.
        """
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(locale="en-US", viewport={"width": 1280, "height": 900})
            page = context.new_page()
            page.goto(self.base_url)

            # The valuation surface is what the application opens on.
            page.wait_for_selector("button:has-text('Analyze')")

            # The research surface is entered from the header.
            page.click("[data-testid='mode-research']")
            page.wait_for_selector("[data-testid='research-notice']")
            page.wait_for_selector("[data-testid='research-metric-select']")

            # The research-only standing is stated before any figure.
            page.wait_for_selector("text=not a valuation reference")

            # No research metric is chosen for the user.
            selected = page.eval_on_selector(
                "[data-testid='research-metric-select']", "e => e.value"
            )
            self.assertEqual(selected, "")
            self.assertIsNone(
                page.query_selector("[data-testid='research-metric-card']")
            )

            # The user chooses one, and the metric's own figures arrive.
            page.select_option(
                "[data-testid='research-metric-select']",
                "RESEARCH_KO_REPORTED_REVENUE_MULTIPLE",
            )
            page.wait_for_selector("[data-testid='research-metric-card']")
            page.wait_for_selector("text=us-gaap:Revenues")
            page.wait_for_selector("[data-testid='research-valid-count']")

            # The refused dates are shown with the reason they were refused.
            page.wait_for_selector("text=RESEARCH_REASON_NO_DENOMINATOR_WINDOW")

            # The calculation runs and produces a figure.
            page.click("[data-testid='research-calculate']")
            page.wait_for_selector("[data-testid='research-result']")
            page.wait_for_selector("[data-testid='research-implied-denominator']")
            page.wait_for_selector("text=not a valuation reference")

            # The evidence of one evaluation date can be opened.
            page.click("[data-testid='research-open-2026-07-29']")
            page.wait_for_selector("[data-testid='research-evidence']")

            context.close()
            browser.close()

    def test_research_comparison_reads_the_real_comparison_api(self):
        """
        The comparison surface against the real comparison API.

        The paired comparison of the two enterprise-value lanes is read from
        the service, not from a stub: the paired count, the attributable
        count and the unpaired dates all come from the observation records.
        """
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                locale="en-US", viewport={"width": 1280, "height": 900}
            )
            page = context.new_page()
            page.goto(self.base_url)

            page.click("[data-testid='mode-research']")
            page.wait_for_selector("[data-testid='research-compare']")

            # The comparison surface chooses no metric for the user.
            page.click("[data-testid='compare-mode-pair']")
            page.wait_for_selector("[data-testid='compare-left-metric']")
            left = page.eval_on_selector(
                "[data-testid='compare-left-metric']", "e => e.value"
            )
            self.assertEqual(left, "")

            page.select_option(
                "[data-testid='compare-left-metric']",
                "RESEARCH_KO_FILED_EV_BRIDGE_MULTIPLE_PRODUCTION_SHAPE",
            )
            page.select_option(
                "[data-testid='compare-right-metric']",
                "RESEARCH_KO_FILED_EV_BRIDGE_MULTIPLE_SHORT_TERM_BORROWINGS",
            )
            page.click("[data-testid='compare-run']")

            page.wait_for_selector("[data-testid='compare-pairs-result']")
            page.wait_for_selector("[data-testid='compare-compatibility-statement']")
            paired = page.text_content("[data-testid='compare-paired-count']")
            attributable = page.text_content(
                "[data-testid='compare-attributable-count']"
            )
            self.assertEqual(paired, "16")
            self.assertEqual(attributable, "16")
            # The dates that are not paired are shown with their reasons.
            page.wait_for_selector("[data-testid='compare-unpaired']")
            unpaired = page.text_content("[data-testid='compare-unpaired']")
            self.assertIn("RESEARCH_REASON_MIXED_BALANCE_SHEET_PERIODS", unpaired)
            self.assertIn("RESEARCH_REASON_INCOMPLETE_EV_BRIDGE", unpaired)

            context.close()
            browser.close()

    def test_research_surface_switches_issuers_against_the_real_api(self):
        """
        Cross-issuer selection through the real research API, no stubs.

        The catalogue is the API's own, the three issuers' lanes each show
        their own basis, median, count and status, and nothing of the lane
        the user left behind stays on the card. The unavailable MSFT lane is
        selectable and says why it holds no figure, and a reverse calculation
        on it is refused by the real API rather than answered with a
        fabricated multiple.
        """
        candidate_ids = [
            "RESEARCH_KO_REPORTED_REVENUE_MULTIPLE",
            "RESEARCH_KO_REPORTED_OPERATING_PROFIT_PLUS_REPORTED_D_AND_A_MULTIPLE",
            "RESEARCH_KO_FILED_EV_BRIDGE_MULTIPLE_PRODUCTION_SHAPE",
            "RESEARCH_KO_FILED_EV_BRIDGE_MULTIPLE_SHORT_TERM_BORROWINGS",
            "RESEARCH_AAPL_REPORTED_REVENUE_MULTIPLE",
            "RESEARCH_AAPL_REPORTED_OPERATING_PROFIT_PLUS_REPORTED_D_AND_A_MULTIPLE",
            "RESEARCH_AAPL_FILED_EV_BRIDGE_MULTIPLE_PRODUCTION_SHAPE",
            "RESEARCH_MSFT_REPORTED_REVENUE_MULTIPLE",
            "RESEARCH_MSFT_REPORTED_OPERATING_PROFIT_PLUS_REPORTED_D_AND_A_MULTIPLE",
            "RESEARCH_MSFT_FILED_EV_BRIDGE_MULTIPLE_OVER_REVENUE",
        ]

        def card_text(page):
            return page.locator(
                "[data-testid='research-metric-card']"
            ).inner_text()

        def wait_for_median(page, median: str):
            # Wait for the selected lane's own figure, not a fixed delay.
            page.wait_for_function(
                "expected => document.querySelector("
                "\"[data-testid='research-median']\")?.textContent === expected",
                arg=median,
            )

        def wait_for_status(page, status: str):
            page.wait_for_function(
                "expected => document.querySelector("
                "\"[data-testid='research-distribution-status']\")"
                "?.dataset.status === expected",
                arg=status,
            )

        def assert_notice(page):
            page.wait_for_selector("[data-testid='research-notice']")
            self.assertIn(
                "not a valuation reference",
                page.locator("[data-testid='research-notice']").inner_text(),
            )

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(locale="en-US", viewport={"width": 1280, "height": 900})
            page = context.new_page()
            page.goto(self.base_url)

            page.wait_for_selector("button:has-text('Analyze')")
            page.click("[data-testid='mode-research']")
            page.wait_for_selector("[data-testid='research-metric-select']")
            assert_notice(page)

            # The catalogue is the API's own: exactly the candidate research
            # metrics, and no diagnostic. The options arrive with the
            # catalogue fetch, so the wait is for them, not a fixed delay.
            page.wait_for_function(
                "() => document.querySelector("
                "\"[data-testid='research-metric-select']\")?.options.length > 1"
            )
            options = page.eval_on_selector(
                "[data-testid='research-metric-select']",
                "e => Array.from(e.options).map(o => o.value)",
            )
            self.assertEqual(sorted(options), sorted([""] + candidate_ids))
            self.assertNotIn(
                "RESEARCH_KO_FILED_EV_BRIDGE_MULTIPLE_DOUBLE_COUNTED_DIAGNOSTIC",
                options,
            )

            # -- AAPL: the homogeneous successor-only revenue sample. --------
            page.select_option(
                "[data-testid='research-metric-select']",
                "RESEARCH_AAPL_REPORTED_REVENUE_MULTIPLE",
            )
            wait_for_median(page, "7.257709")
            wait_for_status(page, "RESEARCH_DISTRIBUTION")
            aapl_card = card_text(page)
            self.assertIn("AAPL reported-revenue multiple", aapl_card)
            self.assertIn(
                "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
                aapl_card,
            )
            self.assertEqual(
                page.text_content("[data-testid='research-valid-count']"), "28"
            )
            assert_notice(page)

            # -- MSFT: its own lane, with none of AAPL's figures left. -------
            page.select_option(
                "[data-testid='research-metric-select']",
                "RESEARCH_MSFT_REPORTED_REVENUE_MULTIPLE",
            )
            wait_for_median(page, "10.848125")
            wait_for_status(page, "RESEARCH_DISTRIBUTION")
            msft_card = card_text(page)
            self.assertIn("MSFT reported-revenue multiple", msft_card)
            self.assertIn(
                "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
                msft_card,
            )
            self.assertEqual(
                page.text_content("[data-testid='research-valid-count']"), "33"
            )
            self.assertNotIn("7.257709", msft_card)
            self.assertNotIn("AAPL", msft_card)
            assert_notice(page)

            # -- KO: its own retired-element lane, with none of MSFT's left. -
            page.select_option(
                "[data-testid='research-metric-select']",
                "RESEARCH_KO_REPORTED_REVENUE_MULTIPLE",
            )
            wait_for_median(page, "6.403373")
            wait_for_status(page, "RESEARCH_DISTRIBUTION")
            ko_card = card_text(page)
            self.assertIn("KO reported-revenue multiple", ko_card)
            self.assertIn("us-gaap:Revenues", ko_card)
            self.assertEqual(
                page.text_content("[data-testid='research-valid-count']"), "29"
            )
            self.assertNotIn("10.848125", ko_card)
            self.assertNotIn("MSFT", ko_card)
            assert_notice(page)

            # -- The unavailable MSFT D&A lane: selectable, says why it has
            # no figure, and the real API refuses a reverse calculation on it
            # rather than producing a multiple.
            page.select_option(
                "[data-testid='research-metric-select']",
                "RESEARCH_MSFT_REPORTED_OPERATING_PROFIT_PLUS_REPORTED_D_AND_A_MULTIPLE",
            )
            wait_for_status(page, "RESEARCH_UNAVAILABLE")
            unavailable_card = card_text(page)
            self.assertIn(
                "MSFT reported operating profit plus reported depreciation and amortization multiple",
                unavailable_card,
            )
            self.assertIn("us-gaap:DepreciationDepletionAndAmortization", unavailable_card)
            self.assertEqual(
                page.text_content("[data-testid='research-median']"), "—"
            )
            self.assertEqual(
                page.text_content("[data-testid='research-valid-count']"), "0"
            )
            self.assertNotIn("6.403373", unavailable_card)
            self.assertNotIn("KO", unavailable_card)
            assert_notice(page)

            page.click("[data-testid='research-calculate']")
            page.wait_for_selector("[data-testid='research-error']")
            self.assertIn(
                "RESEARCH_CALCULATION_REFUSED_MULTIPLE_UNAVAILABLE",
                page.locator("[data-testid='research-error']").inner_text(),
            )
            self.assertIsNone(page.query_selector("[data-testid='research-result']"))

            context.close()
            browser.close()

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
                page.get_by_test_id("results-heading").wait_for(state="visible", timeout=90000)
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

            page.get_by_test_id("results-heading").wait_for(state="visible", timeout=60000)
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

                # Test typing and clicking MSFT, pinned to the offline
                # regression fixture so this layout check stays deterministic
                # (live is now the default mode).
                page.select_option("select >> nth=0", "regression")
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
                page.get_by_test_id("results-heading").wait_for(state="visible", timeout=90000)

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
            page.wait_for_selector("text=Offline Mode", state="detached", timeout=5000)
            self.assertEqual(page.locator("text=Offline Mode").count(), 0)

            context.close()
            browser.close()

    def test_desktop_matrix_audit_drawer_inspection(self):
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(locale="en-US", viewport={"width": 1280, "height": 800})
            page = context.new_page()
            page.goto(self.base_url)

            # Click MSFT quick example, pinned to the offline regression fixture
            # so the audit evidence ids stay deterministic (live is the default
            # mode now, so it must be selected explicitly).
            page.select_option("select >> nth=0", "regression")
            msft_btn = page.locator("button:has-text('MSFT')")
            msft_btn.click()

            page.get_by_test_id("results-heading").wait_for(state="visible", timeout=90000)
            page.wait_for_selector("text=Reverse Requirements Matrix", timeout=10000)

            # Locate row detail toggle button and expand
            toggle_btns = page.locator("button[title='Toggle details']")
            self.assertGreater(toggle_btns.count(), 0)
            toggle_btns.first.click()

            # Verify audit trail and reproducibility elements in real browser response
            page.wait_for_selector("text=Deterministic Calculation Steps", timeout=5000)
            page.wait_for_selector("text=Mathematically Verified", timeout=5000)
            page.wait_for_selector("text=Source Evidence & Provenance", timeout=5000)
            page.wait_for_selector("text=ev-price-001", timeout=5000)

            context.close()
            browser.close()

    def test_export_controls_trigger_real_downloads(self):
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                locale="en-US",
                viewport={"width": 1280, "height": 800},
                accept_downloads=True,
            )
            page = context.new_page()
            page.goto(self.base_url)

            # MSFT quick example, pinned to the offline regression fixture so the
            # export check stays deterministic (live is the default mode now).
            page.select_option("select >> nth=0", "regression")
            msft_btn = page.locator("button:has-text('MSFT')")
            msft_btn.click()
            page.get_by_test_id("results-heading").wait_for(state="visible", timeout=90000)
            page.wait_for_selector("text=Reverse Requirements Matrix", timeout=10000)

            # Export controls are present in the real browser response.
            self.assertGreater(page.get_by_test_id("export-json").count(), 0)
            self.assertGreater(page.get_by_test_id("export-csv").count(), 0)

            # JSON download is re-parseable and reflects the displayed result,
            # without the raw_analysis payload.
            with page.expect_download() as json_dl:
                page.get_by_test_id("export-json").click()
            json_path = json_dl.value.path()
            with open(json_path, "r", encoding="utf-8") as handle:
                envelope = json.load(handle)
            self.assertEqual(envelope["result"]["ticker"], "MSFT")
            self.assertNotIn("raw_analysis", envelope["result"])
            self.assertIn(
                "reverse_requirements_matrix",
                envelope["result"]["reverse_requirements"],
            )

            # CSV download carries the documented full-matrix header.
            with page.expect_download() as csv_dl:
                page.get_by_test_id("export-csv").click()
            csv_path = csv_dl.value.path()
            with open(csv_path, "r", encoding="utf-8") as handle:
                csv_text = handle.read()
            header = csv_text.splitlines()[0]
            self.assertIn("record_type", header)
            self.assertIn("required_eps_cagr", header)

            context.close()
            browser.close()


    def test_desktop_matrix_shows_limitations_for_a_computed_matrix(self):
        """
        A computed matrix still carries the supporting inputs it could not use.

        The offline regression fixture is deterministic and yields a COMPUTED
        matrix whose report also lists unavailable inputs, so the real SPA path
        is exercised without depending on live acquisition.

        Two things are asserted, and the second is the one that stops a
        limitation from being read as a failure: the section is rendered, and
        the matrix is still COMPUTED with its scenarios intact.
        """
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(locale="en-US", viewport={"width": 1280, "height": 800})
            page = context.new_page()
            page.goto(self.base_url)

            # Pinned to the offline regression fixture; live is the default now.
            page.select_option("select >> nth=0", "regression")
            page.locator("button:has-text('MSFT')").click()

            page.get_by_test_id("results-heading").wait_for(state="visible", timeout=90000)
            page.wait_for_selector("text=Reverse Requirements Matrix", timeout=10000)

            # The matrix computed, so the limitations are not a failure banner.
            page.wait_for_selector("text=COMPUTED", timeout=10000)

            section = page.get_by_test_id("limitations-section")
            section.wait_for(state="visible", timeout=10000)
            text = section.inner_text()
            self.assertIn("Unavailable supporting inputs", text)

            # The exact reasons the API supplied are what a reader sees, and the
            # list is rendered once rather than duplicated.
            self.assertIn(
                "No P/FCF reference multiple was supplied", text
            )
            self.assertIn(
                "No SEC regulatory filing observations of declared dividends",
                text,
            )
            self.assertEqual(section.count(), 1)

            # The scenarios are still rendered and still audit-able, so an
            # unavailable reference has not empties the matrix.
            toggles = page.locator("button[title='Toggle details']")
            self.assertGreater(toggles.count(), 0)
            toggles.first.click()
            page.wait_for_selector("text=Deterministic Calculation Steps", timeout=5000)

            context.close()
            browser.close()

    def test_desktop_matrix_renders_not_computed_limitations_once(self):
        """
        The NOT_COMPUTED path keeps its own status explanation and its list.

        TSM is a legitimate contract refusal, so its matrix is NOT_COMPUTED and
        deterministic without any stubbing. The unavailable list must render
        exactly once, inside the banner, and must not be repeated as a second
        standalone section.
        """
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(locale="en-US", viewport={"width": 1280, "height": 800})
            page = context.new_page()
            page.goto(self.base_url)

            page.wait_for_selector("text=Reverse-engineer market expectations", timeout=10000)
            tsm_btn = page.locator("button:has-text('TSM')")
            tsm_btn.click()
            page.wait_for_selector("text=Admission Status: REFUSED", timeout=60000)

            # The banner carries the status explanation rather than a limitations
            # heading, and the list appears once inside it. TSM's refusal path
            # deterministically reports unavailable entries, so this is
            # unconditional rather than guarded.
            banner = page.get_by_text(
                "The reverse requirements matrix could not be computed"
            )
            banner.wait_for(state="visible", timeout=15000)

            lists = page.get_by_test_id("unavailable-list")
            self.assertEqual(
                lists.count(), 1,
                "the NOT_COMPUTED list must render exactly once, not duplicated",
            )
            # The computed-state section must not also be present.
            self.assertEqual(
                page.get_by_test_id("limitations-section").count(), 0
            )

            context.close()
            browser.close()


if __name__ == "__main__":
    unittest.main()

# R3 regression: live-mode selection and assumption propagation through the
# real browser. The API is answered by a Playwright route so the test needs no
# network and no fixed market data; the response is *derived from the request's
# own assumptions*, which is exactly what must be proven.


LIVE_BASE_PRICE = 300.0
LIVE_BASE_EPS = 7.50


def _live_analysis_result(payload: dict) -> dict:
    """An AnalysisResultDTO whose matrix is derived from the submitted assumptions."""
    horizon = (payload.get("reverse_horizons") or [3.0])[0]
    required_return = (payload.get("required_returns") or [0.10])[0]
    exit_pe = payload.get("reference_multiple") or 20.0
    exit_price = LIVE_BASE_PRICE * (1.0 + required_return) ** horizon
    terminal_eps = exit_price / exit_pe
    total_growth = (terminal_eps - LIVE_BASE_EPS) / LIVE_BASE_EPS
    cagr = (terminal_eps / LIVE_BASE_EPS) ** (1.0 / horizon) - 1.0

    return {
        "ticker": payload["ticker"],
        "company_name": "AAPL (Live Acquired)",
        "status": "success",
        "as_of": "2026-10-09",
        "source_identifiers": [
            "YahooFinance+YahooFinanceFundamentals",
            "Yahoo Finance chart API",
            "API_LIVE",
        ],
        "admission_summary": {
            "total_admitted": 1,
            "total_refused": 0,
            "metrics_admitted": ["revenue"],
            "refusals": [],
        },
        "valuation_summary": {
            "current_price": LIVE_BASE_PRICE,
            "currency": "USD",
            "as_of": "2026-10-09",
            "observed_pe": LIVE_BASE_PRICE / LIVE_BASE_EPS,
            "limitations": [],
        },
        "replay_summary": {"attempted": False},
        "refusal_reasons": [],
        "reverse_requirements": {
            "formula_version": "reverse-requirements/1.1",
            "fingerprint": "f" * 64,
            "status": "COMPUTED",
            "status_reason": None,
            "matrix_size": 1,
            "as_of": "2026-10-09",
            "market_price": {
                "value": LIVE_BASE_PRICE,
                "currency": "USD",
                "source": "Yahoo Finance chart API",
            },
            "start_anchor": {
                "value": LIVE_BASE_EPS,
                "basis": "TRAILING_TWELVE_MONTHS",
                "months_covered": 12.0,
                "provider": "YahooFinance+YahooFinanceFundamentals",
                "source_type": "API_LIVE",
                "is_user_assumption": False,
            },
            "unavailable": [],
            "reading_notes": [],
            "reverse_requirements_matrix": [
                {
                    "horizon_years": horizon,
                    "required_return": required_return,
                    "required_return_basis": "PRICE_RETURN_ONLY",
                    "price": LIVE_BASE_PRICE,
                    "as_of": "2026-10-09",
                    "start_eps": {
                        "value": LIVE_BASE_EPS,
                        "basis": "TRAILING_TWELVE_MONTHS",
                        "months_covered": 12.0,
                        "provider": "YahooFinance+YahooFinanceFundamentals",
                        "currency": "USD",
                        "period_undeclared_by_source": True,
                        "source_type": "API_LIVE",
                        "observation_id": "ev-current-eps-001",
                        "is_user_assumption": False,
                        "sec_fact": None,
                    },
                    "exit_multiple": {
                        "value": exit_pe,
                        "source": "user_supplied",
                        "is_user_assumption": True,
                        "eligibility_state": "USER_SPECIFIED",
                        "usable_for_reference": True,
                    },
                    "required_exit_price": exit_price,
                    "required_terminal_eps": terminal_eps,
                    "total_terminal_eps_growth": total_growth,
                    "required_eps_cagr": cagr,
                    "growth_years": horizon,
                    "flags": ["REQUIRED_RETURN_EXCLUDES_DIVIDENDS"],
                    "formula_version": "reverse-requirements/1.1",
                    "calculation_steps": [
                        {
                            "step_number": 1,
                            "step_id": "required_exit_price",
                            "name": "Required Exit Price",
                            "formula_expression": "P_T = P_0 * (1 + r)^T",
                            "operands": {
                                "price": LIVE_BASE_PRICE,
                                "required_return": required_return,
                                "horizon_years": horizon,
                            },
                            "output_value": exit_price,
                            "output_unit": "USD",
                            "reproducible": True,
                            "status": "COMPUTED",
                        },
                        {
                            "step_number": 2,
                            "step_id": "required_terminal_eps",
                            "name": "Required Terminal EPS",
                            "formula_expression": "EPS_T = P_T / Exit_PE",
                            "operands": {
                                "required_exit_price": exit_price,
                                "exit_multiple": exit_pe,
                            },
                            "output_value": terminal_eps,
                            "output_unit": "USD/share",
                            "reproducible": True,
                            "status": "COMPUTED",
                        },
                    ],
                    "evidence": {
                        "price_evidence": {
                            "value": LIVE_BASE_PRICE,
                            "currency": "USD",
                            "provider": "YahooFinance+YahooFinanceFundamentals",
                            "source_type": "API_LIVE",
                            "observation_id": "ev-price-001",
                            "is_user_assumption": False,
                        },
                        "eps_evidence": {
                            "value": LIVE_BASE_EPS,
                            "basis": "TRAILING_TWELVE_MONTHS",
                            "months_covered": 12.0,
                            "provider": "YahooFinance+YahooFinanceFundamentals",
                            "currency": "USD",
                            "period_undeclared_by_source": True,
                            "source_type": "API_LIVE",
                            "observation_id": "ev-current-eps-001",
                            "is_user_assumption": False,
                            "sec_fact": None,
                        },
                        "multiple_evidence": {
                            "value": exit_pe,
                            "source": "user_supplied",
                            "is_user_assumption": True,
                            "eligibility_state": "USER_SPECIFIED",
                            "usable_for_reference": True,
                        },
                        "user_assumptions": [
                            f"Holding Horizon: {horizon} years",
                            f"Required Return Hurdle: {required_return:.2%} (PRICE_RETURN_ONLY)",
                            f"Exit Multiple: {exit_pe}x (user-supplied)",
                        ],
                        "sourced_facts": [
                            f"Market Price: {LIVE_BASE_PRICE} USD "
                            "(as-of 2026-10-09, provider: YahooFinance+YahooFinanceFundamentals)",
                            f"Starting EPS: {LIVE_BASE_EPS} USD "
                            "(TRAILING_TWELVE_MONTHS, provider: YahooFinance+YahooFinanceFundamentals)",
                        ],
                        "missing_or_unvalidated": [
                            "Starting EPS period coverage was not declared by source",
                            "Direct SEC source of selected EPS not established; related filing shown for cross-check only",
                        ],
                        "related_sec_evidence": {
                            "accession": "0000320193-25-000079",
                            "form": "10-K",
                            "filed_date": "2025-10-31",
                            "concept": "us-gaap:EarningsPerShareDiluted",
                            "unit": "USD/shares",
                            "document_url": None,
                            "note": (
                                "Related SEC filing (cross-check); not verified as "
                                "direct source of selected EPS value"
                            ),
                        },
                    },
                }
            ],
        },
    }


class TestLiveModeSelectionBrowser(unittest.TestCase):
    """The browser sends live mode and the selected assumptions, and renders that result."""

    @classmethod
    def setUpClass(cls):
        cls._archive_tmp = tempfile.TemporaryDirectory(prefix="steva-live-mode-")
        cls.archive_dir = cls._archive_tmp.name
        cls.port = find_free_port()
        cls.base_url = f"http://127.0.0.1:{cls.port}"
        app = create_app(archives_dir=cls.archive_dir)
        config = uvicorn.Config(app, host="127.0.0.1", port=cls.port, log_level="warning")
        cls.server = uvicorn.Server(config)
        cls.server_thread = threading.Thread(target=cls.server.run, daemon=True)
        cls.server_thread.start()
        for _ in range(50):
            try:
                with socket.create_connection(("127.0.0.1", cls.port), timeout=0.1):
                    break
            except (ConnectionRefusedError, OSError):
                time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.server.should_exit = True
        cls.server_thread.join(timeout=2.0)
        cls._archive_tmp.cleanup()

    def test_live_mode_assumption_round_trip(self):
        submitted = []

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(locale="en-US", viewport={"width": 1400, "height": 1100})
            # The PWA service worker is registered separately
            # (`test_pwa_metadata_and_service_worker`); here it must stay out of
            # the way because it relays `/api` requests itself, which would hide
            # the outgoing request from the route interception this test asserts.
            context.add_init_script(
                "Object.defineProperty(navigator, 'serviceWorker', { configurable: true, "
                "get() { return { register: () => Promise.reject(new Error('disabled in test')), "
                "addEventListener() {}, removeEventListener() {} }; } });"
            )
            page = context.new_page()

            def handle_analyze(route):
                payload = json.loads(route.request.post_data or "{}")
                submitted.append(payload)
                route.fulfill(
                    status=202,
                    json={
                        "job_id": f"job-r3-{len(submitted)}",
                        "ticker": payload["ticker"],
                        "status": "PENDING",
                    },
                )

            def handle_job(route):
                job_id = route.request.url.rsplit("/", 1)[-1]
                index = int(job_id.rsplit("-", 1)[-1]) - 1
                payload = submitted[index]
                route.fulfill(
                    status=200,
                    json={
                        "job_id": job_id,
                        "ticker": payload["ticker"],
                        "status": "COMPLETED",
                        "stage": "completed",
                        "created_at": "2026-10-11T00:00:00Z",
                        "updated_at": "2026-10-11T00:00:00Z",
                        "error": None,
                        "result": _live_analysis_result(payload),
                    },
                )

            page.route("**/api/analyze", handle_analyze)
            page.route("**/api/jobs/*", handle_job)

            page.goto(self.base_url)
            page.wait_for_selector("text=Reverse-engineer market expectations")

            # The settings drawer is expanded by default, so the mode and
            # assumptions are already reachable; select the mode explicitly and
            # set an initial assumption set, then submit.
            page.select_option("select >> nth=0", "live")
            page.locator("input[placeholder='e.g. 20.0']").fill("20")
            page.locator("input[placeholder*='e.g. 1.0, 2.0, 3.0, 5.0']").fill("3")
            page.locator("input[placeholder*='e.g. 8, 10, 12, 15']").fill("10")

            page.locator("input[placeholder*='Enter ticker']").fill("AAPL")
            page.locator("button[type='submit']").click()
            page.get_by_test_id("results-heading").wait_for(state="visible", timeout=30000)

            self.assertEqual(
                submitted[0],
                {
                    "ticker": "AAPL",
                    "mode": "live",
                    "reference_multiple": 20.0,
                    "reverse_horizons": [3.0],
                    "required_returns": [0.10],
                },
            )

            # Live identities, not a fixture: no regression banner, and the
            # always-visible badge names the live data source.
            self.assertEqual(page.locator("text=REGRESSION FIXTURE (TEST DATA)").count(), 0)
            self.assertGreater(
                page.locator("text=Data source: live (Yahoo / SEC)").count(), 0
            )

            # The displayed matrix matches the request's assumptions.
            page.wait_for_selector("text=Reverse Requirements Matrix")
            matrix_text = page.locator("body").inner_text()
            self.assertIn("3.0y", matrix_text)
            self.assertIn("10.0%", matrix_text)
            self.assertIn("20.0x", matrix_text)
            expected_exit_price = LIVE_BASE_PRICE * (1.10 ** 3)
            expected_terminal_eps = expected_exit_price / 20.0
            self.assertIn(f"{expected_exit_price:,.2f}", matrix_text)
            self.assertIn(f"{expected_terminal_eps:,.2f}", matrix_text)

            # The audit drawer renders live provenance without claiming an SEC source.
            page.locator("button[title='Toggle details']").first.click()
            drawer_text = page.locator("body").inner_text()
            self.assertIn("Provider: YahooFinance+YahooFinanceFundamentals", drawer_text)
            self.assertIn("Provider-Sourced (SEC Link Not Established)", drawer_text)
            self.assertIn("Direct SEC source: not established", drawer_text)
            self.assertIn("Related SEC 10-K (cross-check)", drawer_text)
            self.assertNotIn("Source: SEC 10-K", drawer_text)

            # Change an assumption and resubmit: the request must carry it and the
            # drawer must render the new result, not the previous one.
            page.locator("input[placeholder='e.g. 20.0']").fill("32")
            page.locator("input[placeholder*='e.g. 8, 10, 12, 15']").fill("12")
            page.locator("button[type='submit']").click()
            page.wait_for_timeout(2000)

            self.assertEqual(len(submitted), 2)
            self.assertEqual(
                submitted[1],
                {
                    "ticker": "AAPL",
                    "mode": "live",
                    "reference_multiple": 32.0,
                    "reverse_horizons": [3.0],
                    "required_returns": [0.12],
                },
            )
            self.assertGreater(page.get_by_test_id("results-heading").count(), 0)

            new_matrix_text = page.locator("body").inner_text()
            self.assertIn("12.0%", new_matrix_text)
            self.assertIn("32.0x", new_matrix_text)
            self.assertNotIn("20.0x", new_matrix_text)
            new_exit_price = LIVE_BASE_PRICE * (1.12 ** 3)
            new_terminal_eps = new_exit_price / 32.0
            self.assertIn(f"{new_exit_price:,.2f}", new_matrix_text)
            self.assertIn(f"{new_terminal_eps:,.2f}", new_matrix_text)
            self.assertNotIn(f"{expected_exit_price:,.2f}", new_matrix_text)
            self.assertNotIn(f"{expected_terminal_eps:,.2f}", new_matrix_text)

            context.close()
            browser.close()
