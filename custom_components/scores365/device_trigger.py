"""Device triggers para 365Scores — expone eventos del partido en la UI de automatizaciones.

Cubre los mismos 7 eventos que ya ofrece el blueprint scores365_eventos_partido.yaml,
para que se puedan usar directamente desde la pestaña "Automatizaciones" del
dispositivo sin necesidad del blueprint.
"""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components.device_automation import DEVICE_TRIGGER_BASE_SCHEMA
from homeassistant.components.homeassistant.triggers import state as state_trigger
from homeassistant.components.homeassistant.triggers import time as time_trigger
from homeassistant.const import CONF_DEVICE_ID, CONF_DOMAIN, CONF_ENTITY_ID, CONF_PLATFORM, CONF_TYPE
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.trigger import TriggerActionType, TriggerInfo

from .const import DEVICE_TRIGGER_TYPES, DOMAIN

TRIGGER_SCHEMA = DEVICE_TRIGGER_BASE_SCHEMA.extend(
    {vol.Required(CONF_TYPE): vol.In(DEVICE_TRIGGER_TYPES)}
)

# Mapea cada tipo de trigger al sufijo de unique_id de la entidad que lo respalda
# y a la plataforma de entidad (sensor/binary_sensor) donde vive.
_TRIGGER_SOURCE = {
    "previo_partido":  ("proximo_datetime_5min", "sensor"),
    "partido_inicia":  ("estado_partido", "sensor"),
    "medio_tiempo":    ("minuto_partido", "sensor"),
    "segundo_tiempo":  ("minuto_partido", "sensor"),
    "partido_termina": ("estado_partido", "sensor"),
    "gol":             ("gol", "binary_sensor"),
    "equipo_gana":     ("estado_partido", "sensor"),
}

# Condición from/to (para state trigger) por tipo — None para previo_partido (time trigger)
_STATE_CONDITIONS = {
    "partido_inicia":  {"to": "En curso"},
    "medio_tiempo":    {"to": "Entretiempo"},
    "segundo_tiempo":  {"from": "Entretiempo"},
    "partido_termina": {"from": "En curso", "to": "Finalizado"},
    "gol":             {"to": "on"},
    "equipo_gana":     {"from": "En curso", "to": "Finalizado"},
}


def _find_entity_id(hass: HomeAssistant, device_id: str, platform: str, suffix: str) -> str | None:
    """Busca, entre las entidades del dispositivo, la que corresponde al sufijo dado."""
    registry = er.async_get(hass)
    for entry in er.async_entries_for_device(registry, device_id):
        if entry.domain == platform and entry.unique_id.endswith(f"_{suffix}"):
            return entry.entity_id
    return None


async def async_get_triggers(hass: HomeAssistant, device_id: str) -> list[dict]:
    """Lista los triggers disponibles para un dispositivo 365Scores."""
    registry = er.async_get(hass)
    entries = er.async_entries_for_device(registry, device_id)
    if not any(entry.platform == DOMAIN for entry in entries):
        return []

    return [
        {
            CONF_PLATFORM: "device",
            CONF_DEVICE_ID: device_id,
            CONF_DOMAIN: DOMAIN,
            CONF_TYPE: trigger_type,
        }
        for trigger_type in DEVICE_TRIGGER_TYPES
    ]


async def async_attach_trigger(
    hass: HomeAssistant,
    config: dict,
    action: TriggerActionType,
    trigger_info: TriggerInfo,
) -> CALLBACK_TYPE:
    """Adjunta el trigger, delegando en las plataformas state/time estándar de HA."""
    device_id = config[CONF_DEVICE_ID]
    trigger_type = config[CONF_TYPE]
    suffix, platform = _TRIGGER_SOURCE[trigger_type]

    entity_id = _find_entity_id(hass, device_id, platform, suffix)
    if entity_id is None:
        # Entidad no encontrada (equipo recién configurado, aún sin datos) —
        # no adjuntar nada; se puede reintentar recargando la automatización.
        return lambda: None

    if trigger_type == "previo_partido":
        state_config = {
            CONF_PLATFORM: "time",
            "at": entity_id,
        }
        state_config = await time_trigger.async_validate_trigger_config(hass, state_config)
        return await time_trigger.async_attach_trigger(hass, state_config, action, trigger_info)

    condition = _STATE_CONDITIONS[trigger_type]
    state_config: dict[str, Any] = {
        CONF_PLATFORM: "state",
        CONF_ENTITY_ID: [entity_id],
    }
    state_config.update(condition)
    state_config = await state_trigger.async_validate_trigger_config(hass, state_config)

    if trigger_type != "equipo_gana":
        return await state_trigger.async_attach_trigger(hass, state_config, action, trigger_info)

    # "equipo_gana" necesita además que el último resultado sea favorable —
    # se envuelve la acción para verificar binary_sensor.[equipo]_resultado_favorable
    # antes de invocarla, ya que el state trigger por sí solo no distingue victoria de derrota.
    favorable_entity_id = _find_entity_id(hass, device_id, "binary_sensor", "resultado_favorable")

    @callback
    def _favorable_filtered_action(run_variables: dict, context: Any = None) -> None:
        if favorable_entity_id is not None:
            state = hass.states.get(favorable_entity_id)
            if state is None or state.state != "on":
                return
        hass.async_create_task(action(run_variables, context))

    return await state_trigger.async_attach_trigger(
        hass, state_config, _favorable_filtered_action, trigger_info
    )
