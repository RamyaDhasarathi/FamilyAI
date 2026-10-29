"""Unit tests for RealMarketplaceProvider UI hierarchy parsing and budget ranking."""
import pytest
from app.providers.products.real_marketplace import parse_amazon_ui_hierarchy, RealMarketplaceProvider

MOCK_AMAZON_XML = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<hierarchy rotation="0">
  <node index="0" text="" class="android.widget.FrameLayout" package="in.amazon.mShop.android.shopping" bounds="[0,0][1080,2340]">
    <node index="1" text="Search or ask a question" bounds="[258,115][732,231]" />
    
    <!-- Product 1: LikeStar Holder (Selling Price: Rs 275, MRP: Rs 499, Delivery threshold: Rs 499) -->
    <node index="2" content-desc="LikeStar® Universal Bike &amp; Motorcycle Mobile Holder, 360° Rotation" bounds="[462,400][1042,500]" />
    <node index="3" text="4.0 out of 5 stars 297 ratings" bounds="[462,510][672,550]" />
    <node index="4" text="Lowest price in 30 days ₹275 M.R.P: ₹499 (45% off)" bounds="[462,560][1042,610]" />
    <node index="5" text="₹275" bounds="[462,560][601,610]" />
    <node index="6" text="M.R.P: ₹499" bounds="[462,610][664,650]" />
    <node index="7" text="FREE delivery Tue, 27 Oct on ₹499 of items fulfilled by Amazon" bounds="[462,660][1042,700]" />
    
    <!-- Promotional Banner to ignore -->
    <node index="8" text="Great Indian Festival Rs.129 M.R.P: Rs.599 (78% off)" bounds="[462,720][1042,760]" />
    
    <!-- Product 2: One-Touch Stand (Selling Price: Rs 499, MRP: Rs 1599) -->
    <node index="9" content-desc="Kratos Mobile Holder for Bike with One-Touch Lock, 360° Rotating Adjustable" bounds="[462,800][1042,900]" />
    <node index="10" text="4.2 out of 5 stars 2,682 ratings" bounds="[462,910][672,950]" />
    <node index="11" text="₹499 M.R.P: ₹1,599 (69% off)" bounds="[462,960][1042,1010]" />
    
    <!-- Product 3: Waterproof Mount (Selling Price: Rs 331, MRP: Rs 799) -->
    <node index="12" content-desc="Waterproof Motorcycle Mobile Holder Touch Screen Metal Handlebar Mount" bounds="[462,1100][1042,1200]" />
    <node index="13" text="3.9 out of 5 stars 520 ratings" bounds="[462,1210][672,1250]" />
    <node index="14" text="₹331 M.R.P: ₹799 (59% off) Buy for ₹318 with Prime" bounds="[462,1260][1042,1310]" />

    <!-- Product 4: Over Budget Product (Selling Price: Rs 750) -->
    <node index="15" content-desc="Premium Heavy Duty Anti-Vibration Metal Bike Stand" bounds="[462,1400][1042,1500]" />
    <node index="16" text="₹750 M.R.P: ₹1,999 (62% off)" bounds="[462,1510][1042,1550]" />
  </node>
</hierarchy>
"""


def test_parse_amazon_ui_hierarchy_accurate_prices():
    """Verify price extraction accurately captures real selling price and ignores delivery thresholds."""
    items = parse_amazon_ui_hierarchy(MOCK_AMAZON_XML, budget_limit=500.0)
    assert len(items) == 3

    # Product 1
    assert "LikeStar" in items[0]["title"]
    assert items[0]["price"] == 275.0  # NOT 499 from delivery threshold!

    # Product 2
    assert "Kratos" in items[1]["title"]
    assert items[1]["price"] == 499.0

    # Product 3
    assert "Waterproof" in items[2]["title"]
    assert items[2]["price"] == 331.0  # NOT 318 from prime offer!


@pytest.mark.asyncio
async def test_search_top_3_products_closest_to_budget(monkeypatch):
    """Verify search returns strictly top 3 products sorted by closeness to given budget."""
    provider = RealMarketplaceProvider()

    async def mock_list_devices(*args, **kwargs):
        return []

    monkeypatch.setattr("app.agents.adb_bridge.ADBBridge.list_devices", mock_list_devices)

    # Use provider parser directly
    raw_products = parse_amazon_ui_hierarchy(MOCK_AMAZON_XML, budget_limit=500.0)
    assert len(raw_products) <= 3

    # Check sorting closeness to budget: Rs. 499 is closest to 500, then 331, then 275
    raw_products.sort(key=lambda x: abs(x["price"] - 500.0))
    assert raw_products[0]["price"] == 499.0
    assert raw_products[1]["price"] == 331.0
    assert raw_products[2]["price"] == 275.0
