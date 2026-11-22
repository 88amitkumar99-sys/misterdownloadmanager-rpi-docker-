# Mister Download Manager for Raspberry Pi (Docker)

A Docker image for running Mister Download Manager on a Raspberry Pi.

Original project: https://github.com/anefzaoui/misterdownloadmanager

## Requirements

- Raspberry Pi (ARM) with Docker installed
- A USB drive for downloads

## Run

```bash
mkdir -p /opt/mdm-config /mnt/usb/downloads

docker run -d \
  --name mdm \
  --restart unless-stopped \
  --network host \
  --user 0:0 \
  -e MDM_REMOTE_PORT=8463 \
  -e MDM_REMOTE_URL=https://<Host_IP>:8463/ \
  -v /opt/mdm-config:/config \
  -v /mnt/usb/ 
  ghcr.io/88amitkumar99-sys/misterdownloadmanager:latest
```

Replace `<Host_IP>` with your Pi's IP address (for example, `192.168.1.50`).

## Notes

- Configuration is stored in `/opt/mdm-config` (on the SD card), and downloads are saved to `/mnt/usb` (on the USB drive).
- Make sure the USB drive is mounted before starting the container (check with `df -h /mnt/usb`).
- Do not expose port 8463 to the internet.
