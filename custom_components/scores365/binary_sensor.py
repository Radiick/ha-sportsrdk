"""Binary Sensors para la integración 365Scores."""
from __future__ import annotations

import logging

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_COMPETITOR_ID, CONF_TEAM_NAME, DOMAIN
from .coordinator import Scores365Coordinator

_LOGGER = logging.getLogger(__name__)

BINARY_DEFINITIONS = [
    # (sensor_type, friendly_name, icon, device_class, entity_category)
    ("partido_en_curso",    "Partido en Curso",     "mdi:soccer",       BinarySensorDeviceClass.RUNNING, None),
    ("gol",                 "Gol",                  "mdi:soccer-field", None,                            None),
    ("resultado_favorable", "Resultado Favorable",  "mdi:thumb-up",     None,                            None),
    ("datos_en_cache",      "Datos en Caché",       "mdi:cached",       BinarySensorDeviceClass.PROBLEM, EntityCategory.DIAGNOSTIC),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: Scores365Coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        Scores365BinarySensor(coordinator, entry, stype, fname, icon, dclass, ecat)
        for stype, fname, icon, dclass, ecat in BINARY_DEFINITIONS
    ])


class Scores365BinarySensor(CoordinatorEntity, BinarySensorEntity):

    def __init__(self, coordinator: Scores365Coordinator, entry: ConfigEntry,
                 sensor_type: str, friendly_name: str, icon: str,
                 device_class: BinarySensorDeviceClass | None,
                 entity_category: EntityCategory | None) -> None:
        super().__init__(coordinator)
        self._sensor_type           = sensor_type
        self._team_name             = entry.data[CONF_TEAM_NAME]
        self._competitor_id         = entry.data[CONF_COMPETITOR_ID]
        self._attr_name             = f"{self._team_name} {friendly_name}"
        self._attr_unique_id        = f"{DOMAIN}_{self._competitor_id}_{sensor_type}"
        self._attr_icon             = icon
        self._attr_device_class     = device_class
        self._attr_entity_category  = entity_category

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._competitor_id)},
            name=self._team_name,
            manufacturer="365Scores",
            model="Fútbol en vivo",
            sw_version="1.3.0",
        )

    @property
    def is_on(self) -> bool | None:
        data = self.coordinator.data
        if not data:
            return None
        match self._sensor_type:
            case "partido_en_curso":
                return data.get("is_live", False)
            case "gol":
                return data.get("goal", False)
            case "resultado_favorable":
                last = data.get("last")
                return last.get("favorable", False) if last else None
            case "datos_en_cache":
                return data.get("stale", False)
        return None

    @property
    def extra_state_attributes(self) -> dict:
        data = self.coordinator.data
        if not data:
            return {}

        attrs = {"competitor_id": self._competitor_id, "team": self._team_name}

        if self._sensor_type == "partido_en_curso":
            current = data.get("current")
            if current:
                attrs.update({
                    "local":            current["home_name"],
                    "visitante":        current["away_name"],
                    "score_local":      current["home_score"],
                    "score_visitante":  current["away_score"],
                    "minuto":           current["status_text"],
                    "logo_local":       current.get("home_logo", ""),
                    "logo_visitante":   current.get("away_logo", ""),
                    "ttl_polling":      data.get("ttl"),
                })

        if self._sensor_type == "gol":
            attrs["equipo"] = data.get("goal_team", "")

        if self._sensor_type == "resultado_favorable":
            last = data.get("last")
            if last:
                attrs.update({
                    "resultado":      last["result"],
                    "local":          last["home_name"],
                    "visitante":      last["away_name"],
                    "score":          f"{int(last['home_score'])} - {int(last['away_score'])}",
                    "logo_local":     last.get("home_logo", ""),
                    "logo_visitante": last.get("away_logo", ""),
                })

        if self._sensor_type == "datos_en_cache":
            attrs["ultimo_error"] = data.get("error", "")

        return attrs

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success
