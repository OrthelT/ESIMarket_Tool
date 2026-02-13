import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(log_name: str = 'market_structures', verbose_console_logging: bool = True) -> logging.Logger:
    """Set up logging with both file and console handlers.

    Args:
        log_name: Name for the logger (also used as log filename)
        verbose_console_logging: If True, console shows INFO level; if False, shows WARNING level

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(log_name)

    # Guard against adding duplicate handlers on repeated calls
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    # Use Path anchored to this file's directory so logs/ is always beside the source
    log_dir = Path(__file__).parent / 'logs'
    log_dir.mkdir(exist_ok=True)

    # File handler (rotating)
    file_formatter = logging.Formatter('%(asctime)s|%(name)s|%(levelname)s|%(funcName)s|%(lineno)d|%(message)s')
    file_handler = RotatingFileHandler(
        log_dir / log_name,
        maxBytes=1024 * 1024,  # 1 MB
        backupCount=5,
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(file_formatter)

    # Console handler
    console_formatter = logging.Formatter('%(funcName)s|%(lineno)d|%(message)s')
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO if verbose_console_logging else logging.WARNING)
    console_handler.setFormatter(console_formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger
