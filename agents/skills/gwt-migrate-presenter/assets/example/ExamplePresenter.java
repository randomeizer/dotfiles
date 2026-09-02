package au.gov.qld.des.vims.client.example;

import javax.inject.Inject;

/** Example migrated presenter skeleton. */
public final class ExamplePresenter {

  private final ExampleView view;

  @Inject
  public ExamplePresenter(ExampleView view) {
    this.view = view;
    view.onSave(this::save);
    view.onCancel(view::hide);
  }

  private void save() {
    String recordName = view.getRecordName();
    view.showStatus("Saved " + recordName);
  }
}
