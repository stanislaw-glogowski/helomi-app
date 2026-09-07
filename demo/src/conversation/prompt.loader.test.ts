import { describe, expect, it } from 'bun:test';
import { PromptLoader } from './prompt.loader';

describe('PromptLoader', () => {
  it('loads system message for alexa profile', async () => {
    const loader = new PromptLoader();
    const system = await loader.loadSystemMessage('alexa');

    expect(system).not.toBeNull();
    expect(system?.role).toBe('system');
    expect(typeof system?.content).toBe('string');
    // Content should contain both profile description and formatting instructions
    expect(system?.content).toContain('Profile: Alexa');
    expect(system?.content).toContain('Output Formatting');
    expect(system?.content).toContain('One Sentence Per Line');
  });

  it('returns null for a non-existent profile', async () => {
    const loader = new PromptLoader();
    const system = await loader.loadSystemMessage('non_existent_profile_id_12345');

    expect(system).toBeNull();
  });
});
