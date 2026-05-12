import pandas as pd
import streamlit as st
from pathlib import Path

st.set_page_config(page_title="CoinMarketCap Leads Dashboard", layout="wide")

st.title("📊 CoinMarketCap Leads Dashboard")

csv_path = Path("output/leads.csv")

if not csv_path.exists():
    st.warning("output/leads.csv not found. Run main.py first.")
    st.stop()

df = pd.read_csv(csv_path)
df = df.dropna(axis=1, how="all")

st.metric("Total Projects", len(df))

search = st.text_input("Search by project name")

if search:
    df = df[df["Project Name"].astype(str).str.contains(search, case=False, na=False)]

st.dataframe(df, use_container_width=True)

st.download_button(
    "Download CSV",
    data=df.to_csv(index=False).encode("utf-8"),
    file_name="leads.csv",
    mime="text/csv"
)
