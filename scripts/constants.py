"""
constants.py — central place to store categories and other configuration constants.
Update CATEGORIES below with the canonical list when ready.
"""

# Human-readable categories block used by the normalizer prompt builder.
# Keep this as plain text; the normalizer consumes it verbatim for prompts.
CATEGORIES = """
- Food & Dining (subcategories: Restaurants, Food Delivery, Groceries, Cafes)
- Transport (subcategories: Cab, Metro/Bus, Fuel, Auto)
- Shopping (subcategories: Clothing, Electronics, Amazon/Flipkart, General)
- Utilities (subcategories: Electricity, Water, Internet, Mobile Recharge)
- Entertainment (subcategories: OTT/Streaming, Movies, Events, Gaming)
- Health (subcategories: Pharmacy, Hospital, Lab Tests, Gym)
- Finance (subcategories: EMI, Insurance, Investments, Bank Charges)
- Travel (subcategories: Flights, Hotels, Trains, Taxi)
- Education (subcategories: Courses, Books, Subscriptions)
- Income (subcategories: Salary, Freelance, Cashback, Refund)
- Transfer (subcategories: UPI Transfer, NEFT, Internal Transfer)
- Personal Care (subcategories: Salon, Spa)
- Charity & Gifts
- Other
"""
