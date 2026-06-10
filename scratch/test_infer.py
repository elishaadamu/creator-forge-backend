import requests, base64

invoke_url="http://localhost:8000/v1/infer"
output_image_path="scratch/result.jpg"

headers = {
    "Accept": "application/json",
}

payload = {
    "prompt": "A simple coffee shop interior",
    "seed": 0
}

print("Sending request to local backend...")
response = requests.post(invoke_url, headers=headers, json=payload)
response.raise_for_status()
response_body = response.json()

img_bytes = base64.b64decode(response_body['artifacts'][0]["base64"])
with open(output_image_path, "wb") as f:
    f.write(img_bytes)

print(f"Success! Image saved to {output_image_path}")
