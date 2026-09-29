"""Rotate envelope keys without passing key material on the command line."""

import argparse
import asyncio

from sqlalchemy import func, select

from app.core.api_key_crypto import KeyRing
from app.core.config import settings
from app.core.logging import setup_logging
from app.database.session import async_session_local
from app.models import UserKeyEnvelope
from app.services.api_key_service import ApiKeyService


async def _user_ids(after: int) -> list[int]:
    async with async_session_local() as db:
        return list((await db.scalars(
            select(UserKeyEnvelope.user_id)
            .where(UserKeyEnvelope.user_id > after)
            .order_by(UserKeyEnvelope.user_id)
            .limit(100)
        )).all())


async def _remaining(target_version: str) -> int:
    async with async_session_local() as db:
        return int(await db.scalar(
            select(func.count()).select_from(UserKeyEnvelope)
            .where(UserKeyEnvelope.kek_version != target_version)
        ) or 0)


async def _run(args: argparse.Namespace) -> None:
    ring = KeyRing.from_settings(settings)
    service = ApiKeyService(async_session_local, ring)
    actor = "service:rotation"
    if args.mode == "dek":
        updated = await service.rotate_user_dek(args.user_id, actor=actor)
        print(f"Users processed: 1; updated: {int(updated)}")
        return

    target = args.target_version or ring.active_version
    ring.key_for(target)
    processed = updated = cursor = 0
    if args.user_id is not None:
        processed = 1
        updated = int(await service.rewrap_user_dek(args.user_id, actor=actor, target_kek_version=target))
    else:
        while batch := await _user_ids(cursor):
            for user_id in batch:
                updated += int(await service.rewrap_user_dek(user_id, actor=actor, target_kek_version=target))
                processed += 1
            cursor = batch[-1]
    print(f"Users processed: {processed}; updated: {updated}; remaining on other KEK versions: {await _remaining(target)}")


def main() -> None:
    setup_logging()
    parser = argparse.ArgumentParser(description="Rewrap user DEKs or rotate one user's DEK")
    parser.add_argument("mode", choices=("kek", "dek"))
    parser.add_argument("--user-id", type=int)
    parser.add_argument("--target-version", help="KEK version already present in API_KEY_KEKS")
    args = parser.parse_args()
    if args.mode == "dek" and args.user_id is None:
        parser.error("dek rotation requires --user-id")
    if args.mode == "dek" and args.target_version is not None:
        parser.error("--target-version only applies to kek rotation")
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
