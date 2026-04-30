"""Coordinator para 365Scores - polling dinámico con TTL, retry y backoff."""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    API_BASE_URL,
    API_GAME_URL,
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
    PRE_MATCH_WINDOW,
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

# Modos de polling — usados en el sensor de diagnóstico
POLL_MODE_IDLE       = "Sin partido"
POLL_MODE_PRE_MATCH  = "Pre-partido (30s)"
POLL_MODE_LIVE       = "Partido en curso"
POLL_MODE_LIVE_GAME  = "Partido en curso (URL directa)"
POLL_MODE_BACKOFF    = "Error — backoff"
POLL_MODE_WAKEUP     = "Alarma pre-partido"


class Scores365Coordinator(DataUpdateCoordinator):
    """Coordinator con TTL dinámico, alarma exacta pre-partido y sensor de modo."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.competitor_id  = entry.data[CONF_COMPETITOR_ID]
        self.team_name      = entry.data[CONF_TEAM_NAME]
        self.team_logo_url  = LOGO_BASE_URL.format(competitor_id=self.competitor_id)

        # Estado interno
        self._previous_score: int | None        = None
        self._goal_detected_at: datetime | None = None
        self._is_live: bool                     = False
        self._last_ttl: int                     = TTL_DEFAULT
        self._consecutive_errors: int           = 0
        self._last_valid_data: dict | None      = None
        self._current_game_id: str | None       = None
        self._next_start_time: datetime | None  = None
        self._wakeup_handle: asyncio.TimerHandle | None = None
        self._wakeup_scheduled_for: datetime | None     = None

        # Modo de polling actual — expuesto en sensor de diagnóstico
        self.poll_mode: str = POLL_MODE_IDLE

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{self.competitor_id}",
            update_interval=timedelta(seconds=TTL_DEFAULT),
        )

    # ------------------------------------------------------------------
    # Alarma pre-partido
    # ------------------------------------------------------------------

    def _schedule_pre_match_wakeup(self, start_dt: datetime) -> None:
        """Programa una alarma exacta PRE_MATCH_WINDOW segundos antes del partido."""
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=timezone.utc)

        wakeup_at = start_dt - timedelta(seconds=PRE_MATCH_WINDOW)
        now = datetime.now(timezone.utc)
        delay = (wakeup_at - now).total_seconds()

        # Si ya pasó la ventana o el partido ya inició, no programar
        if delay <= 0:
            return

        # Si ya hay una alarma programada para la misma hora, no reprogramar
        if (self._wakeup_scheduled_for is not None
                and abs((self._wakeup_scheduled_for - wakeup_at).total_seconds()) < 5):
            return

        # Cancelar alarma anterior si existe
        self._cancel_wakeup()

        _LOGGER.debug(
            "%s: Alarma pre-partido programada en %.0fs (a las %s)",
            self.team_name, delay, wakeup_at.strftime("%H:%M:%S"),
        )

        self._wakeup_handle = self.hass.loop.call_later(
            delay, self._on_pre_match_wakeup
        )
        self._wakeup_scheduled_for = wakeup_at

    def _cancel_wakeup(self) -> None:
        """Cancela la alarma pre-partido si existe."""
        if self._wakeup_handle is not None:
            self._wakeup_handle.cancel()
            self._wakeup_handle = None
            self._wakeup_scheduled_for = None

    @callback
    def _on_pre_match_wakeup(self) -> None:
        """Callback cuando la alarma pre-partido se dispara."""
        self._wakeup_handle = None
        self._wakeup_scheduled_for = None
        _LOGGER.debug("%s: ⏰ Alarma pre-partido disparada — activando TTL 1s", self.team_name)
        self.poll_mode = POLL_MODE_WAKEUP
        self._set_interval(1)
        # Forzar refresh inmediato
        self.hass.async_create_task(self.async_refresh())

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
        delay = min(RETRY_BACKOFF_BASE * (2 ** (self._consecutive_errors - 1)),
                    RETRY_BACKOFF_MAX)
        _LOGGER.warning("%s: Error consecutivo #%s, reintentando en %ss",
                        self.team_name, self._consecutive_errors, delay)
        return delay

    def _check_pre_match_window(self) -> bool:
        """True si estamos en la ventana de PRE_MATCH_WINDOW segundos antes del partido."""
        if self._next_start_time is None:
            return False
        now = datetime.now(timezone.utc)
        nst = self._next_start_time
        if nst.tzinfo is None:
            nst = nst.replace(tzinfo=timezone.utc)
        seconds_until = (nst - now).total_seconds()
        return 0 <= seconds_until <= PRE_MATCH_WINDOW

    # ------------------------------------------------------------------
    # Fetch con retry
    # ------------------------------------------------------------------

    async def _async_update_data(self) -> dict[str, Any]:
        timestamp = int(time.time())

        # Determinar modo de polling y URL
        if self._is_live and self._current_game_id:
            url = API_GAME_URL
            params = {**API_PARAMS, "gameId": self._current_game_id, "timestamp": timestamp}
            self.poll_mode = POLL_MODE_LIVE_GAME
            _LOGGER.debug("%s: Polling gameId=%s", self.team_name, self._current_game_id)

        elif not self._is_live and self._check_pre_match_window():
            # Ventana pre-partido activa (llegamos aquí via alarma o polling normal)
            url = API_BASE_URL
            params = {**API_PARAMS, "competitors": self.competitor_id, "timestamp": timestamp}
            self.poll_mode = POLL_MODE_PRE_MATCH
            self._set_interval(1)
            _LOGGER.debug("%s: Polling pre-partido (ventana 30s)", self.team_name)

        else:
            url = API_BASE_URL
            params = {**API_PARAMS, "competitors": self.competitor_id, "timestamp": timestamp}
            self.poll_mode = POLL_MODE_IDLE

        last_err: Exception | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        url, params=params, timeout=aiohttp.ClientTimeout(total=10)
                    ) as response:
                        response.raise_for_status()
                        raw = await response.json(content_type=None)

                self._consecutive_errors = 0
                return self._parse_data(raw)

            except (aiohttp.ClientError, asyncio.TimeoutError) as err:
                last_err = err
                if attempt < MAX_RETRIES:
                    _LOGGER.debug("%s: Intento %s/%s falló (%s), reintentando…",
                                  self.team_name, attempt, MAX_RETRIES, err)
                    await asyncio.sleep(2 * attempt)
            except Exception as err:
                last_err = err
                break

        self._consecutive_errors += 1
        self.poll_mode = POLL_MODE_BACKOFF
        backoff = self._backoff_interval()
        self._set_interval(backoff)

        if self._last_valid_data is not None:
            _LOGGER.warning("%s: Usando datos en caché", self.team_name)
            stale = dict(self._last_valid_data)
            stale["stale"] = True
            stale["error"] = str(last_err)
            stale["poll_mode"] = self.poll_mode
            return stale

        raise UpdateFailed(f"{self.team_name}: Sin datos tras {MAX_RETRIES} intentos: {last_err}")

    # ------------------------------------------------------------------
    # Parser
    # ------------------------------------------------------------------

    def _parse_data(self, raw: dict) -> dict[str, Any]:
        if "game" in raw and "games" not in raw:
            games = [raw["game"]]
        else:
            games = raw.get("games", [])

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

        is_live       = current_game is not None
        self._is_live = is_live

        # Guardar game_id
        if current_game:
            self._current_game_id = str(current_game.get("id", ""))
        else:
            self._current_game_id = None

        # Gestionar startTime y alarma pre-partido
        if next_game and not is_live:
            try:
                st = next_game.get("startTime", "")
                if st:
                    new_start = datetime.fromisoformat(st)
                    # Reprogramar alarma solo si cambió la hora del partido
                    if (self._next_start_time is None
                            or abs((new_start - self._next_start_time).total_seconds()) > 5):
                        self._next_start_time = new_start
                        self._schedule_pre_match_wakeup(new_start)
            except ValueError:
                self._next_start_time = None
        elif is_live:
            # Partido ya inició — cancelar alarma y resetear
            self._cancel_wakeup()
            self._next_start_time = None

        # Actualizar modo de polling
        if is_live:
            self.poll_mode = POLL_MODE_LIVE_GAME if self._current_game_id else POLL_MODE_LIVE
        elif self._check_pre_match_window():
            self.poll_mode = POLL_MODE_PRE_MATCH

        # TTL normal (no sobreescribe si estamos en pre-partido o backoff)
        if self.poll_mode not in (POLL_MODE_PRE_MATCH, POLL_MODE_WAKEUP, POLL_MODE_BACKOFF):
            effective_ttl = self._apply_ttl(raw_ttl, is_live)
            self._last_ttl = effective_ttl
            self._set_interval(effective_ttl)
        else:
            effective_ttl = int(self.update_interval.total_seconds())

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
            "game_id":    self._current_game_id,
            "poll_mode":  self.poll_mode,
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
                "game_id":     str(current_game.get("id", "")),
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
            start_dt = None
            start_datetime_5min = None
            if start_time_str:
                try:
                    start_dt = datetime.fromisoformat(start_time_str)
                    start_datetime_5min = start_dt - timedelta(minutes=5)
                    if start_datetime_5min.tzinfo is None:
                        from homeassistant.util import dt as dt_util
                        start_datetime_5min = dt_util.as_local(start_datetime_5min)
                except ValueError:
                    pass
            result["next"] = {
                "home_name":           home.get("name", ""),
                "away_name":           away.get("name", ""),
                "home_id":             str(home.get("id", "")),
                "away_id":             str(away.get("id", "")),
                "home_logo":           LOGO_BASE_URL.format(competitor_id=home.get("id", "")),
                "away_logo":           LOGO_BASE_URL.format(competitor_id=away.get("id", "")),
                "teams":               f"{home.get('name', '')} vs {away.get('name', '')}",
                "start_time":          start_dt.strftime("%d de %B de %Y, %H:%M") if start_dt else start_time_str,
                "start_datetime_5min": start_datetime_5min,
                "competition":         next_game.get("competitionDisplayName", ""),
                "status":              MATCH_STATUS_NO_MATCH,
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

        self._last_valid_data = result
        return result

    # ------------------------------------------------------------------
    # Helpers de identificación
    # ------------------------------------------------------------------

    def _is_team(self, competitor: dict) -> bool:
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
