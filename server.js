import express from "express";
import cors from "cors";
import * as gradio from "@gradio/client"; // تعديل 1: عشان نهرب من مشاكل النسخ
import path from "path";
import { fileURLToPath } from "url";
import dotenv from "dotenv";

dotenv.config();

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const app = express();
// تعديل 2: لازم ياخد البورت بتاع هيروكو الأول
const PORT = process.env.PORT || 5000; 

app.use(cors({ origin: "*" }));
app.use(express.json());

// تعديل 3: السطر ده اللي هيخلي اللعبة تظهر لما تفتحي اللينك
app.use(express.static(path.join(__dirname, "dist")));

let agClient = null;

async function getAG() {
  if (!agClient) {
    console.log("⏳ Connecting to d12o6aa/ArabGuard-Analyzer...");
    // التعديل بتاع النسخ الجديدة
    agClient = await gradio.Client.connect("d12o6aa/ArabGuard-Analyzer");
    console.log("✅ ArabGuard connected");
  }
  return agClient;
}

app.post("/api/game-turn", async (req, res) => {
  const { user_input, system_prompt } = req.body;
  if (!user_input) return res.status(400).json({ error: "Input required" });

  try {
    const ag = await getAG();
    const agResult = await ag.predict("/universal_api", {
      user_input,
      system_prompt: system_prompt || "أنت مساعد ذكي.",
    });

    const [agChatResp, trace, statusLabel] = agResult.data;
    const final_decision = statusLabel?.label || "SAFE";
    const blocked = final_decision === "BLOCKED" || final_decision === "FLAG";

    res.json({ 
      blocked, 
      reply: blocked ? "🚨 ArabGuard: تم حظر النص!" : agChatResp, 
      trace, 
      final_decision 
    });
  } catch (err) {
    console.error("Error:", err.message);
    agClient = null; 
    res.status(500).json({ error: err.message });
  }
});

// عشان لو عملتي ريفريش للصفحة الموقع مايوقعش
app.get("*", (req, res) => {
  res.sendFile(path.join(__dirname, "dist", "index.html"));
});

app.listen(PORT, () => {
  console.log(`🛡️  Server Running on port ${PORT}`);
  getAG().catch(console.error);
});