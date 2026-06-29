/*
 * @Descripttion: 
 * @version: 
 * @Author: Elegoo
 * @Date: 2020-06-04 11:42:27
 * @LastEditors: Changhua
 * @LastEditTime: 2020-09-07 09:40:03
 */
//#include <EEPROM.h>
#include "CameraWebServer_AP.h"
#include "config.h"
#include <WiFi.h>
#include <HTTPClient.h>
#include "esp_camera.h"

static const char *DEVICE_ID = "tank-01";

void heartbeatTask(void *pvParameters) {
  for (;;) {
    if (WiFi.status() == WL_CONNECTED) {
      HTTPClient http;
      String url = "http://" + String(HUB_HOST) + ":" + String(HUB_PORT) + "/api/message";
      http.begin(url);
      http.addHeader("Content-Type", "application/json");

      String body = String("{\"type\":\"heartbeat\",\"device_id\":\"") + DEVICE_ID +
                    "\",\"ts\":" + String(millis() / 1000.0, 3) + ",\"payload\":{}}";

      int code = http.POST(body);
      if (code > 0) {
        Serial.printf("[heartbeat] sent ok, server responded: %d\n", code);
      } else {
        Serial.printf("[heartbeat] failed: %s\n", http.errorToString(code).c_str());
      }
      http.end();
    } else {
      Serial.println("[heartbeat] WiFi not connected, skipping");
    }
    vTaskDelay(pdMS_TO_TICKS(30UL * 60UL * 1000UL));  // 30 minutes
  }
}
WiFiServer server(100);

#define RXD2 33
#define TXD2 4
CameraWebServer_AP CameraWebServerAP;

bool WA_en = false;

void SocketServer_Test(void)
{
  static bool ED_client = true;
  WiFiClient client = server.available(); //尝试建立客户对象
  if (client)                             //如果当前客户可用
  {
    WA_en = true;
    ED_client = true;
    Serial.println("[Client connected]");
    String readBuff;
    String sendBuff;
    uint8_t Heartbeat_count = 0;
    bool Heartbeat_status = false;
    bool data_begin = true;
    while (client.connected()) //如果客户端处于连接状态
    {
      if (client.available()) //如果有可读数据
      {
        char c = client.read();             //读取一个字节
        Serial.print(c);                    //从串口打印
        if (true == data_begin && c == '{') //接收到开始字符
        {
          data_begin = false;
        }
        if (false == data_begin && c != ' ') //去掉空格
        {
          readBuff += c;
        }
        if (false == data_begin && c == '}') //接收到结束字符
        {
          data_begin = true;
          if (true == readBuff.equals("{Heartbeat}"))
          {
            Heartbeat_status = true;
          }
          else
          {
            Serial2.print(readBuff);
          }
          //Serial2.print(readBuff);
          readBuff = "";
        }
      }
      if (Serial2.available())
      {
        char c = Serial2.read();
        sendBuff += c;
        if (c == '}') //接收到结束字符
        {
          client.print(sendBuff);
          Serial.print(sendBuff); //从串口打印
          sendBuff = "";
        }
      }

      static unsigned long Heartbeat_time = 0;
      if (millis() - Heartbeat_time > 1000) //心跳频率
      {
        client.print("{Heartbeat}");
        if (true == Heartbeat_status)
        {
          Heartbeat_status = false;
          Heartbeat_count = 0;
        }
        else if (false == Heartbeat_status)
        {
          Heartbeat_count += 1;
        }
        if (Heartbeat_count > 3)
        {
          Heartbeat_count = 0;
          Heartbeat_status = false;
          break;
        }
        Heartbeat_time = millis();
      }
      static unsigned long Test_time = 0;
      if (millis() - Test_time > 1000) //定时检测连接设备
      {
        Test_time = millis();
        //Serial2.println(WiFi.softAPgetStationNum());
        if (0 == (WiFi.softAPgetStationNum())) //如果连接的设备个数为“0” 则向车模发送停止命令
        {
          Serial2.print("{\"N\":100}");
          break;
        }
      }
    }
    Serial2.print("{\"N\":100}");
    client.stop(); //结束当前连接:
    Serial.println("[Client disconnected]");
  }
  else
  {
    if (ED_client == true)
    {
      ED_client = false;
      Serial2.print("{\"N\":100}");
    }
  }
}
/*作用于测试架*/
void FactoryTest(void)
{
  static String readBuff;
  String sendBuff;
  if (Serial2.available())
  {
    char c = Serial2.read();
    readBuff += c;
    if (c == '}') //接收到结束字符
    {
      if (true == readBuff.equals("{BT_detection}"))
      {
        Serial2.print("{BT_OK}");
        Serial.println("Factory...");
      }
      else if (true == readBuff.equals("{WA_detection}"))
      {
        Serial2.print("{");
        Serial2.print(CameraWebServerAP.wifi_name);
        Serial2.print("}");
        Serial.println("Factory...");
      }
      readBuff = "";
    }
  }
  {
    if ((WiFi.softAPgetStationNum())) //连接的设备个数不为“0” led指示灯长亮
    {
      if (true == WA_en)
      {
        digitalWrite(13, LOW);
        Serial2.print("{WA_OK}");
        WA_en = false;
      }
    }
    else
    {
      //获取时间戳 timestamp
      static unsigned long Test_time;
      static bool en = true;
      if (millis() - Test_time > 100)
      {
        if (false == WA_en)
        {
          Serial2.print("{WA_NO}");
          WA_en = true;
        }
        if (en == true)
        {
          en = false;
          digitalWrite(13, HIGH);
        }
        else
        {
          en = true;
          digitalWrite(13, LOW);
        }
        Test_time = millis();
      }
    }
  }
}
void setup()
{
  Serial.begin(9600);
  delay(2000);  // let USB serial settle before printing
  Serial.println("[setup] started");

  Serial2.begin(9600, SERIAL_8N1, RXD2, TXD2);
  Serial.println("[setup] Serial2 ready");

  // CameraWebServerAP.initCamera();   // skip on boards without camera
  Serial.println("[setup] skipping camera init (no camera on this board)");

  Serial.println("[setup] attempting WiFi STA connection...");
  if (CameraWebServerAP.connectToRouter(HOME_SSID, HOME_PASSWORD, 10000)) {
    Serial.println("[setup] STA mode active");
    xTaskCreate(heartbeatTask, "heartbeat", 8192, NULL, 1, NULL);
    Serial.println("[setup] heartbeat task started (every 30 min)");
  } else {
    Serial.println("[setup] STA failed, falling back to AP mode");
    CameraWebServerAP.setupAP();
    server.begin();
    Serial.println("[setup] AP mode ready");
  }
  delay(100);
  // while (Serial.read() >= 0)
  // {
  //   /*清空串口缓存...*/
  // }
  // while (Serial2.read() >= 0)
  // {
  //   /*清空串口缓存...*/
  // }
  pinMode(13, OUTPUT);
  digitalWrite(13, HIGH);
  Serial.println("Elegoo-2020...");
  Serial2.print("{Factory}");
}
void loop()
{
  SocketServer_Test();
  FactoryTest();
}

/*
C:\Program Files (x86)\Arduino\hardware\espressif\arduino-esp32/tools/esptool/esptool.exe --chip esp32 --port COM6 --baud 460800 --before default_reset --after hard_reset write_flash -z --flash_mode dio --flash_freq 80m --flash_size detect 
0xe000 C:\Program Files (x86)\Arduino\hardware\espressif\arduino-esp32/tools/partitions/boot_app0.bin 
0x1000 C:\Program Files (x86)\Arduino\hardware\espressif\arduino-esp32/tools/sdk/bin/bootloader_qio_80m.bin 
0x10000 C:\Users\Faynman\Documents\Arduino\Hex/CameraWebServer_AP_20200608xxx.ino.bin 
0x8000 C:\Users\Faynman\Documents\Arduino\Hex/CameraWebServer_AP_20200608xxx.ino.partitions.bin 

flash:path
C:\Program Files (x86)\Arduino\hardware\espressif\arduino-esp32\tools\partitions\boot_app0.bin
C:\Program Files (x86)\Arduino\hardware\espressif\arduino-esp32\tools\sdk\bin\bootloader_dio_40m.bin
C:\Users\Faynman\Documents\Arduino\Hex\CameraWebServer_AP_20200608xxx.ino.partitions.bin
*/
//esptool.py-- port / dev / ttyUSB0-- baub 261216 write_flash-- flash_size = detect 0 GetChipID.ino.esp32.bin
