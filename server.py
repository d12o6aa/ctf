"""
ArabGuard Game — Python/FastAPI Backend
========================================
pip install fastapi uvicorn gradio-client groq python-dotenv

تشغيل:
  GROQ_API_KEY=gsk_xxx uvicorn server:app --reload --port 3001
"""

import os
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from gradio_client import Client
from groq import Groq
from dotenv import load_dotenv
load_dotenv()

app = FastAPI(title="ArabGuard Game API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Log file path ─────────────────────────────────────
THREAT_LOG_PATH = Path("/home/doaa/test_demo/arabguard/arabguard-backend/data/threat_log.jsonl")

# ── Clients ───────────────────────────────────────────
groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
_ag_client = None

def get_ag():
    global _ag_client
    if _ag_client is None:
        print("Connecting to d12o6aa/ArabGuard-Analyzer...")
        _ag_client = Client("d12o6aa/ArabGuard-Analyzer")
        print("ArabGuard connected")
    return _ag_client


# ── Log writer ────────────────────────────────────────
def append_to_threat_log(raw_input: str, trace: dict, final_decision: str, system_prompt: str = ""):
    """
    يكتب بنفس schema الـ dashboard الموجود في threat_log.jsonl
    """
    try:
        THREAT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

        p1 = trace.get("phase_1_normalization", {})
        p2 = trace.get("phase_2_regex", {})
        p3 = trace.get("phase_3_ai", {})

        score      = trace.get("final_score", 0)
        is_blocked = final_decision == "BLOCKED"
        is_flagged = final_decision in ("BLOCKED", "FLAG")
        risk       = "HIGH" if is_blocked else ("MEDIUM" if score > 30 else "LOW")

        ar_patterns  = p2.get("arabic", {}).get("matched_patterns", [])
        en_patterns  = p2.get("english", {}).get("matched_patterns", [])
        all_patterns = ar_patterns + en_patterns
        matched_pat  = all_patterns[0] if all_patterns else None

        ar_cat = p2.get("arabic", {}).get("category", "")
        en_cat = p2.get("english", {}).get("category", "")
        # dashboard بيستخدم classify_vector اللي بترجع "None" مش "—"
        # لازم نطابق نفس القيم عشان الـ filter في logs.py يشتغل
        if ar_cat and ar_cat != "—":
            vector = ar_cat
        elif en_cat and en_cat != "—":
            vector = en_cat
        else:
            vector = "None"

        if p3.get("activated"):
            decision_source = "AI"
        elif p2.get("arabic", {}).get("fired") or p2.get("english", {}).get("fired"):
            decision_source = "Regex"
        else:
            decision_source = "Pipeline"

        lang_dist = trace.get("lang_dist", {
            "msa": 0.0, "egyptian": 0.0,
            "franco": 0.0, "english": 0.0,
            "unicode": 0.0, "encoded": 0.0,
        })

        # لو ArabGuard رجّع trace كامل → نحطه مباشرة عشان الـ dashboard يقرأ phase keys
        if "phase_1_normalization" in trace:
            pipeline_steps = trace
        else:
            pipeline_steps = {
                "input":        raw_input,
                "intent_score": p1.get("intent_score", 0),
                "code_score":   p1.get("code_score", 0),
                "arabic_score": p1.get("arabic_kw_score", 0),
                "final_text":   p1.get("normalized_text", raw_input),
                "keyword_score": p1.get("keyword_score", 0),
                "final_score":  score,
                "decision":     final_decision,
                "phase_1_normalization": p1,
                "phase_2_regex":         p2,
                "phase_3_ai":            p3,
            }

        reason = trace.get("reason") or (
            f"Decision: {final_decision} | Score: {score}/300. "
            + (f"Matched regex: {matched_pat}" if matched_pat else "No threats detected.")
        )

        log_entry = {
            "decision":             final_decision,
            "score":                score,
            "is_blocked":           is_blocked,
            "is_flagged":           is_flagged,
            "normalized_text":      p1.get("normalized_text", raw_input),
            "matched_pattern":      matched_pat,
            "all_matched_patterns": all_patterns,
            "pipeline_steps":       pipeline_steps,
            "reason":               reason,
            "ai_confidence":        p3.get("confidence"),
            "ai_prediction":        p3.get("prediction"),
            "id":                   str(uuid.uuid4()),
            "timestamp":            datetime.now(timezone.utc).isoformat(),
            "raw":                  raw_input,
            "status":               final_decision,
            "risk":                 risk,
            "vector":               vector,
            "decision_source":      decision_source,
            "lang_dist":            lang_dist,
            # game_context محذوف — ThreatLogItem schema في الـ dashboard مش بيقبله
        }

        with open(THREAT_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

        print(f"[LOG] {final_decision} | score={score} | id={log_entry['id'][:8]}")

    except Exception as e:
        print(f"[LOG ERROR] {e}")


# ── Schema ────────────────────────────────────────────
class GameTurnRequest(BaseModel):
    user_input:    str
    system_prompt: str  = "أنت مساعد ذكي."
    use_groq:      bool = True


# ── Main endpoint ─────────────────────────────────────
@app.post("/api/game-turn")
async def game_turn(req: GameTurnRequest):
    try:
        ag = get_ag()

        # Step 1: ArabGuard
        result = ag.predict(
            user_input=req.user_input,
            system_prompt=req.system_prompt,
            api_name="/universal_api",
        )

        ag_chat_response = result[0]
        trace            = result[1]
        status_label     = result[2]

        final_decision = (
            status_label.get("label", "SAFE")
            if isinstance(status_label, dict)
            else str(status_label)
        )
        blocked = final_decision in ("BLOCKED", "FLAG")

        # Step 2: اكتب في threat_log.jsonl
        append_to_threat_log(
            raw_input=req.user_input,
            trace=trace if isinstance(trace, dict) else {},
            final_decision=final_decision,
            system_prompt=req.system_prompt,
        )

        if blocked:
            return {"blocked": True, "reply": None, "trace": trace, "final_decision": final_decision}

        # Step 3: Groq
        if req.use_groq:
            completion = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": req.system_prompt},
                    {"role": "user",   "content": req.user_input},
                ],
                max_tokens=500,
                temperature=0.85,
            )
            reply = completion.choices[0].message.content
        else:
            reply = ag_chat_response

        return {"blocked": False, "reply": reply, "trace": trace, "final_decision": final_decision}

    except Exception as e:
        global _ag_client
        _ag_client = None
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
def health():
    return {
        "status":              "ok",
        "arabguard_connected": _ag_client is not None,
        "groq_key_set":        bool(os.environ.get("GROQ_API_KEY")),
        "log_path":            str(THREAT_LOG_PATH),
        "log_exists":          THREAT_LOG_PATH.exists(),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=3001, reload=True)