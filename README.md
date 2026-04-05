# 365Scores — Fútbol en vivo para Home Assistant

Integración para Home Assistant que muestra información en tiempo real de partidos de fútbol usando la API de 365Scores. Puedes agregar múltiples equipos, cada uno aparece como un **device independiente** con sus propias entidades.

---

## Características

- ✅ Partido en curso: marcador, minuto, equipos
- ✅ Próximo partido: equipos, fecha, timestamp (-30 min para automatizaciones)
- ✅ Último partido: resultado, marcador final
- ✅ Binary sensor de Gol (activo 30 segundos tras detectar el gol)
- ✅ Polling adaptativo: cada 10s en partido, cada 2 min sin partido
- ✅ Múltiples equipos → cada uno es un device distinto
- ✅ Config Flow con UI (sin editar YAML)

---

## Instalación con HACS

1. En Home Assistant, ve a **HACS → Integraciones → ⋮ → Repositorios personalizados**
2. Agrega la URL de este repositorio y selecciona tipo **Integración**
3. Busca `365Scores` e instala
4. Reinicia Home Assistant
5. Ve a **Ajustes → Dispositivos y servicios → + Agregar integración**
6. Busca `365Scores` y sigue el asistente

---

## Instalación manual

Copia la carpeta `custom_components/scores365` en tu carpeta `custom_components` de Home Assistant y reinicia.

---

## Cómo encontrar el Competitor ID

1. Ve a [365scores.com](https://www.365scores.com)
2. Busca tu equipo y entra a su página
3. El número en la URL es el ID. Ejemplo:
   ```
   https://www.365scores.com/es-mx/football/team/club-america-1255
   ```
   → El ID es **1255**

### IDs de equipos de Liga MX (referencia)

| Equipo | ID |
|---|---|
| Club América | 1255 |
| Chivas Guadalajara | 5106 |
| Cruz Azul | 1262 |
| Pumas UNAM | 1261 |
| Tigres UANL | 1264 |
| Monterrey | 1263 |
| Atlas | 1258 |
| León | 1259 |
| Toluca | 1260 |
| Santos Laguna | 1265 |

---

## Entidades creadas por equipo

### Sensores (`sensor`)

| Entidad | Descripción |
|---|---|
| `sensor.[equipo]_marcador_local` | Goles del equipo local |
| `sensor.[equipo]_marcador_visitante` | Goles del equipo visitante |
| `sensor.[equipo]_equipo_local` | Nombre equipo local |
| `sensor.[equipo]_equipo_visitante` | Nombre equipo visitante |
| `sensor.[equipo]_minuto_partido` | Minuto actual (ej: "67'") |
| `sensor.[equipo]_estado_partido` | "En curso" / "Sin partido" |
| `sensor.[equipo]_competicion` | Nombre de la competición |
| `sensor.[equipo]_proximo_equipos` | "América vs Cruz Azul" |
| `sensor.[equipo]_proximo_fecha` | Fecha y hora del próximo partido |
| `sensor.[equipo]_proximo_timestamp` | Unix timestamp (30 min antes del partido) |
| `sensor.[equipo]_ultimo_equipos` | Equipos del último partido |
| `sensor.[equipo]_ultimo_marcador` | Marcador final del último partido |
| `sensor.[equipo]_ultimo_resultado` | "Ganó" / "Empató" / "Perdió" |

### Binary Sensors

| Entidad | Descripción |
|---|---|
| `binary_sensor.[equipo]_partido_en_curso` | `on` si hay partido en vivo |
| `binary_sensor.[equipo]_gol` | `on` durante 30s tras detectar un gol |
| `binary_sensor.[equipo]_resultado_favorable` | `on` si el último resultado fue victoria o empate |

---

## Ejemplos de automatizaciones

### Notificación de gol
```yaml
automation:
  - alias: "Notificar gol del América"
    trigger:
      - platform: state
        entity_id: binary_sensor.america_gol
        to: "on"
    action:
      - service: notify.mobile_app
        data:
          title: "⚽ ¡GOL!"
          message: >
            ¡Gol del {{ states('sensor.america_equipo_local') }}!
            Marcador: {{ states('sensor.america_marcador_local') }} - {{ states('sensor.america_marcador_visitante') }}
```

### Alerta antes del partido
```yaml
automation:
  - alias: "Avisar 30 min antes del partido"
    trigger:
      - platform: template
        value_template: >
          {{ as_timestamp(now()) | int >= states('sensor.america_proximo_timestamp') | int }}
    condition:
      - condition: state
        entity_id: binary_sensor.america_partido_en_curso
        state: "off"
    action:
      - service: notify.mobile_app
        data:
          title: "🏟️ Partido en 30 minutos"
          message: "{{ states('sensor.america_proximo_equipos') }}"
```

---

## Notas

- La API de 365Scores es pública pero no oficial. Puede cambiar sin previo aviso.
- El polling se hace cada 10 segundos durante un partido en vivo.
- Esta integración es solo para fútbol.
