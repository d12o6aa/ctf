import os
import uvicorn
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from sqlalchemy.exc import IntegrityError
from database import get_db, ThreatLog, CompletedLevel, datetime, timezone, uuid
from game_logic import LEVELS_TEMPLATES, get_level_data, get_llm_response
from config import get_ag_client

app = FastAPI(title="ArabGuard Game API")


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # رابط الفرونت إند بتاعك
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],  # السماح بجميع أنواع الطلبات (GET, POST, etc)
    allow_headers=["*"],  # السماح بجميع الـ Headers
)


if os.path.exists("dist"):
    app.mount("/assets", StaticFiles(directory="dist/assets"), name="assets")

class GameTurnRequest(BaseModel):
    user_input: str
    username: str = "Anonymous"
    level_id: int = 1

@app.post("/api/game-turn")
async def game_turn(req: GameTurnRequest, db: Session = Depends(get_db)):
    try:
        level_info = get_level_data(req.level_id)
        if not level_info:
            raise HTTPException(status_code=404, detail="Level not found")

        ag = get_ag_client()
        if not ag:
            raise HTTPException(status_code=503, detail="ArabGuard Model Offline")

        result = ag.predict(
            user_input=req.user_input,
            system_prompt=level_info["system_prompt"],
            api_name="/universal_api"
        )

        ag_chat_response, trace, status_label = result[0], result[1], result[2]
        final_decision = status_label.get("label", "SAFE") if isinstance(status_label, dict) else str(status_label)

        if final_decision in ("BLOCKED", "FLAG"):
            new_log = ThreatLog(
                id=str(uuid.uuid4()), username=req.username,
                raw_input=req.user_input, decision=final_decision,
                score=trace.get("final_score", 0), level_id=req.level_id,
                is_compromised=False, trace=trace,
                timestamp=datetime.now(timezone.utc)
            )
            db.add(new_log)
            db.commit()
            return {"blocked": True, "reply": None, "trace": trace, "final_decision": final_decision}

        reply = get_llm_response(level_info["system_prompt"], req.user_input)

        secret = level_info["target_secret"]
        is_compromised = secret.lower() in req.user_input.lower() or secret.lower() in reply.lower()

        new_log = ThreatLog(
            id=str(uuid.uuid4()), username=req.username,
            raw_input=req.user_input, decision=final_decision,
            score=trace.get("final_score", 0), level_id=req.level_id,
            is_compromised=is_compromised, trace=trace,
            timestamp=datetime.now(timezone.utc)
        )
        db.add(new_log)

        # ── سجّل الليفل كمكتمل لو نجح ──
        if is_compromised:
            try:
                completed = CompletedLevel(
                    username=req.username,
                    level_id=req.level_id,
                    completed_at=datetime.now(timezone.utc)
                )
                db.add(completed)
            except IntegrityError:
                db.rollback()  # already completed before

        db.commit()

        return {
            "blocked": False,
            "reply": reply,
            "trace": trace,
            "final_decision": final_decision,
            "is_compromised": is_compromised,
            "secret_revealed": secret if is_compromised else None
        }
    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/levels")
async def get_levels():
    STRENGTH_COLORS = {
        "EASY":       "#00f5c8",
        "MEDIUM":     "#ff8c42",
        "STRONG":     "#f5c842",
        "ELITE":      "#a333ff",
        "IMPOSSIBLE": "#ff0066",
    }
    return [
        {
            "id":            v["id"],
            "title":         v["title"],
            "strength":      v["strength"],
            "strengthColor": v.get("strengthColor") or STRENGTH_COLORS.get(v["strength"], "#00f5c8"),
            "persona":       v["persona"],
            "personaDesc":   v.get("personaDesc", ""),
            "target":        v.get("target", "السر"),
            "blockedReplies": v.get("blockedReplies", ["مش هينفع!", "ArabGuard شايفك!", "جرب تاني 😄"]),
            "successMsg":    v.get("successMsg", "برافو! اخترقت النظام! 🎉"),
        }
        for v in LEVELS_TEMPLATES.values()
    ]


@app.get("/api/user-progress/{username}")
async def get_user_progress(username: str, db: Session = Depends(get_db)):
    """إرجاع الليفلز اللي خلصها اليوزر"""
    rows = db.query(CompletedLevel.level_id).filter(
        CompletedLevel.username == username
    ).all()
    completed_ids = [r.level_id for r in rows]
    return {"username": username, "completed_levels": completed_ids}


@app.get("/api/leaderboard")
async def get_leaderboard(db: Session = Depends(get_db)):
    """الليدربورد: اليوزر اللي خلص أكبر عدد ليفلز"""
    rows = (
        db.query(
            CompletedLevel.username,
            func.count(CompletedLevel.level_id).label("levels_completed"),
            func.max(CompletedLevel.level_id).label("max_level"),
        )
        .group_by(CompletedLevel.username)
        .order_by(desc("levels_completed"), desc("max_level"))
        .limit(10)
        .all()
    )

    result = []
    for r in rows:
        tries = db.query(func.count(ThreatLog.id)).filter(
            ThreatLog.username == r.username
        ).scalar() or 0
        result.append({
            "username": r.username,
            "levels_completed": r.levels_completed,
            "max_level": r.max_level,
            "tries": tries,
        })
    return result


@app.get("/api/stats")
async def get_stats(db: Session = Depends(get_db)):
    total_attempts = db.query(func.count(ThreatLog.id)).scalar() or 0
    # ← عدد الاختراقات الحقيقية فقط
    successful_hacks = db.query(func.count(ThreatLog.id)).filter(
        ThreatLog.is_compromised == True
    ).scalar() or 0
    return {
        "total_attempts": total_attempts,
        "successful_hacks": successful_hacks
    }


@app.get("/")
async def read_index():
    index_path = os.path.join("dist", "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "ArabGuard API Online."}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 3001)), reload=True)