package au.gov.qld.des.vims.client.example;

import dagger.Module;
import dagger.Provides;

@Module
public class ExampleModule {

  @Provides
  public static ExampleView provideExampleView(ExampleViewImpl impl) {
    return impl;
  }
}
