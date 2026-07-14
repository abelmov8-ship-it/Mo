"""
Runnable self-check for PaymentService.try_claim_pending — the single
guarantee standing between "webhook and manual Verify both fire for the
same tx_ref" and "user gets VIP/wallet credit twice."

Covers:
1. First claim on a PENDING payment succeeds and actually persists APPROVED.
2. A second claim on the same (now-APPROVED) row fails — this is what
   makes it safe for two callers (webhook + manual Verify tap) to both
   reach try_claim_pending for the same row: only one gets True back.
3. A payment that was never PENDING (e.g. already REJECTED) can't be
   claimed at all.

Doesn't attempt to simulate the literal concurrent race with asyncio.gather
— that would mostly be exercising SQLite's own transaction-locking
behavior in this test harness, not this code's logic, and isn't something
to assert on without being able to run it first. The WHERE-gated UPDATE
below is the actual mechanism; this checks that mechanism directly.

Run directly: `python3 tests/check_chapa_idempotency.py`
(Needs sqlalchemy + aiosqlite installed — same as every other DB-touching
check script in this suite.)
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from bot.database.base import Base
import bot.database.models  # noqa: F401  registers all models on Base.metadata
from bot.database.models.payment import Payment, PaymentGateway, PaymentStatus, PaymentType
from bot.database.models.user import User, UserLanguage
from bot.services.payment_service import PaymentService


def check(label: str, condition: bool) -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    if not condition:
        raise SystemExit(1)


async def main() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as session:
        user = User(telegram_id=1, first_name="A", language=UserLanguage.EN)
        session.add(user)
        await session.flush()

        payment = await PaymentService(session).create(
            user_id=user.id, amount=299.0, gateway=PaymentGateway.CHAPA,
            payment_type=PaymentType.VIP, plan="one_month", reference="tx-seq-1",
        )
        await session.commit()
        payment_svc = PaymentService(session)

        # 1 & 2: claim, then re-claim the same row.
        won_first = await payment_svc.try_claim_pending(payment.id)
        check("first claim on a PENDING payment succeeds", won_first is True)

        won_second = await payment_svc.try_claim_pending(payment.id)
        check("second claim on the same now-APPROVED payment fails", won_second is False)
        await session.commit()

    async with Session() as session:
        fresh = await session.get(Payment, payment.id)
        check("status actually persisted as APPROVED", fresh.status == PaymentStatus.APPROVED)
        check("resolved_at was actually set", fresh.resolved_at is not None)

    # 3: a payment that never was PENDING (already REJECTED) can't be claimed.
    async with Session() as session:
        user2 = User(telegram_id=2, first_name="B", language=UserLanguage.EN)
        session.add(user2)
        await session.flush()

        rejected = await PaymentService(session).create(
            user_id=user2.id, amount=50.0, gateway=PaymentGateway.CHAPA,
            payment_type=PaymentType.WALLET_TOPUP, reference="tx-rejected-1",
        )
        await PaymentService(session).reject(rejected.id, note="test")
        await session.commit()

        claimed = await PaymentService(session).try_claim_pending(rejected.id)
        check("a REJECTED payment cannot be claimed", claimed is False)

    await engine.dispose()
    print("\nAll Chapa idempotency checks passed.")


asyncio.run(main())

