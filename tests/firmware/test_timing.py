"""Run the actual sketch against a fake clock/sensors (Windows + MSVC).

Usage: python tests/firmware/test_timing.py [path/to/Hephaestus_V1.ino]
This checks software timing; it cannot measure real I2C/USB/SD latency.
"""
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest


FAKES = r'''
#pragma once
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <sstream>
#include <string>
#include <vector>
#include <stdexcept>
using std::abs;
using byte = uint8_t;
static_assert(sizeof(unsigned long) == 4, "Match the Teensy's 32-bit clock");
uint64_t clockUs = 100;
unsigned long workUs = 0, flushUs = 0;
bool sdPresent = false;
float verticalG = 1.0f;
std::vector<uint64_t> beeps;
unsigned long micros() { return (unsigned long)clockUs; }
unsigned long millis() { return (unsigned long)(clockUs / 1000); }
void delay(unsigned long ms) { clockUs += ms * 1000ULL; }
void delayMicroseconds(unsigned long us) { clockUs += us; }
void pinMode(int, int) {}
void digitalWrite(int, int) {}
void tone(int, int, int) { beeps.push_back(clockUs); }
#define OUTPUT 1
#define HIGH 1
#define LOW 0
#define HEX 16
#define RAD_TO_DEG 57.29577951308232
#define F(x) x
#define BUILTIN_SDCARD 254
#define FILE_WRITE 1
#define MPU6050_GYRO_FS_1000 2
class Print {
public:
  virtual size_t write(uint8_t) = 0;
  void print(const char* s) { while (*s) write(*s++); }
  template<class T> void print(T value) { std::ostringstream s; s << value; print(s.str().c_str()); }
  template<class T> void print(T value, int) { print(value); }
  template<class T> void println(T value) { print(value); print("\n"); }
  template<class T> void println(T value, int p) { print(value, p); print("\n"); }
};
struct FakeSerial : Print {
  std::string line, text;
  std::vector<uint64_t> samples;
  void begin(int) {}
  size_t write(uint8_t c) override {
    text += (char)c;
    if (c == '\n') {
      if (!line.empty() && (isdigit(line[0]) || line[0] == '-') && line.find(" | ") != std::string::npos) {
        samples.push_back(clockUs);
        clockUs += workUs;
      }
      line.clear();
    } else line += (char)c;
    return 1;
  }
  void clear() { line.clear(); text.clear(); samples.clear(); }
} Serial;
struct File {
  explicit operator bool() const { return sdPresent; }
  size_t write(uint8_t) { return 1; }
  void flush() { clockUs += flushUs; }
};
struct { bool begin(int) { return sdPresent; } bool exists(const char*) { return false; }
  File open(const char*, int) { return File(); } } SD;
struct { void begin() {} void setClock(int) {} void beginTransmission(int) {}
  void write(int) {} void endTransmission() {} void requestFrom(int, int) {}
  bool available() { return true; } byte read() { return 0x58; } } Wire2;
struct MPU6050 {
  template<class T> MPU6050(int, T*) {}
  void initialize() {} void setFullScaleGyroRange(int) {} void setFullScaleAccelRange(int) {}
  void setDLPFMode(int) {} void CalibrateAccel(int) {} void CalibrateGyro(int) {}
  void PrintActiveOffsets() {} bool testConnection() { return true; }
  void getMotion6(int16_t* ax, int16_t* ay, int16_t* az, int16_t* gx, int16_t* gy, int16_t* gz) {
    *ax = *ay = *gx = *gy = *gz = 0; *az = (int16_t)(verticalG * 2048);
  }
};
struct Adafruit_BMP280 {
  enum { MODE_NORMAL, SAMPLING_X1=1, SAMPLING_X2=2, SAMPLING_X4=4, SAMPLING_X16=16,
         FILTER_X16=16, STANDBY_MS_1=0, STANDBY_MS_500=500 };
  double periodMs = 0;
  template<class T> Adafruit_BMP280(T*) {}
  bool begin(int) { return true; } int sensorID() { return 0x58; }
  void setSampling(int, int t, int p, int, int standby) {
    periodMs = 1.25 + 2.3*t + 2.3*p + 0.575 + (standby ? standby : 0.5);
  }
  float readPressure() { return 101325; } float readTemperature() { return 20; }
};
'''

CHECKS = r'''
void require(bool value, const char* message) { if (!value) throw std::runtime_error(message); }
void runFor(uint64_t duration) {
  uint64_t end = clockUs + duration;
  while (clockUs < end) { loop(); clockUs += 10; }
}
int main(int argc, char** argv) {
  try {
    std::string test = argv[1];
    sdPresent = test == "sd_led";
    setup(); Serial.clear(); beeps.clear();
    uint64_t start = clockUs;
    if (test == "rate" || test == "sd_led") {
      workUs = 6000;
      runFor(2000000);
      require(Serial.samples.size() >= 119 && Serial.samples.size() <= 120,
              "Expected about 120 samples in 2 seconds including 6 ms of work per sample");
      for (size_t i=1; i<Serial.samples.size(); i++)
        require(Serial.samples[i]-Serial.samples[i-1] >= 16667 &&
                Serial.samples[i]-Serial.samples[i-1] < 16800,
                "Sample spacing drifted or a blocking LED delay remains");
    } else if (test == "stall") {
      runFor(40000);
      size_t before = Serial.samples.size();
      clockUs += 100000; loop();
      require(Serial.samples.size() == before + 1, "One sample should follow a stall");
      for (int i=0; i<100; i++) loop();
      require(Serial.samples.size() == before + 1, "Must not burst catch-up samples");
      require(dt > 0.1f, "Integration must include the actual stall duration");
    } else if (test == "wrap") {
      prevTime = 0xfffff000UL; clockUs = 0xfffff000ULL + 20000;
      loop();
      require(Serial.samples.size() == 1 && fabs(dt-0.02f) < 0.000001f,
              "Sampling and dt must work across micros() rollover");
    } else if (test == "debounce") {
      verticalG = 3; runFor(70000);
      require(flightState == PAD, "A short acceleration spike must not trigger liftoff");
      verticalG = 1; runFor(40000);
      verticalG = 3; runFor(70000);
      require(flightState == PAD, "A broken streak must restart the debounce timer");
      runFor(70000);
      require(flightState == BOOST, "Sustained acceleration must trigger liftoff");
      verticalG = 0.1f; runFor(70000);
      require(flightState == BOOST, "Short low-g streak must not trigger burnout");
      runFor(70000); require(flightState == COAST, "Sustained low-g must trigger burnout");
    } else if (test == "debounce_stall") {
      verticalG=3; runFor(40000); clockUs+=200000; loop();
      require(flightState==PAD, "Unobserved stall time must not confirm liftoff");
      runFor(130000); require(flightState==BOOST, "Liftoff must recover after fresh sustained readings");
      verticalG=0.1f; runFor(40000); clockUs+=200000; loop();
      require(flightState==BOOST, "Unobserved stall time must not confirm burnout");
      runFor(130000); require(flightState==COAST, "Burnout must recover after fresh sustained readings");
    } else if (test == "filter") {
      pitch=90; roll=90; dt=1.0f/60;
      for (int i=0; i<60; i++) formatpacket(i, 0, 0, 0, {0,0,1}, {0,0,0}, 0, {0,0,1});
      require(fabs(pitch-86.4676f) < 0.002f && fabs(roll-86.4676f) < 0.002f,
              "Attitude filtering must preserve its 20 Hz time constant at 60 Hz");
      flightState=COAST; velocity=10; prevAltitude_m=0;
      runFor(1000000);
      require(velocity > 6.65f && velocity < 6.75f,
              "Velocity filtering must preserve its 20 Hz time constant at 60 Hz");
    } else if (test == "buzzer") {
      runFor(9900000); require(beeps.empty(), "Buzzer must not speed up with sampling");
      runFor(300000); require(beeps.size()==1, "First beep should be near 10 seconds");
      runFor(2500000); require(beeps.size()==2, "Following beep should be 2.5 seconds later");
    } else if (test == "counter") {
      logstep=39999; runFor(20000);
      require(Serial.text.find("40000 | ") != std::string::npos,
              "Sample counter must not truncate to signed 16 bits");
    } else if (test == "barometer") {
      require(bmp.periodMs < 16.667, "Barometer conversion + standby must fit the sampling period");
    } else if (test == "simulation") {
      runFor(500000); require(flightState==PAD, "Simulation must begin on pad");
      runFor(1300000); require(flightState==BOOST, "Simulation boost must retain wall-clock timing");
      runFor(1200000); require(flightState==COAST, "Simulation should be coasting after 3 seconds");
      runFor(27000000); require(flightState==LANDED_STATE, "Simulation must reach landing");
      for (auto event : {"LIFTOFF", "BURNOUT", "APOGEE", "CHUTE DEPLOY", "LANDED"}) {
        std::string marker=std::string(">>> EVENT: ")+event;
        size_t first=Serial.text.find(marker);
        require(first != std::string::npos && Serial.text.find(marker, first+1)==std::string::npos,
                "Each simulated flight event must be emitted once");
      }
    }
    return 0;
  } catch (const std::exception& e) { fprintf(stderr, "%s\n", e.what()); return 1; }
}
'''


class FirmwareTiming(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="hephaestus-timing-")
        cls.addClassCleanup(cls.temp.cleanup)
        build = Path(cls.temp.name)
        vswhere = Path(os.environ["ProgramFiles(x86)"]) / "Microsoft Visual Studio/Installer/vswhere.exe"
        vs = subprocess.check_output([str(vswhere), "-latest", "-products", "*",
                                      "-requires", "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
                                      "-property", "installationPath"], text=True).strip()
        vcvars = Path(vs) / "VC/Auxiliary/Build/vcvars64.bat"
        output = subprocess.check_output(f'call "{vcvars}" >nul && set', shell=True, text=True)
        env = dict(line.split("=", 1) for line in output.splitlines() if "=" in line and not line.startswith("="))
        (build / "fakes.h").write_text(FAKES)
        for header in ("Wire.h", "SD.h", "Adafruit_BMP280.h", "MPU6050_6Axis_MotionApps20.h"):
            (build / header).write_text('#include "fakes.h"\n')
        source = SKETCH.read_text()
        # Arduino generates this prototype; ordinary host compilers do not.
        prototype = re.search(r"void formatpacket\([^)]*\)", source).group(0)
        harness = '#include "fakes.h"\nstruct Vector3;\n' + prototype + ';\n'
        harness += '#include "' + SKETCH.as_posix() + '"\n' + CHECKS
        (build / "timing.cpp").write_text(harness)
        cls.executables = {}
        for mode in ("normal", "simulation"):
            exe = build / (mode + ".exe")
            compiler = shutil.which("cl.exe", path=next(v for k, v in env.items() if k.lower() == "path"))
            args = [compiler, "/nologo", "/EHsc", "/std:c++17", "/I" + str(build),
                    str(build / "timing.cpp"), "/Fe:" + str(exe)]
            if mode == "simulation":
                args.append("/DSIMULATE_FLIGHT")
            result = subprocess.run(args, cwd=build, env=env, text=True, capture_output=True)
            if result.returncode:
                raise RuntimeError(result.stdout + result.stderr)
            cls.executables[mode] = exe

    def test_timing(self):
        for case in ("rate", "sd_led", "stall", "wrap", "debounce", "debounce_stall", "filter", "buzzer", "counter", "barometer", "simulation"):
            with self.subTest(case=case):
                exe = self.executables["simulation" if case == "simulation" else "normal"]
                result = subprocess.run([str(exe), case], text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    SKETCH = Path(sys.argv.pop(1)).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[2] / "src/Hephaestus_V1/Hephaestus_V1.ino"
    unittest.main()
