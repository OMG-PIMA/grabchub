import json
import base64
from PIL import Image

def get_card_tuple(image_path):
    try:
        img = Image.open(image_path)
        
        # Look in img.text first, fallback to img.info
        metadata = img.text if hasattr(img, 'text') else img.info
        
        if 'chara' not in metadata:
            return ("Error", "No 'chara' metadata found in this PNG.")
            
        # Extract the Base64 string
        raw_b64 = metadata['chara']
        
        # Pad the Base64 string if necessary to prevent decoding errors
        raw_b64 += "=" * ((4 - len(raw_b64) % 4) % 4)
        
        # Decode the Base64 into bytes, then parse the JSON
        decoded_bytes = base64.b64decode(raw_b64)
        json_data = json.loads(decoded_bytes.decode('utf-8'))
        
        # V2 cards nest the character info inside a 'data' dictionary
        char_info = json_data.get("data", json_data)
        
        # Isolate the title and the body
        title = char_info.get("name", "Unknown Title")
        
        # Cards vary, so we check for description first, then personality
        body = char_info.get("description", char_info.get("personality", "No body text found"))
        
        # Return the parsed data as a tuple
        return (title, body)
        
    except Exception as e:
        return ("Error", f"Failed to parse card data: {e}")

if __name__ == "__main__":
    # Ensure this points to the correct file path
    char_tuple = get_card_tuple("chub_cards/Dr. Kylie Hong_318323.png")
    
    print(char_tuple)
