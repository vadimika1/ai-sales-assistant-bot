from __future__ import annotations

import logging
import sys


def configure_logging(level: str = "INFO") -> None:
    normalized_level = level.upper()
    logging.basicConfig(
        level=normalized_level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )
