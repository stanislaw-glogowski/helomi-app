import { describe, expect, it, spyOn } from 'bun:test';
import { printBanner } from './print-banner';

describe('banner', () => {
  it('prints banner with profiles and llmBaseUrl', () => {
    const logSpy = spyOn(console, 'log').mockImplementation(() => {});
    try {
      printBanner({
        apiUrl: 'http://127.0.0.1:4356',
        llmModel: 'gpt-5.6-luna',
        llmBaseUrl: 'http://localhost:11434/v1',
        profiles: [
          { id: 'alexa', name: 'Alexa', isActive: true },
          { id: 'gizmo', name: 'Gizmo', isActive: false },
        ],
      });

      expect(logSpy).toHaveBeenCalled();
    } finally {
      logSpy.mockRestore();
    }
  });

  it('prints banner with empty profiles list and no llmBaseUrl', () => {
    const logSpy = spyOn(console, 'log').mockImplementation(() => {});
    try {
      printBanner({
        apiUrl: 'http://127.0.0.1:4356',
        llmModel: 'gpt-5.6-luna',
        profiles: [],
      });

      expect(logSpy).toHaveBeenCalled();
    } finally {
      logSpy.mockRestore();
    }
  });
});
