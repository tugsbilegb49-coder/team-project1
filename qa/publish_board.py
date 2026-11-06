"""Publish the reviewed local task manifest using authenticated GitHub CLI."""
import argparse
import base64
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]


class GitHubREST:
    """Reuse Git's credential helper in memory; never print or persist credentials."""
    def __init__(self):
        response = subprocess.run(['git', 'credential', 'fill'], cwd=ROOT,
            input='protocol=https\nhost=github.com\n\n', text=True, capture_output=True,
            env={**os.environ, 'GIT_TERMINAL_PROMPT': '0'})
        if response.returncode:
            raise RuntimeError('No existing GitHub git login. Connect GitHub or authenticate git/gh first.')
        values = dict(line.split('=', 1) for line in response.stdout.splitlines() if '=' in line)
        if not values.get('password'):
            raise RuntimeError('Git credential helper returned no usable GitHub credential.')
        auth = base64.b64encode((values.get('username', '')+':'+values['password']).encode()).decode()
        self.headers = {'Authorization': 'Basic '+auth, 'Accept': 'application/vnd.github+json',
                        'User-Agent': 'WorkTrack-QA', 'Content-Type': 'application/json'}

    def request(self, route, method='GET', data=None):
        request = Request('https://api.github.com'+route, method=method, headers=self.headers,
                          data=json.dumps(data).encode() if data is not None else None)
        try:
            with urlopen(request, timeout=20) as response:
                return json.load(response)
        except HTTPError as exc:
            code = exc.code
            exc.close()
            raise RuntimeError(f'GitHub API {method} failed: HTTP {code}. Check repository permissions.') from None

    def pages(self, route):
        rows = []
        for page in range(1, 21):
            batch = self.request(route+('&' if '?' in route else '?')+f'per_page=100&page={page}')
            rows.extend(batch)
            if len(batch) < 100: return rows
        raise RuntimeError('Repository has too many results for this publisher; narrow the scope.')


def issue_body(item):
    body = 'Owner: Camera, AI, QA, documentation\n\nAcceptance criteria:\n\n'
    body += '\n'.join('- [ ] '+line for line in item['acceptance'])
    body += '\n\nEvidence files (local implementation; link the eventual PR/CI run here):\n\n'
    body += '\n'.join('- `'+path+'`' for path in item['evidence'])
    body += '\n\nEvery PR must link this issue, tested source revision, commands, outcome and artifact URL.\n'
    if item.get('remaining'): body += '\nPending: '+item['remaining']+'\n'
    return body


def publish_issues(board, repo):
    api = GitHubREST()
    prefix = '/repos/'+repo
    milestones = api.pages(prefix+'/milestones?state=all')
    milestone = next((m for m in milestones if m['title'] == board['title']), None)
    if milestone is None:
        milestone = api.request(prefix+'/milestones', 'POST', {'title': board['title'],
            'description': '7-day Camera / AI / QA delivery. Acceptance and actual evidence are tracked per issue.'})
    labels = api.pages(prefix+'/labels')
    if not any(label['name'] == 'camera-ai-qa' for label in labels):
        api.request(prefix+'/labels', 'POST', {'name':'camera-ai-qa','color':'1D76DB','description':'Camera, AI, consent, evaluation and final QA'})
    existing = api.pages(prefix+'/issues?state=all')
    published = []
    for item in board['items']:
        title = f"[{item['key']}] Day {item['day']}: {item['title']}"
        issue = next((i for i in existing if i['title'] == title and 'pull_request' not in i), None)
        if issue is None:
            issue = api.request(prefix+'/issues', 'POST', {'title': title, 'body': issue_body(item),
                'milestone': milestone['number'], 'labels':['camera-ai-qa']})
        published.append({'key':item['key'], 'number':issue['number'], 'url':issue['html_url']})
    title = '[CAM-QA] Seven-day delivery board and test evidence'
    board_issue = next((i for i in existing if i['title'] == title and 'pull_request' not in i), None)
    body = 'Daily task board (review acceptance criteria before marking a task done):\n\n'
    old_body = (board_issue.get('body') or '') if board_issue else ''
    checked = set(re.findall(r'- \[[xX]\] (CAM-QA-\d+):', old_body))
    body += '\n'.join(f"- [{'x' if item['key'] in checked else ' '}] {item['key']}: {item['url']}" for item in published)
    evidence_path = ROOT/'qa/evidence/final-qa.json'
    if evidence_path.exists():
        evidence = json.loads(evidence_path.read_text())
        body += '\n\nLocal QA evidence\n\n'
        body += f"- Source base: `{evidence['source']['git_head']}`; uncommitted changes: `{evidence['source']['working_tree_dirty']}`.\n"
        body += f"- Source SHA-256: `{evidence['source']['source_sha256']}`.\n"
        body += f"- Overall automated QA: **{evidence['status']}**; {len(evidence['stages'])} stages.\n"
        body += '- Reproduce: `python verify_camera_ai.py`; report: `qa/evidence/final-qa.json`.\n'
        body += '- This is local test evidence; remote CI and the implementation PR are pending publication.\n'
        body += '\nRemaining manual validation:\n\n- Human-labeled real camera Precision/Recall/F1.\n- Human presentation rehearsal.\n'
    body += '\nEvery team PR: link its issue, tested revision, commands/results and CI artifact URL. Do not attach camera frames, video, credentials or personal data.\n'
    marker_start, marker_end = '<!-- worktrack-qa:start -->', '<!-- worktrack-qa:end -->'
    managed = marker_start+'\n'+body+'\n'+marker_end
    if board_issue is None:
        board_issue = api.request(prefix+'/issues', 'POST', {'title':title, 'body':managed,
            'milestone':milestone['number'], 'labels':['camera-ai-qa']})
    else:
        old = board_issue.get('body') or ''
        replacement = re.sub(re.escape(marker_start)+'.*?'+re.escape(marker_end), lambda _: managed, old, flags=re.S)
        if replacement == old and marker_start not in old:
            replacement = old+'\n\n'+managed
        board_issue = api.request(prefix+'/issues/'+str(board_issue['number']), 'PATCH', {'body':replacement})
    return {'kind':'issue-milestone-board', 'repository':repo, 'milestone':milestone['html_url'],
            'board':board_issue['html_url'], 'issues':published}


def run(*args):
    return subprocess.check_output(['gh', *args], cwd=ROOT, text=True).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', default='tugsbilegb49-coder/team-project1')
    parser.add_argument('--apply', action='store_true', help='Create missing issues and add them to the project.')
    parser.add_argument('--project', type=int, help='Existing project number; omit to create a project.')
    parser.add_argument('--issues-only', action='store_true', help='Publish an issue/milestone board through existing git login; gh/project scope not needed.')
    args = parser.parse_args()
    board = json.loads((ROOT/'qa/board.json').read_text())
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', args.repo):
        parser.error('--repo must be owner/repository.')
    if not args.apply:
        print(json.dumps({'mode':'dry-run','repo':args.repo,'board':board}, indent=2, ensure_ascii=False))
        return
    if args.issues_only:
        result = publish_issues(board, args.repo)
        output = ROOT/'qa/evidence/github-board.json'
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2)+'\n')
        print(f"Published issue/milestone board: {result['board']}")
        return
    if not shutil.which('gh'):
        parser.error('GitHub CLI is unavailable. Install gh and authenticate; dry-run needs no connection.')
    subprocess.run(['gh','auth','status'], check=True, cwd=ROOT)
    owner = args.repo.split('/')[0]
    number = args.project
    if number is None:
        project = json.loads(run('project','create','--owner',owner,'--title',board['title'],'--format','json'))
        number = project['number']
    existing = json.loads(run('issue','list','--repo',args.repo,'--state','all','--limit','1000','--json','title,url'))
    published = []
    for item in board['items']:
        title = f"[{item['key']}] Day {item['day']}: {item['title']}"
        url = next((i['url'] for i in existing if i['title'] == title), None)
        if url is None:
            body = issue_body(item)
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory)/'issue.md'
                path.write_text(body, encoding='utf-8')
                url = run('issue','create','--repo',args.repo,'--title',title,'--body-file',str(path))
        run('project','item-add',str(number),'--owner',owner,'--url',url)
        published.append({'key':item['key'],'url':url})
    output = ROOT/'.runtime/qa/github-board.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({'owner':owner,'project':number,'issues':published}, indent=2)+'\n')
    print(f'Published {len(published)} issues to project {number}; {output}')


if __name__ == '__main__':
    main()
