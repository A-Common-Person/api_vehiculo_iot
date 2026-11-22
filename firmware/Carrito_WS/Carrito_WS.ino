// Excavadora IoT 4.3. NodeMCU ESP8266, dos 74HC595 y optoacopladores.
#include <ESP8266WiFi.h>
#include <WiFiManager.h>
#include <WebSocketsClient.h>
#include <ArduinoJson.h>

#if __has_include("IoT43Local.h") && __has_include("IoT43Publico.h")
#error "Selecciona un solo archivo de configuración IoT 4.3."
#elif __has_include("IoT43Publico.h")
#include <time.h>
#include "IoT43Publico.h"
#define IOT43_PUBLICO 1
#elif __has_include("IoT43Local.h")
#include "IoT43Local.h"
#else
#error "Genera IoT43Publico.h o IoT43Local.h antes de compilar."
#endif

// ---------------------- PINES DE LOS 74HC595 ----------------------
const int dataPin  = D0;
const int clockPin = D2;
const int latchPin = D1;

// ------------------- POLARIDAD DE LOS OPTOACOPLADORES -------------------
// false = el opto se activa cuando la salida del 595 está en 1
// true  = el opto se activa cuando la salida está en 0 (activo en bajo)
const bool ACTIVO_EN_BAJO = false;

// ------------------ MAPEO DE SALIDAS (12 botones, Q0 a Q11) ------------------
// Chip 1 (Bits 0 a 7)
const uint16_t GIRAR_IZQ   = 1 << 0;  // Q0
const uint16_t AVANZAR     = 1 << 1;  // Q1
const uint16_t RETROCEDER  = 1 << 2;  // Q2
const uint16_t GIRAR_DER   = 1 << 3;  // Q3
const uint16_t VELOCIDAD   = 1 << 4;  // Q4
const uint16_t SONIDO      = 1 << 5;  // Q5
const uint16_t DEMO        = 1 << 6;  // Q6
const uint16_t LUZ         = 1 << 7;  // Q7

// Chip 2 (Bits 8 a 11)
const uint16_t DIAG_IZQ    = 1 << 8;   // Q0 del chip 2
const uint16_t GRUA_SUBIR  = 1 << 9;   // Q1 del chip 2 (Alzar pala)
const uint16_t GRUA_BAJAR  = 1 << 10;  // Q2 del chip 2 (Bajar pala)
const uint16_t DIAG_DER    = 1 << 11;  // Q3 del chip 2

// Variable para recordar el movimiento actual
uint16_t estadoActual = 0;

// ---------------------------- CONFIGURACIÓN WI-FI ----------------------------
const int PIN_RESET = D6;                  // D6 = GPIO12. A GND por 5 s para borrar la red Wi-Fi
const unsigned long TIEMPO_PULSACION_RESET = 5000;

const unsigned long TIEMPO_CONEXION_S   = 20;       // Segundos para probar la red guardada
const unsigned long TIEMPO_PORTAL_S     = 180;      // Segundos que el portal queda abierto sin uso
const unsigned long INTERVALO_REINTENTO = 10000;    // ms entre reintentos si se pierde la señal
const unsigned long INTERVALO_ESTADO    = 30000;    // ms entre mensajes de estado Wi-Fi

// ---------------------------- CONFIGURACIÓN WEBSOCKET ----------------------------
String rutaWS;
WebSocketsClient webSocket;
constexpr unsigned long MAXIMO_PULSO_43_MS = 250;
constexpr unsigned long MINIMO_PASO_DEMO_43_MS = 100;
constexpr unsigned long MAXIMO_PASO_DEMO_43_MS = 3000;
constexpr unsigned long PLAZO_CONFIRMACION_WSS_43_MS = 5000;
constexpr unsigned long REINICIO_WSS_43_MS = 20000;
bool enlaceListo43 = false;
bool wifiDisponibleWss43 = false;
unsigned long ultimoInicioWss43 = 0;
constexpr uint8_t CODIGOS_CONTROL_43[] = {1, 2, 3, 4, 5, 6, 9, 10, 11, 12, 13, 15};
int codigoContinuo43 = 0;

const int           COD_DETENER                 = 9;     // "codigo" de DETENER en la base de datos

bool wsConectado = false;
unsigned long wsConectadoDesde = 0;

bool movimientoPorTiempo = false;   // true = hay un movimiento que se apaga solo
unsigned long movimientoHasta = 0;

void actualizarShiftRegisters(uint16_t estadoBotones);

// Qué hace un comando en el carrito (se define aquí arriba para que Arduino compile bien)
struct AccionCarrito {
  uint16_t mascara;
  bool esPulso;
  const char* nombre;
};

bool buscarAccion(int codigo, AccionCarrito &accion);

WiFiManager wm;
char clavePortal[17];
String nombreDispositivo;

bool estabaConectado = false;
unsigned long ultimoReintento = 0;
unsigned long ultimoEstado = 0;

bool botonPresionado = false;
unsigned long inicioPulsacion = 0;

// ================================ SETUP ================================
void setup() {
  Serial.begin(115200);
  delay(200);

  pinMode(dataPin, OUTPUT);
  pinMode(clockPin, OUTPUT);
  pinMode(latchPin, OUTPUT);
  pinMode(PIN_RESET, INPUT_PULLUP);

  actualizarShiftRegisters(0);  // Todo apagado ANTES de iniciar el Wi-Fi

  Serial.println("IoT 4.3. Monitor Serie: x = DETENER.");

  WiFi.mode(WIFI_STA);
  nombreDispositivo = obtenerNombreDispositivo();
  WiFi.hostname(nombreDispositivo);

  Serial.print("Nombre del dispositivo: ");
  Serial.println(nombreDispositivo);
  Serial.print("MAC: ");
  Serial.println(WiFi.macAddress());

  snprintf(clavePortal, sizeof(clavePortal), "%08lx%08lx",
           static_cast<unsigned long>(ESP.random()), static_cast<unsigned long>(ESP.random()));
  configurarWiFiManager();
  conectarWiFi();
#ifdef IOT43_PUBLICO
  configTime(0, 0, "pool.ntp.org", "time.google.com");
  Serial.println("[WSS 4.3] Esperando la hora para verificar el certificado TLS.");
#endif
  iniciarWebSocket();
}

// ================================= LOOP =================================
void loop() {
  actualizarTemporizadores(); // Apaga movimientos y pulsos al alcanzar su duración
  atenderWebSocket43();
  if (Serial.available() && Serial.read() == 'x') detenerTodo();
  verificarBotonReset();    // GPIO a GND por 5 s (sin delay)
  verificarConexion();      // Reconexión sin bloquear
  mostrarEstadoPeriodico(); // Mensaje corto cada cierto tiempo
}

// Manda los datos a los dos 74HC595
void actualizarShiftRegisters(uint16_t estadoBotones) {
  if (ACTIVO_EN_BAJO) estadoBotones = ~estadoBotones;  // invierte si los optos son activo en bajo

  digitalWrite(latchPin, LOW);
  shiftOut(dataPin, clockPin, MSBFIRST, highByte(estadoBotones));  // Chip 2
  shiftOut(dataPin, clockPin, MSBFIRST, lowByte(estadoBotones));   // Chip 1
  digitalWrite(latchPin, HIGH);
}

// =============================== WEBSOCKET ===============================
// Canal autenticado de órdenes del ESP8266.
void iniciarWebSocket() {
  rutaWS = String("/ws/dispositivos/") + IOT43_UNIDAD;
  Serial.print("[WSS 4.3] Conectando a la unidad ");
  Serial.println(IOT43_UNIDAD);
#ifdef IOT43_PUBLICO
  static BearSSL::X509List certificados(IOT43_CA_PEM);
  webSocket.beginSslWithCA(IOT43_HOST, IOT43_PUERTO, rutaWS.c_str(), &certificados, "");
#else
  webSocket.beginSSL(IOT43_HOST, IOT43_PUERTO, rutaWS.c_str(), IOT43_HUELLA, "");
#endif
  const String autorizacion = String("Bearer ") + IOT43_TOKEN;
  webSocket.setAuthorization(autorizacion.c_str());
  wifiDisponibleWss43 = WiFi.status() == WL_CONNECTED;
  ultimoInicioWss43 = millis();
  webSocket.onEvent(eventoWebSocket);
  webSocket.setReconnectInterval(3500);
  webSocket.enableHeartbeat(6000, 3000, 2);
}

void atenderWebSocket43() {
  if (WiFi.status() != WL_CONNECTED) {
    if (wifiDisponibleWss43) {
      wifiDisponibleWss43 = false;
      wsConectado = false;
      enlaceListo43 = false;
      detenerTodo();
      webSocket.disconnect();
      Serial.println("[WSS 4.3] Salidas apagadas. Esperando que vuelva el Wi-Fi.");
    }
    return;
  }

#ifdef IOT43_PUBLICO
  constexpr time_t FECHA_MINIMA_TLS = 1704067200;  // 2024-01-01 UTC
  if (time(nullptr) < FECHA_MINIMA_TLS) return;
#endif

  const unsigned long ahora = millis();
  const bool confirmacionVencida = wsConectado && ahora - wsConectadoDesde >= PLAZO_CONFIRMACION_WSS_43_MS;
  const bool sinEnlace = !wsConectado && ahora - ultimoInicioWss43 >= REINICIO_WSS_43_MS;
  if (!wifiDisponibleWss43 || (!enlaceListo43 && (confirmacionVencida || sinEnlace))) {
    wsConectado = false;
    enlaceListo43 = false;
    detenerTodo();
    webSocket.disconnect();
    Serial.println("[WSS 4.3] Reintentando con una conexión nueva.");
    iniciarWebSocket();
  }
  webSocket.loop();
}

void anunciarDispositivo() {
  detenerTodo();
  JsonDocument listo;
  listo["tipo"] = "listo";
  listo["id_vehiculo"] = IOT43_UNIDAD;
  listo["salidas_apagadas"] = true;
  listo["mando_continuo"] = true;
  listo["demo_temporizada"] = true;
  listo["confirmar_listo"] = true;
  JsonArray codigos = listo["codigos"].to<JsonArray>();
  for (uint8_t codigo : CODIGOS_CONTROL_43) codigos.add(codigo);
  String trama;
  serializeJson(listo, trama);
  if (!webSocket.sendTXT(trama)) Serial.println("[WSS 4.3] No se pudo anunciar la unidad.");
}

void procesarOrdenIoT43(uint8_t* payload, size_t longitud) {
  if (longitud > 512 || !wsConectado || WiFi.status() != WL_CONNECTED) return;
  JsonDocument orden;
  if (deserializeJson(orden, payload, longitud)) return;
  if (orden["tipo"] == "listo_confirmado") {
    if (!enlaceListo43 && orden["id_vehiculo"] == IOT43_UNIDAD) {
      enlaceListo43 = true;
      Serial.println("[WSS 4.3] Conexión confirmada por FastAPI.");
    }
    return;
  }
  if (!enlaceListo43) return;
  const bool continuo = orden["tipo"] == "mando_continuo";
  const bool demo = orden["tipo"] == "orden_demo";
  if ((!continuo && !demo && orden["tipo"] != "orden") || orden["id_vehiculo"] != IOT43_UNIDAD) return;
  const char* id = orden["id_orden"].as<const char*>();
  if (id == nullptr || strlen(id) != 32) return;
  if (!orden["codigo"].is<int>() || !orden["duracion_ms"].is<unsigned long>()) return;
  const int codigo = orden["codigo"];
  const unsigned long duracion = orden["duracion_ms"];
  bool aplicado = true;
  bool detuvoMando = false;
  if (continuo) {
    AccionCarrito accion;
    if (duracion != 0 || !buscarAccion(codigo, accion) || accion.esPulso) return;
    movimientoPorTiempo = false;
    estadoActual = accion.mascara;
    actualizarShiftRegisters(estadoActual);
    codigoContinuo43 = codigo;
  } else if (demo) {
    AccionCarrito accion;
    if (duracion < MINIMO_PASO_DEMO_43_MS || duracion > MAXIMO_PASO_DEMO_43_MS || codigo == 14
        || !buscarAccion(codigo, accion)) return;
    codigoContinuo43 = 0;
    const unsigned long tiempoSalida = accion.esPulso ? min(duracion, MAXIMO_PULSO_43_MS) : duracion;
    moverPorTiempo(accion.mascara, tiempoSalida);
  } else if (codigo == COD_DETENER && duracion == 0) {
    detuvoMando = codigoContinuo43 != 0 || movimientoPorTiempo;
    detenerTodo();
  } else if (duracion == MAXIMO_PULSO_43_MS) {
    bool permitido = false;
    for (uint8_t admitido : CODIGOS_CONTROL_43) {
      if (codigo == admitido) permitido = true;
    }
    AccionCarrito accion;
    if (!permitido || !buscarAccion(codigo, accion)) return;
    // Completa el pulso y apaga la salida antes de escribir de vuelta en la red.
    const unsigned long inicio = millis();
    moverPorTiempo(accion.mascara, duracion);
    while (millis() - inicio < duracion) {
      if (WiFi.status() != WL_CONNECTED || (Serial.available() && Serial.read() == 'x')) {
        aplicado = false;
        break;
      }
      delay(1);
    }
    detenerTodo();
  } else {
    return;
  }
  JsonDocument confirmacion;
  confirmacion["tipo"] = "confirmacion";
  confirmacion["id_orden"] = id;
  confirmacion["codigo"] = codigo;
  confirmacion["aplicado"] = aplicado;
  String trama;
  serializeJson(confirmacion, trama);
  webSocket.sendTXT(trama);
  if (continuo) Serial.printf("[MANDO] Dirección activa: código %d.\n", codigo);
  if (demo) Serial.printf("[DEMO] Paso aplicado: código %d, %lu ms.\n", codigo, duracion);
  if (detuvoMando) Serial.println("[MANDO] DETENER recibido.");
}

void eventoWebSocket(WStype_t tipo, uint8_t* payload, size_t longitud) {
  switch (tipo) {
    case WStype_DISCONNECTED:
      if (enlaceListo43) ultimoInicioWss43 = millis();
      enlaceListo43 = false;
      if (payload != nullptr && longitud > 0) {
        Serial.printf("[WSS 4.3] Motivo: %.*s\n", static_cast<int>(min(longitud, size_t(96))),
                      reinterpret_cast<const char*>(payload));
      }
      if (wsConectado) {
        // Se cayó una conexión que estaba activa: por seguridad se detiene el carrito
        wsConectado = false;
        detenerTodo();
        Serial.println("[WSS] Desconectado del servidor. Carrito detenido por seguridad.");
      } else {
        Serial.println("[WSS] Desconectado del servidor.");
      }
      break;

    case WStype_CONNECTED:
      wsConectado = true;
      wsConectadoDesde = millis();
      Serial.print("[WSS] Conectado a: ");
      Serial.println((char*)payload);
      anunciarDispositivo();
      break;

    case WStype_TEXT:
      procesarOrdenIoT43(payload, longitud);
      break;

    case WStype_ERROR:
      if (enlaceListo43) ultimoInicioWss43 = millis();
      enlaceListo43 = false;
      wsConectado = false;
      detenerTodo();
      Serial.println("[WSS] Error de conexion.");
      break;

    default:
      break;
  }
}

// ================= ÓRDENES DEL SERVIDOR -> SALIDAS DEL CARRITO =================
// Cada comando de la base de datos tiene un "codigo" numérico. Aquí se traduce
// a la salida del 74HC595 que corresponde. Se mapea por CÓDIGO (no por nombre ni id).
// (La estructura AccionCarrito está definida arriba, junto a las variables.)
bool buscarAccion(int codigo, AccionCarrito &accion) {
  switch (codigo) {
    case 1:  accion = {AVANZAR,     false, "Avanzar"};            return true;
    case 2:  accion = {RETROCEDER,  false, "Retroceder"};         return true;
    case 3:  accion = {GIRAR_DER,   false, "Girar derecha"};      return true;
    case 4:  accion = {GIRAR_IZQ,   false, "Girar izquierda"};    return true;
    case 5:  accion = {GRUA_SUBIR,  false, "Alzar pala"};         return true;
    case 6:  accion = {GRUA_BAJAR,  false, "Bajar pala"};         return true;
    // 7 y 8 (abrir/cerrar pala) no existen en el carrito físico
    case 10: accion = {DIAG_IZQ,    false, "Diagonal izquierda"}; return true;
    case 11: accion = {DIAG_DER,    false, "Diagonal derecha"};   return true;
    case 12: accion = {VELOCIDAD,   true,  "Velocidad"};          return true;
    case 13: accion = {SONIDO,      true,  "Sonido"};             return true;
    case 14: accion = {DEMO,        true,  "Demo del carrito"};   return true;
    case 15: accion = {LUZ,         true,  "Luz"};                return true;
    default: return false;
  }
}

// Envía a los 595 el movimiento actual más el pulso en curso
void refrescarSalidas() {
  actualizarShiftRegisters(estadoActual);
}

void detenerTodo() {
  codigoContinuo43 = 0;
  estadoActual = 0;
  movimientoPorTiempo = false;
  refrescarSalidas();
}

// Mueve y se detiene solo cuando pasa el tiempo (sin delay)
void moverPorTiempo(uint16_t mascara, unsigned long duracionMs) {
  estadoActual = mascara;
  movimientoPorTiempo = true;
  movimientoHasta = millis() + duracionMs;
  refrescarSalidas();
}

// Se llama en cada vuelta del loop
void actualizarTemporizadores() {
  unsigned long ahora = millis();

  if (movimientoPorTiempo && (long)(ahora - movimientoHasta) >= 0) {
    movimientoPorTiempo = false;
    estadoActual = 0;
    refrescarSalidas();
    Serial.println("[CARRITO] Movimiento terminado: detenido.");
  }

}

String obtenerNombreDispositivo() {
  String mac = WiFi.macAddress();   // Formato A1:B2:C3:D4:E5:F6
  mac.replace(":", "");
  mac.toUpperCase();
  return "EXCAVADORA-" + mac.substring(mac.length() - 6);
}

void configurarWiFiManager() {
  wm.setDebugOutput(false);                       // Evita que la biblioteca imprima datos sensibles
  wm.setConnectTimeout(TIEMPO_CONEXION_S);
  wm.setConfigPortalTimeout(TIEMPO_PORTAL_S);
  wm.setAPClientCheck(true);                      // No cerrar el portal mientras un teléfono esté conectado
  wm.setAPCallback(alEntrarModoConfiguracion);
  wm.setSaveConfigCallback(alGuardarCredenciales);

}

void alEntrarModoConfiguracion(WiFiManager*) {
  Serial.println();
  Serial.println(">>> MODO CONFIGURACION <<<");
  Serial.print("Conecta tu telefono a la red: ");
  Serial.println(nombreDispositivo);
  Serial.print("Contrasena de la red: ");
  Serial.println(clavePortal);
  Serial.print("Abre en el navegador: http://");
  Serial.println(WiFi.softAPIP());
  Serial.println("En 'Configure WiFi' elige la red del dispositivo y escribe su contrasena.");
  Serial.println("(Mientras el portal esta abierto, el carrito y el boton de reset no responden)");
}

void alGuardarCredenciales() {
  Serial.println("Credenciales guardadas en la memoria del dispositivo.");
}

void conectarWiFi() {
  Serial.println();
  Serial.println("Intentando conectar a la red Wi-Fi guardada...");

  // Si hay credenciales, intenta conectar. Si no hay o fallan, abre el portal.
  bool conectado = wm.autoConnect(nombreDispositivo.c_str(), clavePortal);

  if (conectado) {
    estabaConectado = true;
    Serial.println("Conexion Wi-Fi establecida.");
    imprimirInfoWiFi();
  } else {
    Serial.println("No se logro conectar. Reiniciando para intentar de nuevo...");
    delay(3000);
    ESP.restart();
  }
}

void imprimirInfoWiFi() {
  Serial.println("-----------------------------------------");
  Serial.print("Dispositivo : "); Serial.println(nombreDispositivo);
  Serial.print("MAC         : "); Serial.println(WiFi.macAddress());
  Serial.print("Estado      : ");
  Serial.println(WiFi.status() == WL_CONNECTED ? "Conectado" : "Sin conexion");
  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("SSID        : "); Serial.println(WiFi.SSID());
    Serial.print("IP          : "); Serial.println(WiFi.localIP());
    Serial.print("Mascara     : "); Serial.println(WiFi.subnetMask());
    Serial.print("Puerta enl. : "); Serial.println(WiFi.gatewayIP());
    Serial.print("RSSI        : "); Serial.print(WiFi.RSSI()); Serial.println(" dBm");
  }
  Serial.print("Servidor       : "); Serial.print(IOT43_HOST); Serial.print(':'); Serial.println(IOT43_PUERTO);
  Serial.print("Vehiculo ID    : "); Serial.println(IOT43_UNIDAD);
  Serial.println("-----------------------------------------");
}

void mostrarEstadoPeriodico() {
  if (millis() - ultimoEstado < INTERVALO_ESTADO) return;
  ultimoEstado = millis();

  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("[Wi-Fi] Conectado a ");
    Serial.print(WiFi.SSID());
    Serial.print(" | IP ");
    Serial.print(WiFi.localIP());
    Serial.print(" | ");
    Serial.print(WiFi.RSSI());
    Serial.println(" dBm");
  } else {
    Serial.println("[Wi-Fi] Sin conexion");
  }
}

// Reconexión sin bloquear
void verificarConexion() {
  unsigned long ahora = millis();

  if (WiFi.status() == WL_CONNECTED) {
    if (!estabaConectado) {
      estabaConectado = true;
      Serial.println("Conexion Wi-Fi recuperada.");
      imprimirInfoWiFi();
    }
    return;
  }

  if (estabaConectado) {
    estabaConectado = false;
    ultimoReintento = ahora;
    Serial.println("Se perdio la conexion Wi-Fi. Reintentando automaticamente...");
  }

  if (ahora - ultimoReintento >= INTERVALO_REINTENTO) {
    ultimoReintento = ahora;
    Serial.println("Reintentando conexion con la red guardada...");
    WiFi.reconnect();   // Usa las credenciales almacenadas, no bloquea
  }
}

// Borra la red guardada y reinicia desde el botón D6
void borrarCredencialesYReiniciar() {
  Serial.println();
  Serial.println("Borrando credenciales Wi-Fi guardadas...");
  estadoActual = 0;
  actualizarShiftRegisters(0);   // El carrito queda detenido antes de reiniciar
  WiFiManager wifiManager;
  wifiManager.resetSettings();
  Serial.println("Reiniciando para abrir el portal de configuracion...");
  ESP.restart();
}

// Mantener D6 a GND por 5 segundos continuos (usa millis, sin delay)
void verificarBotonReset() {
  bool presionado = (digitalRead(PIN_RESET) == LOW);

  if (presionado) {
    if (!botonPresionado) {
      botonPresionado = true;
      inicioPulsacion = millis();
      Serial.println("Boton de reset detectado. Manten 5 segundos para borrar la red...");
    } else if (millis() - inicioPulsacion >= TIEMPO_PULSACION_RESET) {
      Serial.println("Pulsacion de 5 s completada.");
      borrarCredencialesYReiniciar();
    }
  } else {
    if (botonPresionado) {
      Serial.println("Boton liberado antes de tiempo. No se borro nada.");
    }
    botonPresionado = false;
  }
}
