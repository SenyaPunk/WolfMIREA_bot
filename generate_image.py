import json
import time
import base64
import requests


class FusionBrainAPI:
    def __init__(self, url, api_key, secret_key):
        self.URL = url
        self.AUTH_HEADERS = {
            'X-Key': f'Key {api_key}',
            'X-Secret': f'Secret {secret_key}',
        }

    def get_pipeline(self):
        response = requests.get(self.URL + 'key/api/v1/pipelines', headers=self.AUTH_HEADERS)
        if response.status_code != 200:
            print(f"Ошибка {response.status_code}: {response.text}")
            return None
        data = response.json()
        return data[0]['id']

    def generate(self, prompt, pipeline_id, images=1, width=1024, height=1024):
        params = {
            "type": "GENERATE",
            "numImages": images,
            "width": width,
            "height": height,
            "generateParams": {
                "query": prompt
            }
        }

        data = {
            'pipeline_id': (None, pipeline_id),
            'params': (None, json.dumps(params), 'application/json')
        }

        response = requests.post(self.URL + 'key/api/v1/pipeline/run', headers=self.AUTH_HEADERS, files=data)

        if response.status_code not in (200, 201):
            print(f"Ошибка {response.status_code}: {response.text}")
            return None

        try:
            return response.json()['uuid']
        except Exception as e:
            print("Не удалось получить uuid:", e)
            print("Ответ сервера:", response.text)
            return None


    def check_generation(self, request_id, attempts=10, delay=10):
        while attempts > 0:
            response = requests.get(self.URL + 'key/api/v1/pipeline/status/' + request_id, headers=self.AUTH_HEADERS)
            if response.status_code != 200:
                print(f"Ошибка {response.status_code}: {response.text}")
                return None

            data = response.json()
            if data['status'] == 'DONE':
                return data['result']['files']

            attempts -= 1
            time.sleep(delay)

        return None


