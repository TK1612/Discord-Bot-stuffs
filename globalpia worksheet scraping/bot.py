import discord
from discord.ext import commands
import requests
from bs4 import BeautifulSoup
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import re
import math
import asyncio
import urllib.parse

# ==========================================
# 1. GOOGLE SHEETS CONFIGURATION
# ==========================================
scopes = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

try:
    credentials = Credentials.from_service_account_file(
        'lilith-491518-516ebf3954f3.json',
        scopes=scopes
    )
    gc = gspread.authorize(credentials)
except Exception as e:
    print(f"Error loading Google Credentials: {e}")

# SPREADSHEET LINKS
SHEET_1_URL = "STYLESHEET 1 FOR MAIN"
SHEET_2_URL = "STYLESHEET 2 FOR MERGING, PERSONAL AND UPDATES"

# EXACT TAB NAMES FOR SPREADSHEET 1
TAB_MAIN = "Global Novelpia - Main"
TAB_LILITH = "Global Novelpia - Lilith"

# ==========================================
# 2. DISCORD BOT SETUP
# ==========================================
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# ==========================================
# 3. TAG DICTIONARIES & HELPER FUNCTIONS
# ==========================================
CATEGORY_MAP = {
    1: "Fantasy",
    2: "Martial Arts",
    3: "Modern",
    6: "Romance",
    7: "Historical",
    8: "Sports",
    9: "Sci-Fi",
    10: "Miscellaneous",
    12: "Modern Fantasy",
    14: "Horror"
}

MASTER_TAGS = {}


def create_progress_bar(current, total, length=20):
    if total == 0: return "`[░░░░░░░░░░░░░░░░░░░░]` 0%"
    filled = int(length * current // total)
    bar = '█' * filled + '░' * (length - filled)
    percent = int((current / total) * 100)
    return f"`[{bar}]` {percent}% ({current}/{total})"


async def fetch_detail_tags(novel_no, fallback_cate_id=None):
    """Pings the specific detail API and merges the Category Name with detail tags."""
    url = f"https://api-global.novelpia.com/v1/novel?novel_no={novel_no}"
    headers = {'User-Agent': 'Mozilla/5.0'}

    tags = []

    if fallback_cate_id is not None:
        cate_name = CATEGORY_MAP.get(int(fallback_cate_id)) or CATEGORY_MAP.get(str(fallback_cate_id))
        if cate_name:
            tags.append(f"#{cate_name.strip()}")

    try:
        res = await asyncio.to_thread(requests.get, url, headers=headers)
        data = res.json()

        if data.get('code') == '0000':
            result = data.get('result', {})
            tag_list = result.get('tag_list', [])

            if not tags:
                detail_cate_id = result.get('novel', {}).get('flag_cate')
                detail_cate_name = CATEGORY_MAP.get(detail_cate_id)
                if detail_cate_name:
                    tags.append(f"#{detail_cate_name.strip()}")

            for t in tag_list:
                name = None
                if isinstance(t, dict):
                    name = t.get('tag_name')
                elif isinstance(t, int) and t in MASTER_TAGS:
                    name = MASTER_TAGS[t]

                if name:
                    fmt = f"#{name.replace('#', '').strip()}"
                    if fmt not in tags: tags.append(fmt)

        return " ".join(tags) if tags else "#Unknown"
    except Exception:
        return " ".join(tags) if tags else "#Unknown"


def parse_novel_json(novel_data):
    novel = novel_data.get('novel') if 'novel' in novel_data else novel_data
    if not novel: return None

    if novel.get('novel_locale') != 'ko' or novel.get('flag_contest') == 1:
        return None

    title = novel.get('novel_name', 'Unknown Title')
    novel_no = novel.get('novel_no', '')
    url = f"https://global.novelpia.com/novel/{novel_no}"

    flag_comp = novel.get('flag_complete', 0)
    flag_live = novel.get('flag_live', 0)

    status = "Incomplete"
    if flag_comp == 1:
        status = "Complete"
    elif flag_live == 2:
        status = "Discontinued"
    elif flag_live == 1 or flag_comp in [3, 4]:
        status = "Being Edited"

    raw_date = novel.get('new_epi_open_dt', '')
    try:
        parsed_date = datetime.strptime(raw_date, "%Y-%m-%d %H:%M:%S")
        formatted_date = parsed_date.strftime("%d-%b-%Y")
    except:
        formatted_date = "Unknown Date"

    flag_cate_id = novel.get('flag_cate')

    # Pass the Category ID in the Genres slot temporarily
    return [title, "To Obtain", url, formatted_date, None, status, None, None, None, flag_cate_id]


def get_latest_chapter_date(html_text, soup):
    date_matches = re.findall(r'(\d{4}-\d{2}-\d{2})\s\d{2}:\d{2}:\d{2}', html_text)
    if date_matches:
        latest_date_str = sorted(date_matches, reverse=True)[0]
        try:
            parsed = datetime.strptime(latest_date_str, "%Y-%m-%d")
            return parsed.strftime("%d-%b-%Y")
        except:
            pass

    date_tags = soup.find_all('div', class_='update-date')
    if date_tags:
        raw_date = date_tags[0].get_text(strip=True).lower()
        if any(x in raw_date for x in ["min", "hr", "hour", "hrs", "sec", "up"]):
            return datetime.now().strftime("%d-%b-%Y")
        elif "day" in raw_date:
            days_ago_match = re.search(r'\d+', raw_date)
            if days_ago_match:
                days_ago = int(days_ago_match.group())
                return (datetime.now() - timedelta(days=days_ago)).strftime("%d-%b-%Y")
        else:
            try:
                return datetime.strptime(raw_date.title(), "%b %d, %Y").strftime("%d-%b-%Y")
            except:
                return raw_date.title()
    return "Unknown Date"


def scrape_single_novelpia(url):
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(url, headers=headers)
        if response.status_code != 200: return {"error": f"Failed. Status: {response.status_code}"}
    except Exception as e:
        return {"error": f"Network error: {str(e)}"}

    soup = BeautifulSoup(response.text, 'html.parser')
    html_lower = response.text.lower()

    badges_container = soup.find('div', class_='nv-stat-badge')
    badge_text = badges_container.get_text(separator=' ', strip=True).lower() if badges_container else ""
    if "exclusive" in badge_text or "challenge" in badge_text or re.search(r'>\s*exclusive\s*<',
                                                                           html_lower) or re.search(
            r'>\s*challenge\s*<', html_lower):
        return {"error": "Skipped: Contains 'Exclusive' or 'Challenge' tags."}
    if "k-premium" not in badge_text and "k-prem" not in badge_text:
        if not re.search(r'>\s*k-prem(ium)?\.?\s*<', html_lower):
            return {"error": "Skipped: NOT tagged as K-Premium."}

    status = "Incomplete"
    if any(x in badge_text for x in ["completed", "complete"]):
        status = "Complete"
    elif any(x in badge_text for x in ["discontinued", "disc."]):
        status = "Discontinued"
    elif any(x in badge_text for x in ["being edited", "editing"]):
        status = "Being Edited"
    else:
        info_section = soup.find('section', class_='nv-info-section')
        info_text = info_section.get_text(separator=' ', strip=True).lower() if info_section else ""
        if any(x in info_text for x in ["completed", "complete"]):
            status = "Complete"
        elif any(x in info_text for x in ["discontinued", "disc."]):
            status = "Discontinued"
        elif any(x in info_text for x in ["being edited", "editing"]):
            status = "Being Edited"
        else:
            if '"discontinued"' in html_lower or '>discontinued<' in html_lower:
                status = "Discontinued"
            elif '"being edited"' in html_lower or '>being edited<' in html_lower:
                status = "Being Edited"
            elif '"completed"' in html_lower or '>completed<' in html_lower:
                status = "Complete"

    title_tag = soup.find('div', class_='nv-tit')
    title = title_tag.get_text(strip=True) if title_tag else "Unknown Title"
    last_date = get_latest_chapter_date(response.text, soup)

    genre_list = []
    tag_matches = re.findall(r'search_type=tag(?:&|&amp;|\\u0026)search_val=([^&"\'><\\]+)', response.text)

    for t in tag_matches:
        clean_tag = urllib.parse.unquote(t).replace('+', ' ').strip()
        if clean_tag:
            formatted_tag = f"#{clean_tag.replace('#', '')}"
            if formatted_tag not in genre_list:
                genre_list.append(formatted_tag)

    genres = " ".join(genre_list)

    return {
        'English Name': title, 'Status': 'To Obtain', 'Global Link': url,
        'Last Update Date': last_date, 'Download Date': None, 'Status.1': status,
        'Drive Link': None, 'PixelDrain Link': None, 'Mega Link': None, 'Genres': genres
    }


# ==========================================
# 4. BOT COMMANDS
# ==========================================
@bot.event
async def on_ready():
    print(f'✅ Logged in as {bot.user.name}')
    print('📥 Downloading Master Tag Dictionary...')
    try:
        res = requests.get("https://api-global.novelpia.com/v1/novel/tag/list", headers={'User-Agent': 'Mozilla/5.0'})
        if res.status_code == 200:
            tag_data = res.json().get('result', [])
            for t in tag_data:
                MASTER_TAGS[t.get('tag_no')] = t.get('tag_name')
            print(f'✅ Memorized {len(MASTER_TAGS)} tags successfully!')
    except Exception as e:
        print(f'⚠️ Failed to load master tags: {e}')
    print('✅ Bot is ready to scan!')


@bot.command(name='uploadgloballist')
async def upload_global_list(ctx):
    """Fetches novels via API, WIPES Spreadsheet 1, and rewrites everything."""
    msg = await ctx.send("🔄 **Starting process...**\n*Fetching full API list...*")

    base_api_url = "https://api-global.novelpia.com/v1/novel/list?flag_complete=&sort_col=new_epi_open_dt&flag_cate=&flag_detail_trans=&content_type=2&is_indie_to_premium=&rows=30&page="
    headers = {'User-Agent': 'Mozilla/5.0'}

    try:
        initial_response = requests.get(base_api_url + "1", headers=headers).json()
        total_novels = initial_response['result']['total_cnt']
        total_pages = math.ceil(total_novels / 30)

        all_scraped_rows = []
        for page in range(1, total_pages + 1):
            response = requests.get(base_api_url + str(page), headers=headers).json()
            novels_list = response['result']['list']
            for item in novels_list:
                row_data = parse_novel_json(item)
                if row_data is not None:
                    all_scraped_rows.append(row_data)

            if page % 5 == 0 or page == total_pages:
                progress_text = create_progress_bar(page, total_pages)
                await msg.edit(content=f"📚 Fetching database...\n{progress_text}")
            await asyncio.sleep(0.2)

        total_valid = len(all_scraped_rows)
        for i, row in enumerate(all_scraped_rows):
            novel_id = re.search(r'/novel/(\d+)', row[2]).group(1)
            tags = await fetch_detail_tags(novel_id, fallback_cate_id=row[9])
            all_scraped_rows[i][9] = tags

            if i % 10 == 0 or i == total_valid - 1:
                await msg.edit(content=f"🏷️ Merging Categories & Tags...\n{create_progress_bar(i + 1, total_valid)}")
            await asyncio.sleep(0.1)

        await msg.edit(content=f"✅ Data fetched! **Wiping** and rewriting Spreadsheet 1...")

        sheet1 = gc.open_by_url(SHEET_1_URL)
        table_header = ["English Name", "Status", "Global Link", "Last Update Date", "Download Date", "Status.1",
                        "Drive Link", "PixelDrain Link", "Mega Link", "Genres"]

        for tab_name in [TAB_MAIN, TAB_LILITH]:
            try:
                worksheet = sheet1.worksheet(tab_name)
                worksheet.clear()
                worksheet.append_rows([table_header] + all_scraped_rows, value_input_option='USER_ENTERED')
            except Exception as tab_err:
                pass

        await msg.edit(
            content=f"✅ **Process Complete!** Both tabs cleanly replaced with exactly {len(all_scraped_rows)} K-Premium novels.")

    except Exception as e:
        await msg.edit(content=f"❌ **Error:** Check the bot console.")


@bot.command(name='updatelist')
async def update_list(ctx):
    """[SEARCH & ADD] Fetches novels via API, searches the sheet, and ONLY appends missing ones with correct tags."""
    msg = await ctx.send("🔄 **Searching API for new novels...**")

    base_api_url = "https://api-global.novelpia.com/v1/novel/list?flag_complete=&sort_col=new_epi_open_dt&flag_cate=&flag_detail_trans=&content_type=2&is_indie_to_premium=&rows=30&page="
    headers = {'User-Agent': 'Mozilla/5.0'}

    try:
        initial_response = requests.get(base_api_url + "1", headers=headers).json()
        total_novels = initial_response['result']['total_cnt']
        total_pages = math.ceil(total_novels / 30)

        all_scraped_rows = []
        for page in range(1, total_pages + 1):
            response = requests.get(base_api_url + str(page), headers=headers).json()
            novels_list = response['result']['list']
            for item in novels_list:
                row_data = parse_novel_json(item)
                if row_data is not None:
                    all_scraped_rows.append(row_data)

            if page % 10 == 0 or page == total_pages:
                progress_text = create_progress_bar(page, total_pages)
                await msg.edit(content=f"📚 Scanning API for missing novels...\n{progress_text}")
            await asyncio.sleep(0.2)

        sheet1 = gc.open_by_url(SHEET_1_URL)
        inserted_counts = {}

        for tab_name in [TAB_MAIN, TAB_LILITH]:
            try:
                worksheet = sheet1.worksheet(tab_name)
                existing_names = worksheet.col_values(1)

                rows_to_insert = []
                new_rows_raw = [r for r in all_scraped_rows if r[0] not in existing_names]

                if new_rows_raw:
                    await msg.edit(
                        content=f"🏷️ Fetching correct tags for {len(new_rows_raw)} new novels in {tab_name}...")
                    for i, row in enumerate(new_rows_raw):
                        novel_id = re.search(r'/novel/(\d+)', row[2]).group(1)
                        tags = await fetch_detail_tags(novel_id, fallback_cate_id=row[9])

                        row_copy = list(row)
                        row_copy[9] = tags  # Replace category ID with formatted tags
                        rows_to_insert.append(row_copy)
                        await asyncio.sleep(0.1)

                    worksheet.append_rows(rows_to_insert, value_input_option='USER_ENTERED')

                inserted_counts[tab_name] = len(rows_to_insert)
            except:
                pass

        if sum(inserted_counts.values()) == 0:
            await msg.edit(content="✅ **Update Complete!** No new novels found. You are fully caught up.")
        else:
            await msg.edit(
                content=f"✅ **Update Complete!** Appended **{inserted_counts.get(TAB_MAIN, 0)}** new novels to `{TAB_MAIN}` and **{inserted_counts.get(TAB_LILITH, 0)}** to `{TAB_LILITH}`.")

    except Exception as e:
        await msg.edit(content=f"❌ **Error during update:** Check the bot console.")


@bot.command(name='uploadglobal')
async def upload_global(ctx, url: str):
    """Scrapes a single novel and appends the data to BOTH tabs in Spreadsheet 1."""
    if "global.novelpia.com/novel/" not in url: return await ctx.send("❌ Please provide a valid Global Novelpia link.")

    msg = await ctx.send(f"🔍 Scraping data from `{url}`...")
    data = scrape_single_novelpia(url)
    if "error" in data: return await msg.edit(content=f"❌ {data['error']}")

    row_to_insert = [
        data['English Name'], data['Status'], data['Global Link'],
        data['Last Update Date'], data['Download Date'], data['Status.1'],
        data['Drive Link'], data['PixelDrain Link'], data['Mega Link'], data['Genres']
    ]

    try:
        sheet1 = gc.open_by_url(SHEET_1_URL)
        added_to = []
        for tab_name in [TAB_MAIN, TAB_LILITH]:
            try:
                worksheet = sheet1.worksheet(tab_name)
                if data['English Name'] not in worksheet.col_values(1):
                    worksheet.append_row(row_to_insert, value_input_option='USER_ENTERED')
                    added_to.append(tab_name)
            except:
                pass

        if added_to:
            await msg.edit(content=f"✅ Added **{data['English Name']}**!\nTags: {data['Genres']}")
        else:
            await msg.edit(content=f"⚠️ **{data['English Name']}** already exists in both tabs!")
    except Exception as e:
        await msg.edit(content=f"❌ Error writing to Google Sheets. Check console.")


@bot.command(name='merge2')
async def merge2(ctx):
    """Merges S2 into Main Tab and Lilith Tab. Ignores S2's Drive Link for BOTH tabs. Secures Genres."""
    msg = await ctx.send(f"🔄 **Starting Merge...** Integrating Spreadsheet 2 into both tabs...")
    try:
        sheet1 = gc.open_by_url(SHEET_1_URL)
        sheet2 = gc.open_by_url(SHEET_2_URL)

        ws_main = sheet1.worksheet(TAB_MAIN)
        ws_lilith = sheet1.worksheet(TAB_LILITH)
        ws2 = sheet2.sheet1

        data_main = ws_main.get('A1:Z', value_render_option='FORMULA')
        data_lilith = ws_lilith.get('A1:Z', value_render_option='FORMULA')
        data2 = ws2.get('A1:Z', value_render_option='FORMULA')

        header = data_main[0] if data_main else (data2[0] if data2 else [])
        rows1_main = data_main[1:] if len(data_main) > 1 else []
        rows1_lilith = data_lilith[1:] if len(data_lilith) > 1 else []
        rows2 = data2[1:] if len(data2) > 1 else []

        main_dict = {str(row[0]).strip(): row for row in rows1_main if len(row) > 0 and str(row[0]).strip()}
        lilith_dict = {str(row[0]).strip(): row for row in rows1_lilith if len(row) > 0 and str(row[0]).strip()}

        s2_names = {str(row[0]).strip() for row in rows2 if len(row) > 0 and str(row[0]).strip()}

        final_data_main = [header]
        final_data_lilith = [header]

        for r in rows2:
            if not r or not str(r[0]).strip(): continue
            title = str(r[0]).strip()

            r_base = r + [""] * (10 - len(r))

            status_val = "Incomplete"
            check_text = (str(r_base[5]) + " " + str(r_base[7])).lower()
            if "discontinued" in check_text or "disc" in check_text:
                status_val = "Discontinued"
            elif "edited" in check_text or "editing" in check_text:
                status_val = "Being Edited"
            elif "completed" in check_text or "complete" in check_text:
                if "incomplete" not in check_text: status_val = "Complete"
            r_base[5] = status_val

            r_main = list(r_base)
            m_match = main_dict.get(title)

            if m_match and len(m_match) >= 10:
                r_main[6] = m_match[6]
                if not str(r_main[9]).strip():
                    r_main[9] = m_match[9]
            else:
                r_main[6] = ""

            final_data_main.append(r_main[:10])

            r_lilith = list(r_base)
            l_match = lilith_dict.get(title)

            if l_match and len(l_match) >= 10:
                r_lilith[6] = l_match[6]
                if not str(r_lilith[9]).strip():
                    r_lilith[9] = l_match[9]
            else:
                r_lilith[6] = ""

            final_data_lilith.append(r_lilith[:10])

        for title, row in main_dict.items():
            if title not in s2_names:
                row = row + [""] * (10 - len(row))
                final_data_main.append(row[:10])

        for title, row in lilith_dict.items():
            if title not in s2_names:
                row = row + [""] * (10 - len(row))
                final_data_lilith.append(row[:10])

        ws_main.clear()
        ws_main.append_rows(final_data_main, value_input_option='USER_ENTERED')

        ws_lilith.clear()
        ws_lilith.append_rows(final_data_lilith, value_input_option='USER_ENTERED')

        await msg.edit(
            content=f"✅ **Merge Successful!**\n- `{TAB_MAIN}` and `{TAB_LILITH}` updated.\n- Spreadsheet 2 Drive Links were entirely ignored (Spreadsheet 1 links kept).")

    except Exception as e:
        await msg.edit(content="❌ Error during merge. Check bot console.")


# ==========================================
# RUN THE BOT
# ==========================================
DISCORD_TOKEN = 'TOKEN'

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
