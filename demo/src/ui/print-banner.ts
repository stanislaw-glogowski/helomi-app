import type { Profile } from '../api';
import { colorize } from './colorize';
import { print } from './print';

/**
 * Prints a formatted startup banner displaying active configuration and detected profiles.
 */
export function printBanner(options: {
  apiUrl: string;
  llmModel: string;
  llmBaseUrl?: string;
  profiles: Array<Partial<Profile> & Pick<Profile, 'id' | 'isActive'>>;
}): void {
  print();
  print(['╭────────────────────────────────────────────────────────────╮', 'cyan']);
  print(
    ['│', 'cyan'],
    ['              Helomi Voice Assistant – Demo                 ', 'bold'],
    ['│', 'cyan'],
  );
  print(['╰────────────────────────────────────────────────────────────╯', 'cyan']);
  print(['  API Server:  ', 'bold'], [options.apiUrl, 'cyan']);
  print(
    ['  LLM Model:   ', 'bold'],
    [options.llmModel, 'cyan'],
    options.llmBaseUrl ? [` (${options.llmBaseUrl})`, 'dim'] : '',
  );

  const profileList = options.profiles
    .map((p) => `${p.id}${p.isActive ? ` ${colorize('(active)', 'green')}` : ''}`)
    .join(', ');
  print(['  Profiles:    ', 'bold'], profileList || 'none');
  print(['──────────────────────────────────────────────────────────────', 'gray']);
  print(['Listening for speech events... Press Ctrl+C to stop.\n', 'dim']);
}
