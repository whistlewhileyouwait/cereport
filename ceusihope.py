import streamlit as st
from docx import Document
from docx.shared import Pt
import os
import pandas as pd
from dotenv import load_dotenv
from supabase import create_client
from datetime import datetime

# ─── Load Supabase ─────────────────────────────────────
load_dotenv()
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
# ─── Session List ─────────────────────────────────────────────
sessions = [
    {"date": "May 2, 2025\n8:30", "title": "Prevention of Child Molestation", "speaker": "Matthew L. Ferrara, Ph.D.", "credits": 1.5},
    {"date": "May 2, 2025\n10:30", "title": "Overview of the Texas Department of Criminal Justice", "speaker": "Jennifer Deyne, LPC-S, LSOTP-S", "credits": 1.5},
    {"date": "May 2, 2025\n1:30 and 3:30", "title": "Taking the High Road-Ethical Challenges", "speaker": "Dan Powers, LCSW-S", "credits": 3.0},
    {"date": "May 3, 2025\n8:30", "title": "Role of LSOTPs & Polygraph Examiners", "speaker": "Sean Braun, LSOTP; Clay Wood", "credits": 1.5},
    {"date": "May 3, 2025\n10:30", "title": "Working with Female Juveniles", "speaker": "Francisco Torres, LSOTP", "credits": 1.5},
    {"date": "May 3, 2025\n1:30", "title": "Treating Clients with Mild Autism", "speaker": "Emily Dixon, Ph.D.", "credits": 1.5},
    {"date": "May 3, 2025\n3:30", "title": "Sexual Addiction Treatment", "speaker": "Matthew L. Ferrara, Ph.D.", "credits": 1.5},
    {"date": "May 4, 2025\n8:30", "title": "Risk Assessment Reports", "speaker": "Matthew L. Ferrara, Ph.D.", "credits": 1.5},
    {"date": "May 4, 2025\n10:30", "title": "Chaperon Program for Your Practice", "speaker": "Shelley Graham, Ph.D., LSOTP; Anna Shursen, Ph.D., LSOTP", "credits": 1.5},
    {"date": "May 4, 2025\n1:30", "title": "Legal Aspects of Deregistration", "speaker": "Scott Smith, Esq", "credits": 1.5},
    {"date": "May 4, 2025\n3:30", "title": "Adolescent Risk-Need-Responsivity", "speaker": "Casey O'Neal, Ph.D.", "credits": 1.5},
]

# ─── Streamlit UI ─────────────────────────────────────────────
st.title("🎓 CEU Certificate Generator")

name = st.text_input("Enter participant's name:")
st.subheader("✅ Select Sessions Attended")

selected_sessions = []
for session in sessions:
    label = f"{session['date']} – {session['title']} ({session['credits']} hrs)"
    if st.checkbox(label):
        selected_sessions.append(session)

# ─── Generate Certificate Function ────────────────────────────
def generate_certificate(name, sessions_attended):
    template_path = "Certficate of Training Blank (1).docx"
    doc = Document(template_path)

    total_credits = sum(s["credits"] for s in sessions_attended)

    # Update name and CEU count
    for para in doc.paragraphs:
        if "Jane Doe" in para.text:
            para.text = para.text.replace("Jane Doe", name)
            para.runs[0].font.size = Pt(14)
        if "18 In-Person Hours" in para.text:
            para.text = f"{total_credits:.1f} In-Person Hours of Continuing Education Units"
            para.runs[0].font.size = Pt(12)

    # Replace table rows with only attended sessions
    table = doc.tables[0]
    # Clear existing rows except header
    for i in range(len(table.rows) - 1, 0, -1):
        table._tbl.remove(table._tbl.tr_lst[i])

    # Add rows for selected sessions
    for s in sessions_attended:
        row = table.add_row()
        row.cells[0].text = s["date"]
        row.cells[1].text = s["title"]
        row.cells[2].text = s["speaker"]
        row.cells[3].text = f"{s['credits']} hrs."

    filename = f"{name.replace(' ', '_')}_CERT.docx"
    doc.save(filename)
    return filename

# ─── Download Button ──────────────────────────────────────────
if name and selected_sessions:
    if st.button("Generate Certificate"):
        file = generate_certificate(name, selected_sessions)
        with open(file, "rb") as f:
            st.download_button("📥 Download Certificate", f, file_name=file)




# ─── Pull Scan Data ────────────────────────────────────
response = supabase.table("scan_log").select("*").execute()
scan_data = response.data

if not scan_data:
    print("No data found in scan_log.")
    exit()

# ─── Prepare DataFrame ─────────────────────────────────
df = pd.DataFrame(scan_data)
df["timestamp"] = pd.to_datetime(df["timestamp"])
df["date"] = df["timestamp"].dt.date

# ─── Email Generator Function ──────────────────────────
def summarize_attendance(scans_df, person_name):
    person_scans = scans_df[scans_df["name"] == person_name]

    email_lines = [f"Hi {person_name.split()[0]},\n",
                   "Thank you so much for attending the conference! According to our scan records, it looks like you were present during the following times:\n"]

    for day in ["2025-05-02", "2025-05-03", "2025-05-04"]:
        day_dt = datetime.strptime(day, "%Y-%m-%d").date()
        day_scans = person_scans[person_scans["date"] == day_dt]

        if not day_scans.empty:
            in_time = day_scans["timestamp"].min().strftime("%I:%M %p")
            out_time = day_scans["timestamp"].max().strftime("%I:%M %p")
            email_lines.append(f"• {day_dt.strftime('%B %d, %Y')}: {in_time} to {out_time}")
        else:
            email_lines.append(f"• {day_dt.strftime('%B %d, %Y')}: No record")

    email_lines.append("\nIf any of these details need to be updated, just reply to this email and I’ll be happy to take care of it.\n")
    email_lines.append("Thanks again for being part of the event!\n\nBest,\n[Your Name]\n[Your Organization]")

    return "\n".join(email_lines)

# ─── Loop Over Attendees and Export Messages ───────────
attendees = df["name"].dropna().unique()
output = []

for person in attendees:
    message = summarize_attendance(df, person)
    email = df[df["name"] == person]["email"].dropna().iloc[0] if "email" in df.columns else "no-email@example.com"
    output.append({"name": person, "email": email, "message": message})

# ─── Save to CSV (for mail merge or review) ─────────────
out_df = pd.DataFrame(output)
out_df.to_csv("attendance_emails.csv", index=False)

print("✅ Done! Emails saved to attendance_emails.csv")
