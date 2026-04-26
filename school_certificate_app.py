# ============================================================
# SCHOOL CERTIFICATE GENERATOR — Single File Streamlit App
# Fixed: final generated certificate now exactly matches
#        the template-editor preview.
# ============================================================

import streamlit as st
import sqlite3
import os
import io
import uuid
import zipfile
import hashlib
import base64
from datetime import datetime, date

import pandas as pd
import qrcode
from PIL import Image, ImageDraw, ImageFont

from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib.colors import HexColor

# ─────────────────────────────────────────────
# 1. CONSTANTS & DIRECTORIES
# ─────────────────────────────────────────────

DB_PATH    = "certificates.db"
ASSETS_DIR = "cert_assets"
GEN_DIR    = "cert_generated"

for _d in [
    ASSETS_DIR, GEN_DIR,
    os.path.join(ASSETS_DIR, "logos"),
    os.path.join(ASSETS_DIR, "signatures"),
    os.path.join(ASSETS_DIR, "backgrounds"),
    os.path.join(GEN_DIR, "pdf"),
    os.path.join(GEN_DIR, "png"),
    os.path.join(GEN_DIR, "qr"),
]:
    os.makedirs(_d, exist_ok=True)

# PDF canvas dimensions (landscape A4)
PAGE_W, PAGE_H = landscape(A4)   # 841.89 × 595.28 pts

# PNG canvas dimensions (same aspect ratio × 2)
PNG_W, PNG_H = 1684, 1190

# ─────────────────────────────────────────────
# 2. DATABASE
# ─────────────────────────────────────────────

def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    c   = _conn()
    cur = c.cursor()

    cur.execute("""CREATE TABLE IF NOT EXISTS admins (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        username      TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        full_name     TEXT DEFAULT '',
        email         TEXT DEFAULT ''
    )""")

    cur.execute("""CREATE TABLE IF NOT EXISTS templates (
        id                 INTEGER PRIMARY KEY AUTOINCREMENT,
        name               TEXT    NOT NULL,
        school_name        TEXT    DEFAULT '',
        school_name_x      REAL    DEFAULT 0.5,
        school_name_y      REAL    DEFAULT 0.88,
        school_name_size   INTEGER DEFAULT 36,
        school_name_color  TEXT    DEFAULT '#f0c060',
        logo_path          TEXT    DEFAULT '',
        logo_x             REAL    DEFAULT 0.5,
        logo_y             REAL    DEFAULT 0.85,
        logo_w             INTEGER DEFAULT 100,
        logo_h             INTEGER DEFAULT 100,
        sig_path           TEXT    DEFAULT '',
        sig_x              REAL    DEFAULT 0.5,
        sig_y              REAL    DEFAULT 0.22,
        watermark          TEXT    DEFAULT '',
        watermark_opacity  REAL    DEFAULT 0.08,
        bg_path            TEXT    DEFAULT '',
        created_at         TEXT    DEFAULT (datetime('now'))
    )""")

    cur.execute("""CREATE TABLE IF NOT EXISTS certificates (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        certificate_id TEXT UNIQUE NOT NULL,
        student_name   TEXT NOT NULL,
        course         TEXT DEFAULT '',
        event          TEXT DEFAULT '',
        issue_date     TEXT DEFAULT '',
        grade          TEXT DEFAULT '',
        template_id    INTEGER DEFAULT 0,
        template_name  TEXT DEFAULT '',
        pdf_path       TEXT DEFAULT '',
        png_path       TEXT DEFAULT '',
        created_at     TEXT DEFAULT (datetime('now'))
    )""")

    c.commit()

    if cur.execute("SELECT COUNT(*) FROM admins").fetchone()[0] == 0:
        h = hashlib.sha256("admin123".encode()).hexdigest()
        cur.execute(
            "INSERT INTO admins (username,password_hash,full_name) VALUES (?,?,?)",
            ("admin", h, "Administrator"),
        )
        c.commit()

    c.close()


def _hash(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


def db_check_login(username: str, password: str) -> bool:
    c   = _conn()
    row = c.execute("SELECT password_hash FROM admins WHERE username=?", (username,)).fetchone()
    c.close()
    return row is not None and row["password_hash"] == _hash(password)


def db_change_password(username: str, new_pw: str):
    c = _conn()
    c.execute("UPDATE admins SET password_hash=? WHERE username=?", (_hash(new_pw), username))
    c.commit()
    c.close()


def db_save_template(data: dict) -> int:
    c    = _conn()
    cols = ", ".join(data.keys())
    ph   = ", ".join(["?"] * len(data))
    cur  = c.execute(f"INSERT INTO templates ({cols}) VALUES ({ph})", list(data.values()))
    c.commit()
    tid  = cur.lastrowid
    c.close()
    return tid


def db_get_templates() -> list:
    c    = _conn()
    rows = c.execute("SELECT * FROM templates ORDER BY created_at DESC").fetchall()
    c.close()
    return [dict(r) for r in rows]


def db_get_template(tid: int):
    c   = _conn()
    row = c.execute("SELECT * FROM templates WHERE id=?", (tid,)).fetchone()
    c.close()
    return dict(row) if row else None


def db_delete_template(tid: int):
    c = _conn()
    c.execute("DELETE FROM templates WHERE id=?", (tid,))
    c.commit()
    c.close()


def db_save_cert(data: dict):
    c    = _conn()
    cols = ", ".join(data.keys())
    ph   = ", ".join(["?"] * len(data))
    c.execute(f"INSERT INTO certificates ({cols}) VALUES ({ph})", list(data.values()))
    c.commit()
    c.close()


def db_get_certs(name_q="", id_q="") -> list:
    c      = _conn()
    q      = "SELECT * FROM certificates WHERE 1=1"
    params = []
    if name_q:
        q += " AND student_name LIKE ?"
        params.append(f"%{name_q}%")
    if id_q:
        q += " AND certificate_id LIKE ?"
        params.append(f"%{id_q}%")
    q    += " ORDER BY created_at DESC"
    rows  = c.execute(q, params).fetchall()
    c.close()
    return [dict(r) for r in rows]


def db_get_cert_by_id(cid: str):
    c   = _conn()
    row = c.execute("SELECT * FROM certificates WHERE certificate_id=?", (cid,)).fetchone()
    c.close()
    return dict(row) if row else None


def db_stats() -> dict:
    c      = _conn()
    total     = c.execute("SELECT COUNT(*) FROM certificates").fetchone()[0]
    templates = c.execute("SELECT COUNT(*) FROM templates").fetchone()[0]
    recent    = c.execute("SELECT * FROM certificates ORDER BY created_at DESC LIMIT 5").fetchall()
    c.close()
    return {"total": total, "templates": templates, "recent": [dict(r) for r in recent]}


def db_check_duplicate(name: str, event: str) -> bool:
    c   = _conn()
    row = c.execute(
        "SELECT id FROM certificates WHERE student_name=? AND event=?", (name, event)
    ).fetchone()
    c.close()
    return row is not None


# ─────────────────────────────────────────────
# 3. COORDINATE HELPERS
# ─────────────────────────────────────────────
# All template position fractions use the convention:
#   x : 0 = left edge,   1 = right edge
#   y : 0 = BOTTOM edge, 1 = TOP edge   (matches PDF / natural math coords)
#
# PDF (ReportLab) already uses bottom-left origin, so:
#   pdf_x = frac_x * PAGE_W
#   pdf_y = frac_y * PAGE_H
#
# PNG (Pillow) uses top-left origin, so we must flip Y:
#   png_x = frac_x * PNG_W
#   png_y = (1 - frac_y) * PNG_H

def pdf_xy(frac_x: float, frac_y: float) -> tuple:
    return frac_x * PAGE_W, frac_y * PAGE_H


def png_xy(frac_x: float, frac_y: float) -> tuple:
    return int(frac_x * PNG_W), int((1.0 - frac_y) * PNG_H)


def hex_to_rgb_float(h: str) -> tuple:
    h = h.lstrip("#")
    return int(h[0:2], 16) / 255.0, int(h[2:4], 16) / 255.0, int(h[4:6], 16) / 255.0


def hex_to_rgb_int(h: str) -> tuple:
    r, g, b = hex_to_rgb_float(h)
    return int(r * 255), int(g * 255), int(b * 255)


# ─────────────────────────────────────────────
# 4. UTILITY
# ─────────────────────────────────────────────

def gen_cert_id() -> str:
    return "CERT-" + uuid.uuid4().hex[:10].upper()


def make_qr(cert_id: str) -> str:
    path = os.path.join(GEN_DIR, "qr", f"{cert_id}.png")
    qr   = qrcode.QRCode(version=1, box_size=6, border=2)
    qr.add_data(cert_id)
    qr.make(fit=True)
    qr.make_image(fill_color="black", back_color="white").save(path)
    return path


def save_uploaded(uploaded_file, subfolder: str) -> str:
    path = os.path.join(ASSETS_DIR, subfolder, uploaded_file.name)
    with open(path, "wb") as f:
        f.write(uploaded_file.getvalue())
    return path


# ─────────────────────────────────────────────
# 5. DEFAULT BACKGROUND HELPERS
# ─────────────────────────────────────────────

def _draw_default_bg_pdf(c: canvas.Canvas):
    """Draw the default navy/cream background on the ReportLab canvas."""
    c.setFillColorRGB(0.99, 0.97, 0.93)
    c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
    c.setFillColorRGB(0.15, 0.12, 0.35)
    c.rect(0, PAGE_H - 80, PAGE_W, 80, fill=1, stroke=0)
    c.rect(0, 0, PAGE_W, 52, fill=1, stroke=0)
    for color, width, offset in [
        ((0.75, 0.60, 0.20), 6, 14),
        ((0.85, 0.70, 0.30), 2, 22),
    ]:
        c.setStrokeColorRGB(*color)
        c.setLineWidth(width)
        c.rect(offset, offset, PAGE_W - offset * 2, PAGE_H - offset * 2, fill=0, stroke=1)
    c.setStrokeColorRGB(0.90, 0.72, 0.25)
    c.setLineWidth(2)
    c.line(0, PAGE_H - 82, PAGE_W, PAGE_H - 82)
    c.line(0, 54, PAGE_W, 54)
    size = 28
    for px, py in [
        (30, 30), (PAGE_W - 30, 30),
        (30, PAGE_H - 30), (PAGE_W - 30, PAGE_H - 30),
    ]:
        c.line(px - size, py, px + size, py)
        c.line(px, py - size, px, py + size)


def _draw_default_bg_png(img: Image.Image) -> Image.Image:
    """Draw the default navy/cream background on a Pillow image."""
    draw = ImageDraw.Draw(img)
    W, H = img.size
    # header band
    draw.rectangle([0, 0, W, 168], fill=(38, 30, 89))
    # footer band
    draw.rectangle([0, H - 108, W, H], fill=(38, 30, 89))
    # separator lines
    draw.line([(0, 170), (W, 170)], fill=(230, 184, 64), width=5)
    draw.line([(0, H - 111), (W, H - 111)], fill=(230, 184, 64), width=5)
    # border frames
    for col, bw, o in [((191, 153, 51), 14, 24), ((217, 179, 77), 4, 40)]:
        draw.rectangle([o, o, W - o, H - o], outline=col, width=bw)
    return img


# ─────────────────────────────────────────────
# 6. CERTIFICATE GENERATION
# ─────────────────────────────────────────────

def generate_pdf(template: dict, data: dict, cert_id: str) -> tuple:
    """Generate PDF + PNG for a certificate. Returns (pdf_path, png_path)."""
    pdf_path = os.path.join(GEN_DIR, "pdf", f"{cert_id}.pdf")
    png_path = os.path.join(GEN_DIR, "png", f"{cert_id}.png")
    qr_path  = make_qr(cert_id)

    # ── collect template values once ──────────────────
    school_name   = template.get("school_name", "").strip()
    sn_x_frac     = float(template.get("school_name_x",    0.5))
    sn_y_frac     = float(template.get("school_name_y",    0.88))
    sn_size       = int(template.get("school_name_size",   28))
    sn_color_hex  = template.get("school_name_color",      "#f0c060")

    logo_path     = template.get("logo_path", "")
    logo_x_frac   = float(template.get("logo_x",  0.5))
    logo_y_frac   = float(template.get("logo_y",  0.85))
    logo_w_pt     = int(template.get("logo_w",    70))
    logo_h_pt     = int(template.get("logo_h",    70))

    sig_path      = template.get("sig_path", "")
    sig_x_frac    = float(template.get("sig_x",   0.5))
    sig_y_frac    = float(template.get("sig_y",   0.22))

    watermark     = template.get("watermark", "").strip()
    wm_opacity    = float(template.get("watermark_opacity", 0.08))

    bg_path       = template.get("bg_path", "")
    has_bg        = bool(bg_path) and os.path.exists(bg_path)

    # ── PDF ───────────────────────────────────────────
    _generate_pdf_file(
        pdf_path, qr_path, template, data, cert_id,
        school_name, sn_x_frac, sn_y_frac, sn_size, sn_color_hex,
        logo_path, logo_x_frac, logo_y_frac, logo_w_pt, logo_h_pt,
        sig_path, sig_x_frac, sig_y_frac,
        watermark, wm_opacity, bg_path, has_bg,
    )

    # ── PNG ───────────────────────────────────────────
    _generate_png_file(
        png_path, qr_path, data, cert_id,
        school_name, sn_x_frac, sn_y_frac, sn_size, sn_color_hex,
        logo_path, logo_x_frac, logo_y_frac, logo_w_pt, logo_h_pt,
        sig_path, sig_x_frac, sig_y_frac,
        watermark, wm_opacity, bg_path, has_bg,
    )

    return pdf_path, png_path


# ── PDF renderer ──────────────────────────────────────────────────────────────

def _generate_pdf_file(
    pdf_path, qr_path, template, data, cert_id,
    school_name, sn_x_frac, sn_y_frac, sn_size, sn_color_hex,
    logo_path, logo_x_frac, logo_y_frac, logo_w_pt, logo_h_pt,
    sig_path, sig_x_frac, sig_y_frac,
    watermark, wm_opacity, bg_path, has_bg,
):
    c = canvas.Canvas(pdf_path, pagesize=landscape(A4))

    # Background
    if has_bg:
        try:
            c.drawImage(ImageReader(bg_path), 0, 0, width=PAGE_W, height=PAGE_H)
        except Exception:
            _draw_default_bg_pdf(c)
    else:
        _draw_default_bg_pdf(c)

    # Watermark
    if watermark:
        c.saveState()
        c.setFillColorRGB(0.7, 0.7, 0.7)
        c.setFillAlpha(wm_opacity)
        c.setFont("Helvetica-Bold", 80)
        c.translate(PAGE_W / 2, PAGE_H / 2)
        c.rotate(45)
        c.drawCentredString(0, 0, watermark.upper())
        c.restoreState()

    # Logo — convert fraction coords to PDF points
    if logo_path and os.path.exists(logo_path):
        try:
            lx, ly = pdf_xy(logo_x_frac, logo_y_frac)
            c.drawImage(
                ImageReader(logo_path),
                lx - logo_w_pt / 2,
                ly - logo_h_pt / 2,
                width=logo_w_pt, height=logo_h_pt,
                preserveAspectRatio=True, mask="auto",
            )
        except Exception:
            pass

    # School Name
    if school_name:
        r, g, b = hex_to_rgb_float(sn_color_hex)
        c.setFillColorRGB(r, g, b)
        c.setFont("Helvetica-Bold", sn_size)
        sn_px, sn_py = pdf_xy(sn_x_frac, sn_y_frac)
        c.drawCentredString(sn_px, sn_py, school_name)

    # "CERTIFICATE OF ACHIEVEMENT"
    c.setFillColorRGB(0.45, 0.32, 0.05)
    c.setFont("Helvetica-Bold", 32)
    c.drawCentredString(PAGE_W / 2, PAGE_H * 0.78, "CERTIFICATE OF ACHIEVEMENT")

    # Decorative lines around heading
    c.setStrokeColorRGB(0.75, 0.60, 0.20)
    c.setLineWidth(1.5)
    c.line(PAGE_W * 0.15, PAGE_H * 0.755, PAGE_W * 0.38, PAGE_H * 0.755)
    c.line(PAGE_W * 0.62, PAGE_H * 0.755, PAGE_W * 0.85, PAGE_H * 0.755)

    # "This is to certify that"
    c.setFillColorRGB(0.30, 0.25, 0.10)
    c.setFont("Helvetica-Oblique", 20)
    c.drawCentredString(PAGE_W / 2, PAGE_H * 0.705, "This is to certify that")

    # Recipient Name
    c.setFillColorRGB(0.05, 0.05, 0.20)
    c.setFont("Helvetica-Bold", 56)
    c.drawCentredString(PAGE_W / 2, PAGE_H * 0.610, data.get("name", ""))

    # Underline
    c.setStrokeColorRGB(0.75, 0.60, 0.20)
    c.setLineWidth(2)
    c.line(PAGE_W * 0.18, PAGE_H * 0.585, PAGE_W * 0.82, PAGE_H * 0.585)

    # "has successfully completed"
    c.setFillColorRGB(0.25, 0.25, 0.25)
    c.setFont("Helvetica", 20)
    c.drawCentredString(PAGE_W / 2, PAGE_H * 0.535, "has successfully completed")

    # Course
    if data.get("course"):
        c.setFillColorRGB(0.08, 0.18, 0.48)
        c.setFont("Helvetica-Bold", 30)
        c.drawCentredString(PAGE_W / 2, PAGE_H * 0.470, data["course"].upper())

    # Event
    if data.get("event"):
        c.setFillColorRGB(0.30, 0.30, 0.30)
        c.setFont("Helvetica-Oblique", 19)
        c.drawCentredString(PAGE_W / 2, PAGE_H * 0.405,
                            f"\u2014  {data['event']}  \u2014")

    # Separator
    c.setStrokeColorRGB(0.75, 0.60, 0.20)
    c.setLineWidth(0.8)
    c.line(PAGE_W * 0.15, PAGE_H * 0.365, PAGE_W * 0.85, PAGE_H * 0.365)

    # Grade & Date
    if data.get("grade"):
        c.setFont("Helvetica-Bold", 17)
        c.setFillColorRGB(0.12, 0.28, 0.58)
        c.drawString(PAGE_W * 0.20, PAGE_H * 0.330, f"Grade :  {data['grade']}")

    if data.get("date"):
        c.setFont("Helvetica", 17)
        c.setFillColorRGB(0.25, 0.25, 0.25)
        c.drawRightString(PAGE_W * 0.80, PAGE_H * 0.330, f"Date :  {data['date']}")

    # Signature
    sig_px, sig_py = pdf_xy(sig_x_frac, sig_y_frac)
    if sig_path and os.path.exists(sig_path):
        try:
            c.drawImage(
                ImageReader(sig_path),
                sig_px - 75, sig_py + 18,
                width=150, height=58,
                preserveAspectRatio=True, mask="auto",
            )
        except Exception:
            pass
    c.setStrokeColorRGB(0.35, 0.35, 0.35)
    c.setLineWidth(1)
    c.line(sig_px - 90, sig_py + 14, sig_px + 90, sig_py + 14)
    c.setFillColorRGB(0.25, 0.25, 0.25)
    c.setFont("Helvetica", 14)
    c.drawCentredString(sig_px, sig_py - 2, "Authorized Signatory")

    # Certificate ID footer
    c.setFillColorRGB(0.55, 0.55, 0.55)
    c.setFont("Helvetica", 9)
    c.drawString(18, 18, f"Certificate ID: {cert_id}")

    # QR Code (bottom-right)
    if os.path.exists(qr_path):
        try:
            c.drawImage(
                ImageReader(qr_path), PAGE_W - 86, 8,
                width=70, height=70, preserveAspectRatio=True,
            )
        except Exception:
            pass

    c.save()


# ── PNG renderer ──────────────────────────────────────────────────────────────

def _pil_font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    paths = []
    if bold:
        paths += [
            "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
        ]
    else:
        paths += [
            "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
        ]
    paths.append("/usr/share/fonts/truetype/freefont/FreeSerif.ttf")
    for p in paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


def _generate_png_file(
    png_path, qr_path, data, cert_id,
    school_name, sn_x_frac, sn_y_frac, sn_size, sn_color_hex,
    logo_path, logo_x_frac, logo_y_frac, logo_w_pt, logo_h_pt,
    sig_path, sig_x_frac, sig_y_frac,
    watermark, wm_opacity, bg_path, has_bg,
):
    W, H = PNG_W, PNG_H
    img  = Image.new("RGB", (W, H), (252, 248, 235))

    # Background
    if has_bg:
        try:
            bgimg = Image.open(bg_path).resize((W, H))
            img.paste(bgimg, (0, 0))
        except Exception:
            img = _draw_default_bg_png(img)
    else:
        img = _draw_default_bg_png(img)

    draw = ImageDraw.Draw(img)

    # ── helper: centered text using PNG coords ──────
    def _centered(text, y_top, font, fill):
        bb = draw.textbbox((0, 0), text, font=font)
        x  = (W - (bb[2] - bb[0])) // 2
        draw.text((x, y_top), text, fill=fill, font=font)

    # ── Logo ──────────────────────────────────────
    # logo_w_pt / logo_h_pt are the PDF-space sizes (points).
    # Scale to PNG: PNG is 2× the PDF resolution.
    if logo_path and os.path.exists(logo_path):
        try:
            lw_png = logo_w_pt * 2
            lh_png = logo_h_pt * 2
            # Centre of logo in PNG coords (Y flipped)
            cx, cy = png_xy(logo_x_frac, logo_y_frac)
            lx_png = cx - lw_png // 2
            ly_png = cy - lh_png // 2
            logo_img = Image.open(logo_path).convert("RGBA").resize((lw_png, lh_png))
            img.paste(logo_img, (lx_png, ly_png), logo_img)
            draw = ImageDraw.Draw(img)
        except Exception:
            pass

    # ── School Name ───────────────────────────────
    if school_name:
        try:
            sn_fill = hex_to_rgb_int(sn_color_hex)
        except Exception:
            sn_fill = (240, 192, 96)
        # Scale font size: PDF pts → PNG px (×2)
        sn_size_png = sn_size * 2
        sn_font     = _pil_font(sn_size_png, bold=True)
        cx, cy      = png_xy(sn_x_frac, sn_y_frac)
        # centre horizontally; top of text is cy - half line height
        bb   = draw.textbbox((0, 0), school_name, font=sn_font)
        tw   = bb[2] - bb[0]
        th   = bb[3] - bb[1]
        draw.text((cx - tw // 2, cy - th // 2), school_name, fill=sn_fill, font=sn_font)

    # ── Watermark ─────────────────────────────────
    if watermark:
        try:
            wm_layer = Image.new("RGBA", (W, H), (255, 255, 255, 0))
            wm_draw  = ImageDraw.Draw(wm_layer)
            wm_font  = _pil_font(150, bold=True)
            opacity  = int(wm_opacity * 255)
            bb  = wm_draw.textbbox((0, 0), watermark.upper(), font=wm_font)
            wx  = (W - (bb[2] - bb[0])) // 2
            wy  = (H - (bb[3] - bb[1])) // 2
            wm_draw.text((wx, wy), watermark.upper(), fill=(160, 160, 160, opacity), font=wm_font)
            img  = Image.alpha_composite(img.convert("RGBA"), wm_layer).convert("RGB")
            draw = ImageDraw.Draw(img)
        except Exception:
            pass

    # ── Fixed-layout text (mirrors PDF layout at 2× scale) ──

    # "CERTIFICATE OF ACHIEVEMENT"  — PDF: PAGE_H * 0.78
    _centered(
        "CERTIFICATE OF ACHIEVEMENT",
        int(H * (1 - 0.78)) - int(58 // 2),   # y_top in PNG space
        _pil_font(58, bold=True),
        (115, 82, 13),
    )

    # Decorative lines (PDF: 0.755)
    y_deco = int(H * (1 - 0.755))
    draw.line([(int(W * 0.15), y_deco), (int(W * 0.38), y_deco)], fill=(191, 153, 51), width=3)
    draw.line([(int(W * 0.62), y_deco), (int(W * 0.85), y_deco)], fill=(191, 153, 51), width=3)

    # "This is to certify that"  — PDF: 0.705
    _centered(
        "This is to certify that",
        int(H * (1 - 0.705)) - int(36 // 2),
        _pil_font(36),
        (77, 64, 26),
    )

    # Recipient Name  — PDF: 0.610
    _centered(
        data.get("name", ""),
        int(H * (1 - 0.610)) - int(96 // 2),
        _pil_font(96, bold=True),
        (13, 13, 51),
    )

    # Underline  — PDF: 0.585
    y_ul = int(H * (1 - 0.585))
    draw.line([(int(W * 0.18), y_ul), (int(W * 0.82), y_ul)], fill=(191, 153, 51), width=4)

    # "has successfully completed"  — PDF: 0.535
    _centered(
        "has successfully completed",
        int(H * (1 - 0.535)) - int(36 // 2),
        _pil_font(36),
        (64, 64, 64),
    )

    # Course  — PDF: 0.470
    if data.get("course"):
        _centered(
            data["course"].upper(),
            int(H * (1 - 0.470)) - int(52 // 2),
            _pil_font(52, bold=True),
            (20, 46, 122),
        )

    # Event  — PDF: 0.405
    if data.get("event"):
        _centered(
            f"\u2014  {data['event']}  \u2014",
            int(H * (1 - 0.405)) - int(34 // 2),
            _pil_font(34),
            (77, 77, 77),
        )

    # Separator line  — PDF: 0.365
    y_sep = int(H * (1 - 0.365))
    draw.line([(int(W * 0.15), y_sep), (int(W * 0.85), y_sep)], fill=(191, 153, 51), width=2)

    # Grade & Date  — PDF: 0.330
    row_y = int(H * (1 - 0.330)) - 15
    if data.get("grade"):
        draw.text(
            (int(W * 0.20), row_y),
            f"Grade :  {data['grade']}",
            fill=(31, 71, 148),
            font=_pil_font(30, bold=True),
        )
    if data.get("date"):
        date_text = f"Date :  {data['date']}"
        bb = draw.textbbox((0, 0), date_text, font=_pil_font(30))
        draw.text(
            (int(W * 0.80) - (bb[2] - bb[0]), row_y),
            date_text,
            fill=(64, 64, 64),
            font=_pil_font(30),
        )

    # ── Signature ─────────────────────────────────
    # sig_y_frac uses 0=bottom, 1=top convention
    sig_cx, sig_cy = png_xy(sig_x_frac, sig_y_frac)
    if sig_path and os.path.exists(sig_path):
        try:
            sig_img = Image.open(sig_path).convert("RGBA").resize((280, 108))
            img.paste(sig_img, (sig_cx - 140, sig_cy - 54), sig_img)
            draw = ImageDraw.Draw(img)
        except Exception:
            pass
    # Signature line (below centre)
    draw.line([(sig_cx - 160, sig_cy + 60), (sig_cx + 160, sig_cy + 60)],
              fill=(90, 90, 90), width=2)
    sig_label = "Authorized Signatory"
    bb = draw.textbbox((0, 0), sig_label, font=_pil_font(26))
    draw.text(
        (sig_cx - (bb[2] - bb[0]) // 2, sig_cy + 68),
        sig_label, fill=(51, 51, 51), font=_pil_font(26),
    )

    # Certificate ID footer
    draw.text((40, H - 80), f"Certificate ID: {cert_id}",
              fill=(180, 180, 180), font=_pil_font(20))

    # QR Code
    if os.path.exists(qr_path):
        try:
            qr_img = Image.open(qr_path).resize((148, 148))
            img.paste(qr_img, (W - 174, H - 168))
        except Exception:
            pass

    img.save(png_path, "PNG")


# ─────────────────────────────────────────────
# 7. BULK GENERATION
# ─────────────────────────────────────────────

def bulk_generate(template: dict, rows: list) -> tuple:
    results = []
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w") as zf:
        for row in rows:
            cert_id = gen_cert_id()
            try:
                pdf_path, png_path = generate_pdf(template, row, cert_id)
                db_save_cert({
                    "certificate_id": cert_id,
                    "student_name":   row.get("name", ""),
                    "course":         row.get("course", ""),
                    "event":          row.get("event", ""),
                    "issue_date":     row.get("date", ""),
                    "grade":          row.get("grade", ""),
                    "template_id":    template.get("id", 0),
                    "template_name":  template.get("name", ""),
                    "pdf_path":       pdf_path,
                    "png_path":       png_path,
                })
                with open(pdf_path, "rb") as f:
                    zf.writestr(f"{cert_id}_{row.get('name','')}.pdf", f.read())
                results.append({"name": row.get("name", ""), "cert_id": cert_id, "status": "✅ Success"})
            except Exception as e:
                results.append({"name": row.get("name", ""), "cert_id": cert_id, "status": f"❌ {e}"})
    zip_buf.seek(0)
    return results, zip_buf.read()


# ─────────────────────────────────────────────
# 8. PAGE SETUP & CSS
# ─────────────────────────────────────────────

st.set_page_config(
    page_title="CertifyPro — School Certificate Generator",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,700;1,400&family=DM+Sans:wght@300;400;500;600&display=swap');

:root {
    --gold:    #c9a84c;
    --gold-lt: #f0c060;
    --navy:    #0f1b3d;
    --navy-lt: #1a2d5a;
    --cream:   #fdf8f0;
    --text:    #1e1e2e;
    --muted:   #6b7280;
    --border:  #e5e0d5;
    --success: #16a34a;
    --danger:  #dc2626;
}

html, body, .stApp {
    font-family: 'DM Sans', sans-serif !important;
    background: #f4f1eb !important;
    color: var(--text) !important;
}

[data-testid="stSidebar"] {
    background: var(--navy) !important;
    border-right: 1px solid rgba(201,168,76,0.3) !important;
}
[data-testid="stSidebar"] * { color: #e8e0d0 !important; }

.sidebar-brand {
    text-align: center;
    padding: 24px 16px 20px;
    border-bottom: 1px solid rgba(201,168,76,0.25);
    margin-bottom: 16px;
}
.sidebar-brand .brand-icon { font-size: 2.8rem; }
.sidebar-brand .brand-title {
    font-family: 'Playfair Display', serif;
    font-size: 1.4rem;
    color: var(--gold-lt) !important;
    display: block;
    margin-top: 6px;
}
.sidebar-brand .brand-sub {
    font-size: 0.7rem;
    letter-spacing: 3px;
    text-transform: uppercase;
    color: rgba(255,255,255,0.4) !important;
    margin-top: 2px;
    display: block;
}

[data-testid="stSidebar"] .stRadio label {
    display: block;
    padding: 10px 16px;
    border-radius: 8px;
    margin: 2px 0;
    font-size: 0.875rem;
    cursor: pointer;
    transition: background 0.15s;
}
[data-testid="stSidebar"] .stRadio label:hover {
    background: rgba(201,168,76,0.15) !important;
}

.page-header {
    background: linear-gradient(135deg, var(--navy) 0%, var(--navy-lt) 100%);
    border-radius: 16px;
    padding: 28px 32px;
    margin-bottom: 28px;
    border: 1px solid rgba(201,168,76,0.3);
    box-shadow: 0 4px 24px rgba(15,27,61,0.12);
}
.page-header h1 {
    font-family: 'Playfair Display', serif;
    font-size: 1.9rem;
    color: var(--gold-lt) !important;
    margin: 0 0 4px;
}
.page-header p {
    color: rgba(255,255,255,0.55) !important;
    font-size: 0.85rem;
    margin: 0;
    letter-spacing: 0.5px;
}

.stat-card {
    background: white;
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 22px 24px;
    display: flex;
    align-items: center;
    gap: 16px;
    box-shadow: 0 2px 12px rgba(0,0,0,0.04);
    transition: box-shadow 0.2s;
}
.stat-card:hover { box-shadow: 0 6px 20px rgba(0,0,0,0.08); }
.stat-icon {
    width: 56px; height: 56px;
    border-radius: 12px;
    display: flex; align-items: center; justify-content: center;
    font-size: 1.6rem; flex-shrink: 0;
}
.stat-icon.gold  { background: rgba(201,168,76,0.12); }
.stat-icon.navy  { background: rgba(15,27,61,0.08); }
.stat-icon.green { background: rgba(22,163,74,0.1); }
.stat-val  { font-size: 2rem; font-weight: 700; color: var(--navy); line-height:1; }
.stat-lbl  { font-size: 0.78rem; color: var(--muted); margin-top: 2px; text-transform: uppercase; letter-spacing: 0.8px; }

.card {
    background: white;
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 24px;
    box-shadow: 0 2px 12px rgba(0,0,0,0.04);
    margin-bottom: 20px;
}
.card-title {
    font-family: 'Playfair Display', serif;
    font-size: 1.1rem;
    color: var(--navy);
    margin: 0 0 16px;
    padding-bottom: 10px;
    border-bottom: 2px solid var(--gold);
    display: inline-block;
}

.cert-row {
    display: flex; align-items: center; justify-content: space-between;
    padding: 12px 0;
    border-bottom: 1px solid var(--border);
    font-size: 0.85rem;
}
.cert-row:last-child { border-bottom: none; }
.cert-id   { font-family: monospace; color: var(--navy); font-weight: 600; }
.cert-name { color: var(--text); font-weight: 500; }
.cert-date { color: var(--muted); font-size: 0.78rem; }

.badge {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 20px;
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.5px;
}
.badge-gold  { background: rgba(201,168,76,0.15); color: #92700e; }
.badge-navy  { background: rgba(15,27,61,0.08);   color: var(--navy); }
.badge-green { background: rgba(22,163,74,0.1);   color: #15803d; }
.badge-red   { background: rgba(220,38,38,0.1);   color: #b91c1c; }

.stButton > button {
    background: linear-gradient(135deg, var(--navy), var(--navy-lt)) !important;
    color: white !important;
    border: none !important;
    border-radius: 8px !important;
    font-family: 'DM Sans', sans-serif !important;
    font-weight: 500 !important;
    padding: 10px 20px !important;
    transition: all 0.2s !important;
}
.stButton > button:hover {
    background: linear-gradient(135deg, #182f5c, #243f6e) !important;
    box-shadow: 0 4px 12px rgba(15,27,61,0.3) !important;
    transform: translateY(-1px) !important;
}
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, var(--gold), #a8822a) !important;
    color: var(--navy) !important;
}

.stTextInput > div > div > input,
.stSelectbox > div > div,
.stTextArea > div > div > textarea,
.stNumberInput > div > div > input {
    border-radius: 8px !important;
    border: 1.5px solid var(--border) !important;
    font-family: 'DM Sans', sans-serif !important;
    transition: border-color 0.2s !important;
}
.stTextInput > div > div > input:focus,
.stTextArea > div > div > textarea:focus {
    border-color: var(--gold) !important;
    box-shadow: 0 0 0 3px rgba(201,168,76,0.15) !important;
}

.stTabs [data-baseweb="tab-list"] {
    gap: 4px;
    background: #ede9e0;
    padding: 4px;
    border-radius: 10px;
}
.stTabs [data-baseweb="tab"] {
    border-radius: 8px !important;
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.85rem !important;
    font-weight: 500 !important;
    padding: 8px 18px !important;
}
.stTabs [aria-selected="true"] {
    background: var(--navy) !important;
    color: var(--gold-lt) !important;
}

[data-testid="stFileUploader"] {
    border: 2px dashed var(--border) !important;
    border-radius: 12px !important;
    background: #faf8f4 !important;
}

.streamlit-expanderHeader {
    font-family: 'DM Sans', sans-serif !important;
    font-weight: 500 !important;
    border-radius: 8px !important;
    background: #f9f6f0 !important;
}

.stAlert { border-radius: 10px !important; }

.login-wrap {
    min-height: 100vh;
    display: flex; align-items: center; justify-content: center;
    background: linear-gradient(160deg, #0a122b 0%, #1a2d5a 50%, #0f1b3d 100%);
}
.login-box {
    width: 420px;
    background: rgba(255,255,255,0.05);
    backdrop-filter: blur(24px);
    border: 1px solid rgba(201,168,76,0.25);
    border-radius: 20px;
    padding: 48px 44px 40px;
    box-shadow: 0 30px 80px rgba(0,0,0,0.5);
}
.login-logo  { text-align:center; font-size: 3rem; margin-bottom:12px; }
.login-title {
    font-family: 'Playfair Display', serif;
    font-size: 1.9rem; color: var(--gold-lt);
    text-align: center; margin-bottom: 4px;
}
.login-sub {
    text-align: center; font-size: 0.72rem;
    letter-spacing: 3px; text-transform: uppercase;
    color: rgba(255,255,255,0.35); margin-bottom: 36px;
}

.gold-divider {
    border: none; height: 2px;
    background: linear-gradient(90deg, transparent, var(--gold), transparent);
    margin: 20px 0;
}

.quick-actions .stButton > button {
    background: white !important;
    color: var(--navy) !important;
    border: 1.5px solid var(--border) !important;
    border-radius: 12px !important;
    padding: 14px 16px !important;
    font-size: 0.82rem !important;
    width: 100% !important;
    transition: all 0.2s !important;
}
.quick-actions .stButton > button:hover {
    border-color: var(--gold) !important;
    box-shadow: 0 4px 12px rgba(0,0,0,0.08) !important;
    transform: translateY(-2px) !important;
}

::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: #f4f1eb; }
::-webkit-scrollbar-thumb { background: #c9a84c; border-radius: 4px; }

#MainMenu { visibility: hidden; }
footer    { visibility: hidden; }
header    { visibility: hidden; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# 9. SESSION STATE INIT
# ─────────────────────────────────────────────

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "admin_username" not in st.session_state:
    st.session_state.admin_username = ""
if "page" not in st.session_state:
    st.session_state.page = "Dashboard"


# ─────────────────────────────────────────────
# 10. LOGIN PAGE
# ─────────────────────────────────────────────

def show_login():
    st.markdown("""
    <style>
    .stApp { background: linear-gradient(160deg,#0a122b 0%,#1a2d5a 50%,#0f1b3d 100%) !important; }
    </style>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        st.markdown('<div class="login-logo">🎓</div>', unsafe_allow_html=True)
        st.markdown('<div class="login-title">CertifyPro</div>', unsafe_allow_html=True)
        st.markdown('<div class="login-sub">School Certificate Generator</div>', unsafe_allow_html=True)

        with st.form("login_form"):
            username  = st.text_input("Username", placeholder="admin")
            password  = st.text_input("Password", type="password", placeholder="••••••••")
            submitted = st.form_submit_button("Sign In", use_container_width=True)

            if submitted:
                if db_check_login(username.strip(), password):
                    st.session_state.authenticated    = True
                    st.session_state.admin_username   = username.strip()
                    st.rerun()
                else:
                    st.error("Invalid credentials. Try admin / admin123")

        st.markdown(
            '<p style="text-align:center;color:rgba(255,255,255,0.25);'
            'font-size:0.72rem;margin-top:16px;">Default: admin / admin123</p>',
            unsafe_allow_html=True,
        )


# ─────────────────────────────────────────────
# 11. SIDEBAR
# ─────────────────────────────────────────────

def show_sidebar():
    with st.sidebar:
        st.markdown("""
        <div class="sidebar-brand">
            <div class="brand-icon">🎓</div>
            <span class="brand-title">CertifyPro</span>
            <span class="brand-sub">Admin Panel</span>
        </div>
        """, unsafe_allow_html=True)

        pages = [
            "📊 Dashboard",
            "🎨 Template Builder",
            "📄 Single Certificate",
            "📦 Bulk Generation",
            "🔍 QR Verification",
            "📜 Certificate History",
            "⚙️ Settings",
        ]

        page = st.radio("Navigation", pages, label_visibility="collapsed")
        st.session_state.page = page.split(" ", 1)[1]

        st.markdown(
            "<hr style='border-color:rgba(201,168,76,0.2);margin:16px 0;'>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div style="padding:0 8px;font-size:0.78rem;color:rgba(255,255,255,0.4);">'
            f'Logged in as<br>'
            f'<span style="color:#f0c060;font-weight:600;">{st.session_state.admin_username}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🚪 Logout", use_container_width=True):
            st.session_state.authenticated  = False
            st.session_state.admin_username = ""
            st.rerun()


# ─────────────────────────────────────────────
# 12. PAGE: DASHBOARD
# ─────────────────────────────────────────────

def page_dashboard():
    stats = db_stats()

    st.markdown("""
    <div class="page-header">
        <h1>📊 Dashboard</h1>
        <p>Welcome back — here's your certificate management overview</p>
    </div>
    """, unsafe_allow_html=True)

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-icon gold">🏅</div>
            <div><div class="stat-val">{stats['total']}</div>
                 <div class="stat-lbl">Total Certificates</div></div>
        </div>""", unsafe_allow_html=True)
    with c2:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-icon navy">🎨</div>
            <div><div class="stat-val">{stats['templates']}</div>
                 <div class="stat-lbl">Templates Saved</div></div>
        </div>""", unsafe_allow_html=True)
    with c3:
        today_count = sum(
            1 for r in stats["recent"]
            if r.get("created_at", "")[:10] == datetime.now().strftime("%Y-%m-%d")
        )
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-icon green">✅</div>
            <div><div class="stat-val">{today_count}</div>
                 <div class="stat-lbl">Generated Today</div></div>
        </div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    col_r, col_q = st.columns([3, 2])

    with col_r:
        st.markdown('<div class="card"><div class="card-title">Recent Certificates</div>', unsafe_allow_html=True)
        if not stats["recent"]:
            st.info("No certificates yet.")
        else:
            for r in stats["recent"]:
                st.markdown(f"""
                <div class="cert-row">
                    <div>
                        <div class="cert-name">{r['student_name']}</div>
                        <div class="cert-id">{r['certificate_id']}</div>
                    </div>
                    <div style="text-align:right">
                        <div class="badge badge-gold">{r.get('course','—')}</div>
                        <div class="cert-date" style="margin-top:4px">{r.get('created_at','')[:10]}</div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with col_q:
        st.markdown('<div class="card"><div class="card-title">Quick Actions</div>', unsafe_allow_html=True)
        st.markdown('<div class="quick-actions">', unsafe_allow_html=True)
        if st.button("➕  New Certificate", use_container_width=True):
            st.session_state.page = "Single Certificate"
            st.rerun()
        if st.button("📦  Bulk Generate", use_container_width=True):
            st.session_state.page = "Bulk Generation"
            st.rerun()
        if st.button("🎨  Create Template", use_container_width=True):
            st.session_state.page = "Template Builder"
            st.rerun()
        if st.button("🔍  Verify Certificate", use_container_width=True):
            st.session_state.page = "QR Verification"
            st.rerun()
        st.markdown("</div></div>", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# 13. PAGE: TEMPLATE BUILDER
# ─────────────────────────────────────────────

def page_template_builder():
    st.markdown("""
    <div class="page-header">
        <h1>🎨 Template Builder</h1>
        <p>Design and save reusable certificate templates</p>
    </div>
    """, unsafe_allow_html=True)

    tab_new, tab_manage = st.tabs(["➕ Create / Edit Template", "🗂️ Manage Templates"])

    with tab_new:
        templates = db_get_templates()
        mode      = st.radio("Mode", ["Create New", "Edit Existing"], horizontal=True)
        existing  = None

        if mode == "Edit Existing":
            if not templates:
                st.info("No templates found. Create one first.")
                return
            sel      = st.selectbox("Select template", [t["name"] for t in templates])
            existing = next((t for t in templates if t["name"] == sel), None)

        _template_form(existing)

    with tab_manage:
        templates = db_get_templates()
        if not templates:
            st.info("No templates saved yet.")
        else:
            for t in templates:
                with st.expander(f"🎨 {t['name']}  —  created {t['created_at'][:10]}"):
                    c1, c2 = st.columns([4, 1])
                    with c1:
                        st.write(f"**School:** {t.get('school_name','—')}")
                        st.write(f"**Watermark:** {t.get('watermark','—') or '—'}")
                        st.write(f"**Background:** {'Set' if t.get('bg_path') else 'Default'}")
                        st.write(f"**Logo:** {'Set' if t.get('logo_path') else 'None'}")
                        st.write(f"**Signature:** {'Set' if t.get('sig_path') else 'None'}")
                    with c2:
                        if st.button("🗑️ Delete", key=f"del_t_{t['id']}"):
                            db_delete_template(t["id"])
                            st.success("Deleted.")
                            st.rerun()


def _template_form(existing=None):
    px = "e_" if existing else "n_"

    def _v(key, default):
        return existing.get(key, default) if existing else default

    with st.form(f"{px}tpl_form", clear_on_submit=False):
        st.markdown("#### 📋 Basic Info")
        c1, c2 = st.columns(2)
        with c1:
            name        = st.text_input("Template Name *", value=_v("name", ""))
            school_name = st.text_input("School / Institution Name",
                                        value=_v("school_name", "Excellence Academy"))
        with c2:
            watermark         = st.text_input("Watermark Text (optional)", value=_v("watermark", ""))
            watermark_opacity = st.slider("Watermark Opacity", 0.02, 0.4,
                                          float(_v("watermark_opacity", 0.08)), 0.01)

        st.markdown('<hr class="gold-divider">', unsafe_allow_html=True)
        st.markdown("#### 🖼️ Upload Images")
        c1, c2, c3 = st.columns(3)
        with c1:
            bg_file = st.file_uploader("Background Image",
                                       type=["png", "jpg", "jpeg"], key=f"{px}bg")
            if existing and existing.get("bg_path"):
                st.caption(f"Current: {os.path.basename(existing['bg_path'])}")
        with c2:
            logo_file = st.file_uploader("School Logo / Emblem",
                                         type=["png", "jpg", "jpeg"], key=f"{px}logo")
            if existing and existing.get("logo_path"):
                st.caption(f"Current: {os.path.basename(existing['logo_path'])}")
        with c3:
            sig_file = st.file_uploader("Signature Image",
                                        type=["png", "jpg", "jpeg"], key=f"{px}sig")
            if existing and existing.get("sig_path"):
                st.caption(f"Current: {os.path.basename(existing['sig_path'])}")

        st.markdown('<hr class="gold-divider">', unsafe_allow_html=True)
        st.markdown("#### 📌 School Name Style & Position")
        st.caption("Y: 0 = bottom of page, 1 = top of page")
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            sn_x    = st.slider("X (0=left, 1=right)", 0.0, 1.0,
                                 float(_v("school_name_x", 0.5)), 0.01, key=f"{px}sn_x")
        with c2:
            sn_y    = st.slider("Y (0=bottom, 1=top)", 0.0, 1.0,
                                 float(_v("school_name_y", 0.88)), 0.01, key=f"{px}sn_y")
        with c3:
            sn_size = st.number_input("Font Size (PDF pts)", 14, 80,
                                      int(_v("school_name_size", 36)), key=f"{px}sn_sz")
        with c4:
            sn_color = st.color_picker("Color", _v("school_name_color", "#f0c060"),
                                        key=f"{px}sn_col")

        st.markdown('<hr class="gold-divider">', unsafe_allow_html=True)
        st.markdown("#### 🖼️ Logo Position & Size")
        st.caption("Y: 0 = bottom of page, 1 = top of page")
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            logo_x = st.slider("Logo X", 0.0, 1.0, float(_v("logo_x", 0.5)), 0.01, key=f"{px}lx")
        with c2:
            logo_y = st.slider("Logo Y", 0.0, 1.0, float(_v("logo_y", 0.85)), 0.01, key=f"{px}ly")
        with c3:
            logo_w = st.number_input("Logo Width (PDF pts)", 20, 300,
                                     int(_v("logo_w", 100)), key=f"{px}lw")
        with c4:
            logo_h = st.number_input("Logo Height (PDF pts)", 20, 300,
                                     int(_v("logo_h", 100)), key=f"{px}lh")

        st.markdown('<hr class="gold-divider">', unsafe_allow_html=True)
        st.markdown("#### ✍️ Signature Position")
        st.caption("Y: 0 = bottom of page, 1 = top of page")
        c1, c2 = st.columns(2)
        with c1:
            sig_x = st.slider("Signature X", 0.0, 1.0, float(_v("sig_x", 0.5)), 0.01, key=f"{px}sx")
        with c2:
            sig_y = st.slider("Signature Y", 0.0, 1.0, float(_v("sig_y", 0.22)), 0.01, key=f"{px}sy")

        st.markdown("""
        <div style="background:#f0ece0;border-left:4px solid #c9a84c;padding:12px 16px;
                    border-radius:0 8px 8px 0;font-size:0.82rem;color:#555;margin:8px 0 16px">
            <strong>Position convention:</strong>
            X and Y are fractions of the page (0–1).
            Y = 0 is the <em>bottom</em> of the page; Y = 1 is the <em>top</em>.
            Both the PDF and PNG outputs use this same convention so the generated
            certificate will match this preview exactly.
        </div>
        """, unsafe_allow_html=True)

        save_btn = st.form_submit_button("💾 Save Template", use_container_width=True)

        if save_btn:
            if not name.strip():
                st.error("Template name is required.")
                return

            data = {
                "name":             name.strip(),
                "school_name":      school_name,
                "school_name_x":    sn_x,
                "school_name_y":    sn_y,
                "school_name_size": sn_size,
                "school_name_color": sn_color,
                "logo_x":           logo_x,
                "logo_y":           logo_y,
                "logo_w":           logo_w,
                "logo_h":           logo_h,
                "sig_x":            sig_x,
                "sig_y":            sig_y,
                "watermark":        watermark,
                "watermark_opacity": watermark_opacity,
            }

            if bg_file:
                data["bg_path"] = save_uploaded(bg_file, "backgrounds")
            elif existing:
                data["bg_path"] = existing.get("bg_path", "")

            if logo_file:
                data["logo_path"] = save_uploaded(logo_file, "logos")
            elif existing:
                data["logo_path"] = existing.get("logo_path", "")

            if sig_file:
                data["sig_path"] = save_uploaded(sig_file, "signatures")
            elif existing:
                data["sig_path"] = existing.get("sig_path", "")

            if existing:
                c_db = _conn()
                sets = ", ".join([f"{k}=?" for k in data])
                c_db.execute(f"UPDATE templates SET {sets} WHERE id=?",
                             list(data.values()) + [existing["id"]])
                c_db.commit()
                c_db.close()
                st.success(f"✅ Template '{name}' updated!")
            else:
                db_save_template(data)
                st.success(f"✅ Template '{name}' created!")
            st.rerun()


# ─────────────────────────────────────────────
# 14. PAGE: SINGLE CERTIFICATE
# ─────────────────────────────────────────────

def page_single_cert():
    st.markdown("""
    <div class="page-header">
        <h1>📄 Generate Single Certificate</h1>
        <p>Fill in recipient details and generate a professional certificate</p>
    </div>
    """, unsafe_allow_html=True)

    templates = db_get_templates()
    if not templates:
        st.warning("⚠️ No templates found. Please create a template first.")
        if st.button("Go to Template Builder"):
            st.session_state.page = "Template Builder"
            st.rerun()
        return

    col_form, col_prev = st.columns([2, 3])

    with col_form:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="card-title">Recipient Details</div>', unsafe_allow_html=True)

        tpl_names = [t["name"] for t in templates]
        sel_tpl   = st.selectbox("Select Template", tpl_names)
        template  = next(t for t in templates if t["name"] == sel_tpl)

        with st.form("single_cert_form"):
            name       = st.text_input("Student Name *", placeholder="Jane Doe")
            course     = st.text_input("Course / Subject", placeholder="Data Science")
            event      = st.text_input("Event / Program", placeholder="Annual Science Fair")
            issue_date = st.date_input("Issue Date", value=date.today())
            grade      = st.text_input("Grade (optional)", placeholder="A+")

            c1, c2 = st.columns(2)
            with c1:
                preview_btn = st.form_submit_button("👁️ Preview", use_container_width=True)
            with c2:
                gen_btn = st.form_submit_button("🎓 Generate & Download", use_container_width=True)

            if preview_btn or gen_btn:
                if not name.strip():
                    st.error("Student name is required.")
                else:
                    if event.strip() and db_check_duplicate(name.strip(), event.strip()):
                        st.warning(
                            f"⚠️ A certificate already exists for '{name}' in event '{event}'."
                        )

                    cert_id  = gen_cert_id()
                    row_data = {
                        "name":   name.strip(),
                        "course": course.strip(),
                        "event":  event.strip(),
                        "date":   str(issue_date),
                        "grade":  grade.strip(),
                    }

                    with st.spinner("Generating certificate…"):
                        pdf_path, png_path = generate_pdf(template, row_data, cert_id)

                    if gen_btn:
                        db_save_cert({
                            "certificate_id": cert_id,
                            "student_name":   name.strip(),
                            "course":         course.strip(),
                            "event":          event.strip(),
                            "issue_date":     str(issue_date),
                            "grade":          grade.strip(),
                            "template_id":    template["id"],
                            "template_name":  template["name"],
                            "pdf_path":       pdf_path,
                            "png_path":       png_path,
                        })

                    st.session_state["last_pdf"]     = pdf_path
                    st.session_state["last_png"]     = png_path
                    st.session_state["last_cert_id"] = cert_id
                    if gen_btn:
                        st.success(f"✅ Certificate generated! ID: **{cert_id}**")

        st.markdown("</div>", unsafe_allow_html=True)

        if "last_pdf" in st.session_state:
            pdf_path = st.session_state["last_pdf"]
            cert_id  = st.session_state["last_cert_id"]
            if os.path.exists(pdf_path):
                with open(pdf_path, "rb") as f:
                    st.download_button(
                        "⬇️ Download PDF",
                        data=f.read(),
                        file_name=f"{cert_id}.pdf",
                        mime="application/pdf",
                        use_container_width=True,
                    )

    with col_prev:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="card-title">Preview</div>', unsafe_allow_html=True)
        if "last_png" in st.session_state and os.path.exists(st.session_state["last_png"]):
            st.image(st.session_state["last_png"], use_container_width=True)
            st.markdown(
                f'<div style="text-align:center;margin-top:8px">'
                f'<span class="badge badge-gold">ID: {st.session_state["last_cert_id"]}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown("""
            <div style="height:380px;display:flex;align-items:center;justify-content:center;
                        background:#f9f6f0;border-radius:10px;border:2px dashed #e5e0d5;">
                <div style="text-align:center;color:#999">
                    <div style="font-size:3rem">🎓</div>
                    <div style="margin-top:8px;font-size:0.85rem">Preview appears here</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# 15. PAGE: BULK GENERATION
# ─────────────────────────────────────────────

def page_bulk():
    st.markdown("""
    <div class="page-header">
        <h1>📦 Bulk Certificate Generation</h1>
        <p>Upload a CSV/Excel file to generate certificates for multiple recipients at once</p>
    </div>
    """, unsafe_allow_html=True)

    templates = db_get_templates()
    if not templates:
        st.warning("⚠️ Create a template first.")
        return

    col1, col2 = st.columns([2, 3])

    with col1:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="card-title">Upload & Configure</div>', unsafe_allow_html=True)

        tpl_names = [t["name"] for t in templates]
        sel_tpl   = st.selectbox("Select Template", tpl_names, key="bulk_tpl")
        template  = next(t for t in templates if t["name"] == sel_tpl)

        uploaded = st.file_uploader("Upload CSV or Excel", type=["csv", "xlsx", "xls"])

        st.markdown("""
        <div style="background:#f0ece0;border-left:4px solid #c9a84c;
                    padding:10px 14px;border-radius:0 8px 8px 0;font-size:0.78rem;color:#666;margin:10px 0">
            <strong>Required columns:</strong> <code>name</code><br>
            <strong>Optional:</strong> <code>course</code>, <code>event</code>,
            <code>date</code>, <code>grade</code>
        </div>
        """, unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with col2:
        if uploaded:
            try:
                if uploaded.name.endswith(".csv"):
                    df = pd.read_csv(uploaded)
                else:
                    df = pd.read_excel(uploaded)
                df.columns = [str(c).strip().lower() for c in df.columns]

                if "name" not in df.columns:
                    st.error("File must have a 'name' column.")
                    return

                st.markdown('<div class="card">', unsafe_allow_html=True)
                st.markdown(f'<div class="card-title">Preview — {len(df)} rows</div>',
                            unsafe_allow_html=True)
                st.dataframe(df.head(10), use_container_width=True)

                if st.button("🚀 Generate All Certificates", use_container_width=True):
                    rows = df.fillna("").to_dict("records")
                    with st.spinner(f"Generating {len(rows)} certificates…"):
                        results, zip_bytes = bulk_generate(template, rows)

                    result_df = pd.DataFrame(results)
                    st.dataframe(result_df, use_container_width=True)

                    ok  = sum(1 for r in results if "Success" in r["status"])
                    err = len(results) - ok
                    st.markdown(
                        f'<div style="display:flex;gap:12px;margin:12px 0">'
                        f'<span class="badge badge-green">✅ {ok} generated</span>'
                        f'<span class="badge badge-red">❌ {err} failed</span>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                    st.download_button(
                        "⬇️ Download All as ZIP",
                        data=zip_bytes,
                        file_name=f"certificates_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
                        mime="application/zip",
                        use_container_width=True,
                    )
                st.markdown("</div>", unsafe_allow_html=True)

            except Exception as e:
                st.error(f"Error reading file: {e}")
        else:
            st.markdown("""
            <div style="height:300px;display:flex;align-items:center;justify-content:center;
                        background:white;border-radius:14px;border:2px dashed #e5e0d5;">
                <div style="text-align:center;color:#aaa">
                    <div style="font-size:3rem">📂</div>
                    <div style="margin-top:8px;font-size:0.85rem">
                        Upload a CSV or Excel file to get started
                    </div>
                </div>
            </div>""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# 16. PAGE: QR VERIFICATION
# ─────────────────────────────────────────────

def page_verification():
    st.markdown("""
    <div class="page-header">
        <h1>🔍 Certificate Verification</h1>
        <p>Verify the authenticity of any certificate using its ID or QR code</p>
    </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns([1, 2])

    with col1:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="card-title">Enter Certificate ID</div>', unsafe_allow_html=True)
        cert_id_input = st.text_input("Certificate ID", placeholder="CERT-XXXXXXXXXX",
                                      label_visibility="collapsed")
        verify_btn = st.button("🔎 Verify Certificate", use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with col2:
        if verify_btn and cert_id_input.strip():
            cid  = cert_id_input.strip().upper()
            cert = db_get_cert_by_id(cid)

            if cert:
                st.markdown(f"""
                <div class="card" style="border-left:5px solid #16a34a">
                    <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px">
                        <div style="font-size:2.5rem">✅</div>
                        <div>
                            <div style="font-size:1.2rem;font-weight:700;color:#15803d">
                                Certificate Valid
                            </div>
                            <div class="badge badge-green">VERIFIED</div>
                        </div>
                    </div>
                    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;font-size:0.88rem">
                        <div><span style="color:#888">Recipient</span><br>
                            <strong>{cert['student_name']}</strong></div>
                        <div><span style="color:#888">Certificate ID</span><br>
                            <code style="background:#f0f0f0;padding:2px 6px;border-radius:4px">
                            {cert['certificate_id']}</code></div>
                        <div><span style="color:#888">Course</span><br>
                            <strong>{cert.get('course','—')}</strong></div>
                        <div><span style="color:#888">Issue Date</span><br>
                            <strong>{cert.get('issue_date','—')}</strong></div>
                        <div><span style="color:#888">Event</span><br>
                            <strong>{cert.get('event','—')}</strong></div>
                        <div><span style="color:#888">Template</span><br>
                            <strong>{cert.get('template_name','—')}</strong></div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                qr_path = os.path.join(GEN_DIR, "qr", f"{cid}.png")
                if os.path.exists(qr_path):
                    st.image(qr_path, caption="QR Code", width=160)

            else:
                st.markdown(f"""
                <div class="card" style="border-left:5px solid #dc2626">
                    <div style="display:flex;align-items:center;gap:12px">
                        <div style="font-size:2.5rem">❌</div>
                        <div>
                            <div style="font-size:1.2rem;font-weight:700;color:#b91c1c">
                                Certificate Not Found
                            </div>
                            <div style="color:#888;font-size:0.85rem;margin-top:4px">
                                No record found for ID: <code>{cid}</code>
                            </div>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        elif not verify_btn:
            st.markdown("""
            <div style="height:240px;display:flex;align-items:center;justify-content:center;
                        background:white;border-radius:14px;border:2px dashed #e5e0d5">
                <div style="text-align:center;color:#aaa">
                    <div style="font-size:3rem">🔍</div>
                    <div style="margin-top:8px;font-size:0.85rem">
                        Enter a certificate ID and click Verify
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)


# ─────────────────────────────────────────────
# 17. PAGE: CERTIFICATE HISTORY
# ─────────────────────────────────────────────

def page_history():
    st.markdown("""
    <div class="page-header">
        <h1>📜 Certificate History</h1>
        <p>Browse, search and download all generated certificates</p>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        name_q = st.text_input("🔎 Search by Name", placeholder="Type a name…")
    with col2:
        id_q   = st.text_input("🔎 Search by Certificate ID", placeholder="CERT-…")
    with col3:
        st.markdown("<br>", unsafe_allow_html=True)
        search_btn = st.button("Search", use_container_width=True)

    certs = db_get_certs(name_q if search_btn else "", id_q if search_btn else "")

    st.markdown(f"""
    <div style="margin:12px 0 8px">
        <span class="badge badge-navy">{len(certs)} records found</span>
    </div>
    """, unsafe_allow_html=True)

    if not certs:
        st.info("No certificates found.")
        return

    table_data = []
    for cert in certs:
        table_data.append({
            "Certificate ID": cert["certificate_id"],
            "Recipient":      cert["student_name"],
            "Course":         cert.get("course", ""),
            "Event":          cert.get("event", ""),
            "Grade":          cert.get("grade", ""),
            "Issue Date":     cert.get("issue_date", ""),
            "Template":       cert.get("template_name", ""),
            "Created":        cert.get("created_at", "")[:10],
        })

    df_display = pd.DataFrame(table_data)
    st.dataframe(df_display, use_container_width=True, height=400)

    st.markdown("### Download Individual Certificates")
    for cert in certs[:20]:
        with st.expander(f"📄 {cert['student_name']}  ·  {cert['certificate_id']}"):
            c1, c2, c3 = st.columns([2, 1, 1])
            with c1:
                st.write(f"**Course:** {cert.get('course','—')}")
                st.write(f"**Event:** {cert.get('event','—')}")
                st.write(f"**Date:** {cert.get('issue_date','—')}")
            with c2:
                pdf_p = cert.get("pdf_path", "")
                if pdf_p and os.path.exists(pdf_p):
                    with open(pdf_p, "rb") as f:
                        st.download_button(
                            "⬇️ PDF",
                            data=f.read(),
                            file_name=f"{cert['certificate_id']}.pdf",
                            mime="application/pdf",
                            key=f"dl_pdf_{cert['certificate_id']}",
                        )
            with c3:
                png_p = cert.get("png_path", "")
                if png_p and os.path.exists(png_p):
                    with open(png_p, "rb") as f:
                        st.download_button(
                            "⬇️ PNG",
                            data=f.read(),
                            file_name=f"{cert['certificate_id']}.png",
                            mime="image/png",
                            key=f"dl_png_{cert['certificate_id']}",
                        )


# ─────────────────────────────────────────────
# 18. PAGE: SETTINGS
# ─────────────────────────────────────────────

def page_settings():
    st.markdown("""
    <div class="page-header">
        <h1>⚙️ Settings</h1>
        <p>Manage your admin account and application preferences</p>
    </div>
    """, unsafe_allow_html=True)

    tab1, tab2 = st.tabs(["👤 Admin Profile", "🔒 Change Password"])

    with tab1:
        c_db  = _conn()
        admin = c_db.execute(
            "SELECT * FROM admins WHERE username=?",
            (st.session_state.admin_username,),
        ).fetchone()
        c_db.close()
        admin = dict(admin) if admin else {}

        with st.form("profile_form"):
            st.markdown('<div class="card-title">Profile Information</div>', unsafe_allow_html=True)
            full_name = st.text_input("Full Name",     value=admin.get("full_name", ""))
            email     = st.text_input("Email Address", value=admin.get("email", ""))
            st.text_input("Username", value=admin.get("username", ""), disabled=True)
            if st.form_submit_button("💾 Save Profile", use_container_width=True):
                c_db = _conn()
                c_db.execute(
                    "UPDATE admins SET full_name=?, email=? WHERE username=?",
                    (full_name, email, st.session_state.admin_username),
                )
                c_db.commit()
                c_db.close()
                st.success("✅ Profile updated.")

    with tab2:
        with st.form("pw_form"):
            st.markdown('<div class="card-title">Change Password</div>', unsafe_allow_html=True)
            old_pw  = st.text_input("Current Password",    type="password")
            new_pw  = st.text_input("New Password",        type="password")
            new_pw2 = st.text_input("Confirm New Password", type="password")

            if st.form_submit_button("🔒 Change Password", use_container_width=True):
                if not old_pw or not new_pw:
                    st.error("All fields are required.")
                elif new_pw != new_pw2:
                    st.error("New passwords do not match.")
                elif len(new_pw) < 6:
                    st.error("Password must be at least 6 characters.")
                elif not db_check_login(st.session_state.admin_username, old_pw):
                    st.error("Current password is incorrect.")
                else:
                    db_change_password(st.session_state.admin_username, new_pw)
                    st.success("✅ Password changed successfully.")


# ─────────────────────────────────────────────
# 19. MAIN ROUTER
# ─────────────────────────────────────────────

def main():
    init_db()

    if not st.session_state.authenticated:
        show_login()
        return

    show_sidebar()

    page = st.session_state.page

    if page == "Dashboard":
        page_dashboard()
    elif page == "Template Builder":
        page_template_builder()
    elif page == "Single Certificate":
        page_single_cert()
    elif page == "Bulk Generation":
        page_bulk()
    elif page == "QR Verification":
        page_verification()
    elif page == "Certificate History":
        page_history()
    elif page == "Settings":
        page_settings()
    else:
        page_dashboard()


if __name__ == "__main__":
    main()
