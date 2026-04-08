import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

AHREFS_BASE = "https://api.ahrefs.com/v3/site-explorer"


def _fetch_domain_metrics(api_key: str, domain: str) -> dict:
    """Fetch DR and organic traffic for a single domain from Ahrefs."""
    headers = {"Authorization": f"Bearer {api_key}"}
    today = date.today().isoformat()

    try:
        dr_resp = requests.get(
            f"{AHREFS_BASE}/domain-rating",
            headers=headers,
            params={"target": domain, "date": today},
            timeout=15,
        )
        dr_data = dr_resp.json() if dr_resp.ok else {}

        tr_resp = requests.get(
            f"{AHREFS_BASE}/metrics",
            headers=headers,
            params={"target": domain, "date": today, "mode": "subdomains"},
            timeout=15,
        )
        tr_data = tr_resp.json() if tr_resp.ok else {}

        return {
            "domain": domain,
            "dr": dr_data.get("domain_rating", {}).get("domain_rating"),
            "org_traffic": tr_data.get("metrics", {}).get("org_traffic"),
        }
    except Exception:
        return {"domain": domain, "dr": None, "org_traffic": None}


def enrich_with_ahrefs(api_key: str, domains: list) -> dict:
    """
    Fetch real DR and organic traffic from Ahrefs for a list of domains.
    Returns: {domain: {dr, org_traffic}}
    """
    result = {}
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {
            executor.submit(_fetch_domain_metrics, api_key, d): d for d in domains
        }
        for future in as_completed(futures):
            data = future.result()
            result[data["domain"]] = {
                "dr": data["dr"],
                "org_traffic": data["org_traffic"],
            }
    return result
