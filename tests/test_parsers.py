import pytest
import pandas as pd
from pathlib import Path
from occupancy_inventory import (
    build_occupancy_dataframe,
    build_inventory_dataframe,
    export_to_excel,
)
from datacomm_bot import get_optical_summary


def test_build_occupancy_dataframe():
    df = build_occupancy_dataframe()

    assert isinstance(df, pd.DataFrame)
    assert not df.empty
    assert len(df) == 5  # 3 Huawei + 2 Cisco XR interfaces

    expected_cols = [
        "HOSTNAME", "VENDOR", "INTERFACE", "PHY_STATE", "DESCRIPTION",
        "CAPACITY_MBPS", "IN_Mbps", "OUT_Mbps", "IN_OCCUPANCY_%",
        "OUT_OCCUPANCY_%", "PEAK_OCCUPANCY_%", "CRC_ERRORS", "ASSURANCE_FLAG"
    ]
    assert list(df.columns) == expected_cols

    # Multi-vendor check
    vendors = df["VENDOR"].unique().tolist()
    assert "Huawei VRP" in vendors
    assert "Cisco IOS-XR" in vendors

    # Math & Threshold validation
    for _, row in df.iterrows():
        assert row["PEAK_OCCUPANCY_%"] == max(row["IN_OCCUPANCY_%"], row["OUT_OCCUPANCY_%"])
        if str(row["PHY_STATE"]).upper() != "UP":
            assert "CRITICAL: LINK DOWN" in row["ASSURANCE_FLAG"]
        elif row["PEAK_OCCUPANCY_%"] >= 80.0 and row["CRC_ERRORS"] > 0:
            assert "CRITICAL: HIGH LOAD (>=80%) + CRC ERRORS" in row["ASSURANCE_FLAG"]
        elif row["PEAK_OCCUPANCY_%"] >= 80.0:
            assert "WARNING: CAPACITY THRESHOLD (>=80%)" in row["ASSURANCE_FLAG"]


def test_build_inventory_dataframe():
    df = build_inventory_dataframe()

    assert isinstance(df, pd.DataFrame)
    assert not df.empty
    assert len(df) == 6  # 3 Huawei + 3 Cisco components

    expected_cols = [
        "HOSTNAME", "OS_VENDOR", "SLOT_LOCATION",
        "PART_NUMBER", "SERIAL_BARCODE", "DESCRIPTION", "VENDOR"
    ]
    assert list(df.columns) == expected_cols

    # Serial and part number presence
    part_numbers = df["PART_NUMBER"].tolist()
    assert "SFP-10G-LR" in part_numbers
    assert "CR5DLPUF512A" in part_numbers
    assert "A9K-RSP880-SE" in part_numbers


def test_get_optical_summary():
    optics = get_optical_summary()

    assert isinstance(optics, list)
    assert len(optics) == 3

    for item in optics:
        assert "interface" in item
        assert "rx" in item
        assert "tx" in item
        assert "state" in item

    # Verify diagnostic triage classification
    opt_by_intf = {item["interface"]: item for item in optics}
    assert "DEGRADED" in opt_by_intf["10GE1/0/1"]["state"]   # -23.10 dBm
    assert "LOS" in opt_by_intf["10GE1/0/2"]["state"]        # -38.45 dBm
    assert "HEALTHY" in opt_by_intf["100GE2/0/0"]["state"]   # -11.40 dBm


def test_export_to_excel(tmp_path):
    df_occ = build_occupancy_dataframe()
    df_inv = build_inventory_dataframe()
    test_excel = tmp_path / "test_report.xlsx"

    export_to_excel(df_occ, df_inv, str(test_excel))

    assert test_excel.exists()
    assert test_excel.stat().st_size > 0

    # Verify sheets with pandas
    excel_file = pd.ExcelFile(test_excel)
    assert "Link_Occupancy" in excel_file.sheet_names
    assert "Hardware_Inventory" in excel_file.sheet_names
