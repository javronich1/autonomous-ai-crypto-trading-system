"""Offline UI integration tests; visualization dependencies remain optional."""

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path
import socket
from unittest.mock import Mock, create_autospec

import pytest

pytest.importorskip("streamlit", reason="optional UI dependencies are not installed")
pytest.importorskip("plotly", reason="optional UI dependencies are not installed")
AppTest = pytest.importorskip("streamlit.testing.v1").AppTest

import crypto_trader.data as data

UTC = timezone.utc
START = datetime(2024, 1, 1, tzinfo=UTC)
END = START + timedelta(hours=3)
AS_OF = START + timedelta(hours=3, minutes=30)
APP = Path(__file__).resolve().parents[2] / "apps" / "research_terminal.py"


def acquisition_result(
    hours: tuple[int, ...] = (0, 1, 2), *, as_of: datetime = AS_OF
) -> data.BinanceKlineAcquisitionResult:
    """Build immutable API results with exact decimals and real sequence checks."""
    bars = tuple(
        data.OHLCVBar(
            timestamp=START + timedelta(hours=hour),
            open=Decimal("42000.123456789"),
            high=Decimal("42500.200000001"),
            low=Decimal("41900.300000009"),
            close=Decimal("42300.400000007"),
            volume=Decimal("12.500000003"),
        )
        for hour in hours
    )
    effective_end = min(END, as_of.replace(minute=0, second=0, microsecond=0))
    expected = max(0, (effective_end - START) // timedelta(hours=1))
    observed = len(set(hours))
    return data.BinanceKlineAcquisitionResult(
        requested_start=START,
        requested_end=END,
        effective_end=effective_end,
        as_of=as_of,
        bars=bars,
        sequence_validation=data.validate_hourly_bars(bars),
        coverage=data.AcquisitionCoverage(expected, observed, expected - observed),
    )


@pytest.fixture
def fetch(monkeypatch: pytest.MonkeyPatch) -> Mock:
    """Replace acquisition before app execution and fail on any network attempt."""
    def no_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("UI integration tests must remain offline")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setattr(socket.socket, "connect_ex", no_network)
    monkeypatch.setattr(socket, "getaddrinfo", no_network)
    fake = create_autospec(data.fetch_binance_spot_klines)
    fake.return_value = acquisition_result()
    monkeypatch.setattr(data, "fetch_binance_spot_klines", fake)
    return fake


def manual_request() -> AppTest:
    """Render and set fixed historical UTC controls without pressing fetch."""
    app = AppTest.from_file(APP).run()
    assert not app.exception
    app.checkbox[0].uncheck().run()
    for widget in app.date_input:
        widget.set_value(START.date())
    app.time_input[0].set_value(START.time())
    app.time_input[1].set_value(END.time())
    app.time_input[2].set_value(AS_OF.time())
    app.run()
    assert not app.exception
    return app


def metrics(app: AppTest) -> dict[str, str]:
    """Read displayed metrics by their user-visible labels."""
    return {metric.label: metric.value for metric in app.metric}


def test_initial_render_and_every_control_change_never_fetch(fetch: Mock) -> None:
    app = AppTest.from_file(APP).run()
    assert not app.exception
    assert not app.get("plotly_chart")
    assert "FETCH HISTORICAL DATA" in app.info[0].value
    fetch.assert_not_called()
    app.checkbox[0].uncheck().run()
    fetch.assert_not_called()
    for widget in app.date_input:
        widget.set_value(date(2024, 1, 1)).run()
        assert not app.exception
        fetch.assert_not_called()
    for widget in app.time_input:
        widget.set_value(time(5, 0)).run()
        assert not app.exception
        fetch.assert_not_called()
    app.checkbox[0].check().run()
    fetch.assert_not_called()


def test_explicit_fetch_passes_exact_aware_utc_request(fetch: Mock) -> None:
    app = manual_request()
    fetch.assert_not_called()
    app.button[0].click().run()
    assert not app.exception
    fetch.assert_called_once_with(START, END, as_of=AS_OF)
    args, kwargs = fetch.call_args
    assert all(value.tzinfo is UTC for value in (*args, kwargs["as_of"]))
    app.run()
    assert fetch.call_count == 1


def test_current_as_of_is_explicit_and_sampled_at_button_action(fetch: Mock) -> None:
    app = manual_request()
    app.checkbox[0].check().run()
    fetch.assert_not_called()
    before = datetime.now(UTC)
    app.button[0].click().run()
    after = datetime.now(UTC)
    assert not app.exception
    fetch.assert_called_once()
    args, kwargs = fetch.call_args
    assert args == (START, END)
    assert kwargs["as_of"].tzinfo is UTC
    assert before <= kwargs["as_of"] <= after


def test_success_renders_candles_volume_and_exact_normalized_table(fetch: Mock) -> None:
    app = manual_request().button[0].click().run()
    assert not app.exception
    charts = app.get("plotly_chart")
    assert len(charts) == 1
    figure = json.loads(charts[0].proto.spec)
    candles, volume = figure["data"]
    assert candles["type"] == "candlestick"
    assert volume["type"] == "bar"
    expected_timestamps = [f"2024-01-01T0{hour}:00:00+00:00" for hour in range(3)]
    assert candles["x"] == volume["x"] == expected_timestamps
    for field, value in (
        ("open", "42000.123456789"), ("high", "42500.200000001"),
        ("low", "41900.300000009"), ("close", "42300.400000007"),
    ):
        assert candles[field] == [float(value)] * 3
    assert volume["y"] == [float("12.500000003")] * 3
    assert candles["yaxis"] != volume["yaxis"]
    assert figure["layout"]["xaxis"]["matches"] == "x2"
    assert len(app.dataframe) == 1
    assert app.dataframe[0].value.to_dict("records") == [
        {
            "UTC TIMESTAMP": f"2024-01-01 0{hour}:00:00 UTC",
            "OPEN": "42000.123456789", "HIGH": "42500.200000001",
            "LOW": "41900.300000009", "CLOSE": "42300.400000007",
            "VOLUME": "12.500000003",
        }
        for hour in range(3)
    ]
    assert metrics(app)["COVERAGE COMPLETE"] == "YES"
    assert not app.error


@pytest.mark.parametrize("hours, sequence_valid", [((1, 2), "YES"), ((0, 2), "NO")])
def test_missing_coverage_and_sequence_issues_stay_visible(
    fetch: Mock, hours: tuple[int, ...], sequence_valid: str
) -> None:
    fetch.return_value = acquisition_result(hours)
    app = manual_request().button[0].click().run()
    assert not app.exception
    displayed = metrics(app)
    assert displayed["EXPECTED BARS"] == "3"
    assert displayed["OBSERVED UNIQUE ALIGNED"] == "2"
    assert displayed["MISSING EXPECTED"] == "1"
    assert displayed["COVERAGE COMPLETE"] == "NO"
    assert displayed["SEQUENCE VALID"] == sequence_valid
    assert len(app.get("plotly_chart")) == 1
    assert len(app.dataframe[-1].value) == 2
    if sequence_valid == "NO":
        assert app.dataframe[0].value.to_dict("records") == [{
            "CODE": "GAP", "INDEX": 1,
            "MESSAGE": "gap before index 1: 1 expected bar(s) missing",
            "MISSING BARS": 1,
        }]
    else:
        assert len(app.dataframe) == 1


@pytest.mark.parametrize("eligible", [False, True])
def test_empty_eligible_and_missing_source_results_are_distinct(
    fetch: Mock, eligible: bool
) -> None:
    as_of = AS_OF if eligible else START + timedelta(minutes=30)
    fetch.return_value = acquisition_result((), as_of=as_of)
    app = manual_request()
    app.time_input[2].set_value(as_of.time()).run()
    app.button[0].click().run()
    assert not app.exception
    assert not app.get("plotly_chart")
    assert app.dataframe[0].value.empty
    info = " ".join(item.value for item in app.info)
    if eligible:
        assert "No fully closed candles are eligible" not in info
        assert "No source observations were returned" in app.warning[0].value
        assert "All 3 expected hourly bars are missing" in app.warning[0].value
        assert metrics(app)["MISSING EXPECTED"] == "3"
        assert metrics(app)["COVERAGE COMPLETE"] == "NO"
    else:
        assert "No fully closed candles are eligible" in info
        assert not app.warning
        assert metrics(app)["EXPECTED BARS"] == "0"
        assert metrics(app)["COVERAGE COMPLETE"] == "YES"


def test_historical_cap_explanation_uses_explicit_as_of_hour(fetch: Mock) -> None:
    as_of = START + timedelta(hours=2, minutes=30)
    fetch.return_value = acquisition_result((0, 1), as_of=as_of)
    app = manual_request()
    app.time_input[2].set_value(as_of.time()).run()
    app.button[0].click().run()
    assert not app.exception
    assert "explicit AS OF UTC hour (2024-01-01 02:00:00 UTC)" in app.info[0].value
    assert "current" not in app.info[0].value.lower()
    assert "AS OF USED · 2024-01-01 02:30:00 UTC" in [c.value for c in app.caption]
    assert metrics(app)["REQUESTED END"] == "2024-01-01 03:00:00 UTC"
    assert metrics(app)["EFFECTIVE END"] == "2024-01-01 02:00:00 UTC"


@pytest.mark.parametrize("error", [
    data.BinanceKlineAcquisitionError("Binance kline transport failed"),
    ValueError("start must be earlier than end"),
    TypeError("start must be a datetime"),
])
def test_failed_fetch_clears_success_and_displays_error(fetch: Mock, error: Exception) -> None:
    app = manual_request().button[0].click().run()
    assert not app.exception
    assert app.get("plotly_chart")
    fetch.side_effect = error
    app.button[0].click().run()
    assert not app.exception
    assert fetch.call_count == 2
    assert app.error[0].value == f"ACQUISITION FAILED · {error}"
    assert not app.get("plotly_chart")
    assert not app.dataframe
    assert not app.metric
    assert "acquisition_result" not in app.session_state
    app.run()
    assert fetch.call_count == 2
    assert app.error
    fetch.side_effect = None
    app.button[0].click().run()
    assert not app.exception
    assert not app.error
    assert app.get("plotly_chart")
    assert "acquisition_error" not in app.session_state


def test_control_changes_keep_original_result_boundaries_and_notice(fetch: Mock) -> None:
    app = manual_request().button[0].click().run()
    original_metrics = metrics(app)
    original_table = app.dataframe[0].value.copy()
    original_figure = app.get("plotly_chart")[0].proto.spec
    for widget in app.date_input:
        widget.set_value(date(2024, 2, 2)).run()
    for widget in app.time_input:
        widget.set_value(time(5, 0)).run()
    app.checkbox[0].check().run()
    assert not app.exception
    fetch.assert_called_once_with(START, END, as_of=AS_OF)
    assert metrics(app) == original_metrics
    assert app.dataframe[0].value.equals(original_table)
    assert app.get("plotly_chart")[0].proto.spec == original_figure
    captions = " ".join(c.value for c in app.caption)
    assert "Showing the last successful fetch" in captions
    assert "Changes to acquisition controls apply only to the next explicit fetch" in captions
    assert "AS OF USED · 2024-01-01 03:30:00 UTC" in captions
