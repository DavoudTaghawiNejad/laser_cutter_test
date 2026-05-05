# fake_grbl.py
import serial

print('First run:')
print('socat -d -d pty,raw,echo=0,link=/tmp/ttyFAKE \ ')
print('pty,raw,echo=0,link=/tmp/ttyFAKE2')
print('Set port to port: /tmp/ttyFAKE ')

s = serial.Serial('/tmp/ttyFAKE2', 115200, timeout=1)
print("Fake GRBL listening on /tmp/ttyFAKE2")
s.write(b"Grbl 1.1h ['$' for help]\r\n")        # startup banner
while True:
    line = s.readline()
    if line:
        cmd = line.strip().decode(errors='replace')
        print(f"<- {cmd}")
        s.write(b"ok\r\n")
