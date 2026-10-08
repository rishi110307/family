import os
import httpx

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv


# Load environment variables
load_dotenv()

# --------------------------------------------------
# FastAPI App
# --------------------------------------------------

app = FastAPI(
    title="FamilyReady Backend",
    description="Emergency Safe Places API",
    version="1.0.0"
)


# --------------------------------------------------
# CORS
# --------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------
# Google Places API
# --------------------------------------------------

GOOGLE_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")

GOOGLE_PLACES_URL = (
    "https://places.googleapis.com/v1/places:searchNearby"
)


# --------------------------------------------------
# Home Route
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
# Safe Places
# --------------------------------------------------

@app.get("/api/safe-places")
async def get_safe_places(
    lat: float = Query(..., description="User latitude"),
    lng: float = Query(..., description="User longitude")
):

    # Check API key
    if not GOOGLE_API_KEY:
        return {
            "success": False,
            "message": "Google Maps API key is not configured"
        }

    # Google Places request
    request_body = {
        "includedTypes": [
            "hospital",
            "police",
            "fire_station"
        ],

        "maxResultCount": 20,

        "rankPreference": "DISTANCE",

        "locationRestriction": {
            "circle": {
                "center": {
                    "latitude": lat,
                    "longitude": lng
                },
                "radius": 5000
            }
        }
    }

    # Required Google headers
    headers = {
        "Content-Type": "application/json",

        "X-Goog-Api-Key": GOOGLE_API_KEY,

        "X-Goog-FieldMask": (
            "places.displayName,"
            "places.formattedAddress,"
            "places.location,"
            "places.primaryType,"
            "places.googleMapsUri"
        )
    }

    try:

        # Send request to Google
        async with httpx.AsyncClient(timeout=20) as client:

            response = await client.post(
                GOOGLE_PLACES_URL,
                json=request_body,
                headers=headers
            )

        # Google API error
        if response.status_code != 200:

            return {
                "success": False,
                "message": "Google Places API returned an error",
                "status_code": response.status_code,
                "details": response.text
            }

        data = response.json()

        places = []

        # Process Google results
        for place in data.get("places", []):

            display_name = place.get(
                "displayName",
                {}
            ).get(
                "text",
                "Unknown Place"
            )

            location = place.get(
                "location",
                {}
            )

            latitude = location.get("latitude")
            longitude = location.get("longitude")

            if latitude is None or longitude is None:
                continue

            place_type = place.get(
                "primaryType",
                "safe_place"
            )

            address = place.get(
                "formattedAddress",
                "Address unavailable"
            )

            google_maps_uri = place.get(
                "googleMapsUri",
                ""
            )

            places.append({
                "name": display_name,
                "type": place_type,
                "latitude": latitude,
                "longitude": longitude,
                "address": address,
                "googleMapsUri": google_maps_uri
            })

        # Return data to frontend
        return {
            "success": True,
            "count": len(places),
            "places": places
        }

    except httpx.TimeoutException:

        return {
            "success": False,
            "message": "Google Places API request timed out"
        }

    except Exception as e:

        return {
            "success": False,
            "message": "Backend error",
            "details": str(e)
        }
