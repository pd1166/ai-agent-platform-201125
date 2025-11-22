# unified_platform_ultimate.py
# 🚀 AI Agent Platform Ultimate - V14.0 (Gold Edition: Auto-Tooling & Robustness)
# ==============================================================================

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
from typing import Dict, List, Optional
import logging

# ================== CONFIGURATION ==================
st.set_page_config(
    page_title="AI Platform V14.0",
    page_icon="💎",
    layout="wide",
    initial_sidebar_state="expanded"
)

logging.basicConfig(level=logging.INFO)

# ================== SECURITY CHECK ==================
try:
    SYSTEM_API_KEY = st.secrets["OPENAI_API_KEY"]
except:
    st.error("❌ CRITICAL: Missing OPENAI_API_KEY in .streamlit/secrets.toml")
    st.stop()

OWNER_EMAIL = "pompdany@gmail.com"

# ================== BUSINESS LIMITS ==================
PLAN_LIMITS = {
    "free": {"agents": 1, "messages": 50},
    "pro": {"agents": 10, "messages": 1000},
    "vip": {"agents": 99999, "messages": 99999}
}

# ================== RTL & UI STYLING ==================
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
    </style>
    """, unsafe_allow_html=True)

# ================== DATABASE LAYER ==================
DB_FILE = "agents_platform_v14.db"

def init_db():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (email TEXT PRIMARY KEY, plan TEXT, agents_created INTEGER, is_approved BOOLEAN)''')
    c.execute('''CREATE TABLE IF NOT EXISTS agents
                 (id TEXT PRIMARY KEY, creator TEXT, name TEXT, config TEXT, created_at TEXT, secrets TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS messages
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, agent_id TEXT, user_email TEXT, role TEXT, content TEXT, timestamp TEXT)''')
    conn.commit()
    conn.close()

def get_db_connection():
    return sqlite3.connect(DB_FILE, check_same_thread=False)

init_db()

# ================== UTILS ==================
def safe_json_loads(json_str):
    if not json_str: return {}
    if isinstance(json_str, dict): return json_str
    try: return json.loads(json_str)
    except:
        try: return json.loads(json_str.replace("'", '"'))
        except: return {}

def check_limits(email, action_type):
    conn = get_db_connection()
    user = conn.execute("SELECT plan, agents_created FROM users WHERE email=?", (email,)).fetchone()
    conn.close()
    if not user: return False, "User not found"
    
    limits = PLAN_LIMITS.get(user[0], PLAN_LIMITS['free'])
    if action_type == 'create_agent' and user[1] >= limits['agents']:
        return False, "Limit reached"
    return True, "OK"

# ================== TOOL REGISTRY (THE BRAIN) ==================
class ToolRegistry:
    
    # --- DEFINITIONS ---
    @staticmethod
    def get_current_time_tool(): 
        return {"type": "function", "function": {"name": "get_current_time", "description": "Get exact current date and time."}}
    
    @staticmethod
    def get_http_request_tool(): 
        return {
            "type": "function", 
            "function": {
                "name": "make_http_request", 
                "description": "Send HTTP Request to external APIs (Gmail, CRM, Stores).", 
                "parameters": {
                    "type": "object", 
                    "properties": {
                        "url": {"type": "string"}, 
                        "method": {"type": "string", "enum": ["GET", "POST"]}, 
                        "headers": {"type": "string", "description": "JSON string of headers"}, 
                        "data": {"type": "string", "description": "JSON string of body"}
                    }, 
                    "required": ["url", "method"]
                }
            }
        }
        
    @staticmethod
    def get_create_agent_tool(): 
        return {
            "type": "function", 
            "function": {
                "name": "create_new_agent", 
                "description": "Build a new agent. YOU MUST provide api_secrets if the agent needs external access.", 
                "parameters": {
                    "type": "object", 
                    "properties": {
                        "name": {"type": "string"}, 
                        "personality": {"type": "string"}, 
                        "goal": {"type": "string"}, 
                        "tools_needed": {"type": "string", "description": "Keywords: 'http', 'time', 'search'"}, 
                        "api_secrets": {"type": "string", "description": "JSON string of API keys"}
                    }, 
                    "required": ["name", "personality", "goal"]
                }
            }
        }

    # --- EXECUTIONS ---
    @staticmethod
    def execute_get_current_time(**kwargs): 
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    @staticmethod
    def execute_http_request(url, method="GET", headers="{}", data="{}", **kwargs):
        try:
            h = safe_json_loads(headers)
            d = safe_json_loads(data)
            resp = requests.request(method, url, headers=h, json=d, timeout=10)
            return f"HTTP {resp.status_code}: {resp.text[:800]}"
        except Exception as e: return f"Connection Error: {str(e)}"

    @staticmethod
    def execute_create_new_agent(name, personality, goal, creator_email, tools_needed="", api_secrets="{}", **kwargs):
        allowed, msg = check_limits(creator_email, 'create_agent')
        if not allowed: return f"ERROR: {msg}"
        
        # === INTELLIGENT TOOL MAPPING (AUTO-CORRECT) ===
        # This fixes the issue where the AI asks for "Gmail Tool" but the code needs "make_http_request"
        final_tools = []
        
        # 1. Always enable HTTP if secrets are provided (Safety Net)
        secrets_dict = safe_json_loads(api_secrets)
        if secrets_dict and len(secrets_dict) > 0:
            final_tools.append("make_http_request")
            
        # 2. Parse requested tools text
        tools_text = tools_needed.lower()
        if "http" in tools_text or "web" in tools_text or "api" in tools_text or "request" in tools_text:
            if "make_http_request" not in final_tools: final_tools.append("make_http_request")
            
        if "time" in tools_text or "date" in tools_text or "clock" in tools_text:
            final_tools.append("get_current_time")
            
        # === INJECT EXECUTION KERNEL ===
        hardened_personality = f"""
        {personality}
        
        [SYSTEM KERNEL - READ ONLY]:
        1. ROLE: You are an AUTONOMOUS EXECUTOR.
        2. MANDATE: If the user asks for data/action, YOU MUST USE THE TOOLS.
        3. SECRETS: You have access to API Keys embedded in your system. Use them in 'make_http_request'.
        4. PROTOCOL: Do NOT say "I will check". EMIT THE TOOL CALL immediately.
        """
        
        cfg = {
            "name": name, 
            "personality": hardened_personality, 
            "goal": goal, 
            "enabled_tools": final_tools, 
            "model": "gpt-4o-mini", 
            "temperature": 0.5, # Lower temp for better adherence
            "icon": "⚡"
        }
        
        save_agent_to_db(cfg, creator_email, api_secrets)
        return f"SUCCESS: Agent '{name}' created. Tools enabled: {final_tools}. Ready in Chat tab."

    REGISTRY = {"get_current_time": execute_get_current_time, "make_http_request": execute_http_request, "create_new_agent": execute_create_new_agent}
    SCHEMAS = [get_current_time_tool(), get_http_request_tool(), get_create_agent_tool()]

# ================== DB OPS ==================
def save_agent_to_db(agent_data, creator, secrets_json="{}"):
    conn = get_db_connection()
    aid = hashlib.md5(f"{agent_data['name']}{time.time()}".encode()).hexdigest()[:10]
    agent_data['id'] = aid
    conn.execute("INSERT OR REPLACE INTO agents VALUES (?, ?, ?, ?, ?, ?)",
             (aid, creator, agent_data['name'], json.dumps(agent_data), datetime.now().isoformat(), secrets_json))
    conn.execute("UPDATE users SET agents_created = agents_created + 1 WHERE email=?", (creator,))
    conn.commit()
    conn.close()
    return aid

def get_user_agents(user_email):
    conn = get_db_connection()
    rows = conn.execute("SELECT * FROM agents WHERE creator=?", (user_email,)).fetchall()
    conn.close()
    agents = {}
    for r in rows:
        cfg = json.loads(r[3])
        cfg['secrets'] = r[5]
        agents[r[0]] = cfg
    return agents

def load_chat_history(agent_id):
    conn = get_db_connection()
    rows = conn.execute("SELECT role, content FROM messages WHERE agent_id=? ORDER BY id ASC", (agent_id,)).fetchall()
    conn.close()
    return [{"role": r[0], "content": r[1]} for r in rows]

# ================== RUN ENGINE ==================
def run_agent_turn(agent_config, history, user_msg, user_email, agent_id):
    client = OpenAI(api_key=SYSTEM_API_KEY)
    
    # Save User Msg
    conn = get_db_connection()
    conn.execute("INSERT INTO messages (agent_id, user_email, role, content, timestamp) VALUES (?, ?, ?, ?, ?)",
                (agent_id, user_email, "user", user_msg, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    
    # Tool Filtering
    enabled = agent_config.get('enabled_tools', [])
    active_schemas = [t for t in ToolRegistry.SCHEMAS if t['function']['name'] in enabled]
    if not active_schemas: active_schemas = None

    # Secrets Injection
    secrets_context = ""
    if agent_config.get('secrets') and agent_config['secrets'] != "{}":
        secrets_context = f"\n\n[SYSTEM SECRETS]:\n{agent_config['secrets']}\n(Use these in HTTP Headers/Body)"

    messages = [{"role": "system", "content": f"{agent_config['personality']}\n{secrets_context}"}] + history + [{"role": "user", "content": user_msg}]

    try:
        with st.spinner("🤖 הסוכן חושב ומבצע..."):
            response = client.chat.completions.create(
                model=agent_config.get('model', 'gpt-4o-mini'),
                messages=messages,
                tools=active_schemas,
                tool_choice="auto" if active_schemas else None
            )
            msg = response.choices[0].message
            
            # === TOOL EXECUTION BLOCK ===
            if msg.tool_calls:
                messages.append(msg)
                
                for tool in msg.tool_calls:
                    func_name = tool.function.name
                    args = safe_json_loads(tool.function.arguments)
                    
                    with st.status(f"⚙️ מפעיל כלי: {func_name}", expanded=True) as s:
                        if func_name == "create_new_agent": 
                            result = ToolRegistry.execute_create_new_agent(**args, creator_email=user_email)
                        elif func_name in ToolRegistry.REGISTRY: 
                            result = ToolRegistry.REGISTRY[func_name](**args)
                        else: 
                            result = "Error: Tool Disabled or Not Found"
                        
                        st.write(result)
                        s.update(label=f"✅ הסתיים: {func_name}", state="complete")
                    
                    messages.append({"role": "tool", "tool_call_id": tool.id, "content": str(result)})
                
                # Final Response after tools
                final_resp = client.chat.completions.create(model=agent_config.get('model', 'gpt-4o-mini'), messages=messages)
                final_content = final_resp.choices[0].message.content
                
                # Save Assistant Msg
                conn = get_db_connection()
                conn.execute("INSERT INTO messages (agent_id, user_email, role, content, timestamp) VALUES (?, ?, ?, ?, ?)",
                            (agent_id, user_email, "assistant", final_content, datetime.now().isoformat()))
                conn.commit()
                conn.close()
                
                return final_content
            else:
                # Plain Text Response
                conn = get_db_connection()
                conn.execute("INSERT INTO messages (agent_id, user_email, role, content, timestamp) VALUES (?, ?, ?, ?, ?)",
                            (agent_id, user_email, "assistant", msg.content, datetime.now().isoformat()))
                conn.commit()
                conn.close()
                return msg.content
            
    except Exception as e:
        return f"System Error: {str(e)}"

# ================== UI & ROUTING ==================
def main():
    setup_rtl()
    
    with st.sidebar:
        st.title("AI Platform V14.0")
        email = st.text_input("התחברות (Email)", value=st.session_state.get('user_email','')).strip().lower()
        
        if email:
            st.session_state.user_email = email
            conn = get_db_connection()
            
            # Owner Bypass
            if email == OWNER_EMAIL:
                if not conn.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
                    conn.execute("INSERT INTO users (email, plan, agents_created, is_approved) VALUES (?, 'vip', 0, 1)", (email,))
                else:
                    conn.execute("UPDATE users SET is_approved=1, plan='vip' WHERE email=?", (email,))
                conn.commit()

            user = conn.execute("SELECT is_approved FROM users WHERE email=?", (email,)).fetchone()
            if not user:
                conn.execute("INSERT INTO users (email, plan, agents_created, is_approved) VALUES (?, 'free', 0, 0)", (email,))
                conn.commit()
                st.warning("ממתין לאישור")
                st.stop()
            elif not user[0]:
                st.error("חסום / ממתין לאישור")
                st.stop()
            conn.close()
            
            st.success("מחובר ✅")
            st.divider()
            
            menu = ["🏠 בית", "🤖 בונה הסוכנים", "💬 צ'אט"]
            if email == OWNER_EMAIL: menu.append("👑 ניהול")
            st.session_state.page = st.radio("תפריט", menu)

    if 'page' not in st.session_state: st.session_state.page = "🏠 בית"

    # --- PAGES ---
    if st.session_state.page == "🏠 בית":
        st.title("ברוכים הבאים לעתיד")
        st.markdown("המערכת מוכנה ליצירת סוכני אוטומציה.")

    elif st.session_state.page == "👑 ניהול":
        if st.session_state.user_email == OWNER_EMAIL:
            st.title("ניהול משתמשים")
            conn = get_db_connection()
            df = pd.read_sql_query("SELECT * FROM users", conn)
            st.dataframe(df)
            conn.close()

    elif st.session_state.page == "🤖 בונה הסוכנים":
        st.title("🤖 בונה הסוכנים")
        # The Consultant
        builder = {
            "name": "Architect", 
            "personality": "You are an expert AI Consultant. Ask for API Keys if needed. Use 'create_new_agent' to build.", 
            "goal": "Build agents", 
            "enabled_tools": ["create_new_agent"], 
            "model": "gpt-4o"
        }
        
        if "builder_log" not in st.session_state: st.session_state.builder_log = []
        for m in st.session_state.builder_log:
            with st.chat_message(m["role"]): st.markdown(m["content"])
            
        if p := st.chat_input("מה לבנות?"):
            st.session_state.builder_log.append({"role": "user", "content": p})
            with st.chat_message("user"): st.markdown(p)
            with st.chat_message("assistant"):
                resp = run_agent_turn(builder, st.session_state.builder_log[:-1], p, st.session_state.user_email, "BUILDER")
                st.markdown(resp)
                st.session_state.builder_log.append({"role": "assistant", "content": resp})

    elif st.session_state.page == "💬 צ'אט":
        st.title("💬 צ'אט")
        agents = get_user_agents(st.session_state.user_email)
        if not agents: 
            st.info("אין סוכנים.")
        else:
            aid = st.selectbox("בחר סוכן:", list(agents.keys()), format_func=lambda x: agents[x]['name'])
            
            if f"hist_{aid}" not in st.session_state:
                st.session_state[f"hist_{aid}"] = load_chat_history(aid)
            
            # AUTO WELCOME MESSAGE (IF CHAT IS EMPTY)
            if not st.session_state[f"hist_{aid}"]:
                welcome = f"שלום! אני {agents[aid]['name']}. אני מוכן לעבודה. מה תרצה שאעשה?"
                st.session_state[f"hist_{aid}"].append({"role": "assistant", "content": welcome})
            
            for m in st.session_state[f"hist_{aid}"]:
                with st.chat_message(m["role"]): st.markdown(m["content"])
                
            if p := st.chat_input():
                st.session_state[f"hist_{aid}"].append({"role": "user", "content": p})
                with st.chat_message("user"): st.markdown(p)
                with st.chat_message("assistant"):
                    ans = run_agent_turn(agents[aid], st.session_state[f"hist_{aid}"][:-1], p, st.session_state.user_email, aid)
                    st.markdown(ans)
                    st.session_state[f"hist_{aid}"].append({"role": "assistant", "content": ans})

if __name__ == "__main__":
    main()
