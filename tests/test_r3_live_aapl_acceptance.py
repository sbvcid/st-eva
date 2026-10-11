"""Real AAPL live acceptance browser path.

This is the *real-data* acceptance harness behind the R3 acceptance record in
`docs/PROJECT-STATUS.md`. It drives the built frontend in headless Chromium
against the FastAPI app with an isolated temporary archive directory, submits
AAPL with an explicit non-regression mode and a real assumption set, and checks
the returned contract:

* the outgoing request carries the selected mode and assumptions,
* the response reports live acquisition identities (not a regression fixture),
* every computable row recomputes exactly from its own displayed operands,
* direct SEC EPS attribution appears only with a proven input-to-fact linkage
  and is otherwise stated as not established,
* related filing evidence is labelled cross-check only,
* user assumptions stay separated from sourced facts,
* a changed assumption produces a changed matrix, and the audit drawer shows
  that submission's result rather than the previous one,
* no persistent database is touched: the archive lives in a temporary directory.

It is never run implicitly: set ``ST_EVA_R3_LIVE=1`` to execute it against
whatever the live providers return today. No market value is asserted, so the
test stays valid as prices change; a blocked or failing acquisition surfaces as
a failed assertion rather than a silent pass.
"""

import json
import os
import socket
import tempfile
import threading
import time
import unittest

import uvicorn
from playwright.sync_api import sync_playwright

from web.app import create_app

TOLERANCE = 1e-6


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _close(a: float, b: float, tol: float = TOLERANCE) -> bool:
    scale = max(1.0, abs(a), abs(b))
    return abs(a - b) <= tol * scale


@unittest.skipUnless(
    os.environ.get("ST_EVA_R3_LIVE") == "1",
    "real-data acceptance run; enable with ST_EVA_R3_LIVE=1",
)
class TestRealLiveAaplAcceptanceBrowser(unittest.TestCase):
    """Runnable real-data acceptance: enable with ST_EVA_R3_LIVE=1."""

    @classmethod
    def setUpClass(cls):
        cls._archive_tmp = tempfile.TemporaryDirectory(prefix="r3-live-acceptance-")
        cls.archive_dir = cls._archive_tmp.name
        cls.port = _free_port()
        cls.base_url = f"http://127.0.0.1:{cls.port}"
        app = create_app(archives_dir=cls.archive_dir)
        cls.manager = app.state.job_manager
        config = uvicorn.Config(app, host="127.0.0.1", port=cls.port, log_level="warning")
        cls.server = uvicorn.Server(config)
        cls.server_thread = threading.Thread(target=cls.server.run, daemon=True)
        cls.server_thread.start()
        for _ in range(100):
            try:
                with socket.create_connection(("127.0.0.1", cls.port), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.1)
        # The PWA service worker relays `/api` calls itself; disable it so the
        # request bodies this test records are the ones the page actually sent.
        cls._sw_stub = (
            "Object.defineProperty(navigator, 'serviceWorker', { configurable: true, "
            "get() { return { register: () => Promise.reject(new Error('disabled in test')), "
            "addEventListener() {}, removeEventListener() {} }; } });"
        )

    @classmethod
    def tearDownClass(cls):
        cls.server.should_exit = True
        cls.server_thread.join(timeout=3.0)
        cls._archive_tmp.cleanup()

    def _completed_job(self, timeout: float = 480.0) -> dict:
        """The next job run by the app, read from the same registry the browser polls."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            for record in list(self.manager.jobs.values()):
                if record.job_id in self._seen:
                    continue
                status = getattr(record.status, "value", str(record.status))
                if status in ("COMPLETED", "FAILED"):
                    self._seen.add(record.job_id)
                    payload = {
                        "job_id": record.job_id,
                        "status": status,
                        "error": record.error,
                    }
                    if record.result is not None:
                        payload["result"] = record.result.model_dump()
                    return payload
            time.sleep(2)
        raise AssertionError("no submitted job reached a terminal state in time")

    def _submit(self, page, reference_multiple: str, returns: str) -> None:
        page.locator("input[placeholder*='Enter ticker']").fill("AAPL")
        page.locator("button:has-text('Scenario Assumptions')").click()
        # Explicit non-regression acquisition mode.
        page.select_option("select >> nth=0", "live")
        page.locator("input[placeholder='e.g. 20.0']").fill(reference_multiple)
        page.locator("input[placeholder*='e.g. 1.0, 2.0, 3.0, 5.0']").fill("3")
        page.locator("input[placeholder*='e.g. 8, 10, 12, 15']").fill(returns)
        page.locator("button[type='submit']").click()

    def test_real_aapl_live_acceptance(self):
        submitted = []
        self._seen = set()

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                locale="en-US", viewport={"width": 1400, "height": 1100}
            )
            context.add_init_script(self._sw_stub)
            page = context.new_page()

            def on_request(request):
                if "/api/analyze" in request.url and request.method == "POST":
                    submitted.append(json.loads(request.post_data or "{}"))

            page.on("request", on_request)
            page.goto(self.base_url)
            page.wait_for_selector("text=Reverse-engineer market expectations", timeout=60000)

            # Submission 1: AAPL, live mode, 3y / 10% / 30x.
            self._submit(page, "30", "10")
            deadline = time.time() + 180
            while time.time() < deadline and not submitted:
                time.sleep(1)
            self.assertTrue(submitted, "no analysis request reached the API")
            self.assertEqual(
                submitted[-1],
                {
                    "ticker": "AAPL",
                    "mode": "live",
                    "reference_multiple": 30.0,
                    "reverse_horizons": [3.0],
                    "required_returns": [0.10],
                },
            )

            page.wait_for_selector("text=Analysis Verdict", timeout=480000)
            detail = self._completed_job()
            self.assertEqual(detail["status"], "COMPLETED")
            result = detail.get("result") or {}
            self.assertEqual(result.get("ticker"), "AAPL")

            acceptance_record = {
                "submitted": list(submitted),
                "first_result": result,
            }

            body_text = page.locator("body").inner_text()
            self.assertNotIn("REGRESSION FIXTURE (TEST DATA)", body_text)
            self.assertNotIn("RegressionFixture", body_text)

            identifiers = result.get("source_identifiers") or []
            self.assertTrue(identifiers, "the response must name its sources")
            for identifier in identifiers:
                self.assertNotIn("fixture", identifier.lower())
                self.assertNotIn("regression", identifier.lower())
            self.assertTrue(
                any("Yahoo" in identifier for identifier in identifiers),
                f"a live market provider is expected, got {identifiers}",
            )

            valuation = result.get("valuation_summary") or {}
            self.assertIsNotNone(valuation.get("current_price"))
            self.assertGreater(valuation["current_price"], 0)
            self.assertEqual(valuation.get("currency"), "USD")
            self.assertTrue(valuation.get("as_of"))

            rr = result.get("reverse_requirements")
            self.assertIsNotNone(rr, "the response carries no reverse requirements report")
            self.assertEqual(rr.get("formula_version"), "reverse-requirements/1.1")
            self.assertIn(rr.get("status"), ("COMPUTED", "NOT_COMPUTED"))
            rows = rr.get("reverse_requirements_matrix") or []
            self.assertEqual(len(rows), rr.get("matrix_size"))

            if rr.get("status") == "COMPUTED":
                # One row per requested assumption, and nothing invented.
                self.assertEqual(len(rows), 1)
                row = rows[0]
                self.assertAlmostEqual(row["horizon_years"], 3.0, places=9)
                self.assertAlmostEqual(row["required_return"], 0.10, places=9)
                self.assertAlmostEqual(row["exit_multiple"]["value"], 30.0, places=9)
                self.assertEqual(row["exit_multiple"]["source"], "user_supplied")
                self.assertTrue(row["exit_multiple"]["is_user_assumption"])

                # Independent recomputation from the row's own operands.
                price = row["price"]
                required_return = row["required_return"]
                horizon = row["horizon_years"]
                exit_pe = row["exit_multiple"]["value"]
                start_eps = row["start_eps"]["value"]
                expected_exit_price = price * (1.0 + required_return) ** horizon
                expected_terminal_eps = expected_exit_price / exit_pe
                expected_growth = (expected_terminal_eps - start_eps) / start_eps
                expected_cagr = (expected_terminal_eps / start_eps) ** (1.0 / horizon) - 1.0
                self.assertTrue(_close(expected_exit_price, row["required_exit_price"]))
                self.assertTrue(_close(expected_terminal_eps, row["required_terminal_eps"]))
                self.assertTrue(_close(expected_growth, row["total_terminal_eps_growth"]))
                self.assertTrue(_close(expected_cagr, row["required_eps_cagr"]))

                steps = {s["step_id"]: s for s in row["calculation_steps"]}
                self.assertEqual(len(steps), 4)
                for step in steps.values():
                    self.assertTrue(step["reproducible"])
                self.assertTrue(
                    _close(steps["required_exit_price"]["output_value"], expected_exit_price)
                )
                self.assertTrue(
                    _close(steps["required_terminal_eps"]["output_value"], expected_terminal_eps)
                )
                self.assertEqual(steps["required_exit_price"]["operands"]["price"], price)

                # R2.1 provenance rules on the live path.
                evidence = row["evidence"]
                self.assertEqual(evidence["eps_evidence"]["source_type"], "API_LIVE")
                self.assertIn("Yahoo", evidence["eps_evidence"]["provider"])
                self.assertIsNone(
                    evidence["eps_evidence"]["sec_fact"],
                    "a vendor EPS must not carry an SEC filing as its direct source",
                )
                missing = evidence["missing_or_unvalidated"]
                self.assertTrue(
                    any("Direct SEC source of selected EPS not established" in item for item in missing),
                    missing,
                )
                related = evidence.get("related_sec_evidence")
                if related and related.get("accession"):
                    self.assertIn("cross-check", related.get("note", ""))
                self.assertTrue(
                    any(item.startswith("Starting EPS:") for item in evidence["sourced_facts"]),
                    evidence["sourced_facts"],
                )
                self.assertTrue(
                    any("user-supplied" in item for item in evidence["user_assumptions"]),
                    evidence["user_assumptions"],
                )

                # The drawer renders this request's evidence.
                page.locator("button[title='Toggle details']").first.click()
                drawer_text = page.locator("body").inner_text()
                self.assertIn("Provider-Sourced (SEC Link Not Established)", drawer_text)
                self.assertIn("Direct SEC source: not established", drawer_text)
                self.assertNotIn("Source: SEC 10-K", drawer_text)

            # A band that cannot qualify must say so instead of being used as a
            # reference exit multiple.
            for item in rr.get("unavailable") or []:
                if isinstance(item, dict) and item.get("item") == "exit_multiple.band_scenarios":
                    self.assertEqual(item.get("reason_kind"), "INSUFFICIENT_OBSERVATIONS")
                    self.assertIn("observations", item.get("reason", ""))

            # Submission 2: changed assumptions.
            page.locator("input[placeholder='e.g. 20.0']").fill("32")
            page.locator("input[placeholder*='e.g. 8, 10, 12, 15']").fill("12")
            page.locator("button[type='submit']").click()
            deadline = time.time() + 180
            while time.time() < deadline and len(submitted) < 2:
                time.sleep(1)
            self.assertEqual(len(submitted), 2, "the second submission never reached the API")
            self.assertEqual(
                submitted[-1],
                {
                    "ticker": "AAPL",
                    "mode": "live",
                    "reference_multiple": 32.0,
                    "reverse_horizons": [3.0],
                    "required_returns": [0.12],
                },
            )

            second = self._completed_job()
            self.assertEqual(second["status"], "COMPLETED")
            second_rr = second.get("result", {}).get("reverse_requirements") or {}
            page.wait_for_selector("text=Analysis Verdict", timeout=480000)
            if second_rr.get("status") == "COMPUTED":
                second_rows = second_rr.get("reverse_requirements_matrix") or []
                self.assertTrue(second_rows)
                self.assertAlmostEqual(second_rows[0]["exit_multiple"]["value"], 32.0, places=9)
                self.assertAlmostEqual(second_rows[0]["required_return"], 0.12, places=9)
                second_text = page.locator("body").inner_text()
                self.assertIn("32.0x", second_text)
                self.assertNotIn("30.0x", second_text)

            acceptance_record["submitted"] = list(submitted)
            acceptance_record["second_result"] = second.get("result")
            context.close()
            browser.close()

        # Optional machine-readable acceptance record.
        record_path = os.environ.get("ST_EVA_R3_EVIDENCE")
        if record_path:
            with open(record_path, "w", encoding="utf-8") as handle:
                json.dump(acceptance_record, handle, ensure_ascii=False, indent=1)

        # Isolation: the run wrote into the temporary archive only, and the
        # operator's archives directory was never a write target.
        archived = [name for name in os.listdir(self.archive_dir) if name.endswith(".sqlite")]
        self.assertTrue(archived, "the isolated archive should hold the AAPL run")
        self.assertTrue(self.archive_dir.startswith(tempfile.gettempdir()))
        self.assertNotIn(os.path.abspath(self.archive_dir), os.path.abspath("data/archives"))


if __name__ == "__main__":
    unittest.main()
