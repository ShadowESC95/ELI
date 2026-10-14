"""
Free weather plugin for ELI using wttr.in (no API key needed)
"""

import requests
from typing import Dict, Any
import re

class FreeWeatherPlugin:
    """Weather plugin using wttr.in - completely free, no API key"""
    
    name = "weather"
    description = "Weather information using wttr.in"
    
    def get_weather(self, args: dict) -> dict:
        """Get current weather for a city using wttr.in"""
        try:
            location = args.get("location", args.get("city", ""))
            if not location:
                return {"ok": False, "error": "No location specified"}
            
            # Use wttr.in API (free, no key needed)
            url = f"http://wttr.in/{location}?format=j1"
            
            response = requests.get(url, timeout=15)
            response.raise_for_status()
            data = response.json()
            
            # Parse the response
            current = data['current_condition'][0]
            area = data['nearest_area'][0]
            
            location_name = area['areaName'][0]['value']
            country = area['country'][0]['value']
            temp_c = current['temp_C']
            feels_like = current['FeelsLikeC']
            weather_desc = current['weatherDesc'][0]['value']
            humidity = current['humidity']
            wind_speed = current['windspeedKmph']
            wind_dir = current['winddir16Point']
            
            content = (
                f"Weather in {location_name}, {country}:\n"
                f"🌡️ Temperature: {temp_c}°C (feels like {feels_like}°C)\n"
                f"☁️ Conditions: {weather_desc}\n"
                f"💧 Humidity: {humidity}%\n"
                f"💨 Wind: {wind_speed} km/h {wind_dir}"
            )
            
            return {
                "ok": True,
                "location": f"{location_name}, {country}",
                "temperature": f"{temp_c}°C",
                "feels_like": f"{feels_like}°C",
                "weather": weather_desc,
                "humidity": f"{humidity}%",
                "wind": f"{wind_speed} km/h {wind_dir}",
                "content": content,
                "response": content
            }
            
        except requests.exceptions.RequestException as e:
            return {"ok": False, "error": f"Network error: {str(e)}"}
        except (KeyError, IndexError) as e:
            return {"ok": False, "error": f"Could not parse weather data: {str(e)}"}
        except Exception as e:
            return {"ok": False, "error": f"Weather error: {str(e)}"}
    
    def get_forecast(self, args: dict) -> dict:
        """Get 3-day forecast using wttr.in"""
        try:
            location = args.get("location", args.get("city", ""))
            if not location:
                return {"ok": False, "error": "No location specified"}
            
            # Use wttr.in API
            url = f"http://wttr.in/{location}?format=j1"
            
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            forecasts = []
            for day in data['weather'][:3]:  # 3 days
                date = day['date']
                max_temp = day['maxtempC']
                min_temp = day['mintempC']
                desc = day['hourly'][4]['weatherDesc'][0]['value']  # Midday weather
                
                forecasts.append(f"📅 {date}: {min_temp}-{max_temp}°C, {desc}")
            
            area = data['nearest_area'][0]
            location_name = area['areaName'][0]['value']
            
            content = f"3-day forecast for {location_name}:\n" + "\n".join(forecasts)
            
            return {
                "ok": True,
                "content": content,
                "response": content
            }
            
        except Exception as e:
            return {"ok": False, "error": f"Forecast error: {str(e)}"}
    
    actions = {
        "current": get_weather,
        "forecast": get_forecast
    }
