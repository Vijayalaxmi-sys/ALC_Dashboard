import re

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from neo4j_manager import Neo4jManager


# ============================================================
# SETTINGS
# ============================================================

YEAR_START = 2020
YEAR_END = 2026
MAX_RECORDS = 5000


# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="ALC Challenges in Nova Scotia(2020-2026)",
    page_icon="🏥",
    layout="wide"
)


# ============================================================
# CSS
# ============================================================

st.markdown(
    """
    <style>
        .block-container {
            padding-top: 2.0rem;
            padding-bottom: 2.2rem;
            max-width: 1500px;
        }

        .main-title {
            font-size: 1.65rem;
            font-weight: 800;
            color: #111827;
            margin-bottom: 0.25rem;
            letter-spacing: -0.01em;
        }

        .main-subtitle {
            font-size: 0.9rem;
            color: #6b7280;
            margin-bottom: 1rem;
        }

        .section-note {
            background: #f8fafc;
            border: 1px solid #e5e7eb;
            border-radius: 10px;
            padding: 0.65rem 0.85rem;
            color: #374151;
            font-size: 0.88rem;
            margin-bottom: 0.8rem;
        }

        .kpi-card {
            background: #ffffff;
            border: 1px solid #e5e7eb;
            border-radius: 10px;
            padding: 9px 12px;
            min-height: 62px;
            box-shadow: none;
        }

        .kpi-label {
            font-size: 0.76rem;
            color: #6b7280;
            line-height: 1.2;
            margin-bottom: 0.3rem;
            font-weight: 500;
        }

        .kpi-value {
            font-size: 1.45rem;
            line-height: 1.05;
            font-weight: 800;
            color: #111827;
            letter-spacing: -0.02em;
        }

        .small-muted {
            color: #6b7280;
            font-size: 0.88rem;
        }

        .stTabs [data-baseweb="tab-list"] {
            gap: 8px;
            border-bottom: 1px solid #e5e7eb;
            padding-bottom: 0.15rem;
        }

        .stTabs [data-baseweb="tab"] {
            background: transparent;
            border-radius: 8px 8px 0 0;
            padding: 8px 14px;
            color: #4b5563;
            font-weight: 600;
        }

        .stTabs [aria-selected="true"] {
            background: #eef2ff !important;
            color: #1d4ed8 !important;
            border-bottom: 3px solid #2563eb;
        }

        div[data-testid="stSidebar"] {
            background: #f3f4f6;
        }
    </style>
    """,
    unsafe_allow_html=True
)


# ============================================================
# NEO4J HELPERS
# ============================================================

def run_cypher(query):
    db = Neo4jManager()
    try:
        return db.run_cypher(query)
    finally:
        db.close()


def to_dataframe(results):
    if not results:
        return pd.DataFrame()
    return pd.DataFrame(results)


@st.cache_data(ttl=30)
def get_evidence_rows():
    query = f"""
    MATCH (e:Evidence)-[:SUPPORTS]->(c:Challenge)
    OPTIONAL MATCH (c)-[:OCCURS_IN]->(l:Location)
    OPTIONAL MATCH (c)-[:IMPACTS]->(s:Stakeholder)
    OPTIONAL MATCH (c)-[:REPORTED_BY]->(o:Organization)
    OPTIONAL MATCH (c)-[:OBSERVED_IN]->(tp:TimePeriod)
    OPTIONAL MATCH (src:Source)-[:CONTAINS]->(e)
    RETURN
        elementId(e) AS evidence_id,
        c.category AS category,
        c.name AS challenge,
        e.text AS evidence_text,
        e.severity AS estimated_importance,
        e.confidence AS extraction_confidence,
        collect(DISTINCT l.name) AS locations,
        collect(DISTINCT s.name) AS affected_groups,
        collect(DISTINCT o.name) AS organizations,
        collect(DISTINCT tp.year) AS years,
        collect(DISTINCT src.title) AS source_titles,
        collect(DISTINCT src.url) AS source_urls
    ORDER BY extraction_confidence DESC
    LIMIT {MAX_RECORDS}
    """
    return run_cypher(query)


# ============================================================
# CLEANING HELPERS
# ============================================================

def ensure_columns(df, columns):
    fixed = df.copy()
    for col in columns:
        if col not in fixed.columns:
            fixed[col] = [[] for _ in range(len(fixed))]
    return fixed


def safe_list(value):
    if isinstance(value, list):
        return value
    if value is None:
        return []
    if isinstance(value, float) and pd.isna(value):
        return []
    if value in ["", "Unknown", "unknown", "None"]:
        return []
    return [value]


def short_label(text, max_len=45):
    if text is None:
        return ""
    text = str(text).strip()
    if len(text) <= max_len:
        return text
    return text[:max_len].rstrip() + "..."


def clean_list_column(value, max_items=4, max_len=30):
    values = [str(v).strip() for v in safe_list(value) if str(v).strip() not in ["", "Unknown"]]
    if not values:
        return ""

    values = list(dict.fromkeys(values))
    shortened = [short_label(v, max_len) for v in values[:max_items]]
    text = ", ".join(shortened)

    if len(values) > max_items:
        text += f" (+{len(values) - max_items} more)"

    return text


def get_first_valid_url(value):
    for url in safe_list(value):
        url = str(url).strip()
        if url and url.lower() != "unknown":
            if url.startswith("http://") or url.startswith("https://"):
                return url
            return "https://" + url
    return None


def get_first_source_title(value):
    for title in safe_list(value):
        title = str(title).strip()
        if title and title.lower() != "unknown":
            return title
    return ""


def source_display_title(row):
    title = get_first_source_title(row.get("source_titles"))
    url = get_first_valid_url(row.get("source_urls"))

    if title:
        return title
    if url:
        return url
    return "Source missing"


def unique_join(values, max_items=4, max_len=45):
    cleaned = []
    for value in values:
        if value is None:
            continue

        if isinstance(value, list):
            for item in value:
                item = str(item).strip()
                if item and item != "Unknown":
                    cleaned.append(item)
        else:
            value = str(value).strip()
            if value and value != "Unknown":
                cleaned.append(value)

    cleaned = list(dict.fromkeys(cleaned))

    if not cleaned:
        return ""

    display_values = [short_label(v, max_len) for v in cleaned[:max_items]]
    output = ", ".join(display_values)

    if len(cleaned) > max_items:
        output += f" (+{len(cleaned) - max_items} more)"

    return output


def has_source_url(value):
    return get_first_valid_url(value) is not None


def has_source_title(value):
    titles = [str(v).strip() for v in safe_list(value) if str(v).strip() not in ["", "Unknown"]]
    return len(titles) > 0


def source_status(row):
    has_url = has_source_url(row.get("source_urls"))
    has_title = has_source_title(row.get("source_titles"))

    if has_url:
        return "URL available"
    if has_title:
        return "Title only"
    return "Missing source"


def extraction_confidence_bucket(value):
    try:
        value = float(value)
    except Exception:
        return "Unknown"

    if pd.isna(value):
        return "Unknown"
    if value >= 0.80:
        return "High extraction confidence"
    if value >= 0.60:
        return "Medium extraction confidence"
    return "Low extraction confidence"


def extract_years_from_value(value, min_year=YEAR_START, max_year=YEAR_END):
    years_found = set()
    for item in safe_list(value):
        for match in re.findall(r"\b(19\d{2}|20\d{2})\b", str(item)):
            year_num = int(match)
            if min_year <= year_num <= max_year:
                years_found.add(str(year_num))
    return sorted(years_found, key=lambda x: int(x))


def build_display_years(value):
    return extract_years_from_value(value)


def apply_chart_layout(fig, height=360, show_legend=True, legend_position="bottom"):
    """
    Common Plotly styling.
    Use legend_position="right" for stacked charts so legends do not overlap x-axis labels.
    """
    if legend_position == "right":
        margin = dict(l=20, r=220, t=20, b=45)
        legend = dict(
            orientation="v",
            yanchor="top",
            y=1,
            xanchor="left",
            x=1.02
        )
    else:
        margin = dict(l=20, r=20, t=20, b=55)
        legend = dict(
            orientation="h",
            yanchor="bottom",
            y=-0.28,
            xanchor="center",
            x=0.5
        )

    fig.update_layout(
        height=height,
        margin=margin,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(size=13),
        title_text="",
        showlegend=show_legend,
        legend=legend
    )
    return fig




def prepare_horizontal_stack_df(stack_df, stack_col, top_n_categories=10):
    """
    Prepares stacked bar data as horizontal bars.
    This avoids messy diagonal category labels and keeps legends clean on the right.
    """
    if stack_df.empty:
        return stack_df

    totals = (
        stack_df.groupby("category")["evidence_count"]
        .sum()
        .sort_values(ascending=False)
        .head(top_n_categories)
    )

    prepared = stack_df[stack_df["category"].isin(totals.index)].copy()
    prepared["category_short"] = prepared["category"].apply(lambda x: short_label(x, 38))
    prepared["category_total"] = prepared["category"].map(totals)
    prepared = prepared.sort_values(["category_total", stack_col], ascending=[True, True])

    return prepared

def render_kpi(label, value, icon=""):
    st.markdown(
        f"""
        <div class="kpi-card">
            <div class="kpi-label">{label}</div>
            <div class="kpi-value">{value}</div>
        </div>
        """,
        unsafe_allow_html=True
    )


# ============================================================
# DATA PREP HELPERS
# ============================================================

def explode_list_summary(df, list_col, label_col):
    rows = []

    for _, row in df.iterrows():
        for value in safe_list(row.get(list_col)):
            value = str(value).strip()
            if value and value != "Unknown":
                rows.append({
                    label_col: value,
                    "evidence_id": row["evidence_id"],
                    "challenge": row["challenge"]
                })

    if not rows:
        return pd.DataFrame(columns=[label_col, "evidence_count", "challenge_count"])

    temp_df = pd.DataFrame(rows)

    return (
        temp_df.groupby(label_col)
        .agg(
            evidence_count=("evidence_id", "nunique"),
            challenge_count=("challenge", "nunique")
        )
        .reset_index()
        .sort_values(["evidence_count", "challenge_count"], ascending=False)
    )


def top_summary_for_chart(summary_df, label_col, top_n=10, min_count=2):
    if summary_df.empty:
        return summary_df

    chart_df = summary_df.copy()
    chart_df = chart_df[chart_df[label_col].notna()]
    chart_df = chart_df[chart_df[label_col].astype(str).str.strip() != ""]
    chart_df = chart_df[chart_df[label_col].astype(str).str.lower() != "unknown"]

    stronger_df = chart_df[chart_df["evidence_count"] >= min_count]
    if len(stronger_df) >= 5:
        chart_df = stronger_df

    chart_df = (
        chart_df
        .sort_values(["evidence_count", "challenge_count", label_col], ascending=[False, False, True])
        .head(top_n)
        .sort_values("evidence_count", ascending=True)
    )

    chart_df[f"{label_col}_short"] = chart_df[label_col].apply(lambda x: short_label(x, 38))
    return chart_df


def build_category_summary(df):
    if df.empty:
        return pd.DataFrame(columns=["category", "evidence_count", "challenge_count"])

    return (
        df.groupby("category", dropna=False)
        .agg(
            evidence_count=("evidence_id", "nunique"),
            challenge_count=("challenge", "nunique")
        )
        .reset_index()
        .sort_values(["evidence_count", "challenge_count"], ascending=False)
    )


def build_category_by_list_stack(df, list_col, stack_col):
    rows = []

    for _, row in df.iterrows():
        category = row.get("category")
        category = category if category not in [None, "", "Unknown"] else "Uncategorized"

        values = safe_list(row.get(list_col))
        if not values:
            values = ["Not specified"]

        for value in values:
            value = str(value).strip()
            if value and value != "Unknown":
                rows.append({
                    "category": category,
                    stack_col: value,
                    "evidence_id": row["evidence_id"]
                })

    if not rows:
        return pd.DataFrame(columns=["category", stack_col, "evidence_count"])

    temp_df = pd.DataFrame(rows)

    return (
        temp_df.groupby(["category", stack_col])
        .agg(evidence_count=("evidence_id", "nunique"))
        .reset_index()
    )


def build_category_by_source_status(df):
    if df.empty:
        return pd.DataFrame(columns=["category", "source_status", "evidence_count"])

    return (
        df.groupby(["category", "source_status"], dropna=False)
        .agg(evidence_count=("evidence_id", "nunique"))
        .reset_index()
    )


def build_category_by_confidence(df):
    if df.empty:
        return pd.DataFrame(columns=["category", "extraction_confidence_level", "evidence_count"])

    return (
        df.groupby(["category", "extraction_confidence_level"], dropna=False)
        .agg(evidence_count=("evidence_id", "nunique"))
        .reset_index()
    )


def build_year_summary(df):
    rows = []

    for _, row in df.iterrows():
        for year in safe_list(row.get("display_years")):
            rows.append({
                "year": int(year),
                "evidence_id": row["evidence_id"],
                "challenge": row["challenge"]
            })

    if not rows:
        return pd.DataFrame(columns=["year", "evidence_count", "challenge_count"])

    temp_df = pd.DataFrame(rows)

    return (
        temp_df.groupby("year")
        .agg(
            evidence_count=("evidence_id", "nunique"),
            challenge_count=("challenge", "nunique")
        )
        .reset_index()
        .sort_values("year")
    )


def build_source_table(df):
    rows = []

    for _, row in df.iterrows():
        url = get_first_valid_url(row.get("source_urls"))
        title = source_display_title(row)

        rows.append({
            "source_title": title,
            "source_url": url,
            "category": row.get("category"),
            "organization": clean_list_column(row.get("organizations"), max_items=3, max_len=40),
            "evidence_id": row.get("evidence_id"),
            "challenge": row.get("challenge")
        })

    if not rows:
        return pd.DataFrame()

    temp_df = pd.DataFrame(rows)

    source_df = (
        temp_df.groupby(["source_title", "source_url"], dropna=False)
        .agg(
            matched_statements=("evidence_id", "nunique"),
            challenges_extracted=("challenge", "nunique"),
            organizations=("organization", lambda x: unique_join(x, max_items=3, max_len=38)),
            categories_found=("category", lambda x: unique_join(x, max_items=4, max_len=42))
        )
        .reset_index()
        .sort_values("matched_statements", ascending=False)
    )

    return source_df


def get_source_matched_records(filtered_records_df, source_title, source_url):
    if filtered_records_df.empty:
        return pd.DataFrame()

    def matches_source(row):
        row_title = source_display_title(row)
        row_url = get_first_valid_url(row.get("source_urls"))

        same_title = row_title == source_title

        if source_url is None or (isinstance(source_url, float) and pd.isna(source_url)):
            same_url = row_url is None
        else:
            same_url = row_url == source_url

        return same_title and same_url

    return filtered_records_df[filtered_records_df.apply(matches_source, axis=1)].copy()


# ============================================================
# FILTER HELPERS
# ============================================================

def get_filter_options(df, list_col=None, scalar_col=None):
    values = set()

    if scalar_col:
        for value in df[scalar_col].dropna().tolist():
            value = str(value).strip()
            if value and value != "Unknown":
                values.add(value)

    if list_col:
        for row in df[list_col]:
            for value in safe_list(row):
                value = str(value).strip()
                if value and value != "Unknown":
                    values.add(value)

    return sorted(values)


def list_contains_any(value, selected_values):
    if not selected_values:
        return True

    current_values = [str(v).strip() for v in safe_list(value) if str(v).strip()]
    return any(selected in current_values for selected in selected_values)


def scalar_contains_any(value, selected_values):
    if not selected_values:
        return True

    return str(value).strip() in selected_values


def apply_filters(df, categories, locations, organizations, affected_groups, years, min_confidence, search_text):
    filtered = df.copy()

    if categories:
        filtered = filtered[filtered["category"].apply(lambda x: scalar_contains_any(x, categories))]

    if locations:
        filtered = filtered[filtered["locations"].apply(lambda x: list_contains_any(x, locations))]

    if organizations:
        filtered = filtered[filtered["organizations"].apply(lambda x: list_contains_any(x, organizations))]

    if affected_groups:
        filtered = filtered[filtered["affected_groups"].apply(lambda x: list_contains_any(x, affected_groups))]

    if years:
        filtered = filtered[filtered["display_years"].apply(lambda x: list_contains_any(x, years))]

    if min_confidence is not None:
        filtered = filtered[filtered["extraction_confidence"].fillna(0) >= min_confidence]

    if search_text:
        query = search_text.strip().lower()
        if query:
            filtered = filtered[
                filtered["challenge"].astype(str).str.lower().str.contains(query, na=False)
                | filtered["evidence_text"].astype(str).str.lower().str.contains(query, na=False)
                | filtered["category"].astype(str).str.lower().str.contains(query, na=False)
            ]

    return filtered


# ============================================================
# LOAD DATA
# ============================================================

st.markdown('<div class="main-title">ALC Challenges in Nova Scotia(2020-2026)</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="main-subtitle">Use the filters on the left to review extracted ALC challenges. Each challenge includes supporting evidence and a source link for verification. After applying filters, you can verify the source links.</div>',
    unsafe_allow_html=True
)

evidence_df = to_dataframe(get_evidence_rows())

required_columns = [
    "evidence_id",
    "category",
    "challenge",
    "evidence_text",
    "estimated_importance",
    "extraction_confidence",
    "locations",
    "affected_groups",
    "organizations",
    "years",
    "source_titles",
    "source_urls",
]

evidence_df = ensure_columns(evidence_df, required_columns)

if evidence_df.empty:
    st.warning("No ALC evidence records found in Neo4j. Please load graph data first.")
    st.stop()

for col in ["locations", "affected_groups", "organizations", "years", "source_titles", "source_urls"]:
    evidence_df[col] = evidence_df[col].apply(safe_list)

evidence_df["extraction_confidence"] = pd.to_numeric(evidence_df["extraction_confidence"], errors="coerce")
evidence_df["display_years"] = evidence_df["years"].apply(build_display_years)
evidence_df["source_link"] = evidence_df["source_urls"].apply(get_first_valid_url)
evidence_df["source_status"] = evidence_df.apply(source_status, axis=1)
evidence_df["extraction_confidence_level"] = evidence_df["extraction_confidence"].apply(extraction_confidence_bucket)

# Keep dashboard focused on recent ALC evidence when year information exists.
evidence_df = evidence_df[evidence_df["display_years"].apply(lambda years: len(safe_list(years)) > 0)].copy()

if evidence_df.empty:
    st.warning("No evidence records with years from 2020 to 2026 were found.")
    st.stop()


# ============================================================
# SIDEBAR FILTERS
# ============================================================

with st.sidebar:
    st.header("Filters")
    st.caption("Select filters to update the evidence table and charts.")

    category_options = get_filter_options(evidence_df, scalar_col="category")
    location_options = get_filter_options(evidence_df, list_col="locations")
    organization_options = get_filter_options(evidence_df, list_col="organizations")
    affected_group_options = get_filter_options(evidence_df, list_col="affected_groups")

    year_values = sorted(
        set(
            year
            for row in evidence_df["display_years"]
            for year in safe_list(row)
        ),
        key=lambda x: int(x)
    )

    selected_categories = st.multiselect("Challenge category", category_options)
    selected_locations = st.multiselect("Location", location_options)
    selected_organizations = st.multiselect("Organization", organization_options)
    selected_affected_groups = st.multiselect("Affected group", affected_group_options)
    selected_years = st.multiselect("Year", year_values)

    min_confidence = st.slider(
        "Minimum extraction confidence",
        min_value=0.0,
        max_value=1.0,
        value=0.0,
        step=0.05
    )

    search_text = st.text_input("Search evidence", placeholder="Search challenge or evidence text")

    if st.button("Refresh data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

filtered_df = apply_filters(
    df=evidence_df,
    categories=selected_categories,
    locations=selected_locations,
    organizations=selected_organizations,
    affected_groups=selected_affected_groups,
    years=selected_years,
    min_confidence=min_confidence,
    search_text=search_text
)


# ============================================================
# KPIs
# ============================================================

avg_confidence = filtered_df["extraction_confidence"].mean() if not filtered_df.empty else None
source_link_count = filtered_df["source_link"].notna().sum() if not filtered_df.empty else 0

k1, k2, k3, k4, k5 = st.columns(5)

with k1:
    render_kpi("Evidence records", f"{filtered_df['evidence_id'].nunique():,}" if not filtered_df.empty else "0", "📄")
with k2:
    render_kpi("Challenges", f"{filtered_df['challenge'].nunique():,}" if not filtered_df.empty else "0", "⚠️")
with k3:
    render_kpi("Categories", f"{filtered_df['category'].nunique():,}" if not filtered_df.empty else "0", "🏷️")
with k4:
    render_kpi("Records with source link", f"{source_link_count:,}", "🔗")
with k5:
    render_kpi("Avg. extraction confidence", "N/A" if avg_confidence is None or pd.isna(avg_confidence) else f"{avg_confidence:.2f}", "✓")

st.write("")


# ============================================================
# TABS
# ============================================================

tab_evidence, tab_insights, tab_sources = st.tabs(
    ["🔎 Extracted Challenges", "📊 Dashboard Insights", "🔗 Original Sources"]
)


# ============================================================
# TAB 1: EVIDENCE EXPLORER
# ============================================================

with tab_evidence:
    st.markdown("### Extracted ALC Challenges")
    st.markdown(
        """
        <div class="section-note">
        Use the filters on the left to review extracted ALC challenges. Each challenge includes supporting evidence and a source link for verification.
        </div>
        """,
        unsafe_allow_html=True
    )

    if filtered_df.empty:
        st.info("No evidence records match the selected filters.")
    else:
        display_df = filtered_df.copy()

        for col in ["locations", "affected_groups", "organizations", "display_years", "source_titles"]:
            display_df[col] = display_df[col].apply(clean_list_column)

        display_df = display_df[
            [
                "category",
                "challenge",
                "evidence_text",
                "estimated_importance",
                "extraction_confidence",
                "extraction_confidence_level",
                "locations",
                "affected_groups",
                "organizations",
                "display_years",
                "source_titles",
                "source_link",
            ]
        ]

        st.caption("Estimated importance and extraction confidence are model-generated fields. They are not directly reported by the original source.")

        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True,
            height=580,
            column_config={
                "category": st.column_config.TextColumn("Category", width="medium"),
                "challenge": st.column_config.TextColumn("Challenge", width="large"),
                "evidence_text": st.column_config.TextColumn("Evidence", width="large"),
                "estimated_importance": st.column_config.TextColumn("Estimated importance", width="small"),
                "extraction_confidence": st.column_config.NumberColumn("Extraction confidence", format="%.2f", width="small"),
                "extraction_confidence_level": st.column_config.TextColumn("Extraction confidence level", width="small"),
                "locations": st.column_config.TextColumn("Locations", width="medium"),
                "affected_groups": st.column_config.TextColumn("Affected groups", width="medium"),
                "organizations": st.column_config.TextColumn("Organizations", width="medium"),
                "display_years": st.column_config.TextColumn("Years", width="small"),
                "source_titles": st.column_config.TextColumn("Source titles", width="medium"),
                "source_link": st.column_config.LinkColumn(
                    "Evidence link",
                    display_text="Open source",
                    width="small"
                ),
            }
        )


# ============================================================
# TAB 2: INSIGHTS
# ============================================================

with tab_insights:
    st.markdown("### Insights")
    st.caption("Charts summarize the currently filtered evidence records. Extraction confidence is model-generated and is not reported by the original source.")

    if filtered_df.empty:
        st.info("No evidence records match the selected filters.")
    else:
        category_summary_df = build_category_summary(filtered_df)
        location_summary_df = explode_list_summary(filtered_df, "locations", "location")
        organization_summary_df = explode_list_summary(filtered_df, "organizations", "organization")
        affected_group_summary_df = explode_list_summary(filtered_df, "affected_groups", "affected_group")
        source_status_df = build_category_by_source_status(filtered_df)
        confidence_stack_df = build_category_by_confidence(filtered_df)
        stakeholder_stack_df = build_category_by_list_stack(filtered_df, "affected_groups", "affected_group")
        year_summary_df = build_year_summary(filtered_df)

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("#### Evidence by challenge category")
            if not category_summary_df.empty:
                chart_df = category_summary_df.copy().sort_values("evidence_count", ascending=True)
                chart_df["category_short"] = chart_df["category"].apply(lambda x: short_label(x, 38))

                fig = px.bar(
                    chart_df,
                    x="evidence_count",
                    y="category_short",
                    orientation="h",
                    text="evidence_count",
                    hover_data={
                        "category": True,
                        "category_short": False,
                        "challenge_count": True
                    }
                )
                fig.update_traces(textposition="outside", cliponaxis=False)
                fig.update_layout(xaxis_title="Evidence count", yaxis_title="", showlegend=False)
                st.plotly_chart(apply_chart_layout(fig, height=420, show_legend=False), use_container_width=True)

        with col2:
            st.markdown("#### Evidence by affected group")
            if not affected_group_summary_df.empty:
                chart_df = top_summary_for_chart(affected_group_summary_df, "affected_group", top_n=10, min_count=2)

                if chart_df.empty:
                    st.info("No affected group data for selected filters.")
                else:
                    fig = px.bar(
                        chart_df,
                        x="evidence_count",
                        y="affected_group_short",
                        orientation="h",
                        text="evidence_count",
                        hover_data={
                            "affected_group": True,
                            "affected_group_short": False,
                            "challenge_count": True
                        }
                    )
                    fig.update_traces(textposition="outside", cliponaxis=False)
                    fig.update_layout(xaxis_title="Evidence count", yaxis_title="", showlegend=False)
                    st.plotly_chart(apply_chart_layout(fig, height=420, show_legend=False), use_container_width=True)
            else:
                st.info("No affected group data for selected filters.")

        st.divider()

        st.markdown("#### Stacked bar charts")
        st.caption("These show how evidence is distributed inside each challenge category.")

        col3, col4 = st.columns(2)

        with col3:
            st.markdown("##### Challenge category by source status")
            if not source_status_df.empty:
                chart_df = prepare_horizontal_stack_df(source_status_df, "source_status", top_n_categories=10)
                fig = px.bar(
                    chart_df,
                    x="evidence_count",
                    y="category_short",
                    color="source_status",
                    orientation="h",
                    barmode="stack",
                    text="evidence_count",
                    hover_data={"category": True, "category_short": False}
                )
                fig.update_traces(textposition="inside", cliponaxis=False)
                fig.update_layout(xaxis_title="Evidence count", yaxis_title="", legend_title_text="Source status")
                fig.update_yaxes(categoryorder="total ascending")
                st.plotly_chart(apply_chart_layout(fig, height=430, legend_position="right"), use_container_width=True)

        with col4:
            st.markdown("##### Challenge category by extraction confidence level")
            if not confidence_stack_df.empty:
                chart_df = prepare_horizontal_stack_df(confidence_stack_df, "extraction_confidence_level", top_n_categories=10)
                fig = px.bar(
                    chart_df,
                    x="evidence_count",
                    y="category_short",
                    color="extraction_confidence_level",
                    orientation="h",
                    barmode="stack",
                    text="evidence_count",
                    hover_data={"category": True, "category_short": False}
                )
                fig.update_traces(textposition="inside", cliponaxis=False)
                fig.update_layout(xaxis_title="Evidence count", yaxis_title="", legend_title_text="Extraction confidence")
                fig.update_yaxes(categoryorder="total ascending")
                st.plotly_chart(apply_chart_layout(fig, height=430, legend_position="right"), use_container_width=True)

        st.markdown("##### Challenge category by affected group")
        if not stakeholder_stack_df.empty:
            # Keep only stronger affected groups so chart is readable.
            top_groups = (
                stakeholder_stack_df.groupby("affected_group")["evidence_count"]
                .sum()
                .sort_values(ascending=False)
                .head(8)
                .index
                .tolist()
            )
            stakeholder_stack_df = stakeholder_stack_df[
                stakeholder_stack_df["affected_group"].isin(top_groups)
            ]

            chart_df = prepare_horizontal_stack_df(stakeholder_stack_df, "affected_group", top_n_categories=10)
            fig = px.bar(
                chart_df,
                x="evidence_count",
                y="category_short",
                color="affected_group",
                orientation="h",
                barmode="stack",
                text="evidence_count",
                hover_data={"category": True, "category_short": False}
            )
            fig.update_traces(textposition="inside", cliponaxis=False)
            fig.update_layout(xaxis_title="Evidence count", yaxis_title="", legend_title_text="Affected group")
            fig.update_yaxes(categoryorder="total ascending")
            st.plotly_chart(apply_chart_layout(fig, height=520, legend_position="right"), use_container_width=True)

        st.divider()

        col5, col6 = st.columns(2)

        with col5:
            st.markdown("#### Top locations")
            if not location_summary_df.empty:
                chart_df = top_summary_for_chart(location_summary_df, "location", top_n=10, min_count=2)

                if chart_df.empty:
                    st.info("No clean location data for selected filters.")
                else:
                    fig = px.bar(
                        chart_df,
                        x="evidence_count",
                        y="location_short",
                        orientation="h",
                        text="evidence_count",
                        hover_data={
                            "location": True,
                            "location_short": False,
                            "challenge_count": True
                        }
                    )
                    fig.update_traces(textposition="outside", cliponaxis=False)
                    fig.update_layout(xaxis_title="Evidence count", yaxis_title="", showlegend=False)
                    st.plotly_chart(apply_chart_layout(fig, height=390, show_legend=False), use_container_width=True)

        with col6:
            st.markdown("#### Top organizations")
            if not organization_summary_df.empty:
                chart_df = top_summary_for_chart(organization_summary_df, "organization", top_n=10, min_count=2)

                if chart_df.empty:
                    st.info("No clean organization data for selected filters.")
                else:
                    fig = px.bar(
                        chart_df,
                        x="evidence_count",
                        y="organization_short",
                        orientation="h",
                        text="evidence_count",
                        hover_data={
                            "organization": True,
                            "organization_short": False,
                            "challenge_count": True
                        }
                    )
                    fig.update_traces(textposition="outside", cliponaxis=False)
                    fig.update_layout(xaxis_title="Evidence count", yaxis_title="", showlegend=False)
                    st.plotly_chart(apply_chart_layout(fig, height=390, show_legend=False), use_container_width=True)

        st.markdown("#### Evidence and challenges by year")
        if not year_summary_df.empty:
            available_line_years = year_summary_df["year"].astype(int).sort_values().tolist()
            selected_line_years = st.multiselect(
                "Select years for this line graph",
                options=available_line_years,
                default=available_line_years,
                key="line_graph_year_filter"
            )

            line_df = year_summary_df[year_summary_df["year"].isin(selected_line_years)].copy()

            if line_df.empty:
                st.info("Select at least one year to show the line graph.")
            else:
                fig = go.Figure()
                fig.add_trace(
                    go.Scatter(
                        x=line_df["year"],
                        y=line_df["evidence_count"],
                        mode="lines+markers",
                        name="Evidence records",
                        line=dict(width=3),
                        marker=dict(size=8)
                    )
                )
                fig.add_trace(
                    go.Scatter(
                        x=line_df["year"],
                        y=line_df["challenge_count"],
                        mode="lines+markers",
                        name="Challenges",
                        line=dict(width=3),
                        marker=dict(size=8)
                    )
                )
                fig.update_layout(
                    xaxis_title="Year",
                    yaxis_title="Count",
                    hovermode="x unified",
                    xaxis=dict(type="linear", tickmode="linear", dtick=1),
                    legend_title_text="Metric"
                )
                st.plotly_chart(apply_chart_layout(fig, height=410, legend_position="right"), use_container_width=True)
        else:
            st.info("No year data for selected filters.")


# ============================================================
# TAB 3: ORIGINAL SOURCES
# ============================================================

with tab_sources:
    st.markdown("### Original Sources")
    st.markdown(
        """
        <div class="section-note">
        This page shows the original websites or PDFs used to extract ALC challenges. Open each source to view the matched statements extracted from it, then click <b>Open original source</b> to verify the source page.
        </div>
        """,
        unsafe_allow_html=True
    )

    if filtered_df.empty:
        st.info("No source records match the selected filters.")
    else:
        source_df = build_source_table(filtered_df)

        if source_df.empty:
            st.info("No source table could be built from the filtered records.")
        else:
            total_sources = source_df["source_title"].nunique()
            total_matched_statements = source_df["matched_statements"].sum()
            records_with_url = filtered_df["source_link"].notna().sum()

            s1, s2, s3 = st.columns(3)
            with s1:
                st.metric("Original sources", f"{total_sources:,}")
            with s2:
                st.metric("Matched statements", f"{int(total_matched_statements):,}")
            with s3:
                st.metric("Records with source link", f"{int(records_with_url):,}")

            st.caption("Matched statements means the number of supporting evidence statements extracted from that original source.")

            top_sources_df = source_df.head(10).copy()
            top_sources_df["source_short"] = top_sources_df["source_title"].apply(lambda x: short_label(x, 48))
            top_sources_df = top_sources_df.sort_values("matched_statements", ascending=True)

            if not top_sources_df.empty:
                st.markdown("#### Top original sources by matched statements")
                fig = px.bar(
                    top_sources_df,
                    x="matched_statements",
                    y="source_short",
                    orientation="h",
                    text="matched_statements",
                    hover_data={
                        "source_title": True,
                        "source_short": False,
                        "challenges_extracted": True,
                        "categories_found": True
                    }
                )
                fig.update_traces(textposition="outside", cliponaxis=False)
                fig.update_layout(
                    xaxis_title="Matched statements",
                    yaxis_title="",
                    showlegend=False
                )
                st.plotly_chart(apply_chart_layout(fig, height=max(360, 34 * len(top_sources_df) + 110), show_legend=False), use_container_width=True)

            st.markdown("#### Review matched statements by source")

            source_search = st.text_input(
                "Search sources",
                placeholder="Search source title, organization, or category",
                key="source_search"
            )

            display_source_df = source_df.copy()

            if source_search.strip():
                q = source_search.strip().lower()
                display_source_df = display_source_df[
                    display_source_df["source_title"].astype(str).str.lower().str.contains(q, na=False)
                    | display_source_df["organizations"].astype(str).str.lower().str.contains(q, na=False)
                    | display_source_df["categories_found"].astype(str).str.lower().str.contains(q, na=False)
                ]

            if display_source_df.empty:
                st.info("No sources match the source search.")
            else:
                for index, source_row in display_source_df.iterrows():
                    source_title = source_row["source_title"]
                    source_url = source_row["source_url"]
                    matched_count = int(source_row["matched_statements"]) if not pd.isna(source_row["matched_statements"]) else 0
                    challenge_count = int(source_row["challenges_extracted"]) if not pd.isna(source_row["challenges_extracted"]) else 0

                    expander_title = f"{short_label(source_title, 95)} — View {matched_count} matched statements"

                    with st.expander(expander_title):
                        c1, c2, c3 = st.columns([1.2, 1, 1])
                        with c1:
                            st.markdown(f"**Original source:** {source_title}")
                        with c2:
                            st.markdown(f"**Challenges extracted:** {challenge_count}")
                        with c3:
                            st.markdown(f"**Matched statements:** {matched_count}")

                        if source_row.get("organizations"):
                            st.markdown(f"**Organization:** {source_row['organizations']}")

                        if source_row.get("categories_found"):
                            st.markdown(f"**ALC categories found:** {source_row['categories_found']}")

                        if source_url and not pd.isna(source_url):
                            st.link_button("Open original source", source_url)
                        else:
                            st.warning("No source URL available for this source.")

                        related_records = get_source_matched_records(
                            filtered_records_df=filtered_df,
                            source_title=source_title,
                            source_url=source_url
                        )

                        if related_records.empty:
                            st.info("No matched statements found for this source after filters.")
                        else:
                            matched_df = related_records.copy()

                            for col in ["locations", "affected_groups", "organizations", "display_years"]:
                                matched_df[col] = matched_df[col].apply(clean_list_column)

                            matched_df = matched_df[
                                [
                                    "category",
                                    "challenge",
                                    "evidence_text",
                                    "locations",
                                    "affected_groups",
                                    "organizations",
                                    "display_years",
                                    "estimated_importance",
                                    "extraction_confidence",
                                ]
                            ]

                            st.dataframe(
                                matched_df,
                                use_container_width=True,
                                hide_index=True,
                                height=min(420, 120 + 45 * len(matched_df)),
                                column_config={
                                    "category": st.column_config.TextColumn("Category", width="medium"),
                                    "challenge": st.column_config.TextColumn("Extracted challenge", width="large"),
                                    "evidence_text": st.column_config.TextColumn("Matched statement", width="large"),
                                    "locations": st.column_config.TextColumn("Locations", width="medium"),
                                    "affected_groups": st.column_config.TextColumn("Affected groups", width="medium"),
                                    "organizations": st.column_config.TextColumn("Organizations", width="medium"),
                                    "display_years": st.column_config.TextColumn("Years", width="small"),
                                    "estimated_importance": st.column_config.TextColumn("Estimated importance", width="small"),
                                    "extraction_confidence": st.column_config.NumberColumn(
                                        "Extraction confidence",
                                        format="%.2f",
                                        width="small"
                                    ),
                                }
                            )
