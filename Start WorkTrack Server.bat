@echo off
rem Office server: this computer runs WorkTrack for the whole office network.
rem Employees enter the address it shows (https://192.168.x.x:8443) and server code in their WorkTrack app.
call "%~dp0Start WorkTrack.bat" --desktop --share
