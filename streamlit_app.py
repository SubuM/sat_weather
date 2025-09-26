import streamlit as st
import requests
import datetime
import json
import pandas as pd
import numpy as np
from pycountry import countries

# --- CONFIGURATION & CONSTANTS ---
# Fetch the key securely from the secrets file (or set a placeholder if not found)
try:
    OWM_API_KEY = st.secrets["openweathermap_api_key"]
except KeyError:
    OWM_API_KEY = "PLACEHOLDER_FOR_SECRETS_NOT_LOADED" 

CURRENT_WEATHER_URL = "http://api.openweathermap.org/data/2.5/weather"
FORECAST_URL = "http://api.openweathermap.org/data/2.5/forecast"
CITY_LIST_FILE = "city.list.json" 
UNITS = "metric"  

# Emoji mapping based on OpenWeatherMap 'main' weather group
WEATHER_EMOJIS = {
    "Clear": "☀️ Clear Sky",
    "Clouds": "☁️ Cloudy",
    "Rain": "🌧️ Rain",
    "Drizzle": "💧 Drizzle",
    "Thunderstorm": "⛈️ Thunderstorm",
    "Snow": "❄️ Snow",
    "Mist": "🌫️ Mist/Fog",
    "Smoke": "💨 Smoke",
    "Haze": "🌁 Haze",
    "Dust": "🏜️ Dust",
    "Fog": "🌫️ Mist/Fog",
    "Sand": "🏖️ Sand/Dust",
    "Ash": "🌋 Ash",
    "Squall": "🌬️ Squalls",
    "Tornado": "🌪️ Tornado",
}

# --- DYNAMIC CARD STYLES (Font Color Switched for Legibility) ---
# BASE_CARD_CSS is used to manage common styles. The 'color' property is 
# now dynamically included in the dictionary values.

BASE_CARD_CSS = "padding: 15px; border-radius: 10px; box-shadow: 0 4px 8px rgba(0, 0, 0, 0.2); background-size: cover; background-position: center;"

# For images, you must choose dark backgrounds (Rain, Thunderstorm) 
# or light backgrounds (Clear, Snow) and assign the appropriate font color.
CARD_STYLES = {
    # LIGHT BACKGROUNDS (Use Dark Font: #333333)
    "Clear": f"{BASE_CARD_CSS} background-image: linear-gradient(to top right, #ADD8E6, #FFFACD); border-left: 5px solid #FFD700; color: #333333;", 
    "Clouds": f"{BASE_CARD_CSS} background-color: #F0F8FF; border-left: 5px solid #A9A9A9; color: #333333;",
    "Drizzle": f"{BASE_CARD_CSS} background-color: #E0EFFF; border-left: 5px solid #6495ED; color: #333333;", 
    "Snow": f"{BASE_CARD_CSS} background-color: #FFFFFF; border-left: 5px solid #ADD8E6; color: #333333;",
    "Mist": f"{BASE_CARD_CSS} background-color: #E0EEE0; border-left: 5px solid #808080; color: #333333;",
    "Haze": f"{BASE_CARD_CSS} background-color: #FAEBD7; border-left: 5px solid #9932CC; color: #333333;",
    
    # DARK BACKGROUNDS (Use Light Font: #FFFFFF)
    # Using a dark image path placeholder to demonstrate the need for a white font
    "Rain": f"{BASE_CARD_CSS} background-image: url('images/rain_bg.jpg'); background-color: #4169E1; border-left: 5px solid #4169E1; color: #FFFFFF;",
    "Thunderstorm": f"{BASE_CARD_CSS} background-color: #333333; border-left: 5px solid #800080; color: #FFFFFF;", 
    
    # Default (Light background, dark font)
    "Default": f"{BASE_CARD_CSS} background-color: #F5F5F5; border-left: 5px solid #696969; color: #333333;",
}
# --- END OF CONSTANTS ---

# --- DATA LOADING AND CACHING ---

def get_country_name(code):
    """Helper function to convert Alpha-2 code to full country name."""
    try:
        return countries.get(alpha_2=code).name
    except AttributeError:
        return code

@st.cache_data(show_spinner="Loading and processing 200,000+ cities... This may take a moment.")
def load_and_process_city_data():
    """
    Loads the massive OWM city list, processes it into a DataFrame,
    and prepares country name mappings.
    """
    try:
        with open(CITY_LIST_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        df = pd.DataFrame(data)
        df = df[['name', 'country']].rename(columns={'name': 'City', 'country': 'CountryCode'})
        df.dropna(subset=['City', 'CountryCode'], inplace=True)
        
        df['CountryName'] = df['CountryCode'].apply(get_country_name)
        
        country_map = {name: code for name, code in zip(df['CountryName'], df['CountryCode'])}
        sorted_country_names = sorted(df['CountryName'].unique())
        
        st.success("City list loaded and country names mapped successfully!")
        return df, sorted_country_names, country_map
    
    except FileNotFoundError:
        st.error(f"⚠️ Error: The file '{CITY_LIST_FILE}' was not found. Please download it and save it.")
        st.stop()
    except Exception as e:
        st.error(f"An error occurred while loading city data: {e}")
        st.stop()

# --- HELPER FUNCTIONS ---

def convert_timestamp_to_local(timestamp_utc, timezone_offset):
    """
    Converts a UTC Unix timestamp to a local datetime object using the timezone offset.
    Returns the datetime object.
    """
    if timestamp_utc is None or timezone_offset is None:
        return None
        
    dt_utc = datetime.datetime.utcfromtimestamp(timestamp_utc)
    offset = datetime.timedelta(seconds=timezone_offset)
    dt_local = dt_utc + offset
    
    return dt_local

def get_wind_direction(deg):
    """Converts wind degrees (0-360) to a cardinal direction."""
    if deg is None:
        return 'N/A'
    directions = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
                  "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    index = round(deg / (360. / len(directions))) % len(directions)
    return directions[index]

# --- API FETCH LOGIC ---

def handle_api_error():
    """Checks for API key setup."""
    if OWM_API_KEY == "PLACEHOLDER_FOR_SECRETS_NOT_LOADED":
        st.error("⚠️ **Error: OpenWeatherMap API key not found.**")
        st.error("Please create a `.streamlit/secrets.toml` file and add the `openweathermap_api_key`.")
        return True
    return False

def get_current_weather_data(city_name, country_code):
    """Fetches current weather data."""
    if handle_api_error():
        return None
        
    try:
        query = f"{city_name},{country_code}"
        params = {'q': query, 'appid': OWM_API_KEY, 'units': UNITS}
        
        response = requests.get(CURRENT_WEATHER_URL, params=params)
        response.raise_for_status() 
        return response.json()

    except requests.exceptions.HTTPError as err:
        if response.status_code == 404:
            st.error(f"City '{city_name}' not found for current weather. Please select another city.")
        else:
            st.error(f"HTTP Error fetching current weather: {err}")
        return None
    except requests.exceptions.RequestException as e:
        st.error(f"Error connecting to OWM API for current weather: {e}")
        return None

def get_forecast_data(city_name, country_code):
    """Fetches 5-day / 3-hour forecast data."""
    if handle_api_error():
        return None

    try:
        query = f"{city_name},{country_code}"
        params = {'q': query, 'appid': OWM_API_KEY, 'units': UNITS}

        response = requests.get(FORECAST_URL, params=params)
        response.raise_for_status() 
        return response.json()

    except requests.exceptions.HTTPError as err:
        if response.status_code == 404:
            st.warning("Forecast data not available for this specific city.")
        else:
            st.error(f"HTTP Error fetching forecast: {err}")
        return None
    except requests.exceptions.RequestException as e:
        st.error(f"Error connecting to OWM API for forecast: {e}")
        return None


# --- DISPLAY LOGIC ---

def display_weather(data):
    """Parses and displays the current weather data in Streamlit, including extended metrics."""
    
    # 1. Extract Core Data
    city_name = data.get('name', 'N/A')
    country_code = data.get('sys', {}).get('country', 'N/A')
    timezone_offset = data.get('timezone', 0)
    
    main_weather = data.get('weather', [{}])[0].get('main', 'N/A')
    description = data.get('weather', [{}])[0].get('description', 'N/A').capitalize()
    
    temp = data.get('main', {}).get('temp')
    feels_like = data.get('main', {}).get('feels_like')
    temp_min = data.get('main', {}).get('temp_min')
    temp_max = data.get('main', {}).get('temp_max')
    
    pressure = data.get('main', {}).get('pressure')
    humidity = data.get('main', {}).get('humidity')
    visibility = data.get('visibility') # in meters
    
    wind_data = data.get('wind', {})
    wind_speed = wind_data.get('speed')
    wind_deg = wind_data.get('deg')
    wind_gust = wind_data.get('gust') # Extended metric
    
    cloudiness = data.get('clouds', {}).get('all') # Extended metric
    rain_1h = data.get('rain', {}).get('1h', 0)
    snow_1h = data.get('snow', {}).get('1h', 0)
    
    sunrise_utc = data.get('sys', {}).get('sunrise')
    sunset_utc = data.get('sys', {}).get('sunset')

    # 2. Process and Format Data
    unit_symbol = "°C" if UNITS == "metric" else "°F"
    
    weather_emoji = WEATHER_EMOJIS.get(main_weather, "❓")
    full_condition = f"{weather_emoji} ({description})"
    
    wind_dir = get_wind_direction(wind_deg)
    visibility_km = f"{visibility / 1000:.1f} km" if visibility is not None else 'N/A'
    
    sunrise_local = convert_timestamp_to_local(sunrise_utc, timezone_offset)
    sunset_local = convert_timestamp_to_local(sunset_utc, timezone_offset)
    
    # 3. Display in Streamlit
    
    st.markdown(f"## 🌎 Current Weather in {city_name}, {country_code.upper()}")
    
    col1_main, col2_main = st.columns([1, 1])
    
    with col1_main:
        st.markdown(f"### {full_condition}")
        st.markdown(f"**Temperature:** **{temp:.1f} {unit_symbol}**")
        st.markdown(f"**Feels Like:** {feels_like:.1f} {unit_symbol}")
        
    with col2_main:
        st.markdown("### 🌅 Sun Times")
        st.metric(label="Sunrise", value=sunrise_local.strftime('%H:%M:%S') if sunrise_local else 'N/A')
        st.metric(label="Sunset", value=sunset_local.strftime('%H:%M:%S') if sunset_local else 'N/A')
        
    st.divider()

    st.markdown("### 🌡️ Temperature and 💨 Wind") 
    col3, col4, col5 = st.columns(3)
    
    col3.metric("Min/Max Temp (Day)", f"{temp_min:.1f} / {temp_max:.1f} {unit_symbol}")
    col4.metric("Wind Speed", f"{wind_speed} m/s")
    col5.metric("Wind Direction", f"{wind_dir} ({wind_deg}º)" if wind_deg is not None else 'N/A')

    st.divider()

    st.markdown("### 🌬️ Atmospheric Conditions (Extended)") 
    
    # Row 1: Pressure, Humidity, Visibility
    col6, col7, col8 = st.columns(3)
    col6.metric("Pressure", f"{pressure} hPa")
    col7.metric("Humidity", f"{humidity} %")
    col8.metric("Visibility", visibility_km)

    # Row 2: Cloudiness, Wind Gust, Precipitation
    col9, col10, col11 = st.columns(3)
    col9.metric("Cloudiness", f"{cloudiness} %" if cloudiness is not None else 'N/A')
    col10.metric("Wind Gust", f"{wind_gust} m/s" if wind_gust is not None else "N/A")
    col11.metric("Precipitation (1hr)", f"{rain_1h + snow_1h:.2f} mm")


def display_forecast(data, timezone_offset):
    """Parses forecast data, groups it by day, and displays it in Streamlit tabs with custom-styled "weather cards"."""
    
    forecast_list = data.get('list', [])
    if not forecast_list:
        st.warning("No forecast data available for this location.")
        return

    forecast_rows = []
    
    for item in forecast_list:
        dt_utc = item.get('dt')
        dt_local = convert_timestamp_to_local(dt_utc, timezone_offset)
        if dt_local is None: continue

        main = item.get('main', {})
        weather = item.get('weather', [{}])[0]
        wind = item.get('wind', {})
        
        main_weather_group = weather.get('main', 'N/A')
        
        row = {
            "Time": dt_local.strftime('%H:%M'),
            "MainCondition": main_weather_group,
            "ConditionEmoji": WEATHER_EMOJIS.get(main_weather_group, '❓'),
            "ConditionDescription": weather.get('description', 'N/A').capitalize(),
            "Temp": main.get('temp', np.nan),
            "FeelsLike": main.get('feels_like', np.nan),
            "Humidity": main.get('humidity', np.nan),
            "WindSpeed": wind.get('speed', np.nan),
            "WindDeg": wind.get('deg', np.nan),
            "FilterDate": dt_local.date()
        }
        forecast_rows.append(row)

    df_forecast = pd.DataFrame(forecast_rows)
    
    unique_dates = df_forecast['FilterDate'].unique()
    
    tab_titles = []
    for i, date in enumerate(unique_dates):
        if i == 0:
            title = "Today"
        elif i == 1:
            title = "Tomorrow"
        else:
            title = datetime.datetime.strptime(str(date), '%Y-%m-%d').strftime('%A')
        tab_titles.append(f"{title} ({date.strftime('%b %d')})")
        
    tabs = st.tabs(tab_titles)
    
    # Layout Fix: 4 cards per row
    cols_per_row = 4 
    
    for i, date in enumerate(unique_dates):
        with tabs[i]:
            st.markdown(f"### Hourly Forecast for {tab_titles[i]}")
            
            # Filter the DataFrame for the current day
            df_day = df_forecast[df_forecast['FilterDate'] == date].copy()
            
            # FIX: Process the cards sequentially in chunks of 4 to ensure left-to-right order.
            num_cards = len(df_day)
            num_rows = (num_cards + cols_per_row - 1) // cols_per_row
            
            for row_idx in range(num_rows):
                # Create a new set of columns for each row
                current_cols = st.columns(cols_per_row)
                
                # Process the 4 cards (or fewer for the last row)
                start_card_index = row_idx * cols_per_row
                end_card_index = min(start_card_index + cols_per_row, num_cards)
                
                for col_offset, internal_idx in enumerate(range(start_card_index, end_card_index)):
                    
                    hour_data = df_day.iloc[internal_idx] # Access data by internal numerical index
                    
                    # Determine the style based on the main weather condition
                    style = CARD_STYLES.get(hour_data['MainCondition'], CARD_STYLES["Default"])
                    wind_dir = get_wind_direction(hour_data['WindDeg'])
                    
                    # --- HTML/CSS Card Generation ---
                    # The font color is set by the 'color: inherit' and controlled by the 
                    # main style property in CARD_STYLES.
                    html_card = f"""
                    <div style="padding: 15px; border-radius: 10px; box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1); {style}">
                        <h5 style="margin-top: 0; margin-bottom: 5px; color: inherit;">{hour_data['Time']}</h5>
                        <p style="font-size: 1.0em; margin-bottom: 5px; color: inherit;">
                            <b>{hour_data['ConditionEmoji']} {hour_data['ConditionDescription']}</b>
                        </p>
                        <p style="margin: 3px 0; font-size: 0.9em; color: inherit;">
                            🌡️ <b>{hour_data['Temp']:.1f}°C</b> (Feels: {hour_data['FeelsLike']:.1f}°C)
                        </p>
                        <p style="margin: 3px 0; font-size: 0.9em; color: inherit;">
                            💧 Humidity: {hour_data['Humidity']:.0f}%
                        </p>
                        <p style="margin: 3px 0; font-size: 0.9em; color: inherit;">
                            💨 Wind: {hour_data['WindSpeed']:.1f} m/s {wind_dir}
                        </p>
                    </div>
                    """
                    
                    # Place the raw HTML into the current column
                    with current_cols[col_offset]:
                        st.markdown(html_card, unsafe_allow_html=True)
                        st.markdown("", unsafe_allow_html=True) 


# --- STREAMLIT APP LAYOUT (main function) ---

def main():
    st.set_page_config(page_title="Streamlit Weather App (Extended)", layout="wide")
    st.title("Local Weather App with OWM Forecast 🗺️")
    st.markdown("---")

    # Load the city data, sorted country names, and the mapping dict
    city_df, sorted_country_names, country_map = load_and_process_city_data()
    
    # --- Sidebar/Input Area ---
    st.sidebar.header("Select Location")
    
    # 1. Country Selection (Uses full names)
    selected_country_name = st.sidebar.selectbox(
        "Select Country",
        sorted_country_names,
        index=sorted_country_names.index("United States") if "United States" in sorted_country_names else 0,
        key="country_name_select"
    )
    
    # Get the Alpha-2 code
    selected_country_code = country_map.get(selected_country_name, "US")
    
    # 2. Filter Cities
    filtered_cities_df = city_df[city_df['CountryName'] == selected_country_name]
    city_names = filtered_cities_df['City'].unique().tolist()
    city_names.sort()

    # 3. City Selection
    st.sidebar.markdown(f"***Select City in {selected_country_name} ({len(city_names)} cities listed)***")
    
    selected_city_name = st.sidebar.selectbox(
        "City Name",
        options=city_names,
        index=0,
        key="city_name_select"
    )

    fetch_button = st.sidebar.button("Fetch Weather", type="primary")

    st.sidebar.markdown("---")
    st.sidebar.info("The city list is loaded once on app startup for fast filtering.")

    # --- Main Content Area ---
    
    if fetch_button and selected_city_name:
        with st.spinner(f"Getting data for {selected_city_name}, {selected_country_name}..."):
            
            current_weather_data = get_current_weather_data(selected_city_name, selected_country_code)
            
            if current_weather_data:
                # Display Current Weather and Extended Metrics
                display_weather(current_weather_data)
                
                st.header("5-Day Forecast: Hourly Breakdown 🗓️")
                
                # Fetch and Display Forecast
                forecast_data = get_forecast_data(selected_city_name, selected_country_code)
                if forecast_data:
                    timezone_offset = current_weather_data.get('timezone', 0)
                    display_forecast(forecast_data, timezone_offset)
                
    elif not selected_city_name and fetch_button:
        st.warning("Please select a city from the list.")
        
    else:
        st.info("👈 Select a country and a city from the dropdowns to view the current weather and 5-day forecast!")

if __name__ == "__main__":
    main()