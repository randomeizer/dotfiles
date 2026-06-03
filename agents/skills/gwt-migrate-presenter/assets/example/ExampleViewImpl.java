package au.gov.qld.des.vims.client.example;

import au.gov.qld.des.vims.client.app.bundle.AppResources;
import au.gov.qld.des.vims.client.support.AbstractWindowView;
import com.sencha.gxt.widget.core.client.button.TextButton;
import com.sencha.gxt.widget.core.client.container.VerticalLayoutContainer;
import com.sencha.gxt.widget.core.client.form.TextField;
import javax.inject.Inject;

/**
 * Example migrated view implementation skeleton.
 */
public class ExampleViewImpl extends AbstractWindowView implements ExampleView {

  private final TextField nameField = new TextField();
  private final TextButton saveButton = new TextButton("Save");
  private final TextButton cancelButton = new TextButton("Cancel");

  @Inject
  public ExampleViewImpl(AppResources appResources) {
    setHeading("Example");
    getHeader().setIcon(appResources.iconSave());

    VerticalLayoutContainer container = new VerticalLayoutContainer();
    container.add(nameField);
    container.add(saveButton);
    container.add(cancelButton);
    add(container);
  }

  @Override
  public void editRecordName(String recordName) {
    nameField.setValue(recordName);
  }

  @Override
  public String getRecordName() {
    return nameField.getValue();
  }

  @Override
  public void showStatus(String message) {
    setHeading(message);
  }

  @Override
  public void showError(String message) {
    setHeading(message);
  }

  @Override
  public void onSave(Runnable handler) {
    saveButton.addSelectHandler(event -> handler.run());
  }

  @Override
  public void onCancel(Runnable handler) {
    cancelButton.addSelectHandler(event -> handler.run());
  }
}
