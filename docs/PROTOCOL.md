# Protocol notes

These notes come from Armoury Crate Gear for Mac 1.4.11 and an Azoth Extreme on firmware 3.00.11. The HTTP details come from the app's JavaScript, and the USB details come from the app's own packet log.

## Hidden upload panel

The Azoth Extreme's UI bundle renders the custom upload panel behind the following check:

```js
isBLE || isWebApp || isMAC ? null : <UploadPanel />
```

The check hides the panel on every Mac, whatever the connection. The backend code that the panel calls ships in the Mac app and works. A second check in the backend's profile restore code allows only presets over Bluetooth.

## Device IDs

The app's `ExternalFiles/dll/keyboard/config.ini` lists the following product IDs for the Azoth Extreme (vendor ID 2821, `0x0B05`):

| PID | Connection | Custom uploads |
| --- | --- | --- |
| 6975 | USB cable, wired mode | Supported and tested |
| 6978 | 2.4 GHz receiver | Untested |
| 6977 | Bluetooth | Blocked by the app |

## Local HTTP API

The Electron helper serves the API on `127.0.0.1:1042` (HTTPS on 1043). Every path in the following sections is relative to this base URL:

```
http://127.0.0.1:1042/api/1/type/2/model/PID
```

`PID` is the connected product ID from the preceding table, and type `2` means keyboard. Requests that target the device take `deviceSN` and `dongleSN` query parameters. Requests with no `Origin` header pass the server's CORS check.

The tool uses the following endpoints:

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/devices` | Lists the connected keyboard with its PID and serial number. |
| `GET` | `/deviceInfo` | Returns the active profile, firmware version, and battery state. |
| `POST` | `/amoled/animation` | Uploads an image or GIF as `multipart/form-data`. |
| `PATCH` | `/amoled/animation` | Plays the stored custom animation. |
| `PATCH` | `/amoled` | Plays a built-in preset. |

### Upload request

The upload is a `multipart/form-data` POST with the following fields:

| Field | Value |
| --- | --- |
| `input` | The image file. Any field name works, because the server accepts any file part. |
| `resizeWidth`, `resizeHeight` | `184` and `97`, the panel size |
| `extension` | `gif`, `png`, or `jpeg`. Send `jpeg` for a BMP. |
| `cropArea` | JSON `{"left", "top", "width", "height"}` in source pixels. Required. |
| `originImageInfo` | JSON `{"width", "height"}` of the source |
| `rotateAngle` | `0` |
| `pages` | Maximum GIF frames, up to `196`. GIF only. |
| `profileID` | The profile to save into |
| `isOledAnimeGlobal` | `true` |
| `isUploaded` | `0`, which means a new file |
| `isRecommend` | `0` |

The server answers with JSON that names the stored copy (`allPath`, `imagePath`, `fileName`). The route times out after 1,200,000 ms. The upload stores the animation but doesn't display it.

### Apply request

The hidden panel's **Apply** button sends the following JSON body as a PATCH to `/amoled/animation`:

```json
{"profileID": "1", "data": {"setOLEDIndex": "0", "isUploaded": "1", "customAnimePath": ""}, "isPreview": false}
```

`setOLEDIndex` `0` selects the Animation page, and `isUploaded` `1` plays the stored animation instead of uploading one.

### Preset request

The following JSON body, sent as a PATCH to `/amoled`, plays built-in preset 0:

```json
{"profileID": "1", "data": {"preloadAnimationId": "0"}, "isPreview": false}
```

## USB HID reports

Every report is 64 bytes. The app sends the following reports during an upload and when it switches animations:

| Report | Meaning |
| --- | --- |
| `61 01 00 00 COUNT` | Starts a transfer of `COUNT` data packets, as a little-endian 32-bit value. |
| `61 02 INDEX 00 00` + 58 bytes | Carries data. `INDEX` is little-endian 16-bit and counts down from `COUNT - 1` to 0. |
| `61 03` | Ends a transfer, or plays the stored custom animation. |
| `61 00 ID` | Plays built-in preset `ID`. |
| `6a 01` | Selects the Animation page. |
| `50 55` | Saves the setting to the profile. |

The app sends data packets in batches of 20. The keyboard acknowledges each batch with a `61 02 INDEX` report.

### Data stream

The data packets carry one stream in the following order:

1. Frame count, little-endian 16-bit
2. One delay per frame in milliseconds, little-endian 16-bit each
3. Every frame in order, 184 by 97 pixels, RGB565, 2 bytes per pixel

A stream of `F` frames is `2 + 2F + 35,696F` bytes, which the app splits into 58-byte payloads. The formula predicts the packet counts of both test uploads exactly: 44,315 packets for 72 frames, and 57,856 packets for 94 frames.

### Other reports

The following reports appear around transfers and aren't part of an upload:

- `12 01`: Battery poll, sent about once a minute. It competes with transfers, and some data writes fail with IOKit error `0xE00002BC` near it.
- `7d 20 01`: Status query that the keyboard rejects with `ff aa`. The app sends it before most commands, and the rejection is harmless.

## App file locations

The following paths are relative to `/Applications/Armoury Crate Gear.app/Contents/Helper/ASUS NodeJS Web Framework.app/Contents`:

| Path | Contents |
| --- | --- |
| `Resources/app.asar` | Electron main process, with webpack source maps |
| `ExternalFiles/modules/keyboard/index.js` | Request routing and the upload handler `processAmoledCustomAnime` |
| `ExternalFiles/dll/keyboard/asus_keyboard_sdk.dylib` | Go SDK with `setOledCustomRGBImage` and the RGB565 converter |
| `ExternalFiles/view/6975/` | Azoth Extreme UI bundle, including the panel size and the `isMAC` check |
| `ExternalFiles/view/externalFiles/keyboard/ROG AZOTH EXTREME/` | Copies of uploaded animations |

The packet log is at `~/Library/Application Support/ASUS/asus.service.log`.

## Check a new app version

To confirm that a new Armoury Crate Gear version still matches these notes, take the following steps:

1. Extract the main process: `python3 tools/asar_extract.py PATH_TO_APP_ASAR OUT_DIR`
2. Recover its sources: `python3 tools/sourcemap_extract.py OUT_DIR/.webpack/main/index.js.map SRC_DIR`
3. Search `ExternalFiles/modules/keyboard/index.js` for `amoled/animation` and `processAmoledCustomAnime`.
4. Run `./azoth-oled upload FILE --dry-run`, then a real upload, and compare the packet log with the USB report table.

Replace `PATH_TO_APP_ASAR` with the `Resources/app.asar` path, and `OUT_DIR` and `SRC_DIR` with empty folders.
