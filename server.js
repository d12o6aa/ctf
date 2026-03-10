import express from "express";
import cors from "cors";
import path from "path";
import { fileURLToPath } from "url";
import { client } from "@gradio/client"; // التعديل هنا: استخدام client بحرف صغير
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

let agClient = null;

async function getAG() {
  if (!agClient) {
    console.log("⏳ Connecting to ArabGuard Space...");
    try {
      // التعديل هنا: استخدام client.connect مباشرة
      agClient = await client.connect("d12o6aa/ArabGuard-Analyzer"); 
      console.log("✅ ArabGuard connected successfully");
    } catch (error) {
      console.error("❌ Connection failed:", error.message);
      throw error;
    }
  }
  return agClient;
}

app.post("/api/game-turn", async (req, res) => {
  const { user_input, system_prompt } = req.body;
  if (!user_input) return res.status(400).json({ error: "user_input required" });

  try {
    const ag = await getAG();
    const agResult = await ag.predict("/universal_api", {
      user_input,
      system_prompt: system_prompt || "أنت مساعد ذكي.",
    });

    const [agChatResp, trace, statusLabel] = agResult.data;
    const final_decision = statusLabel?.label || "SAFE";
    const blocked = final_decision === "BLOCKED" || final_decision === "FLAG";

    console.log(`[Security] "${user_input.substring(0, 30)}..." -> ${final_decision}`);

    return res.json({ 
      blocked, 
      reply: blocked ? "يا ناصح! ArabGuard لقطك وأنا لسه بقول يا هادي. 😂" : agChatResp, 
      trace, 
      final_decision 
    });

  } catch (err) {
    console.error("Error Detail:", err.message);
    agClient = null; // إعادة المحاولة في الريكويست الجاي لو حصل فشل
    res.status(500).json({ error: "خطأ في الاتصال بالسيرفر الأمني." });
  }
});

// توجيه أي مسار غير معروف لصفحة اللعبة (عشان الـ Refresh يشتغل)
app.get("*", (req, res) => {
  res.sendFile(path.join(__dirname, "dist", "index.html"));
});

app.listen(PORT, () => {
  console.log(`🛡️  Server Running on port: ${PORT}`);
  getAG().catch(err => console.error("Initial connection error:", err.message));
});