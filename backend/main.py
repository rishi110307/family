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


@app.get("/")
def home():
    return {
        "success": True,
        "message": "FamilyReady Backend is running"
    }


@app.get("/health")
def health():
    return {
        "status": "healthy"
    }


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

    # Try each Overpass server until one works
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

    # Parse the Overpass response into a clean list of places
    places = []

    for element in data.get("elements", []):
        tags = element.get("tags", {})

        # Get coordinates (node = lat/lon, way/relation = center)
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
            place_type = "Hospital"
            icon = "🏥"
        elif amenity == "police":
            place_type = "Police Station"
            icon = "👮"
        elif amenity == "fire_station":
            place_type = "Fire Station"
            icon = "🚒"
        elif amenity == "shelter":
            place_type = "Emergency Shelter"
            icon = "🏠"
        elif emergency == "assembly_point":
            place_type = "Assembly Point"
            icon = "📍"
        else:
            continue

        name = tags.get("name", place_type)

        # Build address from available tags
        address_parts = []
        for key in [
            "addr:housenumber",
            "addr:street",
            "addr:suburb",
            "addr:city",
            "addr:postcode"
        ]:
            if tags.get(key):
                address_parts.append(tags[key])

        address = ", ".join(address_parts)
        if not address:
            address = "Address not available"

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

    # Sort by nearest first
    places.sort(key=lambda x: x["distance_km"])

    return {
        "success": True,
        "count": len(places),
        "places": places
    }
