"""Config Flow para la integración 365Scores."""
from __future__ import annotations

import logging
import time
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    API_BASE_URL,
    API_PARAMS,
    CONF_COMPETITOR_ID,
    CONF_LEAGUE_NAME,
    CONF_TEAM_NAME,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_TEAM_NAME): str,
        vol.Required(CONF_COMPETITOR_ID): str,
        vol.Optional(CONF_LEAGUE_NAME, default=""): str,
    }
)


class Scores365ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Maneja el flujo de configuración para 365Scores."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Primer paso: el usuario ingresa nombre e ID del equipo."""
        errors: dict[str, str] = {}

        if user_input is not None:
            competitor_id = user_input[CONF_COMPETITOR_ID].strip()
            team_name = user_input[CONF_TEAM_NAME].strip()

            # Validar que el ID sea numérico
            if not competitor_id.isdigit():
                errors[CONF_COMPETITOR_ID] = "invalid_id"
            else:
                # Validar que el ID existe en la API
                valid, detected_name = await self._validate_competitor(competitor_id)
                if not valid:
                    errors[CONF_COMPETITOR_ID] = "cannot_connect"
                else:
                    # Evitar duplicados
                    await self.async_set_unique_id(f"scores365_{competitor_id}")
                    self._abort_if_unique_id_configured()

                    return self.async_create_entry(
                        title=team_name,
                        data={
                            CONF_TEAM_NAME: team_name,
                            CONF_COMPETITOR_ID: competitor_id,
                            CONF_LEAGUE_NAME: user_input.get(CONF_LEAGUE_NAME, ""),
                        },
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
            description_placeholders={
                "api_hint": "Busca el ID en la URL de 365scores.com al seleccionar tu equipo"
            },
        )

    async def _validate_competitor(self, competitor_id: str) -> tuple[bool, str]:
        """Valida que el competitor ID existe y responde en la API."""
        timestamp = int(time.time())
        params = {**API_PARAMS, "competitors": competitor_id, "timestamp": timestamp}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    API_BASE_URL,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status != 200:
                        return False, ""
                    data = await response.json(content_type=None)

            games = data.get("games", [])
            if games:
                # Intentar extraer el nombre real del equipo de la respuesta
                for game in games:
                    for competitor_key in ["homeCompetitor", "awayCompetitor"]:
                        competitor = game.get(competitor_key, {})
                        if str(competitor.get("id", "")) == competitor_id:
                            return True, competitor.get("name", "")
            # Si no hay partidos pero la API respondió bien, igual es válido
            return True, ""

        except Exception as err:
            _LOGGER.error("Error validando competitor ID %s: %s", competitor_id, err)
            return False, ""

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Retorna el flujo de opciones."""
        return Scores365OptionsFlow(config_entry)


class Scores365OptionsFlow(config_entries.OptionsFlow):
    """Flujo de opciones para modificar configuración existente."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Inicializa el flujo de opciones."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Muestra el formulario de opciones."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_LEAGUE_NAME,
                    default=self.config_entry.data.get(CONF_LEAGUE_NAME, ""),
                ): str,
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)
