#include <Arduino.h>
#include "Application.h"
#include "state_machine/DetectWakeWordState.h"
#include "IndicatorLight.h"

Application::Application(I2SSampler *sample_provider, IndicatorLight *indicator_light)
{
    // detect wake word state - waits for the wake word to be detected
    m_detect_wake_word_state = new DetectWakeWordState(sample_provider);
    // start off in the detecting wakeword state (stay here forever)
    m_current_state = m_detect_wake_word_state;
    m_current_state->enterState();
}

// process the next batch of samples
void Application::run()
{
    bool state_done = m_current_state->run();
    // Stay in DetectWakeWordState forever - wake word detection is handled by serial output
    // When wake word detected, DetectWakeWordState sends trigger via Serial, then returns to listening
    vTaskDelay(10);
}
