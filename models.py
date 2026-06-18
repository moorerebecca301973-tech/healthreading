"""
SQLAlchemy ORM models for the Medical Monitor backend.
"""

from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, func
from database import Base


class User(Base):
    """Admin user account for the web dashboard."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class Reading(Base):
    """Sensor reading received from an ESP32 medical monitor device."""
    __tablename__ = "readings"

    id = Column(Integer, primary_key=True, index=True)
    device_name = Column(String(50), nullable=False, index=True)

    # Vital signs
    temp_c = Column(Float, nullable=True)
    temp_valid = Column(Boolean, default=False)
    spo2 = Column(Float, nullable=True)
    finger_on_sensor = Column(Boolean, default=False)
    bpm_avg = Column(Integer, nullable=True)
    bpm_valid = Column(Boolean, default=False)

    # Raw sensor values (for diagnostics)
    raw_red = Column(Integer, nullable=True)
    raw_ir = Column(Integer, nullable=True)
    wifi_rssi = Column(Integer, nullable=True)

    # Device timestamp and server received timestamp
    device_timestamp_ms = Column(Integer, nullable=True)
    received_at = Column(DateTime(timezone=True), server_default=func.now())
