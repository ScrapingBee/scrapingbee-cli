"""Unit tests for the REPL responsive layout tiers (``_layout_tier``).

The tier boundaries drive every render/height/visibility decision in the REPL,
so we pin them here. Boundaries are derived from the module constants (not
hard-coded numbers) so tuning a breakpoint updates the expectations with it.
"""

from __future__ import annotations

import pytest

from scrapingbee_cli.interactive import (
    _COMPACT_COLS,
    _FULL_BANNER_COLS,
    _MIN_COLS,
    _MIN_ROWS,
    _MINIMAL_COLS,
    _layout_tier,
    _Tier,
)


class TestLayoutTierWidthBoundaries:
    """Width classification at each breakpoint, with ample rows."""

    @pytest.mark.parametrize(
        "cols,expected",
        [
            (_FULL_BANNER_COLS + 110, _Tier.FULL),
            (_FULL_BANNER_COLS, _Tier.FULL),  # exactly at the full-banner width
            (_FULL_BANNER_COLS - 1, _Tier.COMPACT),
            (_COMPACT_COLS, _Tier.COMPACT),
            (_COMPACT_COLS - 1, _Tier.MINIMAL),
            (_MINIMAL_COLS, _Tier.MINIMAL),
            (_MINIMAL_COLS - 1, _Tier.BARE),
            (_MIN_COLS, _Tier.BARE),  # the floor itself is still usable
            (_MIN_COLS - 1, _Tier.TOO_SMALL),
            (1, _Tier.TOO_SMALL),
        ],
    )
    def test_width_boundaries(self, cols, expected):
        assert _layout_tier(cols=cols, rows=_MIN_ROWS + 40) == expected


class TestLayoutTierRowFloor:
    """The row floor forces TOO_SMALL regardless of how wide the terminal is."""

    @pytest.mark.parametrize(
        "rows,expected",
        [
            (_MIN_ROWS + 40, _Tier.FULL),
            (_MIN_ROWS, _Tier.FULL),  # exactly at the floor is still usable
            (_MIN_ROWS - 1, _Tier.TOO_SMALL),
            (1, _Tier.TOO_SMALL),
        ],
    )
    def test_row_floor(self, rows, expected):
        assert _layout_tier(cols=_FULL_BANNER_COLS + 30, rows=rows) == expected

    def test_narrow_and_short_is_too_small(self):
        assert _layout_tier(cols=_MIN_COLS - 5, rows=_MIN_ROWS - 5) == _Tier.TOO_SMALL


class TestLayoutTierOrdering:
    """Tiers are an ordered scale so ``>=`` comparisons in the REPL work."""

    def test_strictly_increasing(self):
        assert _Tier.TOO_SMALL < _Tier.BARE < _Tier.MINIMAL < _Tier.COMPACT < _Tier.FULL
