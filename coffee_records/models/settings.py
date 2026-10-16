"""ShotDefaults ORM model."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, String, func
from sqlalchemy.orm import Mapped, mapped_column

from coffee_records.database import Base
from coffee_records.models.shot import DrinkType

# Primary key of the single ShotDefaults row.
SHOT_DEFAULTS_ID = 1


class ShotDefaults(Base):
    """Singleton row of configurable defaults for the New Shot form."""

    __tablename__ = "shot_defaults"

    id: Mapped[int] = mapped_column(primary_key=True, default=SHOT_DEFAULTS_ID)
    maker: Mapped[str] = mapped_column(String(255), nullable=False)
    dose_weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    pre_infusion_time: Mapped[str | None] = mapped_column(String(50), nullable=True)
    extraction_time: Mapped[float | None] = mapped_column(Float, nullable=True)
    final_weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Stored as VARCHAR (not the drink_type enum) to match the existing schema;
    # values are validated against DrinkType.
    drink_type: Mapped[DrinkType | None] = mapped_column(
        Enum(DrinkType, native_enum=False, length=50), nullable=True
    )
    grinder_temp_before: Mapped[float | None] = mapped_column(Float, nullable=True)
    wedge: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    shaker: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    wdt: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    flow_taper: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
