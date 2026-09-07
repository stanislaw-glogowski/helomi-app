import { describe, expect, it, spyOn } from 'bun:test';
import { Colorize } from './colorize';
import { print } from './print';

describe('print', () => {
  it('prints empty line when no arguments provided', () => {
    const logSpy = spyOn(console, 'log').mockImplementation(() => {});
    try {
      print();
      expect(logSpy).toHaveBeenCalledWith('');
    } finally {
      logSpy.mockRestore();
    }
  });

  it('prints plain strings and colorized parts concatenated', () => {
    const logSpy = spyOn(console, 'log').mockImplementation(() => {});
    try {
      print('prefix: ', ['important', 'bold', 'red'], ' postfix');
      expect(logSpy).toHaveBeenCalledWith(
        `prefix: ${Colorize.bold}${Colorize.red}important\x1b[0m postfix`,
      );
    } finally {
      logSpy.mockRestore();
    }
  });
});
