import os
import discord
import asyncio
import gspread
import difflib
import json
import aiohttp
from datetime import datetime
from google.oauth2.service_account import Credentials
from discord.ext import commands
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ==========================================
# 1. CONFIGURATION & CREDENTIALS
# ==========================================
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

CREDENTIALS_FILE = os.getenv('GOOGLE_CREDENTIALS_FILE', 'credentials.json')
SPREADSHEET_ID = os.getenv('SPREADSHEET_ID')
TRACKING_FILE = 'updatedtitles.json'
PIXELDRAIN_API_KEY = os.getenv('PIXELDRAIN_API_KEY')
BASE_UPLOAD_FOLDER = os.getenv('BASE_UPLOAD_FOLDER', './uploads')

# Initialize Google Sheets
try:
    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
    gc = gspread.authorize(creds)
except Exception as e:
    print(f"❌ Failed to load Google Credentials: {e}")

# ==========================================
# 2. JSON TRACKING & GOOGLE SHEETS LOGIC
# ==========================================
def load_tracked_titles() -> dict:
    if os.path.exists(TRACKING_FILE):
        try:
            with open(TRACKING_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}
    return {}

def save_tracked_title(filename: str):
    titles = load_tracked_titles()
    titles[filename] = datetime.now().strftime('%Y-%m-%d')
    with open(TRACKING_FILE, 'w', encoding='utf-8') as f:
        json.dump(titles, f, indent=4, ensure_ascii=False)

def find_best_match_row(filename: str, column_a_values: list) -> int:
    base_name = os.path.splitext(filename)[0]
    clean_target = base_name.replace('_', ' ').replace('-', ' ').strip().lower()
    
    clean_sheet_names = [val.replace('_', ' ').replace('-', ' ').strip().lower() for val in column_a_values]
    matches = difflib.get_close_matches(clean_target, clean_sheet_names, n=1, cutoff=0.75)
    
    if matches:
        return clean_sheet_names.index(matches[0]) + 1 
    return None

def update_google_sheet_sync(filename: str, link: str):
    try:
        sheet = gc.open_by_key(SPREADSHEET_ID).sheet1 
        TRANSFER_LINK_COL = 8 # Column H
        col_a_values = sheet.col_values(1)
        
        target_row = find_best_match_row(filename, col_a_values)
        
        if target_row:
            sheet.update_cell(target_row, TRANSFER_LINK_COL, link)
            print(f"✅ Sheet Updated: Overwrote/Added link for '{filename}' in row {target_row}.")
        else:
            clean_new_name = os.path.splitext(filename)[0].replace('_', ' ')
            new_row = [clean_new_name, "", "", "", "", "", "", link]
            sheet.append_row(new_row)
            print(f"⚠️ Appended '{filename}' as a new row.")
            
    except Exception as e:
        print(f"❌ Google Sheets Error for {filename}: {e}")

# ==========================================
# 3. DISCORD & PIXELDRAIN API LOGIC
# ==========================================
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

async def upload_to_pixeldrain(file_path: str) -> str:
    url = "https://pixeldrain.com/api/file"
    try:
        auth = aiohttp.BasicAuth(login='', password=PIXELDRAIN_API_KEY)
        
        async with aiohttp.ClientSession(auth=auth) as session:
            with open(file_path, 'rb') as f:
                data = aiohttp.FormData(quote_fields=False)
                data.add_field('file', f, filename=os.path.basename(file_path))
                
                timeout = aiohttp.ClientTimeout(total=300) 
                async with session.post(url, data=data, timeout=timeout) as response:
                    if response.status in [200, 201]:
                        result = await response.json()
                        if result.get("success"):
                            return f"https://pixeldrain.com/u/{result['id']}"
                    
                    print(f"Pixeldrain Error {response.status}: {await response.text()}")
                    return None
                    
    except Exception as e:
        print(f"Error during Pixeldrain API call for {os.path.basename(file_path)}: {e}")
        return None

async def upload_with_retry(file_path: str, status_message=None, max_retries: int = 2) -> str:
    for attempt in range(max_retries + 1):
        link = await upload_to_pixeldrain(file_path)
        if link: return link
        
        print(f"Attempt {attempt + 1} failed for {os.path.basename(file_path)}.")
        if attempt < max_retries:
            if status_message:
                try:
                    await status_message.edit(content=status_message.content + f"\n⚠️ *Upload failed. Retrying in 5 seconds ({attempt + 1}/{max_retries})...*")
                except:
                    pass
            await asyncio.sleep(5) 
    return None

def generate_progress_bar(current: int, total: int, length: int = 15) -> str:
    if total == 0: return ""
    percent = current / total
    filled_length = int(length * percent)
    bar = '█' * filled_length + '░' * (length - filled_length)
    return f"`[{bar}]` {current}/{total}"

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user} - Ready to process files!')

# ==========================================
# 4. BOT COMMANDS
# ==========================================

@bot.command()
async def upload(ctx, *, filename: str):
    file_path = os.path.join(BASE_UPLOAD_FOLDER, filename)

    if not os.path.isfile(file_path):
        return await ctx.send(f"❌ Could not find `{filename}` in the configured directory.")

    message = await ctx.send(f"⏳ Uploading `{filename}` to Pixeldrain...")
    link = await upload_with_retry(file_path, status_message=message)

    if link:
        await message.edit(content=f"**{filename}**\n🔗 {link}\n📝 *Updating Sheet...*")
        await asyncio.to_thread(update_google_sheet_sync, filename, link)
        save_tracked_title(filename) 
        await message.edit(content=f"**{filename}**\n🔗 {link}\n✅ *Added to Sheet & Tracker!*")
    else:
        await message.edit(content="❌ The upload failed after all retries.")

@bot.command()
async def uploadfolder(ctx, *, foldername: str):
    target_folder = os.path.join(BASE_UPLOAD_FOLDER, foldername)

    if not os.path.isdir(target_folder):
        return await ctx.send(f"❌ Could not find folder `{foldername}`.")

    files_to_upload = [f for f in os.listdir(target_folder) if os.path.isfile(os.path.join(target_folder, f))]
    total_files = len(files_to_upload)

    if total_files == 0: return await ctx.send("⚠️ Folder is empty.")

    status_message = await ctx.send(f"📂 **Forced Upload** of {total_files} files...\n{generate_progress_bar(0, total_files)}")
    results = []

    for index, filename in enumerate(files_to_upload):
        await status_message.edit(content=f"⬆️ Uploading: `{filename}`\n{generate_progress_bar(index, total_files)}")
        link = await upload_with_retry(os.path.join(target_folder, filename), status_message=status_message)
        
        if link:
            results.append(f"**{filename}**\n🔗 {link}")
            await asyncio.to_thread(update_google_sheet_sync, filename, link)
            save_tracked_title(filename) 
        else:
            results.append(f"**{filename}**\n❌ *Upload failed.*")

    await status_message.edit(content=f"✅ **Upload Complete!**\n{generate_progress_bar(total_files, total_files)}")
    
    chunk = ""
    for result in results:
        if len(chunk) + len(result) > 1900:
            await ctx.send(chunk)
            chunk = result + "\n\n"
        else:
            chunk += result + "\n\n"
    if chunk: await ctx.send(chunk)

@bot.command()
async def scan(ctx, *, foldername: str):
    target_folder = os.path.join(BASE_UPLOAD_FOLDER, foldername)

    if not os.path.isdir(target_folder):
        return await ctx.send(f"❌ Could not find folder `{foldername}`.")

    all_files = [f for f in os.listdir(target_folder) if os.path.isfile(os.path.join(target_folder, f))]
    tracked_titles = load_tracked_titles()
    
    files_to_upload = [f for f in all_files if f not in tracked_titles]
    total_files = len(files_to_upload)

    if total_files == 0:
        return await ctx.send(f"✅ **All caught up!** No new files found in `{foldername}` to upload.")

    status_message = await ctx.send(f"🔎 **Scan Complete**: Found {total_files} new files to upload...\n{generate_progress_bar(0, total_files)}")
    results = []

    for index, filename in enumerate(files_to_upload):
        await status_message.edit(content=f"⬆️ Uploading: `{filename}`\n{generate_progress_bar(index, total_files)}")
        link = await upload_with_retry(os.path.join(target_folder, filename), status_message=status_message)
        
        if link:
            results.append(f"**{filename}**\n🔗 {link}")
            await asyncio.to_thread(update_google_sheet_sync, filename, link)
            save_tracked_title(filename) 
        else:
            results.append(f"**{filename}**\n❌ *Upload failed.*")

    await status_message.edit(content=f"✅ **Scan & Upload Complete!**\n{generate_progress_bar(total_files, total_files)}")
    
    chunk = ""
    for result in results:
        if len(chunk) + len(result) > 1900:
            await ctx.send(chunk)
            chunk = result + "\n\n"
        else:
            chunk += result + "\n\n"
    if chunk: await ctx.send(chunk)

if __name__ == "__main__":
    DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
    if not DISCORD_TOKEN:
        print("❌ Error: DISCORD_TOKEN is missing in the environment.")
    else:
        bot.run(DISCORD_TOKEN)
