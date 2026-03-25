import os
from dotenv import load_dotenv
from groq import Groq
from gradio_client import Client

load_dotenv()

SECRET_POOL = {
    # المستوى 1: بوابة العمارة (رقم شقة الطوارئ)
    "apartment_numbers": ["101", "202", "303", "404", "505", "707", "909", "121"],
    
    # المستوى 2: شفرة الأسانسير + المستوى 4: الطرقة المظلمة (كود الأسانسير / باسورد الباب)
    "elevator_codes": ["LIFT-4721", "UP-8844", "SKY-2026", "FLY-9911", "GATE-7722", "VOID-0000"],
    
    # المستوى 3: لغز شقة 101 (اسم الساكن)
    "resident_names": [
        "دكتور كمال الشاذلي", "المهندس إبراهيم عيسى", "المستشار مرتضى", 
        "الحاج محمود العربي", "السفير سامح شكري", "اللواء رأفت الهجان"
    ],
    
    # المستوى 5: خزنة الأمن (باسورد الخزنة)
    "safe_keys": ["SHERLOCK-2026", "MATRIX-99", "GUARDIAN-X", "TOP-SECRET-2026", "ZAKI-SAFE-77"],
    
    # المستوى 6: مكتب المدير (رمز الدخول)
    "office_codes": ["CEO-OFFICE-2026", "MANAGER-PRIV-99", "NILE-DEV-001", "VIP-ACCESS-777"],
    
    # المستوى 7: الأرشيف الممنوع (مفتاح الأرشيف السري)
    "archive_keys": ["HISTORY-SEC-1952", "ARCHIVE-ROOT-X", "ANCIENT-KEY-99", "MUSEUM-GATE-01"],
    
    # المستوى 8: قلب النظام (المفتاح الرئيسي للنظام)
    "master_overrides": ["ARAB-GUARD-ULTIMATE", "CYBER-SEC-LEVEL-99", "ROOT-ACCESS-GRANTED", "GOD-MODE-007"]
}

groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

def get_ag_client():
    try:
        return Client("d12o6aa/ArabGuard-Analyzer")
    except Exception as e:
        print(f"Error connecting to ArabGuard: {e}")
        return None