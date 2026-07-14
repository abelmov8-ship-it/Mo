"""Unit tests for UserService."""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.user_service import UserService


@pytest.mark.asyncio
async def test_get_or_create_new_user(session: AsyncSession):
    svc = UserService(session)
    user, created = await svc.get_or_create(999001, "Alice", "alice")
    assert created is True
    assert user.first_name == "Alice"


@pytest.mark.asyncio
async def test_grant_vip(session: AsyncSession, sample_user):
    svc = UserService(session)
    sub = await svc.grant_vip(sample_user, days=7)
    assert sample_user.is_vip is True
    assert sub.custom_days == 7


@pytest.mark.asyncio
async def test_wallet_debit_insufficient(session: AsyncSession, sample_user):
    svc = UserService(session)
    sample_user.wallet_balance = 10.0
    result = await svc.debit_wallet(sample_user, 50.0)
    assert result is False

@pytest.mark.asyncio
async def test_ban_and_unban(session: AsyncSession, sample_user):
    svc = UserService(session)
    await svc.ban(sample_user)
    assert sample_user.is_banned is True
    await svc.unban(sample_user)
    assert sample_user.is_banned is False
