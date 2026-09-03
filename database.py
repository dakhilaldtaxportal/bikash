from datetime import datetime, timezone
from sqlalchemy import (
    create_engine, Column, Integer, BigInteger, String, Float, Boolean,
    DateTime, Text, ForeignKey, Enum as SAEnum
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from sqlalchemy.pool import StaticPool
import enum
import config

Base = declarative_base()

class OrderType(str, enum.Enum):
    NORMAL = "normal"
    BROADCAST = "broadcast"

class OrderStatus(str, enum.Enum):
    PENDING = "pending"          # waiting for rider accept
    ACCEPTED = "accepted"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    REASSIGNED = "reassigned"

class Rider(Base):
    __tablename__ = "riders"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)
    phone = Column(String(30), nullable=True)
    name = Column(String(120), nullable=True)
    home_lat = Column(Float, nullable=True)
    home_lon = Column(Float, nullable=True)
    range_km = Column(Float, default=config.DEFAULT_RIDER_RANGE_KM)
    is_online = Column(Boolean, default=False)
    is_suspended = Column(Boolean, default=False)
    current_lat = Column(Float, nullable=True)
    current_lon = Column(Float, nullable=True)
    last_location_update = Column(DateTime, nullable=True)
    is_busy = Column(Boolean, default=False)  # True when has active accepted order
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    orders = relationship("Order", back_populates="rider")

class Vendor(Base):
    __tablename__ = "vendors"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=True, index=True)
    name = Column(String(120), nullable=False)
    phone = Column(String(30), nullable=False)
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)
    is_suspended = Column(Boolean, default=False)
    added_by = Column(BigInteger, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    orders = relationship("Order", back_populates="vendor")

class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    vendor_id = Column(Integer, ForeignKey("vendors.id"), nullable=False)
    rider_id = Column(Integer, ForeignKey("riders.id"), nullable=True)

    order_text = Column(Text, nullable=False)
    customer_map_link = Column(Text, nullable=True)
    customer_lat = Column(Float, nullable=True)
    customer_lon = Column(Float, nullable=True)

    order_type = Column(SAEnum(OrderType), default=OrderType.NORMAL)
    status = Column(SAEnum(OrderStatus), default=OrderStatus.PENDING)

    delivery_charge = Column(Float, default=0.0)       # vendor -> customer
    broadcast_extra = Column(Float, default=0.0)       # extra paid by vendor to rider
    distance_vendor_customer_km = Column(Float, default=0.0)
    distance_vendor_rider_km = Column(Float, default=0.0)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    accepted_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)       # for accept timeout

    vendor = relationship("Vendor", back_populates="orders")
    rider = relationship("Rider", back_populates="orders")

class Setting(Base):
    __tablename__ = "settings"

    key = Column(String(64), primary_key=True)
    value = Column(String(256), nullable=False)

# ====================== ENGINE & SESSION ======================

def get_engine():
    if config.DATABASE_URL.startswith("sqlite"):
        engine = create_engine(
            config.DATABASE_URL,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            echo=False
        )
    else:
        engine = create_engine(config.DATABASE_URL, echo=False, pool_pre_ping=True)
    return engine

engine = get_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

def init_db():
    Base.metadata.create_all(bind=engine)
    # seed default settings
    session = SessionLocal()
    try:
        defaults = {
            "base_km": str(config.DEFAULT_BASE_KM),
            "base_price": str(config.DEFAULT_BASE_PRICE),
            "extra_per_km": str(config.DEFAULT_EXTRA_PER_KM),
            "broadcast_per_km": str(config.DEFAULT_BROADCAST_PER_KM),
            "normal_radius": str(config.NORMAL_RADIUS_KM),
            "broadcast_radius": str(config.BROADCAST_RADIUS_KM),
        }
        for k, v in defaults.items():
            existing = session.query(Setting).filter_by(key=k).first()
            if not existing:
                session.add(Setting(key=k, value=v))
        session.commit()
    finally:
        session.close()

def get_setting(key: str, default: str = None) -> str:
    session = SessionLocal()
    try:
        row = session.query(Setting).filter_by(key=key).first()
        return row.value if row else default
    finally:
        session.close()

def set_setting(key: str, value: str):
    session = SessionLocal()
    try:
        row = session.query(Setting).filter_by(key=key).first()
        if row:
            row.value = value
        else:
            session.add(Setting(key=key, value=value))
        session.commit()
    finally:
        session.close()

def get_db():
    """Context manager style helper"""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
