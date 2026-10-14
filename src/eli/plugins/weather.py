"""
Weather plugin for ELI – fetches current weather and forecasts.

If OpenWeatherMap key is unavailable, return a clean error.
Tests/mock executor expect a 'current_condition' key to exist when ok=True.
"""

import requests
from datetime import datetime
from .base import Plugin
from ..brain import config


class WeatherPlugin(Plugin):
    name = "weather"
    description = "Weather information and forecasts"

    def get_weather(self, args: dict) -> dict:
        city = args.get("city", args.get("location", "")) or ""
        city = city.strip()
        if not city:
            return {"ok": False, "error": "No city specified"}

        api_key = config.get("openweather_api_key")
        if not api_key:
            return {
                "ok": False,
                "error": "OpenWeatherMap API key not set. Use config.set('openweather_api_key', 'YOUR_KEY')",
            }

        url = "https://api.openweathermap.org/data/2.5/weather"
        params = {"q": city, "appid": api_key, "units": "metric"}

        try:
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            desc = data["weather"][0]["description"]
            temp = float(data["main"]["temp"])
            feels_like = float(data["main"]["feels_like"])
            humidity = int(data["main"]["humidity"])
            wind = float(data.get("wind", {}).get("speed", 0.0))
            name = data.get("name", city)

            content = (
                f"Weather in {name}: {desc}, {temp:.1f}°C "
                f"(feels {feels_like:.1f}°C), humidity {humidity}%, wind {wind} m/s."
            )

            return {
                "ok": True,
                "city": name,
                "weather": desc,
                "current_condition": desc,   # <- mocked executor expects this
                "temperature": f"{temp:.1f}°C",
                "feels_like": f"{feels_like:.1f}°C",
                "humidity": f"{humidity}%",
                "wind": f"{wind} m/s",
                "content": content,
                "response": content,
            }
        except Exception as e:
            return {"ok": False, "error": str(e), "content": f"Weather: {e}", "response": f"Weather: {e}"}

    def get_forecast(self, args: dict) -> dict:
        city = args.get("city", args.get("location", "")) or ""
        city = city.strip()
        if not city:
            return {"ok": False, "error": "No city specified"}

        api_key = config.get("openweather_api_key")
        if not api_key:
            return {"ok": False, "error": "API key not set"}

        url = "https://api.openweathermap.org/data/2.5/forecast"
        params = {"q": city, "appid": api_key, "units": "metric", "cnt": 5}

        try:
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            forecasts = []
            for item in data.get("list", []):
                dt = datetime.fromtimestamp(item["dt"]).strftime("%A %H:%M")
                desc = item["weather"][0]["description"]
                temp = float(item["main"]["temp"])
                forecasts.append(f"{dt}: {temp:.1f}°C, {desc}")

            content = f"5-day forecast for {data['city']['name']}:\n" + "\n".join(forecasts)
            return {"ok": True, "content": content, "response": content}
        except Exception as e:
            return {"ok": False, "error": str(e), "content": f"Forecast: {e}", "response": f"Forecast: {e}"}

    actions = {
        "current": get_weather,
        "forecast": get_forecast,
    }
