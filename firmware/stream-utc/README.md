# XIAO Stream Trial 02 UTC

Field trial for the compact XIAO ESP32-S3, Wio SX1262, SPH0641LU4H-1 microphone and Adafruit microSD BFF.  The monitor scores the ultrasonic stream continuously and saves short clips on candidate detections.  This revision adds same-boot UTC synchronisation and retains the Trial 01 model, threshold and audio settings.

## Prepare for a night

1. In Arduino IDE 2, use **esp32 by Espressif Systems 4.0.0** and install **RadioLib by Jan Gromes 8.0.0** using Library Manager.  Open **XiaoStream/XiaoStream.ino**.  Select **XIAO_ESP32S3**, **8 MB flash**, **OPI PSRAM**, **USB CDC On Boot Enabled** and the experimental board's port.  Click Upload.  The optional Windows installer also supports a resumable flash backup.
2. For Wi-Fi time, put a plain-text file named **stream-wifi.txt** at the root of the FAT32 card.  Line 1 is the 2.4 GHz Wi-Fi name, line 2 its password.  For live event reports, add the receiving PC's IPv4 address on line 3 and run **Listen-WiFi.ps1** on that PC (UDP 8768 on the private LAN).  With two lines the board uses Wi-Fi for time only.  Keep the credentials private.  The existing Trial 01 three-line file works.  With no file, the radio listens for the Museum transit gateway as the time source.
3. Power up with the card inserted.  Serial Monitor at **115200**, **Newline** prints a status every five seconds.  Before deployment, confirm **XIAO-STREAM-02**, **ready=1**, **sd=mounted**, **clips_buffered=1** and **clock_sd=saved** with **clock=WIFI_NTP** or **clock=LORA_OTD**.  Send **clip** once, watch **saved** rise and **gaps** stay steady.  Keep power connected when moving into the field to preserve that boot's clock.  Every reboot starts a new session and acquires time again.

## Overnight behaviour

Capture and scoring begin without waiting for a network.  A frame at or above threshold 1,404 starts a candidate if there has been at least one second since the last positive frame.  The SD writer saves a two-second mono, 192 kHz, 16-bit WAV (768,044 bytes) including up to 251 ms ending at the trigger.  Files are in **/STREAM02/<boot ID>/** and contain the sequence and trigger uptime in their names.  The upload does not change previous STREAM01 recordings.

USB reports every candidate.  A configured Wi-Fi destination receives one short UDP message per candidate when connected.  Delivery is best effort, with no replay or hourly summary.  LoRa is receive-only for clock updates.  Two clip buffers let capture continue while a completed clip is being written.  Closely spaced candidates can share audio in the first clip.  A missing separate WAV increments **unsaved**.  An interrupted write may leave a **.part** file.  Manual recordings are labelled **test**.  Listening continues after sunrise until power is removed.  Field sensitivity and battery runtime require measurement.

## Clock acquisition

* The board requests UTC over NTP on Wi-Fi and accepts a fresh sync callback.  Allow outbound NTP (UDP 123).  In time-only mode it switches Wi-Fi off after sync, then requests a refresh an hour later.  Without a connection or time reply it ends the time-only attempt after 45 seconds and retries five minutes later.  With a reporting address, it stays connected for alerts when the network is available.
* The Wio listens passively at 915 MHz, BW125, SF9, CR4/7, private sync word 0x12.  It uses the gateway send epoch in Museum Route 6 OTD2 or OTD3 packets.  Two advancing packets from one gateway session must agree with elapsed receiver time within four seconds.  Duplicate packets, timetable pages and ACKs cannot set the clock.  This path estimates UTC to roughly seconds; sub-second accuracy has not been measured.  It requires an active, in-range Museum gateway.  A MeshCore RT repeater or an AR4 alone does not supply those packets.
* After a fix the Wio sleeps for about an hour, then listens for a refresh if needed.  A missing radio does not stop capture.  The boot-relative clock continues between fixes.  With no fix, the node reports **clock=UNSYNCED utc_ms=0**, saves clips and keeps seeking time.  A new boot never inherits an old session's timestamp.
* **clock.csv** in each boot directory records validated anchor rows as **boot,uptime_ms,utc_ms,source,END**.  The monitor retries a failed anchor write.  UTC at a trigger is the anchor UTC plus the difference in uptimes.  A later fix can date recordings earlier in the same boot.  Losing power before any anchor is saved leaves that session with relative timing only.

## Morning review

With the card mounted on Windows, run the following from this package, replacing the drive letter.  The bundled script uses Python 3's standard library and leaves the WAVs in place.

```powershell
py -3 clip_times.py E:\STREAM02 --output ClipTimes.csv
```

Each row gives the trigger UTC, time source and distance to the nearest saved anchor for that boot.  The trigger is usually about 251 ms into the audio.  Compare trigger UTC with the other recorders using the same timezone.  Sessions with no anchor have a blank UTC.  Copy the whole boot folder including **clock.csv** when archiving.  Automatic daily import and battery endurance have not been validated for this trial.

## Hardware and verification

Mic CLK D0/GPIO1, DATA D1/GPIO2, SEL strapped low, internal word-select D3/GPIO4.  SD uses factory CS D6/GPIO43 and SCK/MISO/MOSI D8/D9/D10.  Wio uses the same SPI bus with CS41, IRQ39, RST42, BUSY40 and RX switch GPIO38.  SD writes, radio operations and time-anchor writes share a mutex outside the audio capture task.

Trial 01 on COM14 sustained 375 frames/s and wrote two valid two-second WAVs with zero reported gaps.  The two replayed scores at the manual triggers matched the live values.  These checks establish the audio baseline for Trial 02.  A field clock lock, a card read-back and a co-located night are the hardware acceptance checks for the new revision.
