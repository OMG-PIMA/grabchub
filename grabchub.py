import requests
import time
import os
import random
import json

ROOT_DIR="/Volumes/FASTDATA"

# Create distinct subdirectories for organized file storage
PNG_DIR = os.path.join(ROOT_DIR, "chub_cards", "png")
JSON_DIR = os.path.join(ROOT_DIR, "chub_cards", "json")

os.makedirs(PNG_DIR, exist_ok=True)
os.makedirs(JSON_DIR, exist_ok=True)

API_URL = "https://ro.chub.ai/search"

# Initialize session with exact browser-spoofing headers
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:152.0) Gecko/20100101 Firefox/152.0",
    "Accept": "application/json",
    "Origin": "https://chub.ai",
    "Referer": "https://chub.ai/",
    "Content-Type": "application/json",
    "ch-api-key": "f33c8294-fe07-46ad-9759-92ca715303ed",
    "samwise": "f33c8294-fe07-46ad-9759-92ca715303ed" 
})

# Scan both subdirectories to populate the fast memory lookup cache
existing_pngs = set(os.listdir(PNG_DIR))
existing_jsons = set(os.listdir(JSON_DIR))
ghost_cards = set()

def download_image(image_url, filename, char_name, base_filename):
    """Downloads the high-resolution PNG file."""
    if image_url in ghost_cards:
        return
        
    try:
        response = session.get(image_url, stream=True)
        
        if response.status_code == 404:
            print(f"Skipping PNG for '{char_name}' - The creator deleted the image (404).")
            ghost_cards.add(image_url)
            return
            
        response.raise_for_status()
        
        with open(filename, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
                
        print(f"[NEW FILE] Successfully saved PNG: {filename}")
        existing_pngs.add(base_filename) 
        
    except Exception as e:
        print(f"Failed to download PNG for {char_name}: {e}")

def download_json(full_path, filename, char_name, base_filename):
    """Downloads the full, un-truncated character metadata JSON."""
    try:
        api_target = f"https://api.chub.ai/api/characters/{full_path}"
        response = session.get(api_target)
        
        if response.status_code == 404:
            print(f"Skipping JSON for '{char_name}' - Character deleted or hidden (404).")
            return
            
        response.raise_for_status()
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(response.json(), f, indent=4)
            
        print(f"[NEW FILE] Successfully saved JSON: {filename}")
        existing_jsons.add(base_filename)
        
    except Exception as e:
        print(f"Failed to download JSON for {char_name}: {e}")

def crawl_directory(start_page=1):
    print("\n=========================================")
    print("STARTING GLOBAL WGET-STYLE DIRECTORY CRAWL")
    print("=========================================")
    
    page = start_page
    
    while True:
        print(f"--- Crawling Global Feed - Page {page} ---")
        
        query_params = {
            "sort": "id",             
            "min_users_chatted": 0,   
            "min_tokens": 0,          
            "include_forks": "true",
            "max_tokens": 5000,
            "excludetopics": "",
            "search": "",             
            "page": page, 
            "first": 50,              
            "namespace": "characters",
            "nsfw": "true",
            "nsfw_only": "false",
            "min_tags": 0,            
            "nsfl": "true",
            "count": "false",
            "bypass": "true"
        }
        
        try:
            response = session.post(API_URL, params=query_params, json={})
            response.raise_for_status()
            
            data = response.json()
            characters = data.get("data", {}).get("nodes", [])
            
            if not characters:
                print("\nReached the end of the accessible global index. Crawl complete!")
                break
                
            for char in characters:
                name = char.get("name", "Unknown").replace("/", "-").replace("\\", "-").replace(":", "-")
                char_id = char.get("id", "no_id")
                card_url = char.get("max_res_url") 
                full_path = char.get("fullPath")
                
                # Pre-calculate filenames to run the cache check
                base_json_name = f"{name}_{char_id}.json"
                base_png_name = f"{name}_{char_id}.png"
                
                # Short-Circuit logic: skip entirely if we have either asset locally
                if base_json_name in existing_jsons or base_png_name in existing_pngs:
                    continue
                
                # 1. Handle JSON Download Isolation
                if full_path:
                    json_filepath = os.path.join(JSON_DIR, base_json_name)
                    download_json(full_path, json_filepath, name, base_json_name)
                    time.sleep(0.5) 
                
                # 2. Handle PNG Download Isolation
                if card_url and card_url.endswith(".png"):
                    png_filepath = os.path.join(PNG_DIR, base_png_name)
                    download_image(card_url, png_filepath, name, base_png_name)
                    time.sleep(0.5) 
                
        except Exception as e:
            print(f"Error communicating with API on page {page}: {e}")
            time.sleep(5.0)
            
        page += 1
        delay = random.uniform(2.0, 5.0)
        time.sleep(delay)

if __name__ == "__main__":
    crawl_directory(start_page=1)