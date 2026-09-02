---
name: vims-command-to-dispatch
description: Convert one VIMS legacy Command flow at a time to typed Dispatch Action and ActionHandler code. Use when Codex is asked to migrate a specific VIMS Command, Cmd.process caller, CmdExecutor, CommandListLoadRpcProxy, or RpcPagingCommandProxy usage to the Dispatch/Action pattern in the qps/vims codebase.
---

# VIMS Command To Dispatch

## Scope

Migrate one legacy `Command` at a time. When the user explicitly requests several commands, repeat
the complete discovery, implementation, tests, and cleanup workflow sequentially for each command;
do not batch their payloads, handlers, cleanup, or validation into one ambiguous migration.

Treat the command as a user-visible flow, not just a server executor. A migration is only complete when all UI callers for that command have moved to Dispatch and the old command path is removed where it is no longer needed.

Exception: `findTasks` is already migrated for the Home screen. Its legacy `CMD_FIND_TASKS` path remains only because `CommandProcessorImpl.checkTasks()` still runs while other legacy Commands exist. Do not migrate `findTasks` as a normal command; leave it for final command-infrastructure cleanup.

## Discovery

Start from one command name, such as `findOrgUnit` or `saveReferenceType`.

1. Find the command constant in `src/main/java/au/gov/qld/des/vims/common/command/Command.java`.
2. Find every client caller:
   - `rg -n "CMD_<NAME>|new Command\\(Command\\.CMD_<NAME>|Cmd\\.process|CommandListLoadRpcProxy|RpcPagingCommandProxy" src/main/java/au/gov/qld/des/vims/client`
   - Include store providers, combo boxes, presenters, grids, and abstract base presenters.
3. Find the server executor:
   - `rg -n "class .*CmdExecutor|<commandName>CmdExecutor|CMD_<NAME>" src/main/java/au/gov/qld/des/vims/server/command`
   - `CommandProcessorImpl` resolves executors by `<commandName>CmdExecutor`.
4. Inspect command parameters and result shape:
   - Inputs usually come from `command.getParam(...)`.
   - Results usually go into `Command.KEY_RESULT`.
   - Paging uses `Command.KEY_PAGING_INFO`.
   - Loading policy uses `Command.KEY_LOADING_POLICY`.
   - Validation may use `ValidationMessages`, `ValidationException`, `KEY_ERROR_MESSAGES`, or result DTO fields.
5. Find nearby Dispatch examples in the same domain before creating new patterns:
   - Common actions: `src/main/java/au/gov/qld/des/vims/common/dispatch/<domain>`
   - Server handlers: `src/main/java/au/gov/qld/des/vims/server/dispatch/<domain>`
   - Tests: `src/test/java/au/gov/qld/des/vims/server/dispatch/<domain>`

Keep a short migration note listing the exact files and UI call sites found. Work only on the current
command; if the user explicitly requested several, queue the others and start each only after the
current command's cleanup and focused tests pass.

## Action Design

Create the Action under `common/dispatch/<domain>` and keep it typed.

- Use `Action<ResultType>` from `au.gov.qld.des.vims.common.dispatch.Action`.
- Use concrete GWT-serializable result classes. For lists, return a domain `AbstractListOf<T>` or `PageOf<T>` type rather than a raw `List`.
- Use concrete GWT-serializable collection fields such as `ArrayList` and `HashMap` in wire results.
  Let consumer APIs accept wildcard values such as `Map<K, ? extends List<V>>` when generic
  invariance would otherwise reject the concrete serialized shape.
- Use Lombok patterns already present in the repo: `@Getter`, private `@NoArgsConstructor`, `@AllArgsConstructor`, and `@Builder` where similar actions use builders.
- Turn command map parameters into explicit fields. Do not carry a `Command`, parameter map, or stringly typed payload into the Action.
- Follow the repository's audited JSpecify boundaries. Dispatch, DTO, and server packages normally
  remain explicitly `@NullUnmarked`; do not make a shared package or wire model `@NullMarked`
  without auditing its complete contract. Annotate every genuinely nullable field, constructor
  parameter, and result with `org.jspecify.annotations.Nullable`.
- Do not use Jakarta or Javax nullness annotations as substitutes for JSpecify. Preserve existing
  Jakarta/Javax annotations when they have runtime, Bean Validation, persistence, or framework
  meaning; a nullness migration must not silently change those semantics.
- In a deliberately audited class-level or package-level `@NullMarked` scope, omit redundant
  `@NonNull` annotations. Use narrow serialization-constructor suppressions when a framework-only
  no-arg constructor must temporarily violate normal field initialization invariants.
- Add a concise `toString()` with `Description.of(...)` when nearby actions do this for filtering/search actions.

Common mappings:

```text
command.getParam(SomeDto.KEY)        -> private SomeDto someDto
command.getParam(Command.KEY_SEARCH) -> private String query
command.getParam(Command.KEY_PAGING_INFO) -> private PagingInfo pagingInfo
command.getParam(Command.KEY_LOADING_POLICY) -> private String loadingPolicy
command.addParam(Command.KEY_RESULT, value) -> Action<ResultType> return value
```

For any mutation with expected validation failures—including create, update, and remove—prefer a
typed `GenericResult<Either<ValidationMessages, Success>>` wrapper like `StockItemResult`. The
concrete wrapper may be an action-specific nested `Result` while `Success` remains a separately
named domain result when that payload is shared or meaningful, for example
`CreateContactPoint.Result` containing either validation messages or `ContactPointSaveResult`.

For no-result commands, use `Action<Nothing>` and a `NothingActionHandler`.

## Handler Design

Create a handler under `server/dispatch/<domain>`.

- Extend `SimpleActionHandler<ActionType, ResultType>` for result-returning actions.
- Extend `NothingActionHandler<ActionType>` for no-result actions.
- Follow the handler stereotype already present in the repository. Use the current `@Component`
  convention while no custom `@DispatchHandler` exists; introducing a new stereotype is a separate
  infrastructure change and requires separate authorization.
- Do not make a handler final when Spring may proxy it, especially when it or its methods use
  `@Transactional`; this repository uses CGLIB subclass proxies.
- Use constructor injection with `@RequiredArgsConstructor(onConstructor_ = @Autowired)` or the exact local style.
- Preserve the old executor's service, repository, mapper, transaction, security, and validation behavior.
- When converting `ValidationException` into a typed result, catch only that expected exception;
  allow unexpected exceptions to propagate to standard Dispatch failure handling.
- Keep the transaction boundary outside the exception-to-result conversion. When a transactional
  service owns the mutation, do not wrap it in an outer handler transaction: let the service call
  cross its Spring proxy, roll back on `ValidationException`, and only then convert the exception
  into a left result in the handler. If the handler genuinely owns the transaction, do not catch
  the exception before that transaction has completed; refactor the boundary before returning it as
  data.
- Use `ExecutionContext.execute(...)` or `executeRequired(...)` only when composing multiple Actions inside one operation.
- Do not register handlers manually. `DispatchConfiguration` discovers all `ActionHandler` beans from the Spring context.

Port behavior first; improve structure only when the current migration needs it.

## Client Migration

Replace only the selected command's UI call sites.

- Direct `Cmd.process(...)` calls usually become `dispatch.execute(new Action(...), result -> ...)`.
- Preserve mask text by using `dispatch.with(uiManager.maskDuringDispatch(view, "...")).execute(...)` where the command used `CommandAsyncCallback` masking.
- Preserve default failure behavior unless the old callback had custom failure handling.
- Branch expected validation from the typed result in the normal success callback. Keep unexpected
  failures on the standard Dispatch failure path; do not retain a presenter-specific cause-chain
  search for `ValidationDispatchException` after validation has become result data.
- Route validation to the view that owns the affected interaction. A modal create/edit flow should
  keep its editor open and display the messages there; a mutation without an editor, such as grid
  removal, should display them through the hosting view.
- Inject or pass `DispatchAsync` following the presenter's existing dependency style.
- For list loaders, replace `CommandListLoadRpcProxy` with `ActionListLoadProxy`.
- For paged grids, replace `RpcPagingCommandProxy` with `ActionPagingProxy`.
- For action-backed combos/search boxes, prefer existing support classes such as `BaseActionComboBox` and `BaseActionSearchBox`.
- Preserve loader refresh, sorting, filters, paging, selection behavior, event firing, and validation display.
- After replacing command callbacks with direct Dispatch results or narrow presenter callbacks,
  search for internal events that have become orphaned and remove their registrations and types only
  after proving no callers remain.

Do not migrate adjacent commands in the same presenter unless they are inseparable from the selected command's UI path.

## Cleanup

After the selected command's client callers have moved:

1. Search for remaining production references to the command constant, command name, and executor.
2. Remove the `CmdExecutor` only when no production caller still reaches it.
3. Remove the command constant only when no production code and no tests still depend on it.
4. Remove stale command imports and dead helper fields.
5. Remove command-specific internal events or callbacks made obsolete by the typed result after
   proving that no other production caller uses them.
6. Leave shared command infrastructure in place unless the current task is the final infrastructure cleanup.

Use targeted searches before deleting anything:

```bash
rg -n "CMD_<NAME>|<commandName>|<CommandName>CmdExecutor|new Command\\(|Cmd\\.process|CommandListLoadRpcProxy|RpcPagingCommandProxy" src/main/java src/test/java
```

Never remove `CMD_FIND_TASKS`, `FindTasksCmdExecutor`, or the `CommandProcessorImpl.checkTasks()` bridge during an ordinary command migration.

## Tests

Add or update tests for the one command being migrated.

- Add focused handler unit tests under `src/test/java/au/gov/qld/des/vims/server/dispatch/<domain>`.
- Mirror the old executor's important branches: successful load/save, not-found behavior, validation messages, paging/filtering, and transaction-sensitive composition.
- For a typed validation result, test the right/success value, the left/validation value, and that an
  unexpected exception still propagates rather than being converted.
- Update presenter, proxy, or store-provider tests when the UI caller changes from Command to Dispatch.
- Cover custom Dispatch success and failure behaviour in presenter tests. Standard centralized
  Dispatch failure handling needs no presenter-specific failure test when the presenter adds no
  custom failure branch.
- For `ActionPagingProxy` or `ActionListLoadProxy` usage, verify empty optional action behavior, paging/sort translation, and stale-result guards when relevant.
- Run the narrowest useful test first, then the full suite from the repository root using Java 22
  only and no Surefire forking: `mvn -DforkCount=0 test`. Use `-DforkCount=0` for focused tests too.
  Verify Maven's VM with `mvn -version`, not standalone `java -version`.
- Run `mvn -DskipTests compile gwt:compile` after introducing or changing a nested generic result so
  GWT RPC serialization and linking are verified, not only javac compilation.

If tests cannot be run, report the exact reason and the command that should be run.

## Completion Check

Before final response for a one-command migration, confirm:

- The selected command's UI behavior is still reachable from the same screen or widget.
- All inputs previously placed into the `Command` are represented on the Action.
- The handler returns the same successful data shape and validation/error behavior.
- Expected validation is returned as typed data only after the mutation transaction has rolled back;
  unexpected failures still reach standard Dispatch failure handling.
- The UI preserves masks, loading, paging, sorting, filtering, events, and messages.
- No production references remain to the selected command's old client caller or executor, unless a deliberate bridge remains and is documented.
- No unrelated commands were migrated.
- New or changed packages retain an explicit `package-info.java`: audited client packages are
  `@NullMarked`, while Dispatch, DTO, server, mapper, entity, and configuration packages remain
  `@NullUnmarked` until separately audited.
- Every legitimate nullable value introduced by the migration has an explicit JSpecify
  `@Nullable` annotation; redundant `@NonNull` annotations were not added in null-marked scopes.
