"""Look up the most recent grind setting used for a coffee."""

from sqlalchemy.orm import Session

from coffee_records.models.shot import Shot


def find_last_grind_shot(
    session: Session, coffee_id: int, grinder_id: int | None = None
) -> Shot | None:
    """Return the most recent shot of a coffee that recorded a grind setting.

    Shots are ordered by date, then creation time, then id (newest first), so
    several shots on the same day resolve to the last one entered.

    Args:
        session: SQLAlchemy session.
        coffee_id: Coffee bag to look up.
        grinder_id: When given, only shots on this grinder count, so the
            setting's notation matches the grinder it will be used with.

    Returns:
        The latest such shot, or None if the coffee has no recorded grind.
    """
    query = session.query(Shot).filter(
        Shot.coffee_id == coffee_id,
        Shot.grind_setting.isnot(None),
        Shot.grind_setting != "",
    )
    if grinder_id is not None:
        query = query.filter(Shot.grinder_id == grinder_id)
    return query.order_by(
        Shot.date.desc(), Shot.created_at.desc(), Shot.id.desc()
    ).first()
