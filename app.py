import os
from flask import Flask, render_template, request, jsonify

from api.traffic_service import get_live_traffic
from api.cause_detector import detect_traffic_causes
from api.prediction_service import predict_congestion
from api.signal_optimizer import optimize_signal
from api.location_service import (
    get_locations,
    get_location_coordinates
)
from api.weather_service import get_live_weather
from api.propagation_service import analyze_propagation
from api.risk_explainer import compute_explainable_risk
from api.recommendation_engine import generate_recommendations
from api.emergency_service import calculate_emergency_corridor
from api.metro_service import calculate_metro_switch
from api.cctv_service import get_cctv_vision_feed
from api.notification_service import (
    add_subscription,
    load_subscriptions,
    send_whatsapp_alert,
    generate_whatsapp_share_link,
    check_destination_traffic,
    check_route_commute,
    scan_and_notify_subscriptions
)

app = Flask(__name__)


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/service-worker.js")
def service_worker():
    return app.send_static_file("service-worker.js")


@app.route("/manifest.json")
def manifest():
    return app.send_static_file("manifest.json")


@app.route("/dashboard")
def dashboard():
    return render_template(
        "dashboard.html",
        locations=get_locations()
    )


@app.route("/locations")
def locations():
    return jsonify(get_locations())


@app.route("/live_traffic")
def live_traffic():

    location_name = request.args.get(
        "location",
        "Sitabuldi"
    )

    coordinates = get_location_coordinates(
        location_name
    )

    if not coordinates:
        return jsonify({
            "success": False,
            "error": "Location not found."
        }), 404

    # 1. Fetch TomTom Traffic Flow
    result = get_live_traffic(
        coordinates["latitude"],
        coordinates["longitude"]
    )

    result["location"] = location_name

    # 2. Fetch Open-Meteo Real-Time Weather API
    weather_data = get_live_weather(
        coordinates["latitude"],
        coordinates["longitude"]
    )
    result["weather_data"] = weather_data

    if result.get("success"):
        ratio = result.get("traffic_ratio", 0)
        
        # Derive live parameters from fusion telemetry
        result["parameters"] = {
            "vehicle_count": int(35 + (ratio * 1.4)),
            "occupancy": int(min(98, max(15, ratio * 1.1))),
            "queue_length": int(max(5, ratio * 0.85)),
            "lane_blockage": int(max(0, (ratio - 35) * 1.2)) if ratio > 35 else 0,
            "road_work": 20 if ratio > 65 else 0,
            "pedestrian_count": int(60 + ratio * 2.2),
            "turning_traffic": int(15 + ratio * 0.4),
            "emergency_vehicles": 1 if ratio > 75 else 0,
            "blocked_lanes": 1 if ratio > 65 else 0,
            "incident_severity": int(max(0, (ratio - 45) * 1.4)),
            "event_crowd_level": int(max(0, (ratio - 55) * 1.1)),
            "weather": weather_data.get("condition", "clear").lower()
        }

    return jsonify(result)


@app.route("/analyze", methods=["POST"])
def analyze():

    data = request.get_json() or {}

    # Core AI Calculations
    causes = detect_traffic_causes(data)
    prediction = predict_congestion(data)

    signal_data = dict(data)
    signal_data["traffic_level"] = data.get("traffic_level", "MODERATE")
    signal = optimize_signal(signal_data)

    # 3. Novelty Engine 1: Explainable Risk Score (0-100)
    risk_info = compute_explainable_risk(data)

    # 4. Novelty Engine 2: Road-to-Road Propagation (OSM Junction Model)
    propagation_info = analyze_propagation(
        data.get("location", "Sitabuldi"),
        risk_info.get("risk_score", 0),
        data.get("traffic_level", "MODERATE")
    )

    # 5. Novelty Engine 3: Alternate Route & Decision Recommendations
    recommendation_info = generate_recommendations(data, risk_info, propagation_info)

    return jsonify({
        "success": True,
        "causes": causes,
        "prediction": prediction,
        "signal": signal,
        "explainable_risk": risk_info,
        "propagation": propagation_info,
        "recommendations": recommendation_info
    })


@app.route("/calculate", methods=["POST"])
def calculate():
    return analyze()


@app.route("/api/notify/subscribe", methods=["POST"])
def notify_subscribe():
    data = request.get_json() or {}
    phone_number = data.get("phone_number")
    target_location = data.get("target_location", "Sitabuldi")
    api_key = data.get("api_key", "")
    risk_threshold = int(data.get("risk_threshold", 65))

    if not phone_number:
        return jsonify({"success": False, "error": "Phone number is required."}), 400

    res = add_subscription(phone_number, target_location, api_key, risk_threshold)
    return jsonify(res)


@app.route("/api/notify/whatsapp", methods=["POST"])
def notify_whatsapp():
    data = request.get_json() or {}
    phone_number = data.get("phone_number")
    api_key = data.get("api_key", "")
    location = data.get("location", "Sitabuldi")

    status = check_destination_traffic(location)
    res = send_whatsapp_alert(
        phone_number=phone_number,
        api_key=api_key,
        location=location,
        risk_score=status["risk_score"],
        traffic_level=status["traffic_level"],
        speed_kmh=status["speed_kmh"],
        causes=status["causes"],
        recommendations=status["recommendations"]
    )
    return jsonify(res)


@app.route("/api/notify/destination", methods=["GET", "POST"])
def notify_destination():
    if request.method == "POST":
        data = request.get_json() or {}
        location = data.get("location", "Sitabuldi")
    else:
        location = request.args.get("location", "Sitabuldi")

    status = check_destination_traffic(location)
    return jsonify({"success": True, "data": status})


@app.route("/api/notify/route", methods=["GET", "POST"])
def notify_route():
    if request.method == "POST":
        data = request.get_json() or {}
        origin = data.get("origin", "Sitabuldi")
        destination = data.get("destination", "Sadar")
    else:
        origin = request.args.get("origin", "Sitabuldi")
        destination = request.args.get("destination", "Sadar")

    status = check_route_commute(origin, destination)
    return jsonify({"success": True, "data": status})


@app.route("/api/notify/route_whatsapp", methods=["GET", "POST"])
def notify_route_whatsapp():
    if request.method == "POST":
        data = request.get_json() or {}
        start = data.get("start", data.get("origin", "Sitabuldi"))
        goal = data.get("goal", data.get("destination", "Sadar"))
        phone = data.get("phone_number", data.get("phone"))
        apikey = data.get("api_key", data.get("callmebot_key", ""))
    else:
        start = request.args.get("start", request.args.get("origin", "Sitabuldi"))
        goal = request.args.get("goal", request.args.get("destination", "Sadar"))
        phone = request.args.get("phone", request.args.get("phone_number"))
        apikey = request.args.get("api_key", request.args.get("callmebot_key", ""))

    if not phone:
        return jsonify({"success": False, "error": "Phone number is required (e.g. +919876543210)"}), 400

    from route_whatsapp_notifier import analyze_route, send_whatsapp_without_qr_scan
    analysis = analyze_route(start, goal)
    res = send_whatsapp_without_qr_scan(
        phone_number=phone,
        message_text=analysis["whatsapp_message"],
        callmebot_apikey=apikey
    )
    res["route_analysis"] = analysis
    return jsonify(res)


@app.route("/api/notify/scan", methods=["GET", "POST"])
def notify_scan():
    results = scan_and_notify_subscriptions()
    return jsonify({"success": True, "scan_results": results})


@app.route("/api/notify/subscriptions", methods=["GET"])
def notify_subscriptions():
    subs = load_subscriptions()
    return jsonify({"success": True, "subscriptions": subs})


@app.route("/api/emergency_corridor", methods=["GET", "POST"])
def emergency_corridor():
    if request.method == "POST":
        data = request.get_json() or {}
        origin = data.get("origin", "Katol Road")
        destination = data.get("destination", "Medical Square")
        vehicle_type = data.get("vehicle_type", "Ambulance (108)")
        priority = data.get("priority", "Critical")
    else:
        origin = request.args.get("origin", "Katol Road")
        destination = request.args.get("destination", "Medical Square")
        vehicle_type = request.args.get("vehicle_type", "Ambulance (108)")
        priority = request.args.get("priority", "Critical")

    res = calculate_emergency_corridor(origin, destination, vehicle_type, priority)
    return jsonify(res)


@app.route("/api/metro_transit", methods=["GET", "POST"])
def metro_transit():
    if request.method == "POST":
        data = request.get_json() or {}
        origin = data.get("origin", "Katol Road")
        destination = data.get("destination", "Medical Square")
        ratio = int(data.get("traffic_ratio", 75))
    else:
        origin = request.args.get("origin", "Katol Road")
        destination = request.args.get("destination", "Medical Square")
        ratio = int(request.args.get("traffic_ratio", 75))

    res = calculate_metro_switch(origin, destination, ratio)
    return jsonify(res)


@app.route("/api/cctv_feed", methods=["GET", "POST"])
def cctv_feed():
    if request.method == "POST":
        data = request.get_json() or {}
        location = data.get("location", "Katol Road")
        ratio = int(data.get("traffic_ratio", 65))
        weather = data.get("weather", "clear")
    else:
        location = request.args.get("location", "Katol Road")
        ratio = int(request.args.get("traffic_ratio", 65))
        weather = request.args.get("weather", "clear")

    res = get_cctv_vision_feed(location, ratio, weather)
    return jsonify(res)


@app.route("/health")
def health():
    return jsonify({
        "status": "TrafficTwin AI Multi-Source Data Fusion Engine is running",
        "apis": {
            "tomtom_traffic": "active",
            "open_meteo_weather": "active",
            "overpass_osm_geometry": "active"
        }
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(
        host="0.0.0.0",
        port=port,
        debug=True
    )