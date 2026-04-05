"""Coordinator para 365Scores - polling dinámico con TTL, retry y backoff."""
from __future__ import annotations

import asyncio
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
    LOGO_BASE_URL,
    MATCH_STATUS_FINISHED,
    MATCH_STATUS_LIVE,
    MATCH_STATUS_NO_DATA,
    MATCH_STATUS_NO_MATCH,
    MAX_RETRIES,
    RESULT_DRAW,
    RESULT_LOSS,
    RESULT_WIN,
    RETRY_BACKOFF_BASE,
    RETRY_BACKOFF_MAX,
    STATUS_GROUP_FINISHED,
    STATUS_GROUP_LIVE,
    STATUS_GROUP_UPCOMING,
    TTL_CEILING_IDLE,
    TTL_CEILING_LIVE,
    TTL_DEFAULT,
    TTL_FLOOR_IDLE,
    TTL_FLOOR_LIVE,
)

_LOGGER = logging.getLogger(__name__)


class Scores365Coordinator(DataUpdateCoordinator):
    """Coordinator con TTL dinámico, retry con backoff y caché del último dato válido."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.competitor_id  = entry.data[CONF_COMPETITOR_ID]
        self.team_name      = entry.data[CONF_TEAM_NAME]
        self.team_logo_url  = LOGO_BASE_URL.format(competitor_id=self.competitor_id)

        # Estado interno
        self._previous_score: int | None     = None
        self._goal_detected_at: datetime | None = None
        self._is_live: bool                  = False
        self._last_ttl: int                  = TTL_DEFAULT
        self._consecutive_errors: int        = 0
        self._last_valid_data: dict | None   = None   # caché del último dato bueno

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{self.competitor_id}",
            update_interval=timedelta(seconds=TTL_DEFAULT),
        )

    # ------------------------------------------------------------------
    # TTL helpers
    # ------------------------------------------------------------------

    def _apply_ttl(self, raw_ttl: int | None, is_live: bool) -> int:
        ttl = raw_ttl if (raw_ttl is not None and raw_ttl > 0) else TTL_DEFAULT
        if is_live:
            clamped = max(TTL_FLOOR_LIVE, min(ttl, TTL_CEILING_LIVE))
        else:
            clamped = max(TTL_FLOOR_IDLE, min(ttl, TTL_CEILING_IDLE))
        if clamped != ttl:
            _LOGGER.debug("%s: TTL API=%ss → efectivo=%ss (live=%s)",
                          self.team_name, ttl, clamped, is_live)
        return clamped

    def _set_interval(self, seconds: int) -> None:
        new = timedelta(seconds=seconds)
        if self.update_interval != new:
            self.update_interval = new
            _LOGGER.debug("%s: Próximo polling en %ss", self.team_name, seconds)

    def _backoff_interval(self) -> int:
        """Calcula el intervalo de backoff exponencial según errores consecutivos."""
        delay = min(RETRY_BACKOFF_BASE * (2 ** (self._consecutive_errors - 1)),
                    RETRY_BACKOFF_MAX)
        _LOGGER.warning("%s: Error consecutivo #%s, reintentando en %ss",
                        self.team_name, self._consecutive_errors, delay)
        return delay

    # ------------------------------------------------------------------
    # Fetch con retry
    # ------------------------------------------------------------------

    async def _async_update_data(self) -> dict[str, Any]:
        timestamp = int(time.time())
        params = {**API_PARAMS, "competitors": self.competitor_id, "timestamp": timestamp}

        last_err: Exception | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        API_BASE_URL,
                        params=params,
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as response:
                        response.raise_for_status()
                        raw = await response.json(content_type=None)

                # Éxito — resetear contador de errores
                self._consecutive_errors = 0
                return self._parse_data(raw)

            except (aiohttp.ClientError, asyncio.TimeoutError) as err:
                last_err = err
                if attempt < MAX_RETRIES:
                    _LOGGER.debug("%s: Intento %s/%s falló (%s), reintentando…",
                                  self.team_name, attempt, MAX_RETRIES, err)
                    await asyncio.sleep(2 * attempt)   # pequeño delay entre reintentos
            except Exception as err:
                last_err = err
                break   # errores inesperados no se reintentan

        # Todos los intentos fallaron
        self._consecutive_errors += 1
        backoff = self._backoff_interval()
        self._set_interval(backoff)

        # Devuelve último dato válido con flag de error en lugar de levantar excepción
        if self._last_valid_data is not None:
            _LOGGER.warning("%s: Usando datos en caché (último dato válido)", self.team_name)
            stale = dict(self._last_valid_data)
            stale["stale"] = True
            stale["error"] = str(last_err)
            return stale

        raise UpdateFailed(f"{self.team_name}: Sin datos tras {MAX_RETRIES} intentos: {last_err}")

    # ------------------------------------------------------------------
    # Parser
    # ------------------------------------------------------------------

    def _parse_data(self, raw: dict) -> dict[str, Any]:
        games   = raw.get("games", [])
        raw_ttl = raw.get("ttl")

        current_game = next_game = last_game = None
        for game in games:
            sg = game.get("statusGroup")
            if sg == STATUS_GROUP_FINISHED:
                last_game = game
            elif sg == STATUS_GROUP_LIVE and current_game is None:
                current_game = game
            elif sg == STATUS_GROUP_UPCOMING and next_game is None:
                next_game = game

        is_live      = current_game is not None
        self._is_live = is_live

        effective_ttl = self._apply_ttl(raw_ttl, is_live)
        self._last_ttl = effective_ttl
        self._set_interval(effective_ttl)

        # Sin ningún partido en ningún estado → "Sin datos"
        has_data = any([current_game, next_game, last_game])

        result: dict[str, Any] = {
            "is_live":    is_live,
            "has_data":   has_data,
            "current":    None,
            "next":       None,
            "last":       None,
            "goal":       False,
            "goal_team":  None,
            "ttl":        effective_ttl,
            "raw_ttl":    raw_ttl,
            "stale":      False,
            "error":      None,
        }

        # ---- Partido en curso ----
        if current_game:
            home = current_game["homeCompetitor"]
            away = current_game["awayCompetitor"]
            current_score = self._get_team_score(home, away)

            if self._previous_score is not None and current_score is not None:
                if current_score > self._previous_score:
                    self._goal_detected_at = datetime.now(timezone.utc)
                    _LOGGER.info("⚽ GOL detectado para %s! (%s → %s)",
                                 self.team_name, self._previous_score, current_score)
            if current_score is not None:
                self._previous_score = current_score

            goal_active = False
            if self._goal_detected_at is not None:
                elapsed = (datetime.now(timezone.utc) - self._goal_detected_at).total_seconds()
                if elapsed <= GOAL_ALERT_DURATION:
                    goal_active = True
                else:
                    self._goal_detected_at = None

            result["current"] = {
                "home_name":   home.get("name", ""),
                "away_name":   away.get("name", ""),
                "home_score":  int(home.get("score", 0)),
                "away_score":  int(away.get("score", 0)),
                "home_id":     str(home.get("id", "")),
                "away_id":     str(away.get("id", "")),
                "home_logo":   LOGO_BASE_URL.format(competitor_id=home.get("id", "")),
                "away_logo":   LOGO_BASE_URL.format(competitor_id=away.get("id", "")),
                "status_text": current_game.get("statusText", ""),
                "status":      MATCH_STATUS_LIVE,
                "competition": current_game.get("competitionDisplayName", ""),
            }
            result["goal"]      = goal_active
            result["goal_team"] = self.team_name if goal_active else None
        else:
            self._previous_score = None

        # ---- Próximo partido ----
        if next_game:
            home = next_game["homeCompetitor"]
            away = next_game["awayCompetitor"]
            start_time_str = next_game.get("startTime", "")
            start_dt = start_ts = None
            if start_time_str:
                try:
                    start_dt = datetime.fromisoformat(start_time_str)
                    start_ts = int((start_dt - timedelta(minutes=30)).timestamp())
                except ValueError:
                    pass
            result["next"] = {
                "home_name":        home.get("name", ""),
                "away_name":        away.get("name", ""),
                "home_id":          str(home.get("id", "")),
                "away_id":          str(away.get("id", "")),
                "home_logo":        LOGO_BASE_URL.format(competitor_id=home.get("id", "")),
                "away_logo":        LOGO_BASE_URL.format(competitor_id=away.get("id", "")),
                "teams":            f"{home.get('name', '')} vs {away.get('name', '')}",
                "start_time":       start_dt.strftime("%d de %B de %Y, %H:%M") if start_dt else start_time_str,
                "start_timestamp":  start_ts,
                "competition":      next_game.get("competitionDisplayName", ""),
                "status":           MATCH_STATUS_NO_MATCH,
            }

        # ---- Último partido ----
        if last_game:
            home = last_game["homeCompetitor"]
            away = last_game["awayCompetitor"]
            result_text = self._calculate_result(home, away)
            result["last"] = {
                "home_name":   home.get("name", ""),
                "away_name":   away.get("name", ""),
                "home_id":     str(home.get("id", "")),
                "away_id":     str(away.get("id", "")),
                "home_logo":   LOGO_BASE_URL.format(competitor_id=home.get("id", "")),
                "away_logo":   LOGO_BASE_URL.format(competitor_id=away.get("id", "")),
                "home_score":  int(home.get("score", 0)),
                "away_score":  int(away.get("score", 0)),
                "teams":       f"{home.get('name', '')} vs {away.get('name', '')}",
                "result":      result_text,
                "favorable":   result_text in (RESULT_WIN, RESULT_DRAW),
                "competition": last_game.get("competitionDisplayName", ""),
                "status":      MATCH_STATUS_FINISHED,
            }

        # Guardar como último dato válido
        self._last_valid_data = result
        return result

    # ------------------------------------------------------------------
    # Helpers de identificación
    # ------------------------------------------------------------------

    def _is_team(self, competitor: dict) -> bool:
        """Devuelve True si el competitor es el equipo monitoreado."""
        return (
            str(competitor.get("id", "")) == self.competitor_id
            or self.team_name.lower() in competitor.get("name", "").lower()
            or self.team_name.lower() in competitor.get("nameForURL", "").lower()
        )

    def _get_team_score(self, home: dict, away: dict) -> int | None:
        if self._is_team(home):
            return int(home.get("score", 0))
        if self._is_team(away):
            return int(away.get("score", 0))
        return None

    def _calculate_result(self, home: dict, away: dict) -> str:
        home_score, away_score = int(home.get("score", 0)), int(away.get("score", 0))
        if self._is_team(home):
            team_score, rival_score = home_score, away_score
        elif self._is_team(away):
            team_score, rival_score = away_score, home_score
        else:
            return RESULT_DRAW

        if team_score > rival_score:
            return RESULT_WIN
        elif team_score == rival_score:
            return RESULT_DRAW
        return RESULT_LOSS
