# Core & Datacomm Network Assurance Suite

An automated network assurance and Business-As-Usual (BAU) operational toolkit designed for Telco and ISP IP Core/Metro networks. This suite unifies multi-vendor telemetry parsing, automated optical diagnostics, CMDB asset extraction, interactive Streamlit analytics, and Telegram ChatOps.

---

## Key Features

- **Multi-Vendor Link Occupancy Triage**:
  - Ingests raw operational outputs from Huawei VRP (`display interface`) and Cisco IOS-XR (`show interfaces`).
  - Utilizes TextFSM finite state machines to extract 5-minute traffic rates, line states, and CRC error counters.
  - Automatically flags threshold exceptions ($\ge 80\%$ link capacity or physical interface down).

- **Optical Power & Diagnostic Classification**:
  - Parses transceiver optical levels (Rx/Tx power in dBm) across 10GE and 100GE links.
  - Categorizes link health: Healthy, High Attenuation / Degraded ($<-22\text{ dBm}$), and Fiber Cut / Loss of Signal ($<-30\text{ dBm}$).

- **CMDB Inventory Extraction**:
  - Normalizes hardware component metadata from Huawei electronic labels (`display elabel`) and Cisco inventory tables (`show inventory`).
  - Extracts chassis, line card, and pluggable optic serial barcodes and part numbers.

- **Automated Excel Reporting**:
  - Generates executive `.xlsx` reports with dedicated sheets for Link Occupancy and Hardware Inventory.
  - Highlights capacity anomalies with conditional styling.

- **Interactive Streamlit Dashboard (`dashboard.py`)**:
  - Dynamic filtering by router hostname and utilization threshold.
  - Built-in SNMP 64-bit counter delta simulator (`ifHCOutOctets`).
  - REST API poller for live MikroTik RouterOS / CHR instances.

- **Telegram ChatOps Bot (`datacomm_bot.py`)**:
  - Real-time diagnostic queries via mobile interface.
  - Commands: `/start`, `/cek_status`, `/cek_live` (Netmiko SSH poller), and `/report` (on-demand `.xlsx` generation).

---

## Architecture Overview

```
+----------------------------------+        +-----------------------------------+
|  Multi-Vendor Raw CLI Telemetry  |        |      Live Network Lab (CHR)       |
|  - Huawei VRP (display int/elabel)|        |  - MikroTik RouterOS (SSH / REST) |
|  - Cisco IOS-XR (show int/inv)   |        |  - Netmiko SSH Worker             |
+-----------------+----------------+        +-----------------+-----------------+
                  |                                           |
                  v                                           v
       +--------------------+                       +-------------------+
       |  TextFSM Parsers   |                       | Telegram ChatOps  |
       |  & Normalization   |                       | & Streamlit UI    |
       +----------+---------+                       +---------+---------+
                  |                                           |
                  +---------------------+---------------------+
                                        |
                                        v
                       +---------------------------------+
                       |  Assurance Engine & DataFrames  |
                       |  - Occupancy & CRC Correlation  |
                       |  - Optical Power Diagnostics    |
                       |  - CMDB Inventory Tracking      |
                       +----------------+----------------+
                                        |
                                        v
                       +---------------------------------+
                       | Automated Excel / Visual Alerts |
                       +---------------------------------+
```

---

## Installation & Setup

### 1. Prerequisites
- Python 3.10 or higher
- Git

### 2. Clone Repository & Setup Virtual Environment
```bash
git clone <repository_url>
cd datacomm-assurance-sprint

python -m venv .venv
# On Windows:
.venv\Scripts\activate
# On Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
```

### 3. Environment Configuration
Copy `.env.example` to `.env` and configure your credentials:
```bash
cp .env.example .env
```

Set the following parameters in `.env`:
- `TELEGRAM_BOT_TOKEN`: Your bot token issued by `@BotFather`.
- `MIKROTIK_HOST`: IP address of the target MikroTik router/CHR VM.
- `MIKROTIK_PORT`: SSH port (default: 22).
- `MIKROTIK_USERNAME`: Router username.
- `MIKROTIK_PASSWORD`: Router password.

---

## Usage

### Run Parser & Excel Generator
```bash
python occupancy_inventory.py
```

### Launch Interactive Streamlit Dashboard
```bash
streamlit run dashboard.py
```

### Start Telegram ChatOps Bot
```bash
python datacomm_bot.py
```

### Run Automated Tests
```bash
pip install -r requirements-dev.txt
pytest
```

---

## Directory Structure

```
├── .github/
│   └── workflows/
│       └── ci.yml              # Automated test pipeline
├── tests/
│   └── test_parsers.py         # Unit tests for TextFSM parsers
├── .env.example                # Sample environment configuration
├── .gitignore                  # Git exclusions for secrets and artifacts
├── dashboard.py                # Streamlit monitoring dashboard
├── datacomm_bot.py             # Telegram ChatOps bot
├── occupancy_inventory.py      # Core data parser and Excel exporter
├── pytest.ini                  # Pytest configuration
├── requirements.txt            # Production dependencies
├── requirements-dev.txt        # Development and testing dependencies
└── README.md                   # Project documentation
```
