"""
What a hosted provider's request allowance is doing, and when to stop.

A free endpoint can refuse a request for reasons that have nothing to do with
the model: a daily quota, a per-minute limit, a shared upstream pool, a provider
that is down, a model that has been withdrawn. The 2.6.2 round hit four of those
and the only reason none of them was mistaken for a model failure is that a
human read the log. A harness that leaves that to a reader will eventually get it
wrong, and the failure mode is quiet: a refusal becomes a `FAIL` on a test the
model never saw, and a run of mostly-passing tests quietly loses its tail.

So the allowance is a first-class object here. It counts every attempt, it
records which kind of refusal came back, it knows what is left, and it says
*stop* rather than letting a loop decide on its own. What it never does is
switch provider, substitute a model, or re-run a dataset to get a better
number — those change the experiment, and only a person may do that.

The unit is the request, not the test. One test is several requests, so a budget
expressed in tests is a budget nobody can reason about.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

# The kinds a refusal can be, and what each one means for whether to try again.
#
# `retry` is not "yes". It is "the same request may succeed later without anyone
# changing the experiment", which is a narrower thing and the reason the two
# are listed separately.
SIGNALS: Dict[str, Dict[str, Any]] = {
    "rate_limited": {
        "retry": True,
        "retry_after_seconds": 60,
        "is_model_finding": False,
        "note": "quota or a shared upstream pool; the same request may succeed",
    },
    "provider_error": {
        "retry": True,
        "retry_after_seconds": 30,
        "is_model_finding": False,
        "note": "the provider behind the model failed; not about the model",
    },
    "model_unavailable": {
        "retry": False,
        "retry_after_seconds": 0,
        "is_model_finding": False,
        "note": "the model or its endpoint is gone; retrying cannot help",
    },
    "request_rejected": {
        "retry": False,
        "retry_after_seconds": 0,
        "is_model_finding": False,
        "note": (
            "the endpoint refused the request the harness sent; sending it "
            "again gets the same refusal, so this is a harness fault to look at "
            "rather than a provider condition to wait out"
        ),
    },
    "malformed_response": {
        "retry": True,
        "retry_after_seconds": 15,
        "is_model_finding": False,
        "note": "a success status carrying an error; the answer never existed",
    },
    "network": {
        "retry": True,
        "retry_after_seconds": 10,
        "is_model_finding": False,
        "note": "no answer at all",
    },
}

# How many consecutive refusals of the same kind end the phase. Not a retry
# budget — a refusal run is a strong signal that the endpoint, not the request,
# is the problem, and continuing past it is how an allowance disappears.
DEFAULT_REFUSAL_RUN = 3


class RequestBudget:
    """
    One phase's request allowance, counted and reported.

    `limit` is the ceiling this run is willing to spend, set by whoever started
    it from what the provider documents. It is a ceiling and not a prediction:
    a provider may allow more or less, and the ledger records what actually
    happened either way, so the documented figure and the observed one can be
    compared instead of assumed to be the same.
    """

    def __init__(
        self,
        limit: Optional[int],
        label: str = "",
        refusal_run: int = DEFAULT_REFUSAL_RUN,
    ) -> None:
        self.limit = limit
        self.label = label
        self.refusal_run = refusal_run
        self.started_at = time.time()
        # The ledger of what happened to each request, and the count of requests
        # that left the process. Two fields on purpose: an entry is appended for
        # the send *and* for its outcome, so `len(attempts)` counts events and
        # would let a single refused request look like two requests spent. The
        # budget is denominated in requests, and the thing being limited is
        # requests.
        self.attempts: List[Dict[str, Any]] = []
        self.sent = 0
        self.signals: Dict[str, int] = {}
        self._consecutive_refusals: Dict[str, int] = {}
        self.stopped_because: Optional[str] = None

    # -- accounting ------------------------------------------------------

    @property
    def spent(self) -> int:
        return self.sent

    @property
    def remaining(self) -> Optional[int]:
        """What is left against the ceiling, or None when no ceiling was set."""
        return None if self.limit is None else max(0, self.limit - self.spent)

    def can_start(self, test_id: str = "") -> bool:
        if self.stopped_because:
            return False
        if self.remaining is not None and self.remaining <= 0:
            self.stop(
                f"request budget of {self.limit} reached before {test_id or 'the run'}"
            )
            return False
        return True

    def stop(self, reason: str) -> None:
        if self.stopped_because is None:
            self.stopped_because = reason

    # -- recording -------------------------------------------------------

    def record_sent(self, test_id: str = "") -> None:
        """A request left the process. Counted before the answer is known.

        Counting on the way out rather than on the way back is the whole point:
        a refused request can still spend the allowance, and an allowance that
        only counts successes is exactly the one that runs out unexpectedly.
        """
        self.attempts.append(
            {
                "test_id": test_id,
                "outcome": "sent",
                "at": round(time.time() - self.started_at, 1),
            }
        )
        self.sent += 1
        # Deliberately *not* cleared here. Every send is an attempt to get an
        # answer, so a refusal is the answer to the send in front of it; clearing
        # the counter on the way out would make the refusal run unraisable in
        # exactly the shape it exists for, where the harness retries and is
        # refused again. Only a completion clears it.

    def record_answer(self, test_id: str = "", usage: Any = None) -> None:
        self.attempts.append(
            {
                "test_id": test_id,
                "outcome": "answered",
                "usage": usage,
                "at": round(time.time() - self.started_at, 1),
            }
        )
        self._consecutive_refusals.clear()

    def record_refusal(self, kind: str, test_id: str = "", detail: str = "") -> None:
        """
        A request came back refused.

        Classified rather than counted, because the kind decides what happens
        next and it must not be a decision made at the call site. A run of
        `model_unavailable` refusals ends the phase immediately; a run of
        `rate_limited` refusals ends it too, because a saturated pool served by
        retrying harder is the documented way to lose the rest of the day's
        allowance.
        """
        signal = SIGNALS.get(kind, SIGNALS["network"])
        self.attempts.append(
            {
                "test_id": test_id,
                "outcome": f"refused:{kind}",
                "is_model_finding": signal["is_model_finding"],
                "detail": detail[:400],
                "at": round(time.time() - self.started_at, 1),
            }
        )
        self.signals[kind] = self.signals.get(kind, 0) + 1
        self._consecutive_refusals[kind] = self._consecutive_refusals.get(kind, 0) + 1
        if not signal["retry"]:
            self.stop(
                f"{kind}: {signal['note']}"
                + (f" ({model_of(detail)})" if model_of(detail) else "")
            )
        elif self._consecutive_refusals[kind] >= self.refusal_run:
            self.stop(
                f"{self._consecutive_refusals[kind]} {kind} refusals with no "
                f"answer in between"
            )

    def should_retry(self, kind: str) -> bool:
        return bool(SIGNALS.get(kind, SIGNALS["network"])["retry"])

    def retry_after(self, kind: str) -> int:
        return int(SIGNALS.get(kind, SIGNALS["network"])["retry_after_seconds"])

    # -- reporting -------------------------------------------------------

    def summary(self) -> Dict[str, Any]:
        """
        The whole allowance story, in one object, next to the run it governed.

        A reader who wants to know whether a run's results are a model property
        or a provider property should not have to reconstruct it from logs. So
        this records the ceiling that was assumed, the requests that were
        actually sent, the refusals by kind, and the reason the run stopped if
        it did — with `model_finding_refusals` always zero, because a refusal is
        never a finding about the model and the field exists to make that check
        rather than to carry information.
        """
        return {
            "label": self.label,
            "declared_limit": self.limit,
            "requests_sent": self.spent,
            "remaining_budget": self.remaining,
            "elapsed_seconds": round(time.time() - self.started_at, 1),
            "refusals_by_kind": dict(self.signals),
            "model_finding_refusals": sum(
                1 for attempt in self.attempts
                if attempt.get("is_model_finding")
            ),
            "stopped_because": self.stopped_because,
            "rate_limit_headers": {},
            "attempts": self.attempts,
        }

    def write(self, path: str, rate_limit_headers: Optional[Dict[str, str]] = None):
        payload = self.summary()
        if rate_limit_headers:
            payload["rate_limit_headers"] = {
                key: value
                for key, value in rate_limit_headers.items()
                if "rate" in key or "retry" in key or "reset" in key
            }
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, default=str)
        return payload


def model_of(detail: str) -> Optional[str]:
    """Pull the model id out of a refusal message, for a stop message only."""
    marker = "/models/"
    if marker in detail:
        tail = detail.split(marker, 1)[1]
        return tail.split()[0].strip("'\"") if tail else None
    return None
