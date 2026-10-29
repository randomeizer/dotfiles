package au.gov.qld.des.vims.client.example;

import javax.inject.Inject;

/** Example presenter with no framework presenter contract. */
public final class ExamplePresenter {

  private final ExampleView view;

  @Inject
  public ExamplePresenter(ExampleView view) {
    this.view = view;
    initUI();
  }

  private void initUI() {
    view.onPrimaryAction(this::onPrimaryAction);
  }

  private void onPrimaryAction() {
    view.showStatus("Hello from ExamplePresenter");
  }
}
