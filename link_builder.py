import pandas as pd

def get_all_categories(df: pd.DataFrame) -> list[str]:
    """Extract sorted unique categories from loaded dataframe."""
    cats = set()
    for raw in df["categories"].dropna():
        for cat in raw.split(","):
            cat = cat.strip()
            if cat:
                cats.add(cat)
    return sorted(cats)


def filter_by_categories(df: pd.DataFrame, selected: list[str]) -> pd.DataFrame:
    """Keep only sites that have at least one of the selected categories."""
    if not selected:
        return df
    selected_set = {c.lower() for c in selected}
    def matches(raw):
        return any(c.strip().lower() in selected_set for c in raw.split(","))
    mask = df["categories"].fillna("").apply(matches)
    return df[mask]


def apply_hard_filters(df: pd.DataFrame, criteria: dict) -> pd.DataFrame:
    """Apply mandatory threshold filters. Returns filtered copy."""
    mask = pd.Series(True, index=df.index)

    if criteria.get("dr_min") is not None:
        mask &= df["dr"] >= criteria["dr_min"]
    if criteria.get("organic_traffic_min") is not None:
        mask &= df["organic_traffic"] >= criteria["organic_traffic_min"]
    if criteria.get("pct_organic_min") is not None:
        mask &= df["pct_organic"] >= criteria["pct_organic_min"]
    if criteria.get("total_traffic_min") is not None:
        mask &= df["total_traffic"] >= criteria["total_traffic_min"]
    if criteria.get("ukraine_only"):
        mask &= df["country"].str.contains("Ukraine", case=False, na=False) | df["domain"].str.endswith(".ua")
    if criteria.get("price_max") is not None:
        mask &= df["price"] <= criteria["price_max"]
    if criteria.get("price_min") is not None:
        mask &= df["price"] >= criteria["price_min"]

    # Exclude already-used domains
    excluded = [d.strip().lower() for d in (criteria.get("excluded_domains") or []) if d.strip()]
    if excluded:
        mask &= ~df["domain"].str.lower().isin(excluded)

    # Red flag: very high DR + near-zero organic traffic (manipulated metrics)
    red_flag = (df["dr"] > 50) & (df["organic_traffic"] < 500)
    mask &= ~red_flag

    # Price must exist
    mask &= df["price"].notna()

    return df[mask].copy()


def score_sites(df: pd.DataFrame) -> pd.DataFrame:
    """Add quality score (DR + traffic only, no price). Higher = better quality."""
    df = df.copy()
    dr_max = df["dr"].max() or 1
    traffic_max = df["organic_traffic"].max() or 1

    df["score"] = (
        (df["dr"] / dr_max) * 0.50
        + (df["organic_traffic"] / traffic_max) * 0.50
    )
    return df


def select_donors(df: pd.DataFrame, quantity: int, budget: float) -> pd.DataFrame:
    """Select up to `quantity` donors whose cumulative price ≤ budget.
    Sorted by quality (DR + traffic) descending — best sites first,
    skip if individual price exceeds remaining budget."""
    df = df.sort_values("score", ascending=False).reset_index(drop=True)

    selected = []
    cumulative = 0.0

    for _, row in df.iterrows():
        if len(selected) >= quantity:
            break
        if row["price"] is None:
            continue
        if cumulative + row["price"] > budget:
            continue
        cumulative += row["price"]
        row = row.copy()
        row["cumulative_price"] = round(cumulative, 2)
        selected.append(row)

    return pd.DataFrame(selected) if selected else pd.DataFrame()


def build_why_suitable(row: pd.Series) -> str:
    parts = []
    if row["dr"] >= 40:
        parts.append(f"DR {int(row['dr'])} (відмінний)")
    elif row["dr"] >= 30:
        parts.append(f"DR {int(row['dr'])} (добрий)")
    else:
        parts.append(f"DR {int(row['dr'])}")

    ot = row["organic_traffic"]
    if ot >= 50_000:
        parts.append(f"органічний трафік {int(ot):,} (дуже високий)")
    elif ot >= 20_000:
        parts.append(f"органічний трафік {int(ot):,} (відмінний)")
    else:
        parts.append(f"органічний трафік {int(ot):,}")

    parts.append(f"ціна {int(row['price'])} грн")
    return "; ".join(parts)
