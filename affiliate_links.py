# यहाँ सभी ऐप्स और स्टोर्स के एफिलिएट / प्रॉफ़िट लिंक्स रखे गए हैं।
# जब भी नया लिंक बने, बस संबंधित स्टोर की लाइन में लिंक पेस्ट कर दें।

AFFILIATE_STORES = [
    {
        "id": "myntra",
        "name": "Myntra",
        "source": "EarnKaro",
        "badge": "Active Link",
        "url": "https://myntr.it/LlapLAs",
    },
    {
        "id": "amazon",
        "name": "Amazon",
        "source": "Amazon Associates (commissionclo-21)",
        "badge": "Tag Ready",
        "url": "",  # यहाँ अपना commissionclo-21 वाला तैयार लिंक पेस्ट करें
    },
    {
        "id": "meesho",
        "name": "Meesho",
        "source": "EarnKaro",
        "badge": "Paste Link",
        "url": "",  # EarnKaro से लिंक बनने पर यहाँ पेस्ट करें
    },
    {
        "id": "flipkart",
        "name": "Flipkart",
        "source": "EarnKaro",
        "badge": "Paste Link",
        "url": "",  # EarnKaro से लिंक बनने पर यहाँ पेस्ट करें
    },
    # नीचे और ज़्यादा ऐप्स/स्टोर्स जोड़ने के लिए इसी तरह नए ब्लॉक पेस्ट करते जाएं:
    # {
    #     "id": "ajio",
    #     "name": "AJIO",
    #     "source": "EarnKaro",
    #     "badge": "Paste Link",
    #     "url": "",
    # },
]


def get_active_stores():
    """केवल उन्हीं स्टोर्स की लिस्ट लौटाता है जिनमें लिंक डाला जा चुका है।"""
    return [store for store in AFFILIATE_STORES if str(store.get("url") or "").strip()]


def get_all_store_slots():
    """सभी स्टोर स्लॉट्स (भरे हुए और खाली) लौटाता है।"""
    return AFFILIATE_STORES
