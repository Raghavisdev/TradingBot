import requests

BASE_URL = "https://frontend-api.pump.fun/coins/"


def get_pumpfun_data(contract):

    url = BASE_URL + contract

    print("URL:", url)

    response = requests.get(url)

    print("Status Code:", response.status_code)

    print("Response:")
    print(response.text)

    if response.status_code != 200:
        return None

    return response.json()