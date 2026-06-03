package au.gov.qld.des.vims.client.example;

import au.gov.qld.des.vims.client.common.UIConfig;
import au.gov.qld.des.vims.client.support.BasePresenter;
import au.gov.qld.des.vims.client.support.EventManager;
import javax.annotation.Nonnull;
import javax.inject.Inject;

/**
 * Example migrated presenter skeleton.
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
    view.onSave(this::save);
    view.onCancel(this::cancel);
  }

  private void save() {
    String recordName = view.getRecordName();
    view.showStatus("Saved " + recordName);
  }

  private void cancel() {
    view.hide();
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
