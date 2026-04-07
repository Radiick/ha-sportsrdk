"""Switches de eventos por equipo — 365Scores."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    CONF_COMPETITOR_ID,
    CONF_TEAM_NAME,
    DOMAIN,
    SWITCH_EVENTO_EQUIPO_GANA,
    SWITCH_EVENTO_GLOBAL,
    SWITCH_EVENTO_GOL,
    SWITCH_EVENTO_MEDIO_TIEMPO,
    SWITCH_EVENTO_PARTIDO_INICIA,
    SWITCH_EVENTO_PARTIDO_TERMINA,
    SWITCH_EVENTO_PREVIO_PARTIDO,
    SWITCHES_DEPENDIENTES,
)

_LOGGER = logging.getLogger(__name__)

# (switch_key, friendly_name, icon, es_global)
SWITCH_DEFINITIONS = [
    (SWITCH_EVENTO_GLOBAL,          "Eventos Global",          "mdi:toggle-switch",        True),
    (SWITCH_EVENTO_PREVIO_PARTIDO,  "Evento: Previo Partido",  "mdi:clock-alert-outline",  False),
    (SWITCH_EVENTO_PARTIDO_INICIA,  "Evento: Partido Inicia",  "mdi:play-circle-outline",  False),
    (SWITCH_EVENTO_MEDIO_TIEMPO,    "Evento: Medio Tiempo",    "mdi:timer-pause-outline",  False),
    (SWITCH_EVENTO_PARTIDO_TERMINA, "Evento: Partido Termina", "mdi:stop-circle-outline",  False),
    (SWITCH_EVENTO_GOL,             "Evento: Gol",             "mdi:soccer",               False),
    (SWITCH_EVENTO_EQUIPO_GANA,     "Evento: Equipo Gana",     "mdi:trophy-outline",       False),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([
        Scores365Switch(entry, key, fname, icon, is_global)
        for key, fname, icon, is_global in SWITCH_DEFINITIONS
    ])


class Scores365Switch(RestoreEntity, SwitchEntity):
    """
    Switch persistente para habilitar/deshabilitar eventos por equipo.

    Lógica del global:
      - Al apagarse → apaga todos los switches dependientes
      - Los dependientes no se pueden encender si el global está OFF
    """

    def __init__(self, entry: ConfigEntry, switch_key: str,
                 friendly_name: str, icon: str, is_global: bool) -> None:
        self._entry         = entry
        self._switch_key    = switch_key
        self._team_name     = entry.data[CONF_TEAM_NAME]
        self._competitor_id = entry.data[CONF_COMPETITOR_ID]
        self._is_global     = is_global
        self._is_on: bool   = True   # por defecto ON al instalar
        self._attr_name         = f"{self._team_name} {friendly_name}"
        self._attr_unique_id    = f"{DOMAIN}_{self._competitor_id}_{switch_key}"
        self._attr_icon         = icon

    # ------------------------------------------------------------------
    # Restore state al arrancar HA
    # ------------------------------------------------------------------

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None:
            self._is_on = last.state == "on"
            _LOGGER.debug("%s: estado restaurado → %s", self._attr_name, last.state)

    # ------------------------------------------------------------------
    # Propiedades
    # ------------------------------------------------------------------

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
    def is_on(self) -> bool:
        return self._is_on

    @property
    def available(self) -> bool:
        return True

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {
            "competitor_id": self._competitor_id,
            "team":          self._team_name,
            "es_global":     self._is_global,
        }
        if not self._is_global:
            global_on = self._get_global_state()
            attrs["global_activo"] = global_on
            if not global_on:
                attrs["motivo_inactivo"] = "Eventos Global está apagado"
        return attrs

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enciende el switch — los dependientes verifican el global primero."""
        if not self._is_global and not self._get_global_state():
            _LOGGER.warning(
                "%s: No se puede encender '%s' — Eventos Global está apagado",
                self._team_name, self._switch_key,
            )
            return
        self._is_on = True
        self.async_write_ha_state()
        _LOGGER.debug("%s: %s → ON", self._team_name, self._switch_key)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Apaga el switch. Si es global, apaga todos los dependientes."""
        self._is_on = False
        self.async_write_ha_state()
        _LOGGER.debug("%s: %s → OFF", self._team_name, self._switch_key)

        if self._is_global:
            await self._apagar_dependientes()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_global_state(self) -> bool:
        """Lee el estado actual del switch global de este equipo."""
        from homeassistant.helpers import entity_registry as er
        registry = er.async_get(self.hass)
        global_uid = f"{DOMAIN}_{self._competitor_id}_{SWITCH_EVENTO_GLOBAL}"
        for entity in registry.entities.values():
            if entity.unique_id == global_uid:
                state = self.hass.states.get(entity.entity_id)
                return state.state == "on" if state else False
        return False

    async def _apagar_dependientes(self) -> None:
        """Apaga todos los switches dependientes cuando el global se apaga."""
        from homeassistant.helpers import entity_registry as er
        registry = er.async_get(self.hass)

        for key in SWITCHES_DEPENDIENTES:
            uid = f"{DOMAIN}_{self._competitor_id}_{key}"
            for entity in registry.entities.values():
                if entity.unique_id == uid:
                    state = self.hass.states.get(entity.entity_id)
                    if state and state.state == "on":
                        await self.hass.services.async_call(
                            "switch", "turn_off",
                            {"entity_id": entity.entity_id},
                            blocking=True,
                        )
                        _LOGGER.debug(
                            "%s: %s apagado por Global OFF",
                            self._team_name, key,
                        )
