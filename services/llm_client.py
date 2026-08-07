"""OpenAI-compatible chat completion adapter."""

from openai import OpenAI

from utils.config import Settings


class LLMClient:
    """Small adapter that keeps provider-specific code outside the workflow."""

    def __init__(self, settings: Settings | None = None) -> None:
        """Initialize an OpenAI-compatible client from environment settings."""
        self.settings = settings or Settings.from_env()
        self._client = OpenAI(
            api_key=self.settings.api_key or "missing-api-key",
            base_url=self.settings.base_url,
        )

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        """Generate markdown analysis using the configured chat model."""
        if not self.settings.api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured. Copy .env.example to .env.")

        response = self._client.chat.completions.create(
            model=self.settings.model,
            temperature=0.2,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        content = response.choices[0].message.content
        if not content:
            raise RuntimeError("The LLM returned an empty response.")
        return content
