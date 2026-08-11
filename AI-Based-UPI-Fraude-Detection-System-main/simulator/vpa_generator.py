import random

BANKS = ["oksbi", "ybl", "ibl", "okaxis", "paytm", "upi", "okhdfcbank"]

FIRST_NAMES = [
    "rahul", "priya", "amit", "sneha", "vikram", "pooja", "arjun",
    "divya", "rohit", "kavya", "suresh", "meera", "aakash", "nisha",
    "deepak", "anjali", "rajesh", "sita", "mohan", "lakshmi"
]

MERCHANTS = [
    "amazon", "flipkart", "zomato", "swiggy", "bigbasket",
    "myntra", "ajio", "nykaa", "phonepe", "paytmmall",
    "jiomart", "blinkit", "zepto", "dunzo", "meesho"
]

# 🔥 PRE-GENERATED POOLS (NO LOOPS AT RUNTIME)
_USER_VPA_POOL = [
    f"{name}{i}@{bank}"
    for i in range(100, 5100)          # 5000 users
    for name in FIRST_NAMES[:10]       # reduce combinations
    for bank in BANKS[:3]              # limit banks for speed
]

_MERCHANT_VPA_POOL = [
    f"{merchant}@{bank}"
    for merchant in MERCHANTS
    for bank in BANKS[:3]
]

_ACTIVE_USER_POOL = _USER_VPA_POOL[:200]
_ACTIVE_MERCHANT_POOL = _MERCHANT_VPA_POOL[:50]

print(f"✅ User VPA pool size: {len(_USER_VPA_POOL)}")
print(f"✅ Merchant VPA pool size: {len(_MERCHANT_VPA_POOL)}")


# ================= FAST SAMPLING =================
def generate_user_vpa():
    if random.random() < 0.8:
        return random.choice(_ACTIVE_USER_POOL)
    return random.choice(_USER_VPA_POOL)

def generate_merchant_vpa():
    if random.random() < 0.8:
        return random.choice(_ACTIVE_MERCHANT_POOL)
    return random.choice(_MERCHANT_VPA_POOL)


# ================= SIMILAR VPA =================
def generate_similar_vpa(legit_vpa):
    substitutions = {"o": "0", "i": "1", "l": "1", "a": "4", "e": "3"}

    name, _ = legit_vpa.split("@")

    mutated = "".join(
        substitutions.get(ch, ch) if random.random() < 0.3 else ch
        for ch in name
    )

    return f"{mutated}@{random.choice(BANKS)}"