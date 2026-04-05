"""Sensores para la integración 365Scores."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_COMPETITOR_ID,
    CONF_LEAGUE_NAME,
    CONF_TEAM_NAME,
    DOMAIN,
    MATCH_STATUS_NO_MATCH,
)
from .coordinator import Scores365Coordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Configura los sensores de la integración."""
    coordinator: Scores365Coordinator = hass.data[DOMAIN][entry.entry_id]

    sensors = [
        # Partido actual
        Scores365Sensor(coordinator, entry, "marcador_local",       "Marcador Local",       "mdi:scoreboard"),
        Scores365Sensor(coordinator, entry, "marcador_visitante",   "Marcador Visitante",   "mdi:scoreboard"),
        Scores365Sensor(coordinator, entry, "equipo_local",         "Equipo Local",         "mdi:shield"),
        Scores365Sensor(coordinator, entry, "equipo_visitante",     "Equipo Visitante",     "mdi:shield-outline"),
        Scores365Sensor(coordinator, entry, "minuto_partido",       "Minuto",               "mdi:timer"),
        Scores365Sensor(coordinator, entry, "estado_partido",       "Estado del Partido",   "mdi:soccer-field"),
        Scores365Sensor(coordinator, entry, "competicion",         "Competición",          "mdi:trophy"),
        # Próximo partido
        Scores365Sensor(coordinator, entry, "proximo_equipos",     "Próximo: Equipos",     "mdi:calendar-clock"),
        Scores365Sensor(coordinator, entry, "proximo_fecha",       "Próximo: Fecha",       "mdi:calendar"),
        Scores365Sensor(coordinator, entry, "proximo_timestamp",   "Próximo: Timestamp",   "mdi:clock-outline"),
        Scores365Sensor(coordinator, entry, "proximo_liga",        "Próximo: Liga",        "mdi:trophy-outline"),
        # Último partido
        Scores365Sensor(coordinator, entry, "ultimo_equipos",      "Último: Equipos",      "mdi:history"),
        Scores365Sensor(coordinator, entry, "ultimo_marcador",     "Último: Marcador",     "mdi:scoreboard-outline"),
        Scores365Sensor(coordinator, entry, "ultimo_resultado",    "Último: Resultado",    "mdi:check-circle"),
    ]

    async_add_entities(sensors)


class Scores365Sensor(CoordinatorEntity, SensorEntity):
    """Sensor genérico para la integración 365Scores."""

    def __init__(
        self,
        coordinator: Scores365Coordinator,
        entry: ConfigEntry,
        sensor_type: str,
        friendly_name: str,
        icon: str,
    ) -> None:
        """Inicializa el sensor."""
        super().__init__(coordinator)
        self._sensor_type = sensor_type
        self._entry = entry
        self._team_name = entry.data[CONF_TEAM_NAME]
        self._competitor_id = entry.data[CONF_COMPETITOR_ID]
        self._league_name = entry.data.get(CONF_LEAGUE_NAME, "")
        self._attr_name = f"{self._team_name} {friendly_name}"
        self._attr_unique_id = f"{DOMAIN}_{self._competitor_id}_{sensor_type}"
        self._attr_icon = icon

    @property
    def device_info(self) -> DeviceInfo:
        """Info del dispositivo - agrupa todas las entidades del equipo."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._competitor_id)},
            name=self._team_name,
            manufacturer="365Scores",
            model="Fútbol en vivo",
            sw_version="1.0.0",
            configuration_url=f"https://www.365scores.com",
        )

    @property
    def native_value(self) -> Any:
        """Retorna el valor del sensor según su tipo."""
        data = self.coordinator.data
        if not data:
            return None

        current = data.get("current")
        next_match = data.get("next")
        last = data.get("last")

        # Sensores de partido actual
        if self._sensor_type == "estado_partido":
            if current:
                return current["status"]
            elif next_match:
                return MATCH_STATUS_NO_MATCH
            return None

        if self._sensor_type == "equipo_local":
            return current["home_name"] if current else None

        if self._sensor_type == "equipo_visitante":
            return current["away_name"] if current else None

        if self._sensor_type == "marcador_local":
            return current["home_score"] if current else None

        if self._sensor_type == "marcador_visitante":
            return current["away_score"] if current else None

        if self._sensor_type == "minuto_partido":
            return current["status_text"] if current else None

        if self._sensor_type == "competicion":
            if current:
                return current.get("competition", "")
            elif last:
                return last.get("competition", "")
            return None

        # Sensores de próximo partido
        if self._sensor_type == "proximo_equipos":
            return next_match["teams"] if next_match else None

        if self._sensor_type == "proximo_fecha":
            return next_match["start_time"] if next_match else None

        if self._sensor_type == "proximo_timestamp":
            return next_match["start_timestamp"] if next_match else None

        if self._sensor_type == "proximo_liga":
            return next_match.get("competition", "") if next_match else None

        # Sensores de último partido
        if self._sensor_type == "ultimo_equipos":
            return last["teams"] if last else None

        if self._sensor_type == "ultimo_marcador":
            if last:
                return f"{last['home_score']} - {last['away_score']}"
            return None

        if self._sensor_type == "ultimo_resultado":
            return last["result"] if last else None

        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Atributos extra del sensor."""
        data = self.coordinator.data
        if not data:
            return {}

        current = data.get("current")
        next_match = data.get("next")
        last = data.get("last")

        attrs: dict[str, Any] = {
            "competitor_id": self._competitor_id,
            "team": self._team_name,
        }

        if self._sensor_type in ("estado_partido", "marcador_local", "marcador_visitante"):
            if current:
                attrs.update({
                    "local": current["home_name"],
                    "visitante": current["away_name"],
                    "score_local": current["home_score"],
                    "score_visitante": current["away_score"],
                    "minuto": current["status_text"],
                    "competicion": current.get("competition", ""),
                })

        if self._sensor_type == "proximo_equipos" and next_match:
            attrs.update({
                "local": next_match["home_name"],
                "visitante": next_match["away_name"],
                "fecha": next_match["start_time"],
                "timestamp_30min_antes": next_match["start_timestamp"],
                "liga": next_match.get("competition", ""),
            })

        if self._sensor_type == "ultimo_marcador" and last:
            attrs.update({
                "local": last["home_name"],
                "visitante": last["away_name"],
                "score_local": last["home_score"],
                "score_visitante": last["away_score"],
                "resultado": last["result"],
                "favorable": last["favorable"],
                "liga": last.get("competition", ""),
            })

        return attrs

    @property
    def available(self) -> bool:
        """El sensor está disponible si el coordinator tiene datos."""
        return self.coordinator.last_update_success
