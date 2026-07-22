"""
EViENT POS - Configuration Module

Reads application settings from environment variables with sensible defaults.
Uses os.environ.get() for configuration without pydantic-settings dependency.
"""

import os
from dotenv import load_dotenv

# Load from root .env
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))


class Settings:
    """Application settings loaded from environment variables.

    Attributes:
        MONGO_URI: MongoDB connection URI.
        DB_NAME: Name of the MongoDB database.
        JWT_SECRET: Secret key for JWT token signing.
        JWT_EXPIRATION: JWT token expiration time in seconds (default: 8 hours).
    """

    def __init__(self):
        self.MONGO_URI: str = os.environ.get(
            "MONGO_URI", "mongodb://localhost:27017"
        )
        self.DB_NAME: str = os.environ.get("DB_NAME", "evient_pos")
        
        self.JWT_SECRET: str | None = os.environ.get("JWT_SECRET")
        if not self.JWT_SECRET:
            raise ValueError("JWT_SECRET environment variable is required and must be set in .env")
            
        self.JWT_EXPIRATION: int = int(
            os.environ.get("JWT_EXPIRATION", "28800")
        )
        
        # Frontend Configs
        self.API_BASE_URL: str = os.environ.get("API_BASE_URL", "http://localhost:8000/api")
        # Handle escape characters correctly for the cash drawer command
        raw_cmd = os.environ.get("CASH_DRAWER_COMMAND", r"\x1B\x70\x00\x19\xFA")
        # Decode string escapes so \x1b becomes the actual escape character if it's literal string
        try:
            self.CASH_DRAWER_COMMAND = bytes(raw_cmd, "utf-8").decode("unicode_escape")
        except Exception:
            self.CASH_DRAWER_COMMAND = raw_cmd
            
        self.BAUD_RATE: int = int(os.environ.get("BAUD_RATE", "9600"))
        self.BARCODE_TIMEOUT: int = int(os.environ.get("BARCODE_TIMEOUT", "100"))
        self.ITEMS_PER_PAGE: int = int(os.environ.get("ITEMS_PER_PAGE", "20"))
        
        self.SERVER_SERIAL_PORT: str | None = os.environ.get("SERVER_SERIAL_PORT")
        
        self.VIETQR_BANK_ID: str = os.environ.get("VIETQR_BANK_ID", "970436") # Default: Vietcombank
        self.VIETQR_ACCOUNT_NO: str = os.environ.get("VIETQR_ACCOUNT_NO", "0123456789")
        self.VIETQR_ACCOUNT_NAME: str = os.environ.get("VIETQR_ACCOUNT_NAME", "NGUYEN VAN A")
        
        self.VAT_RATE: float = float(os.environ.get("VAT_RATE", "0"))

        # SMTP Email settings
        self.SMTP_HOST = os.environ.get("SMTP_HOST", "")
        self.SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
        self.SMTP_USER = os.environ.get("SMTP_USER", "")
        self.SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
        self.SMTP_FROM_NAME = os.environ.get("SMTP_FROM_NAME", "EViENT POS")
        self.SMTP_USE_TLS = os.environ.get("SMTP_USE_TLS", "true").lower() == "true"

settings = Settings()
