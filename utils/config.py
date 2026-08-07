"""Environment-backed application settings."""

from dataclasses import dataclass
import os

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    """Runtime settings for an OpenAI-compatible provider."""

    api_key: str
    base_url: str
    model: str

    @classmethod
    def from_env(cls) -> "Settings":
        """Load settings from a local .env file and process environment."""
        load_dotenv()
        return cls(
            api_key=os.getenv("OPENAI_API_KEY", "").strip(),
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip(),
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip(),
        )
