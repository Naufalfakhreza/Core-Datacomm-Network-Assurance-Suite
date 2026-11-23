import io
from pathlib import Path
import textfsm
import pandas as pd

# ==============================================================================
# 1. REALISTIC MULTI-VENDOR CLI OUTPUTS (Huawei VRP & Cisco IOS-XR)
# ==============================================================================

HUAWEI_DISPLAY_INTERFACE_RAW = """
10GE1/0/1 current state : UP
Line protocol current state : UP
Description: TO_AGG-CAWANG-01_10GE2/0/1_ETHTRUNK10
Route Port,The Maximum Transmit Unit is 9000
Speed : 10000,  Loopback: NONE
Last 300 seconds input rate 8450000000 bits/sec, 912000 packets/sec
Last 300 seconds output rate 6120000000 bits/sec, 710000 packets/sec
Input errors: 14820,  CRC: 14795,  Giants: 0
Output drops: 412

10GE1/0/2 current state : DOWN
Line protocol current state : DOWN
Description: TO_AGG-CAWANG-01_10GE2/0/2_ETHTRUNK10
Route Port,The Maximum Transmit Unit is 9000
Speed : 10000,  Loopback: NONE
Last 300 seconds input rate 0 bits/sec, 0 packets/sec
Last 300 seconds output rate 0 bits/sec, 0 packets/sec
Input errors: 0,  CRC: 0,  Giants: 0
Output drops: 0

100GE2/0/0 current state : UP
Line protocol current state : UP
Description: TO_P-CORE-GAMBIR-01_100GE4/0/0
Route Port,The Maximum Transmit Unit is 9216
Speed : 100000,  Loopback: NONE
Last 300 seconds input rate 42300000000 bits/sec, 4800000 packets/sec
Last 300 seconds output rate 82900000000 bits/sec, 9150000 packets/sec
Input errors: 0,  CRC: 0,  Giants: 0
Output drops: 1890
"""

CISCO_XR_SHOW_INTERFACES_RAW = """
TenGigE0/0/0/1 is up, line protocol is up 
  Interface state transitions: 3
  Hardware is TenGigE, address is 008a.9612.b001 (bia 008a.9612.b001)
  Description: TO_PE-BEKASI-02_Te0/0/0/1
  Internet address is 10.10.55.1/30
  MTU 9000 bytes, BW 10000000 Kbit (Max: 10000000 Kbit)
  5 minute input rate 8810000000 bits/sec, 945000 packets/sec
  5 minute output rate 3200000000 bits/sec, 410000 packets/sec
  12540000 packets input, 14200000000 bytes, 0 total input drops
  0 input errors, 0 CRC, 0 frame, 0 overrun, 0 ignored, 0 abort

HundredGigE0/1/0/0 is up, line protocol is up 
  Interface state transitions: 1
  Hardware is HundredGigE, address is 008a.9612.c000 (bia 008a.9612.c000)
  Description: TO_P-CORE-JKT-01_Hu0/1/0/0
  Internet address is 10.10.100.1/30
  MTU 9216 bytes, BW 100000000 Kbit (Max: 100000000 Kbit)
  5 minute input rate 54000000000 bits/sec, 5900000 packets/sec
  5 minute output rate 61500000000 bits/sec, 6700000 packets/sec
  98540000 packets input, 94200000000 bytes, 0 total input drops
  0 input errors, 0 CRC, 0 frame, 0 overrun, 0 ignored, 0 abort
"""

HUAWEI_DISPLAY_ELABEL_RAW = """
/$[System Integration Version]
/$SystemIntegrationVersion=3.0

[Slot_1]
/$[Board Integration Version]
/$BoardIntegrationVersion=3.0

[Main_Board]

/$[ArchivesInfo Version]
/$ArchivesInfoVersion=3.0

[Board Properties]
BoardType=CR5DLPUF512A
BarCode=210235987610J4000188
Item=03051234
Description=Flexible Card Line Processing Unit(Slot 1, LPUF-51)
Manufactured=2023-08-14
VendorName=Huawei

[Port_1]
BoardType=SFP-10G-LR
BarCode=03021VWX10293847
Item=34060290
Description=Optical Transceiver,SFP+,10G,1310nm,10km,SM
Manufactured=2024-02-10
VendorName=FINISAR CORP.

[Slot_2]
[Main_Board]
[Board Properties]
BoardType=CR5DMPUB4010
BarCode=210235987610K8000992
Item=03059988
Description=Main Processing Unit(Slot 2, MPUB)
Manufactured=2023-09-01
VendorName=Huawei
"""

CISCO_XR_SHOW_INVENTORY_RAW = """
NAME: "0/RSP0/CPU0", DESCR: "ASR9K Route Switch Processor 880G"
PID: A9K-RSP880-SE     , VID: V03, SN: FOC2341N0AB

NAME: "0/0/CPU0", DESCR: "8-port 100GE / 20-port 10GE Combo Linecard"
PID: A9K-8X100GE-SE    , VID: V02, SN: FOC2402P9KL

NAME: "0/0/0/1", DESCR: "SFP+ 10GBASE-LR Pluggable Optics Module"
PID: SFP-10G-LR        , VID: V03, SN: FNS23991042
"""

# ==============================================================================
# 2. TEXTFSM TEMPLATES (Occupancy & Inventory State Machines)
# ==============================================================================

HUAWEI_INT_TEMPLATE = """Value Required INTERFACE (\\S+)
Value PHY_STATE (UP|DOWN|\\*DOWN)
Value PROT_STATE (UP|DOWN)
Value DESCRIPTION (.+?)
Value SPEED_MBPS (\\d+)
Value IN_BPS (\\d+)
Value OUT_BPS (\\d+)
Value CRC_ERRORS (\\d+)

Start
  ^${INTERFACE}\\s+current state\\s*:\\s*${PHY_STATE}
  ^Line protocol current state\\s*:\\s*${PROT_STATE}
  ^Description:\\s*${DESCRIPTION}$$
  ^Speed\\s*:\\s*${SPEED_MBPS},
  ^Last 300 seconds input rate\\s+${IN_BPS}\\s+bits/sec
  ^Last 300 seconds output rate\\s+${OUT_BPS}\\s+bits/sec
  ^Input errors:\\s+\\d+,\\s+CRC:\\s+${CRC_ERRORS} -> Record
"""

CISCO_XR_INT_TEMPLATE = """Value Required INTERFACE (\\S+)
Value PHY_STATE (up|down|administratively down)
Value PROT_STATE (up|down)
Value DESCRIPTION (.+?)
Value BW_KBIT (\\d+)
Value IN_BPS (\\d+)
Value OUT_BPS (\\d+)
Value CRC_ERRORS (\\d+)

Start
  ^${INTERFACE} is ${PHY_STATE}, line protocol is ${PROT_STATE}
  ^\\s+Description:\\s*${DESCRIPTION}$$
  ^\\s+MTU \\d+ bytes, BW ${BW_KBIT} Kbit
  ^\\s+5 minute input rate ${IN_BPS} bits/sec
  ^\\s+5 minute output rate ${OUT_BPS} bits/sec
  ^\\s+\\d+ input errors, ${CRC_ERRORS} CRC -> Record
"""

HUAWEI_ELABEL_TEMPLATE = """Value Filldown SLOT (Slot_\\d+)
Value Filldown COMPONENT (Main_Board|Port_\\d+)
Value Required BOARD_TYPE (\\S+)
Value Required SERIAL_BARCODE (\\S+)
Value DESCRIPTION (.+?)
Value VENDOR (.+?)

Start
  ^\\[${SLOT}\\]
  ^\\[${COMPONENT}\\]
  ^BoardType=${BOARD_TYPE}
  ^BarCode=${SERIAL_BARCODE}
  ^Description=${DESCRIPTION}$$
  ^VendorName=${VENDOR}$$ -> Record
"""

CISCO_INV_TEMPLATE = """Value Required COMPONENT (.+?)
Value DESCRIPTION (.+?)
Value PART_NUMBER (\\S+)
Value Required SERIAL_BARCODE (\\S+)

Start
  ^NAME:\\s+"${COMPONENT}",\\s+DESCR:\\s+"${DESCRIPTION}"
  ^PID:\\s+${PART_NUMBER}\\s*,\\s+VID:\\s+\\S+,\\s+SN:\\s+${SERIAL_BARCODE} -> Record
"""


# ==============================================================================
# 3. HELPER FUNCTION: PARSE TEXT VIA TEXTFSM INTO PANDAS DATAFRAME
# ==============================================================================
def run_textfsm(template_str: str, raw_cli: str) -> pd.DataFrame:
    fsm = textfsm.TextFSM(io.StringIO(template_str))
    parsed_rows = fsm.ParseText(raw_cli)
    return pd.DataFrame(parsed_rows, columns=fsm.header)


# ==============================================================================
# 4. PARSE & NORMALIZE LINK OCCUPANCY (Huawei + Cisco Combined)
# ==============================================================================
def build_occupancy_dataframe() -> pd.DataFrame:
    # A. Parse Huawei Interfaces
    df_hw = run_textfsm(HUAWEI_INT_TEMPLATE, HUAWEI_DISPLAY_INTERFACE_RAW)
    df_hw["HOSTNAME"] = "PE-JAKTIM-01"
    df_hw["VENDOR"] = "Huawei VRP"
    df_hw["CAPACITY_MBPS"] = pd.to_numeric(df_hw["SPEED_MBPS"])

    # B. Parse Cisco IOS-XR Interfaces
    df_cxr = run_textfsm(CISCO_XR_INT_TEMPLATE, CISCO_XR_SHOW_INTERFACES_RAW)
    df_cxr["HOSTNAME"] = "PE-SURABAYA-02"
    df_cxr["VENDOR"] = "Cisco IOS-XR"
    # Convert Cisco BW from Kbit to Mbps (10,000,000 Kbit -> 10,000 Mbps)
    df_cxr["CAPACITY_MBPS"] = pd.to_numeric(df_cxr["BW_KBIT"]) / 1000.0

    # Combine into unified Telco Assurance table
    common_cols = [
        "HOSTNAME", "VENDOR", "INTERFACE", "PHY_STATE", "DESCRIPTION",
        "CAPACITY_MBPS", "IN_BPS", "OUT_BPS", "CRC_ERRORS"
    ]
    df = pd.concat([df_hw[common_cols], df_cxr[common_cols]], ignore_index=True)

    # Convert numeric columns
    df["IN_Mbps"] = (pd.to_numeric(df["IN_BPS"]) / 1e6).round(2)
    df["OUT_Mbps"] = (pd.to_numeric(df["OUT_BPS"]) / 1e6).round(2)
    df["CRC_ERRORS"] = pd.to_numeric(df["CRC_ERRORS"])

    # Calculate 5-Minute Occupancy %
    df["IN_OCCUPANCY_%"] = ((df["IN_Mbps"] / df["CAPACITY_MBPS"]) * 100).round(2)
    df["OUT_OCCUPANCY_%"] = ((df["OUT_Mbps"] / df["CAPACITY_MBPS"]) * 100).round(2)
    df["PEAK_OCCUPANCY_%"] = df[["IN_OCCUPANCY_%", "OUT_OCCUPANCY_%"]].max(axis=1)

    # Apply Assurance Triage Status Rules
    def evaluate_status(row):
        if str(row["PHY_STATE"]).upper() != "UP":
            return "CRITICAL: LINK DOWN"
        if row["PEAK_OCCUPANCY_%"] >= 80.0 and row["CRC_ERRORS"] > 0:
            return "CRITICAL: HIGH LOAD (>=80%) + CRC ERRORS"
        if row["PEAK_OCCUPANCY_%"] >= 80.0:
            return "WARNING: CAPACITY THRESHOLD (>=80%)"
        if row["CRC_ERRORS"] > 0:
            return "WARNING: OPTICAL CRC DEGRADATION"
        return "NORMAL (<80%)"

    df["ASSURANCE_FLAG"] = df.apply(evaluate_status, axis=1)

    return df[[
        "HOSTNAME", "VENDOR", "INTERFACE", "PHY_STATE", "DESCRIPTION",
        "CAPACITY_MBPS", "IN_Mbps", "OUT_Mbps", "IN_OCCUPANCY_%",
        "OUT_OCCUPANCY_%", "PEAK_OCCUPANCY_%", "CRC_ERRORS", "ASSURANCE_FLAG"
    ]]


# ==============================================================================
# 5. PARSE & NORMALIZE HARDWARE INVENTORY (Huawei elabel + Cisco Inventory)
# ==============================================================================
def build_inventory_dataframe() -> pd.DataFrame:
    df_hw_inv = run_textfsm(HUAWEI_ELABEL_TEMPLATE, HUAWEI_DISPLAY_ELABEL_RAW)
    df_hw_inv["HOSTNAME"] = "PE-JAKTIM-01"
    df_hw_inv["OS_VENDOR"] = "Huawei VRP"
    df_hw_inv["SLOT_LOCATION"] = df_hw_inv["SLOT"] + "/" + df_hw_inv["COMPONENT"]
    df_hw_inv["PART_NUMBER"] = df_hw_inv["BOARD_TYPE"]

    df_cxr_inv = run_textfsm(CISCO_INV_TEMPLATE, CISCO_XR_SHOW_INVENTORY_RAW)
    df_cxr_inv["HOSTNAME"] = "PE-SURABAYA-02"
    df_cxr_inv["OS_VENDOR"] = "Cisco IOS-XR"
    df_cxr_inv["SLOT_LOCATION"] = df_cxr_inv["COMPONENT"]
    df_cxr_inv["VENDOR"] = "Cisco Systems"

    inv_cols = [
        "HOSTNAME", "OS_VENDOR", "SLOT_LOCATION",
        "PART_NUMBER", "SERIAL_BARCODE", "DESCRIPTION", "VENDOR"
    ]
    return pd.concat([df_hw_inv[inv_cols], df_cxr_inv[inv_cols]], ignore_index=True)


# ==============================================================================
# 6. EXPORT TO FORMATTED EXCEL (.XLSX) WITH HIGHLIGHTING FOR >80% LINKS
# ==============================================================================
def export_to_excel(df_occ: pd.DataFrame, df_inv: pd.DataFrame, filename: str):
    from openpyxl.styles import PatternFill, Font

    with pd.ExcelWriter(filename, engine="openpyxl") as writer:
        df_occ.to_excel(writer, sheet_name="Link_Occupancy", index=False)
        df_inv.to_excel(writer, sheet_name="Hardware_Inventory", index=False)

        workbook = writer.book
        ws_occ = writer.sheets["Link_Occupancy"]
        ws_inv = writer.sheets["Hardware_Inventory"]

        # Define Header & Alert Colors
        header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
        header_font = Font(color="FFFFFF", bold=True)
        alert_fill = PatternFill(start_color="FFD9D9", end_color="FFD9D9", fill_type="solid")
        alert_font = Font(color="9C0006", bold=True)

        # Style Headers & Auto-Fit Column Widths on Both Sheets
        for ws in [ws_occ, ws_inv]:
            for cell in ws[1]:
                cell.fill = header_fill
                cell.font = header_font
            for col in ws.columns:
                max_len = max(len(str(cell.value or "")) for cell in col)
                ws.column_dimensions[col[0].column_letter].width = max_len + 4

        # Highlight Any Row in Link_Occupancy with >= 80% Load or LINK DOWN
        for row_idx in range(2, ws_occ.max_row + 1):
            flag_val = str(ws_occ.cell(row=row_idx, column=13).value)
            if "CRITICAL" in flag_val or "WARNING" in flag_val:
                for col_idx in range(1, ws_occ.max_column + 1):
                    cell = ws_occ.cell(row=row_idx, column=col_idx)
                    cell.fill = alert_fill
                    if col_idx in (11, 13):  # Peak Occupancy % and Flag columns
                        cell.font = alert_font


if __name__ == "__main__":
    df_occupancy = build_occupancy_dataframe()
    df_inventory = build_inventory_dataframe()

    print("\n================ 1. LINK OCCUPANCY REPORT ================")
    print(df_occupancy[[
        "HOSTNAME", "INTERFACE", "CAPACITY_MBPS",
        "PEAK_OCCUPANCY_%", "CRC_ERRORS", "ASSURANCE_FLAG"
    ]].to_string(index=False))

    print("\n================ 2. HARDWARE INVENTORY (CMDB) ================")
    print(df_inventory[[
        "HOSTNAME", "SLOT_LOCATION", "PART_NUMBER", "SERIAL_BARCODE", "DESCRIPTION"
    ]].to_string(index=False))

    out_file = "Assurance_Occupancy_Inventory_Report.xlsx"
    export_to_excel(df_occupancy, df_inventory, out_file)
    print(f"\n[SUCCESS] Exported formatted Excel report to: {Path(out_file).resolve()}")