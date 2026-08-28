# Settings Configuration

Helomi uses a hierarchical configuration system. The main settings file is located in the application's resources
directory:

- **macOS (default):** `~/Library/Application Support/Helomi/resources/settings.yml`
- **Explicit location:** `$HELOMI_HOME/resources/settings.yml`
- **Local workspace:** `./resources/settings.yml`

## File Format

Settings can be defined using YAML or JSON formats (e.g., `settings.yml` or `settings.json`).

## Overriding Settings

You can override specific settings without modifying the main configuration file by creating an override file in the
same directory:

- `settings.override.yml`
- `settings.override.json`

The application will automatically merge the override file with the base settings.

## Example Configuration

`settings.yml`:

```yaml
audio:
  sample_rate: 16000
  channels: 1

server:
  host: "127.0.0.1"
  port: 8000
```
