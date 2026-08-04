# Getting started

## Requirements

Helomi targets Apple Silicon Macs. Install Python 3.14, uv, Xcode command-line
tools, and Swift. A real session additionally needs microphone permission,
audio output, network access for initial downloads, and enough unified memory
for the chosen models.

## Initialize a checkout

```bash
make init
```

The command builds the native audio helper, synchronizes dependencies, copies
missing versioned defaults to the selected Helomi data directory, downloads the
OpenWakeWord assets, and downloads models used by the default profile. It does
not overwrite files that are already there.

By default installation uses the checkout-local `.helomi` directory. Set
`HELOMI_HOME` before initialization to use another data directory:

```bash
HELOMI_HOME=/path/to/helomi-data make init
```

## Start Helomi

```bash
make run-cli
```

For the macOS menu-bar frontend, run:

```bash
make run-desktop
```

Select a valid profile in the terminal UI. The default profile is configured in
locale settings; if it is unavailable, the first valid profile is used. Use
`uv run helomi-cli --language pl-PL --profile henry` (or the same flags with
`helomi-desktop`) for a one-run selection. Say the
profile's configured wake-word label, speak your turn, then wait for the spoken
reply. Speaking while playback is active requests an interruption.

If setup or startup fails, start with [troubleshooting](troubleshooting.md) and
run the [audio diagnostic](development/diagnostics.md).
