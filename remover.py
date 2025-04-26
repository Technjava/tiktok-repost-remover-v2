from TikTokApi import TikTokApi
from urllib.parse import urlencode, quote
import asyncio
import os
from datetime import datetime, timedelta
import requests
import json
import sys
import traceback
import colorama
from colorama import Fore, Style, Back
import logging
from typing import List, Dict, Any, Tuple
import time
import platform

colorama.init(autoreset=True)

class ColoredFormatter(logging.Formatter):
    """Custom formatter that adds colors to log messages based on level"""
    
    COLORS = {
        'DEBUG': Fore.CYAN,
        'INFO': Fore.GREEN,
        'WARNING': Fore.YELLOW,
        'ERROR': Fore.RED,
        'CRITICAL': Fore.RED + Back.WHITE
    }
    
    def format(self, record):
        log_message = super().format(record)
        return f"{self.COLORS.get(record.levelname, Fore.WHITE)}{log_message}{Style.RESET_ALL}"

logger = logging.getLogger("TikTok")
logger.setLevel(logging.INFO)

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_formatter = ColoredFormatter("%(message)s")
console_handler.setFormatter(console_formatter)
logger.addHandler(console_handler)

ms_token = "" # ms_token can be obtained by logging in to TikTok and using the browser's developer tools to inspect network requests.
REQUEST_DELAY = 1  # Seconds to wait between requests

# Common cookies for authentication
EXTRA_COOKIES = {
    "sid_tt": "" # Find it by using your browser's developer tools and go to your profile with the panel opened, and find a /items query and look into cookies
}

def get_common_headers(username: str, cookies: Dict[str, str], is_delete: bool = False) -> Dict[str, str]:
    """
    Get common headers for TikTok API requests.
    """
    cookie_header = "; ".join([f"{k}={v}" for k, v in cookies.items()])
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:137.0) Gecko/20100101 Firefox/137.0",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.5",
        "Referer": f"https://www.tiktok.com/@{username}",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "Connection": "keep-alive",
        "Pragma": "no-cache",
        "Cache-Control": "no-cache",
        "TE": "trailers",
        "Priority": "u=4",
        "Cookie": cookie_header
    }
    
    if is_delete:
        headers["Origin"] = "https://www.tiktok.com"
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        headers["Content-Length"] = "0"
        headers["Priority"] = "u=0"
        
    return headers

async def fetch_repost_page(api, session_index, session, sec_uid, cursor, username):
    """
    Fetches a single page of reposts using the provided session and cursor.
    
    Returns a tuple of (items, cursor, has_more)
    """
    params = session.params.copy()
    
    cookies = await api.get_session_cookies(session)
    webIdLastTime = datetime.now().timestamp() * 1000
    
    url = "https://www.tiktok.com/api/repost/item_list/"
    
    if params.get("msToken") is None:
        params["msToken"] = ms_token
            
    params["secUid"] = sec_uid
    params["cursor"] = cursor
    params["count"] = 30
    params["coverFormat"] = 0
    params["data_collection_enabled"] = "true"
    params["needPinnedItemIds"] = "true"
    params["odinId"] = cookies.get("odin_tt")
    params["post_item_list_request_type"] = 0
    params["user_is_login"] = "true"
    
    encoded_params = f"{url}?WebIdLastTime={webIdLastTime}&{urlencode(params, safe='=', quote_via=quote)}"
    signed_url = await api.sign_url(encoded_params, session_index=session_index)
    
    cookies.update(EXTRA_COOKIES)
    
    request_headers = get_common_headers(username, cookies)
    
    try:
        response = requests.get(signed_url, headers=request_headers)
        response.cookies.update(cookies)
        
        if response.status_code != 200:
            logger.error(f"API request failed: {response.status_code} - {response.text[:100]}...")
            return [], cursor, False
        
        data = response.json()
        
        if "statusCode" in data and data["statusCode"] != 0:
            logger.error(f"API error: {data.get('statusMsg', 'Unknown')}")
            return [], cursor, False
        
        items = data.get("itemList", [])
        next_cursor = data.get("cursor", cursor)
        has_more = data.get("hasMore", False)
        
        more_status = "more available" if has_more else "complete"
        logger.info(f"📋 Retrieved {len(items)} reposts, next cursor: {next_cursor}, status: {more_status}")
        
        if len(items) == 0 and has_more:
            print(data)
        
        return items, next_cursor, has_more
        
    except Exception as e:
        logger.error(f"Error fetching reposts: {str(e)}")
        return [], cursor, False

async def delete_single_repost(api, session_index, session, username, video_id):
    """
    Deletes a single repost from TikTok.
    
    Returns: bool indicating success/failure
    """
    try:
        params = session.params.copy()
        
        cookies = await api.get_session_cookies(session)
        webIdLastTime = datetime.now().timestamp() * 1000
        
        url = "https://www.tiktok.com/tiktok/v1/upvote/delete"
        
        if params.get("msToken") is None:
            params["msToken"] = ms_token
                
        params["item_id"] = video_id
        params["odinId"] = cookies.get("odin_tt")
        params["user_is_login"] = "true"
        
        encoded_params = f"{url}?WebIdLastTime={webIdLastTime}&{urlencode(params, safe='=', quote_via=quote)}"
        signed_url = await api.sign_url(encoded_params, session_index=session_index)
        
        cookies.update(EXTRA_COOKIES)
        
        request_headers = get_common_headers(username, cookies, is_delete=True)
        
        response = requests.post(signed_url, headers=request_headers)
        response.cookies.update(cookies)
        
        if response.status_code != 200:
            logger.error(f"Delete request failed: {response.status_code}")
            return False
            
        result = response.json()
        if result.get("status_code", -1) == 0:
            return True
        else:
            logger.warning(f"Delete API error: {result.get('status_msg', 'Unknown')}")
            return False
            
    except Exception as e:
        logger.error(f"Delete error: {str(e)}")
        return False

async def delete_reposts(reposts, keep_count, username):
    """
    Deletes reposts from TikTok, keeping the specified number of most recent reposts.
    """
    to_keep = reposts[:keep_count]
    to_delete = reposts[keep_count:]
    
    logger.info(f"🔒 Keeping {len(to_keep)} most recent reposts")
    logger.info(f"🗑️ Preparing to delete {len(to_delete)} older reposts")
    
    if not to_delete:
        logger.info("No reposts to delete.")
        return 0
        
    success_count = 0
    filename = f"reposts_{username}.json"
    start_time = time.time()
    
    async with TikTokApi() as api:
        logger.info("🔄 Initializing TikTok API...")
        await api.create_sessions(ms_tokens=[ms_token], num_sessions=1, sleep_after=3, browser=os.getenv("TIKTOK_BROWSER", "chromium"))
        
        session_index, session = api._get_session()
        logger.info("✅ API session ready")
        
        all_reposts = reposts.copy()
        
        for i, repost in enumerate(to_delete):
            try:
                # Calculate ETA
                elapsed = time.time() - start_time
                avg_time_per_request = elapsed / (i + 1) if i > 0 else REQUEST_DELAY
                remaining_count = len(to_delete) - i
                eta_seconds = avg_time_per_request * remaining_count
                eta = str(timedelta(seconds=int(eta_seconds)))
                
                video_id = repost.get("video", {}).get("id")
                
                if not video_id:
                    logger.warning(f"⚠️ Missing video ID in repost {i+1}")
                    continue
                
                logger.info(f"🗑️ Deleting repost {i+1}/{len(to_delete)} (ID: {video_id}) | Remaining: {remaining_count} | ETA: {eta}")
                
                success = await delete_single_repost(api, session_index, session, username, video_id)
                
                if success:
                    success_count += 1
                    
                    index_to_remove = keep_count + i
                    
                    if index_to_remove < len(all_reposts):
                        all_reposts.pop(index_to_remove)
                        
                        await save_reposts_to_file(all_reposts, filename)
                        logger.info(f"✅ Repost deleted successfully, file updated")
                else:
                    logger.warning(f"❌ Failed to delete repost {i+1}")
                
                await asyncio.sleep(REQUEST_DELAY)
                
            except Exception as e:
                logger.error(f"Error processing repost {i+1}: {str(e)}")
    
    total_elapsed = time.time() - start_time
    rate = success_count / total_elapsed if total_elapsed > 0 else 0
    
    logger.info(f"\n{Fore.GREEN}✅ Deletion complete: {success_count}/{len(to_delete)} reposts deleted " + 
                f"({rate:.2f} reposts/sec)")
    return success_count

def clear_terminal():
    """Clear the terminal screen based on the operating system."""
    if platform.system() == "Windows":
        os.system("cls")
    else:
        os.system("clear")

async def fetch_all_reposts(username):
    """
    Fetches all reposts for a user by paginating through all available pages.
    """
    all_reposts = []
    
    logger.info(f"🔍 Fetching reposts for @{username}...")
    
    async with TikTokApi() as api:
        logger.info("🔄 Initializing TikTok API...")
        await api.create_sessions(ms_tokens=[ms_token], num_sessions=1, sleep_after=3, browser=os.getenv("TIKTOK_BROWSER", "chromium"))
        
        logger.info(f"🔍 Looking up user info...")
        user_data = await api.user(username=username).info()
        sec_uid = user_data.get("userInfo", {}).get("user", {}).get("secUid")
        
        if not sec_uid:
            logger.error(f"❌ Could not find user @{username}")
            return []
            
        logger.info(f"✅ Found user @{username}")
        
        session_index, session = api._get_session()
        
        current_cursor = 0
        has_more = True
        page = 1
        start_time = time.time()
        
        empty_retry_count = 0
        MAX_EMPTY_RETRIES = 50
        
        while has_more:
            clear_terminal()
            
            print_banner()
            logger.info(f"🔍 Fetching reposts for @{username}...")
            logger.info(f"📋 Fetching page {page}... (cursor: {current_cursor})")
            
            if empty_retry_count > 0:
                logger.warning(f"⚠️ Retry {empty_retry_count}/{MAX_EMPTY_RETRIES} for empty page with cursor {current_cursor}")
            
            items, next_cursor, has_more = await fetch_repost_page(
                api, session_index, session, sec_uid, current_cursor, username
            )
            
            if len(items) == 0 and has_more:
                empty_retry_count += 1
                
                if empty_retry_count < MAX_EMPTY_RETRIES:
                    logger.warning(f"⏳ Empty page but more data available. Retrying with same cursor {current_cursor}...")
                    wait_time = REQUEST_DELAY * (1 + empty_retry_count)
                    logger.info(f"⏱️ Waiting {wait_time}s before retry...")
                    await asyncio.sleep(wait_time)
                    continue  
                else:
                    logger.warning(f"⚠️ Reached maximum retries ({MAX_EMPTY_RETRIES}) for cursor {current_cursor}")
                    logger.info(f"➡️ Moving to next cursor {next_cursor}")
                    current_cursor = next_cursor
                    empty_retry_count = 0
                    page += 1
                    await asyncio.sleep(REQUEST_DELAY)
                    continue
            
            empty_retry_count = 0
            
            all_reposts.extend(items)
            
            total = len(all_reposts)
            more_status = f"{Fore.YELLOW}more available" if has_more else f"{Fore.GREEN}complete"
            logger.info(f"📊 Total reposts: {total} | Status: {more_status}")
            
            current_cursor = next_cursor
            page += 1
            
            if has_more:
                wait_time = REQUEST_DELAY
                logger.info(f"⏱️ Waiting {wait_time}s before next page...")
                await asyncio.sleep(wait_time)
    
    elapsed = time.time() - start_time
    rate = len(all_reposts) / elapsed if elapsed > 0 else 0
    logger.info(f"✅ Retrieved {len(all_reposts)} total reposts in {elapsed:.1f}s ({rate:.1f} reposts/sec)")
    
    return all_reposts

async def save_reposts_to_file(reposts: List[Dict[str, Any]], filename: str = "reposts.json"):
    """
    Saves the list of reposts to a JSON file.
    """
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(reposts, f, ensure_ascii=False, indent=2)
        logger.debug(f"Saved {len(reposts)} reposts to {filename}")
        return True
    except Exception as e:
        logger.error(f"Error saving file: {str(e)}")
        return False

def load_reposts_from_file(filename: str = "reposts.json") -> List[Dict[str, Any]]:
    """
    Loads reposts from a JSON file.
    """
    try:
        with open(filename, "r", encoding="utf-8") as f:
            reposts = json.load(f)
        logger.info(f"📂 Loaded {len(reposts)} reposts from {filename}")
        return reposts
    except FileNotFoundError:
        logger.error(f"❌ File {filename} not found")
        return []
    except json.JSONDecodeError:
        logger.error(f"❌ File {filename} contains invalid JSON")
        return []

def get_user_input(prompt: str, options: List[str] = None) -> str:
    """
    Gets user input with optional validation against a list of valid options.
    """
    while True:
        user_input = input(f"{Fore.CYAN}{prompt}{Style.RESET_ALL}").strip()
        if not options or user_input.lower() in [option.lower() for option in options]:
            return user_input
        logger.warning(f"Invalid input. Please enter one of: {', '.join(options)}")

def print_banner():
    """Print a stylish banner"""
    banner = f"""
{Fore.MAGENTA}╔════════════════════════════════════════════════╗
{Fore.MAGENTA}║  {Fore.CYAN}TikTok Reposts Manager v1.0                  {Fore.MAGENTA}║
{Fore.MAGENTA}║  {Fore.WHITE}Fetch, manage and clean up your TikTok reposts  {Fore.MAGENTA}║
{Fore.MAGENTA}╚════════════════════════════════════════════════╝{Style.RESET_ALL}
    """
    print(banner)

async def main():
    """Main execution function."""
    try:
        print_banner()
        
        action = get_user_input(
            "What would you like to do?\n"
            f"  {Fore.GREEN}1. Fetch reposts from a TikTok user\n"
            f"  {Fore.YELLOW}2. Load reposts from a file\n"
            f"  {Fore.RED}3. Delete reposts{Style.RESET_ALL}\n"
            "Enter choice (1, 2, or 3): ", 
            ["1", "2", "3"]
        )
        
        username = get_user_input("Enter TikTok username: ")
        filename = f"reposts_{username}.json"
        
        if action == "1":
            reposts = await fetch_all_reposts(username)
            
            if reposts:
                await save_reposts_to_file(reposts, filename=filename)
                logger.info(f"💾 Saved {len(reposts)} reposts to {filename}")
            else:
                logger.warning("No reposts were found")
                
        elif action == "2":
            reposts = load_reposts_from_file(filename)
            
            if not reposts:
                logger.warning(f"No reposts found in {filename}")
                
        elif action == "3":
            reposts = load_reposts_from_file(filename)
            
            if not reposts:
                logger.error(f"No reposts found in {filename}. Please fetch reposts first.")
                return
                
            logger.info(f"Found {len(reposts)} reposts in {filename}")
            
            confirm = get_user_input(
                f"{Fore.RED}⚠️ WARNING: Are you sure you want to delete reposts? This action cannot be undone. (yes/no): {Style.RESET_ALL}",
                ["yes", "no"]
            )
            
            if confirm.lower() != "yes":
                logger.info("Deletion cancelled.")
                return
                
            try:
                keep_count = int(get_user_input("How many recent reposts do you want to keep? "))
                if keep_count < 0:
                    keep_count = 0
                    logger.info("Using 0 as the keep count.")
                elif keep_count > len(reposts):
                    logger.warning(f"Keep count ({keep_count}) is greater than the total number of reposts ({len(reposts)}). No reposts will be deleted.")
                    return
                    
                deleted_count = await delete_reposts(reposts, keep_count, username)
                if deleted_count > 0:
                    logger.info(f"🎉 Successfully deleted {deleted_count} reposts!")
                else:
                    logger.warning("No reposts were deleted.")
                
            except ValueError:
                logger.error("Invalid input. Please enter a number.")
                return
        
    except KeyboardInterrupt:
        logger.info("\n👋 Operation cancelled by user.")
    except Exception as e:
        logger.error(f"Error occurred: {str(e)}")
        logger.debug(traceback.format_exc())

if __name__ == "__main__":
    asyncio.run(main())
