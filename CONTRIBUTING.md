# Contributing

Thanks for helping improve Resume Agent MVP.

## Local Setup

```bash
uv sync
copy .env.example .env
uv run python -m app.main
```

Never commit `.env` or API keys. Use `.env.example` for configuration changes.

## Code Guidelines

- Keep the single-page scope and avoid unrelated product features.
- Keep workflow nodes independent with explicit input and output contracts.
- Keep prompts in `prompt/` instead of embedding large prompts in Python.
- Keep provider-specific logic behind `services/llm_client.py`.
- Add a focused test or reproducible verification for behavior changes.
- Use clear docstrings for public functions and classes.

## Pull Requests

1. Describe the user-visible or workflow behavior change.
2. Explain how it was verified.
3. Include screenshots for UI changes.
4. Call out new environment variables or knowledge files.
5. Keep commits focused and avoid committing generated files.
