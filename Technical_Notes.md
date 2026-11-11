# Technical Notes — SolarLand Intelligence

**Purpose.** A browser-based prototype for preliminary screening of potential land parcels near a selected PMU for solar-farm site research.

**Approach.** The user enters PMU coordinates or searches for a place name. The user can screen illustrative demonstration records, upload a CSV of parcel points, or upload a GeoJSON FeatureCollection of parcel polygons. The application calculates straight-line distance with the Haversine formula, calculates polygon area geodesically from WGS84 geometry and converts square metres to acres, and applies the assessment brief's initial thresholds: preferred land size of 80–100 acres, preferred distance within 5 km, and maximum distance of 8 km. Results are ranked and shown in a dashboard, table and interactive map with 5 km and 8 km reference circles. Results can be exported to Excel or CSV.

**Data sources.** User-supplied CSV/GeoJSON; OpenStreetMap Nominatim for optional place-name lookup; OSRM public demo routing service for optional driving-route distance. Illustrative demo records are synthetic examples and are not real or verified parcels.

**Tools.** Python, Streamlit, Pandas, Folium, Streamlit-Folium, Plotly, Requests, Shapely, PyProj and OpenPyXL.

**Limitations.** Public geocoding/routing services may be rate-limited or unavailable. If OSRM cannot return a route, the app uses a straight-line estimate and labels it clearly; this is not a road distance. A land-use category or uploaded parcel boundary does not prove vacancy, availability, ownership, zoning approval or development suitability. The prototype does not assess terrain, flood risk, environmental restrictions, title, access rights, grid capacity or solar yield. All candidate parcels require independent verification.

**Manual tasks.** The user must obtain and upload authoritative parcel data, confirm PMU coordinates, verify parcel availability and ownership, and review the screening output. No private credentials, API keys or restricted personal data are embedded.
