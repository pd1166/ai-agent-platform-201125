# unified_platform_ultimate.py
# 🚀 AI Agent Platform Ultimate - V17.0 (Stability Fix & Persistence)
# ==============================================================================

import streamlit as st
import os
import json
import time
import sqlite3
import requests
import pandas as pd
from datetime import datetime
from openai import OpenAI
import hashlib
from typing import Dict, List, Optional
import logging

# ================== CONFIGURATION ==================
st.set_page_config(
    page_title="AI Platform V17",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

logging.basicConfig(level=logging.INFO)

# ================== SECRETS CHECK ==================
try:
    SYSTEM_API_KEY = st.secrets["OPENAI_API_KEY"]
except:
    st.error("❌ Missing OPENAI_API_KEY in .streamlit/secrets.toml")
    st.stop()

OWNER_EMAIL = "pompdany@gmail.com"

# ================== HELPER FUNCTIONS (UTILS) ==================
def safe_json_loads(json_str):
    """Robust JSON parser"""
    if not json_str: return {}
    if isinstance(json_str, dict): return json_str
    try: return json.loads(json_str)
    except:
        try: return json.loads(json_str.replace("'", '"'))
        except: return {}

def setup_rtl():
    """Inject Hebrew/RTL CSS"""
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
DB_FILE = "agents_platform_v17.db"

def init_db():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (email TEXT PRIMARY KEY, plan TEXT, agents_created INTEGER, joined_at TEXT, is_approved BOOLEAN)''')
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

# --- DATA ACCESS FUNCTIONS (MOVED UP TO PREVENT NAME_ERROR) ---

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
    """Fetch all agents for a user"""
    conn = get_db_connection()
    rows = conn.execute("SELECT * FROM agents WHERE creator=?", (user_email,)).fetchall()
    conn.close()
    agents = {}
    for r in rows:
        try:
            cfg = safe_json_loads(r[3])
            cfg['secrets'] = r[5]
            cfg['id'] = r[0]
            agents[r[0]] = cfg
        except Exception:
            continue 
    return agents

def load_chat_history(agent_id):
    conn = get_db_connection()
    rows = conn.execute("SELECT role, content FROM messages WHERE agent_id=? ORDER BY id ASC", (agent_id,)).fetchall()
    conn.close()
    return [{"role": r[0], "content": r[1]} for r in rows]

def save_message(agent_id, user_email, role, content):
    conn = get_db_connection()
    conn.execute("INSERT INTO messages (agent_id, user_email, role, content, timestamp) VALUES (?, ?, ?, ?, ?)",
                (agent_id, user_email, role, content, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_user_status(email):
    conn = get_db_connection()
    user = conn.execute("SELECT plan, is_approved, agents_created FROM users WHERE email=?", (email,)).fetchone()
    conn.close()
    if not user: return None
    # Get msg count
    conn = get_db_connection()
    msg_count = conn.execute("SELECT COUNT(*) FROM messages WHERE user_email=? AND role='user'", (email,)).fetchone()[0]
    conn.close()
    return {"plan": user[0], "is_approved": bool(user[1]), "agents_used": user[2], "msgs_used": msg_count}

# Initialize DB
init_db()

# ================== BUSINESS LOGIC ==================
PLAN_LIMITS = {
    "free": {"agents": 1, "messages": 50},
    "pro": {"agents": 10, "messages": 1000},
    "vip": {"agents": 99999, "messages": 99999}
}

def check_limits(email, action_type):
    status = get_user_status(email)
    if not status: return False, "User not found"
    limits = PLAN_LIMITS.get(status['plan'], PLAN_LIMITS['free'])
    
    if action_type == 'create_agent' and status['agents_used'] >= limits['agents']:
        return False, f"הגעת למגבלת הסוכנים ({limits['agents']})."
    if action_type == 'send_message' and status['msgs_used'] >= limits['messages']:
        return False, f"הגעת למגבלת ההודעות ({limits['messages']})."
    return True, "OK"

# ================== TOOL REGISTRY ==================
class ToolRegistry:
    @staticmethod
    def get_definitions():
        return [
            {"type": "function", "function": {"name": "get_current_time", "description": "Get server time."}},
            {"type": "function", "function": {"name": "make_http_request", "description": "HTTP Client (GET/POST).", 
             "parameters": {"type": "object", "properties": {"url": {"type": "string"}, "method": {"type": "string"}, "headers": {"type": "string"}, "data": {"type": "string"}}, "required": ["url", "method"]}}},
            {"type": "function", "function": {"name": "create_new_agent", "description": "Builder Tool.", 
             "parameters": {"type": "object", "properties": {"name": {"type": "string"}, "personality": {"type": "string"}, "goal": {"type": "string"}, "tools_needed": {"type": "string"}, "api_secrets": {"type": "string"}}, "required": ["name", "personality", "goal"]}}}
        ]

    @staticmethod
    def execute_tool(name, args, user_email, agent_id=None):
        if name == "get_current_time":
            return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
        elif name == "make_http_request":
            try:
                h = safe_json_loads(args.get('headers'))
                d = safe_json_loads(args.get('data'))
                resp = requests.request(args.get('method', 'GET'), args.get('url'), headers=h, json=d, timeout=15)
                return f"HTTP {resp.status_code}: {resp.text[:1000]}"
            except Exception as e: return f"HTTP Error: {str(e)}"

        elif name == "create_new_agent":
            # 1. Check Limits
            allowed, msg = check_limits(user_email, 'create_agent')
            if not allowed: return f"ERROR: {msg}"
            
            # 2. Parse Tools
            tools_str = args.get('tools_needed', '')
            tools = [t.strip() for t in tools_str.split(',')] if tools_str else []
            
            # Intelligent Auto-Mapping
            if 'http' in tools_str.lower() or 'api' in tools_str.lower():
                if 'make_http_request' not in tools: tools.append('make_http_request')
            if 'time' in tools_str.lower():
                if 'get_current_time' not in tools: tools.append('get_current_time')

            # 3. Hardened Prompt
            kernel = f"{args['personality']}\n\n[SYSTEM KERNEL]: You are an AUTOMATION ENGINE. Use tools ('make_http_request') for ALL external data. Do not hallucinate. Use secrets provided in context."
            
            cfg = {
                "name": args['name'], "personality": kernel, "goal": args['goal'], 
                "enabled_tools": tools, "model": "gpt-4o-mini", 
                "temperature": 0.5, "icon": "⚡"
            }
            
            save_agent_to_db(cfg, user_email, args.get('api_secrets', '{}'))
            return f"SUCCESS: Agent '{args['name']}' created."
            
        return "Unknown Tool"

# ================== RUN ENGINE (FIXED HISTORY) ==================
def run_agent_loop(agent_config, history_list, user_msg, user_email, agent_id):
    """
    history_list: The list object from st.session_state that feeds the UI
    """
    client = OpenAI(api_key=SYSTEM_API_KEY)
    
    # 1. Update UI State Immediately
    history_list.append({"role": "user", "content": user_msg})
    
    # 2. Save to DB
    save_message(agent_id, user_email, "user", user_msg)
    
    # 3. Build Context
    enabled = agent_config.get('enabled_tools', [])
    all_tools = ToolRegistry.get_definitions()
    active_tools = [t for t in all_tools if t['function']['name'] in enabled]
    if not active_tools: active_tools = None

    secrets_context = ""
    if agent_config.get('secrets') and agent_config['secrets'] != "{}":
        secrets_context = f"\n[SECRETS]: {agent_config['secrets']}"

    messages = [{"role": "system", "content": f"{agent_config['personality']}\n{secrets_context}"}] + history_list

    # 4. Execute
    try:
        with st.spinner("🤖 עובד..."):
            response = client.chat.completions.create(
                model=agent_config.get('model', 'gpt-4o-mini'),
                messages=messages,
                tools=active_tools,
                tool_choice="auto" if active_tools else None
            )
            msg = response.choices[0].message
            
            if msg.tool_calls:
                messages.append(msg) # Add thought to context
                
                for tool in msg.tool_calls:
                    func_name = tool.function.name
                    args = safe_json_loads(tool.function.arguments)
                    
                    with st.status(f"⚙️ מפעיל: {func_name}", expanded=True) as s:
                        result = ToolRegistry.execute_tool(func_name, args, user_email, agent_id)
                        st.write(result)
                        s.update(label=f"✅ בוצע: {func_name}", state="complete")
                    
                    messages.append({"role": "tool", "tool_call_id": tool.id, "content": str(result)})
                
                # Final answer
                final_resp = client.chat.completions.create(model=agent_config.get('model', 'gpt-4o-mini'), messages=messages)
                final_content = final_resp.choices[0].message.content
                
                # Update UI & DB
                history_list.append({"role": "assistant", "content": final_content})
                save_message(agent_id, user_email, "assistant", final_content)
                return final_content
                
            else:
                # Plain text
                history_list.append({"role": "assistant", "content": msg.content})
                save_message(agent_id, user_email, "assistant", msg.content)
                return msg.content
            
    except Exception as e:
        err_msg = f"Error: {str(e)}"
        history_list.append({"role": "assistant", "content": err_msg})
        return err_msg

# ================== UI MAIN ==================
def main():
    setup_rtl()
    
    with st.sidebar:
        st.title("Platform V17")
        email = st.text_input("Email", value=st.session_state.get('user_email','')).strip().lower()
        
        if email:
            st.session_state.user_email = email
            conn = get_db_connection()
            # Owner Bypass
            if email == OWNER_EMAIL:
                if not conn.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
                    conn.execute("INSERT INTO users (email, plan, agents_created, joined_at, is_approved) VALUES (?, 'vip', 0, ?, 1)", (email, datetime.now().isoformat()))
                else:
                    conn.execute("UPDATE users SET is_approved=1, plan='vip' WHERE email=?", (email,))
                conn.commit()
            
            # Check User
            user = conn.execute("SELECT is_approved FROM users WHERE email=?", (email,)).fetchone()
            conn.close()
            
            if user and user[0]:
                st.success("מחובר")
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
        st.markdown("ברוכים הבאים לגרסה V17 - גרסת היציבות.")

    elif st.session_state.page == "👑 ניהול":
        if st.session_state.user_email == OWNER_EMAIL:
            st.title("ניהול")
            conn = get_db_connection()
            df = pd.read_sql_query("SELECT * FROM users", conn)
            st.data_editor(df)
            conn.close()

    elif st.session_state.page == "🤖 בונה הסוכנים":
        st.title("🤖 בונה הסוכנים")
        
        builder = {
            "name": "Architect", 
            "personality": "You are an expert AI Architect. Guide the user. Ask for API Keys if needed. Use 'create_new_agent' to build.", 
            "goal": "Build agents", 
            "enabled_tools": ["create_new_agent"], 
            "model": "gpt-4o"
        }
        
        if "builder_log" not in st.session_state: st.session_state.builder_log = []
        for m in st.session_state.builder_log:
            with st.chat_message(m["role"]): st.markdown(m["content"])
            
        if p := st.chat_input("מה לבנות?"):
            # Run loop updates the builder_log in-place
            run_agent_loop(builder, st.session_state.builder_log, p, st.session_state.user_email, "BUILDER")
            st.rerun()

    elif st.session_state.page == "💬 חדר עבודה":
        st.title("💬 חדר עבודה")
        agents = get_user_agents(st.session_state.user_email)
        
        if not agents: 
            st.info("אין סוכנים.")
        else:
            aid = st.selectbox("בחר סוכן:", list(agents.keys()), format_func=lambda x: agents[x]['name'])
            agent = agents[aid]
            
            # Initial Load
            if f"hist_{aid}" not in st.session_state:
                st.session_state[f"hist_{aid}"] = load_chat_history(aid)
                
            # Display
            for m in st.session_state[f"hist_{aid}"]:
                with st.chat_message(m["role"]): st.markdown(m["content"])
                
            if p := st.chat_input():
                # Run loop updates the hist_{aid} list in-place
                run_agent_loop(agent, st.session_state[f"hist_{aid}"], p, st.session_state.user_email, aid)
                st.rerun()

if __name__ == "__main__":
    main()

