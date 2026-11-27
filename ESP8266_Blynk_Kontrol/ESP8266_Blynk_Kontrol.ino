
#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <DHT.h>

// ---------------- PIN ----------------
#define PIN_SOIL   A0
#define PIN_DHT    D7
#define PIN_PUMP   D5
#define PIN_FAN    D6

// Modul relay umumnya active LOW. Ubah jika relay Anda active HIGH.
#define RELAY_ON   LOW
#define RELAY_OFF  HIGH

// ---------------- KALIBRASI FC-28 ----------------
// Ukur sendiri: nilai ADC saat sensor di tanah kering & tanah jenuh air.
const int RAW_DRY = 1024;   // ADC saat tanah kering
const int RAW_WET = 350;    // ADC saat tanah jenuh air
// Skala hasil: 0 - 40 (%), sesuai domain himpunan fuzzy tanah

// ---------------- PARAMETER SISTEM ----------------
const float PUMP_MS_PER_UNIT = 1000.0;  // 1 satuan keluaran fuzzy = 1000 ms
const float PUMP_MIN_SEC     = 1.0;     // di bawah ini dianggap tidak menyiram
const unsigned long SOAK_MS  = 60000UL; // jeda tunggu air meresap sebelum siram lagi
const unsigned long READ_MS  = 2000UL;  // interval baca sensor

const float FAN_ON_TEMP  = 24.7;  // kipas ON jika suhu > ini
const float FAN_OFF_TEMP = 23.5;  // kipas OFF jika suhu < ini (histeresis)
const float FAN_ON_HUM   = 90.0;  // atau kelembaban udara > ini

LiquidCrystal_I2C lcd(0x27, 16, 2);
DHT dht(PIN_DHT, DHT11);

// ---------------- FUNGSI KEANGGOTAAN ----------------
// Trapesium [a,b,c,d]; segitiga = trap(a,b,b,c)
float trap(float x, float a, float b, float c, float d) {
  if (x < a || x > d) return 0.0;
  if (x >= b && x <= c) return 1.0;
  if (x < b) return (b == a) ? 1.0 : (x - a) / (b - a);
  return (d == c) ? 1.0 : (d - x) / (d - c);
}

// Suhu: 0 Dingin, 1 Normal, 2 Panas
void fuzzTemp(float t, float mu[3]) {
  mu[0] = trap(t, 0, 0, 12, 17.1);
  mu[1] = trap(t, 12, 17.1, 24.7, 30);
  mu[2] = trap(t, 24.7, 30, 40, 40);
}
// Kelembaban udara: 0 Rendah, 1 Normal, 2 Tinggi
void fuzzAir(float h, float mu[3]) {
  mu[0] = trap(h, 0, 0, 30, 40);
  mu[1] = trap(h, 30, 40, 80, 90);
  mu[2] = trap(h, 80, 90, 100, 100);
}
// Kelembaban tanah: 0 Kering, 1 Normal, 2 Basah
void fuzzSoil(float s, float mu[3]) {
  mu[0] = trap(s, 0, 0, 6, 10);
  mu[1] = trap(s, 6, 10, 22.6, 26);
  mu[2] = trap(s, 22.6, 26, 40, 40);
}
// Keluaran lama siram (detik): 0 Off, 1 Sedang, 2 Lama
float muOut(int label, float x) {
  switch (label) {
    case 0: return trap(x, 0, 0, 0, 2);      // Off    (segitiga 0,0,2)
    case 1: return trap(x, 1, 3.5, 3.5, 6);  // Sedang (segitiga 1,3.5,6)
    default: return trap(x, 5, 8, 10, 10);   // Lama   (trapesium)
  }
}

// ---------------- BASIS ATURAN (27 aturan) ----------------
// RULE[tanah][suhu][udara] -> 0 Off, 1 Sedang, 2 Lama
const uint8_t RULE[3][3][3] = {
  // Tanah KERING        udara: Rendah, Normal, Tinggi
  { {1, 1, 1},        // suhu Dingin
    {2, 1, 1},        // suhu Normal
    {2, 2, 1} },      // suhu Panas
  // Tanah NORMAL
  { {0, 0, 0},
    {0, 0, 0},
    {1, 0, 0} },
  // Tanah BASAH
  { {0, 0, 0},
    {0, 0, 0},
    {0, 0, 0} }
};

// ---------------- MAMDANI: inferensi + defuzzifikasi centroid ----------------
float fuzzyIrrigation(float temp, float air, float soil) {
  float mT[3], mA[3], mS[3];
  fuzzTemp(temp, mT);
  fuzzAir(air, mA);
  fuzzSoil(soil, mS);

  // Implikasi (MIN) & komposisi aturan (MAX) per label keluaran
  float strength[3] = {0, 0, 0};
  for (int s = 0; s < 3; s++)
    for (int t = 0; t < 3; t++)
      for (int a = 0; a < 3; a++) {
        float w = min(mS[s], min(mT[t], mA[a]));
        int out = RULE[s][t][a];
        if (w > strength[out]) strength[out] = w;
      }

  // Defuzzifikasi centroid, domain 0-10 detik, langkah 0.1
  float num = 0, den = 0;
  for (float x = 0; x <= 10.0; x += 0.1) {
    float mu = 0;
    for (int k = 0; k < 3; k++) mu = max(mu, min(strength[k], muOut(k, x)));
    num += mu * x;
    den += mu;
  }
  return (den > 0) ? num / den : 0.0;
}

// ---------------- STATE ----------------
bool pumpOn = false, fanOn = false;
unsigned long pumpStart = 0, pumpDurMs = 0, lastPumpEnd = 0, lastRead = 0;
bool hasWatered = false;
float temp = 0, hum = 0, soil = 0, fuzzyOut = 0;

float readSoilPercent() {
  long sum = 0;
  for (int i = 0; i < 10; i++) { sum += analogRead(PIN_SOIL); delay(5); }
  float raw = sum / 10.0;
  float pct = (RAW_DRY - raw) * 40.0 / (RAW_DRY - RAW_WET);  // skala 0-40
  return constrain(pct, 0, 40);
}

void setPump(bool on) { pumpOn = on; digitalWrite(PIN_PUMP, on ? RELAY_ON : RELAY_OFF); }
void setFan(bool on)  { fanOn  = on; digitalWrite(PIN_FAN,  on ? RELAY_ON : RELAY_OFF); }

void updateLCD() {
  char l1[17], l2[17];
  snprintf(l1, sizeof(l1), "T:%4.1fC H:%3.0f%%  ", temp, hum);
  snprintf(l2, sizeof(l2), "S:%4.1f P:%s F:%s", soil, pumpOn ? "ON " : "OFF", fanOn ? "ON" : "OFF");
  lcd.setCursor(0, 0); lcd.print(l1);
  lcd.setCursor(0, 1); lcd.print(l2);
}

void setup() {
  Serial.begin(115200);
<<<<<<< HEAD
  pinMode(PIN_PUMP, OUTPUT);
  pinMode(PIN_FAN, OUTPUT);
  setPump(false);
  setFan(false);

  dht.begin();
  lcd.init();
  lcd.backlight();
  lcd.print("Irigasi Fuzzy");
  lcd.setCursor(0, 1);
  lcd.print("Strawberry");
  delay(1500);
  lcd.clear();
}

void loop() {
  unsigned long now = millis();

  // Matikan pompa saat durasi selesai (non-blocking)
  if (pumpOn && now - pumpStart >= pumpDurMs) {
    setPump(false);
    lastPumpEnd = now;
    hasWatered = true;
  }

  if (now - lastRead >= READ_MS) {
    lastRead = now;

    float t = dht.readTemperature();
    float h = dht.readHumidity();
    if (!isnan(t) && !isnan(h)) { temp = t; hum = h; }
    soil = readSoilPercent();

    // Kipas: histeresis agar relay tidak bolak-balik
    if (!fanOn && (temp > FAN_ON_TEMP || hum > FAN_ON_HUM)) setFan(true);
    else if (fanOn && temp < FAN_OFF_TEMP && hum < FAN_ON_HUM - 5) setFan(false);

    // Pompa: hitung fuzzy hanya jika pompa mati dan masa resap sudah lewat
    fuzzyOut = fuzzyIrrigation(temp, hum, soil);
    bool soakDone = !hasWatered || (now - lastPumpEnd >= SOAK_MS);
    if (!pumpOn && soakDone && fuzzyOut >= PUMP_MIN_SEC) {
      pumpDurMs = (unsigned long)(fuzzyOut * PUMP_MS_PER_UNIT);
      pumpStart = now;
      setPump(true);
    }

    Serial.printf("T=%.1f H=%.0f Soil=%.1f -> fuzzy=%.2f s | Pompa=%d Kipas=%d\n",
                  temp, hum, soil, fuzzyOut, pumpOn, fanOn);
    updateLCD();
  }
}

=======
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
>>>>>>> origin/feat/roi-web
