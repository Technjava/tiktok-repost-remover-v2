# 📋 TikTok Reposts Manager

A Python tool to **fetch, manage, and delete reposts** on a TikTok account via the TikTok web API.  
It uses the `TikTokApi` and requires browser cookies and a valid `ms_token` for authentication.

## ✨ Features

- Fetch all reposts from a specific TikTok user
- Save reposts to a JSON file
- Load reposts from a saved file
- Delete all but the latest N reposts
- Progress logs with ETA and colored console output

---

## 📦 Requirements

- Python 3.8+
- TikTokApi (`pip install TikTokApi`)
- Required libraries:
  ```bash
  pip install requests colorama
  ```
## 🔧 Setup

Clone this repo or copy the script
Install dependencies (see above)
Gather TikTok credentials:
    Get your ms_token and cookies from browser dev tools while logged into TikTok.
    Set them in the script:
        ms_token = "your_token_here"
        Fill in EXTRA_COOKIES with your session values

## 🚀 How to Use

```bash
python remover.py
```

Choose from the menu:
    Fetch reposts from a TikTok user
    → Enter the TikTok username
    → Saves all reposts to a file named reposts_<username>.json

    Load reposts from file
    → Loads reposts from reposts_<username>.json
    → Useful before deletion without refetching

    Delete reposts
    → Deletes all but the latest N reposts
    → Prompts you for how many to keep

## 🧠 How It Works

    Uses the TikTok Web API endpoints (/api/repost/item_list/ and /tiktok/v1/upvote/delete)

    Authenticates via browser session cookies

    Uses TikTokApi to handle session management and URL signing

    Logs actions with timestamps, progress, and colored output


## ⚠️ Disclaimer

This tool uses internal web API endpoints and requires browser cookies. TikTok may change their API at any time or take action against automated scripts. Use responsibly and at your own risk.
