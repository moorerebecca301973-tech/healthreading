"""
Medical Monitor Backend API
============================
FastAPI application for receiving, storing, and managing clinical IoT sensor data.

Features:
- Argon2 password hashing with seeded admin user
- JWT-based authentication
- CRUD for sensor readings
- Dashboard analytics endpoints
- Full CORS support
- Deploy-ready for Render

Environment Variables:
- SECRET_KEY: JWT signing secret (CHANGE IN PRODUCTION!)
- SEEDED_USERNAME: Initial admin username (default: admin)
- SEEDED_PASSWORD: Initial admin password (default: admin123)
- ACCESS_TOKEN_EXPIRE_MINUTES: JWT expiry (default: 60)
- DATABASE_URL: SQLite async URL (default: local file)
- CORS_ORIGINS: Comma-separated allowed origins (default: *)
- PORT: Server port (default: 8000)
"""

import os
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta

from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, status, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from database import init_db, get_db, engine
from models import User, Reading
from schemas import (
    LoginRequest,
    TokenResponse,
    ChangePasswordRequest,
    ChangeUsernameRequest,
    UserResponse,
    ReadingCreate,
    ReadingResponse,
    ReadingListResponse,
    DeviceStatus,
    DashboardSummary,
)
from security import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_username,
    SEEDED_USERNAME,
    SEEDED_PASSWORD,
    ACCESS_TOKEN_EXPIRE_MINUTES,
)


# =============================================================================
# LIFESPAN: Initialize DB + seed admin user on startup
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler: init DB and seed admin user."""
    await init_db()
    await seed_admin_user()
    yield
    # Shutdown (nothing to clean up)


async def seed_admin_user():
    """Create the seeded admin user if it doesn't already exist."""
    from database import AsyncSessionLocal
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.username == SEEDED_USERNAME))
        existing = result.scalar_one_or_none()

        if existing is None:
            admin = User(
                username=SEEDED_USERNAME,
                hashed_password=hash_password(SEEDED_PASSWORD),
                is_active=True,
            )
            session.add(admin)
            await session.commit()
            print(f"[SEED] Created admin user: '{SEEDED_USERNAME}'")
        else:
            print(f"[SEED] Admin user '{SEEDED_USERNAME}' already exists.")


# =============================================================================
# FASTAPI APP INSTANCE
# =============================================================================

app = FastAPI(
    title="Medical Monitor API",
    description="Backend API for Clinical-Grade IoT Medical Monitor devices",
    version="1.0.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS CONFIGURATION
# ---------------------------------------------------------------------------
# Allow all origins by default, or configure via environment variable
cors_origins_str = os.getenv("CORS_ORIGINS", "*")
cors_origins = [o.strip() for o in cors_origins_str.split(",")] if cors_origins_str != "*" else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# AUTH ROUTES
# =============================================================================

@app.post("/api/auth/login", response_model=TokenResponse, tags=["Authentication"])
async def login(credentials: LoginRequest, db: AsyncSession = Depends(get_db)):
    """
    Authenticate with username and password.
    Returns a JWT bearer token for use in subsequent requests.
    """
    result = await db.execute(select(User).where(User.username == credentials.username))
    user = result.scalar_one_or_none()

    if not user or not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )

    access_token = create_access_token(data={"sub": user.username})
    return TokenResponse(access_token=access_token)


@app.get("/api/auth/me", response_model=UserResponse, tags=["Authentication"])
async def get_me(
    username: str = Depends(get_current_username),
    db: AsyncSession = Depends(get_db),
):
    """Get the currently authenticated user's profile."""
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@app.post("/api/auth/change-password", tags=["Authentication"])
async def change_password(
    req: ChangePasswordRequest,
    username: str = Depends(get_current_username),
    db: AsyncSession = Depends(get_db),
):
    """
    Change the current user's password.
    Requires current password for verification.
    """
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Verify current password
    if not verify_password(req.current_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    # Hash and save new password
    user.hashed_password = hash_password(req.new_password)
    await db.commit()

    return {"message": "Password changed successfully"}


@app.post("/api/auth/change-username", tags=["Authentication"])
async def change_username(
    req: ChangeUsernameRequest,
    username: str = Depends(get_current_username),
    db: AsyncSession = Depends(get_db),
):
    """
    Change the current user's username.
    Requires password for verification. New username must be unique.
    """
    # Check new username is not taken
    result = await db.execute(select(User).where(User.username == req.new_username))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Username already taken")

    # Verify password
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not verify_password(req.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Password is incorrect")

    user.username = req.new_username
    await db.commit()

    # Return new token with updated username
    new_token = create_access_token(data={"sub": req.new_username})
    return {
        "message": "Username changed successfully",
        "new_username": req.new_username,
        "access_token": new_token,
        "token_type": "bearer",
    }


# =============================================================================
# READING ROUTES (Protected)
# =============================================================================

@app.post("/api/readings", response_model=ReadingResponse, status_code=201, tags=["Readings"])
async def create_reading(
    reading: ReadingCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Receive a sensor reading from an ESP32 device.
    Accepts a JWT token in the Authorization header for device authentication.
    """
    db_reading = Reading(**reading.model_dump())
    db.add(db_reading)
    await db.commit()
    await db.refresh(db_reading)
    return db_reading


@app.get("/api/readings", response_model=ReadingListResponse, tags=["Readings"])
async def list_readings(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    device_name: Optional[str] = Query(None, description="Filter by device name"),
    username: str = Depends(get_current_username),
    db: AsyncSession = Depends(get_db),
):
    """List all sensor readings with pagination and optional device filter."""
    # Build base query
    query = select(Reading)
    count_query = select(func.count(Reading.id))

    if device_name:
        query = query.where(Reading.device_name == device_name)
        count_query = count_query.where(Reading.device_name == device_name)

    # Order by most recent first
    query = query.order_by(desc(Reading.received_at))

    # Count total
    count_result = await db.execute(count_query)
    total = count_result.scalar()

    # Paginate
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    result = await db.execute(query)
    readings = result.scalars().all()

    return ReadingListResponse(
        total=total,
        page=page,
        page_size=page_size,
        readings=[ReadingResponse.model_validate(r) for r in readings],
    )


@app.get("/api/readings/latest", response_model=list[DeviceStatus], tags=["Readings"])
async def get_latest_readings(
    username: str = Depends(get_current_username),
    db: AsyncSession = Depends(get_db),
):
    """Get the latest reading for each device (dashboard overview)."""
    # Subquery: find max id (most recent) per device
    subq = (
        select(
            Reading.device_name,
            func.max(Reading.id).label("max_id")
        )
        .group_by(Reading.device_name)
        .subquery()
    )

    query = (
        select(Reading)
        .join(subq, Reading.id == subq.c.max_id)
    )

    result = await db.execute(query)
    latest_readings = result.scalars().all()

    # Determine online status (received in last 2 minutes)
    now = datetime.now(timezone.utc)
    devices = []
    for r in latest_readings:
        last_seen = r.received_at
        # Handle naive vs aware datetime
        if last_seen and last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)
        is_online = last_seen and (now - last_seen) < timedelta(minutes=2)

        devices.append(DeviceStatus(
            device_name=r.device_name,
            last_seen=last_seen,
            last_spo2=r.spo2,
            last_bpm=r.bpm_avg,
            last_temp_c=r.temp_c,
            wifi_rssi=r.wifi_rssi,
            is_online=is_online,
        ))

    return devices


# =============================================================================
# DASHBOARD / ANALYTICS ROUTES
# =============================================================================

@app.get("/api/dashboard/summary", response_model=DashboardSummary, tags=["Dashboard"])
async def get_dashboard_summary(
    username: str = Depends(get_current_username),
    db: AsyncSession = Depends(get_db),
):
    """Get summary statistics for the dashboard homepage."""
    # Count unique devices
    devices_result = await db.execute(
        select(func.count(func.distinct(Reading.device_name)))
    )
    total_devices = devices_result.scalar() or 0

    # Count today's readings
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_count_result = await db.execute(
        select(func.count(Reading.id)).where(Reading.received_at >= today_start)
    )
    total_readings_today = today_count_result.scalar() or 0

    # Average SpO2 today
    avg_spo2_result = await db.execute(
        select(func.avg(Reading.spo2))
        .where(Reading.received_at >= today_start)
        .where(Reading.finger_on_sensor == True)
        .where(Reading.spo2.isnot(None))
    )
    avg_spo2 = avg_spo2_result.scalar()

    # Average BPM today
    avg_bpm_result = await db.execute(
        select(func.avg(Reading.bpm_avg))
        .where(Reading.received_at >= today_start)
        .where(Reading.bpm_valid == True)
        .where(Reading.bpm_avg.isnot(None))
    )
    avg_bpm = avg_bpm_result.scalar()

    # Count low SpO2 alerts (SpO2 < 90)
    alerts_result = await db.execute(
        select(func.count(Reading.id))
        .where(Reading.received_at >= today_start)
        .where(Reading.spo2 < 90)
        .where(Reading.finger_on_sensor == True)
    )
    alerts_count = alerts_result.scalar() or 0

    return DashboardSummary(
        total_devices=total_devices,
        total_readings_today=total_readings_today,
        avg_spo2_today=round(avg_spo2, 1) if avg_spo2 else None,
        avg_bpm_today=int(avg_bpm) if avg_bpm else None,
        alerts_count=alerts_count,
    )


# =============================================================================
# HEALTH CHECK
# =============================================================================

@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint for Render monitoring."""
    return {"status": "healthy", "service": "medical-monitor-api"}


# =============================================================================
# ROOT REDIRECT
# =============================================================================

@app.get("/", include_in_schema=False)
async def root():
    """Redirect root to API docs."""
    return {"message": "Medical Monitor API", "docs": "/docs"}


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
