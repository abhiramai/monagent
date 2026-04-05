from app.core.db import init_db
from app.core.logger import logger


def main() -> None:
    logger.info("System startup — monagent is initializing")
    init_db()


if __name__ == "__main__":
    main()
