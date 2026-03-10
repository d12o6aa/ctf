from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import requests
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

# تفعيل الـ CORS عشان الفرونت إيند يكلم الباك إيند
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# دالة الاتصال بـ ArabGuard (استخدام الـ API المباشر)
def call_arab_guard(user_input, system_prompt):
    url = "https://d12o6aa-arabguard-analyzer.hf.space/api/predict"
    payload = {
        "data": [user_input, system_prompt or "أنت مساعد ذكي."]
    }
    response = requests.post(url, json=payload)
    if response.status_code == 200:
        return response.json().get("data")
    else:
        raise Exception(f"ArabGuard Error: {response.text}")

@app.post("/api/game-turn")
async def game_turn(request: Request):
    data = await request.json()
    user_input = data.get("user_input")
    system_prompt = data.get("system_prompt", "أنت مساعد ذكي.")

    try:
        # نداء الموديل
        ag_data = call_arab_guard(user_input, system_prompt)
        
        # [reply, trace, status_label]
        reply = ag_data[0]
        trace = ag_data[1]
        status = ag_data[2]
        
        final_decision = status.get("label", "SAFE")
        blocked = final_decision in ["BLOCKED", "FLAG"]

        return {
            "blocked": blocked,
            "reply": "يا ناصح! ArabGuard لقطك. 😂" if blocked else reply,
            "trace": trace,
            "final_decision": final_decision
        }
    except Exception as e:
        return {"error": str(e)}, 500

# تشغيل ملفات الـ React (فولدر dist)
app.mount("/", StaticFiles(directory="dist", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 5000))
    uvicorn.run(app, host="0.0.0.0", port=port)