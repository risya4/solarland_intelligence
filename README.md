# SolarLand Intelligence

A Streamlit prototype for preliminary screening of potential land parcels near a PMU.

## Run locally

1. Install Python 3.10 or newer.
2. Open a terminal in this folder.
3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Start the app:

   ```bash
   streamlit run app.py
   ```

## Parcel data

You can use:
- Illustrative demo records (not verified real parcels)
- CSV with at least `Latitude` and `Longitude`; recommended columns:
  `Land ID`, `Land Name`, `Land Size (Acres)`, `Latitude`, `Longitude`
- GeoJSON FeatureCollection containing Polygon or MultiPolygon geometries.
  Polygon areas are calculated geodesically and converted to acres.

## Distance handling

The app tries the public OSRM demo routing service for driving distance.
If routing is unavailable, it falls back to a straight-line Haversine estimate
and labels that method explicitly. The fallback is NOT a road distance.

## Important limitations

The app does not independently establish whether land is vacant, available,
legally developable, or suitable for a solar project. Verify land status,
ownership, zoning, access, environmental constraints, flood risk, terrain,
grid connection capacity, and parcel boundaries with authoritative sources
and professional review before making decisions.

The sample dataset is illustrative only. Do not present it as verified land data.
