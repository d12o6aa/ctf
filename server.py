import os
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, String, Integer, JSON, DateTime, desc
from sqlalchemy.orm import sessionmaker, Session, declarative_base
from gradio_client import Client
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

# ── DATABASE CONFIGURATION ───────────────────────────
DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# إذا كنتِ تختبرين محلياً بدون داتابيز، سيستخدم SQLite مؤقتاً
if not DATABASE_URL:
    DATABASE_URL = "sqlite:///./test.db"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ── DB MODEL ─────────────────────────────────────────
class ThreatLog(Base):
    __tablename__ = "threat_logs"
    id = Column(String, primary_key=True, index=True)
    username = Column(String, index=True)
    raw_input = Column(String)
    decision = Column(String)
    score = Column(Integer)
    level_id = Column(Integer, default=1)
    trace = Column(JSON)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))

Base.metadata.create_all(bind=engine)

# ── APP INITIALIZATION ──────────────────────────────
app = FastAPI(title="ArabGuard Game API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── STATIC FILES (Frontend Build) ───────────────────
if os.path.exists("dist"):
    app.mount("/assets", StaticFiles(directory="dist/assets"), name="assets")

# ── CLIENTS ──────────────────────────────────────────
groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
_ag_client = None

def get_ag():
    global _ag_client
    if _ag_client is None:
        try:
            _ag_client = Client("d12o6aa/ArabGuard-Analyzer")
        except Exception as e:
            print(f"Error connecting to ArabGuard: {e}")
    return _ag_client

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ── SCHEMAS ──────────────────────────────────────────
class GameTurnRequest(BaseModel):
    user_input: str
    username: str = "Anonymous"
    system_prompt: str = "أنت مساعد ذكي."
    level_id: int = 1
    use_groq: bool = True

# ── LOGIC ────────────────────────────────────────────
def save_to_db(db: Session, username: str, raw_input: str, trace: dict, decision: str, level_id: int = 1):
    try:
        score = trace.get("final_score", 0)
        new_log = ThreatLog(
            id=str(uuid.uuid4()),
            username=username,
            raw_input=raw_input,
            decision=decision,
            score=score,
            level_id=level_id,
            trace=trace,
            timestamp=datetime.now(timezone.utc)
        )
        db.add(new_log)
        db.commit()
    except Exception as e:
        print(f"Database Save Error: {e}")
        db.rollback()

# ── ENDPOINTS ────────────────────────────────────────
@app.post("/api/game-turn")
async def game_turn(req: GameTurnRequest, db: Session = Depends(get_db)):
    try:
        ag = get_ag()
        if not ag:
            raise HTTPException(status_code=503, detail="ArabGuard Model Offline")

        # 1. التحليل عبر ArabGuard
        result = ag.predict(
            user_input=req.user_input,
            system_prompt=req.system_prompt,
            api_name="/universal_api",
        )

        ag_chat_response, trace, status_label = result[0], result[1], result[2]
        
        final_decision = (
            status_label.get("label", "SAFE") 
            if isinstance(status_label, dict) else str(status_label)
        )
        blocked = final_decision in ("BLOCKED", "FLAG")

        # 2. حفظ في الداتابيز
        save_to_db(db, req.username, req.user_input, trace, final_decision, req.level_id)

        if blocked:
            return {"blocked": True, "reply": None, "trace": trace, "final_decision": final_decision}

        # 3. رد Groq في حالة الأمان
        if req.use_groq:
            completion = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": req.system_prompt},
                    {"role": "user", "content": req.user_input},
                ],
                max_tokens=500,
                temperature=0.85,
            )
            reply = completion.choices[0].message.content
        else:
            reply = ag_chat_response

        return {"blocked": False, "reply": reply, "trace": trace, "final_decision": final_decision}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/leaderboard")
async def get_leaderboard(db: Session = Depends(get_db)):
    """
    Top 10 unique players by best score.
    GROUP BY username so each player appears only once.
    """
    from sqlalchemy import func

    best = (
        db.query(
            ThreatLog.username,
            func.max(ThreatLog.score).label("best_score"),
            func.max(ThreatLog.level_id).label("max_level"),
        )
        .group_by(ThreatLog.username)
        .order_by(desc("best_score"))
        .limit(10)
        .all()
    )
    return [
        {"username": p.username, "score": p.best_score, "level_id": p.max_level}
        for p in best
    ]


@app.get("/api/stats")
async def get_stats(db: Session = Depends(get_db)):
    """
    Global game statistics consumed by the LiveBar.
    - total_attempts  : every row ever written to threat_logs
    - successful_hacks: rows where ArabGuard decision was SAFE
    """
    from sqlalchemy import func

    total_attempts = db.query(func.count(ThreatLog.id)).scalar() or 0
    successful_hacks = (
        db.query(func.count(ThreatLog.id))
        .filter(ThreatLog.decision == "SAFE")
        .scalar()
        or 0
    )
    return {
        "total_attempts": total_attempts,
        "successful_hacks": successful_hacks,
    }

@app.get("/health")
def health(db: Session = Depends(get_db)):
    return {
        "status": "ok",
        "arabguard_connected": _ag_client is not None,
        "database_connected": DATABASE_URL is not None
    }

@app.get("/")
async def read_index():
    index_path = os.path.join("dist", "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "ArabGuard API Online. Frontend dist not found."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=int(os.environ.get("PORT", 3001)), reload=True)