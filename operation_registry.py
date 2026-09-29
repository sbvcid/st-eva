from __future__ import annotations

"""
ST-EVA 2.3-C - Operation Registry.

A closed, versioned vocabulary of arithmetic primitives. Every derived figure in
an Investment Context names an operation from this registry, and a consumer
re-checks that figure by resolving the operands and dispatching `op` and
`version` here.

Why a registry rather than a function name
------------------------------------------

If an `operation` field were `"st_eva.compute_pe"`, then a consumer in another
language could not evaluate it, renaming a function would silently change the
meaning of already-written documents, and a "deterministic recomputation" claim
would be unfalsifiable because the thing being checked would be the thing being
verified. All three failures are impossible here:

    - the vocabulary is closed, so evaluation is a dispatch, not an import;
    - semantics are versioned per operation, so a change is `v2` and a `v1`
      document still evaluates correctly;
    - the arity, the accepted units, the unit result, the parameters, and the
      missing-value rule are declared, so an evaluator can reject a malformed
      operation before it computes anything.

Two rules are uniform across the whole registry, and both matter more than any
individual formula:

    Missing inputs PROPAGATE. An operation with an unavailable operand yields
    an unavailable result. Never zero, never a median, never a carry-forward.
    That is the 2.2.3 `else None` discipline promoted to a declared rule.

    Units are checked, not assumed. An operand pair outside the unit table is a
    UnitRuleError, so a malformed document fails loudly instead of producing a
    plausible wrong number.
"""

import math
from dataclasses import dataclass, field, replace
from inspect import signature
from statistics import median as _sample_median
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from data_contract import Unit, safe_float

REGISTRY_VERSION = "1"

# The unit types a figure may carry. Deliberately small and conventional: these
# are market conventions, not physical dimensions, so the arithmetic below is a
# declared lookup rather than dimensional analysis.
NUMERIC = "number"
LIST = "list"

MISSING_VALUE_RULE_PROPAGATE = "PROPAGATE"

BAND_KEYS = ("10th", "25th", "median", "75th", "90th")


class RegistryError(Exception):
    """Base class for every registry failure. All of them are hard errors."""


class UnknownOperationError(RegistryError):
    """The operation is not in the registry."""


class UnsupportedVersionError(RegistryError):
    """The operation exists, but not at the version the document declares."""


class ArityError(RegistryError):
    """The operation was given the wrong number of operands."""


class UnitRuleError(RegistryError):
    """The operand units do not satisfy the operation's unit rule."""


class MissingOperandError(RegistryError):
    """An operand is unavailable, so the result must be unavailable too."""


class ParameterError(RegistryError):
    """A required parameter is absent, or a parameter is out of range."""


class CurrencyMismatchError(UnitRuleError):
    """
    Two operands are denominated in different currencies.

    Subclasses UnitRuleError because it is one: the unit and the currency are
    two axes of the same question, and a mismatch on either axis means the
    result would be a number with no economic meaning.

    This is the guard that stops a US dollar market capitalisation being divided
    by a New Taiwan dollar revenue. Both operands have unit `currency`, so the
    unit table alone is satisfied and would happily produce a plausible-looking
    ratio several orders of magnitude away from any real multiple.
    """


@dataclass(frozen=True)
class ParameterSpec:
    name: str
    type: str
    required: bool = True
    default: Any = None
    minimum: Optional[float] = None
    maximum: Optional[float] = None

    def resolve(self, supplied: Dict[str, Any]) -> Any:
        if self.name in supplied:
            value = supplied[self.name]
        elif self.default is not None:
            value = self.default
        else:
            raise ParameterError(
                f"parameter {self.name!r} is required by this operation"
            )
        if self.type == "float":
            number = safe_float(value)
            if number is None:
                raise ParameterError(
                    f"parameter {self.name!r} must be a finite number, "
                    f"got {value!r}"
                )
            if self.minimum is not None and number < self.minimum:
                raise ParameterError(
                    f"parameter {self.name!r} must be at least {self.minimum}"
                )
            if self.maximum is not None and number > self.maximum:
                raise ParameterError(
                    f"parameter {self.name!r} must be at most {self.maximum}"
                )
            return number
        return value


@dataclass(frozen=True)
class OperationSpec:
    """One entry of the vocabulary. Every field here is load-bearing."""

    operation_id: str
    version: str
    arity: Optional[int]
    arity_range: Optional[Tuple[int, int]]
    input_kinds: Tuple[str, ...]
    output_kind: str
    accepted_input_units: Optional[Tuple[str, ...]]
    output_unit: Optional[str]
    formula: str
    unit_rule: str
    missing_value_rule: str
    parameters: Tuple[ParameterSpec, ...] = ()
    implementation: Optional[Callable[..., Any]] = None
    # "ENGINE" when the 2.2.3 engine produces a figure through this operation.
    # "VOCABULARY" when the entry is part of the declared financial vocabulary
    # and is not yet exercised by the engine. A reader can tell which is which.
    rationale: str = "ENGINE"

    def contract_dict(self) -> Dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "version": self.version,
            "arity": self.arity,
            "arity_range": list(self.arity_range) if self.arity_range else None,
            "input_kinds": list(self.input_kinds),
            "output_kind": self.output_kind,
            "accepted_input_units": (
                list(self.accepted_input_units)
                if self.accepted_input_units
                else None
            ),
            "output_unit": self.output_unit,
            "formula": self.formula,
            "unit_rule": self.unit_rule,
            "missing_value_rule": self.missing_value_rule,
            "parameters": [
                {
                    "name": parameter.name,
                    "type": parameter.type,
                    "required": parameter.required,
                    "default": parameter.default,
                    "minimum": parameter.minimum,
                    "maximum": parameter.maximum,
                }
                for parameter in self.parameters
            ],
            "rationale": self.rationale,
        }


# ---------------------------------------------------------------------------
# Unit rules
# ---------------------------------------------------------------------------

# divide: (numerator unit, denominator unit) -> result unit. A pair absent from
# this table is a UnitRuleError, so a malformed document fails loudly rather
# than producing a plausible wrong number.
DIVIDE_UNITS: Dict[Tuple[str, str], str] = {
    (Unit.CURRENCY.value, Unit.PER_SHARE.value): Unit.MULTIPLE.value,
    (Unit.CURRENCY.value, Unit.MULTIPLE.value): Unit.PER_SHARE.value,
    # Two monetary amounts over two monetary amounts is a valuation multiple
    # (price over free cash flow, enterprise value over EBITDA). Dividing a
    # market capitalisation by a price to recover a share count has the same
    # operand units and a different meaning, so it has its own operation rather
    # than a special case here.
    (Unit.CURRENCY.value, Unit.CURRENCY.value): Unit.MULTIPLE.value,
    # (currency, count) is deliberately absent: a price per share and a
    # valuation multiple per share have identical operand units and different
    # meanings. Callers must name the one they mean with amount_per_share or an
    # explicit multiple operation, rather than have the table guess.
    (Unit.PER_SHARE.value, Unit.PER_SHARE.value): Unit.RATIO.value,
    (Unit.MULTIPLE.value, Unit.MULTIPLE.value): Unit.RATIO.value,
    (Unit.COUNT.value, Unit.COUNT.value): Unit.RATIO.value,
}

# multiply: (left, right) -> result. A price times a share count is money, and
# earnings per share times a P/E multiple is a price per share, which is the
# cross-check on the consensus price.
MULTIPLY_UNITS: Dict[Tuple[str, str], str] = {
    (Unit.CURRENCY.value, Unit.COUNT.value): Unit.CURRENCY.value,
    (Unit.CURRENCY.value, Unit.PER_SHARE.value): Unit.RATIO.value,
    (Unit.PER_SHARE.value, Unit.MULTIPLE.value): Unit.CURRENCY.value,
    (Unit.RATIO.value, Unit.RATIO.value): Unit.RATIO.value,
    (Unit.MULTIPLE.value, Unit.RATIO.value): Unit.MULTIPLE.value,
    (Unit.MULTIPLE.value, Unit.PER_SHARE.value): Unit.CURRENCY.value,
}


def _numeric(value: Any, operation_id: str, position: int) -> float:
    number = safe_float(value)
    if number is None:
        raise MissingOperandError(
            f"{operation_id}: operand {position} is not a finite number "
            f"(got {value!r})"
        )
    return number


def _numeric_list(
    value: Any,
    operation_id: str,
    minimum: int = 1,
) -> List[float]:
    if not isinstance(value, (list, tuple)):
        raise MissingOperandError(
            f"{operation_id}: expected a list operand, got {type(value).__name__}"
        )
    numbers: List[float] = []
    for item in value:
        number = safe_float(item)
        if number is None:
            raise MissingOperandError(
                f"{operation_id}: list operand contains a non-numeric item "
                f"({item!r})"
            )
        numbers.append(number)
    if len(numbers) < minimum:
        raise MissingOperandError(
            f"{operation_id}: needs at least {minimum} sample(s), got "
            f"{len(numbers)}"
        )
    return numbers


def _op_divide(values: Sequence[float], units: Sequence[Optional[str]]) -> float:
    numerator_unit, denominator_unit = units[0], units[1]
    if numerator_unit and denominator_unit:
        key = (numerator_unit, denominator_unit)
        if key not in DIVIDE_UNITS:
            raise UnitRuleError(
                f"divide does not define a result for "
                f"{numerator_unit!r} / {denominator_unit!r}"
            )
    return values[0] / values[1]


def _op_multiply(values: Sequence[float], units: Sequence[Optional[str]]) -> float:
    left_unit, right_unit = units[0], units[1]
    if left_unit and right_unit:
        key = (left_unit, right_unit)
        if key not in MULTIPLY_UNITS:
            raise UnitRuleError(
                f"multiply does not define a result for "
                f"{left_unit!r} * {right_unit!r}"
            )
    return values[0] * values[1]


def _op_percentile_position(
    values: Sequence[float],
    units: Sequence[Optional[str]],
    band: Dict[str, float],
) -> Optional[float]:
    """
    Where a value sits within a percentile band, by linear interpolation.

    The inverse of `percentile`. They are separate operations because
    conflating the two is how a percentile ends up inverted by accident, and an
    inverted percentile would still look like a plausible number.

    The result is a position in the same 10/25/50/75/90 space the band keys are
    named for, not a 0-to-1 fraction, and it is clamped to that range. A band
    whose points are not strictly increasing is refused: a percentile read from
    a band that folds back on itself is meaningless, and returning a number
    anyway would be worse than returning nothing.
    """
    missing = [key for key in BAND_KEYS if key not in band]
    if missing:
        raise ParameterError(
            "percentile_position requires the band keys "
            f"{list(BAND_KEYS)}; missing {missing}"
        )
    points = [
        (_band_key_position(key), float(band[key])) for key in BAND_KEYS
    ]
    for (_, low_value), (_, high_value) in zip(points, points[1:]):
        if low_value >= high_value:
            raise ParameterError(
                "percentile_position requires a strictly increasing band; "
                f"{low_value} is not below {high_value}"
            )

    value = values[0]
    if value <= points[0][1]:
        return points[0][0]
    for (low_position, low_value), (high_position, high_value) in zip(
        points, points[1:]
    ):
        if value <= high_value:
            if value <= low_value:
                return low_position
            return low_position + (high_position - low_position) * (
                (value - low_value) / (high_value - low_value)
            )
    return points[-1][0]


# The band keys name percentile positions in 10/25/50/75/90 space, so a
# percentile read from a band is reported in the same space. A consumer reading
# "27.5" understands it as "the 27.5th percentile", which is what the field
# name has always meant in the 2.2.3 output.
_BAND_KEY_POSITIONS = {
    "10th": 10.0,
    "25th": 25.0,
    "median": 50.0,
    "75th": 75.0,
    "90th": 90.0,
}


def _band_key_position(key: str) -> float:
    return _BAND_KEY_POSITIONS[key]


def _op_log_returns(values: Sequence[float], units: Sequence[Optional[str]]) -> List[float]:
    prices = _numeric_list(values[0], "log_returns")
    if len(prices) < 2:
        raise MissingOperandError("log_returns needs at least two prices")
    if any(price <= 0 for price in prices):
        raise ParameterError("log_returns requires strictly positive prices")
    return [math.log(prices[index] / prices[index - 1]) for index in range(1, len(prices))]


def _op_sample_standard_deviation(
    values: Sequence[float],
    units: Sequence[Optional[str]],
) -> float:
    numbers = _numeric_list(values[0], "sample_standard_deviation", minimum=2)
    mean = sum(numbers) / len(numbers)
    variance = sum((x - mean) ** 2 for x in numbers) / (len(numbers) - 1)
    return math.sqrt(variance)


def _linear_percentile(ordered: Sequence[float], fraction: float) -> float:
    if len(ordered) == 1:
        return float(ordered[0])
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(ordered[lower])
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _scalar_list_op(
    reducer: Callable[[List[float]], float],
    operation_id: str,
) -> Callable[..., Any]:
    def run(values: Sequence[float], units: Sequence[Optional[str]]) -> float:
        return reducer(_numeric_list(values[0], operation_id))

    return run


def _spec(
    operation_id: str,
    *,
    arity: Optional[int] = None,
    arity_range: Optional[Tuple[int, int]] = None,
    input_kinds: Tuple[str, ...],
    output_kind: str,
    accepted_input_units: Optional[Tuple[str, ...]] = None,
    output_unit: Optional[str] = None,
    formula: str,
    unit_rule: str,
    implementation: Optional[Callable[..., Any]] = None,
    parameters: Tuple[ParameterSpec, ...] = (),
    rationale: str = "ENGINE",
    version: str = REGISTRY_VERSION,
) -> OperationSpec:
    return OperationSpec(
        operation_id=operation_id,
        version=version,
        arity=arity,
        arity_range=arity_range,
        input_kinds=input_kinds,
        output_kind=output_kind,
        accepted_input_units=accepted_input_units,
        output_unit=output_unit,
        formula=formula,
        unit_rule=unit_rule,
        missing_value_rule=MISSING_VALUE_RULE_PROPAGATE,
        parameters=parameters,
        implementation=implementation,
        rationale=rationale,
    )


# Operations whose two operands are both quantities of the same kind, and so
# are only combinable when they are also in the same currency. `ratio` and the
# statistical reducers are excluded: they are dimensionless by construction, and
# applying the gate to them would refuse legitimate comparisons across
# differently denominated series.
_BINARY_OPERATIONS: Dict[str, bool] = {
    "divide": True,
    "multiply": True,
    "add": True,
    "subtract": True,
    "amount_per_share": True,
    "shares_from_market_cap": True,
    "market_cap_from_price_shares": True,
    "enterprise_value": True,
}

_ANY_UNIT: Tuple[str, ...] = tuple(unit.value for unit in Unit)

OPERATIONS: Dict[Tuple[str, str], OperationSpec] = {}


def _adapt(implementation: Optional[Callable[..., Any]]) -> Optional[Callable[..., Any]]:
    """
    Give every implementation the same three-argument shape.

    An operation that takes no parameters still receives them, so the dispatch
    in `evaluate` has exactly one calling convention and an implementation
    cannot accidentally read a parameter the spec does not declare.
    """
    if implementation is None:
        return None

    parameter_count = len(signature(implementation).parameters)
    if parameter_count >= 3:
        return implementation

    if parameter_count == 2:

        def two_arg(values: Sequence[Any], units: Sequence[Any], _params: Any) -> Any:
            return implementation(values, units)

        return two_arg

    def one_arg(values: Sequence[Any], _units: Sequence[Any], _params: Any) -> Any:
        return implementation(values)

    return one_arg


def _register(spec: OperationSpec) -> OperationSpec:
    adapted = _adapt(spec.implementation)
    OPERATIONS[(spec.operation_id, spec.version)] = replace(
        spec, implementation=adapted
    )
    return spec


def _build_registry() -> None:
    _register(
        _spec(
            "divide",
            arity=2,
            input_kinds=(NUMERIC, NUMERIC),
            output_kind=NUMERIC,
            accepted_input_units=_ANY_UNIT,
            output_unit="per the DIVIDE_UNITS table",
            formula="a / b",
            unit_rule=(
                "the result unit is looked up in DIVIDE_UNITS by "
                "(numerator unit, denominator unit); an absent pair is a "
                "UnitRuleError"
            ),
            implementation=_op_divide,
        )
    )
    _register(
        _spec(
            "multiply",
            arity=2,
            input_kinds=(NUMERIC, NUMERIC),
            output_kind=NUMERIC,
            accepted_input_units=_ANY_UNIT,
            output_unit="per the MULTIPLY_UNITS table",
            formula="a * b",
            unit_rule=(
                "the result unit is looked up in MULTIPLY_UNITS by operand "
                "units; an absent pair is a UnitRuleError"
            ),
            implementation=_op_multiply,
        )
    )
    for operation_id, formula in (
        ("add", "a + b"),
        ("subtract", "a - b"),
    ):
        _register(
            _spec(
                operation_id,
                arity=2,
                input_kinds=(NUMERIC, NUMERIC),
                output_kind=NUMERIC,
                accepted_input_units=_ANY_UNIT,
                output_unit="the operands' shared unit",
                formula=formula,
                unit_rule=(
                    "both operands must share a unit; the result is that unit. "
                    "Mismatched units are a UnitRuleError, which is what stops "
                    "a subtraction across currencies."
                ),
                implementation=(
                    lambda values, units, _formula=formula: (
                        values[0] + values[1]
                        if _formula == "a + b"
                        else values[0] - values[1]
                    )
                ),
            )
        )
    _register(
        _spec(
            "ratio",
            arity=2,
            input_kinds=(NUMERIC, NUMERIC),
            output_kind=NUMERIC,
            output_unit=Unit.RATIO.value,
            formula="a / b",
            unit_rule=(
                "the result is declared a ratio regardless of operand units, "
                "so use divide when the result unit matters"
            ),
            implementation=lambda values, units: values[0] / values[1],
        )
    )
    _register(
        _spec(
            "sum_periods",
            arity=1,
            input_kinds=(LIST,),
            output_kind=NUMERIC,
            output_unit="the operand's unit",
            formula="sum(x)",
            unit_rule="the result carries the operand's unit",
            implementation=_scalar_list_op(
                lambda numbers: sum(numbers), "sum_periods"
            ),
        )
    )
    _register(
        _spec(
            "mean",
            arity=1,
            input_kinds=(LIST,),
            output_kind=NUMERIC,
            output_unit="the operand's unit",
            formula="sum(x) / n",
            unit_rule="the result carries the operand's unit",
            implementation=_scalar_list_op(
                lambda numbers: sum(numbers) / len(numbers), "mean"
            ),
        )
    )
    _register(
        _spec(
            "sample_standard_deviation",
            arity=1,
            input_kinds=(LIST,),
            output_kind=NUMERIC,
            output_unit="the operand's unit",
            formula="sqrt(sum((x - mean(x)) ** 2) / (n - 1))",
            unit_rule="the result carries the operand's unit",
            implementation=_op_sample_standard_deviation,
        )
    )
    _register(
        _spec(
            "median",
            arity=1,
            input_kinds=(LIST,),
            output_kind=NUMERIC,
            output_unit="the operand's unit",
            formula="the ordinary sample median",
            unit_rule="the result carries the operand's unit",
            implementation=_scalar_list_op(
                lambda numbers: float(_sample_median(numbers)), "median"
            ),
        )
    )

    def run_percentile(
        values: Sequence[float],
        units: Sequence[Optional[str]],
        fraction: float,
    ) -> float:
        numbers = sorted(
            _numeric_list(values[0], "percentile")
        )
        return _linear_percentile(numbers, fraction)

    _register(
        _spec(
            "percentile",
            arity=1,
            input_kinds=(LIST,),
            output_kind=NUMERIC,
            output_unit="the operand's unit",
            formula=(
                "sort ascending, then linear interpolation at position "
                "(n - 1) * fraction"
            ),
            unit_rule="the result carries the operand's unit",
            parameters=(
                ParameterSpec(
                    name="fraction",
                    type="float",
                    required=True,
                    minimum=0.0,
                    maximum=1.0,
                ),
            ),
            implementation=lambda values, units, parameters: run_percentile(
                values, units, parameters["fraction"]
            ),
        )
    )

    def run_percentile_position(
        values: Sequence[float],
        units: Sequence[Optional[str]],
        band: Optional[Dict[str, float]],
    ) -> Optional[float]:
        if not isinstance(band, dict):
            raise ParameterError(
                "percentile_position requires a band figure as its second "
                "operand"
            )
        cleaned: Dict[str, float] = {}
        for key, item in band.items():
            number = safe_float(item)
            if number is not None:
                cleaned[key] = number
        return _op_percentile_position(values, units, cleaned)

    _register(
        _spec(
            "percentile_position",
            arity=2,
            input_kinds=(NUMERIC, LIST),
            output_kind=NUMERIC,
            output_unit=Unit.RATIO.value,
            formula=(
                "locate a value within the band by linear interpolation "
                "between the 10th/25th/median/75th/90th points"
            ),
            unit_rule=(
                "the second operand must be a band figure carrying all of "
                f"{list(BAND_KEYS)}; a band missing any of them is a "
                "ParameterError rather than an interpolation against whatever "
                "keys happen to exist"
            ),
            implementation=lambda values, units, parameters: (
                run_percentile_position(values, units, values[1])
            ),
        )
    )

    def run_compound_growth_rate(
        values: Sequence[float], units: Sequence[Optional[str]]
    ) -> float:
        end, start, years = values[0], values[1], values[2]
        if years <= 0:
            raise ParameterError("years must be positive")
        if start <= 0:
            raise ParameterError("the starting value must be positive")
        return (end / start) ** (1.0 / years) - 1.0

    _register(
        _spec(
            "compound_growth_rate",
            arity=3,
            input_kinds=(NUMERIC, NUMERIC, NUMERIC),
            output_kind=NUMERIC,
            output_unit=Unit.RATIO.value,
            formula="(end / start) ** (1 / years) - 1",
            unit_rule=(
                "years is an operand, not a parameter, so the horizon is a "
                "traced input rather than an ambient assumption: it materially "
                "changes the answer"
            ),
            implementation=run_compound_growth_rate,
        )
    )
    _register(
        _spec(
            "log_return",
            arity=2,
            input_kinds=(NUMERIC, NUMERIC),
            output_kind=NUMERIC,
            output_unit=Unit.RATIO.value,
            formula="ln(to / from)",
            unit_rule="both operands must be strictly positive",
            implementation=lambda values, units: (
                math.log(values[1] / values[0])
                if values[0] > 0 and values[1] > 0
                else _raise_parameter("log_return requires positive prices")
            ),
        )
    )
    _register(
        _spec(
            "log_returns",
            arity=1,
            input_kinds=(LIST,),
            output_kind=LIST,
            output_unit=Unit.RATIO.value,
            formula="[ln(x[i] / x[i - 1]) for i in 1..n - 1]",
            unit_rule=(
                "the operand is a price list; a list-valued result is a legal "
                "operand of sample_standard_deviation"
            ),
            implementation=_op_log_returns,
        )
    )
    _register(
        _spec(
            "annualized_volatility",
            arity=2,
            input_kinds=(NUMERIC, NUMERIC),
            output_kind=NUMERIC,
            output_unit=Unit.RATIO.value,
            formula="stdev * sqrt(periods)",
            unit_rule=(
                "periods is a traced ref so the annualisation convention is "
                "visible in the document rather than buried in the code"
            ),
            implementation=lambda values, units: values[0] * math.sqrt(
                values[1]
            ),
        )
    )
    _register(
        _spec(
            "price_return",
            arity=2,
            input_kinds=(NUMERIC, NUMERIC),
            output_kind=NUMERIC,
            output_unit=Unit.RATIO.value,
            formula="to / from - 1",
            unit_rule="both operands must be strictly positive",
            implementation=lambda values, units: (
                values[1] / values[0] - 1.0
                if values[0] > 0
                else _raise_parameter("price_return requires a positive base")
            ),
        )
    )
    _register(
        _spec(
            "deviation_from_average",
            arity=2,
            input_kinds=(NUMERIC, NUMERIC),
            output_kind=NUMERIC,
            output_unit=Unit.RATIO.value,
            formula="value / average - 1",
            unit_rule="the average must be strictly positive",
            implementation=lambda values, units: (
                values[0] / values[1] - 1.0
                if values[1] > 0
                else _raise_parameter(
                    "deviation_from_average requires a positive average"
                )
            ),
        )
    )
    _register(
        _spec(
            "market_cap_from_price_shares",
            arity=2,
            input_kinds=(NUMERIC, NUMERIC),
            output_kind=NUMERIC,
            output_unit=Unit.CURRENCY.value,
            formula="price * shares",
            unit_rule=(
                "operand units must be (currency, count); the 2.2.3 engine "
                "does not currently compute this, so the entry exists as "
                "declared vocabulary"
            ),
            implementation=_op_multiply,
            rationale="VOCABULARY",
        )
    )
    _register(
        _spec(
            "amount_per_share",
            arity=2,
            input_kinds=(NUMERIC, NUMERIC),
            output_kind=NUMERIC,
            output_unit=Unit.PER_SHARE.value,
            formula="amount / shares",
            unit_rule=(
                "both operands are monetary and a share count, and the result "
                "is an amount per share. A separate operation from divide "
                "because the operand units alone cannot distinguish a price per "
                "share from a valuation multiple"
            ),
            implementation=lambda values, units: values[0] / values[1],
        )
    )
    _register(
        _spec(
            "shares_from_market_cap",
            arity=2,
            input_kinds=(NUMERIC, NUMERIC),
            output_kind=NUMERIC,
            output_unit=Unit.COUNT.value,
            formula="market_cap / price",
            unit_rule=(
                "both operands are monetary and the result is a share count. "
                "It is a separate operation from divide because divide maps two "
                "monetary amounts to a valuation multiple, and mixing the two "
                "would make an implied share count look like a ratio"
            ),
            implementation=lambda values, units: values[0] / values[1],
        )
    )
    _register(
        _spec(
            "enterprise_value",
            arity=2,
            input_kinds=(NUMERIC, NUMERIC),
            output_kind=NUMERIC,
            output_unit=Unit.CURRENCY.value,
            formula="market_cap + net_debt",
            unit_rule=(
                "both operands must be currency; the 2.2.3 engine reads "
                "enterprise value as observed rather than computing it, so "
                "this entry is declared vocabulary"
            ),
            implementation=lambda values, units: values[0] + values[1],
            rationale="VOCABULARY",
        )
    )


def _raise_parameter(message: str) -> float:
    raise ParameterError(message)


_build_registry()


def registered_operations() -> List[str]:
    """Every operation_id in the registry, sorted, for introspection."""
    return sorted({operation_id for operation_id, _ in OPERATIONS})


def versions_for(operation_id: str) -> List[str]:
    return sorted(
        version
        for name, version in OPERATIONS
        if name == operation_id
    )


def lookup(operation_id: str, version: str = REGISTRY_VERSION) -> OperationSpec:
    """
    Resolve an operation, or fail loudly.

    Both failure modes are hard errors, because a document naming an operation
    the evaluator cannot run is a document whose provenance cannot be checked,
    and that is exactly the state 2.3-C exists to rule out.
    """
    versions = versions_for(operation_id)
    if not versions:
        raise UnknownOperationError(
            f"{operation_id!r} is not in the operation registry; known "
            f"operations: {registered_operations()}"
        )
    spec = OPERATIONS.get((operation_id, version))
    if spec is None:
        raise UnsupportedVersionError(
            f"operation {operation_id!r} does not support version "
            f"{version!r}; supported: {versions}"
        )
    return spec


def check_arity(spec: OperationSpec, operand_count: int) -> None:
    if spec.arity is not None and operand_count != spec.arity:
        raise ArityError(
            f"{spec.operation_id} v{spec.version} takes exactly "
            f"{spec.arity} operand(s), got {operand_count}"
        )
    if spec.arity_range is not None:
        low, high = spec.arity_range
        if not low <= operand_count <= high:
            raise ArityError(
                f"{spec.operation_id} v{spec.version} takes between {low} and "
                f"{high} operands, got {operand_count}"
            )


def result_unit(spec: OperationSpec, operand_units: Sequence[Optional[str]]) -> Optional[str]:
    """
    The unit of the result, from the declared table.

    Raises when the operand units have no defined combination, so a unit error
    is caught while the document is being built rather than after a consumer
    has read a number.
    """
    if spec.output_unit in (None, "the operands' shared unit"):
        if spec.operation_id in ("add", "subtract"):
            if (
                len(operand_units) == 2
                and operand_units[0]
                and operand_units[0] != operand_units[1]
            ):
                raise UnitRuleError(
                    f"{spec.operation_id} requires both operands to share a "
                    f"unit, got {operand_units[0]!r} and {operand_units[1]!r}"
                )
            return operand_units[0] if operand_units else None
        if spec.output_unit == "the operand's unit":
            return operand_units[0] if operand_units else None
        return None

    if spec.operation_id == "divide":
        numerator, denominator = operand_units[0], operand_units[1]
        if numerator and denominator:
            key = (numerator, denominator)
            if key not in DIVIDE_UNITS:
                raise UnitRuleError(
                    f"divide does not define a result for {numerator!r} / "
                    f"{denominator!r}"
                )
            return DIVIDE_UNITS[key]
        return spec.output_unit

    if spec.operation_id == "multiply":
        left, right = operand_units[0], operand_units[1]
        if left and right:
            key = (left, right)
            if key not in MULTIPLY_UNITS:
                raise UnitRuleError(
                    f"multiply does not define a result for {left!r} * {right!r}"
                )
            return MULTIPLY_UNITS[key]
        return spec.output_unit

    return spec.output_unit


def evaluate(
    operation_id: str,
    operands: Sequence[Any],
    operand_units: Optional[Sequence[Optional[str]]] = None,
    parameters: Optional[Dict[str, Any]] = None,
    version: str = REGISTRY_VERSION,
    operand_currencies: Optional[Sequence[Optional[str]]] = None,
) -> Any:
    """
    Run a registered operation.

    `operands` are already-resolved values: the graph evaluator resolves refs
    before calling this. An operand that is `None` means the input was
    unavailable, and `MissingOperandError` propagates that rather than
    substituting anything.

    `operand_currencies` is a separate axis from `operand_units`. A unit says
    what kind of quantity a figure is; a currency says which money. Two figures
    can share a unit and be incomparable, and when both state a currency that
    differs, the result is refused.
    """
    spec = lookup(operation_id, version)
    check_arity(spec, len(operands))

    if spec.accepted_input_units and operand_units:
        for position, unit in enumerate(operand_units):
            if unit is not None and unit not in spec.accepted_input_units:
                raise UnitRuleError(
                    f"{spec.operation_id} v{spec.version} operand {position} "
                    f"carries unit {unit!r}, which is not accepted"
                )

    if operand_currencies and _BINARY_OPERATIONS.get(operation_id):
        declared = [
            (position, str(currency).upper())
            for position, currency in enumerate(operand_currencies)
            if currency
        ]
        distinct = {currency for _, currency in declared}
        if len(distinct) > 1:
            detail = ", ".join(
                f"operand {position} is {currency}"
                for position, currency in declared
            )
            raise CurrencyMismatchError(
                f"{spec.operation_id} v{spec.version} combines amounts in "
                f"different currencies ({detail}). The result would be a number "
                "with no economic meaning, so it is refused. Convert to a "
                "common currency at a stated rate, or do not combine them."
            )

    for position, operand in enumerate(operands):
        if operand is None:
            raise MissingOperandError(
                f"{spec.operation_id} v{spec.version}: operand {position} is "
                "unavailable, so the result is unavailable. No substitute is "
                "permitted."
            )

    resolved_parameters: Dict[str, Any] = {}
    for parameter in spec.parameters:
        resolved_parameters[parameter.name] = parameter.resolve(
            parameters or {}
        )

    values: List[Any] = []
    for position, operand in enumerate(operands):
        kind = spec.input_kinds[position] if position < len(spec.input_kinds) else NUMERIC
        if kind == LIST:
            values.append(operand)
        else:
            values.append(_numeric(operand, spec.operation_id, position))

    if spec.implementation is None:
        raise UnknownOperationError(
            f"{spec.operation_id} v{spec.version} is declared but has no "
            "implementation; a declared-but-unimplemented operation cannot be "
            "used in a document"
        )

    return spec.implementation(values, list(operand_units or []), resolved_parameters)


def registry_contract() -> Dict[str, Any]:
    """
    The machine-readable registry, embedded in the context.

    A consumer that trusts neither ST-EVA's evaluator nor its document can read
    the formulas, arities, unit rules, and missing-value rules and check the
    work itself.
    """
    return {
        "registry_version": REGISTRY_VERSION,
        "operations": [
            OPERATIONS[key].contract_dict()
            for key in sorted(OPERATIONS)
        ],
        "unit_rules": {
            "divide": {
                f"{numerator} / {denominator}": result
                for (numerator, denominator), result in sorted(
                    DIVIDE_UNITS.items()
                )
            },
            "multiply": {
                f"{left} * {right}": result
                for (left, right), result in sorted(MULTIPLY_UNITS.items())
            },
        },
    }
