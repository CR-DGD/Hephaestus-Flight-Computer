#include <Wire.h>
#include <Adafruit_BMP280.h>
#include "MPU6050_6Axis_MotionApps20.h"

#define CHIP_ID_REG 0xD0
#define G 9.80665

// !!! SAFETY: NEVER leave this defined for a real flight. When defined, the
// vertical-axis accel and barometric pressure are replaced with a scripted
// fake flight profile (see simVerticalG/simAltitude_m below) -- the board
// will not react to real motion at all. Comment out before flashing for an
// actual launch. Bench/dev testing of BURNOUT/APOGEE/CHUTE/LANDED detection
// only -- a real flight cannot be safely faked on the bench (see chat).
//#define SIMULATE_FLIGHT

/*
* Hephaestus flight computer code
* 1.1
* Flight count - 0
* Galalumga board
* Altitude, Temperature, Pressure from BMP280 breakout board
* Averaged gyro and acceleration from dual GY-251 MPU6050 breakout boards
* Airspeed (vertical velocity) estimate: accelerometer integration fused with
*   barometric altitude derivative via complementary filter
* Flight event detection: liftoff, burnout, apogee, chute deploy (inferred),
*   landing -- logged as ">>> EVENT: ..." lines interleaved in the data stream
* Written by CR_DGD
*/

//Pins
const int buzzer = 8;
const int ledrxtx = 6;
const int ledon = 9;
const int goled = 9;

// Let the board's own electronics finish their initial thermal/electrical
// ramp-up before we init sensors or latch any reference values (P_launch)
// off of them -- capturing those too early biases everything downstream.
const unsigned long PREFLIGHT_SETTLE_MS = 3000;

//Log time value
int logstep = 0;
unsigned long prevTime = 0;
float dt;

//output values
float pitch;
float roll;
float yaw;
float pitchAcc;
float rollAcc;
float yawAcc;
float P_launch = 0;
float velocity = 0;       // fused vertical speed estimate, m/s
float prevAltitude_m = 0; // previous BMP altitude, meters (for baro velocity)

//vec3 struct
struct Vector3 {
  float x;
  float y;
  float z;
};

//------------------------------------------- FLIGHT EVENT DETECTION --------------------------------------------

// Thresholds - tune per rocket/motor
const float LIFTOFF_G        = 2.0;  // g's on vertical axis to call liftoff
const float BURNOUT_G        = 0.5;  // g's on vertical axis to call burnout (near freefall)
const float CHUTE_DECEL      = 4.0;  // m/s^2 deceleration spike (while descending) to infer chute deploy
const float LANDED_SPEED     = 1.0;  // m/s, |velocity| below this counts as "stopped"
const float LANDED_ALT_M     = 3.0;  // meters from pad altitude counts as "on the ground"
const int DEBOUNCE_SAMPLES   = 3;    // consecutive samples required before liftoff/burnout latches
const unsigned long LANDED_HOLD_MS = 1000; // must stay stopped this long to call it landed

enum FlightState { PAD, BOOST, COAST, LANDED_STATE };
FlightState flightState = PAD;
int debounceCount = 0;
bool apogeeLogged = false;
bool chuteLogged = false;
float prevVelocityForChute = 0;
unsigned long landedSince = 0;

//------------------------------------------- SENSOR DECLARE ------------------------------------------------------

/*
* MPU1 at 0x68
* MPU2 at 0x69, ADO High
* BMP280 at 0x76
*/

//MPU1
MPU6050 mpu1(0x68, &Wire2);
//Found device at 0x68

//MPU2
MPU6050 mpu2(0x69, &Wire2);
//Found device at 0x69

//BMP
Adafruit_BMP280 bmp(&Wire2);
//Found device at 0x76


void setup() 
{
//------------------------------------------- SERIAL AND PIN INIT ----------------------------------------------
 //SERIAL & I2C
  Serial.begin(9600);

#ifdef SIMULATE_FLIGHT
  for (int i = 0; i < 5; i++) {
    Serial.println("!!! SIMULATION MODE -- FAKE SENSOR DATA -- DO NOT FLY !!!");
  }
#endif

  Wire2.begin();
  Wire2.setClock(100000);

//PINOUT
  pinMode(buzzer, OUTPUT);
  pinMode(ledrxtx, OUTPUT);
  pinMode(ledon, OUTPUT);
  pinMode(goled, OUTPUT);
  Serial.println("Initializing Pins");

//------------------------------------------- PREFLIGHT SETTLE ----------------------------------------------

  Serial.println("Settling sensors...");
  delay(PREFLIGHT_SETTLE_MS);

//------------------------------------------- SENSOR INIT ---------------------------------------------------

//------------------------------------------- INITALIZE BMP -------------------------------------------------

  unsigned status;
  Serial.println("Initializing BMP");
  status = bmp.begin(0x76);

  if (!status) 
  {
    Serial.println(F("Could not find a valid BMP280 sensor, check wiring or try a different address!"));
    Serial.print("SensorID was: 0x"); Serial.println(bmp.sensorID(),16);
  }
  Serial.print("BMP ID was: 0x"); Serial.println(bmp.sensorID(),16);
  bmp.setSampling(Adafruit_BMP280::MODE_NORMAL,     /* Operating Mode. */
                  Adafruit_BMP280::SAMPLING_X2,     /* Temp. oversampling */
                  Adafruit_BMP280::SAMPLING_X16,    /* Pressure oversampling */
                  Adafruit_BMP280::FILTER_X16,      /* Filtering. */
                  Adafruit_BMP280::STANDBY_MS_500); /* Standby time. */

  P_launch = bmp.readPressure() / 100.0F; // convert Pa to hPa
  Serial.print("Launch pressure: "); Serial.println(P_launch);                

  digitalWrite(goled,HIGH);
  delay(60);
  digitalWrite(goled,LOW);
  delay(60);
  digitalWrite(goled,HIGH);
  delay(60);
  digitalWrite(goled,LOW);
  delay(60);                

//------------------------------------------- INITALIZE MPU1 -------------------------------------------------

  Serial.println("Initializing MPU1");
  mpu1.initialize();
  mpu1.setFullScaleGyroRange(MPU6050_GYRO_FS_1000);
  mpu1.setFullScaleAccelRange(3); // +/-16g (AFS_SEL=3); must match the /2048.0 sensitivity used to convert raw counts to g's below
  mpu1.setDLPFMode(1);
  delay(100);

  mpu1.CalibrateAccel(10);  // Calibration Time: generate offsets and calibrate our MPU6050
  mpu1.CalibrateGyro(10);
  Serial.println("These are the Active offsets: ");
  mpu1.PrintActiveOffsets();//Get expected DMP packet size for later comparison

  digitalWrite(goled,HIGH);
  delay(60);
  digitalWrite(goled,LOW);
  delay(60);
  digitalWrite(goled,HIGH);
  delay(60);
  digitalWrite(goled,LOW);
  delay(60);

//------------------------------------------- INITALIZE MPU2 -------------------------------------------------

  Serial.println("Initializing MPU2");
  mpu2.initialize();
  mpu2.setFullScaleGyroRange(MPU6050_GYRO_FS_1000);
  mpu2.setFullScaleAccelRange(3); // +/-16g (AFS_SEL=3); must match the /2048.0 sensitivity used to convert raw counts to g's below
  mpu2.setDLPFMode(1);
  delay(100);

  mpu2.CalibrateAccel(10);  // Calibration Time: generate offsets and calibrate our MPU6050
  mpu2.CalibrateGyro(10);
  Serial.println("These are the Active offsets: \n");
  mpu2.PrintActiveOffsets();

  digitalWrite(goled,HIGH);
  delay(60);
  digitalWrite(goled,LOW);
  delay(60);
  digitalWrite(goled,HIGH);
  delay(60);
  digitalWrite(goled,LOW);
  delay(60);

  Wire2.beginTransmission(0x76);
  Wire2.write(CHIP_ID_REG);
  Wire2.endTransmission();

//------------------------------------------- BMP TEST -------------------------------------------------
  Wire2.requestFrom(0x76, 1);
  if (Wire2.available()) {
    byte id = Wire2.read();
    Serial.print("Chip ID: 0x");
    Serial.println(id, HEX);

    if (id == 0x58) {
      Serial.println("BMP280 Online");
    } else {
      Serial.println("Unexpected chip.");
    }
  } else {
    Serial.println("No response from BMP280.");
  }

//------------------------------------------- MPU TEST -------------------------------------------------
//MPU1
  if (!mpu1.testConnection()) 
  {
    Serial.println("MPU1 Connection Failed");
  }
  else
  {
    Serial.println("MPU1 Online");
  }
//MPU2
  if (!mpu2.testConnection()) 
  {
    Serial.println("MPU2 Connection Failed");
  }
  else
  {
    Serial.println("MPU2 Online");
  }

  
  digitalWrite(goled,HIGH);
  delay(600);
  digitalWrite(goled,LOW);
  delay(1200);
  digitalWrite(goled,HIGH);
  Serial.println("System check complete. Logging started.");
  // Log format (pipe-delimited): TIME(logstep) | TEMP(F) | ALT(ft) | BARO(hPa) |
  // PITCH/ROLL/YAW(deg) | ACCX/Y/Z(g, unit vector, tilt-relative not physical) |
  // GX/GY/GZ(g, true magnitude, vertical-axis-remapped raw accel) |
  // GYRX/Y/Z(deg/s) | AIRSPD(ft/s, vertical velocity estimate)
  // Event lines are emitted out-of-band as ">>> EVENT: <name> at t=<logstep>" and
  // do not match this column format -- a parser should special-case the ">>>" prefix.
  Serial.println("  TIME  | TEMP |  ALT | BARO | PITCH | ROLL  | YAW  |  ACCX  |  ACCY  |  ACCZ  |  GX  |  GY  |  GZ  |  GYRX  |  GYRY  |  GYRZ | AIRSPD");

}

#ifdef SIMULATE_FLIGHT
//------------------------------------------- BENCH SIMULATION PROFILE --------------------------------------
// Scripted fake flight, indexed by logstep (~20 samples/sec). Phases are
// deliberately long/generous rather than physically exact -- this only
// needs to reliably walk the real event state machine through every
// transition on the bench, not model true flight dynamics.

const float SIM_TEMP_C = 20.0; // constant, event logic never reads temp

float simVerticalG(int step) {
  if (step < 21)  return 1.00;                                    // PAD
  if (step < 41)  return 1.00 + (step - 20) * (5.00 - 1.00) / 20.0; // BOOST ramp 1g->5g
  if (step < 131) return 0.10;                                    // COAST/freefall
  if (step < 141) return 3.50;                                    // CHUTE jerk
  if (step < 161) return 0.95;                                    // canopy descent
  return 1.00;                                                    // LANDED tail
}

float simAltitude_m(int step) {
  if (step < 21)  return 0.0;
  if (step < 41)  return (step - 20) * 80.0 / 20.0;                        // 0 -> 80m
  if (step < 101) return 80.0 + (step - 40) * (300.0 - 80.0) / 60.0;       // 80 -> 300m (apogee ~100)
  if (step < 131) return 300.0 + (step - 100) * (260.0 - 300.0) / 30.0;    // 300 -> 260m
  if (step < 141) return 255.0;                                           // plateau during chute jerk
  if (step < 161) return 255.0 + (step - 140) * (150.0 - 255.0) / 20.0;    // 255 -> 150m
  if (step < 301) return 150.0 + (step - 160) * (0.0 - 150.0) / 140.0;     // 150 -> 0m
  return 0.0;                                                             // LANDED tail, flat
}
#endif

Vector3 remap(Vector3 raw)
{
    Vector3 mapped;

    // Pick axis with largest magnitude as vertical
    float absX = abs(raw.x), absY = abs(raw.y), absZ = abs(raw.z);

    if (absX > absY && absX > absZ) 
    {// X is vertical
        mapped.x = raw.x; mapped.y = raw.y; mapped.z = raw.z;
    } 
    else if (absY > absZ) 
    {// Y is vertical
        mapped.x = raw.y; mapped.y = raw.x; mapped.z = raw.z;
        if (raw.y < 0) mapped.x *= -1;
    } 
    else
    {// Z is vertical
        mapped.x = raw.z; mapped.y = raw.x; mapped.z = raw.y;
        if (raw.z < 0) mapped.x *= -1;
    }
    return mapped;
}

void loop()
{
  logstep++;

  if (prevTime == 0) 
  {
  prevTime = micros();
  return;
  }

  unsigned long currentTime = micros();
  dt = (currentTime - prevTime) / 1000000.0;
  prevTime = currentTime;

//------------------------------------------- MPU LOG -------------------------------------------------

  int16_t ax1, ay1, az1, gx1, gy1, gz1; //MPU1
  int16_t ax2, ay2, az2, gx2, gy2, gz2; //MPU2

#ifdef SIMULATE_FLIGHT
  // Z is this board's confirmed vertical mounting axis (matches real logs).
  int16_t simRawG = (int16_t)(simVerticalG(logstep) * 2048.0);
  ax1 = 0; ay1 = 0; az1 = simRawG; gx1 = 0; gy1 = 0; gz1 = 0;
  ax2 = 0; ay2 = 0; az2 = simRawG; gx2 = 0; gy2 = 0; gz2 = 0;
#else
  mpu1.getMotion6(&ax1, &ay1, &az1, &gx1, &gy1, &gz1);
  delayMicroseconds(500);
  mpu2.getMotion6(&ax2, &ay2, &az2, &gx2, &gy2, &gz2);
#endif

  Vector3 a1 = { ax1/2048.0, ay1/2048.0, az1/2048.0 };
  Vector3 a2 = { ax2/2048.0, ay2/2048.0, az2/2048.0 };
  Vector3 g1 = { gx1/32.8, gy1/32.8, gz1/32.8 };
  Vector3 g2 = { gx2/32.8, gy2/32.8, gz2/32.8 };


  Vector3 accelRaw = { (a1.x+a2.x)/2, (a1.y+a2.y)/2, (a1.z+a2.z)/2 }; // g's, magnitude intact
  Vector3 accel = accelRaw;

  float mag = sqrt(accel.x*accel.x + accel.y*accel.y + accel.z*accel.z);
  accel.x /= mag; accel.y /= mag; accel.z /= mag;

  Vector3 gyro =  { (g1.x+g2.x)/2, (g1.y+g2.y)/2, (g1.z+g2.z)/2 };

  accel = remap(accel);

  // ponytail: remap() picks "vertical" by largest-magnitude axis with no
  // guaranteed up/down sign convention -- fine for an approximately-straight-up
  // flight, not a rigorous world-frame vertical velocity. Upgrade path: fuse
  // with a real orientation estimate (DMP quaternion) if off-vertical flights matter.
  Vector3 accelRawMapped = remap(accelRaw);
  float accelVelocity = (accelRawMapped.x - 1.0) * G * dt; // subtract static 1g, g's -> m/s^2 -> m/s delta

//------------------------------------------- BMP LOG -------------------------------------------------

#ifdef SIMULATE_FLIGHT
  float P_now = P_launch * exp(-simAltitude_m(logstep) / 8434.0); // hPa, inverts the altitude formula below
  float temp = SIM_TEMP_C;
#else
  float P_now = bmp.readPressure() / 100.0F;// current pressure in hPa
  float temp = bmp.readTemperature();// temperature in °C
#endif
  float altitude_m = 8434.0 * log(P_launch / P_now); // meters

  // dt is 0.0 on the very first sample (no delay() has run yet at that point),
  // and X/0.0 is +/-Inf in float math -- guard it, since one Inf sample here
  // permanently poisons the complementary filter below (0.98*Inf is still Inf).
  float baroVelocity = (dt > 0.0) ? (altitude_m - prevAltitude_m) / dt : 0.0; // m/s
  prevAltitude_m = altitude_m;

  temp = temp * 9.0 / 5.0 + 32.0;
  float altitude = altitude_m * 3.28084;

//------------------------------------------- AIRSPEED (complementary filter) -----------------------------------

  velocity = 0.98 * (velocity + accelVelocity) + 0.02 * baroVelocity; // m/s
  // Hold at zero while stationary on the pad: accelRawMapped.x is never
  // exactly 1.000g at rest (real accelerometer calibration always has some
  // residual offset), and that constant tiny bias integrates into apparent
  // drift the longer we sit here. Zeroing it out until liftoff bounds the
  // bias's accumulation window to the actual flight duration instead of
  // however long the rocket waits on the pad.
  if (flightState == PAD) velocity = 0;
  float airspeed = velocity * 3.28084; // ft/s, matches ft-based altitude units

//------------------------------------------- FLIGHT EVENT DETECTION -------------------------------------------------

  float g_vertical = accelRawMapped.x; // g's, raw (includes 1g static gravity while at rest)

  switch (flightState)
  {
    case PAD:
      if (g_vertical > LIFTOFF_G)
      {
        if (++debounceCount >= DEBOUNCE_SAMPLES)
        {
          flightState = BOOST;
          debounceCount = 0;
          Serial.print(">>> EVENT: LIFTOFF at t="); Serial.println(logstep);
        }
      }
      else debounceCount = 0;
      break;

    case BOOST:
      if (g_vertical < BURNOUT_G)
      {
        if (++debounceCount >= DEBOUNCE_SAMPLES)
        {
          flightState = COAST;
          debounceCount = 0;
          Serial.print(">>> EVENT: BURNOUT at t="); Serial.println(logstep);
        }
      }
      else debounceCount = 0;
      break;

    case COAST:
      // Apogee: velocity crosses from climbing to descending (one-shot).
      // ponytail: no debounce here (fused velocity is already filtered) --
      // add one if noise ever triggers this early on real flight data.
      if (!apogeeLogged && velocity < 0)
      {
        apogeeLogged = true;
        Serial.print(">>> EVENT: APOGEE at t="); Serial.println(logstep);
      }

      // Chute deploy (inferred): sharp deceleration spike while descending, one-shot.
      if (apogeeLogged && !chuteLogged)
      {
        float decel = (velocity - prevVelocityForChute) / dt; // m/s^2, positive = slowing the fall
        if (decel > CHUTE_DECEL)
        {
          chuteLogged = true;
          Serial.print(">>> EVENT: CHUTE DEPLOY (inferred) at t="); Serial.println(logstep);
        }
      }

      // Landing: stopped near pad altitude, held for LANDED_HOLD_MS.
      if (abs(velocity) < LANDED_SPEED && abs(altitude_m) < LANDED_ALT_M)
      {
        if (landedSince == 0) landedSince = millis();
        else if (millis() - landedSince >= LANDED_HOLD_MS)
        {
          flightState = LANDED_STATE;
          Serial.print(">>> EVENT: LANDED at t="); Serial.println(logstep);
        }
      }
      else landedSince = 0;
      break;

    case LANDED_STATE:
      break; // nothing further to detect
  }

  prevVelocityForChute = velocity;

//------------------------------------------- FORMAT LOG -------------------------------------------------

  formatpacket(logstep,temp,altitude,P_now,accel,gyro,airspeed,accelRawMapped);
  delay(50);


  if (logstep>20)
  {
    digitalWrite(ledrxtx,HIGH);
  }

  if (logstep>150)
  {
    if (logstep%50 == 0)
    {
      tone(buzzer,500,500);
    }
  }

}

void formatpacket(int16_t time, float temp, float alt, float baro, Vector3 accel, Vector3 gyro, float airspeed, Vector3 gRaw)
{

//------------------------------------------- COMPLEMENT FILTER ------------------------------------------------- 
  float pitchAcc = atan2(accel.y, accel.z)* RAD_TO_DEG;
  float rollAcc  = atan2(-accel.x, accel.z) * RAD_TO_DEG;

  pitch = 0.998 * (pitch + gyro.x * dt) + 0.002 * pitchAcc;
  roll  = 0.998 * (roll  + gyro.y * dt) + 0.002 * rollAcc;
  yaw   = yaw + gyro.z * dt; 


//------------------------------------------- BUFFER LOGGING (TIME TEMP ALT BARO) -------------------------------------------------
  Serial.print(time);
  Serial.print(" | ");
  Serial.print(temp, 1);
  Serial.print(" | ");
  Serial.print(alt, 1);
  Serial.print(" | ");
  Serial.print(baro, 1);
  Serial.print(" | ");
//------------------------------------------- PITCH ROLL LOG -------------------------------------------------
  Serial.print(pitch , 3);
  Serial.print(" | ");
  Serial.print(roll , 3);
  Serial.print(" | ");
  Serial.print(yaw , 3);
  Serial.print(" | ");
//------------------------------------------- ACCEL X Y Z LOG -------------------------------------------------
  Serial.print(accel.x , 4);
  Serial.print(" | ");
  Serial.print(accel.y , 4);
  Serial.print(" | ");
  Serial.print(accel.z , 4);
  Serial.print(" | ");
//------------------------------------------- RAW G LOAD X Y Z LOG -------------------------------------------------
  Serial.print(gRaw.x , 4);
  Serial.print(" | ");
  Serial.print(gRaw.y , 4);
  Serial.print(" | ");
  Serial.print(gRaw.z , 4);
  Serial.print(" | ");
//------------------------------------------- GYRO X Y Z LOG -------------------------------------------------
  Serial.print(gyro.x , 4);
  Serial.print(" | ");
  Serial.print(gyro.y , 4);
  Serial.print(" | ");
  Serial.print(gyro.z , 4);
  Serial.print(" | ");
//------------------------------------------- AIRSPEED LOG -------------------------------------------------
  Serial.println(airspeed , 2);
}

