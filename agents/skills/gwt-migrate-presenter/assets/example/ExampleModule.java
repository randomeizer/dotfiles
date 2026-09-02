package au.gov.qld.des.vims.client.example;

import dagger.Module;
import dagger.Binds;

@Module
public interface ExampleModule {

  @Binds
  ExampleView bindExampleView(ExampleViewImpl implementation);
}
