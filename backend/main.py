from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import httpx
import math

app = FastAPI(
    title="FamilyReady API",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =====================================================
# HOME
# =====================================================
@app.get("/")
def home():
    return {
        "success": True,
        "message": "FamilyReady Backend is running"
    }


# =====================================================
# HEALTH
# =====================================================
@app.get("/health")
def health():
    return {"status": "healthy"}


# =====================================================
# DISTANCE HELPER
# =====================================================
def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


# =====================================================
# SAFE PLACES
# =====================================================
@app.get("/api/safe-places")
async def get_safe_places(
    lat: float = Query(...),
    lng: float = Query(...)
):
    query = f"""
    [out:json][timeout:30];

    (
        nwr["amenity"="hospital"](around:10000,{lat},{lng});
        nwr["amenity"="police"](around:10000,{lat},{lng});
        nwr["amenity"="fire_station"](around:10000,{lat},{lng});
        nwr["amenity"="shelter"](around:10000,{lat},{lng});
        nwr["emergency"="assembly_point"](around:10000,{lat},{lng});
    );

    out center tags;
    """

    OVERPASS_SERVERS = [
        "https://overpass.private.coffee/api/interpreter",
        "https://overpass-api.de/api/interpreter"
    ]

    data = None
    for url in OVERPASS_SERVERS:
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(
                    url,
                    data={"data": query},
                    headers={"User-Agent": "FamilyReady/1.0"}
                )
            if response.status_code == 200:
                data = response.json()
                break
            else:
                print(f"Overpass error at {url}: {response.status_code}")
        except Exception as e:
            print(f"Overpass connection failed at {url}: {e}")

    if data is None:
        return {
            "success": False,
            "message": "Could not connect to OpenStreetMap Overpass servers"
        }

    places = []
    for element in data.get("elements", []):
        tags = element.get("tags", {})

        if "lat" in element and "lon" in element:
            place_lat = element["lat"]
            place_lng = element["lon"]
        elif "center" in element:
            place_lat = element["center"]["lat"]
            place_lng = element["center"]["lon"]
        else:
            continue

        amenity = tags.get("amenity")
        emergency = tags.get("emergency")

        if amenity == "hospital":
            place_type, icon = "Hospital", "🏥"
        elif amenity == "police":
            place_type, icon = "Police Station", "👮"
        elif amenity == "fire_station":
            place_type, icon = "Fire Station", "🚒"
        elif amenity == "shelter":
            place_type, icon = "Emergency Shelter", "🏠"
        elif emergency == "assembly_point":
            place_type, icon = "Assembly Point", "📍"
        else:
            continue

        name = tags.get("name", place_type)

        address_parts = []
        for key in [
            "addr:housenumber", "addr:street", "addr:suburb",
            "addr:city", "addr:postcode"
        ]:
            if tags.get(key):
                address_parts.append(tags[key])

        address = ", ".join(address_parts) or "Address not available"

        distance = calculate_distance(lat, lng, place_lat, place_lng)

        places.append({
            "name": name,
            "type": place_type,
            "icon": icon,
            "latitude": place_lat,
            "longitude": place_lng,
            "address": address,
            "distance_km": round(distance, 2)
        })

    places.sort(key=lambda x: x["distance_km"])

    return {
        "success": True,
        "count": len(places),
        "places": places
    }


# =====================================================
# FLOOD ZONES (broadened query, bigger radius)
# =====================================================
@app.get("/api/flood-zones")
async def get_flood_zones(
    lat: float = Query(...),
    lng: float = Query(...),
    radius: int = Query(25000)
):
    query = f"""
    [out:json][timeout:60];

    (
        // Waterways
        way["waterway"](around:{radius},{lat},{lng});
        relation["waterway"](around:{radius},{lat},{lng});

        // Any water-related natural feature
        way["natural"="water"](around:{radius},{lat},{lng});
        relation["natural"="water"](around:{radius},{lat},{lng});
        way["natural"="wetland"](around:{radius},{lat},{lng});
        way["natural"="bay"](around:{radius},{lat},{lng});
        way["natural"="strait"](around:{radius},{lat},{lng});

        // Man-made water bodies (very common in India)
        way["landuse"="reservoir"](around:{radius},{lat},{lng});
        relation["landuse"="reservoir"](around:{radius},{lat},{lng});
        way["landuse"="basin"](around:{radius},{lat},{lng});
        way["landuse"="pond"](around:{radius},{lat},{lng});

        // Tanks (very common in South India)
        node["man_made"="water_tank"](around:{radius},{lat},{lng});
        way["man_made"="water_tank"](around:{radius},{lat},{lng});
        way["man_made"="reservoir_covered"](around:{radius},{lat},{lng});

        // Flood-prone areas explicitly tagged
        way["hazard"="flood"](around:{radius},{lat},{lng});
        node["hazard"="flood"](around:{radius},{lat},{lng});
        way["flood_prone"="yes"](around:{radius},{lat},{lng});
        node["flood_prone"="yes"](around:{radius},{lat},{lng});

        // Dams (relevant for Tirunelveli — e.g., Papanasam)
        way["waterway"="dam"](around:{radius},{lat},{lng});
        node["waterway"="dam"](around:{radius},{lat},{lng});
    );

    out center tags;
    """

    OVERPASS_SERVERS = [
        "https://overpass.kumi.systems/api/interpreter",
        "https://overpass.private.coffee/api/interpreter",
        "https://overpass.osm.ch/api/interpreter",
        "https://overpass-api.de/api/interpreter",
    ]

    data = None
    errors = []

    for url in OVERPASS_SERVERS:
        try:
            print(f"[flood-zones] POST → {url}")
            async with httpx.AsyncClient(timeout=90) as client:
                response = await client.post(
                    url,
                    data={"data": query},
                    headers={
                        "User-Agent": "FamilyReady/1.0",
                        "Accept": "application/json",
                    },
                )
            print(f"[flood-zones] {url} → {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                break
            else:
                errors.append(f"{url}: HTTP {response.status_code}")
        except httpx.TimeoutException:
            errors.append(f"{url}: timeout")
        except Exception as e:
            errors.append(f"{url}: {str(e)[:100]}")

    if data is None:
        return {
            "success": False,
            "message": "Could not fetch flood zones from OpenStreetMap",
            "errors": errors,
        }

    zones = []
    for el in data.get("elements", []):
        tags = el.get("tags", {})

        if "lat" in el and "lon" in el:
            z_lat, z_lng = el["lat"], el["lon"]
        elif "center" in el:
            z_lat, z_lng = el["center"]["lat"], el["center"]["lon"]
        else:
            continue

        waterway  = tags.get("waterway", "")
        natural   = tags.get("natural", "")
        landuse   = tags.get("landuse", "")
        man_made  = tags.get("man_made", "")
        hazard    = tags.get("hazard", "")
        flood     = tags.get("flood_prone", "")

        if waterway == "river":
            icon, kind, base_risk = "🌊", "River", "High"
        elif waterway == "stream":
            icon, kind, base_risk = "💧", "Stream", "Medium"
        elif waterway == "canal":
            icon, kind, base_risk = "🚰", "Canal", "Medium"
        elif waterway == "drain":
            icon, kind, base_risk = "🕳️", "Drainage", "Medium"
        elif waterway == "dam":
            icon, kind, base_risk = "🚧", "Dam", "High"
        elif natural == "water":
            icon, kind, base_risk = "🌊", "Water Body", "High"
        elif natural == "wetland":
            icon, kind, base_risk = "🌾", "Wetland", "Medium"
        elif natural == "bay":
            icon, kind, base_risk = "🌊", "Bay", "Medium"
        elif landuse == "reservoir":
            icon, kind, base_risk = "💦", "Reservoir", "High"
        elif landuse == "basin":
            icon, kind, base_risk = "🪣", "Basin", "High"
        elif landuse == "pond":
            icon, kind, base_risk = "💧", "Pond", "Medium"
        elif man_made == "water_tank":
            icon, kind, base_risk = "🛢️", "Water Tank", "Medium"
        elif hazard == "flood" or flood == "yes":
            icon, kind, base_risk = "⚠️", "Known Flood Zone", "High"
        else:
            continue

        distance = calculate_distance(lat, lng, z_lat, z_lng)

        if distance < 1:
            risk = "High"
        elif distance < 3:
            risk = base_risk
        elif distance < 10:
            risk = "Medium" if base_risk == "High" else base_risk
        else:
            risk = "Low"

        name = tags.get("name", kind)

        zones.append({
            "name": name,
            "kind": kind,
            "icon": icon,
            "latitude": z_lat,
            "longitude": z_lng,
            "risk": risk,
            "distance_km": round(distance, 2),
        })

    zones.sort(key=lambda x: x["distance_km"])
    zones = zones[:100]

    return {
        "success": True,
        "count": len(zones),
        "zones": zones,
        "search_radius_km": radius / 1000,
    }
