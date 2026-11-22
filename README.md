# Mister Download Manager for Raspberry Pi (Docker / Portainer)

Builds an arm64 Docker image of [Mister Download Manager](https://github.com/anefzaoui/misterdownloadmanager) for a Raspberry Pi, with a phone-friendly page that adds:

- a password (set on the first visit; any number of devices can sign in)
- a speed limit for all downloads and one for each download
- time left, and whether a download can resume
- a download folder you choose on the page
- the speed in the browser tab's title

The image is built by GitHub Actions (`.github/workflows/build-arm64-image.yml`) from the upstream code plus the changes in `mdm-patch/`.

## Requirements

- Raspberry Pi with a 64-bit OS (`uname -m` shows `aarch64`) and Docker
- A USB drive for downloads
- The package `misterdownloadmanager` on GitHub set to **Public** (Packages, Package settings, Change visibility)

## Run (Portainer: Stacks, Add stack)

Replace `192.168.1.50` with your Pi's IP address.

```yaml
services:
  mdm:
    image: ghcr.io/88amitkumar99-sys/misterdownloadmanager:latest
    container_name: mdm
    restart: unless-stopped
    network_mode: host
    user: "0:0"
    environment:
      MDM_REMOTE_PORT: "8463"
      MDM_REMOTE_URL: "https://192.168.1.50:8463/"
    volumes:
      - /opt/mdm-config:/config
      - /mnt/usb/downloads:/downloads
      - /mnt/usb:/mnt/usb
```

## First use

1. Open `https://192.168.1.50:8463/` in a browser. Accept the certificate warning (Advanced, Proceed): the certificate is the app's own.
2. Create a password.
3. Choose the download folder (for example `/mnt/usb/downloads`).

## Notes

- Settings are kept in `/opt/mdm-config` (SD card). Downloads go to the folder you choose, by default `/mnt/usb/downloads` (USB drive).
- Choose a folder inside a mounted volume, or the files are lost when the container is recreated.
- Check the USB drive is mounted before starting the container: `df -h /mnt/usb`.
- Forgot the password? Delete `/opt/mdm-config/remote/password.json`, then open the page again.
- Do not expose port 8463 to the internet.

## License

Mister Download Manager is GPL-3.0-or-later. The changes in `mdm-patch/` are released under the same license.
