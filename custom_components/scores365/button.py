"""Botón de actualización manual — 365Scores."""
from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import BUTTON_REFRESH, DOMAIN
from .coordinator import Scores365Coordinator
from .entity import Scores365EntityMixin

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: Scores365Coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([Scores365RefreshButton(coordinator, entry)])


class Scores365RefreshButton(Scores365EntityMixin, CoordinatorEntity, ButtonEntity):
    """Fuerza una consulta inmediata a la API sin alterar el TTL de polling normal."""

    def __init__(self, coordinator: Scores365Coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._init_common(entry)
        self._attr_name        = f"{self._team_name} Actualizar Ahora"
        self._attr_unique_id   = self._build_unique_id(BUTTON_REFRESH)
        self._attr_icon        = "mdi:refresh"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    async def async_press(self) -> None:
        """Dispara una actualización inmediata, respetando el modo de polling actual."""
        _LOGGER.debug("%s: Actualización manual solicitada", self._team_name)
        await self.coordinator.async_request_refresh()
