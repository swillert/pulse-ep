import requests

BASE_URL = "http://127.0.0.1:5000"  # Replace with your server's URL if different


# Authentication (replace with actual username and password)
def authenticate(username, password):
    login_url = f"{BASE_URL}/login_user"
    response = requests.post(login_url, json={"username": username, "password": password})
    response.raise_for_status()  # Raise an error for bad responses
    return response.json()["access_token"]


# Fetch Mesh Data
def fetch_mesh_data(token, map_id, distance, scalar_name="act"):
    url = f"{BASE_URL}/get_mesh_data"
    headers = {"Authorization": f"Bearer {token}"}
    params = {"map_id": map_id, "distance": distance, "scalar_name": scalar_name}
    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()  # Raise an error for bad responses
    return response.json()


def analyze_structure(data, indent=0):
    """
    Recursively analyze the structure of the JSON data
    and print the keys and their data types.
    """
    indent_str = "  " * indent
    if isinstance(data, dict):
        for key, value in data.items():
            print(f"{indent_str}{key}: {type(value).__name__}")
            analyze_structure(value, indent + 1)
    elif isinstance(data, list):
        if len(data) > 0:
            print(f"{indent_str}List of {len(data)} items")
            analyze_structure(data[0], indent + 1)  # Analyze the first item as a representative
        else:
            print(f"{indent_str}Empty list")
    else:
        print(f"{indent_str}{data}")


def compare_scalar_data(act_data, vol_data):
    """
    Compare act and vol scalar data arrays and print if they are the same or different.
    """
    if len(act_data) != len(vol_data):
        print("The lengths of the act and vol data arrays are different.")
        return False

    for i in range(len(act_data)):
        if act_data[i] != vol_data[i]:
            print(f"Difference found at index {i}: act = {act_data[i]}, vol = {vol_data[i]}")
            return False

    print("The act and vol data arrays are the same.")
    return True


def main():
    username = "sw"  # Replace with actual username
    password = "abraxas"  # Replace with actual password

    # Authenticate and get token
    token = authenticate(username, password)
    print("Access Token:", token)

    # Fetch mesh data for a specific map for "act" and "vol"
    map_id = 1  # Replace with actual map_id
    distance = 5

    act_data = fetch_mesh_data(token, map_id, distance, scalar_name="act")
    vol_data = fetch_mesh_data(token, map_id, distance, scalar_name="vol")

    print("\n--- act_data Structure ---")
    analyze_structure(act_data)

    print("\n--- vol_data Structure ---")
    analyze_structure(vol_data)

    # Compare scalar_data of act and vol
    if "scalar_data" in act_data and "scalar_data" in vol_data:
        compare_scalar_data(act_data["scalar_data"], vol_data["scalar_data"])
    else:
        print("Error: scalar_data not found in the fetched data.")


if __name__ == "__main__":
    main()
