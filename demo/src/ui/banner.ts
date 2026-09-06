import type { Profile } from '../api';
import { ANSI_STYLES } from './styles';

/**
 * Prints a formatted startup banner displaying active configuration and detected profiles.
 */
export function printBanner(options: {
  apiUrl: string;
  llmModel: string;
  llmBaseUrl?: string;
  profiles: Profile[];
}): void {
  console.log();
  console.log(
    `${ANSI_STYLES.cyan}╭────────────────────────────────────────────────────────────╮${ANSI_STYLES.reset}`,
  );
  console.log(
    `${ANSI_STYLES.cyan}│${ANSI_STYLES.reset}              ${ANSI_STYLES.bold}Helomi Voice Assistant – Demo${ANSI_STYLES.reset}                 ${ANSI_STYLES.cyan}│${ANSI_STYLES.reset}`,
  );
  console.log(
    `${ANSI_STYLES.cyan}╰────────────────────────────────────────────────────────────╯${ANSI_STYLES.reset}`,
  );
  console.log(`  ${ANSI_STYLES.bold}API Server:${ANSI_STYLES.reset}  ${options.apiUrl}`);
  console.log(
    `  ${ANSI_STYLES.bold}LLM Model:${ANSI_STYLES.reset}   ${options.llmModel}${
      options.llmBaseUrl
        ? ` ${ANSI_STYLES.dim}(${options.llmBaseUrl})${ANSI_STYLES.reset}`
        : ''
    }`,
  );
  const profileList = options.profiles
    .map(
      (p) =>
        `${p.id}${p.isActive ? ` ${ANSI_STYLES.green}(active)${ANSI_STYLES.reset}` : ''}`,
    )
    .join(', ');
  console.log(
    `  ${ANSI_STYLES.bold}Profiles:${ANSI_STYLES.reset}    ${profileList || 'none'}`,
  );
  console.log(
    `${ANSI_STYLES.gray}──────────────────────────────────────────────────────────────${ANSI_STYLES.reset}`,
  );
  console.log(
    `${ANSI_STYLES.dim}Listening for speech events... Press Ctrl+C to stop.${ANSI_STYLES.reset}\n`,
  );
}
