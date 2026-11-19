helloytd 1.1.0 — Windows x64

1. Extract the entire archive to a writable folder.
2. Open helloytd.exe. Python is included.
3. Paste a link, choose a format, and select download.

The app follows the Windows display language on the first launch.
Use Settings → Language to choose English or Russian. Restart to apply.

FFmpeg and one JavaScript runtime (Node.js or Deno) are required separately.
To install them with Windows Package Manager:
  winget install Gyan.FFmpeg
  winget install DenoLand.Deno

Settings, history, and cache are stored in data next to the EXE. If the
portable folder is read-only, they are stored in %APPDATA%\helloytd.
To move settings to another portable copy, close the app and copy data.
Downloaded files stay in the folder selected in the app.

If YouTube changes its formats, use “update yt-dlp” in Settings.
Restart after updating.

The archive includes Qt and PySide6 under LGPL 3. See
THIRD_PARTY_NOTICES.md for component licenses and corresponding sources.
