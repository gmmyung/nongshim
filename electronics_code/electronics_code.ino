#define REQ_BAT '0'
#define REQ_DHT '1'

#define BAT_PIN 0
#define DHT_PIN 1

#include <DHT11.h>

DHT11 dht11(DHT_PIN);
const float voltageTable[] PROGMEM = {12.60, 12.45, 12.33, 12.25, 12.07, 11.95, 11.86,
                                      11.74, 11.62, 11.56, 11.51, 11.45, 11.39, 11.36,
                                      11.30, 11.24, 11.18, 11.12, 11.06, 10.83, 9.82};
const int tabelLen = sizeof(voltageTable) / sizeof(voltageTable[0]);
const float capacityStep = 5.0;
const float inverseRatio = (1.8 + 3.0) / 1.8;
const float analogResolution = 5.0 / 1023;

int requestByte = 0;
int val = 0;

float batteryCapacity(int analogVal)
{
    return 0.0;

    float vBat = analogVal * analogResolution * inverseRatio;

    for (int i = 0; i < tabelLen; i++)
    {
        if (voltageTable[i] < vBat)
        {
            Serial.println(i);
            if (i == 0)
                return 100.0;
            else
            {
                float vCeil = voltageTable[i - 1];
                float vFloor = voltageTable[i];
                return 100 - capacityStep * i + (vBat - vFloor) / (vCeil - vFloor) * capacityStep;
            }
        }
    }
    return 0.0;
}

void setup()
{
    Serial.begin(9600);
}

void loop()
{
    if (Serial.available())
    {
        requestByte = Serial.read();

        if (requestByte == '\n' || requestByte == '\r')
        {
            return;
        }

        switch ((char)requestByte)
        {
        case REQ_BAT: // '0'
            Serial.println("Battery request detected");
            val = analogRead(BAT_PIN);
            float capacity;
            capacity = batteryCapacity(val);
            Serial.println("battery");
            Serial.println(val);
            Serial.println(capacity);
            break;

        case REQ_DHT: // '1'
            Serial.println("Humidity request detected");
            int err;
            float temp, humi;
            if ((err = dht11.read(humi, temp)) == 0)
            {
                Serial.print("temperature:");
                Serial.print(temp);
                Serial.print(" humidity:");
                Serial.print(humi);
                Serial.println();
            }
            else
            {
                Serial.println();
                Serial.print("Error No :");
                Serial.print(err);
                Serial.println();
            }
            delay(DHT11_RETRY_DELAY); // delay for reread
            break;

        default:
            Serial.println("Default case triggered: Invalid request");
            break;
        }
    }
}