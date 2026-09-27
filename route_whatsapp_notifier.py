import os
import sys
import json
import argparse
import requests
import urllib.parse
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add project root to sys.path if needed
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Ensure stdout supports UTF-8 on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from api.location_service import get_location_coordinates
from api.traffic_service import get_live_traffic
from api.weather_service import get_live_weather

def clean_phone_number(phone: str) -> str:
    """Format phone number to international format (e.g. 919876543210)."""
    digits = "".join(filter(str.isdigit, phone))
    if len(digits) == 10:
        digits = "91" + digits
    return digits

def analyze_route(start_dest: str, goal_dest: str):
    """
    Super-Simple & Clean Route Analyzer:
    Checks Start, Goal, Weather, Traffic and outputs only essential info:
    1. Route (Start ➔ Goal)
    2. Weather
    3. Traffic Status
    4. Decision (Main road se jao ya nahi)
    5. Alternate Route (if rerouting needed)
    """
    # 1. Fetch Coordinates
    start_coords = get_location_coordinates(start_dest) or {"latitude": 21.1458, "longitude": 79.0882}
    goal_coords = get_location_coordinates(goal_dest) or {"latitude": 21.1600, "longitude": 79.0800}

    # 2. Fetch Live Traffic Data
    traffic_start = get_live_traffic(start_coords["latitude"], start_coords["longitude"])
    traffic_goal = get_live_traffic(goal_coords["latitude"], goal_coords["longitude"])

    ratio_start = traffic_start.get("traffic_ratio", 30) if traffic_start.get("success") else 35
    ratio_goal = traffic_goal.get("traffic_ratio", 30) if traffic_goal.get("success") else 35
    avg_ratio = round((ratio_start + ratio_goal) / 2, 1)

    # 3. Fetch Live Weather Data
    weather_info = get_live_weather(goal_coords["latitude"], goal_coords["longitude"])
    weather_cond = weather_info.get("condition", "Clear")
    temp = weather_info.get("temperature", 28.0)

    # 4. Compute Delays
    delay_min = int(avg_ratio * 0.25)

    # 5. Simple Decision & Concise Message
    if avg_ratio >= 40:
        # Rerouting Needed
        traffic_status = f"Heavy Traffic (+{delay_min} min delay)"
        decision = "❌ Main Road se MAT JAO (Traffic jyada hai)"
        
        alternate_routes = [
            f"{start_dest} ➔ Ring Road Bypass ➔ {goal_dest}",
            f"{start_dest} ➔ VIP Road Link ➔ {goal_dest}",
            f"{start_dest} ➔ Flyover Expressway ➔ {goal_dest}"
        ]
        suggested_route = alternate_routes[abs(hash(start_dest + goal_dest)) % len(alternate_routes)]
        route_line = f"🛣️ *Recommended Route:* Take '{suggested_route}'"
    elif weather_cond in ["Rain", "Storm", "Fog"]:
        # Weather Caution
        traffic_status = "Normal Traffic"
        decision = f"⚡ Main Road se JAO, lekin {weather_cond.lower()} ki wajah se dhyan se chalayein!"
        suggested_route = f"Direct Main Road ({start_dest} ➔ {goal_dest})"
        route_line = f"🛣️ *Route:* {suggested_route}"
    else:
        # Smooth / Clear Main Road
        traffic_status = "Clear Flow / Low Traffic"
        decision = "✅ Main Road se JAO, rasta bilkul clear hai!"
        suggested_route = f"Direct Main Road ({start_dest} ➔ {goal_dest})"
        route_line = f"🛣️ *Route:* {suggested_route}"

    # 6. Ultra-Clean & Simple WhatsApp Message Format
    msg_lines = [
        "🚦 *Traffic & Route Alert* 🚦",
        "",
        f"📍 *Route:* {start_dest} ➔ {goal_dest}",
        f"🌤️ *Weather:* {weather_cond} ({temp}°C)",
        f"🚗 *Traffic:* {traffic_status}",
        "",
        f"🎯 *Decision:* {decision}",
        f"{route_line}"
    ]

    whatsapp_message = "\n".join(msg_lines)

    return {
        "start": start_dest,
        "goal": goal_dest,
        "traffic_ratio": avg_ratio,
        "traffic_status": traffic_status,
        "weather": f"{weather_cond} ({temp}°C)",
        "decision": decision,
        "suggested_route": suggested_route,
        "whatsapp_message": whatsapp_message
    }

def send_whatsapp_without_qr_scan(
    phone_number: str,
    message_text: str,
    method: str = "auto",
    callmebot_apikey: str = "",
    twilio_account_sid: str = "",
    twilio_auth_token: str = "",
    twilio_from_number: str = "whatsapp:+14155238886"
):
    """Sends WhatsApp message directly without requiring WhatsApp Web QR scanning."""
    clean_phone = clean_phone_number(phone_number)
    encoded_msg = urllib.parse.quote(message_text)
    share_url = f"https://wa.me/{clean_phone}?text={encoded_msg}"
    app_intent_url = f"whatsapp://send?phone={clean_phone}&text={encoded_msg}"

    # 1. Twilio WhatsApp Cloud API
    if method == "twilio" or (method == "auto" and twilio_account_sid and twilio_auth_token):
        try:
            url = f"https://api.twilio.com/2010-04-01/Accounts/{twilio_account_sid}/Messages.json"
            data = {
                "From": twilio_from_number if twilio_from_number.startswith("whatsapp:") else f"whatsapp:{twilio_from_number}",
                "To": f"whatsapp:+{clean_phone}",
                "Body": message_text
            }
            resp = requests.post(url, data=data, auth=(twilio_account_sid, twilio_auth_token), timeout=10)
            if resp.status_code in [200, 201]:
                return {
                    "success": True,
                    "method": "Twilio Cloud API (Zero QR Scan Needed)",
                    "message": f"WhatsApp message successfully sent to +{clean_phone}!",
                    "details": resp.json()
                }
            else:
                return {"success": False, "method": "Twilio API", "error": f"Twilio API Error ({resp.status_code}): {resp.text}", "share_url": share_url, "app_intent_url": app_intent_url}
        except Exception as e:
            return {"success": False, "error": f"Twilio connection error: {e}", "share_url": share_url, "app_intent_url": app_intent_url}

    # 2. CallMeBot WhatsApp HTTP API (Direct Automated Send)
    if method == "callmebot" or (method == "auto" and callmebot_apikey):
        try:
            url = f"https://api.callmebot.com/whatsapp.php?phone=+{clean_phone}&text={encoded_msg}&apikey={callmebot_apikey}"
            req = requests.get(url, timeout=10)
            if req.status_code == 200:
                return {
                    "success": True,
                    "method": "CallMeBot API (Zero QR Scan Needed)",
                    "message": f"WhatsApp notification sent to +{clean_phone}!",
                    "api_response": req.text[:150]
                }
            else:
                return {"success": False, "method": "CallMeBot API", "error": f"CallMeBot Error HTTP {req.status_code}", "share_url": share_url, "app_intent_url": app_intent_url}
        except Exception as e:
            return {"success": False, "error": f"CallMeBot error: {e}", "share_url": share_url, "app_intent_url": app_intent_url}

    # 3. Direct WhatsApp App Intent (Opens App with Direct Send Button)
    return {
        "success": True,
        "method": "WhatsApp App Direct Link",
        "message": f"Direct Send link generated for +{clean_phone}. (Set CallMeBot API Key for 100% automated background sending).",
        "share_url": share_url,
        "app_intent_url": app_intent_url,
        "phone": f"+{clean_phone}"
    }

def main():
    parser = argparse.ArgumentParser(description="Send Clean & Simple Traffic WhatsApp Notification without QR code scanning.")
    parser.add_argument("--start", type=str, default="", help="Start Destination / Origin")
    parser.add_argument("--goal", type=str, default="", help="Goal / End Destination")
    parser.add_argument("--phone", type=str, default="", help="Recipient Phone Number (e.g. +919876543210)")
    parser.add_argument("--callmebot_key", type=str, default=os.getenv("CALLMEBOT_API_KEY", ""), help="CallMeBot API Key (Optional)")
    parser.add_argument("--twilio_sid", type=str, default=os.getenv("TWILIO_ACCOUNT_SID", ""), help="Twilio Account SID (Optional)")
    parser.add_argument("--twilio_token", type=str, default=os.getenv("TWILIO_AUTH_TOKEN", ""), help="Twilio Auth Token (Optional)")

    args = parser.parse_args()

    # Interactive input if run directly without flags
    start_dest = args.start
    if not start_dest:
        start_dest = input("📍 Start Location daalein (e.g. Sitabuldi): ").strip() or "Sitabuldi"

    goal_dest = args.goal
    if not goal_dest:
        goal_dest = input("🏁 Goal Location daalein (e.g. Sadar): ").strip() or "Sadar"

    phone = args.phone
    if not phone:
        phone = input("📱 WhatsApp Phone Number daalein (e.g. 9876543210): ").strip()

    if not phone:
        print("❌ Phone number zaroori hai!")
        return

    print(f"\n🚀 Analyzing Route: '{start_dest}' ➔ '{goal_dest}'...")
    route_info = analyze_route(start_dest, goal_dest)

    print("\n--- Simple WhatsApp Message ---")
    print(route_info['whatsapp_message'])
    print("-------------------------------\n")

    print(f"📱 Processing WhatsApp Notification to {phone}...")
    send_result = send_whatsapp_without_qr_scan(
        phone_number=phone,
        message_text=route_info['whatsapp_message'],
        callmebot_apikey=args.callmebot_key,
        twilio_account_sid=args.twilio_sid,
        twilio_auth_token=args.twilio_token
    )

    print("\n--- Result ---")
    if send_result.get("share_url"):
        print(f"\n👉 Direct 1-Click WhatsApp Link:\n{send_result['share_url']}\n")
    print(json.dumps(send_result, indent=2))

if __name__ == "__main__":
    main()
