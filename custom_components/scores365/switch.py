"""Switches de control para automatizaciones de LEDs — 365Scores."""
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
    SWITCH_LEDS_GLOBAL,
    SWITCH_LEDS_GOL,
    SWITCH_LEDS_MEDIO_TIEMPO,
)
from .coordinator import Scores365Coordinator

_LOGGER = logging.getLogger(__name__)

# (switch_key, friendly_name, icon, depends_on_global)
SWITCH_DEFINITIONS = [
    (SWITCH_LEDS_GLOBAL,       "LEDs Global",       "mdi:led-strip-variant", False),
    (SWITCH_LEDS_GOL,          "LEDs Gol",          "mdi:led-on",            True),
    (SWITCH_LEDS_MEDIO_TIEMPO, "LEDs Medio Tiempo", "mdi:led-outline",       True),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: Scores365Coordinator = hass.data[DOMAIN][entry.entry_id]

    switches = [
        Scores365Switch(coordinator, entry, key, fname, icon, dep_global)
        for key, fname, icon, dep_global in SWITCH_DEFINITIONS
    ]
    async_add_entities(switches)


class Scores365Switch(RestoreEntity, SwitchEntity):
    """
    Switch persistente para control de automatizaciones de LEDs.

    RestoreEntity guarda el estado ON/OFF en el almacenamiento de HA
    y lo restaura al reiniciar, sin necesidad de base de datos externa.

    Reglas:
      - leds_global: maestro. Al apagarse, apaga leds_gol y leds_medio_tiempo.
      - leds_gol / leds_medio_tiempo: no se pueden encender si global está OFF.
    """

    def __init__(self, coordinator: Scores365Coordinator, entry: ConfigEntry,
                 switch_key: str, friendly_name: str, icon: str,
                 depends_on_global: bool) -> None:
        self._coordinator      = coordinator
        self._switch_key       = switch_key
        self._team_name        = entry.data[CONF_TEAM_NAME]
        self._competitor_id    = entry.data[CONF_COMPETITOR_ID]
        self._depends_on_global = depends_on_global
        self._attr_name        = f"{self._team_name} {friendly_name}"
        self._attr_unique_id   = f"{DOMAIN}_{self._competitor_id}_{switch_key}"
        self._attr_icon        = icon
        self._is_on: bool      = False   # estado en memoria
        self._entry            = entry

    # ------------------------------------------------------------------
    # Restore state al arrancar HA
    # ------------------------------------------------------------------

    async def async_added_to_hass(self) -> None:
        """Restaura el último estado conocido."""
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
            sw_version="1.2.0",
        )

    @property
    def is_on(self) -> bool:
        return self._is_on

    @property
    def available(self) -> bool:
        return True   # los switches siempre están disponibles

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {
            "competitor_id":     self._competitor_id,
            "team":              self._team_name,
            "depende_de_global": self._depends_on_global,
        }
        if self._depends_on_global:
            global_state = self._get_global_switch_state()
            attrs["global_activo"] = global_state
            if not global_state:
                attrs["motivo_inactivo"] = "LEDs Global está apagado"
        return attrs

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enciende el switch. Si depende del global, lo verifica primero."""
        if self._depends_on_global and not self._get_global_switch_state():
            _LOGGER.warning(
                "%s: No se puede encender '%s' porque LEDs Global está apagado",
                self._team_name, self._switch_key,
            )
            return   # no encender, no lanzar error

        self._is_on = True
        self.async_write_ha_state()
        _LOGGER.debug("%s: %s → ON", self._team_name, self._switch_key)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Apaga el switch. Si es el global, apaga los dependientes también."""
        self._is_on = False
        self.async_write_ha_state()
        _LOGGER.debug("%s: %s → OFF", self._team_name, self._switch_key)

        if self._switch_key == SWITCH_LEDS_GLOBAL:
            await self._turn_off_dependents()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_global_switch_state(self) -> bool:
        """Busca el estado del switch global en el mismo device."""
        global_uid = f"{DOMAIN}_{self._competitor_id}_{SWITCH_LEDS_GLOBAL}"
        entity_registry = self.hass.data.get("entity_registry")
        if entity_registry is None:
            from homeassistant.helpers import entity_registry as er
            entity_registry = er.async_get(self.hass)

        for entity in entity_registry.entities.values():
            if entity.unique_id == global_uid:
                state = self.hass.states.get(entity.entity_id)
                if state:
                    return state.state == "on"
        return False

    async def _turn_off_dependents(self) -> None:
        """Apaga leds_gol y leds_medio_tiempo cuando el global se apaga."""
        dependent_keys = [SWITCH_LEDS_GOL, SWITCH_LEDS_MEDIO_TIEMPO]
        from homeassistant.helpers import entity_registry as er
        registry = er.async_get(self.hass)

        for key in dependent_keys:
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
                        _LOGGER.debug("%s: %s apagado por global OFF", self._team_name, key)
