"""Single-flight isolated quarantine. No originals survive request completion."""
import asyncio
import json
import os
from pathlib import Path
import signal
import sys
import tempfile
from fastapi import FastAPI, Request, HTTPException
from ai_firewall.services import auth

app=FastAPI();lock=asyncio.Lock()

@app.get('/health')
async def health():return {'ready':True}

@app.post('/extract')
async def extract(request:Request):
    auth(request,'NATIVE_GATEWAY_KEY')
    extension=request.headers.get('X-File-Extension','')
    if extension not in {'pdf','docx','xlsx','txt','png','jpg','jpeg','tif','tiff','webp'}:raise HTTPException(415,'unsupported_format')
    if lock.locked():raise HTTPException(429,'ocr_worker_busy')
    async with lock:
        with tempfile.TemporaryDirectory(dir='/tmp',prefix='quarantine-') as directory:
            path=Path(directory)/'input';size=0
            with path.open('wb') as output:
                async for chunk in request.stream():
                    size+=len(chunk)
                    if size>10*1024*1024:raise HTTPException(413,'file_too_large')
                    output.write(chunk)
            if not size:raise HTTPException(400,'empty_file')
            process=await asyncio.create_subprocess_exec(sys.executable,'-m','ai_firewall.file_extract',str(path),extension,
                stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL,start_new_session=True)
            try:
                stdout,_=await asyncio.wait_for(process.communicate(),timeout=100)
                if process.returncode:raise ValueError()
                return json.loads(stdout)
            except BaseException as exc:
                try:os.killpg(process.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                await process.wait()
                if isinstance(exc,asyncio.CancelledError):raise
                raise HTTPException(422,'extraction_incomplete') from None
