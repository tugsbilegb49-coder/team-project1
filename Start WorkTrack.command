#!/bin/zsh
cd -- "${0:A:h}" || exit 1
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
if [[ -x .venv/bin/python ]]; then
  .venv/bin/python worktrack.py "$@"
else
  python3 worktrack.py "$@"
fi
result=$?
if (( result != 0 )); then
  printf '\nАлдаа гарлаа. Цонхыг хаахын тулд Enter дарна уу.\n'
  read -r
fi
exit $result
