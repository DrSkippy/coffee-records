"""Equipment ORM models: Grinder, BrewingDevice, Scale."""

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from coffee_records.database import Base


class GrinderType(str, enum.Enum):
    """Grinder burr type."""

    flat = "flat"
    conical = "conical"
    blade = "blade"


class Grinder(Base):
    """A coffee grinder."""

    __tablename__ = "grinders"

    id: Mapped[int] = mapped_column(primary_key=True)
    make: Mapped[str] = mapped_column(String(255), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[GrinderType] = mapped_column(
        Enum(GrinderType, name="grinder_type"), nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    shots: Mapped[list["Shot"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Shot", back_populates="grinder"
    )


class BrewingDevice(Base):
    """An espresso machine or brewing device."""

    __tablename__ = "brewing_devices"

    id: Mapped[int] = mapped_column(primary_key=True)
    make: Mapped[str] = mapped_column(String(255), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(100), nullable=False)
    warmup_minutes: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    shots: Mapped[list["Shot"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Shot", back_populates="device"
    )


class Scale(Base):
    """A coffee scale."""

    __tablename__ = "scales"

    id: Mapped[int] = mapped_column(primary_key=True)
    make: Mapped[str] = mapped_column(String(255), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    shots: Mapped[list["Shot"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Shot", back_populates="scale"
    )
