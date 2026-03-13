import requests

url = "http://localhost:8000/api/v1/dashboard/calendar?year=2026&month=3"
response = requests.get(url)
print(response.json())
