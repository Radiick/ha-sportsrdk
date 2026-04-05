"""Constantes para la integración 365Scores."""

DOMAIN = "scores365"
PLATFORMS = ["sensor", "binary_sensor"]

# Config keys
CONF_COMPETITOR_ID = "competitor_id"
CONF_TEAM_NAME = "team_name"
CONF_LEAGUE_NAME = "league_name"

# API
API_BASE_URL = "https://webws.365scores.com/web/games/current/"
API_PARAMS = {
    "appTypeId": "5",
    "langId": "29",
    "timezoneName": "America/Mexico_City",
    "userCountryId": "31",
}

# Polling intervals (segundos)
SCAN_INTERVAL_LIVE = 10       # Partido en curso
SCAN_INTERVAL_IDLE = 120      # Sin partido

# Status groups de la API
STATUS_GROUP_FINISHED = 4
STATUS_GROUP_LIVE = 3
STATUS_GROUP_UPCOMING = 2

# Sensor names
SENSOR_SCORE_HOME = "marcador_local"
SENSOR_SCORE_AWAY = "marcador_visitante"
SENSOR_TEAM_HOME = "equipo_local"
SENSOR_TEAM_AWAY = "equipo_visitante"
SENSOR_MATCH_TIME = "minuto_partido"
SENSOR_MATCH_STATUS = "estado_partido"
SENSOR_NEXT_MATCH = "proximo_partido"
SENSOR_NEXT_MATCH_TIME = "fecha_proximo_partido"
SENSOR_LAST_SCORE_HOME = "ultimo_marcador_local"
SENSOR_LAST_SCORE_AWAY = "ultimo_marcador_visitante"
SENSOR_LAST_RESULT = "ultimo_resultado"
SENSOR_LAST_TEAMS = "ultimo_enfrentamiento"

# Binary sensor names
BINARY_SENSOR_LIVE = "partido_en_curso"
BINARY_SENSOR_GOAL = "gol"
BINARY_SENSOR_FAVORABLE = "resultado_favorable"

# Estados del partido
MATCH_STATUS_LIVE = "En curso"
MATCH_STATUS_NO_MATCH = "Sin partido"
MATCH_STATUS_FINISHED = "Finalizado"

# Resultados
RESULT_WIN = "Ganó"
RESULT_DRAW = "Empató"
RESULT_LOSS = "Perdió"

# Goal alert duration (segundos)
GOAL_ALERT_DURATION = 30
