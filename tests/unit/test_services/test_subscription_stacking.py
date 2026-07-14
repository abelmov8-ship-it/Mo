"""
Unit tests for the VIP-stacking fix in SubscriptionService / UserService.grant_vip.

Companion to tests/check_subscription_math.py (which checks the extracted
pure function with zero dependencies). These exercise the same behavior
through the real async DB session and ORM models, using the project's
existing fixtures — no new fixtures added.
"""
from datetime import timedelta, timezone, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models.subscription import PlanDuration
from bot.services.subscription_service import SubscriptionService
from bot.services.user_service import UserService


@pytest.mark.asyncio
async def test_grant_vip_stacks_onto_existing_subscription(session: AsyncSession, sample_user):
    user_svc = UserService(session)

    first = await user_svc.grant_vip(sample_user, days=10)
    first_expiry = first.expires_at

    # A second grant while the first is still active should extend the
    # SAME row's expiry outward, not create a shorter-lived second row that
    # the "active subscription" lookup would then have to arbitrate between.
    second = await user_svc.grant_vip(sample_user, days=5)

    assert second.id == first.id
    assert second.expires_at == first_expiry + timedelta(days=5)


@pytest.mark.asyncio
async def test_activate_stacks_onto_existing_subscription(session: AsyncSession, sample_user):
    sub_svc = SubscriptionService(session)

    first = await sub_svc.activate(sample_user, PlanDuration.ONE_MONTH)
    days_one_month = (first.expires_at - first.started_at).days

    # Buying a second plan on top of an active one should add the second
    # plan's days on top of the remaining time, not discard it.
    second = await sub_svc.activate(sample_user, PlanDuration.ONE_WEEK)

    assert second.expires_at > first.expires_at
    # within a couple seconds of the exact expected stacked point
    expected = first.expires_at + timedelta(days=7)
    assert abs((second.expires_at - expected).total_seconds()) < 2


@pytest.mark.asyncio
async def test_activate_does_not_backdate_from_expired_subscription(session: AsyncSession, sample_user):
    sub_svc = SubscriptionService(session)

    # Simulate a subscription that already lapsed.
    expired = await sub_svc.activate(sample_user, PlanDuration.ONE_WEEK)
    expired.expires_at = datetime.now(timezone.utc) - timedelta(days=3)
    await session.flush()

    fresh = await sub_svc.activate(sample_user, PlanDuration.ONE_WEEK)

    # Must grant from "now", not from the stale expired timestamp (which
    # would silently shortchange the user by ~3 days).
    now = datetime.now(timezone.utc)
    expected = now + timedelta(days=7)
    assert abs((fresh.expires_at - expected).total_seconds()) < 5
