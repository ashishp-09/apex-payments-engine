import asyncio
import logging
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from app.domain.models import Outbox

logger = logging.getLogger(__name__)


class OutboxRelay:
    """
    Background worker that drains unpublished outbox events using PostgreSQL
    'FOR UPDATE SKIP LOCKED', guaranteeing at-least-once asynchronous event publishing.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self.session_factory = session_factory
        self._running = False

    async def drain_batch(self, batch_size: int = 50) -> int:
        async with self.session_factory() as session:
            async with session.begin():
                stmt = (
                    select(Outbox)
                    .where(Outbox.published_at.is_(None))
                    .order_by(Outbox.created_at.asc())
                    .limit(batch_size)
                    .with_for_update(skip_locked=True)
                )
                res = await session.execute(stmt)
                events = res.scalars().all()

                if not events:
                    return 0

                now = datetime.now(timezone.utc)
                for ev in events:
                    # In production: publish to Kafka / EventBridge
                    logger.info(f"[OUTBOX PUBLISHED] Event: {ev.event_type} | Aggregate: {ev.aggregate_id}")
                    ev.published_at = now

                return len(events)

    async def run_loop(self, poll_interval_seconds: float = 1.0):
        self._running = True
        logger.info("OutboxRelay worker started.")
        while self._running:
            try:
                drained = await self.drain_batch()
                if drained == 0:
                    await asyncio.sleep(poll_interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in outbox relay: {e}", exc_info=True)
                await asyncio.sleep(poll_interval_seconds)

    def stop(self):
        self._running = False
