"""Sensores para la integración 365Scores."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_COMPETITOR_ID,
    CONF_TEAM_NAME,
    DOMAIN,
    MATCH_STATUS_NO_DATA,
    MATCH_STATUS_NO_MATCH,
)
from .coordinator import Scores365Coordinator

_LOGGER = logging.getLogger(__name__)

SENSOR_DEFINITIONS = [
    # (sensor_type, friendly_name, icon, entity_category)
    ("marcador_local",       "Marcador Local",         "mdi:scoreboard",         None),
    ("marcador_visitante",   "Marcador Visitante",     "mdi:scoreboard",         None),
    ("equipo_local",         "Equipo Local",           "mdi:shield",             None),
    ("equipo_visitante",     "Equipo Visitante",       "mdi:shield-outline",     None),
    ("minuto_partido",       "Minuto",                 "mdi:timer",              None),
    ("estado_partido",       "Estado del Partido",     "mdi:soccer-field",       None),
    ("competicion",          "Competición",            "mdi:trophy",             EntityCategory.DIAGNOSTIC),
    ("ttl_actual",           "TTL de Polling",         "mdi:refresh",            EntityCategory.DIAGNOSTIC),
    ("modo_polling",         "Modo de Polling",        "mdi:radar",              EntityCategory.DIAGNOSTIC),
    ("proximo_equipos",      "Próximo: Equipos",       "mdi:calendar-clock",     None),
    ("proximo_fecha",        "Próximo: Fecha",         "mdi:calendar",           None),
    ("proximo_datetime_5min","Próximo: -5min",         "mdi:clock-alert-outline",None),
    ("proximo_liga",         "Próximo: Liga",          "mdi:trophy-outline",     None),
    ("ultimo_equipos",       "Último: Equipos",        "mdi:history",            None),
    ("ultimo_marcador",      "Último: Marcador",       "mdi:scoreboard-outline", None),
    ("ultimo_resultado",     "Último: Resultado",      "mdi:check-circle",       None),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: Scores365Coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        Scores365Sensor(coordinator, entry, stype, fname, icon, ecat)
        for stype, fname, icon, ecat in SENSOR_DEFINITIONS
    ])


class Scores365Sensor(CoordinatorEntity, SensorEntity):

    def __init__(self, coordinator: Scores365Coordinator, entry: ConfigEntry,
                 sensor_type: str, friendly_name: str, icon: str,
                 entity_category: EntityCategory | None) -> None:
        super().__init__(coordinator)
        self._sensor_type           = sensor_type
        self._team_name             = entry.data[CONF_TEAM_NAME]
        self._competitor_id         = entry.data[CONF_COMPETITOR_ID]
        self._attr_name             = f"{self._team_name} {friendly_name}"
        self._attr_unique_id        = f"{DOMAIN}_{self._competitor_id}_{sensor_type}"
        self._attr_icon             = icon
        self._attr_entity_category  = entity_category
        # El sensor de datetime necesita device_class TIMESTAMP para que
        # platform: time en el blueprint lo reconozca como hora de disparo
        if sensor_type == "proximo_datetime_5min":
            self._attr_device_class = SensorDeviceClass.TIMESTAMP

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._competitor_id)},
            name=self._team_name,
            manufacturer="365Scores",
            model="Fútbol en vivo",
            sw_version="1.5.0",
            configuration_url="https://www.365scores.com",
        )

    @property
    def entity_picture(self) -> str | None:
        """Logo del equipo local o visitante según el sensor, tomado del partido actual."""
        data = self.coordinator.data
        if not data:
            return None
        current = data.get("current")
        if self._sensor_type == "equipo_local":
            return current.get("home_logo") if current else None
        if self._sensor_type == "equipo_visitante":
            return current.get("away_logo") if current else None
        return None

    @property
    def native_value(self) -> Any:
        data = self.coordinator.data
        if not data:
            return None

        current = data.get("current")
        nxt     = data.get("next")
        last    = data.get("last")

        match self._sensor_type:
            case "estado_partido":
                if current:
                    return current["status"]
                if not data.get("has_data"):
                    return MATCH_STATUS_NO_DATA
                return MATCH_STATUS_NO_MATCH
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
                    return current.get("competition")
                return last.get("competition") if last else None
            case "ttl_actual":
                return data.get("ttl")
            case "modo_polling":
                return data.get("poll_mode", self.coordinator.poll_mode)
            case "proximo_equipos":
                return nxt["teams"] if nxt else None
            case "proximo_fecha":
                return nxt["start_time"] if nxt else None
            case "proximo_datetime_5min":
                # Devuelve datetime con TZ — HA lo reconoce como timestamp
                return nxt["start_datetime_5min"] if nxt else None
            case "proximo_liga":
                return nxt.get("competition") if nxt else None
            case "ultimo_equipos":
                return last["teams"] if last else None
            case "ultimo_marcador":
                # int() garantiza "1" en lugar de "1.0"
                if last:
                    return f"{int(last['home_score'])} - {int(last['away_score'])}"
                return None
            case "ultimo_resultado":
                return last["result"] if last else None
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        if not data:
            return {}

        current = data.get("current")
        nxt     = data.get("next")
        last    = data.get("last")

        attrs: dict[str, Any] = {
            "competitor_id": self._competitor_id,
            "team":          self._team_name,
            "datos_en_cache": data.get("stale", False),
        }

        if data.get("stale"):
            attrs["ultimo_error"] = data.get("error", "")

        if self._sensor_type in ("estado_partido", "marcador_local", "marcador_visitante") and current:
            attrs.update({
                "local":           current["home_name"],
                "visitante":       current["away_name"],
                "score_local":     current["home_score"],
                "score_visitante": current["away_score"],
                "minuto":          current["status_text"],
                "competicion":     current.get("competition", ""),
                "logo_local":      current.get("home_logo", ""),
                "logo_visitante":  current.get("away_logo", ""),
            })

        if self._sensor_type == "ttl_actual":
            attrs["raw_ttl_api"] = data.get("raw_ttl")

        if self._sensor_type == "modo_polling":
            coord = self.coordinator
            attrs.update({
                "ttl_actual":        data.get("ttl"),
                "raw_ttl_api":       data.get("raw_ttl"),
                "game_id":           data.get("game_id", ""),
                "errores_seguidos":  coord._consecutive_errors,
                "alarma_programada": str(coord._wakeup_scheduled_for) if coord._wakeup_scheduled_for else "No",
                "proximo_inicio":    str(coord._next_start_time) if coord._next_start_time else "No",
            })

        if self._sensor_type == "proximo_equipos" and nxt:
            attrs.update({
                "local":            nxt["home_name"],
                "visitante":        nxt["away_name"],
                "fecha":            nxt["start_time"],
                "datetime_5min":    str(nxt.get("start_datetime_5min", "")),
                "liga":             nxt.get("competition", ""),
                "logo_local":       nxt.get("home_logo", ""),
                "logo_visitante":   nxt.get("away_logo", ""),
            })

        if self._sensor_type == "ultimo_marcador" and last:
            attrs.update({
                "local":           last["home_name"],
                "visitante":       last["away_name"],
                "score_local":     int(last["home_score"]),
                "score_visitante": int(last["away_score"]),
                "resultado":       last["result"],
                "favorable":       last["favorable"],
                "liga":            last.get("competition", ""),
                "logo_local":      last.get("home_logo", ""),
                "logo_visitante":  last.get("away_logo", ""),
            })

        return attrs

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success
