import os
import logging
from logging.handlers import RotatingFileHandler


def setup_logging(log_name='market_structures', log_file_name='market_structures.log', verbose_console_logging=True):
    """
    Set up logging with both file and console handlers.

    Args:
        log_name: Name for the logger
        log_file_name: Name for the log file (currently unused, kept for compatibility)
        verbose_console_logging: If True, console shows INFO level; if False, shows WARNING level

    Returns:
        Configured logger instance
    """
    # Create logs directory if it doesn't exist
    log_dir = 'logs'
    os.makedirs(log_dir, exist_ok=True)

    # Create logger
    logger = logging.getLogger(log_name)
    logger.setLevel(level=logging.INFO)

    # Create formatters
    file_formatter = logging.Formatter('%(asctime)s|%(name)s|%(levelname)s|%(funcName)s|%(lineno)d|%(message)s')
    console_formatter = logging.Formatter('%(funcName)s|%(lineno)d|%(message)s')

    # Create and configure file handler (rotating log files)
    file_handler = RotatingFileHandler(
        f'{log_dir}/{log_name}',
        maxBytes=1024*1024,  # 1MB
        backupCount=5
    )
    file_handler.setLevel(level=logging.INFO)
    file_handler.setFormatter(file_formatter)

    # Create and configure console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO if verbose_console_logging else logging.WARNING)
    console_handler.setFormatter(console_formatter)

    # Add handlers to logger
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger
