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

// دالة الاتصال بـ ArabGuard عن طريق الـ API المباشر
async function callArabGuardAPI(userInput, systemPrompt) {
    const response = await fetch("https://d12o6aa-arabguard-analyzer.hf.space/call/universal_api", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            data: [userInput, systemPrompt || "أنت مساعد ذكي."]
        })
    });

    if (!response.ok) throw new Error("ArabGuard API Error");
    
    const { event_id } = await response.json();
    
    // هنجيب النتيجة باستخدام الـ event_id
    const resultResponse = await fetch(`https://d12o6aa-arabguard-analyzer.hf.space/call/universal_api/${event_id}`);
    const resultText = await resultResponse.text();
    
    // تحويل النتيجة من Format الـ Server-Sent Events لـ JSON
    const lines = resultText.split('\n');
    for (let line of lines) {
        if (line.startsWith('data:')) {
            const data = JSON.parse(line.slice(5));
            return data; // ده اللي فيه [reply, trace, label]
        }
    }
}

app.post("/api/game-turn", async (req, res) => {
    const { user_input, system_prompt } = req.body;
    if (!user_input) return res.status(400).json({ error: "user_input required" });

    try {
        console.log("⏳ Calling ArabGuard via HTTP...");
        const agData = await callArabGuardAPI(user_input, system_prompt);
        
        const [agChatResp, trace, statusLabel] = agData;
        const final_decision = statusLabel?.label || "SAFE";
        const blocked = final_decision === "BLOCKED" || final_decision === "FLAG";

        console.log(`[Security] Result: ${final_decision}`);

        return res.json({ 
            blocked, 
            reply: blocked ? "يا ناصح! ArabGuard لقطك. 😂" : agChatResp, 
            trace, 
            final_decision 
        });

    } catch (err) {
        console.error("❌ Error:", err.message);
        res.status(500).json({ error: "خطأ في الاتصال بالسيرفر الأمني." });
    }
});

app.get("*", (req, res) => {
    res.sendFile(path.join(__dirname, "dist", "index.html"));
});

app.listen(PORT, () => console.log(`🚀 Server running on port ${PORT}`));