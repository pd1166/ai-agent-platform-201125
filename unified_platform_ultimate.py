# unified_platform_ultimate.py
# 🚀 AI Agent Platform Ultimate - V16.0 (Refined Architecture: Retry, Context Window, Dynamic Config)
# =================================================================================================

import streamlit as st
import os
import json
import time
import sqlite3
import math
import requests
import pandas as pd
from datetime import datetime
from openai import OpenAI
import hashlib
from typing import Dict, List, Optional, Any
import logging

# ================== SYSTEM CONFIG ==================
st.set_page_config(
    page_title="AI Enterprise V16",
    page_icon="💎",
    layout="wide",
    initial_sidebar_state="expanded"
)

logging.basicConfig(level=logging.INFO)

try:
    SYSTEM_API_KEY = st.secrets["OPENAI_API_KEY"]
except:
    st.error("❌ Critical Error: Missing OPENAI_API_KEY in secrets.toml")
    st.stop()

OWNER_EMAIL = "pompdany@gmail.com"
MAX_CONTEXT_HISTORY = 20  # Sliding window size (Last N messages)

# ================== UI STYLING (RTL) ==================
def setup_rtl():
    st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Heebo:wght@400;500;700&display=swap');
        html, body, [class*="css"] { font-family: 'Heebo', sans-serif; direction: rtl; text-align: right; }
        .stTextInput, .stTextArea, .stSelectbox, input, textarea { direction: rtl; text-align: right; }
        .stChatMessage { direction: rtl; text-align: right; }
        p, div, label, h1, h2, h3 { text-align: right !important; }
        code, pre { direction: ltr !important; text-align: left !important; }
        section[data-testid="stSidebar"] { direction: rtl; }
        
        .agent-badge {
            padding: 5px 10px;
            border-radius: 15px;
            background-color: #e0e0e0;
            color: #333;
            font-size: 0.8em;
            margin-left: 5px;
        }
    </style>
    """, unsafe_allow_html=True)

# ================== DATABASE LAYER ==================
DB_FILE = "agents_platform_v16.db"

def init_db():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (email TEXT PRIMARY KEY, plan TEXT, agents_created INTEGER, is_approved BOOLEAN)''')
    c.execute('''CREATE TABLE IF NOT EXISTS agents
                 (id TEXT PRIMARY KEY, creator TEXT, name TEXT, config TEXT, created_at TEXT, secrets TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS messages
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, agent_id TEXT, user_email TEXT, role TEXT, content TEXT, timestamp TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS tasks
                 (id INTEGER PRIMARY KEY, agent_id TEXT, task_desc TEXT, status TEXT, created_at TEXT)''')
    conn.commit()
    conn.close()

def get_db_connection():
    return sqlite3.connect(DB_FILE, check_same_thread=False)

init_db()

# ================== UTILS & LOGIC ==================
def safe_json_loads(json_str):
    if not json_str: return {}
    if isinstance(json_str, dict): return json_str
    try: return json.loads(json_str)
    except:
        try: return json.loads(json_str.replace("'", '"'))
        except: return {}

def get_user_status(email):
    conn = get_db_connection()
    user = conn.execute("SELECT plan, is_approved, agents_created FROM users WHERE email=?", (email,)).fetchone()
    conn.close()
    if not user: return None
    return {"plan": user[0], "is_approved": bool(user[1]), "agents_created": user[2]}

def load_chat_history(agent_id, limit=50):
    """Load history from DB"""
    conn = get_db_connection()
    rows = conn.execute("SELECT role, content FROM messages WHERE agent_id=? ORDER BY id ASC LIMIT ?", (agent_id, limit)).fetchall()
    conn.close()
    return [{"role": r[0], "content": r[1]} for r in rows]

def save_message(agent_id, user_email, role, content):
    conn = get_db_connection()
    conn.execute("INSERT INTO messages (agent_id, user_email, role, content, timestamp) VALUES (?, ?, ?, ?, ?)",
                (agent_id, user_email, role, content, datetime.now().isoformat()))
    conn.commit()
    conn.close()

# ================== ROBUST TOOL REGISTRY ==================
class ToolRegistry:
    
    @staticmethod
    def get_definitions():
        """Dynamic Discovery of available tools"""
        return [
            {"type": "function", "function": {"name": "get_current_time", "description": "Get server time."}},
            {"type": "function", "function": {"name": "make_http_request", "description": "Robust HTTP Client (GET/POST) with retry logic.", 
             "parameters": {"type": "object", "properties": {"url": {"type": "string"}, "method": {"type": "string"}, "headers": {"type": "string"}, "data": {"type": "string"}}, "required": ["url", "method"]}}},
            {"type": "function", "function": {"name": "manage_task", "description": "Task Memory System.", 
             "parameters": {"type": "object", "properties": {"action": {"type": "string", "enum": ["add", "complete"]}, "description": {"type": "string"}}, "required": ["action", "description"]}}},
            {"type": "function", "function": {"name": "create_new_agent", "description": "Builder Tool. Supports temperature and icon customization.", 
             "parameters": {"type": "object", "properties": {
                 "name": {"type": "string"}, 
                 "personality": {"type": "string"}, 
                 "goal": {"type": "string"}, 
                 "tools_needed": {"type": "string"}, 
                 "api_secrets": {"type": "string"},
                 "temperature": {"type": "number", "description": "0.0-1.0 (0=Strict, 1=Creative)"},
                 "icon": {"type": "string", "description": "An emoji representing the agent"}
             }, "required": ["name", "personality"]}}}
        ]

    @staticmethod
    def execute_tool(name, args, user_email, agent_id=None):
        
        # --- 1. Time Tool ---
        if name == "get_current_time":
            return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
        # --- 2. HTTP Tool with RETRY Logic ---
        elif name == "make_http_request":
            url = args.get('url')
            method = args.get('method', 'GET')
            headers = safe_json_loads(args.get('headers'))
            data = safe_json_loads(args.get('data'))
            
            # Smart Retry Loop
            for attempt in range(3):
                try:
                    resp = requests.request(method, url, headers=headers, json=data, timeout=15)
                    return f"HTTP {resp.status_code}: {resp.text[:1000]}"
                except Exception as e:
                    if attempt == 2: # Last attempt
                        return f"HTTP Failed after 3 retries. Error: {str(e)}"
                    time.sleep(2) # Wait before retry
            
        # --- 3. Task Memory ---
        elif name == "manage_task":
            conn = get_db_connection()
            if args['action'] == 'add':
                conn.execute("INSERT INTO tasks (agent_id, task_desc, status, created_at) VALUES (?, ?, 'open', ?)", 
                            (agent_id, args['description'], datetime.now().isoformat()))
                res = "Task added to memory."
            else:
                conn.execute("UPDATE tasks SET status='done' WHERE agent_id=? AND task_desc LIKE ?", 
                            (agent_id, f"%{args['description']}%"))
                res = "Task marked as done."
            conn.commit()
            conn.close()
            return res

        # --- 4. Agent Builder with Dynamic Config ---
        elif name == "create_new_agent":
            tools_text = args.get('tools_needed', '').lower()
            final_tools = ["manage_task"] # Default memory
            
            # Intelligent Mapping
            if "http" in tools_text or "api" in tools_text or "web" in tools_text: final_tools.append("make_http_request")
            if "time" in tools_text or "date" in tools_text: final_tools.append("get_current_time")
            
            # Configuration
            temp = float(args.get('temperature', 0.5))
            icon = args.get('icon', '🤖')
            
            # Hardened Kernel Prompt
            kernel = f"{args['personality']}\n\n[SYSTEM KERNEL]: You are an EXECUTION ENGINE. Use tools ('make_http_request') for ALL external data. Do not hallucinate. Use secrets provided in context."
            
            cfg = {
                "name": args['name'], "personality": kernel, "goal": args['goal'], 
                "enabled_tools": final_tools, "model": "gpt-4o-mini", 
                "temperature": temp, "icon": icon
            }
            
            conn = get_db_connection()
            aid = hashlib.md5(f"{args['name']}{time.time()}".encode()).hexdigest()[:10]
            conn.execute("INSERT OR REPLACE INTO agents VALUES (?, ?, ?, ?, ?, ?)",
                     (aid, user_email, args['name'], json.dumps(cfg), datetime.now().isoformat(), args.get('api_secrets', '{}')))
            conn.execute("UPDATE users SET agents_created = agents_created + 1 WHERE email=?", (user_email,))
            conn.commit()
            conn.close()
            
            # Auto-Welcome
            initial_msg = f"שלום! אני {args['name']} {icon}. הוגדרתי לעבודה בטמפרטורה {temp}. אני מוכן!"
            save_message(aid, user_email, "assistant", initial_msg)
            
            return f"SUCCESS: Agent '{args['name']}' created."
            
        return "Unknown Tool"

# ================== RUN ENGINE (SLIDING WINDOW) ==================
def run_agent_loop(agent_config, full_history, user_msg, user_email, agent_id):
    client = OpenAI(api_key=SYSTEM_API_KEY)
    
    # 1. Save User Msg
    save_message(agent_id, user_email, "user", user_msg)
    
    # 2. Prepare Context (Sliding Window)
    # We create a temporary list for this run, not modifying the display history
    context_messages = []
    
    # A. System Prompt (Always First)
    secrets = agent_config.get('secrets', '')
    sys_content = f"{agent_config['personality']}\nGoal: {agent_config['goal']}"
    if secrets and secrets != "{}": sys_content += f"\n[SECRETS]: {secrets}"
    
    conn = get_db_connection()
    tasks = conn.execute("SELECT task_desc FROM tasks WHERE agent_id=? AND status='open'", (agent_id,)).fetchall()
    conn.close()
    if tasks: sys_content += f"\n[TASKS]: {', '.join([t[0] for t in tasks])}"
    
    context_messages.append({"role": "system", "content": sys_content})
    
    # B. Sliding Window (Last N messages only)
    # Convert full_history to API format and slice
    recent_history = full_history[-MAX_CONTEXT_HISTORY:]
    context_messages.extend(recent_history)
    
    # C. Current User Msg
    context_messages.append({"role": "user", "content": user_msg})

    # 3. Tool Setup
    enabled = agent_config.get('enabled_tools', [])
    all_tools = ToolRegistry.get_definitions()
    active_tools = [t for t in all_tools if t['function']['name'] in enabled]
    if not active_tools: active_tools = None

    # 4. Execution Loop
    steps = 0
    final_response = ""
    
    with st.spinner("🤖 עובד..."):
        while steps < 5:
            steps += 1
            
            try:
                response = client.chat.completions.create(
                    model=agent_config.get('model', 'gpt-4o-mini'),
                    messages=context_messages,
                    tools=active_tools,
                    tool_choice="auto" if active_tools else None,
                    temperature=agent_config.get('temperature', 0.5) # Use dynamic temp
                )
            except Exception as e:
                return f"OpenAI Error: {str(e)}"

            msg = response.choices[0].message
            context_messages.append(msg) # Add to immediate context
            
            if msg.tool_calls:
                for tool in msg.tool_calls:
                    func_name = tool.function.name
                    args = safe_json_loads(tool.function.arguments)
                    
                    with st.status(f"⚙️ מפעיל: {func_name}", expanded=True) as s:
                        result = ToolRegistry.execute_tool(func_name, args, user_email, agent_id)
                        st.write(result)
                        s.update(label=f"✅ בוצע: {func_name}", state="complete")
                    
                    context_messages.append({"role": "tool", "tool_call_id": tool.id, "content": str(result)})
            else:
                final_response = msg.content
                break
    
    # 5. Save Final Response to DB
    save_message(agent_id, user_email, "assistant", final_response)
    return final_response

# ================== UI ==================
def main():
    setup_rtl()
    
    with st.sidebar:
        st.title("V16.0 Enterprise")
        email = st.text_input("Email", value=st.session_state.get('user_email','')).strip().lower()
        
        if email:
            st.session_state.user_email = email
            conn = get_db_connection()
            if email == OWNER_EMAIL:
                if not conn.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
                    conn.execute("INSERT INTO users VALUES (?, 'vip', 0, ?, 1)", (email, datetime.now().isoformat()))
                else:
                    conn.execute("UPDATE users SET is_approved=1, plan='vip' WHERE email=?", (email,))
                conn.commit()
            
            user = conn.execute("SELECT is_approved, plan FROM users WHERE email=?", (email,)).fetchone()
            conn.close()
            
            if user and user[0]:
                st.success(f"מחובר: {user[1]}")
                st.divider()
                menu = ["🏠 בית", "🤖 בונה הסוכנים", "💬 חדר עבודה"]
                if email == OWNER_EMAIL: menu.append("👑 ניהול")
                st.session_state.page = st.radio("תפריט", menu)
            else:
                st.warning("ממתין לאישור")
                st.stop()

    if 'page' not in st.session_state: st.session_state.page = "🏠 בית"

    if st.session_state.page == "🏠 בית":
        st.title("מערכת ניהול סוכנים")
        st.markdown("### חדש בגרסה 16.0\n- חלון זיכרון חכם (מונע קריסות)\n- הגדרת יצירתיות (Temperature)\n- אייקונים מותאמים\n- מנגנון Retry ליציבות")

    elif st.session_state.page == "👑 ניהול":
        if st.session_state.user_email == OWNER_EMAIL:
            st.title("ניהול")
            conn = get_db_connection()
            df = pd.read_sql_query("SELECT * FROM users", conn)
            st.data_editor(df)
            conn.close()

    elif st.session_state.page == "🤖 בונה הסוכנים":
        st.title("🤖 הארכיטקט")
        
        builder = {
            "name": "Architect", 
            "personality": """You are an expert AI Architect. 
            PROTOCOL:
            1. Ask for API Keys if integrations are needed.
            2. When calling 'create_new_agent', decide on a 'temperature' (0.2 for logic/data, 0.8 for creative/writing).
            3. Choose a relevant 'icon' emoji.
            4. Ensure correct tools are mapped.""", 
            "goal": "Build agents", 
            "enabled_tools": ["create_new_agent"], 
            "model": "gpt-4o"
        }
        
        if "builder_log" not in st.session_state: st.session_state.builder_log = []
        for m in st.session_state.builder_log:
            with st.chat_message(m["role"]): st.markdown(m["content"])
            
        if p := st.chat_input("מה לבנות?"):
            run_agent_loop(builder, st.session_state.builder_log, p, st.session_state.user_email, "BUILDER_ID")
            st.rerun()

    elif st.session_state.page == "💬 חדר עבודה":
        st.title("💬 חדר עבודה")
        agents = get_user_agents(st.session_state.user_email)
        
        if not agents: 
            st.info("אין סוכנים.")
        else:
            aid = st.selectbox("בחר סוכן:", list(agents.keys()), format_func=lambda x: f"{agents[x]['icon']} {agents[x]['name']}")
            agent = agents[aid]
            
            # Info Bar
            st.info(f"**אישיות:** {agent['name']} | **טמפרטורה:** {agent.get('temperature', 0.5)} | **כלים:** {len(agent.get('enabled_tools', []))}")
            
            chat_history = load_chat_history(aid)
            for m in chat_history:
                with st.chat_message(m["role"]): st.markdown(m["content"])
                
            if p := st.chat_input():
                run_agent_loop(agent, chat_history, p, st.session_state.user_email, aid)
                st.rerun()

if __name__ == "__main__":
    main()
