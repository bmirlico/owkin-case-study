import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str
    model_name: str
    csv_path: str
    max_tool_iterations: int


def load_settings() -> Settings:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your key, "
            "or pass it via --env-file when running Docker."
        )
    return Settings(
        anthropic_api_key=api_key,
        model_name=os.environ.get("MODEL_NAME", "claude-sonnet-4-6"),
        csv_path=os.environ.get("CSV_PATH", "data/owkin_take_home_data.csv"),
        max_tool_iterations=int(os.environ.get("MAX_TOOL_ITERATIONS", "5")),
    )
