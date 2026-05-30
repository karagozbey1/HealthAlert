#ifndef HA_DEBUG_H
#define HA_DEBUG_H

#include <Arduino.h>
#include "ha_config.h"

#if DEBUG_SERIAL
#define HA_SERIAL_BEGIN(baud) Serial.begin(baud)
#define HA_SERIAL_PRINT(...) Serial.print(__VA_ARGS__)
#define HA_SERIAL_PRINTLN(...) Serial.println(__VA_ARGS__)
#define HA_SERIAL_PRINTF(...) Serial.printf(__VA_ARGS__)
#define HA_SERIAL_AVAILABLE() Serial.available()
#define HA_SERIAL_READ() Serial.read()
#else
#define HA_SERIAL_BEGIN(baud) do {} while (0)
#define HA_SERIAL_PRINT(...) do {} while (0)
#define HA_SERIAL_PRINTLN(...) do {} while (0)
#define HA_SERIAL_PRINTF(...) do {} while (0)
#define HA_SERIAL_AVAILABLE() false
#define HA_SERIAL_READ() (-1)
#endif

#endif
