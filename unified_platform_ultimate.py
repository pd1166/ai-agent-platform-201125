# unified_platform_ultimate.py
# 🚀 AI Agent Platform Ultimate - V10.0 (Gatekeeper & Business Model)
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
    page_title="AI Platform Gatekeeper | V10.0",
    page_icon="🛡️",
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

# ================== BUSINESS MODEL LIMITS ==================
PLAN_LIMITS = {
    "free": {"agents": 1, "messages": 50},
    "pro": {"agents": 10, "messages": 1000},
    "vip": {"agents": 99999, "messages": 99999}
}

# ================== Database Layer ==================
DB_FILE = "agents_platform_v10.db"

def init_db():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    c = conn.cursor()
    
    # Users Table (Added: is_approved)
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (email TEXT PRIMARY KEY, plan TEXT, agents_created INTEGER, joined_at TEXT, is_approved BOOLEAN)''')
    
    # Agents Table
    c.execute('''CREATE TABLE IF NOT EXISTS agents
                 (id TEXT PRIMARY KEY, creator TEXT, name TEXT, config TEXT, created_at TEXT, secrets TEXT)''')
    
    # Messages Table
    c.execute('''CREATE TABLE IF NOT EXISTS messages
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, agent_id TEXT, user_email TEXT, role TEXT, content TEXT, timestamp TEXT)''')
    
    conn.commit()
    conn.close()

def get_db_connection():
    return sqlite3.connect(DB_FILE, check_same_thread=False)

init_db()

# ================== USER & LIMIT CHECKS ==================
def get_user_status(email):
    conn = get_db_connection()
    user = conn.execute("SELECT plan, is_approved, agents_created FROM users WHERE email=?", (email,)).fetchone()
    
    # Count messages for limits
    msg_count = conn.execute("SELECT COUNT(*) FROM messages WHERE user_email=? AND role='user'", (email,)).fetchone()[0]
    conn.close()
    
    if not user: return None
    return {
        "plan": user[0],
        "is_approved": bool(user[1]),
        "agents_used": user[2],
        "msgs_used": msg_count
    }

def check_limits(email, action_type):
    status = get_user_status(email)
    limits = PLAN_LIMITS.get(status['plan'], PLAN_LIMITS['free'])
    
    if action_type == 'create_agent':
        if status['agents_used'] >= limits['agents']:
            return False, f"הגעת למגבלת הסוכנים לחבילת {status['plan']} ({limits['agents']}). שדרג כדי ליצור עוד."
            
    if action_type == 'send_message':
        if status['msgs_used'] >= limits['messages']:
            return False, f"הגעת למגבלת ההודעות לחבילת {status['plan']} ({limits['messages']}). שדרג כדי להמשיך."
            
    return True, "OK"

# ================== TOOL REGISTRY ==================
class ToolRegistry:
    @staticmethod
    def get_current_time_tool(): return {"type": "function", "function": {"name": "get_current_time", "description": "Get current server time"}}
    @staticmethod
    def get_http_request_tool(): return {"type": "function", "function": {"name": "make_http_request", "description": "HTTP Request", "parameters": {"type": "object", "properties": {"url": {"type": "string"}, "method": {"type": "string", "enum": ["GET", "POST"]}, "headers": {"type": "string"}, "data": {"type": "string"}}, "required": ["url", "method"]}}}
    @staticmethod
    def get_create_agent_tool(): return {"type": "function", "function": {"name": "create_new_agent", "description": "Create agent", "parameters": {"type": "object", "properties": {"name": {"type": "string"}, "personality": {"type": "string"}, "goal": {"type": "string"}, "tools_needed": {"type": "string"}, "api_secrets": {"type": "string"}}, "required": ["name", "personality", "goal"]}}}

    @staticmethod
    def execute_get_current_time(**kwargs): return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    @staticmethod
    def execute_http_request(url, method="GET", headers="{}", data="{}", **kwargs):
        try:
            h = json.loads(headers) if headers else {}
            d = json.loads(data) if data else {}
            resp = requests.request(method, url, headers=h, json=d, timeout=10)
            return f"Status: {resp.status_code}\nResponse: {resp.text[:500]}"
        except Exception as e: return f"Error: {e}"
   @staticmethod
    def execute_create_new_agent(name, personality, goal, creator_email, tools_needed="", api_secrets="{}", **kwargs):
        # Check Limits First!
        allowed, msg = check_limits(creator_email, 'create_agent')
        if not allowed: return f"ERROR: {msg}"
        
        # Handle tools list (safe split)
        if tools_needed:
            tools = [t.strip() for t in tools_needed.split(',')]
        else:
            tools = []
            
        cfg = {
            "name": name, 
            "personality": personality, 
            "goal": goal, 
            "enabled_tools": tools, 
            "model": "gpt-4o-mini", 
            "temperature": 0.7, 
            "icon": "🔗"
        }
        
        save_agent_to_db(cfg, creator_email, api_secrets)
        return f"Agent '{name}' created successfully. (Note: APIs might need keys to work)."

    REGISTRY = {"get_current_time": execute_get_current_time, "make_http_request": execute_http_request, "create_new_agent": execute_create_new_agent}
    SCHEMAS = [get_current_time_tool(), get_http_request_tool(), get_create_agent_tool()]

# ================== DB Helpers ==================
def save_agent_to_db(agent_data, creator, secrets_json="{}"):
    conn = get_db_connection()
    aid = agent_data.get('id') or hashlib.md5(f"{agent_data['name']}{datetime.now()}".encode()).hexdigest()[:10]
    agent_data['id'] = aid
    conn.execute("INSERT OR REPLACE INTO agents VALUES (?, ?, ?, ?, ?, ?)",
             (aid, creator, agent_data['name'], json.dumps(agent_data), datetime.now().isoformat(), secrets_json))
    # Update user count
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

# ================== RUN LOGIC ==================
def run_agent_turn(agent_config, history, user_msg, user_email, agent_id):
    # Check Message Limits
    allowed, msg = check_limits(user_email, 'send_message')
    if not allowed: return msg # Return error to chat

    client = OpenAI(api_key=SYSTEM_API_KEY)
    log_message(agent_id, user_email, "user", user_msg)
    
    enabled = agent_config.get('enabled_tools', [])
    active_schemas = [t for t in ToolRegistry.SCHEMAS if t['function']['name'] in enabled]
    if not active_schemas: active_schemas = None

    secrets_context = ""
    if agent_config.get('secrets') and agent_config['secrets'] != "{}":
        secrets_context = f"\n\n[SYSTEM]: API SECRETS IMPLANTED. Use them in 'make_http_request' but DO NOT reveal them:\n{agent_config['secrets']}"

    messages = [{"role": "system", "content": f"You are {agent_config['personality']}. Goal: {agent_config['goal']}.{secrets_context}"}] + history + [{"role": "user", "content": user_msg}]

    while True:
        response = client.chat.completions.create(
            model=agent_config.get('model', 'gpt-4o-mini'), messages=messages, tools=active_schemas, tool_choice="auto" if active_schemas else None
        )
        msg = response.choices[0].message
        
        if msg.tool_calls:
            messages.append(msg)
            for tool in msg.tool_calls:
                func_name = tool.function.name
                args = json.loads(tool.function.arguments)
                with st.status(f"⚙️ מפעיל: {func_name}...", expanded=False) as s:
                    if func_name == "create_new_agent": result = ToolRegistry.execute_create_new_agent(**args, creator_email=user_email)
                    elif func_name in ToolRegistry.REGISTRY: result = ToolRegistry.REGISTRY[func_name](**args)
                    else: result = "Error"
                    st.write(result)
                    s.update(label=f"✅ בוצע: {func_name}", state="complete")
                messages.append({"role": "tool", "tool_call_id": tool.id, "content": str(result)})
        else:
            log_message(agent_id, user_email, "assistant", msg.content)
            return msg.content

# ================== CEO DASHBOARD ==================
def show_ceo_dashboard():
    st.title("🛡️ שער הניהול (Gatekeeper Admin)")
    st.markdown(f"מחובר כבעלים: **{OWNER_EMAIL}**")
    
    conn = get_db_connection()
    pending_count = conn.execute("SELECT COUNT(*) FROM users WHERE is_approved=0").fetchone()[0]
    conn.close()
    
    if pending_count > 0:
        st.warning(f"⚠️ יש {pending_count} משתמשים חדשים שממתינים לאישור שלך!")
    else:
        st.success("כל המשתמשים מטופלים.")

    st.divider()
    
    tab_users, tab_stats = st.tabs(["👥 אישור משתמשים וחבילות", "📈 סטטיסטיקות"])
    
    with tab_users:
        st.subheader("ניהול הרשאות")
        conn = get_db_connection()
        df_users = pd.read_sql_query("SELECT email, plan, is_approved, agents_created, joined_at FROM users", conn)
        conn.close()
        
        edited_df = st.data_editor(
            df_users,
            column_config={
                "is_approved": st.column_config.CheckboxColumn("מאושר?", help="סמן כדי לאשר כניסה"),
                "plan": st.column_config.SelectboxColumn("חבילה", options=["free", "pro", "vip"], required=True),
                "email": st.column_config.TextColumn("Email", disabled=True)
            },
            hide_index=True,
            use_container_width=True,
            key="user_approval_editor"
        )
        
        if st.button("💾 עדכן אישורים וחבילות"):
            conn = get_db_connection()
            for index, row in edited_df.iterrows():
                is_approved_val = 1 if row['is_approved'] else 0
                conn.execute("UPDATE users SET plan=?, is_approved=? WHERE email=?", (row['plan'], is_approved_val, row['email']))
            conn.commit()
            conn.close()
            st.success("הנתונים נשמרו!")
            time.sleep(1)
            st.rerun()

    with tab_stats:
        st.write("סטטיסטיקות שימוש גלובליות יוצגו כאן.")

# ================== LOGIN & ROUTING ==================
def main():
    if 'page' not in st.session_state: st.session_state.page = "🏠 בית"
    
    with st.sidebar:
        st.title("Platform V10.0")
        
        # AUTHENTICATION LOGIC
   # AUTHENTICATION LOGIC (FIXED)
        email = st.text_input("התחבר (Email)", value=st.session_state.get('user_email','')).strip().lower()
        
        user_status = None
        if email:
            st.session_state.user_email = email
            conn = get_db_connection()
            
            # 1. תיקון כפוי: אם זה המייל של המנהל - תמיד אשר אותו ותן לו VIP
            if email == OWNER_EMAIL:
                # בדיקה אם קיים
                exists = conn.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone()
                if not exists:
                    # צור חדש כ-VIP
                    conn.execute("INSERT INTO users (email, plan, agents_created, joined_at, is_approved) VALUES (?, ?, 0, ?, 1)", 
                                (email, "vip", datetime.now().isoformat()))
                else:
                    # עדכן קיים ל-VIP ומאושר
                    conn.execute("UPDATE users SET is_approved=1, plan='vip' WHERE email=?", (email,))
                conn.commit()
                # הודעת הצלחה קטנה (אפשר למחוק אח"כ)
                st.toast("מערכת זיהתה בעלים - גישה אושרה!", icon="🦅")

            # 2. בדיקת סטטוס רגילה
            user = conn.execute("SELECT is_approved, plan FROM users WHERE email=?", (email,)).fetchone()
            
            if not user:
                # משתמש חדש (שהוא לא המנהל)
                conn.execute("INSERT INTO users (email, plan, agents_created, joined_at, is_approved) VALUES (?, ?, 0, ?, 0)", 
                            (email, "free", datetime.now().isoformat()))
                conn.commit()
                st.warning("חשבון נוצר! ממתין לאישור מנהל.")
            else:
                user_status = {"approved": bool(user[0]), "plan": user[1]}
                if not user_status['approved']:
                    st.error("⛔ החשבון שלך עדיין ממתין לאישור המנהל.")
            conn.close()
        
        # SHOW MENU ONLY IF APPROVED
        if user_status and user_status['approved']:
            st.success(f"מחובר: {user_status['plan'].upper()}")
            st.divider()
            
            menu = ["🏠 בית", "🤖 בונה הסוכנים", "💬 צ'אט"]
            if email == OWNER_EMAIL:
                menu.append("🛡️ שער הניהול (CEO)")
                
            st.session_state.page = st.radio("ניווט", menu)
        else:
            st.session_state.page = "BLOCKED"

    # --- ROUTING ---
    if st.session_state.page == "BLOCKED":
        st.title("⛔ גישה מוגבלת")
        st.write("אנא התחבר עם משתמש מאושר כדי להמשיך.")
        
    elif st.session_state.page == "🛡️ שער הניהול (CEO)":
        if st.session_state.get('user_email') == OWNER_EMAIL:
            show_ceo_dashboard()
        else: st.error("אין כניסה")

    elif st.session_state.page == "🏠 בית":
        st.title("מערכת הסוכנים המאובטחת")
        limits = PLAN_LIMITS.get(user_status['plan'], PLAN_LIMITS['free']) if user_status else {}
        st.info(f"החבילה שלך: {user_status['plan']}")
        st.write(f"מגבלת סוכנים: {limits.get('agents')}")
        st.write(f"מגבלת הודעות: {limits.get('messages')}")

    elif st.session_state.page == "🤖 בונה הסוכנים":
        st.title("🤖 בונה הסוכנים")
        # Builder logic from previous version
        builder_agent = {"name": "Architect", "personality": "AI Architect.", "goal": "Build agents", "enabled_tools": ["create_new_agent"], "model": "gpt-4o"}
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
        if not my_agents: st.info("אין סוכנים.")
        else:
            aid = st.selectbox("בחר:", list(my_agents.keys()), format_func=lambda x: my_agents[x]['name'])
            if "chat_sessions" not in st.session_state: st.session_state.chat_sessions = {}
            if aid not in st.session_state.chat_sessions: st.session_state.chat_sessions[aid] = []
            for m in st.session_state.chat_sessions[aid]:
                with st.chat_message(m["role"]): st.markdown(m["content"])
            if p := st.chat_input():
                st.session_state.chat_sessions[aid].append({"role": "user", "content": p})
                with st.chat_message("user"): st.markdown(p)
                with st.chat_message("assistant"):
                    ans = run_agent_turn(my_agents[aid], st.session_state.chat_sessions[aid][:-1], p, st.session_state.user_email, aid)
                    st.markdown(ans)
                    st.session_state.chat_sessions[aid].append({"role": "assistant", "content": ans})

if __name__ == "__main__":

    main()
