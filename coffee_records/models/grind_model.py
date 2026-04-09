"""ORM models for persisted grind model training results."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from coffee_records.database import Base


class GrindModelTraining(Base):
    """One row per fitted grind model training run for a given grinder.

    Global coefficients (a0, a2–a5) are stored directly on this row.
    Per-coffee intercepts are stored in GrindModelCoffeeIntercept.
    """

    __tablename__ = "grind_model_trainings"

    id: Mapped[int] = mapped_column(primary_key=True)
    grinder_id: Mapped[int] = mapped_column(
        ForeignKey("grinders.id"), nullable=False
    )
    trained_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    n_shots_available: Mapped[int] = mapped_column(Integer, nullable=False)
    n_shots_used: Mapped[int] = mapped_column(Integer, nullable=False)
    n_coffees: Mapped[int] = mapped_column(Integer, nullable=False)
    n_iterations: Mapped[int] = mapped_column(Integer, nullable=False)
    converged: Mapped[bool] = mapped_column(Boolean, nullable=False)
    r_squared: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Global model coefficients
    a0: Mapped[float] = mapped_column(Float, nullable=False)  # temp - 65
    a2: Mapped[float] = mapped_column(Float, nullable=False)  # extraction_time - target
    a3: Mapped[float] = mapped_column(Float, nullable=False)  # dose - 20
    a4: Mapped[float] = mapped_column(Float, nullable=False)  # age_days
    a5: Mapped[float] = mapped_column(Float, nullable=False)  # yield - 2*dose

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    grinder: Mapped["Grinder"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Grinder"
    )
    coffee_intercepts: Mapped[list["GrindModelCoffeeIntercept"]] = relationship(
        "GrindModelCoffeeIntercept",
        back_populates="training",
        cascade="all, delete-orphan",
    )


class GrindModelCoffeeIntercept(Base):
    """Per-coffee intercept for a specific grind model training run."""

    __tablename__ = "grind_model_coffee_intercepts"

    id: Mapped[int] = mapped_column(primary_key=True)
    training_id: Mapped[int] = mapped_column(
        ForeignKey("grind_model_trainings.id"), nullable=False
    )
    coffee_id: Mapped[int] = mapped_column(
        ForeignKey("coffees.id"), nullable=False
    )
    intercept: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    training: Mapped["GrindModelTraining"] = relationship(
        "GrindModelTraining", back_populates="coffee_intercepts"
    )
    coffee: Mapped["Coffee"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Coffee"
    )
