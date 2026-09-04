import fs from "node:fs";
import path from "node:path";

export interface LoadedPrompt {
  profileId: string;
  prompt: string;
  source: string;
  isFallback: boolean;
}

const BUILTIN_DEFAULT_PROMPT =
  "You are a helpful and concise AI voice assistant. Answer directly, politely, and conversationally in 1-3 sentences without markdown formatting, code blocks, emojis, or reasoning tags.";

export class PromptLoader {
  private readonly promptDirs: string[];

  constructor(customDir?: string) {
    this.promptDirs = [
      ...(customDir ? [path.resolve(customDir)] : []),
      path.resolve(process.cwd(), "prompts"),
      path.resolve(import.meta.dirname, "prompts"),
    ];
  }

  /**
   * Loads system prompt for the specified profile from disk (`./prompts/<profile_id>.md`).
   * Falls back to `./prompts/default.md` if the specific profile prompt does not exist.
   * If neither exists, falls back to a built-in safe default prompt.
   */
  load(profileId: string): LoadedPrompt {
    // 1. Try finding <profile_id>.md
    const specificPath = this.resolveFile(`${profileId}.md`);
    if (specificPath) {
      try {
        const prompt = fs.readFileSync(specificPath, "utf-8").trim();
        if (prompt.length > 0) {
          return {
            profileId,
            prompt,
            source: specificPath,
            isFallback: false,
          };
        }
      } catch (err) {
        console.warn(`⚠️ Error reading prompt file ${specificPath}:`, err);
      }
    }

    // 2. Try falling back to default.md
    const defaultPath = this.resolveFile("default.md");
    if (defaultPath) {
      try {
        const prompt = fs.readFileSync(defaultPath, "utf-8").trim();
        if (prompt.length > 0) {
          return {
            profileId,
            prompt,
            source: defaultPath,
            isFallback: true,
          };
        }
      } catch (err) {
        console.warn(`⚠️ Error reading default prompt file ${defaultPath}:`, err);
      }
    }

    // 3. Fall back to built-in prompt
    return {
      profileId,
      prompt: BUILTIN_DEFAULT_PROMPT,
      source: "builtin-default",
      isFallback: true,
    };
  }

  private resolveFile(fileName: string): string | null {
    for (const dir of this.promptDirs) {
      const candidate = path.join(dir, fileName);
      if (fs.existsSync(candidate) && fs.statSync(candidate).isFile()) {
        return candidate;
      }
    }
    return null;
  }
}
