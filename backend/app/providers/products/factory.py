"""Factory for product providers."""
from __future__ import annotations

from app.core.config import get_settings
from app.providers.products.base import BaseProductProvider
from app.providers.products.development_catalogue import DevelopmentCatalogueProvider
from app.providers.products.real_marketplace import RealMarketplaceProvider

_product_provider: BaseProductProvider | None = None


def get_product_provider() -> BaseProductProvider:
    settings = get_settings()
    if settings.PRODUCT_PROVIDER == "development_catalogue":
        return DevelopmentCatalogueProvider()
    return RealMarketplaceProvider()
