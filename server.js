import express from "express";
import cors from "cors";
import { Client } from "@gradio/client";
import Groq from "groq-sdk";
import dotenv from "dotenv";

dotenv.config();

const app = express();
const PORT = process.env.PORT || 3001;
const groq = new Groq({ apiKey: process.env.GROQ_API_KEY });

app.use(cors({ origin: "*" }));
app.use(express.json());

let agClient = null;

async function getAG() {
  if (!agClient) {
    console.log("⏳ Connecting to d12o6aa/ArabGuard-Analyzer...");
    agClient = await Client.connect("d12o6aa/ArabGuard-Analyzer");
    console.log("✅ ArabGuard connected");
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
      reply: blocked ? "يا ناصح! ArabGuard لقطك. 😂" : agChatResp, 
      trace, 
      final_decision 
    });

  } catch (err) {
    console.error("Error:", err.message);
    agClient = null;
    res.status(500).json({ error: err.message });
  }
});

app.listen(PORT, () => {
  console.log(`🛡️  Server Running on http://localhost:${PORT}`);
  getAG().catch(console.error);
});