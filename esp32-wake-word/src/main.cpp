#include <Arduino.h>
#include <WiFi.h>
#include <driver/i2s.h>
#include <esp_task_wdt.h>
#include "I2SMicSampler.h"
#include "I2SOutput.h"
#include "config.h"
#include "Application.h"
#include "SPIFFS.h"
#include "Speaker.h"
#include "IndicatorLight.h"

// i2s config for reading from I2S microphone
i2s_config_t i2sMemsConfigBothChannels = {
    .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX),
    .sample_rate = 16000,
    .bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT,
    .channel_format = I2S_MIC_CHANNEL,
    .communication_format = I2S_COMM_FORMAT_STAND_I2S,  // ESP32-S3 compatible
    .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
    .dma_buf_count = 4,
    .dma_buf_len = 64,
    .use_apll = false,
    .tx_desc_auto_clear = false,
    .fixed_mclk = 0};

// i2s microphone pins
i2s_pin_config_t i2s_mic_pins = {
    .bck_io_num = I2S_MIC_SERIAL_CLOCK,
    .ws_io_num = I2S_MIC_LEFT_RIGHT_CLOCK,
    .data_out_num = I2S_PIN_NO_CHANGE,
    .data_in_num = I2S_MIC_SERIAL_DATA};

// i2s speaker pins
i2s_pin_config_t i2s_speaker_pins = {
    .bck_io_num = I2S_SPEAKER_SERIAL_CLOCK,
    .ws_io_num = I2S_SPEAKER_LEFT_RIGHT_CLOCK,
    .data_out_num = I2S_SPEAKER_SERIAL_DATA,
    .data_in_num = I2S_PIN_NO_CHANGE};

// Global task handle for application processing
TaskHandle_t g_applicationTaskHandle = nullptr;

// This task does all the heavy lifting for our application
void applicationTask(void *param)
{
  Application *application = static_cast<Application *>(param);

  const TickType_t xMaxBlockTime = pdMS_TO_TICKS(100);
  while (true)
  {
    // wait for notification from I2S reader task (triggered when audio buffer fills)
    uint32_t ulNotificationValue = ulTaskNotifyTake(pdTRUE, xMaxBlockTime);
    if (ulNotificationValue > 0)
    {
      // Run the wake word detection on the latest audio buffer
      application->run();
    }
  }
}

void setup()
{
  Serial.begin(115200);
  delay(1000);
  Serial.println("Starting up - Marvin Wake Word Detector");

  // WiFi is optional - only connect if credentials are defined
#ifdef WIFI_SSID
  Serial.println("WiFi credentials found, connecting...");
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PSWD);
  if (WiFi.waitForConnectResult() != WL_CONNECTED)
  {
    Serial.println("Connection Failed! Continuing without WiFi...");
  } else {
    Serial.println("WiFi connected!");
  }
#else
  Serial.println("WiFi disabled - running in local mode only");
#endif

  Serial.printf("Total heap: %d\n", ESP.getHeapSize());
  Serial.printf("Free heap: %d\n", ESP.getFreeHeap());

  // startup SPIFFS for the wav files
  SPIFFS.begin();
  // make sure we don't get killed for our long running tasks
  esp_task_wdt_init(10, false);

  // Create sampler for I2S microphone
  Serial.println("Creating I2S microphone sampler...");
  I2SSampler *i2s_sampler = new I2SMicSampler(i2s_mic_pins, false);

  // create our application - only uses DetectWakeWordState
  Serial.println("Creating application...");
  Application *application = new Application(i2s_sampler, nullptr);

  // set up the application task BEFORE starting I2S
  // The I2S reader task will notify this task when buffers are ready
  Serial.println("Creating application task...");
  xTaskCreate(applicationTask, "Application Task", 8192, application, 1, &g_applicationTaskHandle);

  delay(100);  // Give task time to create

  // Now start the I2S reader with proper error handling
  Serial.println("Initializing I2S microphone (I2S_NUM_0)...");
  i2s_sampler->start(I2S_NUM_0, i2sMemsConfigBothChannels, g_applicationTaskHandle);

  Serial.println("✅ Setup complete - Real I2S microphone active");
  Serial.println("Wake word detection running with live audio input...\n");
}

void loop()
{
  // I2S reader task handles all audio input via interrupts
  // This loop is now just a placeholder - all work done in applicationTask
  vTaskDelay(1000);  // Sleep to avoid wasting CPU
}