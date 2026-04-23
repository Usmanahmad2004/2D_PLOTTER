#include <Servo.h>

// ----------------------------
// PIN CONFIG
// ----------------------------
const int X_STEP_PIN = 2;
const int X_DIR_PIN  = 3;
const int X_EN_PIN   = 9;

const int Y_STEP_PIN = 5;
const int Y_DIR_PIN  = 6;
const int Y_EN_PIN   = 10;

const int PEN_SERVO_PIN = 7;
//const int ON_PIN = 2;   // interrupt-capable on Uno/Nano

// ----------------------------
// MACHINE STATE
// ----------------------------
Servo penServo;

volatile bool abortFlag = false;

float drawWidthMM = 100.0;
float drawHeightMM = 100.0;
float stepsPerMMX = 80.0;
float stepsPerMMY = 80.0;

int penUpAngle = 90;
int penDownAngle = 35;
unsigned int feedDelayUS = 700;   // smaller = faster

long currentXSteps = 0;
long currentYSteps = 0;
bool penIsDown = false;

// ----------------------------
// UTILS
// ----------------------------
void abortISR() {
  abortFlag = true;
}

void enableMotors() {
  digitalWrite(X_EN_PIN, LOW);
  digitalWrite(Y_EN_PIN, LOW);
}

void disableMotors() {
  digitalWrite(X_EN_PIN, HIGH);
  digitalWrite(Y_EN_PIN, HIGH);
}

void penUp() {
  penServo.write(penUpAngle);
  delay(250);
  penIsDown = false;
}

void penDown() {
  penServo.write(penDownAngle);
  delay(250);
  penIsDown = true;
}

void pulsePin(int pin) {
  digitalWrite(pin, HIGH);
  delayMicroseconds(3);
  digitalWrite(pin, LOW);
}

long mmToXSteps(float mm) {
  return lround(mm * stepsPerMMX);
}

long mmToYSteps(float mm) {
  return lround(mm * stepsPerMMY);
}

void printOK() {
  Serial.println("OK");
}

void printErr(const char* msg) {
  Serial.print("ERR ");
  Serial.println(msg);
}

bool checkAbort() {
  if (abortFlag) {
    penUp();
    Serial.println("ABORTED");
    abortFlag = false;
    return true;
  }
  return false;
}

// ----------------------------
// COORDINATED MOTION
// ----------------------------
// simple Bresenham-style line stepping
bool moveToSteps(long targetX, long targetY) {
  enableMotors();

  long dx = labs(targetX - currentXSteps);
  long dy = labs(targetY - currentYSteps);

  int sx = (targetX >= currentXSteps) ? 1 : -1;
  int sy = (targetY >= currentYSteps) ? 1 : -1;

  digitalWrite(X_DIR_PIN, (sx > 0) ? HIGH : LOW);
  digitalWrite(Y_DIR_PIN, (sy > 0) ? HIGH : LOW);

  long err = dx - dy;
  long x = currentXSteps;
  long y = currentYSteps;

  while (true) {
    if (checkAbort()) return false;
    if (x == targetX && y == targetY) break;

    long e2 = 2 * err;
    bool stepX = false;
    bool stepY = false;

    if (e2 > -dy) {
      err -= dy;
      x += sx;
      stepX = true;
    }

    if (e2 < dx) {
      err += dx;
      y += sy;
      stepY = true;
    }

    if (stepX) pulsePin(X_STEP_PIN);
    if (stepY) pulsePin(Y_STEP_PIN);

    delayMicroseconds(feedDelayUS);
  }

  currentXSteps = targetX;
  currentYSteps = targetY;
  return true;
}

bool moveToMM(float xMM, float yMM) {
  long tx = mmToXSteps(xMM);
  long ty = mmToYSteps(yMM);
  return moveToSteps(tx, ty);
}

// ----------------------------
// SANITY CHECK
// ----------------------------
bool runSanitySquare() {
  penUp();
  if (!moveToMM(0, 0)) return false;

  penDown();
  if (!moveToMM(drawWidthMM, 0)) return false;
  if (!moveToMM(drawWidthMM, drawHeightMM)) return false;
  if (!moveToMM(0, drawHeightMM)) return false;
  if (!moveToMM(0, 0)) return false;

  penUp();
  return true;
}

// ----------------------------
// COMMAND PARSING
// ----------------------------
String readLine() {
  static String line = "";
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      String out = line;
      line = "";
      return out;
    }
    line += c;
  }
  return "";
}

bool startsWithToken(String s, const char* tok) {
  return s.startsWith(tok);
}

void handleCommand(String cmd) {
  cmd.trim();
  if (cmd.length() == 0) return;

  if (cmd == "HELLO") {
    Serial.println("READY");
    return;
  }

  if (cmd == "FREE_MOTORS") {
    penUp();
    disableMotors();
    printOK();
    return;
  }

  if (cmd == "SET_ORIGIN") {
    enableMotors();
    currentXSteps = 0;
    currentYSteps = 0;
    penUp();
    printOK();
    return;
  }

  if (cmd == "SANITY") {
    bool ok = runSanitySquare();
    if (ok) printOK();
    return;
  }

  if (cmd == "PU") {
    penUp();
    printOK();
    return;
  }

  if (cmd == "PD") {
    penDown();
    printOK();
    return;
  }

  if (startsWithToken(cmd, "CFG ")) {
    float w, h, spmx, spmy;
    int upA, downA;
    unsigned int feed;
    int n = sscanf(cmd.c_str(), "CFG %f %f %f %f %d %d %u",
                   &w, &h, &spmx, &spmy, &upA, &downA, &feed);
    if (n != 7) {
      printErr("bad CFG");
      return;
    }

    drawWidthMM = w;
    drawHeightMM = h;
    stepsPerMMX = spmx;
    stepsPerMMY = spmy;
    penUpAngle = upA;
    penDownAngle = downA;
    feedDelayUS = feed;

    penUp();
    printOK();
    return;
  }

  if (startsWithToken(cmd, "M ")) {
    float x, y;
    int n = sscanf(cmd.c_str(), "M %f %f", &x, &y);
    if (n != 2) {
      printErr("bad M");
      return;
    }
    penUp();
    if (moveToMM(x, y)) printOK();
    return;
  }

  if (startsWithToken(cmd, "D ")) {
    float x, y;
    int n = sscanf(cmd.c_str(), "D %f %f", &x, &y);
    if (n != 2) {
      printErr("bad D");
      return;
    }
    if (!penIsDown) penDown();
    if (moveToMM(x, y)) printOK();
    return;
  }

  printErr("unknown");
}

// ----------------------------
// SETUP / LOOP
// ----------------------------
void setup() {
  pinMode(X_STEP_PIN, OUTPUT);
  pinMode(X_DIR_PIN, OUTPUT);
  pinMode(X_EN_PIN, OUTPUT);

  pinMode(Y_STEP_PIN, OUTPUT);
  pinMode(Y_DIR_PIN, OUTPUT);
  pinMode(Y_EN_PIN, OUTPUT);

  //pinMode(ABORT_BUTTON_PIN, INPUT_PULLUP);

  penServo.attach(PEN_SERVO_PIN);

  disableMotors();
  penUp();

  //attachInterrupt(digitalPinToInterrupt(ABORT_BUTTON_PIN), abortISR, FALLING);

  Serial.begin(115200);
}

void loop() {
  String cmd = readLine();
  if (cmd.length() > 0) {
    handleCommand(cmd);
  }
}