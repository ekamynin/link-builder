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

st.set_page_config(
    page_title="Link Builder | Collaborator",
    page_icon="🔗",
    layout="wide",
)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ Налаштування")
    st.divider()

    if "df_loaded" in st.session_state:
        st.success(f"✅ {len(st.session_state['df_loaded'])} майданчиків завантажено")
        if st.button("🔄 Оновити дані", use_container_width=True):
            del st.session_state["df_loaded"]
            st.rerun()

    st.divider()
    st.caption("Link Builder v1.0")


# ── Data loading ──────────────────────────────────────────────────────────────
def load_data(api_key, dr_min, traffic_min, da_min, price_min, price_max):
    progress = st.progress(0, text="Завантаження сторінки 1…")

    def cb(done, total):
        progress.progress(int(done / total * 100), text=f"Завантаження сторінки {done} із {total}…")

    items, _ = fetch_all_sites(
        api_key,
        dr_min=dr_min,
        traffic_min=traffic_min,
        da_min=da_min,
        price_min=price_min,
        price_max=price_max,
        progress_callback=cb,
    )
    progress.empty()
    return pd.DataFrame([parse_site(i) for i in items])


API_KEY = "hH0Zieka-iOKh-gLoJonsRYU0-MxOXXAFsnHjxw0ZII2N9PFgYwa72fXSOAM8DXT"

if "df_loaded" not in st.session_state:
    with st.spinner("Завантажуємо майданчики…"):
        try:
            df = load_data(API_KEY, 20, 5000, 10, None, None)
            st.session_state["df_loaded"] = df
            st.rerun()
        except Exception as e:
            st.error(f"Помилка завантаження даних: {e}")


# ── Result renderer ───────────────────────────────────────────────────────────
def render_results(df_result: pd.DataFrame, budget: float, label: str):
    if df_result.empty:
        st.warning("Не знайдено донорів у рамках бюджету та критеріїв. Спробуй послабити фільтри.")
        return

    total_spent = df_result["price"].sum()
    budget_remaining = budget - total_spent

    rows = []
    for rank, (_, row) in enumerate(df_result.iterrows(), 1):
        cats = row.get("categories", "")
        rows.append({
            "#": rank,
            "Домен": row["domain"],
            "Ціна (грн)": f"{int(row['price']):,}",
            "Тематика": cats[:60] + "…" if len(cats) > 60 else cats,
            "DR": int(row["dr"]),
            "Органічний трафік": f"{int(row['organic_traffic']):,}",
            "% Органіки": f"{row['pct_organic']:.0f}%",
            "Ціна написання": f"{int(row['price_writing']):,} грн" if row.get("price_writing") else "Не пишуть",
            "Бюджет витрачено (грн)": f"{int(row['cumulative_price']):,}",
            "Чому підходить": build_why_suitable(row),
            "Посилання на майданчик": row["collaborator_url"],
        })

    df_display = pd.DataFrame(rows)

    st.markdown(f"### Результат для: **{label}**")
    st.dataframe(df_display.drop(columns=["Посилання на майданчик"]), use_container_width=True, hide_index=True)

    col1, col2, col3 = st.columns(3)
    col1.metric("💸 Витрачено", f"{int(total_spent):,} грн")
    col2.metric("💰 Залишок бюджету", f"{int(budget_remaining):,} грн")
    col3.metric("🔗 Донорів підібрано", len(df_result))

    st.markdown("#### Топ-3 рекомендації")
    for i, (_, row) in enumerate(df_result.head(3).iterrows(), 1):
        st.markdown(f"**{i}. [{row['domain']}]({row['collaborator_url']})** — {build_why_suitable(row)}")

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df_display.to_excel(writer, index=False, sheet_name="Донори")
    buf.seek(0)
    st.download_button(
        "📥 Завантажити Excel",
        data=buf,
        file_name=f"donors_{label.replace(' ', '_')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# ── Main UI ───────────────────────────────────────────────────────────────────
st.title("🔗 Link Builder")
st.caption("Підбір донорів для лінкбілдингу")

df_all: pd.DataFrame = st.session_state.get("df_loaded", pd.DataFrame())

tab1, tab2 = st.tabs(["📁 За тематикою", "⚙️ Власні параметри"])


# ── Tab 1: By niche ───────────────────────────────────────────────────────────
with tab1:
    st.markdown("### Підбір за тематикою")
    st.caption("Обери нішу — система сама відфільтрує підходящі майданчики і підбере найкращі у рамках бюджету.")

    col_l, col_r = st.columns([2, 1])
    with col_l:
        selected_niche = st.selectbox(
            "Тематика сайту, для якого шукаємо донорів",
            options=list(NICHES.keys()),
            help="Обери нішу, яка відповідає тематиці твого сайту"
        )
        my_site_t1 = st.text_input(
            "Мій сайт (необов'язково)",
            placeholder="наприклад: landrover.com.ua",
            key="site_t1",
            help="Твій сайт — той, на який будуть вести посилання від донорів. Використовується лише для назви звіту.",
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
            value=6, min_value=1, max_value=50, key="qty_t1",
            help="Максимальна кількість майданчиків у результаті"
        )
        budget_t1 = st.number_input(
            "Загальний бюджет (грн)",
            value=45000, min_value=1000, step=1000, key="bgt_t1",
            help="Сума всіх розміщень не перевищить цей бюджет"
        )
        dr_min_t1 = st.number_input(
            "DR мін (авторитетність домену, Ahrefs)",
            value=20, min_value=0, max_value=100, key="dr_t1",
            help="Domain Rating від Ahrefs. Чим вище — тим авторитетніший сайт. Рекомендовано ≥ 20."
        )
        traffic_min_t1 = st.number_input(
            "Органічний трафік мін (відвідувачів/міс)",
            value=15000, step=1000, key="tr_t1",
            help="Мінімальна кількість органічних відвідувачів на місяць за даними Ahrefs"
        )
        pct_organic_t1 = st.slider(
            "Мінімальна частка органіки (%)",
            0, 100, 30, key="pct_t1",
            help="Яку частку від загального трафіку складає органічний пошук. Низький % = підозрілий трафік."
        )
        ukraine_t1 = st.checkbox(
            "Тільки українські сайти",
            value=True, key="ua_t1",
            help="Фільтрує за доменом .ua або країною Ukraine"
        )

    if st.button("🔍 Підібрати донорів", key="run_t1", type="primary", use_container_width=True, disabled=df_all.empty):
        excluded_list = [d.strip() for raw in excluded_t1.replace(",", "\n").splitlines() for d in [raw.strip()] if d]

        criteria = {
            "dr_min": dr_min_t1,
            "organic_traffic_min": traffic_min_t1,
            "pct_organic_min": pct_organic_t1,
            "total_traffic_min": 5000,
            "ukraine_only": ukraine_t1,
            "excluded_domains": excluded_list,
        }

        df_niche = filter_by_niche(df_all, NICHES[selected_niche])
        df_filtered = apply_hard_filters(df_niche, criteria)

        st.caption(f"За тематикою «{selected_niche}»: {len(df_niche)} сайтів → після фільтрів: {len(df_filtered)}")

        if df_filtered.empty:
            st.warning("Жоден майданчик не пройшов фільтри. Спробуй знизити мінімальні пороги.")
        else:
            df_result = select_donors(score_sites(df_filtered), quantity_t1, budget_t1)
            label = f"{my_site_t1 or selected_niche} ({selected_niche})"
            render_results(df_result, budget_t1, label)


# ── Tab 2: Custom params ──────────────────────────────────────────────────────
with tab2:
    st.markdown("### Власні параметри")
    st.caption("Повний контроль: сам задаєш усі критерії фільтрації та підбору.")

    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown("#### Про що шукаємо")
        my_site_t2 = st.text_input(
            "Мій сайт (необов'язково)",
            placeholder="mysite.com.ua",
            key="site_t2",
            help="Твій сайт — той, на який будуть вести посилання. Лише для назви звіту.",
        )
        niche_manual = st.text_input(
            "Тематика — ключові слова для пошуку по категоріях майданчиків",
            placeholder="авто, транспорт, car",
            key="niche_t2",
            help="Система шукатиме майданчики, у категоріях яких є ці слова. Залиш порожнім — пошук по всіх.",
        )
        excluded_t2 = st.text_area(
            "Домени, які вже використовувались (виключити)",
            placeholder="used1.ua\nused2.ua",
            key="excl_t2",
            height=100,
            help="Ці майданчики будуть повністю проігноровані.",
        )
        st.markdown("#### Бюджет")
        quantity_t2 = st.number_input("Скільки донорів потрібно", value=6, min_value=1, max_value=100, key="qty_t2")
        budget_t2 = st.number_input("Загальний бюджет (грн)", value=45000, min_value=500, step=1000, key="bgt_t2")

    with col_b:
        st.markdown("#### Мінімальні вимоги до майданчика")
        dr_min_t2 = st.number_input(
            "DR мін (авторитетність домену, Ahrefs)",
            value=20, min_value=0, max_value=100, key="dr_t2",
            help="Domain Rating. Чим вище — тим авторитетніший сайт."
        )
        traffic_min_t2 = st.number_input(
            "Органічний трафік мін (відвідувачів/міс)",
            value=15000, step=1000, key="tr_t2",
            help="Мінімум органічних відвідувачів на місяць (Ahrefs)"
        )
        total_traffic_min_t2 = st.number_input(
            "Загальний трафік мін (відвідувачів/міс)",
            value=5000, step=500, key="tt_t2",
            help="Загальна кількість відвідувачів із усіх джерел"
        )
        pct_organic_t2 = st.slider(
            "Мінімальна частка органіки (%)",
            0, 100, 30, key="pct_t2",
            help="Низький % органіки може означати накрутку трафіку"
        )
        price_min_t2 = st.number_input("Ціна від (грн)", value=0, min_value=0, step=100, key="pmin_t2")
        price_max_t2 = st.number_input("Ціна до (грн)", value=0, min_value=0, step=500,
                                        help="0 = без обмеження", key="pmax_t2")
        ukraine_t2 = st.checkbox(
            "Тільки українські сайти",
            value=True, key="ua_t2",
            help="Фільтр за доменом .ua або країною Ukraine"
        )

    if st.button("🔍 Підібрати донорів", key="run_t2", type="primary", use_container_width=True, disabled=df_all.empty):
        excluded_list_t2 = [d.strip() for raw in excluded_t2.replace(",", "\n").splitlines() for d in [raw.strip()] if d]
        niche_keywords_t2 = [kw.strip() for kw in niche_manual.split(",") if kw.strip()]

        criteria_t2 = {
            "dr_min": dr_min_t2,
            "organic_traffic_min": traffic_min_t2,
            "total_traffic_min": total_traffic_min_t2,
            "pct_organic_min": pct_organic_t2,
            "price_min": price_min_t2 if price_min_t2 > 0 else None,
            "price_max": price_max_t2 if price_max_t2 > 0 else None,
            "ukraine_only": ukraine_t2,
            "excluded_domains": excluded_list_t2,
        }

        df_work = filter_by_niche(df_all, niche_keywords_t2) if niche_keywords_t2 else df_all.copy()
        df_filtered_t2 = apply_hard_filters(df_work, criteria_t2)

        st.caption(f"За тематикою: {len(df_work)} сайтів → після фільтрів: {len(df_filtered_t2)}")

        if df_filtered_t2.empty:
            st.warning("Жоден майданчик не пройшов фільтри. Спробуй знизити мінімальні пороги.")
        else:
            df_result_t2 = select_donors(score_sites(df_filtered_t2), quantity_t2, budget_t2)
            label_t2 = f"{my_site_t2 or 'сайт'} ({niche_manual or 'будь-яка ніша'})"
            render_results(df_result_t2, budget_t2, label_t2)
