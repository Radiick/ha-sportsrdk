"""Botón de actualización manual — 365Scores."""
from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import BUTTON_REFRESH, CONF_COMPETITOR_ID, CONF_TEAM_NAME, DOMAIN
from .coordinator import Scores365Coordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: Scores365Coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([Scores365RefreshButton(coordinator, entry)])


class Scores365RefreshButton(CoordinatorEntity, ButtonEntity):
    """Fuerza una consulta inmediata a la API sin alterar el TTL de polling normal."""

    def __init__(self, coordinator: Scores365Coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._team_name        = entry.data[CONF_TEAM_NAME]
        self._competitor_id    = entry.data[CONF_COMPETITOR_ID]
        self._attr_name        = f"{self._team_name} Actualizar Ahora"
        self._attr_unique_id   = f"{DOMAIN}_{self._competitor_id}_{BUTTON_REFRESH}"
        self._attr_icon        = "mdi:refresh"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._competitor_id)},
            name=self._team_name,
            manufacturer="365Scores",
            model="Fútbol en vivo",
            sw_version="1.5.0",
        )

    async def async_press(self) -> None:
        """Dispara una actualización inmediata, respetando el modo de polling actual."""
        _LOGGER.debug("%s: Actualización manual solicitada", self._team_name)
        await self.coordinator.async_request_refresh()
