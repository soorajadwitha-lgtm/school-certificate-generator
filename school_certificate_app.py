import sqlite3
import os
import bcrypt
from datetime import datetime

DB_PATH = "certificate_system.db"

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            full_name TEXT,
            email TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            background_path TEXT,
            logo_path TEXT,
            signature_principal_path TEXT,
            signature_coordinator_path TEXT,
            school_name TEXT,
            school_name_x REAL DEFAULT 0.5,
            school_name_y REAL DEFAULT 0.1,
            school_name_font TEXT DEFAULT 'Helvetica-Bold',
            school_name_size INTEGER DEFAULT 36,
            school_name_color TEXT DEFAULT '#000000',
            school_name_bold INTEGER DEFAULT 1,
            school_name_italic INTEGER DEFAULT 0,
            school_name_align TEXT DEFAULT 'center',
            logo_x REAL DEFAULT 0.5,
            logo_y REAL DEFAULT 0.15,
            logo_width INTEGER DEFAULT 100,
            logo_height INTEGER DEFAULT 100,
            logo_transparency REAL DEFAULT 1.0,
            watermark_text TEXT DEFAULT '',
            watermark_transparency REAL DEFAULT 0.1,
            name_x REAL DEFAULT 0.5,
            name_y REAL DEFAULT 0.42,
            name_font TEXT DEFAULT 'Helvetica-Bold',
            name_size INTEGER DEFAULT 48,
            name_color TEXT DEFAULT '#1a1a2e',
            course_x REAL DEFAULT 0.5,
            course_y REAL DEFAULT 0.55,
            course_font TEXT DEFAULT 'Helvetica',
            course_size INTEGER DEFAULT 24,
            course_color TEXT DEFAULT '#333333',
            date_x REAL DEFAULT 0.25,
            date_y REAL DEFAULT 0.75,
            grade_x REAL DEFAULT 0.5,
            grade_y REAL DEFAULT 0.62,
            rank_x REAL DEFAULT 0.75,
            rank_y REAL DEFAULT 0.75,
            sig_principal_x REAL DEFAULT 0.2,
            sig_principal_y REAL DEFAULT 0.82,
            sig_coordinator_x REAL DEFAULT 0.8,
            sig_coordinator_y REAL DEFAULT 0.82,
            sig_width INTEGER DEFAULT 120,
            sig_height INTEGER DEFAULT 60,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS certificates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            certificate_id TEXT UNIQUE NOT NULL,
            student_name TEXT NOT NULL,
            course TEXT,
            event TEXT,
            issue_date TEXT,
            grade TEXT,
            rank TEXT,
            template_id INTEGER,
            template_name TEXT,
            pdf_path TEXT,
            png_path TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (template_id) REFERENCES templates(id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE NOT NULL,
            value TEXT
        )
    """)

    conn.commit()

    # Seed default admin
    c.execute("SELECT COUNT(*) FROM admins")
    if c.fetchone()[0] == 0:
        pw = bcrypt.hashpw("admin123".encode(), bcrypt.gensalt()).decode()
        c.execute("INSERT INTO admins (username, password_hash, full_name, email) VALUES (?,?,?,?)",
                  ("admin", pw, "System Administrator", "admin@school.edu"))
        conn.commit()

    # Seed default settings
    defaults = {
        "school_name": "Excellence Academy",
        "school_address": "123 Education Street, Knowledge City",
        "contact_info": "info@school.edu | +1-234-567-8900",
        "logo_path": "",
        "sig_principal_path": "",
        "sig_coordinator_path": "",
    }
    for k, v in defaults.items():
        c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?,?)", (k, v))
    conn.commit()
    conn.close()


def get_setting(key):
    conn = get_connection()
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else ""

def set_setting(key, value):
    conn = get_connection()
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)", (key, value))
    conn.commit()
    conn.close()

def get_all_settings():
    conn = get_connection()
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    conn.close()
    return {r["key"]: r["value"] for r in rows}

def save_template(data: dict):
    conn = get_connection()
    cols = ", ".join(data.keys())
    placeholders = ", ".join(["?" for _ in data])
    conn.execute(f"INSERT INTO templates ({cols}) VALUES ({placeholders})", list(data.values()))
    conn.commit()
    conn.close()

def update_template(template_id, data: dict):
    data["updated_at"] = datetime.now().isoformat()
    sets = ", ".join([f"{k}=?" for k in data])
    conn = get_connection()
    conn.execute(f"UPDATE templates SET {sets} WHERE id=?", list(data.values()) + [template_id])
    conn.commit()
    conn.close()

def get_templates():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM templates ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_template(template_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM templates WHERE id=?", (template_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def delete_template(template_id):
    conn = get_connection()
    conn.execute("DELETE FROM templates WHERE id=?", (template_id,))
    conn.commit()
    conn.close()

def save_certificate(data: dict):
    conn = get_connection()
    cols = ", ".join(data.keys())
    placeholders = ", ".join(["?" for _ in data])
    conn.execute(f"INSERT INTO certificates ({cols}) VALUES ({placeholders})", list(data.values()))
    conn.commit()
    conn.close()

def get_certificates(search_name=None, search_id=None, search_date=None):
    conn = get_connection()
    query = "SELECT * FROM certificates WHERE 1=1"
    params = []
    if search_name:
        query += " AND student_name LIKE ?"
        params.append(f"%{search_name}%")
    if search_id:
        query += " AND certificate_id LIKE ?"
        params.append(f"%{search_id}%")
    if search_date:
        query += " AND issue_date = ?"
        params.append(search_date)
    query += " ORDER BY created_at DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_certificate_by_id(cert_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM certificates WHERE certificate_id=?", (cert_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def check_duplicate(student_name, event):
    conn = get_connection()
    row = conn.execute(
        "SELECT id FROM certificates WHERE student_name=? AND event=?",
        (student_name, event)
    ).fetchone()
    conn.close()
    return row is not None

def get_admin(username):
    conn = get_connection()
    row = conn.execute("SELECT * FROM admins WHERE username=?", (username,)).fetchone()
    conn.close()
    return dict(row) if row else None

def update_admin(username, data: dict):
    sets = ", ".join([f"{k}=?" for k in data])
    conn = get_connection()
    conn.execute(f"UPDATE admins SET {sets} WHERE username=?", list(data.values()) + [username])
    conn.commit()
    conn.close()

def get_stats():
    conn = get_connection()
    total_certs = conn.execute("SELECT COUNT(*) FROM certificates").fetchone()[0]
    total_templates = conn.execute("SELECT COUNT(*) FROM templates").fetchone()[0]
    recent = conn.execute(
        "SELECT * FROM certificates ORDER BY created_at DESC LIMIT 5"
    ).fetchall()
    conn.close()
    return {
        "total_certificates": total_certs,
        "total_templates": total_templates,
        "recent_certificates": [dict(r) for r in recent],
    }
import bcrypt
import streamlit as st
from database import get_admin, update_admin

def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()

def login(username: str, password: str) -> bool:
    admin = get_admin(username)
    if admin and verify_password(password, admin["password_hash"]):
        st.session_state["authenticated"] = True
        st.session_state["admin_username"] = username
        st.session_state["admin_name"] = admin.get("full_name", username)
        return True
    return False

def logout():
    for key in ["authenticated", "admin_username", "admin_name"]:
        st.session_state.pop(key, None)

def is_authenticated() -> bool:
    return st.session_state.get("authenticated", False)

def change_password(username: str, old_pw: str, new_pw: str) -> tuple[bool, str]:
    admin = get_admin(username)
    if not admin:
        return False, "Admin not found."
    if not verify_password(old_pw, admin["password_hash"]):
        return False, "Current password is incorrect."
    if len(new_pw) < 6:
        return False, "New password must be at least 6 characters."
    update_admin(username, {"password_hash": hash_password(new_pw)})
    return True, "Password changed successfully."

def update_profile(username: str, full_name: str, email: str) -> tuple[bool, str]:
    update_admin(username, {"full_name": full_name, "email": email})
    st.session_state["admin_name"] = full_name
    return True, "Profile updated successfully."

def render_login_page():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700&family=Lato:wght@300;400;700&display=swap');

    .stApp { background: linear-gradient(135deg, #0f0c29, #302b63, #24243e); }

    .login-container {
        max-width: 420px;
        margin: 60px auto;
        background: rgba(255,255,255,0.05);
        backdrop-filter: blur(20px);
        border: 1px solid rgba(255,255,255,0.15);
        border-radius: 20px;
        padding: 48px 40px;
        box-shadow: 0 25px 80px rgba(0,0,0,0.4);
    }
    .login-title {
        font-family: 'Playfair Display', serif;
        font-size: 2rem;
        color: #f0c060;
        text-align: center;
        margin-bottom: 4px;
        letter-spacing: 1px;
    }
    .login-subtitle {
        font-family: 'Lato', sans-serif;
        font-size: 0.85rem;
        color: rgba(255,255,255,0.5);
        text-align: center;
        margin-bottom: 32px;
        letter-spacing: 3px;
        text-transform: uppercase;
    }
    .stTextInput > div > div > input {
        background: rgba(255,255,255,0.08) !important;
        border: 1px solid rgba(255,255,255,0.2) !important;
        border-radius: 10px !important;
        color: white !important;
        padding: 12px 16px !important;
        font-family: 'Lato', sans-serif !important;
    }
    .stTextInput label { color: rgba(255,255,255,0.7) !important; font-family: 'Lato', sans-serif !important; }
    .stButton > button {
        background: linear-gradient(135deg, #f0c060, #e09030) !important;
        color: #1a1a2e !important;
        font-family: 'Lato', sans-serif !important;
        font-weight: 700 !important;
        border: none !important;
        border-radius: 10px !important;
        padding: 12px !important;
        width: 100% !important;
        font-size: 1rem !important;
        letter-spacing: 2px !important;
        text-transform: uppercase !important;
        cursor: pointer !important;
        transition: all 0.3s ease !important;
    }
    </style>
    """, unsafe_allow_html=True)

    st.markdown('<div class="login-container">', unsafe_allow_html=True)
    st.markdown('<div class="login-title">🎓 CertifyPro</div>', unsafe_allow_html=True)
    st.markdown('<div class="login-subtitle">Certificate Management System</div>', unsafe_allow_html=True)

    with st.form("login_form"):
        username = st.text_input("Username", placeholder="Enter username")
        password = st.text_input("Password", type="password", placeholder="Enter password")
        submitted = st.form_submit_button("SIGN IN")
        if submitted:
            if login(username, password):
                st.success("Login successful!")
                st.rerun()
            else:
                st.error("❌ Invalid credentials. Please try again.")

    st.markdown('</div>', unsafe_allow_html=True)
    st.markdown('<p style="text-align:center;color:rgba(255,255,255,0.3);font-size:0.75rem;margin-top:24px;font-family:Lato,sans-serif;">Default: admin / admin123</p>', unsafe_allow_html=True)
  import os
import uuid
import qrcode
import io
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib.colors import HexColor, Color
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import tempfile

GENERATED_DIR = "generated"
os.makedirs(GENERATED_DIR, exist_ok=True)
os.makedirs(os.path.join(GENERATED_DIR, "pdf"), exist_ok=True)
os.makedirs(os.path.join(GENERATED_DIR, "png"), exist_ok=True)
os.makedirs(os.path.join(GENERATED_DIR, "qr"), exist_ok=True)

PAGE_W, PAGE_H = landscape(A4)  # 841.89 x 595.28 pts


def generate_certificate_id():
    return "CERT-" + uuid.uuid4().hex[:10].upper()


def hex_to_rgb_tuple(hex_color: str):
    hex_color = hex_color.lstrip("#")
    r = int(hex_color[0:2], 16) / 255.0
    g = int(hex_color[2:4], 16) / 255.0
    b = int(hex_color[4:6], 16) / 255.0
    return r, g, b


def generate_qr(certificate_id: str) -> str:
    qr_path = os.path.join(GENERATED_DIR, "qr", f"{certificate_id}.png")
    qr = qrcode.QRCode(version=1, box_size=6, border=2)
    qr.add_data(certificate_id)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    img.save(qr_path)
    return qr_path


def rl_font(font_name: str, bold: bool = False, italic: bool = False) -> str:
    base = font_name if font_name else "Helvetica"
    if "Helvetica" in base or "helvetica" in base:
        if bold and italic:
            return "Helvetica-BoldOblique"
        elif bold:
            return "Helvetica-Bold"
        elif italic:
            return "Helvetica-Oblique"
        return "Helvetica"
    if "Times" in base or "times" in base:
        if bold and italic:
            return "Times-BoldItalic"
        elif bold:
            return "Times-Bold"
        elif italic:
            return "Times-Italic"
        return "Times-Roman"
    if "Courier" in base:
        if bold and italic:
            return "Courier-BoldOblique"
        elif bold:
            return "Courier-Bold"
        elif italic:
            return "Courier-Oblique"
        return "Courier"
    return base


def draw_text_centered(c, text, x_frac, y_frac, font, size, color_hex, align="center"):
    r, g, b = hex_to_rgb_tuple(color_hex)
    c.setFillColorRGB(r, g, b)
    c.setFont(font, size)
    x_pt = x_frac * PAGE_W
    y_pt = y_frac * PAGE_H
    if align == "center":
        c.drawCentredString(x_pt, y_pt, text)
    elif align == "right":
        c.drawRightString(x_pt, y_pt, text)
    else:
        c.drawString(x_pt, y_pt, text)


def generate_certificate_pdf(template: dict, data: dict, cert_id: str) -> tuple[str, str]:
    """Returns (pdf_path, png_path)"""
    pdf_path = os.path.join(GENERATED_DIR, "pdf", f"{cert_id}.pdf")
    png_path = os.path.join(GENERATED_DIR, "png", f"{cert_id}.png")
    qr_path = generate_qr(cert_id)

    c = canvas.Canvas(pdf_path, pagesize=landscape(A4))
    c.setPageSize(landscape(A4))

    # Background
    if template.get("background_path") and os.path.exists(template["background_path"]):
        try:
            bg = ImageReader(template["background_path"])
            c.drawImage(bg, 0, 0, width=PAGE_W, height=PAGE_H, preserveAspectRatio=False)
        except Exception:
            _draw_default_background(c)
    else:
        _draw_default_background(c)

    # Watermark
    if template.get("watermark_text", "").strip():
        _draw_watermark(c, template["watermark_text"], float(template.get("watermark_transparency", 0.1)))

    # Logo
    if template.get("logo_path") and os.path.exists(template["logo_path"]):
        try:
            logo = ImageReader(template["logo_path"])
            lw = int(template.get("logo_width", 100))
            lh = int(template.get("logo_height", 100))
            lx = float(template.get("logo_x", 0.5)) * PAGE_W - lw / 2
            ly = float(template.get("logo_y", 0.85)) * PAGE_H - lh / 2
            opacity = float(template.get("logo_transparency", 1.0))
            c.saveState()
            c.setFillAlpha(opacity)
            c.drawImage(logo, lx, ly, width=lw, height=lh, preserveAspectRatio=True, mask="auto")
            c.restoreState()
        except Exception:
            pass

    # School name
    if template.get("school_name", "").strip():
        draw_text_centered(
            c,
            template["school_name"],
            float(template.get("school_name_x", 0.5)),
            float(template.get("school_name_y", 0.88)),
            rl_font(
                template.get("school_name_font", "Helvetica"),
                bool(template.get("school_name_bold", 1)),
                bool(template.get("school_name_italic", 0)),
            ),
            int(template.get("school_name_size", 36)),
            template.get("school_name_color", "#1a1a2e"),
            template.get("school_name_align", "center"),
        )

    # Certificate of achievement heading
    c.setFillColorRGB(0.4, 0.3, 0.1)
    c.setFont("Helvetica-Oblique", 18)
    c.drawCentredString(PAGE_W / 2, PAGE_H * 0.75, "Certificate of Achievement")

    # Recipient name
    draw_text_centered(
        c,
        data.get("name", ""),
        float(template.get("name_x", 0.5)),
        float(template.get("name_y", 0.62)),
        rl_font(template.get("name_font", "Helvetica"), True, False),
        int(template.get("name_size", 48)),
        template.get("name_color", "#1a1a2e"),
        "center",
    )

    # Divider line under name
    c.setStrokeColorRGB(0.75, 0.6, 0.2)
    c.setLineWidth(1.5)
    name_y = float(template.get("name_y", 0.62)) * PAGE_H
    c.line(PAGE_W * 0.2, name_y - 8, PAGE_W * 0.8, name_y - 8)

    # Course
    if data.get("course"):
        c.setFillColorRGB(0.25, 0.25, 0.25)
        c.setFont(rl_font(template.get("course_font", "Helvetica"), False, True), int(template.get("course_size", 22)))
        c.drawCentredString(
            float(template.get("course_x", 0.5)) * PAGE_W,
            float(template.get("course_y", 0.53)) * PAGE_H,
            f"for successfully completing  {data['course']}",
        )

    # Event
    if data.get("event"):
        c.setFillColorRGB(0.35, 0.35, 0.35)
        c.setFont("Helvetica", 16)
        c.drawCentredString(PAGE_W / 2, PAGE_H * 0.46, f"Event: {data['event']}")

    # Grade & Rank
    if data.get("grade"):
        c.setFillColorRGB(0.15, 0.3, 0.6)
        c.setFont("Helvetica-Bold", 16)
        c.drawString(float(template.get("grade_x", 0.35)) * PAGE_W, float(template.get("grade_y", 0.38)) * PAGE_H,
                     f"Grade: {data['grade']}")
    if data.get("rank"):
        c.setFillColorRGB(0.6, 0.3, 0.1)
        c.setFont("Helvetica-Bold", 16)
        c.drawString(float(template.get("rank_x", 0.55)) * PAGE_W, float(template.get("rank_y", 0.38)) * PAGE_H,
                     f"Rank: {data['rank']}")

    # Date
    c.setFillColorRGB(0.3, 0.3, 0.3)
    c.setFont("Helvetica", 14)
    c.drawString(
        float(template.get("date_x", 0.15)) * PAGE_W,
        float(template.get("date_y", 0.28)) * PAGE_H,
        f"Date: {data.get('date', '')}",
    )

    # Signatures
    sig_y = float(template.get("sig_principal_y", 0.22)) * PAGE_H
    sw = int(template.get("sig_width", 120))
    sh = int(template.get("sig_height", 60))

    if template.get("signature_principal_path") and os.path.exists(template["signature_principal_path"]):
        try:
            sig = ImageReader(template["signature_principal_path"])
            sx = float(template.get("sig_principal_x", 0.2)) * PAGE_W - sw / 2
            c.drawImage(sig, sx, sig_y, width=sw, height=sh, preserveAspectRatio=True, mask="auto")
        except Exception:
            pass

    if template.get("signature_coordinator_path") and os.path.exists(template["signature_coordinator_path"]):
        try:
            sig2 = ImageReader(template["signature_coordinator_path"])
            sx2 = float(template.get("sig_coordinator_x", 0.8)) * PAGE_W - sw / 2
            c.drawImage(sig2, sx2, sig_y, width=sw, height=sh, preserveAspectRatio=True, mask="auto")
        except Exception:
            pass

    # Signature labels
    c.setFillColorRGB(0.2, 0.2, 0.2)
    c.setFont("Helvetica", 10)
    c.drawCentredString(float(template.get("sig_principal_x", 0.2)) * PAGE_W, sig_y - 14, "Principal")
    c.drawCentredString(float(template.get("sig_coordinator_x", 0.8)) * PAGE_W, sig_y - 14, "Coordinator")

    # Signature lines
    c.setStrokeColorRGB(0.5, 0.5, 0.5)
    c.setLineWidth(0.8)
    px = float(template.get("sig_principal_x", 0.2)) * PAGE_W
    cx2 = float(template.get("sig_coordinator_x", 0.8)) * PAGE_W
    c.line(px - 60, sig_y - 2, px + 60, sig_y - 2)
    c.line(cx2 - 60, sig_y - 2, cx2 + 60, sig_y - 2)

    # Certificate ID
    c.setFillColorRGB(0.5, 0.5, 0.5)
    c.setFont("Helvetica", 9)
    c.drawString(20, 20, f"Certificate ID: {cert_id}")

    # QR Code
    if os.path.exists(qr_path):
        try:
            qr_img = ImageReader(qr_path)
            c.drawImage(qr_img, PAGE_W - 90, 10, width=75, height=75, preserveAspectRatio=True)
        except Exception:
            pass

    c.save()

    # Generate PNG preview
    try:
        _pdf_to_png_fallback(cert_id, pdf_path, png_path, template, data, qr_path)
    except Exception:
        pass

    return pdf_path, png_path


def _draw_default_background(c):
    """Draw a beautiful default gradient-like background using rectangles."""
    # Cream/ivory base
    c.setFillColorRGB(0.99, 0.97, 0.93)
    c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)

    # Decorative outer border
    c.setStrokeColorRGB(0.75, 0.60, 0.20)
    c.setLineWidth(6)
    c.rect(15, 15, PAGE_W - 30, PAGE_H - 30, fill=0, stroke=1)

    c.setStrokeColorRGB(0.85, 0.70, 0.30)
    c.setLineWidth(2)
    c.rect(22, 22, PAGE_W - 44, PAGE_H - 44, fill=0, stroke=1)

    # Corner decorations
    size = 30
    c.setStrokeColorRGB(0.75, 0.60, 0.20)
    c.setLineWidth(2)
    for (cx, cy) in [(30, 30), (PAGE_W - 30, 30), (30, PAGE_H - 30), (PAGE_W - 30, PAGE_H - 30)]:
        c.line(cx - size, cy, cx + size, cy)
        c.line(cx, cy - size, cx, cy + size)

    # Header band
    c.setFillColorRGB(0.15, 0.12, 0.35)
    c.rect(0, PAGE_H - 80, PAGE_W, 80, fill=1, stroke=0)

    # Footer band
    c.setFillColorRGB(0.15, 0.12, 0.35)
    c.rect(0, 0, PAGE_W, 55, fill=1, stroke=0)

    # Gold accent lines
    c.setStrokeColorRGB(0.90, 0.72, 0.25)
    c.setLineWidth(2)
    c.line(0, PAGE_H - 82, PAGE_W, PAGE_H - 82)
    c.line(0, 57, PAGE_W, 57)


def _draw_watermark(c, text, opacity):
    c.saveState()
    c.setFillColorRGB(0.7, 0.7, 0.7)
    c.setFillAlpha(opacity)
    c.setFont("Helvetica-Bold", 80)
    c.translate(PAGE_W / 2, PAGE_H / 2)
    c.rotate(45)
    c.drawCentredString(0, 0, text.upper())
    c.restoreState()


def _pdf_to_png_fallback(cert_id, pdf_path, png_path, template, data, qr_path):
    """Create PNG preview using Pillow — matches PDF layout."""
    W, H = 1684, 1190  # A4 landscape @ 2x
    img = Image.new("RGB", (W, H), (252, 247, 235))
    draw = ImageDraw.Draw(img)

    # Border
    for i, (c, w) in enumerate([(( 191, 153, 51), 12), ((217, 179, 77), 4)]):
        o = i * 14
        draw.rectangle([30 + o, 30 + o, W - 30 - o, H - 30 - o], outline=c, width=w)

    # Header & footer bands
    draw.rectangle([0, 0, W, 160], fill=(38, 30, 89))
    draw.rectangle([0, H - 110, W, H], fill=(38, 30, 89))
    draw.line([(0, 162), (W, 162)], fill=(230, 184, 64), width=4)
    draw.line([(0, H - 113), (W, H - 113)], fill=(230, 184, 64), width=4)

    # School name on header
    school = template.get("school_name", "")
    if school:
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf", 52)
        except Exception:
            font = ImageFont.load_default()
        bbox = draw.textbbox((0, 0), school, font=font)
        tw = bbox[2] - bbox[0]
        draw.text(((W - tw) // 2, 55), school, fill=(240, 192, 96), font=font)

    # Title
    try:
        title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSerif-BoldItalic.ttf", 36)
    except Exception:
        title_font = ImageFont.load_default()
    t = "Certificate of Achievement"
    bbox = draw.textbbox((0, 0), t, font=title_font)
    draw.text(((W - (bbox[2] - bbox[0])) // 2, 210), t, fill=(102, 77, 26), font=title_font)

    # Name
    try:
        name_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf", 72)
    except Exception:
        name_font = ImageFont.load_default()
    name = data.get("name", "")
    bbox = draw.textbbox((0, 0), name, font=name_font)
    tw = bbox[2] - bbox[0]
    name_y = 420
    draw.text(((W - tw) // 2, name_y), name, fill=(26, 26, 46), font=name_font)
    draw.line([(W * 0.2, name_y + 88), (W * 0.8, name_y + 88)], fill=(191, 153, 51), width=3)

    # Course
    if data.get("course"):
        try:
            cf = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSerifCondensed-Italic.ttf", 32)
        except Exception:
            cf = ImageFont.load_default()
        ct = f"for successfully completing  {data['course']}"
        bbox = draw.textbbox((0, 0), ct, font=cf)
        draw.text(((W - (bbox[2] - bbox[0])) // 2, 540), ct, fill=(64, 64, 64), font=cf)

    # Event, grade, rank, date
    try:
        sf = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 26)
        sbf = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 26)
    except Exception:
        sf = sbf = ImageFont.load_default()

    if data.get("event"):
        et = f"Event: {data['event']}"
        bbox = draw.textbbox((0, 0), et, font=sf)
        draw.text(((W - (bbox[2] - bbox[0])) // 2, 620), et, fill=(89, 89, 89), font=sf)

    if data.get("grade"):
        draw.text((int(W * 0.32), 720), f"Grade: {data['grade']}", fill=(38, 77, 153), font=sbf)
    if data.get("rank"):
        draw.text((int(W * 0.55), 720), f"Rank: {data['rank']}", fill=(153, 77, 26), font=sbf)
    if data.get("date"):
        draw.text((int(W * 0.1), 820), f"Date: {data['date']}", fill=(77, 77, 77), font=sf)

    # Sig lines
    draw.line([(int(W * 0.12), 970), (int(W * 0.38), 970)], fill=(128, 128, 128), width=2)
    draw.line([(int(W * 0.62), 970), (int(W * 0.88), 970)], fill=(128, 128, 128), width=2)
    draw.text((int(W * 0.18), 976), "Principal", fill=(51, 51, 51), font=sf)
    draw.text((int(W * 0.68), 976), "Coordinator", fill=(51, 51, 51), font=sf)

    # Cert ID
    try:
        small_f = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
    except Exception:
        small_f = ImageFont.load_default()
    draw.text((40, H - 90), f"Certificate ID: {cert_id}", fill=(200, 200, 200), font=small_f)

    # QR Code
    if os.path.exists(qr_path):
        try:
            qr_img = Image.open(qr_path).resize((150, 150))
            img.paste(qr_img, (W - 180, H - 170))
        except Exception:
            pass

    img.save(png_path, "PNG", dpi=(150, 150))


def generate_bulk(template: dict, rows: list) -> list:
    """Generate certificates for a list of dicts. Returns list of result dicts."""
    results = []
    for row in rows:
        cert_id = generate_certificate_id()
        try:
            pdf_path, png_path = generate_certificate_pdf(template, row, cert_id)
            results.append({
                "cert_id": cert_id,
                "name": row.get("name", ""),
                "pdf_path": pdf_path,
                "png_path": png_path,
                "status": "success",
                "error": "",
            })
        except Exception as e:
            results.append({
                "cert_id": cert_id,
                "name": row.get("name", ""),
                "pdf_path": "",
                "png_path": "",
                "status": "error",
                "error": str(e),
            })
    return results
      import streamlit as st
import os
from PIL import Image
import io
import database as db

ASSETS_DIR = "assets"
os.makedirs(ASSETS_DIR, exist_ok=True)
os.makedirs(os.path.join(ASSETS_DIR, "backgrounds"), exist_ok=True)
os.makedirs(os.path.join(ASSETS_DIR, "logos"), exist_ok=True)
os.makedirs(os.path.join(ASSETS_DIR, "signatures"), exist_ok=True)

FONTS = ["Helvetica", "Helvetica-Bold", "Times-Roman", "Times-Bold", "Courier", "Courier-Bold"]
FONT_DISPLAY = {
    "Helvetica": "Helvetica (Sans-Serif)",
    "Helvetica-Bold": "Helvetica Bold",
    "Times-Roman": "Times Roman (Serif)",
    "Times-Bold": "Times Bold",
    "Courier": "Courier (Monospace)",
    "Courier-Bold": "Courier Bold",
}


def save_uploaded_file(uploaded_file, subfolder):
    path = os.path.join(ASSETS_DIR, subfolder, uploaded_file.name)
    with open(path, "wb") as f:
        f.write(uploaded_file.read())
    return path


def render_template_builder():
    st.markdown("## 🎨 Template Builder")
    st.markdown("---")

    templates = db.get_templates()
    tab1, tab2, tab3 = st.tabs(["➕ Create New Template", "✏️ Edit Template", "🗑️ Manage Templates"])

    with tab1:
        render_template_form(None)

    with tab2:
        if not templates:
            st.info("No templates yet. Create one first.")
        else:
            template_names = {t["name"]: t["id"] for t in templates}
            selected = st.selectbox("Select template to edit", list(template_names.keys()))
            if selected:
                tpl = db.get_template(template_names[selected])
                render_template_form(tpl)

    with tab3:
        render_manage_templates(templates)


def render_template_form(existing=None):
    is_edit = existing is not None
    prefix = "edit_" if is_edit else "new_"

    with st.form(f"{prefix}template_form"):
        st.markdown("### 📋 Basic Information")
        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input("Template Name *", value=existing["name"] if existing else "", key=f"{prefix}name")
            school_name = st.text_input("School Name", value=existing.get("school_name", "") if existing else db.get_setting("school_name"), key=f"{prefix}school_name")
        with col2:
            watermark_text = st.text_input("Watermark Text (optional)", value=existing.get("watermark_text", "") if existing else "", key=f"{prefix}wm_text")
            watermark_transparency = st.slider("Watermark Opacity", 0.0, 0.5, float(existing.get("watermark_transparency", 0.08)) if existing else 0.08, 0.01, key=f"{prefix}wm_opacity")

        st.markdown("### 🖼️ Images")
        col1, col2, col3 = st.columns(3)
        with col1:
            bg_file = st.file_uploader("Background Image", type=["png", "jpg", "jpeg"], key=f"{prefix}bg")
            if existing and existing.get("background_path"):
                st.caption(f"Current: {os.path.basename(existing['background_path'])}")
        with col2:
            logo_file = st.file_uploader("School Logo/Emblem", type=["png", "jpg", "jpeg"], key=f"{prefix}logo")
            if existing and existing.get("logo_path"):
                st.caption(f"Current: {os.path.basename(existing['logo_path'])}")
        with col3:
            sig_principal = st.file_uploader("Principal Signature", type=["png", "jpg", "jpeg"], key=f"{prefix}sig_p")
            sig_coordinator = st.file_uploader("Coordinator Signature", type=["png", "jpg", "jpeg"], key=f"{prefix}sig_c")

        st.markdown("### 📌 Element Positions (0.0 = left/bottom, 1.0 = right/top)")

        st.markdown("**School Name Position & Style**")
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            sn_x = st.slider("X Position", 0.0, 1.0, float(existing.get("school_name_x", 0.5)) if existing else 0.5, 0.01, key=f"{prefix}sn_x")
        with c2:
            sn_y = st.slider("Y Position", 0.0, 1.0, float(existing.get("school_name_y", 0.88)) if existing else 0.88, 0.01, key=f"{prefix}sn_y")
        with c3:
            sn_size = st.number_input("Font Size", 12, 72, int(existing.get("school_name_size", 36)) if existing else 36, key=f"{prefix}sn_size")
        with c4:
            sn_color = st.color_picker("Color", existing.get("school_name_color", "#f0c060") if existing else "#f0c060", key=f"{prefix}sn_color")

        c1, c2, c3 = st.columns(3)
        with c1:
            sn_font = st.selectbox("Font", FONTS, index=FONTS.index(existing.get("school_name_font", "Helvetica")) if existing and existing.get("school_name_font") in FONTS else 0, key=f"{prefix}sn_font")
        with c2:
            sn_bold = st.checkbox("Bold", value=bool(existing.get("school_name_bold", True)) if existing else True, key=f"{prefix}sn_bold")
            sn_italic = st.checkbox("Italic", value=bool(existing.get("school_name_italic", False)) if existing else False, key=f"{prefix}sn_italic")
        with c3:
            sn_align = st.selectbox("Alignment", ["center", "left", "right"], index=["center", "left", "right"].index(existing.get("school_name_align", "center")) if existing else 0, key=f"{prefix}sn_align")

        st.markdown("**Logo Position & Size**")
        c1, c2, c3, c4, c5 = st.columns(5)
        with c1:
            logo_x = st.slider("Logo X", 0.0, 1.0, float(existing.get("logo_x", 0.5)) if existing else 0.5, 0.01, key=f"{prefix}logo_x")
        with c2:
            logo_y = st.slider("Logo Y", 0.0, 1.0, float(existing.get("logo_y", 0.85)) if existing else 0.85, 0.01, key=f"{prefix}logo_y")
        with c3:
            logo_w = st.number_input("Logo Width (px)", 20, 300, int(existing.get("logo_width", 100)) if existing else 100, key=f"{prefix}logo_w")
        with c4:
            logo_h = st.number_input("Logo Height (px)", 20, 300, int(existing.get("logo_height", 100)) if existing else 100, key=f"{prefix}logo_h")
        with c5:
            logo_trans = st.slider("Logo Opacity", 0.1, 1.0, float(existing.get("logo_transparency", 1.0)) if existing else 1.0, 0.05, key=f"{prefix}logo_trans")

        st.markdown("**Name Text Position**")
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            name_x = st.slider("Name X", 0.0, 1.0, float(existing.get("name_x", 0.5)) if existing else 0.5, 0.01, key=f"{prefix}name_x")
        with c2:
            name_y = st.slider("Name Y", 0.0, 1.0, float(existing.get("name_y", 0.55)) if existing else 0.55, 0.01, key=f"{prefix}name_y")
        with c3:
            name_size = st.number_input("Name Font Size", 18, 96, int(existing.get("name_size", 48)) if existing else 48, key=f"{prefix}name_size")
        with c4:
            name_color = st.color_picker("Name Color", existing.get("name_color", "#1a1a2e") if existing else "#1a1a2e", key=f"{prefix}name_color")

        st.markdown("**Signature Positions**")
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            sig_p_x = st.slider("Principal X", 0.0, 1.0, float(existing.get("sig_principal_x", 0.2)) if existing else 0.2, 0.01, key=f"{prefix}sig_p_x")
        with c2:
            sig_p_y = st.slider("Principal Y", 0.0, 1.0, float(existing.get("sig_principal_y", 0.22)) if existing else 0.22, 0.01, key=f"{prefix}sig_p_y")
        with c3:
            sig_c_x = st.slider("Coordinator X", 0.0, 1.0, float(existing.get("sig_coordinator_x", 0.8)) if existing else 0.8, 0.01, key=f"{prefix}sig_c_x")
        with c4:
            sig_c_y = st.slider("Coordinator Y", 0.0, 1.0, float(existing.get("sig_coordinator_y", 0.22)) if existing else 0.22, 0.01, key=f"{prefix}sig_c_y")

        submitted = st.form_submit_button("💾 Save Template", use_container_width=True)

        if submitted:
            if not name.strip():
                st.error("Template name is required.")
                return

            data = {
                "name": name,
                "school_name": school_name,
                "watermark_text": watermark_text,
                "watermark_transparency": watermark_transparency,
                "school_name_x": sn_x, "school_name_y": sn_y,
                "school_name_size": sn_size, "school_name_color": sn_color,
                "school_name_font": sn_font, "school_name_bold": int(sn_bold),
                "school_name_italic": int(sn_italic), "school_name_align": sn_align,
                "logo_x": logo_x, "logo_y": logo_y,
                "logo_width": logo_w, "logo_height": logo_h, "logo_transparency": logo_trans,
                "name_x": name_x, "name_y": name_y,
                "name_size": name_size, "name_color": name_color,
                "sig_principal_x": sig_p_x, "sig_principal_y": sig_p_y,
                "sig_coordinator_x": sig_c_x, "sig_coordinator_y": sig_c_y,
            }

            if bg_file:
                data["background_path"] = save_uploaded_file(bg_file, "backgrounds")
            elif existing:
                data["background_path"] = existing.get("background_path", "")

            if logo_file:
                data["logo_path"] = save_uploaded_file(logo_file, "logos")
            elif existing:
                data["logo_path"] = existing.get("logo_path", "")

            if sig_principal:
                data["signature_principal_path"] = save_uploaded_file(sig_principal, "signatures")
            elif existing:
                data["signature_principal_path"] = existing.get("signature_principal_path", "")

            if sig_coordinator:
                data["signature_coordinator_path"] = save_uploaded_file(sig_coordinator, "signatures")
            elif existing:
                data["signature_coordinator_path"] = existing.get("signature_coordinator_path", "")

            if is_edit:
                db.update_template(existing["id"], data)
                st.success(f"✅ Template '{name}' updated successfully!")
            else:
                db.save_template(data)
                st.success(f"✅ Template '{name}' created successfully!")
            st.rerun()


def render_manage_templates(templates):
    if not templates:
        st.info("No templates found.")
        return

    st.markdown(f"**{len(templates)} template(s) saved**")
    for tpl in templates:
        with st.expander(f"🎨 {tpl['name']} — {tpl['created_at'][:10]}"):
            c1, c2 = st.columns([3, 1])
            with c1:
                st.write(f"**School:** {tpl.get('school_name', 'N/A')}")
                st.write(f"**Watermark:** {tpl.get('watermark_text', 'None')}")
                bg = tpl.get("background_path", "")
                st.write(f"**Background:** {os.path.basename(bg) if bg else 'Default'}")
            with c2:
                if st.button("🗑️ Delete", key=f"del_tpl_{tpl['id']}"):
                    db.delete_template(tpl["id"])
                    st.success("Deleted.")
                    st.rerun()
