"""Built-in price guide, used when no AI key is set or the AI call fails.

These are rough starting points for a direct-from-farm sale in mid-Michigan.
They are NOT market data. Edit them to match your local market, or later replace
`fallback_draft` with a model trained on real sales from the `listings` table
(see README: "Next step: train your own price model").
"""

CATEGORIES = ["Vegetables", "Fruit", "Eggs & dairy", "Meat", "Honey & preserves", "Flowers", "Other"]
UNITS = ["lb", "dozen", "bunch", "pint", "quart", "peck", "bushel", "each"]

# keyword -> (category, unit, low, typical, high)
GUIDE = {
    "apple":     ("Fruit", "lb", 1.50, 2.25, 3.00),
    "pear":      ("Fruit", "lb", 1.75, 2.50, 3.25),
    "peach":     ("Fruit", "lb", 2.50, 3.25, 4.00),
    "cherr":     ("Fruit", "pint", 4.00, 5.00, 6.50),
    "blueberr":  ("Fruit", "pint", 4.00, 5.00, 6.00),
    "strawberr": ("Fruit", "quart", 5.00, 6.50, 8.00),
    "raspberr":  ("Fruit", "pint", 5.00, 6.00, 7.50),
    "melon":     ("Fruit", "each", 3.00, 4.00, 6.00),
    "tomato":    ("Vegetables", "lb", 2.00, 3.00, 4.50),
    "potato":    ("Vegetables", "lb", 0.80, 1.25, 2.00),
    "onion":     ("Vegetables", "lb", 1.00, 1.50, 2.25),
    "carrot":    ("Vegetables", "bunch", 2.00, 3.00, 4.00),
    "corn":      ("Vegetables", "dozen", 5.00, 6.00, 8.00),
    "squash":    ("Vegetables", "each", 1.50, 2.00, 3.50),
    "pumpkin":   ("Vegetables", "each", 3.00, 5.00, 10.00),
    "lettuce":   ("Vegetables", "each", 2.00, 3.00, 4.00),
    "kale":      ("Vegetables", "bunch", 2.00, 3.00, 4.00),
    "pepper":    ("Vegetables", "lb", 2.00, 3.00, 4.50),
    "cucumber":  ("Vegetables", "each", 0.75, 1.00, 1.50),
    "bean":      ("Vegetables", "lb", 2.50, 3.50, 4.50),
    "garlic":    ("Vegetables", "each", 1.00, 1.50, 2.50),
    "egg":       ("Eggs & dairy", "dozen", 4.00, 5.00, 7.00),
    "milk":      ("Eggs & dairy", "quart", 3.00, 4.00, 6.00),
    "cheese":    ("Eggs & dairy", "lb", 8.00, 12.00, 18.00),
    "beef":      ("Meat", "lb", 6.00, 9.00, 14.00),
    "pork":      ("Meat", "lb", 5.00, 7.00, 10.00),
    "chicken":   ("Meat", "lb", 4.00, 5.50, 7.00),
    "honey":     ("Honey & preserves", "pint", 8.00, 12.00, 16.00),
    "maple":     ("Honey & preserves", "pint", 10.00, 14.00, 18.00),
    "jam":       ("Honey & preserves", "each", 5.00, 7.00, 9.00),
    "flower":    ("Flowers", "bunch", 8.00, 12.00, 20.00),
    "sunflower": ("Flowers", "bunch", 6.00, 10.00, 15.00),
}


def fallback_draft(notes: str) -> dict:
    text = (notes or "").lower()
    match = next((k for k in GUIDE if k in text), None)
    if match:
        cat, unit, lo, mid, hi = GUIDE[match]
        reason = "Based on the built-in mid-Michigan price guide. Adjust for your quality and market."
    else:
        cat, unit, lo, mid, hi = "Other", "each", 2.00, 3.00, 5.00
        reason = "No match in the built-in price guide, so this is a generic placeholder. Set your own price."
    first_line = (notes or "Fresh local produce").strip().split("\n")[0]
    return {
        "title": first_line[:40].strip().capitalize(),
        "description": (notes or "").strip()[:300] or "Fresh from our farm this week.",
        "category": cat, "unit": unit,
        "price": mid, "price_low": lo, "price_high": hi,
        "price_reason": reason,
        "freshness": "",
    }
