from __future__ import annotations

"""
ST-EVA optional LLM interpretation adapter.

The adapter never performs valuation arithmetic. It converts an already
validated ST-EVA JSON snapshot into a strict interpretation prompt. A caller
may send that prompt to Gemini, GPT, or another model through its own client.

The model is explicitly forbidden from inventing financial inputs, changing
computed values, or issuing a buy/sell recommendation.
"""

import json
from typing import Any, Dict


SYSTEM_PROMPT = """You are the interpretation layer for ST-EVA.
Interpret only the supplied machine-readable valuation analysis.

Rules:
1. Do not calculate or modify financial numbers. Quote supplied values only.
2. Do not invent missing EPS, FCF, EBITDA, revenue, multiples, dates, or
   consensus estimates.
3. Treat every implied fundamental as conditional on its stated valuation
   multiple.
4. Distinguish OBSERVED data, DERIVED calculations, and CONDITIONAL inference.
5. Do not issue a buy/sell recommendation, target price, probability, ranking,
   or investment verdict.
6. Explain what the current price requires under each available valuation
   reference and where the references disagree.
7. Explicitly mention unavailable data and low observation counts.
8. Keep the answer concise and evidence-oriented.
"""


def build_interpretation_prompt(analysis: Dict[str, Any]) -> str:
    payload = json.dumps(analysis, ensure_ascii=False, indent=2)
    return (
        SYSTEM_PROMPT
        + "\n\nST-EVA analysis JSON follows. Do not add external facts.\n\n"
        + payload
        + "\n\nReturn a factual interpretation of the supplied analysis."
    )


def build_interpretation_request(analysis: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "system": SYSTEM_PROMPT,
        "input": analysis,
        "instruction": (
            "Interpret the supplied ST-EVA result without changing any "
            "numbers or introducing unsourced financial assumptions."
        ),
    }
