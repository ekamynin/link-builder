import io
import re
from datetime import datetime

import pandas as pd
import streamlit as st

from collaborator_api import fetch_all_sites, parse_site
from ahrefs_api import enrich_with_ahrefs
from link_builder import (
    CATEGORY_TRANSLATIONS,
    apply_hard_filters,
    build_why_suitable,
    filter_by_categories,
    filter_by_keywords,
    get_all_categories,
    score_sites,
    select_donors,
)

st.set_page_config(
    page_title="Link Builder",
    page_icon="🔗",
    layout="wide",
)

# ── Secrets ───────────────────────────────────────────────────────────────────
COLLAB_KEY  = st.secrets.get("COLLABORATOR_API_KEY", "")
AHREFS_KEY  = st.secrets.get("AHREFS_API_KEY", "")


# ── Cached API fetch ──────────────────────────────────────────────────────────
@st.cache_data(ttl=21600, show_spinner=False)
def fetch_sites_cached(api_key: str) -> pd.DataFrame:
    """Tab 1: pre-filtered dataset (DR≥20, traffic≥5000)."""
    items, _ = fetch_all_sites(api_key, dr_min=20, traffic_min=5000, da_min=10)
    return pd.DataFrame([parse_site(i) for i in items])


@st.cache_data(ttl=21600, show_spinner=False)
def fetch_sites_all_cached(api_key: str) -> pd.DataFrame:
    """Tab 2: all available sites, no pre-filtering."""
    items, _ = fetch_all_sites(api_key, dr_min=0, traffic_min=0, da_min=0)
    return pd.DataFrame([parse_site(i) for i in items])


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ Налаштування")
    st.divider()

    if "df_loaded" in st.session_state:
        loaded_at = st.session_state.get("loaded_at", "")
        st.success(f"✅ {len(st.session_state['df_loaded']):,} майданчиків")
        if loaded_at:
            st.caption(f"Оновлено: {loaded_at}")
        if st.button("🔄 Оновити дані", use_container_width=True,
                     help="Примусово завантажити свіжі дані з Collaborator"):
            st.cache_data.clear()
            del st.session_state["df_loaded"]
            st.rerun()

    st.divider()
    st.caption("Link Builder v1.0")


# ── Auto-load data ────────────────────────────────────────────────────────────
if "df_loaded" not in st.session_state:
    if not COLLAB_KEY:
        st.error("❌ Не знайдено COLLABORATOR_API_KEY у секретах. Додай його в Settings → Secrets.")
        st.stop()
    with st.spinner("Зачекайте, будь ласка, завантажуємо майданчики з Collaborator…"):
        try:
            df = fetch_sites_cached(COLLAB_KEY)
            st.session_state["df_loaded"] = df
            st.session_state["loaded_at"] = datetime.now().strftime("%d.%m.%Y %H:%M")
            st.rerun()
        except Exception as e:
            st.error(f"❌ Помилка завантаження даних: {e}")
            st.stop()


# ── Helpers ───────────────────────────────────────────────────────────────────
def normalize_domain(raw: str) -> str:
    """Strip protocol, www, trailing slashes and paths.
    Handles: donpion.ua / https://donpion.ua / www.donpion.ua / https://www.donpion.ua/path
    """
    d = raw.strip().lower()
    d = re.sub(r"^https?://", "", d)   # remove protocol
    d = re.sub(r"^www\.", "", d)        # remove www.
    d = d.split("/")[0]                 # remove path
    d = d.split("?")[0]                 # remove query string
    return d


def parse_excluded(text: str) -> list:
    """Parse excluded domains textarea — one per line or comma-separated."""
    domains = []
    for raw in text.replace(",", "\n").splitlines():
        d = normalize_domain(raw)
        if d:
            domains.append(d)
    return domains


def translate_categories(raw: str) -> str:
    """Translate comma-separated categories to Ukrainian."""
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    translated = [CATEGORY_TRANSLATIONS.get(p, p) for p in parts]
    # Deduplicate while preserving order
    seen, result = set(), []
    for t in translated:
        if t not in seen:
            seen.add(t)
            result.append(t)
    return ", ".join(result)


def render_results(df_result: pd.DataFrame, df_pool: pd.DataFrame,
                   budget: float, label: str, quantity: int = 0):
    if df_result.empty:
        st.warning("⚠️ Не знайдено донорів у рамках бюджету та критеріїв. Спробуй знизити мінімальні пороги або збільшити бюджет.")
        return

    if quantity and len(df_result) < quantity:
        found = len(df_result)
        st.warning(
            f"⚠️ Запитано **{quantity}** донорів, але за вказаними параметрами знайдено лише **{found}**. "
            f"Спробуй знизити мінімальний DR або трафік, розширити тематику або збільшити бюджет."
        )

    # Ahrefs enrichment
    ahrefs_data = {}
    if AHREFS_KEY:
        with st.spinner("Перевіряємо DR і трафік через Ahrefs…"):
            try:
                ahrefs_data = enrich_with_ahrefs(AHREFS_KEY, df_result["domain"].tolist())
            except Exception:
                pass

    total_spent = df_result["price"].sum()
    budget_remaining = budget - total_spent

    rows = []
    for rank, (_, row) in enumerate(df_result.iterrows(), 1):
        ah = ahrefs_data.get(row["domain"], {})
        dr_val  = ah.get("dr")          if ah.get("dr")          is not None else row["dr"]
        tr_val  = ah.get("org_traffic") if ah.get("org_traffic") is not None else row["organic_traffic"]
        verified = ah.get("dr") is not None
        rows.append({
            "#": rank,
            "Домен": row["domain"],
            "Ціна (грн)": int(row["price"]),
            "Тематика": translate_categories(row.get("categories", "")),
            "DR": f"{int(dr_val)} ✓" if verified else str(int(dr_val)),
            "Органічний трафік": f"{int(tr_val):,} ✓" if verified else f"{int(tr_val):,}",
            "% Органіки": f"{row['pct_organic']:.0f}%",
            "Ціна написання": (
                f"{int(row['price_writing']):,} грн"
                if pd.notna(row.get("price_writing")) and row.get("price_writing")
                else "Не пишуть"
            ),
            "Бюджет витрачено (грн)": int(row["cumulative_price"]),
            "Чому підходить": build_why_suitable(row),
            "Переглянути": row["collaborator_url"],
        })

    df_display = pd.DataFrame(rows)

    st.markdown(f"### Результат для: **{label}**")
    st.dataframe(
        df_display,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Ціна (грн)": st.column_config.NumberColumn("Ціна (грн)", format="%d"),
            "Бюджет витрачено (грн)": st.column_config.NumberColumn("Бюджет витрачено (грн)", format="%d"),
            "Переглянути": st.column_config.LinkColumn(
                "Переглянути",
                display_text="🔗 Collaborator",
                help="Відкрити майданчик на Collaborator"
            ),
        },
    )

    col1, col2, col3 = st.columns(3)
    col1.metric("💸 Витрачено", f"{int(total_spent):,} грн")
    col2.metric("💰 Залишок бюджету", f"{int(budget_remaining):,} грн")
    col3.metric("🔗 Донорів підібрано", len(df_result))

    used_pct = total_spent / budget * 100 if budget else 0
    if used_pct < 50:
        st.info(f"ℹ️ Використано {used_pct:.0f}% бюджету. Щоб отримати якісніших донорів — підвищи мінімальний DR або органічний трафік.")

    # Extra recommendations within remaining budget
    if budget_remaining > 0:
        selected_domains = set(df_result["domain"])
        extras = (
            df_pool[
                ~df_pool["domain"].isin(selected_domains)
                & df_pool["price"].notna()
                & (df_pool["price"] <= budget_remaining)
            ]
            .sort_values("price", ascending=True)
            .head(5)
        )
        if not extras.empty:
            st.markdown(f"#### 💡 Рекомендуємо додатково — вписуються в залишок **{int(budget_remaining):,} грн**")
            for _, row in extras.iterrows():
                st.markdown(
                    f"- **[{row['domain']}]({row['collaborator_url']})** — "
                    f"{int(row['price']):,} грн | {build_why_suitable(row)}"
                )

    # Excel export (with real domain names, not URLs)
    export_df = df_display.copy()
    export_df["Домен"] = df_result["domain"].values
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        export_df.to_excel(writer, index=False, sheet_name="Донори")
    buf.seek(0)
    st.download_button(
        "📥 Завантажити Excel",
        data=buf,
        file_name=f"donors_{label[:30].replace(' ', '_')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# ── Main UI ───────────────────────────────────────────────────────────────────
st.title("🔗 Link Builder")
st.caption("Підбір донорів для лінкбілдингу")

df_all: pd.DataFrame = st.session_state.get("df_loaded", pd.DataFrame())
all_cats = get_all_categories(df_all) if not df_all.empty else []

tab1, tab2 = st.tabs(["📁 За тематикою", "⚙️ Власні параметри"])


# ── Tab 1 ─────────────────────────────────────────────────────────────────────
with tab1:
    st.markdown("### Підбір за тематикою")
    st.caption("Обери категорії — система відфільтрує майданчики і підбере найкращі у рамках бюджету.")

    col_l, col_r = st.columns([2, 1])
    with col_l:
        selected_cats = st.multiselect(
            "Категорії майданчиків",
            options=all_cats,
            help="Можна обрати кілька. Список береться напряму з бази Collaborator.",
        )
        my_site_t1 = st.text_input(
            "Мій сайт (необов'язково)",
            placeholder="landrover.com.ua",
            key="site_t1",
            help="Використовується лише для назви звіту і Excel-файлу.",
        )
        excluded_t1 = st.text_area(
            "Домени, які вже використовувались (виключити)",
            placeholder="site1.ua\nsite2.ua",
            key="excl_t1",
            height=80,
            help="Ці майданчики будуть повністю проігноровані при підборі.",
        )
    with col_r:
        st.markdown("#### Параметри підбору")
        quantity_t1 = st.number_input(
            "Скільки донорів потрібно",
            value=6, min_value=1, max_value=100, key="qty_t1",
        )
        budget_t1 = st.number_input(
            "Загальний бюджет (грн)",
            value=45000, min_value=1000, step=1000, key="bgt_t1",
            help="Сума всіх розміщень не перевищить цей бюджет.",
        )
        dr_min_t1 = st.number_input(
            "DR мін",
            value=20, min_value=0, max_value=100, key="dr_t1",
            help="Domain Rating від Ahrefs. Рекомендовано ≥ 20.",
        )
        traffic_min_t1 = st.number_input(
            "Органічний трафік мін",
            value=15000, step=1000, key="tr_t1",
            help="Мінімум органічних відвідувачів на місяць.",
        )
        pct_organic_t1 = st.slider(
            "Мінімальна частка органіки (%)",
            0, 100, 30, key="pct_t1",
            help="Низький % = підозрілий трафік.",
        )
        ukraine_t1 = st.checkbox(
            "Тільки українські сайти",
            value=True, key="ua_t1",
        )

    if st.button("🔍 Підібрати донорів", key="run_t1", type="primary",
                 use_container_width=True, disabled=df_all.empty):
        if not selected_cats:
            st.warning("⚠️ Обери хоча б одну категорію.")
        elif budget_t1 <= 0:
            st.warning("⚠️ Вкажи бюджет більше 0.")
        elif quantity_t1 <= 0:
            st.warning("⚠️ Кількість донорів має бути більше 0.")
        else:
            excluded_list = parse_excluded(excluded_t1)
            criteria = {
                "dr_min": dr_min_t1,
                "organic_traffic_min": traffic_min_t1,
                "pct_organic_min": pct_organic_t1,
                "total_traffic_min": 5000,
                "ukraine_only": ukraine_t1,
                "excluded_domains": excluded_list,
            }
            df_niche = filter_by_categories(df_all, selected_cats)
            df_filtered = apply_hard_filters(df_niche, criteria)
            cats_label = ", ".join(selected_cats)
            st.caption(f"«{cats_label}»: {len(df_niche)} сайтів → після фільтрів: {len(df_filtered)}")

            if df_filtered.empty:
                st.warning("⚠️ Жоден майданчик не пройшов фільтри. Спробуй знизити мінімальні пороги.")
            else:
                df_scored = score_sites(df_filtered)
                df_result = select_donors(df_scored, quantity_t1, budget_t1)
                render_results(df_result, df_scored, budget_t1, my_site_t1 or cats_label, quantity_t1)


# ── Tab 2 ─────────────────────────────────────────────────────────────────────
with tab2:
    st.markdown("### Власні параметри")
    st.caption("Повний контроль: сам задаєш усі критерії фільтрації та підбору.")

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("#### Мета")
        my_site_t2 = st.text_input(
            "Мій сайт (необов'язково)", placeholder="mysite.com.ua", key="site_t2",
            help="Використовується лише для назви звіту.",
        )
        niche_manual = st.text_input(
            "Тематика — ключові слова через кому",
            placeholder="авто, транспорт, car", key="niche_t2",
            help="Система шукатиме майданчики, у категоріях яких є ці слова. Залиш порожнім — всі категорії.",
        )
        excluded_t2 = st.text_area(
            "Домени, які вже використовувались (виключити)",
            placeholder="used1.ua\nused2.ua", key="excl_t2", height=100,
        )
        st.markdown("#### Бюджет")
        quantity_t2 = st.number_input("Скільки донорів потрібно", value=6, min_value=1, max_value=100, key="qty_t2")
        budget_t2 = st.number_input("Загальний бюджет (грн)", value=45000, min_value=500, step=1000, key="bgt_t2")

    with col_b:
        st.markdown("#### Мінімальні вимоги")
        dr_min_t2 = st.number_input("DR мін", value=20, min_value=0, max_value=100, key="dr_t2",
                                     help="Domain Rating від Ahrefs.")
        traffic_min_t2 = st.number_input("Органічний трафік мін", value=15000, step=1000, key="tr_t2")
        total_traffic_min_t2 = st.number_input("Загальний трафік мін", value=5000, step=500, key="tt_t2")
        pct_organic_t2 = st.slider("Мінімальна частка органіки (%)", 0, 100, 30, key="pct_t2")
        price_min_t2 = st.number_input("Ціна від (грн)", value=0, min_value=0, step=100, key="pmin_t2")
        price_max_t2 = st.number_input("Ціна до (грн)", value=0, min_value=0, step=500,
                                        help="0 = без обмеження", key="pmax_t2")
        ukraine_t2 = st.checkbox("Тільки українські сайти", value=True, key="ua_t2")

    if st.button("🔍 Підібрати донорів", key="run_t2", type="primary",
                 use_container_width=True, disabled=df_all.empty):
        if budget_t2 <= 0:
            st.warning("⚠️ Вкажи бюджет більше 0.")
        elif quantity_t2 <= 0:
            st.warning("⚠️ Кількість донорів має бути більше 0.")
        else:
            # Lazy-load unrestricted dataset on first use
            if "df_all_sites" not in st.session_state:
                with st.spinner("Завантажуємо повну базу майданчиків…"):
                    try:
                        st.session_state["df_all_sites"] = fetch_sites_all_cached(COLLAB_KEY)
                    except Exception as e:
                        st.error(f"❌ Помилка завантаження даних: {e}")
                        st.stop()
            df_all_unrestricted = st.session_state["df_all_sites"]

            excluded_list_t2 = parse_excluded(excluded_t2)
            niche_kw = [kw.strip() for kw in niche_manual.split(",") if kw.strip()]
            criteria_t2 = {
                "dr_min": dr_min_t2 if dr_min_t2 > 0 else None,
                "organic_traffic_min": traffic_min_t2 if traffic_min_t2 > 0 else None,
                "total_traffic_min": total_traffic_min_t2 if total_traffic_min_t2 > 0 else None,
                "pct_organic_min": pct_organic_t2 if pct_organic_t2 > 0 else None,
                "price_min": price_min_t2 if price_min_t2 > 0 else None,
                "price_max": price_max_t2 if price_max_t2 > 0 else None,
                "ukraine_only": ukraine_t2,
                "excluded_domains": excluded_list_t2,
            }
            df_work = filter_by_keywords(df_all_unrestricted, niche_kw) if niche_kw else df_all_unrestricted.copy()
            df_filtered_t2 = apply_hard_filters(df_work, criteria_t2, strict=False)
            st.caption(f"За тематикою: {len(df_work)} сайтів → після фільтрів: {len(df_filtered_t2)}")

            if df_filtered_t2.empty:
                st.warning("⚠️ Жоден майданчик не пройшов фільтри. Спробуй знизити мінімальні пороги.")
            else:
                df_scored_t2 = score_sites(df_filtered_t2)
                df_result_t2 = select_donors(df_scored_t2, quantity_t2, budget_t2)
                label_t2 = f"{my_site_t2 or 'сайт'} ({niche_manual or 'всі категорії'})"
                render_results(df_result_t2, df_scored_t2, budget_t2, label_t2, quantity_t2)
