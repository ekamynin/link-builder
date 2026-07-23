import streamlit as st

st.set_page_config(
    page_title="SEO Tools",
    page_icon="🛠️",
    layout="wide",
)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    if "df_loaded" in st.session_state:
        n = len(st.session_state["df_loaded"])
        loaded_at = st.session_state.get("loaded_at", "")
        st.markdown("**Каталог майданчиків**")
        st.success(f"✅ {n:,} майданчиків")
        if loaded_at:
            st.caption(f"Оновлено: {loaded_at}")
    st.divider()
    st.caption("SEO Tools v1.0")


# ── Header ────────────────────────────────────────────────────────────────────
st.title("🛠️ SEO Tools")
st.caption("Внутрішні інструменти для SEO-команди")
st.divider()

# ── Service cards ─────────────────────────────────────────────────────────────
col1, col2, col3, col4 = st.columns(4)

with col1:
    with st.container(border=True):
        st.markdown("#### 🔗 Link Builder")
        st.write(
            "Підбір донорів для лінкбілдингу з бази Collaborator.pro. "
            "Фільтрація за тематикою, DR, трафіком і бюджетом. "
            "Перевірка якості через Ahrefs."
        )
        st.page_link("pages/1_Link_Builder.py", label="Відкрити Link Builder", icon="🔗")

with col2:
    with st.container(border=True):
        st.markdown("#### 🔍 Index Checker")
        st.write(
            "Масова перевірка індексації URL через DataForSEO або SerpAPI. "
            "HTTP статус, noindex, nofollow. "
            "Підтримує до 500 URL за запуск, експорт в Excel."
        )
        st.page_link("pages/2_Index_Checker.py", label="Відкрити Index Checker", icon="🔍")

with col3:
    with st.container(border=True):
        st.markdown("#### 📊 Donor Checker")
        st.write(
            "Масова перевірка списку донорів. "
            "Ціна публікації та написання з Collaborator.pro. "
            "DR і органічний трафік через Ahrefs."
        )
        st.page_link("pages/3_Donor_Checker.py", label="Відкрити Donor Checker", icon="📊")

with col4:
    with st.container(border=True):
        st.markdown("#### 🎯 Competitor Backlinks")
        st.write(
            "Порівняння донорського профілю твого сайту та конкурентів. "
            "Знаходить майданчики, яких у тебе ще немає. "
            "DR, трафік і ціни з Collaborator."
        )
        st.page_link("pages/4_Competitor_Backlinks.py", label="Відкрити Competitor Backlinks", icon="🎯")
