import urllib.parse

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


def resolve_store_logo(store_name: str, target_url: str = "", custom_logo: str = "", domain: str = "") -> str:
    """बिना हार्डकोड के स्टोर/ऐप के नाम या URL से अपने-आप Google Favicon लोगो URL बनाता है।"""
    clean_custom = str(custom_logo or "").strip()
    if clean_custom.startswith(("http://", "https://")):
        return clean_custom

    clean_domain = str(domain or "").strip().lower().replace("https://", "").replace("http://", "").split("/")[0].replace("www.", "")
    if clean_domain and "." in clean_domain:
        return f"https://www.google.com/s2/favicons?domain={urllib.parse.quote(clean_domain)}&sz=128"

    parsed_host = urllib.parse.urlparse(str(target_url or "").strip()).netloc.lower().replace("www.", "").strip()
    if parsed_host and "." in parsed_host:
        return f"https://www.google.com/s2/favicons?domain={urllib.parse.quote(parsed_host)}&sz=128"

    slug = "".join(ch for ch in str(store_name or "").strip().lower() if ch.isalnum())
    if slug:
        return f"https://www.google.com/s2/favicons?domain={urllib.parse.quote(slug + '.com')}&sz=128"

    return ""


def get_active_stores():
    """केवल उन्हीं स्टोर्स की लिस्ट लौटाता है जिनमें लिंक डाला जा चुका है, और हर स्टोर का लोगो अपने-आप जोड़ता है।"""
    active = []
    for store in AFFILIATE_STORES:
        url = str(store.get("url") or "").strip()
        if not url:
            continue
        item = dict(store)
        item["logo"] = resolve_store_logo(
            store_name=item.get("name", ""),
            target_url=url,
            custom_logo=item.get("logo", ""),
            domain=item.get("domain", ""),
        )
        active.append(item)
    return active


def get_all_store_slots():
    """सभी स्टोर स्लॉट्स (भरे हुए और खाली) लौटाता है।"""
    return AFFILIATE_STORES
