import logging
import logging.config
import sys
from pathlib import Path

_CONFIGURED = False


def setup_logging(default_level: int = logging.INFO) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    config_path = Path(__file__).resolve().parents[1] / "config" / "logging.ini"
    if config_path.exists():
        logging.config.fileConfig(
            config_path,
            disable_existing_loggers=False,
            defaults={"sys": sys},
        )
    else:
        logging.basicConfig(level=default_level)

    _CONFIGURED = True
