"""Development product catalogue — realistic fixture data for Family OS."""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from app.providers.products.base import BaseProductProvider, ProductResult

# ---------------------------------------------------------------------------
# Catalogue data
# ---------------------------------------------------------------------------

_COMMON = {
    "source_type": "DEVELOPMENT_CATALOGUE",
    "availability": "In Stock",
    "delivery_estimate": "3-5 business days",
    "warranty_details": "1 year manufacturer warranty",
    "return_details": "10 days return policy",
}


_CATALOGUE: List[Dict[str, Any]] = [
    # ── MOUSE ────────────────────────────────────────────────────────────────
    {
        "provider_product_id": "DEV-MOUSE-001",
        "title": "Logitech M235 Wireless Mouse",
        "brand": "Logitech",
        "price_amount": 895.0,
        "currency": "INR",
        "merchant": "Development Catalogue",
        "product_url": "https://dev.familyos.local/products/DEV-MOUSE-001",
        "category": "MOUSE",
        "specifications": {
            "DPI": "1000",
            "Battery": "AA",
            "Connection": "USB nano receiver",
            "Weight": "84g",
            "Ergonomic": "right-handed",
        },
        **_COMMON,
    },
    {
        "provider_product_id": "DEV-MOUSE-002",
        "title": "HP Wireless Mouse Z3700",
        "brand": "HP",
        "price_amount": 699.0,
        "currency": "INR",
        "merchant": "Development Catalogue",
        "product_url": "https://dev.familyos.local/products/DEV-MOUSE-002",
        "category": "MOUSE",
        "specifications": {
            "DPI": "1200",
            "Battery": "AAA",
            "Connection": "USB nano",
            "Color": "Blue",
        },
        **_COMMON,
    },
    {
        "provider_product_id": "DEV-MOUSE-003",
        "title": "Dell WM126 Wireless Mouse",
        "brand": "Dell",
        "price_amount": 799.0,
        "currency": "INR",
        "merchant": "Development Catalogue",
        "product_url": "https://dev.familyos.local/products/DEV-MOUSE-003",
        "category": "MOUSE",
        "specifications": {
            "DPI": "1000",
            "Battery": "AA",
            "Connection": "USB nano",
            "Color": "Black",
        },
        **_COMMON,
    },
    {
        "provider_product_id": "DEV-MOUSE-004",
        "title": "Logitech M590 Silent Wireless Mouse",
        "brand": "Logitech",
        "price_amount": 1499.0,
        "currency": "INR",
        "merchant": "Development Catalogue",
        "product_url": "https://dev.familyos.local/products/DEV-MOUSE-004",
        "category": "MOUSE",
        "specifications": {
            "DPI": "1000",
            "Buttons": "7",
            "Connection": "USB/Bluetooth dual",
            "Silent": "true",
        },
        **_COMMON,
    },
    {
        "provider_product_id": "DEV-MOUSE-005",
        "title": "AmazonBasics Wireless Mouse",
        "brand": "AmazonBasics",
        "price_amount": 549.0,
        "currency": "INR",
        "merchant": "Development Catalogue",
        "product_url": "https://dev.familyos.local/products/DEV-MOUSE-005",
        "category": "MOUSE",
        "specifications": {
            "DPI": "1600",
            "Connection": "USB nano",
            "Battery": "AA",
        },
        **_COMMON,
    },
    # ── LAPTOP ───────────────────────────────────────────────────────────────
    {
        "provider_product_id": "DEV-LAPTOP-001",
        "title": "HP Pavilion 15",
        "brand": "HP",
        "price_amount": 45000.0,
        "currency": "INR",
        "merchant": "Development Catalogue",
        "product_url": "https://dev.familyos.local/products/DEV-LAPTOP-001",
        "category": "LAPTOP",
        "specifications": {
            "RAM": "8GB",
            "Storage": "512GB SSD",
            "Processor": "AMD Ryzen 5",
            "Display": "15.6 inch FHD",
            "Battery": "8hr",
        },
        **_COMMON,
    },
    {
        "provider_product_id": "DEV-LAPTOP-002",
        "title": "Lenovo IdeaPad 3",
        "brand": "Lenovo",
        "price_amount": 38000.0,
        "currency": "INR",
        "merchant": "Development Catalogue",
        "product_url": "https://dev.familyos.local/products/DEV-LAPTOP-002",
        "category": "LAPTOP",
        "specifications": {
            "RAM": "8GB",
            "Storage": "256GB SSD",
            "Processor": "Intel i3",
            "Display": "15.6 inch",
            "Battery": "7hr",
        },
        **_COMMON,
    },
    {
        "provider_product_id": "DEV-LAPTOP-003",
        "title": "Dell Inspiron 15",
        "brand": "Dell",
        "price_amount": 52000.0,
        "currency": "INR",
        "merchant": "Development Catalogue",
        "product_url": "https://dev.familyos.local/products/DEV-LAPTOP-003",
        "category": "LAPTOP",
        "specifications": {
            "RAM": "16GB",
            "Storage": "512GB SSD",
            "Processor": "Intel i5",
            "Display": "15.6 inch FHD",
            "Battery": "6hr",
        },
        **_COMMON,
    },
    # ── WASHING_MACHINE ───────────────────────────────────────────────────────
    {
        "provider_product_id": "DEV-WM-001",
        "title": "Samsung 6.5kg Front Load Washing Machine",
        "brand": "Samsung",
        "price_amount": 28000.0,
        "currency": "INR",
        "merchant": "Development Catalogue",
        "product_url": "https://dev.familyos.local/products/DEV-WM-001",
        "category": "WASHING_MACHINE",
        "specifications": {
            "Capacity": "6.5kg",
            "Type": "Front Load",
            "Programs": "15",
            "Energy": "5 star",
            "RPM": "1000",
        },
        **_COMMON,
    },
    {
        "provider_product_id": "DEV-WM-002",
        "title": "LG 7kg Top Load Washing Machine",
        "brand": "LG",
        "price_amount": 22000.0,
        "currency": "INR",
        "merchant": "Development Catalogue",
        "product_url": "https://dev.familyos.local/products/DEV-WM-002",
        "category": "WASHING_MACHINE",
        "specifications": {
            "Capacity": "7kg",
            "Type": "Top Load",
            "Programs": "8",
            "Energy": "4 star",
        },
        **_COMMON,
    },
    {
        "provider_product_id": "DEV-WM-003",
        "title": "Whirlpool 7.5kg Top Load Washing Machine",
        "brand": "Whirlpool",
        "price_amount": 19500.0,
        "currency": "INR",
        "merchant": "Development Catalogue",
        "product_url": "https://dev.familyos.local/products/DEV-WM-003",
        "category": "WASHING_MACHINE",
        "specifications": {
            "Capacity": "7.5kg",
            "Type": "Top Load",
            "Programs": "6",
            "Energy": "5 star",
        },
        **_COMMON,
    },
    # ── BACKPACK ─────────────────────────────────────────────────────────────
    {
        "provider_product_id": "DEV-BAG-001",
        "title": "Wildcraft 30L School Bag",
        "brand": "Wildcraft",
        "price_amount": 899.0,
        "currency": "INR",
        "merchant": "Development Catalogue",
        "product_url": "https://dev.familyos.local/products/DEV-BAG-001",
        "category": "BACKPACK",
        "specifications": {
            "Capacity": "30L",
            "Material": "Polyester",
            "Compartments": "3",
            "Waterproof": "yes",
        },
        **_COMMON,
    },
    {
        "provider_product_id": "DEV-BAG-002",
        "title": "American Tourister 32L Backpack",
        "brand": "American Tourister",
        "price_amount": 1499.0,
        "currency": "INR",
        "merchant": "Development Catalogue",
        "product_url": "https://dev.familyos.local/products/DEV-BAG-002",
        "category": "BACKPACK",
        "specifications": {
            "Capacity": "32L",
            "Material": "Polyester",
            "Laptop compartment": "yes",
        },
        **_COMMON,
    },
    # ── HEADPHONES / EARBUDS ────────────────────────────────────────────────
    {
        "provider_product_id": "DEV-HEAD-001",
        "title": "Noise Master Buds 2 with Sound by Bose Truly Wireless Earbuds (2026), 51dB Adaptive ANC",
        "brand": "Noise",
        "price_amount": 1699.0,
        "currency": "INR",
        "merchant": "Amazon India",
        "product_url": "https://www.amazon.in/dp/B0D1EXAMPLE1",
        "category": "HEADPHONES",
        "specifications": {
            "Noise Cancellation": "51dB Adaptive ANC",
            "Sound": "Sound by Bose, Hi-Res Audio",
            "Mics": "6-mic ENC",
            "Battery": "40 hours total playtime",
        },
        **_COMMON,
    },
    {
        "provider_product_id": "DEV-HEAD-002",
        "title": "boAt Airdopes 141 ANC Truly Wireless Earbuds with 32dB ANC, 42H Playback",
        "brand": "boAt",
        "price_amount": 1499.0,
        "currency": "INR",
        "merchant": "Amazon India",
        "product_url": "https://www.amazon.in/dp/B0D1EXAMPLE2",
        "category": "HEADPHONES",
        "specifications": {
            "Noise Cancellation": "32dB ANC",
            "Battery": "42H playback",
            "Driver": "10mm drivers",
            "Fast Charge": "10 mins = 150 mins",
        },
        **_COMMON,
    },
    {
        "provider_product_id": "DEV-HEAD-003",
        "title": "Sony WH-CH520 Wireless Bluetooth On-Ear Headphones with DSEE and 50H Battery",
        "brand": "Sony",
        "price_amount": 3990.0,
        "currency": "INR",
        "merchant": "Amazon India",
        "product_url": "https://www.amazon.in/dp/B0D1EXAMPLE3",
        "category": "HEADPHONES",
        "specifications": {
            "Form Factor": "On-Ear",
            "Battery": "Up to 50 hours",
            "Microphone": "Built-in for hands-free calling",
            "Custom EQ": "Supported via Sony Headphones Connect App",
        },
        **_COMMON,
    },
    # ── SMARTWATCH ───────────────────────────────────────────────────────────
    {
        "provider_product_id": "DEV-WATCH-001",
        "title": "Noise Pulse 2 Max 1.85\" TFT LCD Bluetooth Calling Smartwatch",
        "brand": "Noise",
        "price_amount": 1299.0,
        "currency": "INR",
        "merchant": "Amazon India",
        "product_url": "https://www.amazon.in/dp/B0D1EXAMPLE4",
        "category": "SMARTWATCH",
        "specifications": {
            "Display": "1.85 inch 550 nits brightness",
            "Calling": "Bluetooth Calling with built-in mic & speaker",
            "Sports Modes": "100+ sports modes",
            "Battery": "10 days normal use",
        },
        **_COMMON,
    },
]


# ---------------------------------------------------------------------------
# Provider implementation
# ---------------------------------------------------------------------------


class DevelopmentCatalogueProvider(BaseProductProvider):
    """In-memory product catalogue for development and testing.

    All products are statically defined and returned synchronously (wrapped in
    ``async`` to satisfy the :class:`BaseProductProvider` contract).
    """

    @property
    def provider_name(self) -> str:  # noqa: D102
        return "development_catalogue"

    async def is_available(self) -> bool:  # noqa: D102
        return True

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
        """Filter the static catalogue and return matching products.

        Filtering logic:
        1. Category keyword match (case-insensitive substring).
        2. Budget — product price must be ``<= budget_amount`` (if provided).
        3. Brand preference — preferred brands are boosted to the front
           (not a hard filter).
        Results are sorted by price ascending, with preferred-brand items
        appearing before others at the same price tier.
        """
        import re
        import urllib.parse

        cat_lower = (category or "").lower().replace(" ", "_").replace("-", "_")
        brand_prefs_lower = [b.lower() for b in (brand_preference or [])]
        query_words = set(re.findall(r"\w+", (query or "").lower()))

        cat_matches: List[Dict[str, Any]] = []
        word_matches: List[Dict[str, Any]] = []

        for item in _CATALOGUE:
            item_cat = item.get("category", "").lower().replace(" ", "_")
            item_title_lower = (item.get("title") or "").lower()

            # Budget filter
            if budget_amount is not None:
                price = item.get("price_amount")
                if price is not None and price > (budget_amount * 1.05):
                    continue

            # Category match
            if bool(cat_lower) and (
                cat_lower in item_cat
                or item_cat in cat_lower
                or cat_lower in item_title_lower
            ):
                cat_matches.append(item)
            elif any(
                w in item_cat or w in item_title_lower
                for w in query_words
                if len(w) > 3 and w not in ("find", "search", "with", "from", "under", "want", "need", "best", "good", "wireless", "noise")
            ):
                word_matches.append(item)

        candidates = cat_matches if cat_matches else word_matches

        # Sort: preferred brands first, then price ascending.
        def _sort_key(p: Dict[str, Any]) -> tuple:
            brand = (p.get("brand") or "").lower()
            brand_rank = 0 if brand in brand_prefs_lower else 1
            price = p.get("price_amount") or 0
            return (brand_rank, price)

        candidates.sort(key=_sort_key)

        results = [
            ProductResult(
                provider_product_id=c["provider_product_id"],
                title=c["title"],
                brand=c.get("brand"),
                price_amount=c.get("price_amount"),
                currency=c.get("currency", "INR"),
                merchant=c.get("merchant"),
                product_url=c.get("product_url"),
                image_url=c.get("image_url"),
                availability=c.get("availability"),
                delivery_estimate=c.get("delivery_estimate"),
                warranty_details=c.get("warranty_details"),
                return_details=c.get("return_details"),
                specifications=c.get("specifications", {}),
                source_type=c.get("source_type", "DEVELOPMENT_CATALOGUE"),
                category=c.get("category"),
            )
            for c in candidates[:limit]
        ]
        return results
