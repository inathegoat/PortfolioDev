import requests
import logging
from src.tools.base import BaseTool, PERMISSION_READ_ONLY

logger = logging.getLogger(__name__)

class WeatherTool(BaseTool):
    """
    Outil pour obtenir la météo actuelle d'une ville via Open-Meteo (gratuit, pas de clé API).
    """
    name = "get_weather"
    description = "Obtenir la météo actuelle (température, vent) pour une ville donnée."
    permission_level = PERMISSION_READ_ONLY

    def schema(self) -> dict:
        return {
            "city": {
                "type": "string",
                "required": True,
                "description": "Le nom de la ville (ex: Paris, Tokyo)",
            }
        }

    def execute(self, city: str = "", **kwargs) -> dict:
        if not city:
            return {"status": "error", "message": "Le nom de la ville est requis."}

        try:
            # 1. Geocoding pour trouver les coordonnées de la ville
            geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1&language=fr"
            geo_resp = requests.get(geo_url, timeout=10)
            geo_data = geo_resp.json()

            if not geo_data.get("results"):
                return {"status": "error", "message": f"Impossible de trouver la ville '{city}'."}

            location = geo_data["results"][0]
            lat = location["latitude"]
            lon = location["longitude"]
            country = location.get("country", "")

            # 2. Obtenir la météo
            weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
            weather_resp = requests.get(weather_url, timeout=10)
            weather_data = weather_resp.json()
            
            current = weather_data.get("current_weather", {})
            temp = current.get("temperature")
            wind = current.get("windspeed")
            
            return {
                "status": "success",
                "message": f"Météo récupérée pour {city}, {country}.",
                "details": f"Température: {temp}°C, Vent: {wind} km/h.",
            }

        except Exception as e:
            logger.error(f"Weather plugin error: {e}")
            return {"status": "error", "message": f"Erreur de connexion à l'API météo: {e}"}
