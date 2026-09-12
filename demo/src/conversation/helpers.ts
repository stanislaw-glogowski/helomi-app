/**
 * Cleans an LLM output line for TTS synthesis:
 * - Strips `<think>` tags and reasoning blocks
 * - Strips code blocks and inline markdown formatting
 * - Converts markdown links to plain text labels
 * - Preserves vocal tags in square brackets (e.g. `[laughter]`)
 * - Normalizes excessive spaces and trims
 */
export function cleanLine(raw: string): string {
  return raw
    .replace(/<think>[\s\S]*?<\/think>/gi, '')
    .replace(/```[\s\S]*?```/g, '')
    .replace(/[*_#`~>]/g, '')
    .replace(/\[([^\]]+)]\([^)]+\)/g, '$1')
    .replace(/\s+/g, ' ')
    .trim();
}

/**
 * Custom fetch wrapper for Ollama endpoints to disable thinking mode (`think: false`).
 */
export async function ollamaFetch(
  input: RequestInfo | URL,
  init?: RequestInit | undefined,
) {
  if (init?.body && typeof init.body === 'string') {
    try {
      const body = JSON.parse(init.body);
      body.think = false;
      return fetch(input, { ...init, body: JSON.stringify(body) });
    } catch {}
  }
  return fetch(input, init);
}
