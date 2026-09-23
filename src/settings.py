"""Environment loading and validation.

Every credential and tuning value is validated at startup. A run that is going
to fail on a missing key must fail before it spends anything, not halfway
through the paid stages.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"


def _load_env_file(path: Path) -> None:
    """Minimal .env loader. Real environment variables always win, so GitHub
    Actions secrets override the local file rather than the other way round."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


class ConfigError(RuntimeError):
    """Raised when the environment is not usable. Always fatal."""


@dataclass(frozen=True)
class Settings:
    apify_token: str
    openrouter_api_key: str
    cerebras_api_key: str
    groq_api_key: str
    discord_webhook_url: str
    daily_budget_usd: float
    score_gate: int
    posted_limit: str
    writer_provider: str
    writer_model: str
    scorer_provider: str
    scorer_model: str
    dry_run: bool

    @property
    def redacted(self) -> dict[str, str]:
        """Safe-to-log view. Never log the dataclass itself."""
        def mask(secret: str) -> str:
            if len(secret) <= 8:
                return "***"
            return f"{secret[:6]}…{secret[-4:]}"
        return {
            "apify_token": mask(self.apify_token),
            "openrouter_api_key": mask(self.openrouter_api_key),
            "cerebras_api_key": mask(self.cerebras_api_key) if self.cerebras_api_key else "(unset)",
            "groq_api_key": mask(self.groq_api_key) if self.groq_api_key else "(unset)",
            "discord_webhook_url": mask(self.discord_webhook_url),
            "daily_budget_usd": f"${self.daily_budget_usd:.2f}",
            "score_gate": str(self.score_gate),
            "posted_limit": self.posted_limit,
            "writer": f"{self.writer_provider}/{self.writer_model}",
            "scorer": f"{self.scorer_provider}/{self.scorer_model}",
            "dry_run": str(self.dry_run),
        }


_PLACEHOLDERS = {
    "apify_api_your_token_here",
    "your_mistral_key_here",
    "sk-or-v1-your_key_here",
    "csk-your_key_here",
    "https://discord.com/api/webhooks/000/xxx",
}

VALID_POSTED_LIMITS = {"1h", "24h", "week", "month"}


def _require(name: str) -> str:
    value = (os.environ.get(name) or "").strip()
    if not value:
        raise ConfigError(
            f"{name} is not set. Add it to {ENV_PATH} (or set it as a GitHub "
            f"Actions secret) and run again."
        )
    if value in _PLACEHOLDERS:
        raise ConfigError(
            f"{name} still holds the placeholder value from .env.example. "
            f"Replace it with your real credential in {ENV_PATH}."
        )
    return value


def load_settings() -> Settings:
    _load_env_file(ENV_PATH)

    apify_token = _require("APIFY_TOKEN")
    openrouter_api_key = _require("OPENROUTER_API_KEY")
    cerebras_api_key = (os.environ.get("CEREBRAS_API_KEY") or "").strip()
    groq_api_key = (os.environ.get("GROQ_API_KEY") or "").strip()
    discord_webhook_url = _require("DISCORD_WEBHOOK_URL")

    # Shape checks catch the common paste errors (wrong key in the wrong slot,
    # truncated copy) before any network call is made.
    if not apify_token.startswith("apify_api_"):
        raise ConfigError(
            "APIFY_TOKEN does not start with 'apify_api_'. Copy the Personal "
            "API token from Apify Console -> Settings -> API & Integrations."
        )
    if not discord_webhook_url.startswith("https://discord.com/api/webhooks/"):
        raise ConfigError(
            "DISCORD_WEBHOOK_URL must start with "
            "'https://discord.com/api/webhooks/'. Copy it from "
            "Channel -> Edit Channel -> Integrations -> Webhooks."
        )
    if not openrouter_api_key.startswith("sk-or-"):
        raise ConfigError(
            "OPENROUTER_API_KEY should start with 'sk-or-'. Create one at "
            "openrouter.ai -> Keys. Remember to also enable 'Free model "
            "publication' at openrouter.ai/settings/privacy, or free models "
            "return 404."
        )
    # Cerebras and Groq are optional fallbacks. A wrong-looking key is worth
    # flagging, but a missing one just means that provider is skipped.
    if cerebras_api_key and not cerebras_api_key.startswith("csk-"):
        raise ConfigError("CEREBRAS_API_KEY should start with 'csk-'.")
    if groq_api_key and not groq_api_key.startswith("gsk_"):
        raise ConfigError("GROQ_API_KEY should start with 'gsk_'.")

    try:
        daily_budget = float(os.environ.get("DAILY_BUDGET_USD", "1.00"))
    except ValueError as exc:
        raise ConfigError("DAILY_BUDGET_USD must be a number, e.g. 0.50") from exc
    if daily_budget <= 0:
        raise ConfigError("DAILY_BUDGET_USD must be greater than 0.")
    if daily_budget > 5:
        raise ConfigError(
            f"DAILY_BUDGET_USD is ${daily_budget:.2f}, which is far above the "
            "agreed $0.50/day cap. Refusing to run as a safeguard against a "
            "typo draining the Apify balance. Edit .env deliberately to change."
        )

    try:
        score_gate = int(os.environ.get("SCORE_GATE", "55"))
    except ValueError as exc:
        raise ConfigError("SCORE_GATE must be a whole number, e.g. 55") from exc
    if not 0 <= score_gate <= 100:
        raise ConfigError("SCORE_GATE must be between 0 and 100.")

    posted_limit = os.environ.get("POSTED_LIMIT", "24h").strip()
    if posted_limit not in VALID_POSTED_LIMITS:
        raise ConfigError(
            f"POSTED_LIMIT must be one of {sorted(VALID_POSTED_LIMITS)}, "
            f"got {posted_limit!r}."
        )

    return Settings(
        apify_token=apify_token,
        openrouter_api_key=openrouter_api_key,
        cerebras_api_key=cerebras_api_key,
        groq_api_key=groq_api_key,
        discord_webhook_url=discord_webhook_url,
        daily_budget_usd=daily_budget,
        score_gate=score_gate,
        posted_limit=posted_limit,
        writer_provider=os.environ.get("WRITER_PROVIDER", "openrouter").strip(),
        writer_model=os.environ.get("WRITER_MODEL", "z-ai/glm-5.2:free").strip(),
        scorer_provider=os.environ.get("SCORER_PROVIDER", "groq").strip(),
        scorer_model=os.environ.get("SCORER_MODEL", "gpt-oss-120b").strip(),
        dry_run=os.environ.get("DRY_RUN", "0").strip() in {"1", "true", "yes"},
    )


def main() -> int:
    """`python -m src.settings` — verify the environment without spending anything."""
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"✗ Config error\n  {exc}", file=sys.stderr)
        return 1
    print("✓ Environment valid\n")
    for key, value in settings.redacted.items():
        print(f"  {key:<20} {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
