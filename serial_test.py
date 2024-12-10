import serial
import time

# Configure the serial port
# Make sure to use the correct port name for your system
ser = serial.Serial('/dev/ttyACM0', 9600, timeout=1)

# Wait for the serial connection to initialize
time.sleep(2)

try:
    while True:
        # Send '0' to the Arduino
        ser.write(b'0')
        
        # Read the response
        response = ser.readline().decode('utf-8').strip()
        
        # Print the response
        print(f"Received: {response}")
        
        # Wait a bit before sending again
        time.sleep(1)

except KeyboardInterrupt:
    print("Program terminated by user")

finally:
    # Close the serial connection
    ser.close()
    print("Serial connection closed")
