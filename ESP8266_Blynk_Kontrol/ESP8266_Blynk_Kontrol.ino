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