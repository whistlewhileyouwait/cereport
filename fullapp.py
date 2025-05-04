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


def generate_ce_report_with_intervals(sessions_for_day):
    raw_logs = get_scan_log()
    # 1) Build and sort timestamps per badge
    scans_by = {}
    for e in raw_logs:
        bid = int(e["badge_id"])
        ts  = e["timestamp"]
        if isinstance(ts, str) and ts.startswith("datetime.datetime"):
            inner = ts[len("datetime.datetime("):-1]
            ts = datetime.datetime.fromisoformat(inner)
        elif isinstance(ts, str):
            ts = datetime.datetime.fromisoformat(ts)
        scans_by.setdefault(bid, []).append(ts)
    for bid, times in scans_by.items():
        times.sort()
    # DEBUG: show the intervals you’ll build for badge “72” (or pick an ID you know)
    dbg_id = 72
    st.write("→ raw timestamps for", dbg_id, ":", scans_by.get(dbg_id))
    
    # 2) Build intervals
    intervals_by = {}
    for bid, times in scans_by.items():
        intervals = []
        for i in range(0, len(times), 2):
            start = times[i]
            end   = times[i+1] if i+1 < len(times) else datetime.datetime.combine(start.date(), datetime.time(23,59,59))
            intervals.append((start, end))
        intervals_by[bid] = intervals
    st.write("→ intervals for", dbg_id, ":", intervals_by.get(dbg_id))
    
    # 3) parse the sessions you passed in
    parsed = []
    for s in sessions_for_day:
        s_start = datetime.datetime.strptime(s["start"], "%Y-%m-%d %H:%M")
        s_end   = datetime.datetime.strptime(s["end"],   "%Y-%m-%d %H:%M")
        parsed.append((s["title"], s_start, s_end))
    st.write("→ sessions_for_day:", parsed)
    
    # 4) show overlap tests for that one badge
    for title, s_start, s_end in parsed:
        overlaps = any(iv_start < s_end and iv_end > s_start
                       for iv_start, iv_end in intervals_by.get(dbg_id, []))
        st.write(f"{title}: overlap? {overlaps}")
    
    # …then your normal build‑rows logic…

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

    # 1) Fetch attendees & raw scan log
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

    # ─── CE Credit report ───────────────────────────────────────────────────────
    st.subheader("📜 CE Credit Attendance Report")

    # Conference dates
    min_date = datetime.date(2025, 5, 2)
    max_date = datetime.date(2025, 5, 4)

    # Default to today if it’s in range, otherwise the first conference day
    today = datetime.date.today()
    default_date = today if min_date <= today <= max_date else min_date

    # Let the user pick a date within the conference window
    selected_date = st.date_input(
        "Select conference date",
        value=default_date,
        min_value=min_date,
        max_value=max_date,
    )

    # Filter sessions to that day
    sessions_for_day = [
        s for s in conference_sessions
        if datetime.datetime.strptime(s["start"], "%Y-%m-%d %H:%M").date()
        == selected_date
    ]

    if not sessions_for_day:
        st.info(f"No sessions scheduled for {selected_date}.")
    else:
        df_ce = generate_ce_report_with_intervals(sessions_for_day)
        st.dataframe(df_ce)
        st.download_button(
            "📥 Download CE Credit Report",
            data=df_ce.to_csv(index=False).encode("utf-8"),
            file_name=f"ce_report_{selected_date}.csv",
            mime="text/csv"
        )
        # … after your CE‐report block …
        if st.button("💾 Save CE Report to Supabase"):
            from database import save_ce_report
            save_ce_report(df_ce, selected_date)
            st.success(f"CE report for {selected_date} saved ({len(df_ce)} attendees).")

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
