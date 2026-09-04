import "dotenv/config";
import { generateText } from "ai";
import { createOpenAI } from "@ai-sdk/openai";
import { ProfileMemoryManager } from "./memory.js";
import { PromptLoader } from "./prompt.js";

// -----------------------------------------------------------------------------
// Configuration
// -----------------------------------------------------------------------------
const SERVER_URL = process.env.HELOMI_SERVER_URL ?? "http://127.0.0.1:4356";
const TARGET_PROFILE = process.env.HELOMI_PROFILE_ID?.trim() || undefined;
const MAX_MEMORY_MESSAGES = Math.max(1, parseInt(process.env.MAX_MEMORY_MESSAGES ?? "10", 10));

const OPENAI_BASE_URL = process.env.OPENAI_BASE_URL || undefined;
const OPENAI_API_KEY = process.env.OPENAI_API_KEY || "ollama";
const MODEL_NAME = process.env.LLM_MODEL ?? "gpt-4o-mini";

// -----------------------------------------------------------------------------
// Components Initialization
// -----------------------------------------------------------------------------
const memory = new ProfileMemoryManager(MAX_MEMORY_MESSAGES);
const promptLoader = new PromptLoader();

// OpenAI-compatible client with reasoning explicitly disabled for Ollama (think: false)
const openai = createOpenAI({
  baseURL: OPENAI_BASE_URL,
  apiKey: OPENAI_API_KEY,
  fetch: async (url, init) => {
    if (init?.body && typeof init.body === "string") {
      try {
        const body = JSON.parse(init.body);
        body.think = false; // Disable reasoning monologue in Ollama / compatible APIs
        init = { ...init, body: JSON.stringify(body) };
      } catch {}
    }
    return fetch(url, init);
  },
});

const model = openai(MODEL_NAME);

/**
 * Strips reasoning tokens and markdown formatting unsuited for speech synthesis.
 */
function cleanSpeechText(rawText: string): string {
  return rawText
    .replace(/<think>[\s\S]*?<\/think>/gi, "")
    .replace(/```[\s\S]*?```/g, "")
    .replace(/[*_#`~>]/g, "")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * Sends synthesized speech text back to Helomi TTS.
 */
async function speak(text: string, profileId: string, sessionId: string): Promise<void> {
  const res = await fetch(`${SERVER_URL}/api/v1/speech`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-session-id": sessionId,
    },
    body: JSON.stringify({
      type: "say_text",
      profile_id: profileId,
      text,
    }),
  });

  if (!res.ok) {
    console.error(`❌ [${profileId}] Failed to send speech command: ${res.statusText}`);
  } else {
    console.log(`✅ [${profileId}] Statement transmitted to Helomi speaker.\n`);
  }
}

/**
 * Discovers loaded profiles from Helomi server.
 */
async function discoverProfiles(): Promise<string[]> {
  if (TARGET_PROFILE) {
    return [TARGET_PROFILE];
  }

  try {
    const res = await fetch(`${SERVER_URL}/api/v1/profile`);
    if (res.ok) {
      const data = (await res.json()) as Array<{ id: string; name: string; is_active: boolean }>;
      if (Array.isArray(data) && data.length > 0) {
        return data.map((p) => p.id);
      }
    }
  } catch (err) {
    console.warn(`⚠️ Could not query /api/v1/profile (${(err as Error).message}), defaulting to 'default'`);
  }

  return ["default"];
}

/**
 * Manages an active SSE connection for a specific profile.
 */
async function subscribeToProfile(profileId: string): Promise<void> {
  const streamUrl = `${SERVER_URL}/api/v1/speech?profile_id=${encodeURIComponent(profileId)}`;
  let sessionId: string | null = null;

  while (true) {
    try {
      console.log(`📡 [${profileId}] Connecting to Helomi stream...`);
      const response = await fetch(streamUrl);

      if (!response.ok || !response.body) {
        throw new Error(`HTTP ${response.status} ${response.statusText}`);
      }

      sessionId = response.headers.get("x-session-id");
      console.log(`🟢 [${profileId}] Stream connected (Session: ${sessionId ?? "pending"})`);

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

          let payload: Record<string, any>;
          try {
            payload = JSON.parse(dataMatch);
          } catch {
            continue;
          }

          if (eventType === "session" && payload.session_id) {
            sessionId = payload.session_id;
            console.log(`🔑 [${profileId}] Session confirmed: ${sessionId}`);
          }

          if (eventType === "profile_activated") {
            console.log(`🔔 [${profileId}] Voice profile activated`);
          }

          if (eventType === "profile_deactivated") {
            console.log(`🔕 [${profileId}] Voice profile deactivated`);
          }

          if (eventType === "transcription_ready" && payload.text?.trim()) {
            const userText = payload.text.trim();
            console.log(`\n🎙️  [${profileId}] User: "${userText}"`);

            // 1. Load prompt dynamically from disk (with fallback)
            const promptInfo = promptLoader.load(profileId);
            console.log(
              `📄 [${profileId}] Prompt: ${promptInfo.source} ${promptInfo.isFallback ? "(fallback)" : ""}`
            );

            // 2. Fetch isolated profile conversation memory
            const history = memory.getMessages(profileId);
            console.log(`🧠 [${profileId}] ${memory.getSummary(profileId)}`);

            // 3. Generate response with LLM
            console.log(`💭 [${profileId}] Generating response using ${MODEL_NAME}...`);
            try {
              const { text } = await generateText({
                model,
                system: promptInfo.prompt,
                messages: [
                  ...history,
                  { role: "user", content: userText },
                ],
              });

              const reply = cleanSpeechText(text);
              console.log(`🤖 [${profileId}] Assistant: "${reply}"`);

              // 4. Update memory with both user turn and assistant reply (capped at maxMessages)
              memory.addUserMessage(profileId, userText);
              memory.addAssistantMessage(profileId, reply);
              console.log(`🧠 [${profileId}] Updated: ${memory.getSummary(profileId)}`);

              // 5. Send speech synthesis command back to Helomi
              if (sessionId) {
                await speak(reply, profileId, sessionId);
              } else {
                console.error(`❌ [${profileId}] Missing session ID, cannot speak response.`);
              }
            } catch (llmErr) {
              console.error(`❌ [${profileId}] LLM generation failed:`, llmErr);
            }
          }
        }
      }

      console.warn(`⚠️ [${profileId}] SSE connection ended. Reconnecting in 3 seconds...`);
    } catch (err) {
      console.error(`❌ [${profileId}] SSE error: ${(err as Error).message}. Reconnecting in 3s...`);
    }

    await new Promise((resolve) => setTimeout(resolve, 3000));
  }
}

// -----------------------------------------------------------------------------
// Application Lifecycle
// -----------------------------------------------------------------------------
async function main() {
  console.log("==========================================================");
  console.log("🧠 Helomi Profile-Based Assistant with Memory");
  console.log("==========================================================");
  console.log(`📡 Helomi:  ${SERVER_URL}`);
  console.log(`🤖 Model:   ${MODEL_NAME} (${OPENAI_BASE_URL ?? "https://api.openai.com/v1"})`);
  console.log(`💾 Memory:  Max ${MAX_MEMORY_MESSAGES} messages per profile`);
  console.log(`📁 Prompts: ./prompts/<profile_id>.md (fallback to default.md)`);
  console.log("==========================================================\n");

  const profileIds = await discoverProfiles();
  console.log(`🎯 Active listener profiles: [${profileIds.join(", ")}]\n`);

  // Subscribe to all target profiles concurrently
  await Promise.all(profileIds.map((id) => subscribeToProfile(id)));
}

main().catch((err) => {
  console.error("❌ Fatal application error:", err);
  process.exit(1);
});
