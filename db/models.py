from datetime import date, datetime, time

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, String, Time, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.database import Base


class Pet(Base):
    __tablename__ = "pets"

    pet_id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    pet_name: Mapped[str] = mapped_column(String(100), nullable=False)
    pet_type: Mapped[str] = mapped_column(String(50), nullable=False)
    pet_gender: Mapped[str] = mapped_column(String(20), nullable=False)
    pet_breed: Mapped[str] = mapped_column(String(100), nullable=False)

    pet_birth_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )
    pet_birth_time: Mapped[time | None] = mapped_column(
        Time,
        nullable=True,
    )

    city: Mapped[str] = mapped_column(String(255), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    users: Mapped[list["User"]] = relationship(back_populates="pet")


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    pet_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("pets.pet_id"),
        nullable=False,
    )

    user_name: Mapped[str] = mapped_column(String(100), nullable=False)
    user_email: Mapped[str] = mapped_column(String(255), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    pet: Mapped["Pet"] = relationship(back_populates="users")
