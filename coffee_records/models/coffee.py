"""Coffee bag ORM model."""

import enum
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from coffee_records.database import Base


class RoastLevel(str, enum.Enum):
    """Coffee roast level."""

    light = "light"
    medium = "medium"
    dark = "dark"


class Coffee(Base):
    """A bag of coffee beans."""

    __tablename__ = "coffees"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    roaster: Mapped[str] = mapped_column(String(255), nullable=False)
    roast_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    origin_country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    roast_level: Mapped[RoastLevel | None] = mapped_column(
        Enum(RoastLevel, name="roast_level"), nullable=True
    )
    variety: Mapped[str | None] = mapped_column(Text, nullable=True)
    process: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    shots: Mapped[list["Shot"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Shot", back_populates="coffee"
    )
