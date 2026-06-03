---
name: gwt-migrate-presenter
description: Migrate existing VIMS GWT presenter/view pairs to the newer BasePresenter plus View/ViewImpl structure with interface-first views, Dagger module bindings, and required event-manager/provider wiring. Use when Codex needs to convert legacy concrete *View classes into *View interfaces plus *ViewImpl, move presenters away from legacy AbstractPresenter patterns, or tighten presenter/view boundaries so presenters do not depend on GWT or GXT widget internals.
---

# GWT Presenter/View Migration (VIMS)

Migrate one existing presenter/view pair at a time toward an interface-first, composition-first
shape like `Login` and `Home`:
- thin framework host only when it stays non-prescriptive, for example `BasePresenter<YourView>`
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
- When runtime values such as `parent`, `context`, or `eventManager` are required, use assisted
  injection plus a Dagger factory rather than manual `new`.
- If a non-Dagger caller still needs to create or access the presenter or presenter factory, add the
  smallest possible `@Deprecated` `AppEnvironment` accessor that forwards to `AppComponent`.
- If shared behaviour is genuinely reusable, extract it into a helper, utility, service, or other
  dependency rather than a richer base presenter or base view.
- Finish each migration by creating or updating exhaustive presenter unit tests in TestNG.

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

4. Rename the legacy concrete view when needed
- If a concrete class already uses the final `FooView` name, rename it to `FooViewImpl`.
- Introduce a new `FooView` interface with only the presenter-facing API.
- Keep any editor bindings, widget fields, and GWT/GXT wiring inside `FooViewImpl`.

5. Migrate the presenter
- Prefer `BasePresenter<FooView>` only when it remains a thin framework host and the presenter flow
  still reads clearly from `FooPresenter`.
- Use `@Inject` or `@AssistedInject` constructor injection and store dependencies as `final` fields.
- Move UI wiring into `initUI`.
- Return the interface type from `getView()`.
- Implement `getContext()` and `getEventManager()` explicitly.
- Remove presenter dependencies on `SelectEvent`, `NativeEvent`, widget classes, editor drivers, and concrete view internals unless there is no practical abstraction.
- Pull feature-specific sequence and branching down out of legacy parent classes before deciding
  what, if anything, should be extracted for reuse.
- Do not instantiate `FooViewImpl` or other dependencies inside the presenter constructor.
- If the presenter needs runtime arguments such as `parent`, `context`, or `eventManager`, define an
  assisted `Factory` and have Dagger create the presenter through that factory.
- If the presenter still needs reusable support such as validation flow, loader wiring, masking, or
  report orchestration, prefer an injected or composable collaborator over another shared parent.

6. Migrate the view implementation
- Keep layout construction, widgets, editor setup, masking hooks, and event translation in `FooViewImpl`.
- Translate raw UI signals into callbacks accepted through the public interface.
- Keep the view reactive and thin. It should update fields, show or hide visual state, and invoke registered lambdas.
- Do not let the view decide business outcomes or own navigation rules.
- Keep view sequencing visible in `FooViewImpl` rather than hiding it in view inheritance layers,
  except for thin generic framework glue from the host base class.

7. Update module and event wiring
- Add or update a Dagger module provider that returns the interface type, usually `FooView`, backed by `FooViewImpl`.
- Expose the presenter through Dagger as well: direct `@Inject` construction when no runtime args are
  needed, or an assisted `Factory` when they are.
- If the presenter is created by an event manager or bootstrap path, update the relevant manager to inject or use `Provider<FooPresenter>` or an assisted presenter factory.
- Replace direct constructor calls to old concrete views or presenters when the migration introduces interface binding and Dagger creation.
- If a legacy non-Dagger caller must create the presenter, expose only the required presenter or
  factory from `AppComponent`, then add a matching minimal `@Deprecated` `AppEnvironment` accessor.
- Avoid introducing a new common base class as the default reuse mechanism while doing this wiring.

8. Create or update exhaustive presenter unit tests
- Create or update `FooPresenterTest` under `vims-app/src/test/java/...` beside the feature package.
- Use current VIMS test standards: TestNG, `EasyMockSupport`, `@Test(groups = "unit")`, and `@BeforeMethod` calling `resetAll()`.
- Mock the migrated view interface and presenter dependencies. Do not couple presenter tests to concrete `FooViewImpl`.
- Cover constructor and `initUI` wiring, registered view callbacks, event-manager registration, migrated business logic, validation branches, dispatch success and failure paths, and null or edge cases.
- Capture callbacks registered on the view and invoke them directly so the tests prove the presenter reacts correctly through the interface seam.
- Preserve existing regression coverage and add tests for behaviour that changed during migration, especially places where widget access was replaced by view methods.
- Prefer one focused test per behaviour, with helper methods for repeated constructor expectations where that improves readability.
- Follow `vims-app/src/test/java/au/gov/qld/des/vims/client/auth/LoginPresenterTest.java` and `vims-app/src/test/java/au/gov/qld/des/vims/client/HomePresenterTest.java`.

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
- Run the focused presenter test class when practical.
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
- `vims-app/src/test/java/au/gov/qld/des/vims/client/auth/LoginPresenterTest.java`
- `vims-app/src/test/java/au/gov/qld/des/vims/client/HomePresenterTest.java`

Use `assets/example/` for a minimal end-state skeleton:
- `ExamplePresenter.java`
- `ExampleView.java`
- `ExampleViewImpl.java`
- `ExampleModule.java`
