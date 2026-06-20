"""
Mock Swiggy MCP Server
-----------------------
A local fake MCP server that mimics Swiggy Food MCP tools
(search_restaurants, get_menu, get_addresses, create_cart)
so you can build/test your LangGraph agent without real Swiggy access.

Run:
    pip install fastmcp
    python server.py

This will start an HTTP MCP server at http://localhost:8001/mcp
"""

from fastmcp import FastMCP

mcp = FastMCP("mock-swiggy-food")

# ----------------------------
# Fake data
# ----------------------------

FAKE_RESTAURANTS = [
    {
        "restaurant_id": "r1",
        "name": "Green Bowl Kitchen",
        "cuisine": "Healthy, Salads, Bowls",
        "rating": 4.5,
        "price_for_two": 350,
        "eta_minutes": 28,
    },
    {
        "restaurant_id": "r2",
        "name": "Protein Punch",
        "cuisine": "High-Protein, Grilled, North Indian",
        "rating": 4.3,
        "price_for_two": 450,
        "eta_minutes": 35,
    },
    {
        "restaurant_id": "r3",
        "name": "Budget Bites",
        "cuisine": "North Indian, Thali, Combo Meals",
        "rating": 4.0,
        "price_for_two": 200,
        "eta_minutes": 25,
    },
]

FAKE_MENUS = {
    "r1": [
        {"item_id": "i1", "name": "Paneer Power Bowl", "price": 220, "protein_g": 28, "calories": 410},
        {"item_id": "i2", "name": "Quinoa Veggie Salad", "price": 190, "protein_g": 14, "calories": 320},
        {"item_id": "i3", "name": "Grilled Chicken Bowl", "price": 260, "protein_g": 35, "calories": 450},
    ],
    "r2": [
        {"item_id": "i4", "name": "Tandoori Chicken (Half)", "price": 280, "protein_g": 42, "calories": 480},
        {"item_id": "i5", "name": "Egg Bhurji with Roti", "price": 180, "protein_g": 24, "calories": 380},
        {"item_id": "i6", "name": "Soya Chaap Tikka", "price": 220, "protein_g": 30, "calories": 400},
    ],
    "r3": [
        {"item_id": "i7", "name": "Dal Rice Combo", "price": 120, "protein_g": 12, "calories": 520},
        {"item_id": "i8", "name": "Veg Thali", "price": 150, "protein_g": 15, "calories": 600},
        {"item_id": "i9", "name": "Chole Kulche", "price": 100, "protein_g": 10, "calories": 450},
    ],
}

FAKE_ADDRESSES = [
    {"address_id": "a1", "label": "Home", "line": "123 MG Road, Bengaluru"},
    {"address_id": "a2", "label": "Work", "line": "45 Tech Park, Whitefield"},
]


# ----------------------------
# Tools
# ----------------------------

@mcp.tool()
def get_addresses() -> list[dict]:
    """Get saved delivery addresses for the user."""
    return FAKE_ADDRESSES


@mcp.tool()
def search_restaurants(query: str = "", address_id: str = "a1") -> list[dict]:
    """
    Search restaurants near the given address.
    'query' can be a cuisine/keyword filter (e.g. 'protein', 'budget', 'healthy').
    """
    query = (query or "").lower()
    if not query:
        return FAKE_RESTAURANTS

    results = [
        r for r in FAKE_RESTAURANTS
        if query in r["name"].lower() or query in r["cuisine"].lower()
    ]
    return results or FAKE_RESTAURANTS


@mcp.tool()
def get_menu(restaurant_id: str) -> list[dict]:
    """Get menu items (with price, protein_g, calories) for a restaurant_id."""
    return FAKE_MENUS.get(restaurant_id, [])


@mcp.tool()
def create_cart(restaurant_id: str, item_ids: list[str], address_id: str = "a1") -> dict:
    """
    Create a cart with selected items from a restaurant.
    This is a MOCK - it does not place a real order.
    """
    menu = FAKE_MENUS.get(restaurant_id, [])
    items = [m for m in menu if m["item_id"] in item_ids]
    total = sum(i["price"] for i in items)
    return {
        "cart_id": f"mock_cart_{restaurant_id}",
        "restaurant_id": restaurant_id,
        "items": items,
        "total_price": total,
        "address_id": address_id,
        "status": "MOCK_CART_CREATED (not a real order)",
    }


if __name__ == "__main__":
    # Streamable HTTP transport, similar shape to Swiggy's real MCP servers
    mcp.run(transport="streamable-http", host="127.0.0.1", port=8001)
