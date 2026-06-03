# Target Patterns

Use these files as the greenfield reference shape when creating a new presenter/view pair:

- `vims-app/src/main/java/au/gov/qld/des/vims/client/auth/LoginPresenter.java`
- `vims-app/src/main/java/au/gov/qld/des/vims/client/auth/LoginView.java`
- `vims-app/src/main/java/au/gov/qld/des/vims/client/auth/LoginViewImpl.java`
- `vims-app/src/main/java/au/gov/qld/des/vims/client/auth/AuthModule.java`
- `vims-app/src/main/java/au/gov/qld/des/vims/client/HomePresenter.java`
- `vims-app/src/main/java/au/gov/qld/des/vims/client/HomeView.java`
- `vims-app/src/main/java/au/gov/qld/des/vims/client/HomeViewImpl.java`
- `vims-app/src/main/java/au/gov/qld/des/vims/client/HomeModule.java`

## What To Notice

- The presenter depends on services plus a view interface, not widget internals.
- The main sequence is visible from the concrete presenter and view implementation.
- The view interface is small and intent-based.
- The view implementation owns layout, widgets, and raw UI event translation.
- Reusable workflow should be composed through helpers or dependencies, not hidden in richer parent
  presenter or view classes.
- `BasePresenter` and view host bases are acceptable only when they stay thin and
  non-prescriptive.
- The Dagger module returns the interface type.
- Event-manager or bootstrap wiring can use `Provider<...Presenter>` when the presenter is created indirectly.

## Creation Heuristics

- Keep new presenters and views readable on their own; do not rely on custom inherited lifecycle
  behaviour to understand feature flow.
- Prefer composition over inheritance for shared workflow.
