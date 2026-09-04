# Examples

Here are some common usage examples for configuring and running Helomi.

## Running a Specific Profile

To run the CLI with a custom profile named `my_assistant`:

```bash
uv run helomi-cli parrot my_assistant
```

## Overriding the Server Port

Create `settings.override.yml` in your `.helomi` directory:

```yaml
server:
  host: "0.0.0.0"
  port: 8080
```

Then start the server:

```bash
uv run helomi-cli serve
```

## Disabling Wake-Word

If you want to disable wake-word detection globally, update your `settings.override.yml`:

```yaml
wakeword:
  adapter: null
```

## Setting a Default Profile

To ensure the CLI or Server always defaults to a specific profile, you can set it in `settings.override.yml`:

```yaml
profile:
  default: "my_assistant"
```
