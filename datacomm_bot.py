import asyncio
import io
import os
import textfsm
from pathlib import Path
from dotenv import load_dotenv
from netmiko import ConnectHandler
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Load environment variables from .env file
load_dotenv()

# Import Day 4 occupancy & inventory functions
from occupancy_inventory import (
    build_occupancy_dataframe,
    build_inventory_dataframe,
    export_to_excel,
)

# CONFIGURATION (Loaded from environment variables or .env)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

MIKROTIK_CHR = {
    "device_type": "mikrotik_routeros",
    "host": os.getenv("MIKROTIK_HOST", "192.168.56.101"),
    "username": os.getenv("MIKROTIK_USERNAME", os.getenv("MIKROTIK_USER", "admin")),
    "password": os.getenv("MIKROTIK_PASSWORD", os.getenv("MIKROTIK_PASS", "")),
    "port": int(os.getenv("MIKROTIK_PORT", "22")),
    "conn_timeout": int(os.getenv("MIKROTIK_CONN_TIMEOUT", "8")),
}

# OPTICAL POWER CLI DATA & TEXTFSM PARSER (Huawei VRP + Cisco IOS-XR)
HUAWEI_OPTICS_RAW = """
10GE1/0/1 transceiver diagnostic information:
  Current Rx Power(dBM)                 : -23.10
  Default Rx Power Low Threshold(dBM)   : -20.00
  Current Tx Power(dBM)                 : -1.15
10GE1/0/2 transceiver diagnostic information:
  Current Rx Power(dBM)                 : -38.45
  Default Rx Power Low Threshold(dBM)   : -20.00
  Current Tx Power(dBM)                 : -0.92
100GE2/0/0 transceiver diagnostic information:
  Current Rx Power(dBM)                 : -11.40
  Default Rx Power Low Threshold(dBM)   : -18.00
  Current Tx Power(dBM)                 : 0.45
"""

HUAWEI_OPTICS_TEMPLATE = """Value Required INTERFACE (\\S+)
Value RX_DBM ([-\\d.]+)
Value LOW_THRESH ([-\\d.]+)
Value TX_DBM ([-\\d.]+)

Start
  ^${INTERFACE}\\s+transceiver diagnostic information:
  ^\\s+Current Rx Power\\(dBM\\)\\s*:\\s*${RX_DBM}
  ^\\s+Default Rx Power Low Threshold\\(dBM\\)\\s*:\\s*${LOW_THRESH}
  ^\\s+Current Tx Power\\(dBM\\)\\s*:\\s*${TX_DBM} -> Record
"""


def get_optical_summary() -> list[dict]:
    fsm = textfsm.TextFSM(io.StringIO(HUAWEI_OPTICS_TEMPLATE))
    rows = fsm.ParseText(HUAWEI_OPTICS_RAW)
    results = []
    for intf, rx, low, tx in rows:
        rx_val = float(rx)
        if rx_val <= -30.0:
            state = "🔴 LOS (Fiber Cut / Dark)"
        elif rx_val <= -22.0:
            state = "🟠 DEGRADED (High Attenuation)"
        else:
            state = "🟢 HEALTHY"
        results.append({
            "interface": intf,
            "rx": rx_val,
            "tx": float(tx),
            "state": state,
        })
    return results


# LIVE NETMIKO SSH WORKER (Connects to Your Local VirtualBox MikroTik CHR)
def poll_mikrotik_chr_sync() -> dict:
    """Blocking SSH call executed inside a background thread via asyncio.to_thread."""
    with ConnectHandler(**MIKROTIK_CHR) as ssh:
        identity = ssh.send_command("/system identity print").strip()
        traffic = ssh.send_command("/interface monitor-traffic ether2 once").strip()
        ospf = ssh.send_command("/routing ospf neighbor print").strip()
        lldp = ssh.send_command("/ip neighbor print detail").strip()
        return {
            "ok": True,
            "identity": identity,
            "traffic": traffic,
            "ospf": ospf,
            "lldp": lldp,
        }


# TELEGRAM BOT COMMAND HANDLERS
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "🛠 *Core & Datacomm Assurance BAU Bot*\n\n"
        "Available NOC Diagnostics Commands:\n"
        "• `/cek_status` — Parse Optical Rx/Tx Power (dBm) & 5-Min Link Occupancy %\n"
        "• `/cek_live` — Live SSH via Netmiko into local `PE-JAKTIM-01` (MikroTik CHR)\n"
        "• `/report` — Generate & download `.xlsx` Occupancy + CMDB Inventory Report"
    )
    await update.message.reply_text(welcome_text, parse_mode=ParseMode.MARKDOWN)


async def cek_status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Deliverable: Replies with Optical Rx/Tx Power & 5-Min Link Occupancy %."""
    optics_list = get_optical_summary()
    df_occ = build_occupancy_dataframe()

    lines = ["📡 *CORE & DATACOMM TRIAGE SUMMARY*\n"]

    # Section 1: Optical Power (Rx/Tx dBm)
    lines.append("*1. Optical Transceiver Diagnostics (`PE-JAKTIM-01`):*")
    for opt in optics_list:
        lines.append(
            f"• `{opt['interface']}` | Rx: `{opt['rx']} dBm` | Tx: `{opt['tx']} dBm` → {opt['state']}"
        )

    # Section 2: Link Occupancy & CRC Status
    lines.append("\n*2. Link Occupancy & Capacity Triage (5-Min Rate):*")
    for _, row in df_occ.iterrows():
        icon = "🟢"
        if "CRITICAL" in row["ASSURANCE_FLAG"]:
            icon = "🔴"
        elif "WARNING" in row["ASSURANCE_FLAG"]:
            icon = "🟠"

        lines.append(
            f"{icon} *{row['HOSTNAME']}* `{row['INTERFACE']}`\n"
            f"   Peak Load: *{row['PEAK_OCCUPANCY_%']}%* "
            f"(In: `{row['IN_Mbps']}M` / Out: `{row['OUT_Mbps']}M` of `{int(row['CAPACITY_MBPS'])}M`)\n"
            f"   CRC: `{row['CRC_ERRORS']}` | Status: `{row['ASSURANCE_FLAG']}`"
        )

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


async def cek_live_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Deliverable: Live SSH into VirtualBox MikroTik CHR via Netmiko."""
    status_msg = await update.message.reply_text(
        f"⏳ Connecting via SSH (Netmiko) to `{MIKROTIK_CHR['host']}`...",
        parse_mode=ParseMode.MARKDOWN,
    )
    try:
        data = await asyncio.to_thread(poll_mikrotik_chr_sync)
        reply = (
            f"✅ *LIVE SSH TELEMETRY ({MIKROTIK_CHR['host']})*\n\n"
            f"*Identity:*\n```\n{data['identity']}\n```\n"
            f"*Core Link Traffic (`ether2`):*\n```\n{data['traffic']}\n```\n"
            f"*OSPF Neighbor State:*\n```\n{data['ospf'] or 'No active OSPF neighbors'}\n```\n"
            f"*LLDP Topology Neighbor:*\n```\n{data['lldp'] or 'No LLDP neighbors detected'}\n```"
        )
        await status_msg.edit_text(reply, parse_mode=ParseMode.MARKDOWN)
    except Exception as exc:
        await status_msg.edit_text(
            f"⚠️ *SSH Connection Failed to `{MIKROTIK_CHR['host']}`*\n"
            f"Error: `{exc}`\n\n"
            f"_Tip: Ensure your VirtualBox CHR-R1 VM is running and reachable from Windows._",
            parse_mode=ParseMode.MARKDOWN,
        )


async def report_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generates the Excel report from Day 4 and sends it directly to Telegram."""
    df_occ = build_occupancy_dataframe()
    df_inv = build_inventory_dataframe()
    excel_path = Path("Assurance_Occupancy_Inventory_Report.xlsx")

    await asyncio.to_thread(export_to_excel, df_occ, df_inv, str(excel_path))

    with open(excel_path, "rb") as doc:
        await update.message.reply_document(
            document=doc,
            filename=excel_path.name,
            caption="📊 Automated Link Occupancy (>80% Flagged) & CMDB Inventory Report",
        )


# MAIN ENTRY POINT
if __name__ == "__main__":
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "PASTE_YOUR_BOTFATHER_TOKEN_HERE":
        print("[!] Error: TELEGRAM_BOT_TOKEN is not configured.")
        print("    Please copy .env.example to .env and set your @BotFather token:")
        print("    TELEGRAM_BOT_TOKEN=your_token_here")
    else:
        print("Starting Core & Datacomm Assurance Bot... Press Ctrl+C to stop.")
        app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

        app.add_handler(CommandHandler("start", start_cmd))
        app.add_handler(CommandHandler("cek_status", cek_status_cmd))
        app.add_handler(CommandHandler("cek_live", cek_live_cmd))
        app.add_handler(CommandHandler("report", report_cmd))

        app.run_polling()