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
        # 1. جلب بيانات الليفل والسر من الـ Templates والـ Pool أولاً
        level_template = LEVELS_TEMPLATES.get(req.level_id)
        if not level_template:
            raise HTTPException(status_code=404, detail="Level not found")

        # اختيار السر بناءً على الـ Category
        category = level_template.get("category", "apartment_numbers")
        if category not in SECRET_POOL:
            category = "apartment_numbers"
        
        # اختيار سر عشوائي لهذا الدور
        target_secret = random.choice(SECRET_POOL[category])
        
        # تجهيز الـ System Prompt بالسر المختار
        system_prompt = level_template["prompt_template"].format(secret=target_secret)

        # 2. استدعاء ArabGuard للتحقق من الاختراق (Security Check)
        ag = get_ag_client()
        if not ag:
            # لو الموديل الأمني واقع، ممكن نعديها أو نوقف، الأفضل نعديها بـ SAFE مؤقتاً
            trace, final_decision = {"final_score": 0}, "SAFE"
        else:
            result = ag.predict(
                user_input=req.user_input,
                system_prompt=system_prompt,
                api_name="/universal_api"
            )
            trace, status_label = result[1], result[2]
            final_decision = status_label.get("label", "SAFE") if isinstance(status_label, dict) else str(status_label)

        # 3. لو الطلب محظور (BLOCKED)
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
            return {"blocked": True, "reply": "ArabGuard اكتشف محاولة مريبة! العب غيرها.", "trace": trace, "final_decision": final_decision}

        # 4. الحصول على رد الـ LLM (عم محمد، نهى، إلخ) باستخدام الفانكشن اللي فيها Fallback
        reply = get_llm_response(system_prompt, req.user_input)

        # 5. التحقق هل المستخدم قدر يخلي الـ AI يقول السر؟
        # بنتحقق لو السر موجود في رد الـ AI
        is_compromised = target_secret.lower() in reply.lower()

        # 6. تسجيل اللوج في قاعدة البيانات
        new_log = ThreatLog(
            id=str(uuid.uuid4()), username=req.username,
            raw_input=req.user_input, decision=final_decision,
            score=trace.get("final_score", 0), level_id=req.level_id,
            is_compromised=is_compromised, trace=trace,
            timestamp=datetime.now(timezone.utc)
        )
        db.add(new_log)

        # 7. لو نجح في الاختراق، سجل الليفل كمكتمل
        if is_compromised:
            try:
                # نتحقق الأول لو مسجل قبل كدة عشان ميرميش IntegrityError
                already_done = db.query(CompletedLevel).filter(
                    CompletedLevel.username == req.username, 
                    CompletedLevel.level_id == req.level_id
                ).first()
                
                if not already_done:
                    completed = CompletedLevel(
                        username=req.username,
                        level_id=req.level_id,
                        completed_at=datetime.now(timezone.utc)
                    )
                    db.add(completed)
            except Exception as e:
                print(f"Update progress error: {e}")
                db.rollback()

        db.commit()

        return {
            "blocked": False,
            "reply": reply,
            "trace": trace,
            "final_decision": final_decision,
            "is_compromised": is_compromised,
            "secret_revealed": target_secret if is_compromised else None
        }

    except Exception as e:
        db.rollback()
        print(f"Critical Error in game_turn: {e}")
        raise HTTPException(status_code=500, detail="حصل مشكلة في السيرفر، جرب تاني يا بطل!")

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

@app.get("/api/user-progress/{username}")
@app.get("/api/user-progress/") 
async def get_user_progress(username: str = "Anonymous", db: Session = Depends(get_db)):
    try:
        completed = db.query(CompletedLevel.level_id).filter(CompletedLevel.username == username).all()
        return {"completed_levels": [c.level_id for c in completed]}
    except Exception as e:
        print(f"Error fetching progress: {e}")
        return {"completed_levels": []}

@app.get("/")
async def read_index():
    index_path = os.path.join("dist", "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "ArabGuard API Online."}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 3001)), reload=True)