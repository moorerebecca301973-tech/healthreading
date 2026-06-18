"""
Pydantic schemas for request validation and response serialization.
"""

from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from typing import Optional


# =============================================================================
# AUTH SCHEMAS
# =============================================================================

class LoginRequest(BaseModel):
    """Login payload - accepts username and password."""
    username: str = Field(..., min_length=1, max_length=50, examples=["admin"])
    password: str = Field(..., min_length=1, max_length=128, examples=["admin123"])


class TokenResponse(BaseModel):
    """JWT token response after successful login."""
    access_token: str
    token_type: str = "bearer"


class ChangePasswordRequest(BaseModel):
    """Request to change the current user's password."""
    current_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=6, max_length=128)


class ChangeUsernameRequest(BaseModel):
    """Request to change the current user's username."""
    new_username: str = Field(..., min_length=3, max_length=50, examples=["newadmin"])
    password: str = Field(..., min_length=1, max_length=128)


class UserResponse(BaseModel):
    """User data returned to the client (no password)."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    is_active: bool
    created_at: Optional[datetime] = None


# =============================================================================
# READING SCHEMAS
# =============================================================================

class ReadingCreate(BaseModel):
    """Incoming sensor reading from an ESP32 device."""
    device_name: str = Field(..., min_length=1, max_length=50)
    temp_c: Optional[float] = None
    temp_valid: bool = False
    spo2: Optional[float] = None
    finger_on_sensor: bool = False
    bpm_avg: Optional[int] = None
    bpm_valid: bool = False
    raw_red: Optional[int] = None
    raw_ir: Optional[int] = None
    wifi_rssi: Optional[int] = None
    device_timestamp_ms: Optional[int] = None


class ReadingResponse(BaseModel):
    """Sensor reading data returned to the client."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    device_name: str
    temp_c: Optional[float] = None
    temp_valid: bool
    spo2: Optional[float] = None
    finger_on_sensor: bool
    bpm_avg: Optional[int] = None
    bpm_valid: bool
    raw_red: Optional[int] = None
    raw_ir: Optional[int] = None
    wifi_rssi: Optional[int] = None
    device_timestamp_ms: Optional[int] = None
    received_at: Optional[datetime] = None


class ReadingListResponse(BaseModel):
    """Paginated list of readings."""
    total: int
    page: int
    page_size: int
    readings: list[ReadingResponse]


# =============================================================================
# DASHBOARD / STATUS SCHEMAS
# =============================================================================

class DeviceStatus(BaseModel):
    """Current status of a monitored device."""
    device_name: str
    last_seen: Optional[datetime] = None
    last_spo2: Optional[float] = None
    last_bpm: Optional[int] = None
    last_temp_c: Optional[float] = None
    wifi_rssi: Optional[int] = None
    is_online: bool = False


class DashboardSummary(BaseModel):
    """Summary statistics for the dashboard homepage."""
    total_devices: int
    total_readings_today: int
    avg_spo2_today: Optional[float] = None
    avg_bpm_today: Optional[int] = None
    alerts_count: int = 0
