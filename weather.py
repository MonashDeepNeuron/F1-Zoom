import requests

API_KEY = "419e6250c392ccd52db1c706da0cdca3"   # <-- replace with your key
CITY = "Monza,IT"          # You can also use "London,UK" or lat/lon coordinates
URL = f"http://api.openweathermap.org/data/2.5/forecast?q={CITY}&appid={API_KEY}&units=metric"

response = requests.get(URL)
data = response.json()

print(data)

# Just take the first forecast entry (next 3 hours)
forecast = data['list'][0]

temp = forecast['main']['temp']
humidity = forecast['main']['humidity']
wind_speed = forecast['wind']['speed']
wind_deg = forecast['wind']['deg']
rain_prob = forecast.get('pop', 0) * 100  # convert 0–1 to %
rain_intensity = forecast.get('rain', {}).get('3h', 0)  # mm in 3h

# Categorize rain intensity
if rain_intensity == 0:
    rain_category = "No rain"
elif rain_intensity < 2.5:
    rain_category = "Light rain"
elif rain_intensity < 10:
    rain_category = "Moderate rain"
else:
    rain_category = "Heavy rain"

print(f"City: {CITY}")
print(f"Temperature: {temp} C")
print(f"Humidity: {humidity}%")
print(f"Wind: {wind_speed} m/s, {wind_deg} degrees")
print(f"Rain Probability: {rain_prob:.1f}%")
print(f"Rain Intensity: {rain_intensity} mm/3h -> {rain_category}")
