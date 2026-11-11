import requests

VCOMMISSION_API_KEY = "6af364581ba6729dae93901dcf56af364581ba95"
AFFILIATE_ID = "133696"

def get_all_campaigns():
    all_formatted_campaigns = []
    seen_ids = set()
    page = 1
    
    while True:
        trackier_url = f"https://api.trackier.com/v2/publisher/campaigns?apiKey={VCOMMISSION_API_KEY}&page={page}&limit=50"
        try:
            headers = {"Authorization": VCOMMISSION_API_KEY, "Accept": "application/json"}
            response = requests.get(trackier_url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                campaigns_data = data.get("data", {})
                
                campaigns = []
                if isinstance(campaigns_data, dict):
                    campaigns = campaigns_data.get("campaigns", [])
                elif isinstance(campaigns_data, list):
                    campaigns = campaigns_data
                
                if not campaigns:
                    break
                
                for camp in campaigns:
                    raw_name = camp.get("title") or camp.get("name") or "Unknown Store"
                    offer_id = str(camp.get("id") or camp.get("campaign_id") or "")
                    
                    if not offer_id or offer_id in seen_ids:
                        continue
                        
                    clean_name = raw_name.split(".com")[0].split(" Ecommerce")[0].split(" -")[0].strip()
                    destination_url = camp.get("url") or camp.get("preview_url") or camp.get("previewUrl") or ""
                    
                    domain = ""
                    if destination_url and "://" in destination_url:
                        domain = destination_url.split("://")[1].split("/")[0].replace("www.", "")
                    else:
                        domain = clean_name.lower().replace(" ", "").replace("&", "") + ".com"
                    
                    logo_url = f"https://www.google.com/s2/favicons?domain={domain}&sz=128"
                    
                    base_url = f"https://www.{domain}" if not destination_url else destination_url
                    separator = "&" if "?" in base_url else "?"
                    tracking_link = f"{base_url}{separator}utm_source=vcommission&utm_medium={AFFILIATE_ID}_&utm_campaign=trk_{offer_id}&pub_id={AFFILIATE_ID}"
                    
                    seen_ids.add(offer_id)
                    all_formatted_campaigns.append({
                        "name": clean_name,
                        "logo": logo_url,
                        "link": tracking_link,
                        "network": "vCommission"
                    })
                
                if len(campaigns) < 50:
                    break
                page += 1
            else:
                break
        except Exception as e:
            print(f"Error fetching vCommission page {page}: {e}")
            break
            
    return all_formatted_campaigns
