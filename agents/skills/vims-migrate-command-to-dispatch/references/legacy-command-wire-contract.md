# Known VIMS legacy Command wire contract

Use this reference during discovery for every ordinary VIMS legacy `Command`. The infrastructure
shape below is a repository invariant. Confirm that the selected command follows it and record the
baseline once; do not rediscover the same wire contract for every migration.

## Standard path

```text
Command.CMD_<NAME> constant
        |
        v
client creates Command(constant) and adds command parameters
        |
        v
Cmd.process(command)
        |
        v
CommandProcessorImpl derives command.getName() + "CmdExecutor"
        |
        v
Spring resolves the matching <commandName>CmdExecutor bean
        |
        v
CmdExecutor receives the configured Command instance
```

The standard contract means the command-specific discovery work is limited to:

- the constant and its value;
- the production UI construction/dispatch call sites and their entry paths;
- parameter keys, runtime types, nullability, and any ignored or duplicated payloads;
- executor service/mapper/repository calls, result/error behavior, and side effects;
- tests and nearby Dispatch examples.

## Verify the baseline and deviations

Run focused searches sufficient to establish that the selected command uses the baseline:

```bash
rg -n "CMD_<NAME>|new Command\\(Command\\.CMD_<NAME>|Cmd\\.process" \
  src/main/java src/test/java
rg -n "<commandName>CmdExecutor|class .*CmdExecutor|CommandProcessorImpl" \
  src/main/java/au/gov/qld/des/vims/server
```

Escalate discovery only when one of these conditions is present:

- the command is constructed from a raw string or a nonstandard constant path;
- a proxy, store, abstract presenter, subclass, reflection path, or manual executor registration
  bypasses or supplements the standard path;
- the executor does not use the conventional Spring bean name;
- the command is handled by shared executor infrastructure or participates in a bridge that will
  outlive the selected migration;
- the command's parameter/result contract cannot be explained from its caller and executor.

If none applies, record the standard wire contract as confirmed and focus discovery on the
command-specific behavior ledger. Do not create a hard risk merely because dynamic executor
resolution exists; it is expected infrastructure. Create one only for a deviation or uncertainty.
