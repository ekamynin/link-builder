import io
import pandas as pd
import streamlit as st

from collaborator_api import fetch_all_sites, parse_site
from link_builder import (
    NICHES,
    apply_hard_filters,
    build_why_suitable,
    filter_by_niche,
    score_sites,
    select_donors,
)

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Link Builder | Collaborator",
    page_icon="🔗",
    layout="wide",
)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ Налаштування API")
    api_key = st.text_input(
        "Collaborator API Key",
        value="hH0Zieka-iOKh-gLoJonsRYU0-MxOXXAFsnHjxw0ZII2N9PFgYwa72fXSOAM8DXT",
        type="password",
    )
    st.divider()
    st.markdown("### Базові фільтри (API рівень)")
    st.caption("Впливають на вибірку при завантаженні даних")
    api_dr_min = st.number_input("DR мін", value=20, min_value=0, max_value=100)
    api_traffic_min = st.number_input("Органічний трафік мін", value=5000, min_value=0, step=1000)
    api_da_min = st.number_input("DA Moz мін", value=10, min_value=0, max_value=100)
    api_price_min = st.number_input("Ціна від (грн)", value=0, min_value=0, step=100)
    api_price_max = st.number_input("Ціна до (грн)", value=0, min_value=0, step=500,
                                     help="0 = без обмеження")

    st.divider()
    load_btn = st.button("🔄 Завантажити дані", use_container_width=True, type="primary")

    if "df_loaded" in st.session_state:
        st.success(f"Завантажено: {len(st.session_state['df_loaded'])} сайтів")

    st.divider()
    st.caption("Link Builder v1.0 | Collaborator.pro API")


# ── Data loading ──────────────────────────────────────────────────────────────
def load_data(api_key, dr_min, traffic_min, da_min, price_min, price_max):
    progress = st.progress(0, text="Завантаження сторінки 1...")

    def cb(done, total):
        pct = int(done / total * 100)
        progress.progress(pct, text=f"Завантаження сторінки {done} / {total}…")

    items, total_count = fetch_all_sites(
        api_key,
        dr_min=dr_min,
        traffic_min=traffic_min,
        da_min=da_min,
        price_min=price_min if price_min > 0 else None,
        price_max=price_max if price_max > 0 else None,
        progress_callback=cb,
    )
    progress.empty()
    sites = [parse_site(item) for item in items]
    return pd.DataFrame(sites)


if load_btn:
    if not api_key:
        st.sidebar.error("Введіть API Key")
    else:
        with st.spinner("Підключення до Collaborator API…"):
            try:
                df = load_data(
                    api_key,
                    api_dr_min,
                    api_traffic_min,
                    api_da_min,
                    api_price_min,
                    api_price_max,
                )
                st.session_state["df_loaded"] = df
                st.sidebar.success(f"Завантажено: {len(df)} сайтів")
            except Exception as e:
                st.sidebar.error(f"Помилка API: {e}")


# ── Result renderer ───────────────────────────────────────────────────────────
def render_results(df_result: pd.DataFrame, budget: float, site_topic: str):
    if df_result.empty:
        st.warning("Не вдалося підібрати донорів у рамках бюджету та критеріїв.")
        return

    total_spent = df_result["price"].sum()
    budget_remaining = budget - total_spent

    # Build display table
    rows = []
    for rank, (_, row) in enumerate(df_result.iterrows(), 1):
        rows.append({
            "#": rank,
            "Домен": row["domain"],
            "Ціна (грн)": f"{int(row['price']):,}",
            "Тематика": row["categories"][:60] + "…" if len(row.get("categories", "")) > 60 else row.get("categories", ""),
            "DR": int(row["dr"]),
            "Органічний трафік": f"{int(row['organic_traffic']):,}",
            "DA Moz": int(row["da_moz"]),
            "% Органіки": f"{row['pct_organic']:.0f}%",
            "Сума (грн)": f"{int(row['cumulative_price']):,}",
            "Чому підходить": build_why_suitable(row),
            "Посилання": row["collaborator_url"],
        })

    df_display = pd.DataFrame(rows)

    st.markdown(f"### Знайдено {len(df_result)} донорів для **{site_topic}**")
    st.dataframe(
        df_display.drop(columns=["Посилання"]),
        use_container_width=True,
        hide_index=True,
    )

    # Budget summary
    col1, col2, col3 = st.columns(3)
    col1.metric("Витрачено", f"{int(total_spent):,} грн")
    col2.metric("Залишок бюджету", f"{int(budget_remaining):,} грн")
    col3.metric("Кількість донорів", len(df_result))

    # Top 3
    st.markdown("#### Топ-3 рекомендації")
    for i, (_, row) in enumerate(df_result.head(3).iterrows(), 1):
        st.markdown(f"**{i}. [{row['domain']}]({row['collaborator_url']})** — {build_why_suitable(row)}")

    # Export
    export_df = df_display.copy()
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        export_df.to_excel(writer, index=False, sheet_name="Донори")
    buf.seek(0)
    st.download_button(
        "📥 Завантажити Excel",
        data=buf,
        file_name=f"link_builder_{site_topic.replace(' ', '_')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# ── Main UI ───────────────────────────────────────────────────────────────────
st.title("🔗 Link Builder")
st.caption("Підбір донорів для лінкбілдингу")

if "df_loaded" not in st.session_state:
    st.info("👈 Натисніть **Завантажити дані** в бічній панелі для початку роботи.")
    st.stop()

df_all: pd.DataFrame = st.session_state["df_loaded"]

tab1, tab2 = st.tabs(["📁 За тематикою", "⚙️ Власні параметри"])

# ── Tab 1: By niche ───────────────────────────────────────────────────────────
with tab1:
    st.markdown("### Підбір за нішою")
    st.caption("Оберіть тематику — система автоматично відфільтрує відповідні донори.")

    col_l, col_r = st.columns([2, 1])
    with col_l:
        selected_niche = st.selectbox("Тематика сайту", options=list(NICHES.keys()))
        site_name_t1 = st.text_input("Сайт реципієнт", placeholder="landrover.com.ua", key="site_t1")
        excluded_t1 = st.text_area(
            "Виключити домени (по одному на рядок або через кому)",
            placeholder="site1.ua\nsite2.ua",
            key="excl_t1",
            height=80,
        )
    with col_r:
        st.markdown("#### Параметри відбору")
        quantity_t1 = st.number_input("Кількість донорів", value=6, min_value=1, max_value=50, key="qty_t1")
        budget_t1 = st.number_input("Бюджет (грн)", value=45000, min_value=1000, step=1000, key="bgt_t1")
        dr_min_t1 = st.number_input("DR мін", value=20, min_value=0, max_value=100, key="dr_t1")
        traffic_min_t1 = st.number_input("Органіч. трафік мін", value=15000, step=1000, key="tr_t1")
        pct_organic_t1 = st.slider("% органіки мін", 0, 100, 30, key="pct_t1")
        ukraine_t1 = st.checkbox("Тільки Україна (.ua / country=Ukraine)", value=True, key="ua_t1")

    if st.button("🔍 Підібрати донорів", key="run_t1", type="primary", use_container_width=True):
        excluded_list = [
            d.strip()
            for raw in excluded_t1.replace(",", "\n").splitlines()
            for d in [raw.strip()]
            if d
        ]
        niche_kw = NICHES[selected_niche]

        criteria = {
            "dr_min": dr_min_t1,
            "organic_traffic_min": traffic_min_t1,
            "pct_organic_min": pct_organic_t1,
            "total_traffic_min": 5000,
            "da_min": 15,
            "ukraine_only": ukraine_t1,
            "excluded_domains": excluded_list,
        }

        df_niche = filter_by_niche(df_all, niche_kw)
        st.caption(f"Знайдено {len(df_niche)} сайтів у ніші «{selected_niche}» до фільтрації")

        df_filtered = apply_hard_filters(df_niche, criteria)
        st.caption(f"Після hard-фільтрів: {len(df_filtered)} сайтів")

        if df_filtered.empty:
            st.warning("Немає донорів, що відповідають обов'язковим критеріям.")
        else:
            df_scored = score_sites(df_filtered)
            df_result = select_donors(df_scored, quantity_t1, budget_t1)
            topic_label = f"{site_name_t1 or selected_niche} ({selected_niche})"
            render_results(df_result, budget_t1, topic_label)


# ── Tab 2: Custom params ──────────────────────────────────────────────────────
with tab2:
    st.markdown("### Власні параметри")
    st.caption("Повний контроль над фільтрацією та ранжуванням.")

    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown("#### Мета")
        site_name_t2 = st.text_input("Сайт реципієнт", placeholder="mysite.com.ua", key="site_t2")
        niche_manual = st.text_input(
            "Тематика / ніша (ключові слова через кому)",
            placeholder="авто, транспорт, car",
            key="niche_t2",
        )
        excluded_t2 = st.text_area(
            "Виключити домени (по одному на рядок або через кому)",
            placeholder="used1.ua\nused2.ua",
            key="excl_t2",
            height=100,
        )

        st.markdown("#### Бюджет")
        quantity_t2 = st.number_input("Кількість донорів", value=6, min_value=1, max_value=100, key="qty_t2")
        budget_t2 = st.number_input("Бюджет (грн)", value=45000, min_value=500, step=1000, key="bgt_t2")

    with col_b:
        st.markdown("#### Hard фільтри")
        dr_min_t2 = st.number_input("DR мін", value=20, min_value=0, max_value=100, key="dr_t2")
        da_min_t2 = st.number_input("DA Moz мін", value=15, min_value=0, max_value=100, key="da_t2")
        traffic_min_t2 = st.number_input("Органіч. трафік мін", value=15000, step=1000, key="tr_t2")
        total_traffic_min_t2 = st.number_input("Загальний трафік мін", value=5000, step=500, key="tt_t2")
        pct_organic_t2 = st.slider("% органіки мін", 0, 100, 30, key="pct_t2")
        price_min_t2 = st.number_input("Ціна від (грн)", value=0, min_value=0, step=100, key="pmin_t2")
        price_max_t2 = st.number_input("Ціна до (грн)", value=0, min_value=0, step=500,
                                        help="0 = без обмеження", key="pmax_t2")
        ukraine_t2 = st.checkbox("Тільки Україна (.ua / country=Ukraine)", value=True, key="ua_t2")

    if st.button("🔍 Підібрати донорів", key="run_t2", type="primary", use_container_width=True):
        excluded_list_t2 = [
            d.strip()
            for raw in excluded_t2.replace(",", "\n").splitlines()
            for d in [raw.strip()]
            if d
        ]
        niche_keywords_t2 = [kw.strip() for kw in niche_manual.split(",") if kw.strip()]

        criteria_t2 = {
            "dr_min": dr_min_t2,
            "da_min": da_min_t2,
            "organic_traffic_min": traffic_min_t2,
            "total_traffic_min": total_traffic_min_t2,
            "pct_organic_min": pct_organic_t2,
            "price_min": price_min_t2 if price_min_t2 > 0 else None,
            "price_max": price_max_t2 if price_max_t2 > 0 else None,
            "ukraine_only": ukraine_t2,
            "excluded_domains": excluded_list_t2,
        }

        df_work = filter_by_niche(df_all, niche_keywords_t2) if niche_keywords_t2 else df_all.copy()
        st.caption(f"Після фільтру тематики: {len(df_work)} сайтів")

        df_filtered_t2 = apply_hard_filters(df_work, criteria_t2)
        st.caption(f"Після hard-фільтрів: {len(df_filtered_t2)} сайтів")

        if df_filtered_t2.empty:
            st.warning("Немає донорів, що відповідають обов'язковим критеріям.")
        else:
            df_scored_t2 = score_sites(df_filtered_t2)
            df_result_t2 = select_donors(df_scored_t2, quantity_t2, budget_t2)
            topic_label_t2 = f"{site_name_t2 or 'сайт'} ({niche_manual or 'будь-яка ніша'})"
            render_results(df_result_t2, budget_t2, topic_label_t2)
