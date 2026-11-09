#!/bin/zsh
# Office server: this computer runs WorkTrack for the whole office network.
# Employees enter the address it shows (https://192.168.x.x:8443) and server code in their WorkTrack app.
exec "${0:A:h}/Start WorkTrack.command" --desktop --share
