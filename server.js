import express from "express";
import cors from "cors";
import path from "path";
import { fileURLToPath } from "url";
import dotenv from "dotenv";

dotenv.config();

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const app = express();
const PORT = process.env.PORT || 5000;

app.use(cors({ origin: "*" }));
app.use(express.json());
app.use(express.static(path.join(__dirname, "dist")));

// دالة الاتصال بـ ArabGuard (استخدام الـ API المباشر لـ Hugging Face)
async function callArabGuardAPI(userInput, systemPrompt) {
    console.log("📡 Calling ArabGuard Space via Direct Predict API...");
    
    // هذا هو الرابط البرمجي المباشر للـ Space الخاص بكِ
    const HF_API_URL = "https://d12o6aa-arabguard-analyzer.hf.space/api/predict";

    const response = await fetch(HF_API_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            data: [
                userInput, 
                systemPrompt || "أنت مساعد ذكي."
            ]
        })
    });

    if (!response.ok) {
        const errorDetail = await response.text();
        console.error("❌ Hugging Face Error:", errorDetail);
        throw new Error("ArabGuard Space Error");
    }

    const result = await response.json();
    console.log("✅ ArabGuard response received!");
    
    // النتيجة ترجع في مصفوفة اسمها data
    // result.data[0] -> الرد (Chat Response)
    // result.data[1] -> التريس (Trace JSON)
    // result.data[2] -> الحالة (Label: SAFE/BLOCKED)
    return result.data; 
}

app.post("/api/game-turn", async (req, res) => {
    const { user_input, system_prompt } = req.body;
    if (!user_input) return res.status(400).json({ error: "user_input is required" });

    try {
        const agData = await callArabGuardAPI(user_input, system_prompt);
        
        const reply = agData[0];
        const trace = agData[1];
        const status = agData[2];

        const final_decision = status?.label || "SAFE";
        const blocked = final_decision === "BLOCKED" || final_decision === "FLAG";

        console.log(`🛡️  Security Decision: ${final_decision}`);

        return res.json({ 
            blocked, 
            reply: blocked ? "يا ناصح! ArabGuard لقط محاولة الاختراق دي. 😂" : reply, 
            trace, 
            final_decision 
        });

    } catch (err) {
        console.error("❌ Backend Error:", err.message);
        res.status(500).json({ error: "فشل الاتصال بـ ArabGuard" });
    }
});

app.get("*", (req, res) => {
    res.sendFile(path.join(__dirname, "dist", "index.html"));
});

app.listen(PORT, () => {
    console.log(`🚀 ArabGuard Game live on port ${PORT}`);
});