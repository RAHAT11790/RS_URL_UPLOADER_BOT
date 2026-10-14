#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# RS HuggingFace Router — Simple Router
# Modified By: @RS_WONER

import os
import asyncio
import aiohttp
import re
from aiohttp import web

PORT = int(os.environ.get("PORT", 7860))

# ========== STYLISH TEXT ==========
def S(text):
    bold_map = {
        'A': '𝐀', 'B': '𝐁', 'C': '𝐂', 'D': '𝐃', 'E': '𝐄', 'F': '𝐅', 'G': '𝐆', 'H': '𝐇', 'I': '𝐈',
        'J': '𝐉', 'K': '𝐊', 'L': '𝐋', 'M': '𝐌', 'N': '𝐍', 'O': '𝐎', 'P': '𝐏', 'Q': '𝐐', 'R': '𝐑',
        'S': '𝐒', 'T': '𝐓', 'U': '𝐔', 'V': '𝐕', 'W': '𝐖', 'X': '𝐗', 'Y': '𝐘', 'Z': '𝐙',
        'a': '𝐚', 'b': '𝐛', 'c': '𝐜', 'd': '𝐝', 'e': '𝐞', 'f': '𝐟', 'g': '𝐠', 'h': '𝐡', 'i': '𝐢',
        'j': '𝐣', 'k': '𝐤', 'l': '𝐥', 'm': '𝐦', 'n': '𝐧', 'o': '𝐨', 'p': '𝐩', 'q': '𝐪', 'r': '𝐫',
        's': '𝐬', 't': '𝐭', 'u': '𝐮', 'v': '𝐯', 'w': '𝐰', 'x': '𝐱', 'y': '𝐲', 'z': '𝐳',
        '0': '𝟎', '1': '𝟏', '2': '𝟐', '3': '𝟑', '4': '𝟒', '5': '𝟓', '6': '𝟔', '7': '𝟕', '8': '𝟖', '9': '𝟗'
    }
    return ''.join(bold_map.get(c, c) for c in text)

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>𝐑𝐒 𝐇𝐅 𝐑𝐎𝐔𝐓𝐄𝐑</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    background: #0a0a0a;
    font-family: monospace;
    padding: 20px;
    min-height: 100vh;
  }
  .container { max-width: 900px; margin: 0 auto; }
  
  .header {
    text-align: center;
    padding: 30px 20px;
    border-bottom: 2px solid #ff4500;
    margin-bottom: 30px;
  }
  .header h1 {
    font-size: 2rem;
    background: linear-gradient(135deg, #ff4500, #ff8c00);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin-bottom: 10px;
  }
  .header p { color: #888; font-size: 0.9rem; }
  
  .card {
    background: #111;
    border: 1px solid #222;
    border-radius: 16px;
    padding: 24px;
    margin-bottom: 20px;
  }
  .card h2 {
    color: #ff8c00;
    font-size: 1.2rem;
    margin-bottom: 16px;
    display: flex;
    align-items: center;
    gap: 8px;
  }
  
  input {
    width: 100%;
    padding: 14px;
    background: #1a1a1a;
    border: 1px solid #333;
    border-radius: 10px;
    color: #fff;
    font-size: 0.9rem;
    margin-bottom: 12px;
  }
  input:focus { outline: none; border-color: #ff4500; }
  
  button {
    padding: 12px 24px;
    background: linear-gradient(135deg, #ff4500, #ff8c00);
    border: none;
    border-radius: 10px;
    color: #fff;
    font-weight: bold;
    cursor: pointer;
    margin-right: 10px;
  }
  button:hover { opacity: 0.85; }
  .btn-secondary { background: #222; border: 1px solid #444; }
  
  .result {
    background: #1a1a1a;
    border-radius: 10px;
    padding: 16px;
    margin-top: 16px;
    display: none;
    word-break: break-all;
  }
  .result.show { display: block; }
  .result.success { border-left: 4px solid #00e676; }
  .result.error { border-left: 4px solid #ff1744; }
  
  .files-list {
    margin-top: 16px;
    list-style: none;
  }
  .files-list li {
    background: #1a1a1a;
    border: 1px solid #333;
    border-radius: 8px;
    padding: 12px;
    margin-bottom: 8px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
  }
  .files-list a {
    color: #ff8c00;
    text-decoration: none;
  }
  
  .loader {
    display: none;
    margin-top: 12px;
    color: #888;
  }
  .loader.show { display: block; }
  .spinner {
    display: inline-block;
    width: 18px;
    height: 18px;
    border: 2px solid #333;
    border-top-color: #ff4500;
    border-radius: 50%;
    animation: spin 0.6s linear infinite;
    vertical-align: middle;
    margin-right: 8px;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
  
  .footer {
    text-align: center;
    padding: 24px;
    color: #555;
    font-size: 0.8rem;
    border-top: 1px solid #222;
    margin-top: 20px;
  }
  .footer a { color: #ff8c00; text-decoration: none; }
</style>
</head>
<body>

<div class="container">
  <div class="header">
    <h1>𝐑𝐒 𝐇𝐅 𝐑𝐎𝐔𝐓𝐄𝐑</h1>
    <p>𝐇𝐮𝐠𝐠𝐢𝐧𝐠𝐅𝐚𝐜𝐞 𝐃𝐢𝐫𝐞𝐜𝐭 𝐋𝐢𝐧𝐤 𝐆𝐞𝐧𝐞𝐫𝐚𝐭𝐨𝐫</p>
  </div>

  <div class="card">
    <h2>🔗 𝐆𝐄𝐓 𝐃𝐈𝐑𝐄𝐂𝐓 𝐋𝐈𝐍𝐊</h2>
    <input type="text" id="inputUrl" placeholder="https://huggingface.co/owner/repo/resolve/main/file.xyz">
    <button onclick="getDirectLink()">𝐆𝐄𝐓 𝐋𝐈𝐍𝐊</button>
    <button class="btn-secondary" onclick="copyLink()">𝐂𝐎𝐏𝐘</button>
    <div class="loader" id="loader"><span class="spinner"></span> 𝐏𝐫𝐨𝐜𝐞𝐬𝐬𝐢𝐧𝐠...</div>
    <div class="result" id="result"></div>
  </div>

  <div class="card">
    <h2>📁 𝐇𝐅 𝐑𝐄𝐏𝐎 𝐅𝐈𝐋𝐄𝐒</h2>
    <input type="text" id="repoInput" placeholder="owner/repo (e.g. stabilityai/stable-diffusion)">
    <button onclick="getRepoFiles()">𝐋𝐈𝐒𝐓 𝐅𝐈𝐋𝐄𝐒</button>
    <div class="loader" id="repoLoader"><span class="spinner"></span> 𝐅𝐞𝐭𝐜𝐡𝐢𝐧𝐠...</div>
    <ul class="files-list" id="filesList"></ul>
  </div>

  <div class="card">
    <h2>📌 𝐇𝐎𝐖 𝐓𝐎 𝐔𝐒𝐄</h2>
    <div style="color:#888; line-height:1.8;">
      ┣⪼ <b>𝐃𝐢𝐫𝐞𝐜𝐭 𝐋𝐢𝐧𝐤</b> - 𝐏𝐚𝐬𝐭𝐞 𝐇𝐅 𝐟𝐢𝐥𝐞 𝐔𝐑𝐋, 𝐠𝐞𝐭 𝐯𝐚𝐥𝐢𝐝 𝐥𝐢𝐧𝐤<br>
      ┣⪼ <b>𝐑𝐞𝐩𝐨 𝐅𝐢𝐥𝐞𝐬</b> - 𝐄𝐧𝐭𝐞𝐫 <code>𝐨𝐰𝐧𝐞𝐫/𝐫𝐞𝐩𝐨</code> 𝐭𝐨 𝐬𝐞𝐞 𝐚𝐥𝐥 𝐟𝐢𝐥𝐞𝐬<br>
      ┣⪼ <b>𝐁𝐨𝐭 𝐔𝐬𝐚𝐠𝐞</b> - 𝐒𝐞𝐧𝐝 𝐭𝐡𝐞 𝐝𝐢𝐫𝐞𝐜𝐭 𝐥𝐢𝐧𝐤 𝐭𝐨 <b>@RS_URL_UPLOADER_BOT</b><br>
      ┗⪼ <b>𝐍𝐨 𝐭𝐨𝐤𝐞𝐧 𝐧𝐞𝐞𝐝𝐞𝐝</b> - 𝐖𝐨𝐫𝐤𝐬 𝐟𝐨𝐫 𝐩𝐮𝐛𝐥𝐢𝐜 𝐟𝐢𝐥𝐞𝐬
    </div>
  </div>

  <div class="footer">
    😈 <b>𝐏𝐨𝐰𝐞𝐫𝐞𝐝 𝐛𝐲 @𝐑𝐒_𝐖𝐎𝐍𝐄𝐑</b> | <a href="https://t.me/RS_URL_UPLOADER_BOT" target="_blank">@RS_URL_UPLOADER_BOT</a>
  </div>
</div>

<script>
async function getDirectLink() {
  let url = document.getElementById('inputUrl').value.trim();
  if (!url) return;
  const result = document.getElementById('result');
  const loader = document.getElementById('loader');
  result.className = 'result';
  result.innerHTML = '';
  loader.classList.add('show');
  
  try {
    const resp = await fetch('/api/check', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({url: url})
    });
    const data = await resp.json();
    loader.classList.remove('show');
    
    if (data.ok) {
      result.className = 'result show success';
      result.innerHTML = '✅ <b>𝐕𝐀𝐋𝐈𝐃 𝐋𝐈𝐍𝐊</b><br><br>📦 <b>𝐒𝐢𝐳𝐞:</b> ' + data.size + '<br>📄 <b>𝐓𝐲𝐩𝐞:</b> ' + data.type + '<br><br><a href="' + data.final_url + '" target="_blank" style="color:#ff8c00">🔗 ' + data.final_url + '</a>';
    } else {
      result.className = 'result show error';
      result.innerHTML = '❌ <b>𝐈𝐍𝐕𝐀𝐋𝐈𝐃 𝐋𝐈𝐍𝐊</b><br><br>' + (data.error || '𝐔𝐑𝐋 𝐧𝐨𝐭 𝐚𝐜𝐜𝐞𝐬𝐬𝐢𝐛𝐥𝐞');
    }
  } catch(e) {
    loader.classList.remove('show');
    result.className = 'result show error';
    result.innerHTML = '❌ <b>𝐄𝐑𝐑𝐎𝐑</b><br><br>' + e.message;
  }
}

async function getRepoFiles() {
  let repo = document.getElementById('repoInput').value.trim();
  if (!repo) return;
  const filesList = document.getElementById('filesList');
  const loader = document.getElementById('repoLoader');
  filesList.innerHTML = '';
  loader.classList.add('show');
  
  try {
    const resp = await fetch('/api/files', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({repo: repo})
    });
    const data = await resp.json();
    loader.classList.remove('show');
    
    if (data.error) {
      filesList.innerHTML = '<li style="color:#ff1744">❌ ' + data.error + '</li>';
      return;
    }
    
    if (data.files && data.files.length > 0) {
      for (let f of data.files) {
        let li = document.createElement('li');
        li.innerHTML = '<span>📄 <b>' + f.name + '</b></span><span style="color:#888">' + f.size + '</span><a href="' + f.url + '" target="_blank">⬇️ 𝐃𝐨𝐰𝐧𝐥𝐨𝐚𝐝</a>';
        filesList.appendChild(li);
      }
    } else {
      filesList.innerHTML = '<li>📂 𝐍𝐨 𝐟𝐢𝐥𝐞𝐬 𝐟𝐨𝐮𝐧𝐝</li>';
    }
  } catch(e) {
    loader.classList.remove('show');
    filesList.innerHTML = '<li style="color:#ff1744">❌ ' + e.message + '</li>';
  }
}

function copyLink() {
  let url = document.getElementById('inputUrl').value.trim();
  if (!url) return;
  navigator.clipboard.writeText(url).then(() => {
    let btn = document.querySelector('.btn-secondary');
    let old = btn.innerHTML;
    btn.innerHTML = '✅ 𝐂𝐎𝐏𝐈𝐄𝐃!';
    setTimeout(() => btn.innerHTML = old, 1500);
  });
}
</script>
</body>
</html>
"""

async def index(request):
    return web.Response(text=HTML, content_type='text/html')

async def api_check(request):
    try:
        body = await request.json()
        url = body.get('url', '').strip()
        if not url:
            return web.json_response({'ok': False, 'error': 'No URL provided'})
        
        async with aiohttp.ClientSession() as session:
            async with session.head(url, allow_redirects=True, timeout=15) as resp:
                if resp.status in (200, 206):
                    size = resp.headers.get('Content-Length', '0')
                    ctype = resp.headers.get('Content-Type', 'unknown')
                    
                    def hb(s):
                        try:
                            s = int(s)
                            for u in ['B', 'KB', 'MB', 'GB']:
                                if s < 1024:
                                    return f"{s:.1f} {u}"
                                s /= 1024
                            return f"{s:.1f} TB"
                        except:
                            return 'Unknown'
                    
                    return web.json_response({
                        'ok': True,
                        'size': hb(size),
                        'type': ctype.split('/')[-1] if '/' in ctype else ctype,
                        'final_url': str(resp.url)
                    })
                else:
                    return web.json_response({'ok': False, 'error': f'HTTP {resp.status}'})
    except asyncio.TimeoutError:
        return web.json_response({'ok': False, 'error': 'Timeout'})
    except Exception as e:
        return web.json_response({'ok': False, 'error': str(e)})

async def api_files(request):
    try:
        body = await request.json()
        repo = body.get('repo', '').strip()
        if not repo or '/' not in repo:
            return web.json_response({'error': 'Invalid format. Use: owner/repo'})
        
        owner, name = repo.split('/', 1)
        api_url = f'https://huggingface.co/api/models/{owner}/{name}'
        
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, timeout=20) as resp:
                if resp.status != 200:
                    return web.json_response({'error': f'Repo not found (HTTP {resp.status})'})
                data = await resp.json()
        
        siblings = data.get('siblings', [])
        files = []
        for s in siblings:
            fname = s.get('rfilename', '')
            if not fname:
                continue
            size = s.get('size', 0)
            def hb(s):
                s = int(s) if s else 0
                for u in ['B', 'KB', 'MB', 'GB']:
                    if s < 1024:
                        return f"{s:.1f} {u}"
                    s /= 1024
                return f"{s:.1f} TB"
            files.append({
                'name': fname,
                'size': hb(size),
                'url': f'https://huggingface.co/{repo}/resolve/main/{fname}'
            })
        
        return web.json_response({'files': files[:50]})
    except Exception as e:
        return web.json_response({'error': str(e)})

def create_app():
    app = web.Application()
    app.router.add_get('/', index)
    app.router.add_post('/api/check', api_check)
    app.router.add_post('/api/files', api_files)
    return app

if __name__ == '__main__':
    print(f'🚀 RS HF Router running on port {PORT}')
    web.run_app(create_app(), host='0.0.0.0', port=PORT)