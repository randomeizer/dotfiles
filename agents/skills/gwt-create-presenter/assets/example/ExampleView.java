package au.gov.qld.des.vims.client.example;

import au.gov.qld.des.vims.client.support.View;

/**
 * Example view interface.
 */
public interface ExampleView extends View {
  void onPrimaryAction(Runnable handler);

  void showMessage(String message);
}
