@echo off
wpeinit
if exist X:\DiskManager\job.json (
  rem Real-disk writes require explicit user authorization. Add --allow-real only after approval.
  X:\DiskManager\DiskManagerOffline.exe run --job X:\DiskManager\job.json --journal X:\DiskManager\journal.log
  if %errorlevel%==0 (
    echo DiskManager offline move completed. Rebooting...
    wpeutil reboot
  ) else (
    echo DiskManager offline move failed. See X:\DiskManager\journal.log
    pause
  )
) else (
  echo DiskManager job.json not found.
  pause
)
