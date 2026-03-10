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

async function callArabGuardAPI(userInput, systemPrompt) {
  console.log("📡 Calling ArabGuard via Standard API...");
  
  // غيرنا المسار لـ /api/predict لأنه الأضمن في Gradio 4+
  const response = await fetch("https://d12o6aa-arabguard-analyzer.hf.space/api/predict", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      data: [userInput, systemPrompt || "أنت مساعد ذكي."],
      fn_index: 0 // ده بيقوله نادِ أول دالة (universal_api) عندك
    })
  });

  if (!response.ok) {
    const err = await response.text();
    console.error("❌ Hugging Face Error:", err);
    throw new Error("ArabGuard Space Error");
  }

  const result = await response.json();
  // لو الرد فيه data، يبقى تمام
  if (result.data) {
      return result.data; 
  } else {
      console.error("❌ Unexpected HF Response:", result);
      throw new Error("Invalid response format from ArabGuard");
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