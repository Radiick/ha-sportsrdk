"""Coordinator para 365Scores - maneja el polling de la API."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    API_BASE_URL,
    API_PARAMS,
    CONF_COMPETITOR_ID,
    CONF_TEAM_NAME,
    DOMAIN,
    GOAL_ALERT_DURATION,
    MATCH_STATUS_FINISHED,
    MATCH_STATUS_LIVE,
    MATCH_STATUS_NO_MATCH,
    RESULT_DRAW,
    RESULT_LOSS,
    RESULT_WIN,
    SCAN_INTERVAL_IDLE,
    SCAN_INTERVAL_LIVE,
    STATUS_GROUP_FINISHED,
    STATUS_GROUP_LIVE,
    STATUS_GROUP_UPCOMING,
)

_LOGGER = logging.getLogger(__name__)


class Scores365Coordinator(DataUpdateCoordinator):
    """Coordinator que gestiona la obtención de datos de 365Scores."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Inicializa el coordinator."""
        self.competitor_id = entry.data[CONF_COMPETITOR_ID]
        self.team_name = entry.data[CONF_TEAM_NAME]
        self._previous_score: int | None = None
        self._goal_detected_at: datetime | None = None
        self._is_live: bool = False

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{self.competitor_id}",
            update_interval=timedelta(seconds=SCAN_INTERVAL_IDLE),
        )

    def _set_interval(self, is_live: bool) -> None:
        """Ajusta el intervalo de polling según si hay partido en curso."""
        if is_live != self._is_live:
            self._is_live = is_live
            self.update_interval = timedelta(
                seconds=SCAN_INTERVAL_LIVE if is_live else SCAN_INTERVAL_IDLE
            )
            _LOGGER.debug(
                "Intervalo de polling cambiado a %s segundos para %s",
                self.update_interval.total_seconds(),
                self.team_name,
            )

    async def _async_update_data(self) -> dict[str, Any]:
        """Obtiene y procesa los datos de la API."""
        timestamp = int(time.time())
        params = {**API_PARAMS, "competitors": self.competitor_id, "timestamp": timestamp}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    API_BASE_URL, params=params, timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    response.raise_for_status()
                    raw = await response.json(content_type=None)
        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Error al conectar con 365Scores: {err}") from err
        except Exception as err:
            raise UpdateFailed(f"Error inesperado: {err}") from err

        return self._parse_data(raw)

    def _parse_data(self, raw: dict) -> dict[str, Any]:
        """Procesa el JSON crudo de la API y retorna datos normalizados."""
        games = raw.get("games", [])

        current_game = None
        next_game = None
        last_game = None

        for game in games:
            status_group = game.get("statusGroup")
            if status_group == STATUS_GROUP_FINISHED:
                last_game = game
            elif status_group == STATUS_GROUP_LIVE and current_game is None:
                current_game = game
            elif status_group == STATUS_GROUP_UPCOMING and next_game is None:
                next_game = game

        # Ajustar intervalo de polling
        self._set_interval(current_game is not None)

        result: dict[str, Any] = {
            "is_live": current_game is not None,
            "current": None,
            "next": None,
            "last": None,
            "goal": False,
            "goal_team": None,
        }

        # --- Partido en curso ---
        if current_game:
            home = current_game["homeCompetitor"]
            away = current_game["awayCompetitor"]
            current_score = self._get_team_score(home, away)

            # Detectar gol
            goal_detected = False
            if self._previous_score is not None and current_score is not None:
                if current_score > self._previous_score:
                    goal_detected = True
                    self._goal_detected_at = datetime.now(timezone.utc)
                    _LOGGER.info("¡GOL detectado para %s!", self.team_name)

            if current_score is not None:
                self._previous_score = current_score

            # Mantener alerta de gol activa por GOAL_ALERT_DURATION segundos
            goal_active = False
            if self._goal_detected_at is not None:
                elapsed = (datetime.now(timezone.utc) - self._goal_detected_at).total_seconds()
                if elapsed <= GOAL_ALERT_DURATION:
                    goal_active = True
                else:
                    self._goal_detected_at = None

            result["current"] = {
                "home_name": home.get("name", ""),
                "away_name": away.get("name", ""),
                "home_score": home.get("score", 0),
                "away_score": away.get("score", 0),
                "status_text": current_game.get("statusText", ""),
                "status": MATCH_STATUS_LIVE,
                "competition": current_game.get("competitionDisplayName", ""),
            }
            result["goal"] = goal_active
            result["goal_team"] = self.team_name if goal_active else None

        else:
            # Sin partido en curso → resetear score previo
            self._previous_score = None

        # --- Próximo partido ---
        if next_game:
            home = next_game["homeCompetitor"]
            away = next_game["awayCompetitor"]
            start_time_str = next_game.get("startTime", "")
            start_dt = None
            start_ts = None

            if start_time_str:
                try:
                    start_dt = datetime.fromisoformat(start_time_str)
                    # Timestamp 30 minutos antes (para automatizaciones)
                    start_ts = int((start_dt - timedelta(minutes=30)).timestamp())
                except ValueError:
                    pass

            result["next"] = {
                "home_name": home.get("name", ""),
                "away_name": away.get("name", ""),
                "teams": f"{home.get('name', '')} vs {away.get('name', '')}",
                "start_time": start_dt.strftime("%d de %B de %Y, %H:%M") if start_dt else start_time_str,
                "start_timestamp": start_ts,
                "competition": next_game.get("competitionDisplayName", ""),
                "status": MATCH_STATUS_NO_MATCH,
            }

        # --- Último partido ---
        if last_game:
            home = last_game["homeCompetitor"]
            away = last_game["awayCompetitor"]
            result_text = self._calculate_result(home, away)

            result["last"] = {
                "home_name": home.get("name", ""),
                "away_name": away.get("name", ""),
                "home_score": home.get("score", 0),
                "away_score": away.get("score", 0),
                "teams": f"{home.get('name', '')} vs {away.get('name', '')}",
                "result": result_text,
                "favorable": result_text in (RESULT_WIN, RESULT_DRAW),
                "competition": last_game.get("competitionDisplayName", ""),
                "status": MATCH_STATUS_FINISHED,
            }

        return result

    def _get_team_score(self, home: dict, away: dict) -> int | None:
        """Obtiene el marcador del equipo monitoreado."""
        team_name_lower = self.team_name.lower()
        home_name = home.get("name", "").lower()
        away_name = away.get("name", "").lower()
        home_url = home.get("nameForURL", "").lower()
        away_url = away.get("nameForURL", "").lower()

        if team_name_lower in home_name or team_name_lower in home_url:
            return home.get("score", 0)
        elif team_name_lower in away_name or team_name_lower in away_url:
            return away.get("score", 0)
        return None

    def _calculate_result(self, home: dict, away: dict) -> str:
        """Calcula si el resultado fue favorable para el equipo monitoreado."""
        team_name_lower = self.team_name.lower()
        home_name = home.get("name", "").lower()
        away_name = away.get("name", "").lower()
        home_url = home.get("nameForURL", "").lower()
        away_url = away.get("nameForURL", "").lower()

        home_score = home.get("score", 0)
        away_score = away.get("score", 0)

        if team_name_lower in home_name or team_name_lower in home_url:
            team_score, rival_score = home_score, away_score
        elif team_name_lower in away_name or team_name_lower in away_url:
            team_score, rival_score = away_score, home_score
        else:
            # Equipo no identificado, reportar igual
            return RESULT_DRAW

        if team_score > rival_score:
            return RESULT_WIN
        elif team_score == rival_score:
            return RESULT_DRAW
        else:
            return RESULT_LOSS
