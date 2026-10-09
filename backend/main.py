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
    return {"status": "healthy"}


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


# Multiple Overpass mirrors — first one that responds wins
OVERPASS_SERVERS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.osm.ch/api/interpreter",
    "https://overpass.openstreetmap.ru/api/interpreter",
]


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

    data = None
    errors = []

    # Try each mirror
    for url in OVERPASS_SERVERS:
        try:
            print(f"Trying Overpass: {url}")
            async with httpx.AsyncClient(timeout=45) as client:
                response = await client.post(
                    url,
                    data={"data": query},
                    headers={
                        "User-Agent": "FamilyReady/1.0 (emergency preparedness app)",
                        "Accept": "application/json",
                    },
                )

            print(f"  → {url} returned {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                break
            else:
                errors.append(f"{url}: HTTP {response.status_code}")

        except httpx.TimeoutException:
            errors.append(f"{url}: timeout")
            print(f"  → {url} timed out")
        except Exception as e:
            errors.append(f"{url}: {str(e)[:80]}")
            print(f"  → {url} failed: {e}")

    if data is None:
        return {
            "success": False,
            "message": "Could not connect to OpenStreetMap Overpass servers",
            "errors": errors,
        }

    # Parse results
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
            "distance_km": round(distance, 2),
        })

    places.sort(key=lambda x: x["distance_km"])

    return {
        "success": True,
        "count": len(places),
        "places": places,
    }
