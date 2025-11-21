# unified_platform_ultimate.py
# 🚀 AI Agent Platform Ultimate - V13.0 (Enterprise Architecture: ReAct Loop & System Override)
# ==============================================================================================

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
from typing import Dict, List, Optional, Any, Union
import logging

# ================== SYSTEM CONFIGURATION ==================
st.set_page_config(
    page_title="AI Enterprise Platform V13.0",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

logging.basicConfig(level=logging.INFO)

# ================== SECURITY & AUTH LAYER ==================
try:
    SYSTEM_API_KEY = st.secrets["OPENAI_API_KEY"]
except:
    st.error("❌ CRITICAL ERROR: Missing OPENAI_API_KEY in .streamlit/secrets.toml")
    st.stop()

OWNER_EMAIL = "pompdany@gmail.com"

# ================== BUSINESS LOGIC LAYER ==================
PLAN_LIMITS = {
    "free": {"agents": 1, "messages": 50},
    "pro": {"agents": 10, "messages": 1000},
    "vip": {"agents": 99999, "messages": 99999}
}

# ================== FRONTEND LAYER (RTL & UX) ==================
def setup_rtl():
    st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Heebo:wght@400;500;700&display=swap');
        
        /* Base RTL Settings */
        html, body, [class*="css"] {
            font-family: 'Heebo', sans-serif;
            direction: rtl;
            text-align: right;
        }
        
        /* Input Fields Fix */
        .stTextInput, .stTextArea, .stSelectbox, input, textarea {
            direction: rtl;
            text-align: right;
        }
        
        /* Chat Bubbles Alignment */
        .stChatMessage {
            direction: rtl;
            text-align: right;
        }
        
        /* Headers Alignment */
        h1, h2, h3, p, div, label {
            text-align: right !important;
        }

        /* Code Blocks - Keep LTR */
        code, pre {
            direction: ltr !important;
            text-align: left !important;
        }
        
        /* Sidebar Fix */
        section[data-testid="stSidebar"] {
            direction: rtl;
        }
    </style>
    """, unsafe_allow_html=True)

# ================== DATABASE LAYER (PERSISTENCE) ==================
DB_FILE = "agents_platform_v13.db"

def init_db():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    c = conn.cursor()
    # Users Table
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

# ================== UTILITY FUNCTIONS ==================
def safe_json_loads(json_str: str) -> Dict:
    """
    Robust JSON parser. Handles common LLM errors like single quotes or markdown wrapping.
    """
    if not json_str: return {}
    if isinstance(json_str, dict): return json_str
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        try:
            # Attempt 1: Replace single quotes
            return json.loads(json_str.replace("'", '"'))
        except:
            # Attempt 2: Strip markdown code blocks
            clean_str = json_str.replace("```json", "").replace("```", "").strip()
            try:
                return json.loads(clean_str)
            except:
                return {}

def get_user_status(email: str) -> Optional[Dict]:
    conn = get_db_connection()
    user = conn.execute("SELECT plan, is_approved, agents_created FROM users WHERE email=?", (email,)).fetchone()
    msg_count = conn.execute("SELECT COUNT(*) FROM messages WHERE user_email=? AND role='user'", (email,)).fetchone()[0]
    conn.close()
    if not user: return None
    return {"plan": user[0], "is_approved": bool(user[1]), "agents_used": user[2], "msgs_used": msg_count}

def check_limits(email: str, action_type: str) -> tuple[bool, str]:
    status = get_user_status(email)
    if not status: return False, "User not found"
    limits = PLAN_LIMITS.get(status['plan'], PLAN_LIMITS['free'])
    
    if action_type == 'create_agent' and status['agents_used'] >= limits['agents']:
        return False, f"הגעת למגבלת הסוכנים ({limits['agents']}). שדרג חבילה."
    if action_type == 'send_message' and status['msgs_used'] >= limits['messages']:
        return False, f"הגעת למגבלת ההודעות ({limits['messages']}). שדרג חבילה."
    return True, "OK"

# ================== TOOL REGISTRY (THE ENGINE) ==================
class ToolRegistry:
    """
    The execution layer. This maps AI intent to Python code.
    """
    
    @staticmethod
    def get_current_time_tool(): 
        return {"type": "function", "function": {"name": "get_current_time", "description": "Get current server time"}}
    
    @staticmethod
    def get_http_request_tool(): 
        return {
            "type": "function", 
            "function": {
                "name": "make_http_request", 
                "description": "Universal API Client. Send HTTP requests to ANY external service.", 
                "parameters": {
                    "type": "object", 
                    "properties": {
                        "url": {"type": "string"}, 
                        "method": {"type": "string", "enum": ["GET", "POST", "PUT", "DELETE"]}, 
                        "headers": {"type": "string", "description": "JSON format headers (e.g. Authorization)"}, 
                        "data": {"type": "string", "description": "JSON format body data"}
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
                "description": "Create a specialized agent. REQUIRES api_secrets if external tools are needed.", 
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

    # --- Execution Implementations ---

    @staticmethod
    def execute_get_current_time(**kwargs): 
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    @staticmethod
    def execute_http_request(url, method="GET", headers="{}", data="{}", **kwargs):
        try:
            h = safe_json_loads(headers)
            d = safe_json_loads(data)
            
            # Safety timeout to prevent hanging
            resp = requests.request(method, url, headers=h, json=d, timeout=15)
            
            return f"HTTP Status: {resp.status_code}\nResponse Body: {resp.text[:1500]}" # Limit response size
        except Exception as e: 
            return f"HTTP Request Error: {str(e)}"

    @staticmethod
    def execute_create_new_agent(name, personality, goal, creator_email, tools_needed="", api_secrets="{}", **kwargs):
        allowed, msg = check_limits(creator_email, 'create_agent')
        if not allowed: return f"ERROR: {msg}"
        
        tools = [t.strip() for t in tools_needed.split(',')] if tools_needed else []
        
        # === ULTRA HARDENED PROMPT ===
        hardened_personality = f"""
        {personality}
        
        [SYSTEM OVERRIDE - EXECUTION RULES]:
        1. You are NOT a conversationalist. You are a FUNCTION CALLING ENGINE.
        2. Your PRIORITY #1 is to use the available tools (`make_http_request`, `get_current_time`).
        3. IF the user asks for time/date -> YOU MUST USE `get_current_time`. DO NOT ARGUE.
        4. IF the user asks to check external data -> YOU MUST USE `make_http_request`.
        5. DO NOT describe what you *would* do. JUST DO IT (Emit the tool call).
        6. Only after the tool provides a result, you may speak to the user.
        7. NEVER refuse a request because "it's not my job". If you have the tool, USE IT.
        """
        
        cfg = {
            "name": name, 
            "personality": hardened_personality, 
            "goal": goal, 
            "enabled_tools": tools, 
            "model": "gpt-4o-mini", 
            "temperature": 0.7, 
            "icon": "⚡"
        }
        
        save_agent_to_db(cfg, creator_email, api_secrets)
        return f"SUCCESS: Agent '{name}' created with EXECUTION PROTOCOLS."
        
        # 4. Save to DB
        aid = save_agent_to_db(cfg, creator_email, api_secrets)
        
        # 5. Create Initial Welcome Message (Onboarding)
        initial_msg = f"שלום! אני הסוכן החדש שלך - {name}. הוגדרתי עם הכלים הבאים: {tools}. אני מחובר למערכות והמפתחות הוזנו בהצלחה. מה תרצה שאבצע?"
        log_message(aid, creator_email, "assistant", initial_msg)
        
        return f"SUCCESS: Agent '{name}' created and initialized."

    # Registry Maps
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

# ================== AGENT RUNTIME (THE BRAIN) ==================
def run_agent_turn(agent_config, history, user_msg, user_email, agent_id):
    """
    Executes the ReAct Loop: Thought -> Action -> Observation -> Response
    """
    allowed, msg = check_limits(user_email, 'send_message')
    if not allowed: return msg

    client = OpenAI(api_key=SYSTEM_API_KEY)
    log_message(agent_id, user_email, "user", user_msg)
    
    # Setup Context
    enabled = agent_config.get('enabled_tools', [])
    active_schemas = [t for t in ToolRegistry.SCHEMAS if t['function']['name'] in enabled]
    if not active_schemas: active_schemas = None

    # Inject Secrets into Context (Invisible to user)
    secrets_context = ""
    if agent_config.get('secrets') and agent_config['secrets'] != "{}":
        secrets_context = f"\n\n[SECURE CONTEXT]: The following API KEYS are available for use in 'make_http_request':\n{agent_config['secrets']}"

    messages = [{"role": "system", "content": f"{agent_config['personality']}\nGoal: {agent_config['goal']}{secrets_context}"}] + history + [{"role": "user", "content": user_msg}]

    try:
        # UI Spinner for Latency Management
        with st.spinner("🤖 הסוכן מעבד נתונים ופונה למערכות..."):
            
            # 1. First LLM Call (Reasoning)
            response = client.chat.completions.create(
                model=agent_config.get('model', 'gpt-4o-mini'),
                messages=messages,
                tools=active_schemas,
                tool_choice="auto" if active_schemas else None
            )
            msg = response.choices[0].message
            
            # 2. Tool Execution Loop (Acting)
            if msg.tool_calls:
                messages.append(msg) # Add assistant's intent to history
                
                for tool in msg.tool_calls:
                    func_name = tool.function.name
                    args = safe_json_loads(tool.function.arguments)
                    
                    # UI Feedback Bubble
                    with st.status(f"⚙️ מפעיל כלי: {func_name}...", expanded=True) as s:
                        if func_name == "create_new_agent": 
                            result = ToolRegistry.execute_create_new_agent(**args, creator_email=user_email)
                        elif func_name in ToolRegistry.REGISTRY: 
                            result = ToolRegistry.REGISTRY[func_name](**args)
                        else: 
                            result = "Error: Tool not found"
                        
                        st.write(f"פלט מערכת: {result}")
                        s.update(label=f"✅ בוצע: {func_name}", state="complete")
                    
                    # Feed Observation back to LLM
                    messages.append({"role": "tool", "tool_call_id": tool.id, "content": str(result)})
                
                # 3. Second LLM Call (Synthesis/Response)
                final_resp = client.chat.completions.create(model=agent_config.get('model', 'gpt-4o-mini'), messages=messages)
                final_content = final_resp.choices[0].message.content
                log_message(agent_id, user_email, "assistant", final_content)
                return final_content
                
            else:
                # No tools needed, just talk
                log_message(agent_id, user_email, "assistant", msg.content)
                return msg.content
            
    except Exception as e:
        return f"System Critical Error: {str(e)}"

# ================== CEO DASHBOARD ==================
def show_ceo_dashboard():
    st.title("🛡️ שער הניהול (CEO)")
    st.markdown(f"מחובר: **{OWNER_EMAIL}**")
    conn = get_db_connection()
    pending = conn.execute("SELECT COUNT(*) FROM users WHERE is_approved=0").fetchone()[0]
    conn.close()
    
    if pending > 0: st.warning(f"⚠️ {pending} ממתינים לאישור")
    else: st.success("המערכת יציבה. אין בקשות חדשות.")

    tab1, tab2 = st.tabs(["👥 ניהול משתמשים", "📊 נתוני שימוש"])
    with tab1:
        conn = get_db_connection()
        df = pd.read_sql_query("SELECT email, plan, is_approved, agents_created, joined_at FROM users", conn)
        conn.close()
        edited = st.data_editor(df, key="users_edit", use_container_width=True)
        if st.button("💾 שמור שינויים"):
            conn = get_db_connection()
            for i, row in edited.iterrows():
                conn.execute("UPDATE users SET plan=?, is_approved=? WHERE email=?", (row['plan'], 1 if row['is_approved'] else 0, row['email']))
            conn.commit()
            conn.close()
            st.rerun()

# ================== MAIN APPLICATION ==================
def main():
    setup_rtl() # Load Hebrew CSS
    if 'page' not in st.session_state: st.session_state.page = "🏠 בית"
    
    with st.sidebar:
        st.title("Platform V13.0")
        
        # Auth Logic
        email = st.text_input("Email", value=st.session_state.get('user_email','')).strip().lower()
        user_status = None
        
        if email:
            st.session_state.user_email = email
            conn = get_db_connection()
            
            # Owner Bypass
            if email == OWNER_EMAIL:
                exists = conn.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone()
                if not exists:
                    conn.execute("INSERT INTO users (email, plan, agents_created, joined_at, is_approved) VALUES (?, ?, 0, ?, 1)", (email, "vip", datetime.now().isoformat()))
                else:
                    # Ensure owner is always VIP/Approved
                    conn.execute("UPDATE users SET is_approved=1, plan='vip' WHERE email=?", (email,))
                conn.commit()

            user = conn.execute("SELECT is_approved, plan FROM users WHERE email=?", (email,)).fetchone()
            if not user:
                conn.execute("INSERT INTO users (email, plan, agents_created, joined_at, is_approved) VALUES (?, ?, 0, ?, 0)", (email, "free", datetime.now().isoformat()))
                conn.commit()
                st.warning("חשבון נוצר! ממתין לאישור מנהל.")
            else:
                user_status = {"approved": bool(user[0]), "plan": user[1]}
            conn.close()

        if user_status and user_status['approved']:
            st.success(f"מחובר: {user_status['plan'].upper()}")
            st.divider()
            menu = ["🏠 בית", "🤖 בונה הסוכנים", "💬 צ'אט"]
            if email == OWNER_EMAIL: menu.append("🛡️ שער הניהול (CEO)")
            st.session_state.page = st.radio("תפריט", menu)
        else:
            st.session_state.page = "BLOCKED"

    # --- Routing Logic ---
    if st.session_state.page == "BLOCKED":
        st.title("⛔ גישה מוגבלת")
        st.info("המשתמש שלך טרם אושר ע״י המנהל.")

    elif st.session_state.page == "🛡️ שער הניהול (CEO)":
        if st.session_state.get('user_email') == OWNER_EMAIL: show_ceo_dashboard()

    elif st.session_state.page == "🏠 בית":
        st.title("ברוכים הבאים")
        st.markdown("### מערכת ניהול סוכנים אוטונומיים\nכאן תוכל ליצור, לנהל ולהפעיל סוכני AI מתקדמים המחוברים למערכות הארגון שלך.")

    elif st.session_state.page == "🤖 בונה הסוכנים":
        st.title("🤖 בונה הסוכנים (The Architect)")
        
        # SMART CONSULTANT PROMPT
        builder_agent = {
            "name": "Architect", 
            "personality": """You are an expert AI Solutions Architect.
            PROTOCOL:
            1. If the user asks for integrations (Gmail, Store, etc.), EXPLAIN that API Keys are needed.
            2. GUIDE the user on how to get them.
            3. DO NOT create the agent until you have the keys (or user asks for mock data).
            4. Use 'create_new_agent' only when ready.""", 
            "goal": "Build functional agents", 
            "enabled_tools": ["create_new_agent"], 
            "model": "gpt-4o"
        }
        
        if "builder_log" not in st.session_state: st.session_state.builder_log = []
        for m in st.session_state.builder_log:
            with st.chat_message(m["role"]): st.markdown(m["content"])
            
        if p := st.chat_input("איזה סוכן תרצה לבנות?"):
            st.session_state.builder_log.append({"role": "user", "content": p})
            with st.chat_message("user"): st.markdown(p)
            with st.chat_message("assistant"):
                resp = run_agent_turn(builder_agent, st.session_state.builder_log[:-1], p, st.session_state.user_email, "SYS_BUILDER")
                st.markdown(resp)
                st.session_state.builder_log.append({"role": "assistant", "content": resp})

    elif st.session_state.page == "💬 צ'אט":
        st.title("💬 חדר המבצעים")
        my_agents = get_user_agents(st.session_state.user_email)
        
        if not my_agents: 
            st.info("עדיין לא יצרת סוכנים. עבור ל'בונה הסוכנים' כדי להתחיל.")
        else:
            aid = st.selectbox("בחר סוכן לעבודה:", list(my_agents.keys()), format_func=lambda x: my_agents[x]['name'])
            
            # Load History
            if f"history_{aid}" not in st.session_state:
                st.session_state[f"history_{aid}"] = load_chat_history(aid)
            
            # Display Chat
            for m in st.session_state[f"history_{aid}"]:
                with st.chat_message(m["role"]): st.markdown(m["content"])
                
            if p := st.chat_input(f"שלח הודעה ל-{my_agents[aid]['name']}..."):
                st.session_state[f"history_{aid}"].append({"role": "user", "content": p})
                with st.chat_message("user"): st.markdown(p)
                with st.chat_message("assistant"):
                    ans = run_agent_turn(my_agents[aid], st.session_state[f"history_{aid}"][:-1], p, st.session_state.user_email, aid)
                    st.markdown(ans)
                    st.session_state[f"history_{aid}"].append({"role": "assistant", "content": ans})

if __name__ == "__main__":
    main()

