import io
import os
import time
import requests
import urllib3
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Reuse your Day 4 & Day 5 assurance parsers
from occupancy_inventory import (
    build_occupancy_dataframe,
    build_inventory_dataframe,
    export_to_excel,
)
from datacomm_bot import get_optical_summary

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==============================================================================
# 1. PAGE SETUP & LAYOUT CONFIGURATION
# ==============================================================================
st.set_page_config(
    page_title="Core & Datacomm Assurance Dashboard",
    page_icon="📡",
    layout="wide",
)

st.title("Core & Datacomm Network Assurance Dashboard")
st.caption(
    "Real-Time Link Occupancy (JD #6) • Optical Fault Triage (JD #5) • "
    "CMDB Hardware Inventory (JD #4) • BAU Automation (JD #1 & #2)"
)

# Load parsed DataFrames
df_occ = build_occupancy_dataframe()
df_inv = build_inventory_dataframe()
df_opt = pd.DataFrame(get_optical_summary())
df_opt.rename(
    columns={
        "interface": "INTERFACE",
        "rx": "RX_POWER_dBm",
        "tx": "TX_POWER_dBm",
        "state": "OPTICAL_STATUS",
    },
    inplace=True,
)
df_opt["HOSTNAME"] = "PE-JAKTIM-01"

# ==============================================================================
# 2. SIDEBAR FILTERS & EXCEL EXPORT BUTTON
# ==============================================================================
st.sidebar.header("🔍 NOC Filter Controls")
selected_hosts = st.sidebar.multiselect(
    "Filter by Router Hostname:",
    options=df_occ["HOSTNAME"].unique().tolist(),
    default=df_occ["HOSTNAME"].unique().tolist(),
)

occ_threshold = st.sidebar.slider(
    "Capacity Alert Threshold (%):",
    min_value=50,
    max_value=95,
    value=80,
    step=5,
)

show_only_alarms = st.sidebar.checkbox("Show Only Links with Alarms / High Load", value=False)

# Filter occupancy dataframe based on sidebar selection
df_occ_filtered = df_occ[df_occ["HOSTNAME"].isin(selected_hosts)].copy()
if show_only_alarms:
    df_occ_filtered = df_occ_filtered[
        (df_occ_filtered["PEAK_OCCUPANCY_%"] >= occ_threshold)
        | (df_occ_filtered["PHY_STATE"].str.upper() != "UP")
        | (df_occ_filtered["CRC_ERRORS"] > 0)
    ]

# Generate in-memory Excel file for 1-click download in sidebar
excel_buffer = io.BytesIO()
export_to_excel(df_occ, df_inv, excel_buffer)
excel_buffer.seek(0)

st.sidebar.divider()
st.sidebar.subheader("📥 BAU Report Export")
st.sidebar.download_button(
    label="📊 Download Excel Report (.xlsx)",
    data=excel_buffer,
    file_name="Assurance_Occupancy_Inventory_Report.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)

# ==============================================================================
# 3. TOP KPI METRIC CARDS
# ==============================================================================
total_links = len(df_occ)
high_occ_links = len(df_occ[df_occ["PEAK_OCCUPANCY_%"] >= occ_threshold])
optical_alarms = len(df_opt[df_opt["RX_POWER_dBm"] <= -22.0])
total_assets = len(df_inv)

col1, col2, col3, col4 = st.columns(4)
col1.metric("Monitored Core/Metro Links", total_links, "Huawei VRP & Cisco XR")
col2.metric(
    f"Links >= {occ_threshold}% Occupancy",
    high_occ_links,
    delta=f"{high_occ_links} Capacity Warnings",
    delta_color="inverse",
)
col3.metric(
    "Active Optical Alarms (<-22 dBm)",
    optical_alarms,
    delta="1 LOS, 1 High Attenuation",
    delta_color="inverse",
)
col4.metric("Tracked CMDB Hardware Assets", total_assets, "Chassis, Linecards & SFPs")

st.divider()

# ==============================================================================
# 4. ROW 1: TOP HIGH-OCCUPANCY LINKS & ACTIVE OPTICAL ALARMS
# ==============================================================================
left_col, right_col = st.columns([3, 2])

with left_col:
    st.subheader(f"📈 Top Link Occupancy (Threshold: {occ_threshold}%)")
    chart_df = df_occ_filtered.copy()
    chart_df["LINK_LABEL"] = chart_df["HOSTNAME"] + " | " + chart_df["INTERFACE"]
    st.bar_chart(
        chart_df.set_index("LINK_LABEL")[["IN_OCCUPANCY_%", "OUT_OCCUPANCY_%"]],
        height=280,
    )

with right_col:
    st.subheader("🚨 Active Optical Transceiver Alarms (dBm)")
    st.dataframe(
        df_opt[["HOSTNAME", "INTERFACE", "RX_POWER_dBm", "TX_POWER_dBm", "OPTICAL_STATUS"]],
        use_container_width=True,
        hide_index=True,
    )
    st.info(
        "**Triage Reference:** Healthy `Rx Power` is **-8 to -18 dBm**. "
        "Readings below **-22 dBm** trigger CRC bit errors; **-30 to -40 dBm** indicates `LOS` (Fiber Cut)."
    )

# ==============================================================================
# 5. ROW 2: DETAILED LINK OCCUPANCY TABLE (Color-Coded)
# ==============================================================================
st.subheader("📋 Multi-Vendor Link Occupancy & CRC Triage Table")


def highlight_assurance_rows(row):
    flag = str(row["ASSURANCE_FLAG"])
    if "CRITICAL" in flag:
        return ["background-color: rgba(255, 75, 75, 0.20)"] * len(row)
    if "WARNING" in flag or row["PEAK_OCCUPANCY_%"] >= occ_threshold:
        return ["background-color: rgba(255, 165, 0, 0.20)"] * len(row)
    return [""] * len(row)


st.dataframe(
    df_occ_filtered.style.apply(highlight_assurance_rows, axis=1),
    use_container_width=True,
    hide_index=True,
)

st.divider()

# ==============================================================================
# 6. ROW 3: HARDWARE INVENTORY (CMDB) & SNMP / LIVE MIKROTIK CHR LAB POLLING
# ==============================================================================
inv_col, snmp_col = st.columns([3, 2])

with inv_col:
    st.subheader("🗄 Network Hardware Inventory (CMDB / Serial Search)")
    search_query = st.text_input(
        "Search Inventory by Serial/BarCode, Part Number (e.g., SFP-10G-LR), or Hostname:",
        value="",
    )
    df_inv_filtered = df_inv[df_inv["HOSTNAME"].isin(selected_hosts)]
    if search_query:
        mask = (
            df_inv_filtered["SERIAL_BARCODE"].str.contains(search_query, case=False, na=False)
            | df_inv_filtered["PART_NUMBER"].str.contains(search_query, case=False, na=False)
            | df_inv_filtered["DESCRIPTION"].str.contains(search_query, case=False, na=False)
            | df_inv_filtered["HOSTNAME"].str.contains(search_query, case=False, na=False)
        )
        df_inv_filtered = df_inv_filtered[mask]

    st.dataframe(df_inv_filtered, use_container_width=True, hide_index=True)

with snmp_col:
    st.subheader("⚡ SNMP `ifHCOutOctets` & Live CHR Poller")
    tab1, tab2 = st.tabs(["SNMP 64-Bit Counter Simulator", "Live MikroTik CHR Poller"])

    with tab1:
        st.caption(
            "OID `1.3.6.1.2.1.31.1.1.1.10` (`ifHCOutOctets`) polls cumulative bytes at $t_1$ and $t_2$:"
        )
        c1, c2 = st.columns(2)
        t1_octets = c1.number_input("Poll t1 Octets (Bytes):", value=1_000_000_000_000, step=10_000_000_000)
        t2_octets = c2.number_input("Poll t2 Octets (Bytes):", value=1_315_000_000_000, step=10_000_000_000)
        interval_sec = c1.number_input("Poll Interval Δt (sec):", value=300, min_value=1)
        port_speed_mbps = c2.selectbox("ifHighSpeed (Mbps):", [1000, 10000, 40000, 100000], index=1)

        delta_bytes = max(0, t2_octets - t1_octets)
        rate_bps = (delta_bytes * 8) / interval_sec
        rate_mbps = rate_bps / 1e6
        calc_occ_pct = (rate_mbps / port_speed_mbps) * 100

        st.metric(
            "Calculated 5-Min Rate & Occupancy",
            f"{rate_mbps:,.2f} Mbps ({calc_occ_pct:.2f}%)",
            delta="CRITICAL >= 80%" if calc_occ_pct >= 80 else "NORMAL < 80%",
            delta_color="inverse" if calc_occ_pct >= 80 else "normal",
        )

    with tab2:
        c_ip, c_proto = st.columns([2, 1])
        default_chr_ip = os.getenv("MIKROTIK_HOST", "192.168.56.101")
        default_chr_user = os.getenv("MIKROTIK_USERNAME", os.getenv("MIKROTIK_USER", "admin"))
        default_chr_pass = os.getenv("MIKROTIK_PASSWORD", os.getenv("MIKROTIK_PASS", ""))

        chr_ip = c_ip.text_input("MikroTik CHR Host IP:", value=default_chr_ip)
        proto = c_proto.selectbox("Protocol:", ["http", "https"], index=0)

        c_user, c_pass = st.columns(2)
        chr_user = c_user.text_input("Username:", value=default_chr_user)
        chr_pass = c_pass.text_input("Password:", value=default_chr_pass, type="password")

        if st.button("🔄 Poll Live MikroTik CHR (REST / SNMP Counters)"):
            url = f"{proto}://{chr_ip}/rest/interface"
            try:
                r1 = requests.get(url, auth=(chr_user, chr_pass), verify=False, timeout=3)
                data1 = r1.json()

                # Check if MikroTik returned an error dict (e.g., 401 Unauthorized)
                if isinstance(data1, dict):
                    st.error(f"MikroTik REST API returned HTTP {r1.status_code}: {data1}")
                elif isinstance(data1, list):
                    time.sleep(1)
                    r2 = requests.get(url, auth=(chr_user, chr_pass), verify=False, timeout=3)
                    data2 = r2.json()

                    rows = []
                    for i1, i2 in zip(data1, data2):
                        rx_bps = (int(i2.get("rx-byte", 0)) - int(i1.get("rx-byte", 0))) * 8
                        tx_bps = (int(i2.get("tx-byte", 0)) - int(i1.get("tx-byte", 0))) * 8
                        rows.append({
                            "Interface": i2.get("name"),
                            "Running": i2.get("running"),
                            "ifHCInOctets (Rx Bytes)": f"{int(i2.get('rx-byte', 0)):,}",
                            "ifHCOutOctets (Tx Bytes)": f"{int(i2.get('tx-byte', 0)):,}",
                            "Live Rx (bps)": rx_bps,
                            "Live Tx (bps)": tx_bps,
                        })
                    st.success(f"Connected to {chr_ip} via {proto.upper()} (`PE-JAKTIM-01`)")
                    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            except Exception as e:
                st.warning(f"Could not reach `{url}`: {e}")