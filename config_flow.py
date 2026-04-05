"""Binary Sensors para la integración 365Scores."""
from __future__ import annotations

import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_COMPETITOR_ID,
    CONF_TEAM_NAME,
    DOMAIN,
)
from .coordinator import Scores365Coordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Configura los binary sensors."""
    coordinator: Scores365Coordinator = hass.data[DOMAIN][entry.entry_id]

    binary_sensors = [
        Scores365BinarySensor(coordinator, entry, "partido_en_curso", "Partido en Curso",  "mdi:soccer",        BinarySensorDeviceClass.RUNNING),
        Scores365BinarySensor(coordinator, entry, "gol",              "Gol",               "mdi:soccer-field",  None),
        Scores365BinarySensor(coordinator, entry, "resultado_favorable", "Resultado Favorable", "mdi:thumb-up", None),
    ]

    async_add_entities(binary_sensors)


class Scores365BinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor para la integración 365Scores."""

    def __init__(
        self,
        coordinator: Scores365Coordinator,
        entry: ConfigEntry,
        sensor_type: str,
        friendly_name: str,
        icon: str,
        device_class: BinarySensorDeviceClass | None,
    ) -> None:
        """Inicializa el binary sensor."""
        super().__init__(coordinator)
        self._sensor_type = sensor_type
        self._entry = entry
        self._team_name = entry.data[CONF_TEAM_NAME]
        self._competitor_id = entry.data[CONF_COMPETITOR_ID]
        self._attr_name = f"{self._team_name} {friendly_name}"
        self._attr_unique_id = f"{DOMAIN}_{self._competitor_id}_{sensor_type}"
        self._attr_icon = icon
        self._attr_device_class = device_class

    @property
    def device_info(self) -> DeviceInfo:
        """Info del dispositivo."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._competitor_id)},
            name=self._team_name,
            manufacturer="365Scores",
            model="Fútbol en vivo",
            sw_version="1.0.0",
        )

    @property
    def is_on(self) -> bool | None:
        """Retorna el estado del binary sensor."""
        data = self.coordinator.data
        if not data:
            return None

        if self._sensor_type == "partido_en_curso":
            return data.get("is_live", False)

        if self._sensor_type == "gol":
            return data.get("goal", False)

        if self._sensor_type == "resultado_favorable":
            last = data.get("last")
            if last:
                return last.get("favorable", False)
            return None

        return None

    @property
    def extra_state_attributes(self) -> dict:
        """Atributos extra del binary sensor."""
        data = self.coordinator.data
        if not data:
            return {}

        attrs = {
            "competitor_id": self._competitor_id,
            "team": self._team_name,
        }

        if self._sensor_type == "partido_en_curso":
            current = data.get("current")
            if current:
                attrs.update({
                    "local": current["home_name"],
                    "visitante": current["away_name"],
                    "score_local": current["home_score"],
                    "score_visitante": current["away_score"],
                    "minuto": current["status_text"],
                })

        if self._sensor_type == "gol":
            attrs["equipo"] = data.get("goal_team", "")

        if self._sensor_type == "resultado_favorable":
            last = data.get("last")
            if last:
                attrs.update({
                    "resultado": last["result"],
                    "local": last["home_name"],
                    "visitante": last["away_name"],
                    "score": f"{last['home_score']} - {last['away_score']}",
                })

        return attrs

    @property
    def available(self) -> bool:
        """Disponible si el coordinator tiene datos."""
        return self.coordinator.last_update_success
