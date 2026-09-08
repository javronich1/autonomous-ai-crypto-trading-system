"""Snapshot bytes must remain portable across caller Decimal contexts."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext

from crypto_trader.data import (
    AcquisitionCoverage,
    BinanceKlineAcquisitionResult,
    OHLCVBar,
    validate_hourly_bars,
)
from crypto_trader.data.snapshots import deserialize_snapshot, serialize_snapshot


def test_snapshot_roundtrip_is_independent_of_decimal_context() -> None:
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = start + timedelta(hours=1)
    bar = OHLCVBar(start, Decimal('1.2300E+8'), Decimal('2E+8'),
                   Decimal('1E+8'), Decimal('1.5E+8'), Decimal('-0E+4'))
    result = BinanceKlineAcquisitionResult(
        start, end, end, end, (bar,), validate_hourly_bars((bar,)),
        AcquisitionCoverage(1, 1, 0),
    )
    with localcontext() as context:
        context.capitals = 1
        expected = serialize_snapshot(result)
    with localcontext() as context:
        context.capitals = 0
        context.prec = 2
        context.Emax = 3
        context.Emin = -3
        context.clamp = 1
        context.clear_flags()
        original_flags = dict(context.flags)
        assert serialize_snapshot(result) == expected
        restored = deserialize_snapshot(expected)
        for name in ('open', 'high', 'low', 'close', 'volume'):
            assert getattr(restored.bars[0], name).as_tuple() == getattr(bar, name).as_tuple()
        assert context.capitals == 0
        assert context.prec == 2
        assert dict(context.flags) == original_flags
