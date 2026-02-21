"""
Shared pytest fixtures for Class Trader backend tests.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def db():
    """
    A mock AsyncSession. Tests that call functions with DB access pass this in.
    Most tests mock out the actual DB-calling sub-functions rather than the
    session itself, but having a shared mock keeps test signatures clean.
    """
    return AsyncMock()


def mock_settings(**overrides):
    """
    Return a MagicMock configured with default risk parameters.
    Pass keyword args to override specific settings.
    """
    s = MagicMock()
    s.min_confidence_main = overrides.get('min_confidence_main', 0.65)
    s.min_confidence_penny = overrides.get('min_confidence_penny', 0.60)
    s.max_position_pct_main = overrides.get('max_position_pct_main', 30.0)
    s.max_position_dollars_penny = overrides.get('max_position_dollars_penny', 8.0)
    s.daily_loss_limit_main_pct = overrides.get('daily_loss_limit_main_pct', 5.0)
    s.daily_loss_limit_penny_pct = overrides.get('daily_loss_limit_penny_pct', 15.0)
    s.consecutive_loss_pause = overrides.get('consecutive_loss_pause', 3)
    return s
