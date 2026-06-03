# StockCodeEdit Reference

Use these files when the migration involves editor-backed forms, validation display, or a partially migrated presenter/view pair:

- `vims-app/src/main/java/au/gov/qld/des/vims/client/equip/StockCodeEditPresenter.java`
- `vims-app/src/main/java/au/gov/qld/des/vims/client/equip/StockCodeEditView.java`
- `vims-app/src/main/java/au/gov/qld/des/vims/client/equip/StockCodeEditViewImpl.java`
- `vims-app/src/main/java/au/gov/qld/des/vims/client/equip/EquipmentModule.java`

## Why It Matters

`StockCodeEdit*` is useful because it is not fully legacy and not fully at the target end state:
- the view already has an interface
- the implementation already keeps editor-driver and widget setup local
- the module already binds the interface to the implementation
- the presenter still illustrates the kind of logic that must stay independent from UI internals

## What To Reuse

- Callback-based registration such as `onSaveAndCloseButtonSelected`, `onCancelButtonSelected`, and value-change callbacks.
- Domain-oriented view methods such as `editStockCode`, `createStockCode`, `makeSapCodeMandatory`, and `showValidationMessages`.
- Keeping `SimpleBeanEditorDriver` and widget field details inside the implementation.

## What To Watch

- Tighten any remaining API surface that leaks unnecessary UI behavior.
- Do not let the presenter reach through the interface into widgets, editor drivers, or concrete event types.
- Do not move validation rules or save-orchestration decisions into the view just because the form is editor-backed.
