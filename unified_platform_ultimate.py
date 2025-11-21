# unified_platform_ultimate.py
# 🚀 AI Agent Platform Ultimate - V12.0 (Final UX/UI Polish + RTL + Logic Fix)
# ==============================================================================

import streamlit as st
import os
import json
import time
import sqlite3
import math
import requests
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
from openai import OpenAI
import hashlib
from typing import Dict, List, Optional
import logging

# ================== Configuration ==================
st.set_page_config(
    page_title="AI Platform V12.0",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

logging.basicConfig(level=logging.INFO)

# ================== SECRETS & AUTH ==================
try:
    SYSTEM_API_KEY = st.secrets["OPENAI_API_KEY"]
except:
    st.error("❌ Missing OPENAI_API_KEY in .streamlit/secrets.toml")
    st.stop()

OWNER_EMAIL = "pompdany@gmail.com"

# ================== RTL & STYLING (HEBREW SUPPORT) ==================
def setup_rtl():
    st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Heebo:wght@400;500;700&display=swap');
        
        html, body, [class*="css"] {
            font-family: 'Heebo', sans-serif;
            direction: rtl;
            text-align: right;
        }
        
        .stTextInput, .stTextArea, .stSelectbox, input, textarea {
            direction: rtl;
            text-align: right;
        }
        
        .stChatMessage {
            direction: rtl;
            text-align: right;
        }
        
        p, div, label, h1, h2, h3 {
            text-align: right !important;
        }

        /* Force LTR for code blocks */
        code, pre {
            direction: ltr !important;
            text-align: left !important;
        }
        
        /* Sidebar adjustments */
        section[data-testid="stSidebar"] {
            direction: rtl;
        }
    </style>
    """, unsafe_allow_html=True)

# ================== BUSINESS LIMITS ==================
PLAN_LIMITS = {
    "free": {"agents": 1, "messages": 50},
    "pro": {"agents": 10, "messages": 1000},
    "vip": {"agents": 99999, "messages": 99999}
}

# ================== DB INIT ==================
DB_FILE = "agents_platform_v12.db"

def init_db():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (email TEXT PRIMARY KEY, plan TEXT, agents_created INTEGER, joined_at TEXT, is_approved BOOLEAN)''')
    c.execute('''CREATE TABLE IF NOT EXISTS agents
                 (id TEXT PRIMARY KEY, creator TEXT, name TEXT, config TEXT, created_at TEXT, secrets TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS messages
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, agent_id TEXT, user_email TEXT, role TEXT, content TEXT, timestamp TEXT)''')
    conn.commit()
    conn.close()

def get_db_connection():
    return sqlite3.connect(DB_FILE, check_same_thread=False)

init_db()

# ================== HELPER FUNCTIONS ==================
def safe_json_loads(json_str):
    if not json_str: return {}
    try: return json.loads(json_str)
    except:
        try: return json.loads(json_str.replace("'", '"'))
        except: return {}

def get_user_status(email):
    conn = get_db_connection()
    user = conn.execute("SELECT plan, is_approved, agents_created FROM users WHERE email=?", (email,)).fetchone()
    msg_count = conn.execute("SELECT COUNT(*) FROM messages WHERE user_email=? AND role='user'", (email,)).fetchone()[0]
    conn.close()
    if not user: return None
    return {"plan": user[0], "is_approved": bool(user[1]), "agents_used": user[2], "msgs_used": msg_count}

def check_limits(email, action_type):
    status = get_user_status(email)
    if not status: return False, "User not found"
    limits = PLAN_LIMITS.get(status['plan'], PLAN_LIMITS['free'])
    
    if action_type == 'create_agent' and status['agents_used'] >= limits['agents']:
        return False, f"הגעת למגבלת הסוכנים ({limits['agents']}). שדרג חבילה."
    if action_type == 'send_message' and status['msgs_used'] >= limits['messages']:
        return False, f"הגעת למגבלת ההודעות ({limits['messages']}). שדרג חבילה."
    return True, "OK"

# ================== TOOL REGISTRY ==================
class ToolRegistry:
    @staticmethod
    def get_current_time_tool(): return {"type": "function", "function": {"name": "get_current_time", "description": "Get current server time"}}
    
    @staticmethod
    def get_http_request_tool(): 
        return {
            "type": "function", 
            "function": {
                "name": "make_http_request", 
                "description": "Send HTTP Request (GET/POST). Use this to fetch data or trigger actions.", 
                "parameters": {
                    "type": "object", 
                    "properties": {
                        "url": {"type": "string"}, 
                        "method": {"type": "string", "enum": ["GET", "POST"]}, 
                        "headers": {"type": "string", "description": "JSON format headers"}, 
                        "data": {"type": "string", "description": "JSON format body"}
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
                "description": "Create a new agent. Requires name, personality, goal.", 
                "parameters": {
                    "type": "object", 
                    "properties": {
                        "name": {"type": "string"}, 
                        "personality": {"type": "string"}, 
                        "goal": {"type": "string"}, 
                        "tools_needed": {"type": "string"}, 
                        "api_secrets": {"type": "string"}
                    }, 
                    "required": ["name", "personality", "goal"]
                }
            }
        }

    @staticmethod
    def execute_get_current_time(**kwargs): 
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    @staticmethod
    def execute_http_request(url, method="GET", headers="{}", data="{}", **kwargs):
        try:
            h = safe_json_loads(headers)
            d = safe_json_loads(data)
            resp = requests.request(method, url, headers=h, json=d, timeout=15)
            return f"HTTP Status: {resp.status_code}\nResponse Body: {resp.text[:1000]}"
        except Exception as e: return f"HTTP Request Failed: {str(e)}"

    @staticmethod
    def execute_create_new_agent(name, personality, goal, creator_email, tools_needed="", api_secrets="{}", **kwargs):
        allowed, msg = check_limits(creator_email, 'create_agent')
        if not allowed: return f"ERROR: {msg}"
        
        tools = [t.strip() for t in tools_needed.split(',')] if tools_needed else []
        
        # HARDENING THE PROMPT: FORCE TOOL USAGE
        hardened_personality = personality + "\n\n[SYSTEM INSTRUCTION]: You are an autonomous agent. If your task requires external data (email, stock, etc.), you MUST use the 'make_http_request' tool. Do NOT halluciation or pretend to check. If you cannot check, say you cannot check."
        
        cfg = {
            "name": name, 
            "personality": hardened_personality, 
            "goal": goal, 
            "enabled_tools": tools, 
            "model": "gpt-4o-mini", 
            "temperature": 0.7, 
            "icon": "🤖"
        }
        
        save_agent_to_db(cfg, creator_email, api_secrets)
        return f"SUCCESS: Agent '{name}' created. Tell the user they can now switch to the Chat tab to use it."

    REGISTRY = {"get_current_time": execute_get_current_time, "make_http_request": execute_http_request, "create_new_agent": execute_create_new_agent}
    SCHEMAS = [get_current_time_tool(), get_http_request_tool(), get_create_agent_tool()]

# ================== DB HELPERS ==================
def save_agent_to_db(agent_data, creator, secrets_json="{}"):
    conn = get_db_connection()
    aid = agent_data.get('id') or hashlib.md5(f"{agent_data['name']}{datetime.now()}".encode()).hexdigest()[:10]
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

def log_message(agent_id, user_email, role, content):
    conn = get_db_connection()
    conn.execute("INSERT INTO messages (agent_id, user_email, role, content, timestamp) VALUES (?, ?, ?, ?, ?)",
                (agent_id, user_email, role, content, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def load_chat_history(agent_id):
    conn = get_db_connection()
    rows = conn.execute("SELECT role, content FROM messages WHERE agent_id=? ORDER BY id ASC", (agent_id,)).fetchall()
    conn.close()
    return [{"role": r[0], "content": r[1]} for r in rows]

# ================== RUN LOGIC (With Thinking Indicator) ==================
def run_agent_turn(agent_config, history, user_msg, user_email, agent_id):
    allowed, msg = check_limits(user_email, 'send_message')
    if not allowed: return msg

    client = OpenAI(api_key=SYSTEM_API_KEY)
    log_message(agent_id, user_email, "user", user_msg)
    
    enabled = agent_config.get('enabled_tools', [])
    active_schemas = [t for t in ToolRegistry.SCHEMAS if t['function']['name'] in enabled]
    if not active_schemas: active_schemas = None

    secrets_context = ""
    if agent_config.get('secrets') and agent_config['secrets'] != "{}":
        secrets_context = f"\n\n[SYSTEM]: API SECRETS AVAILABLE. Use them in 'make_http_request'.\nSecrets: {agent_config['secrets']}"

    messages = [{"role": "system", "content": f"You are {agent_config['personality']}. Goal: {agent_config['goal']}.{secrets_context}"}] + history + [{"role": "user", "content": user_msg}]

    try:
        # UI SPINNER - THE FIX FOR "IS IT STUCK?"
        with st.spinner("הסוכן חושב..."):
            response = client.chat.completions.create(
                model=agent_config.get('model', 'gpt-4o-mini'), messages=messages, tools=active_schemas, tool_choice="auto" if active_schemas else None
            )
            msg = response.choices[0].message
            
            if msg.tool_calls:
                messages.append(msg)
                for tool in msg.tool_calls:
                    func_name = tool.function.name
                    args = safe_json_loads(tool.function.arguments)
                    
                    with st.status(f"⚙️ מפעיל כלי: {func_name}...", expanded=True) as s:
                        if func_name == "create_new_agent": result = ToolRegistry.execute_create_new_agent(**args, creator_email=user_email)
                        elif func_name in ToolRegistry.REGISTRY: result = ToolRegistry.REGISTRY[func_name](**args)
                        else: result = "Error: Tool not found"
                        st.write(f"תוצאה: {result}")
                        s.update(label=f"✅ בוצע: {func_name}", state="complete")
                    
                    messages.append({"role": "tool", "tool_call_id": tool.id, "content": str(result)})
                
                final_resp = client.chat.completions.create(model=agent_config.get('model', 'gpt-4o-mini'), messages=messages)
                final_content = final_resp.choices[0].message.content
                log_message(agent_id, user_email, "assistant", final_content)
                return final_content
                
            else:
                log_message(agent_id, user_email, "assistant", msg.content)
                return msg.content
            
    except Exception as e:
        return f"System Error: {str(e)}"

# ================== CEO DASHBOARD ==================
def show_ceo_dashboard():
    st.title("🛡️ שער הניהול (CEO)")
    st.markdown(f"מחובר: **{OWNER_EMAIL}**")
    conn = get_db_connection()
    pending = conn.execute("SELECT COUNT(*) FROM users WHERE is_approved=0").fetchone()[0]
    conn.close()
    if pending > 0: st.warning(f"⚠️ {pending} ממתינים לאישור")
    
    tab1, tab2 = st.tabs(["👥 משתמשים", "📈 נתונים"])
    with tab1:
        conn = get_db_connection()
        df = pd.read_sql_query("SELECT email, plan, is_approved, agents_created FROM users", conn)
        conn.close()
        edited = st.data_editor(df, key="users_edit", use_container_width=True)
        if st.button("שמור שינויים"):
            conn = get_db_connection()
            for i, row in edited.iterrows():
                conn.execute("UPDATE users SET plan=?, is_approved=? WHERE email=?", (row['plan'], 1 if row['is_approved'] else 0, row['email']))
            conn.commit()
            conn.close()
            st.rerun()

# ================== MAIN ==================
def main():
    setup_rtl() # LOAD RTL CSS
    if 'page' not in st.session_state: st.session_state.page = "🏠 בית"
    
    with st.sidebar:
        st.title("Platform V12.0")
        email = st.text_input("Email", value=st.session_state.get('user_email','')).strip().lower()
        user_status = None
        
        if email:
            st.session_state.user_email = email
            conn = get_db_connection()
            if email == OWNER_EMAIL:
                if not conn.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
                    conn.execute("INSERT INTO users (email, plan, agents_created, joined_at, is_approved) VALUES (?, ?, 0, ?, 1)", (email, "vip", datetime.now().isoformat()))
                else:
                    conn.execute("UPDATE users SET is_approved=1, plan='vip' WHERE email=?", (email,))
                conn.commit()

            user = conn.execute("SELECT is_approved, plan FROM users WHERE email=?", (email,)).fetchone()
            if not user:
                conn.execute("INSERT INTO users (email, plan, agents_created, joined_at, is_approved) VALUES (?, ?, 0, ?, 0)", (email, "free", datetime.now().isoformat()))
                conn.commit()
                st.warning("ממתין לאישור")
            else:
                user_status = {"approved": bool(user[0]), "plan": user[1]}
            conn.close()

        if user_status and user_status['approved']:
            st.success(f"Plan: {user_status['plan']}")
            st.divider()
            menu = ["🏠 בית", "🤖 בונה הסוכנים", "💬 צ'אט"]
            if email == OWNER_EMAIL: menu.append("🛡️ שער הניהול (CEO)")
            st.session_state.page = st.radio("תפריט", menu)
        else:
            st.session_state.page = "BLOCKED"

    if st.session_state.page == "BLOCKED":
        st.title("⛔ גישה מוגבלת")
        st.info("המשתמש שלך טרם אושר.")

    elif st.session_state.page == "🛡️ שער הניהול (CEO)":
        if st.session_state.get('user_email') == OWNER_EMAIL: show_ceo_dashboard()

    elif st.session_state.page == "🏠 בית":
        st.title("ברוכים הבאים")
        st.markdown("המערכת מוכנה לעבודה.")

    elif st.session_state.page == "🤖 בונה הסוכנים":
        st.title("🤖 בונה הסוכנים")
        
        # UPDATED BUILDER PERSONALITY - EDUCATIONAL & STRICT
        builder_agent = {
            "name": "Architect", 
            "personality": """You are an AI Solutions Architect.
            YOUR GOAL: Guide the user to build a working agent.
            
            PROTOCOL:
            1. If the user asks for integrations (Gmail, CRM, etc.), EXPLAIN CLEARLY that API Keys are needed.
            2. TEACH the user how to get them if they don't know (e.g., "To get a Gmail key, you need to go to Google Cloud Console...").
            3. DO NOT create the agent until the user provides the keys or asks for a mock/test agent.
            4. Once keys are provided, use 'create_new_agent' and put keys in 'api_secrets'.""", 
            "goal": "Build agents with valid connectivity", 
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
                resp = run_agent_turn(builder_agent, st.session_state.builder_log[:-1], p, st.session_state.user_email, "SYS_BUILDER")
                st.markdown(resp)
                st.session_state.builder_log.append({"role": "assistant", "content": resp})

    elif st.session_state.page == "💬 צ'אט":
        st.title("💬 צ'אט")
        my_agents = get_user_agents(st.session_state.user_email)
        if not my_agents: 
            st.info("אין סוכנים. לך לבונה!")
        else:
            aid = st.selectbox("בחר:", list(my_agents.keys()), format_func=lambda x: my_agents[x]['name'])
            
            if f"history_{aid}" not in st.session_state:
                st.session_state[f"history_{aid}"] = load_chat_history(aid)
            
            for m in st.session_state[f"history_{aid}"]:
                with st.chat_message(m["role"]): st.markdown(m["content"])
                
            if p := st.chat_input():
                st.session_state[f"history_{aid}"].append({"role": "user", "content": p})
                with st.chat_message("user"): st.markdown(p)
                with st.chat_message("assistant"):
                    ans = run_agent_turn(my_agents[aid], st.session_state[f"history_{aid}"][:-1], p, st.session_state.user_email, aid)
                    st.markdown(ans)
                    st.session_state[f"history_{aid}"].append({"role": "assistant", "content": ans})

if __name__ == "__main__":
    main()
