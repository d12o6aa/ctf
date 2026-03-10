import express from "express";
import cors from "cors";
import path from "path";
import { fileURLToPath } from "url";
import Groq from "groq-sdk";
import dotenv from "dotenv";

dotenv.config();

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const app = express();
const PORT = process.env.PORT || 5000;
const groq = new Groq({ apiKey: process.env.GROQ_API_KEY });

app.use(cors({ origin: "*" }));
app.use(express.json());
app.use(express.static(path.join(__dirname, "dist")));

// دالة الاتصال بـ ArabGuard (استخدام الـ API المباشر لـ Hugging Face)
async function callArabGuardAPI(userInput, systemPrompt) {
    console.log("📡 Calling ArabGuard Space...");
    
    // ملاحظة: اللينك ده هو الـ API Endpoint الصحيح للـ Space بتاعك
    const HF_API = "https://d12o6aa-arabguard-analyzer.hf.space/call/universal_api";

    const response = await fetch(HF_API, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            data: [userInput, systemPrompt || "أنت مساعد ذكي."]
        })
    });

    if (!response.ok) {
        const errorDetail = await response.text();
        console.error("❌ HF Error:", errorDetail);
        throw new Error("ArabGuard Space Refused Connection");
    }

    const { event_id } = await response.json();
    console.log(`✅ Event ID created: ${event_id}`);

    // الخطوة الثانية: الحصول على النتيجة باستخدام الـ event_id
    const resultResponse = await fetch(`${HF_API}/${event_id}`);
    const resultText = await resultResponse.text();

    // فك شفرة الـ Stream اللي راجع من Hugging Face
    const lines = resultText.split('\n');
    for (let line of lines) {
        if (line.startsWith('data: ')) {
            const jsonStr = line.replace('data: ', '');
            try {
                const data = JSON.parse(jsonStr);
                return data; // [agChatResp, trace, statusLabel]
            } catch (e) {
                console.error("❌ Parsing Error:", e.message);
            }
        }
    }
    throw new Error("Could not find data in HF response");
}

app.post("/api/game-turn", async (req, res) => {
    const { user_input, system_prompt } = req.body;
    if (!user_input) return res.status(400).json({ error: "Input required" });

    try {
        const agData = await callArabGuardAPI(user_input, system_prompt);
        
        const [reply, trace, status] = agData;
        const final_decision = status?.label || "SAFE";
        const blocked = final_decision === "BLOCKED" || final_decision === "FLAG";

        console.log(`🛡️  Decision for "${user_input.substring(0, 20)}": ${final_decision}`);

        res.json({ 
            blocked, 
            reply: blocked ? "🚨 ArabGuard: محاولة اختراق! تم حظر النص." : reply, 
            trace, 
            final_decision 
        });

    } catch (err) {
        console.error("❌ Server Error:", err.message);
        res.status(500).json({ error: "فشل الاتصال بـ ArabGuard" });
    }
});

app.get("*", (req, res) => {
    res.sendFile(path.join(__dirname, "dist", "index.html"));
});

app.listen(PORT, () => {
    console.log(`🚀 ArabGuard Game live on port ${PORT}`);
});