/**
 * ArabGuard Game Backend Proxy
 * ==============================
 * هذا الـ server هو الـ bridge بين الـ React frontend
 * وبين ArabGuard Gradio API + Groq LLM
 *
 * Install: npm install express cors @gradio/client groq-sdk
 * Run:     GROQ_API_KEY=xxx node server.js
 */

const express = require("express");
const cors = require("cors");
const { Client } = require("@gradio/client");
const Groq = require("groq-sdk");

const app = express();
app.use(cors());
app.use(express.json());

const groq = new Groq({ apiKey: process.env.GROQ_API_KEY });

// Cache the ArabGuard client connection
let arabGuardClient = null;
async function getArabGuard() {
  if (!arabGuardClient) {
    console.log("Connecting to ArabGuard...");
    arabGuardClient = await Client.connect("d12o6aa/ArabGuard-Analyzer");
    console.log("ArabGuard connected ✓");
  }
  return arabGuardClient;
}

/**
 * POST /api/arabguard
 * Body: { user_input: string, system_prompt: string }
 * Returns: { chat_response, trace, status, final_decision }
 */
app.post("/api/arabguard", async (req, res) => {
  try {
    const { user_input, system_prompt } = req.body;

    if (!user_input) {
      return res.status(400).json({ error: "user_input is required" });
    }

    const client = await getArabGuard();

    // Call ArabGuard /universal_api
    // Returns: [chatResponse (str), trace (object), status (label)]
    const result = await client.predict("/universal_api", {
      user_input: user_input,
      system_prompt: system_prompt || "أنت مساعد ذكي.",
    });

    const [chat_response, trace, status_label] = result.data;

    // Extract final decision from status label
    const final_decision = status_label?.label || "SAFE";

    console.log(`[ArabGuard] "${user_input.substring(0, 40)}..." → ${final_decision}`);

    res.json({
      chat_response,
      trace,
      status: status_label,
      final_decision,
    });

  } catch (error) {
    console.error("ArabGuard error:", error);
    // Return safe fallback to not break the game
    res.json({
      chat_response: null,
      trace: null,
      status: { label: "SAFE" },
      final_decision: "SAFE",
      error: error.message,
    });
  }
});

/**
 * POST /api/chat
 * Body: { user_input: string, system_prompt: string }
 * Returns: { reply: string }
 * 
 * Uses Groq Llama-3.3-70b (only called when ArabGuard says SAFE)
 */
app.post("/api/chat", async (req, res) => {
  try {
    const { user_input, system_prompt } = req.body;

    const completion = await groq.chat.completions.create({
      model: "llama-3.3-70b-versatile",
      messages: [
        { role: "system", content: system_prompt },
        { role: "user", content: user_input },
      ],
      max_tokens: 500,
      temperature: 0.8,
    });

    const reply = completion.choices[0]?.message?.content || "مفيش رد.";
    console.log(`[Groq] reply: "${reply.substring(0, 60)}..."`);

    res.json({ reply });

  } catch (error) {
    console.error("Groq error:", error);
    res.status(500).json({ error: error.message });
  }
});

/**
 * POST /api/game-turn
 * Combined endpoint: ArabGuard check + Groq LLM (if safe)
 * Body: { user_input, system_prompt, level_id }
 * Returns: { blocked, reply, trace, final_decision, score_change }
 */
app.post("/api/game-turn", async (req, res) => {
  try {
    const { user_input, system_prompt } = req.body;

    // Step 1: ArabGuard
    const client = await getArabGuard();
    const guardResult = await client.predict("/universal_api", {
      user_input,
      system_prompt: system_prompt || "أنت مساعد ذكي.",
    });

    const [, trace, status_label] = guardResult.data;
    const final_decision = status_label?.label || "SAFE";
    const blocked = final_decision === "BLOCKED" || final_decision === "FLAG";

    if (blocked) {
      return res.json({
        blocked: true,
        reply: null,
        trace,
        final_decision,
        score_change: -10,
      });
    }

    // Step 2: Groq LLM (only if SAFE)
    const completion = await groq.chat.completions.create({
      model: "llama-3.3-70b-versatile",
      messages: [
        { role: "system", content: system_prompt },
        { role: "user", content: user_input },
      ],
      max_tokens: 500,
      temperature: 0.8,
    });

    const reply = completion.choices[0]?.message?.content || "مفيش رد.";

    res.json({
      blocked: false,
      reply,
      trace,
      final_decision,
      score_change: +5,
    });

  } catch (error) {
    console.error("Game turn error:", error);
    res.status(500).json({ error: error.message });
  }
});

// Health check
app.get("/health", (req, res) => {
  res.json({ status: "ok", arabguard: !!arabGuardClient });
});

const PORT = process.env.PORT || 3001;
app.listen(PORT, () => {
  console.log(`\n🛡️  ArabGuard Game Server running on port ${PORT}`);
  console.log(`   POST /api/arabguard  → ArabGuard check only`);
  console.log(`   POST /api/chat       → Groq LLM only`);
  console.log(`   POST /api/game-turn  → Combined (ArabGuard + Groq)\n`);
  // Pre-connect to ArabGuard on startup
  getArabGuard().catch(console.error);
});