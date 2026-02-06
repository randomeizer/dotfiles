package au.gov.qld.des.vims.client.example;

import au.gov.qld.des.vims.client.app.bundle.AppResources;
import au.gov.qld.des.vims.client.support.AbstractContentPanelView;
import com.sencha.gxt.widget.core.client.button.TextButton;
import com.sencha.gxt.widget.core.client.container.VerticalLayoutContainer;
import com.sencha.gxt.widget.core.client.event.SelectEvent;
import com.sencha.gxt.widget.core.client.form.LabelField;
import javax.inject.Inject;

/**
 * Example view implementation skeleton.
 */
public class ExampleViewImpl extends AbstractContentPanelView implements ExampleView {

  private final LabelField messageLabel = new LabelField();
  private final TextButton primaryButton = new TextButton("Primary Action");

  @Inject
  public ExampleViewImpl(AppResources appResources) {
    setHeading("Example");
    getHeader().setIcon(appResources.iconAppHome());

    VerticalLayoutContainer container = new VerticalLayoutContainer();
    container.add(messageLabel);
    container.add(primaryButton);

    add(container);
  }

  @Override
  public void onPrimaryAction(Runnable handler) {
    primaryButton.addSelectHandler((SelectEvent event) -> handler.run());
  }

  @Override
  public void showMessage(String message) {
    messageLabel.setText(message);
  }
}
