/*
#include <WiFi.h>
#include <WebServer.h>
#include "esp_camera.h"
#include "esp_system.h"
#include <string.h>

// =====================================================
// 1. KONFIGURASI WIFI DAN FLASK API
// =====================================================
const char* ssid = "infor";
const char* password = ""; 

#ifndef FLASK_HOST
#define FLASK_HOST "127.0.0.1"
#endif
const char* serverHost = FLASK_HOST;
#ifndef FLASK_PORT
#define FLASK_PORT 5000
#endif
const int serverPort = FLASK_PORT;

WebServer server(80); 

unsigned long lastCaptureTime = 0;
const unsigned long timerInterval = 60000; // 60 detik

// =====================================================
// 2. PIN KAMERA ESP32-S3 WROOM CAM
// =====================================================
#define PWDN_GPIO_NUM     -1
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM     15
#define SIOD_GPIO_NUM     4
#define SIOC_GPIO_NUM     5
#define Y9_GPIO_NUM       16
#define Y8_GPIO_NUM       17
#define Y7_GPIO_NUM       18
#define Y6_GPIO_NUM       12
#define Y5_GPIO_NUM       10
#define Y4_GPIO_NUM       8
#define Y3_GPIO_NUM       9
#define Y2_GPIO_NUM       11
#define VSYNC_GPIO_NUM    6
#define HREF_GPIO_NUM     7
#define PCLK_GPIO_NUM     13

bool cameraReady = false;

// =====================================================
// 3. INISIALISASI KAMERA
// =====================================================
void initCamera() {
  Serial.println("\n================================");
  Serial.println("MEMULAI INISIALISASI KAMERA");
  Serial.println("================================");

  if (psramFound()) {
    Serial.println("PSRAM TERDETEKSI!");
  } else {
    Serial.println("PSRAM TIDAK TERDETEKSI! Kamera tidak akan diinisialisasi.");
    cameraReady = false;
    return;
  }

  camera_config_t config = {};
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;
  config.frame_size = FRAMESIZE_QVGA;
  config.jpeg_quality = 15;
  config.fb_count = 1;
  config.fb_location = CAMERA_FB_IN_PSRAM;
  config.grab_mode = CAMERA_GRAB_WHEN_EMPTY;

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("GAGAL INISIALISASI KAMERA: 0x%x\n", err);
    cameraReady = false;
    return;
  }
  Serial.println("KAMERA BERHASIL DIINISIALISASI!");
  cameraReady = true;
}

// =====================================================
// 4. MENGIRIM FOTO KE FLASK API
// =====================================================
void sendPhoto() {
  if (!cameraReady) return;

  Serial.println("\nMENGAMBIL FOTO STRAWBERRY...");
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) {
    Serial.println("GAGAL MENGAMBIL FOTO!");
    return;
  }

  WiFiClient client;
  client.setTimeout(10000);
  if (!client.connect(serverHost, serverPort)) {
    Serial.println("GAGAL TERHUBUNG KE FLASK SERVER!");
    esp_camera_fb_return(fb);
    return;
  }

  String boundary = "ESP32Boundary";
  String head = "--" + boundary + "\r\nContent-Disposition: form-data; name=\"file\"; filename=\"strawberry.jpg\"\r\nContent-Type: image/jpeg\r\n\r\n";
  String tail = "\r\n--" + boundary + "--\r\n";
  uint32_t totalLen = head.length() + fb->len + tail.length();

  client.println("POST /predict HTTP/1.1");
  client.println("Host: " + String(serverHost));
  client.println("Content-Length: " + String(totalLen));
  client.println("Content-Type: multipart/form-data; boundary=" + boundary);
  client.println("Connection: close\r\n");
  client.print(head);

  size_t fbLen = fb->len;
  for (size_t n = 0; n < fbLen; n += 1024) {
    size_t chunk = (fbLen - n < 1024) ? (fbLen - n) : 1024;
    client.write(fb->buf + n, chunk);
  }

  client.print(tail);
  Serial.println("Foto sudah dikirim! Menunggu respons...");

  unsigned long responseStart = millis();
  while (!client.available() && client.connected() && millis() - responseStart < 10000) {
    delay(10);
  }

  if (client.available()) {
    while (client.available()) {
      Serial.println(client.readStringUntil('\n'));
    }
  } else {
    Serial.println("Server tidak memberikan respons!");
  }

  client.stop();
  esp_camera_fb_return(fb);
  Serial.println("PROSES PENGIRIMAN SELESAI");
}

// =====================================================
// 5. ROUTE HANDLER & SETUP
// =====================================================
void handleCapture() {
  Serial.println("\n[TRIGGER] Perintah memfoto diterima dari Website!");
  server.send(200, "application/json", "{\"status\":\"ok\"}");
  sendPhoto();
}

void setup() {
  Serial.begin(115200);
  delay(1500);

  initCamera();

  Serial.println("\nMenghubungkan ke Wi-Fi...");
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  
  if (strlen(password) > 0) {
    WiFi.begin(ssid, password);
  } else {
    WiFi.begin(ssid);
  }

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println("\n\nWIFI BERHASIL TERHUBUNG!");
  Serial.print("IP ESP32 : ");
  Serial.println(WiFi.localIP()); 

  server.on("/capture", HTTP_GET, handleCapture);
  server.begin();
}

// =====================================================
// 6. LOOP
// =====================================================
void loop() {
  if (WiFi.status() == WL_CONNECTED) {
    server.handleClient(); // Trigger Manual

    unsigned long currentMillis = millis();
    if (currentMillis - lastCaptureTime >= timerInterval || lastCaptureTime == 0) {
      lastCaptureTime = currentMillis;
      sendPhoto(); // Trigger Otomatis
    }
  } else {
    static unsigned long lastStatusTime = 0;
    if (millis() - lastStatusTime >= 5000) {
      lastStatusTime = millis();
      Serial.println("Menunggu koneksi Wi-Fi...");
    }
  }
  delay(10);
}
  */

#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <DHT.h>
#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>

// ==================================================
// 1. KONFIGURASI PIN
// ==================================================
#define PIN_SOIL A0
#define PIN_DHT  D7
#define PIN_PUMP D5
#define PIN_FAN  D6

#define DHT_TYPE DHT11

// Relay active LOW
#define RELAY_ON  LOW
#define RELAY_OFF HIGH

LiquidCrystal_I2C lcd(0x27, 16, 2);

DHT dht(PIN_DHT, DHT_TYPE);

// ==================================================
// KONFIGURASI WIFI, FLASK, DAN MQTT
// ==================================================
const char* WIFI_SSID = "JTI-3_E";
const char* WIFI_PASS = "";

// Endpoint Flask. Pastikan Flask menyediakan POST /api/sensor.
const char* FLASK_URL = "http://10.10.18.201:5000/api/sensor";

// Asumsi broker Mosquitto berjalan di laptop yang sama.
// Jika broker berbeda, ganti MQTT_SERVER dengan IP broker.
// MQTT TLS: broker menggunakan port 8883.
// Host harus cocok dengan CN/SAN sertifikat broker. Jika sertifikat
// diterbitkan untuk hostname, isi MQTT_SERVER dengan hostname tersebut,
// bukan IP. Ini tidak mengubah alamat Flask di atas.
const char* MQTT_SERVER = "10.10.18.201";
const uint16_t MQTT_PORT = 8883;

// GANTI isi di bawah dengan CA root/intermediate PEM asli dari penyedia broker.
// Sertifikat placeholder ini TIDAK valid untuk koneksi; jangan dibiarkan saat upload.
static const char MQTT_ROOT_CA[] PROGMEM = R"EOF(
-----BEGIN CERTIFICATE-----
MIIDjjCCAnagAwIBAgIQAzrx5qcRqaC7KGSxHQn65TANBgkqhkiG9w0BAQsFADBh
MQswCQYDVQQGEwJVUzEVMBMGA1UEChMMRGlnaUNlcnQgSW5jMRkwFwYDVQQLExB3
d3cuZGlnaWNlcnQuY29tMSAwHgYDVQQDExdEaWdpQ2VydCBHbG9iYWwgUm9vdCBH
MjAeFw0xMzA4MDExMjAwMDBaFw0zODAxMTUxMjAwMDBaMGExCzAJBgNVBAYTAlVT
MRUwEwYDVQQKEwxEaWdpQ2VydCBJbmMxGTAXBgNVBAsTEHd3dy5kaWdpY2VydC5j
b20xIDAeBgNVBAMTF0RpZ2lDZXJ0IEdsb2JhbCBSb290IEcyMIIBIjANBgkqhkiG
9w0BAQEFAAOCAQ8AMIIBCgKCAQEAuzfNNNx7a8myaJCtSnX/RrohCgiN9RlUyfuI
2/Ou8jqJkTx65qsGGmvPrC3oXgkkRLpimn7Wo6h+4FR1IAWsULecYxpsMNzaHxmx
1x7e/dfgy5SDN67sH0NO3Xss0r0upS/kqbitOtSZpLYl6ZtrAGCSYP9PIUkY92eQ
q2EGnI/yuum06ZIya7XzV+hdG82MHauVBJVJ8zUtluNJbd134/tJS7SsVQepj5Wz
tCO7TG1F8PapspUwtP1MVYwnSlcUfIKdzXOS0xZKBgyMUNGPHgm+F6HmIcr9g+UQ
vIOlCsRnKPZzFBQ9RnbDhxSJITRNrw9FDKZJobq7nMWxM4MphQIDAQABo0IwQDAP
BgNVHRMBAf8EBTADAQH/MA4GA1UdDwEB/wQEAwIBhjAdBgNVHQ4EFgQUTiJUIBiV
5uNu5g/6+rkS7QYXjzkwDQYJKoZIhvcNAQELBQADggEBAGBnKJRvDkhj6zHd6mcY
1Yl9PMWLSn/pvtsrF9+wX3N3KjITOYFnQoQj8kVnNeyIv/iPsGEMNKSuIEyExtv4
NeF22d+mQrvHRAiGfzZ0JFrabA0UWTW98kndth/Jsw1HKj2ZL7tcu7XUIOGZX1NG
Fdtom/DzMNU+MeKNhJ7jitralj41E6Vf8PlwUHBHQRFXGU7Aj64GxJUTFy8bJZ91
8rGOmaFvE7FBcf6IKshPECBV1/MUReXgRPTqh5Uykw7+U0b6LJ3/iyK5S9kJRaTe
pLiaWN0bfVKfjllDiIGknibVb63dDcY3fe0Dkhvld1927jyNxF1WW6LZZm6zNTfl
MrY=
-----END CERTIFICATE-----

)EOF";
const char* MQTT_USER = "ws_tertanam";
const char* MQTT_PASS = "tertanam123";
const char* MQTT_TOPIC = "strawberry/monitoring";

WiFiClientSecure networkClient;
PubSubClient mqttClient(networkClient);

unsigned long lastMqttReconnect = 0;
const unsigned long MQTT_RECONNECT_INTERVAL = 5000UL;

// ==================================================
// 2. KALIBRASI SENSOR FC-28
// ==================================================
// Sesuaikan berdasarkan pengukuran sensor milikmu.
// ADC ESP8266 umumnya 0-1023.
const int RAW_DRY = 1023;
const int RAW_WET = 350;

// Catatan:
// Hasil konversi merupakan indeks kelembapan relatif
// 0-100, bukan VWC terkalibrasi.

// ==================================================
// 3. PARAMETER SISTEM
// ==================================================
const float PUMP_MIN_SEC = 1.0;
const float PUMP_MS_PER_UNIT = 1000.0;

const unsigned long SOAK_MS = 60000UL;
const unsigned long READ_MS = 2000UL;

const float FAN_THRESHOLD = 5.0;

// ==================================================
// 4. FUNGSI KEANGGOTAAN TRAPEZOID
// ==================================================
float trap(float x, float a, float b,
           float c, float d) {

  if (x < a || x > d) return 0.0;

  if (x >= b && x <= c) return 1.0;

  if (x < b) {
    return (b == a) ? 1.0 :
           (x - a) / (b - a);
  }

  return (d == c) ? 1.0 :
         (d - x) / (d - c);
}

// ==================================================
// 5. FUZZIFIKASI INPUT IRIGASI
// ==================================================

// Input 1: Kelembapan tanah
// 0 = Kering, 1 = Lembap, 2 = Basah

void fuzzSoil(float s, float mu[3]) {

  mu[0] = trap(s, 0, 0, 30, 60);
  mu[1] = trap(s, 30, 60, 80, 90);
  mu[2] = trap(s, 70, 90, 100, 100);
}

// Input 2: Suhu udara
// 0 = Dingin, 1 = Normal, 2 = Panas

void fuzzTemp(float t, float mu[3]) {

  mu[0] = trap(t, 0, 0, 12, 15);
  mu[1] = trap(t, 12, 15, 23, 25);
  mu[2] = trap(t, 23, 25, 30, 30);
}

// Input 3: Kelembapan udara
// 0 = Rendah, 1 = Normal, 2 = Tinggi

void fuzzAir(float h, float mu[3]) {

  mu[0] = trap(h, 0, 0, 50, 80);
  mu[1] = trap(h, 50, 80, 85, 90);
  mu[2] = trap(h, 85, 90, 100, 100);
}

// ==================================================
// 6. OUTPUT IRIGASI
// ==================================================
// 0 = OFF
// 1 = Cepat
// 2 = Sedang
// 3 = Lama

float muPumpOut(int label, float x) {

  switch (label) {

    case 0:
      return trap(x, 0, 0, 0, 2);

    case 1:
      return trap(x, 3, 5, 7, 9);

    case 2:
      return trap(x, 7, 10, 12, 15);

    default:
      return trap(x, 13, 16, 20, 20);
  }
}

// ==================================================
// 7. BASIS ATURAN FUZZY IRIGASI
// ==================================================
// RULE[tanah][suhu][kelembapan udara]
//
// Output:
// 0 = OFF
// 1 = Cepat
// 2 = Sedang
// 3 = Lama
//
// Aturan pengembangan berdasarkan 9 aturan jurnal
// dengan penyesuaian kelembapan udara.

const uint8_t RULE_PUMP[3][3][3] = {

  // TANAH KERING
  {
    // Suhu Dingin: udara Rendah, Normal, Tinggi
    {2, 1, 0},

    // Suhu Normal
    {3, 3, 2},

    // Suhu Panas
    {3, 3, 2}
  },

  // TANAH LEMBAP
  {
    // Suhu Dingin
    {1, 0, 0},

    // Suhu Normal
    {2, 1, 0},

    // Suhu Panas
    {3, 2, 1}
  },

  // TANAH BASAH
  {
    // Suhu Dingin
    {0, 0, 0},

    // Suhu Normal
    {0, 0, 0},

    // Suhu Panas
    {2, 1, 0}
  }
};

// ==================================================
// 8. INFERENSI DAN DEFUZZIFIKASI IRIGASI
// ==================================================

float fuzzyIrrigation(float temp,
                      float air,
                      float soil) {

  float mS[3], mT[3], mA[3];

  fuzzSoil(soil, mS);
  fuzzTemp(temp, mT);
  fuzzAir(air, mA);

  // Kekuatan masing-masing output
  float strength[4] = {0, 0, 0, 0};

  // Inferensi MIN dan agregasi MAX
  for (int s = 0; s < 3; s++) {

    for (int t = 0; t < 3; t++) {

      for (int a = 0; a < 3; a++) {

        float w = min(
          mS[s],
          min(mT[t], mA[a])
        );

        int output = RULE_PUMP[s][t][a];

        if (w > strength[output]) {
          strength[output] = w;
        }
      }
    }
  }

  // Defuzzifikasi centroid
  // Domain durasi 0-20 detik
  float numerator = 0;
  float denominator = 0;

  for (float x = 0; x <= 20.0; x += 0.1) {

    float mu = 0;

    for (int k = 0; k < 4; k++) {

      float value = min(
        strength[k],
        muPumpOut(k, x)
      );

      mu = max(mu, value);
    }

    numerator += mu * x;
    denominator += mu;
  }

  if (denominator > 0) {
    return numerator / denominator;
  }

  return 0;
}

// ==================================================
// 9. FUZZY MAMDANI PENGENDALI KIPAS
// ==================================================
// Input: Suhu dan kelembapan udara
// Output: OFF / ON

// Aturan kipas:
// Suhu dingin  : OFF, OFF, ON
// Suhu normal  : OFF, OFF, ON
// Suhu panas   : ON,  ON,  ON
//
// Kolom: udara rendah, normal, tinggi
//
// 0 = OFF
// 1 = ON

const uint8_t RULE_FAN[3][3] = {

  {0, 0, 1},
  {0, 0, 1},
  {1, 1, 1}
};

// Membership output kipas
float muFanOut(int label, float x) {

  if (label == 0) {
    return trap(x, 0, 0, 2, 5);
  }

  return trap(x, 5, 8, 10, 10);
}

// Inferensi dan defuzzifikasi kipas
float fuzzyFan(float temp, float air) {

  float mT[3], mA[3];

  fuzzTemp(temp, mT);
  fuzzAir(air, mA);

  float strength[2] = {0, 0};

  for (int t = 0; t < 3; t++) {

    for (int a = 0; a < 3; a++) {

      float w = min(mT[t], mA[a]);

      int output = RULE_FAN[t][a];

      if (w > strength[output]) {
        strength[output] = w;
      }
    }
  }

  // Centroid output 0-10
  float numerator = 0;
  float denominator = 0;

  for (float x = 0; x <= 10.0; x += 0.1) {

    float mu = 0;

    for (int k = 0; k < 2; k++) {

      float value = min(
        strength[k],
        muFanOut(k, x)
      );

      mu = max(mu, value);
    }

    numerator += mu * x;
    denominator += mu;
  }

  if (denominator > 0) {
    return numerator / denominator;
  }

  return 0;
}

// ==================================================
// 10. PEMBACAAN SENSOR
// ==================================================

float readSoilPercent() {

  long sum = 0;

  for (int i = 0; i < 10; i++) {

    sum += analogRead(PIN_SOIL);
    delay(5);
  }

  float raw = sum / 10.0;

  float pct =
    (RAW_DRY - raw) * 100.0 /
    (RAW_DRY - RAW_WET);

  return constrain(pct, 0, 100);
}

// ==================================================
// 11. STATE SISTEM
// ==================================================

bool pumpOn = false;
bool fanOn = false;
bool hasWatered = false;
bool envValid = false;

unsigned long pumpStart = 0;
unsigned long pumpDurMs = 0;
unsigned long lastPumpEnd = 0;
unsigned long lastRead = 0;

float temp = 0;
float hum = 0;
float soil = 0;

float irrigationOut = 0;
float fanOut = 0;

// ==================================================
// 12. KONTROL RELAY
// ==================================================

void setPump(bool on) {

  pumpOn = on;

  digitalWrite(
    PIN_PUMP,
    on ? RELAY_ON : RELAY_OFF
  );
}

void setFan(bool on) {

  fanOn = on;

  digitalWrite(
    PIN_FAN,
    on ? RELAY_ON : RELAY_OFF
  );
}

// ==================================================
// 13. LCD
// ==================================================

void updateLCD() {

  char line1[17];
  char line2[17];

  snprintf(
    line1,
    sizeof(line1),
    "T:%4.1f H:%2.0f%%",
    temp,
    hum
  );

  snprintf(
    line2,
    sizeof(line2),
    "S:%3.0f P:%s F:%s",
    soil,
    pumpOn ? "ON" : "OFF",
    fanOn ? "ON" : "OFF"
  );

  lcd.setCursor(0, 0);
  lcd.print("                ");
  lcd.setCursor(0, 0);
  lcd.print(line1);

  lcd.setCursor(0, 1);
  lcd.print("                ");
  lcd.setCursor(0, 1);
  lcd.print(line2);
}

// ==================================================
// 14. KONEKSI WIFI, MQTT, DAN PENGIRIMAN DATA
// ==================================================

void connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);

  Serial.print("Menghubungkan WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println();
  Serial.print("WiFi terhubung. IP ESP8266: ");
  Serial.println(WiFi.localIP());
}

void reconnectMQTT() {
  if (WiFi.status() != WL_CONNECTED || mqttClient.connected()) {
    return;
  }

  unsigned long now = millis();
  if (now - lastMqttReconnect < MQTT_RECONNECT_INTERVAL) {
    return;
  }
  lastMqttReconnect = now;

  String clientId = "StrawberryCare-" + String(ESP.getChipId(), HEX);

  Serial.print("Menghubungkan MQTT...");
  if (mqttClient.connect(clientId.c_str(), MQTT_USER, MQTT_PASS)) {
    Serial.println("berhasil");
  } else {
    Serial.print("gagal, rc=");
    Serial.println(mqttClient.state());
  }
}

String buildTelemetryJSON() {
  String json = "{";
  json += "\"temperature\":" + String(temp, 1) + ",";
  json += "\"humidity_air\":" + String(hum, 1) + ",";
  json += "\"soil_moisture\":" + String(soil, 1) + ",";
  json += "\"irrigation_output\":" + String(irrigationOut, 2) + ",";
  json += "\"fan_output\":" + String(fanOut, 2) + ",";
  json += "\"pump_status\":\"" + String(pumpOn ? "ON" : "OFF") + "\",";
  json += "\"fan_status\":\"" + String(fanOn ? "ON" : "OFF") + "\"";
  json += "}";
  return json;
}

void sendTelemetry() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi terputus, data tidak dikirim.");
    return;
  }

  String payload = buildTelemetryJSON();

  // Kirim data ke Flask melalui HTTP POST.
  WiFiClient httpClient;
  HTTPClient http;

  if (http.begin(httpClient, FLASK_URL)) {
    http.addHeader("Content-Type", "application/json");
    int httpCode = http.POST(payload);

    Serial.print("Flask HTTP response: ");
    Serial.println(httpCode);

    if (httpCode > 0) {
      Serial.println(http.getString());
    } else {
      Serial.println("Gagal mengirim data ke Flask.");
    }
    http.end();
  } else {
    Serial.println("Tidak dapat memulai koneksi HTTP ke Flask.");
  }

  // Kirim payload yang sama ke MQTT.
  if (mqttClient.connected()) {
    bool published = mqttClient.publish(
      MQTT_TOPIC,
      payload.c_str()
    );
    Serial.println(published
      ? "Data berhasil dipublish ke MQTT."
      : "Publish MQTT gagal.");
  } else {
    Serial.println("MQTT belum terhubung; data tidak dipublish.");
  }
}

// ==================================================
// 15. SETUP
// ==================================================

void setup() {

  Serial.begin(115200);

  connectWiFi();
  networkClient.setCACert(MQTT_ROOT_CA);
  mqttClient.setServer(MQTT_SERVER, MQTT_PORT);

  pinMode(PIN_PUMP, OUTPUT);
  pinMode(PIN_FAN, OUTPUT);

  setPump(false);
  setFan(false);

  dht.begin();

  lcd.init();
  lcd.backlight();

  lcd.setCursor(0, 0);
  lcd.print("Strawberry Care");

  lcd.setCursor(0, 1);
  lcd.print("Fuzzy Mamdani");

  delay(1500);
  lcd.clear();
}

// ==================================================
// 16. LOOP UTAMA
// ==================================================

void loop() {

  if (WiFi.status() == WL_CONNECTED) {
    if (!mqttClient.connected()) reconnectMQTT();
    mqttClient.loop();
  }

  unsigned long now = millis();

  // ----------------------------------------------
  // A. MATIKAN POMPA SAAT DURASI HABIS
  // ----------------------------------------------

  if (pumpOn && now - pumpStart >= pumpDurMs) {

    setPump(false);

    lastPumpEnd = now;
    hasWatered = true;

    Serial.println("Pompa selesai menyiram.");
  }

  // ----------------------------------------------
  // B. PEMBACAAN SENSOR
  // ----------------------------------------------

  if (now - lastRead >= READ_MS) {

    lastRead = now;

    float t = dht.readTemperature();
    float h = dht.readHumidity();

    if (!isnan(t) && !isnan(h)) {

      temp = t;
      hum = h;

      envValid = true;
    }

    soil = readSoilPercent();

    // --------------------------------------------
    // C. PENGENDALI KIPAS FUZZY MAMDANI
    // --------------------------------------------

    if (envValid) {

      fanOut = fuzzyFan(temp, hum);

      setFan(fanOut >= FAN_THRESHOLD);

    }

    // --------------------------------------------
    // D. PENGENDALI IRIGASI FUZZY MAMDANI
    // --------------------------------------------

    if (envValid) {

      irrigationOut = fuzzyIrrigation(
        temp,
        hum,
        soil
      );

      bool soakDone =
        !hasWatered ||
        (now - lastPumpEnd >= SOAK_MS);

      if (
        !pumpOn &&
        soakDone &&
        irrigationOut >= PUMP_MIN_SEC
      ) {

        pumpDurMs =
          (unsigned long)(
            irrigationOut * PUMP_MS_PER_UNIT
          );

        pumpStart = now;

        setPump(true);
      }
    }

    // --------------------------------------------
    // E. SERIAL MONITOR
    // --------------------------------------------

    Serial.println("--------------------------------");

    Serial.printf(
      "Suhu             : %.1f C\n", temp
    );

    Serial.printf(
      "Kelembapan Udara : %.1f %%\n", hum
    );

    Serial.printf(
      "Kelembapan Tanah : %.1f\n", soil
    );

    Serial.printf(
      "Output Irigasi   : %.2f detik\n",
      irrigationOut
    );

    Serial.printf(
      "Output Kipas     : %.2f\n", fanOut
    );

    Serial.printf(
      "Pompa            : %s\n",
      pumpOn ? "ON" : "OFF"
    );

    Serial.printf(
      "Kipas            : %s\n",
      fanOn ? "ON" : "OFF"
    );

    Serial.printf(
      "Masa Resap       : %s\n",
      (!hasWatered ||
       now - lastPumpEnd >= SOAK_MS)
        ? "Selesai"
        : "Menunggu"
    );

    Serial.println("--------------------------------");

    // --------------------------------------------
    // F. UPDATE LCD
    // --------------------------------------------

    updateLCD();

    // Kirim pembacaan terbaru ke Flask dan MQTT.
    sendTelemetry();
  }
}
