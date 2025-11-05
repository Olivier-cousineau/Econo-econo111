from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # Chaîne simple — pas de JSON
    bestbuy_user_agents: str = Field(default="Mozilla/5.0")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


def get_settings():
    """Retourne les paramètres globaux sans jamais planter."""
    try:
        return Settings()
    except Exception:
        # Sécurité : si la variable est manquante ou invalide
        return Settings(bestbuy_user_agents="Mozilla/5.0")
