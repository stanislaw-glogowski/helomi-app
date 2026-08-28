import "dotenv/config";
import { generateText } from "ai";
import { openai } from "@ai-sdk/openai";
import { createOllama } from "ollama-ai-provider";

/**
 * =============================================================================
 * "Yes, Minister!" – Helomi Speech-to-Political-Discourse Translator
 * =============================================================================
 *
 * This example listens to real-time voice transcriptions from the Helomi server,
 * translates the spoken input, and refines it into eloquent, diplomatic,
 * and pompous political rhetoric ("Yes, Minister" style) before commanding
 * Helomi to synthesize and speak the response aloud.
 */

// -----------------------------------------------------------------------------
// Configuration (defaults overridable via environment variables)
// -----------------------------------------------------------------------------
const SERVER_URL = process.env.HELOMI_SERVER_URL ?? "http://127.0.0.1:4356";
const PROFILE_ID = process.env.HELOMI_PROFILE_ID ?? "default";
const SOURCE_LANGUAGE = process.env.SOURCE_LANGUAGE ?? "Polish";
const TARGET_LANGUAGE = process.env.TARGET_LANGUAGE ?? "English";

const LLM_PROVIDER = process.env.LLM_PROVIDER ?? "openai"; // "openai" | "ollama"
const OLLAMA_BASE_URL = process.env.OLLAMA_BASE_URL ?? "http://127.0.0.1:11434/api";
const MODEL_NAME =
  process.env.LLM_MODEL ?? (LLM_PROVIDER === "ollama" ? "llama3.2" : "gpt-4o-mini");

// System prompt defining the "Yes, Minister" translation and political transformation
const SYSTEM_PROMPT = `You are Sir Humphrey Appleby from "Yes, Minister" acting as a seasoned political orator and translator.
The user will provide spoken text in ${SOURCE_LANGUAGE}.
1. Translate the underlying meaning into ${TARGET_LANGUAGE}.
2. Rephrase it as a distinguished, diplomatic politician would say it (eloquent, strategic, courteous, and pompous).
3. Return ONLY the final spoken statement. Do not add quotes, markdown formatting, or explanations.`;

// Initialize Ollama provider instance
const ollama = createOllama({ baseURL: OLLAMA_BASE_URL });

/**
 * Resolves the appropriate language model based on the configured provider.
 */
function getLanguageModel() {
  if (LLM_PROVIDER === "ollama") {
    return ollama(MODEL_NAME);
  }
  return openai(MODEL_NAME);
}

// -----------------------------------------------------------------------------
// Main Application Loop
// -----------------------------------------------------------------------------
async function main() {
  console.log("==========================================================");
  console.log("🏛️  Yes, Minister! – Helomi Speech Translator");
  console.log("==========================================================");
  console.log(`📡 Connecting to Helomi at ${SERVER_URL} (profile: ${PROFILE_ID})`);
  console.log(`🧠 LLM Engine: ${LLM_PROVIDER} [${MODEL_NAME}]`);
  console.log(`🌐 Translation: ${SOURCE_LANGUAGE} -> ${TARGET_LANGUAGE} (Political Tone)`);
  console.log("==========================================================\n");

  // 1. Establish Server-Sent Events (SSE) stream connection with Helomi
  const streamUrl = `${SERVER_URL}/api/v1/speech?profile_id=${encodeURIComponent(PROFILE_ID)}`;
  const response = await fetch(streamUrl);

  if (!response.ok || !response.body) {
    throw new Error(`Connection failed: HTTP ${response.status} ${response.statusText}`);
  }

  // Session ID can come from the response header or the initial 'session' event
  let sessionId = response.headers.get("x-session-id");
  console.log("🟢 Connected to Helomi speech stream. Awaiting voice input...");

  // 2. Stream Reader Loop
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    // SSE events are delimited by double newlines (\n\n)
    const events = buffer.split("\n\n");
    buffer = events.pop() ?? "";

    for (const eventBlock of events) {
      const lines = eventBlock.split("\n");
      let eventType = "";
      let eventData = "";

      for (const line of lines) {
        if (line.startsWith("event: ")) eventType = line.slice(7).trim();
        else if (line.startsWith("data: ")) eventData = line.slice(6).trim();
      }

      if (!eventType || !eventData) continue;

      const payload = JSON.parse(eventData);

      // Handle session acquisition
      if (eventType === "session" && payload.session_id) {
        sessionId = payload.session_id;
        console.log(`🔑 Active Helomi session established: ${sessionId}`);
      }

      // Handle real-time speech transcription events
      if (eventType === "transcription_ready" && payload.text) {
        const userText = payload.text.trim();
        if (!userText) continue;

        console.log(`\n🎙️  [Original Speech]: "${userText}"`);

        // 3. Translate and transform the message into political rhetoric
        console.log("🎩 Rephrasing for the House of Commons...");
        const { text: politicalTranslation } = await generateText({
          model: getLanguageModel(),
          system: SYSTEM_PROMPT,
          prompt: userText,
        });

        console.log(`📢 [Political Statement]: "${politicalTranslation}"`);

        // 4. Send synthesized text back to Helomi TTS
        if (!sessionId) {
          console.error("❌ Cannot dispatch speech command: missing session ID");
          continue;
        }

        const speakResponse = await fetch(`${SERVER_URL}/api/v1/speech`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "x-session-id": sessionId,
          },
          body: JSON.stringify({
            type: "say_text",
            profile_id: PROFILE_ID,
            text: politicalTranslation,
          }),
        });

        if (!speakResponse.ok) {
          console.error(`❌ Failed to send speech command: ${speakResponse.statusText}`);
        } else {
          console.log("✅ Statement successfully transmitted to Helomi speaker.\n");
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
