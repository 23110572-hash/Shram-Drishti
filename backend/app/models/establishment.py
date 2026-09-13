"""Establishments and the attributes that decide which rules apply to them.

This model is the input to rule applicability. Almost every threshold in the
Codes is conditional on something here — worker count, sector, state, whether
contract labour is engaged, whether women are employed, whether the process is
hazardous. Getting these fields wrong means correct rules fire on the wrong
establishments, so each one is explicit rather than inferred at evaluation time.

Verified thresholds this profile feeds (see information.md section 14):

* IR Code s.3(1)   — Works Committee at 100+ workers
* IR Code s.4(1)   — Grievance Redressal Committee at 20+ workers
* IR Code s.28(1)  — Standing Orders at 300+ workers
* Wages s.14/17/18 — apply to every establishment with employees
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.base import EnumColumn, IdMixin, TimestampMixin
from app.models.enums import SkillCategory, WageRateSource


class Establishment(IdMixin, TimestampMixin, Base):
    __tablename__ = "establishment"
    __id_prefix__ = "est"
    __table_args__ = (
        Index("ix_establishment_jurisdiction", "state_code"),
        Index("ix_establishment_org", "organisation_id"),
    )

    organisation_id: Mapped[str] = mapped_column(
        ForeignKey("organisation.id", ondelete="RESTRICT"), nullable=False
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Shram Suvidha Labour Identification Number, where one exists.
    lin: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)

    # --------------------------------------------------------- jurisdiction
    # State code drives which minimum wage table and which state Rules apply.
    state_code: Mapped[str] = mapped_column(String(8), nullable=False)
    district: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Many states set different rates by zone or area class.
    wage_zone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    address: Mapped[str | None] = mapped_column(String(512), nullable=True)

    @property
    def jurisdiction_code(self) -> str:
        """Overlay key used by the rule engine, e.g. ``IN/MH``."""
        return f"IN/{self.state_code}"

    # ------------------------------------------------------------- activity
    # National Industrial Classification code, for sector peer comparison.
    nic_code: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    sector: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # ------------------------------------------ headcount and applicability
    # Current declared headcount. Rule applicability uses the twelve-month peak
    # as well, because several Code provisions read "employed on any day of the
    # preceding twelve months".
    worker_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    worker_count_peak_12m: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    women_worker_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    contract_worker_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    interstate_migrant_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    is_factory: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_mine: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_plantation: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_construction: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    has_hazardous_process: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    engages_contract_labour: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    has_night_shift: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # ------------------------------------------------------------ lifecycle
    commenced_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    registrations: Mapped[list[Registration]] = relationship(
        back_populates="establishment", cascade="all, delete-orphan"
    )
    contractors: Mapped[list[Contractor]] = relationship(
        back_populates="establishment", cascade="all, delete-orphan"
    )

    @property
    def women_worker_ratio(self) -> float:
        """Used by IR Code s.4(4) proviso on committee composition."""
        if self.worker_count <= 0:
            return 0.0
        return self.women_worker_count / self.worker_count


class Registration(IdMixin, TimestampMixin, Base):
    """A registration, licence or certificate held by the establishment.

    Modelled generically with a ``kind`` discriminator because the validity
    check is identical across all of them: does it exist, and has it expired.
    """

    __tablename__ = "registration"
    __id_prefix__ = "reg"
    __table_args__ = (Index("ix_registration_validity", "establishment_id", "valid_to"),)

    establishment_id: Mapped[str] = mapped_column(
        ForeignKey("establishment.id", ondelete="CASCADE"), nullable=False
    )

    # e.g. FACTORY_LICENCE, EPF, ESIC, BOCW, SHOPS_AND_ESTABLISHMENTS
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    number: Mapped[str] = mapped_column(String(64), nullable=False)
    issuing_authority: Mapped[str | None] = mapped_column(String(255), nullable=True)

    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Null means open-ended, which is legitimate for some registrations. An
    # expiry check must therefore treat null as "does not expire", not "expired".
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)

    establishment: Mapped[Establishment] = relationship(back_populates="registrations")

    def is_valid_on(self, on: date) -> bool:
        if self.valid_from and on < self.valid_from:
            return False
        if self.valid_to and on > self.valid_to:
            return False
        return True


class Contractor(IdMixin, TimestampMixin, Base):
    """A labour contractor engaged by the establishment.

    Held separately from registrations because the compliance question is
    different: not only "is the licence valid" but "does the licence cover the
    number of workers actually deployed".
    """

    __tablename__ = "contractor"
    __id_prefix__ = "con"

    establishment_id: Mapped[str] = mapped_column(
        ForeignKey("establishment.id", ondelete="CASCADE"), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    licence_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    licence_valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    licence_valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Cap stated on the licence, versus how many are actually on site.
    licensed_worker_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    deployed_worker_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    establishment: Mapped[Establishment] = relationship(back_populates="contractors")


class MinimumWageRate(IdMixin, TimestampMixin, Base):
    """A minimum wage figure for one state, skill category and period.

    ``source`` is legally material. A finding raised against a REFERENCE rate
    must not be presented with the authority of one raised against an official
    NOTIFIED rate, so provenance travels with every rate and is stamped onto
    every finding that uses it.

    Rates are stored per day. Monthly comparisons multiply by
    ``monthly_working_days`` rather than assuming 30, because notifications
    conventionally compute monthly figures on 26 paid days.
    """

    __tablename__ = "minimum_wage_rate"
    __id_prefix__ = "mwr"
    __table_args__ = (
        Index(
            "ix_minimum_wage_lookup",
            "state_code",
            "skill_category",
            "effective_from",
        ),
    )

    state_code: Mapped[str] = mapped_column(String(8), nullable=False)
    state_name: Mapped[str] = mapped_column(String(128), nullable=False)
    wage_zone: Mapped[str | None] = mapped_column(String(32), nullable=True)

    skill_category: Mapped[SkillCategory] = mapped_column(
        EnumColumn(SkillCategory, 24), nullable=False
    )

    # Paise, not rupees. Integer arithmetic avoids float rounding errors in a
    # calculation that decides whether an employer underpaid a worker.
    daily_rate_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    monthly_working_days: Mapped[int] = mapped_column(Integer, default=26, nullable=False)

    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)

    source: Mapped[WageRateSource] = mapped_column(
        EnumColumn(WageRateSource, 16), nullable=False
    )
    source_note: Mapped[str | None] = mapped_column(String(512), nullable=True)

    @property
    def daily_rate_rupees(self) -> float:
        return self.daily_rate_paise / 100

    @property
    def monthly_rate_paise(self) -> int:
        return self.daily_rate_paise * self.monthly_working_days
