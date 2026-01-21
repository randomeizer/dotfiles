package au.gov.qld.des.vims.client.example;

import au.gov.qld.des.vims.client.common.UIConfig;
import au.gov.qld.des.vims.client.support.BasePresenter;
import au.gov.qld.des.vims.client.support.EventManager;
import javax.annotation.Nonnull;
import javax.inject.Inject;

/**
 * Example presenter skeleton.
 */
public class ExamplePresenter extends BasePresenter<ExampleView> {

  private final ExampleView view;

  @Inject
  public ExamplePresenter(@Nonnull ExampleView view) {
    super(new UIConfig());
    this.view = view;
    initUI();
  }

  private void initUI() {
    view.onPrimaryAction(this::onPrimaryAction);
  }

  private void onPrimaryAction() {
    view.showMessage("Hello from ExamplePresenter");
  }

  @Override
  public String getContext() {
    return UIConfig.KEY_GLOBAL_CONTEXT;
  }

  @Override
  public EventManager getEventManager() {
    return null;
  }

  @Override
  public ExampleView getView() {
    return view;
  }
}
