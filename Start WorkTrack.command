#!/bin/zsh
cd -- "${0:A:h}" || exit 1
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
if (( $# == 0 )); then
  set -- --desktop
fi
# Say what is missing and open its download page instead of failing with a technical error.
missing=()
[[ -x .venv/bin/python ]] || command -v python3 >/dev/null || missing+=("Python 3.12 https://www.python.org/downloads/")
command -v node >/dev/null || missing+=("Node.js LTS https://nodejs.org/")
if (( ${#missing} )); then
  printf '\nWorkTrack-д эхлээд дараах үнэгүй програм хэрэгтэй:\n'
  for item in "${missing[@]}"; do
    printf '  - %s\n' "${item% *}"
    open "${item##* }"
  done
  printf '\nТатах хуудсыг browser-т нээлээ. Суулгаад энэ файлыг дахин нээнэ үү.\nЦонхыг хаахын тулд Enter дарна уу.\n'
  read -r
  exit 1
fi
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
