---
name: gwt-create-presenter
description: Create GWT Presenter/View/ViewImpl for VIMS client using BasePresenter, Dagger injection, and module provider patterns. Use LoginPresenter/View and HomePresenter/View as exemplars.
---

# GWT Presenter/View Creation (VIMS)

Use this skill when adding a new client-side presenter/view in `au.gov.qld.des.vims.client.*`.
Follow existing VIMS patterns based on `LoginPresenter/View` and `HomePresenter/View`.

## Quick workflow
1) Identify feature package and decide view type
- **Window flow**: use `AbstractWindowView` (login-like dialogs).
- **Content panel flow**: use `AbstractContentPanelView` (main screen panels).

2) Create the View interface
- Extend `au.gov.qld.des.vims.client.support.View`.
- Add `Maskable` if dispatch masking is needed.
- Keep method names imperative (`show`, `hide`, `display`, `setX`, `onX`).

3) Create the ViewImpl
- Extend `AbstractWindowView` or `AbstractContentPanelView`.
- Accept `AppResources` and other UI dependencies via `@Inject` constructor.
- Build UI in the constructor and/or `initUI` method.

4) Create the Presenter
- Extend `BasePresenter<YourView>`.
- Use `@Inject` + `@Nonnull` constructor params.
- Store dependencies as `final` fields.
- Wire UI handlers in `initUI`.
- Register event handlers with `AppEventManager` where needed.

5) Add a Dagger module provider
- Create `YourFeatureModule` with `provideYourView(...)` returning `YourViewImpl`.
- If required, add `Provider<YourPresenter>` to the relevant event manager.

6) Tests (if needed)
- Follow `LoginPresenterTest` or `LoadingPresenterTest` patterns for mocks and callbacks.

## Conventions to follow
- Use `@Nonnull` on injected params and state where possible.
- Prefer `UIConfig.KEY_GLOBAL_CONTEXT` in `getContext()` unless feature requires a specific one.
- Keep presenter logic in the presenter, and UI logic in the view.
- Avoid heavy work in view constructors beyond UI setup.

## References (open when needed)
- `vims-app/src/main/java/au/gov/qld/des/vims/client/login/LoginPresenter.java`
- `vims-app/src/main/java/au/gov/qld/des/vims/client/login/LoginView.java`
- `vims-app/src/main/java/au/gov/qld/des/vims/client/login/LoginViewImpl.java`
- `vims-app/src/main/java/au/gov/qld/des/vims/client/HomePresenter.java`
- `vims-app/src/main/java/au/gov/qld/des/vims/client/HomeView.java`
- `vims-app/src/main/java/au/gov/qld/des/vims/client/HomeViewImpl.java`

## Example skeletons
See `assets/example/` for a minimal Presenter/View/ViewImpl example.
