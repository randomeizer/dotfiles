package au.gov.qld.des.vims.client.example;

import au.gov.qld.des.vims.client.support.View;

/**
 * Example presenter-facing view API.
 */
public interface ExampleView extends View {

  void editRecordName(String recordName);

  String getRecordName();

  void showStatus(String message);

  void showError(String message);

  void show();

  void hide();

  void onSave(Runnable handler);

  void onCancel(Runnable handler);
}
