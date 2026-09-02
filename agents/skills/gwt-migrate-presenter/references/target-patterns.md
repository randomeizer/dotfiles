# Target Patterns

Use these files as the target structure for migrated presenters and views:

- `src/main/java/au/gov/qld/des/vims/client/auth/LoginPresenter.java`
- `src/main/java/au/gov/qld/des/vims/client/auth/LoginView.java`
- `src/main/java/au/gov/qld/des/vims/client/auth/LoginViewImpl.java`
- `src/main/java/au/gov/qld/des/vims/client/auth/AuthModule.java`
- `src/main/java/au/gov/qld/des/vims/client/HomePresenter.java`
- `src/main/java/au/gov/qld/des/vims/client/HomeView.java`
- `src/main/java/au/gov/qld/des/vims/client/HomeViewImpl.java`
- `src/main/java/au/gov/qld/des/vims/client/HomeModule.java`

## What To Notice

- The presenter depends on services plus the view interface, not on widget internals.
- A presenter is a plain injected final class when it needs no framework presenter contract. It
  implements `Presenter` directly only when callers consume that contract, and uses a thin base only
  when required framework behaviour would otherwise be duplicated.
- The main sequence is visible from the concrete presenter and view implementation.
- The view interface is small and intent-based.
- The view implementation owns layout, widget construction, and event translation.
- Reusable workflow should be composed through helpers or dependencies, not hidden in richer parent
  presenter or view classes.
- `BasePresenter` and view host bases are acceptable only when they stay thin, non-prescriptive, and
  provide behaviour the concrete class actually needs.
- The module returns the interface type rather than requiring callers to know the concrete implementation.
- Event-manager or app startup wiring can create presenters indirectly through `Provider<...Presenter>`.

## Migration Heuristics

- Use `Login*` as the reference for window-style flows and direct callback registration.
- Use `Home*` as the reference for content-panel flows, maskable views, loaders, and event-manager registration.
- If the legacy presenter currently creates its own child widgets or view internals, move that knowledge behind the view interface first, then simplify the presenter.
- If a legacy parent class hides feature sequence or branching, pull that behaviour down into the
  concrete class before deciding what should be extracted for reuse.
- Prefer composition over inheritance for shared workflow.
