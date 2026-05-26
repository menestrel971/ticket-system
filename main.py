import os
import json
import httpx
import sqlite3
from datetime import datetime
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager

# ── Config from env ──────────────────────────────────────────────────────────
GEMINI_API_KEY  = os.getenv("GEMINI_API_KEY", "")
TELEGRAM_TOKEN  = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID= os.getenv("TELEGRAM_CHAT_ID", "")
DB_PATH           = os.getenv("DB_PATH", "tickets.db")

# ── DB Setup ─────────────────────────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            email       TEXT NOT NULL,
            phone       TEXT,
            subject     TEXT NOT NULL,
            message     TEXT NOT NULL,
            category    TEXT,
            priority    TEXT,
            reasoning   TEXT,
            summary     TEXT,
            status      TEXT DEFAULT 'new',
            created_at  TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="Ticket System MVP", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# ── AI Classification ─────────────────────────────────────────────────────────
async def classify_ticket(subject: str, message: str) -> dict:
    """Call Gemini to classify ticket category, priority and generate summary."""
    prompt = f"""Ты — AI-ассистент системы обработки заявок. Проанализируй заявку и верни ТОЛЬКО JSON.

Заявка:
Тема: {subject}
Сообщение: {message}

Определи:
1. category — одна из: ["техническая проблема", "вопрос по оплате", "консультация", "жалоба", "запрос функции", "другое"]
2. priority — одна из: ["критический", "высокий", "средний", "низкий"]
3. reasoning — 1-2 предложения, почему выбрана именно эта категория и приоритет
4. summary — краткое резюме обращения в 1 предложении

Правила приоритета:
- критический: система не работает, потеря данных, срочная помощь
- высокий: существенная проблема, мешает работе
- средний: неудобство, вопрос, улучшение
- низкий: общий вопрос, предложение, не срочно

Верни ТОЛЬКО валидный JSON без markdown и без ```json:
{{"category": "...", "priority": "...", "reasoning": "...", "summary": "..."}}"""

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}",
                headers={"Content-Type": "application/json"},
                json={"contents": [{"parts": [{"text": prompt}]}]}
            )
            data = resp.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            # strip possible markdown fences
            text = text.replace("```json", "").replace("```", "").strip()
            return json.loads(text)
    except Exception as e:
        return {
            "category": "другое",
            "priority": "средний",
            "reasoning": f"AI недоступен: {str(e)[:80]}",
            "summary": f"{subject[:100]}"
        }

# ── Telegram Notification ─────────────────────────────────────────────────────
async def send_telegram(ticket_id: int, name: str, email: str, subject: str,
                         category: str, priority: str, summary: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return

    priority_emoji = {
        "критический": "🔴", "высокий": "🟠", "средний": "🟡", "низкий": "🟢"
    }.get(priority, "⚪")

    category_emoji = {
        "техническая проблема": "🔧", "вопрос по оплате": "💳",
        "консультация": "💬", "жалоба": "😤",
        "запрос функции": "✨", "другое": "📋"
    }.get(category, "📋")

    text = (
        f"📨 *Новая заявка #{ticket_id}*\n\n"
        f"👤 *Заявитель:* {name}\n"
        f"📧 *Email:* {email}\n"
        f"📌 *Тема:* {subject}\n\n"
        f"{category_emoji} *Категория:* {category}\n"
        f"{priority_emoji} *Приоритет:* {priority}\n\n"
        f"📝 *Суть:* {summary}\n\n"
        f"🕐 {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    )

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": text,
                    "parse_mode": "Markdown"
                }
            )
    except Exception:
        pass

# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/submit")
async def submit_ticket(
    request: Request,
    name:    str = Form(...),
    email:   str = Form(...),
    phone:   str = Form(""),
    subject: str = Form(...),
    message: str = Form(...),
):
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # AI classification
    ai = await classify_ticket(subject, message)

    # Save to DB
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute(
        """INSERT INTO tickets (name, email, phone, subject, message,
           category, priority, reasoning, summary, status, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (name, email, phone, subject, message,
         ai["category"], ai["priority"], ai["reasoning"], ai["summary"],
         "new", created_at)
    )
    ticket_id = cur.lastrowid
    conn.commit()
    conn.close()

    # Telegram
    await send_telegram(ticket_id, name, email, subject,
                        ai["category"], ai["priority"], ai["summary"])

    return RedirectResponse(f"/success/{ticket_id}", status_code=303)


@app.get("/success/{ticket_id}", response_class=HTMLResponse)
async def success(request: Request, ticket_id: int):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    ticket = conn.execute("SELECT * FROM tickets WHERE id=?", (ticket_id,)).fetchone()
    conn.close()
    return templates.TemplateResponse("success.html", {"request": request, "ticket": ticket})


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})


@app.get("/api/tickets")
async def api_tickets(
    status:   str = "",
    priority: str = "",
    category: str = "",
    limit:    int = 100
):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    query = "SELECT * FROM tickets WHERE 1=1"
    params = []
    if status:
        query += " AND status=?"; params.append(status)
    if priority:
        query += " AND priority=?"; params.append(priority)
    if category:
        query += " AND category=?"; params.append(category)
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/stats")
async def api_stats():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    total    = conn.execute("SELECT COUNT(*) as c FROM tickets").fetchone()["c"]
    by_pri   = conn.execute("SELECT priority, COUNT(*) as c FROM tickets GROUP BY priority").fetchall()
    by_cat   = conn.execute("SELECT category, COUNT(*) as c FROM tickets GROUP BY category").fetchall()
    by_stat  = conn.execute("SELECT status, COUNT(*) as c FROM tickets GROUP BY status").fetchall()
    today    = conn.execute(
        "SELECT COUNT(*) as c FROM tickets WHERE DATE(created_at)=DATE('now')"
    ).fetchone()["c"]
    conn.close()

    return {
        "total": total,
        "today": today,
        "by_priority": [dict(r) for r in by_pri],
        "by_category": [dict(r) for r in by_cat],
        "by_status":   [dict(r) for r in by_stat],
    }


@app.patch("/api/tickets/{ticket_id}/status")
async def update_status(ticket_id: int, request: Request):
    body = await request.json()
    new_status = body.get("status", "new")
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE tickets SET status=? WHERE id=?", (new_status, ticket_id))
    conn.commit()
    conn.close()
    return {"ok": True}
