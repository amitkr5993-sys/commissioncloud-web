import urllib.parse

# यहाँ सभी ऐप्स और स्टोर्स के एफिलिएट / प्रॉफ़िट लिंक्स रखे गए हैं।
# जब भी नया लिंक बने, बस संबंधित स्टोर की लाइन में लिंक पेस्ट कर दें।

# संभावित ब्रांड/स्टोर डोमेन मैपिंग ताकि नया स्टोर या लिंक जोड़ने पर अपने-आप सही लोगो मिले।
# बिना हार्डकोड किए भी यदि कोई नया नाम आए, तो resolve_store_logo अपने-आप नाम से डोमेन बनाकर लोगो निकाल लेगा।
KNOWN_STORE_DOMAINS = {
    "myntra": "myntra.com",
    "amazon": "amazon.in",
    "meesho": "meesho.com",
    "flipkart": "flipkart.com",
    "ajio": "ajio.com",
    "ajio direct": "ajio.com",
    "jiomart": "jiomart.com",
    "strch": "strch.in",
    "dot & key": "dotandkey.com",
    "dot & key store": "dotandkey.com",
    "blinkit": "blinkit.com",
    "agoda": "agoda.com",
    "air india": "airindia.com",
    "dell": "dell.com",
    "hamara mall": "hamaramall.com",
    "havells": "havells.com",
    "mivi": "mivi.in",
    "muscleblaze": "muscleblaze.com",
    "oppo": "oppo.com",
    "realme": "realme.com",
    "realme store": "realme.com",
    "shopsy": "shopsy.in",
    "shopsy store": "shopsy.in",
    "swiggy instamart": "swiggy.com",
    "instamart": "swiggy.com",
    "zandu care": "zanduayurveda.com",
    "zandu": "zanduayurveda.com",
    "truemeds": "truemeds.in",
    "truemeds store": "truemeds.in",
    "boat": "boat-lifestyle.com",
    "boat store": "boat-lifestyle.com",
}

AFFILIATE_STORES = [
    {
        "id": "myntra",
        "name": "Myntra",
        "domain": "myntra.com",
        "source": "EarnKaro",
        "badge": "Active Link",
        "url": "https://myntr.it/LlapLAs",
    },
    {
        "id": "amazon",
        "name": "Amazon",
        "domain": "amazon.in",
        "source": "Amazon Associates (commissionclo-21)",
        "badge": "Logo Ready",
        "url": "",
    },
    {
        "id": "meesho",
        "name": "Meesho",
        "domain": "meesho.com",
        "source": "EarnKaro",
        "badge": "Logo Ready",
        "url": "",
    },
    {
        "id": "flipkart",
        "name": "Flipkart",
        "domain": "flipkart.com",
        "source": "EarnKaro",
        "badge": "Logo Ready",
        "url": "",
    },
    {
        "id": "ajio",
        "name": "AJIO Direct",
        "domain": "ajio.com",
        "source": "Affiliate",
        "badge": "Active Link",
        "url": "https://ajiio.in/1lPbqQl",
    },
    {
        "id": "jiomart",
        "name": "JioMart",
        "domain": "jiomart.com",
        "source": "Affiliate",
        "badge": "Active Link",
        "url": "https://bitli.in/sSHJCpW",
    },
    {
        "id": "strch",
        "name": "Strch",
        "domain": "strch.in",
        "source": "Affiliate",
        "badge": "Active Link",
        "url": "https://bitli.in/2vzomZh",
    },
    {
        "id": "dot_and_key",
        "name": "Dot & Key Store",
        "domain": "dotandkey.com",
        "source": "Affiliate",
        "badge": "Active Link",
        "url": "https://bitli.in/F8jSEnN",
    },
    {
        "id": "blinkit",
        "name": "Blinkit",
        "domain": "blinkit.com",
        "source": "Affiliate",
        "badge": "Active Link",
        "url": "https://bitli.in/FkcmIPc",
    },
    {
        "id": "agoda",
        "name": "Agoda",
        "domain": "agoda.com",
        "source": "Affiliate",
        "badge": "Active Link",
        "url": "https://bitli.in/Tp3qLrd",
    },
    {
        "id": "air_india",
        "name": "Air India",
        "domain": "airindia.com",
        "source": "Affiliate",
        "badge": "Active Link",
        "url": "https://bitli.in/XSsddh8",
    },
    {
        "id": "dell",
        "name": "Dell",
        "domain": "dell.com",
        "source": "Affiliate",
        "badge": "Active Link",
        "url": "https://bitli.in/o5Yg8wg",
    },
    {
        "id": "hamara_mall",
        "name": "Hamara Mall",
        "domain": "hamaramall.com",
        "source": "Affiliate",
        "badge": "Active Link",
        "url": "https://bitli.in/u5fI6pv",
    },
    {
        "id": "havells",
        "name": "Havells",
        "domain": "havells.com",
        "source": "Affiliate",
        "badge": "Active Link",
        "url": "https://bitli.in/9d93h7D",
    },
    {
        "id": "mivi",
        "name": "Mivi",
        "domain": "mivi.in",
        "source": "Affiliate",
        "badge": "Active Link",
        "url": "https://bitli.in/ADbtog8",
    },
    {
        "id": "muscleblaze",
        "name": "MuscleBlaze",
        "domain": "muscleblaze.com",
        "source": "Affiliate",
        "badge": "Active Link",
        "url": "https://bitli.in/oji4VVi",
    },
    {
        "id": "oppo",
        "name": "Oppo",
        "domain": "oppo.com",
        "source": "Affiliate",
        "badge": "Active Link",
        "url": "https://bitli.in/stWRpy9",
    },
    {
        "id": "realme",
        "name": "Realme Store",
        "domain": "realme.com",
        "source": "Affiliate",
        "badge": "Active Link",
        "url": "https://bitli.in/jKsRxOr",
    },
    {
        "id": "shopsy",
        "name": "Shopsy Store",
        "domain": "shopsy.in",
        "source": "Affiliate",
        "badge": "Active Link",
        "url": "https://bitli.in/LfaJxVd",
    },
    {
        "id": "swiggy_instamart",
        "name": "Swiggy Instamart",
        "domain": "swiggy.com",
        "source": "Affiliate",
        "badge": "Active Link",
        "url": "https://bitli.in/4l4aOvi",
    },
    {
        "id": "zandu_care",
        "name": "Zandu Care",
        "domain": "zanduayurveda.com",
        "source": "Affiliate",
        "badge": "Active Link",
        "url": "https://bitli.in/Ky21Evt",
    },
    {
        "id": "truemeds",
        "name": "Truemeds Store",
        "domain": "truemeds.in",
        "source": "Affiliate",
        "badge": "Active Link",
        "url": "https://bitli.in/aFR9mvP",
    },
    {
        "id": "boat",
        "name": "BoAt store",
        "domain": "boat-lifestyle.com",
        "source": "Affiliate",
        "badge": "Logo Ready",
        "url": "https://bitli.in/hmoTfby",
    },
]


def _normalize_domain(raw_value: str) -> str:
    value = str(raw_value or "").strip().lower()
    if not value:
        return ""
    if "://" not in value:
        value = "https://" + value
    host = urllib.parse.urlparse(value).netloc.lower().strip()
    if host.startswith("www."):
        host = host[4:]
    return host


def resolve_store_logo(store_name: str, target_url: str = "", custom_logo: str = "", domain: str = "") -> str:
    """बिना हार्डकोड के स्टोर/ऐप के नाम, डोमेन या URL से अपने-आप Google Favicon लोगो URL बनाता है।"""
    clean_custom = str(custom_logo or "").strip()
    if clean_custom.startswith(("http://", "https://")):
        return clean_custom

    clean_domain = _normalize_domain(domain)
    if clean_domain and "." in clean_domain:
        return f"https://www.google.com/s2/favicons?domain={urllib.parse.quote(clean_domain)}&sz=128"

    normalized_name = " ".join(str(store_name or "").strip().lower().split())
    if normalized_name in KNOWN_STORE_DOMAINS:
        mapped_domain = KNOWN_STORE_DOMAINS[normalized_name]
        return f"https://www.google.com/s2/favicons?domain={urllib.parse.quote(mapped_domain)}&sz=128"

    parsed_host = _normalize_domain(target_url)
    if parsed_host and "." in parsed_host and parsed_host not in {"bitli.in", "myntr.it"}:
        return f"https://www.google.com/s2/favicons?domain={urllib.parse.quote(parsed_host)}&sz=128"

    slug = "".join(ch for ch in normalized_name if ch.isalnum())
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
    """सभी स्टोर स्लॉट्स (भरे हुए और खाली) लौटाता है, हर एक में अपने-आप लोगो जोड़कर।"""
    slots = []
    for store in AFFILIATE_STORES:
        item = dict(store)
        item["logo"] = resolve_store_logo(
            store_name=item.get("name", ""),
            target_url=item.get("url", ""),
            custom_logo=item.get("logo", ""),
            domain=item.get("domain", ""),
        )
        slots.append(item)
    return slots
