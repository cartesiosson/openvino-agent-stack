"""
title: Weather (Open-Meteo)
author: agent-stack
version: 0.1.0
description: Tiempo actual de una ciudad, sin API key (Open-Meteo).
required_open_webui_version: 0.5.0
"""

import httpx
from pydantic import BaseModel, Field


class Tools:
    class Valves(BaseModel):
        timeout: int = Field(default=10, description="Timeout en segundos")
        language: str = Field(default="es", description="Idioma de los resultados de geocoding")

    def __init__(self):
        self.valves = self.Valves()

    def get_weather(self, city: str) -> str:
        """
        Devuelve el tiempo actual de una ciudad usando Open-Meteo.

        :param city: nombre de la ciudad, p.ej. "Madrid" o "Barcelona, ES"
        :return: temperatura, viento y código de tiempo
        """
        try:
            with httpx.Client(timeout=self.valves.timeout) as c:
                geo = c.get(
                    "https://geocoding-api.open-meteo.com/v1/search",
                    params={"name": city, "count": 1, "language": self.valves.language},
                ).json()
                results = geo.get("results") or []
                if not results:
                    return f"no encontré '{city}'"
                loc = results[0]
                lat, lon, name = loc["latitude"], loc["longitude"], loc["name"]

                w = c.get(
                    "https://api.open-meteo.com/v1/forecast",
                    params={
                        "latitude": lat,
                        "longitude": lon,
                        "current": "temperature_2m,wind_speed_10m,weather_code",
                    },
                ).json()
                cur = w.get("current", {})
                return (
                    f"{name}: {cur.get('temperature_2m')}°C, "
                    f"viento {cur.get('wind_speed_10m')} km/h, "
                    f"código meteo {cur.get('weather_code')}"
                )
        except Exception as e:
            return f"error: {e}"
