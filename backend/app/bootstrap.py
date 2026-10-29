"""Command-line script to bootstrap the initial family and administrator."""
from __future__ import annotations

import asyncio
import os
import sys

# Ensure backend root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import get_settings
from app.db.session import get_session_factory
from app.services.auth_service import AuthService


async def run_bootstrap():
    settings = get_settings()
    print("=" * 60)
    print("Family OS — Bootstrap Initial Family & Admin")
    print("=" * 60)

    email = os.getenv("BOOTSTRAP_ADMIN_EMAIL", settings.BOOTSTRAP_ADMIN_EMAIL)
    password = os.getenv("BOOTSTRAP_ADMIN_PASSWORD", settings.BOOTSTRAP_ADMIN_PASSWORD)
    display_name = os.getenv("BOOTSTRAP_ADMIN_DISPLAY_NAME", settings.BOOTSTRAP_ADMIN_DISPLAY_NAME)
    family_name = os.getenv("BOOTSTRAP_FAMILY_NAME", settings.BOOTSTRAP_FAMILY_NAME)
    token = os.getenv("BOOTSTRAP_TOKEN", settings.BOOTSTRAP_TOKEN)

    if not token or token.startswith("REPLACE_"):
        print("Error: BOOTSTRAP_TOKEN environment variable must be set.")
        sys.exit(1)

    factory = get_session_factory()
    async with factory() as session:
        auth_service = AuthService()
        try:
            result = await auth_service.bootstrap(
                db=session,
                bootstrap_token=token,
                email=email,
                password=password,
                display_name=display_name,
                family_name=family_name,
                correlation_id="cli_bootstrap",
            )
            print("Bootstrap successful!")
            print(f"Family ID:     {result['family_id']}")
            print(f"Family Name:   {result['family_name']}")
            print(f"Admin User ID: {result['user_id']}")
            print(f"Admin Email:   {email}")
            print(f"Role:          {result['family_role']}")
            print(f"Access Token:  {result['access_token'][:20]}...")
            print("=" * 60)
        except Exception as exc:
            print(f"Bootstrap failed: {exc}")
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run_bootstrap())
