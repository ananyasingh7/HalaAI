import logging
import shutil
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from sqlmodel import SQLModel

from app.logging_setup import setup_logging
from data.sql.database import engine

setup_logging()
logger = logging.getLogger(__name__)

VECTOR_DB_PATH = ROOT_DIR / "data" / "vector_db"


def reset_postgres() -> None:
    logger.warning("Dropping all SQLModel tables (sessions history).")
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    logger.info("Postgres history DB reset complete.")


def reset_vector_db() -> None:
    if VECTOR_DB_PATH.exists():
        logger.warning("Removing ChromaDB directory: %s", VECTOR_DB_PATH)
        shutil.rmtree(VECTOR_DB_PATH)
    VECTOR_DB_PATH.mkdir(parents=True, exist_ok=True)
    logger.info("Vector DB reset complete.")


def main() -> None:
    reset_postgres()
    reset_vector_db()
    logger.info("All datastores reset.")


if __name__ == "__main__":
    main()
