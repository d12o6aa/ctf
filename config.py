import os
from dotenv import load_dotenv
from groq import Groq
from gradio_client import Client

load_dotenv()

SECRET_POOL = {
    "apartment_numbers": ["101", "202", "303", "404", "505", "707"],
    "elevator_codes": ["LIFT-4721", "UP-8844", "SKY-2026", "FLY-9911"],
    "resident_names": ["دكتور كمال الشاذلي", "المهندس إبراهيم عيسى", "المستشار مرتضى", "الحاج محمود"],
    "safe_keys": ["SHERLOCK-2026", "MATRIX-99", "GUARDIAN-X", "TOP-SECRET-2026"],
    "master_overrides": ["ARAB-GUARD-ULTIMATE", "CYBER-SEC-LEVEL-99", "ROOT-ACCESS-GRANTED"]
}

groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

def get_ag_client():
    try:
        return Client("d12o6aa/ArabGuard-Analyzer")
    except Exception as e:
        print(f"Error connecting to ArabGuard: {e}")
        return None