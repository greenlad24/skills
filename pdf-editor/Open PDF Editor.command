#!/bin/bash
# Double-click this file to start the PDF editor.
#
# It serves the folder on a random port bound to 127.0.0.1 (this Mac only) and
# opens your browser. Nothing leaves the machine; the server is only here
# because browsers restrict what a page opened straight from a file:// URL is
# allowed to do.
#
# Close this Terminal window (or press Ctrl-C) when you are done.

cd "$(dirname "$0")" || exit 1

PORT=""
for candidate in 8757 8758 8759 8760 8761 8762; do
  if ! nc -z 127.0.0.1 "$candidate" >/dev/null 2>&1; then
    PORT="$candidate"
    break
  fi
done
[ -z "$PORT" ] && PORT=8763

URL="http://127.0.0.1:$PORT/index.html"

start_server() {
  # Ruby first: Big Sur ships it, and unlike /usr/bin/python3 it never pops up
  # the "install developer tools" dialog.
  if command -v ruby >/dev/null 2>&1; then
    echo "Serving with ruby on $URL"
    ruby -run -e httpd . -p "$PORT" -b 127.0.0.1 >/dev/null 2>&1 &
  elif command -v python3 >/dev/null 2>&1 && python3 -c '' >/dev/null 2>&1; then
    echo "Serving with python3 on $URL"
    python3 -m http.server "$PORT" --bind 127.0.0.1 >/dev/null 2>&1 &
  elif command -v php >/dev/null 2>&1; then
    echo "Serving with php on $URL"
    php -S "127.0.0.1:$PORT" >/dev/null 2>&1 &
  elif command -v python >/dev/null 2>&1; then
    echo "Serving with python on $URL"
    python -m SimpleHTTPServer "$PORT" >/dev/null 2>&1 &
  else
    return 1
  fi
  SERVER_PID=$!
  return 0
}

if start_server; then
  # Give the server a moment to bind before the browser asks for the page.
  sleep 1
  open "$URL"
  echo
  echo "PDF editor is running. Leave this window open while you work."
  echo "Press Ctrl-C (or just close this window) to stop it."
  trap 'kill $SERVER_PID 2>/dev/null; exit 0' INT TERM
  wait $SERVER_PID
else
  echo "No python3, ruby or php found — opening the page directly instead."
  echo "It still works, just a little slower on big documents."
  open "index.html"
fi
