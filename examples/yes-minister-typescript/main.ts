import "dotenv/config";
import { generateText } from "ai";
import { createOpenAI } from "@ai-sdk/openai";

// -----------------------------------------------------------------------------
// Configuration
// -----------------------------------------------------------------------------
const SERVER_URL = process.env.HELOMI_SERVER_URL ?? "http://127.0.0.1:4356";
const PROFILE_ID = process.env.HELOMI_PROFILE_ID ?? "default";
const SOURCE_LANGUAGE = process.env.SOURCE_LANGUAGE ?? "Polish";
const TARGET_LANGUAGE = process.env.TARGET_LANGUAGE ?? "English";

const OPENAI_BASE_URL = process.env.OPENAI_BASE_URL || undefined;
const OPENAI_API_KEY = process.env.OPENAI_API_KEY || "ollama";
const MODEL_NAME = process.env.LLM_MODEL ?? "gpt-4o-mini";

// Strict system prompt prohibiting reasoning monologue and markdown
const SYSTEM_PROMPT = `You are Sir Humphrey Appleby from "Yes, Minister" acting as a seasoned political orator and translator.
The user will provide spoken text in ${SOURCE_LANGUAGE}.
1. Translate the underlying meaning into ${TARGET_LANGUAGE}.
2. Rephrase it as a distinguished, diplomatic politician would say it (eloquent, strategic, courteous, and pompous).
3. Do NOT think, reason, or output <think> tags. Output ONLY the final spoken statement without quotes or markdown.`;

// OpenAI-compatible client with reasoning explicitly disabled for Ollama (think: false)
const openai = createOpenAI({
  baseURL: OPENAI_BASE_URL,
  apiKey: OPENAI_API_KEY,
  fetch: async (url, init) => {
    if (init?.body && typeof init.body === "string") {
      try {
        const body = JSON.parse(init.body);
        body.think = false; // Disable reasoning in Ollama / compatible APIs
        init = { ...init, body: JSON.stringify(body) };
      } catch {}
    }
    return fetch(url, init);
  },
});

const model = openai(MODEL_NAME);

/**
 * Translates and rephrases input text into political rhetoric, stripping reasoning tags.
 */
async function translateToPoliticalSpeech(userText: string): Promise<string> {
  const { text } = await generateText({
    model,
    system: SYSTEM_PROMPT,
    prompt: userText,
  });
  return text.replace(/<think>[\s\S]*?<\/think>/gi, "").trim();
}

/**
 * Sends synthesized speech text back to Helomi TTS.
 */
async function speak(text: string, sessionId: string): Promise<void> {
  const res = await fetch(`${SERVER_URL}/api/v1/speech`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-session-id": sessionId,
    },
    body: JSON.stringify({
      type: "say_text",
      profile_id: PROFILE_ID,
      text,
    }),
  });

  if (!res.ok) {
    console.error(`❌ Failed to send speech command: ${res.statusText}`);
  } else {
    console.log("✅ Statement successfully transmitted to Helomi speaker.\n");
  }
}

// -----------------------------------------------------------------------------
// Main Application Loop
// -----------------------------------------------------------------------------
async function main() {
  console.log("==========================================================");
  console.log("🏛️  Yes, Minister! – Helomi Speech Translator");
  console.log("==========================================================");
  console.log(`📡 Helomi: ${SERVER_URL} (${PROFILE_ID})`);
  console.log(`🧠 Model:  ${MODEL_NAME} (${OPENAI_BASE_URL ?? "https://api.openai.com/v1"})`);
  console.log(`🌐 Mode:   ${SOURCE_LANGUAGE} -> ${TARGET_LANGUAGE}`);
  console.log("==========================================================\n");

  const streamUrl = `${SERVER_URL}/api/v1/speech?profile_id=${encodeURIComponent(PROFILE_ID)}`;
  const response = await fetch(streamUrl);

  if (!response.ok || !response.body) {
    throw new Error(`Connection failed: HTTP ${response.status} ${response.statusText}`);
  }

  let sessionId = response.headers.get("x-session-id");
  console.log("🟢 Connected to Helomi speech stream. Awaiting voice input...");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split("\n\n");
    buffer = events.pop() ?? "";

    for (const eventBlock of events) {
      const eventType = eventBlock.match(/^event:\s*(.+)$/m)?.[1]?.trim();
      const dataMatch = eventBlock.match(/^data:\s*(.+)$/m)?.[1]?.trim();
      if (!eventType || !dataMatch) continue;

      const payload = JSON.parse(dataMatch);

      if (eventType === "session" && payload.session_id) {
        sessionId = payload.session_id;
        console.log(`🔑 Active Helomi session established: ${sessionId}`);
      }

      if (eventType === "transcription_ready" && payload.text?.trim()) {
        const userText = payload.text.trim();
        console.log(`\n🎙️  [Original Speech]: "${userText}"`);

        console.log("🎩 Rephrasing for the House of Commons...");
        const statement = await translateToPoliticalSpeech(userText);
        console.log(`📢 [Political Statement]: "${statement}"`);

        if (sessionId) {
          await speak(statement, sessionId);
        } else {
          console.error("❌ Cannot dispatch speech command: missing session ID");
        }
      }
    }
  }
}

// -----------------------------------------------------------------------------
// Entrypoint Execution
// -----------------------------------------------------------------------------
main().catch((err) => {
  console.error("❌ Fatal Error:", err);
  process.exit(1);
});
