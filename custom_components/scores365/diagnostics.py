"""Diagnósticos para la integración 365Scores."""
from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import Scores365Coordinator


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Vuelca el estado interno del coordinator para depuración.

    No se redacta nada: competitor_id y team_name no son datos sensibles
    (son públicos en la URL de 365scores.com).
    """
    coordinator: Scores365Coordinator = hass.data[DOMAIN][entry.entry_id]

    return {
        "entry_data": dict(entry.data),
        "entry_options": dict(entry.options),
        "coordinator": {
            "team_name": coordinator.team_name,
            "competitor_id": coordinator.competitor_id,
            "poll_mode": coordinator.poll_mode,
            "update_interval_seconds": (
                coordinator.update_interval.total_seconds()
                if coordinator.update_interval else None
            ),
            "last_update_success": coordinator.last_update_success,
            "consecutive_errors": coordinator._consecutive_errors,
            "last_ttl": coordinator._last_ttl,
            "is_live": coordinator._is_live,
            "current_game_id": coordinator._current_game_id,
            "next_start_time": (
                coordinator._next_start_time.isoformat()
                if coordinator._next_start_time else None
            ),
            "wakeup_scheduled_for": (
                coordinator._wakeup_scheduled_for.isoformat()
                if coordinator._wakeup_scheduled_for else None
            ),
            "pre_match_active": coordinator._pre_match_active,
            "pre_match_activated_at": (
                coordinator._pre_match_activated_at.isoformat()
                if coordinator._pre_match_activated_at else None
            ),
        },
        "data": coordinator.data,
    }
