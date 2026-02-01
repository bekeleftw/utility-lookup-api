#!/usr/bin/env python3
"""
Centralized logging configuration for the Utility Lookup API.

Usage:
    from logging_config import get_logger
    logger = get_logger(__name__)
    
    logger.info("Processing request", extra={"address": address})
    logger.error("API call failed", extra={"endpoint": url, "error": str(e)})
"""

import logging
import sys
import os
from datetime import datetime
import json


class JSONFormatter(logging.Formatter):
    """Format log records as JSON for structured logging."""
    
    def format(self, record):
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        # Add extra fields if present
        if hasattr(record, "address"):
            log_data["address"] = record.address
        if hasattr(record, "endpoint"):
            log_data["endpoint"] = record.endpoint
        if hasattr(record, "state"):
            log_data["state"] = record.state
        if hasattr(record, "source"):
            log_data["source"] = record.source
        if hasattr(record, "duration_ms"):
            log_data["duration_ms"] = record.duration_ms
        if hasattr(record, "status_code"):
            log_data["status_code"] = record.status_code
        if hasattr(record, "error"):
            log_data["error"] = record.error
        if hasattr(record, "utility_type"):
            log_data["utility_type"] = record.utility_type
            
        # Include exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
            
        return json.dumps(log_data)


class ConsoleFormatter(logging.Formatter):
    """Human-readable format for console output."""
    
    COLORS = {
        "DEBUG": "\033[36m",    # Cyan
        "INFO": "\033[32m",     # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",    # Red
        "CRITICAL": "\033[35m", # Magenta
    }
    RESET = "\033[0m"
    
    def format(self, record):
        color = self.COLORS.get(record.levelname, self.RESET)
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        # Build extra info string
        extras = []
        for attr in ["address", "endpoint", "state", "source", "duration_ms", "error"]:
            if hasattr(record, attr):
                extras.append(f"{attr}={getattr(record, attr)}")
        extra_str = f" [{', '.join(extras)}]" if extras else ""
        
        return f"{timestamp} {color}{record.levelname:8}{self.RESET} [{record.name}] {record.getMessage()}{extra_str}"


def get_logger(name: str) -> logging.Logger:
    """
    Get a configured logger instance.
    
    Args:
        name: Logger name (typically __name__)
        
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    
    # Only configure if not already configured
    if not logger.handlers:
        # Set level from environment or default to INFO
        log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
        logger.setLevel(getattr(logging, log_level, logging.INFO))
        
        # Determine output format
        use_json = os.environ.get("LOG_FORMAT", "").lower() == "json"
        
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG)
        
        if use_json:
            console_handler.setFormatter(JSONFormatter())
        else:
            console_handler.setFormatter(ConsoleFormatter())
            
        logger.addHandler(console_handler)
        
        # Prevent propagation to root logger
        logger.propagate = False
    
    return logger


# Pre-configured loggers for main modules
api_logger = get_logger("api")
sewer_logger = get_logger("sewer_lookup")
utility_logger = get_logger("utility_lookup")
geocode_logger = get_logger("geocoding")
