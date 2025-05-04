import datetime
import pandas as pd
import streamlit as st
import qrcode
import numpy as np
import cv2
import os
from io import BytesIO
from PIL import Image
from dotenv import load_dotenv
from supabase import create_client, Client
from database import get_all_attendees, log_scan
from database import get_scan_log

# ─── Load .env & initialize Supabase client ───────────────────────────────
load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

from database import (
    register_attendee,
    get_all_attendees,
    log_scan,
    get_scan_log,
)

# ─── Page‑swap helper (only once) ─────────────────────────────────────────
def switch_page(page_name: str):
    st.session_state.page = page_name


# ─── Init page state ────────────────────────────────────────────────────────
if 'page' not in st.session_state:
    st.session_state.page = 'home'
# Initialize Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Conference session definitions with titles and exact times
conference_sessions = [
    {"title": "Prevention of C.M.", "start": "2025-05-02 08:30", "end": "2025-05-02 10:00"},
    {"title": "The TDCJ SO Treatment Program", "start": "2025-05-02 10:30", "end": "2025-05-02 12:00"},
    {"title": "Taking the High Road - Ethical Challenges (Part 1)", "start": "2025-05-02 13:30", "end": "2025-05-02 15:00"},
    {"title": "Taking the High Road - Ethical Challenges (Part 2)", "start": "2025-05-02 15:30", "end": "2025-05-02 17:00"},
    {"title": "Use of Polygraph Exams in Treatment", "start": "2025-05-03 08:30", "end": "2025-05-03 10:00"},
    {"title": "Challenges, Lessons Learned...", "start": "2025-05-03 10:30", "end": "2025-05-03 12:00"},
    {"title": "Treating Clients with Mild Autism", "start": "2025-05-03 13:30", "end": "2025-05-03 15:00"},
    {"title": "Unpacking the Offense Cycle", "start": "2025-05-03 15:30", "end": "2025-05-03 17:00"},
    {"title": "Risk Assessment Reports", "start": "2025-05-04 08:30", "end": "2025-05-04 10:00"},
    {"title": "Chaperon Training", "start": "2025-05-04 10:30", "end": "2025-05-04 12:00"},
    {"title": "Legal and Strategy Aspects of Deregistration", "start": "2025-05-04 13:30", "end": "2025-05-04 15:00"},
    {"title": "RNR Approach to Adolescent Assessment", "start": "2025-05-04 15:30", "end": "2025-05-04 17:00"},
]


# ─── Utility functions ─────────────────────────────────────────────────────
def generate_qr_code(badge_id: int) -> bytes:
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=5, border=2)
    qr.add_data(str(badge_id))
    qr.make(fit=True)
    img = qr.make_image(fill='black', back_color='white')
    buf = BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


def run_qr_scanner():
    st.subheader("📷 Scan QR Code")
    img_file = st.camera_input("Point camera at QR code")
    if not img_file:
        return

    img = Image.open(img_file).convert("RGB")
    gray = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY)
    data, _, _ = cv2.QRCodeDetector().detectAndDecode(gray)
    if not data:
        st.warning("⚠ QR Code not recognized.")
        return

    badge_id = data.strip()
    log_scan(badge_id)

    people = get_all_attendees()
    person = next((p for p in people if p["badge_id"] == int(badge_id)), None)
    name = person["name"] if person else badge_id
    st.success(f"✅ Scanned and checked in: {name}")
st.subheader("📅 Daily Punch Report")




def generate_punch_report():
    attendees = get_all_attendees()    # list of { badge_id, name, email, … }
    raw_logs  = get_scan_log()         # list of { badge_id, timestamp }

    # 2) normalize timestamps to datetime
    norm = []
    for e in raw_logs:
        bid = int(e["badge_id"])
        ts  = e["timestamp"]
        if isinstance(ts, str):
            # strip the “datetime.datetime(...)” wrapper if present
            if ts.startswith("datetime.datetime"):
                inner = ts[len("datetime.datetime("):-1]
                ts = datetime.datetime.fromisoformat(inner)
            else:
                ts = datetime.datetime.fromisoformat(ts)
        norm.append({"badge_id": bid, "timestamp": ts})

    # 3) group by badge_id and date → list of timestamps
    from collections import defaultdict
    scans_by_date = defaultdict(list)
    for e in norm:
        d = e["timestamp"].date()
        scans_by_date[(e["badge_id"], d)].append(e["timestamp"])

    # 4) build rows: for each (badge, date) compute min & max
    rows = []
    # build a lookup for name/email
    info = { int(a["badge_id"]): (a["name"], a["email"]) for a in attendees }
    for (bid, d), times in sorted(scans_by_date.items()):
        times.sort()
        check_in  = times[0].strftime("%H:%M:%S")
        check_out = times[-1].strftime("%H:%M:%S")
        name, email = info.get(bid, ("<unknown>", ""))
        rows.append({
            "Badge ID": bid,
            "Name":      name,
            "Email":     email,
            "Date":      d.isoformat(),
            "Check‑In":  check_in,
            "Check‑Out": check_out
        })

    return pd.DataFrame(rows).sort_values(["Date","Badge ID"]).reset_index(drop=True)
def generate_flattened_log():
    # 1) Fetch registered attendees
    attendees = get_all_attendees()   # list of dicts: { badge_id, name, email, … }
    attendee_map = { int(a["badge_id"]): a for a in attendees }

    raw_scans = get_scan_log()        # list of { badge_id, name, email, timestamp }

    # 3) Group scans by badge_id (earliest → latest)
    scans_by = {}
    for entry in sorted(raw_scans, key=lambda x: x["timestamp"]):
        bid = int(entry["badge_id"])
        scans_by.setdefault(bid, []).append(entry["timestamp"])

    # 4) Build a row for every scanned badge
    rows = []
    for bid, times in scans_by.items():
        # look up registration info if it exists
        info = attendee_map.get(bid, {})
        row = {
            "Badge ID": bid,
            "Name":      info.get("name", f"<unregistered {bid}>"),
            "Email":     info.get("email", ""),
        }
        # fill Scan 1…Scan 10
        for i in range(1, 11):
            if i <= len(times):
                row[f"Scan {i}"] = times[i-1].strftime("%Y-%m-%d %H:%M:%S")
            else:
                row[f"Scan {i}"] = ""
        rows.append(row)

    # 5) Sort numerically by badge and return
    rows = sorted(rows, key=lambda r: r["Badge ID"])
    return pd.DataFrame(rows)
# ─── Page layouts ────────────────────────────────────────────────────────────
if st.session_state.page == 'home':
    st.title("📋 Conference Check‑In System")

    # QR scanner
    run_qr_scanner()

# Manual badge ID
    st.subheader("🔢 Manual Check-In by Badge ID")
    badge_input = st.text_input("Enter Badge ID", key="manual_badge")

    if st.button("Check In", key="checkin_manual"):
        if badge_input:
        # 1) Record the scan
            log_scan(badge_input)

        # 2) Fetch name (none → resp.data is None)
            resp = (
                supabase
                .table("attendees")
                .select("name")
                .eq("badge_id", int(badge_input))
                .maybe_single()
                .execute()
            )
            if resp is not None and resp.data:
                name = resp.data.get("name", badge_input)
            else:
                name = badge_input

        # 4) Show the confirmation
            st.success(f"✅ Checked in: {name}")
        else:
            st.warning("Please enter a valid badge ID.")

    st.subheader("👤 Manual Check-In by Name")
    people = get_all_attendees()
    names = [f"{p['name']} ({p['badge_id']})" for p in people]
    selection = st.selectbox("Select Attendee", names, index=0)

    if st.button("Check In Selected", key="checkin_select"):
        bid = int(selection.split("(")[-1].rstrip(")"))
        log_scan(bid)
        # lookup the person’s name for that badge
        name = next(p["name"] for p in people if p["badge_id"] == bid)
        st.success(f"✅ Checked in: {name} ({bid})")

    # Go to Admin
    if st.button("🔐 Admin Area"):
        switch_page('admin')

elif st.session_state.page == 'admin':
    st.title("🔐 Admin – Attendance Dashboard")

    # ← Back to Home
    if st.button("⬅ Back to Home"):
        switch_page('home')

    st.subheader("👥 All Registered Attendees")
    attendees = get_all_attendees()   # list of dicts with int badge_id
    logs      = get_scan_log()        # list of dicts with badge_id (str), timestamp (datetime or repr)

    # 2) Build badge_id → sorted list of timestamp strings
    scans_map: dict[int, list[str]] = {}
    for entry in logs:
        # normalize badge_id to int
        try:
            bid = int(entry["badge_id"])
        except Exception:
            bid = entry["badge_id"]

        # normalize timestamp to datetime
        ts = entry["timestamp"]
        if isinstance(ts, str) and ts.startswith("datetime.datetime"):
            # strip off the wrapper: datetime.datetime(…)
            inner = ts.replace("datetime.datetime(", "").rstrip(")")
            ts = datetime.datetime.fromisoformat(inner)
        elif isinstance(ts, str):
            ts = datetime.datetime.fromisoformat(ts)

        # format and collect
        s = ts.strftime("%Y-%m-%d %H:%M:%S")
        scans_map.setdefault(bid, []).append(s)

    # sort each attendee’s scans chronologically
    for bid in scans_map:
        scans_map[bid].sort()

    # 3) Assemble rows for the DataFrame
    rows = []
    for person in attendees:
        bid   = person["badge_id"]
        times = scans_map.get(bid, [])
        rows.append({
            "Badge ID":  bid,
            "Name":       person["name"],
            "Email":      person["email"],
            "All Scans":  ", ".join(times)
        })

    # 4) Render table & download button
    df_all = pd.DataFrame(rows)
    st.dataframe(df_all)
    st.download_button(
        "📥 Download Attendees with Scans",
        data=df_all.to_csv(index=False).encode("utf-8"),
        file_name="attendees_with_scans.csv",
        mime="text/csv"
    )

    st.markdown("---")

    st.subheader("📊 Raw Attendance Log")
    raw = get_scan_log()
    df_raw = pd.DataFrame(raw)
    st.dataframe(df_raw)
    st.download_button(
    "📥 Download Raw Attendance Log",
    df_raw.to_csv(index=False).encode("utf-8"),
    file_name="raw_attendance.csv"
)
    st.markdown("---")
    
    st.subheader("📅 Daily Punch Report")
    df_punch = generate_punch_report()

    # highlight any row where Check‑In == Check‑Out
    def highlight_missed(row):
        return ["background-color: #ffcccc" if row["Check‑In"] == row["Check‑Out"] else "" 
                for _ in row]

    styled = df_punch.style.apply(highlight_missed, axis=1)
    st.dataframe(styled)

    st.download_button(
        "📥 Download Punch Report",
        data=df_punch.to_csv(index=False).encode("utf-8"),
        file_name="punch_report.csv",
        mime="text/csv"
    )


    # — your usual init —
load_dotenv()
supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

def get_next_badge_id():
    # pull the single highest badge_id, descending, limit=1
    resp = (
      supabase
        .table("attendees")
        .select("badge_id")
        .order("badge_id", desc=True)
        .limit(1)
        .execute()
    )
    data = resp.data or []
    if data:
        return data[0]["badge_id"] + 1
    return 1

# — in your Streamlit layout, e.g. sidebar —
st.sidebar.header("➕ Quick Register")

next_id = get_next_badge_id()
with st.sidebar.form("quick_register"):
    name     = st.text_input("Full Name")
    email    = st.text_input("Email")
    # pre-fill and lock the badge field
    badge_id = st.number_input(
        "Badge ID",
        min_value=1,
        value=next_id,
        disabled=True
    )
    submitted = st.form_submit_button("Register")

if submitted:
    try:
        supabase.table("attendees").insert({
            "badge_id": int(badge_id),
            "name":     name,
            "email":    email
        }).execute()
        st.sidebar.success(f"Registered {name} (# {badge_id})")
    except Exception as e:
        st.sidebar.error(f"Failed to register: {e}")


    if st.button("⬅ Back to Admin"):
        switch_page('admin')
