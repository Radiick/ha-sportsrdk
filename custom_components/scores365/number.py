"""Slider de delay para automatizaciones — 365Scores."""
from __future__ import annotations

import logging

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DELAY_DEFAULT, DELAY_MAX, DELAY_MIN, DELAY_STEP, NUMBER_DELAY
from .entity import Scores365EntityMixin

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([Scores365DelayNumber(entry)])


class Scores365DelayNumber(Scores365EntityMixin, RestoreEntity, NumberEntity):
    """
    Slider de 0 a 60 segundos para agregar delay a automatizaciones.

    El valor se persiste con RestoreEntity — sobrevive reinicios de HA.

    Uso en automatización:
        delay:
          seconds: "{{ states('number.america_delay_automatizacion') | int }}"
    """

    def __init__(self, entry: ConfigEntry) -> None:
        self._init_common(entry)
        self._attr_name       = f"{self._team_name} Delay Automatización"
        self._attr_unique_id  = self._build_unique_id(NUMBER_DELAY)
        self._attr_icon       = "mdi:timer-sand"
        self._attr_native_min_value  = DELAY_MIN
        self._attr_native_max_value  = DELAY_MAX
        self._attr_native_step       = DELAY_STEP
        self._attr_mode              = NumberMode.SLIDER
        self._attr_native_unit_of_measurement = "s"
        self._current_value: float = float(DELAY_DEFAULT)

    async def async_added_to_hass(self) -> None:
        """Restaura el último valor al arrancar HA."""
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None:
            try:
                self._current_value = float(last.state)
                _LOGGER.debug("%s: delay restaurado → %ss",
                              self._team_name, self._current_value)
            except (ValueError, TypeError):
                self._current_value = float(DELAY_DEFAULT)

    @property
    def native_value(self) -> float:
        return self._current_value

    @property
    def available(self) -> bool:
        """Siempre disponible: es una preferencia local (RestoreEntity), no
        depende de la salud de la API — el usuario debe poder ajustar este
        valor incluso si 365Scores está caído."""
        return True

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "competitor_id": self._competitor_id,
            "team":          self._team_name,
            "uso":           (
                "Úsalo en automatizaciones con: "
                f"{{{{ states('{self.entity_id}') | int }}}}"
            ),
        }

    async def async_set_native_value(self, value: float) -> None:
        """Actualiza el valor del slider."""
        self._current_value = value
        self.async_write_ha_state()
        _LOGGER.debug("%s: delay cambiado a %ss", self._team_name, value)
