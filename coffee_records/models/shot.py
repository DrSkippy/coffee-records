"""Shot ORM model."""

import enum
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Enum, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from coffee_records.database import Base


class DrinkType(str, enum.Enum):
    """Final drink type."""

    americano = "americano"
    latte = "latte"
    cappuccino = "cappuccino"
    drip = "drip"
    aeropress = "aeropress"


class Shot(Base):
    """A single espresso shot record."""

    __tablename__ = "shots"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    maker: Mapped[str] = mapped_column(String(255), nullable=False)

    coffee_id: Mapped[int | None] = mapped_column(
        ForeignKey("coffees.id"), nullable=True
    )
    dose_weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    pre_infusion_time: Mapped[str | None] = mapped_column(String(50), nullable=True)
    extraction_time: Mapped[float | None] = mapped_column(Float, nullable=True)
    extraction_delta: Mapped[float | None] = mapped_column(Float, nullable=True, default=0.0)
    scale_id: Mapped[int | None] = mapped_column(
        ForeignKey("scales.id"), nullable=True
    )
    final_weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    drink_type: Mapped[DrinkType | None] = mapped_column(
        Enum(DrinkType, name="drink_type"), nullable=True
    )
    grinder_temp_before: Mapped[float | None] = mapped_column(Float, nullable=True)
    grinder_temp_after: Mapped[float | None] = mapped_column(Float, nullable=True)

    wedge: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    shaker: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    wdt: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    flow_taper: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    grind_setting: Mapped[str | None] = mapped_column(String(50), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    video_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)

    grinder_id: Mapped[int | None] = mapped_column(
        ForeignKey("grinders.id"), nullable=True
    )
    device_id: Mapped[int | None] = mapped_column(
        ForeignKey("brewing_devices.id"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    coffee: Mapped["Coffee | None"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Coffee", back_populates="shots"
    )
    grinder: Mapped["Grinder | None"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Grinder", back_populates="shots"
    )
    device: Mapped["BrewingDevice | None"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "BrewingDevice", back_populates="shots"
    )
    scale: Mapped["Scale | None"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Scale", back_populates="shots"
    )
