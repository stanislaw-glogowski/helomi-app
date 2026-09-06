import { join } from 'node:path';
import * as process from 'node:process';
import type { SystemModelMessage } from 'ai';

/**
 * Loads and combines assistant persona markdown files with TTS output formatting instructions.
 */
export class PromptLoader {
  static readonly ROOT_DIR = 'prompts';
  static readonly PROFILES_DIR = 'profiles';
  static readonly INSTRUCTIONS_FILE = 'instructions';

  private readonly rootPath: string;
  private instructions: string | undefined;

  constructor(options: { rootPath?: string } = {}) {
    const { rootPath } = options;

    if (rootPath) {
      this.rootPath = rootPath;
    } else {
      this.rootPath = join(process.cwd(), PromptLoader.ROOT_DIR);
    }
  }

  /**
   * Loads the persona description for a profile ID and appends output formatting rules.
   * Returns null if the profile prompt markdown file does not exist.
   */
  async loadSystemMessage(profileId: string): Promise<SystemModelMessage | null> {
    const content = await this.loadContent(join(PromptLoader.PROFILES_DIR, profileId));

    if (!content) {
      return null;
    }

    if (this.instructions === undefined) {
      this.instructions = (await this.loadContent(PromptLoader.INSTRUCTIONS_FILE)) ?? '';
    }

    return {
      role: 'system',
      content: `${content}\n\n${this.instructions}`,
    };
  }

  /**
   * Reads a markdown file from the prompt directory.
   */
  private async loadContent(name: string): Promise<string | null> {
    try {
      const file = Bun.file(join(this.rootPath, `${name}.md`));
      return await file.text().then((text) => text.trim());
    } catch {
      return null;
    }
  }
}
