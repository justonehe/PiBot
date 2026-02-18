import os
import json
import time
import subprocess
import threading
import logging
import socket
import requests
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify, render_template_string
from openai import OpenAI

# ----------------- Configuration -----------------
VOLC_API_KEY = os.environ.get("VOLC_API_KEY", "bada174e-cad9-4a2e-9e0c-ab3b57cec669")
VOLC_BASE_URL = os.environ.get("VOLC_BASE_URL", "https://ark.cn-beijing.volces.com/api/coding/v3")
MODEL_NAME = os.environ.get("MODEL_NAME", "doubao-seed-code")

WORKER_IP = os.environ.get("WORKER_IP", "192.168.10.66")
WORKER_USER = os.environ.get("WORKER_USER", "justone")
INBOX_REMOTE = "~/inbox"
OUTBOX_REMOTE = "~/outbox"

TAPE_FILE = Path("memory.jsonl")

# ----------------- Core Logic -----------------
def append_to_tape(role, content, meta=None):
    entry = {
        "id": int(time.time() * 1000),
        "ts": datetime.now().isoformat(),
        "role": role,
        "content": content,
        "meta": meta or {}
    }
    with open(TAPE_FILE, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry

def read_tape(limit=20):
    if not TAPE_FILE.exists():
        return []
    with open(TAPE_FILE, "r") as f:
        lines = f.readlines()
    entries = []
    for line in lines[-limit:]:
        try:
            entries.append(json.loads(line))
        except:
            pass
    return entries

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"

# ----------------- LLM & Skills -----------------
client = OpenAI(api_key=VOLC_API_KEY, base_url=VOLC_BASE_URL)

def dispatch_task(cmd):
    task_id = f"task-{int(time.time())}"
    task_payload = {"id": task_id, "cmd": cmd, "ts": time.time()}
    local_file = f"/tmp/{task_id}.json"
    with open(local_file, "w") as f:
        json.dump(task_payload, f)
    scp_cmd = f"scp -o StrictHostKeyChecking=no {local_file} {WORKER_USER}@{WORKER_IP}:{INBOX_REMOTE}/{task_id}.json"
    subprocess.run(scp_cmd, shell=True)
    return {"status": "dispatched", "id": task_id}

# ----------------- Flask Web UI -----------------
app = Flask(__name__)

# Template context shared by both Desktop and Mobile
HTML_BASE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
    <title>{{ title }}</title>
    <style>
        :root { --primary: #007aff; --bg: #f2f2f7; --card: #ffffff; --text: #1c1c1e; }
        body { font-family: -apple-system, sans-serif; background: var(--bg); margin: 0; display: flex; flex-direction: column; height: 100vh; color: var(--text); }
        .header { background: var(--card); padding: 15px; border-bottom: 1px solid #ddd; display: flex; justify-content: space-between; align-items: center; }
        #chat-container { flex: 1; overflow-y: auto; padding: 15px; display: flex; flex-direction: column; gap: 10px; background: #fff; }
        .message { padding: 10px 14px; white-space: pre-wrap; border-radius: 18px; max-width: 80%; line-height: 1.4; word-wrap: break-word; font-size: 15px; }
        .user { align-self: flex-end; background: var(--primary); color: #fff; border-bottom-right-radius: 4px; }
        .assistant { align-self: flex-start; background: #e9e9eb; color: #000; border-bottom-left-radius: 4px; }
        .sys { align-self: center; font-size: 0.8em; color: #8e8e93; background: #f0f0f0; padding: 2px 10px; border-radius: 10px; }
        .input-area { padding: 10px; background: var(--card); border-top: 1px solid #ddd; display: flex; gap: 10px; }
        #user-input { flex: 1; padding: 12px; border-radius: 20px; border: 1px solid #ddd; font-size: 16px; outline: none; }
        #send-btn { background: var(--primary); color: white; border: none; padding: 0 15px; border-radius: 20px; font-weight: bold; }
    </style>
</head>
<body>
    <div class="header">
        <span style="font-weight:bold;">🤖 {{ title }}</span>
        <span style="font-size:0.8em; color:gray;">{{ ip }}</span>
    </div>
    <div id="chat-container"></div>
    <div class="input-area">
        <input type="text" id="user-input" placeholder="输入指令..." autocomplete="off">
        <button id="send-btn">发送</button>
    </div>
    <script>
        const chat = document.getElementById('chat-container');
        const input = document.getElementById('user-input');
        const btn = document.getElementById('send-btn');
        let lastUpdate = 0;

        function appendMsg(role, text) {
            const div = document.createElement('div');
            div.className = `message ${role}`;
            
            // Parse Markdown: images, links, bold, code
            let html = text
                .replace(/!\[([^\]]*)\]\(([^)]+)\)/g, (m, alt, src) => `<img src="${src}" alt="${alt}" style="max-width:100%; border-radius:8px; margin:4px 0;">`)
                .replace(/\[([^\]]+)\]\(([^)]+)\)/g, (m, text, url) => `<a href="${url}" target="_blank">${text}</a>`)
                .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
                .replace(/`([^`]+)`/g, '<code style="background:#f0f0f0; padding:2px 6px; border-radius:4px;">$1</code>')

            div.innerHTML = html;
            chat.appendChild(div);
            chat.scrollTop = chat.scrollHeight;
        }

        async function loadHistory() {
            try {
                const res = await fetch('/api/history?t=' + Date.now());
                const data = await res.json();
                if (data.timestamp > lastUpdate) {
                    chat.innerHTML = '';
                    data.history.forEach(m => appendMsg(m.role, m.content));
                    lastUpdate = data.timestamp;
                }
            } catch(e) {}
        }

        async function send() {
            const val = input.value.trim();
            if(!val) return;
            input.value = '';
            appendMsg('user', val);
            try {
                await fetch('/api/chat', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({msg: val})
                });
                setTimeout(loadHistory, 800);
            } catch(e) { alert('Failed'); }
        }

        btn.onclick = send;
        input.onkeypress = (e) => { if(e.key === 'Enter') send(); };
        setInterval(loadHistory, 3000);
        loadHistory();
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_BASE, title="PiBot Desktop", ip=get_local_ip())

@app.route('/mobile')
def mobile():
    return render_template_string(HTML_BASE, title="PiBot Mobile", ip=get_local_ip())

@app.route('/api/history')
def api_history():
    history = read_tape(20)
    ts = os.path.getmtime(TAPE_FILE) if TAPE_FILE.exists() else 0
    return jsonify({"history": history, "timestamp": ts})

@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.json
    user_msg = data.get("msg")
    append_to_tape("user", user_msg)
    
    try:
        from skill_manager import SkillManager
        skill_mgr = SkillManager()
        skill_mgr.load_skills()
        skill_prompt = skill_mgr.get_prompt()
    except Exception as e:
        logging.error(f"Skill error: {e}")
        skill_mgr, skill_prompt = None, ""

    messages = [
        {"role": "system", "content": f"你是 Master Agent。当前技能：\n{skill_prompt}"},
        {"role": "user", "content": user_msg}
    ]
    
    try:
        response = client.chat.completions.create(model=MODEL_NAME, messages=messages)
        ai_reply = response.choices[0].message.content
        
        # Handle Skill Execution
        if "<call_skill>" in ai_reply and skill_mgr:
            start = ai_reply.find("<call_skill>") + 12
            end = ai_reply.find("</call_skill>")
            content = ai_reply[start:end].strip()
            
            if ":" in content:
                skill_name, args = content.split(":", 1)
                result = skill_mgr.execute(skill_name, args)
            else:
                result = skill_mgr.execute(content)
                
            append_to_tape("assistant", f"{ai_reply}\n[Result]: {result}")
            return jsonify({"reply": "executed"})
            
        append_to_tape("assistant", ai_reply)
        return jsonify({"reply": ai_reply})
    except Exception as e:
        return jsonify({"reply": f"Error: {e}"})

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app.run(host='0.0.0.0', port=5000, threaded=True)
