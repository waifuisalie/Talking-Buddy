// WiFi credentials (optional for local wake word detection only)
// Uncomment if you want WiFi connectivity for future features
// #define WIFI_SSID "<<YOUR SSID>>"
// #define WIFI_PSWD "<<YOUR PASSWORD>>"

// are you using an I2S microphone - comment this out if you want to use an analog mic and ADC input
#define USE_I2S_MIC_INPUT

// I2S Microphone Settings (ICS-43434)

// Which channel is the I2S microphone on? I2S_CHANNEL_FMT_ONLY_LEFT or I2S_CHANNEL_FMT_ONLY_RIGHT
#define I2S_MIC_CHANNEL I2S_CHANNEL_FMT_ONLY_LEFT
// #define I2S_MIC_CHANNEL I2S_CHANNEL_FMT_ONLY_RIGHT
#define I2S_MIC_SERIAL_CLOCK GPIO_NUM_5      // SCK  -> GPIO 5
#define I2S_MIC_LEFT_RIGHT_CLOCK GPIO_NUM_4  // WS   -> GPIO 4
#define I2S_MIC_SERIAL_DATA GPIO_NUM_6       // SD   -> GPIO 6

// Analog Microphone Settings - ADC1_CHANNEL_7 is GPIO35
#define ADC_MIC_CHANNEL ADC1_CHANNEL_7

// speaker settings
#define I2S_SPEAKER_SERIAL_CLOCK GPIO_NUM_14
#define I2S_SPEAKER_LEFT_RIGHT_CLOCK GPIO_NUM_12
#define I2S_SPEAKER_SERIAL_DATA GPIO_NUM_27

// command recognition settings (NOT USED - we trigger local chatbot via serial instead)
// #define COMMAND_RECOGNITION_ACCESS_KEY "P5QMUSMFV6IRRSTABXFQ7UIXPFRMC4L5"
