package au.gov.qld.des.vims.client.example;

import au.gov.qld.des.vims.client.support.View;

/**
 * Example view interface.
 */
public interface ExampleView extends View {

  void display();

  void onPrimaryAction(Runnable handler);

  void showStatus(String message);
}
