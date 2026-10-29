---
name: gwt-create-presenter
description: Create new VIMS GWT presenter/view pairs using plain or framework-backed injected presenters, interface-first views, ViewImpl classes, Dagger module bindings, and optional event-manager/provider wiring. Use when Codex needs to add a new client-side presenter/view in VIMS, shape a presenter-facing view API that hides GWT and GXT internals, or scaffold a new presenter/view/module set that follows the Login and Home patterns from the start.
---

# GWT Presenter/View Creation (VIMS)

Create new presenter/view pairs in `au.gov.qld.des.vims.client.*` using the same interface-first,
composition-first shape seen in `Login` and `Home`:
- plain injected final presenter when no framework presenter contract is consumed
- direct `Presenter` implementation only when callers actually use that contract
- thin framework host such as `BasePresenter<YourView>` only when it supplies required behaviour
- public `YourView` interface
- concrete `YourViewImpl`
- Dagger module binding for the interface
- Dagger-created presenter, including assisted factory wiring when runtime arguments such as `parent`,
  `context`, or `eventManager` are required

Read `references/target-patterns.md` when you need the concrete exemplars.

## Creation Principles

Treat these as defaults:
- Keep GWT/GXT-specific code out of presenters where a view abstraction is practical.
- Keep business logic out of views.
- Make the presenter depend only on a stable view interface that hides widget types and internals.
- Make the view independent of the presenter by exposing lambda-based registration points for UI-driven actions.
- Keep the feature sequence readable from the concrete presenter and view implementation.
- Do not introduce new presenter or view parent classes just to hold feature process logic.
- Make presenter construction Dagger-first by default. Inject the view through Dagger as well.
- When runtime values such as `parent`, `context`, or `eventManager` are required, use assisted
  injection plus a Dagger factory rather than manual `new`.
- If a non-Dagger caller still needs to create or access the presenter or presenter factory, add the
  smallest possible `@Deprecated` `AppEnvironment` accessor that forwards to `AppComponent`.
- Prefer injected helpers or composable dependencies for reusable behaviour such as masking, report
  orchestration, validation helpers, loader wiring, or event registration patterns.
- Follow the repository JSpecify policy: explicitly mark new client packages `@NullMarked`, use
  `org.jspecify.annotations.Nullable` for genuinely nullable declarations, and omit redundant
  `@NonNull` inside null-marked scopes. Do not change an existing `@NullUnmarked` package without
  auditing the whole package.
- Create presenter unit tests in TestNG that cover the implemented behaviours.

## Composite Presenters and Child Placement

When creating a presenter that will live inside a parent tab, panel, or wizard:
- Prefer an instance-owned `UiSlotKey` over exposing the child view to its parent presenter.
- Have the composite view create its child container and register the slot during construction, then
  expose only the opaque key. Construct the composite view before creating its children.
- Pass the target slot into the child presenter's assisted factory, with `UiSlotKey` first among
  assisted parameters. If placement is immutable, pass it onward to the assisted view factory and
  mount the completed view at the end of view construction.
- A Dagger `@AssistedFactory` must return its concrete `@AssistedInject` type. Use a small `@Provides`
  adapter when the presenter should consume an interface-returning view factory.
- It is acceptable for a presenter to own a `TreeStore` or `ListStore` as model state and pass it to
  the view. Keep grids, rendering lifecycle, visual selection, and layout in the implementation.
- Do not add parent, event manager, context, or generic `UIConfig` arguments by convention. Use only
  required narrow callbacks and typed feature-specific configuration.

## Quick Workflow

1. Choose the view host
- **Window flow**: use `AbstractWindowView`.
- **Content panel flow**: use `AbstractContentPanelView`.
- Treat these host bases as thin framework glue, not as the right place for feature workflow.

2. Design the public view interface
- Extend `au.gov.qld.des.vims.client.support.View`.
- Add `Maskable` only if dispatch masking is needed.
- Design methods from presenter needs, not widget structure.
- Keep method names imperative and domain-oriented, for example `display`, `showError`, `setTasks`, `editRecord`, `onSave`.

3. Create the view implementation
- Extend `AbstractWindowView` or `AbstractContentPanelView`.
- Accept `AppResources` and other UI dependencies via `@Inject`.
- Keep layout, widget construction, editor/binding details, masking hooks, and raw event translation in `YourViewImpl`.
- Convert raw UI events into callback invocation through the public interface.
- Keep the UI setup and event flow visible in `YourViewImpl` rather than hiding it in another layer
  of inheritance.

4. Create the presenter
- Prefer a plain final class when no caller consumes `Presenter` and no framework lifecycle is
  required. Implement `Presenter` directly only when callers use that contract. Use
  `BasePresenter<YourView>` only when it supplies required framework behaviour and remains thin.
- Use `@Inject` or `@AssistedInject` constructor injection; apply the JSpecify policy above.
- Store dependencies as `final` fields.
- Wire view callbacks in `initUI`.
- Keep dispatch, business rules, event-manager interactions, and state changes in the presenter.
- Add `getView()`, `getContext()`, or `getEventManager()` only when the selected contract or an
  actual caller needs them, not by convention.
- Keep sequencing and orchestration in the concrete presenter.
- Do not instantiate `YourViewImpl` or other dependencies inside the presenter constructor.
- If the presenter needs runtime arguments such as `parent`, `context`, or `eventManager`, define an
  assisted `Factory` and have Dagger create the presenter through that factory.
- Introduce a shared helper only when there are at least two clear consumers or the logic is truly
  generic framework glue.

5. Create exhaustive presenter unit tests
- Create `YourPresenterTest` under `src/test/java/...` beside the feature package.
- Use current VIMS test standards: TestNG, `EasyMockSupport`, `@Test(groups = "unit")`, and `@BeforeMethod` calling `resetAll()`.
- Mock the view interface and presenter dependencies. Do not depend on concrete `YourViewImpl` internals in the presenter tests.
- Cover constructor and `initUI` wiring, registered view callbacks, public presenter entry points, event-manager registration, dispatch success and failure paths, validation branches, and null or edge cases.
- Capture lambdas, callbacks, or handlers registered on the view and invoke them directly to prove presenter behaviour.
- Prefer one focused test per behaviour, with helper methods for repeated constructor expectations when that keeps the suite readable.
- Follow `src/test/java/au/gov/qld/des/vims/client/auth/LoginPresenterTest.java` and `src/test/java/au/gov/qld/des/vims/client/HomePresenterTest.java`.

6. Add module and wiring
- Create `YourFeatureModule` with `provideYourView(...)` returning `YourViewImpl`.
- Expose the presenter through Dagger as well: direct `@Inject` construction when no runtime args are
  needed, or an assisted `Factory` when they are.
- Add `Provider<YourPresenter>` or an assisted presenter factory to the relevant event manager only
  when the presenter is created indirectly.
- If a legacy non-Dagger class must create the presenter, expose only the required presenter or
  factory from `AppComponent`, then add a matching minimal `@Deprecated` `AppEnvironment` accessor.
- Do not create a new common base class as the default reuse mechanism while wiring the feature.

7. Validate the shape
- Confirm the presenter talks only to intent-based view methods.
- Confirm the presenter itself is created through Dagger and the view is injected through Dagger.
- Confirm the presenter and view sequence is understandable from the concrete implementation without
  reading parent-class lifecycle code.
- Confirm the view interface does not expose widgets, editor drivers, `HandlerRegistration`, or event types.
- Confirm the view implementation contains the GWT/GXT and layout code.
- Confirm any `AppEnvironment` fallback added for legacy callers is explicitly `@Deprecated` and as
  narrow as possible.
- Confirm reusable workflow, if any, was placed in a helper or dependency rather than a richer
  inherited base.
- Confirm the presenter test suite is exhaustive for the implemented behaviours and follows current TestNG patterns.
- Run the focused presenter test class when practical. Use Maven with Java 22 and `-DforkCount=0`;
  verify Maven’s VM with `mvn -version`. After Dagger or assisted-factory changes, use
  `mvn -DskipTests compile gwt:compile` so annotation processing precedes GWT compilation.

## API Design Rules

Prefer:
- `void display()`
- `void showError(String message)`
- `void setTasks(Collection<TaskDto> tasks)`
- `void editRecord(RecordDto record)`
- `void onSave(Runnable handler)`
- `void onSelectionChanged(Consumer<ItemDto> handler)`
- injected helper or service for shared masking, report handling, validation flow, loader wiring,
  or event-registration patterns

Avoid:
- `TextButton getSaveButton()`
- `Grid<TaskDto> getGrid()`
- `ComboBox<?> getCombo()`
- `Driver getDriver()`
- moving feature orchestration into `Abstract*Presenter` or `Abstract*View` subclasses just to
  reuse it

Keep dispatch or database initiation presenter-driven. The view should raise user intent through callbacks and reflect visual state.

## What Goes Where

Presenter responsibilities:
- business rules
- dispatch orchestration
- event-manager interactions
- navigation decisions
- state changes
- explicit sequencing for the feature flow

View responsibilities:
- layout and widgets
- editor/binding details
- masking hooks
- translating UI events into callback invocation
- purely visual state changes
- visible UI setup and event translation flow

## References

Open these only when needed:
- `references/target-patterns.md`
- `src/test/java/au/gov/qld/des/vims/client/auth/LoginPresenterTest.java`
- `src/test/java/au/gov/qld/des/vims/client/HomePresenterTest.java`

Use `assets/example/` for a minimal skeleton:
- `ExamplePresenter.java`
- `ExampleView.java`
- `ExampleViewImpl.java`
- `ExampleModule.java`
- `package-info.java`
