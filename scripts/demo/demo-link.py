import asyncio
import os
import sys
import uuid

sys.path.insert(0, os.getcwd())
from familyos import db, identity

MEMBER = uuid.UUID("049ba7b1-253f-41bb-922f-e35ffa22c24c")
async def main():
    pool = await db.connect()
    async with pool.acquire() as conn:
        raw = await identity._issue_link(conn, MEMBER, purpose="sign_in")
    await pool.close()
    open(os.environ["OUT"], "w").write(raw)
asyncio.run(main())
