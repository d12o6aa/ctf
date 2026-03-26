import os
import uvicorn
import random  # <--- إضافة دي ضروري جداً
import uuid    # <--- استدعاء مباشر أضمن
from datetime import datetime, timezone # <--- استدعاء مباشر أضمن
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from sqlalchemy.exc import IntegrityError

# تأكدي إن الملفات دي موجودة وفيها الحاجات دي فعلاً
from database import get_db, ThreatLog, CompletedLevel 
from game_logic import LEVELS_TEMPLATES, get_level_data, get_llm_response
from config import SECRET_POOL, get_ag_client

app = FastAPI(title="ArabGuard Game API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
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
        # 1. جلب بيانات الليفل
        level_template = LEVELS_TEMPLATES.get(req.level_id)
        if not level_template:
            raise HTTPException(status_code=404, detail="Level not found")

        # 2. اختيار السر وتجهيز البرومبت
        category = level_template.get("category", "apartment_numbers")
        current_pool = SECRET_POOL.get(category, SECRET_POOL.get("apartment_numbers", ["101"]))
        
        # اختيار سر عشوائي لهذا الدور
        target_secret = random.choice(current_pool)
        
        # دمج السر في البرومبت (استخدام replace أضمن من format لو فيه أقواس كتير)
        system_prompt = level_template["prompt_template"].replace("{secret}", target_secret)

        # 3. استدعاء الـ LLM
        reply = get_llm_response(system_prompt, req.user_input)
        
        # 4. التحقق من الاختراق
        is_compromised = target_secret.lower() in reply.lower()

        # 5. تسجيل اللوج
        new_log = ThreatLog(
            id=str(uuid.uuid4()), 
            username=req.username,
            raw_input=req.user_input, 
            decision="SAFE",
            score=0, 
            level_id=req.level_id,
            is_compromised=is_compromised,
            timestamp=datetime.now(timezone.utc)
        )
        db.add(new_log)

        # 6. تحديث التقدم لو فاز
        if is_compromised:
            already_done = db.query(CompletedLevel).filter(
                CompletedLevel.username == req.username, 
                CompletedLevel.level_id == req.level_id
            ).first()
            if not already_done:
                db.add(CompletedLevel(username=req.username, level_id=req.level_id))

        db.commit()

        return {
            "blocked": False,
            "reply": reply,
            "is_compromised": is_compromised,
            "secret_revealed": target_secret if is_compromised else None
        }

    except Exception as e:
        if db: db.rollback()
        print(f"Server Error Trace: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

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
            "successMsg":    v.get("successMsg", "برافو! اخترقت النظام! 🎉"),
        }
        for v in LEVELS_TEMPLATES.values()
    ]

# تم دمج دالتي الـ Progress في دالة واحدة نظيفة
@app.get("/api/user-progress/{username}")
async def get_user_progress(username: str, db: Session = Depends(get_db)):
    try:
        rows = db.query(CompletedLevel.level_id).filter(CompletedLevel.username == username).all()
        return {"completed_levels": [r.level_id for r in rows]}
    except:
        return {"completed_levels": []}

@app.get("/api/user-progress/")
async def get_empty_progress():
    return {"completed_levels": []}

@app.get("/api/leaderboard")
async def get_leaderboard(db: Session = Depends(get_db)):
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
        result.append({
            "username": r.username,
            "levels_completed": r.levels_completed,
            "max_level": r.max_level
        })
    return result

@app.get("/api/stats")
async def get_stats(db: Session = Depends(get_db)):
    total_attempts = db.query(func.count(ThreatLog.id)).scalar() or 0
    successful_hacks = db.query(func.count(ThreatLog.id)).filter(ThreatLog.is_compromised == True).scalar() or 0
    return {"total_attempts": total_attempts, "successful_hacks": successful_hacks}

@app.get("/")
async def read_index():
    index_path = os.path.join("dist", "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "ArabGuard API Online."}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 3001)))