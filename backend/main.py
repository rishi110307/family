from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import httpx

app = FastAPI(
    title="FamilyReady Safe Places API",
    version="1.0.0"
)

# Allow your frontend to connect
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------
# Home
# --------------------------------------------------

@app.get("/")
def home():
    return {
        "success": True,
        "message": "FamilyReady Backend is running"
    }


# --------------------------------------------------
# Health Check
# --------------------------------------------------

@app.get("/health")
def health():
    return {
        "status": "healthy"
    }


# --------------------------------------------------
# Find Real Nearby Safe Places
# --------------------------------------------------

@app.get("/api/safe-places")
async def get_safe_places(
    lat: float = Query(...),
    lng: float = Query(...)
):

    # OpenStreetMap Overpass query
    query = f"""
    [out:json][timeout:30];

    (
        node["amenity"="hospital"](around:5000,{lat},{lng});
        way["amenity"="hospital"](around:5000,{lat},{lng});

        node["amenity"="police"](around:5000,{lat},{lng});
        way["amenity"="police"](around:5000,{lat},{lng});

        node["amenity"="fire_station"](around:5000,{lat},{lng});
        way["amenity"="fire_station"](around:5000,{lat},{lng});

        node["amenity"="shelter"](around:5000,{lat},{lng});
        way["amenity"="shelter"](around:5000,{lat},{lng});

        node["emergency"="assembly_point"](around:5000,{lat},{lng});
    );

    out center tags;
    """

    url = "https://overpass-api.de/api/interpreter"

    try:

        async with httpx.AsyncClient(timeout=40) as client:

            response = await client.post(
                url,
                data=query
            )

        if response.status_code != 200:

            return {
                "success": False,
                "message": "OpenStreetMap service error",
                "status_code": response.status_code
            }

        data = response.json()

        places = []

        for element in data.get("elements", []):

            tags = element.get("tags", {})

            # Node coordinates
            if "lat" in element and "lon" in element:

                place_lat = element["lat"]
                place_lng = element["lon"]

            # Way coordinates
            elif "center" in element:

                place_lat = element["center"]["lat"]
                place_lng = element["center"]["lon"]

            else:
                continue

            # Determine type
            if tags.get("amenity") == "hospital":
                place_type = "hospital"
                icon = "🏥"

            elif tags.get("amenity") == "police":
                place_type = "police"
                icon = "👮"

            elif tags.get("amenity") == "fire_station":
                place_type = "fire_station"
                icon = "🚒"

            elif tags.get("amenity") == "shelter":
                place_type = "shelter"
                icon = "🏠"

            elif tags.get("emergency") == "assembly_point":
                place_type = "assembly_point"
                icon = "📍"

            else:
                place_type = "safe_place"
                icon = "📍"

            # Name
            name = tags.get(
                "name",
                "Unnamed Safe Place"
            )

            # Address
            address_parts = []

            for key in [
                "addr:housenumber",
                "addr:street",
                "addr:city",
                "addr:postcode"
            ]:

                if key in tags:
                    address_parts.append(tags[key])

            address = ", ".join(address_parts)

            if not address:
                address = "Address not available"

            places.append({
                "name": name,
                "type": place_type,
                "icon": icon,
                "latitude": place_lat,
                "longitude": place_lng,
                "address": address
            })

        return {
            "success": True,
            "count": len(places),
            "places": places
        }

    except httpx.TimeoutException:

        return {
            "success": False,
            "message": "OpenStreetMap request timed out"
        }

    except Exception as e:

        return {
            "success": False,
            "message": "Backend error",
            "details": str(e)
        }
