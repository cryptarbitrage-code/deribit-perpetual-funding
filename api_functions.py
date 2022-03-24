import json
import requests
from settings import api_exchange_address


def get_funding_rate_history(instrument, start_timestamp, end_timestamp):
    url = "/api/v2/public/get_funding_rate_history"
    parameters = {'instrument_name': instrument,
                  'start_timestamp': start_timestamp,
                  'end_timestamp': end_timestamp}
    # send HTTPS GET request
    json_response = requests.get((api_exchange_address + url + "?"), params=parameters)
    response_dict = json.loads(json_response.content)
    funding_details = response_dict["result"]

    return funding_details
