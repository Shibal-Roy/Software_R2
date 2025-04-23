import asyncio
import websockets
import json
import re

def parse_telemetry(telemetry_str):
    """Parse telemetry string into a dictionary."""
    pattern = r'X-([-\d.]+)-Y-([-\d.]+)-BAT-([\d.]+)-GYR-\[([-\d.,]+)\]-WIND-([\d.]+)-DUST-([\d.]+)-SENS-(\w+)'
    match = re.match(pattern, telemetry_str)
    if not match:
        return None
    try:
        x = float(match.group(1))
        y = float(match.group(2))
        bat = float(match.group(3))
        gyr = list(map(float, match.group(4).split(',')))
        wind = float(match.group(5))
        dust = float(match.group(6))
        sensor = match.group(7)
        return {
            'x': x,
            'y': y,
            'battery': bat,
            'gyro': gyr,
            'wind': wind,
            'dust': dust,
            'sensor': sensor
        }
    except (ValueError, IndexError):
        return None

def check_crash(parsed):
    """Check if the drone has crashed based on telemetry."""
    if parsed['battery'] <= 0:
        return True
    y = parsed['y']
    sensor = parsed['sensor']
    if sensor == 'RED' and y > 3:
        return True
    if sensor == 'YELLOW' and y > 1000:
        return True
    if y < 0:
        return True
    if abs(parsed['x']) > 1e5:
        return True
    gx, gy, gz = parsed['gyro']
    tilt_magnitude = (gx**2 + gy**2 + gz**2)**0.5
    if tilt_magnitude > 1.0:  # Gyroscope values should be in the range -1.0 to 1.0
        return True
    return False

async def drone_control():
    """Control the drone based on telemetry data."""
    uri = "ws://localhost:8765"
    try:
        async with websockets.connect(uri) as websocket:
            current_movement = 'fwd'
            speed = 3
            target_altitude = 2000

            while True:
                try:
                    response = await websocket.recv()
                    data = json.loads(response)
                    if data['status'] == 'crashed':
                        print("Crashed:", data)
                        break
                    telemetry_str = data['telemetry']
                    parsed = parse_telemetry(telemetry_str)
                    if not parsed:
                        print("Failed to parse telemetry")
                        continue

                    if check_crash(parsed):
                        print("Crash condition met!")
                        break

                    sensor_status = parsed['sensor']
                    current_y = parsed['y']
                    current_x = parsed['x']
                    battery = parsed['battery']
                    gx, gy, gz = parsed['gyro']

                    # Set target altitude based on sensor status
                    if sensor_status == 'RED':
                        target_altitude = 2
                    elif sensor_status == 'YELLOW':
                        target_altitude = 999
                    else:
                        target_altitude = 2000

                    # Calculate altitude command with dynamic clamping
                    delta_y = target_altitude - current_y
                    max_delta = max(10, min(100, abs(delta_y) // 2))
                    altitude_cmd = max(-max_delta, min(max_delta, int(delta_y)))
                    if abs(delta_y) < 10:
                        altitude_cmd = 0

                    # Adjust speed and movement based on tilt and x position
                    if battery < 20:
                        speed = 1
                    else:
                        if abs(gx) >= 0.8:  # Adjust speed based on tilt magnitude
                            speed = max(1, speed - 1)
                            current_movement = 'rev' if current_movement == 'fwd' else 'fwd'
                        elif abs(gx) < 0.5 and battery > 20:
                            speed = min(5, speed + 1)

                    # Check x position to avoid limits
                    if current_x > 90000:
                        current_movement = 'rev'
                    elif current_x < -90000:
                        current_movement = 'fwd'

                    # Prepare command
                    command = {
                        'speed': speed,
                        'altitude': altitude_cmd,
                        'movement': current_movement
                    }

                    await websocket.send(json.dumps(command))

                except json.JSONDecodeError:
                    print("Failed to decode server response")
                except websockets.exceptions.ConnectionClosed:
                    print("Connection closed by server")
                    break

    except ConnectionRefusedError:
        print("Failed to connect to the server. Ensure the server is running.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(drone_control())
