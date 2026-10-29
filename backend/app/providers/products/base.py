"""Abstract product provider interface for Family OS."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class ProductResult(BaseModel):
    """Normalised product result returned by any product provider."""

    provider_product_id: str
    title: str
    brand: Optional[str] = None
    price_amount: Optional[float] = None
    currency: str = "INR"
    merchant: Optional[str] = None
    product_url: Optional[str] = None
    image_url: Optional[str] = None
    availability: Optional[str] = None
    delivery_estimate: Optional[str] = None
    warranty_details: Optional[str] = None
    return_details: Optional[str] = None
    specifications: Dict[str, Any] = {}
    source_type: str = "DEVELOPMENT_CATALOGUE"
    category: Optional[str] = None


class BaseProductProvider(ABC):
    """Abstract base for all product search providers."""

    @abstractmethod
    async def search(
        self,
        category: str,
        query: str,
        budget_amount: Optional[float] = None,
        currency: str = "INR",
        brand_preference: Optional[List[str]] = None,
        required_specs: Optional[Dict[str, Any]] = None,
        limit: int = 10,
    ) -> List[ProductResult]:
        """Search for products matching the given intent.

        Args:
            category: Product category (e.g. ``'MOUSE'``, ``'LAPTOP'``).
            query: Free-text query string.
            budget_amount: Maximum acceptable price.
            currency: ISO-4217 currency code (default ``'INR'``).
            brand_preference: Preferred brand names, in priority order.
            required_specs: Key/value pairs that the product must satisfy.
            limit: Maximum number of results to return.

        Returns:
            List of :class:`ProductResult` sorted by relevance / price.
        """

    @abstractmethod
    async def is_available(self) -> bool:
        """Return ``True`` if the provider is ready to serve requests."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable name of this provider."""
