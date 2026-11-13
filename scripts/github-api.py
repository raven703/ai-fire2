"""GitHub API using existing gh/environment/Git credentials, never printing secrets."""
import json
import os
import subprocess
import sys
import urllib.request

class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        redirected=super().redirect_request(req,fp,code,msg,headers,newurl)
        if redirected is not None:
            redirected.remove_header('Authorization')
        return redirected

def token():
    value=os.getenv('GH_TOKEN') or os.getenv('GITHUB_TOKEN')
    if value:return value
    try:
        value=subprocess.check_output(['gh','auth','token'],stderr=subprocess.DEVNULL,text=True).strip()
        if value:return value
    except (FileNotFoundError,subprocess.CalledProcessError):pass
    r=subprocess.run(['git','credential','fill'],input='protocol=https\nhost=github.com\n\n',
        text=True,capture_output=True,timeout=30,check=True,env={**os.environ,'GIT_TERMINAL_PROMPT':'0'})
    return dict(l.split('=',1) for l in r.stdout.splitlines() if '=' in l)['password']

def request(path,method='GET',data=None,binary=False):
    req=urllib.request.Request('https://api.github.com/'+path.lstrip('/'),
        data=json.dumps(data).encode() if data is not None else None,method=method,
        headers={'Authorization':'Bearer '+token(),'Accept':'application/vnd.github+json',
            'X-GitHub-Api-Version':'2022-11-28','User-Agent':'ai-fire2-deployment'})
    with urllib.request.build_opener(SafeRedirect()).open(req,timeout=90) as r:raw=r.read()
    return raw if binary else json.loads(raw) if raw else {}

if __name__=='__main__':
    if len(sys.argv)>2 and sys.argv[2]=='download':
        from pathlib import Path
        Path(sys.argv[3]).write_bytes(request(sys.argv[1],binary=True))
    else:print(json.dumps(request(sys.argv[1],sys.argv[2] if len(sys.argv)>2 else 'GET',
        json.loads(sys.argv[3]) if len(sys.argv)>3 else None)))