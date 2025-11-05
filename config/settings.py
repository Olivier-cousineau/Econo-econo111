from typing import List
from pydantic_settings import BaseSettings
from pydantic import Field
import json


class Settings(BaseSettings):
    bestbuy_user_agents: List[str] = Field(default_factory=lambda: ["Mozilla/5.0"])

    def model_post_init(self, __context):
        """Convertit automatiquement une chaîne CSV ou JSON en liste."""
        raw_value = getattr(self, "bestbuy_user_agents", None)
        if isinstance(raw_value, str):
            try:
                # Essaye de décoder en JSON d'abord
                self.bestbuy_user_agents = json.loads(raw_value)
            except json.JSONDecodeError:
                # Sinon, traite comme liste CSV
                self.bestbuy_user_agents = [
                    ua.strip() for ua in raw_value.split(",") if ua.strip()
                ]
        # Si vide, garde la valeur par défaut
        if not self.bestbuy_user_agents:
            self.bestbuy_user_agents = ["Mozilla/5.0"]


def get_settings():
    """Retourne les paramètres globaux avec fallback sûr."""
    return Settings()
