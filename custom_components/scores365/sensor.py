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

# (sensor_type, friendly_name, icon)
SENSOR_DEFINITIONS = [
    ("marcador_local",      "Marcador Local",       "mdi:scoreboard"),
    ("marcador_visitante",  "Marcador Visitante",   "mdi:scoreboard"),
    ("equipo_local",        "Equipo Local",         "mdi:shield"),
    ("equipo_visitante",    "Equipo Visitante",     "mdi:shield-outline"),
    ("minuto_partido",      "Minuto",               "mdi:timer"),
    ("estado_partido",      "Estado del Partido",   "mdi:soccer-field"),
    ("competicion",         "Competición",          "mdi:trophy"),
    ("ttl_actual",          "TTL de Polling",       "mdi:refresh"),
    ("proximo_equipos",     "Próximo: Equipos",     "mdi:calendar-clock"),
    ("proximo_fecha",       "Próximo: Fecha",       "mdi:calendar"),
    ("proximo_timestamp",   "Próximo: Timestamp",   "mdi:clock-outline"),
    ("proximo_liga",        "Próximo: Liga",        "mdi:trophy-outline"),
    ("ultimo_equipos",      "Último: Equipos",      "mdi:history"),
    ("ultimo_marcador",     "Último: Marcador",     "mdi:scoreboard-outline"),
    ("ultimo_resultado",    "Último: Resultado",    "mdi:check-circle"),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Configura los sensores."""
    coordinator: Scores365Coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        Scores365Sensor(coordinator, entry, stype, fname, icon)
        for stype, fname, icon in SENSOR_DEFINITIONS
    ])


class Scores365Sensor(CoordinatorEntity, SensorEntity):
    """Sensor genérico para la integración 365Scores."""

    def __init__(self, coordinator: Scores365Coordinator, entry: ConfigEntry,
                 sensor_type: str, friendly_name: str, icon: str) -> None:
        super().__init__(coordinator)
        self._sensor_type = sensor_type
        self._team_name = entry.data[CONF_TEAM_NAME]
        self._competitor_id = entry.data[CONF_COMPETITOR_ID]
        self._attr_name = f"{self._team_name} {friendly_name}"
        self._attr_unique_id = f"{DOMAIN}_{self._competitor_id}_{sensor_type}"
        self._attr_icon = icon

    @property
    def device_info(self) -> DeviceInfo:
        """Agrupa entidades bajo el mismo device, con logo del equipo."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._competitor_id)},
            name=self._team_name,
            manufacturer="365Scores",
            model="Fútbol en vivo",
            sw_version="1.0.0",
            configuration_url="https://www.365scores.com",
        )

    @property
    def entity_picture(self) -> str | None:
        """Muestra el logo del equipo en los sensores de marcador."""
        if self._sensor_type in ("marcador_local", "marcador_visitante",
                                  "estado_partido", "equipo_local"):
            return self.coordinator.team_logo_url
        return None

    @property
    def native_value(self) -> Any:
        """Valor del sensor."""
        data = self.coordinator.data
        if not data:
            return None

        current  = data.get("current")
        nxt      = data.get("next")
        last     = data.get("last")

        match self._sensor_type:
            # Partido actual
            case "estado_partido":
                return current["status"] if current else MATCH_STATUS_NO_MATCH
            case "equipo_local":
                return current["home_name"] if current else None
            case "equipo_visitante":
                return current["away_name"] if current else None
            case "marcador_local":
                return current["home_score"] if current else None
            case "marcador_visitante":
                return current["away_score"] if current else None
            case "minuto_partido":
                return current["status_text"] if current else None
            case "competicion":
                if current:
                    return current.get("competition", "")
                return last.get("competition", "") if last else None
            case "ttl_actual":
                return data.get("ttl")
            # Próximo partido
            case "proximo_equipos":
                return nxt["teams"] if nxt else None
            case "proximo_fecha":
                return nxt["start_time"] if nxt else None
            case "proximo_timestamp":
                return nxt["start_timestamp"] if nxt else None
            case "proximo_liga":
                return nxt.get("competition", "") if nxt else None
            # Último partido
            case "ultimo_equipos":
                return last["teams"] if last else None
            case "ultimo_marcador":
                return f"{last['home_score']} - {last['away_score']}" if last else None
            case "ultimo_resultado":
                return last["result"] if last else None

        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Atributos extra — incluye logos de ambos equipos."""
        data = self.coordinator.data
        if not data:
            return {}

        current = data.get("current")
        nxt     = data.get("next")
        last    = data.get("last")

        attrs: dict[str, Any] = {
            "competitor_id": self._competitor_id,
            "team": self._team_name,
        }

        if self._sensor_type in ("estado_partido", "marcador_local", "marcador_visitante") and current:
            attrs.update({
                "local":            current["home_name"],
                "visitante":        current["away_name"],
                "score_local":      current["home_score"],
                "score_visitante":  current["away_score"],
                "minuto":           current["status_text"],
                "competicion":      current.get("competition", ""),
                "logo_local":       current.get("home_logo", ""),
                "logo_visitante":   current.get("away_logo", ""),
            })

        if self._sensor_type == "ttl_actual":
            attrs["raw_ttl_api"] = data.get("raw_ttl")

        if self._sensor_type == "proximo_equipos" and nxt:
            attrs.update({
                "local":                    nxt["home_name"],
                "visitante":                nxt["away_name"],
                "fecha":                    nxt["start_time"],
                "timestamp_30min_antes":    nxt["start_timestamp"],
                "liga":                     nxt.get("competition", ""),
                "logo_local":               nxt.get("home_logo", ""),
                "logo_visitante":           nxt.get("away_logo", ""),
            })

        if self._sensor_type == "ultimo_marcador" and last:
            attrs.update({
                "local":            last["home_name"],
                "visitante":        last["away_name"],
                "score_local":      last["home_score"],
                "score_visitante":  last["away_score"],
                "resultado":        last["result"],
                "favorable":        last["favorable"],
                "liga":             last.get("competition", ""),
                "logo_local":       last.get("home_logo", ""),
                "logo_visitante":   last.get("away_logo", ""),
            })

        return attrs

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success
