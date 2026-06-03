---
name: gwt-create-presenter
description: Create new VIMS GWT presenter/view pairs using BasePresenter, interface-first views, ViewImpl classes, Dagger module bindings, and optional event-manager/provider wiring. Use when Codex needs to add a new client-side presenter/view in VIMS, shape a presenter-facing view API that hides GWT and GXT internals, or scaffold a new presenter/view/module set that follows the Login and Home patterns from the start.
---

# GWT Presenter/View Creation (VIMS)

Create new presenter/view pairs in `au.gov.qld.des.vims.client.*` using the same interface-first,
composition-first shape seen in `Login` and `Home`:
- thin framework host only when it stays non-prescriptive, for example `BasePresenter<YourView>`
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
- Create exhaustive presenter unit tests in TestNG as part of the initial implementation.

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
- Extend `BasePresenter<YourView>` only when it remains a thin framework host and the feature flow
  still reads clearly from `YourPresenter`.
- Use `@Inject` or `@AssistedInject` plus `@Nonnull` constructor parameters.
- Store dependencies as `final` fields.
- Wire view callbacks in `initUI`.
- Keep dispatch, business rules, event-manager interactions, and state changes in the presenter.
- Implement `getContext()` and `getEventManager()` explicitly.
- Keep sequencing and orchestration in the concrete presenter.
- Do not instantiate `YourViewImpl` or other dependencies inside the presenter constructor.
- If the presenter needs runtime arguments such as `parent`, `context`, or `eventManager`, define an
  assisted `Factory` and have Dagger create the presenter through that factory.
- Introduce a shared helper only when there are at least two clear consumers or the logic is truly
  generic framework glue.

5. Create exhaustive presenter unit tests
- Create `YourPresenterTest` under `vims-app/src/test/java/...` beside the feature package.
- Use current VIMS test standards: TestNG, `EasyMockSupport`, `@Test(groups = "unit")`, and `@BeforeMethod` calling `resetAll()`.
- Mock the view interface and presenter dependencies. Do not depend on concrete `YourViewImpl` internals in the presenter tests.
- Cover constructor and `initUI` wiring, registered view callbacks, public presenter entry points, event-manager registration, dispatch success and failure paths, validation branches, and null or edge cases.
- Capture lambdas, callbacks, or handlers registered on the view and invoke them directly to prove presenter behaviour.
- Prefer one focused test per behaviour, with helper methods for repeated constructor expectations when that keeps the suite readable.
- Follow `vims-app/src/test/java/au/gov/qld/des/vims/client/auth/LoginPresenterTest.java` and `vims-app/src/test/java/au/gov/qld/des/vims/client/HomePresenterTest.java`.

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
- Run the focused presenter test class when practical.

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
- `vims-app/src/test/java/au/gov/qld/des/vims/client/auth/LoginPresenterTest.java`
- `vims-app/src/test/java/au/gov/qld/des/vims/client/HomePresenterTest.java`

Use `assets/example/` for a minimal skeleton:
- `ExamplePresenter.java`
- `ExampleView.java`
- `ExampleViewImpl.java`
- `ExampleModule.java`
