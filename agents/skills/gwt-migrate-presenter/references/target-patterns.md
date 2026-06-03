# Target Patterns

Use these files as the target structure for migrated presenters and views:

- `vims-app/src/main/java/au/gov/qld/des/vims/client/auth/LoginPresenter.java`
- `vims-app/src/main/java/au/gov/qld/des/vims/client/auth/LoginView.java`
- `vims-app/src/main/java/au/gov/qld/des/vims/client/auth/LoginViewImpl.java`
- `vims-app/src/main/java/au/gov/qld/des/vims/client/auth/AuthModule.java`
- `vims-app/src/main/java/au/gov/qld/des/vims/client/HomePresenter.java`
- `vims-app/src/main/java/au/gov/qld/des/vims/client/HomeView.java`
- `vims-app/src/main/java/au/gov/qld/des/vims/client/HomeViewImpl.java`
- `vims-app/src/main/java/au/gov/qld/des/vims/client/HomeModule.java`

## What To Notice

- The presenter depends on services plus the view interface, not on widget internals.
- The main sequence is visible from the concrete presenter and view implementation.
- The view interface is small and intent-based.
- The view implementation owns layout, widget construction, and event translation.
- Reusable workflow should be composed through helpers or dependencies, not hidden in richer parent
  presenter or view classes.
- `BasePresenter` and view host bases are acceptable only when they stay thin and
  non-prescriptive.
- The module returns the interface type rather than requiring callers to know the concrete implementation.
- Event-manager or app startup wiring can create presenters indirectly through `Provider<...Presenter>`.

## Migration Heuristics

- Use `Login*` as the reference for window-style flows and direct callback registration.
- Use `Home*` as the reference for content-panel flows, maskable views, loaders, and event-manager registration.
- If the legacy presenter currently creates its own child widgets or view internals, move that knowledge behind the view interface first, then simplify the presenter.
- If a legacy parent class hides feature sequence or branching, pull that behaviour down into the
  concrete class before deciding what should be extracted for reuse.
- Prefer composition over inheritance for shared workflow.
