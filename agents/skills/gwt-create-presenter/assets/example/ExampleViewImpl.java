package au.gov.qld.des.vims.client.example;

import au.gov.qld.des.vims.client.app.bundle.AppResources;
import au.gov.qld.des.vims.client.support.AbstractContentPanelView;
import com.sencha.gxt.widget.core.client.container.VerticalLayoutContainer;
import com.sencha.gxt.widget.core.client.form.LabelField;
import javax.inject.Inject;

/**
 * Example view implementation skeleton.
 */
public class ExampleViewImpl extends AbstractContentPanelView implements ExampleView {

  private final LabelField messageLabel = new LabelField();

  @Inject
  public ExampleViewImpl(AppResources appResources) {
    setHeading("Example");
    getHeader().setIcon(appResources.iconAppHome());

    VerticalLayoutContainer container = new VerticalLayoutContainer();
    container.add(messageLabel);

    add(container);
  }

  @Override
  public void onPrimaryAction(Runnable handler) {
    // Wire buttons or UI handlers here.
  }

  @Override
  public void showMessage(String message) {
    messageLabel.setText(message);
  }
}
