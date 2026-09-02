---
name: gwt-migrate-presenter
description: Migrate existing VIMS GWT presenter/view pairs to an interface-first View/ViewImpl design with plain or framework-backed injected presenters, Dagger wiring, and optional event-manager integration. Use when Codex needs to split legacy concrete views, move presenters away from abstract hierarchies, migrate composite presenter trees, or remove GWT/GXT internals from presenters.
---

# GWT Presenter/View Migration (VIMS)

Migrate one existing presenter/view pair at a time toward an interface-first, composition-first
shape like `Login` and `Home`:
- plain injected final presenter when no framework presenter contract is consumed
- direct `Presenter` implementation only when callers actually use that contract
- thin framework host such as `BasePresenter<YourView>` only when it supplies required behaviour
- public `YourView` interface
- concrete `YourViewImpl`
- Dagger module binding for the interface
- Dagger-created presenter, including assisted factory wiring when runtime arguments such as `parent`,
  `context`, or `eventManager` are required
- event-manager or provider wiring where the presenter is created indirectly

Read `references/target-patterns.md` for the target shape and `references/stock-code-edit.md` when the migration involves editor-backed forms, validation, or partial migration patterns.

## Migration Principles

Treat these as defaults, not suggestions:
- Keep GWT/GXT-specific code out of presenters where a view abstraction is practical.
- Keep business logic out of views.
- Make the presenter talk only to a stable, public view API that hides view internals and widget types.
- Make the view independent of the presenter. Expose lambda registration points for UI-driven events, reactions, and request triggers.
- Treat inherited presenter and view bases as thin framework shells only, not as the home for
  feature workflow.
- Do not leave migrated classes extending feature-rich legacy bases such as `AbstractReportPresenter`
  or `AbstractReportView`. Pull the required behaviour down into the concrete presenter and view, then
  decide later whether any of it is genuinely reusable.
- Make the execution order obvious from the concrete presenter and view implementation.
- Make presenter construction Dagger-first by default. Inject the view through Dagger as well.
- Keep `AppResources.INSTANCE` out of presenter state, model objects, tree nodes, and static
  initialization. Inject resources into the view and assign visual resources there.
- When runtime values such as `parent`, `context`, or `eventManager` are required, use assisted
  injection plus a Dagger factory rather than manual `new`.
- If a non-Dagger caller still needs to create or access the presenter or presenter factory, add the
  smallest possible `@Deprecated` `AppEnvironment` accessor that forwards to `AppComponent`.
- If shared behaviour is genuinely reusable, extract it into a helper, utility, service, or other
  dependency rather than a richer base presenter or base view.
- Follow the repository JSpecify policy while changing APIs. Keep audited client packages explicitly
  `@NullMarked` in `package-info.java`, annotate every legitimately nullable field, parameter, and
  return type with JSpecify `@Nullable`, and omit redundant `@NonNull` inside a null-marked scope.
- Finish each migration by creating or updating exhaustive presenter unit tests in TestNG.

## Composite Presenters and Child Placement

For a presenter that coordinates tab, panel, or wizard children:
- Migrate leaf presenters before their parent coordinator.
- Do not require a parent presenter to obtain child views through `getView()` merely to place them.
- Let the composite view create its child containers and register instance-owned `UiSlotKey` values
  during construction. Expose the opaque keys to the parent presenter, not the containers or widgets.
- Construct the composite view before its child presenters. Pass each target `UiSlotKey` into the
  child presenter's assisted factory, with the slot key first among assisted parameters.
- Treat placement as immutable construction context when the child will always occupy one slot.
  Pass the slot key from the child presenter into its assisted view factory; the completed view may
  mount itself with `UiManager.requireSlot(slotKey).setWidget(this)` at the end of construction.
- A Dagger `@AssistedFactory` must return the concrete `@AssistedInject` type. When the presenter
  should depend on an interface-returning factory, adapt the generated implementation factory with
  a small `@Provides` method and test that every assisted argument is forwarded in order.
- Presenter-owned `TreeStore` and `ListStore` instances are acceptable model state. Pass the store
  into the view for rendering while keeping grids, render readiness, selection visuals, and layout
  mechanics inside the view implementation.
- Do not pass a generic parent, `EventManager`, `UIConfig`, or context into a child unless it is used.
  Prefer narrow callbacks for child-to-parent requests and typed feature configuration for genuine
  runtime settings.
- When a composite parent needs to coordinate or mock a child, prefer a narrow child-presenter
  contract. If an existing final child has no contract, exercise the real child with a stubbed view
  rather than weakening production finality for a mocking framework.

## Quick Workflow

1. Identify the migration shape
- **Fully legacy pair**: presenter extends a legacy base and the view is a concrete class with no interface.
- **Partial migration**: the view already has an interface or module binding, but the presenter still knows too much about UI details.
- **Event-driven/bootstrap presenter**: the presenter is created through an event manager or app startup path and needs provider wiring updates.
- Identify which parts of the current sequence are hidden in legacy parent classes before changing
  the public API.

2. Classify the view host
- **Window flow**: prefer `AbstractWindowView`.
- **Content panel flow**: prefer `AbstractContentPanelView`.
- Keep the existing host if the view already fits one cleanly. Do not churn layout inheritance
  unless it helps the migration.
- Do not treat the host base class as the right place for feature orchestration.

3. Extract the public view API from presenter needs
- Start from what the presenter needs to do, not from what widgets exist.
- Keep names imperative and domain-oriented, for example `display`, `showError`, `editStockCode`, `setTasks`, `makeSapCodeMandatory`.
- Prefer callbacks such as `onSave`, `onCancel`, `onSelectionChanged`, `onRefreshRequested`.
- Do not expose `TextButton`, `Grid`, `ComboBox`, editor drivers, `HandlerRegistration`, or other internal UI types through the view interface.
- While extracting the API, also identify any sequence or branching currently hidden in base-class
  hooks so it can be made explicit in the concrete implementation.
- Inspect static helpers and DTO transformations in the old view. Move business transformations to
  the presenter or a narrow collaborator even when they happen to operate on view-owned records.
- For GWT-serializable results with concrete collection fields such as `ArrayList`, let consumer APIs
  accept wildcard collection values, for example `Map<K, ? extends List<V>>`, rather than relying on
  invalid generic covariance or adding unnecessary copies.

4. Rename the legacy concrete view when needed
- If a concrete class already uses the final `FooView` name, rename it to `FooViewImpl`.
- Introduce a new `FooView` interface with only the presenter-facing API.
- Keep any editor bindings, widget fields, and GWT/GXT wiring inside `FooViewImpl`.

5. Migrate the presenter
- Prefer a plain final class when no caller consumes `Presenter` and no framework lifecycle is
  required. Implement `Presenter` directly only when the contract is genuinely consumed. Use
  `BasePresenter<FooView>` only when it remains a thin framework host with required behaviour.
- Use `@Inject` or `@AssistedInject` constructor injection and store dependencies as `final` fields.
- Move UI wiring into `initUI`.
- Return the interface type from `getView()` only when a caller genuinely needs the view. Do not add
  `getView()`, `getContext()`, or `getEventManager()` solely to satisfy a convention.
- Remove presenter dependencies on `SelectEvent`, `NativeEvent`, widget classes, editor drivers, and concrete view internals unless there is no practical abstraction.
- Pull feature-specific sequence and branching down out of legacy parent classes before deciding
  what, if anything, should be extracted for reuse.
- Do not instantiate `FooViewImpl` or other dependencies inside the presenter constructor.
- If the presenter needs runtime arguments such as `parent`, `context`, or `eventManager`, define an
  assisted `Factory` and have Dagger create the presenter through that factory.
- If the presenter still needs reusable support such as validation flow, loader wiring, masking, or
  report orchestration, prefer an injected or composable collaborator over another shared parent.
- When a Dispatch mutation returns `Either<ValidationMessages, Success>`, branch on that result in
  the presenter. Treat validation as an expected business outcome and leave unexpected failures on
  the standard Dispatch failure path.

6. Migrate the view implementation
- Keep layout construction, widgets, editor setup, masking hooks, and event translation in `FooViewImpl`.
- Translate raw UI signals into callbacks accepted through the public interface.
- Keep the view reactive and thin. It should update fields, show or hide visual state, and invoke registered lambdas.
- Do not let the view decide business outcomes or own navigation rules.
- Keep view sequencing visible in `FooViewImpl` rather than hiding it in view inheritance layers,
  except for thin generic framework glue from the host base class.
- Let the view own mapping and displaying `ValidationMessages`. Return create/edit validation to the
  modal editor so it remains open; show validation for non-editor mutations, such as removal,
  through the hosting grid or panel view.
- When constructing `FormValidator` for a view that is both a GWT `Widget` and `FormView`, pass an
  explicit field supplier such as `this::getFields` to avoid ambiguous constructor selection.

7. Update module and event wiring
- Add or update a Dagger module provider that returns the interface type, usually `FooView`, backed by `FooViewImpl`.
- Expose the presenter through Dagger as well: direct `@Inject` construction when no runtime args are
  needed, or an assisted `Factory` when they are.
- If the presenter is created by an event manager or bootstrap path, update the relevant manager to inject or use `Provider<FooPresenter>` or an assisted presenter factory.
- Replace direct constructor calls to old concrete views or presenters when the migration introduces interface binding and Dagger creation.
- If a legacy non-Dagger caller must create the presenter, expose only the required presenter or
  factory from `AppComponent`, then add a matching minimal `@Deprecated` `AppEnvironment` accessor.
- Avoid introducing a new common base class as the default reuse mechanism while doing this wiring.
- Search for feature events that became obsolete after introducing direct callbacks or Dispatch
  results. Remove their registrations, event and handler types only after proving no callers remain.
- If the migration creates a client package, add its explicit `package-info.java` with
  `@NullMarked`; package annotations do not extend into subpackages. If an existing package is
  `@NullUnmarked`, do not change that boundary without auditing the whole package.

8. Create or update exhaustive presenter unit tests
- Create or update `FooPresenterTest` under `src/test/java/...` beside the feature package.
- Use current VIMS test standards: TestNG, `EasyMockSupport`, `@Test(groups = "unit")`, and `@BeforeMethod` calling `resetAll()`.
- Mock the migrated view interface and presenter dependencies. Do not couple presenter tests to concrete `FooViewImpl`.
- Cover constructor and `initUI` wiring, registered view callbacks, event-manager registration, migrated business logic, validation branches, dispatch success and failure paths, and null or edge cases.
- For typed mutation results, cover both the validation and successful branches, including which
  view receives the validation messages. Do not add custom-failure tests when unexpected failures
  use unchanged centralized Dispatch handling.
- Capture callbacks registered on the view and invoke them directly so the tests prove the presenter reacts correctly through the interface seam.
- Preserve existing regression coverage and add tests for behaviour that changed during migration, especially places where widget access was replaced by view methods.
- Mock child-presenter contracts where available. For a final concrete child without a contract, use
  the real child with a stubbed view instead of making it non-final for the test.
- Prefer one focused test per behaviour, with helper methods for repeated constructor expectations where that improves readability.
- Follow `src/test/java/au/gov/qld/des/vims/client/auth/LoginPresenterTest.java` and
  `src/test/java/au/gov/qld/des/vims/client/HomePresenterTest.java`.

9. Validate the result
- Confirm the presenter only depends on interface methods and non-UI services.
- Confirm the presenter itself is created through Dagger and the view is injected through Dagger.
- Confirm the presenter and view sequence is understandable from the concrete implementation without
  needing to read parent-class lifecycle code.
- Confirm the view interface exposes intent-based methods and callback registration, not widget access.
- Confirm the view implementation contains the GWT/GXT and layout code.
- Confirm the migrated presenter and view no longer depend on feature-rich legacy report or form
  abstract bases for feature behaviour; any retained base should be thin framework glue only.
- Confirm any `AppEnvironment` fallback added for legacy callers is explicitly `@Deprecated` and as
  narrow as possible.
- Confirm any reusable workflow extracted during the migration now lives in a narrowly-scoped
  helper or dependency rather than a richer inherited base.
- Confirm the presenter test suite covers the migrated behaviour exhaustively using current TestNG patterns.
- Confirm nullable declarations use `org.jspecify.annotations.Nullable`, and that no redundant
  `@NonNull` annotations were added inside a `@NullMarked` package or type.
- Run the focused presenter test class when practical.
- Run Maven with Java 22 only and `-DforkCount=0` for focused and full tests. Verify Maven's VM with
  `mvn -version`; standalone `java -version` may resolve to a different installation.
- After Dagger or assisted-factory changes, run `mvn -DskipTests compile gwt:compile` so Java
  annotation processing generates `DaggerAppComponent` before the GWT compiler starts.
- Open the references listed below and compare the migrated structure with the target shape.

## API Design Rules

Use these rules when shaping the public view interface:
- Expose intent, not structure.
- Return domain data or DTOs when the presenter genuinely needs them.
- Let the view own widget-specific conversions and bindings.
- Keep database or dispatch initiation presenter-driven. The view should only raise user intent through callbacks.

Prefer:
- `void onSave(Runnable handler)`
- `void onDefaultSourceValueChanged(Consumer<StoreType> handler)`
- `void editStockCode(StockCodeDto stockCode)`
- `void showValidationMessages(ValidationMessages messages)`
- injected helper or service for shared masking, report handling, validation flow, loader wiring,
  or event-registration patterns

Avoid:
- `TextButton getSaveButton()`
- `Grid<TaskDto> getGrid()`
- `ComboBox<StoreType> getDefaultSourceCombo()`
- `Driver getDriver()`
- moving feature orchestration into `Abstract*Presenter` or `Abstract*View` subclasses just to
  reuse it

## What To Move Where

Move into the presenter:
- business rules
- validation orchestration
- dispatch or database calls
- event-manager interactions
- navigation decisions
- state transitions
- explicit sequencing for the feature flow, even when older code previously hid it in parent hooks

Keep in the view:
- layout and widget construction
- editor binding details
- masking hooks and visual affordances
- raw UI event handling that simply invokes registered lambdas
- purely visual state changes such as enabling, disabling, showing, hiding, and relabeling controls
- visible UI setup and translation flow, instead of relying on custom inherited lifecycle behaviour

If the legacy view contains business decisions, pull them back into the presenter and replace them with simpler display or update methods.
If a legacy parent class contains feature-specific sequence or branching, pull that behaviour down
into the concrete class before deciding what should be extracted for reuse.

## Partial Migration Guidance

Use `StockCodeEdit*` as the complex exemplar for partial migrations:
- `StockCodeEditView` already shows the right direction: it exposes an interface and callback-based interactions.
- `StockCodeEditViewImpl` still owns editor wiring, widget setup, and GWT/GXT detail, which is appropriate.
- `EquipmentModule` already binds the interface to the implementation.

When finishing a migration like `StockCodeEdit*`:
- tighten the public API further if it still leaks UI detail
- keep presenter logic free of widget classes and UI event types
- keep all editor-driver, widget, and layout details inside the implementation
- keep save, refresh, cancel, and selection actions represented as lambdas or simple domain-oriented methods
- keep the overall flow understandable from the concrete presenter and view, not from an abstract
  parent hierarchy

## References

Open these only as needed:
- `references/target-patterns.md`
- `references/stock-code-edit.md`
- `src/test/java/au/gov/qld/des/vims/client/auth/LoginPresenterTest.java`
- `src/test/java/au/gov/qld/des/vims/client/HomePresenterTest.java`

Use `assets/example/` for a minimal end-state skeleton:
- `ExamplePresenter.java`
- `ExampleView.java`
- `ExampleViewImpl.java`
- `ExampleModule.java`
