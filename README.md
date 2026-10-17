# Hephaestus Flight Computer

Embedded flight computer developed for real-time environmental sensing and motion tracking using multiple onboard sensors.

## Overview
Hephaestus is a custom-built flight computer designed to collect and process flight data including altitude, pressure, temperature, and motion. The system integrates multiple sensors to improve data reliability and accuracy through averaging and redundancy.

##  Features
- **Altitude, Temperature, Pressure**
  - Powered by BMP280 barometric sensor
-  **Motion Tracking**
  - Dual MPU6050 (GY-521) IMUs for redundancy
  - Averaged gyro and accelerometer readings for noise reduction
-  **Sensor Fusion Approach**
  - Combines data from multiple IMUs to improve stability and accuracy
  - Complementary filter for Pitch and Roll
-  **Real-Time Telemetry Output**
  - Serial output for debugging and live monitoring
-  **Data Recovery**
  - SD card writing

## System Architecture
- **PCB:** Custom designed Galalumga board
- **Microcontroller:** Teensy 4.1
- **Sensors:**
  - 1x BMP280 (I2C)
  - 2x MPU6050 (I2C, adressed)
- **Data Handling:**
  - Sensor polling loop
  - Averaging algorithm for IMU data
  - Complementary filtered IMU
  - Formatted serial output

## Example Output
<img width="1513" height="234" alt="image" src="https://github.com/user-attachments/assets/afbe94a2-c4d7-4770-84f9-34c6dc938cd3" />

## Sampling and verification

- The firmware targets 60 Hz (16,667 microseconds between sample starts), including sensor reads and logging within that interval. Slow SD writes/flushes can still cause missed periods; integration uses the measured elapsed time and the loop does not burst to catch up.
- The BMP280 uses temperature x1, pressure x4, and 0.5 ms standby (~83 Hz typical conversions). This reduces oversampling relative to the old x16 setting; its x16 IIR filter remains enabled, so conversion rate is not the same as response bandwidth.
- Filter weights, flight-event debounce, the bench simulation, and the buzzer use elapsed time. Filter/debounce timing retains the original nominal 20 Hz tuning.
- `TIME` and event `t=` remain sample counters, not seconds. USB serial baud settings do not control Teensy's USB transfer speed.
- On the bench, check for roughly 600 samples over 10 seconds after startup, both with and without the SD card. Inspect occasional long intervals separately; host serial timestamps can include USB buffering. The real board's sustained rate and flight-event tuning still require hardware validation.
- Keep `SIMULATE_FLIGHT` commented out for real sensor operation. The simulation substitutes fake sensor data.

Compile with the installed Arduino/Teensy toolchain: `arduino-cli compile --fqbn teensy:avr:teensy41 src/Hephaestus_V1`.

Run the software timing checks on Windows with Python and the Visual Studio C++ tools installed: `python tests/firmware/test_timing.py`. They compile the actual sketch against a fake clock and hardware interfaces, including simulation, rollover, overruns, debounce, filter response, and counter formatting. They do not measure hardware latency.


## Tech Stack
- C++ (Arduino framework)
- I2C communication
- Embedded systems programming

## Goals
- Provide reliable flight telemetry
- Reduce sensor noise through redundancy
- Serve as a foundation for future flight logic (e.g., apogee detection, deployment systems)

## Future Improvements
- Kalman filtering / sensor fusion refinement
- Data logging (SD card)
- Wireless telemetry (LoRa / RF)
- Flight event detection (apogee, descent)
- Eventual SMT PCB and sensor upgrades.

## Hardware Setup
<img width="935" height="546" alt="image" src="https://github.com/user-attachments/assets/206de5bb-a208-4b8d-8ecd-56a43a2ca192" />

##  Repository Structure
- /src - main .ino file
- /vis - data visualization algo
- /docs - documentation

## Author
**CR_DGD**

---

### Notes
- Designed for experimentation and iterative development
- Flight count: 0 (pre-flight testing phase)
