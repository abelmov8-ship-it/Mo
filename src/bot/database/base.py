from sqlalchemy.orm import DeclarativeBase, MappedAsDataclass


class Base(DeclarativeBase):
    """
    All ORM models inherit from this base.
    Provides the shared metadata registry and optional repr generation.
    """
    pass
