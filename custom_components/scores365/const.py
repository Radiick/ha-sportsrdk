"""Constantes para la integración 365Scores."""

DOMAIN = "scores365"
PLATFORMS = ["sensor", "binary_sensor", "switch", "number"]

# Config keys
CONF_COMPETITOR_ID = "competitor_id"
CONF_TEAM_NAME     = "team_name"
CONF_LEAGUE_NAME   = "league_name"

# API
API_BASE_URL = "https://webws.365scores.com/web/games/current/"
API_PARAMS = {
    "appTypeId": "5",
    "langId": "29",
    "timezoneName": "America/Mexico_City",
    "userCountryId": "31",
}

# Logo URL con fallback de imagen por defecto
LOGO_BASE_URL = (
    "https://imagecache.365scores.com/image/upload/"
    "f_png,w_80,h_80,c_limit,q_auto:eco,dpr_2,d_Competitors:default1.png"
    "/v5/Competitors/{competitor_id}"
)

# Polling TTL — límites para el valor dinámico que devuelve la API
TTL_FLOOR_LIVE   = 5    # Mínimo en partido en curso
TTL_CEILING_LIVE = 30   # Máximo en partido en curso
TTL_FLOOR_IDLE   = 30   # Mínimo sin partido
TTL_CEILING_IDLE = 300  # Máximo sin partido (5 min)
TTL_DEFAULT      = 60   # Fallback si la API no devuelve ttl

# Reintentos en caso de error de red
MAX_RETRIES        = 3
RETRY_BACKOFF_BASE = 10
RETRY_BACKOFF_MAX  = 300

# Status groups de la API
STATUS_GROUP_FINISHED = 4
STATUS_GROUP_LIVE     = 3
STATUS_GROUP_UPCOMING = 2

# Estados del partido
MATCH_STATUS_LIVE     = "En curso"
MATCH_STATUS_NO_MATCH = "Sin partido"
MATCH_STATUS_FINISHED = "Finalizado"
MATCH_STATUS_NO_DATA  = "Sin datos"

# Resultados
RESULT_WIN  = "Ganó"
RESULT_DRAW = "Empató"
RESULT_LOSS = "Perdió"

# Goal alert duration (segundos)
GOAL_ALERT_DURATION = 30

# Switch keys — eventos por equipo
SWITCH_EVENTO_GLOBAL         = "evento_global"
SWITCH_EVENTO_PREVIO_PARTIDO = "evento_previo_partido"
SWITCH_EVENTO_PARTIDO_INICIA = "evento_partido_inicia"   # cubre todos los cambios de tiempo
SWITCH_EVENTO_GOL            = "evento_gol"
SWITCH_EVENTO_EQUIPO_GANA    = "evento_equipo_gana"

# Todos los switches dependientes del global
SWITCHES_DEPENDIENTES = [
    SWITCH_EVENTO_PREVIO_PARTIDO,
    SWITCH_EVENTO_PARTIDO_INICIA,
    SWITCH_EVENTO_GOL,
    SWITCH_EVENTO_EQUIPO_GANA,
]

# Number keys
NUMBER_DELAY = "delay_automatizacion"

# Delay slider
DELAY_MIN     = 0
DELAY_MAX     = 60
DELAY_STEP    = 1
DELAY_DEFAULT = 0
