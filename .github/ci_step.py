"""Run one CI check and, if it fails, also publish the failure output as GitHub annotations.

Annotations show on the run page and through the public API, so a failure can be read
without downloading logs. Usage: python .github/ci_step.py "Title" command [args...]
"""

import shutil
import subprocess
import sys

CHUNK = 3500  # Keep each annotation well under GitHub's message limit.
MAX_ANNOTATIONS = 9  # GitHub keeps at most 10 error annotations per step.


def escape(text):
    return text.replace('%', '%25').replace('\r', '').replace('\n', '%0A')


def failure_part(output):
    """unittest/pytest print the failure details after a '=====' rule; start there if present."""
    marker = min((i for i in (output.find('\n===='), output.find('\nFAILED ')) if i >= 0), default=-1)
    return output[marker:] if marker >= 0 else output


def main():
    title, command = sys.argv[1], sys.argv[2:]
    command[0] = shutil.which(command[0]) or command[0]  # npm/npx are .cmd files on Windows.
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    sys.stdout.buffer.write(result.stdout)
    sys.stdout.flush()
    if result.returncode:
        details = failure_part(result.stdout.decode('utf-8', 'replace'))
        chunks = [details[i : i + CHUNK] for i in range(0, len(details), CHUNK)]
        if len(chunks) > MAX_ANNOTATIONS:
            chunks = chunks[: MAX_ANNOTATIONS - 1] + chunks[-1:]
        for number, chunk in enumerate(chunks, 1):
            print(f'::error title={title} ({number}/{len(chunks)})::{escape(chunk)}', flush=True)
    return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
