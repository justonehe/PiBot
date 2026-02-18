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
VOLC_API_KEY = "bada174e-cad9-4a2e-9e0c-ab3b57cec669"
VOLC_BASE_URL = "https://ark.cn-beijing.volces.com/api/coding/v3"
MODEL_NAME = "doubao-seed-code"

WORKER_IP = "192.168.10.66"
WORKER_USER = "justone"
INBOX_REMOTE = "~/inbox"
OUTBOX_REMOTE = "~/outbox"

# ----------------- Memory -----------------
TAPE_FILE = Path("memory.jsonl")

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

# ----------------- Helpers -----------------
def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"

def get_weather():
    try:
        res = requests.get("https://wttr.in/Shanghai?format=%c+%t", timeout=2)
        if res.status_code == 200:
            return res.text.strip()
    except:
        pass
    return "⛅️ 25°C"

# ----------------- Worker -----------------
def dispatch_task(cmd):
    task_id = f"task-{int(time.time())}"
    task_payload = {
        "id": task_id,
        "cmd": cmd,
        "ts": time.time()
    }
    local_file = f"/tmp/{task_id}.json"
    with open(local_file, "w") as f:
        json.dump(task_payload, f)
    
    logging.info(f"Dispatching task {task_id} to Worker...")
    scp_cmd = f"scp -o StrictHostKeyChecking=no {local_file} {WORKER_USER}@{WORKER_IP}:{INBOX_REMOTE}/{task_id}.json"
    subprocess.run(scp_cmd, shell=True)
    return {"status": "dispatched", "id": task_id}

def check_task_result(task_id):
    remote_file = f"{OUTBOX_REMOTE}/{task_id}.json.result"
    local_res = f"/tmp/{task_id}.result"
    scp_cmd = f"scp -o StrictHostKeyChecking=no {WORKER_USER}@{WORKER_IP}:{remote_file} {local_res}"
    res = subprocess.run(scp_cmd, shell=True, capture_output=True)
    if res.returncode == 0 and os.path.exists(local_res):
        with open(local_res, "r") as f:
            return json.load(f)
    return None

# ----------------- LLM -----------------
client = OpenAI(api_key=VOLC_API_KEY, base_url=VOLC_BASE_URL)

def ask_llm(user_input):
    history = read_tape(10)
    messages = [{"role": "system", "content": "你是 Master Agent。你的职责是理解用户意图。\n能够闲聊，也能指挥 Worker。\n如果用户要求执行 Shell 命令、下载、系统操作，请输出特殊标记：\n<call_worker>COMMAND</call_worker>\n例如：<call_worker>ping baidu.com</call_worker>"}]
    for h in history:
        messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": user_input})
    try:
        completion = client.chat.completions.create(model=MODEL_NAME, messages=messages)
        return completion.choices[0].message.content
    except Exception as e:
        return f"Error: {str(e)}"

# ----------------- Flask -----------------
app = Flask(__name__)

# --- Shared JS ---
COMMON_SCRIPT = """
    <script>
        window.onerror = function(msg, source, lineno) { console.error("JS Error: " + msg + " line " + lineno); }
        document.addEventListener("DOMContentLoaded", function() {
            const input = document.getElementById('msg-input');
            const btn = document.getElementById('send-btn');
            const chat = document.getElementById('chat-container');

            async function sendMsg() {
                const txt = input.value.trim();
                if(!txt) return;
                input.value = '';
                try {
                    await fetch('/api/chat', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({msg: txt})
                    });
                } catch(e) { alert('Send failed: ' + e); }
            }
            if(btn && input) {
                btn.onclick = sendMsg;
                input.onkeypress = (e) => { if(e.key === 'Enter') sendMsg(); };
            }

            let lastId = 0;
            async function syncChat() {
                try {
                    const res = await fetch('/api/history?since=' + lastId);
                    if(!res.ok) return;
                    const entries = await res.json();
                    let scrolled = false;
                    entries.forEach(entry => {
                        if(entry.id <= lastId) return;
                        lastId = entry.id;
                        let cls = 'sys';
                        if(entry.role === 'user') cls = 'user';
                        if(entry.role === 'assistant') cls = 'ai';
                        chat.innerHTML += `<div class="msg ${cls}">${entry.content}</div>`;
                        scrolled = true;
                    });
                    if(scrolled) chat.scrollTop = chat.scrollHeight;
                } catch(e) {}
            }
            setInterval(syncChat, 2000);
            syncChat();
        });
    </script>
"""

# --- Desktop Template ---
DESKTOP_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>PiBot Master</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js"></script>
    <style>
        :root { --bg-color: #f2f2f7; --card-bg: #ffffff; --accent: #007aff; --text-main: #1c1c1e; --text-dim: #8e8e93; --shadow: 0 4px 12px rgba(0,0,0,0.05); }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Inter', sans-serif; background: var(--bg-color); color: var(--text-main); margin: 0; padding: 24px; height: 100vh; display: grid; grid-template-columns: 280px 1fr; gap: 24px; box-sizing: border-box; overflow: hidden; }
        aside { display: flex; flex-direction: column; gap: 20px; height: 100%; }
        .widget { background: var(--card-bg); padding: 20px; border-radius: 18px; box-shadow: var(--shadow); }
        #clock-card { text-align: center; padding: 30px 20px; }
        #clock-card h1 { font-size: 3.5em; margin: 0; font-weight: 600; line-height: 1; }
        #clock-card p { font-size: 1em; color: var(--text-dim); margin: 8px 0 0 0; text-transform: uppercase; }
        #weather-card { text-align: center; font-size: 1.3em; font-weight: 500; }
        #todo-card { flex: 1; overflow-y: auto; }
        #todo-card h3 { margin: 0 0 15px 0; color: var(--text-dim); font-size: 0.8em; text-transform: uppercase; }
        #todo-list { list-style: none; padding: 0; margin: 0; }
        #todo-list li { padding: 10px 0; border-bottom: 1px solid #f0f0f0; display: flex; align-items: center; gap: 10px; font-size: 0.95em; }
        #todo-list li::before { content: ""; display: inline-block; width: 8px; height: 8px; border-radius: 50%; border: 2px solid var(--accent); }
        #qr-card { display: flex; flex-direction: column; align-items: center; gap: 10px; text-align: center; }
        #net-info { font-size: 0.85em; color: var(--text-dim); font-family: monospace; }
        
        main { background: var(--card-bg); border-radius: 24px; padding: 24px; box-shadow: var(--shadow); display: flex; flex-direction: column; overflow: hidden; }
        #chat-container { flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 16px; padding-bottom: 20px; }
        #input-area { display: flex; gap: 12px; padding-top: 16px; border-top: 1px solid #f0f0f0; }
        #msg-input { flex: 1; padding: 14px; border-radius: 12px; border: 1px solid #e5e5ea; background: #f9f9f9; font-size: 1em; outline: none; }
        #msg-input:focus { border-color: var(--accent); background: #fff; }
        #send-btn { background: var(--accent); color: #fff; border: none; padding: 0 24px; border-radius: 12px; font-weight: 600; cursor: pointer; }
        
        .msg { padding: 12px 18px; border-radius: 16px; max-width: 75%; line-height: 1.5; position: relative; }
        .user { align-self: flex-end; background: var(--accent); color: #fff; border-bottom-right-radius: 4px; }
        .ai { align-self: flex-start; background: #f2f2f7; color: var(--text-main); border-bottom-left-radius: 4px; }
        .sys { align-self: center; color: var(--text-dim); font-size: 0.85em; background: rgba(0,0,0,0.03); padding: 4px 12px; border-radius: 100px; }
    </style>
</head>
<body>
    <aside>
        <div id="clock-card" class="widget">
            <h1 id="time">00:00</h1>
            <p id="date">JAN 1</p>
        </div>
        <div id="weather-card" class="widget">
            <span id="weather-icon">Loading...</span>
        </div>
        <div id="todo-card" class="widget">
            <h3>Tasks</h3>
            <ul id="todo-list">
                <li>System Monitor</li>
                <li>Worker Node Status</li>
            </ul>
        </div>
        <div id="qr-card" class="widget">
            <div id="qrcode"></div>
            <div id="net-info">Scanning this Code<br>Opens Mobile Control</div>
        </div>
    </aside>
    <main>
        <div id="chat-container"><div class="msg sys">System Online</div></div>
        <div id="input-area">
            <input type="text" id="msg-input" placeholder="Desktop Control..." autocomplete="off">
            <button id="send-btn">Send</button>
        </div>
    </main>
    <script>
        function updateTime() {
            const now = new Date();
            document.getElementById('time').innerText = now.toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'});
            document.getElementById('date').innerText = now.toLocaleDateString([], {weekday:'short', month:'short', day:'numeric'});
        }
        setInterval(updateTime, 1000); updateTime();
        
        async function updateWeather() {
            try { const r = await fetch('/api/weather'); if(r.ok) document.getElementById('weather-icon').innerText = await r.text(); } catch(e){}
        }
        updateWeather(); setInterval(updateWeather, 600000);

        new QRCode(document.getElementById("qrcode"), { text: "http://{{ host_ip }}:5000/mobile", width: 100, height: 100 });
        
        document.addEventListener('keydown', async (e) => {
            if (e.key === 'Escape') {
                if(confirm('Shutdown Dashboard?')) await fetch('/api/kill');
            }
        });
    </script>
    """ + COMMON_SCRIPT + """
</body>
</html>
"""

# --- Mobile Template ---
MOBILE_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Master Mobile</title>
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
    <style>
        :root { --bg-color: #f2f2f7; --card-bg: #ffffff; --accent: #007aff; --text-main: #1c1c1e; }
        body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: var(--bg-color); margin: 0; height: 100vh; display: flex; flex-direction: column; overflow: hidden; }
        
        header { background: var(--card-bg); padding: 15px; text-align: center; border-bottom: 1px solid #e5e5ea; display: flex; justify-content: space-between; align-items: center; }
        header h1 { margin: 0; font-size: 1.1em; font-weight: 600; }
        #weather-icon { font-size: 0.9em; color: #8e8e93; }

        #chat-container { flex: 1; overflow-y: auto; padding: 15px; display: flex; flex-direction: column; gap: 12px; background: #fff; }
        #input-area { background: #f9f9f9; padding: 10px; border-top: 1px solid #e5e5ea; display: flex; gap: 10px; padding-bottom: max(10px, env(safe-area-inset-bottom)); }
        
        #msg-input { flex: 1; padding: 10px; border-radius: 20px; border: 1px solid #d1d1d6; font-size: 1em; outline: none; }
        #send-btn { background: var(--accent); color: white; border: none; border-radius: 50%; width: 40px; height: 40px; font-weight: bold; cursor: pointer; display: flex; align-items: center; justify-content: center; }
        
        .msg { padding: 10px 14px; border-radius: 18px; max-width: 80%; line-height: 1.4; word-wrap: break-word; }
        .user { align-self: flex-end; background: var(--accent); color: #fff; border-bottom-right-radius: 4px; }
        .ai { align-self: flex-start; background: #e9e9eb; color: #000; border-bottom-left-radius: 4px; }
        .sys { align-self: center; font-size: 0.8em; color: #8e8e93; margin: 5px 0; }
    </style>
</head>
<body>
    <header>
        <h1>Master Control</h1>
        <span id="weather-icon">Waiting...</span>
    </header>
    <div id="chat-container"><div class="msg sys">Connected to Master</div></div>
    <div id="input-area">
        <input type="text" id="msg-input" placeholder="Message..." autocomplete="off">
        <button id="send-btn">↑</button>
    </div>
    <script>
        async function updateWeather() {
            try { const r = await fetch('/api/weather'); if(r.ok) document.getElementById('weather-icon').innerText = await r.text(); } catch(e){}
        }
        updateWeather();
    </script>
    """ + COMMON_SCRIPT + """
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(DESKTOP_TEMPLATE, host_ip=get_local_ip())

@app.route('/mobile')
def mobile():
    return render_template_string(MOBILE_TEMPLATE)

@app.route('/api/weather')
def api_weather():
    return get_weather()

@app.route('/api/history')
def api_history():
    since = int(request.args.get('since', 0))
    all_history = read_tape(20)
    new_entries = [h for h in all_history if h['id'] > since]
    return jsonify(new_entries)

@app.route('/api/kill')
def api_kill():
    subprocess.Popen("pkill -f chromium", shell=True)
    return "Killed"

@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.json
    user_msg = data.get("msg")
    append_to_tape("user", user_msg)
    ai_reply = ask_llm(user_msg)
    
    action_cmd = None
    task_id = None
    if "<call_worker>" in ai_reply:
        start = ai_reply.find("<call_worker>") + 13
        end = ai_reply.find("</call_worker>")
        action_cmd = ai_reply[start:end].strip()
        res = dispatch_task(action_cmd)
        task_id = res.get("id")
        ai_reply = ai_reply.replace(f"<call_worker>{action_cmd}</call_worker>", "")
        ai_reply += f"\n[Task dispatched to Worker: {action_cmd}]"
    
    append_to_tape("assistant", ai_reply)
    return jsonify({"reply": ai_reply, "action": action_cmd, "task_id": task_id})

@app.route('/api/result/<task_id>')
def get_result(task_id):
    res = check_task_result(task_id)
    if res: return jsonify(res)
    return jsonify({"status": "pending"})

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # Enable threading to handle multiple clients (Kiosk + Phone) without blocking
    app.run(host='0.0.0.0', port=5000, threaded=True)
