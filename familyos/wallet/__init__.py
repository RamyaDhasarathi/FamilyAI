"""The optional family wallet. The rest of FamilyOS touches this package in one place: `register(app)` in main.create_app. The contract is in docs/wallet.md."""
from __future__ import annotations


def register(app) -> None:
    from familyos import audit
    from familyos.wallet import routes, service
    app.include_router(routes.router)
    audit.SAY_HOOKS["wallet"] = service.say
