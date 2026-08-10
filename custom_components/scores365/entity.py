"""Mixin compartido para entidades 365Scores — evita duplicar device_info y boilerplate."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import DeviceInfo

from .const import CONF_COMPETITOR_ID, CONF_TEAM_NAME, DOMAIN, VERSION


class Scores365EntityMixin:
    """Mixin sin herencia de Entity — evita conflictos de MRO.

    Se combina con la clase base real de cada plataforma (CoordinatorEntity,
    RestoreEntity). No participa en la cadena de __init__ de Entity, por lo
    que cada subclase debe llamar a _init_common() explícitamente.
    """

    def _init_common(self, entry: ConfigEntry) -> None:
        self._team_name     = entry.data[CONF_TEAM_NAME]
        self._competitor_id = entry.data[CONF_COMPETITOR_ID]

    def _build_unique_id(self, key: str) -> str:
        return f"{DOMAIN}_{self._competitor_id}_{key}"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._competitor_id)},
            name=self._team_name,
            manufacturer="365Scores",
            model="Fútbol en vivo",
            sw_version=VERSION,
            configuration_url="https://www.365scores.com",
        )
